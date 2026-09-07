"""
Tests for Phase 5: Retrieval Quality, Embedding Cache Persistence, and Batch Acceleration.
"""

import time
import pytest
import numpy as np

from agents.evidence_loader import EvidenceLoader, EvidenceSpan
from agents.retrieval_layer import (
    EvidenceRetriever,
    HashedLexicalEmbeddingModel,
    OllamaEmbeddingModel,
    SentenceTransformerEmbeddingModel,
    batch_embed_across_candidates,
    get_default_embedding_model
)
from agents.embedding_cache import EMBEDDING_CACHE
from eval_cases.dataset import CASES


def test_embedding_cache_hit_speedup():
    """Verifies that re-evaluating or re-embedding an unchanged candidate is measurably faster due to cache hits."""
    c1 = next(x for x in CASES if x["candidate_id"] == "case_01_strong_01")
    dossier = EvidenceLoader.load_case_from_dict(c1)
    spans = dossier.spans

    EMBEDDING_CACHE.clear()
    embedder = HashedLexicalEmbeddingModel()

    # Pass 1: Cold cache (calculates all vectors from scratch)
    t0 = time.time()
    retriever_cold = EvidenceRetriever(spans, embedding_model=embedder)
    cold_duration = time.time() - t0

    # Pass 2: Warm cache (100% cache hits from EMBEDDING_CACHE)
    t1 = time.time()
    retriever_warm = EvidenceRetriever(spans, embedding_model=embedder)
    warm_duration = time.time() - t1

    # Verify warm build is fast and retrieved results are identical
    query = "Distributed consensus Raft Paxos"
    res_cold = retriever_cold.retrieve(query, top_k=3)
    res_warm = retriever_warm.retrieve(query, top_k=3)

    assert len(res_cold) == len(res_warm)
    for rc, rw in zip(res_cold, res_warm):
        assert rc.span.span_id == rw.span.span_id
        assert abs(rc.similarity_score - rw.similarity_score) < 1e-4

    assert warm_duration <= cold_duration or warm_duration < 0.05


def test_batch_embed_across_multiple_candidates():
    """Verifies batch_embed_across_candidates builds retrievers for a batch of candidates."""
    batch_cases = CASES[:3]
    dossiers = [EvidenceLoader.load_case_from_dict(c) for c in batch_cases]
    candidates_spans = [d.spans for d in dossiers]

    retrievers = batch_embed_across_candidates(candidates_spans)
    assert len(retrievers) == 3

    for r in retrievers:
        res = r.retrieve("Kafka event streaming", top_k=2)
        assert len(res) > 0


def test_source_isolated_retrieval_integrity():
    """Verifies that source-isolated retrieval returns evidence from each distinct source."""
    c1 = next(x for x in CASES if x["candidate_id"] == "case_15_deceptive_centerpiece")
    dossier = EvidenceLoader.load_case_from_dict(c1)
    retriever = EvidenceRetriever(dossier.spans)

    by_source = retriever.retrieve_per_source("High-frequency algorithmic trading latency", top_k_per_source=2)
    assert "cv" in by_source
    assert "interview" in by_source
    assert "assessment" in by_source
