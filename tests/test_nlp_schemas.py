"""
Quick smoke test for agent.schemas
===================================

Run:
    python -m agent.tests.test_schemas
"""

import io
import os
import sys

# Force UTF-8 on Windows to handle special characters
if sys.platform == "win32" and not hasattr(sys.stdout, "_pytest_captured_and_tear_down") and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from agent.schemas import CommandIntent, IntentPattern, IntentDefinition


def test_intent_pattern():
    """IntentPattern should compile templates and extract slots."""
    p = IntentPattern(template="open {application}")

    print("=== IntentPattern ===")
    print(f"  Template : {p.template}")
    print(f"  Slots    : {p.slots}")
    print(f"  Regex    : {p.regex.pattern}")

    # Should match "open chrome"
    m = p.regex.search("open chrome")
    assert m is not None, "Failed to match 'open chrome'"
    print(f"  Match 'open chrome' -> {m.groupdict()}")

    # Should match "open vs code"
    m2 = p.regex.search("open vs code")
    assert m2 is not None, "Failed to match 'open vs code'"
    print(f"  Match 'open vs code' -> {m2.groupdict()}")

    # Multi-slot pattern
    p2 = IntentPattern(template="search {query} on {application}")
    print(f"\n  Template : {p2.template}")
    print(f"  Slots    : {p2.slots}")
    m3 = p2.regex.search("search machine learning on chrome")
    assert m3 is not None, "Failed to match multi-slot"
    print(f"  Match -> {m3.groupdict()}")

    print("  [PASS] IntentPattern: ALL PASSED\n")


def test_command_intent():
    """CommandIntent should be immutable and serialisable."""
    print("=== CommandIntent ===")

    cmd = CommandIntent(
        intent="search_web",
        entities={"application": "chrome", "query": "machine learning"},
        confidence=0.96,
        raw_text="open chrome and search machine learning",
    )

    print(f"  str     : {cmd}")
    print(f"  to_dict : {cmd.to_dict()}")

    # Frozen -- should not allow mutation
    try:
        cmd.intent = "hacked"
        print("  [FAIL] mutation was allowed!")
    except AttributeError:
        print("  [PASS] Frozen: mutation correctly blocked")

    # Default values
    default = CommandIntent()
    assert default.intent == "unknown"
    assert default.confidence == 0.0
    print(f"  Default : {default}")
    print("  [PASS] CommandIntent: ALL PASSED\n")


def test_intent_definition():
    """IntentDefinition should match patterns and score keywords."""
    print("=== IntentDefinition ===")

    defn = IntentDefinition(
        name="open_application",
        category="application",
        description="Open a desktop application",
        patterns=[
            IntentPattern("open {application}"),
            IntentPattern("launch {application}"),
            IntentPattern("{application} open karo"),
        ],
        keywords=["open", "launch", "start", "run"],
        entity_schema={"application": "str"},
    )

    # Pattern match
    result = defn.match("open chrome")
    assert result is not None, "Failed to match 'open chrome'"
    score, entities = result
    print(f"  match('open chrome')       -> score={score:.2f}, entities={entities}")

    result2 = defn.match("chrome open karo")
    assert result2 is not None, "Failed to match Hinglish"
    score2, entities2 = result2
    print(f"  match('chrome open karo')  -> score={score2:.2f}, entities={entities2}")

    # No match
    result3 = defn.match("what is the weather")
    assert result3 is None, "Should not match unrelated text"
    print("  match('what is the weather') -> None [PASS]")

    # Keyword scoring
    ks = defn.keyword_score(["open", "chrome", "please"])
    print(f"  keyword_score(['open', 'chrome', 'please']) -> {ks:.2f}")
    assert ks == 0.25, f"Expected 0.25, got {ks}"  # 1 of 4 keywords

    print("  [PASS] IntentDefinition: ALL PASSED\n")


if __name__ == "__main__":
    test_intent_pattern()
    test_command_intent()
    test_intent_definition()
    print(">>> All schema tests passed!")
