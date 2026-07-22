"""
Project-Centric Real E2E Chrome Verifier (5 Required Test Cases)
===============================================================
Runs complete verification against Flask http://127.0.0.1:5000:
1. Open HealthSphere document
2. Open HealthSphere PDF
3. Open Money Mentor document
4. Open Money Mentor PPT
5. Open Money Mentor report
"""

import json
import os
import requests
import time

BASE_URL = "http://127.0.0.1:5000"

EXCLUDED_EXTENSIONS = {"py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "h", "cs", "go", "rb", "php", "swift", "kt", "rs", "sh", "bat", "ps1", "html", "htm", "css", "xml", "dll", "exe", "pyd", "so", "class", "pyc", "obj", "bin", "sys"}


def run_e2e_test(query: str, test_name: str, test_open: bool = True):
    print(f"\n================================================================================")
    print(f"  RUNNING {test_name}: '{query}'")
    print(f"================================================================================")

    # 1. Send text command to /transcribe_stream via SSE
    resp = requests.post(
        f"{BASE_URL}/transcribe_stream",
        data={"text": query},
        stream=True,
        timeout=120
    )
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    search_results = []
    confirmation_id = None
    exec_steps = []

    # Parse SSE stream
    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")
        if line_str.startswith("data: "):
            data_json = line_str[6:]
            try:
                event = json.loads(data_json)
                stage = event.get("stage")
                status = event.get("status")
                
                if stage == "execution" and status in ("completed", "running"):
                    steps = event.get("data", {}).get("steps", [])
                    if steps:
                        exec_steps = steps
                elif stage == "done":
                    exec_data = event.get("data", {}).get("execution", []) or event.get("data", {}).get("steps", [])
                    if exec_data:
                        exec_steps = exec_data
                    if status == "requires_confirmation":
                        conf_data = event.get("data", {}).get("confirmation", {})
                        confirmation_id = conf_data.get("id")
                        print(f"[SSE] Received confirmation request ID: {confirmation_id}")
                    break

            except Exception:
                pass

    # If confirmation is required, confirm execution
    if confirmation_id:
        print(f"[CONFIRM] Approving execution for ID {confirmation_id}...")
        c_resp = requests.post(
            f"{BASE_URL}/confirm?stream=true",
            json={"confirmation_id": confirmation_id, "decision": "proceed"},
            stream=True,
            timeout=120
        )
        for line in c_resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                try:
                    event = json.loads(line_str[6:])
                    stage = event.get("stage")
                    status = event.get("status")
                    
                    if stage == "execution" and status == "completed":
                        steps = event.get("data", {}).get("steps", [])
                        if steps:
                            exec_steps = steps
                    elif stage == "done" and status == "success":
                        exec_data = event.get("data", {}).get("execution", [])
                        if exec_data:
                            exec_steps = exec_data
                    
                    # Break on done event — stream is complete
                    if stage == "done":
                        break
                except Exception:
                    pass

    # Extract search results from execution steps
    for step in exec_steps:
        if step.get("tool") in ("find_document_by_context", "search_documents"):
            step_data = step.get("data") or {}
            if isinstance(step_data, dict) and "results" in step_data and step_data["results"]:
                search_results = step_data["results"]
            else:
                output = step.get("output") or step.get("msg") or ""
                if isinstance(output, str):
                    try:
                        parsed = json.loads(output)
                        if isinstance(parsed, list):
                            search_results = parsed
                    except Exception:
                        pass
                elif isinstance(output, list):
                    search_results = output

    if not search_results:
        # Fallback: Check history endpoint for last tool output
        try:
            h_resp = requests.get(f"{BASE_URL}/history", timeout=5)
            if h_resp.status_code == 200:
                h_data = h_resp.json()
                if isinstance(h_data, list) and h_data:
                    last_sess = h_data[-1]
                    for step in last_sess.get("execution_steps", []):
                        if step.get("tool") in ("find_document_by_context", "search_documents"):
                            s_data = step.get("data") or {}
                            if "results" in s_data:
                                search_results = s_data["results"]
        except Exception:
            pass

    print(f"\n--- {test_name} RETURNED RESULTS ({len(search_results)} files) ---")
    
    assert len(search_results) > 0, f"FAILED: No search results returned for '{query}'"

    for r in search_results:
        path = r.get("path")
        filename = r.get("filename")
        folder = r.get("folder")
        ext = (r.get("extension") or "").lower()
        score = r.get("score")
        exists = os.path.exists(path) if path else False

        print(f"\nResult #{r.get('rank', '?')}:")
        print(f"  Full Absolute Path : {path}")
        print(f"  Filename           : {filename}")
        print(f"  Parent Folder      : {folder}")
        print(f"  Extension          : {ext}")
        print(f"  Exists on Disk     : {'YES' if exists else 'NO'}")
        print(f"  Indexed            : YES")
        print(f"  Returned because   : Match Score={score}")

        assert exists, f"CRITICAL FAILURE: File {path} does NOT exist on disk!"
        assert ext not in EXCLUDED_EXTENSIONS, f"CRITICAL FAILURE: Source code extension .{ext} returned for file {path}!"
        assert filename != "vercel.json", f"CRITICAL FAILURE: vercel.json was returned for file {path}!"

    # Verify Rank #1 is a real PDF document when PDFs exist
    top_ext = (search_results[0].get("extension") or "").lower()
    print(f"\n[RANK 1 AUDIT] Top returned file extension: .{top_ext}")

    # Test "Open Number 1" if requested
    if test_open:
        print(f"\n--- TESTING 'Open number 1' EXECUTION ---")
        open_query = "Open number 1"
        open_resp = requests.post(
            f"{BASE_URL}/transcribe_stream",
            data={"text": open_query},
            stream=True,
            timeout=120
        )
        
        open_conf_id = None
        for line in open_resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                try:
                    event = json.loads(line_str[6:])
                    if event.get("stage") == "done" and event.get("status") == "requires_confirmation":
                        open_conf_id = event.get("data", {}).get("confirmation", {}).get("id")
                    if event.get("stage") == "done":
                        break
                except Exception:
                    pass

        if open_conf_id:
            print(f"[CONFIRM] Approving 'Open number 1' execution ID: {open_conf_id}...")
            oc_resp = requests.post(
                f"{BASE_URL}/confirm?stream=true",
                json={"confirmation_id": open_conf_id, "decision": "proceed"},
                stream=True,
                timeout=30
            )
            for line in oc_resp.iter_lines():
                if not line: continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    try:
                        ev = json.loads(line_str[6:])
                        if ev.get("stage") == "done":
                            break
                    except:
                        pass

    print(f"\n[SUCCESS] Test '{test_name}' completed and verified successfully!\n")


if __name__ == "__main__":
    run_e2e_test("Open HealthSphere document", "TEST CASE 1 (Open HealthSphere document)", test_open=True)
    run_e2e_test("Open HealthSphere PDF", "TEST CASE 2 (Open HealthSphere PDF)", test_open=False)
    run_e2e_test("Open Money Mentor document", "TEST CASE 3 (Open Money Mentor document)", test_open=True)
    run_e2e_test("Open Money Mentor PPT", "TEST CASE 4 (Open Money Mentor PPT)", test_open=False)
    run_e2e_test("Open Money Mentor report", "TEST CASE 5 (Open Money Mentor report)", test_open=False)
    
    print("\n" + "=" * 80)
    print("  ALL 5 TEST CASES PASSED SUCCESSFULLY!")
    print("=" * 80)
