"""
Phase 7 Observability & Telemetry Test Suite
Tests Prometheus metrics exposition (/metrics) and structured logging output.
"""

import json
import logging
import pytest
from fastapi.testclient import TestClient
from agents.observability import METRICS, log_agent_event
from agents.pipeline import HireTracePipeline
from agents.evidence_loader import EvidenceLoader
from eval_cases.dataset import CASES
from ui.server import app

client = TestClient(app)


def test_metrics_endpoint_exposition():
    """Verify GET /metrics returns standard Prometheus text format with expected series."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text

    # Verify standard metric series are declared
    assert "# HELP hiretrace_queue_depth" in body
    assert "# TYPE hiretrace_queue_depth gauge" in body
    assert "hiretrace_queue_depth " in body

    assert "# HELP hiretrace_jobs_total" in body
    assert "# TYPE hiretrace_jobs_total counter" in body

    assert "# HELP hiretrace_pipeline_evaluations_total" in body
    assert "hiretrace_pipeline_evaluations_total" in body

    assert "# HELP hiretrace_agent_duration_seconds" in body
    assert "hiretrace_agent_duration_seconds" in body

    assert "# HELP hiretrace_llm_calls_total" in body
    assert "hiretrace_llm_calls_total" in body


def test_metrics_updated_after_pipeline_execution(monkeypatch):
    """Verify that running a pipeline run updates Prometheus metrics and agent latency tables."""
    monkeypatch.setenv("HIRETRACE_OFFLINE_MOCK", "1")

    initial_runs = METRICS.pipeline_runs_total

    dossier = EvidenceLoader.load_case_from_dict(CASES[0])
    pipeline = HireTracePipeline()
    report = pipeline.run(dossier, log_trajectory=False)

    assert METRICS.pipeline_runs_total == initial_runs + 1

    # Verify agent latencies were recorded
    stats = METRICS.get_agent_stats()
    assert "RequirementMappingAgent" in stats
    assert stats["RequirementMappingAgent"]["count"] > 0
    assert stats["CrossSourceVerificationAgent"]["count"] > 0
    assert stats["RecommendationWriterAgent"]["count"] > 0

    # Verify rendered output contains updated stats
    rendered = METRICS.render_prometheus(pipeline.client)
    assert f'hiretrace_pipeline_evaluations_total{{outcome="completed"}} {METRICS.pipeline_runs_total}' in rendered
    assert 'hiretrace_agent_duration_seconds_count{agent="RequirementMappingAgent"}' in rendered


def test_structured_agent_logging():
    """Verify structured JSON logging for agent executions."""
    import io
    logging.disable(logging.NOTSET)
    agent_logger = logging.getLogger("hiretrace.agent")
    agent_logger.disabled = False
    agent_logger.setLevel(logging.INFO)
    
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    agent_logger.addHandler(handler)

    try:
        log_agent_event(
            agent="TestAgent",
            candidate_id="cand_test_obs",
            duration_sec=0.1234,
            outcome="success",
            degraded=False,
            details={"spans": 5}
        )
        handler.flush()
        output = log_stream.getvalue().strip()
        assert output, "Structured JSON log record for TestAgent was not captured"
        
        data = json.loads(output)
        assert data.get("agent") == "TestAgent"
        assert data["candidate_id"] == "cand_test_obs"
        assert data["duration_sec"] == 0.1234
        assert data["outcome"] == "success"
        assert data["details"]["spans"] == 5
    finally:
        agent_logger.removeHandler(handler)
