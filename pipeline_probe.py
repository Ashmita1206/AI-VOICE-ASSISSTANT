"""
pipeline_probe.py
=================

Instruments the REAL voice pipeline end-to-end using the same HTTP
endpoints that the microphone and dashboard use. Zero application code
is modified; probes are injected at runtime and removed afterwards.

Two-leg flow (mirrors the real dashboard):

  Leg 1:  POST /transcribe_stream  (audio -> STT -> Intent -> Planner)
          Returns a requires_confirmation SSE event with a plan and confirmation_id.

  Leg 2:  POST /confirm?stream=true (auto-proceeds with the plan)
          Streams execution progress -> Explorer launch -> done.

Usage
-----
    # 1. Start Flask:
    #      python -m web.app
    # 2. In a second terminal (from the project root):
    #      python pipeline_probe.py                        # uses Recording.wav
    #      python pipeline_probe.py path/to/audio.wav      # custom file
    #      python pipeline_probe.py --gen "open my HealthSphere file"   # pyttsx3 TTS
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import threading
from datetime import datetime

# -- third-party (all available in the project venv) ------------------------
import requests
import psutil

try:
    import win32gui
    import win32process
    _WIN32 = True
except ImportError:
    _WIN32 = False

# ==============================================================================
# Config
# ==============================================================================
BASE_URL    = "http://localhost:5000"
STREAM_URL  = f"{BASE_URL}/transcribe_stream"
CONFIRM_URL = f"{BASE_URL}/confirm"
DEFAULT_WAV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Recording.wav")

# ==============================================================================
# Colour helpers
# ==============================================================================
RESET="\033[0m"; BOLD="\033[1m"; RED="\033[91m"; GREEN="\033[92m"
YELLOW="\033[93m"; CYAN="\033[96m"; MAG="\033[95m"; WHITE="\033[97m"

def _ts(): return datetime.now().strftime("%H:%M:%S.%f")[:-3]
def _p(c,tag,msg): print(f"{c}{BOLD}[{_ts()}][{tag}]{RESET} {msg}", flush=True)

def stage(t,m): _p(CYAN,t,m)
def ok(t,m):    _p(GREEN,t,m)
def warn(t,m):  _p(YELLOW,t,m)
def err(t,m):   _p(RED,t,m)
def info(t,m):  _p(WHITE,t,m)
def detail(t,m):_p(MAG,t,m)

# ==============================================================================
# Audio generation
# ==============================================================================
def generate_wav(text, out):
    stage("GEN", f'Generating WAV: "{text}"')
    try:
        import pyttsx3
        e = pyttsx3.init(); e.save_to_file(text, out); e.runAndWait()
        ok("GEN", f"WAV written ({os.path.getsize(out)} bytes): {out}"); return out
    except Exception as exc:
        err("GEN", f"pyttsx3 failed: {exc}"); sys.exit(1)

# ==============================================================================
# SSE parser
# ==============================================================================
def parse_sse(line):
    line = line.strip()
    if not line.startswith("data:"): return None
    raw = line[len("data:"):].strip()
    try: return json.loads(raw)
    except: return {"_raw": raw}

# ==============================================================================
# Explorer verification
# ==============================================================================
def explorer_pids():
    return {p.pid for p in psutil.process_iter(["name","pid"])
            if (p.info["name"] or "").lower() == "explorer.exe"}

def wait_for_new_explorer(before, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        new = explorer_pids() - before
        if new:
            ok("VERIFY", f"New explorer.exe PID(s): {new}"); return True
        time.sleep(0.25)
    warn("VERIFY", "No new explorer.exe process within timeout"); return False

def check_explorer_windows(timeout=6.0):
    if not _WIN32: return []
    found = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if psutil.Process(pid).name().lower() == "explorer.exe":
                            found.append(title)
                    except: pass
        try: win32gui.EnumWindows(_enum, None)
        except: pass
        if found: break
        time.sleep(0.3)
    return found

# ==============================================================================
# Runtime probes (non-destructive — removed after run)
# ==============================================================================
_SAVED = {}

def install_probes():
    """Wrap every registered tool handler to print entry/exit without touching source."""
    try:
        from execution import registry as _reg

        def _wrap(name, fn):
            def _w(args):
                stage("DISPATCH", f"{BOLD}{name}{RESET}  args={json.dumps(args,default=str)[:280]}")
                t0 = time.perf_counter()
                r = fn(args)
                ms = int((time.perf_counter()-t0)*1000)
                ok_or_fail = GREEN if getattr(r,"success",False) else RED
                print(f"{ok_or_fail}{BOLD}[{_ts()}][DISPATCH_RET]{RESET} "
                      f"{name} -> {'OK' if getattr(r,'success',False) else 'FAIL'}  "
                      f"({ms}ms)  msg={getattr(r,'message','')!r}", flush=True)
                # Special: if this is find_document_by_context, dump full output
                if name == "find_document_by_context":
                    detail("RETRIEVAL", f"output={getattr(r,'output','')[:400]}")
                # Special: if this is open_file, log path being opened
                if name == "open_file":
                    detail("OPEN_FILE", f"path arg={args.get('path','?')!r}")
                return r
            _w.__name__ = f"__probe_{name}"
            return _w

        for n, fn in list(_reg._REGISTRY.items()):
            _SAVED[n] = fn
            _reg._REGISTRY[n] = _wrap(n, fn)
        info("PROBE", f"Dispatch probes installed on {len(_SAVED)} tools.")
    except Exception as e:
        warn("PROBE", f"Could not install dispatch probes: {e}")

def install_explorer_probe():
    """Patch subprocess.Popen to log the exact explorer command line."""
    try:
        import subprocess as _sp
        _orig = _sp.Popen
        def _patched(args, **kw):
            cmd_str = args if isinstance(args,str) else " ".join(str(a) for a in args)
            if "explorer" in cmd_str.lower():
                detail("EXPLORER_CMD", f"Launching: {cmd_str}")
            return _orig(args, **kw)
        _sp.Popen = _patched
        _SAVED["__sp_popen"] = (_sp, _orig)
        info("PROBE", "subprocess.Popen patched — Explorer commands will be logged.")
    except Exception as e:
        warn("PROBE", f"Could not patch Popen: {e}")

def remove_probes():
    try:
        from execution import registry as _reg
        for k,v in _SAVED.items():
            if k == "__sp_popen":
                mod, orig = v; mod.Popen = orig
            elif k in _reg._REGISTRY:
                _reg._REGISTRY[k] = v
        info("PROBE", "All probes removed.")
    except Exception as e:
        warn("PROBE", f"Error removing probes: {e}")

# ==============================================================================
# SSE event printer
# ==============================================================================
LABELS = {
    "transcript":("STT",CYAN), "intent":("INTENT",YELLOW),
    "entities":("ENTITY",YELLOW), "discovery":("DISCOVERY",MAG),
    "planner":("PLANNER",MAG), "execution":("EXECUTOR",GREEN),
    "response":("RESPONSE",CYAN), "done":("DONE",GREEN),
}

def print_event(ev):
    s = ev.get("stage","?"); status = ev.get("status","?")
    tag, col = LABELS.get(s, ("SSE",WHITE))
    print(f"\n{col}{BOLD}{'-'*55}{RESET}", flush=True)
    _p(col, tag, f"stage={s!r}  status={status!r}")
    data = ev.get("data",{}); msg = ev.get("message")
    if msg: info(tag, f"msg: {msg}")

    if s == "transcript" and isinstance(data,dict):
        text = data.get("text","")
        ok(tag, f'Transcription: {BOLD}"{text}"{RESET}')
        info(tag, f"lang={data.get('language','')}  confidence={data.get('language_probability',0)*100:.1f}%")
        stt = data.get("stt",{}); pt = stt.get("processing_time_ms",0)
        info(tag, f"STT processing time: {pt} ms")

    elif s == "intent" and isinstance(data,dict):
        ok(tag, f"Intent: {BOLD}{data.get('name','?')}{RESET}  "
                f"confidence={data.get('confidence',0):.1f}%")

    elif s == "entities" and isinstance(data,dict):
        detail(tag, f"Entities: {json.dumps(data)}")

    elif s == "planner" and isinstance(data,dict):
        steps = data.get("steps",[])
        thought = data.get("reasoning",data.get("thought",""))
        if thought: detail(tag, f"Reasoning: {thought[:200]}")
        ok(tag, f"Plan: {len(steps)} step(s)")
        for i,st in enumerate(steps,1):
            info(tag, f"  {i}. {BOLD}{st.get('tool','?')}{RESET}  args={json.dumps(st.get('args',{}),default=str)[:200]}")

    elif s == "execution":
        items = data if isinstance(data,list) else ([data] if isinstance(data,dict) else [])
        for r in items:
            tool=r.get("tool","?"); succ=r.get("success"); emsg=r.get("message","")
            c2 = GREEN if succ else RED
            print(f"{c2}{BOLD}[{_ts()}][EXEC_RESULT]{RESET} "
                  f"tool={tool}  success={succ}  msg={emsg!r}", flush=True)

    elif s == "done":
        ok(tag, "Pipeline DONE.")
        if isinstance(data,dict):
            sp = data.get("speech",{})
            if sp: info(tag, f"TTS: {sp.get('text','')[:120]}")
            info(tag, f"Total pipeline time: {data.get('pipeline_time_ms',0)} ms")
            # Print confirmation block if present
            conf = data.get("confirmation",{})
            if conf:
                detail(tag, f"Confirmation ID: {conf.get('id','?')}")
                for i,a in enumerate(conf.get("estimated_actions",[]),1):
                    info(tag, f"  Action {i}: {a}")
    return ev

# ==============================================================================
# Stream consumer helper
# ==============================================================================
def consume_stream(resp, stop_after=None):
    """Iterate SSE lines from *resp*. Returns last event."""
    last = {}
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw: continue
        ev = parse_sse(raw)
        if ev is None: continue
        print_event(ev); last = ev
        if stop_after and ev.get("stage") == stop_after: break
        if ev.get("stage") == "done": break
    return last

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", default=DEFAULT_WAV)
    ap.add_argument("--gen", metavar="TEXT")
    ap.add_argument("--no-probes", action="store_true")
    args = ap.parse_args()

    # Resolve audio
    if args.gen:
        fd, tmp = tempfile.mkstemp(suffix=".wav"); os.close(fd)
        audio_path = generate_wav(args.gen, tmp)
    else:
        audio_path = args.audio
        if not os.path.exists(audio_path):
            err("INIT", f"Audio not found: {audio_path}")
            err("INIT", 'Use --gen "your voice command" to synthesize test audio')
            sys.exit(1)

    info("INIT", f"Audio: {audio_path}  ({os.path.getsize(audio_path)/1024:.1f} KB)")

    # Health check — wait up to 40s for Flask to become ready
    flask_up = False
    for _attempt in range(8):
        try:
            h = requests.get(f"{BASE_URL}/health", timeout=8)
            ok("INIT", f"Flask UP (attempt {_attempt+1}): {h.json()}")
            flask_up = True
            break
        except (requests.ConnectionError, requests.ReadTimeout):
            if _attempt < 7:
                info("INIT", f"Flask not ready (attempt {_attempt+1}/8) — retrying in 5s...")
                import time as _time_mod; _time_mod.sleep(5)
    if not flask_up:
        err("INIT", f"Flask not reachable at {BASE_URL} after 40s. Run: python -m web.app")
        sys.exit(1)

    # Snapshot explorer PIDs
    pids_before = explorer_pids()
    info("VERIFY", f"explorer.exe PIDs before: {pids_before or 'none'}")

    # Install probes
    if not args.no_probes:
        install_probes()
        install_explorer_probe()

    # -- LEG 1: /transcribe_stream --------------------------------------------
    print(f"\n{BOLD}{'='*65}{RESET}", flush=True)
    stage("LEG1", f"POST {STREAM_URL}")
    print(f"{BOLD}{'='*65}{RESET}\n", flush=True)

    suffix  = os.path.splitext(audio_path)[1] or ".wav"
    mimes   = {".wav":"audio/wav",".webm":"audio/webm",".mp3":"audio/mpeg",
               ".ogg":"audio/ogg",".m4a":"audio/mp4"}
    ctype   = mimes.get(suffix.lower(),"audio/wav")

    confirmation_id = None
    try:
        with open(audio_path,"rb") as f:
            r1 = requests.post(STREAM_URL,
                               files={"audio":(os.path.basename(audio_path),f,ctype)},
                               stream=True, timeout=180)
        ok("LEG1", f"HTTP {r1.status_code}")
        last_ev = consume_stream(r1)

        # Extract confirmation_id from done/requires_confirmation
        if last_ev.get("status") == "requires_confirmation":
            conf = last_ev.get("data",{}).get("confirmation",{})
            confirmation_id = conf.get("id")
            detail("LEG1", f"Confirmation ID: {confirmation_id}")
            detail("LEG1", f"Plan steps: {[s.get('tool') for s in last_ev.get('data',{}).get('confirmation',{}).get('plan',{}).get('steps',[])]}")
    except Exception as exc:
        err("LEG1", f"Error: {exc}")
        import traceback; traceback.print_exc()
    finally:
        if args.gen and os.path.exists(audio_path): os.remove(audio_path)

    # -- LEG 2: /confirm  (auto-proceed) --------------------------------------
    if confirmation_id:
        print(f"\n{BOLD}{'='*65}{RESET}", flush=True)
        stage("LEG2", f"POST {CONFIRM_URL}?stream=true  (confirmation_id={confirmation_id})")
        print(f"{BOLD}{'='*65}{RESET}\n", flush=True)
        try:
            r2 = requests.post(
                f"{CONFIRM_URL}?stream=true",
                json={"confirmation_id": confirmation_id, "decision": "proceed"},
                headers={"Accept":"text/event-stream"},
                stream=True, timeout=180
            )
            ok("LEG2", f"HTTP {r2.status_code}")
            consume_stream(r2)
        except Exception as exc:
            err("LEG2", f"Error: {exc}")
            import traceback; traceback.print_exc()
    else:
        warn("LEG2", "No confirmation_id received — skipping execution leg.")
        warn("LEG2", "This means the pipeline did NOT reach requires_confirmation.")
        warn("LEG2", "Check if planner returned an empty plan or a validation error above.")

    # -- Remove probes --------------------------------------------------------
    if not args.no_probes:
        remove_probes()

    # -- Explorer verification ------------------------------------------------
    print(f"\n{BOLD}{'='*65}{RESET}", flush=True)
    stage("VERIFY", "Checking for Explorer window …")
    explorer_ok = wait_for_new_explorer(pids_before, timeout=8.0)
    titles = check_explorer_windows(timeout=5.0)
    if titles:
        ok("VERIFY", f"Explorer windows visible ({len(titles)}):")
        for t in sorted(set(titles)): info("VERIFY", f"  {t!r}")
    else:
        warn("VERIFY", "No Explorer window detected via win32gui.")

    # -- Final summary --------------------------------------------------------
    print(f"\n{BOLD}{'='*65}{RESET}", flush=True)
    print(f"{BOLD}PROBE SUMMARY{RESET}", flush=True)
    print(f"{BOLD}{'='*65}{RESET}", flush=True)
    c = GREEN if explorer_ok else RED
    print(f"{c}{BOLD}[{_ts()}][RESULT]{RESET} Explorer launched through real pipeline: {explorer_ok}", flush=True)
    if not confirmation_id:
        warn("RESULT","Pipeline stopped at planning — execution never ran.")
        warn("RESULT","Likely cause: planner validation error or no steps returned.")
    elif not explorer_ok:
        warn("RESULT","Execution ran but Explorer did not launch.")
        warn("RESULT","Check DISPATCH logs above for find_document_by_context or open_file failure.")
    else:
        ok("RESULT","Full pipeline verified: voice -> STT -> intent -> plan -> execute -> Explorer.")

if __name__ == "__main__":
    main()
