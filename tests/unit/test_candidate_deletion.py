"""
Unit and regression tests for candidate data deletion and retention policies:
1. DELETE /api/candidate/{candidate_id} removes DB rows, files, and cache entries.
2. Deleting nonexistent candidate returns HTTP 404.
3. Deleting with path-traversal ID returns HTTP 400 with no filesystem side effects.
4. Retention policy purge deletes candidates older than HIRETRACE_DATA_RETENTION_DAYS.
"""

import os
import json
import time
import pytest
from fastapi.testclient import TestClient

from ui.server import app, CASES_DIR, UPLOADS_DIR, CACHE_DIR
from agents.db import DB, Candidate, Document, Evaluation
from agents.retention import purge_expired_candidates, delete_candidate_artifacts
from agents.embedding_cache import EMBEDDING_CACHE


@pytest.fixture
def client():
    return TestClient(app)


def test_delete_candidate_success(client, monkeypatch):
    """Test that DELETE /api/candidate/{candidate_id} cleans DB rows, files, and cache entries."""
    monkeypatch.setenv("HIRETRACE_DEV_MODE", "1")
    cid = "test_candidate_to_delete_99"

    # 1. Setup DB rows
    DB.upsert_candidate(candidate_id=cid, name="Delete Me", target_role="Engineer")
    DB.save_documents(cid, {"cv": "Curriculum vitae text to delete."})
    DB.save_evaluation(cid, role_fit_score=85.0, evidence_consistency_score=90.0, quadrant="STRONG MATCH", report_dict={"summary": "ok"})
    
    # 2. Setup filesystem artifacts
    cand_upload_dir = os.path.join(UPLOADS_DIR, cid)
    os.makedirs(cand_upload_dir, exist_ok=True)
    cv_file = os.path.join(cand_upload_dir, "resume.txt")
    with open(cv_file, "w", encoding="utf-8") as f:
        f.write("Candidate resume content")

    disk_case = os.path.join(CASES_DIR, f"{cid}.json")
    with open(disk_case, "w", encoding="utf-8") as f:
        json.dump({"candidate_id": cid, "name": "Delete Me"}, f)

    traj_file = os.path.join(CACHE_DIR, f"{cid}_trajectory.json")
    with open(traj_file, "w", encoding="utf-8") as f:
        json.dump({"candidate_id": cid, "steps": []}, f)

    # 3. Setup embedding cache fingerprint
    EMBEDDING_CACHE.save_candidate_fingerprint(cid, "fp_test_delete_123")
    assert EMBEDDING_CACHE.get_candidate_fingerprint(cid) == "fp_test_delete_123"

    # Verify everything exists before deletion
    assert DB.get_candidate_full(cid) is not None
    assert os.path.exists(cand_upload_dir)
    assert os.path.exists(disk_case)
    assert os.path.exists(traj_file)

    # 4. Call DELETE endpoint
    resp = client.delete(f"/api/candidate/{cid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["summary"]["status"] == "deleted"

    # 5. Assert DB rows removed
    assert DB.get_candidate_full(cid) is None
    with DB.session_scope() as session:
        assert session.query(Candidate).filter_by(candidate_id=cid).first() is None
        assert session.query(Document).filter_by(candidate_id=cid).first() is None
        assert session.query(Evaluation).filter_by(candidate_id=cid).first() is None

    # 6. Assert filesystem artifacts removed
    assert not os.path.exists(cand_upload_dir)
    assert not os.path.exists(disk_case)
    assert not os.path.exists(traj_file)

    # 7. Assert cache evicted
    assert EMBEDDING_CACHE.get_candidate_fingerprint(cid) is None


def test_delete_nonexistent_candidate_returns_404(client, monkeypatch):
    """Deleting a candidate that does not exist returns HTTP 404."""
    monkeypatch.setenv("HIRETRACE_DEV_MODE", "1")
    resp = client.delete("/api/candidate/nonexistent_cand_xyz_404")
    assert resp.status_code == 404
    assert "not found" in resp.text.lower()


def test_delete_path_traversal_returns_400_with_no_filesystem_effects(client, monkeypatch):
    """Attempting path traversal in DELETE returns HTTP 400 and does not delete outer files."""
    monkeypatch.setenv("HIRETRACE_DEV_MODE", "1")

    # Attempt path traversal
    resp1 = client.delete("/api/candidate/..")
    assert resp1.status_code in (400, 404, 422)

    resp2 = client.delete("/api/candidate/../traversal")
    assert resp2.status_code in (400, 404, 422)


def test_retention_purge_deletes_only_expired_candidates(monkeypatch):
    """Test that retention purge deletes only candidates older than retention threshold."""
    now = time.time()
    
    old_cid = "test_cand_retention_old_100d"
    new_cid = "test_cand_retention_new_2d"

    # Insert old candidate (100 days old)
    DB.upsert_candidate(candidate_id=old_cid, name="Old Cand", target_role="Engineer")
    with DB.session_scope() as session:
        cand = session.query(Candidate).filter_by(candidate_id=old_cid).first()
        cand.created_at = now - (100 * 86400)

    # Insert new candidate (2 days old)
    DB.upsert_candidate(candidate_id=new_cid, name="New Cand", target_role="Engineer")
    with DB.session_scope() as session:
        cand = session.query(Candidate).filter_by(candidate_id=new_cid).first()
        cand.created_at = now - (2 * 86400)

    assert DB.get_candidate_full(old_cid) is not None
    assert DB.get_candidate_full(new_cid) is not None

    # Run retention purge with 30-day window
    purged = purge_expired_candidates(retention_days=30)
    purged_ids = [p["candidate_id"] for p in purged]

    assert old_cid in purged_ids
    assert new_cid not in purged_ids

    # Verify old candidate is gone from DB, new candidate remains
    assert DB.get_candidate_full(old_cid) is None
    assert DB.get_candidate_full(new_cid) is not None

    # Clean up new candidate
    delete_candidate_artifacts(new_cid)
    assert DB.get_candidate_full(new_cid) is None
