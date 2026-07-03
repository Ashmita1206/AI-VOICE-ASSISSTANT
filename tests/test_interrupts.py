"""
Tests for Interrupt and Workflow Resuming
"""

from agentic.conversation.interrupt_handler import check_interrupt
from agentic.conversation.workflow_manager import check_resume_workflow
from agentic.conversation.status_manager import check_status_query
from agentic.memory.session_state import get_session

def test_check_interrupt():
    session = get_session()
    session.clear_all()
    
    session.current_task = "Downloading file"
    
    msg = check_interrupt("stop")
    assert msg is not None
    assert "stopped" in msg.lower()
    assert session.current_task is None

def test_check_status_query():
    session = get_session()
    session.clear_all()
    
    msg = check_status_query("what are you doing?")
    assert msg is not None
    assert "idle" in msg.lower()
    
    session.current_task = "Searching web"
    msg = check_status_query("status")
    assert "Searching web" in msg

def test_resume_workflow():
    session = get_session()
    session.clear_all()
    
    session.interrupted_task = {"tool": "dummy", "args": {}, "message": "Dummy task"}
    
    is_resume, msg = check_resume_workflow("resume previous task")
    
    assert is_resume is True
    assert "Dummy task" in msg
    assert session.interrupted_task is None
    assert session.pending_action is not None
