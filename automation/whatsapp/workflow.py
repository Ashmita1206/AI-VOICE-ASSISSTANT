"""
LangGraph StateMachine Workflow for WhatsApp Automation
=========================================================

Implements StateGraph nodes & transitions for:
  - Intent
  - ExtractEntities
  - LookupContact
  - Validate
  - Confirmation
  - ExecuteTool
  - Retry
  - Success
  - Failure
  - WaitingUserInput
"""

from __future__ import annotations
import logging
from typing import Any, Dict
from langgraph.graph import StateGraph, END
from automation.whatsapp.schemas import WhatsAppWorkflowState
from automation.whatsapp.constants import (
    STATE_INTENT,
    STATE_EXTRACT_ENTITIES,
    STATE_LOOKUP_CONTACT,
    STATE_VALIDATE,
    STATE_CONFIRMATION,
    STATE_EXECUTE_TOOL,
    STATE_RETRY,
    STATE_SUCCESS,
    STATE_FAILURE,
    STATE_WAITING_USER_INPUT,
)
from automation.whatsapp.contact_lookup import ContactLookupService
from automation.whatsapp.service import WhatsAppAutomation
from automation.whatsapp.validator import WhatsAppValidator
from automation.whatsapp.formatter import WhatsAppFormatter
from automation.whatsapp.config import WHATSAPP_RETRY_COUNT

logger = logging.getLogger("automation.whatsapp.workflow")


# ── Node Handler Functions ───────────────────────────────────────────

def intent_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Classify intent and initialize workflow state."""
    logger.info("[LANGGRAPH] Node: Intent input='%s'", state.get("user_input", ""))
    return {
        "intent": "send_whatsapp_message",
        "current_state": STATE_INTENT,
        "attempts": state.get("attempts", 0),
        "max_retries": state.get("max_retries", WHATSAPP_RETRY_COUNT),
    }


def extract_entities_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Extract recipient contact and message body from user input."""
    user_input = state.get("user_input", "")
    recipient = state.get("recipient", "")
    message = state.get("message", "")

    # Basic heuristic / entity parser if not already provided
    if not recipient or not message:
        import re
        to_match = re.search(r"send\s+(?:a\s+)?(?:whatsapp\s+)?(?:message\s+)?to\s+([A-Za-z0-9\s]+?)\s+(?:saying|that|with)\s+(.+)", user_input, re.IGNORECASE)
        if to_match:
            recipient = recipient or to_match.group(1).strip()
            message = message or to_match.group(2).strip()
        else:
            w_match = re.search(r"whatsapp\s+([A-Za-z0-9\s]+?)\s+(?:saying|that|with)\s+(.+)", user_input, re.IGNORECASE)
            if w_match:
                recipient = recipient or w_match.group(1).strip()
                message = message or w_match.group(2).strip()

    logger.info("[LANGGRAPH] Node: ExtractEntities recipient='%s' message='%s'", recipient, message)
    return {
        "recipient": recipient,
        "message": message,
        "current_state": STATE_EXTRACT_ENTITIES,
    }


def lookup_contact_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Perform multi-strategy contact lookup in SQLite phonebook."""
    recipient = state.get("recipient", "")
    lookup_service = ContactLookupService()
    lookup_res = lookup_service.search(recipient)

    logger.info("[LANGGRAPH] Node: LookupContact status='%s'", lookup_res.status)

    if lookup_res.status == "multiple_matches":
        candidates = [c.model_dump() for c in lookup_res.candidates]
        return {
            "candidate_contacts": candidates,
            "current_state": STATE_WAITING_USER_INPUT,
            "output_response": f"Multiple contacts found for '{recipient}'. Please select:\n" + WhatsAppFormatter.format_candidates_list(lookup_res.candidates),
        }
    elif lookup_res.selected_contact:
        c = lookup_res.selected_contact
        return {
            "recipient": c.name,
            "phone_number": c.phone_number,
            "contact_info": c.model_dump(),
            "current_state": STATE_LOOKUP_CONTACT,
        }
    else:
        return {
            "current_state": STATE_FAILURE,
            "last_error": f"Contact '{recipient}' not found in phonebook.",
            "output_response": f"Sorry, I could not find '{recipient}' in your contacts.",
        }


def validate_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Validate payload fields (recipient, phone number, message text)."""
    recipient = state.get("recipient", "")
    phone_number = state.get("phone_number", "")
    message = state.get("message", "")

    is_valid, err_msg = WhatsAppValidator.validate_payload(recipient, phone_number, message)
    logger.info("[LANGGRAPH] Node: Validate is_valid=%s err='%s'", is_valid, err_msg)

    if not is_valid:
        return {
            "is_valid": False,
            "validation_error": err_msg,
            "current_state": STATE_FAILURE,
            "last_error": err_msg,
            "output_response": f"Validation failed: {err_msg}",
        }

    return {
        "is_valid": True,
        "validation_error": "",
        "current_state": STATE_VALIDATE,
    }


def confirmation_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Check user confirmation requirement."""
    confirmed = state.get("confirmed", False)
    confirmation_required = state.get("confirmation_required", True)

    if confirmation_required and not confirmed:
        prompt_text = WhatsAppFormatter.format_confirmation_prompt(
            state.get("recipient", ""),
            state.get("phone_number", ""),
            state.get("message", ""),
        )
        return {
            "current_state": STATE_WAITING_USER_INPUT,
            "output_response": prompt_text,
        }

    return {
        "current_state": STATE_CONFIRMATION,
    }


def execute_tool_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Execute WhatsAppAutomation tool."""
    attempts = state.get("attempts", 0) + 1
    logger.info("[LANGGRAPH] Node: ExecuteTool attempt %d", attempts)

    whatsapp_service = WhatsAppAutomation()
    exec_res = whatsapp_service.execute({
        "recipient": state.get("recipient"),
        "phone_number": state.get("phone_number"),
        "message": state.get("message"),
    })

    if exec_res.success:
        return {
            "attempts": attempts,
            "execution_result": exec_res.to_dict(),
            "output_response": exec_res.message,
            "current_state": STATE_SUCCESS,
        }

    return {
        "attempts": attempts,
        "last_error": exec_res.message,
        "execution_result": exec_res.to_dict(),
        "current_state": STATE_RETRY if attempts < state.get("max_retries", WHATSAPP_RETRY_COUNT) else STATE_FAILURE,
    }


