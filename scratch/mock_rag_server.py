"""
Local Mock Colab RAG Server
============================
Simulates the Colab GPU RAG server locally for testing.
Runs on port 8009, mimicking the real /health, /embed, /search, /rerank endpoints.
"""
import time
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Mock Colab GPU RAG Server", version="1.0.0")

MODEL_NAME = "all-MiniLM-L6-v2"

# Pre-load a real SentenceTransformer model for accurate embeddings
try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    print(f"[MOCK SERVER] Model '{MODEL_NAME}' loaded for accurate embeddings")
    USE_REAL_MODEL = True
except Exception:
    model = None
    USE_REAL_MODEL = False
    print("[MOCK SERVER] SentenceTransformer not available, using random vectors")


class EmbedRequest(BaseModel):
    text: Optional[str] = None
    texts: Optional[List[str]] = None

class SearchRequest(BaseModel):
    query: str
    documents: List[str]
    top_n: Optional[int] = 5

class RerankRequest(BaseModel):
    query: str
    documents: List[str]


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "model": MODEL_NAME,
        "device": "cuda:0",
        "gpu": "NVIDIA T4 (Mock Local Server)",
        "vram_allocated_mb": 512.0,
        "timestamp": time.time()
    }


@app.post("/embed")
def generate_embeddings_api(req: EmbedRequest):
    t0 = time.perf_counter()
    if req.text:
        if USE_REAL_MODEL:
            vec = model.encode(req.text, convert_to_numpy=True, normalize_embeddings=True)
        else:
            vec = np.ones(384, dtype=np.float32) / np.sqrt(384)
        t_infer = time.perf_counter() - t0
        return {
            "embedding": vec.tolist(),
            "shape": list(vec.shape),
            "inference_time_ms": round(t_infer * 1000, 2)
        }
    elif req.texts:
        if USE_REAL_MODEL:
            vecs = model.encode(req.texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=True)
        else:
            vecs = np.array([np.ones(384, dtype=np.float32) / np.sqrt(384) for _ in req.texts])
        t_infer = time.perf_counter() - t0
        return {
            "embeddings": vecs.tolist(),
            "count": len(vecs),
            "inference_time_ms": round(t_infer * 1000, 2)
        }
    else:
        raise HTTPException(status_code=400, detail="Must provide 'text' or 'texts'.")


@app.post("/search")
def search_api(req: SearchRequest):
    if not req.documents:
        return {"results": [], "query": req.query}

    t0 = time.perf_counter()
    if USE_REAL_MODEL:
        q_vec = model.encode(req.query, convert_to_numpy=True, normalize_embeddings=True)
        doc_vecs = model.encode(req.documents, batch_size=32, convert_to_numpy=True, normalize_embeddings=True)
    else:
        q_vec = np.ones(384, dtype=np.float32) / np.sqrt(384)
        doc_vecs = np.array([np.ones(384, dtype=np.float32) / np.sqrt(384) for _ in req.documents])

    similarities = np.dot(doc_vecs, q_vec)
    ranked_indices = np.argsort(similarities)[::-1][:req.top_n]

    results = []
    for idx in ranked_indices:
        results.append({
            "index": int(idx),
            "document": req.documents[idx],
            "score": float(similarities[idx])
        })

    t_infer = time.perf_counter() - t0
    return {
        "results": results,
        "query": req.query,
        "inference_time_ms": round(t_infer * 1000, 2)
    }


@app.post("/rerank")
def rerank_api(req: RerankRequest):
    search_res = search_api(SearchRequest(query=req.query, documents=req.documents, top_n=len(req.documents)))
    return {"reranked": search_res["results"], "query": req.query}


if __name__ == "__main__":
    print("=" * 60)
    print("Mock Colab RAG GPU Server starting on port 8009...")
    print("Health: http://127.0.0.1:8009/health")
    print("Embed:  http://127.0.0.1:8009/embed")
    print("Search: http://127.0.0.1:8009/search")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8009, log_level="info")
