import pytest
import requests
import json
import time
import threading
import socket
from ui.server import ReusableHTTPServer, HireTraceHandler


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_url():
    # First check if default port 8080 is active
    try:
        r = requests.get("http://127.0.0.1:8080/api/cases", timeout=1.0)
        if r.status_code == 200:
            return "http://127.0.0.1:8080"
    except Exception:
        pass

    # Start ephemeral background server
    port = get_free_port()
    server = ReusableHTTPServer(("127.0.0.1", port), HireTraceHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    return f"http://127.0.0.1:{port}"


def test_api_cases_list(server_url):
    res = requests.get(f"{server_url}/api/cases")
    assert res.status_code == 200
    cases = res.json()
    assert len(cases) >= 15
    assert any(c["candidate_id"] == "case_15_deceptive_centerpiece" for c in cases)


def test_dynamic_candidate_intake(server_url):
    payload = {
        "name": "Dr. Maya Lin",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "cv_text": "# Dr. Maya Lin\nEmail: maya.lin@tech.internal\nSenior Distributed Systems Researcher with 6 years experience in Python, AsyncIO, and Kafka message brokers. Developed open source Raft consensus library with 180 stars.",
        "interview_notes": "Maya discussed her experience implementing Kafka consumers and asyncio worker pools.",
        "technical_assessment": "Scored 85/100 on asynchronous broker implementation challenge.",
        "project_rfc": "Authored RFC for multi-region event replication."
    }

    res = requests.post(f"{server_url}/api/candidate/new", json=payload, timeout=300)
    assert res.status_code == 200
    data = res.json()
    assert data.get("success") is True
    candidate_id = data.get("candidate_id", "")
    assert "custom_dr__maya_lin" in candidate_id
    assert "report" in data
    assert "baseline_a" in data
    
    try:
        # Check that candidate now appears in /api/cases
        list_res = requests.get(f"{server_url}/api/cases")
        all_cases = list_res.json()
        assert any(c["candidate_id"] == candidate_id for c in all_cases)
    finally:
        # Clean up ephemeral test artifact so eval_cases remains pristine
        import os
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        case_file = os.path.join(root_dir, "eval_cases", f"{candidate_id}.json")
        traj_file = os.path.join(root_dir, "trajectories", f"{candidate_id}_trajectory.json")
        if os.path.exists(case_file):
            try:
                os.remove(case_file)
            except Exception:
                pass
        if os.path.exists(traj_file):
            try:
                os.remove(traj_file)
            except Exception:
                pass

