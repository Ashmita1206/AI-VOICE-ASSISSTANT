"""
WhatsApp Automation Custom Exceptions
======================================
"""

from typing import Any, List, Optional


class WhatsAppAutomationError(Exception):
    """Base exception for all WhatsApp automation failures."""
    pass


class ContactNotFoundError(WhatsAppAutomationError):
    """Raised when no matching contact could be found."""
    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__(f"No contact found for query '{query}'.")


class AmbiguousContactError(WhatsAppAutomationError):
    """Raised when multiple contacts match a search query."""
    def __init__(self, query: str, matches: List[Any]) -> None:
        self.query = query
        self.matches = matches
        super().__init__(f"Multiple contacts ({len(matches)}) found for query '{query}'.")


class InvalidMessageError(WhatsAppAutomationError):
    """Raised when the message payload fails validation."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid message payload: {reason}")


class N8nWebhookError(WhatsAppAutomationError):
    """Raised when n8n webhook returns a non-success error response."""
    def __init__(self, status_code: int, error_message: str) -> None:
        self.status_code = status_code
        self.error_message = error_message
        super().__init__(f"n8n webhook error ({status_code}): {error_message}")


class RetryExhaustedError(WhatsAppAutomationError):
    """Raised when max retries are exhausted for WhatsApp message dispatch."""
    def __init__(self, attempts: int, last_error: Optional[str] = None) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Exhausted max retries ({attempts}). Last error: {last_error}")
