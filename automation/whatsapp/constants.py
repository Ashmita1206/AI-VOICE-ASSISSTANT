"""
WhatsApp Automation Constants
==============================
"""

# Tool Name
TOOL_NAME_WHATSAPP_SEND = "send_whatsapp_automation"

# Action & Intent Names
ACTION_SEND_WHATSAPP = "send_whatsapp"
INTENT_WHATSAPP_SEND = "send_whatsapp_message"

# LangGraph Node State Names
STATE_INTENT = "Intent"
STATE_EXTRACT_ENTITIES = "ExtractEntities"
STATE_VALIDATE = "Validate"
STATE_LOOKUP_CONTACT = "LookupContact"
STATE_CONFIRMATION = "Confirmation"
STATE_EXECUTE_TOOL = "ExecuteTool"
STATE_RETRY = "Retry"
STATE_SUCCESS = "Success"
STATE_FAILURE = "Failure"
STATE_WAITING_USER_INPUT = "WaitingUserInput"

# Lookup Statuses
LOOKUP_STATUS_EXACT = "exact_match"
LOOKUP_STATUS_PARTIAL = "partial_match"
LOOKUP_STATUS_NICKNAME = "nickname_match"
LOOKUP_STATUS_MULTIPLE = "multiple_matches"
LOOKUP_STATUS_NOT_FOUND = "not_found"

# Default Retries
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 1.5
