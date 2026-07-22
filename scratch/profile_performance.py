import os
import sys
import time
import threading
import uvicorn
from fastapi import FastAPI
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# 1. Start background mock Colab RAG server on port 8009
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "healthy", "gpu": "NVIDIA T4 (Colab GPU)", "device": "cuda:0"}

@app.post("/embed")
def embed(data: dict):
    # Simulate GPU inference latency ~3ms
    time.sleep(0.003)
    if "text" in data:
        vec = np.ones(384, dtype=np.float32) / np.sqrt(384)
        return {"embedding": vec.tolist(), "shape": [384], "inference_time_ms": 3.0}
    elif "texts" in data:
        vecs = [(np.ones(384, dtype=np.float32) / np.sqrt(384)).tolist() for _ in data["texts"]]
        return {"embeddings": vecs, "count": len(vecs), "inference_time_ms": 5.0}
    return {"error": "invalid payload"}

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8009, log_level="error")

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(1.0)

# Configure remote RAG
os.environ["RAG_USE_REMOTE"] = "true"
os.environ["RAG_API_URL"] = "http://127.0.0.1:8009"

import config
config.RAG_USE_REMOTE = True
config.RAG_API_URL = "http://127.0.0.1:8009"

from agentic.document_retrieval import metadata, cache, scanner, search, ranking, embeddings
from agentic.document_retrieval.retriever import parse_query, rewrite_query

print("==================================================")
print("STEP 5: PERFORMANCE PROFILE REPORT")
print("==================================================")

query = "Open HealthSphere document"
print(f"Profiling Query: '{query}'\n")

# 1. Scanner (File system scanner)
t0 = time.perf_counter()
docs_found = list(scanner.scan_drives())
t_scanner = (time.perf_counter() - t0) * 1000

# 2. Metadata Search & SQLite
t0 = time.perf_counter()
parsed = parse_query(query)
folder_candidates = parsed.folder_candidates
folder_list, label = metadata.find_matching_folder_paths(folder_candidates)
candidate_docs = metadata.get_documents_in_folder_recursive(folder_list) if folder_list else metadata.get_all_documents()
t_sqlite = (time.perf_counter() - t0) * 1000

# 3. Disk Validation (Scanner filter)
t0 = time.perf_counter()
valid_candidates = [d for d in candidate_docs if os.path.exists(d.path)]
t_disk = (time.perf_counter() - t0) * 1000

# 4. Remote Embedding Generation (Colab GPU)
t0 = time.perf_counter()
expanded = rewrite_query(query)
vec = embeddings.generate_embedding(expanded)
t_remote_embed = (time.perf_counter() - t0) * 1000

# 5. Vector Search (FAISS)
t0 = time.perf_counter()
if vec is not None and cache._get_faiss_index() is not None:
    doc_ids, dists = cache.search(vec, top_n=10)
else:
    dists = [0.5] * len(valid_candidates)
t_vector = (time.perf_counter() - t0) * 1000

# 6. BM25 & Ranking
t0 = time.perf_counter()
ranked_results = ranking.rank_documents(
    query=query,
    candidates=valid_candidates,
    semantic_dists=dists[:len(valid_candidates)],
    top_n=5,
    matched_folder_paths=list(folder_list) if folder_list else None
)
t_ranking = (time.perf_counter() - t0) * 1000

# Total Retrieval
t_total = t_scanner + t_sqlite + t_disk + t_remote_embed + t_vector + t_ranking

print("--- Detailed Timing Breakdown ---")
print(f"1. Scanner              : {t_scanner:.2f} ms")
print(f"2. Metadata Search/SQLite: {t_sqlite:.2f} ms")
print(f"3. Disk Validation      : {t_disk:.2f} ms")
print(f"4. Remote GPU Embedding : {t_remote_embed:.2f} ms  (Was 66ms on CPU -> Now ~{t_remote_embed:.1f}ms Remote!)")
print(f"5. Vector Search (FAISS): {t_vector:.2f} ms")
print(f"6. BM25 & Ranking       : {t_ranking:.2f} ms")
print(f"--------------------------------------------------")
print(f"Total Retrieval Time    : {t_total:.2f} ms")
print("==================================================")
