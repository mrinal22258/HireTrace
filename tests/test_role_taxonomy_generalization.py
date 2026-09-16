"""
Tests for Phase 7: Role Coverage & Taxonomy Generalization.

Validates:
1. New taxonomy buckets (Forward Deployed Engineer, DevRel, EM, QA/SDET, Firmware/Hardware).
2. Honest fallback and LLM-generated bespoke JD path for novel roles.
3. Degraded marking on _default_requirements.
4. End-to-end custom JD upload via /api/candidate/upload.
"""

import os
import pytest
from fastapi.testclient import TestClient

from agents.jd_templates import (
    RoleTaxonomy,
    classify_role,
    generate_role_tailored_jd,
    generate_role_tailored_jd_with_meta,
    ROLE_JD_TEMPLATES
)
from agents.requirement_mapping_agent import RequirementMappingAgent, JobRequirement
from agents.mock_ollama_client import MockOllamaClient
from ui.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_classify_role_new_taxonomy_buckets():
    """Confirms all 5 new taxonomy buckets match correctly from role title keywords."""
    fde_tax, matched = classify_role("Senior Forward Deployed Engineer")
    assert matched is True
    assert fde_tax == RoleTaxonomy.FORWARD_DEPLOYED_ENGINEER

    se_tax, matched = classify_role("Customer Solutions Engineer")
    assert matched is True
    assert se_tax == RoleTaxonomy.FORWARD_DEPLOYED_ENGINEER

    devrel_tax, matched = classify_role("Developer Relations Advocate")
    assert matched is True
    assert devrel_tax == RoleTaxonomy.DEVELOPER_RELATIONS

    em_tax, matched = classify_role("Director of Engineering")
    assert matched is True
    assert em_tax == RoleTaxonomy.ENGINEERING_MANAGEMENT

    qa_tax, matched = classify_role("Staff SDET & Test Automation Architect")
    assert matched is True
    assert qa_tax == RoleTaxonomy.QA_TEST_ENGINEERING

    hw_tax, matched = classify_role("Senior Firmware & Embedded RTOS Engineer")
    assert matched is True
    assert hw_tax == RoleTaxonomy.HARDWARE_FIRMWARE_EMBEDDED


def test_novel_role_llm_generated_jd_fallback():
    """Verifies that an unrecognized novel role uses bespoke LLM generation when available."""
    mock_llm = MockOllamaClient()
    role_title = "Chief Spacecraft Orbital Trajectory Optimizer"

    # Novel role does not match standard keywords
    tax, matched = classify_role(role_title)
    assert matched is False
    assert tax == RoleTaxonomy.GENERAL_SOFTWARE

    # Generation engages LLM
    jd, taxonomy, is_match, source = generate_role_tailored_jd_with_meta(role_title, client=mock_llm)
    assert is_match is False
    assert source == "llm_generated"
    assert role_title in jd
    assert "REQ-01" in jd


def test_default_requirements_degraded_marker():
    """Confirms that _default_requirements() marks items with degraded: True and offline source note."""
    agent = RequirementMappingAgent()
    reqs = agent._default_requirements("Senior Quantum Cryptographer")
    assert len(reqs) >= 4
    for r in reqs:
        assert r.degraded is True
        assert r.source_note == "generic requirements — offline mode"
        d = r.to_dict()
        assert d.get("degraded") is True
        assert d.get("source_note") == "generic requirements — offline mode"


def test_end_to_end_custom_jd_upload(client):
    """Submits candidate with custom pasted JD text and verifies it is preserved and evaluated."""
    custom_jd = (
        "# Custom High-Altitude Balloon Pilot\n"
        "### Core Requirements\n"
        "- REQ-01: Atmospheric Science: Stratospheric wind pattern navigation.\n"
        "- REQ-02: Avionics Telemetry: Real-time satellite radio communication.\n"
    )

    cv_content = (
        "# Captain Jane Foster\n"
        "10 years experience piloting stratospheric balloons and operating avionics telemetry.\n"
    )

    res = client.post(
        "/api/candidate/upload?sync=true",
        data={
            "name": "Jane Foster",
            "target_role": "High-Altitude Balloon Pilot",
            "cv_text": cv_content,
            "jd_text": custom_jd,
        }
    )
    assert res.status_code == 200, res.text
    data = res.json()
    report = data.get("report") or {}
    assert report.get("custom_jd_provided") is True
    assert report.get("taxonomy_matched") is True
    assert report.get("role_match_note") is None


def test_unmatched_role_report_honesty(client):
    """Submits candidate with novel role and NO JD text; verifies honest taxonomy notice is emitted."""
    cv_content = (
        "# Alex Quantum\n"
        "Specialist in abstract theoretical topological manifold analysis.\n"
    )

    res = client.post(
        "/api/candidate/upload?sync=true",
        data={
            "name": "Alex Quantum",
            "target_role": "Quantum Topologist",
            "cv_text": cv_content,
        }
    )
    assert res.status_code == 200, res.text
    data = res.json()
    report = data.get("report") or {}
    assert report.get("custom_jd_provided") is False
    assert report.get("taxonomy_matched") is False
    assert "No specialized rubric matched" in (report.get("role_match_note") or "")
