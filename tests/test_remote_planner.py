"""
Tests for Remote Planner & Fallback Heuristics
==============================================
"""

import pytest
import responses
import requests

from agentic.llm.manager import get_planner_manager
from agentic.llm.fallback import apply_heuristic_fallback
import config

# Provide a dummy URL for testing
config.COLAB_API_URL = "https://mock.ngrok-free.dev/plan"

@responses.activate
def test_colab_online():
    """Test successful 200 OK from Colab."""
    mock_json = {
        "response": '{"intent": "check_time", "confidence": 0.99, "steps": [{"tool": "check_time", "args": {}}]}'
    }
    
    responses.add(
        responses.POST,
        config.COLAB_API_URL,
        json=mock_json,
        status=200
    )
    
    manager = get_planner_manager()
    # Clear cache
    manager._cache.clear()
    
    plan = manager.plan("What time is it?")
    assert plan.intent == "check_time"
    assert len(responses.calls) == 1

@responses.activate
def test_colab_timeout_triggers_fallback():
    """Test that a timeout triggers exponential backoff and finally the fallback."""
    responses.add(
        responses.POST,
        config.COLAB_API_URL,
        body=requests.exceptions.Timeout("Connection timed out"),
    )
    
    manager = get_planner_manager()
    manager._cache.clear()
    
    # We will test the fallback with a string that DOES NOT match heuristics
    # to ensure it returns the standard offline fallback
    plan = manager.plan("hello world")
    assert plan.intent == "open_resource"
    assert "offline" in plan.reasoning.lower() or "not reach" in plan.reasoning.lower() or "could not parse" in plan.reasoning.lower()
    
    # It should have retried (1 initial + 3 retries = 4 requests)
    assert len(responses.calls) == 4

@responses.activate
def test_ngrok_expired_triggers_fallback():
    """Test that a 404 or 502 from ngrok triggers fallback."""
    responses.add(
        responses.POST,
        config.COLAB_API_URL,
        status=502
    )
    
    manager = get_planner_manager()
    manager._cache.clear()
    
    plan = manager.plan("hello world")
    assert plan.intent == "open_resource"
    assert len(responses.calls) == 4

def test_fallback_heuristic_open_browser_search():
    """Test the specific multi-word search heuristic."""
    text = "Open the web browser and search machine learning and AIML"
    
    plan = apply_heuristic_fallback(text)
    
    assert plan.intent == "search_web"
    assert len(plan.steps) == 3
    
    # Check open_browser step
    assert plan.steps[0].tool == "launch_application"
    assert plan.steps[0].args["application"] == "chrome"
    
    # Check focus window
    assert plan.steps[1].tool == "focus_window"
    assert plan.steps[1].args["target"] == "Chrome"
    
    # Check search step & query extraction
    assert plan.steps[2].tool == "search_inside_application"
    assert plan.steps[2].args["query"] == "machine learning and aiml"

def test_fallback_heuristic_whatsapp():
    """Test WhatsApp sequence."""
    text = "send hi to Harshita on whatsapp"
    plan = apply_heuristic_fallback(text)
    assert plan.intent == "send_whatsapp"
    assert len(plan.steps) == 6
    assert plan.steps[0].tool == "launch_application"
    assert plan.steps[0].wait_for == "window_ready"
    assert plan.steps[1].tool == "focus_window"
    assert plan.steps[2].tool == "search_inside_application"
    assert plan.steps[3].tool == "press_key"
    assert plan.steps[4].tool == "type_text"
    assert plan.steps[4].args["text"] == "hi"
    assert plan.steps[5].tool == "press_key"

def test_fallback_heuristic_spotify():
    """Test Spotify sequence."""
    text = "play Believer on spotify"
    plan = apply_heuristic_fallback(text)
    assert plan.intent == "play_music"
    assert len(plan.steps) == 5
    assert plan.steps[0].tool == "launch_application"
    assert plan.steps[0].wait_for == "window_ready"
    assert plan.steps[1].tool == "focus_window"
    assert plan.steps[2].tool == "search_inside_application"
    assert plan.steps[2].args["query"] == "believer"
    assert plan.steps[3].tool == "press_key"
    assert plan.steps[4].tool == "perform_app_action"
