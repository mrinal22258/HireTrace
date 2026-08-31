"""
Tests for NormalizedCrossSourceContradictionComparator against unseen contradiction formulations.
100% offline, zero network requests, evaluates generalization beyond benchmark phrasing.
"""

import pytest
from agents.evidence_loader import EvidenceSpan
from agents.cross_source_verification_agent import NormalizedCrossSourceContradictionComparator


def test_unseen_tenure_formulation_stripe():
    """Tenure contradiction with unseen employer and phrased differently."""
    cv_span = EvidenceSpan(
        span_id="CV-U01",
        source_file="cv.txt",
        document_type="cv",
        text="Senior Infrastructure Engineer at Stripe (4 years, 2019-2023): Designed edge proxies.",
        section="Experience"
    )
    int_span = EvidenceSpan(
        span_id="INT-U01",
        source_file="interview.txt",
        document_type="interview",
        text="Candidate clarified their tenure: 'I was only at Stripe for about 14 months before transitioning.'",
        section="Work History"
    )

    discrepancies = NormalizedCrossSourceContradictionComparator.compare_spans(
        req_id="REQ-TEST",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[],
        proj_spans=[],
        jd_spans=[]
    )

    assert len(discrepancies) == 1
    assert "Tenure" in discrepancies[0].topic
    assert discrepancies[0].source_a_span_id == "CV-U01"
    assert discrepancies[0].source_b_span_id == "INT-U01"


def test_unseen_tenure_formulation_acme():
    """Tenure contradiction with generic employer Acme Dynamics."""
    cv_span = EvidenceSpan(
        span_id="CV-U02",
        source_file="cv.txt",
        document_type="cv",
        text="Principal SRE at Acme Dynamics: 3.5 years of experience leading reliability.",
        section="Experience"
    )
    int_span = EvidenceSpan(
        span_id="INT-U02",
        source_file="interview.txt",
        document_type="interview",
        text="Recruiter note: Joined Acme Dynamics 12 months ago following the acquisition.",
        section="History"
    )

    discrepancies = NormalizedCrossSourceContradictionComparator.compare_spans(
        req_id="REQ-TEST",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[],
        proj_spans=[],
        jd_spans=[]
    )

    assert len(discrepancies) == 1
    assert "Tenure" in discrepancies[0].topic


def test_unseen_leadership_scope_quantum():
    """Unseen project leadership assertion contradicted by RFC contributor notes."""
    cv_span = EvidenceSpan(
        span_id="CV-U03",
        source_file="cv.txt",
        document_type="cv",
        text="Head of distributed compute initiative; owned rollout of real-time telemetry pipelines.",
        section="Projects"
    )
    proj_span = EvidenceSpan(
        span_id="PRJ-U03",
        source_file="project.txt",
        document_type="project",
        text="Architecture RFC-901: Compute telemetry was led by Principal Architect Dr. Evans; candidate assisted with serialization wrappers.",
        section="Author List"
    )

    discrepancies = NormalizedCrossSourceContradictionComparator.compare_spans(
        req_id="REQ-TEST",
        cv_spans=[cv_span],
        int_spans=[],
        ass_spans=[],
        proj_spans=[proj_span],
        jd_spans=[]
    )

    assert len(discrepancies) == 1
    assert "Ownership" in discrepancies[0].topic or "Leadership" in discrepancies[0].topic


def test_unseen_concurrency_failure_deadlock():
    """CV claims deadlock-free concurrency, technical assessment records irreversible deadlock."""
    cv_span = EvidenceSpan(
        span_id="CV-U04",
        source_file="cv.txt",
        document_type="cv",
        text="Expert in asyncio concurrency patterns; guarantee 100% deadlock-free event loop architectures.",
        section="Skills"
    )
    ass_span = EvidenceSpan(
        span_id="ASS-U04",
        source_file="assessment.txt",
        document_type="assessment",
        text="Test Case 4: Candidate concurrency implementation encountered irreversible deadlock, freezing the entire event loop. Score: 25/100.",
        section="Evaluation"
    )

    discrepancies = NormalizedCrossSourceContradictionComparator.compare_spans(
        req_id="REQ-TEST",
        cv_spans=[cv_span],
        int_spans=[],
        ass_spans=[ass_span],
        proj_spans=[],
        jd_spans=[]
    )

    assert len(discrepancies) == 1
    assert "Deadlock" in discrepancies[0].topic or "Concurrency" in discrepancies[0].topic


def test_unseen_direct_denial_rust():
    """CV claims mastery in Rust, interview reveals candidate has never used it."""
    cv_span = EvidenceSpan(
        span_id="CV-U05",
        source_file="cv.txt",
        document_type="cv",
        text="Expert architecting high-throughput microservices with extensive mastery of Rust.",
        section="Skills"
    )
    int_span = EvidenceSpan(
        span_id="INT-U05",
        source_file="interview.txt",
        document_type="interview",
        text="Interviewer question on memory safety: Candidate stated 'I personally have never configured or written production Rust.'",
        section="Technical Q&A"
    )

    discrepancies = NormalizedCrossSourceContradictionComparator.compare_spans(
        req_id="REQ-TEST",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[],
        proj_spans=[],
        jd_spans=[]
    )

    assert len(discrepancies) == 1
    assert "Rust" in discrepancies[0].topic or "Inexperience" in discrepancies[0].topic


def test_unseen_negative_control_honest_candidate():
    """Consistent unseen candidate evidence must generate zero false positive discrepancies."""
    cv_span = EvidenceSpan(
        span_id="CV-U06",
        source_file="cv.txt",
        document_type="cv",
        text="Software Engineer at Datadog (2 years, 2022-2024): Contributed to agent metric ingestion in Go.",
        section="Experience"
    )
    int_span = EvidenceSpan(
        span_id="INT-U06",
        source_file="interview.txt",
        document_type="interview",
        text="Candidate discussed 24 months of production work at Datadog maintaining Go metric ingestors under team lead.",
        section="Discussion"
    )
    ass_span = EvidenceSpan(
        span_id="ASS-U06",
        source_file="assessment.txt",
        document_type="assessment",
        text="Automated suite: Clean code, handles error propagation well. Score: 88/100.",
        section="Summary"
    )

    discrepancies = NormalizedCrossSourceContradictionComparator.compare_spans(
        req_id="REQ-TEST",
        cv_spans=[cv_span],
        int_spans=[int_span],
        ass_spans=[ass_span],
        proj_spans=[],
        jd_spans=[]
    )

    assert len(discrepancies) == 0
