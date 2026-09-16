"""
Parity test comparing retrieval behavior between embedding backends.
Ensures static/hashed and transformer backends maintain valid evidence span retrieval.
"""

import pytest
import numpy as np
from agents.evidence_loader import EvidenceSpan
from agents.retrieval_layer import (
    EvidenceRetriever,
    HashedLexicalEmbeddingModel,
    Model2VecEmbeddingModel,
    SentenceTransformerEmbeddingModel
)


def test_embedding_backends_produce_valid_normalized_vectors():
    texts = [
        "Senior Python Engineer with 6 years experience in distributed microservices.",
        "Led incident response for high-throughput payment processing pipelines.",
        "Candidate showed weak answers on database replication and consensus protocols."
    ]

    hashed = HashedLexicalEmbeddingModel()
    h_vecs = hashed.embed_texts(texts)
    assert h_vecs.shape == (3, 384)
    norms = np.linalg.norm(h_vecs, axis=1)
    np.testing.assert_allclose(norms, np.ones(3), atol=1e-5)

    m2v = Model2VecEmbeddingModel()
    m_vecs = m2v.embed_texts(texts)
    assert m_vecs.shape[0] == 3
    norms = np.linalg.norm(m_vecs, axis=1)
    np.testing.assert_allclose(norms, np.ones(3), atol=1e-5)


def test_retriever_span_overlap_between_backends():
    spans = [
        EvidenceSpan(span_id="cv_01", source_file="cv.txt", document_type="cv", section="experience", text="Extensive Python backend development and FastAPI microservices."),
        EvidenceSpan(span_id="cv_02", source_file="cv.txt", document_type="cv", section="skills", text="PostgreSQL database query optimization and partition management."),
        EvidenceSpan(span_id="int_01", source_file="interview.txt", document_type="interview", section="tech", text="Candidate described architecture of distributed consensus cluster."),
        EvidenceSpan(span_id="ass_01", source_file="assessment.txt", document_type="assessment", section="coding", text="Implemented distributed task queue with retry logic and rate limits."),
        EvidenceSpan(span_id="cv_03", source_file="cv.txt", document_type="cv", section="devops", text="Docker containerization, Kubernetes helm charts, CI/CD pipelines.")
    ]

    retriever_hashed = EvidenceRetriever(spans, embedding_model=HashedLexicalEmbeddingModel())
    retriever_m2v = EvidenceRetriever(spans, embedding_model=Model2VecEmbeddingModel())

    query = "Python distributed systems microservices"
    results_hashed = retriever_hashed.retrieve(query, top_k=3)
    results_m2v = retriever_m2v.retrieve(query, top_k=3)

    assert len(results_hashed) >= 1
    assert len(results_m2v) >= 1

    ids_hashed = {r.span.span_id for r in results_hashed}
    ids_m2v = {r.span.span_id for r in results_m2v}

    # At least top relevant span (cv_01 / ass_01) should overlap
    overlap = ids_hashed.intersection(ids_m2v)
    assert len(overlap) >= 1, f"Expected span overlap between backends, got {ids_hashed} vs {ids_m2v}"
