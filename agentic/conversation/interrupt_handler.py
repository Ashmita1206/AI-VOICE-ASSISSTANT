"""
Interrupt Handler
=================

Detects abort/stop intents and clears current queues or pending actions.
"""

from agentic.conversation.confirmation_manager import is_negative
from agentic.memory.session_state import get_session

def check_interrupt(transcript: str) -> str | None:
    """
    If the user specifically says 'stop' or 'cancel' with no other context,
    interrupt the current workflow.
    """
    if is_negative(transcript):
        session = get_session()
        
        if session.pending_action:
            session.interrupted_task = session.pending_action
            session.clear_pending_action()
            return "Okay, I have cancelled the action."
            
        if session.current_task:
            session.current_task = None
            session.task_status = None
            return "I have stopped the current workflow."
            
        return "I have cancelled the action."
        
    return None
