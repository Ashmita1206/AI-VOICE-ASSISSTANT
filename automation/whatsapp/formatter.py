"""
WhatsApp Message Formatter
==========================
"""

from typing import List, Optional
from automation.whatsapp.schemas import ContactItem


class WhatsAppFormatter:
    """Formats payload text, contact choices, and response summaries."""

    @classmethod
    def format_success_response(cls, recipient: str, phone_number: str, message: str) -> str:
        """Format natural language response after successful message delivery."""
        return f"Successfully sent WhatsApp message to {recipient} ({phone_number}): \"{message}\""

    @classmethod
    def format_candidates_list(cls, candidates: List[ContactItem]) -> str:
        """Format a bulleted list of ambiguous matching contacts for user selection."""
        lines = []
        for idx, c in enumerate(candidates, 1):
            nick_str = f" (aka {c.nickname})" if c.nickname else ""
            lines.append(f"{idx}. {c.name}{nick_str} - {c.phone_number}")
        return "\n".join(lines)

    @classmethod
    def format_confirmation_prompt(cls, recipient: str, phone_number: str, message: str) -> str:
        """Format user confirmation prompt text."""
        return (
            f"Are you sure you want to send this WhatsApp message?\n\n"
            f"To: {recipient} ({phone_number})\n"
            f"Message: \"{message}\""
        )
