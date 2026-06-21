"""
AI Voice Assistant — Central Configuration
==========================================

All configurable settings live here. Import this module anywhere
you need access to paths, model parameters, or audio settings.
"""

import os
import torch


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "audio_recordings")

# Ensure the audio output directory exists
os.makedirs(AUDIO_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Device Detection
# ---------------------------------------------------------------------------
def _detect_device() -> tuple[str, str]:
    """Auto-detect the best available compute device and matching type.

    Returns:
        (device, compute_type) — e.g. ("cuda", "float16") or ("cpu", "int8")
    """
    if torch.cuda.is_available():
        return "cuda", "float16"
    return "cpu", "int8"


DEVICE, COMPUTE_TYPE = _detect_device()


# ---------------------------------------------------------------------------
# Faster-Whisper Model
# ---------------------------------------------------------------------------
STT_MODEL_ID = "deepdml/faster-whisper-large-v3-turbo-ct2"

# Beam size for decoding (higher = more accurate but slower)
STT_BEAM_SIZE = 5

# Voice-activity-detection filter — removes non-speech segments
STT_VAD_FILTER = True


# ---------------------------------------------------------------------------
# Audio Recording
# ---------------------------------------------------------------------------
AUDIO_SAMPLE_RATE = 16_000   # 16 kHz — required by Whisper
AUDIO_CHANNELS = 1           # mono
AUDIO_DEFAULT_DURATION = 5   # seconds (for fixed-duration recording)

# Voice-activity parameters for "record until silence" mode
SILENCE_THRESHOLD = 0.01     # RMS amplitude below which we consider silence
SILENCE_DURATION = 2.0       # seconds of consecutive silence to stop recording


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
