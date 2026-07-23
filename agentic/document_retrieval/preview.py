"""
Document Retrieval Preview formatting
=====================================

Formatting for voice TTS and UI.
"""

from typing import List

from agentic.document_retrieval.schemas import SearchResult

def format_results_for_voice(results: List[SearchResult]) -> str:
    """Format results for spoken readout."""
    if not results:
        return "I could not find any matching documents. Please try rephrasing your search."
        
    lines = [f"I found {len(results)} matching file{'s' if len(results) > 1 else ''}:"]
    for r in results:
        # Provide a clean, speakable label
        stem = r.filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
        lines.append(f"  Number {r.rank}: {stem}")
        
    lines.append("Please say 'open number' followed by your choice, for example 'open number 1'.")
    return "\n".join(lines)

def format_results_for_display(results: List[SearchResult]) -> List[dict]:
    """Format results for the UI Modal."""
    return [r.to_dict() for r in results]
