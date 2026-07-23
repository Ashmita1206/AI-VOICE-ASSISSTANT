"""
WhatsApp Automation Payload Validator
======================================
"""

import re
from typing import Tuple
from automation.whatsapp.exceptions import InvalidMessageError


class WhatsAppValidator:
    """Validates WhatsApp message payload fields."""

    MIN_MESSAGE_LENGTH = 1
    MAX_MESSAGE_LENGTH = 4096

    @classmethod
    def validate_phone_number(cls, phone_number: str) -> bool:
        """Check if phone number format is valid (E.164 or digits)."""
        if not phone_number:
            return False
        cleaned = re.sub(r"[\s\-\(\)\+]", "", phone_number)
        return cleaned.isdigit() and len(cleaned) >= 7

    @classmethod
    def validate_message_text(cls, message: str) -> Tuple[bool, str]:
        """Validate message text content."""
        if not message or not message.strip():
            return False, "Message body cannot be empty."
        if len(message) > cls.MAX_MESSAGE_LENGTH:
            return False, f"Message length exceeds maximum allowed limit ({cls.MAX_MESSAGE_LENGTH} chars)."
        return True, ""

    @classmethod
    def validate_payload(cls, recipient: str, phone_number: str, message: str) -> Tuple[bool, str]:
        """Validate all payload fields. Returns (is_valid, error_reason)."""
        if not recipient or not recipient.strip() or recipient.upper() == "UNKNOWN":
            return False, "Recipient contact name is missing or invalid."

        if not phone_number or not cls.validate_phone_number(phone_number):
            return False, f"Invalid or missing phone number for recipient '{recipient}'."

        msg_valid, msg_reason = cls.validate_message_text(message)
        if not msg_valid:
            return False, msg_reason

        return True, ""
