import os
import re
import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML_PATH = os.path.join(ROOT_DIR, "ui", "index.html")

def test_no_inline_event_handlers_in_index_html():
    """Asserts that zero inline on* attributes (onclick, oninput, onchange, etc.) exist in ui/index.html."""
    assert os.path.exists(INDEX_HTML_PATH), f"File not found: {INDEX_HTML_PATH}"
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Find all inline event handler attributes: on* =
    on_matches = re.findall(r'\bon[a-zA-Z]+\s*=', content, re.IGNORECASE)
    assert len(on_matches) == 0, (
        f"Found {len(on_matches)} inline event handler attributes ({on_matches[:5]}) in ui/index.html. "
        "All event handlers must use delegated dispatchers in ui/app.js to comply with strict CSP without 'unsafe-inline'."
    )

def test_no_inline_script_blocks_in_index_html():
    """Asserts that zero inline <script> blocks exist in ui/index.html (Task E7)."""
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Inline scripts without src=
    inline_scripts = re.findall(r'<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)
    assert len(inline_scripts) == 0, (
        f"Found {len(inline_scripts)} inline <script> blocks in ui/index.html. "
        "All scripts must be loaded from external files (e.g. boot.js)."
    )
