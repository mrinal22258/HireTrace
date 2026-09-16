"""
Tests for Phase 9: Curated Role Taxonomy & Graceful JD Generation Fallback.
"""

import pytest
from agents.jd_templates import (
    RoleTaxonomy,
    classify_role,
    generate_role_tailored_jd,
    TAXONOMY_KEYWORDS,
    ROLE_JD_TEMPLATES
)


def test_classify_role_known_categories():
    """Verify standard engineering roles match their designated taxonomy categories."""
    assert classify_role("Senior Robotics Perception Engineer")[0] == RoleTaxonomy.ROBOTICS_AUTONOMOUS
    assert classify_role("Autonomous Vehicle SLAM Specialist")[0] == RoleTaxonomy.ROBOTICS_AUTONOMOUS
    assert classify_role("Lead Machine Learning Researcher")[0] == RoleTaxonomy.AI_MACHINE_LEARNING
    assert classify_role("Applied AI & RAG Engineer")[0] == RoleTaxonomy.AI_MACHINE_LEARNING
    assert classify_role("Staff Frontend React Developer")[0] == RoleTaxonomy.FRONTEND_FULLSTACK
    assert classify_role("Senior Full Stack Web Developer")[0] == RoleTaxonomy.FRONTEND_FULLSTACK
    assert classify_role("Principal Distributed Systems Architect")[0] == RoleTaxonomy.DISTRIBUTED_SYSTEMS_INFRA
    assert classify_role("Kafka Backend Infrastructure Engineer")[0] == RoleTaxonomy.DISTRIBUTED_SYSTEMS_INFRA
    assert classify_role("Lead Data Engineer & Lakehouse Architect")[0] == RoleTaxonomy.DATA_ENGINEERING
    assert classify_role("Senior DevSecOps & Security Specialist")[0] == RoleTaxonomy.SECURITY_CYBERSECURITY
    assert classify_role("iOS Swift Mobile Engineer")[0] == RoleTaxonomy.MOBILE_ENGINEERING


def test_classify_role_novel_fallback():
    """Verify novel, unknown, or non-technical roles gracefully degrade to GENERAL_SOFTWARE."""
    taxonomy, matched = classify_role("Quantum Computing Cryptanalyst")
    assert taxonomy == RoleTaxonomy.GENERAL_SOFTWARE
    assert matched is False

    taxonomy, matched = classify_role("Bioinformatics Gene Splicing Analyst")
    assert taxonomy == RoleTaxonomy.GENERAL_SOFTWARE
    assert matched is False

    taxonomy, matched = classify_role("VP of Customer Delight")
    assert taxonomy == RoleTaxonomy.GENERAL_SOFTWARE
    assert matched is False

    taxonomy, matched = classify_role("")
    assert taxonomy == RoleTaxonomy.GENERAL_SOFTWARE
    assert matched is False

    taxonomy, matched = classify_role(None)
    assert taxonomy == RoleTaxonomy.GENERAL_SOFTWARE
    assert matched is False


def test_generate_role_tailored_jd_structure():
    """Verify generated JDs retain complete requirement schemas (REQ-01 to REQ-05)."""
    # Known role
    jd = generate_role_tailored_jd("Senior Perception Engineer")
    assert "# Senior Perception Engineer" in jd
    assert "REQ-01" in jd
    assert "REQ-02" in jd
    assert "REQ-03" in jd
    assert "REQ-04" in jd
    assert "REQ-05" in jd
    assert "Robotics" in jd or "Perception" in jd

    # Novel role fallback
    fallback_jd = generate_role_tailored_jd("Chief Astronaut Officer")
    assert "# Chief Astronaut Officer" in fallback_jd
    assert "Enterprise Technology Solutions" in fallback_jd
    assert "REQ-01" in fallback_jd
    assert "REQ-05" in fallback_jd

    # Empty role title
    empty_jd = generate_role_tailored_jd("")
    assert "# Software Engineer" in empty_jd
    assert "Enterprise Technology Solutions" in empty_jd
    assert "REQ-01" in empty_jd
