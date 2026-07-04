"""
Application Tools
=================

Handlers for opening desktop applications.
"""

import subprocess
import sys
import logging
import time
from typing import Any

from execution.registry import register_tool
from execution.schemas import ExecutionResult, ExecutionTimer

logger = logging.getLogger(__name__)

import os
import re
import types

# We reuse find_application as a final fallback
from agentic.os_scanner import find_application

try:
    import win32gui
    import win32process
except ImportError:
    win32gui = None
    win32process = None

CANONICAL_ALIASES = {
    "file explorer": ["file manager", "file explorer", "explorer", "this pc"],
    "task manager": ["task manager", "taskmgr", "system monitor"],
    "command prompt": ["cmd", "command prompt", "terminal"],
    "settings": ["settings", "windows settings"],
    "calculator": ["calculator", "calc"],
    "notepad": ["notepad", "text editor"],
    "visual studio code": ["vs code", "vscode", "vs"],
    "chatgpt": ["chat gpt", "chatgpt"],
    "spotify": ["spotify"],
    "whatsapp": ["whatsapp"]
}

CANONICAL_EXECUTABLES = {
    "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "command prompt": "cmd.exe",
    "settings": "ms-settings:",
    "calculator": "calc.exe",
    "notepad": "notepad.exe"
}

def resolve_canonical_app(query: str) -> str | None:
    """Check aliases before fuzzy matching. Return canonical application immediately."""
    cleaned = clean_query_for_matching(query)
    # Check aliases directly
    for canonical, aliases in CANONICAL_ALIASES.items():
        if cleaned in aliases:
            return canonical
        # Also check if normalized matches exactly
        q_norm = "".join(c for c in cleaned if c.isalnum())
        for alias in aliases:
            if q_norm == "".join(c for c in alias if c.isalnum()):
                return canonical
    return None

def is_abbreviation(abbr: str, full: str) -> bool:
    """Check if abbr is an abbreviation of full name (e.g. 'vscode' -> 'visual studio code')."""
    abbr = abbr.lower().replace(" ", "").replace("-", "")
    full = full.lower().replace("-", " ")
    full_words = full.split()
    
    # 1. Direct initials matching
    initials = "".join(w[0] for w in full_words if w)
    if abbr == initials:
        return True
        
    # 2. Initials + suffix matching (e.g. 'vs' + 'code' = 'vscode')
    for i in range(1, len(full_words)):
        prefix_initials = "".join(w[0] for w in full_words[:i])
        if w := full_words[i:]:
            last_word = w[0]
            if abbr.startswith(prefix_initials):
                suffix = abbr[len(prefix_initials):]
                if last_word.startswith(suffix):
                    return True
                
    # 3. Common aliases
    for canonical, aliases in CANONICAL_ALIASES.items():
        if abbr in [a.replace(" ", "") for a in aliases] and full.replace(" ", "") == canonical.replace(" ", ""):
            return True
            
    return False

def is_fuzzy_match(query: str, name: str) -> bool:
    """Perform robust fuzzy matching between query and a target name."""
    query = query.lower().strip()
    name = name.lower().strip()
    
    if query == name:
        return True
        
    q_norm = "".join(c for c in query if c.isalnum())
    n_norm = "".join(c for c in name if c.isalnum())
    if q_norm == n_norm:
        return True
        
    for canonical, aliases in CANONICAL_ALIASES.items():
        if query in aliases or q_norm in ["".join(c for c in a if c.isalnum()) for a in aliases]:
            target_norm = "".join(c for c in canonical if c.isalnum())
            if target_norm == n_norm or target_norm in n_norm or n_norm in target_norm:
                return True
                
    if q_norm in n_norm or n_norm in q_norm:
        return True
        
    if is_abbreviation(query, name):
        return True
        
    import difflib
    # Fuzzy matching should compare canonical application names, requiring higher confidence
    if difflib.SequenceMatcher(None, query, name).ratio() >= 0.85:
        return True
        
    return False

def clean_query_for_matching(query: str) -> str:
    """Clean action words and common verbs from query to isolate application name."""
    text = query.lower().strip()
    text = re.sub(r"[.!?]+$", "", text).strip()
    
    words = text.split()
    remove_words = {"app", "application", "launch", "open", "start", "the"}
    filtered_words = [w for w in words if w not in remove_words]
    
    cleaned = " ".join(filtered_words)
    return cleaned

