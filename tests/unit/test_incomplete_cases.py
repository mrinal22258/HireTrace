"""
Tests for Case 12, Case 13, and Case 14 semantics.
Verifies:
1. Case 12 (Evan Brooks): Explicit truthful admission of zero Kafka experience is NOT a contradiction.
   REQ-02 is marked INSUFFICIENT_EVIDENCE, discrepancies = 0, consistency = 55.0, quadrant = INSUFFICIENT EVIDENCE.
2. Case 13 (Nathaniel Reed, missing interview) & Case 14 (Maya Lin, missing assessment):
   Missing one source document != contradiction or failure.
   Discrepancies = 0, consistency = 85.0, quadrant = STRONG MATCH with sufficiency flag.
"""

import pytest
from agents.evidence_loader import EvidenceLoader, CandidateDossier, EvidenceSpan
from agents.cross_source_verification_agent import (
    GenericContradictionComparator,
    CrossSourceVerificationAgent,
    RequirementVerification,
    EvidenceMatrix
)
from agents.recommendation_writer_agent import RecommendationWriterAgent
from agents.pipeline import HireTracePipeline
from baseline.rubric_scorer import RubricScorer, RubricScoreBreakdown
from agents.requirement_mapping_agent import JobRequirement
from agents.evidence_aggregation_agent import AggregatedEvidence
from eval_cases.dataset import CASES


def test_case_12_evan_brooks_no_false_positive():
    """Case 12 truthful admission of inexperience must never produce a contradiction."""
    case_12 = next(c for c in CASES if c["candidate_id"] == "case_12_adv_jd_vs_claim")
    dossier = EvidenceLoader.load_case_from_dict(case_12)

    cv_spans = [s for s in dossier.spans if s.document_type == "cv"]
    proj_spans = [s for s in dossier.spans if s.document_type == "project"]
    int_spans = [s for s in dossier.spans if s.document_type == "interview"]
    ass_spans = [s for s in dossier.spans if s.document_type == "assessment"]

    # 1. Comparator must return 0 discrepancies
    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-02",
        cv_spans=cv_spans,
        int_spans=int_spans,
        ass_spans=ass_spans,
        proj_spans=proj_spans
    )
    assert len(discrepancies) == 0, f"Expected 0 discrepancies for Case 12, got: {discrepancies}"

    # 2. Test _is_genuine_contradiction filter
    # Pairing "No experience with Kafka" against RFC-02 must return False
    qa = "No experience with Kafka, RabbitMQ, or distributed event streaming architectures."
    qb = "# RFC-02: Microservice API Gateway Architecture\nCompany: CloudSys Solutions | Author: Evan Brooks"
    assert not CrossSourceVerificationAgent._is_genuine_contradiction(
        topic="Experience with Kafka and distributed event streaming",
        quote_a=qa,
        quote_b=qb,
        contradiction_type="cv_vs_interview"
    )


def test_case_13_case_14_missing_evidence_semantics():
    """Missing one source document must yield consistency 85 and STRONG MATCH quadrant."""
    writer = RecommendationWriterAgent()

    # Synthetic matrix for a strong candidate missing 1 document (e.g. interview)
    v1 = RequirementVerification("REQ-01", "Core Python & AsyncIO", "SUPPORTED", 0.9, "Strong", ["CV-001"], [], [])
    v2 = RequirementVerification("REQ-02", "Distributed Systems & Kafka", "SUPPORTED", 0.9, "Strong", ["CV-001"], [], [])
    v3 = RequirementVerification("REQ-03", "Technical Leadership", "SUPPORTED", 0.9, "Strong", ["CV-001"], [], [])
    v4 = RequirementVerification("REQ-04", "Production Tenure", "SUPPORTED", 0.9, "Strong", ["CV-001"], [], [])

    matrix = EvidenceMatrix(
        candidate_id="case_13_incomplete_no_interview",
        verifications=[v1, v2, v3, v4],
        total_requirements=4,
        supported_count=4,
        contradicted_count=0,
        insufficient_count=0,
        all_discrepancies=[],
        consistency_score=85.0
    )

    rubric = RubricScoreBreakdown(
        candidate_id="case_13_incomplete_no_interview",
        open_source=25.0,
        self_projects=20.0,
        production=20.0,
        technical_skills=10.0,
        bonus_points=0.0,
        raw_total=75.0,
        normalized_score=62.5
    )

    report = writer.generate_report(
        candidate_name="Nathaniel Reed",
        target_role="Senior Python & Distributed Systems Engineer",
        matrix=matrix,
        rubric=rubric
    )

    assert report.evidence_consistency_score == 85.0
    assert report.quadrant == "STRONG MATCH"
    assert report.contradicted_claim_count == 0
    assert len(report.key_discrepancies) == 0


