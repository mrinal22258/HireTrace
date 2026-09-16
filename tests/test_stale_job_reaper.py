"""
Unit tests for the stale/orphaned job reaper mechanism.

Verifies:
1. DB.reap_stale_jobs() properly detects and fails stuck 'evaluating' jobs.
2. Fresh/in-progress jobs within the timeout threshold are NOT reaped.
3. JobManager.get_job() lazy self-healing detects and fails stale jobs on poll.
"""

import time
import pytest
from agents.db import DB, JobQueue
from agents.job_manager import JobManager


@pytest.fixture(autouse=True)
def clean_test_jobs():
    test_prefix = "test_stale_reap_"
    with DB.session_scope() as session:
        session.query(JobQueue).filter(JobQueue.candidate_id.like(f"{test_prefix}%")).delete()
    yield
    with DB.session_scope() as session:
        session.query(JobQueue).filter(JobQueue.candidate_id.like(f"{test_prefix}%")).delete()


def test_db_reap_stale_jobs():
    now = time.time()
    stale_cid = "test_stale_reap_crashed_worker"
    fresh_cid = "test_stale_reap_healthy_worker"

    # Seed stale job: evaluated 600s ago (stuck)
    with DB.session_scope() as session:
        stale_job = JobQueue(
            id=f"job_{stale_cid}",
            candidate_id=stale_cid,
            status="evaluating",
            progress_pct=40,
            current_step="Evaluating candidate claims...",
            enqueued_at=now - 700,
            started_at=now - 600,
            updated_at=now - 600,
        )
        # Seed fresh job: updated 20s ago
        fresh_job = JobQueue(
            id=f"job_{fresh_cid}",
            candidate_id=fresh_cid,
            status="evaluating",
            progress_pct=60,
            current_step="Retrieving cross-source evidence...",
            enqueued_at=now - 30,
            started_at=now - 25,
            updated_at=now - 20,
        )
        session.add(stale_job)
        session.add(fresh_job)

    # Run reaper with 300s timeout
    reaped = DB.reap_stale_jobs(timeout_seconds=300.0)

    assert stale_cid in reaped
    assert fresh_cid not in reaped

    # Verify stale job state
    stale_record = DB.get_job(stale_cid)
    assert stale_record is not None
    assert stale_record["status"] == "failed"
    assert "Job timed out — worker may have crashed. Please retry." in stale_record["error_msg"]

    # Verify fresh job state is intact
    fresh_record = DB.get_job(fresh_cid)
    assert fresh_record is not None
    assert fresh_record["status"] == "evaluating"


def test_job_manager_lazy_stale_self_healing(monkeypatch):
    now = time.time()
    lazy_stale_cid = "test_stale_reap_lazy_poll"

    # Seed an evaluating job that was abandoned 400s ago
    with DB.session_scope() as session:
        job = JobQueue(
            id=f"job_{lazy_stale_cid}",
            candidate_id=lazy_stale_cid,
            status="evaluating",
            progress_pct=35,
            current_step="Step 2: Processing embeddings",
            enqueued_at=now - 500,
            started_at=now - 400,
            updated_at=now - 400,
        )
        session.add(job)

    # Set timeout threshold to 300s
    monkeypatch.setenv("HIRETRACE_JOB_STALE_TIMEOUT_SECONDS", "300")

    jm = JobManager(max_workers=1)
    res = jm.get_job(lazy_stale_cid)

    assert res is not None
    assert res.status == "failed"
    assert "Job timed out — worker may have crashed. Please retry." in (res.error or "")

    # Check DB was also updated
    db_res = DB.get_job(lazy_stale_cid)
    assert db_res["status"] == "failed"
