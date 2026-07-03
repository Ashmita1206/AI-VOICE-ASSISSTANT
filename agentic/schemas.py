"""
Agentic Layer Schemas
=====================

Data contracts for the Qwen-based planning and execution pipeline.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionStep:
    """A single tool execution step parsed from the LLM."""
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


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
                args=step_data.get("args", {})
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
