"""
Command Registry
================

Centralised, declarative repository of all supported commands.

No logic lives here.  This module simply defines the dataset of
available intents using the schemas defined in ``agent.schemas``.
Adding a new voice command is as simple as adding a new
``IntentDefinition`` to the ``_REGISTRY`` list.

Usage:
    from agent.command_registry import get_all_intents, get_intent

    all_defs = get_all_intents()
    search_def = get_intent("search_web")
"""

from __future__ import annotations

from agent.schemas import IntentDefinition, IntentPattern

# ══════════════════════════════════════════════════════════════════════
# THE REGISTRY
# ══════════════════════════════════════════════════════════════════════

_REGISTRY: list[IntentDefinition] = [

    # ──────────────────────────────────────────────────────────────────
    # APPLICATION COMMANDS
    # ──────────────────────────────────────────────────────────────────

    IntentDefinition(
        name="open_application",
        category="application",
        description="Open or launch a desktop application.",
        patterns=[
            # Standard English forms
            IntentPattern("open {application}"),
            IntentPattern("launch {application}"),
            IntentPattern("start {application}"),
            # Hinglish preprocessor output (e.g., "chrome kholo" -> "chrome open")
            IntentPattern("{application} open"),
        ],
        keywords=["open", "launch", "start", "application", "app"],
        entity_schema={"application": "str"},
    ),
    IntentDefinition(
        name="close_application",
        category="application",
        description="Close or terminate a running application.",
        patterns=[
            IntentPattern("close {application}"),
            IntentPattern("quit {application}"),
            IntentPattern("terminate {application}"),
            # Hinglish preprocessor output
            IntentPattern("{application} close"),
        ],
        keywords=["close", "quit", "terminate", "exit", "kill"],
        entity_schema={"application": "str"},
    ),
    IntentDefinition(
        name="open_terminal",
        category="application",
        description="Open the system terminal/command prompt.",
        patterns=[
            IntentPattern("open terminal"),
            IntentPattern("terminal open"),
            IntentPattern("launch terminal"),
        ],
        keywords=["terminal", "prompt", "console", "bash"],
        entity_schema={},
    ),
    IntentDefinition(
        name="open_file_manager",
        category="application",
        description="Open the OS file explorer.",
        patterns=[
            IntentPattern("open file manager"),
            IntentPattern("file manager open"),
            IntentPattern("open explorer"),
        ],
        keywords=["file", "manager", "explorer", "files"],
        entity_schema={},
    ),

    # ──────────────────────────────────────────────────────────────────
    # BROWSER & WEB COMMANDS
    # ──────────────────────────────────────────────────────────────────

    IntentDefinition(
        name="open_browser",
        category="browser",
        description="Launch the default web browser.",
        patterns=[
            IntentPattern("open browser"),
            IntentPattern("browser open"),
        ],
        keywords=["browser", "internet", "web"],
        entity_schema={},
    ),
    IntentDefinition(
        name="search_web",
        category="browser",
        description="Search for a query, optionally on a specific application/engine.",
        patterns=[
            IntentPattern("search {query} on {application}"),
            IntentPattern("search {query} in {application}"),
            IntentPattern("{application} on {query} search"), # Google pe ML search kro -> google on ML search
            IntentPattern("{application} in {query} search"),
            IntentPattern("search {query}"),
            IntentPattern("{query} search"),
            IntentPattern("google {query}"),
            IntentPattern("search for {query}"),
        ],
        keywords=["search", "google", "find", "query", "look"],
        entity_schema={"query": "str", "application": "str"},
    ),
    IntentDefinition(
        name="open_website",
        category="browser",
        description="Open a specific website by name.",
        patterns=[
            IntentPattern("open website {website}"),
            IntentPattern("open {website}"),
            IntentPattern("{website} open"),
            IntentPattern("go to {website}"),
        ],
        keywords=["website", "site", "com", "www"],
        entity_schema={"website": "str"},
    ),

    # ──────────────────────────────────────────────────────────────────
    # SYSTEM COMMANDS
    # ──────────────────────────────────────────────────────────────────

    IntentDefinition(
        name="system_info",
        category="system",
        description="Get general system health and info.",
        patterns=[
            IntentPattern("system info"),
            IntentPattern("system information"),
            IntentPattern("pc info"),
        ],
        keywords=["system", "info", "information", "health", "status"],
        entity_schema={},
    ),
    IntentDefinition(
        name="check_time",
        category="system",
        description="Get the current local time.",
        patterns=[
            IntentPattern("what time is it"),
            IntentPattern("tell me the time"),
            IntentPattern("check time"),
            IntentPattern("time is what"),
            IntentPattern("time tell"),
        ],
        keywords=["time", "clock", "hour"],
        entity_schema={},
    ),
    IntentDefinition(
        name="check_date",
        category="system",
        description="Get the current date.",
        patterns=[
            IntentPattern("what is the date"),
            IntentPattern("what date is today"),
            IntentPattern("check date"),
            IntentPattern("date tell"),
        ],
        keywords=["date", "today", "day", "month", "year"],
        entity_schema={},
    ),
    IntentDefinition(
        name="check_memory",
        category="system",
        description="Check RAM usage.",
        patterns=[
            IntentPattern("check memory"),
            IntentPattern("memory usage"),
            IntentPattern("how much ram"),
        ],
        keywords=["memory", "ram", "usage", "free"],
        entity_schema={},
    ),
    IntentDefinition(
        name="check_disk",
        category="system",
        description="Check storage usage.",
        patterns=[
            IntentPattern("check disk"),
            IntentPattern("disk space"),
            IntentPattern("storage space"),
        ],
        keywords=["disk", "storage", "space", "drive"],
        entity_schema={},
    ),
    IntentDefinition(
        name="ip_address",
        category="system",
        description="Get local/public IP address.",
        patterns=[
            IntentPattern("what is my ip"),
            IntentPattern("ip address"),
            IntentPattern("check ip"),
        ],
        keywords=["ip", "address", "network"],
        entity_schema={},
    ),
    IntentDefinition(
        name="uptime",
        category="system",
        description="Check how long the system has been running.",
        patterns=[
            IntentPattern("system uptime"),
            IntentPattern("how long has the pc been on"),
            IntentPattern("uptime"),
        ],
        keywords=["uptime", "running", "since"],
        entity_schema={},
    ),

    # ──────────────────────────────────────────────────────────────────
    # UTILITIES
    # ──────────────────────────────────────────────────────────────────

    IntentDefinition(
        name="list_files",
        category="utilities",
        description="List files in the current or specified directory.",
        patterns=[
            IntentPattern("list files"),
            IntentPattern("show files"),
            IntentPattern("what is in this folder"),
            IntentPattern("list files in {directory}"),
        ],
        keywords=["list", "files", "show", "directory", "folder", "ls", "dir"],
        entity_schema={"directory": "str"},
    ),
    IntentDefinition(
        name="take_screenshot",
        category="utilities",
        description="Capture the current screen.",
        patterns=[
            IntentPattern("take screenshot"),
            IntentPattern("take a screenshot"),
            IntentPattern("capture screen"),
        ],
        keywords=["screenshot", "capture", "screen", "snip"],
        entity_schema={},
    ),

    # ──────────────────────────────────────────────────────────────────
    # FALLBACK
    # ──────────────────────────────────────────────────────────────────

    IntentDefinition(
        name="unknown",
        category="fallback",
        description="Fallback intent when nothing else matches with sufficient confidence.",
        patterns=[],  # Explicitly empty; handled dynamically by the classifier
        keywords=[],
        entity_schema={},
    ),
]


# ══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════

# Cache for fast lookup by name
_INTENT_MAP = {defn.name: defn for defn in _REGISTRY}


def get_all_intents() -> list[IntentDefinition]:
    """Return a list of all defined intents in the registry."""
    return _REGISTRY


def get_intent(name: str) -> IntentDefinition | None:
    """Look up a specific intent by its canonical name.

    Returns ``None`` if the intent is not found.
    """
    return _INTENT_MAP.get(name)


def list_intent_names() -> list[str]:
    """Return a list of all intent names (e.g. for logging or CLI)."""
    return list(_INTENT_MAP.keys())
