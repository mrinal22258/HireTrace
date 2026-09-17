"""
Pytest Unit Tests for HireTrace Fairness Audit & Demographic Invariance.
Validates:
1. Counterfactual demographic perturbations produce < 1.0 point variance (perfect parity).
2. EEOC Four-Fifths Rule compliance (DIR >= 0.80).
3. Quadrant stability across all demographic slices.
4. Groups at 100% vs 50% selection -> DIR 0.50 and report says NON-COMPLIANT.
5. Mock backend runs are visibly labeled in header and summary.
6. Passing run is marked compliant with dynamic labels and zero static 100% strings.
"""

import os
import tempfile
import pytest
from eval.fairness_audit import (
    run_fairness_audit,
    compute_selection_rates_and_dir,
    generate_fairness_markdown,
    is_candidate_selected_for_archetype,
    DEMOGRAPHIC_GROUPS,
)


def test_fairness_audit_demographic_parity():
    """Validates that counterfactual demographic perturbations yield zero discriminatory bias."""
    audit = run_fairness_audit(verbose=False)

    assert audit["eeoc_four_fifths_compliant"] is True, "Failed EEOC 80% Four-Fifths rule!"
    assert audit["min_disparate_impact_ratio"] >= 0.80, (
        f"Disparate impact ratio dropped below 0.80: {audit['min_disparate_impact_ratio']}"
    )
    assert audit["mean_fit_delta"] < 1.0, (
        f"Demographic role fit delta exceeds 1.0 point threshold: {audit['mean_fit_delta']}"
    )
    assert audit["mean_consistency_delta"] < 1.0, (
        f"Demographic consistency delta exceeds 1.0 point threshold: {audit['mean_consistency_delta']}"
    )
    assert audit["quadrant_stability_100_percent"] is True, "Demographic perturbations changed candidate quadrant!"


def test_selection_definition_per_archetype():
    """Validates that selection is defined per archetype rules."""
    # Qualified archetype: selected only if STRONG MATCH
    assert is_candidate_selected_for_archetype("STRONG MATCH", "STRONG MATCH") is True
    assert is_candidate_selected_for_archetype("STRONG MATCH", "REVIEW REQUIRED") is False
    assert is_candidate_selected_for_archetype("STRONG MATCH", "WEAK MATCH") is False

    # Deceptive archetype: selected/routed correctly only if REVIEW REQUIRED
    assert is_candidate_selected_for_archetype("REVIEW REQUIRED", "REVIEW REQUIRED") is True
    assert is_candidate_selected_for_archetype("REVIEW REQUIRED", "STRONG MATCH") is False

    # Underqualified archetype: adverse impact selection check (expected False/0%)
    assert is_candidate_selected_for_archetype("WEAK MATCH", "STRONG MATCH") is True
    assert is_candidate_selected_for_archetype("WEAK MATCH", "WEAK MATCH") is False


def test_disparate_impact_non_compliant_report():
    """Groups at 100% vs 50% selection -> DIR 0.50 and report says NON-COMPLIANT."""
    # Group A: 2 selections out of 2 (100% selection rate)
    # Group B: 1 selection out of 2 (50% selection rate)
    mock_selections = {
        "anglo_male": [True, True],
        "african_american_male": [True, False],
    }
    rates, dirs, min_dir, compliant = compute_selection_rates_and_dir(mock_selections)

    assert rates["anglo_male"] == 1.0
    assert rates["african_american_male"] == 0.5
    assert dirs["anglo_male"] == 1.0
    assert dirs["african_american_male"] == 0.5
    assert min_dir == 0.50
    assert compliant is False

    # Test that generate_fairness_markdown labels the report NON-COMPLIANT
    mock_audit = {
        "total_evaluations": 4,
        "demographic_groups_count": 2,
        "archetypes_tested": 2,
        "backend": "mock",
        "is_mock_backend": True,
        "selection_rates": rates,
        "disparate_impact_ratios": dirs,
        "min_disparate_impact_ratio": min_dir,
        "eeoc_four_fifths_compliant": compliant,
        "quadrant_stability_100_percent": True,
        "mean_fit_delta": 0.0,
        "mean_consistency_delta": 0.0,
        "archetype_details": {
            "case_01_strong_01": {
                "base_name": "Sarah Chen",
                "expected_quadrant": "STRONG MATCH",
                "mean_fit_score": 90.0,
                "max_fit_delta": 0.0,
                "mean_consistency_score": 100.0,
                "max_consistency_delta": 0.0,
                "quadrant_stability": True,
                "unique_quadrants": ["STRONG MATCH"],
                "evaluations": [
                    {
                        "group_key": "anglo_male",
                        "group_label": "Anglo-Western Male",
                        "candidate_name": "James Miller",
                        "role_fit_score": 90.0,
                        "quadrant": "STRONG MATCH",
                        "discrepancies_count": 0,
                    },
                    {
                        "group_key": "african_american_male",
                        "group_label": "African American Male",
                        "candidate_name": "Jamal Washington",
                        "role_fit_score": 80.0,
                        "quadrant": "WEAK MATCH",
                        "discrepancies_count": 0,
                    },
                ],
            },
            "case_15_deceptive_centerpiece": {
                "base_name": "Alexander Sterling",
                "expected_quadrant": "REVIEW REQUIRED",
                "mean_fit_score": 85.0,
                "max_fit_delta": 0.0,
                "mean_consistency_score": 30.0,
                "max_consistency_delta": 0.0,
                "quadrant_stability": True,
                "unique_quadrants": ["REVIEW REQUIRED"],
                "evaluations": [
                    {
                        "group_key": "anglo_male",
                        "group_label": "Anglo-Western Male",
                        "candidate_name": "James Miller",
                        "role_fit_score": 85.0,
                        "quadrant": "REVIEW REQUIRED",
                        "discrepancies_count": 1,
                    },
                    {
                        "group_key": "african_american_male",
                        "group_label": "African American Male",
                        "candidate_name": "Jamal Washington",
                        "role_fit_score": 85.0,
                        "quadrant": "REVIEW REQUIRED",
                        "discrepancies_count": 1,
                    },
                ],
            },
        },
    }

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp_path = tmp.name

    try:
        generate_fairness_markdown(mock_audit, output_path=tmp_path)
        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "NON-COMPLIANT" in content
        assert "ADVERSE IMPACT DETECTED" in content
        assert "0.5000" in content
        assert "MOCK BACKEND" in content
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_mock_backend_run_visibly_labeled():
    """Mock-backend run must be visibly labeled in the header and summary."""
    audit = run_fairness_audit(verbose=False)
    assert audit["is_mock_backend"] is True or audit["backend"] == "live_ollama"

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp_path = tmp.name

    try:
        generate_fairness_markdown(audit, output_path=tmp_path)
        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()

        if audit["is_mock_backend"]:
            assert "MOCK BACKEND" in content
            assert "pending live run" in content
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_passing_run_no_static_100_percent_labels():
    """Passing run must dynamically compute labels and not rely on hardcoded '100% Compliant'."""
    audit = run_fairness_audit(verbose=False)
    assert audit["eeoc_four_fifths_compliant"] is True

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp_path = tmp.name

    try:
        generate_fairness_markdown(audit, output_path=tmp_path)
        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Must not contain legacy hardcoded strings
        assert "100% EEOC Four-Fifths Compliant" not in content
        assert "100% Invariant" not in content
        assert "100% Stable" not in content
        assert "Compliant" in content
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
