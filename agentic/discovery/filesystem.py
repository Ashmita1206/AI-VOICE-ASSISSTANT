"""
Filesystem Scanner
==================

Scans the local filesystem for common workspace folders, project structures,
and recent files or directories.
"""

import os
import logging
from typing import List, Tuple
from agentic.discovery.schemas import Resource
from agentic.discovery.apps import resolve_lnk_target

logger = logging.getLogger(__name__)

def scan_home_directories() -> List[Resource]:
    """Scan the user's home directory for top-level folders and workspaces."""
    user_home = os.path.expanduser("~")
    resources = []
    
    common_folders = [
        "Documents", "Downloads", "Pictures", "Videos", "Music", 
        "Projects", "Source", "Github", "Workspace", "Desktop"
    ]
    
    for folder_name in common_folders:
        folder_path = os.path.join(user_home, folder_name)
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            last_used = 0.0
            try:
                last_used = os.path.getmtime(folder_path)
            except Exception:
                pass
            resources.append(Resource(
                name=folder_name,
                type="folder",
                source="filesystem",
                path=folder_path,
                confidence=0.8,
                last_used=last_used
            ))
            
    # List other non-hidden directories under the user's home
    try:
        # Filter out system and hidden files/directories
        exclude = {
            "appdata", "application data", "cookies", "local settings", 
            "my documents", "nethood", "printhood", "recent", "sendto", 
            "start menu", "templates"
        }
        for entry in os.scandir(user_home):
            if entry.is_dir() and not entry.name.startswith("."):
                name_lower = entry.name.lower()
                if name_lower not in exclude and entry.name not in common_folders:
                    last_used = 0.0
                    try:
                        last_used = os.path.getmtime(entry.path)
                    except Exception:
                        pass
                    resources.append(Resource(
                        name=entry.name,
                        type="folder",
                        source="filesystem",
                        path=entry.path,
                        confidence=0.7,
                        last_used=last_used
                    ))
    except Exception as e:
        logger.debug(f"Failed to scan home directory contents: {e}")
        
    return resources

def scan_recent_items() -> Tuple[List[Resource], List[Resource]]:
    """Scan the Windows Recent Items folder to find recently opened files and folders."""
    recent_files = []
    recent_folders = []
    
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return recent_files, recent_folders
        
    recent_dir = os.path.join(appdata, r"Microsoft\Windows\Recent")
    if not os.path.exists(recent_dir):
        return recent_files, recent_folders
        
    try:
        for entry in os.scandir(recent_dir):
            if entry.is_file() and entry.name.lower().endswith(".lnk"):
                target = resolve_lnk_target(entry.path)
                if target and os.path.exists(target):
                    # Use the display name from the shortcut file (without .lnk extension)
                    display_name, _ = os.path.splitext(entry.name)
                    
                    last_used = 0.0
                    try:
                        last_used = os.path.getmtime(target)
                    except Exception:
                        pass
                    
                    if os.path.isdir(target):
                        recent_folders.append(Resource(
                            name=display_name,
                            type="folder",
                            source="filesystem",
                            path=target,
                            confidence=0.85,
                            last_used=last_used
                        ))
                    else:
                        recent_files.append(Resource(
                            name=display_name,
                            type="file",
                            source="filesystem",
                            path=target,
                            confidence=0.85,
                            last_used=last_used
                        ))
    except Exception as e:
        logger.debug(f"Failed to scan recent items: {e}")
        
    return recent_files, recent_folders

def search_recent_files() -> List[Resource]:
    """Retrieve recently used files."""
    files, _ = scan_recent_items()
    return files

def search_recent_folders() -> List[Resource]:
    """Retrieve recently used folders."""
    _, folders = scan_recent_items()
    return folders
