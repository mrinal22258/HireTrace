import os
import time
import pytest
from agents.db import DatabaseManager


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_hiretrace.db")
    db = DatabaseManager(db_path=db_file)
    return db


def test_database_crud_and_documents(temp_db):
    cid = "cand_test_001"
    temp_db.upsert_candidate(
        candidate_id=cid,
        name="Jordan Lee",
        target_role="Lead Platform Engineer",
        category="applicant",
        status="done"
    )

    # Save documents
    docs = {
        "cv": "Jordan Lee resume text with 10 years experience.",
        "interview": "Strong architectural explanations."
    }
    raw_meta = {
        "cv": {"disk_path": "/tmp/cv.pdf", "sha256": "fake_hash_12345", "size_bytes": 1024}
    }
    temp_db.save_documents(cid, docs, raw_meta)

    # Save evaluation
    report = {
        "candidate_id": cid,
        "role_fit_score": 88.5,
        "evidence_consistency_score": 92.0,
        "quadrant": "STRONG MATCH",
        "critical_discrepancies": []
    }
    rubric = {"overall_score": 84.0}
    temp_db.save_evaluation(
        candidate_id=cid,
        role_fit_score=88.5,
        evidence_consistency_score=92.0,
        quadrant="STRONG MATCH",
        report_dict=report,
        baseline_a_dict=rubric,
        latency_ms=120.0
    )

    # Fetch full candidate
    cand_full = temp_db.get_candidate_full(cid)
    assert cand_full is not None
    assert cand_full["name"] == "Jordan Lee"
    assert cand_full["role_fit_score"] == 88.5
    assert cand_full["quadrant"] == "STRONG MATCH"
    assert cand_full["cv_text"] == docs["cv"]
    assert cand_full["raw_documents"]["cv"]["sha256"] == "fake_hash_12345"

    # Deduplication hash lookup
    found_cid = temp_db.check_dedup_hash("fake_hash_12345")
    assert found_cid == cid


def test_database_pagination_and_search(temp_db):
    # Insert 15 mock candidates
    quadrants = ["STRONG MATCH", "REVIEW REQUIRED", "INSUFFICIENT EVIDENCE", "WEAK MATCH", "LOW_FIT_FAST_REJECT"]
    for i in range(15):
        cid = f"cand_{i:02d}"
        q = quadrants[i % len(quadrants)]
        name = f"Candidate {i:02d} {'Alpha' if i < 5 else 'Beta'}"
        temp_db.upsert_candidate(cid, name, "Systems Engineer", "applicant", "done")
        temp_db.save_evaluation(cid, 70.0 + i, 80.0, q, {"critical_discrepancies": []})

    # 1. Test pagination page 1 with limit 5
    page1 = temp_db.list_candidates(page=1, limit=5)
    assert page1["total"] == 15
    assert page1["page"] == 1
    assert page1["limit"] == 5
    assert page1["pages"] == 3
    assert len(page1["items"]) == 5

    # 2. Test pagination page 2
    page2 = temp_db.list_candidates(page=2, limit=5)
    assert len(page2["items"]) == 5
    assert page2["items"][0]["candidate_id"] != page1["items"][0]["candidate_id"]

    # 3. Test quadrant filter
    strong_results = temp_db.list_candidates(quadrant="STRONG MATCH")
    assert strong_results["total"] == 3
    for it in strong_results["items"]:
        assert it["quadrant"] == "STRONG MATCH"

    # 4. Test text search filter
    alpha_results = temp_db.list_candidates(search="Alpha")
    assert alpha_results["total"] == 5
    for it in alpha_results["items"]:
        assert "Alpha" in it["name"]


def test_concurrent_database_reads_writes(temp_db):
    import concurrent.futures

    def worker_write(i):
        cid = f"concurrent_cand_{i}"
        temp_db.upsert_candidate(cid, f"Concurrent Candidate {i}", "Software Engineer", "applicant", "done")
        temp_db.save_evaluation(cid, 80.0 + (i % 20), 90.0, "STRONG MATCH", {"test": True})
        return temp_db.get_candidate_full(cid)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_write, i) for i in range(25)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 25
    assert all(r is not None for r in results)


def test_postgres_url_switch(monkeypatch, tmp_path):
    # Test that setting DATABASE_URL configures the engine URL properly
    custom_url = f"sqlite:///{str(tmp_path / 'pg_mock.db').replace('\\', '/')}"
    monkeypatch.setenv("DATABASE_URL", custom_url)
    db = DatabaseManager()
    assert db.database_url == custom_url

