"""
Status Manager
==============

Answers meta-questions about what the agent is currently doing or what it has done.
"""

import re
from agentic.memory.session_state import get_session
from agentic.memory.history_manager import get_last_command, get_recent_commands

STATUS_QUERIES = re.compile(
    r"^(what are you doing|current task|status|are you busy|what did i ask before|show my recent commands)",
    re.IGNORECASE
)

def check_status_query(transcript: str) -> str | None:
    """Intercept meta-questions and return the status without LLM processing."""
    text = re.sub(r"[^\w\s]", "", transcript).strip().lower()
    
    if "what did i ask before" in text:
        return get_last_command()
        
    if "recent commands" in text:
        return get_recent_commands(limit=3)
        
    if "what are you doing" in text or "status" in text or "current task" in text:
        session = get_session()
        
        lines = ["I am currently:"]
        is_busy = False
        
        if session.current_task:
            lines.append(f"- Executing task: {session.current_task}")
            is_busy = True
            
        if session.pending_action:
            lines.append(f"- Waiting for confirmation to {session.pending_action['tool'].replace('_', ' ')}")
            is_busy = True
            
        if not is_busy:
            return "I am currently idle. How can I help you?"
            
        return "\n".join(lines)
        
    return None
