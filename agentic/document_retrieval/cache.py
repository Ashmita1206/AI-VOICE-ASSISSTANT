"""
Document Retrieval FAISS Cache
==============================

Manages the FAISS vector index.
"""

import logging
import os
import threading
from typing import List, Tuple

import numpy as np

from agentic.document_retrieval import config

logger = logging.getLogger(__name__)

# Lazy-loaded FAISS index
_index = None
_lock = threading.Lock()

# Dimension depends on the model. BAAI/bge-m3 = 1024. all-MiniLM = 384
_DIMENSION = 1024 if "bge-m3" in config.PRIMARY_EMBEDDING_MODEL else 384

def _get_faiss_index():
    global _index
    if _index is not None:
        return _index
        
    with _lock:
        if _index is not None:
            return _index
            
        try:
            import faiss
            
            if os.path.exists(config.FAISS_INDEX_PATH):
                try:
                    logger.info(f"[FAISS] Loading existing index from {config.FAISS_INDEX_PATH}")
                    _index = faiss.read_index(config.FAISS_INDEX_PATH)
                except Exception as e:
                    logger.error(f"[FAISS] Failed to load index, creating new: {e}")
                    # Create an IndexIDMap to map vectors to our SQLite IDs
                    base_index = faiss.IndexFlatL2(_DIMENSION)
                    _index = faiss.IndexIDMap(base_index)
            else:
                logger.info(f"[FAISS] Creating new index with dimension {_DIMENSION}")
                os.makedirs(os.path.dirname(config.FAISS_INDEX_PATH), exist_ok=True)
                base_index = faiss.IndexFlatL2(_DIMENSION)
                _index = faiss.IndexIDMap(base_index)
                
            return _index
        except ImportError:
            logger.error("[FAISS] faiss-cpu is not installed!")
            return None
        except Exception as e:
            logger.error(f"[FAISS] Initialization failed: {e}")
            return None

def save_index():
    """Save the FAISS index to disk."""
    if _index is not None:
        with _lock:
            try:
                import faiss
                faiss.write_index(_index, config.FAISS_INDEX_PATH)
            except Exception as e:
                logger.error(f"[FAISS] Failed to save index: {e}")

def add_embeddings(doc_ids: List[int], vectors: List[np.ndarray]) -> bool:
    """Add multiple vectors to the index with their SQLite IDs."""
    if not doc_ids or not vectors or len(doc_ids) != len(vectors):
        return False
        
    index = _get_faiss_index()
    if index is None:
        return False
        
    try:
        # Convert to appropriate format
        id_array = np.array(doc_ids, dtype=np.int64)
        vec_array = np.vstack(vectors).astype(np.float32)
        
        with _lock:
            # We don't remove old ones here; we assume caller did if it was an update
            index.add_with_ids(vec_array, id_array)
            save_index()
        return True
    except Exception as e:
        logger.error(f"[FAISS] Failed to add embeddings: {e}")
        return False

def remove_embeddings(doc_ids: List[int]) -> bool:
    """Remove vectors from the index by their ID."""
    if not doc_ids:
        return True
        
    index = _get_faiss_index()
    if index is None:
        return False
        
    try:
        id_array = np.array(doc_ids, dtype=np.int64)
        with _lock:
            index.remove_ids(id_array)
            save_index()
        return True
    except Exception as e:
        logger.error(f"[FAISS] Failed to remove embeddings: {e}")
        return False

def search(query_vector: np.ndarray, top_n: int = 50) -> Tuple[List[int], List[float]]:
    """Search for the most similar vectors. Returns (IDs, Distances)."""
    index = _get_faiss_index()
    if index is None or index.ntotal == 0:
        return [], []
        
    try:
        vec_array = np.expand_dims(query_vector, axis=0).astype(np.float32)
        
        # Determine actual K to fetch
        k = min(top_n, index.ntotal)
        
        distances, indices = index.search(vec_array, k)
        
        # Extract results
        res_ids = []
        res_dists = []
        
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1:  # -1 means no neighbor found (shouldn't happen with k <= ntotal)
                res_ids.append(int(idx))
                res_dists.append(float(dist))
                
        return res_ids, res_dists
    except Exception as e:
        logger.error(f"[FAISS] Search failed: {e}")
        return [], []

def get_faiss_vector_count() -> int:
    """Return total number of vectors in the FAISS index."""
    index = _get_faiss_index()
    return index.ntotal if index is not None else 0
