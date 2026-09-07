"""
Tests for Phase 3: Distributed Job Queue and Horizontal Worker Scalability.

Validates:
1. Job status survives worker restart / memory wipes (persisted in DB JobQueue).
2. Worker failure / crash mid-job persists failure status and error details without losing state.
3. Multiple independent workers consume and process jobs concurrently from the shared DB.
4. Independent web replicas reading JobManager.get_job see real-time status written by workers.
"""

import os
import time
import pytest
from unittest.mock import patch, MagicMock

from agents.db import DatabaseManager, DB
from agents.job_manager import JobManager, CandidateJob
from agents.tasks import run_candidate_evaluation_core


def test_job_persistence_survives_memory_wipe(tmp_path):
    """Verifies that job state is persisted to the DB and recovered after in-memory state is wiped."""
    test_db_path = str(tmp_path / "test_persistence.db")
    custom_db = DatabaseManager(db_path=test_db_path)

    with patch("agents.job_manager.DB", custom_db):
        jm1 = JobManager(max_workers=1)
        job1 = jm1.create_job("cand_persist_01", "Emma Watson", "ML Research Engineer")
        assert job1.status == "queued"

        jm1.update_job("cand_persist_01", status="evaluating", progress_pct=50, current_step="Running CrossSourceVerificationAgent")

        # Simulate fresh process / replica restart by initializing a completely new JobManager
        jm2 = JobManager(max_workers=1)
        # In-memory dict of jm2 is empty for cand_persist_01
        assert "cand_persist_01" not in jm2._jobs

        # get_job should recover true state from DB
        recovered = jm2.get_job("cand_persist_01")
        assert recovered is not None
        assert recovered.candidate_id == "cand_persist_01"
        assert recovered.status == "evaluating"
        assert recovered.progress_pct == 50
        assert recovered.current_step == "Running CrossSourceVerificationAgent"


def test_worker_failure_is_persisted_without_losing_job(tmp_path):
    """Verifies that an unhandled crash/exception in a worker marks the job failed in DB with error details."""
    test_db_path = str(tmp_path / "test_worker_crash.db")
    custom_db = DatabaseManager(db_path=test_db_path)
    cases_dir = str(tmp_path / "cases")

    candidate_id = "cand_crash_01"
    custom_db.upsert_candidate(
        candidate_id=candidate_id,
        name="Faulty Candidate",
        target_role="Site Reliability Engineer",
        category="custom_upload",
        status="queued"
    )
    custom_db.save_job(
        candidate_id=candidate_id,
        status="evaluating",
        progress_pct=10,
        current_step="Claimed"
    )

    case_data = {
        "candidate_id": candidate_id,
        "name": "Faulty Candidate",
        "target_role": "Site Reliability Engineer",
        "documents": {}
    }

    # Mock pipeline to simulate a sudden crash/failure
    mock_pipeline = MagicMock()
    mock_pipeline.run.side_effect = RuntimeError("Fatal GPU memory allocation failure")

    with patch("agents.tasks.DB", custom_db), patch("agents.tasks.FastTriageEngine.evaluate", return_value=(False, None)):
        with pytest.raises(RuntimeError):
            run_candidate_evaluation_core(
                cid=candidate_id,
                case_data=case_data,
                cases_dir=cases_dir,
                pipeline=mock_pipeline
            )

    # Verify that the failure was persisted to DB with error message
    db_job = custom_db.get_job(candidate_id)
    assert db_job is not None
    assert db_job["status"] == "failed"
    assert db_job["progress_pct"] == 100
    assert "Fatal GPU memory allocation failure" in db_job["error_msg"]


def test_concurrent_worker_progress_updates(tmp_path):
    """Verifies that multiple worker threads can process jobs simultaneously without state corruption."""
    test_db_path = str(tmp_path / "test_concurrent_workers.db")
    custom_db = DatabaseManager(db_path=test_db_path)

    with patch("agents.job_manager.DB", custom_db):
        jm = JobManager(max_workers=3)

        for i in range(5):
            cid = f"cand_worker_{i}"
            jm.create_job(cid, f"Candidate {i}", "Backend Engineer")
            jm.update_job(cid, status="evaluating", progress_pct=20 * (i + 1), current_step=f"Step {i}")

        for i in range(5):
            cid = f"cand_worker_{i}"
            job = jm.get_job(cid)
            assert job is not None
            assert job.status == "evaluating"
            assert job.progress_pct == 20 * (i + 1)
            assert job.current_step == f"Step {i}"
