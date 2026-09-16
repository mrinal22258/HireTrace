import pytest
from fastapi.testclient import TestClient
from agents.recommendation_writer_agent import AssessmentReport
from ui.server import app, enrich_report_with_score_breakdown

client = TestClient(app)


def test_assessment_report_score_breakdown_and_provenance():
    """Verify AssessmentReport dataclass and to_dict expose score_breakdown and provenance."""
    report = AssessmentReport(
        candidate_id="case_01_strong_01",
        candidate_name="Sarah Chen",
        target_role="Senior Distributed Systems Engineer",
        role_fit_score=85.0,
        evidence_consistency_score=92.0,
        quadrant="STRONG MATCH",
        recommendation="Proceed to human review.",
        priority_questions=["Explain Kafka partitioning."],
        key_discrepancies=[],
        requirement_table=[],
        unsupported_claim_count=0,
        contradicted_claim_count=0,
        rubric_baseline_score=75.0,
        formatted_terminal_card="",
        llm_req_fit_score=91.67,
        model_name="qwen2.5:3b",
        prompt_version="v2.4-grounded-json",
        evaluated_at="2026-09-12T12:00:00Z",
    )
    d = report.to_dict()

    assert "score_breakdown" in d
    sb = d["score_breakdown"]
    assert sb["llm_requirement_match"] == pytest.approx(91.7, 0.1)
    assert sb["rubric_baseline_score"] == 75.0
    assert sb["role_fit_score"] == 85.0
    assert sb["llm_weight"] == 0.60
    assert sb["rubric_weight"] == 0.40

    assert "provenance" in d
    prov = d["provenance"]
    assert prov["model_name"] == "qwen2.5:3b"
    assert prov["prompt_version"] == "v2.4-grounded-json"
    assert prov["evaluated_at"] == "2026-09-12T12:00:00Z"
    assert prov["quadrant_fit_threshold"] == 72.0
    assert prov["quadrant_consistency_threshold"] == 70.0


def test_enrich_report_derivation():
    """Verify enrich_report_with_score_breakdown derives missing LLM match score without ambiguity."""
    payload_report = {
        "role_fit_score": 76.0,
        "rubric_baseline_score": 55.0,
        "quadrant": "REVIEW REQUIRED",
    }
    payload_rubric = {
        "raw_total": 55.0,
    }
    enriched_rep, enriched_base = enrich_report_with_score_breakdown(
        payload_report,
        baseline_a=payload_rubric,
        candidate_id="case_01_strong_01"
    )
    sb = enriched_rep["score_breakdown"]
    assert "llm_req_fit_score" in sb
    # (76.0 - 0.40 * 55.0) / 0.60 = (76 - 22) / 0.6 = 54 / 0.6 = 90.0
    assert sb["llm_req_fit_score"] == pytest.approx(90.0, 0.01)
    assert sb["rubric_baseline_score"] == 55.0
    assert sb["role_fit_score"] == 76.0

    assert "provenance" in enriched_rep
    assert enriched_rep["provenance"]["prompt_version"] == "v2.4-grounded-json"


def test_enrich_report_degraded():
    """Verify degraded reports preserve degraded flags and provide degraded_reason."""
    payload_report = {
        "degraded": True,
        "degraded_reason": "Local Ollama backend is offline",
        "role_fit_score": None,
    }
    enriched_rep, _ = enrich_report_with_score_breakdown(payload_report)
    assert enriched_rep["degraded"] is True
    assert enriched_rep["degraded_reason"] == "Local Ollama backend is offline"
    assert enriched_rep["score_breakdown"]["llm_req_fit_score"] is None


def test_api_evaluate_contains_phase_a_fields():
    """Verify live/cached /api/evaluate endpoint returns score_breakdown, provenance, and summary_audit."""
    response = client.post("/api/evaluate/case_01_strong_01")
    assert response.status_code == 200
    data = response.json()

    assert "report" in data
    rep = data["report"]
    assert "score_breakdown" in rep
    assert "provenance" in rep
    assert "baseline_a" in data
    assert "summary_audit" in data["baseline_a"]
    assert isinstance(data["baseline_a"]["summary_audit"], list)
    assert len(data["baseline_a"]["summary_audit"]) > 0

