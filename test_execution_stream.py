"""
Test script to simulate /transcribe_stream and /confirm stream for
'Open data science document from File Explorer' and trace all SSE events.
"""

import sys
import json
import requests

BASE_URL = "http://127.0.0.1:5000"

def main():
    print("[TEST] Sending POST /transcribe_stream with text='Open data science document from File Explorer'")
    
    resp = requests.post(f"{BASE_URL}/transcribe_stream", data={"text": "Open data science document from File Explorer"}, stream=True)
    print(f"[TEST] /transcribe_stream HTTP status: {resp.status_code}")
    
    confirmation_id = None
    plan = None
    
    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        print(f"[SSE RECV] {decoded}")
        if decoded.startswith("data: "):
            try:
                evt = json.loads(decoded[6:])
                stage = evt.get("stage")
                status = evt.get("status")
                if stage == "done" and status == "requires_confirmation":
                    conf = evt.get("data", {}).get("confirmation", {})
                    confirmation_id = conf.get("id")
                    plan = conf.get("plan")
                    print(f"\n[TEST] Received Confirmation ID: {confirmation_id}\n")
            except Exception as e:
                pass

    if not confirmation_id:
        print("[TEST ERROR] No confirmation ID received!")
        return

    print(f"[TEST] Sending POST /confirm?stream=true with ID: {confirmation_id}")
    confirm_resp = requests.post(
        f"{BASE_URL}/confirm?stream=true",
        json={"confirmation_id": confirmation_id, "decision": "proceed"},
        headers={"Accept": "text/event-stream"},
        stream=True
    )
    print(f"[TEST] /confirm HTTP status: {confirm_resp.status_code}")
    
    for line in confirm_resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        print(f"[CONFIRM SSE] {decoded}")

if __name__ == "__main__":
    main()
