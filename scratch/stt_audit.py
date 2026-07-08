import sys, os, io, time, socket, ssl, json
sys.path.insert(0, r'd:\ai voice assisstant')
if sys.platform.startswith('win'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(r'd:\ai voice assisstant\.env')
import config

SEP = "-" * 60
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"

# ── CHECK 1: .env values ───────────────────────────────────────────────
print(SEP)
print("CHECK 1 — .env and config.py runtime values")
print(SEP)
raw = os.getenv("STT_USE_REMOTE", "__NOT_SET__")
print(f"{INFO} os.getenv('STT_USE_REMOTE') raw : {raw!r}")
print(f"{INFO} config.STT_USE_REMOTE           : {config.STT_USE_REMOTE}")
print(f"{INFO} config.STT_API_URL              : {config.STT_API_URL}")
print(f"{INFO} config.STT_API_TIMEOUT          : {config.STT_API_TIMEOUT}s")
print(f"{INFO} config.DEVICE                   : {config.DEVICE}")
print(f"{INFO} config.COMPUTE_TYPE             : {config.COMPUTE_TYPE}")

if config.STT_USE_REMOTE:
    print(f"{PASS} STT_USE_REMOTE is TRUE — remote mode configured")
else:
    print(f"{FAIL} STT_USE_REMOTE is FALSE — local mode active")

# ── CHECK 2: Active engine ─────────────────────────────────────────────
print()
print(SEP)
print("CHECK 2 — Active STT engine (get_stt())")
print(SEP)
from web.services import get_stt
stt_a = get_stt()
stt_b = get_stt()
cls_name = stt_a.__class__.__name__
print(f"{INFO} Engine class   : {cls_name}")
print(f"{INFO} Engine module  : {stt_a.__class__.__module__}")
print(f"{INFO} Singleton check: call-1 id={id(stt_a)}, call-2 id={id(stt_b)}, same={stt_a is stt_b}")

if cls_name == "RemoteWhisperSTT":
    print(f"{PASS} RemoteWhisperSTT is active — will contact Colab")
else:
    print(f"{FAIL} WhisperSTT (LOCAL) is active — Colab NOT contacted")
    if hasattr(stt_a, 'api_url'):
        print(f"{INFO} api_url: {stt_a.api_url}")

# ── CHECK 3: Network to Colab ──────────────────────────────────────────
print()
print(SEP)
print("CHECK 3 — Network connectivity to STT_API_URL")
print(SEP)
import urllib.parse
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print(f"{FAIL} 'requests' library not installed")

api_url = config.STT_API_URL.rstrip("/")
parsed  = urllib.parse.urlparse(api_url)
host    = parsed.hostname or ""
scheme  = parsed.scheme or "https"
port    = parsed.port or (443 if scheme == "https" else 80)
print(f"{INFO} Full URL : {api_url}")
print(f"{INFO} Host     : {host}")
print(f"{INFO} Port     : {port}")

# DNS
DNS_OK = False
try:
    ip = socket.gethostbyname(host)
    print(f"{PASS} DNS resolved: {host} -> {ip}")
    DNS_OK = True
except socket.gaierror as e:
    print(f"{FAIL} DNS FAILED for {host!r}: {e}")

# TCP
TCP_OK = False
if DNS_OK:
    try:
        s = socket.create_connection((host, port), timeout=10)
        s.close()
        print(f"{PASS} TCP connected to {host}:{port}")
        TCP_OK = True
    except Exception as e:
        print(f"{FAIL} TCP FAILED: {e}")

# TLS
if TCP_OK and scheme == "https":
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=host) as ss:
            ss.settimeout(10)
            ss.connect((host, port))
        print(f"{PASS} TLS handshake OK")
    except ssl.SSLError as e:
        print(f"{FAIL} SSL error: {e}")
    except Exception as e:
        print(f"{WARN} TLS check skipped: {e}")

# ── CHECK 4: GET /health ───────────────────────────────────────────────
print()
print(SEP)
print("CHECK 4 — GET /health on Colab server")
print(SEP)
HEALTH_OK = False
health_base = api_url.rsplit("/transcribe", 1)[0]
health_url  = health_base + "/health"
print(f"{INFO} Health URL: {health_url}")

