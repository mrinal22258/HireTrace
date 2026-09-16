"""Profile one candidate end-to-end and print a per-step latency table.
Usage: python scripts/profile_pipeline.py --candidate <candidate_id> --repeat 3
"""
import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict

# Ensure repo root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agents.pipeline import HireTracePipeline
from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.ollama_client import OllamaClient


def load_dossier(candidate_id: str) -> CandidateDossier:
    candidates_to_try = [
        os.path.join("eval_cases", f"{candidate_id}.json"),
        os.path.join("eval_cases", candidate_id),
        os.path.join("uploads", candidate_id, "candidate.json"),
        os.path.join("uploads", candidate_id, f"{candidate_id}.json"),
    ]
    for path in candidates_to_try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return EvidenceLoader.load_case_from_dict(data)
    raise FileNotFoundError(f"Could not find dossier for candidate '{candidate_id}' in eval_cases/ or uploads/")


def profile(candidate_id: str, repeat: int, out_file: str = None) -> str:
    client = OllamaClient()
    ok, diag = client.check_health()
    output_lines = []
    def log(msg=""):
        print(msg)
        output_lines.append(msg)

    log(f"LLM endpoint healthy={ok} {diag}\n")
    pipeline = HireTracePipeline(ollama_client=client)
    dossier = load_dossier(candidate_id)
    per_step = defaultdict(list)
    totals = []

    for run_index in range(repeat):
        t0 = time.time()
        report = pipeline.run(dossier, log_trajectory=True)
        totals.append(time.time() - t0)
        traj_path = os.path.join("trajectories", f"{dossier.candidate_id}_trajectory.json")
        if not os.path.exists(traj_path):
            traj_path = os.path.join("trajectories", f"{dossier.candidate_id}.json")
        with open(traj_path, encoding="utf-8") as fh:
            traj = json.load(fh)
        for step in traj["steps"]:
            per_step[step.get("agent") or step["step"]].append(step["duration_sec"])
        log(f"run {run_index + 1}: {totals[-1]:.2f}s")

    log(f"\n{'step':<48}{'median':>9}{'min':>9}{'max':>9}{'% of total':>12}")
    log("-" * 87)
    median_total = statistics.median(totals)
    rows = sorted(per_step.items(), key=lambda kv: -statistics.median(kv[1]))
    for name, samples in rows:
        med = statistics.median(samples)
        pct = (100 * med / median_total) if median_total > 0 else 0.0
        log(f"{name:<48}{med:>9.3f}{min(samples):>9.3f}{max(samples):>9.3f}{pct:>11.1f}%")
    log("-" * 87)
    log(f"{'TOTAL':<48}{median_total:>9.3f}")
    log("\nFirst run vs. later runs (cold model load shows up here):")
    first_vs_later = (
        f" run 1: {totals[0]:.2f}s later median: {statistics.median(totals[1:]):.2f}s"
        if repeat > 1
        else " (use --repeat 3 to see this)"
    )
    log(first_vs_later)

    rendered = "\n".join(output_lines)
    if out_file:
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        print(f"\nWrote baseline to {out_file}")
    return rendered


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="case_15_deceptive_centerpiece", help="Candidate ID or file prefix")
    ap.add_argument("--repeat", type=int, default=3, help="Number of repetitions")
    ap.add_argument("--out", default=None, help="Optional output path to save baseline")
    args = ap.parse_args()
    profile(args.candidate, args.repeat, args.out)
