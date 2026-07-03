"""
Agent Schemas — Data Contracts for Intent Detection
=====================================================

This module defines the three core dataclasses that every other
module in the ``agent`` package depends on:

    CommandIntent      — the final structured output returned to callers
    IntentPattern      — a single regex-based pattern for matching one intent
    IntentDefinition   — groups all patterns + metadata for one intent

Design rationale
----------------
* **Dataclasses over dicts** — gives us type safety, IDE autocomplete,
  ``__repr__`` for free, and a clear schema that acts as documentation.
* **to_dict() helpers** — so the output can be trivially serialised to
  JSON for logging, evaluation, or API responses.
* **Frozen CommandIntent** — once a classification result is produced,
  it should never be mutated.  This prevents subtle downstream bugs.

These schemas are intentionally dependency-free (stdlib only) so they
can be imported anywhere without pulling in heavy libraries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────────────────────────────
# 1. CommandIntent — the final output of the classification pipeline
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommandIntent:
    """Immutable result of intent classification.

    This is the single object that flows from the agent to the
    execution layer in Phase 4.

    Attributes
    ----------
    intent : str
        Canonical intent name, e.g. ``"search_web"``, ``"open_application"``.
        Falls back to ``"unknown"`` when nothing matched.
    entities : dict[str, str]
        Named slots extracted from the utterance.
        E.g. ``{"application": "chrome", "query": "machine learning"}``.
    confidence : float
        Combined score in [0.0, 1.0].  Higher = more certain.
    raw_text : str
        The original (pre-processed) text that was classified,
        preserved for debugging and evaluation.

    Examples
    --------
    >>> cmd = CommandIntent(
    ...     intent="search_web",
    ...     entities={"application": "chrome", "query": "ML"},
    ...     confidence=0.96,
    ...     raw_text="open chrome and search ML",
    ... )
    >>> cmd.to_dict()
    {'intent': 'search_web', 'entities': {'application': 'chrome', 'query': 'ML'}, 'confidence': 0.96, 'raw_text': 'open chrome and search ML'}
    """

    intent: str = "unknown"
    entities: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    raw_text: str = ""

    # ── Serialisation ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for JSON serialisation."""
        return {
            "intent": self.intent,
            "entities": dict(self.entities),   # defensive copy
            "confidence": round(self.confidence, 4),
            "raw_text": self.raw_text,
        }

    def __str__(self) -> str:
        """Human-readable summary for logging / CLI output."""
        ent_str = ", ".join(f"{k}={v!r}" for k, v in self.entities.items())
        return (
            f"[{self.intent}] "
            f"confidence={self.confidence:.2f}  "
            f"entities={{{ent_str}}}"
        )


# ──────────────────────────────────────────────────────────────────────
# 2. IntentPattern — one regex template that can match a single intent
# ──────────────────────────────────────────────────────────────────────

