"""
Agentic Layer Tests
===================

Tests the schemas, planner parsing, tool registry, and executor dispatch.

Run:
    python -m agentic.tests.test_agentic
"""

import sys
import json

from agentic.schemas import ExecutionPlan, ActionStep
from agentic.tool_registry import get_all_tools, get_tool
from agentic.planner import Planner
from agentic.executor import Executor


def mock_completion_func(messages: list[dict[str, str]]) -> str:
    """A mock LLM that returns a static JSON string based on the input."""
    user_text = messages[-1]["content"]
    
    if "machine learning" in user_text:
        return """```json
{
  "thought": "User wants to search for machine learning.",
  "steps": [
    {
      "tool": "search_web",
      "args": {"query": "machine learning"}
    }
  ],
  "response": "Searching for machine learning."
}
```"""
    elif "garbage" in user_text:
        return "I am not returning JSON, I am just breaking."
    else:
        return """{
  "thought": "Fallback test.",
  "steps": [{"tool": "resolve_and_open", "args": {"query": "Fallback test"}}],
  "response": "Fallback."
}"""


def run_tests():
    print("=== Agentic Layer Tests ===")
    
    passed = 0
    tests = 0

    def assert_test(condition, name):
        nonlocal passed, tests
        tests += 1
        if condition:
            print(f"[PASS] {name}")
            passed += 1
        else:
            print(f"[FAIL] {name}")

    # 1. Tool Registry Tests
    tools = get_all_tools()
    assert_test(len(tools) > 0, "Tool registry loaded")
    assert_test(get_tool("search_web") is not None, "get_tool works")

    # 2. Planner Tests
    planner = Planner(completion_func=mock_completion_func)
    
    # Test valid JSON with markdown backticks
    plan1 = planner.plan("Search for machine learning")
    assert_test(len(plan1.steps) == 1, "Planner parses steps")
    assert_test(plan1.steps[0].tool == "search_web", "Planner parses correct tool")
    assert_test(plan1.steps[0].args.get("query") == "machine learning", "Planner parses args")
    assert_test(not plan1.fallback_invoked, "Fallback not invoked for valid JSON")
    
    # Test invalid JSON fallback
    plan2 = planner.plan("garbage input to break json parser")
    assert_test(plan2.fallback_invoked, "Fallback invoked for bad JSON")
    assert_test(plan2.steps[0].tool == "resolve_and_open", "Fallback step is 'resolve_and_open'")

    # 3. Executor Tests
    executor = Executor()
    
    # Execute valid plan
    results1 = executor.execute(plan1)
    assert_test(len(results1) == 1, "Executor returns results for each step")
    assert_test(results1[0]["status"] == "success", "Executor mock handler runs successfully")
    
    # Execute fallback plan
    results2 = executor.execute(plan2)
    assert_test(results2[0]["status"] == "success", "Executor mock handler runs successfully for fallback")

    print(f"\n>>> Results: {passed}/{tests} passed.")
    if passed != tests:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
