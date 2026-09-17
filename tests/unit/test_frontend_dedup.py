"""
Unit tests for frontend candidate deduplication and identity disambiguation.
Verifies:
1. deduplicateCandidates(list):
   - Same name + different candidate IDs -> both kept.
   - Same candidate ID -> kept once.
   - Unique IDs -> output count == input count.
   - Null / array / missing ID guards.
2. Candidate subtitle disambiguation:
   - Shared names receive an ID suffix (e.g. ' · #a3f2') in subtitle.
"""

import json
import re
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def run_js_dedup(input_list):
    """Executes the exact deduplicateCandidates function extracted from ui/app.js using Node.js."""
    app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    
    # Extract deduplicateCandidates definition
    match = re.search(r"function deduplicateCandidates\s*\([^)]*\)\s*\{[\s\S]*?\n    \}", app_js)
    assert match, "Could not locate deduplicateCandidates in ui/app.js"
    dedup_fn = match.group(0)

    js_code = f"""
    {dedup_fn}
    const input = {json.dumps(input_list)};
    const result = deduplicateCandidates(input);
    console.log(JSON.stringify(result));
    """
    proc = subprocess.run(["node", "-e", js_code], capture_output=True, encoding="utf-8", check=True)
    return json.loads(proc.stdout.strip())


def run_js_get_subtitle_suffix(target_cand, cases_list):
    """Executes getCandidateIdSuffix extracted from ui/app.js using Node.js."""
    app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    
    match = re.search(r"function getCandidateIdSuffix\s*\([^)]*\)\s*\{[\s\S]*?\n    \}", app_js)
    assert match, "Could not locate getCandidateIdSuffix in ui/app.js"
    suffix_fn = match.group(0)

    js_code = f"""
    const AppState = {{ cases: {json.dumps(cases_list)} }};
    function escapeHtml(str) {{ return String(str); }}
    {suffix_fn}
    const cand = {json.dumps(target_cand)};
    const result = getCandidateIdSuffix(cand);
    console.log(JSON.stringify(result));
    """
    proc = subprocess.run(["node", "-e", js_code], capture_output=True, encoding="utf-8", check=True)
    return json.loads(proc.stdout.strip())


def test_dedup_same_name_different_ids_both_kept():
    """Applicants with identical names but different IDs must NOT be deduplicated away."""
    input_data = [
        {"candidate_id": "cand_01_a3f2", "name": "Sarah Chen", "role": "Backend Engineer"},
        {"candidate_id": "cand_02_b7e9", "name": "Sarah Chen", "role": "Senior Engineer"},
    ]
    result = run_js_dedup(input_data)
    assert len(result) == 2
    assert [c["candidate_id"] for c in result] == ["cand_01_a3f2", "cand_02_b7e9"]


def test_dedup_same_id_kept_once():
    """Candidates with the same candidate_id must be deduplicated."""
    input_data = [
        {"candidate_id": "cand_01_a3f2", "name": "Sarah Chen"},
        {"candidate_id": "cand_01_a3f2", "name": "Sarah Chen (Updated)"},
    ]
    result = run_js_dedup(input_data)
    assert len(result) == 1
    assert result[0]["candidate_id"] == "cand_01_a3f2"
    assert result[0]["name"] == "Sarah Chen"


def test_dedup_unique_ids_count_matches():
    """All candidates with unique IDs must be preserved."""
    input_data = [
        {"candidate_id": f"cand_{i}", "name": f"Candidate {i}"}
        for i in range(10)
    ]
    result = run_js_dedup(input_data)
    assert len(result) == len(input_data)


def test_dedup_null_and_array_guards():
    """Non-arrays or items missing candidate_id must be gracefully handled without errors."""
    app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    match = re.search(r"function deduplicateCandidates\s*\([^)]*\)\s*\{[\s\S]*?\n    \}", app_js)
    assert match
    dedup_fn = match.group(0)

    js_code = f"""
    {dedup_fn}
    console.log(JSON.stringify({{
        nullInput: deduplicateCandidates(null),
        undefinedInput: deduplicateCandidates(undefined),
        invalidItems: deduplicateCandidates([null, {{}}, {{ candidate_id: null }}, {{ candidate_id: 'c1' }}])
    }}));
    """
    proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout.strip())
    assert res["nullInput"] == []
    assert res["undefinedInput"] == []
    assert len(res["invalidItems"]) == 1
    assert res["invalidItems"][0]["candidate_id"] == "c1"


def test_duplicate_name_card_subtitle_suffix():
    """When two candidates share a name, a suffix is generated for the subtitle."""
    c1 = {"candidate_id": "cand_01_a3f2", "name": "Sarah Chen"}
    c2 = {"candidate_id": "cand_02_b7e9", "name": "Sarah Chen"}
    cases = [c1, c2]

    suffix1 = run_js_get_subtitle_suffix(c1, cases)
    suffix2 = run_js_get_subtitle_suffix(c2, cases)

    assert suffix1 == " \u00b7 #a3f2"
    assert suffix2 == " \u00b7 #b7e9"


def test_unique_name_no_card_subtitle_suffix():
    """Unique names must not have any disambiguation suffix added."""
    c1 = {"candidate_id": "cand_01_a3f2", "name": "Sarah Chen"}
    c2 = {"candidate_id": "cand_02_b7e9", "name": "Marcus Vance"}
    cases = [c1, c2]

    suffix1 = run_js_get_subtitle_suffix(c1, cases)
    suffix2 = run_js_get_subtitle_suffix(c2, cases)

    assert suffix1 == ""
    assert suffix2 == ""


def test_acceptance_duplicate_candidate_both_cards_visible():
    """
    Acceptance criteria:
    Copy an eval-case fixture, change only the ID, and verify both cards are kept
    and rendered distinctly in the candidate list.
    """
    fixture_path = ROOT / "eval_cases" / "case_01_strong_01.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        orig_case = json.load(f)

    dup_case = dict(orig_case)
    dup_case["candidate_id"] = "case_01_strong_01_dup"

    loaded_cases = [orig_case, dup_case]
    deduped = run_js_dedup(loaded_cases)

    # Both candidates must be retained
    assert len(deduped) == 2
    assert {c["candidate_id"] for c in deduped} == {
        "case_01_strong_01",
        "case_01_strong_01_dup"
    }

    # Verify both cards get distinct subtitle suffixes
    s1 = run_js_get_subtitle_suffix(orig_case, deduped)
    s2 = run_js_get_subtitle_suffix(dup_case, deduped)
    assert s1 != ""
    assert s2 != ""
    assert s1 != s2

