import os
import sys
import torch

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import config
from agentic.document_retrieval import embeddings, cache
from web.services import get_stt

print("==================================================")
print("STEP 1: MODEL DEVICE AUDIT REPORT")
print("==================================================")

cuda_available = torch.cuda.is_available()
torch_device = "cuda" if cuda_available else "cpu"

print(f"1. Torch CUDA: {cuda_available}")
print(f"2. Torch Device: {torch_device}")

# SentenceTransformer / Retriever embedding model
st_device = "None / Not Loaded (Remote active)"
retriever_emb_device = "Remote (Google Colab GPU)"
local_loaded = False

if getattr(config, "RAG_USE_REMOTE", True) and getattr(config, "RAG_API_URL", ""):
    remote_enabled = True
    rag_url = getattr(config, "RAG_API_URL", "")
    if embeddings._model is not None:
        local_loaded = True
        st_device = str(next(embeddings._model.parameters()).device) if list(embeddings._model.parameters()) else "cpu"
        retriever_emb_device = f"Local ({st_device})"
else:
    remote_enabled = False
    rag_url = getattr(config, "RAG_API_URL", "")
    st_model = embeddings._get_model()
    if st_model is not None:
        local_loaded = True
        st_device = str(next(st_model.parameters()).device) if list(st_model.parameters()) else "cpu"
        retriever_emb_device = f"Local ({st_device})"

print(f"3. SentenceTransformer Device: {st_device}")

# Whisper device
try:
    stt_obj = get_stt()
    stt_type = type(stt_obj).__name__
    if hasattr(stt_obj, '_model') and stt_obj._model is not None:
        whisper_device = getattr(stt_obj._model, 'device', 'unknown')
    else:
        whisper_device = f"{stt_type} (Lazy/Remote)"
except Exception as e:
    whisper_device = f"Error: {e}"

print(f"4. Whisper Device: {whisper_device}")
print(f"5. Retriever Embedding Device: {retriever_emb_device}")

# FAISS type
try:
    faiss_idx = cache._get_faiss_index()
    if faiss_idx is not None:
        faiss_type = type(faiss_idx).__name__
    else:
        faiss_type = "None / Empty"
except Exception as e:
    faiss_type = f"Error: {e}"

print(f"6. FAISS Type: {faiss_type}")
print(f"7. Remote Embedding Enabled?: {remote_enabled}")
print(f"8. RAG_API_URL: '{rag_url}'")
print(f"9. Whether ANY Embedding Runs Locally: {local_loaded}")
print("==================================================")
