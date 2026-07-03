"""
Agent Package — Phase 3: Command Understanding & Intent Detection
==================================================================

Converts transcribed text into structured intents with entities
and confidence scores.

Usage:
    from agent import IntentClassifier, CommandIntent

    classifier = IntentClassifier()
    result = classifier.classify("Open Chrome and search machine learning")
    # → CommandIntent(intent='search_web', entities={'application': 'chrome', 'query': 'machine learning'}, ...)
"""

from agent.schemas import CommandIntent, IntentPattern, IntentDefinition

__all__ = [
    "CommandIntent",
    "IntentPattern",
    "IntentDefinition",
]
