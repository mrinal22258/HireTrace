"""
Tests for Phase 8: Evaluation Progress Monotonicity & Single-Flight Concurrency.

Covers:
1. Monotonicity guard in DB.save_job and JobManager.update_job:
   - Prevents stale or out-of-order writes from lowering progress_pct while in 'evaluating'.
   - Allows progress_pct transitions when moving to terminal or fresh queued state.
2. Single-flight concurrency guard in JobManager.submit_evaluation:
   - Concurrent/duplicate evaluation requests for the same candidate_id return the existing active job
     without enqueuing duplicate pipeline runs or resetting progress.
3. Single-flight guard in FastAPI /api/evaluate/{candidate_id}:
   - If an evaluation job is queued/evaluating/retrying, endpoint returns HTTP 202 with poll_url
     instead of launching a second untracked PIPELINE.run().
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from agents.db import DB, JobQueue
from agents.job_manager import JobManager, CandidateJob, JOB_MANAGER
from ui.server import app


@pytest.fixture(autouse=True)
def clean_test_jobs():
    """Clean up test jobs before and after each test."""
    test_prefix = "test_mono_"
    with DB.session_scope() as session:
        session.query(JobQueue).filter(JobQueue.candidate_id.like(f"{test_prefix}%")).delete()
    yield
    with DB.session_scope() as session:
        session.query(JobQueue).filter(JobQueue.candidate_id.like(f"{test_prefix}%")).delete()


def test_db_save_job_progress_monotonicity():
    """Verify DB.save_job rejects writes that reduce progress_pct while evaluating."""
    cid = "test_mono_monotonicity_01"

    # 1. Create job in evaluating status at 45%
    DB.save_job(
        candidate_id=cid,
        status="evaluating",
        progress_pct=45,
        current_step="Cross-source verification",
    )
    job = DB.get_job(cid)
    assert job is not None
    assert job["progress_pct"] == 45
    assert job["status"] == "evaluating"

    # 2. Attempt stale write with lower progress (20%) while evaluating -> MUST BE REJECTED
    DB.save_job(
        candidate_id=cid,
        status="evaluating",
        progress_pct=20,
        current_step="Late arrival step",
    )
    job = DB.get_job(cid)
    assert job["progress_pct"] == 45, "Monotonicity guard should reject lower progress_pct"

    # 3. Valid write with higher progress (75%) -> MUST SUCCEED
    DB.save_job(
        candidate_id=cid,
        status="evaluating",
        progress_pct=75,
        current_step="Aggregating evidence",
    )
    job = DB.get_job(cid)
    assert job["progress_pct"] == 75

    # 4. Completion transition to 'done' at 100% -> MUST SUCCEED
    DB.save_job(
        candidate_id=cid,
        status="done",
        progress_pct=100,
        current_step="Complete",
    )
    job = DB.get_job(cid)
    assert job["status"] == "done"
    assert job["progress_pct"] == 100

    # 5. Subsequent fresh evaluation from queued -> permitted after terminal status
    DB.save_job(
        candidate_id=cid,
        status="queued",
        progress_pct=10,
        current_step="Queued for re-evaluation",
    )
    job = DB.get_job(cid)
    assert job["status"] == "queued"
    assert job["progress_pct"] == 10


def test_job_manager_in_memory_monotonicity():
    """Verify JobManager.update_job rejects lower progress in-memory and in DB."""
    jm = JobManager()
    cid = "test_mono_in_memory_02"
    job = jm.create_job(cid, name="Test Candidate", target_role="Staff SRE")

    jm.update_job(cid, status="evaluating", progress_pct=50, current_step="Step 1")
    cached = jm.get_job(cid)
    assert cached.progress_pct == 50

    # Lower progress update attempt
    jm.update_job(cid, status="evaluating", progress_pct=30, current_step="Step 0 again")
    cached = jm.get_job(cid)
    assert cached.progress_pct == 50, "JobManager in-memory update_job must reject backwards progress"


def test_submit_evaluation_single_flight_guard():
    """Verify JobManager.submit_evaluation attaches to active job without re-dispatching."""
    jm = JobManager()
    cid = "test_mono_single_flight_03"
    case_data = {
        "candidate_id": cid,
        "name": "Single Flight Candidate",
        "target_role": "Staff SRE"
    }

    # Mock dispatch function
    dispatch_mock = MagicMock()
    with patch.object(jm, "_run_job_worker", dispatch_mock):
        # First submission -> creates job and dispatches
        job1 = jm.submit_evaluation(case_data)
        assert job1.candidate_id == cid
        assert job1.status == "queued"

        # Advance job to evaluating at 60%
        jm.update_job(cid, status="evaluating", progress_pct=60, current_step="Analyzing")

        # Second concurrent submission -> must return existing active job without dispatching second task
        job2 = jm.submit_evaluation(case_data)
        assert job2.candidate_id == cid
        assert job2.status == "evaluating"
        assert job2.progress_pct == 60


def test_api_evaluate_avoids_duplicate_run_when_job_active():
    """Verify /api/evaluate/{candidate_id} returns 202 when job is already queued or evaluating."""
    client = TestClient(app)
    cid = "test_mono_api_guard_04"

    # Register candidate in DB first
    DB.upsert_candidate(
        candidate_id=cid,
        name="Concurrent Test Candidate",
        target_role="Frontend Engineer",
        status="evaluating",
        tenant_id="default_tenant",
    )

    # Put a job in 'evaluating' status
    JOB_MANAGER.create_job(cid, name="Concurrent Test Candidate", target_role="Frontend Engineer")
    JOB_MANAGER.update_job(cid, status="evaluating", progress_pct=40, current_step="Parsing")

    with patch("agents.pipeline.HireTracePipeline.run") as mock_pipeline_run:
        # Request evaluation while active job exists
        response = client.post(
            f"/api/evaluate/{cid}",
            headers={"X-API-Key": "test_dev_key"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "evaluating"
        assert data["progress_pct"] == 40
        assert data["poll_url"] == f"/api/candidate/{cid}/status"
        # Crucial check: PIPELINE.run must NOT have been called!
        mock_pipeline_run.assert_not_called()
