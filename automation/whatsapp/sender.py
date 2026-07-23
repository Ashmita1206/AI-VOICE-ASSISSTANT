"""
WhatsApp Message Sender
=======================

Dispatches WhatsApp messages exclusively through the centralized n8n_client.
Isolates API / Webhook integration details from domain logic.
"""

from typing import Any, Dict
from services.n8n_client import get_n8n_client, N8nClient
from automation.whatsapp.schemas import WhatsAppMessagePayload
from automation.whatsapp.retry import RetryHandler
from automation.whatsapp.logger import get_logger

logger = get_logger()


class WhatsAppSender:
    """Dispatches WhatsApp payloads via n8n_client with retry policy."""

    def __init__(self, n8n_client: N8nClient = None) -> None:
        self.client = n8n_client or get_n8n_client()
        self.retry_handler = RetryHandler()

    def send(self, payload: WhatsAppMessagePayload) -> Dict[str, Any]:
        """Send WhatsApp payload via n8n client."""
        logger.info("[WHATSAPP SENDER] Dispatching payload to recipient='%s' phone='%s'", payload.recipient, payload.phone_number)

        def _do_send() -> Dict[str, Any]:
            return self.client.send_whatsapp_message(
                phone_number=payload.phone_number,
                message=payload.message,
                contact_name=payload.recipient,
                metadata=payload.metadata,
            )

        try:
            res = self.retry_handler.execute_with_retry(_do_send)
            return res
        except Exception as e:
            logger.error("[WHATSAPP SENDER] Dispatch failed: %s", e)
            return {"success": False, "error": str(e)}
