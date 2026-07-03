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
