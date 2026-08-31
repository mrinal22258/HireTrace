"""
High-Throughput Embedding Cache for HireTrace.

Caches:
1. Shared Job Description embeddings (computed once on startup, reused across all candidates)
2. Chunk-level embeddings keyed by SHA-256 hash (avoids re-embedding identical text)
"""

import hashlib
import threading
from typing import Dict, List, Optional, Any
import numpy as np


class EmbeddingCache:
    """Thread-safe in-memory vector cache."""

    def __init__(self):
        self._jd_cache: Dict[str, np.ndarray] = {}  # jd_hash -> vector
        self._chunk_cache: Dict[str, np.ndarray] = {}  # sha256 -> vector
        self._lock = threading.Lock()

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_jd_embedding(self, jd_text: str) -> Optional[np.ndarray]:
        h = self.hash_text(jd_text)
        with self._lock:
            return self._jd_cache.get(h)

    def set_jd_embedding(self, jd_text: str, embedding: np.ndarray):
        h = self.hash_text(jd_text)
        with self._lock:
            self._jd_cache[h] = embedding

    def get_chunk_embedding(self, text: str) -> Optional[np.ndarray]:
        h = self.hash_text(text)
        with self._lock:
            return self._chunk_cache.get(h)

    def set_chunk_embedding(self, text: str, embedding: np.ndarray):
        h = self.hash_text(text)
        with self._lock:
            self._chunk_cache[h] = embedding

    def clear(self):
        with self._lock:
            self._jd_cache.clear()
            self._chunk_cache.clear()


# Global singleton embedding cache
EMBEDDING_CACHE = EmbeddingCache()
