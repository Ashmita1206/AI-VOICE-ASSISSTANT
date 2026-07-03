"""
Tests for Entity Extractor
==========================

Verifies alias resolution, regex-based extraction, rule-based fallback,
and context-aware reclassification.

Run:
    python -m agent.tests.test_entity_extractor
"""

import sys
from agent.entity_extractor import EntityExtractor

def run_tests():
    print("=== Entity Extractor Tests ===")
    
    extractor = EntityExtractor()
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

    # 1. Basic Alias Resolution
    assert_eq(extractor.normalize_application("google chrome"), "chrome", "App alias: google chrome -> chrome")
    assert_eq(extractor.normalize_application("visual studio code"), "vscode", "App alias: visual studio code -> vscode")
    assert_eq(extractor.normalize_website("google"), "https://google.com", "Web alias: google -> url")
    
    # 2. Regex Extraction
    entities = extractor.extract_entities(
        text="open google chrome",
        intent_name="open_application",
        regex_entities={"application": "google chrome"}
    )
    assert_eq(entities, {"application": "chrome"}, "Regex extraction: app normalization")

    # 3. Context-aware Reclassification
    entities = extractor.extract_entities(
        text="open github",
        intent_name="open_application", 
        regex_entities={"application": "github"}
    )
    # github is a known website, NOT an app, so it should reclassify to website
    assert_eq(entities, {"website": "https://github.com"}, "Reclassification: app -> website (unambiguous)")
    
    # 4. Web intent context bias
    # Let's say "chrome" could theoretically be a website in some weird universe, 
    # but "youtube" is definitely a website.
    entities = extractor.extract_entities(
        text="youtube pe music search karo", # norm: youtube on music search
        intent_name="search_web",
        regex_entities={"application": "youtube", "query": "music"}
    )
    assert_eq(entities, {"website": "https://youtube.com", "query": "music"}, "Reclassification: app -> website (web context)")

    # 5. Rule-based fallback
    entities = extractor.extract_entities(
        text="open visual studio code",
        intent_name="open_application",
        regex_entities=None # simulated failure to capture via regex
    )
    assert_eq(entities, {"application": "vscode"}, "Fallback: scan for known app")

    print(f"\n>>> Results: {passed}/{tests} passed.")
    if passed != tests:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
