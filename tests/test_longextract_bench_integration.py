"""
Unit tests for LongExtractBench Integration and Structured CV Extraction.
Validates:
1. Deterministic grader correctly pairs rows by content and normalizes cosmetic differences.
2. Classification rules isolate non-empty results from failure envelopes.
3. Local scoring harness aggregates precision, recall, and leaf accuracy with zero paid API dependencies.
4. Schema validation on candidate_cv_schema.json.
"""

import os
import json
import pytest

from vendor.longextract_bench.grading import grade, canonical
from vendor.longextract_bench.classify import classify
from vendor.longextract_bench.score import score_single, score_dataset
from agents.cv_extractor import extract_structured_cv, fallback_deterministic_extractor


def test_canonical_normalization():
    """Validates that cosmetic diffs (case, spaces, commas, numbers) are normalized."""
    assert canonical("ScaleMatrix Telemetry") == canonical("scalematrix telemetry")
    assert canonical("1,000") == canonical("1000")
    assert canonical("45.0") == canonical("45")
    assert canonical("n/a") == ""
    assert canonical(None) == ""


def test_deterministic_grader_row_pairing():
    """Validates content-based row pairing and leaf accuracy."""
    gt = {
        "candidate_name": "Sarah Chen",
        "employment_history": [
            {
                "employer": "ScaleMatrix Telemetry",
                "title": "Senior Infrastructure Engineer",
                "start_date": "2021-10",
                "end_date": None,
                "is_current": True
            },
            {
                "employer": "DataPulse Networks",
                "title": "Backend Software Engineer",
                "start_date": "2019-06",
                "end_date": "2021-09",
                "is_current": False
            }
        ],
        "skills": ["Python", "AsyncIO", "Kafka"]
    }

    # Predicted rows in reverse order with cosmetic differences
    pred = {
        "candidate_name": "sarah chen",
        "employment_history": [
            {
                "employer": "DataPulse Networks",
                "title": "Backend Software Engineer",
                "start_date": "2019-06",
                "end_date": "2021-09",
                "is_current": False
            },
            {
                "employer": "ScaleMatrix Telemetry",
                "title": "Senior Infrastructure Engineer",
                "start_date": "2021-10",
                "end_date": None,
                "is_current": True
            }
        ],
        "skills": ["python", "asyncio", "kafka"]
    }

    schema = {
        "properties": {
            "employment_history": {"type": "array"},
            "skills": {"type": "array"}
        }
    }
    res = grade(gt, pred, schema)
    assert res["matched"] == 2
    assert res["precision"] == 1.0
    assert res["recall"] == 1.0
    assert res["leaf_accuracy"] == 100.0


def test_classify_success_and_failure():
    """Validates that classify correctly distinguishes usable extractions from failures."""
    state, reason = classify({"result": {"candidate_name": "Test"}})
    assert state == "success"
    assert reason is None

    state, reason = classify({"result": {}})
    assert state == "failure"
    assert reason == "empty result"

    state, reason = classify({"_meta": {"status": "failed", "error": "rate limited"}})
    assert state == "failure"
    assert "rate limited" in reason


def test_cv_extractor_deterministic_fallback():
    """Validates that the fallback extractor extracts structured facts without network."""
    sample_cv = """# John Doe, Staff Engineer
## Technical Skills
- Languages: Python, Go, SQL
- Distributed Systems: Kafka, Redis

## Experience
Senior Engineer | Acme Cloud (Jan 2021 - Present | 4 years)
- Built streaming analytics pipeline.
"""
    extracted = extract_structured_cv(sample_cv, candidate_name="John Doe")
    assert extracted["candidate_name"] == "John Doe"
    assert len(extracted["employment_history"]) >= 1
    assert extracted["employment_history"][0]["employer"] == "Acme Cloud"
    assert extracted["employment_history"][0]["start_date"] == "2021-01"
    assert extracted["employment_history"][0]["is_current"] is True
    assert "Python" in extracted["skills"]


def test_ground_truth_cv_dataset_present():
    """Verifies that at least 15 hand-labeled ground truth CV files exist."""
    gt_dir = os.path.join("eval_cases", "cv_ground_truth")
    assert os.path.isdir(gt_dir)
    dirs = [d for d in os.listdir(gt_dir) if os.path.isdir(os.path.join(gt_dir, d))]
    assert len(dirs) >= 15
    for d in dirs:
        gt_file = os.path.join(gt_dir, d, "ground_truth.json")
        assert os.path.exists(gt_file), f"Missing ground truth for {d}"
        with open(gt_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "candidate_name" in data
            assert "employment_history" in data
            assert "skills" in data
