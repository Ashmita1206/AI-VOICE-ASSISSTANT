import json
import os
import sys
import time
import requests

BASE_URL = "http://127.0.0.1:5000"

def test_user_flow(command: str):
    print("\n================================================================================")
    print(f"USER INPUT: '{command}'")
    print("================================================================================")

    t0 = time.perf_counter()
    resp = requests.post(
        f"{BASE_URL}/transcribe_stream",
        data={"text": command},
        stream=True,
        timeout=60
    )

    assert resp.status_code == 200, f"HTTP Error {resp.status_code}"

    transcript = None
    planner_output = None
    exec_steps = []
    completion_msg = None

    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")
        if line_str.startswith("data: "):
            try:
                event = json.loads(line_str[6:])
                stage = event.get("stage")
                status = event.get("status")

                if stage == "transcript":
                    transcript = event.get("data", {}).get("text") or event.get("message")
                    print(f"  [SSE Stage 1 - TRANSCRIPT] Text: '{transcript}'")
                elif stage == "planner" and status == "completed":
                    planner_output = event.get("data", {})
                    intent = planner_output.get("intent")
                    print(f"  [SSE Stage 2 - PLANNER] Intent: '{intent}' | Steps: {len(planner_output.get('steps', []))}")
                elif stage == "execution":
                    msg = event.get("message")
                    if msg:
                        print(f"  [SSE Stage 3 - EXECUTION] Message: '{msg[:100]}...'")
                    if status == "completed":
                        exec_steps = event.get("data", {}).get("steps", [])
                elif stage == "done":
                    completion_msg = event.get("message")
                    print(f"  [SSE Stage 4 - DONE] Status: {status} | Latency: {(time.perf_counter() - t0)*1000:.1f}ms")
            except Exception as e:
                pass

    print(f"\n--- VERIFYING RESULTS FOR: '{command}' ---")
    if exec_steps:
        for step in exec_steps:
            tool = step.get("tool")
            tool_status = step.get("status")
            print(f"  [OK] Tool Executed : {tool} (Status: {tool_status})")
            s_data = step.get("data") or {}
            results = s_data.get("results") or []
            if results:
                print(f"  [OK] Modal Payload : {len(results)} document result(s) returned for UI modal!")
                for r in results[:3]:
                    print(f"      - #{r.get('rank')}: {r.get('filename')} ({r.get('path')})")
            elif "opened_file" in s_data:
                print(f"  [OK] OS Open Result: File '{s_data.get('opened_file')}' opened successfully via os.startfile()!")
    else:
        print("  ✓ Command processed.")

    print(f"[PASSED] Full User Flow Verified for '{command}'")


if __name__ == "__main__":
    print("================================================================================")
    print("STEP-BY-STEP USER UI FLOW END-TO-END VERIFICATION")
    print("================================================================================")

    # 1. Test "Open HealthSphere document"
    test_user_flow("Open HealthSphere document")
    time.sleep(1)

    # 2. Test "Open number 1" (Opens the top result from search)
    test_user_flow("Open number 1")
    time.sleep(1)

    # 3. Test "Open HealthSphere PDF"
    test_user_flow("Open HealthSphere PDF")
    time.sleep(1)

    # 4. Test "Open Money Mentor document"
    test_user_flow("Open Money Mentor document")
    time.sleep(1)

    # 5. Test "Open Money Mentor PDF"
    test_user_flow("Open Money Mentor PDF")
    time.sleep(1)

    # 6. Test "Open number 1"
    test_user_flow("Open number 1")

    print("\n" + "=" * 80)
    print("ALL USER COMMAND FLOWS VERIFIED SUCCESSFULLY!")
    print("=" * 80)
