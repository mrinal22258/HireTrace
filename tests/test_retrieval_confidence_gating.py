"""
Unit tests for Retrieval Confidence Gating in CrossSourceVerificationAgent.
Validates that low similarity matches force INSUFFICIENT_EVIDENCE rather than allowing hallucinated support.
"""

import pytest
from agents.cross_source_verification_agent import CrossSourceVerificationAgent
from agents.evidence_loader import EvidenceSpan
from agents.requirement_mapping_agent import JobRequirement
from agents.retrieval_layer import RetrievedSpan
from agents.evidence_aggregation_agent import AggregatedEvidence
from agents.ollama_client import OllamaClient


def test_retrieval_gating_forces_insufficient_evidence():
    """Verify that when top retrieved spans fall below the similarity threshold, status is forced to INSUFFICIENT_EVIDENCE."""
    agent = CrossSourceVerificationAgent(
        ollama_client=OllamaClient(),
        enable_generic_comparator=False,
        retrieval_similarity_threshold=0.35
    )

    req = JobRequirement(
        req_id="REQ-TEST-01",
        name="Quantum Computing Cryptography",
        category="technical_skills",
        description="Quantum key distribution and cryptographic algorithms",
        importance="NICE_TO_HAVE",
        expected_sources=["cv", "interview"]
    )

    # Low similarity scored span (0.12 < 0.35)
    weak_span = EvidenceSpan(
        span_id="CV-999",
        source_file="cv.txt",
        document_type="cv",
        section="Hobbies",
        text="Enjoys casual chess, hiking, and playing acoustic guitar in spare time."
    )
    agg = AggregatedEvidence(
        requirement=req,
        cv_spans=[RetrievedSpan(span=weak_span, similarity_score=0.12)],
        interview_spans=[],
        assessment_spans=[],
        project_spans=[],
        jd_spans=[],
        sources_present=["cv"]
    )

    verif = agent.verify_requirement(agg)

    assert verif.status == "INSUFFICIENT_EVIDENCE"
    assert verif.confidence >= 0.90
    assert "retrieval confidence" in verif.synthesis.lower() or "retrieval gating" in verif.synthesis.lower()
    assert verif.claim_type == "synthesized_inference"
    assert not verif.is_grounded


def test_retrieval_gating_allows_high_similarity():
    """Verify that when retrieved spans have sufficient similarity, gating passes to standard verification."""
    agent = CrossSourceVerificationAgent(
        ollama_client=OllamaClient(),
        enable_generic_comparator=False,
        retrieval_similarity_threshold=0.20
    )

    req = JobRequirement(
        req_id="REQ-TEST-02",
        name="PostgreSQL Optimization",
        category="technical_skills",
        description="Database partitioning and query performance tuning",
        importance="MUST_HAVE",
        expected_sources=["cv", "interview"]
    )

    # Strong similarity scored span
    strong_span = EvidenceSpan(
        span_id="CV-012",
        source_file="cv.txt",
        document_type="cv",
        section="Experience",
        text="Designed database partitioning strategy on a 6TB PostgreSQL cluster, reducing query times from 8.2s to 350ms."
    )
    agg = AggregatedEvidence(
        requirement=req,
        cv_spans=[RetrievedSpan(span=strong_span, similarity_score=0.45)],
        interview_spans=[],
        assessment_spans=[],
        project_spans=[],
        jd_spans=[],
        sources_present=["cv"]
    )

    verif = agent.verify_requirement(agg)

    # Should not be blocked by retrieval gating
    assert "Retrieval gating" not in verif.synthesis
    assert "CV-012" in verif.supporting_citations
