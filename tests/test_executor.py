"""
Tests for Executor and Automation Integrations
"""

import pytest
from agentic.schemas import ExecutionPlan, ActionStep
from execution.executor import DesktopExecutor

def test_executor_stops_on_dangerous_tool():
    executor = DesktopExecutor()
    
    plan = ExecutionPlan(
        thought="Testing send message",
        steps=[
            ActionStep(tool="open_whatsapp", args={}),
            ActionStep(tool="send_whatsapp_message", args={"contact": "Rahul", "message": "Hi"})
        ]
    )
    
    results = executor.execute(plan)
    
    # Check that execution halted and returned the confirmation requirement
    assert len(results) == 2
    assert results[1]["requires_confirmation"] is True
    assert "Rahul" in results[1]["message"]

def test_executor_safe_multi_step():
    executor = DesktopExecutor()
    
    plan = ExecutionPlan(
        thought="Testing safe steps",
        steps=[
            ActionStep(tool="create_folder", args={"path": "~/test_folder"}),
            ActionStep(tool="list_files", args={"path": "~"})
        ]
    )
    
    results = executor.execute(plan)
    
    assert len(results) == 2
    assert results[0]["requires_confirmation"] is False
    assert results[1]["requires_confirmation"] is False
