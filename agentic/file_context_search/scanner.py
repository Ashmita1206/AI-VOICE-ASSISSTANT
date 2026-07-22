"""
Drive Scanner
=============

Recursively walks local drives and yields (path, stat) for every
supported document file, skipping system/noise directories.

This module is read-only — it never modifies, deletes, or opens files.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Generator, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    # Office documents
    "pdf", "doc", "docx", "odt", "rtf",
    # Presentations
    "ppt", "pptx", "odp",
    # Spreadsheets
    "xls", "xlsx", "ods", "csv",
    # Text & Markup
    "txt", "md",
    # Data (inside project folders)
    "json",
    # Images
    "jpeg", "jpg", "png", "webp", "gif", "bmp", "svg",
    # Notebooks
    "ipynb",
})

# ── Directories to skip entirely ───────────────────────────────────────────
_SKIP_DIR_NAMES: frozenset[str] = frozenset({
    # Node / web
    "node_modules", ".npm", ".yarn",
    # Python
    "__pycache__", ".venv", "venv", "env", ".tox", "site-packages",
    # Version control
    ".git", ".svn", ".hg",
    # Caches / temp
    ".cache", ".tmp", "tmp", "temp", "Temp",
    # Windows system
    "Windows", "Program Files", "Program Files (x86)",
    "ProgramData", "Recovery", "System Volume Information",
    "$Recycle.Bin", "$WINDOWS.~BT", "$WinREAgent",
    # Browser caches
    "Cache", "CachedData", "Code Cache", "GPUCache",
    # Build artefacts
    "dist", "build", ".next", "__pycache__",
    # IDE
    ".idea", ".vscode", ".vs",
})

# Partial path fragments that trigger a skip (case-insensitive contains check)
_SKIP_PATH_FRAGMENTS: tuple[str, ...] = (
    r"\AppData\Local\Temp",
    r"\AppData\Local\Microsoft\Windows",
    r"\AppData\LocalLow",
    r"\AppData\Roaming\npm",
    r"\AppData\Local\Packages",
    r"\Windows\WinSxS",
    r"\Windows\System32",
    r"\Windows\SysWOW64",
)

# Maximum file size to index (50 MB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024


def _get_drives() -> list[str]:
    """Return a list of drive roots to scan on Windows, or '/' on Unix."""
    if sys.platform.startswith("win"):
        drives: list[str] = []
        # Check C through Z
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append(root)
        return drives
    return ["/"]


def _should_skip_dir(dirpath: str, dirname: str) -> bool:
    """Return True if this directory should be excluded from scanning."""
    # Exact name match
    if dirname in _SKIP_DIR_NAMES:
        return True
    # Names starting with a dot (hidden directories)
    if dirname.startswith("."):
        return True
    # Path fragment match (Windows-specific system paths)
    if sys.platform.startswith("win"):
        norm = dirpath.lower()
        for frag in _SKIP_PATH_FRAGMENTS:
            if frag.lower() in norm:
                return True
    return False


def scan_drives(
    extra_roots: list[str] | None = None,
) -> Generator[Tuple[str, os.stat_result], None, None]:
    """Recursively scan all drives and yield ``(absolute_path, stat_result)``
    for every supported file.

    Parameters
    ----------
    extra_roots:
        Additional root directories to scan beyond the detected drives.

    Yields
    ------
    tuple[str, os.stat_result]
        Absolute file path and its ``os.stat_result``.
    """
    roots = _get_drives()
    if extra_roots:
        roots.extend(extra_roots)

    seen_paths: set[str] = set()

    for root in roots:
        if not os.path.exists(root):
            logger.debug("Drive not found, skipping: %s", root)
            continue
        logger.info("[SCANNER] Scanning root: %s", root)
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=None):
            # Prune directories in-place (modifies the walk)
            dirnames[:] = [
                d for d in dirnames
                if not _should_skip_dir(dirpath, d)
            ]

            for filename in filenames:
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                full_path = os.path.join(dirpath, filename)

                # De-duplicate (symlinks etc.)
                if full_path in seen_paths:
                    continue
                seen_paths.add(full_path)

                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue

                # Skip oversized files
                if stat.st_size > MAX_FILE_SIZE_BYTES:
                    logger.debug("Skipping large file: %s (%d bytes)", full_path, stat.st_size)
                    continue

                yield full_path, stat
