"""
WhatsApp Automation Service
===========================

Implements generic AutomationTool abstract base interface for WhatsApp messaging.
Registered in system tool execution registry as 'send_whatsapp_automation'.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Tuple
from execution.schemas import ExecutionResult
from execution.registry import register_tool
from automation.base import AutomationTool
from automation.whatsapp.constants import TOOL_NAME_WHATSAPP_SEND
from automation.whatsapp.validator import WhatsAppValidator
from automation.whatsapp.contact_lookup import ContactLookupService
from automation.whatsapp.sender import WhatsAppSender
from automation.whatsapp.schemas import WhatsAppMessagePayload
from automation.whatsapp.formatter import WhatsAppFormatter

logger = logging.getLogger("automation.whatsapp.service")


class WhatsAppAutomation(AutomationTool):
    """WhatsApp Automation Module implementing AutomationTool."""

    def __init__(self, contact_lookup: ContactLookupService = None, sender: WhatsAppSender = None) -> None:
        self.contact_lookup = contact_lookup or ContactLookupService()
        self.sender = sender or WhatsAppSender()

    @property
    def name(self) -> str:
        return TOOL_NAME_WHATSAPP_SEND

    @property
    def description(self) -> str:
        return "Automates sending WhatsApp messages to contacts via n8n integration."

    def validate(self, args: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate recipient, phone number, and message text args."""
        recipient = args.get("recipient") or args.get("contact") or ""
        phone_number = args.get("phone_number") or ""
        message = args.get("message") or ""

        # If phone_number is not explicitly provided, attempt contact lookup
        if not phone_number and recipient:
            lookup_res = self.contact_lookup.search(recipient)
            if lookup_res.selected_contact:
                phone_number = lookup_res.selected_contact.phone_number

        return WhatsAppValidator.validate_payload(recipient, phone_number, message)

    def execute(self, args: Dict[str, Any]) -> ExecutionResult:
        """Execute WhatsApp message dispatch workflow."""
        recipient = args.get("recipient") or args.get("contact") or ""
        phone_number = args.get("phone_number") or ""
        message = args.get("message") or ""

        # Contact lookup resolution if phone number is missing
        if not phone_number:
            lookup_res = self.contact_lookup.search(recipient)
            if lookup_res.status == "multiple_matches":
                candidates_text = WhatsAppFormatter.format_candidates_list(lookup_res.candidates)
                return ExecutionResult(
                    success=False,
                    tool=self.name,
                    message=f"Multiple contacts found for '{recipient}'. Please clarify:\n{candidates_text}",
                    requires_interaction=True,
                    data={"candidates": [c.model_dump() for c in lookup_res.candidates]},
                )
            elif not lookup_res.selected_contact:
                return ExecutionResult(
                    success=False,
                    tool=self.name,
                    message=f"Could not find contact '{recipient}' in phonebook.",
                )
            selected = lookup_res.selected_contact
            recipient = selected.name
            phone_number = selected.phone_number

        # Validate final payload
        is_valid, err_msg = WhatsAppValidator.validate_payload(recipient, phone_number, message)
        if not is_valid:
            return ExecutionResult(success=False, tool=self.name, message=err_msg)

        payload = WhatsAppMessagePayload(
            recipient=recipient,
            phone_number=phone_number,
            message=message,
            metadata=args.get("metadata", {}),
        )

        dispatch_res = self.sender.send(payload)
        if dispatch_res.get("success"):
            resp_text = WhatsAppFormatter.format_success_response(recipient, phone_number, message)
            return ExecutionResult(
                success=True,
                tool=self.name,
                message=resp_text,
                output=resp_text,
                data={"recipient": recipient, "phone_number": phone_number, "message": message},
            )
        else:
            err = dispatch_res.get("error", "Dispatch failed")
            return ExecutionResult(
                success=False,
                tool=self.name,
                message=f"Failed to send WhatsApp message to {recipient}: {err}",
            )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "contact": {"type": "string", "description": "Target contact name or phone number"},
                    "recipient": {"type": "string", "description": "Recipient name"},
                    "phone_number": {"type": "string", "description": "Phone number in E.164 format"},
                    "message": {"type": "string", "description": "Message text content to send"},
                },
                "required": ["message"],
            },
        }


# Singleton service instance
_whatsapp_service = WhatsAppAutomation()


@register_tool(TOOL_NAME_WHATSAPP_SEND)
def send_whatsapp_automation(args: Dict[str, Any]) -> ExecutionResult:
    """Tool handler wrapper registered as send_whatsapp_automation."""
    return _whatsapp_service.execute(args)
