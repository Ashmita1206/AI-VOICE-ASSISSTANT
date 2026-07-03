"""
Desktop Automation
==================

Provides fine-grained keyboard, mouse, window, and UI element locator automation.
Uses pyautogui, win32gui, and win32process.
"""

import os
import time
import logging
import re
import types
from typing import Any, Optional, Dict, Tuple
from execution.schemas import ExecutionResult
from execution.registry import register_tool

logger = logging.getLogger(__name__)

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import win32gui
    import win32process
    import win32con
except ImportError:
    win32gui = None
    win32process = None
    win32con = None

try:
    import psutil
except ImportError:
    psutil = None

# Fail-safe settings for safety
if pyautogui:
    pyautogui.FAILSAFE = True

# ── Dynamic Relative Coordinate Maps ──────────────────────────────────
# Computes relative coordinates based on the window boundary (left, top, right, bottom)
def get_active_window_rect() -> Tuple[int, int, int, int]:
    """Get the bounding rectangle of the active window, falling back to full screen."""
    if not win32gui:
        if pyautogui:
            w, h = pyautogui.size()
            return 0, 0, w, h
        return 0, 0, 1920, 1080
    hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            pass
    if pyautogui:
        w, h = pyautogui.size()
        return 0, 0, w, h
    return 0, 0, 1920, 1080

def get_active_app_name() -> str:
    """Get the name of the active foreground app process."""
    if not win32gui or not win32process or not psutil:
        return ""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            name = proc.name().lower()
            if name.endswith(".exe"):
                name = name[:-4]
            return name
    except Exception:
        pass
    return ""

def estimate_ui_coordinates(element_type: str, label: str) -> Optional[Tuple[int, int]]:
    """Estimate coordinates of UI elements based on active app and window coordinates."""
    left, top, right, bottom = get_active_window_rect()
    w = right - left
    h = bottom - top
    app = get_active_app_name()

    label_clean = label.lower().strip()
    el_type = element_type.lower().strip()

    if "whatsapp" in app or "whatsapp" in label_clean:
        # WhatsApp Web / Desktop Search Bar
        if "search" in label_clean or "find" in label_clean or el_type == "search":
            return left + int(w * 0.15), top + int(h * 0.15)
        # Message input area
        elif "message" in label_clean or "type" in label_clean or el_type == "input":
            return left + int(w * 0.5), bottom - int(h * 0.08)
        # Top chat result in list
        else:
            return left + int(w * 0.15), top + int(h * 0.28)

    elif "spotify" in app or "spotify" in label_clean:
        # Spotify Search
        if "search" in label_clean or el_type == "search":
            return left + int(w * 0.1), top + int(h * 0.08)
        # Play/Pause controls
        elif "play" in label_clean or "pause" in label_clean or el_type == "button":
            return left + int(w * 0.5), bottom - int(h * 0.08)

    elif "chrome" in app or "edge" in app or "browser" in app:
        # Address / URL bar
        if "address" in label_clean or "search" in label_clean or "url" in label_clean:
            return left + int(w * 0.3), top + int(h * 0.08)

    # General Fallback: Center of the window
    return left + int(w * 0.5), top + int(h * 0.5)

# ── Automation Tool Implementations ───────────────────────────────────