def retry_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Backoff retry node."""
    logger.warning("[LANGGRAPH] Node: Retry attempt %d error='%s'", state.get("attempts", 0), state.get("last_error", ""))
    return {
        "current_state": STATE_RETRY,
    }


def success_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Final success terminal state."""
    logger.info("[LANGGRAPH] Node: Success response='%s'", state.get("output_response", ""))
    return {
        "current_state": STATE_SUCCESS,
    }


def failure_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Final failure terminal state."""
    logger.error("[LANGGRAPH] Node: Failure error='%s'", state.get("last_error", ""))
    return {
        "current_state": STATE_FAILURE,
        "output_response": state.get("output_response") or f"Failed to execute WhatsApp automation: {state.get('last_error')}",
    }


def waiting_user_input_node(state: WhatsAppWorkflowState) -> Dict[str, Any]:
    """Node: Waiting for user input / clarification state."""
    logger.info("[LANGGRAPH] Node: WaitingUserInput prompt='%s'", state.get("output_response", ""))
    return {
        "current_state": STATE_WAITING_USER_INPUT,
    }


# ── Routing Conditional Edges ───────────────────────────────────────

def route_after_lookup(state: WhatsAppWorkflowState) -> str:
    current = state.get("current_state", "")
    if current == STATE_WAITING_USER_INPUT:
        return STATE_WAITING_USER_INPUT
    elif current == STATE_FAILURE:
        return STATE_FAILURE
    return STATE_VALIDATE


def route_after_validate(state: WhatsAppWorkflowState) -> str:
    if state.get("current_state") == STATE_FAILURE or not state.get("is_valid", True):
        return STATE_FAILURE
    return STATE_CONFIRMATION


def route_after_confirm(state: WhatsAppWorkflowState) -> str:
    if state.get("current_state") == STATE_WAITING_USER_INPUT:
        return STATE_WAITING_USER_INPUT
    return STATE_EXECUTE_TOOL


def route_after_execute(state: WhatsAppWorkflowState) -> str:
    current = state.get("current_state", "")
    if current == STATE_SUCCESS:
        return STATE_SUCCESS
    elif current == STATE_RETRY:
        return STATE_RETRY
    return STATE_FAILURE


# ── Build LangGraph StateGraph ───────────────────────────────────────

def create_whatsapp_workflow() -> StateGraph:
    """Build and compile the LangGraph StateGraph for WhatsApp automation."""
    workflow = StateGraph(WhatsAppWorkflowState)

    workflow.add_node(STATE_INTENT, intent_node)
    workflow.add_node(STATE_EXTRACT_ENTITIES, extract_entities_node)
    workflow.add_node(STATE_LOOKUP_CONTACT, lookup_contact_node)
    workflow.add_node(STATE_VALIDATE, validate_node)
    workflow.add_node(STATE_CONFIRMATION, confirmation_node)
    workflow.add_node(STATE_EXECUTE_TOOL, execute_tool_node)
    workflow.add_node(STATE_RETRY, retry_node)
    workflow.add_node(STATE_SUCCESS, success_node)
    workflow.add_node(STATE_FAILURE, failure_node)
    workflow.add_node(STATE_WAITING_USER_INPUT, waiting_user_input_node)

    # Graph Edges
    workflow.set_entry_point(STATE_INTENT)
    workflow.add_edge(STATE_INTENT, STATE_EXTRACT_ENTITIES)
    workflow.add_edge(STATE_EXTRACT_ENTITIES, STATE_LOOKUP_CONTACT)

    workflow.add_conditional_edges(
        STATE_LOOKUP_CONTACT,
        route_after_lookup,
        {
            STATE_WAITING_USER_INPUT: STATE_WAITING_USER_INPUT,
            STATE_FAILURE: STATE_FAILURE,
            STATE_VALIDATE: STATE_VALIDATE,
        },
    )

    workflow.add_conditional_edges(
        STATE_VALIDATE,
        route_after_validate,
        {
            STATE_FAILURE: STATE_FAILURE,
            STATE_CONFIRMATION: STATE_CONFIRMATION,
        },
    )

    workflow.add_conditional_edges(
        STATE_CONFIRMATION,
        route_after_confirm,
        {
            STATE_WAITING_USER_INPUT: STATE_WAITING_USER_INPUT,
            STATE_EXECUTE_TOOL: STATE_EXECUTE_TOOL,
        },
    )

    workflow.add_conditional_edges(
        STATE_EXECUTE_TOOL,
        route_after_execute,
        {
            STATE_SUCCESS: STATE_SUCCESS,
            STATE_RETRY: STATE_RETRY,
            STATE_FAILURE: STATE_FAILURE,
        },
    )

    workflow.add_edge(STATE_RETRY, STATE_EXECUTE_TOOL)
    workflow.add_edge(STATE_SUCCESS, END)
    workflow.add_edge(STATE_FAILURE, END)
    workflow.add_edge(STATE_WAITING_USER_INPUT, END)

    return workflow.compile()
