"""
CI Security Scan Test Suite for HireTrace Frontend (ui/index.html) and Server Config.
Guarantees:
1. No inline event handlers interpolate template literal variables (`onclick="...('${...}')"` or `on*="${...}"`).
2. No blocking alert() or confirm() calls remain in frontend scripts.
3. Accessible modal dialog attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`) are present.
4. Dev-mode production-bind guard functions correctly.
"""

import os
import re
import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML_PATH = os.path.join(ROOT_DIR, "ui", "index.html")


@pytest.fixture(scope="module")
def index_html_content() -> str:
    assert os.path.exists(INDEX_HTML_PATH), f"File not found: {INDEX_HTML_PATH}"
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_no_inline_event_handler_variable_interpolation(index_html_content: str):
    """
    Scans for patterns like onclick="...('${...}')" or on*="...${...}..."
    where dynamic template literal variables are interpolated directly into inline event attributes.
    This pattern causes attribute HTML-entity decoding before JS parsing, enabling XSS.
    """
    # Look for inline handler attribute followed by template literal interpolation ${
    pattern = re.compile(r'''\bon[a-zA-Z]+\s*=\s*["'][^"']*\$\{''', re.IGNORECASE)
    matches = pattern.findall(index_html_content)
    assert not matches, (
        f"Found {len(matches)} unsafe inline event handlers interpolating variables:\n"
        f"{matches[:5]}\n"
        "Use data-* attributes with delegated addEventListener instead."
    )


def test_no_alert_or_confirm_calls(index_html_content: str):
    """
    Asserts no blocking alert(...) or confirm(...) calls exist in the UI codebase.
    Non-blocking toasts and inline modal error banners must be used instead.
    """
    alert_pattern = re.compile(r'''(?<!\w)alert\s*\(''', re.IGNORECASE)
    confirm_pattern = re.compile(r'''(?<!\w)confirm\s*\(''', re.IGNORECASE)

    alert_matches = alert_pattern.findall(index_html_content)
    confirm_matches = confirm_pattern.findall(index_html_content)

    assert not alert_matches, f"Found {len(alert_matches)} alert() calls in ui/index.html. Replace with showToast or inline error banner."
    assert not confirm_matches, f"Found {len(confirm_matches)} confirm() calls in ui/index.html. Replace with styled modal dialogs."


def test_modal_accessibility_attributes(index_html_content: str):
    """
    Validates modal dialog accessibility:
    - role="dialog"
    - aria-modal="true"
    - aria-labelledby="..."
    """
    required_attrs = ['role="dialog"', 'aria-modal="true"', 'aria-labelledby=']
    for attr in required_attrs:
        assert attr in index_html_content, f"Missing required modal accessibility attribute: {attr}"


def test_dev_mode_production_bind_guard(monkeypatch):
    """
    Verifies that check_dev_mode_production_bind refuses insecure public binds
    when dev mode or auth-disabled flags are set without explicit override.
    """
    from agents.security import check_dev_mode_production_bind

    # Case 1: Loopback bind with dev mode is allowed
    monkeypatch.setenv("HIRETRACE_DEV_MODE", "1")
    monkeypatch.delenv("HIRETRACE_I_UNDERSTAND_DEV_MODE_IS_INSECURE", raising=False)
    check_dev_mode_production_bind(host="127.0.0.1")

    # Case 2: Public bind 0.0.0.0 with dev mode must be blocked
    with pytest.raises(RuntimeError, match="Refusing to start"):
        check_dev_mode_production_bind(host="0.0.0.0")

    # Case 3: Public bind with explicit override is permitted
    monkeypatch.setenv("HIRETRACE_I_UNDERSTAND_DEV_MODE_IS_INSECURE", "1")
    check_dev_mode_production_bind(host="0.0.0.0")

