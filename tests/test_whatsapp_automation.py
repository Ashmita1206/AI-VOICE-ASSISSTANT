"""
Unit Tests for WhatsApp Automation System & Components
======================================================
"""

import unittest
from unittest.mock import MagicMock, patch
from automation.whatsapp.schemas import ContactItem, WhatsAppMessagePayload
from automation.whatsapp.contact_lookup import ContactLookupService
from automation.whatsapp.validator import WhatsAppValidator
from automation.whatsapp.formatter import WhatsAppFormatter
from automation.whatsapp.sender import WhatsAppSender
from automation.whatsapp.service import WhatsAppAutomation
from services.n8n_client import N8nClient, get_n8n_client
from agentic.rag.langchain_wrapper import LangChainRAGRetriever


class TestWhatsAppValidator(unittest.TestCase):
    """Test payload validation logic."""

    def test_valid_payload(self):
        is_valid, err = WhatsAppValidator.validate_payload("Harshita", "+919876543210", "I will reach in 10 minutes.")
        self.assertTrue(is_valid)
        self.assertEqual(err, "")

    def test_missing_recipient(self):
        is_valid, err = WhatsAppValidator.validate_payload("", "+919876543210", "Hello")
        self.assertFalse(is_valid)
        self.assertIn("missing", err.lower())

    def test_invalid_phone(self):
        is_valid, err = WhatsAppValidator.validate_payload("Harshita", "123", "Hello")
        self.assertFalse(is_valid)
        self.assertIn("phone number", err.lower())

    def test_empty_message(self):
        is_valid, err = WhatsAppValidator.validate_payload("Harshita", "+919876543210", "   ")
        self.assertFalse(is_valid)
        self.assertIn("empty", err.lower())


class TestContactLookupService(unittest.TestCase):
    """Test contact lookup strategies."""

    def setUp(self):
        self.service = ContactLookupService(db_path=":memory:")
        self.service._get_all_contacts = MagicMock(return_value=[
            ContactItem(name="Harshita Sharma", phone_number="+919876543210", nickname="Harshu"),
            ContactItem(name="Rahul Verma", phone_number="+919876543211", nickname="Rahul V"),
            ContactItem(name="Rahul Kumar", phone_number="+919876543212", nickname="RK"),
        ])

    def test_exact_match(self):
        res = self.service.search("Harshita Sharma")
        self.assertEqual(res.status, "exact_match")
        self.assertIsNotNone(res.selected_contact)
        self.assertEqual(res.selected_contact.phone_number, "+919876543210")

    def test_nickname_match(self):
        res = self.service.search("Harshu")
        self.assertEqual(res.status, "nickname_match")
        self.assertEqual(res.selected_contact.name, "Harshita Sharma")

    def test_partial_single_match(self):
        res = self.service.search("Harshita")
        self.assertEqual(res.status, "partial_match")
        self.assertEqual(res.selected_contact.name, "Harshita Sharma")

    def test_multiple_matches(self):
        res = self.service.search("Rahul")
        self.assertEqual(res.status, "multiple_matches")
        self.assertEqual(len(res.candidates), 2)

    def test_not_found(self):
        res = self.service.search("NonExistentUser123")
        self.assertEqual(res.status, "not_found")
        self.assertIsNone(res.selected_contact)


class TestN8nClient(unittest.TestCase):
    """Test N8nClient webhook execution."""

    @patch("requests.post")
    def test_send_whatsapp_message_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "queued"}
        mock_post.return_value = mock_resp

        client = N8nClient(base_url="http://test-n8n:5678/webhook")
        res = client.send_whatsapp_message("+919876543210", "Hello test", "Harshita")

        self.assertTrue(res["success"])
        self.assertEqual(res["status_code"], 200)
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_send_whatsapp_message_timeout(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        client = N8nClient(base_url="http://test-n8n:5678/webhook", timeout=2)
        res = client.send_whatsapp_message("+919876543210", "Hello test", "Harshita")

        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 408)


class TestWhatsAppAutomationService(unittest.TestCase):
    """Test full WhatsAppAutomation tool execution."""

    def setUp(self):
        self.mock_lookup = MagicMock()
        self.mock_sender = MagicMock()
        self.service = WhatsAppAutomation(contact_lookup=self.mock_lookup, sender=self.mock_sender)

    def test_execute_success_with_explicit_phone(self):
        self.mock_sender.send.return_value = {"success": True, "data": {"status": "ok"}}

        res = self.service.execute({
            "recipient": "Harshita",
            "phone_number": "+919876543210",
            "message": "I will reach in 10 minutes."
        })

        self.assertTrue(res.success)
        self.assertIn("Successfully sent WhatsApp message to Harshita", res.message)

    def test_execute_lookup_and_send(self):
        mock_contact = ContactItem(name="Harshita", phone_number="+919876543210")
        self.mock_lookup.search.return_value = MagicMock(
            status="exact_match",
            selected_contact=mock_contact,
            candidates=[]
        )
        self.mock_sender.send.return_value = {"success": True}

        res = self.service.execute({
            "contact": "Harshita",
            "message": "I will reach in 10 minutes."
        })

        self.assertTrue(res.success)
        self.assertEqual(res.data["phone_number"], "+919876543210")


class TestLangChainRAGRetriever(unittest.TestCase):
    """Test LangChain BaseRetriever wrapper."""

    @patch("agentic.file_context_search.manager.DocumentSearchManager.find_documents")
    def test_retrieval(self, mock_find):
        mock_find.return_value = [
            MagicMock(rank=1, score=0.95, path="/path/doc.pdf", filename="doc.pdf", extension="pdf", folder="docs", confidence="high", snippet="Sample RAG context text")
        ]

        retriever = LangChainRAGRetriever(top_n=3)
        docs = retriever.invoke("sample query")

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "Sample RAG context text")
        self.assertEqual(docs[0].metadata["filename"], "doc.pdf")


if __name__ == "__main__":
    unittest.main()
