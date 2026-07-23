"""
Unit Tests for LangGraph StateMachine Workflow for WhatsApp Automation
========================================================================
"""

import unittest
from unittest.mock import MagicMock, patch
from automation.whatsapp.workflow import (
    create_whatsapp_workflow,
    intent_node,
    extract_entities_node,
    lookup_contact_node,
    validate_node,
    confirmation_node,
    execute_tool_node,
)
from automation.whatsapp.schemas import ContactItem


class TestLangGraphWhatsAppWorkflow(unittest.TestCase):
    """Test LangGraph state machine nodes and state transitions."""

    def test_intent_node(self):
        state = {"user_input": "Send WhatsApp to Harshita saying hello"}
        res = intent_node(state)
        self.assertEqual(res["intent"], "send_whatsapp_message")

    def test_extract_entities_node(self):
        state = {"user_input": "Send WhatsApp message to Harshita saying I will reach in 10 minutes."}
        res = extract_entities_node(state)
        self.assertEqual(res["recipient"], "Harshita")
        self.assertEqual(res["message"], "I will reach in 10 minutes.")

    @patch("automation.whatsapp.workflow.ContactLookupService")
    def test_lookup_contact_node_single_match(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.search.return_value = MagicMock(
            status="exact_match",
            selected_contact=ContactItem(name="Harshita", phone_number="+919876543210"),
            candidates=[]
        )
        mock_service_cls.return_value = mock_service

        state = {"recipient": "Harshita"}
        res = lookup_contact_node(state)

        self.assertEqual(res["recipient"], "Harshita")
        self.assertEqual(res["phone_number"], "+919876543210")

    def test_validate_node_valid(self):
        state = {"recipient": "Harshita", "phone_number": "+919876543210", "message": "I am on the way"}
        res = validate_node(state)
        self.assertTrue(res["is_valid"])

    def test_validate_node_invalid(self):
        state = {"recipient": "Harshita", "phone_number": "123", "message": "I am on the way"}
        res = validate_node(state)
        self.assertFalse(res["is_valid"])

    def test_confirmation_node_not_confirmed(self):
        state = {
            "recipient": "Harshita",
            "phone_number": "+919876543210",
            "message": "Hi",
            "confirmed": False,
            "confirmation_required": True,
        }
        res = confirmation_node(state)
        self.assertEqual(res["current_state"], "WaitingUserInput")
        self.assertIn("Are you sure you want to send this WhatsApp message?", res["output_response"])

    @patch("automation.whatsapp.workflow.WhatsAppAutomation")
    def test_execute_tool_node_success(self, mock_auto_cls):
        mock_auto = MagicMock()
        mock_auto.execute.return_value = MagicMock(
            success=True,
            message="Sent message to Harshita",
            to_dict=lambda: {"success": True, "message": "Sent message to Harshita"}
        )
        mock_auto_cls.return_value = mock_auto

        state = {
            "recipient": "Harshita",
            "phone_number": "+919876543210",
            "message": "Hello",
            "attempts": 0,
            "max_retries": 3,
        }
        res = execute_tool_node(state)

        self.assertEqual(res["current_state"], "Success")
        self.assertEqual(res["output_response"], "Sent message to Harshita")

    def test_workflow_graph_compilation(self):
        app = create_whatsapp_workflow()
        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
