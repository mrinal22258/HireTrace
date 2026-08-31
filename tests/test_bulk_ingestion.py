import os
import io
import time
import zipfile
import socket
import shutil
import threading
import pytest
import requests

from agents.bulk_ingestion import BulkIngestionEngine, format_candidate_name
from agents.db import DB
from ui.server import ReusableHTTPServer, HireTraceHandler, root_dir, CASES_DIR, CACHE_DIR, UPLOADS_DIR, PIPELINE, ALL_CASES


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


def test_format_candidate_name():
    assert format_candidate_name("cynthia_vance") == "Cynthia Vance"
    assert format_candidate_name("david-kim-resume") == "David Kim"
    assert format_candidate_name("jane_doe_cv.pdf") == "Jane Doe"


def create_sample_zip(include_subfolders: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if include_subfolders:
            cv_a = "# Cynthia Vance\nSenior Backend Architect with 8 years Python, AsyncIO, and Kafka experience."
            interview_a = "Cynthia demonstrated strong knowledge of partition rebalancing."
            cv_b = "# David Kim\nStaff Systems Engineer specializing in distributed consensus and raft protocols."

            z.writestr("applicants/cynthia_vance/cv.txt", cv_a)
            z.writestr("applicants/cynthia_vance/interview_notes.txt", interview_a)
            z.writestr("applicants/david_kim/cv.txt", cv_b)
        else:
            cv_flat1 = "# Rachel Adams\nLead Platform Engineer with 6 years experience in Kubernetes, Python, and microservices."
            cv_flat2 = "# Steven Choi\nInfrastructure Engineer building high-throughput message brokers in Python."
            z.writestr("rachel_adams.txt", cv_flat1)
            z.writestr("steven_choi.txt", cv_flat2)

    return buf.getvalue()


def test_bulk_engine_zip_and_deduplication():
    # Clean any leftover test cases from ALL_CASES and DB before test
    ALL_CASES[:] = [c for c in ALL_CASES if not c.get("candidate_id", "").startswith("custom_bulk_")]
    with DB._lock:
        conn = DB._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM dedup_hashes WHERE candidate_id LIKE 'custom_bulk_%';")
                conn.execute("DELETE FROM candidates WHERE candidate_id LIKE 'custom_bulk_%';")
                conn.execute("DELETE FROM documents WHERE candidate_id LIKE 'custom_bulk_%';")
                conn.execute("DELETE FROM evaluations WHERE candidate_id LIKE 'custom_bulk_%';")
        finally:
            conn.close()

    engine = BulkIngestionEngine()
    zip_bytes = create_sample_zip(include_subfolders=True)


    # 1. First run: processes 2 unique candidates
    batch1 = engine.process_archive(
        zip_bytes=zip_bytes,
        batch_id="test_batch_001",
        target_role="Senior Software Engineer",
        uploads_root=UPLOADS_DIR,
        cases_dir=CASES_DIR,
        pipeline=PIPELINE,
        all_cases_list=ALL_CASES
    )

    assert batch1.total_files == 3
    assert batch1.parsed == 2
    assert batch1.queued == 2
    assert batch1.duplicates == 0
    assert len(batch1.candidates) == 2

    # 2. Second run with same resumes: should deduplicate both candidates
    batch2 = engine.process_archive(
        zip_bytes=zip_bytes,
        batch_id="test_batch_002",
        target_role="Senior Software Engineer",
        uploads_root=UPLOADS_DIR,
        cases_dir=CASES_DIR,
        pipeline=PIPELINE,
        all_cases_list=ALL_CASES
    )

    assert batch2.total_files == 3
    assert batch2.parsed == 2
    assert batch2.queued == 0
    assert batch2.duplicates == 2

    # Cleanup created cases
    for cand in batch1.candidates:
        cid = cand.get("candidate_id")
        if cid:
            ALL_CASES[:] = [c for c in ALL_CASES if c.get("candidate_id") != cid]
            case_file = os.path.join(CASES_DIR, f"{cid}.json")
            traj_file = os.path.join(CACHE_DIR, f"{cid}_trajectory.json")
            cand_folder = os.path.join(UPLOADS_DIR, cid)
            for p in (case_file, traj_file):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            if os.path.exists(cand_folder):
                try:
                    shutil.rmtree(cand_folder)
                except Exception:
                    pass


def test_bulk_api_endpoint(server_url):
    zip_bytes = create_sample_zip(include_subfolders=False)
    files = {
        "archive_file": ("flat_resumes.zip", zip_bytes, "application/zip")
    }
    data = {
        "target_role": "Platform Engineer"
    }

    # Post to /api/candidates/bulk
    res = requests.post(f"{server_url}/api/candidates/bulk", data=data, files=files, timeout=15)
    assert res.status_code == 202, f"Expected 202, got {res.status_code}: {res.text}"
    resp_json = res.json()

    assert resp_json.get("success") is True
    batch_id = resp_json.get("batch_id")
    assert batch_id and "batch_" in batch_id
    assert resp_json.get("total_files") == 2
    assert resp_json.get("parsed") == 2

    # Poll /api/batch/<id>/status
    poll_res = requests.get(f"{server_url}/api/batch/{batch_id}/status")
    assert poll_res.status_code == 200
    batch_status = poll_res.json()
    assert batch_status["batch_id"] == batch_id
    assert batch_status["total_files"] == 2
    assert "progress_pct" in batch_status

    # Wait for batch evaluation to finish or progress
    max_wait = 40
    start_t = time.time()
    while time.time() - start_t < max_wait:
        poll = requests.get(f"{server_url}/api/batch/{batch_id}/status").json()
        if poll.get("evaluated", 0) >= 2 or poll.get("status") == "completed":
            break
        time.sleep(0.5)

    # Cleanup artifacts
    for cand in batch_status.get("candidates", []):
        cid = cand.get("candidate_id")
        if cid:
            ALL_CASES[:] = [c for c in ALL_CASES if c.get("candidate_id") != cid]
            case_file = os.path.join(CASES_DIR, f"{cid}.json")
            traj_file = os.path.join(CACHE_DIR, f"{cid}_trajectory.json")
            cand_folder = os.path.join(UPLOADS_DIR, cid)
            for p in (case_file, traj_file):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            if os.path.exists(cand_folder):
                try:
                    shutil.rmtree(cand_folder)
                except Exception:
                    pass

    with DB._lock:
        conn = DB._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM dedup_hashes WHERE candidate_id LIKE 'custom_bulk_%';")
                conn.execute("DELETE FROM candidates WHERE candidate_id LIKE 'custom_bulk_%';")
                conn.execute("DELETE FROM documents WHERE candidate_id LIKE 'custom_bulk_%';")
                conn.execute("DELETE FROM evaluations WHERE candidate_id LIKE 'custom_bulk_%';")
        finally:
            conn.close()


