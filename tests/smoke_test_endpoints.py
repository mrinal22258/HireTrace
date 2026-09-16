"""
End-to-end smoke test suite for HireTrace API endpoints.
Validates all public routes against mock LLM backend.
Used as behavior snapshot across server refactorings.
"""

import os
import sys
import json
import socket
import threading
import time
import pytest
import requests

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from ui.server import ReusableHTTPServer, HireTraceHandler


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def smoke_server():
    port = get_free_port()
    server = ReusableHTTPServer(("127.0.0.1", port), HireTraceHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    base_url = f"http://127.0.0.1:{port}"
    yield base_url


def test_smoke_static_pages(smoke_server):
    # 1. Main UI
    r = requests.get(f"{smoke_server}/")
    assert r.status_code == 200
    assert "HireTrace" in r.text

    # 2. Static data bundle
    r = requests.get(f"{smoke_server}/static_data.js")
    assert r.status_code == 200
    assert len(r.text) > 100


def test_smoke_cases_endpoints(smoke_server):
    # 1. All cases summary
    r = requests.get(f"{smoke_server}/api/cases?include_demo=true")
    assert r.status_code == 200
    cases = r.json()
    assert isinstance(cases, list)
    assert len(cases) > 0

    # 2. Paginated cases
    r = requests.get(f"{smoke_server}/api/cases?page=1&limit=5&include_demo=true")
    assert r.status_code == 200
    paged = r.json()
    assert "items" in paged
    assert "total" in paged
    assert paged["total"] >= len(paged["items"])

    # 3. Full case details
    cid = cases[0]["candidate_id"]
    r = requests.get(f"{smoke_server}/api/case/{cid}/full")
    assert r.status_code == 200
    full_data = r.json()
    assert full_data["candidate_id"] == cid
    assert "documents" in full_data


def test_smoke_candidate_intake_and_eval(smoke_server):
    # 1. Create candidate via JSON
    payload = {
        "name": "Smoke Test Candidate",
        "target_role": "Distributed Systems Engineer",
        "cv_text": "Experienced engineer with 5 years in Python and Kafka.",
        "interview_notes": "Demonstrated deep knowledge of consensus protocols.",
        "technical_assessment": "90/100 score in distributed systems challenge."
    }
    r = requests.post(f"{smoke_server}/api/candidate/new", json=payload)
    assert r.status_code == 200
    res = r.json()
    assert res.get("success") is True
    cid = res.get("candidate_id")
    assert cid is not None

    # 2. Poll status
    r = requests.get(f"{smoke_server}/api/candidate/{cid}/status")
    assert r.status_code == 200
    status_data = r.json()
    assert "status" in status_data

    # 3. Trigger evaluation
    r = requests.post(f"{smoke_server}/api/evaluate/{cid}")
    assert r.status_code == 200
    eval_res = r.json()
    assert "report" in eval_res or "job_id" in eval_res or eval_res.get("success") is True


def test_smoke_eval_summary(smoke_server):
    # Summary
    r = requests.get(f"{smoke_server}/api/eval_summary")
    assert r.status_code == 200
    summary = r.json()
    assert "metrics" in summary
    assert "metadata" in summary
