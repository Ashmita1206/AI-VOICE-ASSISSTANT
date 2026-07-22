"""
Document Retrieval Embeddings
=============================

Generates semantic embeddings using SentenceTransformers.
"""

import logging
from typing import List, Optional
import numpy as np

from agentic.document_retrieval import config

logger = logging.getLogger(__name__)

_model = None
_model_name = None
_model_load_attempted = False

def _get_model():
    """Lazy-load the SentenceTransformer model."""
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
            logger.info(f"[EMBEDDINGS] Loading primary model: {config.PRIMARY_EMBEDDING_MODEL}")
            _model = SentenceTransformer(config.PRIMARY_EMBEDDING_MODEL)
            _model_name = config.PRIMARY_EMBEDDING_MODEL
        except Exception as e:
            logger.warning(f"[EMBEDDINGS] Failed to load primary model: {e}")
            logger.info(f"[EMBEDDINGS] Falling back to: {config.FALLBACK_EMBEDDING_MODEL}")
            _model = SentenceTransformer(config.FALLBACK_EMBEDDING_MODEL)
            _model_name = config.FALLBACK_EMBEDDING_MODEL
            
        logger.info(f"[EMBEDDINGS] Model loaded successfully: {_model_name}")
        return _model
    except ImportError:
        logger.error("[EMBEDDINGS] sentence-transformers not installed.")
        return None
    except Exception as e:
        logger.error(f"[EMBEDDINGS] Failed to load embedding model completely: {e}")
        return None

def generate_embedding(text: str) -> Optional[np.ndarray]:
    """Encode text as a float32 numpy vector (normalized)."""
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
    model = _get_model()
    if model is None:
        return [None] * len(texts)
        
    snippets = [t[:config.MAX_EMBED_CHARS].strip() for t in texts]
    
    # We still need to handle empty strings
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
