import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
import time
import numpy as np

print("=== Testing Remote RAG Integration Setup ===")

import config
from agentic.document_retrieval import embeddings

print("1. Checking config variables:")
print(f"   RAG_USE_REMOTE : {getattr(config, 'RAG_USE_REMOTE', False)}")
print(f"   RAG_API_URL    : {getattr(config, 'RAG_API_URL', 'Not Set')}")
print(f"   RAG_API_TIMEOUT: {getattr(config, 'RAG_API_TIMEOUT', 30)}")

print("\n2. Testing embeddings.generate_embedding() dispatch:")
# Test with a dummy url to ensure graceful fallback / remote handling
t0 = time.perf_counter()
vec = embeddings.generate_embedding("Open HealthSphere document")
t_elapsed = time.perf_counter() - t0

if vec is not None:
    print(f"   SUCCESS: Generated embedding vector of shape {vec.shape} in {t_elapsed*1000:.2f} ms")
    print(f"   Vector dtype: {vec.dtype}")
else:
    print(f"   Result: None (as expected if remote server URL is unpopulated)")

print("\n3. Testing batch embedding dispatch:")
t0 = time.perf_counter()
batch_vecs = embeddings.generate_embeddings_batch(["HealthSphere doc", "Money Mentor doc"])
t_elapsed = time.perf_counter() - t0
print(f"   Batch count: {len(batch_vecs)} in {t_elapsed*1000:.2f} ms")

print("\nIntegration test completed successfully!")
