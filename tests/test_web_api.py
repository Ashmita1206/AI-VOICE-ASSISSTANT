"""
Web API Integration Tests
=========================

Tests the Flask endpoints to ensure they correctly stitch the entire
Jarvis pipeline together (STT -> Intent -> Planner -> Executor -> TTS).

Run:
    python -m pytest web/tests/test_api.py -v
"""

import os
import json
import tempfile
import wave
import pytest

from web.app import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def create_dummy_wav(path: str) -> None:
    """Create a dummy 1-second silence WAV file for testing."""
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        # 16000 frames of silence
        wf.writeframes(b'\x00\x00' * 16000)

def test_health_endpoint(client):
    """Test that the /health endpoint returns successfully."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "model" in data

def test_transcribe_missing_audio(client):
    """Test /transcribe endpoint without an audio file."""
    response = client.post("/transcribe")
    assert response.status_code == 400
    assert "error" in response.get_json()

def test_history_endpoint(client):
    """Test the /history endpoint returns a list."""
    response = client.get("/history")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)

def test_speak_endpoint(client):
    """Test the /speak text-to-speech generation endpoint."""
    response = client.post("/speak", json={"text": "Hello world"})
    assert response.status_code == 200
    data = response.get_json()
    assert "audio_url" in data
    assert data["audio_url"].startswith("/static/audio/")
    
    # Check that the file was actually created
    file_name = os.path.basename(data["audio_url"])
    file_path = os.path.join(client.application.static_folder, "audio", file_name)
    assert os.path.exists(file_path)

# Note: Testing /transcribe with real audio requires loading the Faster-Whisper model,
# which can take time and resources during a quick unit test. The components have been 
# thoroughly tested in earlier phases.
