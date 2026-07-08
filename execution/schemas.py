"""
Execution Layer Schemas
=======================

Data contracts for tool execution results, safety checks, and
stateful execution lifecycle tracking.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """Standardised return value from every tool handler.

    Attributes
    ----------
    success : bool
        Whether the tool executed without error.
    tool : str
        The canonical tool name that was executed.
    message : str
        Human-readable summary of what happened.
    output : str | None
        Raw stdout/stderr from the underlying command, if any.
    execution_time_ms : int
        Wall-clock execution time in milliseconds.
    requires_confirmation : bool
        If True, the command was blocked by the safety layer
        and needs explicit user approval before running.
    """

    success: bool = True
    tool: str = ""
    message: str = ""
    output: str | None = None
    execution_time_ms: int = 0
    requires_confirmation: bool = False
    confirmation_id: str | None = None

    # ── Stateful engine fields (added in feature/stateful-execution-engine) ──
    # Reflects the StepStatus value at the time this result was recorded.
    # Defaults to "success" or "failure" to stay compatible with existing callers.
    state: str = ""               # e.g. "success", "failure", "recovery"
    attempts: int = 1             # number of execution attempts (1 = first try)
    recovery_used: bool = False   # True if a recovery strategy was invoked
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "success": self.success,
            "tool": self.tool,
            "message": self.message,
            "output": self.output,
            "execution_time_ms": self.execution_time_ms,
            "requires_confirmation": self.requires_confirmation,
            # Stateful engine fields
            "state": self.state or ("success" if self.success else "failure"),
            "attempts": self.attempts,
            "recovery_used": self.recovery_used,
            "metadata": self.metadata,
        }
        if self.confirmation_id:
            d["confirmation_id"] = self.confirmation_id
        return d


class ExecutionTimer:
    """Context manager that measures elapsed wall-clock milliseconds."""

    def __init__(self) -> None:
        self.start: float = 0.0
        self.elapsed_ms: int = 0

    def __enter__(self) -> "ExecutionTimer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_ms = int((time.perf_counter() - self.start) * 1000)
