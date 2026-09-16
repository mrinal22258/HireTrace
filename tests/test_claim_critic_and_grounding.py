"""
Unit tests for ClaimCriticAgent and Grounding Enforcement.
Validates exact quote substring containment, citation ID existence, and automatic downgrade to synthesized inference.
"""

import pytest
from agents.critic_agent import ClaimCriticAgent
from agents.evidence_loader import EvidenceSpan
from agents.cross_source_verification_agent import EvidenceMatrix, RequirementVerification
from agents.recommendation_writer_agent import AssessmentReport


@pytest.fixture
def sample_spans():
    return [
        EvidenceSpan(
            span_id="CV-001",
            source_file="cv.txt",
            document_type="cv",
            section="Summary",
            text="Senior Distributed Systems Engineer with 5+ years experience building Kafka pipelines."
        ),
        EvidenceSpan(
            span_id="INT-001",
            source_file="interview.txt",
            document_type="interview",
            section="Q1",
            text="I led the migration to event-driven microservices handling 50k events per second."
        )
    ]


@pytest.fixture
def mock_matrix():
    return EvidenceMatrix(
        candidate_id="cand_test",
        verifications=[],
        total_requirements=3,
        supported_count=2,
        contradicted_count=0,
        insufficient_count=1,
        all_discrepancies=[],
        consistency_score=90.0
    )


def test_critic_confirms_valid_grounded_claim(sample_spans, mock_matrix):
    critic = ClaimCriticAgent()

    report = AssessmentReport(
        candidate_id="cand_test",
        candidate_name="Test Candidate",
        target_role="Backend Engineer",
        role_fit_score=85.0,
        evidence_consistency_score=90.0,
        quadrant="STRONG MATCH",
        recommendation="Proceed to human review.",
        priority_questions=["Clarify tenure."],
        key_discrepancies=[],
        requirement_table=[
            {
                "req_id": "REQ-01",
                "name": "Event-Driven Microservices",
                "status": "SUPPORTED",
                "display": "✓ SUPPORTED",
                "confidence": 0.90,
                "citations": ["INT-001"],
                "citations_detail": [{
                    "span_id": "INT-001",
                    "quote": "I led the migration to event-driven microservices handling 50k events per second."
                }],
                "synthesis": "Verified via interview.",
                "claim_type": "grounded",
                "is_grounded": True,
                "grounding_rationale": ""
            }
        ],
        unsupported_claim_count=0,
        contradicted_claim_count=0,
        rubric_baseline_score=80.0,
        formatted_terminal_card="REQUIREMENTS\n  Event-Driven Microservices   [PASS] SUPPORTED [GROUNDED: INT-001]"
    )

    reviewed = critic.review_report(report, mock_matrix, sample_spans)

    assert reviewed.requirement_table[0]["is_grounded"] is True
    assert reviewed.requirement_table[0]["claim_type"] == "grounded"
    assert reviewed.grounded_claims_count == 1
    assert reviewed.grounding_rate == 1.0


def test_critic_downgrades_tampered_quote(sample_spans, mock_matrix):
    critic = ClaimCriticAgent()

    report = AssessmentReport(
        candidate_id="cand_test",
        candidate_name="Test Candidate",
        target_role="Backend Engineer",
        role_fit_score=85.0,
        evidence_consistency_score=90.0,
        quadrant="STRONG MATCH",
        recommendation="Proceed to human review.",
        priority_questions=["Clarify tenure."],
        key_discrepancies=[],
        requirement_table=[
            {
                "req_id": "REQ-01",
                "name": "Event-Driven Microservices",
                "status": "SUPPORTED",
                "display": "✓ SUPPORTED",
                "confidence": 0.90,
                "citations": ["INT-001"],
                "citations_detail": [{
                    "span_id": "INT-001",
                    # Tampered quote that does NOT exist in INT-001
                    "quote": "I single-handedly built an autonomous quantum blockchain handling 10 million transactions."
                }],
                "synthesis": "Tampered claim.",
                "claim_type": "grounded",
                "is_grounded": True,
                "grounding_rationale": ""
            }
        ],
        unsupported_claim_count=0,
        contradicted_claim_count=0,
        rubric_baseline_score=80.0,
        formatted_terminal_card="REQUIREMENTS\n  Event-Driven Microservices   [PASS] SUPPORTED [GROUNDED: INT-001]"
    )

    reviewed = critic.review_report(report, mock_matrix, sample_spans)

    req = reviewed.requirement_table[0]
    assert req["is_grounded"] is False
    assert req["claim_type"] == "synthesized_inference"
    assert "not an exact substring" in req["grounding_rationale"]
    assert reviewed.grounded_claims_count == 0
    assert reviewed.synthesized_inferences_count == 1
    assert reviewed.grounding_rate == 0.0


def test_critic_downgrades_nonexistent_citation_id(sample_spans, mock_matrix):
    critic = ClaimCriticAgent()

    report = AssessmentReport(
        candidate_id="cand_test",
        candidate_name="Test Candidate",
        target_role="Backend Engineer",
        role_fit_score=85.0,
        evidence_consistency_score=90.0,
        quadrant="STRONG MATCH",
        recommendation="Proceed to human review.",
        priority_questions=[],
        key_discrepancies=[],
        requirement_table=[
            {
                "req_id": "REQ-02",
                "name": "Kubernetes Orchestration",
                "status": "SUPPORTED",
                "display": "✓ SUPPORTED",
                "confidence": 0.85,
                "citations": ["NON_EXISTENT_SPAN_999"],
                "citations_detail": [],
                "synthesis": "Fictitious citation.",
                "claim_type": "grounded",
                "is_grounded": True,
                "grounding_rationale": ""
            }
        ],
        unsupported_claim_count=0,
        contradicted_claim_count=0,
        rubric_baseline_score=80.0,
        formatted_terminal_card="REQUIREMENTS\n  Kubernetes Orchestration    [PASS] SUPPORTED"
    )

    reviewed = critic.review_report(report, mock_matrix, sample_spans)

    req = reviewed.requirement_table[0]
    assert req["is_grounded"] is False
    assert req["claim_type"] == "synthesized_inference"
    assert "not found in candidate dossier" in req["grounding_rationale"]
    assert reviewed.grounded_claims_count == 0
    assert reviewed.synthesized_inferences_count == 1