def clean_query_name(query: str) -> str:
    """Legacy cleaner wrapper."""
    return clean_query_for_matching(query)

def bring_process_to_foreground(pid: int) -> bool:
    """Find visible HWNDs for process ID and bring them to foreground."""
    if not win32gui or not win32process:
        return False
        
    found_hwnds = []
    
    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
            if win_pid == pid:
                title = win32gui.GetWindowText(hwnd)
                if title:
                    found_hwnds.append(hwnd)
        return True
        
    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception as e:
        logger.debug(f"EnumWindows failed: {e}")
        
    if found_hwnds:
        for hwnd in found_hwnds:
            try:
                # SW_RESTORE = 9, SW_SHOW = 5
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, 9)
                else:
                    win32gui.ShowWindow(hwnd, 5)
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                logger.debug(f"SetForegroundWindow failed: {e}")
        return True
    return False

def get_start_apps() -> list[dict[str, str]]:
    """Retrieve Windows Start Menu apps using PowerShell Get-StartApps."""
    import json
    apps = []
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            for item in data:
                name = item.get("Name")
                appid = item.get("AppID")
                if name and appid:
                    apps.append({"name": name, "appid": appid})
    except Exception as e:
        logger.debug(f"Get-StartApps JSON call failed: {e}")
        
    if not apps:
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-StartApps"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            if res.returncode == 0:
                lines = res.stdout.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("Name ") or line.startswith("----"):
                        continue
                    parts = re.split(r'\s{2,}', line)
                    if len(parts) >= 2:
                        apps.append({"name": parts[0].strip(), "appid": parts[1].strip()})
        except Exception as e:
            logger.debug(f"Get-StartApps fallback failed: {e}")
            
    return apps

def find_indexed_app(query: str) -> tuple[str | None, str | None]:
    """Search registry, desktop shortcuts, start menu shortcuts for a match."""
    # Registry Uninstall
    try:
        from agentic.discovery.apps import scan_registry_apps
        registry_apps = scan_registry_apps()
        for app in registry_apps:
            if is_fuzzy_match(query, app.name):
                exe_path = app.executable or app.path
                if exe_path and os.path.exists(exe_path):
                    return app.name, exe_path
    except Exception as e:
        logger.debug(f"Registry search failed: {e}")
        
    # Start Menu & Desktop Shortcuts
    try:
        paths = [
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
        ]
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            paths.append(os.path.join(user_profile, "Desktop"))
        public_profile = os.environ.get("PUBLIC")
        if public_profile:
            paths.append(os.path.join(public_profile, "Desktop"))
            
        from agentic.discovery.apps import resolve_lnk_target
        for p in paths:
            if not os.path.exists(p):
                continue
            for root, dirs, files in os.walk(p):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        name, _ = os.path.splitext(file)
                        if is_fuzzy_match(query, name):
                            filepath = os.path.join(root, file)
                            target = resolve_lnk_target(filepath)
                            if target and os.path.exists(target):
                                return name, target
    except Exception as e:
        logger.debug(f"Shortcut search failed: {e}")
        
    return None, None

def find_website_resource(query: str):
    """Scan browser bookmarks and history for matching website."""
    try:
        from agentic.discovery.manager import discover
        matches = discover(query)
        website_matches = [m for m in matches if m.type == "website"]
        if website_matches:
            website_matches.sort(key=lambda x: x.confidence, reverse=True)
            return website_matches[0]
    except Exception as e:
        logger.debug(f"discover check failed: {e}")
    return None

def make_custom_result(success: bool, resource_type: str, reason: str) -> ExecutionResult:
    """Helper to return an ExecutionResult with customized to_dict output format."""
    res = ExecutionResult(
        success=success,
        tool="resolve_and_open",
        message=reason
    )
    res.resource_type = resource_type
    res.reason = reason
    
    def custom_to_dict(self):
        d = ExecutionResult.to_dict(self)
        d["resource_type"] = self.resource_type
        d["reason"] = self.reason
        if hasattr(self, "app_running"):
            d["app_running"] = self.app_running
        if hasattr(self, "action"):
            d["action"] = self.action
        return d
    res.to_dict = types.MethodType(custom_to_dict, res)
    return res

