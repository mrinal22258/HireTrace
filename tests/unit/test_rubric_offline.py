"""
Unit tests for Industry Standard ATS Deterministic Scorer and CV profile extraction.
100% offline, zero network requests, verifying date merging and negation handling.
"""

import pytest
from agents.evidence_loader import EvidenceLoader
from baseline.rubric_scorer import RubricScorer, CandidateCVProfile


def test_negation_awareness_in_skill_extraction():
    cv_with_negation = """# Candidate CV
Skills: Python, FastAPI.
Note: Candidate has NO experience with Kafka or distributed streaming.
Lacks exposure to Docker and Kubernetes.
"""
    profile = EvidenceLoader.extract_structured_cv_profile(cv_with_negation, candidate_id="test_neg")
    assert profile["primary_language_match"] is True
    # Kafka is explicitly negated, so distributed_cloud_match should be False
    assert profile["distributed_cloud_match"] is False


def test_date_interval_merging_prevents_double_counting():
    cv_overlapping_jobs = """# Candidate CV
Experience:
- Senior Engineer at Alpha Corp (2021 - 2024)
- Contract Advisor at Beta Inc (2022 - 2024)
"""
    # 2021-2024 is 3 years total, not 3 + 2 = 5 years
    profile = EvidenceLoader.extract_structured_cv_profile(cv_overlapping_jobs, candidate_id="test_dates")
    assert profile["years_production_experience"] == 3.0


def test_ats_rubric_scorer_caps_and_normalization():
    profile = CandidateCVProfile(
        candidate_id="test_top",
        has_public_repo=True,
        open_source_prs_count=50,
        maintained_repos_count=10,
        total_repo_stars=500,
        has_system_project=True,
        has_production_architecture=True,
        has_live_demo=True,
        has_test_coverage=True,
        years_production_experience=8.0,
        has_high_scale_experience=True,
        primary_language_match=True,
        database_systems_match=True,
        distributed_cloud_match=True,
        has_tech_writing_or_talks=True,
        has_mentorship_or_leadership=True
    )
    result = RubricScorer.evaluate_from_profile(profile)
    assert result.raw_total <= 120.0
    assert result.normalized_score <= 100.0
    assert result.normalized_score >= 80.0
