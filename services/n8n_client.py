"""
n8n Webhook Client
==================

Centralized service client for invoking external n8n workflows.
Prevents scattering webhook endpoints across automation modules.
"""

from __future__ import annotations
import os
import time
import logging
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)

# Environment Configuration
N8N_WEBHOOK_BASE_URL = os.getenv("N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook").rstrip("/")
N8N_WHATSAPP_PATH = os.getenv("N8N_WHATSAPP_PATH", "/whatsapp-send").lstrip("/")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_TIMEOUT = int(os.getenv("N8N_TIMEOUT", "30"))


class N8nClient:
    """Client for executing external n8n workflows via webhooks."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout: int = 30) -> None:
        self.base_url = (base_url or N8N_WEBHOOK_BASE_URL).rstrip("/")
        self.api_key = api_key or N8N_API_KEY
        self.timeout = timeout or N8N_TIMEOUT

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-N8N-API-KEY"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def trigger_workflow(self, endpoint_path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger a generic n8n webhook workflow."""
        path = endpoint_path.lstrip("/")
        url = f"{self.base_url}/{path}"
        logger.info("[N8N CLIENT] Triggering workflow URL=%s", url)

        start_ts = time.perf_counter()
        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=self.timeout)
            elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
            logger.info("[N8N CLIENT] Received status=%d latency_ms=%d", response.status_code, elapsed_ms)

            if response.status_code in (200, 201, 202):
                try:
                    res_json = response.json()
                except Exception:
                    res_json = {"status": "success", "raw": response.text}
                return {"success": True, "status_code": response.status_code, "data": res_json}

            logger.error("[N8N CLIENT] Error response (%d): %s", response.status_code, response.text[:200])
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"n8n returned HTTP {response.status_code}: {response.text[:100]}",
            }
        except requests.exceptions.Timeout:
            logger.error("[N8N CLIENT] Request timed out after %ds", self.timeout)
            return {"success": False, "status_code": 408, "error": f"Request to n8n timed out after {self.timeout}s"}
        except requests.exceptions.ConnectionError as ce:
            logger.error("[N8N CLIENT] Connection failed: %s", ce)
            return {"success": False, "status_code": 503, "error": f"Failed to connect to n8n webhook server: {ce}"}
        except Exception as exc:
            logger.exception("[N8N CLIENT] Unexpected error triggering workflow")
            return {"success": False, "status_code": 500, "error": f"n8n client error: {exc}"}

    def send_whatsapp_message(
        self,
        phone_number: str,
        message: str,
        contact_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Specific wrapper for sending a WhatsApp message via n8n."""
        payload = {
            "phone_number": phone_number,
            "message": message,
            "contact_name": contact_name or "",
            "timestamp": time.time(),
            "metadata": metadata or {},
        }
        return self.trigger_workflow(N8N_WHATSAPP_PATH, payload)


# Singleton instance
_client_instance: Optional[N8nClient] = None


def get_n8n_client() -> N8nClient:
    """Return singleton N8nClient instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = N8nClient()
    return _client_instance
