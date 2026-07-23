"""
WhatsApp Automation Retry Handler
=================================
"""

import time
import logging
from typing import Callable, Any, Dict
from automation.whatsapp.config import WHATSAPP_RETRY_COUNT, WHATSAPP_BACKOFF_FACTOR
from automation.whatsapp.exceptions import RetryExhaustedError

logger = logging.getLogger("automation.whatsapp.retry")


class RetryHandler:
    """Executes callables with exponential backoff retry logic."""

    def __init__(self, max_retries: int = WHATSAPP_RETRY_COUNT, backoff_factor: float = WHATSAPP_BACKOFF_FACTOR) -> None:
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def execute_with_retry(self, func: Callable[..., Dict[str, Any]], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Execute callable with backoff retries. Returns result dictionary."""
        attempts = 0
        last_error = ""

        while attempts < self.max_retries:
            attempts += 1
            logger.info("[RETRY HANDLER] Attempt %d/%d for WhatsApp delivery", attempts, self.max_retries)
            try:
                res = func(*args, **kwargs)
                if res.get("success"):
                    return res

                last_error = res.get("error", "Unknown dispatch failure")
                logger.warning("[RETRY HANDLER] Attempt %d failed: %s", attempts, last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("[RETRY HANDLER] Attempt %d exception: %s", attempts, e)

            if attempts < self.max_retries:
                sleep_time = self.backoff_factor ** attempts
                logger.info("[RETRY HANDLER] Sleeping %.1fs before retry", sleep_time)
                time.sleep(sleep_time)

        raise RetryExhaustedError(attempts, last_error)