@dataclass
class IntentPattern:
    """A single pattern template associated with an intent.

    The ``template`` uses ``{slot_name}`` placeholders which are
    compiled into named regex capture groups at init time.

    Attributes
    ----------
    template : str
        Human-readable pattern, e.g. ``"open {application}"``.
    slots : list[str]
        Ordered list of slot names extracted from the template.
        Populated automatically during ``__post_init__``.
    regex : re.Pattern
        Compiled regex with named groups for each slot.
        Populated automatically during ``__post_init__``.

    Examples
    --------
    >>> p = IntentPattern(template="open {application}")
    >>> p.slots
    ['application']
    >>> bool(p.regex.search("open chrome"))
    True
    """

    template: str
    slots: list[str] = field(default_factory=list, init=False)
    regex: re.Pattern = field(default=None, init=False)  # type: ignore[assignment]

    # Regex that finds {slot_name} placeholders in the template
    _SLOT_RE: re.Pattern = field(
        default=re.compile(r"\{(\w+)\}"),
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        """Compile the template into a regex with named capture groups.

        Conversion logic:
            "open {application}"
                ↓
            "^open\\s+(?P<application>.+?)$"

        Steps:
        1. Extract slot names from {placeholders}.
        2. Escape the literal parts of the template for regex safety.
        3. Replace each {slot} with a named capture group ``(?P<name>.+?)``.
        4. Wrap with ``^...$`` anchors and compile case-insensitively.
        """
        # Step 1: Find all slot names
        self.slots = self._SLOT_RE.findall(self.template)

        # Step 2: Build the regex string
        # Split the template around the {slot} placeholders
        parts = self._SLOT_RE.split(self.template)
        # parts alternates: [literal, slot_name, literal, slot_name, ...]

        regex_parts: list[str] = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # Literal text — escape it, then replace whitespace with \s+
                escaped = re.escape(part.strip())
                # Allow flexible whitespace between words
                escaped = re.sub(r"\\ ", r"\\s+", escaped)
                regex_parts.append(escaped)
            else:
                # Slot name — insert a named capture group
                regex_parts.append(f"(?P<{part}>.+?)")

        # Step 3: Join, anchor, and compile
        pattern_str = r"\s+".join(p for p in regex_parts if p)
        self.regex = re.compile(f"^{pattern_str}$", re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────
# 3. IntentDefinition — all patterns + metadata for a single intent
# ──────────────────────────────────────────────────────────────────────

@dataclass
class IntentDefinition:
    """Complete definition for one intent in the command registry.

    Attributes
    ----------
    name : str
        Canonical intent identifier, e.g. ``"search_web"``.
    category : str
        Grouping label for organisation / reporting.
        E.g. ``"application"``, ``"web"``, ``"system"``, ``"file"``.
    description : str
        Human-readable explanation of what this intent does.
    patterns : list[IntentPattern]
        All regex patterns that can match this intent (English,
        Hindi, Hinglish variants).
    keywords : list[str]
        Words strongly associated with this intent, used for
        keyword-overlap scoring as a secondary signal.
    entity_schema : dict[str, str]
        Expected entities and their types, e.g.
        ``{"application": "str", "query": "str"}``.
        Used for validation and documentation.

    Examples
    --------
    >>> defn = IntentDefinition(
    ...     name="open_application",
    ...     category="application",
    ...     description="Open a desktop application",
    ...     patterns=[IntentPattern("open {application}")],
    ...     keywords=["open", "launch", "start"],
    ...     entity_schema={"application": "str"},
    ... )
    >>> defn.name
    'open_application'
    """

    name: str
    category: str
    description: str
    patterns: list[IntentPattern] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    entity_schema: dict[str, str] = field(default_factory=dict)

    def match(self, text: str) -> tuple[float, dict[str, str]] | None:
        """Try every pattern against *text* and return the best match.

        Parameters
        ----------
        text : str
            Pre-processed (lowercased, normalised) user utterance.

        Returns
        -------
        tuple[float, dict[str, str]] | None
            ``(coverage_score, extracted_entities)`` for the best
            matching pattern, or ``None`` if nothing matched.

            **coverage_score** = fraction of the input text consumed
            by the match (0.0–1.0).  Longer matches score higher.
        """
        best_score: float = 0.0
        best_entities: dict[str, str] = {}

        for pattern in self.patterns:
            m = pattern.regex.search(text)
            if m is None:
                continue

            # Coverage: how much of the input did the pattern consume?
            matched_len = m.end() - m.start()
            coverage = matched_len / max(len(text), 1)

            if coverage > best_score:
                best_score = coverage
                best_entities = {
                    k: v.strip()
                    for k, v in m.groupdict().items()
                    if v is not None
                }

        if best_score > 0.0:
            return best_score, best_entities
        return None

    def keyword_score(self, tokens: list[str]) -> float:
        """Compute keyword overlap between *tokens* and this intent's keywords.

        Uses Jaccard-like scoring:
            score = |matched_keywords| / |all_keywords|

        Returns 0.0 if the intent has no keywords defined.
        """
        if not self.keywords:
            return 0.0
        matched = sum(1 for kw in self.keywords if kw in tokens)
        return matched / len(self.keywords)
