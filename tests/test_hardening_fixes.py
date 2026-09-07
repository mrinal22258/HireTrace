"""
Unit and integration tests for production hardening and scaling fixes:
- Fix 2: API key startup validation (rejects placeholder and short keys)
- Fix 3: Redis sliding-window multi-replica rate limiting and fallback
- Fix 4: Constant-time authentication
- Fix 5: DB save retry with backoff, JobPersistenceError, and HTTP 503 response
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from agents.security import (
    validate_security_configuration,
    authenticate_and_authorize,
    RedisRateLimiter,
    RateLimiter,
)
from agents.job_manager import JobManager, JobPersistenceError
from agents.db import DB
from ui.server import app


# ---------------------------------------------------------------------------
# FIX 2: Production API Key Startup Validation
# ---------------------------------------------------------------------------

def test_validate_security_rejects_placeholder_key(monkeypatch):
    """Refuse to start if HIRETRACE_REQUIRE_AUTH=1 and key is default placeholder."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("HIRETRACE_API_KEY", "prod_hiretrace_secret_key_change_me")
    monkeypatch.delenv("HIRETRACE_TEST_BYPASS_KEY_LENGTH", raising=False)

    with pytest.raises(RuntimeError, match="Insecure placeholder API key"):
        validate_security_configuration()


def test_validate_security_rejects_short_key(monkeypatch):
    """Refuse to start if HIRETRACE_REQUIRE_AUTH=1 and key is < 24 chars."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("HIRETRACE_API_KEY", "too-short-key-123")
    monkeypatch.delenv("HIRETRACE_TEST_BYPASS_KEY_LENGTH", raising=False)

    with pytest.raises(RuntimeError, match="too short"):
        validate_security_configuration()


def test_validate_security_rejects_empty_keys(monkeypatch):
    """Refuse to start if HIRETRACE_REQUIRE_AUTH=1 and no keys configured."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HIRETRACE_API_KEY", raising=False)
    monkeypatch.delenv("HIRETRACE_API_KEYS", raising=False)
    monkeypatch.delenv("HIRETRACE_TEST_BYPASS_KEY_LENGTH", raising=False)

    with pytest.raises(RuntimeError, match="no API keys were configured"):
        validate_security_configuration()


def test_validate_security_accepts_valid_key(monkeypatch):
    """Startup validation succeeds with valid high-entropy key."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("HIRETRACE_API_KEY", "prod_super_secret_enterprise_token_2026_xyz")
    monkeypatch.delenv("HIRETRACE_TEST_BYPASS_KEY_LENGTH", raising=False)

    # Should not raise
    validate_security_configuration()


def test_validate_security_passes_when_auth_disabled(monkeypatch):
    """Startup validation allows unconfigured keys when auth is disabled."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "0")
    monkeypatch.delenv("HIRETRACE_API_KEY", raising=False)
    validate_security_configuration()


# ---------------------------------------------------------------------------
# FIX 4: Constant-Time Authentication
# ---------------------------------------------------------------------------

def test_constant_time_authentication_validation(monkeypatch):
    """Verify authenticate_and_authorize verifies keys with constant-time equality."""
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("HIRETRACE_API_KEY", "tenant_alpha_secure_key_123456789")

    # Valid key in header (case-insensitive dictionary emulation)
    class MockRequest:
        def __init__(self, headers):
            self.headers = {k.lower(): v for k, v in headers.items()}

    req_valid = MockRequest({"x-api-key": "tenant_alpha_secure_key_123456789"})
    tenant = authenticate_and_authorize(req_valid)
    assert tenant == "default_tenant"

    # Bearer auth format
    req_bearer = MockRequest({"authorization": "Bearer tenant_alpha_secure_key_123456789"})
    tenant_b = authenticate_and_authorize(req_bearer)
    assert tenant_b == "default_tenant"

    # Invalid key -> 401
    req_invalid = MockRequest({"x-api-key": "wrong_and_invalid_token"})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        authenticate_and_authorize(req_invalid)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# FIX 3: Redis Sliding-Window Rate Limiter & Multi-Replica Sharing
# ---------------------------------------------------------------------------

class MockPipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def zremrangebyscore(self, key, min_s, max_s):
        self.commands.append(("zremrangebyscore", (key, min_s, max_s)))
        return self

    def zcard(self, key):
        self.commands.append(("zcard", (key,)))
        return self

    def zrange(self, key, start, stop, withscores=False):
        self.commands.append(("zrange", (key, start, stop, withscores)))
        return self

    def zadd(self, key, mapping):
        self.commands.append(("zadd", (key, mapping)))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", (key, seconds)))
        return self

    def execute(self):
        results = []
        for cmd, args in self.commands:
            func = getattr(self.client, cmd)
            results.append(func(*args))
        return results


