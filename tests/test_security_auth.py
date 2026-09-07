"""
Phase 6 Security & Multi-Tenancy Test Suite
Tests API key authentication, tenant isolation (403), rate limiting (429), and Pydantic validation (422).
"""

import os
import pytest
from fastapi.testclient import TestClient
from agents.db import DB
from agents.security import RATE_LIMITER
from ui.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_security_env(monkeypatch):
    """Set up controlled security environment for testing."""
    monkeypatch.setenv("HIRETRACE_OFFLINE_MOCK", "1")
    RATE_LIMITER.reset()
    RATE_LIMITER.max_requests = 30


def test_unauthenticated_request_rejected_when_auth_required(monkeypatch):
    """When HIRETRACE_REQUIRE_AUTH=1, requests without valid token get 401."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("HIRETRACE_API_KEY", "secret-test-key")

    resp = client.get("/api/cases")
    assert resp.status_code == 401
    assert "Missing or invalid API key" in resp.text

    # Request with invalid key -> 401
    resp_invalid = client.get("/api/cases", headers={"X-API-Key": "wrong-key"})
    assert resp_invalid.status_code == 401
    assert "Missing or invalid API key" in resp_invalid.text

    # Request with valid key -> 200
    resp_valid = client.get("/api/cases", headers={"X-API-Key": "secret-test-key"})
    assert resp_valid.status_code == 200


def test_multi_tenant_api_key_mapping(monkeypatch):
    """Test mapping different API keys to different tenants."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    keys_json = '{"key-acme": "tenant-acme", "key-globex": "tenant-globex"}'
    monkeypatch.setenv("HIRETRACE_API_KEYS", keys_json)

    # Acme key sees acme cases
    resp_acme = client.get("/api/cases", headers={"X-API-Key": "key-acme"})
    assert resp_acme.status_code == 200

    # Globex key sees globex cases
    resp_globex = client.get("/api/cases", headers={"Authorization": "Bearer key-globex"})
    assert resp_globex.status_code == 200


def test_cross_tenant_isolation_forbidden(monkeypatch):
    """Verify tenant isolation: Tenant B cannot inspect or evaluate Tenant A's candidate (403 Forbidden)."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    keys_json = '{"key-tenant-alpha": "tenant_alpha", "key-tenant-beta": "tenant_beta"}'
    monkeypatch.setenv("HIRETRACE_API_KEYS", keys_json)

    cand_id = "cand_alpha_security_test_01"

    # Alpha creates a candidate
    payload = {
        "candidate_id": cand_id,
        "name": "Alpha Candidate",
        "target_role": "Security Engineer",
        "cv_text": "Experienced security analyst with zero-trust architecture background.",
        "interview_notes": "Passed penetration testing and IAM system review.",
        "technical_assessment": "Auth architecture review passed.",
        "project_rfc": "Proposed SSO and RBAC enforcement."
    }

    create_resp = client.post(
        "/api/candidate/new?sync=true",
        headers={"X-API-Key": "key-tenant-alpha"},
        json=payload
    )
    assert create_resp.status_code == 200

    # Alpha can view full case
    alpha_view = client.get(
        f"/api/case/{cand_id}/full",
        headers={"X-API-Key": "key-tenant-alpha"}
    )
    assert alpha_view.status_code == 200

    # Beta attempts to view Alpha's candidate -> 403 Forbidden
    beta_view = client.get(
        f"/api/case/{cand_id}/full",
        headers={"X-API-Key": "key-tenant-beta"}
    )
    assert beta_view.status_code == 403
    assert "Forbidden" in beta_view.text

    # Beta attempts to trigger evaluate on Alpha's candidate -> 403 Forbidden
    beta_eval = client.post(
        f"/api/evaluate/{cand_id}",
        headers={"X-API-Key": "key-tenant-beta"}
    )
    assert beta_eval.status_code == 403
    assert "Forbidden" in beta_eval.text


def test_rate_limiter_exceeded_returns_429(monkeypatch):
    """Test sliding window rate limiting returning HTTP 429."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "0")
    RATE_LIMITER.reset()
    RATE_LIMITER.max_requests = 3

    cand_prefix = "rate_limit_test"
    for i in range(3):
        resp = client.post(
            "/api/candidate/new",
            headers={"X-Tenant-ID": "test_tenant_rate"},
            json={
                "candidate_id": f"{cand_prefix}_{i}",
                "name": f"Rate Limit Test {i}",
                "target_role": "Backend Engineer",
                "cv_text": "Python experience.",
            }
        )
        assert resp.status_code in (200, 202)

    # 4th call should hit rate limit
    blocked_resp = client.post(
        "/api/candidate/new",
        headers={"X-Tenant-ID": "test_tenant_rate"},
        json={
            "candidate_id": f"{cand_prefix}_overflow",
            "name": "Rate Limit Overflow",
            "target_role": "Backend Engineer",
            "cv_text": "Python experience.",
        }
    )
    assert blocked_resp.status_code == 429
    assert "Rate limit exceeded" in blocked_resp.text
    assert "Retry-After" in blocked_resp.headers


def test_pydantic_schema_validation_rejects_malformed_id():
    """Verify Pydantic validation rejects invalid candidate IDs with 422."""
    resp = client.post(
        "/api/candidate/new",
        json={
            "candidate_id": "invalid ID with spaces!@#$",
            "name": "Invalid ID Candidate",
            "target_role": "QA Engineer",
            "cv_text": "Sample text",
        }
    )
    assert resp.status_code == 422
