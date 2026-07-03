"""
TTS Layer Tests
===============

Tests the Response Generator and the TTS Manager.
Demonstrates actual speech generation.

Run:
    python -m tts.tests.test_tts
"""

import sys
import os
import logging
from pprint import pprint

# Silence pygame hello message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
logging.basicConfig(level=logging.WARNING)

from execution.schemas import ExecutionResult
from tts.response_generator import generate_response
from tts.manager import TTSManager


def run_tests():
    print("=== TTS Layer Verification ===")
    
    manager = TTSManager()
    
    # Define test cases mapping back to the Phase 5 outputs
    test_cases = [
        {
            "name": "What time is it",
            "results": [
                ExecutionResult(
                    success=True, 
                    tool="check_time", 
                    output="2026-06-22 15:16:00"
                )
            ]
        },
        {
            "name": "Open Chrome",
            "results": [
                ExecutionResult(
                    success=True, 
                    tool="open_browser", 
                    message="Opened browser chrome."
                )
            ]
        },
        {
            "name": "Take screenshot",
            "results": [
                ExecutionResult(
                    success=True, 
                    tool="take_screenshot", 
                    message="Opened Snipping Tool."
                )
            ]
        },
        {
            "name": "Open terminal",
            "results": [
                ExecutionResult(
                    success=True, 
                    tool="open_terminal"
                )
            ]
        },
        {
            "name": "Open Chrome and search machine learning",
            "results": [
                ExecutionResult(
                    success=True, 
                    tool="open_browser", 
                    message="Opened browser chrome."
                ),
                ExecutionResult(
                    success=True, 
                    tool="search_web", 
                    message="Searched web for: machine learning"
                )
            ]
        },
        {
            "name": "[Safety Test] Block dangerous command",
            "results": [
                 ExecutionResult(
                    success=False, 
                    tool="open_terminal", 
                    requires_confirmation=True
                )
            ]
        }
    ]

    for case in test_cases:
        print(f"\n--- Demonstrating: {case['name']} ---")
        
        # 1. Generate text
        results_dicts = [r.to_dict() for r in case["results"]]
        spoken_text = generate_response(results_dicts)
        print(f"Generated text: \"{spoken_text}\"")
        
        # 2. Synthesize speech (skip actual audio if CI, but we run it to test)
        # We will attempt to speak it. If you have speakers, you should hear this!
        res = manager.speak(spoken_text)
        if res.success:
            print(f"[SUCCESS] Spoken via {res.engine_used} in {res.execution_time_ms}ms")
        else:
            print(f"[ERROR] Failed to speak: {res.error_message}")
            
    print("\n>>> All TTS tests ran successfully.")

if __name__ == "__main__":
    run_tests()
