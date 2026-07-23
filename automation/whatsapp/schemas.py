"""
WhatsApp Automation Schemas
===========================

Pydantic schemas and LangGraph state dictionary types.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field


class ContactItem(BaseModel):
    """Schema representing a single phonebook contact entry."""
    id: Optional[int] = None
    name: str
    phone_number: str
    nickname: Optional[str] = None
    email: Optional[str] = None


class ContactLookupResult(BaseModel):
    """Result of a contact lookup query."""
    status: str  # exact_match, nickname_match, partial_match, multiple_matches, not_found
    query: str
    selected_contact: Optional[ContactItem] = None
    candidates: List[ContactItem] = Field(default_factory=list)


class WhatsAppMessagePayload(BaseModel):
    """Payload data required to dispatch a WhatsApp message."""
    recipient: str
    phone_number: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WhatsAppWorkflowState(TypedDict, total=False):
    """LangGraph State dictionary for WhatsApp automation pipeline."""
    user_input: str
    intent: str
    recipient: str
    message: str
    phone_number: str
    contact_info: Optional[Dict[str, Any]]
    candidate_contacts: List[Dict[str, Any]]
    is_valid: bool
    validation_error: str
    confirmed: bool
    confirmation_required: bool
    attempts: int
    max_retries: int
    last_error: str
    execution_result: Optional[Dict[str, Any]]
    output_response: str
    current_state: str
