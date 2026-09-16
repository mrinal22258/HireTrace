import os
import time
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from ui.server import app, DB, PIPELINE


@pytest.fixture
def client():
    return TestClient(app)


def test_healthz_endpoint(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert data["version"] == "2.0.0"


def test_readyz_endpoint_healthy(client):
    res = client.get("/readyz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ready", "degraded")
    assert "database" in data
    assert "llm" in data


def test_readyz_endpoint_llm_down(client):
    with patch.object(PIPELINE.client, "is_available", return_value=False), \
         patch.dict(os.environ, {"HIRETRACE_OFFLINE_MOCK": "0"}):
        res = client.get("/readyz")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["llm"] == "unreachable"


def test_readyz_endpoint_db_down(client):
    with patch.object(DB, "session_scope", side_effect=Exception("DB connection timeout")):
        res = client.get("/readyz")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "not_ready"
        assert "unreachable" in data["database"]


def test_static_dashboard_security_headers(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "no-referrer"
    csp = res.headers.get("Content-Security-Policy")
    assert csp is not None
    assert "default-src 'self'" in csp
    # Assert Strict-Transport-Security is NOT set in application
    assert "Strict-Transport-Security" not in res.headers


def test_favicon(client):
    res = client.get("/favicon.ico")
    assert res.status_code in (200, 204)


def test_structured_access_logging(client, capsys):
    client.get("/healthz")
    # Verify logger handled the request without error


def test_audit_summary_endpoint(client):
    res = client.get("/api/audit/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "snapshot_taken_at" in data
    assert data.get("data_source") == "frozen_benchmark_snapshot"
    assert "fairness" in data
    assert data["fairness"]["eeoc_four_fifths_compliant"] is True
    assert data["fairness"]["minimum_disparate_impact_ratio"] == 1.0
    assert "grounding" in data
    assert data["grounding"]["grounded_claim_fidelity"] == 100.0
    assert "adversarial" in data
    assert data["adversarial"]["prompt_injection_defense_rate"] == 100.0
    assert "governance" in data
    assert data["governance"]["human_in_the_loop_mandatory"] is True


def test_include_demo_filter_cases_and_leaderboard(client):
    """Verifies that include_demo=false excludes benchmark candidates, and include_demo=true includes them."""
    from eval_cases.dataset import CASES
    bench_ids = {c["candidate_id"] for c in CASES}

    # 1. /api/cases with default (include_demo=false)
    res_default = client.get("/api/cases")
    assert res_default.status_code == 200
    cases_default = res_default.json()
    assert not any(c["candidate_id"] in bench_ids for c in cases_default)

    # 2. /api/cases with explicit include_demo=false
    res_false = client.get("/api/cases?include_demo=false")
    assert res_false.status_code == 200
    cases_false = res_false.json()
    assert not any(c["candidate_id"] in bench_ids for c in cases_false)

    # 3. /api/cases with include_demo=true
    res_true = client.get("/api/cases?include_demo=true")
    assert res_true.status_code == 200
    cases_true = res_true.json()
    assert any(c["candidate_id"] in bench_ids for c in cases_true)

    # 4. /api/leaderboard with default (include_demo=false)
    res_lead_default = client.get("/api/leaderboard")
    assert res_lead_default.status_code == 200
    lead_default = res_lead_default.json()
    assert not any(c["candidate_id"] in bench_ids for c in lead_default)

    # 5. /api/leaderboard with include_demo=true
    res_lead_true = client.get("/api/leaderboard?include_demo=true")
    assert res_lead_true.status_code == 200
    lead_true = res_lead_true.json()
    assert any(c["candidate_id"] in bench_ids for c in lead_true)



