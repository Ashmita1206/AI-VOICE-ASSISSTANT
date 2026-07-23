"""
Document Retrieval Embeddings
=============================

Generates semantic embeddings using Google Colab GPU (Remote) or SentenceTransformers (Local Fallback).
"""

import logging
import os
from typing import List, Optional
import numpy as np

import config as global_config
from agentic.document_retrieval import config

logger = logging.getLogger(__name__)

_model = None
_model_name = None
_model_load_attempted = False
_remote_client = None

def _get_remote_client():
    global _remote_client
    use_remote = getattr(global_config, "RAG_USE_REMOTE", True)
    rag_url = getattr(global_config, "RAG_API_URL", os.getenv("RAG_API_URL", ""))
    if use_remote and rag_url:
        if _remote_client is None:
            from agentic.document_retrieval.remote_embeddings import RemoteEmbeddingsClient
            _remote_client = RemoteEmbeddingsClient(api_url=rag_url)
        return _remote_client
    return None

def _get_model():
    """Lazy-load local SentenceTransformer model if remote client is not active."""
    global _model, _model_name, _model_load_attempted
    if _model is not None:
        return _model
    if _model_load_attempted:
        return None
        
    _model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        
        # Try primary model first
        try:
            logger.info(f"[EMBEDDINGS] Loading primary model locally: {config.PRIMARY_EMBEDDING_MODEL}")
            _model = SentenceTransformer(config.PRIMARY_EMBEDDING_MODEL)
            _model_name = config.PRIMARY_EMBEDDING_MODEL
        except Exception as e:
            logger.warning(f"[EMBEDDINGS] Failed to load primary model: {e}")
            logger.info(f"[EMBEDDINGS] Falling back to: {config.FALLBACK_EMBEDDING_MODEL}")
            _model = SentenceTransformer(config.FALLBACK_EMBEDDING_MODEL)
            _model_name = config.FALLBACK_EMBEDDING_MODEL
            
        logger.info(f"[EMBEDDINGS] Local model loaded successfully: {_model_name}")
        return _model
    except ImportError:
        logger.error("[EMBEDDINGS] sentence-transformers not installed.")
        return None
    except Exception as e:
        logger.error(f"[EMBEDDINGS] Failed to load embedding model completely: {e}")
        return None

def generate_embedding(text: str) -> Optional[np.ndarray]:
    """Encode text as a float32 numpy vector (normalized)."""
    remote = _get_remote_client()
    if remote is not None:
        vec = remote.generate_embedding(text)
        if vec is not None:
            return vec
        logger.warning("[EMBEDDINGS] Remote embedding returned None, attempting local fallback...")

    model = _get_model()
    if model is None:
        return None
        
    snippet = text[:config.MAX_EMBED_CHARS].strip()
    if not snippet:
        return None
        
    try:
        vector = model.encode(snippet, convert_to_numpy=True, normalize_embeddings=True)
        return vector.astype(np.float32)
    except Exception as e:
        logger.warning(f"[EMBEDDINGS] Failed to encode text: {e}")
        return None

def generate_embeddings_batch(texts: List[str]) -> List[Optional[np.ndarray]]:
    """Encode a batch of texts."""
    remote = _get_remote_client()
    if remote is not None:
        vecs = remote.generate_embeddings_batch(texts)
        if any(v is not None for v in vecs):
            return vecs
        logger.warning("[EMBEDDINGS] Remote batch embeddings returned empty, attempting local fallback...")

    model = _get_model()
    if model is None:
        return [None] * len(texts)
        
    snippets = [t[:config.MAX_EMBED_CHARS].strip() for t in texts]
    
    valid_indices = [i for i, s in enumerate(snippets) if s]
    valid_snippets = [s for s in snippets if s]
    
    results = [None] * len(texts)
    
    if not valid_snippets:
        return results
        
    try:
        vectors = model.encode(valid_snippets, batch_size=32, convert_to_numpy=True, normalize_embeddings=True)
        for idx, vec in zip(valid_indices, vectors):
            results[idx] = vec.astype(np.float32)
        return results
    except Exception as e:
        logger.warning(f"[EMBEDDINGS] Failed to encode batch: {e}")
        return results

