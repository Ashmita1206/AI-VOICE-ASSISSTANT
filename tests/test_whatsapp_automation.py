"""
WhatsApp UI Automation Search Tests
====================================

Unit tests for WhatsApp specific in-app search using UI Automation.
Mocks all GUI, OS, and process dependencies to run deterministically.
"""

import sys
import time
from unittest.mock import MagicMock, patch, call
import pytest

from execution.schemas import ExecutionResult
from automation.desktop import search_inside_application
from automation.whatsapp import open_whatsapp
from collections import namedtuple

Rect = namedtuple("Rect", ["left", "top", "right", "bottom"])

def create_uia_mock(name="UIAMock", control_type="EditControl", is_enabled=True, is_offscreen=False, exists=True, has_focus=False, rect=None):
    m = MagicMock(name=name)
    m.ControlTypeName = control_type
    m.Name = name
    m.IsEnabled = is_enabled
    m.IsOffscreen = is_offscreen
    m.Exists.return_value = exists
    m.HasKeyboardFocus = has_focus
    if rect:
        m.BoundingRectangle = rect
    else:
        m.BoundingRectangle = Rect(100, 100, 200, 150)
    return m

@pytest.fixture
def mock_automation_env():
    # Setup mocks for all dependencies
    with patch("automation.desktop.win32gui") as mock_win32gui, \
         patch("automation.desktop.win32process") as mock_win32process, \
         patch("automation.desktop.pyautogui") as mock_pyautogui, \
         patch("automation.desktop.get_active_app_name") as mock_get_app, \
         patch("uiautomation.GetRootControl") as mock_get_root, \
         patch("pyperclip.paste") as mock_paste, \
         patch("pyperclip.copy") as mock_copy, \
         patch("automation.desktop.time.sleep") as mock_sleep:
         
        # Set up default returns
        mock_win32gui.GetForegroundWindow.return_value = 11111
        mock_win32gui.GetWindowText.return_value = "WhatsApp - Microsoft Edge"
        mock_get_app.return_value = "msedge"
        
        # Setup UIA controls
        mock_active_win = MagicMock(name="ActiveWin")
        mock_active_win.NativeWindowHandle = 11111
        mock_active_win.Name = "WhatsApp - Microsoft Edge"
        mock_active_win.ClassName = "Chrome_WidgetWin_1"
        mock_active_win.BoundingRectangle = Rect(0, 0, 1920, 1080)

        mock_root = MagicMock(name="Root")
        mock_root.GetChildren.return_value = [mock_active_win]
        mock_get_root.return_value = mock_root
        
        # Configure default Control return to keep hierarchy chain
        mock_active_win.Control.return_value = mock_active_win
        
        # Configure default Exists to False to prevent false positives in direct search loop
        mock_active_win.Control.return_value.EditControl.return_value.Exists.return_value = False
        mock_active_win.Control.return_value.DocumentControl.return_value.Exists.return_value = False
        mock_active_win.Control.return_value.CustomControl.return_value.Exists.return_value = False
        
        mock_active_win.EditControl.return_value.Exists.return_value = False
        mock_active_win.DocumentControl.return_value.Exists.return_value = False
        mock_active_win.CustomControl.return_value.Exists.return_value = False
        
        yield {
            "win32gui": mock_win32gui,
            "win32process": mock_win32process,
            "pyautogui": mock_pyautogui,
            "get_active_app_name": mock_get_app,
            "root": mock_root,
            "active_win": mock_active_win,
            "paste": mock_paste,
            "copy": mock_copy,
            "sleep": mock_sleep
        }

def test_whatsapp_search_active_window_success(mock_automation_env):
    """WhatsApp is already active, search box found, focus verified, text typed and verified, and chat verified successfully."""
    mocks = mock_automation_env
    mock_active_win = mocks["active_win"]
    
    # 1. Setup mock search box
    mock_search_box = create_uia_mock(name="Search or start new chat", exists=True, has_focus=False)
    from unittest.mock import PropertyMock
    type(mock_search_box).HasKeyboardFocus = PropertyMock(side_effect=[False, True, True, True, True, True])
    
    mock_active_win.Control.return_value.EditControl.return_value = mock_search_box
    mock_active_win.EditControl.return_value = mock_search_box
    mock_active_win.GetChildren.return_value = [mock_search_box]
    
    # Mock message textbox for chat open verification (Name="Type a message")
    mock_msg_box = create_uia_mock(name="Type a message", control_type="EditControl", exists=True)
    # Configure verify_chat_opened to find it
    mock_active_win.Control.side_effect = lambda *args, **kwargs: mock_msg_box if kwargs.get("Name") == "Type a message" else mock_active_win
    
    # Mock dynamic import of uiautomation WindowControl inside desktop.py
    with patch("uiautomation.WindowControl") as mock_window_class:
        mock_window_class.return_value = mock_active_win
        
        # Clipboard returns expected query
        mocks["paste"].return_value = "Harshita"
        
        res = search_inside_application({"query": "Harshita", "application": "whatsapp"})
        
        assert res.success is True
        assert "WhatsApp via UIA" in res.message
        assert res.metadata == {"hwnd": 11111}
        
        # Verify pyautogui clicks & types
        # Note: click is on center of Rect(100, 100, 200, 150) which is (150, 125)
        mocks["pyautogui"].click.assert_called_once_with(150, 125)
        mocks["pyautogui"].write.assert_called_once_with("Harshita", interval=0.02)
        mocks["pyautogui"].press.assert_has_calls([call("backspace"), call("right"), call("down"), call("enter")])

