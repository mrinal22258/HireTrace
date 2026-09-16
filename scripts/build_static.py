#!/usr/bin/env python3
"""
Build script for Standalone / Hugging Face Static Space Export.
Syncs all UI assets from ui/ to repo root and rewrites absolute URL paths
to root-relative paths so the application functions with zero backend server.
"""

import os
import sys
import re
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
UI_DIR = ROOT_DIR / "ui"


def rewrite_html_for_static(html_content: str) -> str:
    """
    Rewrites absolute paths (/styles.css, /app.js, /vendor/..., /assets/...)
    to relative paths suitable for standalone root static serving.
    """
    # Rewrites href="/..." and src="/..." to relative paths
    def _rel(match):
        attr = match.group(1)  # src or href
        url = match.group(2)
        if url.startswith("//") or url.startswith("http://") or url.startswith("https://") or url.startswith("data:"):
            return match.group(0)
        clean_url = url.lstrip("/")
        return f'{attr}="{clean_url}"'

    pattern = re.compile(r'(src|href)=["\']/([^"\']+)["\']')
    rewritten = pattern.sub(_rel, html_content)
    return rewritten


def build_static():
    print(f"[*] Building static export from {UI_DIR} to {ROOT_DIR}...")

    # 1. Regenerate ui/static_data.js to guarantee fresh embedded evaluations and audit summary
    export_script = ROOT_DIR / "scripts" / "export_static_data.py"
    if export_script.exists():
        print("  -> Regenerating ui/static_data.js via export_static_data.py...")
        sys.path.insert(0, str(ROOT_DIR))
        from scripts.export_static_data import generate_static_data
        generate_static_data()

    # 2. Read and rewrite index.html
    src_index = UI_DIR / "index.html"
    if not src_index.exists():
        raise FileNotFoundError(f"Source index.html missing at {src_index}")

    with open(src_index, "r", encoding="utf-8") as f:
        html_src = f.read()

    html_out = rewrite_html_for_static(html_src)
    dst_index = ROOT_DIR / "index.html"
    with open(dst_index, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"  -> Generated {dst_index} ({dst_index.stat().st_size / 1024:.1f} KB)")

    # 3. Copy direct static text and JS files
    files_to_copy = [
        "styles.css",
        "app.js",
        "static_data.js",
        "dom-safe.js",
        "motion.js",
        "boot.js",
        "ocean-mesh-background.js",
        "mascot-cursor-tracker.js",
        "favicon.ico",
        "hiretrace_mascot_directions.webp",
        "hiretrace_mascot_reactions.webp",
        "mascot.svg",
        "mascot_celebrating.svg",
        "mascot_checking.svg",
        "mascot_entrance.svg",
        "mascot_idle.svg",
        "announcements.json",
    ]

    for fname in files_to_copy:
        src = UI_DIR / fname
        dst = ROOT_DIR / fname
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  -> Copied {fname}")
        else:
            print(f"  [!] Warning: {src} not found in ui/")

    # 4. Copy vendor directory
    src_vendor = UI_DIR / "vendor"
    dst_vendor = ROOT_DIR / "vendor"
    if src_vendor.exists():
        # Copy files inside ui/vendor into root vendor/ (preserving longextract_bench if present)
        dst_vendor.mkdir(exist_ok=True)
        for item in src_vendor.iterdir():
            if item.is_file():
                shutil.copy2(item, dst_vendor / item.name)
        print("  -> Synced vendor libraries (gsap, ScrollTrigger) to root vendor/")

    # 5. Ensure robots.txt exists
    robots_dst = ROOT_DIR / "robots.txt"
    if not robots_dst.exists():
        with open(robots_dst, "w", encoding="utf-8") as f:
            f.write("User-agent: *\nAllow: /\n")
        print("  -> Created default robots.txt")

    print(f"[OK] Static export build complete at {ROOT_DIR}")


if __name__ == "__main__":
    build_static()