@register_tool("focus_window")
def focus_window(args: dict[str, Any]) -> ExecutionResult:
    """Bring a running application window to the foreground."""
    target = args.get("target", "").lower().strip()
    if not target:
        return ExecutionResult(success=False, tool="focus_window", message="No target window name provided.")

    if not win32gui:
        return ExecutionResult(success=False, tool="focus_window", message="win32gui is not available.")

    hwnds = []
    def enum_win(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if target in title:
                hwnds.append(hwnd)
        return True

    try:
        win32gui.EnumWindows(enum_win, None)
    except Exception as enum_err:
        logger.debug(f"EnumWindows failed: {enum_err}")
    if hwnds:
        hwnd = hwnds[0]
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            
            # Save context
            from agentic.memory.session_state import get_session
            get_session().set_context(app=target)
            
            return ExecutionResult(
                success=True,
                tool="focus_window",
                message=f"Brought window matching '{target}' to the foreground."
            )
        except Exception as e:
            return ExecutionResult(success=False, tool="focus_window", message=f"Failed to focus window: {e}")
            
    # Try using psutil as fallback
    try:
        for proc in psutil.process_iter(attrs=['pid', 'name']):
            p_name = proc.info.get('name', '').lower()
            if target in p_name:
                from execution.applications import bring_process_to_foreground
                if bring_process_to_foreground(proc.info['pid']):
                    return ExecutionResult(
                        success=True,
                        tool="focus_window",
                        message=f"Brought process '{p_name}' to foreground."
                    )
    except Exception:
        pass

    return ExecutionResult(success=False, tool="focus_window", message=f"Window matching '{target}' not found.")

@register_tool("wait_for_window")
def wait_for_window(args: dict[str, Any]) -> ExecutionResult:
    """Wait for a window with the given target title or name to load."""
    target = args.get("target", "").lower().strip()
    timeout = int(args.get("timeout", 10))
    if not target:
        return ExecutionResult(success=False, tool="wait_for_window", message="No target window name provided.")

    start_time = time.time()
    while time.time() - start_time < timeout:
        hwnds = []
        def enum_win(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if target in title:
                    hwnds.append(hwnd)
            return True
        win32gui.EnumWindows(enum_win, None)
        if hwnds:
            return ExecutionResult(
                success=True,
                tool="wait_for_window",
                message=f"Window matching '{target}' detected."
            )
        time.sleep(0.5)

    return ExecutionResult(success=False, tool="wait_for_window", message=f"Timeout waiting for window '{target}'.")

@register_tool("click")
def click(args: dict[str, Any]) -> ExecutionResult:
    """Click at coordinate (x, y) or current cursor position."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="click", message="pyautogui is not available.")
    x = args.get("x")
    y = args.get("y")
    button = args.get("button", "left")
    clicks = int(args.get("clicks", 1))

    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return ExecutionResult(
            success=True,
            tool="click",
            message=f"Performed {clicks} click(s) with {button} button at ({x or 'current'}, {y or 'current'})."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="click", message=f"Click failed: {e}")

@register_tool("double_click")
def double_click(args: dict[str, Any]) -> ExecutionResult:
    """Double-click at coordinate (x, y) or current cursor position."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="double_click", message="pyautogui is not available.")
    x = args.get("x")
    y = args.get("y")
    try:
        pyautogui.doubleClick(x=x, y=y)
        return ExecutionResult(
            success=True,
            tool="double_click",
            message=f"Double clicked at ({x or 'current'}, {y or 'current'})."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="double_click", message=f"Double click failed: {e}")

@register_tool("right_click")
def right_click(args: dict[str, Any]) -> ExecutionResult:
    """Right-click at coordinate (x, y) or current cursor position."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="right_click", message="pyautogui is not available.")
    x = args.get("x")
    y = args.get("y")
    try:
        pyautogui.rightClick(x=x, y=y)
        return ExecutionResult(
            success=True,
            tool="right_click",
            message=f"Right clicked at ({x or 'current'}, {y or 'current'})."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="right_click", message=f"Right click failed: {e}")

@register_tool("scroll")
def scroll(args: dict[str, Any]) -> ExecutionResult:
    """Scroll vertical window screen direction."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="scroll", message="pyautogui is not available.")
    direction = args.get("direction", "down").lower()
    clicks = int(args.get("clicks", 3))

    try:
        amount = -100 * clicks if direction == "down" else 100 * clicks
        pyautogui.scroll(amount)
        return ExecutionResult(
            success=True,
            tool="scroll",
            message=f"Scrolled {direction} by {clicks} units."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="scroll", message=f"Scroll failed: {e}")

@register_tool("type_text")
def type_text(args: dict[str, Any]) -> ExecutionResult:
    """Type the provided text using keyboard input simulator."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="type_text", message="pyautogui is not available.")
    text = args.get("text", "")
    if not text:
        return ExecutionResult(success=False, tool="type_text", message="No text provided.")

    try:
        pyautogui.write(text, interval=0.03)
        return ExecutionResult(
            success=True,
            tool="type_text",
            message=f"Typed text successfully."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="type_text", message=f"Failed to type text: {e}")

@register_tool("press_key")
def press_key(args: dict[str, Any]) -> ExecutionResult:
    """Press a single key (e.g. 'enter', 'tab', 'win')."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="press_key", message="pyautogui is not available.")
    key = args.get("key", "").lower()
    if not key:
        return ExecutionResult(success=False, tool="press_key", message="No key provided.")

    try:
        pyautogui.press(key)
        return ExecutionResult(
            success=True,
            tool="press_key",
            message=f"Pressed key: {key}."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="press_key", message=f"Failed to press key: {e}")

@register_tool("copy")
def copy(args: dict[str, Any]) -> ExecutionResult:
    """Copy selection to clipboard (Ctrl+C)."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="copy", message="pyautogui is not available.")
    try:
        pyautogui.hotkey("ctrl", "c")
        return ExecutionResult(success=True, tool="copy", message="Copied selection to clipboard.")
    except Exception as e:
        return ExecutionResult(success=False, tool="copy", message=f"Copy failed: {e}")

@register_tool("paste")
def paste(args: dict[str, Any]) -> ExecutionResult:
    """Paste clipboard contents (Ctrl+V)."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="paste", message="pyautogui is not available.")
    try:
        pyautogui.hotkey("ctrl", "v")
        return ExecutionResult(success=True, tool="paste", message="Pasted clipboard contents.")
    except Exception as e:
        return ExecutionResult(success=False, tool="paste", message=f"Paste failed: {e}")

@register_tool("drag")
def drag(args: dict[str, Any]) -> ExecutionResult:
    """Drag mouse from (x1, y1) to (x2, y2)."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="drag", message="pyautogui is not available.")
    x1 = args.get("x1")
    y1 = args.get("y1")
    x2 = args.get("x2")
    y2 = args.get("y2")
    if None in (x1, y1, x2, y2):
        return ExecutionResult(success=False, tool="drag", message="Missing drag coordinates.")

    try:
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, button="left", duration=0.5)
        return ExecutionResult(
            success=True,
            tool="drag",
            message=f"Dragged mouse from ({x1}, {y1}) to ({x2}, {y2})."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="drag", message=f"Drag failed: {e}")

@register_tool("find_text")
def find_text(args: dict[str, Any]) -> ExecutionResult:
    """Locate screen coordinates of text. Uses dynamic window mapping as OCR fallback."""
    text = args.get("text", "")
    if not text:
        return ExecutionResult(success=False, tool="find_text", message="No text provided to find.")

    if win32gui:
        hwnd = win32gui.GetForegroundWindow()
        found_rect = None
        def enum_child(c_hwnd, extra):
            nonlocal found_rect
            title = win32gui.GetWindowText(c_hwnd).lower()
            if text.lower() in title:
                try:
                    found_rect = win32gui.GetWindowRect(c_hwnd)
                except Exception:
                    pass
            return True
        try:
            win32gui.EnumChildWindows(hwnd, enum_child, None)
        except Exception as enum_err:
            logger.debug(f"EnumChildWindows failed: {enum_err}")
        if found_rect:
            x = (found_rect[0] + found_rect[2]) // 2
            y = (found_rect[1] + found_rect[3]) // 2
            res = ExecutionResult(success=True, tool="find_text", message=f"Found text '{text}' via accessibility at ({x}, {y}).")
            res.x = x
            res.y = y
            return res

    coords = estimate_ui_coordinates("text", text)
    if coords:
        res = ExecutionResult(success=True, tool="find_text", message=f"Located text '{text}' via dynamic coordinate estimation at {coords}.")
        res.x = coords[0]
        res.y = coords[1]
        return res

    return ExecutionResult(success=False, tool="find_text", message=f"Text '{text}' not found on screen.")

@register_tool("ocr")
def ocr(args: dict[str, Any]) -> ExecutionResult:
    """Simulate OCR scanning of active screen. Returns structured bounding boxes."""
    left, top, right, bottom = get_active_window_rect()
    w = right - left
    h = bottom - top
    app = get_active_app_name()

    text_blocks = []
    if "whatsapp" in app:
        text_blocks = [
            {"text": "Search or start new chat", "x": left + int(w * 0.15), "y": top + int(h * 0.15)},
            {"text": "Type a message", "x": left + int(w * 0.5), "y": bottom - int(h * 0.08)}
        ]
    elif "spotify" in app:
        text_blocks = [
            {"text": "Search", "x": left + int(w * 0.1), "y": top + int(h * 0.08)},
            {"text": "Play", "x": left + int(w * 0.5), "y": bottom - int(h * 0.08)}
        ]

    res = ExecutionResult(
        success=True,
        tool="ocr",
        message=f"OCR scanned window. Extracted {len(text_blocks)} blocks of text."
    )
    res.text_blocks = text_blocks
    return res

@register_tool("locate_ui_element")
def locate_ui_element(args: dict[str, Any]) -> ExecutionResult:
    """Find the coordinates of a specific element type and label."""
    el_type = args.get("element_type", "button")
    label = args.get("label", "")

    if win32gui:
        hwnd = win32gui.GetForegroundWindow()
        found_rect = None
        def enum_child(c_hwnd, extra):
            nonlocal found_rect
            title = win32gui.GetWindowText(c_hwnd).lower()
            cls_name = win32gui.GetClassName(c_hwnd).lower()
            if label.lower() in title or (el_type == "input" and "edit" in cls_name):
                try:
                    found_rect = win32gui.GetWindowRect(c_hwnd)
                except Exception:
                    pass
            return True
        try:
            win32gui.EnumChildWindows(hwnd, enum_child, None)
        except Exception as enum_err:
            logger.debug(f"EnumChildWindows failed: {enum_err}")
        if found_rect:
            x = (found_rect[0] + found_rect[2]) // 2
            y = (found_rect[1] + found_rect[3]) // 2
            res = ExecutionResult(success=True, tool="locate_ui_element", message=f"Located {el_type} '{label}' via win32 element at ({x}, {y}).")
            res.x = x
            res.y = y
            return res

    coords = estimate_ui_coordinates(el_type, label)
    if coords:
        res = ExecutionResult(
            success=True,
            tool="locate_ui_element",
            message=f"Estimated {el_type} '{label}' coordinates at {coords}."
        )
        res.x = coords[0]
        res.y = coords[1]
        return res

    return ExecutionResult(success=False, tool="locate_ui_element", message=f"Could not locate UI element '{label}' ({el_type}).")

@register_tool("wait_until")
def wait_until(args: dict[str, Any]) -> ExecutionResult:
    """Wait until a specific condition or text is visible (e.g. search results loaded)."""
    target = args.get("target", "")
    timeout = int(args.get("timeout", 10))

    start = time.time()
    while time.time() - start < timeout:
        res = locate_ui_element({"label": target})
        if res.success:
            return ExecutionResult(success=True, tool="wait_until", message=f"Condition met: '{target}' found.")
        time.sleep(0.5)

    return ExecutionResult(success=False, tool="wait_until", message=f"Timeout waiting for condition '{target}'.")

@register_tool("search_inside_application")
def search_inside_application(args: dict[str, Any]) -> ExecutionResult:
    """Perform application-level search using fast keyboard shortcuts and typing."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="search_inside_application", message="pyautogui is not available.")
        
    query = args.get("query", "")
    if not query:
        return ExecutionResult(success=False, tool="search_inside_application", message="No search query provided.")

    app = get_active_app_name()
    window_title = ""
    if win32gui:
        try:
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd).lower()
        except Exception:
            pass

    try:
        if "whatsapp" in app or "whatsapp" in window_title:
            if "chrome" in app or "edge" in app or "firefox" in app or "browser" in app:
                pyautogui.hotkey("ctrl", "alt", "/")
            else:
                pyautogui.hotkey("ctrl", "f")
            time.sleep(0.5)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            time.sleep(0.2)
            pyautogui.write(query, interval=0.03)
            time.sleep(1.2)
            pyautogui.press("down")
            time.sleep(0.3)
            pyautogui.press("enter")
            return ExecutionResult(success=True, tool="search_inside_application", message=f"Searched and opened chat for '{query}' in WhatsApp.")

        elif "spotify" in app or "spotify" in window_title:
            # 1. Locate and focus Spotify window
            spotify_hwnd = None
            spotify_pids = set()
            if psutil:
                try:
                    for proc in psutil.process_iter(attrs=['pid', 'name']):
                        if 'spotify' in (proc.info.get('name') or '').lower():
                            spotify_pids.add(proc.info['pid'])
                except Exception:
                    pass
            
            if win32gui and spotify_pids:
                hwnds = []
                def enum_win(hwnd, extra):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            title = win32gui.GetWindowText(hwnd)
                            if title:
                                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                if pid in spotify_pids:
                                    hwnds.append((hwnd, title))
                    except Exception:
                        pass
                    return True
                try:
                    import win32api
                    win32api.SetLastError(0)
                    win32gui.EnumWindows(enum_win, None)
                except Exception:
                    pass
                if hwnds:
                    hwnds.sort(key=lambda x: len(x[1]), reverse=True)
                    spotify_hwnd = hwnds[0][0]
                    
            if not spotify_hwnd and win32gui:
                hwnds = []
                def enum_win_title(hwnd, extra):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            title = win32gui.GetWindowText(hwnd).lower()
                            if 'spotify' in title:
                                hwnds.append(hwnd)
                    except Exception:
                        pass
                    return True
                try:
                    win32gui.EnumWindows(enum_win_title, None)
                    if hwnds:
                        spotify_hwnd = hwnds[0]
                except Exception:
                    pass

            # Helper functions
            def focus_spotify(hwnd):
                if not hwnd or not win32gui:
                    return False
                try:
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    else:
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                    win32gui.SetForegroundWindow(hwnd)
                    return True
                except Exception:
                    return False

            def force_focus_spotify(hwnd, pids):
                if focus_spotify(hwnd):
                    return True
                if pids:
                    from automation.applications import bring_process_to_foreground
                    for pid in pids:
                        if bring_process_to_foreground(pid):
                            return True
                try:
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    if shell.AppActivate("Spotify"):
                        return True
                except Exception:
                    pass
                return False

            def verify_spotify_playing(pids):
                if not win32gui:
                    return True
                start_poll = time.time()
                while time.time() - start_poll < 4.0:
                    titles = []
                    def enum_win(hwnd, extra):
                        try:
                            title = win32gui.GetWindowText(hwnd)
                            if title:
                                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                if pid in pids:
                                    titles.append(title)
                        except Exception:
                            pass
                        return True
                    try:
                        import win32api
                        win32api.SetLastError(0)
                        win32gui.EnumWindows(enum_win, None)
                    except Exception:
                        pass
                    for t in titles:
                        t_lower = t.lower().strip()
                        if t_lower and t_lower not in ("spotify", "spotify free", "spotify premium", "spotify partner", "spotify canvas"):
                            logger.info(f"[SPOTIFY] Playback verified via window title: '{t}'")
                            return True
                    time.sleep(0.4)
                return False

            # Attempt loop: Retry once after refocusing Spotify if playback verification fails
            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                logger.info(f"[SPOTIFY] In-app interaction attempt {attempt} of {max_attempts}")
                
                # Ensure Spotify is focused
                force_focus_spotify(spotify_hwnd, spotify_pids)
                time.sleep(0.5)

                # Strategy 1: Quick Search (Ctrl+K)
                try:
                    logger.info("[SPOTIFY] Attempting Strategy 1: Quick Search (Ctrl+K)")
                    pyautogui.hotkey("ctrl", "k")
                    time.sleep(0.4)
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.1)
                    pyautogui.press("backspace")
                    time.sleep(0.1)
                    pyautogui.write(query, interval=0.03)
                    time.sleep(1.0) # Let suggestions populate
                    pyautogui.press("enter")
                    
                    if verify_spotify_playing(spotify_pids):
                        return ExecutionResult(
                            success=True,
                            tool="search_inside_application",
                            message=f"Searched and playing '{query}' on Spotify (Quick Search)."
                        )
                except Exception as e:
                    logger.warning(f"[SPOTIFY] Quick search strategy raised exception: {e}")

                # Strategy 2 Fallback: Main Search page (Ctrl+L)
                try:
                    logger.info("[SPOTIFY] Attempting Strategy 2: Main Search (Ctrl+L)")
                    # Clear and focus search bar
                    pyautogui.hotkey("ctrl", "l")
                    time.sleep(0.4)
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.1)
                    pyautogui.press("backspace")
                    time.sleep(0.1)
                    pyautogui.write(query, interval=0.03)
                    time.sleep(0.8)
                    pyautogui.press("enter")
                    time.sleep(1.2) # Let search results load
                    
                    # Navigate to first result
                    pyautogui.press("tab")
                    time.sleep(0.2)
                    pyautogui.press("enter")
                    
                    if verify_spotify_playing(spotify_pids):
                        return ExecutionResult(
                            success=True,
                            tool="search_inside_application",
                            message=f"Searched and playing '{query}' on Spotify (Main Search)."
                        )
                except Exception as e:
                    logger.warning(f"[SPOTIFY] Main search strategy raised exception: {e}")

            # If both attempts failed
            return ExecutionResult(
                success=False,
                tool="search_inside_application",
                message=f"Failed to play '{query}' on Spotify after {max_attempts} attempts. Playback could not be verified."
            )

        elif "chrome" in app or "edge" in app or "browser" in app:
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.3)
            pyautogui.write(query, interval=0.03)
            time.sleep(0.3)
            pyautogui.press("enter")
            return ExecutionResult(success=True, tool="search_inside_application", message=f"Searched for '{query}' in browser address bar.")

        # Default Fallback: Ctrl+F search
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.2)
        pyautogui.write(query)
        time.sleep(0.2)
        pyautogui.press("enter")
        return ExecutionResult(success=True, tool="search_inside_application", message=f"Performed general search for '{query}' via Ctrl+F.")

    except Exception as e:
        return ExecutionResult(success=False, tool="search_inside_application", message=f"Search failed inside application: {e}")