def test_whatsapp_search_box_disabled(mock_automation_env):
    """WhatsApp is active but search box is disabled, returns failure."""
    mocks = mock_automation_env
    mock_active_win = mocks["active_win"]
    
    mock_search_box = create_uia_mock(name="Search or start new chat", is_enabled=False, exists=True)
    mock_active_win.Control.return_value.EditControl.return_value = mock_search_box
    mock_active_win.EditControl.return_value = mock_search_box
    mock_active_win.GetChildren.return_value = [mock_search_box]
    
    with patch("uiautomation.WindowControl") as mock_window_class:
        mock_window_class.return_value = mock_active_win
        
        res = search_inside_application({"query": "Harshita", "application": "whatsapp"})
        
        assert res.success is False
        assert "Search control disabled" in res.message

def test_whatsapp_search_box_hidden(mock_automation_env):
    """WhatsApp is active but search box is hidden/offscreen, returns failure."""
    mocks = mock_automation_env
    mock_active_win = mocks["active_win"]
    
    mock_search_box = create_uia_mock(name="Search or start new chat", is_offscreen=False, exists=True)
    from unittest.mock import PropertyMock
    type(mock_search_box).IsOffscreen = PropertyMock(side_effect=[False, False, False, True, True, True, True])
    mock_active_win.Control.return_value.EditControl.return_value = mock_search_box
    mock_active_win.EditControl.return_value = mock_search_box
    mock_active_win.GetChildren.return_value = [mock_search_box]
    
    with patch("uiautomation.WindowControl") as mock_window_class:
        mock_window_class.return_value = mock_active_win
        
        res = search_inside_application({"query": "Harshita", "application": "whatsapp"})
        
        assert res.success is False
        assert "Search control hidden" in res.message

def test_whatsapp_search_box_not_found_timeout(mock_automation_env):
    """WhatsApp search control never becomes available during polling timeout, returns timeout reason."""
    mocks = mock_automation_env
    mock_active_win = mocks["active_win"]
    
    # Direct find fails
    mock_active_win.EditControl.return_value.Exists.return_value = False
    mock_active_win.Control.return_value.EditControl.return_value.Exists.return_value = False
    
    # Recursive walk returns nothing
    mock_active_win.GetChildren.return_value = []
    mocks["root"].GetChildren.return_value = [mock_active_win]
    
    with patch("uiautomation.WindowControl") as mock_window_class:
        mock_window_class.return_value = mock_active_win
        
        # Use an incrementing generator for time.time to avoid raising StopIteration
        current_time = [100.0]
        def mock_time_func():
            current_time[0] += 5.0
            return current_time[0]
            
        with patch("time.time", side_effect=mock_time_func):
            res = search_inside_application({"query": "Harshita", "application": "whatsapp"})
            
            assert res.success is False
            assert "Search control never became available" in res.message

def test_whatsapp_search_chat_opening_fails(mock_automation_env):
    """WhatsApp is active, typing succeeds, but chat opening verification fails, returns failure."""
    mocks = mock_automation_env
    mock_active_win = mocks["active_win"]
    
    mock_search_box = create_uia_mock(name="Search or start new chat", exists=True, has_focus=True)
    mock_active_win.Control.return_value.EditControl.return_value = mock_search_box
    mock_active_win.EditControl.return_value = mock_search_box
    
    # Chat message box does NOT appear
    mock_msg_box = create_uia_mock(name="Type a message", exists=False)
    mock_active_win.Control.side_effect = lambda *args, **kwargs: mock_msg_box if kwargs.get("Name") == "Type a message" else mock_active_win
    mock_active_win.GetChildren.return_value = [mock_search_box]
    
    with patch("uiautomation.WindowControl") as mock_window_class:
        mock_window_class.return_value = mock_active_win
        
        mocks["paste"].return_value = "Harshita"
        
        res = search_inside_application({"query": "Harshita", "application": "whatsapp"})
        
        assert res.success is False
        assert "Conversation did not open" in res.message

def test_whatsapp_tab_reuse_open(mock_automation_env):
    """Test that open_whatsapp reuses an existing WhatsApp tab if found."""
    mocks = mock_automation_env
    
    # Mock window which contains the WhatsApp tab
    mock_browser = MagicMock(name="Browser")
    mock_browser.Name = "Microsoft Edge"
    mock_browser.NativeWindowHandle = 33333
    
    # Mock UIA root to list browser window
    mocks["root"].GetChildren.return_value = [mock_browser]
    
    # Mock tab item
    mock_tab = MagicMock(name="Tab")
    mock_tab.ControlTypeName = "TabItemControl"
    mock_tab.Name = "WhatsApp"
    mock_tab.GetSelectionItemPattern.return_value.Select = MagicMock()
    
    # Recursive tab finder matches it
    mock_browser.GetChildren.return_value = [mock_tab]
    
    with patch("automation.whatsapp.win32gui", create=True) as mock_w32gui:
        mock_w32gui.GetForegroundWindow.return_value = 11111
        mock_w32gui.SetForegroundWindow = MagicMock()
        mock_w32gui.IsWindowVisible.return_value = True
        
        res = open_whatsapp({})
        
        assert res.success is True
        assert "WhatsApp tab reused" in res.message
        assert res.metadata["hwnd"] == 33333
        assert res.metadata["reused_window"] is True
        
        # Verify tab select was called
        mock_tab.GetSelectionItemPattern.return_value.Select.assert_called_once()
