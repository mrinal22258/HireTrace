"""
Unit tests for HireTrace deterministic rubric scorer (Baseline A).
"""
import pytest
from baseline.rubric_scorer import (
    RubricScorer,
    CandidateCVProfile,
    OPEN_SOURCE_MAX,
    SELF_PROJECTS_MAX,
    PRODUCTION_MAX,
    TECHNICAL_SKILLS_MAX,
    BONUS_POINTS_MAX,
    TOTAL_RAW_MAX
)


def test_empty_profile_scores_zero():
    """An empty profile should result in a score of 0."""
    profile = CandidateCVProfile(candidate_id="zero_01")
    result = RubricScorer.evaluate(profile)
    assert result.raw_total == 0.0
    assert result.normalized_score == 0.0
    assert result.category_scores["open_source"] == 0.0
    assert result.category_scores["self_projects"] == 0.0
    assert result.category_scores["production"] == 0.0
    assert result.category_scores["technical_skills"] == 0.0
    assert result.category_scores["bonus_points"] == 0.0


def test_maximum_possible_score():
    """A profile maxing out every single category should hit 120 raw and 100 normalized."""
    profile = CandidateCVProfile(
        candidate_id="max_01",
        name="Super Developer",
        has_public_repo=True,
        open_source_prs_count=10,  # capped
        maintained_repos_count=5,   # capped
        total_repo_stars=100,       # capped
        has_system_project=True,
        has_production_architecture=True,
        has_live_demo=True,
        has_test_coverage=True,
        years_production_experience=6.0,
        has_high_scale_experience=True,
        primary_language_match=True,
        database_systems_match=True,
        distributed_cloud_match=True,
        has_tech_writing_or_talks=True,
        has_mentorship_or_leadership=True,
        has_competitive_or_academic=True,
        has_security_or_certifications=True,
    )
    result = RubricScorer.evaluate(profile)
    assert result.raw_total == TOTAL_RAW_MAX  # 120.0
    assert result.normalized_score == 100.0
    assert result.open_source.score == OPEN_SOURCE_MAX  # 35.0
    assert result.self_projects.score == SELF_PROJECTS_MAX  # 30.0
    assert result.production.score == PRODUCTION_MAX  # 25.0
    assert result.technical_skills.score == TECHNICAL_SKILLS_MAX  # 10.0
    assert result.bonus_points.score == BONUS_POINTS_MAX  # 20.0


def test_category_caps_enforced():
    """Even if inputs vastly exceed thresholds, category caps must never be breached."""
    profile = CandidateCVProfile(
        candidate_id="overcap_01",
        has_public_repo=True,
        open_source_prs_count=1000,
        maintained_repos_count=50,
        total_repo_stars=50000,
    )
    res = RubricScorer.score_open_source(profile)
    assert res.score == OPEN_SOURCE_MAX
    assert res.score <= 35.0


def test_realistic_mid_senior_profile():
    """
    Test a realistic profile scored around ~62/120 (normalized ~51.7%),
    matching the calibration reference in the prompt.
    """
    profile = CandidateCVProfile(
        candidate_id="real_01",
        name="Alex Engineer",
        has_public_repo=True,           # +5
        open_source_prs_count=3,        # +6 (total OS = 11)
        maintained_repos_count=0,
        total_repo_stars=12,            # +5 (total OS = 16)
        has_system_project=True,        # +10
        has_production_architecture=True,# +10
        has_live_demo=False,
        has_test_coverage=True,         # +5 (total SP = 25)
        years_production_experience=3.5,# +16 (production = 16)
        has_high_scale_experience=False,
        primary_language_match=True,    # +4
        database_systems_match=True,    # +3
        distributed_cloud_match=False,  # (total Tech = 7)
        has_tech_writing_or_talks=True, # +5 (total Bonus = 5)
    )
    # Expected raw: 16 (OS) + 25 (SP) + 16 (Prod) + 7 (Tech) + 5 (Bonus) = 69
    result = RubricScorer.evaluate(profile)
    assert 60 <= result.raw_total <= 75
    assert 50.0 <= result.normalized_score <= 65.0
    assert len(result.summary_audit) > 0


def test_evaluate_from_dict_and_serialization():
    """Ensure dictionary ingestion and serialization to dictionary work seamlessly."""
    raw_data = {
        "candidate_id": "dict_candidate",
        "name": "Dev From Dict",
        "has_public_repo": True,
        "open_source_prs_count": 2,
        "years_production_experience": 2.0,
        "primary_language_match": True,
    }
    result = RubricScorer.evaluate_from_dict(raw_data)
    assert result.candidate_id == "dict_candidate"
    assert result.raw_total > 0
    
    serialized = result.to_dict()
    assert serialized["candidate_id"] == "dict_candidate"
    assert "normalized_score" in serialized
    assert "details" in serialized
    assert serialized["details"]["open_source"]["score"] > 0
