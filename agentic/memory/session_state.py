"""
Session State Manager
=====================

Maintains the ephemeral, cross-turn state of the conversation and workflow.
"""

import time
import uuid
from typing import Any, Dict, List, Optional
import threading

class SessionState:
    """Singleton representing the current active session state."""
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SessionState, cls).__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self):
        self.pending_action: Optional[Dict[str, Any]] = None
        self.last_application: Optional[str] = None
        self.last_active_app: Optional[str] = None
        self.last_directory: Optional[str] = None
        self.last_contact: Optional[str] = None
        self.last_song: Optional[str] = None
        self.last_search_query: Optional[str] = None
        self.current_task: Optional[str] = None
        self.task_status: Optional[str] = None
        self.task_started_at: Optional[float] = None
        self.interrupted_task: Optional[Dict[str, Any]] = None
        self.conversation_history: List[Dict[str, Any]] = []

    def set_pending_action(self, tool: str, args: Dict[str, Any], message: str) -> str:
        """Set an action that requires user confirmation.
        
        Returns the generated confirmation_id (UUID).
        """
        confirmation_id = uuid.uuid4().hex[:16]
        self.pending_action = {
            "id": confirmation_id,
            "tool": tool,
            "args": args,
            "message": message,
            "timestamp": time.time(),
            "created_at": time.time(),
        }
        return confirmation_id
        
    def clear_pending_action(self):
        self.pending_action = None

    def get_pending_by_id(self, confirmation_id: str) -> Optional[Dict[str, Any]]:
        """Look up the pending action by its confirmation ID.
        
        Returns the pending action dict if the ID matches, else None.
        """
        if self.pending_action and self.pending_action.get("id") == confirmation_id:
            return self.pending_action
        return None

    def get_pending_confirmation(self) -> Optional[Dict[str, Any]]:
        """Return the current pending confirmation in API-friendly format.
        
        Returns None if no pending action or if it has timed out.
        """
        if not self.pending_action:
            return None
        
        # Auto-expire timed-out confirmations
        if self.is_confirmation_timeout():
            self.clear_pending_action()
            return None
        
        action = self.pending_action
        elapsed = time.time() - action["timestamp"]
        return {
            "id": action["id"],
            "tool": action["tool"],
            "args": action["args"],
            "message": action["message"],
            "created_at": action["created_at"],
            "remaining_seconds": max(0, int(60 - elapsed)),
        }

    def is_confirmation_timeout(self) -> bool:
        """Check if the pending action has exceeded the 60s timeout."""
        if not self.pending_action:
            return False
        elapsed = time.time() - self.pending_action["timestamp"]
        return elapsed > 60.0

    def add_history(self, transcript: str, intent: str, plan: Dict[str, Any], result: str):
        """Add a command to the short-term conversation history."""
        self.conversation_history.append({
            "timestamp": time.time(),
            "transcript": transcript,
            "intent": intent,
            "plan": plan,
            "result": result
        })
        
        # Keep only the last 20 turns in memory
        if len(self.conversation_history) > 20:
            self.conversation_history.pop(0)

    def set_context(self, app=None, directory=None, contact=None, song=None, search_query=None):
        """Update recent context entities."""
        if app:
            self.last_application = app
            self.last_active_app = app
        if directory:
            self.last_directory = directory
        if contact:
            self.last_contact = contact
        if song:
            self.last_song = song
        if search_query:
            self.last_search_query = search_query

    def clear_all(self):
        """Reset the session state entirely."""
        self._init_state()

def get_session() -> SessionState:
    return SessionState()
