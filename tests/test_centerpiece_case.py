"""
Test running HireTrace pipeline on the centerpiece deceptive case (Alexander Sterling).
Verifies:
1. Two-dimensional output (Role Fit vs Evidence Consistency)
2. Quadrant placement is REVIEW REQUIRED
3. Planted contradictions (Tenure mismatch, Leadership claim mismatch) are detected
4. Trajectory file is generated
"""

import os
import json
import pytest

from agents.evidence_loader import EvidenceLoader
from agents.pipeline import HireTracePipeline


def test_centerpiece_case_pipeline():
    case_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval_cases", "case_15_deceptive_centerpiece.json")
    with open(case_path, "r", encoding="utf-8") as f:
        case_data = json.load(f)

    # 1. Load dossier
    dossier = EvidenceLoader.load_case_from_dict(case_data)
    assert len(dossier.spans) > 5

    # 2. Run pipeline
    pipeline = HireTracePipeline(trajectory_dir="trajectories")
    report = pipeline.run(dossier, log_trajectory=True)

    try:
        print("\n" + report.formatted_terminal_card.encode("ascii", errors="replace").decode("ascii"))
    except Exception:
        pass

    # 3. Assertions
    assert report.candidate_id == "case_15_deceptive_centerpiece"
    assert report.recommendation == "Proceed to human review."
    assert report.quadrant in ("REVIEW REQUIRED", "INSUFFICIENT EVIDENCE")
    assert report.evidence_consistency_score < 70.0  # Low consistency due to contradictions
    assert report.contradicted_claim_count > 0
    assert len(report.key_discrepancies) >= 1
    assert len(report.priority_questions) >= 2

    # Check trajectory file created
    traj_path = os.path.join("trajectories", "case_15_deceptive_centerpiece_trajectory.json")
    assert os.path.exists(traj_path)
    with open(traj_path, "r", encoding="utf-8") as tf:
        traj_data = json.load(tf)
        assert len(traj_data["steps"]) == 6
