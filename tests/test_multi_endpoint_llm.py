"""
Unit and Integration Tests for Phase 4: Multi-Endpoint LLM Scaling & Circuit Breaking.
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from agents.ollama_client import OllamaClient, EndpointState, set_max_concurrency


def test_multi_endpoint_capacity_and_semaphore():
    client = OllamaClient(
        base_urls=["http://gpu-01:11434", "http://gpu-02:11434", "http://gpu-03:11434"],
        concurrency_per_endpoint=2
    )
    assert len(client.endpoints) == 3
    assert client.total_capacity == 6  # 3 endpoints * 2 concurrency

    telemetry = client.get_telemetry()
    assert telemetry["configured_endpoints"] == 3
    assert telemetry["max_concurrency"] == 6
    assert len(telemetry["endpoints"]) == 3


def test_least_loaded_routing():
    client = OllamaClient(
        base_urls=["http://gpu-01:11434", "http://gpu-02:11434"],
        concurrency_per_endpoint=1
    )
    client.is_available = lambda: True

    # Simulate gpu-01 having 2 active in-flight requests
    client.endpoints[0].in_flight = 2
    client.endpoints[1].in_flight = 0

    # Best endpoint must be gpu-02
    chosen = client._get_best_endpoint()
    assert chosen is not None
    assert chosen.url == "http://gpu-02:11434"


def test_circuit_breaker_tripping_and_failover():
    client = OllamaClient(
        base_urls=["http://gpu-healthy:11434", "http://gpu-flaky:11434"],
        concurrency_per_endpoint=1
    )
    flaky = client.endpoints[1]
    flaky.failure_threshold = 2
    flaky.cooldown_sec = 10.0

    # 1 failure
    flaky.record_failure("HTTP 500")
    assert flaky.circuit_open is False
    assert flaky.is_available() is True

    # 2nd failure -> circuit trips
    flaky.record_failure("HTTP 500")
    assert flaky.circuit_open is True
    assert flaky.is_available() is False

    # Router should route exclusively to the healthy endpoint
    for _ in range(5):
        best = client._get_best_endpoint()
        assert best.url == "http://gpu-healthy:11434"


def test_all_endpoints_down_returns_degraded():
    client = OllamaClient(
        base_urls=["http://unreachable-gpu:11434"],
        concurrency_per_endpoint=1
    )
    client.is_available = lambda: True
    client.endpoints[0].circuit_open = True
    client.endpoints[0].circuit_opened_at = time.time()  # Not expired

    res = client.generate_json(prompt="Analyze candidate")
    assert res.get("degraded") is True
    assert res.get("error_code") == "CIRCUITS_OPEN"
    assert res.get("role_fit_score") is None
