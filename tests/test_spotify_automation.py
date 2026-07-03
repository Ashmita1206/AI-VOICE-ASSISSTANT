"""
Spotify Automation Tests
========================

Unit tests for Spotify specific in-app interactions.
Mocks all GUI, OS, and process dependencies to run deterministically.
"""

import sys
import time
from unittest.mock import MagicMock, patch, call
import pytest

from execution.schemas import ExecutionResult
from automation.desktop import search_inside_application
from automation.applications import perform_app_action

# Minimal mock class for proc
class MockProc:
    def __init__(self, pid, name):
        self.pid = pid
        self._name = name
    def info(self):
        return {"pid": self.pid, "name": self._name}
    def name(self):
        return self._name

@pytest.fixture
def mock_win32_and_psutil():
    # Setup processes
    mock_spotify_proc = MagicMock()
    mock_spotify_proc.info = {"pid": 9999, "name": "Spotify.exe"}
    
    with patch("automation.desktop.psutil") as mock_psutil, \
         patch("automation.desktop.win32gui") as mock_win32gui, \
         patch("automation.desktop.win32process") as mock_win32process, \
         patch("automation.desktop.win32con") as mock_win32con, \
         patch("automation.desktop.pyautogui") as mock_pyautogui:
         
        mock_psutil.process_iter.return_value = [mock_spotify_proc]
        mock_win32process.GetWindowThreadProcessId.return_value = (0, 9999)
        mock_win32gui.IsWindowVisible.return_value = True
        
        yield {
            "psutil": mock_psutil,
            "win32gui": mock_win32gui,
            "win32process": mock_win32process,
            "pyautogui": mock_pyautogui,
            "win32con": mock_win32con
        }

def test_spotify_search_strategy_1_success(mock_win32_and_psutil):
    """If Quick Search (Ctrl+K) succeeds and verification passes, strategy 1 completes."""
    mocks = mock_win32_and_psutil
    
    # Mock EnumWindows to return window handles
    def mock_enum(cb, extra):
        cb(12345, None)  # hwnd=12345
        return True
    mocks["win32gui"].EnumWindows.side_effect = mock_enum
    
    # Discovery: "Spotify Premium", Verification: "Believer - Imagine Dragons"
    window_texts = ["Spotify Premium", "Believer - Imagine Dragons"]
    mocks["win32gui"].GetWindowText.side_effect = lambda hwnd: window_texts.pop(0) if window_texts else "Believer - Imagine Dragons"

    res = search_inside_application({"query": "Believer"})
    
    assert res.success is True
    assert "Quick Search" in res.message
    
    # Assert hotkeys sent for Strategy 1
    mocks["pyautogui"].hotkey.assert_any_call("ctrl", "k")
    mocks["pyautogui"].write.assert_called_with("Believer", interval=0.03)
    mocks["pyautogui"].press.assert_called_with("enter")

def test_spotify_strategy_1_fails_strategy_2_success(mock_win32_and_psutil):
    """If Quick Search fails verification, falls back to Strategy 2 (Ctrl+L) and verification passes."""
    mocks = mock_win32_and_psutil
    
    def mock_enum(cb, extra):
        cb(12345, None)
        return True
    mocks["win32gui"].EnumWindows.side_effect = mock_enum
    
    # Dynamically determine the window title based on whether Strategy 2 (Ctrl+L) has been triggered yet.
    # This prevents the fast polling loop (with mocked sleep) from prematurely succeeding on Strategy 1.
    def get_title(hwnd):
        calls = [c[0] for c in mocks["pyautogui"].hotkey.call_args_list]
        if ("ctrl", "l") in calls:
            return "Believer - Imagine Dragons"  # Playing
        return "Spotify"  # Paused / not started

    mocks["win32gui"].GetWindowText.side_effect = get_title

    # Patch time.sleep in desktop.py to avoid delay during polling
    with patch("automation.desktop.time.sleep") as mock_sleep:
        res = search_inside_application({"query": "Believer"})

    assert res.success is True
    assert "Main Search" in res.message
    
    # Strategy 1 was called
    mocks["pyautogui"].hotkey.assert_any_call("ctrl", "k")
    # Strategy 2 was called as fallback
    mocks["pyautogui"].hotkey.assert_any_call("ctrl", "l")
    mocks["pyautogui"].press.assert_any_call("tab")

def test_spotify_max_attempts_exhaustion(mock_win32_and_psutil):
    """If both strategies fail to start playback across all attempts, reports failure."""
    mocks = mock_win32_and_psutil
    
    def mock_enum(cb, extra):
        cb(12345, None)
        return True
    mocks["win32gui"].EnumWindows.side_effect = mock_enum
    
    # Window title is always "Spotify" (no song playing)
    mocks["win32gui"].GetWindowText.return_value = "Spotify"

    with patch("automation.desktop.time.sleep") as mock_sleep:
        res = search_inside_application({"query": "Believer"})

    assert res.success is False
    assert "Failed to play" in res.message
    assert mocks["win32gui"].EnumWindows.call_count > 2

def test_perform_app_action_delegation(mock_win32_and_psutil):
    """perform_app_action delegates to search_inside_application when app is spotify and action is play."""
    mocks = mock_win32_and_psutil
    
    # Mock for applications.py to resolve the process
    mock_spotify_proc = MagicMock()
    mock_spotify_proc.info = {"pid": 9999, "name": "Spotify.exe"}
    mocks["psutil"].process_iter.return_value = [mock_spotify_proc]
    
    def mock_enum(cb, extra):
        cb(12345, None)
        return True
    mocks["win32gui"].EnumWindows.side_effect = mock_enum
    
    # Safe side effect that won't raise StopIteration
    titles = ["Spotify Premium", "Spotify Premium", "Believer - Imagine Dragons"]
    mocks["win32gui"].GetWindowText.side_effect = lambda hwnd: titles.pop(0) if titles else "Believer - Imagine Dragons"

    res = perform_app_action({
        "app": "spotify",
        "action": "play",
        "payload": {"song": "Believer"}
    })
    
    assert res.success is True
    assert res.tool == "perform_app_action"
    assert "Quick Search" in res.message
