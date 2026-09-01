"""
Test for HireTrace 'No Silent Fallback' rule.

Asserts that running the assessment pipeline with Ollama / local LLM backend
deliberately unreachable produces an explicitly flagged DEGRADED report
with role_fit_score=None, rather than a fabricated or silent 50.0 score.
"""

import pytest
from agents.ollama_client import OllamaClient
from agents.pipeline import HireTracePipeline
from agents.evidence_loader import EvidenceLoader
from eval_cases.dataset import CASES


def test_pipeline_with_unreachable_ollama_marks_report_degraded():
    # 1. Instantiate client pointing to an unallocated/unreachable local port
    unreachable_client = OllamaClient(base_url="http://127.0.0.1:59999")
    assert unreachable_client.is_available() is False

    # 2. Directly verify generate_json returns degraded dict rather than fake score
    resp = unreachable_client.generate_json(prompt="Test prompt")
    assert resp.get("degraded") is True
    assert "role_fit_score" not in resp or resp.get("role_fit_score") is None
    assert "error" in resp

    # 3. Load standard candidate dossier
    case_data = CASES[0]
    dossier = EvidenceLoader.load_case_from_dict(case_data)

    # 4. Run pipeline with the unreachable client
    pipeline = HireTracePipeline(ollama_client=unreachable_client)
    report = pipeline.run(dossier, log_trajectory=False)

    # 5. Assert report is marked DEGRADED with NO fabricated score
    assert report.degraded is True, "Report must be explicitly marked degraded"
    assert report.role_fit_score is None, (
        f"role_fit_score must be None when LLM is unavailable, got: {report.role_fit_score}"
    )
    assert report.degraded_reason is not None
    assert report.quadrant in ("DEGRADED", "REVIEW REQUIRED")

    # 6. Verify serialization surfaces degraded state in API dictionary
    rep_dict = report.to_dict()
    assert rep_dict["degraded"] is True
    assert rep_dict["role_fit_score"] is None
    assert "DEGRADED" in report.formatted_terminal_card
