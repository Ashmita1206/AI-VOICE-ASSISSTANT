"""
Workflow Manager
================

Resurrects interrupted or cancelled tasks.
"""

import re
from typing import Tuple, Optional
from agentic.memory.session_state import get_session

RESUME_QUERY = re.compile(r"^(resume|continue)( previous task| last task| sending message)?$", re.IGNORECASE)

def check_resume_workflow(transcript: str) -> Tuple[bool, Optional[str]]:
    """Check if the user wants to resume an interrupted action."""
    text = re.sub(r"[^\w\s]", "", transcript).strip().lower()
    
    if RESUME_QUERY.match(text):
        session = get_session()
        
        if session.interrupted_task:
            # Re-queue it as pending
            session.pending_action = session.interrupted_task
            session.interrupted_task = None
            # Update timestamp so it doesn't immediately timeout
            import time
            session.pending_action["timestamp"] = time.time()
            
            return True, f"Resuming: {session.pending_action['message']}"
            
        return True, "There is no previous task to resume."
        
    return False, None
