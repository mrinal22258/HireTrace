import json
import pytest
from fastapi.testclient import TestClient
from ui.server import app

client = TestClient(app)


def test_api_system_mode():
    """Verify /api/system/mode returns current execution mode and offline guarantees."""
    res = client.get("/api/system/mode")
    assert res.status_code == 200
    data = res.json()
    assert "mode" in data
    assert data["mode"] in ["live", "demo"]
    assert "llm_available" in data
    assert isinstance(data["llm_available"], bool)
    assert data["offline_default"] is True
    assert "api_cost" in data
    assert data["api_cost"] == "$0.00"


def test_api_cases_has_unsupported_and_contradicted_counts():
    """Verify /api/cases summaries include unsupported_claim_count and contradicted_claim_count."""
    res = client.get("/api/cases?include_demo=true")
    assert res.status_code == 200
    cases = res.json()
    assert len(cases) > 0

    for c in cases:
        assert "unsupported_claim_count" in c, f"Candidate {c.get('candidate_id')} missing unsupported_claim_count"
        assert "contradicted_claim_count" in c, f"Candidate {c.get('candidate_id')} missing contradicted_claim_count"
        assert isinstance(c["unsupported_claim_count"], int)
        assert isinstance(c["contradicted_claim_count"], int)


def test_api_leaderboard_sorting_and_filtering():
    """Verify /api/leaderboard supports role filtering and sort keys (fit, consistency, unsupported, name)."""
    # 1. Default sort by fit
    res_fit = client.get("/api/leaderboard?sort_by=fit&include_demo=true")
    assert res_fit.status_code == 200
    items_fit = res_fit.json()
    assert len(items_fit) > 0

    fit_scores = [i.get("role_fit_score") for i in items_fit if i.get("role_fit_score") is not None]
    assert fit_scores == sorted(fit_scores, reverse=True)

    # 2. Sort by consistency
    res_cons = client.get("/api/leaderboard?sort_by=consistency&include_demo=true")
    assert res_cons.status_code == 200
    items_cons = res_cons.json()
    cons_scores = [i.get("evidence_consistency_score") for i in items_cons if i.get("evidence_consistency_score") is not None]
    assert cons_scores == sorted(cons_scores, reverse=True)

    # 3. Sort by unsupported claims
    res_uns = client.get("/api/leaderboard?sort_by=unsupported&include_demo=true")
    assert res_uns.status_code == 200
    items_uns = res_uns.json()
    uns_counts = [i.get("unsupported_claim_count", 0) for i in items_uns]
    assert uns_counts == sorted(uns_counts)

    # 4. Sort by name
    res_name = client.get("/api/leaderboard?sort_by=name")
    assert res_name.status_code == 200
    items_name = res_name.json()
    names = [i.get("name", "") for i in items_name]
    assert names == sorted(names)

    # 5. Role filtering
    sample_role = items_fit[0].get("target_role")
    if sample_role:
        res_filtered = client.get("/api/leaderboard", params={"role": sample_role})
        assert res_filtered.status_code == 200
        items_filtered = res_filtered.json()
        assert len(items_filtered) > 0
        for item in items_filtered:
            assert sample_role.lower() in item.get("target_role", "").lower() or item.get("target_role", "").lower() in sample_role.lower()


def test_api_pipeline_stream_sse():
    """Verify /api/pipeline/stream/{candidate_id} yields text/event-stream with per-agent steps."""
    res = client.get("/api/pipeline/stream/case_01_strong_01")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = []
    for line in res.iter_lines():
        if line and line.startswith("data: "):
            payload = json.loads(line[6:])
            events.append(payload)

    assert len(events) >= 3, "Expected at least 3 SSE pipeline progress events"

    agent_names = [e.get("agent") for e in events]
    assert "RequirementMappingAgent" in agent_names
    assert "EvidenceAggregationAgent" in agent_names
    assert "RecommendationWriterAgent" in agent_names or "PipelineEngine" in agent_names

    # Final event should reach 100% or completed
    last_event = events[-1]
    assert last_event.get("progress_pct") == 100
    assert last_event.get("status") in ("completed", "done")
