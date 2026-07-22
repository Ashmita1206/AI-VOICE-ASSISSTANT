"""
Targeted diagnostic: Trace what happens when "Open number 1" is sent AFTER a search.
Tests the exact pipeline the user described.
"""
import json
import time
import requests

BASE = "http://127.0.0.1:5000"

def stream_and_trace(command):
    print(f"\n{'='*80}")
    print(f"COMMAND: '{command}'")
    print(f"{'='*80}")
    resp = requests.post(f"{BASE}/transcribe_stream", data={"text": command}, stream=True, timeout=90)
    assert resp.status_code == 200, f"HTTP {resp.status_code}"
    
    events = []
    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        if decoded.startswith("data: "):
            try:
                evt = json.loads(decoded[6:])
                events.append(evt)
                stage = evt.get("stage", "?")
                status = evt.get("status", "?")
                msg = evt.get("message", "")
                data = evt.get("data", {})
                
                if stage == "transcript":
                    print(f"  TRANSCRIPT: '{data.get('text', msg)}'")
                elif stage == "planner" and status == "completed":
                    intent = data.get("intent", "?")
                    steps = data.get("steps", [])
                    print(f"  PLANNER INTENT: '{intent}'")
                    for i, s in enumerate(steps):
                        print(f"    Step {i}: tool='{s.get('tool')}' args={s.get('args')}")
                elif stage == "execution":
                    if status == "completed":
                        exec_steps = data.get("steps", [])
                        print(f"  EXECUTION COMPLETED: {len(exec_steps)} step(s)")
                        for es in exec_steps:
                            tool = es.get("tool", "?")
                            es_status = es.get("status", "?")
                            es_data = es.get("data", {})
                            es_output = es.get("output", "")
                            print(f"    tool='{tool}' status='{es_status}'")
                            if es_data:
                                if "opened_file" in es_data:
                                    print(f"    >>> OPENED FILE: {es_data['opened_file']}")
                                if es_data.get("opened"):
                                    print(f"    >>> OPENED=True, path={es_data.get('path')}")
                                if "results" in es_data:
                                    print(f"    >>> RESULTS COUNT: {len(es_data['results'])}")
                                    for r in es_data['results'][:2]:
                                        print(f"        #{r.get('rank')}: {r.get('filename')} -> {r.get('path')}")
                            if es_output:
                                print(f"    output: {str(es_output)[:150]}")
                    elif msg:
                        # truncate long messages
                        short = msg[:100].replace("\n"," ")
                        print(f"  EXEC MSG: {short}")
                elif stage == "done":
                    print(f"  DONE: status={status}")
            except Exception:
                pass
    return events

# STEP 1: Search for HealthSphere document
print("STEP 1: Search for document (to populate pending_document_results)")
search_events = stream_and_trace("Open HealthSphere document")
time.sleep(1)

# STEP 2: Open number 1
print("\nSTEP 2: Open number 1 (should open the first search result)")
open_events = stream_and_trace("Open number 1")
time.sleep(1)

# STEP 3: Search for Money Mentor
print("\nSTEP 3: Search Money Mentor")
stream_and_trace("Open Money Mentor document")
time.sleep(1)

# STEP 4: Open number 1 again
print("\nSTEP 4: Open number 1 for Money Mentor")
stream_and_trace("Open number 1")

print("\n" + "="*80)
print("DIAGNOSTIC COMPLETE")
print("="*80)
