"""
Tests for Session State and Memory History
"""

import time
from agentic.memory.session_state import get_session
from agentic.memory.history_manager import get_last_command, get_recent_commands, search_history

def test_session_singleton():
    s1 = get_session()
    s2 = get_session()
    assert s1 is s2

def test_pending_action():
    session = get_session()
    session.clear_all()
    
    session.set_pending_action("test_tool", {"arg": "val"}, "Are you sure?")
    assert session.pending_action is not None
    assert session.pending_action["tool"] == "test_tool"
    assert session.is_confirmation_timeout() is False
    
    # Simulate timeout
    session.pending_action["timestamp"] = time.time() - 61
    assert session.is_confirmation_timeout() is True
    
def test_history_manager():
    session = get_session()
    session.clear_all()
    
    assert "haven't asked" in get_last_command()
    
    session.add_history("open chrome", "app_open", {}, "success")
    session.add_history("search test", "search", {}, "success")
    
    assert "search test" in get_last_command()
    
    recent = get_recent_commands()
    assert "open chrome" in recent
    assert "search test" in recent
    
    search_results = search_history("chrome")
    assert len(search_results) == 1
    assert search_results[0]["transcript"] == "open chrome"
