"""
Application Context Manager
===========================

Tracks the currently active foreground application, window title, and handle.
"""

import os
import json
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Base directory for cache
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
APP_CONTEXT_PATH = os.path.join(CACHE_DIR, "app_context.json")

try:
    import win32gui
    import win32process
    import psutil
except ImportError:
    win32gui = None
    win32process = None
    psutil = None

class AppContextManager:
    """Manages system active application context and window handles."""

    @staticmethod
    def get_context() -> Dict[str, Any]:
        """Load the active application context from disk."""
        if os.path.exists(APP_CONTEXT_PATH):
            try:
                with open(APP_CONTEXT_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"Failed to read app context: {e}")
        return {
            "active_app": None,
            "window_handle": None,
            "last_command": None,
            "timestamp": None
        }

    @staticmethod
    def set_context(active_app: str, window_handle: Optional[str] = None, last_command: Optional[str] = None):
        """Save the active application context to disk."""
        data = {
            "active_app": active_app,
            "window_handle": str(window_handle) if window_handle is not None else None,
            "last_command": last_command,
            "timestamp": time.time()
        }
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(APP_CONTEXT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"App context updated: {active_app}")
        except Exception as e:
            logger.debug(f"Failed to save app context: {e}")

def get_active_window_info() -> Dict[str, Any]:
    """Retrieve details about the currently active foreground window on Windows."""
    if not win32gui or not win32process or not psutil:
        return {
            "active_app": None,
            "window_handle": None,
            "window_title": None
        }
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            proc_name = proc.name()
            # Remove extension
            if proc_name.lower().endswith(".exe"):
                proc_name = proc_name[:-4]
            return {
                "active_app": proc_name,
                "window_handle": str(hwnd),
                "window_title": title
            }
    except Exception as e:
        logger.debug(f"Failed to retrieve active window info: {e}")
        
    return {
        "active_app": None,
        "window_handle": None,
        "window_title": None
    }
