"""
Real Local Integration Test with Live Ollama Inference.

Runs an actual candidate dossier through the complete 4-agent HireTrace pipeline
using local open-weights inference (qwen2.5:3b).
Asserts that real semantic assessment is performed with NO mocked client, NO fake scores,
and explicit degraded == False.
"""

import os
import pytest
from agents.ollama_client import OllamaClient
from agents.pipeline import HireTracePipeline
from agents.evidence_loader import EvidenceLoader
from eval_cases.dataset import CASES


def test_live_candidate_pipeline_with_real_ollama():
    if os.getenv("HIRETRACE_OFFLINE_MOCK", "").lower() in ("1", "true", "yes"):
        pytest.skip("Skipping live Ollama test: offline mock mode explicitly enabled for CI")

    client = OllamaClient()
    is_ready, health_msg = client.check_health()
    if not is_ready:
        pytest.skip(f"Ollama integration test skipped: {health_msg}")

    # Use standard candidate (Sarah Chen)
    case_data = CASES[0]
    dossier = EvidenceLoader.load_case_from_dict(case_data)

    pipeline = HireTracePipeline(ollama_client=client)
    report = pipeline.run(dossier, log_trajectory=False)

    # Assertions confirming real, non-degraded assessment
    assert report.degraded is False, f"Report unexpectedly degraded: {report.degraded_reason}"
    assert report.role_fit_score is not None, "Real LLM inference must produce a non-null role_fit_score"
    assert report.role_fit_score > 0.0, f"Expected positive role_fit_score, got {report.role_fit_score}"
    assert report.evidence_consistency_score is not None
    assert report.quadrant in ("STRONG MATCH", "REVIEW REQUIRED", "INSUFFICIENT EVIDENCE", "WEAK MATCH")
    assert len(report.priority_questions) >= 1, "Expected priority review questions from recommendation agent"
    assert client.successful_calls >= 1, "Expected at least 1 successful live LLM call"
    assert client.fallback_calls == 0, f"Expected 0 fallback calls during live inference, got {client.fallback_calls}"
