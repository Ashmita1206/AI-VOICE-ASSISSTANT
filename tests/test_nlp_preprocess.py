"""
Tests for TextPreprocessor
==========================

Tests the various normalisation steps (lowercasing, punctuation removal,
typos, Hinglish translation, and synonym normalisation).

Run:
    python -m agent.tests.test_preprocess
"""

import io
import os
import sys

# Force UTF-8 on Windows to handle special characters
if sys.platform == "win32" and not hasattr(sys.stdout, "_pytest_captured_and_tear_down") and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from agent.preprocess import normalize_text, tokenize


def run_tests():
    print("=== Text Preprocessor Tests ===")

    tests = [
        # ── 1. Basic cleaning ──
        {
            "name": "Lowercase & Punctuation",
            "input": "Open Chrome, and search Machine Learning!!!",
            "expected": "open chrome and search machine learning",
        },
        {
            "name": "Multiple Spaces",
            "input": "  open   chrome    and search   ",
            "expected": "open chrome and search",
        },
        {
            "name": "Empty / Whitespace",
            "input": "   , , ,   ",
            "expected": "",
        },

        # ── 2. Typos & Shorthand ──
        {
            "name": "Typo Correction (kro, pls)",
            "input": "pls search kro",
            "expected": "please search", # pls->please, kro->karo->"" (removed by hinglish words)
        },
        {
            "name": "Tech Typos",
            "input": "open brwser and take screnshot",
            "expected": "open browser and take screenshot",
        },

        # ── 3. Hinglish Phrases (multi-word) ──
        {
            "name": "Phrase: band karo",
            "input": "chrome band karo",
            "expected": "chrome close",
        },
        {
            "name": "Phrase: search kar do",
            "input": "google pe ML search kar do",
            "expected": "google on ml search",
        },
        {
            "name": "Phrase: longest match first",
            "input": "open kar do",
            "expected": "open",
        },

        # ── 4. Hinglish Words (single-word) & Helpers ──
        {
            "name": "Words: kholo",
            "input": "chrome kholo",
            "expected": "chrome open",
        },
        {
            "name": "Words: Connectors",
            "input": "chrome aur firefox kholo",
            "expected": "chrome and firefox open",
        },
        {
            "name": "Words: Grammatical Helpers (karo)",
            # "karo" translates to "", "search" remains.
            "input": "ML search karo",
            "expected": "ml search",
        },

        # ── 5. English Synonyms ──
        {
            "name": "Synonyms: launch / start",
            "input": "launch chrome or start firefox",
            "expected": "open chrome or open firefox",
        },
        {
            "name": "Synonyms: terminate",
            "input": "terminate process",
            "expected": "close process",
        },

        # ── 6. Complex Mixed Utterances ──
        {
            "name": "Mixed Hinglish + Typos",
            "input": "Chrome kholo aur ML search kro plz",
            "expected": "chrome open and ml search please",
        },
        {
            "name": "Google Search Hindi",
            "input": "Google pe machine learning search kro",
            "expected": "google on machine learning search",
        },
    ]

    passed = 0
    for i, tc in enumerate(tests, 1):
        actual = normalize_text(tc["input"])
        if actual == tc["expected"]:
            print(f"[PASS] {tc['name']}")
            passed += 1
        else:
            print(f"[FAIL] {tc['name']}")
            print(f"       Input    : {tc['input']!r}")
            print(f"       Expected : {tc['expected']!r}")
            print(f"       Actual   : {actual!r}")

    print("\n=== Tokenization ===")
    tokens = tokenize("Chrome kholo aur ML search kro plz")
    expected_tokens = ["chrome", "open", "and", "ml", "search", "please"]
    if tokens == expected_tokens:
        print("[PASS] Tokenization")
        passed += 1
    else:
        print("[FAIL] Tokenization")
        print(f"       Actual: {tokens}")

    total = len(tests) + 1
    print(f"\n>>> Results: {passed}/{total} passed.")
    if passed == total:
        print(">>> ALL TESTS PASSED!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
