"""
Regression tests for path traversal prevention in candidate_id validation and filesystem writing.
Validates that malicious inputs (e.g. '..', '../test', '/root') are rejected with 400 or 422
and never result in file creation outside intended base directories.
"""

import os
import pytest
from fastapi.testclient import TestClient
from ui.server import app, UPLOADS_DIR, CASES_DIR

client = TestClient(app)


def test_candidate_new_rejects_path_traversal_dots():
    """POSTing candidate_id='..' to /api/candidate/new must return 400 or 422."""
    payload = {
        "candidate_id": "..",
        "name": "Traversal Attacker",
        "target_role": "Security Researcher",
        "cv_text": "Trying to write outside base directory."
    }
    resp = client.post("/api/candidate/new", json=payload)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"

    # Verify no file named '...json' was created outside CASES_DIR
    parent_dir = os.path.dirname(CASES_DIR)
    escaped_file = os.path.join(parent_dir, "..json")
    assert not os.path.exists(escaped_file)


def test_candidate_upload_rejects_path_traversal_dots():
    """POSTing candidate_id='..' to /api/candidate/upload must return 400 or 422."""
    data = {
        "candidate_id": "..",
        "name": "Traversal Attacker Upload",
        "target_role": "Security Researcher",
        "cv_text": "Trying to write outside base directory via upload."
    }
    resp = client.post("/api/candidate/upload", data=data)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"

    # Verify no upload folder named '..' was created outside UPLOADS_DIR
    parent_dir = os.path.dirname(UPLOADS_DIR)
    escaped_file = os.path.join(parent_dir, "..")
    # Even if parent_dir exists, make sure no subfolder or file was compromised
    assert not os.path.exists(os.path.join(UPLOADS_DIR, "..", "cv_test.txt"))


def test_candidate_id_with_nested_traversal_rejected():
    """POSTing candidate_id='../../etc/passwd' must return 400 or 422."""
    for bad_id in ("../../etc/passwd", "..\\windows\\win.ini", "sub/dir", "cand.id.with.dots"):
        resp = client.post(
            "/api/candidate/new",
            json={
                "candidate_id": bad_id,
                "name": "Nested Attacker",
                "cv_text": "Sample text"
            }
        )
        assert resp.status_code in (400, 422), f"Failed for {bad_id}: {resp.status_code}"
