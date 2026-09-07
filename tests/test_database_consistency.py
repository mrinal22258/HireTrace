"""
Tests validating that the SQL Database is the single source of truth (Phase 2).

Validates:
1. Two concurrent app/process instances pointed at the same database see identical data.
2. Candidate created by process A is immediately readable by process B without in-memory state.
3. Job status updates by worker process A are immediately visible to web process B.
4. Concurrent multi-threaded operations maintain transactional consistency.
"""

import os
import time
import pytest
from concurrent.futures import ThreadPoolExecutor

from agents.db import DatabaseManager


@pytest.fixture
def shared_db_path(tmp_path):
    return str(tmp_path / "shared_cluster.db")


def test_dual_process_candidate_consistency(shared_db_path):
    """Simulates Process A (Web Replica 1) and Process B (Web Replica 2) sharing the same DB."""
    replica_1 = DatabaseManager(db_path=shared_db_path)
    replica_2 = DatabaseManager(db_path=shared_db_path)

    cid = "cand_cluster_001"

    # Replica 1 ingests candidate
    replica_1.upsert_candidate(
        candidate_id=cid,
        name="Elena Rostova",
        target_role="Staff Distributed Systems Architect",
        category="live_applicant",
        status="queued"
    )
    replica_1.save_documents(cid, {
        "cv": "Elena Rostova CV text. 10 years experience with Raft and Paxos.",
        "interview": "Clear technical discussion on distributed consensus."
    })

    # Replica 2 immediately queries the candidate without any in-memory sharing
    cand_on_replica_2 = replica_2.get_candidate_full(cid)
    assert cand_on_replica_2 is not None
    assert cand_on_replica_2["candidate_id"] == cid
    assert cand_on_replica_2["name"] == "Elena Rostova"
    assert cand_on_replica_2["status"] == "queued"
    assert "Raft and Paxos" in cand_on_replica_2["cv_text"]

    # Replica 2 lists candidates
    cases_replica_2 = replica_2.list_candidates(page=1, limit=10)
    assert cases_replica_2["total"] >= 1
    assert any(c["candidate_id"] == cid for c in cases_replica_2["items"])


def test_worker_and_web_replica_job_queue_consistency(shared_db_path):
    """Simulates a worker container updating job status and web container reading it."""
    worker_node = DatabaseManager(db_path=shared_db_path)
    web_node = DatabaseManager(db_path=shared_db_path)

    cid = "cand_job_002"

    # Web node enqueues job
    web_node.upsert_candidate(cid, "Marcus Brody", "Backend Engineer", status="queued")
    web_node.save_job(cid, status="queued", progress_pct=10, current_step="Enqueued in task queue")

    # Worker node reads job
    job = worker_node.get_job(cid)
    assert job is not None
    assert job["status"] == "queued"
    assert job["progress_pct"] == 10

    # Worker node updates progress
    worker_node.save_job(cid, status="evaluating", progress_pct=60, current_step="Cross-source verification")

    # Web node immediately reads updated progress
    updated_job = web_node.get_job(cid)
    assert updated_job["status"] == "evaluating"
    assert updated_job["progress_pct"] == 60
    assert updated_job["current_step"] == "Cross-source verification"

    # Worker completes evaluation
    report = {
        "candidate_id": cid,
        "role_fit_score": 89.0,
        "evidence_consistency_score": 94.0,
        "quadrant": "STRONG MATCH",
        "key_discrepancies": []
    }
    worker_node.save_evaluation(
        candidate_id=cid,
        role_fit_score=89.0,
        evidence_consistency_score=94.0,
        quadrant="STRONG MATCH",
        report_dict=report,
        baseline_a_dict={"overall_score": 85.0}
    )
    worker_node.save_job(cid, status="done", progress_pct=100, current_step="Assessment complete")

    # Web node reads final evaluation
    eval_result = web_node.get_evaluation(cid)
    assert eval_result is not None
    assert eval_result["quadrant"] == "STRONG MATCH"
    assert eval_result["report"]["role_fit_score"] == 89.0

    full_cand = web_node.get_candidate_full(cid)
    assert full_cand["status"] == "done"
    assert full_cand["quadrant"] == "STRONG MATCH"


def test_concurrent_multi_replica_writes(shared_db_path):
    """Tests 10 concurrent threads acting as separate API replicas writing to the DB."""
    db = DatabaseManager(db_path=shared_db_path)

    def _write_candidate(idx: int):
        replica = DatabaseManager(db_path=shared_db_path)
        cid = f"concurrent_cand_{idx:03d}"
        replica.upsert_candidate(cid, f"Candidate {idx}", "Engineer", status="done")
        replica.save_documents(cid, {"cv": f"CV for candidate {idx}"})
        replica.save_evaluation(
            candidate_id=cid,
            role_fit_score=75.0 + (idx % 20),
            evidence_consistency_score=80.0,
            quadrant="STRONG MATCH",
            report_dict={"role_fit_score": 75.0 + (idx % 20)}
        )
        return cid

    with ThreadPoolExecutor(max_workers=8) as executor:
        cids = list(executor.map(_write_candidate, range(25)))

    # Verify all 25 candidates were persisted
    res = db.list_candidates(page=1, limit=50)
    assert res["total"] == 25
    assert len(res["items"]) == 25
