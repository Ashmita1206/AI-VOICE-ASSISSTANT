"""
Browser Scanner
===============

Scans bookmarks, history, and active browser tabs from Chrome, Edge, and Firefox.
"""

import os
import json
import shutil
import sqlite3
import tempfile
import logging
from typing import List, Dict, Any
from agentic.discovery.schemas import Resource

try:
    import win32gui
    import win32process
    import psutil
except ImportError:
    win32gui = None
    win32process = None
    psutil = None

logger = logging.getLogger(__name__)

def get_user_data_paths() -> Dict[str, str]:
    """Retrieve default paths for browser user data on Windows."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    
    paths = {}
    if local_appdata:
        paths["chrome"] = os.path.join(local_appdata, r"Google\Chrome\User Data")
        paths["edge"] = os.path.join(local_appdata, r"Microsoft\Edge\User Data")
    if appdata:
        paths["firefox"] = os.path.join(appdata, r"Mozilla\Firefox\Profiles")
        
    return paths

def parse_chrome_style_bookmarks(bookmarks_path: str, browser_name: str) -> List[Resource]:
    """Parse bookmarks from Chrome/Edge JSON bookmarks file."""
    resources = []
    if not os.path.exists(bookmarks_path):
        return resources
        
    try:
        with open(bookmarks_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
            
        def traverse(node):
            if not isinstance(node, dict):
                return
            if node.get("type") == "url" and node.get("url"):
                resources.append(Resource(
                    name=node.get("name", ""),
                    type="website",
                    source="browser_bookmark",
                    url=node.get("url"),
                    confidence=0.9
                ))
            elif node.get("type") == "folder" and "children" in node:
                for child in node["children"]:
                    traverse(child)
                    
        # Chrome bookmarks usually have roots
        roots = data.get("roots", {})
        for root_key in ["bookmark_bar", "other", "synced"]:
            if root_key in roots:
                traverse(roots[root_key])
    except Exception as e:
        logger.debug(f"Failed to parse bookmarks from {bookmarks_path}: {e}")
        
    return resources

def scan_chrome_style_history(history_path: str, browser_name: str) -> List[Resource]:
    """Extract history from Chrome/Edge SQLite history file by copying it first."""
    resources = []
    if not os.path.exists(history_path):
        return resources
        
    temp_dir = tempfile.gettempdir()
    temp_history = os.path.join(temp_dir, f"{browser_name}_history_copy")
    
    try:
        # Copy to avoid locking issues if browser is running
        shutil.copy2(history_path, temp_history)
        conn = sqlite3.connect(temp_history)
        cursor = conn.cursor()
        
        # Query top 150 visited URLs
        cursor.execute(
            "SELECT title, url, visit_count FROM urls "
            "WHERE url NOT LIKE 'file://%' AND url NOT LIKE 'chrome://%' AND url NOT LIKE 'edge://%' "
            "ORDER BY last_visit_time DESC LIMIT 150"
        )
        
        for title, url, visit_count in cursor.fetchall():
            if url:
                resources.append(Resource(
                    name=title or url,
                    type="website",
                    source="browser_history",
                    url=url,
                    confidence=0.75
                ))
        conn.close()
    except Exception as e:
        logger.debug(f"Failed to read history from {history_path}: {e}")
    finally:
        if os.path.exists(temp_history):
            try:
                os.remove(temp_history)
            except OSError:
                pass
                
    return resources

def scan_firefox_places(places_path: str) -> tuple[List[Resource], List[Resource]]:
    """Scan Firefox places.sqlite for both bookmarks and history."""
    bookmarks = []
    history = []
    if not os.path.exists(places_path):
        return bookmarks, history
        
    temp_dir = tempfile.gettempdir()
    temp_places = os.path.join(temp_dir, "firefox_places_copy")
    
    try:
        shutil.copy2(places_path, temp_places)
        conn = sqlite3.connect(temp_places)
        cursor = conn.cursor()
        
        # 1. Fetch Bookmarks
        try:
            cursor.execute(
                "SELECT b.title, p.url FROM moz_bookmarks b "
                "JOIN moz_places p ON b.fk = p.id "
                "WHERE p.url IS NOT NULL AND p.url != ''"
            )
            for title, url in cursor.fetchall():
                bookmarks.append(Resource(
                    name=title or url,
                    type="website",
                    source="browser_bookmark",
                    url=url,
                    confidence=0.9
                ))
        except sqlite3.Error as e:
            logger.debug(f"Error scanning Firefox bookmarks: {e}")
            
        # 2. Fetch History
        try:
            cursor.execute(
                "SELECT title, url FROM moz_places "
                "WHERE visit_count > 0 AND url NOT LIKE 'place:%' AND url NOT LIKE 'about:%' "
                "ORDER BY last_visit_date DESC LIMIT 150"
            )
            for title, url in cursor.fetchall():
                history.append(Resource(
                    name=title or url,
                    type="website",
                    source="browser_history",
                    url=url,
                    confidence=0.75
                ))
        except sqlite3.Error as e:
            logger.debug(f"Error scanning Firefox history: {e}")
            
        conn.close()
    except Exception as e:
        logger.debug(f"Failed to read Firefox places from {places_path}: {e}")
    finally:
        if os.path.exists(temp_places):
            try:
                os.remove(temp_places)
            except OSError:
                pass
                
    return bookmarks, history

def scan_bookmarks() -> List[Resource]:
    """Scan bookmarks across all supported browsers."""
    resources = []
    paths = get_user_data_paths()
    
    # Chrome and Edge
    for browser in ["chrome", "edge"]:
        base_path = paths.get(browser)
        if base_path and os.path.exists(base_path):
            # Check default and profiles
            for item in os.listdir(base_path):
                profile_dir = os.path.join(base_path, item)
                if os.path.isdir(profile_dir):
                    bookmarks_file = os.path.join(profile_dir, "Bookmarks")
                    if os.path.exists(bookmarks_file):
                        resources.extend(parse_chrome_style_bookmarks(bookmarks_file, browser))
                        
    # Firefox
    firefox_path = paths.get("firefox")
    if firefox_path and os.path.exists(firefox_path):
        for item in os.listdir(firefox_path):
            profile_dir = os.path.join(firefox_path, item)
            if os.path.isdir(profile_dir):
                places_file = os.path.join(profile_dir, "places.sqlite")
                if os.path.exists(places_file):
                    ff_bookmarks, _ = scan_firefox_places(places_file)
                    resources.extend(ff_bookmarks)
                    
    return resources

def scan_history() -> List[Resource]:
    """Scan browser history across all supported browsers."""
    resources = []
    paths = get_user_data_paths()
    
    # Chrome and Edge
    for browser in ["chrome", "edge"]:
        base_path = paths.get(browser)
        if base_path and os.path.exists(base_path):
            # Check default and profiles
            for item in os.listdir(base_path):
                profile_dir = os.path.join(base_path, item)
                if os.path.isdir(profile_dir):
                    history_file = os.path.join(profile_dir, "History")
                    if os.path.exists(history_file):
                        resources.extend(scan_chrome_style_history(history_file, browser))
                        
    # Firefox
    firefox_path = paths.get("firefox")
    if firefox_path and os.path.exists(firefox_path):
        for item in os.listdir(firefox_path):
            profile_dir = os.path.join(firefox_path, item)
            if os.path.isdir(profile_dir):
                places_file = os.path.join(profile_dir, "places.sqlite")
                if os.path.exists(places_file):
                    _, ff_history = scan_firefox_places(places_file)
                    resources.extend(ff_history)
                    
    return resources

def scan_open_tabs() -> List[Resource]:
    """Scan open browser windows/tabs by looking at system window titles."""
    tabs = []
    if not win32gui or not win32process or not psutil:
        return tabs
        
    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    proc_name = proc.name().lower()
                    if proc_name in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"):
                        # Extract title and remove standard browser suffixes
                        clean_title = title
                        for suffix in (" - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox", " - Brave"):
                            if clean_title.endswith(suffix):
                                clean_title = clean_title[:-len(suffix)]
                                break
                        tabs.append(Resource(
                            name=clean_title.strip(),
                            type="website",
                            source="open_tabs",
                            url=None,  # URL isn't easily readable from HWND titles
                            confidence=0.85
                        ))
                except Exception:
                    pass
        return True
        
    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception as e:
        logger.debug(f"Failed to scan window titles: {e}")
        
    return tabs