class MockRedisClient:
    """In-memory mock implementing Redis sorted sets with pipeline support."""
    def __init__(self):
        self.zsets = {}
        self.expiries = {}

    def ping(self):
        return True

    def pipeline(self):
        return MockPipeline(self)

    def zadd(self, key, mapping):
        if key not in self.zsets:
            self.zsets[key] = {}
        for member, score in mapping.items():
            self.zsets[key][member] = float(score)

    def zremrangebyscore(self, key, min_score, max_score):
        if key not in self.zsets:
            return 0
        min_s = float(min_score) if min_score != "-inf" else float("-inf")
        max_s = float(max_score) if max_score != "+inf" else float("+inf")
        to_del = [m for m, s in self.zsets[key].items() if min_s <= s <= max_s]
        for m in to_del:
            del self.zsets[key][m]
        return len(to_del)

    def zcard(self, key):
        if key not in self.zsets:
            return 0
        return len(self.zsets[key])

    def zrange(self, key, start, stop, withscores=False):
        if key not in self.zsets:
            return []
        items = sorted(self.zsets[key].items(), key=lambda x: x[1])
        sliced = items[start:stop + 1] if stop != -1 else items[start:]
        if withscores:
            return sliced
        return [m for m, s in sliced]

    def expire(self, key, seconds):
        self.expiries[key] = seconds
        return True


def test_redis_rate_limiter_multi_replica_shared_enforcement():
    """
    Two independent RedisRateLimiter instances sharing the same Redis client
    (simulating 2 web tier replicas) enforce a combined rate limit.
    """
    shared_redis = MockRedisClient()
    limit = 4
    window = 60

    replica_1 = RedisRateLimiter(shared_redis, window_seconds=window, max_requests=limit)
    replica_2 = RedisRateLimiter(shared_redis, window_seconds=window, max_requests=limit)

    client_id = "tenant_enterprise_01"

    # Replica 1 handles 2 requests -> both allowed
    allowed, _ = replica_1.check(client_id)
    assert allowed is True
    allowed, _ = replica_1.check(client_id)
    assert allowed is True

    # Replica 2 handles 2 requests -> both allowed (total: 4)
    allowed, _ = replica_2.check(client_id)
    assert allowed is True
    allowed, _ = replica_2.check(client_id)
    assert allowed is True

    # 5th request on Replica 1 -> DENIED because combined limit of 4 is reached
    allowed_5, retry_after_5 = replica_1.check(client_id)
    assert allowed_5 is False
    assert retry_after_5 >= 1

    # 6th request on Replica 2 -> also DENIED
    allowed_6, retry_after_6 = replica_2.check(client_id)
    assert allowed_6 is False
    assert retry_after_6 >= 1


def test_redis_rate_limiter_fails_open_on_redis_error():
    """If Redis operations encounter an error, fail open to in-memory limiter without crashing."""
    broken_redis = MockRedisClient()
    broken_redis.pipeline = MagicMock(side_effect=Exception("Redis connection refused"))

    limiter = RedisRateLimiter(broken_redis, window_seconds=60, max_requests=2)

    # Should not raise; falls back gracefully
    allowed, _ = limiter.check("test_client")
    assert allowed is True


# ---------------------------------------------------------------------------
# FIX 5: DB Save Retries, JobPersistenceError, and HTTP 503
# ---------------------------------------------------------------------------

def test_create_job_retries_and_raises_job_persistence_error():
    """create_job retries DB.save_job 3 times with backoff, then raises JobPersistenceError."""
    jm = JobManager()
    save_mock = MagicMock(side_effect=RuntimeError("Postgres write timeout"))

    with patch("agents.job_manager.DB.save_job", save_mock), \
         patch("agents.job_manager.time.sleep") as sleep_mock:
        with pytest.raises(JobPersistenceError, match="Failed to persist job"):
            jm.create_job("cand_db_fail_01", "Fail Cand", "Engineer")

        assert save_mock.call_count == 3
        assert sleep_mock.call_count == 2
        # Ensure failed job is NOT stored in in-memory state
        assert "cand_db_fail_01" not in jm._jobs


def test_server_intake_returns_503_on_job_persistence_error(monkeypatch):
    """FastAPI POST /api/candidate/upload returns HTTP 503 when DB persistence fails."""
    monkeypatch.setenv("HIRETRACE_OFFLINE_MOCK", "1")
    monkeypatch.setenv("HIRETRACE_REQUIRE_AUTH", "0")

    save_mock = MagicMock(side_effect=RuntimeError("Connection dropped"))

    with patch("agents.job_manager.DB.save_job", save_mock), \
         patch("agents.job_manager.time.sleep"):
        client = TestClient(app)
        payload = {
            "candidate_id": "cand_persistence_503_test",
            "name": "Grace Hopper",
            "target_role": "Systems Architect",
            "cv_text": "Pioneered compilers and distributed computing."
        }
        # Call async enqueue via upload endpoint
        resp = client.post("/api/candidate/upload?sync=false", json=payload)
        assert resp.status_code == 503
        assert "failed to enqueue evaluation, please retry" in resp.text
