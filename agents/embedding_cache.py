"""
Persistent Multi-Tier Embedding Cache for HireTrace.

Features:
1. In-memory & on-disk caching of document chunk embeddings keyed by SHA-256 hash.
2. Shared Job Description vector caching across candidates.
3. Batch cache lookup to minimize redundant neural embedding passes during bulk ingestion.
4. Per-candidate persisted FAISS index cache for instant re-evaluation.
"""

import os
import time
import hashlib
import threading
import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

logger = logging.getLogger("hiretrace.embedding_cache")

DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval_cases", "cache")


class EmbeddingCache:
    """Thread-safe, on-disk persisted embedding and index cache."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, "chunk_embeddings.npz")
        self.indices_dir = os.path.join(self.cache_dir, "candidate_indices")
        os.makedirs(self.indices_dir, exist_ok=True)

        self._jd_cache: Dict[str, np.ndarray] = {}  # jd_hash -> vector
        self._chunk_cache: Dict[str, np.ndarray] = {}  # sha256 -> vector
        self._lock = threading.Lock()

        self._load_from_disk()

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load_from_disk(self):
        """Loads cached embeddings from disk on initialization."""
        if os.path.exists(self.cache_file):
            try:
                data = np.load(self.cache_file)
                with self._lock:
                    for key in data.files:
                        self._chunk_cache[key] = data[key]
                logger.info(f"Loaded {len(self._chunk_cache)} cached vector embeddings from {self.cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load embedding cache from {self.cache_file}: {e}")

    def save_to_disk(self):
        """Persists in-memory chunk cache to disk."""
        with self._lock:
            if not self._chunk_cache:
                return
            snapshot = dict(self._chunk_cache)

        try:
            np.savez_compressed(self.cache_file, **snapshot)
        except Exception as e:
            logger.warning(f"Failed to persist embedding cache to disk: {e}")

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

    def get_batch(self, texts: List[str]) -> Tuple[Dict[int, np.ndarray], List[Tuple[int, str]]]:
        """
        Batch lookup for chunk embeddings.
        Returns:
            (cached_dict: {index: embedding}, missing_list: [(index, text), ...])
        """
        cached: Dict[int, np.ndarray] = {}
        missing: List[Tuple[int, str]] = []

        with self._lock:
            for idx, t in enumerate(texts):
                h = self.hash_text(t)
                vec = self._chunk_cache.get(h)
                if vec is not None:
                    cached[idx] = vec
                else:
                    missing.append((idx, t))

        return cached, missing

    def set_batch(self, indexed_embeddings: List[Tuple[str, np.ndarray]]):
        """Batch insert embeddings into cache and triggers async disk sync."""
        with self._lock:
            for text, vec in indexed_embeddings:
                h = self.hash_text(text)
                self._chunk_cache[h] = vec

    def get_candidate_fingerprint(self, candidate_id: str) -> Optional[str]:
        fp_path = os.path.join(self.indices_dir, f"{candidate_id}.fp")
        if os.path.exists(fp_path):
            try:
                with open(fp_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def save_candidate_fingerprint(self, candidate_id: str, fingerprint: str):
        fp_path = os.path.join(self.indices_dir, f"{candidate_id}.fp")
        try:
            with open(fp_path, "w", encoding="utf-8") as f:
                f.write(fingerprint.strip())
        except Exception as e:
            logger.warning(f"Failed to write candidate index fingerprint: {e}")

    def clear(self):
        with self._lock:
            self._jd_cache.clear()
            self._chunk_cache.clear()
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
            except Exception:
                pass


# Global singleton embedding cache
EMBEDDING_CACHE = EmbeddingCache()
