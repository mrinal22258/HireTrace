"""
Exports precomputed evaluation trajectories, case dossiers, and benchmarks
into ui/static_data.js for standalone static deployment (e.g. Hugging Face Spaces).
"""

import os
import sys
import json

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.evidence_loader import EvidenceLoader
from baseline.rubric_scorer import RubricScorer
from eval_cases.dataset import CASES, SHARED_JD

CACHE_DIR = os.path.join(root_dir, "trajectories")
CASES_DIR = os.path.join(root_dir, "eval_cases")
EVAL_FILE = os.path.join(root_dir, "eval", "eval_results.json")

def generate_static_data():
    summary_list = []
    full_docs_map = {}
    eval_map = {}

    for c in CASES:
        cid = c["candidate_id"]
        traj_file = os.path.join(CACHE_DIR, f"{cid}_trajectory.json")
        fit_score = 50.0
        consistency_score = 50.0
        quadrant = "EVALUATING"
        has_disc = False

        final_report = {}
        if os.path.exists(traj_file):
            try:
                with open(traj_file, "r", encoding="utf-8") as f:
                    tdata = json.load(f)
                final_report = tdata.get("final_report", {})
                for step in reversed(tdata.get("steps", [])):
                    if step.get("step") == "recommendation_writing":
                        out = step.get("output", {})
                        if not final_report:
                            final_report = out
                        fit_score = out.get("role_fit_score", 50.0)
                        consistency_score = out.get("evidence_consistency_score", 50.0)
                        quadrant = out.get("quadrant", "REVIEW REQUIRED")
                        has_disc = len(out.get("key_discrepancies", [])) > 0
                        break
            except Exception as err:
                print(f"Warning loading trajectory for {cid}: {err}")

        summary_list.append({
            "candidate_id": cid,
            "name": c["name"],
            "category": c.get("category", "applicant"),
            "target_role": c.get("target_role", "Senior Software Engineer"),
            "role_fit_score": fit_score,
            "evidence_consistency_score": consistency_score,
            "quadrant": quadrant,
            "has_discrepancies": has_disc
        })

        dossier = EvidenceLoader.load_case_from_dict(c)
        full_docs_map[cid] = {
            "candidate_id": cid,
            "name": c["name"],
            "target_role": c.get("target_role", "Senior Software Engineer"),
            "category": c.get("category", "applicant"),
            "documents": {
                "cv": c.get("cv_text", ""),
                "interview": c.get("interview_notes", ""),
                "assessment": c.get("technical_assessment", ""),
                "project_rfc": c.get("project_rfc", ""),
                "jd": c.get("jd_text", SHARED_JD)
            },
            "structured_profile": dossier.structured_cv_profile,
            "evidence_spans": [s.to_dict() for s in dossier.spans]
        }

        rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)
        eval_map[cid] = {
            "report": final_report,
            "baseline_a": rubric.to_dict(),
            "cached": True
        }

    eval_summary = {}
    if os.path.exists(EVAL_FILE):
        with open(EVAL_FILE, "r", encoding="utf-8") as f:
            edata = json.load(f)
        eval_summary = {
            "metadata": edata.get("metadata", {}),
            "metrics": edata.get("metrics", {})
        }

    data = {
        "cases": summary_list,
        "fullDocs": full_docs_map,
        "evaluations": eval_map,
        "evalSummary": eval_summary
    }

    # Write to static_data.js in ui/
    ui_out = os.path.join(root_dir, "ui", "static_data.js")
    with open(ui_out, "w", encoding="utf-8") as f:
        f.write("window.HIRETRACE_STATIC = " + json.dumps(data, indent=2) + ";\n")
    print(f"SUCCESS: Generated {ui_out} ({os.path.getsize(ui_out) / 1024:.1f} KB)")

if __name__ == "__main__":
    generate_static_data()
