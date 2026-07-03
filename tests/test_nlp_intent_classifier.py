"""
Tests for Intent Classifier
===========================

Verifies confidence calculation, intent ranking, and basic classification.

Run:
    python -m agent.tests.test_intent_classifier
"""

import sys
from agent.intent_classifier import IntentClassifier

def run_tests():
    print("=== Intent Classifier Tests ===")
    
    classifier = IntentClassifier()
    passed = 0
    tests = 0

    def assert_eq(actual, expected, name):
        nonlocal passed, tests
        tests += 1
        if actual == expected:
            print(f"[PASS] {name}")
            passed += 1
        else:
            print(f"[FAIL] {name}")
            print(f"       Expected: {expected}")
            print(f"       Actual:   {actual}")

    # 1. Exact pattern match bonus
    res = classifier.classify("open browser")
    assert_eq(res.intent, "open_browser", "Exact match no-entity intent")
    assert res.confidence >= 0.90, f"Confidence too low: {res.confidence}"

    # 2. Entity pattern match
    res = classifier.classify("open chrome")
    assert_eq(res.intent, "open_application", "Entity match intent")
    assert_eq(res.entities.get("application"), "chrome", "Entity extracted")

    # 3. Partial keyword match fallback
    res = classifier.classify("time tell me please")
    assert_eq(res.intent, "check_time", "Keyword fallback")

    # 4. Unknown intent
    res = classifier.classify("battery kitni hai")
    assert_eq(res.intent, "unknown", "Unknown intent classification")

    # 5. Play music intent
    res = classifier.classify("play Believer on Spotify")
    assert_eq(res.intent, "play_music", "Spotify play_music intent classification")
    assert_eq(res.entities.get("application"), "spotify", "Spotify app entity extracted")
    assert_eq(res.entities.get("query"), "believer", "Song query entity extracted")

    # 6. Send message intent
    res = classifier.classify("message Rahul saying how are you")
    assert_eq(res.intent, "send_message", "WhatsApp send_message intent classification")
    assert_eq(res.entities.get("contact"), "rahul", "Contact entity extracted")
    assert_eq(res.entities.get("message"), "how are you", "Message entity extracted")

    print(f"\n>>> Results: {passed}/{tests} passed.")
    if passed != tests:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
