import pytest
from agents.fast_triage import FastTriageEngine
from agents.evidence_loader import EvidenceLoader


def test_fast_triage_disqualifies_low_fit_candidate():
    low_fit_case = {
        "candidate_id": "case_low_fit_99",
        "name": "Barney Gumble",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "live_applicant",
        "cv_text": (
            "# Barney Gumble\n"
            "High school short-order line cook with 3 months experience.\n"
            "Responsible for operating deep fryer and washing dishes.\n"
            "Hobbies: Bowling, watching cartoons."
        ),
        "interview_notes": "",
        "technical_assessment": "",
        "project_rfc": ""
    }

    dossier = EvidenceLoader.load_case_from_dict(low_fit_case)
    is_rejected, triage_report = FastTriageEngine.evaluate(dossier, low_fit_case["target_role"])

    assert is_rejected is True
    assert triage_report is not None
    assert triage_report["quadrant"] == "LOW_FIT_FAST_REJECT"
    assert triage_report["role_fit_score"] < 18.0
    assert triage_report["triage_tier"] == "tier_0_fast_reject"
    assert "Bypassed 4-agent LLM pipeline" in triage_report["executive_summary"]


def test_fast_triage_passes_qualified_candidate():
    qualified_case = {
        "candidate_id": "case_qualified_01",
        "name": "Elena Rostova",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "live_applicant",
        "cv_text": (
            "# Elena Rostova\n"
            "Staff Distributed Systems Architect with 9 years experience in Python, asyncio, Kafka, microservices, and Kubernetes.\n"
            "Lead developer of high-throughput distributed database engine using Raft consensus.\n"
            "Scaled message broker processing 100,000 requests/sec across AWS cloud infrastructure."
        ),
        "interview_notes": "Elena answered detailed questions about network partition recovery.",
        "technical_assessment": "98/100 score on concurrency stress test.",
        "project_rfc": "Author of RFC 101: Distributed State Machine Replication."
    }

    dossier = EvidenceLoader.load_case_from_dict(qualified_case)
    is_rejected, triage_report = FastTriageEngine.evaluate(dossier, qualified_case["target_role"])

    # High fit candidate should NOT be fast-rejected!
    assert is_rejected is False
    assert triage_report is None
