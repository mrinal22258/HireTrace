"""
Unit tests for hardened CORS configuration.
Ensures:
1. Production mode defaults to no cross-origin credentialed access.
2. Dev mode allows localhost / 127.0.0.1.
3. Explicit ALLOWED_ORIGINS are honored.
4. Wildcard origins never enable allow_credentials=True.
"""

import os
from ui.server import get_cors_configuration


def test_cors_production_default(monkeypatch):
    """Production mode with no ALLOWED_ORIGINS set defaults to empty allowlist."""
    monkeypatch.delenv("HIRETRACE_DEV_MODE", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    origins, regex, allow_creds = get_cors_configuration()
    assert origins == []
    assert regex is None
    assert allow_creds is False


def test_cors_dev_mode_localhost(monkeypatch):
    """Dev mode allows localhost and 127.0.0.1 ports via regex."""
    monkeypatch.setenv("HIRETRACE_DEV_MODE", "1")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    origins, regex, allow_creds = get_cors_configuration()
    assert origins == []
    assert regex is not None
    assert "localhost" in regex
    assert allow_creds is True


def test_cors_explicit_origins(monkeypatch):
    """Explicit ALLOWED_ORIGINS list is parsed and credentials allowed."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.hiretrace.com, https://portal.example.com")
    monkeypatch.delenv("HIRETRACE_DEV_MODE", raising=False)

    origins, regex, allow_creds = get_cors_configuration()
    assert origins == ["https://app.hiretrace.com", "https://portal.example.com"]
    assert regex is None
    assert allow_creds is True


def test_cors_wildcard_denies_credentials(monkeypatch):
    """Wildcard origin must never allow credentials (prevents CORS vulnerability)."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")

    origins, regex, allow_creds = get_cors_configuration()
    assert origins == ["*"]
    assert allow_creds is False
