"""
Tests for Command Registry
==========================

Ensures that the registry is correctly populated, patterns compile,
and the API functions work as expected.

Run:
    python -m agent.tests.test_command_registry
"""

import sys
from agent.command_registry import get_all_intents, get_intent, list_intent_names


def run_tests():
    print("=== Command Registry Tests ===")

    all_intents = get_all_intents()
    names = list_intent_names()

    # ── 1. Basic Registry Population ──
    print(f"Total intents loaded: {len(all_intents)}")
    assert len(all_intents) > 10, "Registry should have more than 10 intents."
    assert "unknown" in names, "Fallback 'unknown' intent must be present."
    print("[PASS] Registry loads correctly")

    # ── 2. Required Intents Exist ──
    required = [
        "open_application", "close_application", "open_terminal", "open_file_manager",
        "open_browser", "search_web", "open_website",
        "system_info", "check_time", "check_date", "check_memory", "check_disk", "ip_address", "uptime",
        "list_files", "take_screenshot", "unknown"
    ]
    missing = [req for req in required if req not in names]
    assert not missing, f"Missing required intents: {missing}"
    print("[PASS] All required intents exist")

    # ── 3. Lookup Works ──
    search_def = get_intent("search_web")
    assert search_def is not None, "Failed to retrieve 'search_web'"
    assert search_def.category == "browser"
    assert "search" in search_def.keywords
    assert get_intent("does_not_exist") is None, "Should return None for bad lookup"
    print("[PASS] Intent lookup API works")

    # ── 4. Patterns Compile & Entity Schemas Valid ──
    # Because IntentPattern compiles in __post_init__, if we got here,
    # it means they all compiled successfully. Let's do a sanity check on slots.
    for defn in all_intents:
        if defn.name == "unknown":
            continue
        
        # Verify schema
        for pattern in defn.patterns:
            # Check that every slot parsed by the regex is documented in the schema
            for slot in pattern.slots:
                assert slot in defn.entity_schema, (
                    f"Pattern '{pattern.template}' in '{defn.name}' has undocumented slot '{slot}'"
                )
    print("[PASS] Patterns compile and schemas align")

    # ── 5. Keyword Population ──
    for defn in all_intents:
        if defn.name == "unknown":
            continue
        assert len(defn.keywords) > 0, f"Intent '{defn.name}' has no keywords!"
    print("[PASS] Keywords exist for all active intents")

    print("\n>>> ALL TESTS PASSED!")


if __name__ == "__main__":
    try:
        run_tests()
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
