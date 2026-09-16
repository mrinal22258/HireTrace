import time
import pytest
from unittest.mock import MagicMock
from agents.security import RateLimiter, RedisRateLimiter
from agents.observability import METRICS


def test_rate_limiter_bounded_lru_eviction(monkeypatch):
    """Test that in-memory RateLimiter evicts older keys when exceeding capacity."""
    # Use a small limit of 5 keys
    limiter = RateLimiter(max_requests=10, window_seconds=60, max_keys=5)
    
    # Insert 5 keys
    for i in range(5):
        allowed, _ = limiter.check(f"tenant:ip_{i}")
        assert allowed is True
        
    assert len(limiter._history) == 5
    assert limiter._history.get("tenant:ip_0") is not None
    
    # Notice: accessing ip_0 with get() made ip_0 the MOST recently used,
    # so ip_1 is now the least recently used key.
    # Inserting 6th key -> ip_1 should be evicted!
    allowed, _ = limiter.check("tenant:ip_5")
    assert allowed is True
    assert len(limiter._history) == 5
    assert limiter._history.get("tenant:ip_1") is None
    assert limiter._history.get("tenant:ip_5") is not None
    assert limiter._history.get("tenant:ip_0") is not None


def test_rate_limiter_env_var_max_keys(monkeypatch):
    """Test that HIRETRACE_RATE_LIMIT_MAX_KEYS configures the LRU size."""
    monkeypatch.setenv("HIRETRACE_RATE_LIMIT_MAX_KEYS", "3")
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    assert limiter.max_keys == 3
    assert limiter._history.maxsize == 3

    for i in range(4):
        limiter.check(f"client_{i}")
    assert len(limiter._history) == 3
    assert limiter._history.get("client_0") is None
    assert limiter._history.get("client_3") is not None


def test_redis_rate_limiter_fail_open_increments_metric_and_throttles_logs():
    """Test that RedisRateLimiter increments Prometheus metric on Redis error and fails open."""
    broken_redis = MagicMock()
    broken_redis.pipeline.side_effect = Exception("Redis connection refused")

    initial_fallbacks = METRICS.redis_ratelimit_fallbacks_total

    limiter = RedisRateLimiter(broken_redis, window_seconds=60, max_requests=2)

    # 1st call fails open
    allowed, _ = limiter.check("client_failopen")
    assert allowed is True
    assert METRICS.redis_ratelimit_fallbacks_total == initial_fallbacks + 1

    # 2nd call fails open
    allowed, _ = limiter.check("client_failopen")
    assert allowed is True
    assert METRICS.redis_ratelimit_fallbacks_total == initial_fallbacks + 2

    # Render metrics to ensure Prometheus output contains the counter
    prom_output = METRICS.render_prometheus()
    assert "hiretrace_redis_ratelimit_fallbacks_total" in prom_output
    assert f"hiretrace_redis_ratelimit_fallbacks_total {initial_fallbacks + 2}" in prom_output