if HAS_REQUESTS and DNS_OK:
    try:
        t0 = time.perf_counter()
        hr = requests.get(health_url, timeout=10)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        print(f"{INFO} HTTP status : {hr.status_code}")
        print(f"{INFO} Latency     : {latency_ms} ms")
        try:
            body = hr.json()
            print(f"{INFO} Body        : {json.dumps(body)}")
        except Exception:
            print(f"{INFO} Body (raw)  : {hr.text[:300]}")
        if hr.status_code == 200:
            print(f"{PASS} Colab /health returned 200 — server is UP")
            HEALTH_OK = True
        elif hr.status_code == 404:
            print(f"{WARN} HTTP 404 — server up but /health not registered")
            HEALTH_OK = True
        else:
            print(f"{FAIL} HTTP {hr.status_code} from /health")
    except requests.exceptions.ConnectionError as e:
        print(f"{FAIL} Connection refused/reset: {e}")
    except requests.exceptions.Timeout:
        print(f"{FAIL} Timeout after 10s")
    except Exception as e:
        print(f"{FAIL} Error: {e}")
else:
    print(f"{WARN} Skipped — DNS failed or requests not available")

# ── CHECK 5: POST /transcribe ──────────────────────────────────────────
print()
print(SEP)
print("CHECK 5 — POST /transcribe with sample audio")
print(SEP)
TRANSCRIBE_OK = False
transcript_text = ""
audio_path = r'd:\ai voice assisstant\Recording.wav'

