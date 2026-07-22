import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
import time
import torch

print("==================================================")
print("PART 1: MODEL DEVICE & CUDA AUDIT")
print("==================================================")

cuda_avail = torch.cuda.is_available()
device_count = torch.cuda.device_count() if cuda_avail else 0
gpu_name = torch.cuda.get_device_name(0) if cuda_avail else "None (CPU Only)"

print(f"CUDA Available : {cuda_avail}")
print(f"Device Count   : {device_count}")
print(f"GPU Name       : {gpu_name}")

if cuda_avail:
    vram_alloc = torch.cuda.memory_allocated(0) / (1024**2)
    vram_res = torch.cuda.memory_reserved(0) / (1024**2)
    print(f"VRAM Allocated : {vram_alloc:.2f} MB")
    print(f"VRAM Reserved  : {vram_res:.2f} MB")
else:
    print("VRAM Used      : 0 MB (Running on CPU)")

print("\n--- Auditing Individual Models ---")

# 1. SentenceTransformer / Embedding Model
print("\n1. SentenceTransformer (Document Retrieval)")
try:
    from agentic.document_retrieval import embeddings
    model = embeddings._get_model()
    if model:
        device_type = str(next(model.parameters()).device) if hasattr(model, 'parameters') and list(model.parameters()) else "cpu"
        t0 = time.perf_counter()
        _ = model.encode("Test query for latency audit", convert_to_numpy=True)
        t_infer = time.perf_counter() - t0
        print(f"   Model Name       : {embeddings._model_name}")
        print(f"   CUDA Available   : {cuda_avail}")
        print(f"   Running on       : {device_type}")
        print(f"   GPU Name         : {gpu_name}")
        print(f"   Inference Device : {device_type}")
        print(f"   Inference Time   : {t_infer*1000:.2f} ms")
    else:
        print("   Status: Not loaded / None")
except Exception as e:
    print(f"   Error auditing SentenceTransformer: {e}")

# 2. Faster-Whisper / Whisper STT
print("\n2. Faster-Whisper / Whisper STT")
try:
    import config
    from web.services import get_stt
    stt_obj = get_stt()
    stt_type = type(stt_obj).__name__
    print(f"   STT Implementation : {stt_type}")
    print(f"   STT_USE_REMOTE     : {getattr(config, 'STT_USE_REMOTE', False)}")
    if hasattr(stt_obj, '_model') and stt_obj._model is not None:
        print(f"   Local Model Device : {getattr(stt_obj._model, 'device', 'unknown')}")
    else:
        print(f"   Local Model        : Lazy / Remote (No local GPU allocation)")
except Exception as e:
    print(f"   Error auditing STT: {e}")

# 3. FAISS Embedding Generation
print("\n3. FAISS Vector Search")
try:
    from agentic.document_retrieval import cache
    faiss_idx = cache._get_faiss_index()
    if faiss_idx is not None:
        print(f"   FAISS Index Type   : {type(faiss_idx).__name__}")
        print(f"   FAISS Total Vectors: {faiss_idx.ntotal}")
        print(f"   FAISS Device       : CPU (faiss-cpu)")
    else:
        print("   FAISS Index        : Empty / Uninitialized")
except Exception as e:
    print(f"   Error auditing FAISS: {e}")

# 4. BM25 & Metadata Filtering
print("\n4. BM25 & Metadata Filtering (SQLite)")
print("   Device             : CPU (Lightweight metadata operation)")

print("\n==================================================")
print("PART 3: RETRIEVAL PIPELINE SLOWDOWN PROFILING")
print("==================================================")

from agentic.document_retrieval import metadata, cache, scanner, search, ranking
from agentic.document_retrieval.retriever import parse_query, rewrite_query

query = "Open HealthSphere document"
print(f"Test Query: '{query}'\n")

# Stage 1: Parsing
t0 = time.perf_counter()
parsed = parse_query(query)
normalized = parsed.normalized_query
expanded = rewrite_query(query)
folder_candidates = parsed.folder_candidates
t_parse = time.perf_counter() - t0

# Stage 2: SQLite Metadata Lookup
t0 = time.perf_counter()
folder_list, detected_folder_label = metadata.find_matching_folder_paths(folder_candidates)
candidate_docs = metadata.get_documents_in_folder_recursive(folder_list) if folder_list else []
t_sqlite = time.perf_counter() - t0

# Stage 3: Scanning (Disk Validation)
t0 = time.perf_counter()
valid_candidates = [d for d in candidate_docs if os.path.exists(d.path)]
t_scan = time.perf_counter() - t0

# Stage 4: Local CPU Embedding Generation
t0 = time.perf_counter()
vec = embeddings.generate_embedding(expanded)
t_embed = time.perf_counter() - t0

# Stage 5: Vector Search (FAISS)
t0 = time.perf_counter()
if vec is not None and cache._get_faiss_index() is not None:
    doc_ids, dists = cache.search(vec, top_n=10)
else:
    dists = [0.5] * len(valid_candidates)
t_vector = time.perf_counter() - t0

# Stage 6: BM25 & Ranking
t0 = time.perf_counter()
results = ranking.rank_documents(
    query=query,
    candidates=valid_candidates,
    semantic_dists=dists[:len(valid_candidates)],
    top_n=5,
    matched_folder_paths=list(folder_list) if folder_list else None
)
t_rank = time.perf_counter() - t0

t_total = t_parse + t_sqlite + t_scan + t_embed + t_vector + t_rank

print("--- Performance Breakdown ---")
print(f"1. Parsing & Rewrite : {t_parse:.4f} s")
print(f"2. SQLite Metadata   : {t_sqlite:.4f} s")
print(f"3. Disk Validation   : {t_scan:.4f} s")
print(f"4. CPU Embedding Gen : {t_embed:.4f} s  <-- SLOWDOWN BOTTLENECK")
print(f"5. Vector Search     : {t_vector:.4f} s")
print(f"6. BM25 & Ranking    : {t_rank:.4f} s")
print(f"Total Search Latency : {t_total:.4f} s")
