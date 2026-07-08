"""
Agentic Layer Schemas
=====================

Data contracts for the Qwen-based planning and execution pipeline.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionStep:
    """A single tool execution step parsed from the LLM.

    Attributes
    ----------
    tool:
        Canonical tool name (e.g. ``"launch_application"``).
    args:
        Tool argument dictionary.
    wait_for:
        Optional readiness condition to wait for *after* execution.
        Recognised values: ``"window_ready"``, ``"process_running"``,
        ``"window_exists"``, ``"window_active"``, ``"element_ready"``,
        ``"browser_loaded"``.
    timeout:
        Seconds for the wait phase (uses wait primitive defaults if None).
    requires:
        Human-readable label of a prerequisite (e.g. ``"Spotify Ready"``).
        Used for logging and UI feedback only — not enforced programmatically.
    max_retries:
        Maximum number of recovery-retry cycles before marking step FAILURE.
        Default is 2 (one initial attempt + two retries).
    """
    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    # ── Stateful execution metadata (added in feature/stateful-execution-engine) ──
    wait_for: str | None = None      # wait condition after this step
    timeout: int | None = None       # seconds; None = use wait primitive default
    requires: str | None = None      # prerequisite label (logging only)
    max_retries: int = 2             # max recovery-retry cycles


@dataclass
class ExecutionPlan:
    """The structured multi-step plan produced by the Planner."""
    thought: str
    steps: list[ActionStep] = field(default_factory=list)
    response: str = ""
    
    # Internal metadata
    confidence: float = 1.0
    fallback_invoked: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionPlan":
        """Instantiate an ExecutionPlan from the raw LLM JSON dict."""
        steps = []
        for step_data in data.get("steps", []):
            steps.append(ActionStep(
                tool=step_data.get("tool", "unknown"),
                args=step_data.get("args", {}),
                # Stateful execution metadata (optional — planners may omit these)
                wait_for=step_data.get("wait_for"),
                timeout=step_data.get("timeout"),
                requires=step_data.get("requires"),
                max_retries=int(step_data.get("max_retries", 2)),
            ))
            
        return cls(
            thought=data.get("thought", ""),
            steps=steps,
            response=data.get("response", "")
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert back to dictionary format."""
        return {
            "thought": self.thought,
            "steps": [{"tool": s.tool, "args": s.args} for s in self.steps],
            "response": self.response
        }


@dataclass
class ToolDefinition:
    """Metadata and schema for an executable tool."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema dict for args
    
    def to_json_schema(self) -> dict[str, Any]:
        """Convert to standard function-calling JSON schema format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
