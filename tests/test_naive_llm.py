"""
Unit tests for HireTrace Baseline B (Naive LLM single prompt).
"""
import pytest
from agents.evidence_loader import CandidateDossier
from baseline.naive_llm import NaiveLLMBaseline


from agents.ollama_client import OllamaClient


@pytest.mark.skipif(not OllamaClient().is_available(), reason="Local Ollama daemon is not running")
def test_naive_llm_structure():
    baseline = NaiveLLMBaseline()
    dossier = CandidateDossier(
        candidate_id="test_candidate",
        name="Test Dev",
        target_role="Backend Engineer",
        jd_text="Need Python backend developer with 3+ years experience.",
        cv_text="Python engineer with 3 years experience at StartupCo."
    )
    result = baseline.evaluate(dossier)
    assert result["candidate_id"] == "test_candidate"
    assert "role_fit_score" in result
    assert "verdict" in result
    assert "latency_sec" in result
