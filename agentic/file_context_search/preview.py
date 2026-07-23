"""
File Preview Generator
======================

Produces a short, human-readable snippet from any indexed file —
used for both the UI result card and TTS readout.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PREVIEW_CHARS = 300


def get_file_preview(path: str, stored_summary: str = "") -> str:
    """Return a 1–3 sentence preview of the file content.

    Priority order:
    1. Use ``stored_summary`` if non-empty (already in the index DB).
    2. Re-extract a brief snippet from the file on disk.
    3. Return a generic label if extraction fails.

    Parameters
    ----------
    path:
        Absolute path to the file.
    stored_summary:
        Pre-computed summary stored in the DB (may be empty).

    Returns
    -------
    str
        Short text preview safe for TTS / display.
    """
    if stored_summary and stored_summary.strip():
        return stored_summary.strip()[:MAX_PREVIEW_CHARS]

    try:
        from agentic.file_context_search.embeddings import extract_text, extract_summary
        text = extract_text(path)
        if text:
            return extract_summary(text, max_chars=MAX_PREVIEW_CHARS)
    except Exception as exc:
        logger.debug("[PREVIEW] Could not extract preview for %s: %s", path, exc)

    # Fallback: use the filename itself as a description
    stem = Path(path).stem.replace("_", " ").replace("-", " ")
    return f"File: {stem}"


def format_results_for_voice(results: list) -> str:
    """Format a list of SearchResult objects into a TTS-friendly string.

    Parameters
    ----------
    results:
        List of :class:`~agentic.file_context_search.schemas.SearchResult`.

    Returns
    -------
    str
        Multi-line string suitable for speaking aloud.
    """
    if not results:
        return "I could not find any matching documents. Please try a different description."

    lines = [f"I found {len(results)} matching file{'s' if len(results) > 1 else ''}:"]
    for r in results:
        lines.append(f"  Number {r.rank}: {r.voice_label()}")

    lines.append("Please say 'open number' followed by your choice, for example 'open number 1'.")
    return "\n".join(lines)


def format_results_for_display(results: list) -> list[dict]:
    """Convert results to a list of display-friendly dicts for the UI.

    Parameters
    ----------
    results:
        List of :class:`~agentic.file_context_search.schemas.SearchResult`.

    Returns
    -------
    list[dict]
        Each dict has: rank, filename, folder, extension, modified_date,
        confidence, snippet, path.
    """
    return [r.to_dict() for r in results]
