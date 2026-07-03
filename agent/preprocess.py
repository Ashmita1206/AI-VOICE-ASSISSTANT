"""
Text Preprocessor for Intent Classification
=============================================

Normalises raw transcribed text before it enters the intent
classification pipeline.

Pipeline (in order)
-------------------
1. Lowercase
2. Strip punctuation  (keeps alphanumerics, underscores, whitespace)
3. Normalise whitespace
4. Fix common typos           ("kro" → "karo", "pls" → "please")
5. Replace Hinglish phrases   ("band karo" → "close")  — multi-word, longest-first
6. Replace Hinglish words     ("kholo" → "open")        — single-word
7. Replace English synonyms   ("launch" → "open")       — single-word
8. Final whitespace cleanup

Design decisions
----------------
* **Table-driven** — every normalisation step is powered by a lookup
  dict, not by if-else chains.  Adding new vocabulary = adding a dict
  entry, zero logic changes.
* **Phrase-before-word** — multi-word Hinglish phrases (e.g. "band karo")
  are replaced first, longest-first, so they aren't broken up by
  single-word replacements.
* **No word-order rewriting** — the preprocessor normalises vocabulary
  only.  "Chrome kholo" becomes "chrome open", not "open chrome".
  The intent classifier handles both word orders via its pattern set.
* **Class + module-level API** — ``TextPreprocessor`` is configurable
  (custom tables for testing / extension).  ``normalize_text()`` and
  ``tokenize()`` are convenience wrappers around a default instance.

Usage
-----
    from agent.preprocess import normalize_text, tokenize

    normalize_text("Chrome kholo aur ML search karo")
    # → "chrome open and ml search"

    tokenize("open chrome and search machine learning")
    # → ["open", "chrome", "and", "search", "machine", "learning"]
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# LOOKUP TABLES
# ══════════════════════════════════════════════════════════════════════
#
# To add support for a new typo / Hindi word / synonym, just add an
# entry to the appropriate dict below.  No other code changes needed.
# ══════════════════════════════════════════════════════════════════════


# ── 1. Typo corrections ─────────────────────────────────────────────
# Common misspellings and shorthand found in voice transcriptions.
# Applied BEFORE Hinglish translation so the corrected forms can be
# picked up by the phrase / word tables downstream.
#
# Key = typo (lowercase),  Value = corrected form.

TYPO_MAP: dict[str, str] = {
    # ── Hindi phonetic shorthand ──
    "kro":   "karo",
    "kre":   "karo",
    "krna":  "karna",
    "krke":  "karke",
    "btao":  "batao",
    "bta":   "bata",
    "dkho":  "dekho",
    "dkhao": "dikhao",
    "chlao": "chalao",
    "chla":  "chala",
    "bnao":  "banao",
    "bnd":   "band",

    # ── English shorthand / SMS-speak ──
    "pls":   "please",
    "plz":   "please",
    "u":     "you",
    "ur":    "your",
    "bcoz":  "because",
    "msg":   "message",
    "yt":    "youtube",
    "fb":    "facebook",
    "ggl":   "google",
    "hw":    "how",
    "wht":   "what",
    "abt":   "about",

    # ── Tech-word typos ──
    "brwser":    "browser",
    "brawser":   "browser",
    "screnshot": "screenshot",
    "scrnsht":   "screenshot",
    "termnl":    "terminal",
    "systm":     "system",
}


# ── 2. Hinglish phrases (multi-word → English) ──────────────────────
# Processed BEFORE single-word replacements, longest-first, to avoid
# partial matches.  E.g. "band karo" must map to "close" as a unit,
# not "close" + leftover tokens.

HINGLISH_PHRASES: dict[str, str] = {
    # ── Open variants ──
    "open kar do":   "open",
    "open karo":     "open",
    "khol do":       "open",
    "khol de":       "open",

    # ── Close variants ──
    "band kar do":   "close",
    "band karo":     "close",
    "band karna":    "close",

    # ── Search variants ──
    "search kar do": "search",
    "search karo":   "search",
    "search karna":  "search",

    # ── Tell / show variants ──
    "bata do":       "tell",
    "bata de":       "tell",
    "dikha do":      "show",
    "dikha de":      "show",

    # ── Start / run variants ──
    "chalu kar do":  "start",
    "chalu karo":    "start",
    "chala do":      "run",

    # ── Check variants ──
    "check kar do":  "check",
    "check karo":    "check",
    "dekh lo":       "check",

    # ── Create variants ──
    "bana do":       "create",
    "bana de":       "create",
}


# ── 3. Hinglish single-word table ───────────────────────────────────
# Applied AFTER phrase replacement.  Standalone Hindi verb helpers
# ("karo", "kar", "karna") that survived phrase matching are mapped
# to empty strings (effectively removed).

HINGLISH_WORDS: dict[str, str] = {
    # ── Action verbs ──
    "kholo":   "open",
    "kholna":  "open",
    "khol":    "open",
    "band":    "close",
    "batao":   "tell",
    "bolo":    "tell",
    "dikhao":  "show",
    "chalao":  "run",
    "dekho":   "check",
    "banao":   "create",
    "likho":   "write",
    "bhejo":   "send",
    "sunao":   "play",
    "hatao":   "remove",
    "nikalo":  "remove",
    "dalo":    "put",
    "rakho":   "keep",
    "chalu":   "start",

    # ── Connectors / prepositions ──
    "aur":  "and",
    "ya":   "or",
    "pe":   "on",
    "par":  "on",
    "mein": "in",
    "se":   "from",
    "ko":   "to",
    "ka":   "of",
    "ki":   "of",
    "ke":   "of",
    "hai":  "is",
    "hain": "are",

    # ── Question words ──
    "kya":   "what",
    "kitni": "how much",
    "kitna": "how much",
    "kab":   "when",
    "kahan": "where",
    "kaun":  "who",
    "kaise": "how",

    # ── Modifiers ──
    "abhi":  "now",
    "samay": "time",
    "waqt":  "time",
    "naya":  "new",
    "nayi":  "new",
    "naam":  "named",

    # ── Pronouns ──
    "mera": "my",
    "meri": "my",
    "tera": "your",
    "teri": "your",

    # ── Verb helpers (remove after phrase processing) ──
    # These are Hindi grammatical particles that carry no
    # standalone meaning after phrase-level patterns have
    # been applied.
    "karo":  "",
    "kar":   "",
    "karna": "",
    "karke": "",

    # ── Politeness ──
    "zara":   "please",
    "kripya": "please",
}


# ── 4. English synonym normalisation ────────────────────────────────
# Maps English synonyms to a canonical verb so the intent classifier
# needs fewer patterns.

SYNONYM_MAP: dict[str, str] = {
    # → open
    "launch":  "open",
    "start":   "open",
    "execute": "open",

    # → close
    "terminate": "close",
    "quit":      "close",
    "exit":      "close",
    "kill":      "close",

    # → search
    "find":   "search",
    "lookup": "search",

    # → restart
    "reboot": "restart",
}


# ── Punctuation regex ────────────────────────────────────────────────
# Removes everything that is NOT a word character (\w = [a-zA-Z0-9_])
# or whitespace.  This strips commas, periods, question marks, etc.
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


# ══════════════════════════════════════════════════════════════════════
# TextPreprocessor
# ══════════════════════════════════════════════════════════════════════

class TextPreprocessor:
    """Configurable text preprocessing pipeline.

    Each normalisation step is driven by a lookup table that can be
    overridden at construction time for testing or domain tuning.

    Parameters
    ----------
    typo_map : dict, optional
        Custom typo correction table.
    hinglish_phrases : dict, optional
        Custom multi-word Hinglish→English phrase table.
    hinglish_words : dict, optional
        Custom single-word Hinglish→English table.
    synonym_map : dict, optional
        Custom English synonym normalisation table.
    """

    def __init__(
        self,
        *,
        typo_map: dict[str, str] | None = None,
        hinglish_phrases: dict[str, str] | None = None,
        hinglish_words: dict[str, str] | None = None,
        synonym_map: dict[str, str] | None = None,
    ) -> None:
        self._typo_map = typo_map if typo_map is not None else TYPO_MAP
        self._hinglish_words = (
            hinglish_words if hinglish_words is not None else HINGLISH_WORDS
        )
        self._synonym_map = (
            synonym_map if synonym_map is not None else SYNONYM_MAP
        )

        # Pre-compile Hinglish phrases into regexes, longest first.
        raw_phrases = (
            hinglish_phrases if hinglish_phrases is not None else HINGLISH_PHRASES
        )
        self._phrase_patterns = self._compile_phrases(raw_phrases)

        logger.debug(
            "TextPreprocessor ready — %d typos, %d phrases, "
            "%d words, %d synonyms",
            len(self._typo_map),
            len(self._phrase_patterns),
            len(self._hinglish_words),
            len(self._synonym_map),
        )

    # ── Public API ───────────────────────────────────────────────────

    def normalize(self, text: str) -> str:
        """Run the full preprocessing pipeline on *text*.

        Parameters
        ----------
        text : str
            Raw transcribed text (may contain mixed-case, punctuation,
            Hinglish vocabulary, typos, extra whitespace, etc.).

        Returns
        -------
        str
            Cleaned, lowercased, vocabulary-normalised text ready for
            the intent classifier.  Returns ``""`` for blank input.
        """
        if not text or not text.strip():
            return ""

        # 1. Lowercase
        result = text.lower()

        # 2. Strip punctuation (keeps word chars + whitespace)
        result = _PUNCT_RE.sub("", result)

        # 3. Normalise whitespace
        result = self._normalize_whitespace(result)

        # 4. Fix typos (word-level)
        result = self._replace_tokens(result, self._typo_map)

        # 5. Replace Hinglish phrases (multi-word, longest first)
        result = self._replace_phrases(result)

        # 6. Replace Hinglish words (single-word)
        result = self._replace_tokens(result, self._hinglish_words)

        # 7. Replace English synonyms (single-word)
        result = self._replace_tokens(result, self._synonym_map)

        # 8. Final whitespace cleanup
        result = self._normalize_whitespace(result)

        logger.debug("preprocess: %r -> %r", text, result)
        return result

    def tokenize(self, text: str) -> list[str]:
        """Normalise *text* and split into a list of tokens.

        Parameters
        ----------
        text : str
            Raw or pre-normalised text.

        Returns
        -------
        list[str]
            Whitespace-split token list.  Empty list for blank input.
        """
        normalised = self.normalize(text)
        return normalised.split() if normalised else []

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _compile_phrases(
        phrases: dict[str, str],
    ) -> list[tuple[re.Pattern, str]]:
        """Compile phrase table into regexes sorted longest-first.

        Longest-first ordering is critical: it ensures that
        ``"open kar do"`` (3 words) is tried before ``"open karo"``
        (2 words), preventing partial matches.

        Each phrase is wrapped in ``\\b`` word-boundary anchors so it
        only matches complete words (e.g. ``"band"`` inside
        ``"husband"`` is not matched).
        """
        sorted_items = sorted(
            phrases.items(),
            key=lambda kv: len(kv[0]),
            reverse=True,
        )
        compiled: list[tuple[re.Pattern, str]] = []
        for phrase, replacement in sorted_items:
            pattern = re.compile(
                r"\b" + re.escape(phrase) + r"\b",
                re.IGNORECASE,
            )
            compiled.append((pattern, replacement))
        return compiled

    def _replace_phrases(self, text: str) -> str:
        """Apply all compiled phrase patterns to *text*."""
        for pattern, replacement in self._phrase_patterns:
            text = pattern.sub(replacement, text)
        return text

    @staticmethod
    def _replace_tokens(text: str, token_map: dict[str, str]) -> str:
        """Replace individual tokens using *token_map*.

        Splits on whitespace, looks up each token in the map, and
        re-joins.  Handles three cases:

        * **Not in map** → keep the original token.
        * **Mapped to non-empty string** → replace (supports multi-word
          replacements like ``"kitni"`` → ``"how much"``).
        * **Mapped to ``""``** → remove the token entirely.
        """
        tokens = text.split()
        result: list[str] = []
        for token in tokens:
            replacement = token_map.get(token)
            if replacement is None:
                # Not in map — keep original
                result.append(token)
            elif replacement:
                # Mapped to a non-empty value (may be multi-word)
                result.extend(replacement.split())
            # else: mapped to "" → skip (remove the token)
        return " ".join(result)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Collapse runs of whitespace into single spaces and strip."""
        return re.sub(r"\s+", " ", text).strip()


# ══════════════════════════════════════════════════════════════════════
# Module-level convenience API
# ══════════════════════════════════════════════════════════════════════

_default_preprocessor = TextPreprocessor()


def normalize_text(text: str) -> str:
    """Normalise raw transcribed text (module-level shortcut).

    See :meth:`TextPreprocessor.normalize` for full documentation.
    """
    return _default_preprocessor.normalize(text)


def tokenize(text: str) -> list[str]:
    """Normalise and tokenise raw text (module-level shortcut).

    See :meth:`TextPreprocessor.tokenize` for full documentation.
    """
    return _default_preprocessor.tokenize(text)
