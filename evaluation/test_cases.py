"""
Test Case Registry
===================

Defines the ``TestCase`` data structure and provides a registry
of test cases for accuracy evaluation.

Test cases can be:
1. Registered in code (built-in examples)
2. Loaded from a JSON file (custom user data)
3. Created programmatically

JSON file format::

    [
        {
            "audio_path": "path/to/audio.wav",
            "reference_text": "the exact transcript",
            "language": "en",
            "category": "english_clean"
        }
    ]
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Any

import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Supported categories
# ──────────────────────────────────────────────────────────────────────

CATEGORIES = {
    "english_clean": "Clear English speech — no background noise",
    "hindi":         "Hindi language speech",
    "hinglish":      "Mixed Hindi-English (code-switching)",
    "noisy":         "Speech with background noise",
}


# ──────────────────────────────────────────────────────────────────────
# TestCase dataclass
# ──────────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    """A single evaluation test case.

    Attributes
    ----------
    audio_path : str
        Path to the audio file (WAV/MP3/FLAC/OGG).
    reference_text : str
        The ground-truth transcript for this audio.
    language : str
        ISO 639-1 language code (e.g. "en", "hi").
    category : str
        One of the CATEGORIES keys (e.g. "english_clean", "noisy").
    description : str
        Optional human-readable description of this test case.
    """

    audio_path: str
    reference_text: str
    language: str = "en"
    category: str = "english_clean"
    description: str = ""

    def __post_init__(self) -> None:
        """Resolve relative audio paths against the project root."""
        if not os.path.isabs(self.audio_path):
            self.audio_path = os.path.join(config.BASE_DIR, self.audio_path)

    def exists(self) -> bool:
        """Check if the audio file actually exists on disk."""
        return os.path.isfile(self.audio_path)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Test case registry
# ──────────────────────────────────────────────────────────────────────

class TestCaseRegistry:
    """Central registry that holds all test cases for evaluation.

    Usage::

        registry = TestCaseRegistry()
        registry.add(TestCase("audio.wav", "hello world", "en", "english_clean"))
        registry.load_from_json("my_tests.json")

        for tc in registry.get_by_category("english_clean"):
            print(tc.audio_path)
    """

    def __init__(self) -> None:
        self._cases: list[TestCase] = []

    def add(self, test_case: TestCase) -> None:
        """Add a single test case to the registry."""
        self._cases.append(test_case)

    def add_many(self, cases: list[TestCase]) -> None:
        """Add multiple test cases."""
        self._cases.extend(cases)

    def load_from_json(self, json_path: str) -> int:
        """Load test cases from a JSON file.

        Parameters
        ----------
        json_path : str
            Path to a JSON file containing a list of test case dicts.

        Returns
        -------
        int
            Number of test cases loaded.
        """
        if not os.path.isfile(json_path):
            logger.warning("Test cases file not found: %s", json_path)
            return 0

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        for item in data:
            try:
                tc = TestCase(
                    audio_path=item["audio_path"],
                    reference_text=item["reference_text"],
                    language=item.get("language", "en"),
                    category=item.get("category", "english_clean"),
                    description=item.get("description", ""),
                )
                self._cases.append(tc)
                count += 1
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping invalid test case entry: %s — %s", item, exc)

        logger.info("Loaded %d test cases from %s", count, json_path)
        return count

    def save_to_json(self, json_path: str) -> None:
        """Save all test cases to a JSON file."""
        data = []
        for tc in self._cases:
            # Store paths relative to BASE_DIR for portability
            rel_path = os.path.relpath(tc.audio_path, config.BASE_DIR)
            entry = tc.to_dict()
            entry["audio_path"] = rel_path
            data.append(entry)

        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d test cases to %s", len(data), json_path)

    def get_all(self) -> list[TestCase]:
        """Return all registered test cases."""
        return list(self._cases)

    def get_by_category(self, category: str) -> list[TestCase]:
        """Return test cases filtered by category."""
        return [tc for tc in self._cases if tc.category == category]

    def get_by_language(self, language: str) -> list[TestCase]:
        """Return test cases filtered by language code."""
        return [tc for tc in self._cases if tc.language == language]

    def get_valid(self) -> list[TestCase]:
        """Return only test cases whose audio files exist on disk."""
        valid = [tc for tc in self._cases if tc.exists()]
        skipped = len(self._cases) - len(valid)
        if skipped:
            logger.warning(
                "%d test case(s) skipped — audio files not found.", skipped
            )
        return valid

    @property
    def categories(self) -> list[str]:
        """Return unique categories present in the registry."""
        return sorted(set(tc.category for tc in self._cases))

    def __len__(self) -> int:
        return len(self._cases)

    def __repr__(self) -> str:
        return f"TestCaseRegistry({len(self._cases)} cases)"
