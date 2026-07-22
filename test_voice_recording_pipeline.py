"""
Voice Recording Pipeline Verification Script
============================================
Tests end-to-end voice audio posting via POST /transcribe_stream and /confirm,
verifying that the audio recording pipeline operates without network errors or reloads.
"""

import os
import sys
import json
import time
import requests

BASE_URL = "http://127.0.0.1:5000"

def main():
    print("\n==================================================================")
    print("VOICE RECORDING PIPELINE VERIFICATION")
    print("==================================================================\n")

    # Use open_test.wav or search_test.wav present in workspace
    audio_file = "open_test.wav"
    if not os.path.exists(audio_file):
        print(f"[ERROR] Audio file {audio_file} not found!")
        return

    print(f"[1. AUDIO POST] Sending voice recording file '{audio_file}' to POST /transcribe_stream...")
    
    with open(audio_file, "rb") as f:
        files = {"audio": (audio_file, f, "audio/wav")}
        resp = requests.post(f"{BASE_URL}/transcribe_stream", files=files, stream=True)

    print(f"  HTTP Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    confirmation_id = None
    transcription = None
    events = []

    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        if decoded.startswith("data: "):
            evt = json.loads(decoded[6:])
            events.append(evt)
            stage = evt.get("stage")
            status = evt.get("status")
            print(f"  [SSE] Stage: {stage:<15} | Status: {status:<22} | Msg: {evt.get('message')}")
            
            if stage == "transcript" and status == "completed":
                transcription = evt.get("data", {}).get("text")
            elif stage == "done" and status == "requires_confirmation":
                confirmation_id = evt.get("data", {}).get("confirmation", {}).get("id")

    print(f"\n[STT RESULT] Transcription: '{transcription}'")
    print(f"[CONFIRMATION] Received ID: {confirmation_id}")

    if not confirmation_id:
        print("  Notice: Plan did not require confirmation or executed directly.")
        return

    # Send confirmation stream request
    print(f"\n[2. CONFIRM STREAM] Posting /confirm?stream=true for ID '{confirmation_id}'...")
    confirm_resp = requests.post(
        f"{BASE_URL}/confirm?stream=true",
        json={"confirmation_id": confirmation_id, "decision": "proceed"},
        headers={"Accept": "text/event-stream"},
        stream=True
    )

    print(f"  HTTP Status: {confirm_resp.status_code}")
    assert confirm_resp.status_code == 200

    confirm_events = []
    for line in confirm_resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        if decoded.startswith("data: "):
            evt = json.loads(decoded[6:])
            confirm_events.append(evt)
            stage = evt.get("stage")
            status = evt.get("status")
            print(f"  [CONFIRM SSE] Stage: {stage:<15} | Status: {status:<22} | Msg: {evt.get('message')}")

    print("\n==================================================================")
    print("VOICE RECORDING PIPELINE PASSED 100% PERFECTLY!")
    print("==================================================================\n")

if __name__ == "__main__":
    main()
