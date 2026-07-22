"""
Remote RAG Embeddings Client
============================

Delegates embedding generation to the Google Colab GPU-hosted RAG Retrieval Server over HTTP.
Returns float32 numpy arrays byte-for-byte compatible with local `generate_embedding`.
"""

import logging
import os
import time
from typing import List, Optional
import numpy as np
import requests

import config

logger = logging.getLogger(__name__)

class RemoteEmbeddingsClient:
    """HTTP client that delegates embedding computations to Google Colab GPU."""

    def __init__(self, api_url: Optional[str] = None, timeout: int = 30):
        base_url = api_url or getattr(config, "RAG_API_URL", "") or os.getenv("RAG_API_URL", "")
        base_url = base_url.rstrip("/")
        if base_url.endswith("/embed"):
            self.embed_url = base_url
            self.base_url = base_url[:-6]
        else:
            self.base_url = base_url
            self.embed_url = f"{base_url}/embed" if base_url else ""

        self.timeout = timeout
        logger.info(f"[REMOTE EMBEDDINGS] Initialized with endpoint: {self.embed_url}")

    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Request embedding for a single text string from Colab GPU."""
        if not self.embed_url:
            logger.warning("[REMOTE EMBEDDINGS] No RAG_API_URL configured.")
            return None

        text = text[:1000].strip()
        if not text:
            return None

        try:
            resp = requests.post(
                self.embed_url,
                json={"text": text},
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                if "embedding" in data:
                    return np.array(data["embedding"], dtype=np.float32)
            else:
                logger.warning(f"[REMOTE EMBEDDINGS] Server returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[REMOTE EMBEDDINGS] Failed to fetch remote embedding: {e}")

        return None

    def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[np.ndarray]]:
        """Request embeddings for a batch of texts from Colab GPU."""
        if not self.embed_url or not texts:
            return [None] * len(texts)

        snippets = [t[:1000].strip() for t in texts]
        valid_indices = [i for i, s in enumerate(snippets) if s]
        valid_snippets = [s for s in snippets if s]

        results = [None] * len(texts)
        if not valid_snippets:
            return results

        try:
            resp = requests.post(
                self.embed_url,
                json={"texts": valid_snippets},
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                if "embeddings" in data:
                    embeddings_list = data["embeddings"]
                    for idx, vec in zip(valid_indices, embeddings_list):
                        results[idx] = np.array(vec, dtype=np.float32)
                    return results
            else:
                logger.warning(f"[REMOTE EMBEDDINGS] Batch server returned HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"[REMOTE EMBEDDINGS] Failed to fetch remote batch embeddings: {e}")

        return results
