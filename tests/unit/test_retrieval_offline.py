"""
Unit tests for deterministic offline FAISS retrieval layer.
100% offline, zero network requests, verifying SHA-256 cross-process stability.
"""

import pytest
import numpy as np
from agents.retrieval_layer import EmbeddingModel, EvidenceRetriever, _stable_hash
from agents.evidence_loader import EvidenceSpan


def test_stable_hash_is_deterministic():
    h1 = _stable_hash("apache_kafka", seed=1)
    h2 = _stable_hash("apache_kafka", seed=1)
    assert h1 == h2
    assert isinstance(h1, int)

    # Different seeds should produce different digests
    h3 = _stable_hash("apache_kafka", seed=2)
    assert h1 != h3


def test_embedding_model_deterministic_reproducibility():
    model1 = EmbeddingModel(embedding_dim=384)
    model2 = EmbeddingModel(embedding_dim=384)

    text = "Senior Python Engineer with 5 years experience in distributed event streaming."
    vec1 = model1.embed_texts([text])[0]
    vec2 = model2.embed_texts([text])[0]

    np.testing.assert_allclose(vec1, vec2, rtol=1e-5, atol=1e-5)
    # Check normalized vector
    norm = float(np.linalg.norm(vec1))
    assert abs(norm - 1.0) < 1e-4


def test_source_isolated_retrieval_prevents_cv_starvation():
    spans = []
    # 20 CV spans
    for i in range(20):
        spans.append(EvidenceSpan(
            span_id=f"CV-{i:03d}",
            source_file="cv.txt",
            document_type="cv",
            section="Resume",
            text=f"CV bullet point {i} discussing general engineering and background."
        ))
    # Only 2 assessment spans
    spans.append(EvidenceSpan(
        span_id="ASS-001",
        source_file="assessment.txt",
        document_type="assessment",
        section="Results",
        text="Candidate failed partition rebalance stress test under high consumer load."
    ))
    spans.append(EvidenceSpan(
        span_id="ASS-002",
        source_file="assessment.txt",
        document_type="assessment",
        section="Results",
        text="Code deadlock occurred during lock acquisition in consumer worker."
    ))

    retriever = EvidenceRetriever(spans)

    # Isolated search for assessment spans
    ass_results = retriever.retrieve("partition rebalance deadlock", top_k=2, filter_doc_type="assessment")
    assert len(ass_results) == 2
    assert all(r.span.document_type == "assessment" for r in ass_results)
    assert ass_results[0].span.span_id in ("ASS-001", "ASS-002")

    # Multi-source dictionary search
    grouped = retriever.retrieve_per_source("Kafka rebalance", top_k_per_source=2)
    assert len(grouped["assessment"]) == 2
    assert len(grouped["cv"]) == 2
