"""
App Scanner
===========

Scans the local Windows OS for installed applications via Registry,
Start Menu shortcuts, and Desktop entries.
"""

import os
import re
import sys
import logging
from typing import List
from agentic.discovery.schemas import Resource

# Only import Windows-specific libraries if on Windows
try:
    import winreg
    import win32com.client
except ImportError:
    winreg = None
    win32com.client = None

logger = logging.getLogger(__name__)

def resolve_lnk_target(lnk_path: str) -> str:
    """Resolve the target path of a Windows .lnk shortcut file."""
    if not win32com.client:
        return ""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(lnk_path)
        return shortcut.TargetPath
    except Exception as e:
        logger.debug(f"Failed to resolve .lnk file {lnk_path}: {e}")
        return ""

def parse_url_file(filepath: str) -> str:
    """Extract URL from a Windows .url internet shortcut file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().lower().startswith("url="):
                    return line.split("=", 1)[1].strip()
    except Exception as e:
        logger.debug(f"Failed to parse .url file {filepath}: {e}")
    return ""

def scan_registry_apps() -> List[Resource]:
    """Scan registry uninstall keys to find installed applications."""
    if not winreg:
        return []
        
    apps = []
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
    ]
    
    seen_names = set()
    for hkey, path in keys:
        try:
            key = winreg.OpenKey(hkey, path)
            num_subkeys = winreg.QueryInfoKey(key)[0]
            for i in range(num_subkeys):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                        if not name or name.strip() in seen_names:
                            continue
                        
                        seen_names.add(name.strip())
                        
                        exec_path = None
                        try:
                            icon, _ = winreg.QueryValueEx(subkey, "DisplayIcon")
                            if icon:
                                exec_path = icon.split(",")[0].strip(' "')
                        except FileNotFoundError:
                            pass
                        
                        install_loc = None
                        try:
                            loc, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                            if loc:
                                install_loc = loc.strip(' "')
                        except FileNotFoundError:
                            pass
                            
                        if not exec_path and install_loc:
                            exec_path = install_loc

                        # Make a guess at the resource type
                        res_type = "application"
                        executable = None
                        path_val = None

                        if exec_path:
                            if exec_path.lower().endswith(".exe"):
                                executable = exec_path
                            else:
                                path_val = exec_path
                                
                        apps.append(Resource(
                            name=name.strip(),
                            type=res_type,
                            source="registry",
                            executable=executable,
                            path=path_val,
                            confidence=0.85,
                            install_location=install_loc
                        ))
                    except FileNotFoundError:
                        pass
                    finally:
                        subkey.Close()
                except OSError:
                    pass
            key.Close()
        except OSError:
            pass
            
    return apps

def scan_desktop_files() -> List[Resource]:
    """Scan user and public desktop folders for shortcuts."""
    resources = []
    
    # Desktop paths on Windows
    desktop_paths = []
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        desktop_paths.append(os.path.join(user_profile, "Desktop"))
    
    public_profile = os.environ.get("PUBLIC")
    if public_profile:
        desktop_paths.append(os.path.join(public_profile, "Desktop"))
        
    for dp in desktop_paths:
        if not os.path.exists(dp):
            continue
            
        try:
            for entry in os.scandir(dp):
                if entry.is_file():
                    name, ext = os.path.splitext(entry.name)
                    ext = ext.lower()
                    
                    if ext == ".lnk":
                        target = resolve_lnk_target(entry.path)
                        if target:
                            res_type = "folder" if os.path.isdir(target) else "application"
                            resources.append(Resource(
                                name=name,
                                type=res_type,
                                source="desktop",
                                executable=target if res_type == "application" else None,
                                path=target if res_type == "folder" else None,
                                confidence=0.95
                            ))
                    elif ext == ".url":
                        url = parse_url_file(entry.path)
                        if url:
                            resources.append(Resource(
                                name=name,
                                type="website",
                                source="desktop",
                                url=url,
                                confidence=0.95
                            ))
        except Exception as e:
            logger.debug(f"Error scanning desktop path {dp}: {e}")
            
    return resources

def scan_start_menu() -> List[Resource]:
    """Scan Windows start menu for application shortcuts."""
    resources = []
    
    start_menu_paths = []
    # User Start Menu
    appdata = os.environ.get("APPDATA")
    if appdata:
        start_menu_paths.append(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs"))
    # System Start Menu
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        start_menu_paths.append(os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs"))
        
    for sm_path in start_menu_paths:
        if not os.path.exists(sm_path):
            continue
            
        for root, dirs, files in os.walk(sm_path):
            for file in files:
                name, ext = os.path.splitext(file)
                ext = ext.lower()
                filepath = os.path.join(root, file)
                
                if ext == ".lnk":
                    target = resolve_lnk_target(filepath)
                    if target:
                        res_type = "folder" if os.path.isdir(target) else "application"
                        resources.append(Resource(
                            name=name,
                            type=res_type,
                            source="start_menu",
                            executable=target if res_type == "application" else None,
                            path=target if res_type == "folder" else None,
                            confidence=0.9
                        ))
                elif ext == ".url":
                    url = parse_url_file(filepath)
                    if url:
                        resources.append(Resource(
                            name=name,
                            type="website",
                            source="start_menu",
                            url=url,
                            confidence=0.9
                        ))
                        
    return resources

def scan_installed_apps() -> List[Resource]:
    """Aggregate scans from registry, start menu, and desktop."""
    all_resources = []
    seen_executables = set()
    seen_names = set()
    
    # Prioritize start menu and desktop shortcuts over raw registry entries, as they are cleaner
    shortcuts = scan_desktop_files() + scan_start_menu()
    for res in shortcuts:
        name_key = res.name.lower().strip()
        exec_key = (res.executable or res.path or "").lower().strip()
        
        if exec_key:
            seen_executables.add(exec_key)
        seen_names.add(name_key)
        all_resources.append(res)
        
    registry_apps = scan_registry_apps()
    for res in registry_apps:
        name_key = res.name.lower().strip()
        exec_key = (res.executable or res.path or "").lower().strip()
        
        # Avoid duplicates from registry
        if name_key in seen_names:
            continue
        if exec_key and exec_key in seen_executables:
            continue
            
        all_resources.append(res)
        if exec_key:
            seen_executables.add(exec_key)
        seen_names.add(name_key)
        
    return all_resources
