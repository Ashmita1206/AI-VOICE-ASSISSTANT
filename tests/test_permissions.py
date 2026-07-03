"""
Tests for Permission Engine
"""

from agentic.permissions import PermissionManager

def test_safe_tools():
    assert PermissionManager.is_safe("open_application")
    assert PermissionManager.is_safe("search_web")
    assert not PermissionManager.requires_confirmation("open_website")

def test_dangerous_tools():
    assert not PermissionManager.is_safe("delete_file")
    assert PermissionManager.requires_confirmation("shutdown_system")
    assert PermissionManager.requires_confirmation("send_whatsapp_message")

def test_confirmation_messages():
    msg = PermissionManager.build_confirmation_message("delete_file", {"path": "report.pdf"})
    assert "report.pdf" in msg
    assert "Delete" in msg

    msg2 = PermissionManager.build_confirmation_message("type_message", {"contact": "Rahul"})
    assert "Rahul" in msg2
    assert "Should I send" in msg2
