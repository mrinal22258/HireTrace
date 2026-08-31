import os
import io
import time
import socket
import shutil
import threading
import pytest
import requests

from agents.job_manager import JobManager, CandidateJob
from ui.server import ReusableHTTPServer, HireTraceHandler, root_dir, CASES_DIR, CACHE_DIR, UPLOADS_DIR


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url():
    port = get_free_port()
    server = ReusableHTTPServer(("127.0.0.1", port), HireTraceHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    return f"http://127.0.0.1:{port}"


def test_job_manager_unit():
    jm = JobManager(max_workers=1)
    job = jm.create_job("test_cand_01", "Alice Baker", "Lead Architect")
    assert job.status == "queued"
    assert job.progress_pct == 10

    retrieved = jm.get_job("test_cand_01")
    assert retrieved is not None
    assert retrieved.name == "Alice Baker"

    jm.update_job("test_cand_01", status="evaluating", progress_pct=50, current_step="Mapping requirements")
    updated = jm.get_job("test_cand_01")
    assert updated.status == "evaluating"
    assert updated.progress_pct == 50
    assert updated.current_step == "Mapping requirements"

    job_dict = updated.to_dict()
    assert job_dict["candidate_id"] == "test_cand_01"
    assert job_dict["progress_pct"] == 50


def test_async_upload_and_status_polling(server_url):
    cv_content = (
        "# Liam O'Connor\n"
        "Distributed Systems Architect with 7 years experience in Python, asyncio, uvloop, and Kafka.\n"
        "Designed real-time financial settlement engine processing 20,000 tx/sec."
    )
    files = {
        "cv_file": ("liam_cv.txt", cv_content.encode("utf-8"), "text/plain")
    }
    data = {
        "name": "Liam OConnor",
        "target_role": "Staff Distributed Systems Engineer",
        "interview_notes": "Liam clearly explained partition rebalancing and exactly-once processing semantics in Kafka."
    }

    # 1. Async POST returns immediately with 202 Accepted
    t0 = time.time()
    res = requests.post(f"{server_url}/api/candidate/upload", data=data, files=files, timeout=10)
    elapsed = time.time() - t0

    assert res.status_code == 202, f"Expected 202 Accepted, got {res.status_code}: {res.text}"
    assert elapsed < 3.0, f"Async upload took too long: {elapsed:.2f}s (should be sub-second)"

    resp_json = res.json()
    assert resp_json.get("success") is True
    cid = resp_json.get("candidate_id")
    assert cid and "custom_liam_oconnor" in cid
    assert resp_json.get("status") == "queued"
    assert resp_json.get("poll_url") == f"/api/candidate/{cid}/status"

    # 2. Poll status endpoint until completion
    max_wait_seconds = 60
    poll_start = time.time()
    final_job = None

    while time.time() - poll_start < max_wait_seconds:
        poll_res = requests.get(f"{server_url}/api/candidate/{cid}/status")
        assert poll_res.status_code == 200
        poll_data = poll_res.json()
        status = poll_data.get("status")
        assert status in ("queued", "parsing", "evaluating", "done")

        if status == "done":
            final_job = poll_data
            break
        elif status == "failed":
            pytest.fail(f"Evaluation failed: {poll_data.get('error')}")

        time.sleep(0.5)

    assert final_job is not None, "Evaluation timed out without reaching 'done' status"
    assert final_job["status"] == "done"
    assert final_job["progress_pct"] == 100
    assert "report" in final_job and final_job["report"] is not None
    assert "baseline_a" in final_job and final_job["baseline_a"] is not None

    # Clean up test artifacts
    case_file = os.path.join(CASES_DIR, f"{cid}.json")
    traj_file = os.path.join(CACHE_DIR, f"{cid}_trajectory.json")
    cand_upload_folder = os.path.join(UPLOADS_DIR, cid)
    for p in (case_file, traj_file):
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    if os.path.exists(cand_upload_folder):
        try:
            shutil.rmtree(cand_upload_folder)
        except Exception:
            pass


def test_status_endpoint_not_found(server_url):
    res = requests.get(f"{server_url}/api/candidate/non_existent_candidate_9999/status")
    assert res.status_code == 404
