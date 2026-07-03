"""
LLM Planner
===========

Interfaces with the LLM (Qwen via OpenAI-compatible API) to generate
ExecutionPlans from transcribed text.
"""

import json
import logging
from typing import Any, Callable

from agentic.schemas import ExecutionPlan
from agentic.tool_registry import get_tool_schemas
from agentic.prompts import SYSTEM_PROMPT_TEMPLATE, FEW_SHOT_EXAMPLES

logger = logging.getLogger(__name__)

# A placeholder for the LLM completion function signature
CompletionFunc = Callable[[list[dict[str, str]]], str]


class Planner:
    """Uses an LLM to plan tool executions from user speech."""

    def __init__(self, completion_func: CompletionFunc | None = None):
        """
        Parameters
        ----------
        completion_func : Callable
            A function that takes a list of OpenAI-style message dicts
            and returns the raw string response from the LLM. If None,
            the planner will raise an error on `.plan()` unless replaced.
        """
        self.completion_func = completion_func
        self.tools_json = json.dumps(get_tool_schemas(), indent=2)
        
        # Build the static system prompt once
        self.system_message = SYSTEM_PROMPT_TEMPLATE.format(
            tools_json=self.tools_json
        )

    def build_messages(self, transcription: str) -> list[dict[str, str]]:
        """Construct the full message array for the LLM."""
        messages = [{"role": "system", "content": self.system_message}]
        messages.extend(FEW_SHOT_EXAMPLES)
        messages.append({"role": "user", "content": transcription})
        return messages

    def plan(self, transcription: str) -> ExecutionPlan:
        """Call the LLM and parse the resulting execution plan.
        
        Handles JSON parsing errors by returning a graceful fallback plan.
        """
        if not self.completion_func:
            raise ValueError("No completion_func provided to Planner.")

        messages = self.build_messages(transcription)
        
        try:
            raw_response = self.completion_func(messages)
            logger.debug("Raw LLM response: %s", raw_response)
            
            # Clean up potential markdown formatting if the LLM ignored instructions
            cleaned = raw_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
                
            data = json.loads(cleaned.strip())
            return ExecutionPlan.from_dict(data)
            
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from LLM: %s\nResponse was: %s", e, raw_response)
            return self._create_fallback("I encountered an error understanding that request.", query=transcription)
        except Exception as e:
            logger.exception("Unexpected error during planning.")
            return self._create_fallback("An unexpected error occurred during planning.", query=transcription)

    def _create_fallback(self, response_text: str, query: str = "") -> ExecutionPlan:
        """Create a safe fallback ExecutionPlan."""
        plan = ExecutionPlan.from_dict({
            "thought": "Fallback invoked due to processing error.",
            "steps": [{"tool": "resolve_and_open", "args": {"query": query}}],
            "response": response_text
        })
        plan.fallback_invoked = True
        plan.confidence = 0.5
        return plan
