"""
Unit tests validating .dockerignore rules and repository cleanliness.
Ensures production Docker context excludes all local databases, test artifacts,
caches, and credential files.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_dockerignore_exists_and_contains_mandatory_patterns():
    """Verify .dockerignore exists and excludes all sensitive runtime files."""
    dockerignore_path = ROOT_DIR / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore file must exist in repo root"

    content = dockerignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

    mandatory_patterns = [
        ".git",
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        ".coverage",
        "hiretrace.db",
        "hiretrace.db-wal",
        "hiretrace.db-shm",
        "uploads/",
        "eval_cases/cache/",
        "*.zip",
        "*.mp4",
        "video/",
        "scratch/",
        ".env",
        "tests/",
    ]

    for pattern in mandatory_patterns:
        matched = any(pattern in line for line in lines)
        assert matched, f"Mandatory pattern '{pattern}' missing from .dockerignore"


def test_package_submission_excludes_runtime_and_database_files(tmp_path):
    """Test that package_submission produces a zip with zero db, coverage, or runtime artifacts."""
    import zipfile
    from scripts.package_submission import package_submission

    out_zip = str(tmp_path / "test_submission.zip")
    package_submission(out_zip, include_video=False)

    assert os.path.exists(out_zip)
    with zipfile.ZipFile(out_zip, "r") as zf:
        names = zf.namelist()

    forbidden_substrings = [
        "hiretrace.db",
        ".coverage",
        ".git/",
        "__pycache__",
        ".pytest_cache",
        "uploads/",
        "eval_cases/cache/",
        ".env"
    ]

    for name in names:
        if name == ".env.example":
            continue
        for bad in forbidden_substrings:
            assert bad not in name, f"Forbidden artifact '{bad}' leaked into submission zip: {name}"