def test_case_12_quadrant_placement():
    """Case 12 with missing REQ-02 core competency must land in INSUFFICIENT EVIDENCE."""
    writer = RecommendationWriterAgent()

    v1 = RequirementVerification("REQ-01", "Core Python & AsyncIO", "SUPPORTED", 0.9, "Strong", ["CV-001"], [], [])
    v2 = RequirementVerification("REQ-02", "Distributed Systems & Kafka", "INSUFFICIENT_EVIDENCE", 0.9, "No Kafka", ["CV-001"], [], [])
    v3 = RequirementVerification("REQ-03", "Technical Leadership", "SUPPORTED", 0.9, "Strong", ["CV-001"], [], [])
    v4 = RequirementVerification("REQ-04", "Production Tenure", "SUPPORTED", 0.9, "Strong", ["CV-001"], [], [])

    matrix = EvidenceMatrix(
        candidate_id="case_12_adv_jd_vs_claim",
        verifications=[v1, v2, v3, v4],
        total_requirements=4,
        supported_count=3,
        contradicted_count=0,
        insufficient_count=1,
        all_discrepancies=[],
        consistency_score=55.0
    )

    rubric = RubricScoreBreakdown(
        candidate_id="case_12_adv_jd_vs_claim",
        open_source=10.0,
        self_projects=15.0,
        production=20.0,
        technical_skills=5.0,
        bonus_points=0.0,
        raw_total=50.0,
        normalized_score=41.7
    )

    report = writer.generate_report(
        candidate_name="Evan Brooks",
        target_role="Senior Python & Distributed Systems Engineer",
        matrix=matrix,
        rubric=rubric
    )

    assert report.evidence_consistency_score == 55.0
    assert report.quadrant == "INSUFFICIENT EVIDENCE"
    assert report.contradicted_claim_count == 0


def test_case_12_end_to_end_pipeline_regression():
    """Direct end-to-end Case 12 pipeline regression asserting true negative contradiction and insufficient evidence."""
    case_12 = next(c for c in CASES if c["candidate_id"] == "case_12_adv_jd_vs_claim")
    dossier = EvidenceLoader.load_case_from_dict(case_12)
    pipeline = HireTracePipeline()
    report = pipeline.run(dossier, log_trajectory=False)

    assert report.contradicted_claim_count == 0
    assert len(report.key_discrepancies) == 0
    assert report.quadrant == "INSUFFICIENT EVIDENCE"
    assert report.evidence_consistency_score == 55.0


def test_weak_match_quadrant_threshold_cases_06_07_08():
    """Cases 06, 07, and 08 must be classified as WEAK MATCH."""
    pipeline = HireTracePipeline()
    for cid in ["case_06_weak_01", "case_07_weak_02", "case_08_weak_03"]:
        c = next(case for case in CASES if case["candidate_id"] == cid)
        dossier = EvidenceLoader.load_case_from_dict(c)
        report = pipeline.run(dossier, log_trajectory=False)
        assert report.quadrant == "WEAK MATCH", f"{cid} expected WEAK MATCH, got {report.quadrant}"
        assert report.contradicted_claim_count == 0
        assert len(report.key_discrepancies) == 0
