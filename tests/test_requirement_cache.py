"""
Test suite for Requirement Mapping Agent SHA-256 Caching.

Asserts that:
1. Identical (target_role, jd_text) inputs hit the cache on repeated calls.
2. In-memory and persistent DB cache eliminate redundant LLM / parser invocations.
3. Varying target_role or JD content properly generates distinct cache keys.
"""

import time
import uuid
import pytest
from agents.requirement_mapping_agent import RequirementMappingAgent
from eval_cases.dataset import SHARED_JD


def test_requirement_mapping_cache_hits():
    agent = RequirementMappingAgent()
    unique_token = uuid.uuid4().hex[:8]
    role = f"Principal Systems Architect {unique_token}"
    jd = f"{SHARED_JD}\nReference: {unique_token}"

    # 1. Initial call (Miss)
    res1 = agent.map_requirements(jd_text=jd, target_role=role)
    assert len(res1) >= 4
    stats1 = agent.get_cache_stats()
    assert stats1["misses"] == 1
    assert stats1["hits"] == 0

    # 2. Second call with identical JD and role (In-memory Hit)
    res2 = agent.map_requirements(jd_text=jd, target_role=role)
    assert len(res2) == len(res1)
    assert [r.req_id for r in res2] == [r.req_id for r in res1]
    stats2 = agent.get_cache_stats()
    assert stats2["hits"] == 1
    assert stats2["misses"] == 1

    # 3. Third call with identical JD but leading/trailing whitespace (Hit)
    res3 = agent.map_requirements(jd_text=f"  {jd} \n", target_role=f" {role} ")
    assert len(res3) == len(res1)
    stats3 = agent.get_cache_stats()
    assert stats3["hits"] == 2

    # 4. Fourth call with fresh agent instance (Persistent DB cache hit)
    fresh_agent = RequirementMappingAgent()
    assert len(fresh_agent._memory_cache) == 0
    res4 = fresh_agent.map_requirements(jd_text=jd, target_role=role)
    assert len(res4) == len(res1)
    stats4 = fresh_agent.get_cache_stats()
    assert stats4["hits"] == 1  # Loaded from DB cache
    assert stats4["misses"] == 0


def test_requirement_mapping_cache_different_roles():
    agent = RequirementMappingAgent()
    token = uuid.uuid4().hex[:8]
    jd = f"Seeking a high performance database architect. Ref: {token}"

    res_a = agent.map_requirements(jd, target_role=f"Database Architect {token}")
    res_b = agent.map_requirements(jd, target_role=f"Frontend Engineer {token}")

    key_a = agent.compute_cache_key(jd, f"Database Architect {token}")
    key_b = agent.compute_cache_key(jd, f"Frontend Engineer {token}")

    assert key_a != key_b
    assert agent.get_cache_stats()["misses"] == 2

