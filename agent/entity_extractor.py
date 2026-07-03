"""
Entity Extractor
================

Extracts and normalises entity values from classified utterances.

The extractor operates in three stages:

1. **Regex entities** — Named capture groups from the winning
   IntentPattern are the primary source of entity values.
2. **Alias resolution** — Raw values like ``"google chrome"`` are
   mapped to canonical forms (``"chrome"``), and website names
   are mapped to full URLs.
3. **Rule-based fallback** — If expected entities are missing,
   scans the text for known application / website names.

The extractor also handles **cross-entity reclassification**:
when a value captured as ``"application"`` is actually a known
website (e.g. ``"youtube"``), it is reclassified to the
``"website"`` entity with its normalised URL.

Usage
-----
    from agent.entity_extractor import EntityExtractor

    extractor = EntityExtractor()
    entities = extractor.extract_entities(
        text="open google chrome",
        intent_name="open_application",
        regex_entities={"application": "google chrome"},
    )
    # -> {"application": "chrome"}
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# ALIAS TABLES
# ══════════════════════════════════════════════════════════════════════
# Canonical names are included as self-mappings so that
# ``is_known_application("chrome")`` returns True.

APPLICATION_ALIASES: dict[str, str] = {
    # Chrome
    "chrome":             "chrome",
    "google chrome":      "chrome",
    "chrome browser":     "chrome",
    "browser":            "chrome",
    # Firefox
    "firefox":            "firefox",
    "mozilla firefox":    "firefox",
    "fire fox":           "firefox",
    # VS Code
    "vscode":             "vscode",
    "visual studio code": "vscode",
    "vs code":            "vscode",
    "visual studio":      "vscode",
    # Terminal
    "gnome-terminal":     "gnome-terminal",
    "terminal":           "gnome-terminal",
    "cmd":                "terminal",
    "command prompt":     "terminal",
    "powershell":         "powershell",
    # File manager
    "nautilus":           "nautilus",
    "file manager":       "nautilus",
    "explorer":           "nautilus",
    "files":              "nautilus",
    # Others
    "calculator":         "calculator",
    "notepad":            "notepad",
    "gedit":              "gedit",
    "text editor":        "gedit",
}

WEBSITE_ALIASES: dict[str, str] = {
    "google":         "https://google.com",
    "youtube":        "https://youtube.com",
    "github":         "https://github.com",
    "gmail":          "https://gmail.com",
    "chatgpt":        "https://chat.openai.com",
    "reddit":         "https://reddit.com",
    "twitter":        "https://twitter.com",
    "facebook":       "https://facebook.com",
    "linkedin":       "https://linkedin.com",
    "stackoverflow":  "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
}

# Intents where an "application" entity that resolves to a website
# should be reclassified as a "website" entity.
_WEB_INTENTS = frozenset({"search_web", "open_website"})


# ══════════════════════════════════════════════════════════════════════
# EntityExtractor
# ══════════════════════════════════════════════════════════════════════

class EntityExtractor:
    """Extracts and normalises entities from classified text.

    Parameters
    ----------
    application_aliases : dict, optional
        Custom application alias table.
    website_aliases : dict, optional
        Custom website alias table.
    """

    def __init__(
        self,
        *,
        application_aliases: dict[str, str] | None = None,
        website_aliases: dict[str, str] | None = None,
    ) -> None:
        self._app_aliases = (
            application_aliases
            if application_aliases is not None
            else APPLICATION_ALIASES
        )
        self._web_aliases = (
            website_aliases
            if website_aliases is not None
            else WEBSITE_ALIASES
        )

    # ── Public API ───────────────────────────────────────────────────

    def extract_entities(
        self,
        text: str,
        intent_name: str,
        regex_entities: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Extract, normalise, and resolve entities.

        Priority:
            1. Regex-captured entities (from pattern match)
            2. Alias resolution (normalise values)
            3. Rule-based fallback (scan text for known names)
            4. Empty dict

        Parameters
        ----------
        text : str
            Normalised (preprocessed) utterance text.
        intent_name : str
            The classified intent name (used for context-aware
            normalisation, e.g. web intents).
        regex_entities : dict, optional
            Entities captured by the winning regex pattern.

        Returns
        -------
        dict[str, str]
            Clean, normalised entity dict.
        """
        entities: dict[str, str] = {}

        # 1. Start with regex-captured entities
        if regex_entities:
            entities = {
                k: v.strip()
                for k, v in regex_entities.items()
                if v and v.strip()
            }

        # 2. Normalise values and reclassify where needed
        entities = self._normalize_entities(entities, intent_name)

        # 3. Rule-based fallback when regex captured nothing
        if not entities:
            entities = self._fallback_extraction(text, intent_name)

        logger.debug(
            "extract_entities: intent=%s, regex=%s -> %s",
            intent_name,
            regex_entities,
            entities,
        )
        return entities

    def normalize_application(self, value: str) -> str:
        """Map an application name to its canonical form.

        Returns the alias if found, otherwise the input
        lowercased and stripped.
        """
        clean = value.lower().strip()
        return self._app_aliases.get(clean, clean)

    def normalize_website(self, value: str) -> str:
        """Map a website name to its canonical URL.

        Returns the alias URL if found, otherwise the input
        lowercased and stripped.
        """
        clean = value.lower().strip()
        return self._web_aliases.get(clean, clean)

    def is_known_website(self, value: str) -> bool:
        """Check if *value* is a recognised website alias."""
        return value.lower().strip() in self._web_aliases

    def is_known_application(self, value: str) -> bool:
        """Check if *value* is a recognised application alias."""
        return value.lower().strip() in self._app_aliases

    def resolve_alias(self, value: str) -> tuple[str, str | None]:
        """Resolve *value* against all alias tables.

        Returns
        -------
        tuple[str, str | None]
            ``(canonical_value, entity_type)`` where *entity_type*
            is ``"website"``, ``"application"``, or ``None``.
            Website aliases are checked first (higher priority).
        """
        clean = value.lower().strip()
        if clean in self._web_aliases:
            return self._web_aliases[clean], "website"
        if clean in self._app_aliases:
            return self._app_aliases[clean], "application"
        return clean, None

    # ── Private helpers ──────────────────────────────────────────────

    def _normalize_entities(
        self,
        entities: dict[str, str],
        intent_name: str,
    ) -> dict[str, str]:
        """Normalise entity values and reclassify if needed.

        Reclassification rules:
        * In web intents (``search_web``, ``open_website``), an
          ``"application"`` that is a known website becomes a
          ``"website"`` entity.
        * Outside web intents, an ``"application"`` that is ONLY a
          known website (and NOT a known application) is also
          reclassified.
        """
        result: dict[str, str] = {}

        for key, value in entities.items():
            if key == "application":
                is_web = self.is_known_website(value)
                is_app = self.is_known_application(value)

                if intent_name in _WEB_INTENTS and is_web:
                    # Web context: prefer website classification
                    result["website"] = self.normalize_website(value)
                elif is_web and not is_app:
                    # Unambiguously a website, not an application
                    result["website"] = self.normalize_website(value)
                else:
                    result["application"] = self.normalize_application(value)

            elif key == "website":
                result["website"] = self.normalize_website(value)

            elif key == "query":
                result["query"] = value.strip()

            elif key == "directory":
                result["directory"] = value.strip()

            elif key == "filename":
                result["filename"] = value.strip()

            else:
                # Pass through unknown entity types unchanged
                result[key] = value.strip()

        return result

    def _fallback_extraction(
        self,
        text: str,
        intent_name: str,
    ) -> dict[str, str]:
        """Scan text for known entity values when regex captured nothing.

        Tries multi-word aliases first (longest-first) to prevent
        partial matches.
        """
        entities: dict[str, str] = {}
        text_lower = text.lower()

        # Check for known websites in web-related intents
        if intent_name in _WEB_INTENTS:
            for name, url in sorted(
                self._web_aliases.items(),
                key=lambda kv: len(kv[0]),
                reverse=True,
            ):
                if name in text_lower:
                    entities["website"] = url
                    break

        # Check for known applications in app-related intents
        if intent_name in ("open_application", "close_application"):
            for name, canonical in sorted(
                self._app_aliases.items(),
                key=lambda kv: len(kv[0]),
                reverse=True,
            ):
                if name in text_lower:
                    entities["application"] = canonical
                    break

        return entities
