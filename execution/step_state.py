"""
Step State
==========

Defines the execution step lifecycle used by the stateful execution engine.

Lifecycle diagram::

    PENDING
      ↓
    EXECUTING
      ↓
    WAITING          ← waits for application/window/element readiness
      ↓
    VERIFYING        ← checks that the step achieved its intended outcome
      ↓
    SUCCESS          ← happy path ends here

    If verification fails:

    VERIFYING
      ↓
    RECOVERY         ← attempt automated recovery (relaunch, focus, etc.)
      ↓
    RETRY            ← re-execute the step
      ↓
    VERIFYING        ← verify the retry result
      ↓
    SUCCESS | FAILURE

Each step may be retried up to ``max_retries`` times before being marked FAILURE.
A FAILURE status halts the remaining plan.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from execution.schemas import ExecutionResult


# ---------------------------------------------------------------------------
# Lifecycle Enum
# ---------------------------------------------------------------------------

class StepStatus(Enum):
    """Possible lifecycle states of a single execution step."""
    PENDING    = "pending"
    EXECUTING  = "executing"
    WAITING    = "waiting"
    VERIFYING  = "verifying"
    RECOVERY   = "recovery"
    RETRY      = "retry"
    SUCCESS    = "success"
    FAILURE    = "failure"
    SKIPPED    = "skipped"   # reserved for future conditional execution


# ---------------------------------------------------------------------------
# Per-step record
# ---------------------------------------------------------------------------

@dataclass
class StepRecord:
    """Mutable state tracker for a single plan step.

    Attributes
    ----------
    step_index:
        Zero-based position of this step in the plan.
    tool:
        Canonical tool name (e.g. ``"launch_application"``).
    args:
        Tool argument dictionary.
    wait_for:
        Optional readiness condition to wait for after execution
        (e.g. ``"window_ready"``, ``"process_running"``).
    timeout:
        Optional timeout in seconds for the wait phase.
    requires:
        Human-readable label of what this step depends on
        (e.g. ``"Spotify Ready"``). Used for logging/UI only.
    max_retries:
        Maximum number of recovery-retry cycles before marking FAILURE.
    status:
        Current lifecycle state.
    attempts:
        Number of execution attempts made (1-based; 1 = first try).
    result:
        Most recent :class:`ExecutionResult` from the handler.
    started_at:
        Epoch timestamp when execution began (set on first EXECUTING transition).
    finished_at:
        Epoch timestamp when a terminal state (SUCCESS/FAILURE/SKIPPED) was reached.
    error_message:
        Last error or failure message, if any.
    metadata:
        Arbitrary extra info (recovery strategy used, wait elapsed time, etc.).
    """
    step_index: int
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    wait_for: Optional[str] = None
    timeout: Optional[float] = None
    requires: Optional[str] = None
    max_retries: int = 2

    # Mutable runtime state
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    result: Optional[ExecutionResult] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Lifecycle helpers ──────────────────────────────────────────────────

    def mark_executing(self) -> None:
        """Transition to EXECUTING and record start time."""
        self.status = StepStatus.EXECUTING
        self.attempts += 1
        if self.started_at == 0.0:
            self.started_at = time.time()

    def mark_waiting(self) -> None:
        """Transition to WAITING (between execution and verification)."""
        self.status = StepStatus.WAITING

    def mark_verifying(self) -> None:
        """Transition to VERIFYING."""
        self.status = StepStatus.VERIFYING

    def mark_recovery(self) -> None:
        """Transition to RECOVERY."""
        self.status = StepStatus.RECOVERY

    def mark_retry(self) -> None:
        """Transition to RETRY and increment attempt counter."""
        self.status = StepStatus.RETRY
        self.attempts += 1

    def mark_success(self, result: ExecutionResult) -> None:
        """Transition to SUCCESS and store the final result."""
        self.status = StepStatus.SUCCESS
        self.result = result
        self.finished_at = time.time()

    def mark_failure(self, message: str) -> None:
        """Transition to FAILURE."""
        self.status = StepStatus.FAILURE
        self.error_message = message
        self.finished_at = time.time()

    def mark_skipped(self, reason: str) -> None:
        """Transition to SKIPPED."""
        self.status = StepStatus.SKIPPED
        self.error_message = reason
        self.finished_at = time.time()

    # ── Convenience queries ────────────────────────────────────────────────

    @property
    def is_terminal(self) -> bool:
        """True if the step is in a terminal state (no further transitions possible)."""
        return self.status in (StepStatus.SUCCESS, StepStatus.FAILURE, StepStatus.SKIPPED)

    @property
    def can_retry(self) -> bool:
        """True if another recovery-retry cycle is allowed."""
        # attempts tracks total executions; first try is attempt 1
        # retries = attempts - 1
        return (self.attempts - 1) < self.max_retries

    @property
    def elapsed_ms(self) -> int:
        """Wall-clock time from start to finish (or now if not finished) in ms."""
        if self.started_at == 0.0:
            return 0
        end = self.finished_at if self.finished_at > 0 else time.time()
        return int((end - self.started_at) * 1000)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the record to a plain dictionary."""
        return {
            "step_index": self.step_index,
            "tool": self.tool,
            "status": self.status.value,
            "attempts": self.attempts,
            "elapsed_ms": self.elapsed_ms,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "result": self.result.to_dict() if self.result else None,
        }


# ---------------------------------------------------------------------------
# Plan-level execution context
# ---------------------------------------------------------------------------

@dataclass
class ExecutionContext:
    """Holds the runtime state for an entire execution plan.

    Attributes
    ----------
    records:
        Ordered list of :class:`StepRecord` objects, one per plan step.
    plan_started_at:
        Epoch timestamp of when execution began.
    current_index:
        Index of the step currently being executed.
    """
    records: list[StepRecord] = field(default_factory=list)
    plan_started_at: float = field(default_factory=time.time)
    current_index: int = 0

    @classmethod
    def from_plan(cls, plan) -> "ExecutionContext":
        """Build an :class:`ExecutionContext` from an :class:`ExecutionPlan`.

        Parameters
        ----------
        plan:
            An ``agentic.schemas.ExecutionPlan`` instance.

        Returns
        -------
        ExecutionContext
        """
        records = []
        for i, step in enumerate(plan.steps):
            records.append(StepRecord(
                step_index=i,
                tool=step.tool,
                args=step.args,
                wait_for=getattr(step, "wait_for", None),
                timeout=getattr(step, "timeout", None),
                requires=getattr(step, "requires", None),
                max_retries=getattr(step, "max_retries", 2),
            ))
        return cls(records=records)

    # ── Convenience accessors ──────────────────────────────────────────────

    @property
    def current_record(self) -> Optional[StepRecord]:
        """The step currently being executed, or None if out of range."""
        if 0 <= self.current_index < len(self.records):
            return self.records[self.current_index]
        return None

    @property
    def all_succeeded(self) -> bool:
        """True if every step has reached SUCCESS."""
        return all(r.status == StepStatus.SUCCESS for r in self.records)

    @property
    def failed_record(self) -> Optional[StepRecord]:
        """Return the first record in FAILURE state, if any."""
        for r in self.records:
            if r.status == StepStatus.FAILURE:
                return r
        return None

    @property
    def total_elapsed_ms(self) -> int:
        """Total wall-clock time for the whole plan in ms."""
        return int((time.time() - self.plan_started_at) * 1000)

    def advance(self) -> None:
        """Move the current index to the next step."""
        self.current_index += 1

    def to_summary(self) -> list[dict[str, Any]]:
        """Return a list of step summary dicts suitable for API responses."""
        return [r.to_dict() for r in self.records]
