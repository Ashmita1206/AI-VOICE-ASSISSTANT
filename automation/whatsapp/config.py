"""
WhatsApp Automation Configuration
===================================
"""

import os
from dotenv import load_dotenv

load_dotenv()

# n8n Webhook Settings
N8N_WEBHOOK_BASE_URL = os.getenv("N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook")
N8N_WHATSAPP_PATH = os.getenv("N8N_WHATSAPP_PATH", "/whatsapp-send")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

# Retry & Timeout
WHATSAPP_RETRY_COUNT = int(os.getenv("WHATSAPP_RETRY_COUNT", "3"))
WHATSAPP_BACKOFF_FACTOR = float(os.getenv("WHATSAPP_BACKOFF_FACTOR", "1.5"))
WHATSAPP_TIMEOUT_SECONDS = int(os.getenv("WHATSAPP_TIMEOUT_SECONDS", "30"))

# Default phone contacts directory or file path
CONTACTS_DB_PATH = os.getenv("CONTACTS_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "history.db"))
