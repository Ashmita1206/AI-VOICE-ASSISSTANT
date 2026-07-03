"""
Executor
========

Takes an ExecutionPlan and runs the defined tool steps.
Currently uses mocked stubs for execution.
"""

import logging
from typing import Any

from agentic.schemas import ExecutionPlan, ActionStep
from agentic.tool_registry import get_tool

logger = logging.getLogger(__name__)


class Executor:
    """Dispatches tool calls defined in an ExecutionPlan."""

    def __init__(self):
        # Dispatch table mapping tool names to actual functions.
        # For now, all map to a generic mock runner.
        self._handlers = {
            "open_browser": self._mock_handler,
            "search_web": self._mock_handler,
            "open_application": self._mock_handler,
            "check_time": self._mock_handler,
            "list_files": self._mock_handler,
            "take_screenshot": self._mock_handler,
            "open_file_manager": self._mock_handler,
            "check_memory": self._mock_handler,
            "unknown": self._handle_unknown,
        }

    def execute(self, plan: ExecutionPlan) -> list[Any]:
        """Execute all steps in the plan sequentially.
        
        Returns
        -------
        list[Any]
            A list of results from each step.
        """
        logger.info("Executing plan with %d steps. Thought: %s", len(plan.steps), plan.thought)
        results = []
        
        for step in plan.steps:
            res = self.execute_step(step)
            results.append(res)
            
        return results

    def execute_step(self, step: ActionStep) -> Any:
        """Dispatch a single ActionStep to its corresponding handler."""
        tool_def = get_tool(step.tool)
        if not tool_def and step.tool != "unknown":
            logger.warning("Tool '%s' is not registered.", step.tool)
            return self._mock_handler(step.tool, step.args, error="Unregistered tool")

        handler = self._handlers.get(step.tool, self._mock_handler)
        
        try:
            return handler(step.tool, step.args)
        except Exception as e:
            logger.exception("Error executing step %s", step.tool)
            return {"status": "error", "message": str(e)}

    # ── Handlers ───────────────────────────────────────────────────────

    def _mock_handler(self, tool_name: str, args: dict[str, Any], **kwargs) -> dict[str, Any]:
        """A generic mock handler that just prints the action."""
        # In a real scenario, this would call actual OS modules (e.g., subprocess.run)
        print(f"[EXECUTOR] Running '{tool_name}' with args: {args}")
        if kwargs:
            print(f"    Extra: {kwargs}")
        return {"status": "success", "tool": tool_name, "args": args}

    def _handle_unknown(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Handler for the 'unknown' fallback tool."""
        print("[EXECUTOR] Fallback triggered. Unrecognized intent.")
        return {"status": "fallback"}
