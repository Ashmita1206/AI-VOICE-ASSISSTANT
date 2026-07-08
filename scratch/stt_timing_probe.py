"""
STT Timing Benchmark — READ ONLY, no source modifications.
Run: python scratch/stt_timing_probe.py
Delete after debugging.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
import config

AUDIO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Recording.wav")
SEP = "-" * 60

print(f"\n{'='*60}")
print("  STT PHASE-BY-PHASE TIMING BENCHMARK")
print(f"{'='*60}")
print(f"  Audio file  : {AUDIO}")
print(f"  File size   : {os.path.getsize(AUDIO)/1024:.1f} KB")
print(f"  Device      : {config.DEVICE}")
print(f"  Compute type: {config.COMPUTE_TYPE}")
print(f"  Model ID    : {config.STT_MODEL_ID}")
print(f"  Beam size   : {config.STT_BEAM_SIZE}")
print(f"  VAD filter  : {config.STT_VAD_FILTER}")
print()

# ── Phase 0: singleton state ───────────────────────────────────────────
print(SEP)
print("PHASE 0 -- Singleton state in services.py")
print(SEP)
from web.services import _stt as _stt_before
print(f"  services._stt before get_stt() : {_stt_before!r}")
from web.services import get_stt
stt_1 = get_stt()
stt_2 = get_stt()
print(f"  get_stt() call-1 id            : {id(stt_1)}")
print(f"  get_stt() call-2 id            : {id(stt_2)}")
print(f"  Same object (singleton)?       : {stt_1 is stt_2}")
print(f"  Engine class                   : {stt_1.__class__.__name__}")
print(f"  Model already loaded?          : {stt_1._model is not None}")
print()

# ── Phase 1: __init__ cost ─────────────────────────────────────────────
print(SEP)
print("PHASE 1 -- WhisperSTT.__init__() [no model load]")
print(SEP)
from stt.whisper_engine import WhisperSTT
t0 = time.perf_counter()
fresh = WhisperSTT()
t_init = time.perf_counter() - t0
print(f"  __init__() time : {t_init*1000:.1f} ms")
print(f"  _model is None? : {fresh._model is None}  (lazy - not loaded yet)")
print()

# ── Phase 2: _load_model cost ─────────────────────────────────────────
print(SEP)
print("PHASE 2 -- WhisperModel load (_load_model via .model property)")
print(SEP)
print("  Loading model now - may take 10-90s on CPU...")
t0 = time.perf_counter()
_ = fresh.model
t_load = time.perf_counter() - t0
print(f"  _load_model() time : {t_load:.3f}s")
print(f"  _model is None?    : {fresh._model is None}")
print()

# ── Phase 3: First transcribe() ───────────────────────────────────────
print(SEP)
print("PHASE 3 -- First transcribe() [model warm, no prior audio cache]")
print(SEP)
t0 = time.perf_counter()
result = fresh.transcribe(AUDIO)
t_t1 = time.perf_counter() - t0
print(f"  Wall time (total)         : {t_t1:.3f}s")
print(f"  processing_time (ct2 only): {result['processing_time']:.3f}s")
print(f"  overhead (decode+VAD+post): {t_t1 - result['processing_time']:.3f}s")
print(f"  audio duration            : {result['duration']:.3f}s")
print(f"  RTF (real-time factor)    : {result['processing_time'] / max(result['duration'],0.001):.2f}x")
print(f"  language                  : {result['language']} ({result['language_probability']*100:.1f}%)")
print(f"  text                      : \"{result['text'][:100]}\"")
print()

# ── Phase 4: Second transcribe() ─────────────────────────────────────
print(SEP)
print("PHASE 4 -- Second transcribe() [fully warm]")
print(SEP)
t0 = time.perf_counter()
result2 = fresh.transcribe(AUDIO)
t_t2 = time.perf_counter() - t0
print(f"  Wall time (total)     : {t_t2:.3f}s")
print(f"  processing_time       : {result2['processing_time']:.3f}s")
print(f"  RTF                   : {result2['processing_time'] / max(result2['duration'],0.001):.2f}x")
print()

# ── Phase 5: Reload-per-request simulation ───────────────────────────
print(SEP)
print("PHASE 5 -- Simulated reload-per-request (new WhisperSTT each call)")
print(SEP)
t0 = time.perf_counter()
bad = WhisperSTT()
_ = bad.model
result3 = bad.transcribe(AUDIO)
t_reload = time.perf_counter() - t0
print(f"  new-instance + load + transcribe : {t_reload:.3f}s")
print(f"  vs singleton 2nd call            : {t_t2:.3f}s")
print(f"  Penalty per request if reloading : {t_reload - t_t2:.3f}s")
print()

# ── Phase 6: VAD overhead ─────────────────────────────────────────────
print(SEP)
print("PHASE 6 -- VAD=True vs VAD=False")
print(SEP)
_m = fresh._model
t0 = time.perf_counter()
segs, info = _m.transcribe(AUDIO, beam_size=config.STT_BEAM_SIZE, vad_filter=True)
list(segs)
t_vad_on = time.perf_counter() - t0
t0 = time.perf_counter()
segs2, _ = _m.transcribe(AUDIO, beam_size=config.STT_BEAM_SIZE, vad_filter=False)
list(segs2)
t_vad_off = time.perf_counter() - t0
print(f"  VAD=True  : {t_vad_on:.3f}s")
print(f"  VAD=False : {t_vad_off:.3f}s")
print(f"  VAD cost  : {t_vad_on - t_vad_off:.3f}s")
print()

# ── Phase 7: Beam size overhead ───────────────────────────────────────
print(SEP)
print("PHASE 7 -- Beam size: 5 vs 1")
print(SEP)
t0 = time.perf_counter()
segs3, _ = _m.transcribe(AUDIO, beam_size=5, vad_filter=False)
list(segs3)
t_b5 = time.perf_counter() - t0
t0 = time.perf_counter()
segs4, _ = _m.transcribe(AUDIO, beam_size=1, vad_filter=False)
list(segs4)
t_b1 = time.perf_counter() - t0
print(f"  beam=5 : {t_b5:.3f}s")
print(f"  beam=1 : {t_b1:.3f}s")
print(f"  cost   : {t_b5 - t_b1:.3f}s")
print()

# ── Summary ───────────────────────────────────────────────────────────
print("=" * 60)
print("  FINAL TIMING SUMMARY")
print("=" * 60)
print(f"  __init__()                     : {t_init*1000:.0f} ms")
print(f"  _load_model() [once at startup]: {t_load:.2f}s")
print(f"  1st transcribe() (model warm)  : {t_t1:.2f}s")
print(f"  2nd transcribe() (fully warm)  : {t_t2:.2f}s")
print(f"  reload-per-request simulation  : {t_reload:.2f}s")
print(f"  VAD overhead                   : {t_vad_on - t_vad_off:.2f}s")
print(f"  beam_size 5 vs 1 overhead      : {t_b5 - t_b1:.2f}s")
print(f"  CPU RTF (beam=5, VAD=True)     : {result['processing_time']/max(result['duration'],0.001):.1f}x")
print()
if t_load > 10:
    print("  [SLOW MODEL LOAD] >10s - one-time cost if singleton is working.")
if result['processing_time'] / max(result['duration'], 0.001) > 5:
    print("  [HIGH RTF] CPU inference >> 5x real-time. Main bottleneck is CPU.")
if t_vad_on - t_vad_off > 2:
    print("  [VAD COST] VAD adds significant seconds.")
if t_reload - t_t2 > 10:
    print("  [RELOAD PENALTY] Reloading model per request would add massive overhead.")
print()
print("  Benchmark complete. Delete scratch/stt_timing_probe.py when done.")