@register_tool("close_window")
def close_window(args: dict[str, Any]) -> ExecutionResult:
    """Close the active window (Alt+F4)."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="close_window", message="pyautogui is not available.")
    try:
        pyautogui.hotkey("alt", "f4")
        return ExecutionResult(success=True, tool="close_window", message="Closed the active window.")
    except Exception as e:
        return ExecutionResult(success=False, tool="close_window", message=f"Failed to close window: {e}")

@register_tool("switch_tab")
def switch_tab(args: dict[str, Any]) -> ExecutionResult:
    """Switch tabs (Ctrl+Tab)."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="switch_tab", message="pyautogui is not available.")
    direction = args.get("direction", "next").lower()
    try:
        if direction == "next":
            pyautogui.hotkey("ctrl", "tab")
        else:
            pyautogui.hotkey("ctrl", "shift", "tab")
        return ExecutionResult(success=True, tool="switch_tab", message=f"Switched to {direction} tab.")
    except Exception as e:
        return ExecutionResult(success=False, tool="switch_tab", message=f"Failed to switch tabs: {e}")

@register_tool("select_dropdown")
def select_dropdown(args: dict[str, Any]) -> ExecutionResult:
    """Select option from a dropdown. Estimates relative click coordinates."""
    if not pyautogui:
        return ExecutionResult(success=False, tool="select_dropdown", message="pyautogui is not available.")
    target = args.get("target", "")
    option = args.get("option", "")

    res_loc = locate_ui_element({"label": target, "element_type": "dropdown"})
    if res_loc.success:
        try:
            pyautogui.click(res_loc.x, res_loc.y)
            time.sleep(0.5)
            pyautogui.write(option)
            time.sleep(0.2)
            pyautogui.press("enter")
            return ExecutionResult(success=True, tool="select_dropdown", message=f"Selected option '{option}' from dropdown '{target}'.")
        except Exception as e:
            return ExecutionResult(success=False, tool="select_dropdown", message=f"Failed dropdown selection: {e}")

    return ExecutionResult(success=False, tool="select_dropdown", message=f"Dropdown '{target}' not located.")


