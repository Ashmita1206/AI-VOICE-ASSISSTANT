"""
WhatsApp Automation Prompts
===========================

LangChain PromptTemplates for recipient extraction, message extraction,
user confirmation, contact ambiguity resolution, and error response formatting.
No hardcoded prompt strings in logic code.
"""

from langchain_core.prompts import PromptTemplate

# Prompt 1: Extract Recipient/Contact Name
EXTRACT_CONTACT_PROMPT = PromptTemplate(
    input_variables=["user_input"],
    template="""Extract the target recipient or contact name from the user's input.
User input: "{user_input}"

Return ONLY the contact name. If no contact name is mentioned, return "UNKNOWN".
Contact Name:"""
)

# Prompt 2: Extract Message Text
EXTRACT_MESSAGE_PROMPT = PromptTemplate(
    input_variables=["user_input", "recipient"],
    template="""Extract the message text to be sent from the user's input.
User input: "{user_input}"
Target recipient: "{recipient}"

Return ONLY the message content to be sent. If no message content is mentioned, return "UNKNOWN".
Message Content:"""
)

# Prompt 3: Confirmation Message
CONFIRMATION_PROMPT = PromptTemplate(
    input_variables=["recipient", "phone_number", "message"],
    template="""Should I send this WhatsApp message to {recipient} ({phone_number})?

Message: "{message}"

Reply with "proceed" to send or "cancel" to cancel."""
)

# Prompt 4: Ambiguity Resolution
AMBIGUITY_PROMPT = PromptTemplate(
    input_variables=["recipient", "candidates_str"],
    template="""Multiple contacts found matching "{recipient}":
{candidates_str}

Please specify which contact you would like to send the message to."""
)

# Prompt 5: Retry Format
RETRY_PROMPT = PromptTemplate(
    input_variables=["attempt", "max_retries", "error_message"],
    template="""WhatsApp delivery failed (attempt {attempt}/{max_retries}): {error_message}. Retrying execution..."""
)
