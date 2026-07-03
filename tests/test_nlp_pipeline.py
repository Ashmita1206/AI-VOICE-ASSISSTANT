"""
End-to-End Pipeline Tests
=========================

Tests the full pipeline from raw text -> preprocessing -> classification -> extraction.

Run:
    python -m agent.tests.test_pipeline
"""

import sys
from agent.intent_classifier import IntentClassifier

def run_tests():
    print("=== End-to-End Pipeline Tests ===")
    
    classifier = IntentClassifier()
    
    test_cases = [
        (
            "open chrome", 
            "open_application", 
            {"application": "chrome"}
        ),
        (
            "launch firefox", 
            "open_application", 
            {"application": "firefox"}
        ),
        (
            "chrome kholo", 
            "open_application", 
            {"application": "chrome"}
        ),
        (
            "google pe machine learning search karo", 
            "search_web", 
            {"website": "https://google.com", "query": "machine learning"}
        ),
        (
            "what time is it", 
            "check_time", 
            {}
        ),
        (
            "take screenshot", 
            "take_screenshot", 
            {}
        ),
        (
            "open file manager", 
            "open_file_manager", 
            {}
        ),
        (
            "check memory", 
            "check_memory", 
            {}
        ),
        (
            "list files", 
            "list_files", 
            {}
        ),
        (
            "battery kitni hai", 
            "unknown", 
            {}
        ),
        (
            "Chrome kholo aur machine learning search karo", 
            "search_web", 
            {"application": "chrome", "query": "machine learning"}
        )
    ]

    passed = 0
    for text, exp_intent, exp_entities in test_cases:
        res = classifier.classify(text)
        
        ok = True
        if res.intent != exp_intent:
            print(f"[FAIL] {text!r}")
            print(f"       Intent mismatch. Expected {exp_intent}, got {res.intent}")
            ok = False
        elif res.entities != exp_entities:
            print(f"[FAIL] {text!r}")
            print(f"       Entity mismatch. Expected {exp_entities}, got {res.entities}")
            ok = False
            
        if ok:
            print(f"[PASS] {text!r} -> {res.intent} {res.entities}")
            passed += 1

    print(f"\n>>> Results: {passed}/{len(test_cases)} passed.")
    if passed != len(test_cases):
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
