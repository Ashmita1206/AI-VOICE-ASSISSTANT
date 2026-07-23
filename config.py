"""
AI Voice Assistant — Central Configuration
==========================================

All configurable settings live here. Import this module anywhere
you need access to paths, model parameters, or audio settings.
Settings are loaded from environment variables if present.
"""

import os
import torch
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

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
STT_MODEL_ID = os.getenv("STT_MODEL_ID", "deepdml/faster-whisper-large-v3-turbo-ct2")

# Beam size for decoding (higher = more accurate but slower)
STT_BEAM_SIZE = int(os.getenv("STT_BEAM_SIZE", "5"))

# Voice-activity-detection filter — removes non-speech segments
STT_VAD_FILTER = os.getenv("STT_VAD_FILTER", "True").lower() == "true"


# ---------------------------------------------------------------------------
# Audio Recording
# ---------------------------------------------------------------------------
AUDIO_SAMPLE_RATE = 16_000   # 16 kHz — required by Whisper
AUDIO_CHANNELS = 1           # mono
AUDIO_DEFAULT_DURATION = 5   # seconds (for fixed-duration recording)

# Voice-activity parameters for "record until silence" mode
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.01"))
SILENCE_DURATION = float(os.getenv("SILENCE_DURATION", "2.0"))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# ---------------------------------------------------------------------------
# Remote LLM (Colab) Configuration
# ---------------------------------------------------------------------------
COLAB_API_URL = os.getenv("COLAB_API_URL", "https://evaluator-agreeing-plenty.ngrok-free.dev")
COLAB_TIMEOUT = int(os.getenv("COLAB_TIMEOUT", "120"))


# ---------------------------------------------------------------------------
# Remote STT (Colab) Configuration
# ---------------------------------------------------------------------------
# Set STT_USE_REMOTE=true in your .env to route transcription to the
# Colab-hosted Faster-Whisper GPU server instead of running locally.
#
# STT_API_URL   — full URL to the /transcribe endpoint exposed by colab_stt_server.ipynb
#                 e.g. https://abcd1234.ngrok-free.app/transcribe
# STT_API_TIMEOUT — HTTP timeout for transcription requests (default: 60s)
# ---------------------------------------------------------------------------
STT_USE_REMOTE  = os.getenv("STT_USE_REMOTE", "false").lower() == "true"
STT_API_URL     = os.getenv("STT_API_URL", "https://common-sketch-cornmeal.ngrok-free.dev/transcribe")
STT_API_TIMEOUT = int(os.getenv("STT_API_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# Remote RAG Embedding Retriever (Colab GPU) Configuration
# ---------------------------------------------------------------------------
# Set RAG_USE_REMOTE=true in your .env to route embedding generation to
# the Colab-hosted GPU server instead of computing on local CPU.
# ---------------------------------------------------------------------------
RAG_USE_REMOTE  = os.getenv("RAG_USE_REMOTE", "true").lower() == "true"
RAG_API_URL     = os.getenv("RAG_API_URL", os.getenv("COLAB_API_URL", "https://evaluator-agreeing-plenty.ngrok-free.dev"))
RAG_API_TIMEOUT = int(os.getenv("RAG_API_TIMEOUT", "30"))

