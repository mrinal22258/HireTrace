"""
Unit tests for GenericContradictionComparator.
100% offline, zero LLM dependencies, zero network requests.
"""

import pytest
from agents.evidence_loader import EvidenceSpan
from agents.cross_source_verification_agent import GenericContradictionComparator


def test_parse_duration_months():
    assert GenericContradictionComparator.parse_duration_months("3.5 years of experience") == 42.0
    assert GenericContradictionComparator.parse_duration_months("3 years at ScaleMatrix") == 36.0
    assert GenericContradictionComparator.parse_duration_months("18 months ago") == 18.0
    assert GenericContradictionComparator.parse_duration_months("2 yrs") == 24.0
    assert GenericContradictionComparator.parse_duration_months("no duration mentioned") is None


def test_generic_tenure_discrepancy():
    cv_span = EvidenceSpan(
        span_id="CV-001",
        source_file="cv.txt",
        document_type="cv",
        section="Experience",
        text="Lead Distributed Systems Engineer at FinFlow for 3.5 years managing Kafka."
    )
    int_span = EvidenceSpan(
        span_id="INT-001",
        source_file="interview_notes.txt",
        document_type="interview",
        section="Transcript",
        text="Joined FinFlow ~18 months ago as a team member working on consumers."
    )

    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-01",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[],
        proj_spans=[]
    )

    assert len(discrepancies) >= 1
    tenure_disc = next((d for d in discrepancies if "Tenure" in d.topic), None)
    assert tenure_disc is not None
    assert tenure_disc.contradiction_type == "cv_vs_interview"
    assert tenure_disc.severity == "HIGH"


def test_generic_ownership_authority_discrepancy():
    cv_span = EvidenceSpan(
        span_id="CV-002",
        source_file="cv.txt",
        document_type="cv",
        section="Experience",
        text="Led migration of core ingestion service to Apache Kafka."
    )
    proj_span = EvidenceSpan(
        span_id="PRO-001",
        source_file="project_doc.txt",
        document_type="project",
        section="Roster",
        text="Part of 7-person team led by Principal Architect Marcus Vance."
    )

    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-02",
        cv_spans=[cv_span],
        int_spans=[],
        ass_spans=[],
        proj_spans=[proj_span]
    )

    assert len(discrepancies) >= 1
    own_disc = next((d for d in discrepancies if "Leadership" in d.topic or "Authority" in d.topic), None)
    assert own_disc is not None
    assert own_disc.contradiction_type == "cv_vs_project"


def test_consistent_evidence_produces_zero_discrepancies():
    cv_span = EvidenceSpan(
        span_id="CV-001",
        source_file="cv.txt",
        document_type="cv",
        section="Experience",
        text="Senior Backend Engineer with 4 years experience at DataPulse."
    )
    int_span = EvidenceSpan(
        span_id="INT-001",
        source_file="interview_notes.txt",
        document_type="interview",
        section="Transcript",
        text="I have worked at DataPulse for 4 years building APIs."
    )

    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-01",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[],
        proj_spans=[]
    )

    assert len(discrepancies) == 0


def test_unrelated_positive_claims_do_not_contradict():
    """Different projects using similar technologies should never trigger ownership contradictions."""
    cv_span = EvidenceSpan(
        span_id="CV-010",
        source_file="cv.txt",
        document_type="cv",
        section="Experience",
        text="Led architecture of internal Redis cache cluster at ScaleMatrix."
    )
    proj_span = EvidenceSpan(
        span_id="PRO-010",
        source_file="project_doc.txt",
        document_type="project",
        section="Architecture",
        text="Contributing member on the ClickHouse telemetry analytics engine."
    )

    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-03",
        cv_spans=[cv_span],
        int_spans=[],
        ass_spans=[],
        proj_spans=[proj_span]
    )

    assert len(discrepancies) == 0


def test_different_employers_do_not_trigger_tenure_contradiction():
    """Durations at different employers should not be compared against each other."""
    cv_span = EvidenceSpan(
        span_id="CV-011",
        source_file="cv.txt",
        document_type="cv",
        section="Experience",
        text="Senior Engineer at DataStream for 4 years."
    )
    int_span = EvidenceSpan(
        span_id="INT-011",
        source_file="interview_notes.txt",
        document_type="interview",
        section="Transcript",
        text="Prior to that, I was at ApexGrid for 18 months."
    )

    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-05",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[],
        proj_spans=[]
    )

    assert len(discrepancies) == 0


def test_technical_competency_claim_vs_deadlock_failure():
    """World-class concurrency claim vs critical deadlock failure is correctly detected."""
    cv_span = EvidenceSpan(
        span_id="CV-012",
        source_file="cv.txt",
        document_type="cv",
        section="Technical Summary",
        text="Recognized world-class authority on Python AsyncIO internals and low-latency non-blocking network programming."
    )
    ass_span = EvidenceSpan(
        span_id="ASS-012",
        source_file="assessment.txt",
        document_type="assessment",
        section="Test Results",
        text="Score: 22 / 100 | Grade: Critical Failure. Concurrency Suite FAILED: Produced immediate event loop deadlocks under 50 concurrent requests."
    )

    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-01",
        cv_spans=[cv_span],
        int_spans=[],
        ass_spans=[ass_span],
        proj_spans=[]
    )

    assert len(discrepancies) >= 1
    d = discrepancies[0]
    assert d.contradiction_type == "cv_vs_assessment"
    assert d.source_a_span_id == "CV-012"
    assert d.source_b_span_id == "ASS-012"


def test_direct_admission_of_inexperience():
    """CV claim of mastery vs explicit direct interview admission of zero experience is detected."""
    cv_span = EvidenceSpan(
        span_id="CV-013",
        source_file="cv.txt",
        document_type="cv",
        section="Skills",
        text="Extensive mastery architecting Apache Kafka distributed clusters and topic partition balancing."
    )
    int_span = EvidenceSpan(
        span_id="INT-013",
        source_file="interview_notes.txt",
        document_type="interview",
        section="Interview",
        text="I personally have never configured or operated a Kafka broker or managed partition topologies."
    )

    discrepancies = GenericContradictionComparator.compare_spans(
        req_id="REQ-02",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[],
        proj_spans=[]
    )

    assert len(discrepancies) >= 1
    assert any("Negation" in d.topic or "Inexperience" in d.topic for d in discrepancies)

