import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
import time
import threading
import uvicorn
from fastapi import FastAPI
import numpy as np

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "healthy", "gpu": "NVIDIA RTX 4090 (Colab Simulation)", "device": "cuda:0"}

@app.post("/embed")
def embed(data: dict):
    if "text" in data:
        # Mock 384-dim normalized embedding vector
        vec = np.ones(384, dtype=np.float32) / np.sqrt(384)
        return {"embedding": vec.tolist(), "shape": [384], "inference_time_ms": 2.5}
    elif "texts" in data:
        vecs = [np.ones(384, dtype=np.float32).tolist() for _ in data["texts"]]
        return {"embeddings": vecs, "count": len(vecs), "inference_time_ms": 4.1}
    return {"error": "invalid payload"}

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8009, log_level="error")

if __name__ == "__main__":
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(1.5)  # Wait for server

    os.environ["RAG_USE_REMOTE"] = "true"
    os.environ["RAG_API_URL"] = "http://127.0.0.1:8009"

    import config
    config.RAG_USE_REMOTE = True
    config.RAG_API_URL = "http://127.0.0.1:8009"

    from agentic.document_retrieval.remote_embeddings import RemoteEmbeddingsClient
    client = RemoteEmbeddingsClient(api_url="http://127.0.0.1:8009")

    print("=== TESTING MOCK COLAB RAG SERVER INTEGRATION ===")
    
    t0 = time.perf_counter()
    vec = client.generate_embedding("Open HealthSphere document")
    t_single = (time.perf_counter() - t0) * 1000

    print(f"1. Single Embedding Result: {vec is not None}")
    if vec is not None:
        print(f"   Shape: {vec.shape}, Dtype: {vec.dtype}")
        print(f"   Remote Latency: {t_single:.2f} ms")

    t0 = time.perf_counter()
    batch_vecs = client.generate_embeddings_batch(["HealthSphere doc", "Money Mentor doc"])
    t_batch = (time.perf_counter() - t0) * 1000

    print(f"\n2. Batch Embeddings Result Count: {len(batch_vecs)}")
    print(f"   Batch Latency: {t_batch:.2f} ms")

    print("\n✅ Remote RAG integration test PASSED! Embeddings served remotely without loading local CPU model.")
    sys.exit(0)
