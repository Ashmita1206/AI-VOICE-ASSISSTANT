"""
Planner Output Schema
=====================

Structured output contract for the Qwen3-8B planner.
Every inference MUST produce a result matching this shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlannerStep:
    """A single tool invocation step."""
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    wait_for: str | None = None
    timeout: int | float | None = None
    requires: str | None = None


@dataclass
class PlannerOutput:
    """Structured output from the Qwen3-8B planner.

    Attributes
    ----------
    intent : str
        The high-level intent inferred by the model.
    confidence : float
        The model's self-reported confidence (0.0–1.0).
    reasoning : str
        Brief chain-of-thought explanation.
    steps : list[PlannerStep]
        Ordered tool invocation steps.
    """
    intent: str = "unknown"
    confidence: float = 0.0
    reasoning: str = ""
    steps: list[PlannerStep] = field(default_factory=list)

    # ── Serialisation ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "steps": [
                {
                    "tool": s.tool,
                    "args": s.args,
                    **({"wait_for": s.wait_for} if s.wait_for else {}),
                    **({"timeout": s.timeout} if s.timeout else {}),
                    **({"requires": s.requires} if s.requires else {})
                }
                for s in self.steps
            ],
        }

    # ── Deserialisation ──────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlannerOutput:
        steps = [
            PlannerStep(
                tool=s.get("tool", "unknown"),
                args=s.get("args", {}),
                wait_for=s.get("wait_for"),
                timeout=s.get("timeout"),
                requires=s.get("requires")
            )
            for s in data.get("steps", [])
        ]
        return cls(
            intent=data.get("intent", "unknown"),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=data.get("reasoning", ""),
            steps=steps,
        )

    @classmethod
    def from_json(cls, raw: str) -> PlannerOutput:
        """Parse a raw JSON string into a PlannerOutput.

        Handles common LLM quirks like markdown fencing.
        """
        cleaned = raw.strip()
        # Strip markdown code fences
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        data = json.loads(cleaned.strip())
        return cls.from_dict(data)

    # ── Factory ──────────────────────────────────────────────────────

    @classmethod
    def fallback(cls, reason: str = "Planning failed.", query: str = "") -> PlannerOutput:
        """Return a safe fallback output when parsing or inference fails."""
        return cls(
            intent="open_resource",
            confidence=0.5,
            reasoning=reason,
            steps=[PlannerStep(tool="resolve_and_open", args={"query": query})],
        )
