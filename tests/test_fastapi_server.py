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


def test_favicon(client):
    res = client.get("/favicon.ico")
    assert res.status_code == 204


def test_structured_access_logging(client, capsys):
    client.get("/healthz")
    # Verify logger handled the request without error
