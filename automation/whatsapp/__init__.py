"""
WhatsApp Automation Package
============================

Production-ready WhatsApp Automation module built on LangGraph + LangChain + n8n.
Exposes public API for WhatsApp messaging, contact lookup, and workflow state machine.
"""

from automation.whatsapp.service import WhatsAppAutomation, send_whatsapp_automation
from automation.whatsapp.contact_lookup import ContactLookupService
from automation.whatsapp.sender import WhatsAppSender
from automation.whatsapp.workflow import create_whatsapp_workflow
from automation.whatsapp.schemas import WhatsAppWorkflowState, WhatsAppMessagePayload, ContactItem

__all__ = [
    "WhatsAppAutomation",
    "send_whatsapp_automation",
    "ContactLookupService",
    "WhatsAppSender",
    "create_whatsapp_workflow",
    "WhatsAppWorkflowState",
    "WhatsAppMessagePayload",
    "ContactItem",
]
