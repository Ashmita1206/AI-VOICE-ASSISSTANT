"""
File Context Search Tool
========================

Handles searching and opening documents using the file_context_search plugin.
Registers ONE tool: find_document_by_context
"""

import json
import logging
import subprocess
import os
from typing import Any

from execution.registry import register_tool
from execution.schemas import ExecutionResult

logger = logging.getLogger(__name__)

@register_tool("find_document_by_context")
def find_document_by_context(args: dict[str, Any]) -> ExecutionResult:
    """Semantic context search across local files, OR opens a previously found result.

    Args (from planner)
    -------------------
    query : str, optional
        Search description (e.g. "CDOT proposal").
    result_number : int, optional
        If provided, opens the file corresponding to this result from the previous search.
    top_n : int, optional
        Maximum results to return for a search (default 5).
    """
    print("=" * 80)
    print("[TOOL DEBUG] ENTER find_document_by_context")
    print(f"[TOOL DEBUG] Original args: {args}")
    print(f"[TOOL DEBUG] Args keys: {list(args.keys())}")
    
    # ── OPEN MODE ─────────────────────────────────────────────────────────────
    raw_number = args.get("result_number", args.get("number"))
    print(f"[TOOL DEBUG] raw_number: {raw_number}")
    
    if raw_number is not None:
        print("[TOOL DEBUG] ENTERING OPEN MODE")
        try:
            result_number = int(raw_number)
        except (ValueError, TypeError):
            result_number = 1
        print(f"[TOOL DEBUG] result_number: {result_number}")
            
        try:
            from agentic.memory.session_state import get_session
            session = get_session()
            pending = getattr(session, "pending_document_results", [])
        except Exception as exc:
            logger.warning("[FILE_SEARCH] Could not read session: %s", exc)
            pending = []
        print(f"[TOOL DEBUG] pending results count: {len(pending)}")
            
        if not pending:
            print("[TOOL DEBUG] No pending results - returning error")
            result = ExecutionResult(
                success=False,
                tool="find_document_by_context",
                message="I don't have any recent document search results to open.",
            )
            print(f"[TOOL DEBUG] OPEN MODE RETURN: {result.to_dict()}")
            return result
            
        if result_number < 1 or result_number > len(pending):
            print(f"[TOOL DEBUG] Invalid selection: {result_number} not in range 1-{len(pending)}")
            result = ExecutionResult(
                success=False,
                tool="find_document_by_context",
                message=f"Invalid selection. Please choose a number between 1 and {len(pending)}.",
            )
            print(f"[TOOL DEBUG] OPEN MODE RETURN: {result.to_dict()}")
            return result
            
        chosen = pending[result_number - 1]
        file_path: str = chosen.get("path", "")
        print(f"[TOOL DEBUG] Chosen file path: {file_path}")
        
        if not file_path or not os.path.exists(file_path):
            print(f"[TOOL DEBUG] File not found: {file_path}, exists: {os.path.exists(file_path) if file_path else False}")
            result = ExecutionResult(
                success=False,
                tool="find_document_by_context",
                message="Could not locate the file on disk.",
            )
            print(f"[TOOL DEBUG] OPEN MODE RETURN: {result.to_dict()}")
            return result
            
        # 1. Open Windows File Explorer to highlight the file
        explorer_cmd = f'explorer /select,"{file_path}"'
        try:
            logger.info("[FIND_DOC] Launching Explorer — cmd: %s", explorer_cmd)
            proc = subprocess.Popen(explorer_cmd, shell=True)
            logger.info("[FIND_DOC] Explorer PID: %s", getattr(proc, 'pid', '?'))
        except Exception as e:
            logger.warning("[FIND_DOC] Failed to launch Explorer: %s", e)
            
        # 2. Open the file itself using existing open_file handler
        try:
            from automation.filesystem import open_file as _open_file
            logger.info("[FIND_DOC] Calling open_file() for path: %s", file_path)
            print(f"[TOOL DEBUG] Calling open_file for: {file_path}")
            result = _open_file({"path": file_path})
            logger.info("[FIND_DOC] open_file() result: success=%s  msg=%r", result.success, result.message)
            print(f"[TOOL DEBUG] open_file result: success={result.success}, message={result.message}")
            # Disk verification
            import os as _os
            exists = _os.path.exists(file_path)
            logger.info("[FIND_DOC] File exists on disk: %s  path=%s", exists, file_path)
            filename = chosen.get("filename", file_path)
            result = ExecutionResult(
                success=result.success,
                tool="find_document_by_context",
                message=f"Opening {filename}.",
            )
            print(f"[TOOL DEBUG] OPEN MODE RETURN: {result.to_dict()}")
            return result
        except Exception as exc:
            logger.exception("[FIND_DOC] Failed to open file: %s", file_path)
            print(f"[TOOL DEBUG] Exception in open_file: {exc}")
            result = ExecutionResult(
                success=False,
                tool="find_document_by_context",
                message=f"Failed to open the file: {exc}",
            )
            print(f"[TOOL DEBUG] OPEN MODE RETURN: {result.to_dict()}")
            return result


    # ── SEARCH MODE ───────────────────────────────────────────────────────────
    print("[TOOL DEBUG] ENTERING SEARCH MODE")
    query = args.get("query", "").strip()
    print(f"[TOOL DEBUG] Query: '{query}'")
    
    if not query:
        print("[TOOL DEBUG] No query provided - returning error")
        result = ExecutionResult(
            success=False,
            tool="find_document_by_context",
            message="No search query or result number provided.",
        )
        print(f"[TOOL DEBUG] SEARCH MODE RETURN: {result.to_dict()}")
        return result
        
    top_n = min(int(args.get("top_n", 5)), 5)
    print(f"[TOOL DEBUG] top_n: {top_n}")
    
    # 1. Visibly launch Windows File Explorer to give the visual experience
    try:
        subprocess.Popen("explorer", shell=True)
        logger.info("[FILE_SEARCH] Visibly launched File Explorer for search experience.")
        print("[TOOL DEBUG] Launched File Explorer")
    except Exception as e:
        logger.warning("[FILE_SEARCH] Failed to launch explorer: %s", e)
        print(f"[TOOL DEBUG] Failed to launch explorer: {e}")
        
    # 2. Execute semantic search
    try:
        from agentic.file_context_search.manager import DocumentSearchManager
        from agentic.file_context_search.preview import (
            format_results_for_voice,
            format_results_for_display,
        )
        
        print("[TOOL DEBUG] Calling DocumentSearchManager.find_documents")
        results = DocumentSearchManager.find_documents(query, top_n=top_n)
        print(f"[TOOL DEBUG] Search returned {len(results)} results")
        
        try:
            from agentic.memory.session_state import get_session
            session = get_session()
            session.pending_document_results = [r.to_dict() for r in results]
            print(f"[TOOL DEBUG] Stored {len(results)} results in session")
        except Exception as sess_exc:
            logger.warning("[FILE_SEARCH] Could not store results in session: %s", sess_exc)
            print(f"[TOOL DEBUG] Failed to store results in session: {sess_exc}")
            
        if not results:
            print("[TOOL DEBUG] No results found")
            status = DocumentSearchManager.get_indexer_status()
            print(f"[TOOL DEBUG] Indexer status: {status}")
            if status["indexed_count"] == 0:
                voice_msg = "I am still building the document index in the background. Please try again shortly."
            else:
                voice_msg = f"I could not find any files matching '{query}'."
            result = ExecutionResult(
                success=True,
                tool="find_document_by_context",
                message=voice_msg,
                output=json.dumps([]),
                data={"results": []}
            )
            print(f"[TOOL DEBUG] SEARCH MODE RETURN (no results): {result.to_dict()}")
            return result
            
        print(f"[TOOL DEBUG] Found {len(results)} results")
        for i, r in enumerate(results):
            print(f"[TOOL DEBUG] Result {i+1}: {r.to_dict()}")
            
        voice_msg = "I found matching documents. The results are now displayed on your screen. Please say 'Open number 1' or click a result."
        display_data = format_results_for_display(results)
        print(f"[TOOL DEBUG] Display data length: {len(display_data)}")
        
        result = ExecutionResult(
            success=True,
            tool="find_document_by_context",
            message=voice_msg,
            output=display_data,
            data={"results": [r.to_dict() for r in results]},
            requires_interaction=True
        )
        print(f"[TOOL DEBUG] requires_interaction: {result.requires_interaction}")
        print(f"[TOOL DEBUG] data.results count: {len(result.data.get('results', []))}")
        print(f"[TOOL DEBUG] SEARCH MODE RETURN (success): {result.to_dict()}")
        return result
        
    except Exception as exc:
        logger.exception("[FILE_SEARCH] Search failed: %s", exc)
        print(f"[TOOL DEBUG] Exception in search: {exc}")
        result = ExecutionResult(
            success=False,
            tool="find_document_by_context",
            message="An error occurred while searching for the document.",
        )
        print(f"[TOOL DEBUG] SEARCH MODE RETURN (exception): {result.to_dict()}")
        return result
