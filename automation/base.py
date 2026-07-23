"""
Automation Interface
====================

Defines the generic AutomationTool abstract base class.
All app-specific automation modules (WhatsApp, Gmail, Calendar, Slack, etc.)
must inherit from this interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple
from execution.schemas import ExecutionResult


class AutomationTool(ABC):
    """Abstract base class for all task automation modules in the system."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier name for the automation tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this automation tool does."""
        pass

    @abstractmethod
    def validate(self, args: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate input arguments before execution.

        Returns:
            (is_valid, error_message)
        """
        pass

    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> ExecutionResult:
        """Execute the automation tool with given arguments.

        Returns:
            ExecutionResult containing success status, output, and metadata.
        """
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema representation of the tool parameters."""
        pass
