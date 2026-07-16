"""
Document Search Tool Handler
==============================

Registers two new tools with the execution registry:

``find_document_by_context``
    Performs a semantic context search and returns a ranked list of up to
    5 matching files.  Results are stored in the session so the user can
    say "open number 2" in a follow-up turn.

``open_document_result``
    Resolves ``result_number`` (1–5) against the session's pending document
    results and opens the chosen file using the existing ``open_file``
    automation.

These tools are ADDITIVE — they do not modify any existing handler.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from execution.registry import register_tool
from execution.schemas import ExecutionResult

logger = logging.getLogger(__name__)


# ── Tool 1: find_document_by_context ──────────────────────────────────────

@register_tool("find_document_by_context")
def find_document_by_context(args: dict[str, Any]) -> ExecutionResult:
    """Semantic context search across all indexed local files.

    Args (from planner)
    -------------------
    query : str
        Free-form user description (e.g. "CDOT proposal from last year").
    top_n : int, optional
        Maximum results to return (default 5, max 5).
    """
    query: str = args.get("query", "").strip()

    if not query:
        return ExecutionResult(
            success=False,
            tool="find_document_by_context",
            message="No search query provided. Please describe the document you are looking for.",
        )

    top_n = min(int(args.get("top_n", 5)), 5)

    try:
        from agentic.document_search.manager import DocumentSearchManager
        from agentic.document_search.preview import (
            format_results_for_voice,
            format_results_for_display,
        )

        # Perform the search (lazy-starts indexer if not running)
        results = DocumentSearchManager.find_documents(query, top_n=top_n)

        # ── Store in session for follow-up "open number X" ─────────────
        try:
            from agentic.memory.session_state import get_session
            session = get_session()
            session.pending_document_results = [r.to_dict() for r in results]
            logger.info(
                "[DOC_SEARCH] Stored %d pending results in session.", len(results)
            )
        except Exception as sess_exc:
            logger.warning("[DOC_SEARCH] Could not store results in session: %s", sess_exc)

        if not results:
            # Index may be empty (first run still scanning)
            from agentic.document_search.manager import DocumentSearchManager as DSM
            status = DSM.get_indexer_status()
            if status["indexed_count"] == 0:
                voice_msg = (
                    "I am still building the document index. "
                    "Please try again in a few minutes."
                )
            else:
                voice_msg = (
                    f"I could not find any files matching '{query}'. "
                    "Try using different keywords or a more specific description."
                )
            return ExecutionResult(
                success=True,
                tool="find_document_by_context",
                message=voice_msg,
                output=json.dumps([]),
            )

        # ── Format voice and display responses ─────────────────────────
        voice_msg = format_results_for_voice(results)
        display_data = format_results_for_display(results)

        return ExecutionResult(
            success=True,
            tool="find_document_by_context",
            message=voice_msg,
            output=json.dumps(display_data, ensure_ascii=False),
        )

    except Exception as exc:
        logger.exception("[DOC_SEARCH] Unexpected error during search")
        return ExecutionResult(
            success=False,
            tool="find_document_by_context",
            message=f"Document search failed: {exc}",
        )


# ── Tool 2: open_document_result ──────────────────────────────────────────

@register_tool("open_document_result")
def open_document_result(args: dict[str, Any]) -> ExecutionResult:
    """Open a file from the previously returned document search results.

    Args (from planner)
    -------------------
    result_number : int
        1-based index into the pending results list (1–5).
    """
    raw_number = args.get("result_number", args.get("number", 1))
    try:
        result_number = int(raw_number)
    except (ValueError, TypeError):
        result_number = 1

    # ── Retrieve pending results from session ──────────────────────────
    try:
        from agentic.memory.session_state import get_session
        session = get_session()
        pending = getattr(session, "pending_document_results", [])
    except Exception as exc:
        logger.warning("[DOC_SEARCH] Could not read session: %s", exc)
        pending = []

    if not pending:
        return ExecutionResult(
            success=False,
            tool="open_document_result",
            message=(
                "I don't have any recent document search results. "
                "Please say 'find' followed by a document description first."
            ),
        )

    if result_number < 1 or result_number > len(pending):
        return ExecutionResult(
            success=False,
            tool="open_document_result",
            message=(
                f"Invalid selection. Please choose a number between "
                f"1 and {len(pending)}."
            ),
        )

    chosen = pending[result_number - 1]
    file_path: str = chosen.get("path", "")

    if not file_path:
        return ExecutionResult(
            success=False,
            tool="open_document_result",
            message="Could not determine the file path for that result.",
        )

    # ── Delegate to existing open_file handler ─────────────────────────
    try:
        from automation.filesystem import open_file as _open_file
        result = _open_file({"path": file_path})
        if result.success:
            filename = chosen.get("filename", file_path)
            result.message = f"Opening {filename}."
        return ExecutionResult(
            success=result.success,
            tool="open_document_result",
            message=result.message,
        )
    except Exception as exc:
        logger.exception("[DOC_SEARCH] Failed to open file: %s", file_path)
        return ExecutionResult(
            success=False,
            tool="open_document_result",
            message=f"Failed to open the file: {exc}",
        )
