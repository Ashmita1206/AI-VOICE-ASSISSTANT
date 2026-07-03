"""
Tests for Confirmation Manager
"""

import time
from agentic.conversation.confirmation_manager import is_positive, is_negative, handle_pending_confirmation
from agentic.memory.session_state import get_session

def test_nlp_yes_no():
    assert is_positive("yes")
    assert is_positive("sure")
    assert is_positive("proceed")
    assert not is_positive("no")
    
    assert is_negative("no")
    assert is_negative("cancel")
    assert not is_negative("yes")

def test_handle_pending_confirmation_yes():
    session = get_session()
    session.clear_all()
    
    # We will mock a tool that we know exists from filesystem.py
    session.set_pending_action("create_file", {"path": "~/dummy.txt"}, "Create?")
    
    handled, msg = handle_pending_confirmation("yes")
    
    assert handled is True
    assert session.pending_action is None
    # We assume execution happened and returned a message
    assert msg is not None

def test_handle_pending_confirmation_no():
    session = get_session()
    session.clear_all()
    
    session.set_pending_action("create_file", {"path": "~/dummy.txt"}, "Create?")
    
    handled, msg = handle_pending_confirmation("no")
    
    assert handled is True
    assert session.pending_action is None
    assert session.interrupted_task is not None
    assert "cancelled" in msg.lower()


# ══════════════════════════════════════════════════════════════════════
# UUID-based Confirmation Tests
# ══════════════════════════════════════════════════════════════════════

def test_set_pending_returns_uuid():
    """set_pending_action should return a unique confirmation ID."""
    session = get_session()
    session.clear_all()
    
    cid = session.set_pending_action("delete_file", {"path": "test.txt"}, "Delete test.txt?")
    
    assert cid is not None
    assert isinstance(cid, str)
    assert len(cid) == 16
    assert session.pending_action["id"] == cid

def test_get_pending_by_id_match():
    """get_pending_by_id should return the action when ID matches."""
    session = get_session()
    session.clear_all()
    
    cid = session.set_pending_action("delete_file", {"path": "test.txt"}, "Delete test.txt?")
    
    action = session.get_pending_by_id(cid)
    assert action is not None
    assert action["tool"] == "delete_file"
    assert action["args"]["path"] == "test.txt"

def test_get_pending_by_id_no_match():
    """get_pending_by_id should return None for a wrong ID."""
    session = get_session()
    session.clear_all()
    
    session.set_pending_action("delete_file", {"path": "test.txt"}, "Delete test.txt?")
    
    action = session.get_pending_by_id("wrong-id-12345678")
    assert action is None

def test_get_pending_confirmation_format():
    """get_pending_confirmation should return API-friendly format with remaining_seconds."""
    session = get_session()
    session.clear_all()
    
    cid = session.set_pending_action("shutdown_system", {}, "Shutdown?")
    
    confirmation = session.get_pending_confirmation()
    assert confirmation is not None
    assert confirmation["id"] == cid
    assert confirmation["tool"] == "shutdown_system"
    assert confirmation["message"] == "Shutdown?"
    assert "remaining_seconds" in confirmation
    assert confirmation["remaining_seconds"] <= 60
    assert confirmation["remaining_seconds"] > 0

def test_get_pending_confirmation_timeout():
    """get_pending_confirmation should return None after timeout."""
    session = get_session()
    session.clear_all()
    
    session.set_pending_action("delete_file", {"path": "old.txt"}, "Delete old.txt?")
    # Backdate the timestamp to simulate timeout
    session.pending_action["timestamp"] = time.time() - 61
    
    confirmation = session.get_pending_confirmation()
    assert confirmation is None
    assert session.pending_action is None  # auto-cleared

def test_confirm_survives_new_pending():
    """A pending action should survive until explicitly resolved."""
    session = get_session()
    session.clear_all()
    
    cid = session.set_pending_action("delete_file", {"path": "report.pdf"}, "Delete report.pdf?")
    
    # The confirmation should still be retrievable
    action = session.get_pending_by_id(cid)
    assert action is not None
    
    # Calling get_pending_confirmation multiple times should not clear it
    for _ in range(5):
        confirmation = session.get_pending_confirmation()
        assert confirmation is not None
        assert confirmation["id"] == cid

