"""
Utility functions for file_context_search.
"""

def sanitize_query(query: str) -> str:
    """Sanitize and clean up a search query."""
    return query.strip().lower()
