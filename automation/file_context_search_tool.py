"""
File Context Search Tool
========================

Handles searching and opening documents using the document_retrieval engine.
"""

from typing import Any
from execution.schemas import ExecutionResult
from automation.document_retrieval_tool import find_document_by_context, open_document_result

__all__ = ["find_document_by_context", "open_document_result"]
