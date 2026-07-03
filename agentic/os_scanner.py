"""
OS Application Scanner
======================

Dynamically discovers installed applications by scanning Linux desktop entries
and utilizing shutil.which for binary lookups. Provides fuzzy matching capabilities.
"""

import os
import glob
import shutil
import logging
import difflib

logger = logging.getLogger(__name__)

# Cache of discovered applications { "chrome": "google-chrome", "spotify": "spotify" }
_APPS_CACHE: dict[str, str] = {}
_SCANNED = False

def scan_installed_apps() -> dict[str, str]:
    """Scan the system for applications and cache the mapping."""
    global _SCANNED
    if _SCANNED:
        return _APPS_CACHE

    logger.info("Scanning for installed applications...")
    
    # Common desktop entry locations on Ubuntu/Linux
    desktop_dirs = [
        "/usr/share/applications/",
        "/usr/local/share/applications/",
        os.path.expanduser("~/.local/share/applications/")
    ]
    
    apps = {}
    for d in desktop_dirs:
        if not os.path.exists(d):
            continue
            
        for filepath in glob.glob(os.path.join(d, "*.desktop")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    name = None
                    exec_cmd = None
                    
                    for line in f:
                        line = line.strip()
                        if line.startswith("Name=") and not name:
                            name = line.split("=", 1)[1].lower()
                        elif line.startswith("Exec=") and not exec_cmd:
                            # Exec=google-chrome %U -> google-chrome
                            exec_full = line.split("=", 1)[1]
                            exec_cmd = exec_full.split()[0].strip(' "''')
                            # Handle paths in Exec
                            exec_cmd = os.path.basename(exec_cmd)
                    
                    if name and exec_cmd:
                        # Verify the executable exists in PATH
                        if shutil.which(exec_cmd):
                            apps[name] = exec_cmd
            except Exception as e:
                logger.debug("Failed to parse desktop file %s: %s", filepath, e)

    # Hardcode some common aliases if they exist on the system
    common_aliases = {
        "vscode": "code",
        "vs code": "code",
        "chrome": "google-chrome",
        "telegram": "telegram-desktop"
    }
    
    for alias, cmd in common_aliases.items():
        if shutil.which(cmd):
            apps[alias] = cmd

    _APPS_CACHE.update(apps)
    _SCANNED = True
    logger.info(f"Discovered {len(apps)} executable applications.")
    return _APPS_CACHE

def find_application(app_name: str) -> str | None:
    """Fuzzy match an application name to its executable command."""
    apps = scan_installed_apps()
    app_name = app_name.lower().strip()
    
    # 1. Exact match
    if app_name in apps:
        return apps[app_name]
        
    # 2. Substring match (e.g. 'chrome' in 'google chrome')
    for name, cmd in apps.items():
        if app_name in name:
            return cmd
            
    # 3. Fuzzy match
    matches = difflib.get_close_matches(app_name, apps.keys(), n=1, cutoff=0.6)
    if matches:
        return apps[matches[0]]
        
    # 4. Final fallback - maybe the user just passed the exact command name
    if shutil.which(app_name):
        return app_name

    return None
