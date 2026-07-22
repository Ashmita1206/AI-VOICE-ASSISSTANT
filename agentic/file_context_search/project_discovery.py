"""
Project Folder Discovery
========================
Discovers all project directories across drives whose names match the query target.
Treats project folders as first-class entities.
"""

import os
import re
import sys
import logging
from typing import List

logger = logging.getLogger(__name__)

STOP_WORDS = {"open", "search", "find", "document", "file", "explorer", "from", "the", "a", "an", "in", "for", "pdf", "ppt", "pptx", "report", "presentation", "doc", "docx"}


def normalize_compact(text: str) -> str:
    """Return compact alphanumeric lowercase string (e.g. 'moneymentor')."""
    if not text:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", text.lower())


def extract_project_keywords(query: str) -> tuple[str, list[str]]:
    """Extract project compact string and project tokens from query."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", query.lower())
    tokens = [t for t in clean.split() if t not in STOP_WORDS]
    compact = normalize_compact("".join(tokens))
    return compact, tokens


def _get_search_roots() -> list[str]:
    """Return base roots to scan for project folders on local system."""
    roots = []
    if sys.platform.startswith("win"):
        for letter in "DCEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append(drive)
    else:
        roots.append("/")
    return roots


def discover_project_folders(query: str) -> list[str]:
    """Discover all folders across drives matching the target project in user query."""
    compact, tokens = extract_project_keywords(query)
    if not compact and not tokens:
        logger.warning("[PROJECT DISCOVERY] No project keywords found in query: %r", query)
        return []

    logger.info("[PROJECT DISCOVERY] Searching project folders for query: %r | Compact: %r | Tokens: %s",
                query, compact, tokens)

    matched_folders: list[str] = []
    seen: set[str] = set()

    def check_and_add(folder_path: str):
        norm = os.path.normpath(folder_path)
        if norm.lower() not in seen and os.path.isdir(norm):
            seen.add(norm.lower())
            matched_folders.append(norm)

    # 1. First check explicit known drive paths for instant matching
    known_paths = [
        r"D:\HEALTHSPHERE",
        r"D:\HEALTHSPHERE\HealthSphere",
        r"D:\healthsphere content",
        r"D:\MONEY MENTOR",
        r"D:\MONEY MENTOR\money-mentor",
        r"D:\moneymentor",
        r"D:\moneymentor content",
    ]
    for kp in known_paths:
        if os.path.exists(kp):
            folder_name_compact = normalize_compact(os.path.basename(kp))
            path_compact = normalize_compact(kp)
            
            if ("healthsphere" in compact and "healthsphere" in path_compact) or \
               (("money" in compact or "mentor" in compact) and ("money" in path_compact or "mentor" in path_compact)):
                check_and_add(kp)

    # 2. Dynamic drive walk (top 3 levels deep) to discover any custom project folders
    roots = _get_search_roots()
    for root in roots:
        try:
            for dirpath, dirnames, _ in os.walk(root):
                # Calculate depth
                rel = os.path.relpath(dirpath, root)
                depth = 0 if rel == "." else len(rel.split(os.sep))
                if depth > 4:
                    dirnames.clear()
                    continue

                # Ignore system noise dirs
                dirnames[:] = [
                    d for d in dirnames 
                    if d.lower() not in [
                        "node_modules", ".git", "__pycache__", "venv", ".venv",
                        "dist", "build", ".next", "$recycle.bin", "windows", "program files", "appdata"
                    ]
                ]

                for d in dirnames:
                    full_d = os.path.join(dirpath, d)
                    d_compact = normalize_compact(d)

                    is_match = False
                    if "healthsphere" in compact and "healthsphere" in d_compact:
                        is_match = True
                    elif ("money" in compact or "mentor" in compact) and \
                         ("money" in d_compact or "mentor" in d_compact):
                        is_match = True
                    elif compact and len(compact) >= 4 and compact in d_compact:
                        is_match = True
                    elif tokens and all(t in d_compact for t in tokens):
                        is_match = True

                    if is_match:
                        check_and_add(full_d)

        except Exception as e:
            logger.warning("[PROJECT DISCOVERY] Error scanning drive %s: %s", root, e)

    logger.info("[PROJECT DISCOVERY] Matched %d Project Folders: %s", len(matched_folders), matched_folders)
    return matched_folders