if not os.path.isfile(audio_path):
    # create a tiny synthetic wav
    import wave, struct, math, tempfile
    tmp_fd, audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)
    with wave.open(audio_path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        frames = b"".join(struct.pack("<h", int(32767*math.sin(2*3.14159*440*i/16000))) for i in range(16000*2))
        wf.writeframes(frames)
    print(f"{INFO} Created synthetic 2s wav: {audio_path}")
    _synth = True
else:
    _synth = False
    print(f"{INFO} Audio: {audio_path} ({os.path.getsize(audio_path)/1024:.1f} KB)")

if HAS_REQUESTS and HEALTH_OK:
    print(f"{INFO} POST -> {api_url}")
    print(f"{INFO} Timeout: {config.STT_API_TIMEOUT}s")
    try:
        t0 = time.perf_counter()
        with open(audio_path, "rb") as af:
            resp = requests.post(
                api_url,
                files={"audio": (os.path.basename(audio_path), af)},
                timeout=config.STT_API_TIMEOUT
            )
        rtt_ms = int((time.perf_counter() - t0) * 1000)
        print(f"{INFO} HTTP status  : {resp.status_code}")
        print(f"{INFO} Round-trip   : {rtt_ms} ms ({rtt_ms/1000:.1f}s)")
        print(f"{INFO} Content-Type : {resp.headers.get('Content-Type','(none)')}")
        print(f"{INFO} Size         : {len(resp.content)} bytes")
        if resp.status_code == 200:
            try:
                payload = resp.json()
                print(f"{INFO} Response JSON:")
                print(json.dumps(payload, indent=4, ensure_ascii=False))
                if "text" in payload:
                    transcript_text = payload["text"]
                    print(f"{PASS} Transcript: \"{transcript_text[:120]}\"")
                    TRANSCRIBE_OK = True
                elif "error" in payload:
                    print(f"{FAIL} Server error: {payload['error']}")
                else:
                    print(f"{WARN} Unexpected keys: {list(payload.keys())}")
            except Exception as e:
                print(f"{FAIL} JSON parse failed: {e}")
                print(f"{INFO} Raw: {resp.text[:400]}")
        else:
            print(f"{FAIL} HTTP {resp.status_code}")
            try: print(f"{INFO} Error: {json.dumps(resp.json(), indent=2)}")
            except: print(f"{INFO} Body: {resp.text[:300]}")
    except requests.exceptions.ConnectionError as e:
        print(f"{FAIL} Connection error: {e}")
    except requests.exceptions.Timeout:
        print(f"{FAIL} Timeout after {config.STT_API_TIMEOUT}s")
    except Exception as e:
        print(f"{FAIL} Exception: {e}")
    if _synth:
        try: os.remove(audio_path)
        except: pass
else:
    print(f"{WARN} Skipped — server not reachable or requests unavailable")

# ── CHECK 6: Flask startup log scan ───────────────────────────────────
print()
print(SEP)
print("CHECK 6 — Scan running Flask process for STT mode log")
print(SEP)
# The Flask process is already running (python -m web.app).
# We cannot read its stdout here, but we can check what get_stt() logs.
import logging
log_capture = []
class CapHandler(logging.Handler):
    def emit(self, record):
        log_capture.append(self.format(record))

root = logging.getLogger()
cap = CapHandler()
root.addHandler(cap)

# Force get_stt to log by resetting singleton
import web.services as svc_mod
svc_mod._stt = None
_ = svc_mod.get_stt()
root.removeHandler(cap)

remote_logged = any("REMOTE" in m for m in log_capture)
local_logged  = any("LOCAL"  in m for m in log_capture)
for m in log_capture:
    print(f"{INFO} LOG: {m}")
if remote_logged:
    print(f"{PASS} 'STT mode: REMOTE' was logged")
elif local_logged:
    print(f"{FAIL} 'STT mode: LOCAL' was logged (Colab not used)")
else:
    print(f"{WARN} No STT mode log captured (singleton already initialised)")

# ── FINAL SUMMARY ─────────────────────────────────────────────────────
print()
print("=" * 60)
print("  FINAL AUDIT SUMMARY")
print("=" * 60)

REMOTE_MODE      = config.STT_USE_REMOTE
ENGINE_CLASS     = svc_mod.get_stt().__class__.__name__
REMOTE_HEALTH    = "UP (200)" if HEALTH_OK else ("DNS_FAIL" if not DNS_OK else "TCP_FAIL" if not TCP_OK else "DOWN")
REMOTE_TRANSCR   = "SUCCESS - transcript returned" if TRANSCRIBE_OK else "FAILED"
LOCAL_USED       = ENGINE_CLASS == "WhisperSTT"

if not REMOTE_MODE:
    root_cause = "STT_USE_REMOTE=false in .env — remote mode explicitly disabled"
    fix = "Set STT_USE_REMOTE=true in .env then RESTART Flask"
elif not DNS_OK:
    root_cause = "ngrok URL cannot be resolved — DNS failure (Colab session ended)"
    fix = "Re-run Colab Cells 2-3, copy new ngrok URL, update STT_API_URL in .env, restart Flask"
elif not TCP_OK:
    root_cause = "TCP connection refused — ngrok tunnel is dead"
    fix = "Re-run Colab Cells 2-3 to restart ngrok, update .env, restart Flask"
elif not HEALTH_OK:
    root_cause = "Server reachable but /health failed — Flask in Colab crashed"
    fix = "Re-run Colab Cell 3, wait for 'STT API is LIVE', restart local Flask"
elif not TRANSCRIBE_OK:
    root_cause = "/health OK but POST /transcribe failed — Whisper model error in Colab"
    fix = "Check Colab Cell 3 logs for exception, re-run cell, test with .wav file"
elif ENGINE_CLASS != "RemoteWhisperSTT":
    root_cause = "Flask not restarted after changing STT_USE_REMOTE (cached config)"
    fix = "Restart Flask — do not just reload .env while server is running"
else:
    root_cause = "None — all checks passed"
    fix = "No action needed"

print(f"\nREMOTE MODE       : {'YES' if REMOTE_MODE else 'NO'}")
print(f"ACTIVE ENGINE     : {ENGINE_CLASS}")
print(f"REMOTE HEALTH     : {REMOTE_HEALTH}")
print(f"REMOTE TRANSCRIBE : {REMOTE_TRANSCR}")
print(f"LOCAL WHISPER USED: {'YES' if LOCAL_USED else 'NO'}")
print(f"ROOT CAUSE        : {root_cause}")
print(f"FIX REQUIRED      : {fix}")
print()