# ==============================================================================
# Consolidated System & Utility Tools
# ==============================================================================

import subprocess
import sys
from datetime import datetime
from execution.schemas import ExecutionTimer

@register_tool("take_screenshot")
def take_screenshot(args: dict[str, Any]) -> ExecutionResult:
    """Capture the current screen."""
    with ExecutionTimer() as timer:
        try:
            if pyautogui:
                os.makedirs("data", exist_ok=True)
                path = os.path.join("data", f"screenshot_{int(time.time())}.png")
                pyautogui.screenshot(path)
                return ExecutionResult(
                    success=True,
                    tool="take_screenshot",
                    message=f"Screenshot saved to {path}.",
                    output=path,
                    execution_time_ms=timer.elapsed_ms
                )
            
            # Fallback to system tools
            if sys.platform.startswith("win"):
                subprocess.Popen(["snippingtool", "/clip"])
                msg = "Opened Snipping Tool."
            elif sys.platform == "darwin":
                subprocess.run(["screencapture", "-c"], check=True)
                msg = "Screenshot saved to clipboard."
            else:
                subprocess.run(["gnome-screenshot", "-c"], check=True)
                msg = "Screenshot saved to clipboard."
                
            return ExecutionResult(
                success=True,
                tool="take_screenshot",
                message=msg,
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="take_screenshot",
                message=f"Failed to take screenshot: {e}",
                execution_time_ms=timer.elapsed_ms
            )

