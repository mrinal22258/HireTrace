"""
Unit tests for LRU-bounded embedding cache.
Validates:
1. Eviction of oldest entries when capacity is exceeded.
2. Persistence to disk and reloading from npz.
3. Configurable max size via EMBEDDING_CACHE_MAX_ENTRIES env var.
"""

import os
import shutil
import tempfile
import numpy as np
import pytest

from agents.embedding_cache import EmbeddingCache


@pytest.fixture
def temp_cache_dir():
    d = tempfile.mkdtemp(prefix="ht_cache_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_lru_cache_eviction_when_capacity_exceeded(temp_cache_dir):
    """Cache bounded to 3 entries must evict oldest entry when 4th is added."""
    cache = EmbeddingCache(cache_dir=temp_cache_dir, max_entries=3)
    assert cache.max_entries == 3

    vec1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    vec2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    vec3 = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    vec4 = np.array([1.0, 1.0, 1.0], dtype=np.float32)

    cache.set_chunk_embedding("text1", vec1)
    cache.set_chunk_embedding("text2", vec2)
    cache.set_chunk_embedding("text3", vec3)

    assert len(cache._chunk_cache) == 3
    assert np.allclose(cache.get_chunk_embedding("text1"), vec1)

    # Adding 4th entry evicts the least recently used
    cache.set_chunk_embedding("text4", vec4)
    assert len(cache._chunk_cache) == 3

    # text2 was least recently accessed (since we accessed text1 before adding text4)
    assert cache.get_chunk_embedding("text2") is None
    assert np.allclose(cache.get_chunk_embedding("text1"), vec1)
    assert np.allclose(cache.get_chunk_embedding("text4"), vec4)


def test_lru_cache_disk_persistence_roundtrip(temp_cache_dir):
    """LRU cache can be persisted to disk and reloaded without data corruption."""
    cache1 = EmbeddingCache(cache_dir=temp_cache_dir, max_entries=5)
    v1 = np.array([0.5, 0.5], dtype=np.float32)
    v2 = np.array([0.9, 0.1], dtype=np.float32)

    cache1.set_chunk_embedding("queryA", v1)
    cache1.set_chunk_embedding("queryB", v2)
    cache1.save_to_disk()

    # Re-open new instance from disk
    cache2 = EmbeddingCache(cache_dir=temp_cache_dir, max_entries=5)
    assert len(cache2._chunk_cache) == 2
    assert np.allclose(cache2.get_chunk_embedding("queryA"), v1)
    assert np.allclose(cache2.get_chunk_embedding("queryB"), v2)


def test_lru_cache_env_var_configuration(temp_cache_dir, monkeypatch):
    """EMBEDDING_CACHE_MAX_ENTRIES env var controls default max_entries."""
    monkeypatch.setenv("EMBEDDING_CACHE_MAX_ENTRIES", "42")
    cache = EmbeddingCache(cache_dir=temp_cache_dir)
    assert cache.max_entries == 42
    assert cache._chunk_cache.maxsize == 42