def resolve_app_launch_strategy(query: str) -> tuple[str | None, str, str, str]:
    """
    Look up application to launch using Windows non-recursive strategy.
    
    Returns tuple: (executable_path_or_None, process_check_log, registry_log, start_menu_log)
    """
    cleaned = clean_query_for_matching(query)
    
    # Check aliases before fuzzy matching
    canonical_match = resolve_canonical_app(cleaned)
    if canonical_match and canonical_match in CANONICAL_EXECUTABLES:
        # If an alias matches a built-in, return the canonical application immediately
        return CANONICAL_EXECUTABLES[canonical_match], "canonical alias", "canonical alias", "canonical alias"
    elif canonical_match:
        # Use canonical name for fuzzy matching
        cleaned = canonical_match
        
    process_check_log = "not running"
    registry_log = "not found"
    start_menu_log = "not found"
    
    running_match = None
    registry_match = None
    start_menu_match = None
    
    # Step 1: Check running process
    try:
        import psutil
        for proc in psutil.process_iter(attrs=['pid', 'name', 'exe']):
            p_name = proc.info.get('name')
            p_exe = proc.info.get('exe')
            if not p_name:
                continue
            p_name_clean = p_name
            if p_name_clean.lower().endswith(".exe"):
                p_name_clean = p_name_clean[:-4]
            if is_fuzzy_match(cleaned, p_name_clean):
                if p_exe and os.path.exists(p_exe):
                    running_match = p_exe
                    process_check_log = "running"
                    break
    except Exception:
        pass
        
    # Step 2: Get-StartApps
    start_apps = get_start_apps()
    for app in start_apps:
        if is_fuzzy_match(cleaned, app["name"]):
            start_menu_match = f"shell:AppsFolder\\{app['appid']}"
            start_menu_log = "found shortcut"
            break
            
    # Step 3: Registry & Shortcuts
    if not start_menu_match:
        name_ind, path_ind = find_indexed_app(cleaned)
        if path_ind:
            registry_match = path_ind
            registry_log = f"found {os.path.basename(path_ind)}"
            
    target_exe = start_menu_match or registry_match or running_match
    return target_exe, process_check_log, registry_log, start_menu_log

