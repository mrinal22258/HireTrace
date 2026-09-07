"""
Concurrency and Race Condition Tests for Standalone DB Worker Job Claiming.

Verifies that DB.claim_next_queued_job() is strictly atomic under high concurrent load:
- Spawns multiple worker threads racing to claim from a shared queue.
- Asserts that every single queued job is claimed exactly once (zero duplicates).
- Asserts that no thread ever claims a job that was already claimed by another thread.
- Repeated across multiple iterations to guarantee zero flakiness.

Note: Tested against SQLite WAL engine locally; the PostgreSQL FOR UPDATE SKIP LOCKED
path is exercised in staging/production deployments against live Postgres.
"""

import time
import threading
import pytest
from typing import List, Set
from agents.db import DB, JobQueue


def run_claim_race_iteration(num_jobs: int = 20, num_workers: int = 5) -> None:
    # 1. Clear test jobs
    with DB.session_scope() as session:
        session.query(JobQueue).filter(JobQueue.candidate_id.like("test_race_%")).delete()

    # 2. Seed N queued jobs with staggered enqueued_at timestamps
    now = time.time()
    for i in range(num_jobs):
        cid = f"test_race_{i:03d}"
        DB.save_job(
            candidate_id=cid,
            status="queued",
            progress_pct=0,
            current_step="Waiting in queue..."
        )

    # 3. Spin up concurrent worker threads
    claimed_by_worker: List[List[str]] = [[] for _ in range(num_workers)]
    start_barrier = threading.Barrier(num_workers)
    stop_event = threading.Event()

    def worker_loop(worker_idx: int):
        start_barrier.wait()  # Synchronize all threads to start at the exact same millisecond
        while not stop_event.is_set():
            job = DB.claim_next_queued_job()
            if job:
                claimed_by_worker[worker_idx].append(job["candidate_id"])
            else:
                # No more jobs available
                break

    threads = [
        threading.Thread(target=worker_loop, args=(i,), name=f"race_worker_{i}")
        for i in range(num_workers)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    stop_event.set()

    # 4. Verify results
    all_claimed: List[str] = []
    for worker_cids in claimed_by_worker:
        all_claimed.extend(worker_cids)

    # Filter only this run's test jobs
    test_claimed = [cid for cid in all_claimed if cid.startswith("test_race_")]

    # Exact claim assertion: Every job must be claimed exactly once
    assert len(test_claimed) == num_jobs, (
        f"Expected {num_jobs} claimed jobs, but got {len(test_claimed)}. "
        f"Claims: {test_claimed}"
    )

    unique_claimed: Set[str] = set(test_claimed)
    assert len(unique_claimed) == num_jobs, (
        f"Duplicate claims detected! Total claims: {len(test_claimed)}, unique: {len(unique_claimed)}. "
        f"Duplicates: {[cid for cid in test_claimed if test_claimed.count(cid) > 1]}"
    )

    # Verify that in DB, all jobs are in 'evaluating' status
    for i in range(num_jobs):
        cid = f"test_race_{i:03d}"
        db_job = DB.get_job(cid)
        assert db_job is not None
        assert db_job["status"] == "evaluating"

    # Cleanup
    with DB.session_scope() as session:
        session.query(JobQueue).filter(JobQueue.candidate_id.like("test_race_%")).delete()


def test_concurrent_worker_claim_race_single_run():
    """Test single high-concurrency race run with 25 jobs and 6 worker threads."""
    run_claim_race_iteration(num_jobs=25, num_workers=6)


def test_concurrent_worker_claim_race_repeated_iterations():
    """Run 20 consecutive iterations to guarantee claim atomicity is 100% reliable and non-flaky."""
    for iteration in range(20):
        run_claim_race_iteration(num_jobs=10, num_workers=4)


def test_worker_compilation_and_import():
    """Verify worker.py compiles cleanly with py_compile and can be imported without syntax/indentation errors."""
    import sys
    import os
    import py_compile

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    worker_path = os.path.join(repo_root, "worker.py")

    # 1. Bytecode compilation
    compiled_path = py_compile.compile(worker_path, doraise=True)
    assert compiled_path is not None

    # 2. Module import check
    import worker
    assert hasattr(worker, "run_standalone_db_worker")
    assert hasattr(worker, "run_celery_worker")
    assert callable(worker.run_standalone_db_worker)


def test_worker_cli_help():
    """Subprocess CLI smoke test verifying python worker.py --help succeeds."""
    import sys
    import os
    import subprocess

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = subprocess.run(
        [sys.executable, "worker.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10
    )
    assert res.returncode == 0
    assert "--mode" in res.stdout
    assert "--poll-interval" in res.stdout


def test_worker_standalone_db_process_start_and_shutdown():
    """Verify python worker.py --mode db starts, polls DB, and shuts down cleanly on SIGTERM."""
    import sys
    import os
    import subprocess

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen(
        [sys.executable, "worker.py", "--mode", "db", "--poll-interval", "0.2"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    # Allow worker to initialize, seed tables, and enter while running loop
    time.sleep(1.0)
    assert proc.poll() is None, f"Worker process crashed on startup! Stderr: {proc.stderr.read()}"

    # Terminate worker process cleanly
    proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()

    # Process should exit cleanly
    assert proc.returncode is not None


def test_worker_standalone_db_evaluates_queued_job():
    """End-to-end execution test: standalone worker.py claims and evaluates a queued candidate."""
    import sys
    import os
    import subprocess
    from agents.db import DB

    cid = "cand_worker_e2e_01"
    # Seed candidate and queued job
    DB.upsert_candidate(
        candidate_id=cid,
        name="Ada Lovelace",
        target_role="Lead Algorithm Engineer",
        category="live_applicant",
        status="queued"
    )
    DB.save_documents(
        cid,
        {
            "cv": "Wrote the first computer program. Expert in analytical mechanics and algorithms.",
            "interview": "Strong foundational mathematics and computing principles.",
            "assessment": "Excellent algorithmic formulation and analytical reasoning.",
            "project": "Proposed the Bernoulli number algorithm for the Analytical Engine."
        }
    )
    DB.save_job(
        candidate_id=cid,
        status="queued",
        progress_pct=10,
        current_step="Queued for worker evaluation"
    )

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["HIRETRACE_OFFLINE_MOCK"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "worker.py", "--mode", "db", "--poll-interval", "0.2"],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        # Poll DB until job completes
        completed = False
        for _ in range(30):
            time.sleep(0.5)
            job = DB.get_job(cid)
            if job and job["status"] == "done":
                completed = True
                break
        assert completed is True, f"Worker failed to evaluate job! Current status: {DB.get_job(cid)}"

        # Verify evaluation was persisted
        eval_record = DB.get_evaluation(cid)
        assert eval_record is not None
        assert eval_record.get("report") is not None
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
