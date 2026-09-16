"""
Tests for Phase 2: LLM Output Reliability.

Validates:
1. Self-consistency 3x majority voting in CrossSourceVerificationAgent.
2. Handling of 1-1-1 disagreement splits yielding NEEDS_HUMAN_REVIEW.
3. Structured JSON-schema decoding and Pydantic validation.
"""

import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel
from agents.cross_source_verification_agent import (
    CrossSourceVerificationAgent,
    RequirementVerificationSchema,
    DiscrepancyItemSchema
)
from agents.requirement_mapping_agent import (
    JobRequirement,
    RequirementMappingSchema,
    RequirementItemSchema
)
from agents.evidence_aggregation_agent import AggregatedEvidence
from agents.evidence_loader import EvidenceSpan
from agents.ollama_client import OllamaClient


def test_pydantic_schema_validation_success():
    """Validates that RequirementVerificationSchema accepts valid fields."""
    data = {
        "status": "SUPPORTED",
        "confidence": 0.95,
        "synthesis": "Candidate demonstrates strong AsyncIO skills.",
        "supporting_citations": ["CV-001"],
        "discrepancies": []
    }
    obj = RequirementVerificationSchema.model_validate(data)
    assert obj.status == "SUPPORTED"
    assert obj.confidence == 0.95
    assert obj.supporting_citations == ["CV-001"]


def test_self_consistency_majority_vote_resolves():
    """Validates that a 2-1 vote across 3 passes resolves to the majority status."""
    mock_client = MagicMock()
    mock_client.is_available.return_value = True
    mock_client.backend = "ollama"

    # Pass 1: SUPPORTED, Pass 2: INSUFFICIENT_EVIDENCE, Pass 3: SUPPORTED -> Majority: SUPPORTED
    mock_client.generate_json.side_effect = [
        {"status": "SUPPORTED", "confidence": 0.90, "synthesis": "Supported pass 1", "supporting_citations": ["CV-001"]},
        {"status": "INSUFFICIENT_EVIDENCE", "confidence": 0.60, "synthesis": "Missing details", "supporting_citations": []},
        {"status": "SUPPORTED", "confidence": 0.92, "synthesis": "Supported pass 3", "supporting_citations": ["CV-001"]}
    ]

    agent = CrossSourceVerificationAgent(
        ollama_client=mock_client,
        enable_generic_comparator=False,
        vote_count=3
    )

    span = EvidenceSpan("CV-001", "cv.txt", "cv", "experience", "Built distributed Python services with Kafka.", {})
    from agents.retrieval_layer import RetrievedSpan
    retrieved = RetrievedSpan(span=span, similarity_score=0.85)

    req = JobRequirement("REQ-01", "Python & Kafka", "technical_skills", "Distributed systems in Python", "MUST_HAVE", ["cv"])
    agg = AggregatedEvidence(
        requirement=req,
        cv_spans=[retrieved],
        interview_spans=[],
        assessment_spans=[],
        project_spans=[],
        jd_spans=[],
        sources_present=["cv"]
    )

    verif = agent.verify_requirement(agg)
    assert verif.status == "SUPPORTED"
    assert verif.confidence >= 0.90
    assert mock_client.generate_json.call_count == 3


def test_self_consistency_tie_split_yields_needs_human_review():
    """Validates that a 1-1-1 split across 3 passes produces NEEDS_HUMAN_REVIEW."""
    mock_client = MagicMock()
    mock_client.is_available.return_value = True
    mock_client.backend = "ollama"

    # 1-1-1 3-way split: 1 SUPPORTED, 1 CONTRADICTED, 1 INSUFFICIENT_EVIDENCE
    mock_client.generate_json.side_effect = [
        {"status": "SUPPORTED", "confidence": 0.80, "synthesis": "Appears supported", "supporting_citations": ["CV-001"]},
        {"status": "CONTRADICTED", "confidence": 0.85, "synthesis": "Possible mismatch", "supporting_citations": ["CV-001"]},
        {"status": "INSUFFICIENT_EVIDENCE", "confidence": 0.70, "synthesis": "Inconclusive evidence", "supporting_citations": []}
    ]

    agent = CrossSourceVerificationAgent(
        ollama_client=mock_client,
        enable_generic_comparator=False,
        vote_count=3
    )

    span = EvidenceSpan("CV-001", "cv.txt", "cv", "experience", "Built distributed Python services with Kafka.", {})
    from agents.retrieval_layer import RetrievedSpan
    retrieved = RetrievedSpan(span=span, similarity_score=0.85)

    req = JobRequirement("REQ-01", "Python & Kafka", "technical_skills", "Distributed systems in Python", "MUST_HAVE", ["cv"])
    agg = AggregatedEvidence(
        requirement=req,
        cv_spans=[retrieved],
        interview_spans=[],
        assessment_spans=[],
        project_spans=[],
        jd_spans=[],
        sources_present=["cv"]
    )

    verif = agent.verify_requirement(agg)
    assert verif.status == "NEEDS_HUMAN_REVIEW"
    assert verif.confidence == 0.50
    assert "Self-consistency split" in verif.synthesis
    assert verif.claim_type == "synthesized_inference"
    assert verif.is_grounded is False


def test_ollama_client_validate_and_repair_retry(monkeypatch):
    """Validates that OllamaClient retries with a repair prompt on schema validation failure."""
    client = OllamaClient(base_url="http://127.0.0.1:11434", backend="ollama")
    monkeypatch.setattr(client, "is_available", lambda: True)

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self._json = json_data
            self.status_code = status_code
            self.text = "mock"

        def json(self):
            return self._json

    # Attempt 1 returns invalid schema (missing required fields), Attempt 2 returns valid schema
    responses = [
        MockResponse({"response": '{"invalid": "data"}'}),
        MockResponse({"response": '{"status": "SUPPORTED", "confidence": 0.9, "synthesis": "Valid", "supporting_citations": ["CV-001"]}'})
    ]

    mock_post = MagicMock(side_effect=responses)
    import requests
    monkeypatch.setattr(requests, "post", mock_post)

    out = client.generate_json(
        prompt="Verify candidate",
        schema_model=RequirementVerificationSchema,
        max_retries=1
    )

    assert out.get("status") == "SUPPORTED"
    assert mock_post.call_count == 2
    # Verify the repair instruction was injected into prompt on attempt 2
    second_call_payload = mock_post.call_args_list[1][1]["json"]
    assert "[REPAIR:" in second_call_payload["prompt"]


def test_ollama_client_validate_and_repair_exhaustion_degraded(monkeypatch):
    """Validates that OllamaClient falls back to degraded mode if schema repair is exhausted."""
    client = OllamaClient(base_url="http://127.0.0.1:11434", backend="ollama")
    monkeypatch.setattr(client, "is_available", lambda: True)

    class MockResponse:
        def __init__(self, json_data):
            self._json = json_data
            self.status_code = 200
            self.text = "mock"

        def json(self):
            return self._json

    # Both attempts return invalid schema
    mock_post = MagicMock(return_value=MockResponse({"response": '{"invalid": "data"}'}))
    import requests
    monkeypatch.setattr(requests, "post", mock_post)

    out = client.generate_json(
        prompt="Verify candidate",
        schema_model=RequirementVerificationSchema,
        max_retries=1
    )

    assert out.get("degraded") is True
    assert "SCHEMA_VALIDATION_ERROR" in out.get("error_code")

