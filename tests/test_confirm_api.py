"""
Tests for Confirmation API Endpoints
=====================================

Integration tests for POST /confirm and GET /pending.
"""

import json
import time
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import create_app
from agentic.memory.session_state import SessionState, get_session


@pytest.fixture
def client():
    """Create a Flask test client."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def clean_session():
    """Reset the session state before each test."""
    session = get_session()
    session.clear_all()
    yield
    session.clear_all()


# ══════════════════════════════════════════════════════════════════════
# POST /confirm
# ══════════════════════════════════════════════════════════════════════

class TestConfirmEndpoint:

    def test_confirm_proceed(self, client):
        """Clicking Proceed should execute the tool and return success."""
        session = get_session()
        cid = session.set_pending_action(
            tool="create_file",
            args={"path": "test_confirm_dummy.txt", "content": "hello"},
            message="Create test_confirm_dummy.txt?",
        )

        resp = client.post('/confirm', json={
            "confirmation_id": cid,
            "decision": "proceed",
        })
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["success"] is True
        assert session.pending_action is None  # cleared

    def test_confirm_cancel(self, client):
        """Clicking Cancel should clear the pending action and return cancelled message."""
        session = get_session()
        cid = session.set_pending_action(
            tool="delete_file",
            args={"path": "report.pdf"},
            message="Delete report.pdf?",
        )

        resp = client.post('/confirm', json={
            "confirmation_id": cid,
            "decision": "cancel",
        })
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["success"] is True
        assert "cancelled" in data["message"].lower()
        assert session.pending_action is None

    def test_confirm_invalid_id(self, client):
        """An invalid confirmation ID should return an error."""
        resp = client.post('/confirm', json={
            "confirmation_id": "nonexistent-id",
            "decision": "proceed",
        })
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["success"] is False

    def test_confirm_missing_id(self, client):
        """Missing confirmation_id should return 400."""
        resp = client.post('/confirm', json={
            "decision": "proceed",
        })
        assert resp.status_code == 400

    def test_confirm_invalid_decision(self, client):
        """Invalid decision value should return 400."""
        session = get_session()
        cid = session.set_pending_action(
            tool="create_file",
            args={"path": "dummy.txt"},
            message="Create dummy?",
        )

        resp = client.post('/confirm', json={
            "confirmation_id": cid,
            "decision": "maybe",
        })
        assert resp.status_code == 400

    def test_confirm_timeout(self, client):
        """A timed-out confirmation should fail with a timeout message."""
        session = get_session()
        cid = session.set_pending_action(
            tool="delete_file",
            args={"path": "test.txt"},
            message="Delete test.txt?",
        )
        # Manually backdate the timestamp to simulate timeout
        session.pending_action["timestamp"] = time.time() - 61

        resp = client.post('/confirm', json={
            "confirmation_id": cid,
            "decision": "proceed",
        })
        data = resp.get_json()

        assert resp.status_code == 200
        assert "timed out" in data["message"].lower()

    def test_confirm_proceed_stream(self, client):
        """Clicking Proceed with text/event-stream Accept header should stream execution updates."""
        from agentic.memory.pending_action import PendingActionManager
        plan_dict = {
            "intent": "play_music",
            "thought": "Open Spotify and play a song",
            "steps": [
                {"tool": "check_memory", "args": {}}
            ]
        }
        cid = PendingActionManager.save(plan_dict)

        resp = client.post('/confirm', json={
            "confirmation_id": cid,
            "decision": "proceed",
        }, headers={"Accept": "text/event-stream"})

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["Content-Type"]
        
        data = resp.data.decode("utf-8")
        assert "data: " in data
        assert '"stage": "execution"' in data
        assert '"stage": "done"' in data

    def test_plan_validation_logic(self):
        """Test the validate_execution_plan function directly."""
        from web.stream_service import validate_execution_plan
        from agentic.llm.schemas import PlannerOutput, PlannerStep
        
        # 1. Null/Empty
        assert validate_execution_plan(None) == "Planner JSON is missing or null."
        
        # 2. Empty steps
        po_empty = PlannerOutput(intent="status", steps=[])
        assert validate_execution_plan(po_empty) == "Planner produced no executable steps."
        
        # 3. Missing tool
        po_missing_tool = PlannerOutput(intent="test", steps=[PlannerStep(tool="")])
        assert "missing a tool name" in validate_execution_plan(po_missing_tool)
        
        # 4. Unregistered tool
        po_unregistered = PlannerOutput(intent="test", steps=[PlannerStep(tool="super_hacky_tool")])
        assert "is not registered" in validate_execution_plan(po_unregistered)
        
        # 5. Duplicate steps
        po_duplicate = PlannerOutput(intent="test", steps=[
            PlannerStep(tool="press_key", args={"key": "enter"}),
            PlannerStep(tool="press_key", args={"key": "enter"})
        ])
        assert "Duplicate step detected" in validate_execution_plan(po_duplicate)
        
        # 6. Valid steps
        po_valid = PlannerOutput(intent="test", steps=[
            PlannerStep(tool="press_key", args={"key": "enter"}),
            PlannerStep(tool="launch_application", args={"application": "Spotify"})
        ])
        assert validate_execution_plan(po_valid) is None


# ══════════════════════════════════════════════════════════════════════
# GET /pending
# ══════════════════════════════════════════════════════════════════════

class TestPendingEndpoint:

    def test_pending_returns_confirmation(self, client):
        """GET /pending should return the pending confirmation object."""
        session = get_session()
        cid = session.set_pending_action(
            tool="shutdown_system",
            args={},
            message="Shutdown the system?",
        )

        resp = client.get('/pending')
        data = resp.get_json()

        assert data["confirmation"] is not None
        assert data["confirmation"]["id"] == cid
        assert data["confirmation"]["tool"] == "shutdown_system"
        assert data["confirmation"]["message"] == "Shutdown the system?"
        assert "remaining_seconds" in data["confirmation"]

    def test_pending_returns_null_when_empty(self, client):
        """GET /pending should return null when no pending action exists."""
        resp = client.get('/pending')
        data = resp.get_json()

        assert data["confirmation"] is None

    def test_pending_survives_multiple_calls(self, client):
        """Pending confirmation should persist across multiple GET /pending calls."""
        session = get_session()
        cid = session.set_pending_action(
            tool="delete_file",
            args={"path": "important.txt"},
            message="Delete important.txt?",
        )

        # Call multiple times
        for _ in range(3):
            resp = client.get('/pending')
            data = resp.get_json()
            assert data["confirmation"] is not None
            assert data["confirmation"]["id"] == cid

    def test_pending_cleared_after_proceed(self, client):
        """After confirming, GET /pending should return null."""
        session = get_session()
        cid = session.set_pending_action(
            tool="create_file",
            args={"path": "test_confirm_clear.txt", "content": "test"},
            message="Create test_confirm_clear.txt?",
        )

        # Confirm
        client.post('/confirm', json={
            "confirmation_id": cid,
            "decision": "proceed",
        })

        # Check pending
        resp = client.get('/pending')
        data = resp.get_json()
        assert data["confirmation"] is None

    def test_pending_cleared_after_cancel(self, client):
        """After cancelling, GET /pending should return null."""
        session = get_session()
        cid = session.set_pending_action(
            tool="delete_file",
            args={"path": "test.txt"},
            message="Delete test.txt?",
        )

        # Cancel
        client.post('/confirm', json={
            "confirmation_id": cid,
            "decision": "cancel",
        })

        # Check pending
        resp = client.get('/pending')
        data = resp.get_json()
        assert data["confirmation"] is None


class TestPermissionsAPI:

    def test_permissions_check_endpoint(self, client):
        """POST /permissions/check should verify specified permissions."""
        resp = client.post('/permissions/check', json={
            "permissions": ["Accessibility/UI Automation", "Keyboard Control"]
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert "Accessibility/UI Automation" in data["granted"]
        assert "Keyboard Control" in data["granted"]

    def test_permissions_grant_endpoint(self, client):
        """POST /permissions/grant should trigger grant settings for requested permission."""
        resp = client.post('/permissions/grant', json={
            "permission": "Screen Capture"
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["permission"] == "Screen Capture"

    def test_permissions_mock_endpoint(self, client):
        """POST /permissions/mock should allow toggling permission states for validation flows."""
        # 1. Set to False
        resp = client.post('/permissions/mock', json={
            "permission": "Accessibility/UI Automation",
            "granted": False
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["granted"] is False

        # Check it is False
        check_resp = client.post('/permissions/check', json={
            "permissions": ["Accessibility/UI Automation"]
        })
        assert check_resp.get_json()["granted"]["Accessibility/UI Automation"] is False

        # 2. Reset back to True
        resp2 = client.post('/permissions/mock', json={
            "permission": "Accessibility/UI Automation",
            "granted": True
        })
        assert resp2.status_code == 200
        assert resp2.get_json()["granted"] is True
