"""
WhatsApp Automation Logger
===========================
"""

import logging

logger = logging.getLogger("automation.whatsapp")


def get_logger() -> logging.Logger:
    """Return dedicated logger instance for WhatsApp automation."""
    return logger
