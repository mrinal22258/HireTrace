"""
Pytest Unit Tests for HireTrace Fairness Audit & Demographic Invariance.
Validates:
1. Counterfactual demographic perturbations produce < 1.0 point variance (perfect parity).
2. EEOC Four-Fifths Rule compliance (DIR >= 0.80).
3. Quadrant stability across all demographic slices.
"""

import pytest
from eval.fairness_audit import run_fairness_audit


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