@register_tool("open_application")
def open_application(args: dict[str, Any]) -> ExecutionResult:
    """Launch a desktop application dynamically using OS scanning."""
    app_name = args.get("application", "").lower()
    if not app_name:
        return ExecutionResult(
            success=False,
            tool="open_application",
            message="No application name provided."
        )

    # 0. Check if already running
    cleaned = clean_query_for_matching(app_name)
    canonical_match = resolve_canonical_app(cleaned)
    search_query = canonical_match or cleaned
    if canonical_match and canonical_match in CANONICAL_EXECUTABLES:
        executable = CANONICAL_EXECUTABLES[canonical_match]
        # Skip process scan, launch canonical immediately below if not handled here
        pass
        
    try:
        if win32gui and win32process:
            hwnds = []
            def enum_win(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower()
                    if search_query in title:
                        hwnds.append((hwnd, title))
                return True
            win32gui.EnumWindows(enum_win, None)
            if hwnds:
                hwnds.sort(key=lambda x: len(x[1]))  # shortest title match
                hwnd = hwnds[0][0]
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                bring_process_to_foreground(pid)
                
                from agentic.memory.session_state import get_session
                get_session().set_context(app=cleaned)
                from agentic.memory.app_context import AppContextManager
                AppContextManager.set_context(active_app=cleaned, window_handle=None)
                
                res = ExecutionResult(
                    success=True,
                    tool="open_application",
                    message=f"Application '{app_name}' is already running. Brought to foreground."
                )
                res.app_running = True
                res.action = "activate_window"
                def custom_to_dict(self):
                    d = ExecutionResult.to_dict(self)
                    d["app_running"] = self.app_running
                    d["action"] = self.action
                    return d
                res.to_dict = types.MethodType(custom_to_dict, res)
                return res
    except Exception as e:
        logger.debug(f"Window enumeration failed: {e}")
        
    running_match_pid = None
    try:
        import psutil
        for proc in psutil.process_iter(attrs=['pid', 'name']):
            p_name = proc.info.get('name')
            if not p_name:
                continue
            p_name_clean = p_name[:-4] if p_name.lower().endswith(".exe") else p_name
            if is_fuzzy_match(canonical_match or cleaned, p_name_clean):
                running_match_pid = proc.info.get('pid')
                break
    except Exception:
        pass

    if running_match_pid:
        bring_process_to_foreground(running_match_pid)
        from agentic.memory.session_state import get_session
        get_session().set_context(app=cleaned)
        from agentic.memory.app_context import AppContextManager
        AppContextManager.set_context(active_app=cleaned, window_handle=None)
        
        res = ExecutionResult(
            success=True,
            tool="open_application",
            message=f"Application {app_name} is already running. Brought to foreground."
        )
        res.app_running = True
        res.action = "activate_window"
        def custom_to_dict(self):
            d = ExecutionResult.to_dict(self)
            d["app_running"] = self.app_running
            d["action"] = self.action
            return d
        res.to_dict = types.MethodType(custom_to_dict, res)
        return res

    # 1. Try Windows non-recursive strategy first
    executable, _, _, _ = resolve_app_launch_strategy(app_name)
    
    if not executable:
        # Try new Windows Discovery Engine / resolve_best_resource as fallback
        from agentic.discovery.manager import resolve_best_resource
        res = resolve_best_resource(app_name, f"open {app_name}")
        
        if res:
            if res.type == "website":
                from automation.browser import open_browser
                return open_browser({"url": res.url})
            elif res.type == "folder":
                from automation.filesystem import open_folder
                return open_folder({"path": res.path})
            elif res.type == "file":
                from automation.filesystem import open_file
                return open_file({"path": res.path})
            elif res.type == "application":
                executable = res.executable or res.path
                
    if not executable:
        executable = find_application(app_name)
        
    if not executable:
        return ExecutionResult(
            success=False,
            tool="open_application",
            message=f"Application '{app_name}' not installed or found."
        )

    with ExecutionTimer() as timer:
        try:
            # We use Popen / startfile so we don't block the Python script waiting for the app to close
            if sys.platform.startswith("win"):
                if hasattr(os, "startfile"):
                    os.startfile(executable)
                else:
                    subprocess.Popen(executable, shell=True)
            else:
                subprocess.Popen(["nohup", executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            return ExecutionResult(
                success=True,
                tool="open_application",
                message=f"Launched application: {app_name} ({executable}).",
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="open_application",
                message=f"Failed to launch {app_name}: {e}",
                execution_time_ms=timer.elapsed_ms
            )

@register_tool("launch_application")
def launch_application(args: dict[str, Any]) -> ExecutionResult:
    """Launch an application. Focusing if running, check shortcuts, or search backup with Windows Search."""
    app_name = args.get("application", "").lower().strip()
    if not app_name:
        return ExecutionResult(success=False, tool="launch_application", message="No application name provided.")

    cleaned = clean_query_for_matching(app_name)
    canonical_match = resolve_canonical_app(cleaned)
    search_query = canonical_match or cleaned
    
    try:
        if win32gui and win32process:
            hwnds = []
            def enum_win_launch(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower()
                    if search_query in title:
                        hwnds.append((hwnd, title))
                return True
            win32gui.EnumWindows(enum_win_launch, None)
            if hwnds:
                hwnds.sort(key=lambda x: len(x[1]))
                hwnd = hwnds[0][0]
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                bring_process_to_foreground(pid)
                return ExecutionResult(
                    success=True,
                    tool="launch_application",
                    message=f"Reused existing window for '{app_name}'."
                )
    except Exception as e:
        logger.debug(f"Window enumeration failed: {e}")
        
    running_match_pid = None
    try:
        import psutil
        for proc in psutil.process_iter(attrs=['pid', 'name']):
            p_name = proc.info.get('name')
            if p_name:
                p_clean = p_name[:-4] if p_name.lower().endswith(".exe") else p_name
                if is_fuzzy_match(search_query, p_clean):
                    running_match_pid = proc.info.get('pid')
                    break
    except Exception:
        pass

    if running_match_pid:
        bring_process_to_foreground(running_match_pid)
        return ExecutionResult(
            success=True,
            tool="launch_application",
            message=f"Application '{app_name}' is already running. Brought to foreground."
        )

    # Try default shortcut/registry resolution
    executable, _, _, _ = resolve_app_launch_strategy(app_name)
    if executable:
        try:
            if executable.startswith("shell:AppsFolder\\"):
                subprocess.Popen(["explorer.exe", executable])
            elif hasattr(os, "startfile"):
                os.startfile(executable)
            else:
                subprocess.Popen(executable, shell=True)
            return ExecutionResult(
                success=True,
                tool="launch_application",
                message=f"Launched application '{app_name}' via shortcuts."
            )
        except Exception:
            pass

    # Windows Search Fallback
    print(f"[LAUNCH] '{app_name}' not running or indexed. Triggering Windows Search fallback...")
    try:
        import pyautogui
        pyautogui.press("win")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.03)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(2.5)

        launched = False
        try:
            for proc in psutil.process_iter(attrs=['name']):
                p_name = proc.info.get('name')
                if p_name:
                    p_clean = p_name[:-4] if p_name.lower().endswith(".exe") else p_name
                    if is_fuzzy_match(search_query, p_clean):
                        launched = True
                        break
        except Exception:
            pass

        if launched:
            return ExecutionResult(
                success=True,
                tool="launch_application",
                message=f"Successfully launched '{app_name}' using Windows Search."
            )
    except Exception as e:
        logger.debug(f"Windows Search automation failed: {e}")

    # Browser Fallback
    print(f"[LAUNCH] Windows Search failed for '{app_name}'. Triggering browser fallback...")
    try:
        url = f"https://www.google.com/search?q={app_name}"
        if "chatgpt" in search_query:
            url = "https://chat.openai.com"
        elif "whatsapp" in search_query:
            url = "https://web.whatsapp.com"
        import webbrowser
        webbrowser.open_new_tab(url)
        return ExecutionResult(
            success=True,
            tool="launch_application",
            message=f"Could not launch '{app_name}' locally. Opened browser fallback: {url}",
            metadata={"opened_in_browser": True, "url": url}
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            tool="launch_application",
            message=f"Failed to launch '{app_name}' locally or in browser: {e}"
        )

@register_tool("open_terminal")
def open_terminal(args: dict[str, Any]) -> ExecutionResult:
    """Open a new terminal window."""
    with ExecutionTimer() as timer:
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen("start cmd", shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Terminal"])
            else:
                subprocess.Popen(["gnome-terminal"])
                
            return ExecutionResult(
                success=True,
                tool="open_terminal",
                message="Opened terminal window.",
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="open_terminal",
                message=f"Failed to open terminal: {e}",
                execution_time_ms=timer.elapsed_ms
            )

@register_tool("open_file_manager")
def open_file_manager(args: dict[str, Any]) -> ExecutionResult:
    """Open the file manager."""
    with ExecutionTimer() as timer:
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen("explorer .", shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "."])
            else:
                subprocess.Popen(["nautilus", "."])
                
            return ExecutionResult(
                success=True,
                tool="open_file_manager",
                message="Opened file manager.",
                execution_time_ms=timer.elapsed_ms
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                tool="open_file_manager",
                message=f"Failed to open file manager: {e}",
                execution_time_ms=timer.elapsed_ms
            )

@register_tool("resolve_and_open")
def resolve_and_open(args: dict[str, Any]) -> ExecutionResult:
    """Resolve and open a desktop application, website, file or folder by fuzzy matching."""
    query = args.get("query", "")
    if not query:
        return ExecutionResult(
            success=False,
            tool="resolve_and_open",
            message="No query provided to resolve_and_open."
        )
        
    cleaned_query = clean_query_for_matching(query)
    canonical_match = resolve_canonical_app(cleaned_query)
    search_query = canonical_match or cleaned_query
    
    if canonical_match and canonical_match in CANONICAL_EXECUTABLES:
        print(f"[DISCOVERY] Canonical alias matched: {canonical_match}")
        print("[DISCOVERY] Launching application...")
        executable = CANONICAL_EXECUTABLES[canonical_match]
        try:
            if sys.platform.startswith("win"):
                if hasattr(os, "startfile"):
                    os.startfile(executable)
                else:
                    subprocess.Popen(executable, shell=True)
            else:
                subprocess.Popen(["nohup", executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.debug(f"Failed to launch canonical app: {e}")
        return make_custom_result(
            success=True,
            resource_type="application",
            reason="Canonical application launched"
        )
        
    print(f"[DISCOVERY] Query: {search_query}")
    
    # Step 1: Check if the application is already running using psutil.
    # If running, bring its window to the foreground.
    running_match_pid = None
    running_match_name = None
    try:
        import psutil
        for proc in psutil.process_iter(attrs=['pid', 'name', 'exe']):
            p_name = proc.info.get('name')
            if not p_name:
                continue
            p_name_clean = p_name
            if p_name_clean.lower().endswith(".exe"):
                p_name_clean = p_name_clean[:-4]
            if is_fuzzy_match(search_query, p_name_clean):
                running_match_pid = proc.info.get('pid')
                running_match_name = p_name
                break
    except Exception as e:
        logger.debug(f"Step 1 psutil check failed: {e}")
        
    if running_match_pid:
        print(f"[DISCOVERY] Found running app: {running_match_name}")
        print("[DISCOVERY] Bringing window to foreground...")
        print("[DISCOVERY] Browser fallback skipped.")
        bring_process_to_foreground(running_match_pid)
        
        from agentic.memory.session_state import get_session
        get_session().set_context(app=cleaned_query)
        from agentic.memory.app_context import AppContextManager
        AppContextManager.set_context(active_app=cleaned_query, window_handle=None)
        
        res = make_custom_result(
            success=True,
            resource_type="application",
            reason="Application found and launched"
        )
        res.app_running = True
        res.action = "activate_window"
        return res
        
    # Step 2: Search Windows Start Menu applications using PowerShell: Get-StartApps
    start_apps = get_start_apps()
    start_app_match = None
    for app in start_apps:
        if is_fuzzy_match(search_query, app["name"]):
            start_app_match = app
            break
            
    if start_app_match:
        print(f"[DISCOVERY] Found StartApp: {start_app_match['name']}")
        print("[DISCOVERY] Launching application...")
        print("[DISCOVERY] Browser fallback skipped.")
        try:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{start_app_match['appid']}"])
        except Exception as e:
            logger.debug(f"Failed to launch StartApp via explorer: {e}")
        return make_custom_result(
            success=True,
            resource_type="application",
            reason="Application found and launched"
        )
        
    # Step 3: Search indexed resources:
    # - Registry uninstall entries
    # - Start Menu shortcuts
    # - Desktop shortcuts
    # - shell:AppsFolder entries
    # - installed executables
    indexed_app_name, indexed_app_exe = find_indexed_app(search_query)
    if indexed_app_exe:
        print(f"[DISCOVERY] Found indexed app: {indexed_app_name}")
        print("[DISCOVERY] Launching application...")
        print("[DISCOVERY] Browser fallback skipped.")
        try:
            if sys.platform.startswith("win"):
                if hasattr(os, "startfile"):
                    os.startfile(indexed_app_exe)
                else:
                    subprocess.Popen(indexed_app_exe, shell=True)
            else:
                subprocess.Popen(["nohup", indexed_app_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.debug(f"Failed to launch indexed app: {e}")
        return make_custom_result(
            success=True,
            resource_type="application",
            reason="Application found and launched"
        )
        
    # Step 5: Check browser bookmarks/history
    # if a website exists, open it.
    print("[DISCOVERY] No application found.")
    website_match = find_website_resource(search_query)
    if website_match:
        print(f"[DISCOVERY] Found website match: {website_match.name}")
        print("[DISCOVERY] Opening website...")
        try:
            import webbrowser
            webbrowser.open_new_tab(website_match.url)
        except Exception as e:
            logger.debug(f"Failed to open website fallback: {e}")
        return make_custom_result(
            success=True,
            resource_type="website",
            reason="Website found and opened"
        )
        
    # Step 6: Open Google Search as the final fallback.
    print("[DISCOVERY] No website match found.")
    print("[DISCOVERY] Opening Google Search fallback...")
    
    # Custom fallback URLs for chatgpt and whatsapp
    q_clean = cleaned_query.lower().strip().replace(" ", "")
    if "chatgpt" in q_clean:
        url = "https://chat.openai.com"
    elif "whatsapp" in q_clean:
        url = "https://web.whatsapp.com"
    else:
        url = f"https://www.google.com/search?q={cleaned_query}"
        
    try:
        import webbrowser
        webbrowser.open_new_tab(url)
    except Exception as e:
        logger.debug(f"Failed to open fallback URL: {e}")
        
    return make_custom_result(
        success=True,
        resource_type="website",
        reason="Google search fallback opened"
    )

@register_tool("is_app_running")
def is_app_running(args: dict[str, Any]) -> ExecutionResult:
    """Check if a specific desktop application is currently running."""
    app_name = args.get("app", "").lower()
    if not app_name:
        return ExecutionResult(success=False, tool="is_app_running", message="No application name provided.")
        
    cleaned = clean_query_for_matching(app_name)
    canonical_match = resolve_canonical_app(cleaned)
    search_query = canonical_match or cleaned
    running = False
    try:
        import psutil
        for proc in psutil.process_iter(attrs=['name']):
            p_name = proc.info.get('name')
            if p_name:
                p_clean = p_name[:-4] if p_name.lower().endswith(".exe") else p_name
                if is_fuzzy_match(cleaned, p_clean):
                    running = True
                    break
    except Exception as e:
        logger.debug(f"is_app_running psutil scan failed: {e}")
        
    res = ExecutionResult(
        success=True,
        tool="is_app_running",
        message=f"Application '{app_name}' is {'running' if running else 'not running'}."
    )
    res.app_running = running
    
    def custom_to_dict(self):
        d = ExecutionResult.to_dict(self)
        d["app_running"] = self.app_running
        return d
    res.to_dict = types.MethodType(custom_to_dict, res)
    return res

@register_tool("activate_window")
def activate_window(args: dict[str, Any]) -> ExecutionResult:
    """Bring a running application window to the foreground."""
    app_name = args.get("app", "").lower()
    if not app_name:
        return ExecutionResult(success=False, tool="activate_window", message="No application name provided.")
        
    cleaned = clean_query_for_matching(app_name)
    canonical_match = resolve_canonical_app(cleaned)
    search_query = canonical_match or cleaned
    target_pid = None
    try:
        import psutil
        for proc in psutil.process_iter(attrs=['pid', 'name']):
            p_name = proc.info.get('name')
            if p_name:
                p_clean = p_name[:-4] if p_name.lower().endswith(".exe") else p_name
                if is_fuzzy_match(cleaned, p_clean):
                    target_pid = proc.info.get('pid')
                    break
    except Exception as e:
        logger.debug(f"activate_window process scan failed: {e}")
        
    if target_pid:
        focused = bring_process_to_foreground(target_pid)
        if focused:
            from agentic.memory.session_state import get_session
            get_session().set_context(app=cleaned)
            from agentic.memory.app_context import AppContextManager
            AppContextManager.set_context(active_app=cleaned, window_handle=None)
            
            res = ExecutionResult(
                success=True,
                tool="activate_window",
                message=f"Activated window for '{app_name}'."
            )
            res.app_running = True
            res.action = "activate_window"
            
            def custom_to_dict(self):
                d = ExecutionResult.to_dict(self)
                d["app_running"] = self.app_running
                d["action"] = self.action
                return d
            res.to_dict = types.MethodType(custom_to_dict, res)
            return res
            
    return ExecutionResult(
        success=False,
        tool="activate_window",
        message=f"Application '{app_name}' is not running or could not be focused."
    )

@register_tool("get_active_window")
def get_active_window(args: dict[str, Any]) -> ExecutionResult:
    """Get the details of the currently focused window."""
    from agentic.memory.app_context import get_active_window_info
    info = get_active_window_info()
    if info["active_app"]:
        res = ExecutionResult(
            success=True,
            tool="get_active_window",
            message=f"Active app: {info['active_app']} (Window: {info['window_title']})"
        )
        res.active_app = info["active_app"]
        res.window_handle = info["window_handle"]
        res.window_title = info["window_title"]
        
        def custom_to_dict(self):
            d = ExecutionResult.to_dict(self)
            d["active_app"] = self.active_app
            d["window_handle"] = self.window_handle
            d["window_title"] = self.window_title
            return d
        res.to_dict = types.MethodType(custom_to_dict, res)
        return res
    else:
        return ExecutionResult(
            success=False,
            tool="get_active_window",
            message="No active window details retrieved."
        )

@register_tool("perform_app_action")
def perform_app_action(args: dict[str, Any]) -> ExecutionResult:
    """Perform application-specific automation action (e.g. Spotify play/pause/search, WhatsApp send)."""
    import time
    app = args.get("app", "").lower()
    action = args.get("action", "").lower()
    payload = args.get("payload", {})
    
    if not app or not action:
        return ExecutionResult(success=False, tool="perform_app_action", message="Missing app or action.")
        
    app_clean = clean_query_for_matching(app)
    
    from agentic.memory.session_state import get_session
    session = get_session()
    session.set_context(app=app_clean)
    
    if app_clean == "spotify":
        import psutil
        running_pid = None
        for proc in psutil.process_iter(attrs=['pid', 'name']):
            p_name = proc.info.get('name')
            if p_name:
                p_clean = p_name[:-4] if p_name.lower().endswith(".exe") else p_name
                if is_fuzzy_match("spotify", p_clean):
                    running_pid = proc.info.get('pid')
                    break
        
        if not running_pid:
            executable, _, _, _ = resolve_app_launch_strategy("spotify")
            if executable:
                try:
                    import os
                    import sys
                    import subprocess
                    if sys.platform.startswith("win") and hasattr(os, "startfile"):
                        os.startfile(executable)
                    else:
                        subprocess.Popen(executable, shell=True)
                    time.sleep(3.0)
                    for proc in psutil.process_iter(attrs=['pid', 'name']):
                        p_name = proc.info.get('name')
                        if p_name:
                            p_clean = p_name[:-4] if p_name.lower().endswith(".exe") else p_name
                            if is_fuzzy_match("spotify", p_clean):
                                running_pid = proc.info.get('pid')
                                break
                except Exception as e:
                    return ExecutionResult(success=False, tool="perform_app_action", message=f"Failed to launch Spotify: {e}")
            else:
                return ExecutionResult(success=False, tool="perform_app_action", message="Spotify is not installed or running.")
                
        if running_pid:
            bring_process_to_foreground(running_pid)
            time.sleep(0.5)
            
        if action == "play":
            song = payload.get("song", "")
            if song:
                session.set_context(song=song)
                try:
                    from automation.desktop import search_inside_application
                    # Execute the robust search and play sequence
                    res = search_inside_application({"query": song})
                    # Adjust tool name for return compatibility
                    res.tool = "perform_app_action"
                    return res
                except Exception as e:
                    return ExecutionResult(
                        success=False,
                        tool="perform_app_action",
                        message=f"Failed to delegate playback to search_inside_application: {e}"
                    )
            else:
                import ctypes
                try:
                    ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
                    return ExecutionResult(success=True, tool="perform_app_action", message="Resumed playback on Spotify.")
                except Exception as e:
                    return ExecutionResult(success=False, tool="perform_app_action", message=f"Failed to resume Spotify: {e}")
                    
        elif action in ("pause", "stop"):
            import ctypes
            try:
                ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
                return ExecutionResult(success=True, tool="perform_app_action", message="Paused playback on Spotify.")
            except Exception as e:
                return ExecutionResult(success=False, tool="perform_app_action", message=f"Failed to pause Spotify: {e}")
                
    elif app_clean == "whatsapp":
        contact = payload.get("contact", "")
        message = payload.get("message", "")
        if action == "send_message":
            if not contact or not message:
                return ExecutionResult(success=False, tool="perform_app_action", message="Missing contact or message for WhatsApp.")
            session.set_context(contact=contact)
            from automation.whatsapp import send_whatsapp_message
            return send_whatsapp_message({"contact": contact, "message": message})
            
    return ExecutionResult(
        success=False,
        tool="perform_app_action",
        message=f"Action '{action}' on app '{app}' is not supported or implemented."
    )
