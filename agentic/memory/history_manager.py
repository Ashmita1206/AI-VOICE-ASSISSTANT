"""
History Manager
===============

Handles reading and querying from the SessionState command history.
"""

from typing import List, Dict, Any
from agentic.memory.session_state import get_session

def get_last_command() -> str:
    """Return a summary of the last command."""
    session = get_session()
    if not session.conversation_history:
        return "You haven't asked anything yet."
        
    last = session.conversation_history[-1]
    return f"Your last command was: '{last['transcript']}'"

def get_recent_commands(limit: int = 3) -> str:
    """Return a numbered list of the most recent commands."""
    session = get_session()
    if not session.conversation_history:
        return "No recent commands found."
        
    recent = session.conversation_history[-limit:]
    lines = []
    for i, entry in enumerate(recent, 1):
        lines.append(f"{i}. {entry['transcript']}")
        
    return "\n".join(lines)

def search_history(keyword: str) -> List[Dict[str, Any]]:
    """Search the ephemeral conversation history for a keyword."""
    session = get_session()
    keyword = keyword.lower()
    return [
        entry for entry in session.conversation_history
        if keyword in entry["transcript"].lower() or keyword in entry["result"].lower()
    ]
