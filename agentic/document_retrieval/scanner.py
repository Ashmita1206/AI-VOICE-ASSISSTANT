"""
Document Retrieval Scanner
==========================

Recursively walks local drives and yields (path, stat) for every
supported document file, skipping system/noise directories.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Generator, Tuple

from agentic.document_retrieval import config

logger = logging.getLogger(__name__)

def _get_drives() -> list[str]:
    """Return a list of drive roots to scan on Windows, or '/' on Unix."""
    if sys.platform.startswith("win"):
        drives = []
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append(root)
        return drives
    return ["/"]

EXCLUDED_FILENAME_KEYWORDS = frozenset({
    "app_context", "history", "document_index", "document_retrieval",
    "knowledge_index", "session", "pytest", "cacert", "package-lock"
})

def _get_user_priority_roots() -> list[str]:
    """Return user priority folders (Desktop, Documents, Downloads, OneDrive Desktop/Documents, etc.)."""
    user_home = os.path.expanduser("~")
    onedrive_home = os.path.join(user_home, "OneDrive")
    
    priority_dirs = [
        os.path.join(user_home, "Desktop"),
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Downloads"),
        os.path.join(user_home, "Pictures"),
        os.path.join(user_home, "Projects"),
        os.path.join(user_home, "Workspaces"),
        onedrive_home,
        os.path.join(onedrive_home, "Desktop"),
        os.path.join(onedrive_home, "Documents"),
        os.path.join(onedrive_home, "Pictures"),
    ]
    return [d for d in priority_dirs if os.path.exists(d)]

def _should_skip_dir(dirpath: str, dirname: str) -> bool:
    """Return True if this directory should be excluded from scanning, logging the exact reason."""
    lower_dir = dirname.lower()
    full_target_path = os.path.join(dirpath, dirname)
    
    if lower_dir in config.SKIP_DIR_NAMES:
        logger.info(f"Skipping: {full_target_path} | Reason: System Folder ({dirname})")
        print(f"Skipping: {full_target_path} | Reason: System Folder")
        return True
        
    if lower_dir.startswith("."):
        logger.info(f"Skipping: {full_target_path} | Reason: Hidden Folder ({dirname})")
        return True
    
    norm = dirpath.lower().replace("/", "\\")
    for frag in config.SKIP_PATH_FRAGMENTS:
        if frag.lower() in norm:
            logger.info(f"Skipping: {full_target_path} | Reason: System Path Fragment ({frag})")
            return True
            
    return False

def scan_drives(extra_roots: list[str] | None = None) -> Generator[Tuple[str, os.stat_result], None, None]:
    """Recursively scan priority user folders first, then all drives, yielding supported files."""
    roots = _get_user_priority_roots()
    drive_roots = _get_drives()
    
    for dr in drive_roots:
        if dr not in roots:
            roots.append(dr)
            
    if extra_roots:
        roots.extend(extra_roots)

    seen_paths = set()

    for root in roots:
        if not os.path.exists(root):
            continue
        logger.info(f"[SCANNER] Scanning root: {root}")
        
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=None):
            # Prune directory tree to prevent traversing into skipped system folders
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(dirpath, d)]

            valid_folder_files = []

            for filename in filenames:
                lower_fn = filename.lower()
                
                # Filter out system/internal filenames
                if any(kw in lower_fn for kw in EXCLUDED_FILENAME_KEYWORDS):
                    continue

                ext = lower_fn.rsplit(".", 1)[-1] if "." in lower_fn else ""
                if ext in config.NEVER_INDEX_EXTENSIONS or ext not in config.SUPPORTED_EXTENSIONS:
                    continue

                full_path = os.path.join(dirpath, filename)
                if full_path in seen_paths:
                    continue

                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue

                if stat.st_size > config.MAX_FILE_SIZE_BYTES or stat.st_size == 0:
                    continue

                seen_paths.add(full_path)
                valid_folder_files.append((full_path, filename, stat))

            # Phase 5: Log folder scanning progress and discovered files
            if valid_folder_files:
                fn_list = ", ".join([item[1] for item in valid_folder_files[:5]])
                if len(valid_folder_files) > 5:
                    fn_list += f" (+{len(valid_folder_files) - 5} more)"
                    
                log_msg = (
                    f"\nScanning:\n{dirpath}\n\n"
                    f"Found:\n{fn_list}\n\n"
                    f"Completed folder.\nIndexed {len(valid_folder_files)} files."
                )
                logger.info(log_msg)
                print(log_msg)

                for full_path, _, stat in valid_folder_files:
                    yield full_path, stat
