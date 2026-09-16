"""
Regression test asserting zero hardcoded hex color literals outside token blocks.
Protects the Ocean Depth Design System against color leakage.
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEX_REGEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')


def test_no_hardcoded_hex_in_styles_css_outside_tokens():
    styles_path = ROOT / "ui" / "styles.css"
    assert styles_path.exists(), "ui/styles.css missing"

    with open(styles_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find the end of token blocks (where BASE & RESET begins)
    token_end_idx = 0
    for idx, line in enumerate(lines):
        if "BASE & RESET" in line:
            token_end_idx = idx
            break

    assert token_end_idx > 0, "Could not locate end of token blocks in ui/styles.css"

    leaked = []
    for idx in range(token_end_idx, len(lines)):
        for match in HEX_REGEX.finditer(lines[idx]):
            leaked.append((idx + 1, match.group(0), lines[idx].strip()))

    assert len(leaked) == 0, f"Found {len(leaked)} hardcoded hex colors outside token blocks in ui/styles.css: {leaked}"


def test_no_hardcoded_hex_in_app_js():
    app_path = ROOT / "ui" / "app.js"
    assert app_path.exists(), "ui/app.js missing"

    with open(app_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    leaked = []
    for idx, line in enumerate(lines):
        for match in HEX_REGEX.finditer(line):
            leaked.append((idx + 1, match.group(0), line.strip()))

    assert len(leaked) == 0, f"Found {len(leaked)} hardcoded hex colors in ui/app.js: {leaked}"


def test_no_hardcoded_hex_in_index_html():
    html_path = ROOT / "ui" / "index.html"
    assert html_path.exists(), "ui/index.html missing"

    with open(html_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    leaked = []
    for idx, line in enumerate(lines):
        for match in HEX_REGEX.finditer(line):
            leaked.append((idx + 1, match.group(0), line.strip()))

    assert len(leaked) == 0, f"Found {len(leaked)} hardcoded hex colors in ui/index.html: {leaked}"


def test_no_color_properties_in_index_html_inline_styles():
    html_path = ROOT / "ui" / "index.html"
    assert html_path.exists(), "ui/index.html missing"

    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    styles = re.findall(r'style="([^"]*)"', content)
    color_props = ['color', 'background', 'border-color', 'box-shadow', 'fill']

    violations = []
    for s in styles:
        props = [p.strip() for p in s.split(';') if p.strip()]
        for p in props:
            parts = p.split(':', 1)
            if len(parts) == 2:
                k = parts[0].strip().lower()
                if any(cp == k or cp in k for cp in color_props):
                    violations.append((s, p))

    assert len(violations) == 0, f"Found {len(violations)} color properties in inline styles in index.html: {violations}"