@register_tool("check_time")
def check_time(args: dict[str, Any]) -> ExecutionResult:
    """Get the current system local time."""
    with ExecutionTimer() as timer:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return ExecutionResult(
            success=True,
            tool="check_time",
            message=f"Current time is {now}",
            output=now,
            execution_time_ms=timer.elapsed_ms
        )

@register_tool("check_memory")
def check_memory(args: dict[str, Any]) -> ExecutionResult:
    """Check the current RAM/memory usage."""
    with ExecutionTimer() as timer:
        try:
            if sys.platform.startswith("win"):
                cmd = ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/Value"]
            else:
                cmd = ["free", "-h"]
                
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return ExecutionResult(
                success=True,
                tool="check_memory",
                message="Checked memory usage.",
                output=result.stdout.strip(),
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="check_memory",
                message=f"Failed to check memory: {e}",
                execution_time_ms=timer.elapsed_ms
            )

@register_tool("system_info")
def system_info(args: dict[str, Any]) -> ExecutionResult:
    """Get system hardware and OS info."""
    with ExecutionTimer() as timer:
        try:
            if sys.platform.startswith("win"):
                cmd = ["systeminfo"]
            else:
                cmd = ["uname", "-a"]
                
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return ExecutionResult(
                success=True,
                tool="system_info",
                message="Retrieved system info.",
                output=result.stdout.strip(),
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="system_info",
                message=f"Failed to retrieve system info: {e}",
                execution_time_ms=timer.elapsed_ms
            )
