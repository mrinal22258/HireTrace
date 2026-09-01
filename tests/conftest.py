"""
Pytest configuration and CI test hooks for HireTrace.

Ensures the complete test suite can execute deterministically in CI environments
(GitHub Actions, headless sandboxes) without requiring a physical GPU or live Ollama daemon.
"""

import os
import pytest
from agents.ollama_client import OllamaClient
from agents.mock_ollama_client import MockOllamaClient


@pytest.fixture(autouse=True)
def configure_ci_mock_backend(monkeypatch, request):
    """
    Enables offline mock mode if local Ollama/vLLM is unreachable,
    allowing full-pipeline integration tests to run in headless CI environments.
    Exempts tests that specifically validate degraded state or live integration.
    """
    test_name = request.node.name
    test_module = request.module.__name__ if request.module else ""

    # Never mock tests designed specifically to test live integration or degraded state
    if "degraded" in test_name or "degraded" in test_module:
        return
    if "live_ollama" in test_name or "live_ollama" in test_module:
        return

    # If user explicitly forced offline mock via env var, keep it
    if os.getenv("HIRETRACE_OFFLINE_MOCK", "").lower() in ("1", "true", "yes"):
        monkeypatch.setenv("HIRETRACE_OFFLINE_MOCK", "1")
        return

    # If live Ollama is unreachable, activate offline mock mode for CI
    standard_client = OllamaClient(base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    if not standard_client.is_available():
        monkeypatch.setenv("HIRETRACE_OFFLINE_MOCK", "1")


@pytest.fixture
def mock_ollama():
    """Explicit fixture for tests requesting a mock Ollama client."""
    return MockOllamaClient()
