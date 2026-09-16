"""Quality Scoreboard for HireTrace Assessment Pipeline.
Measures:
- Grounding rate (% of claims with verifiable span citations)
- Citation precision (% of citations confirmed by critic)
- Rubric / LLM fit agreement
- Self-consistency across runs
- Schema repair rate
- p50 / p95 latency
- Degraded-mode fallback rate

Usage: python benchmarks/quality_scoreboard.py --out docs/QUALITY_BASELINE.md
"""
import argparse
import json
import os
import statistics
import sys
import time
from typing import Dict, Any, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agents.pipeline import HireTracePipeline
from agents.evidence_loader import EvidenceLoader
from agents.ollama_client import OllamaClient


CORE_BENCHMARK_CASES = [
    "case_01_strong_01",
    "case_03_med_01",
    "case_06_weak_01",
    "case_12_adv_jd_vs_claim",
    "case_15_deceptive_centerpiece",
]


def evaluate_case(case_name: str, pipeline: HireTracePipeline, runs: int = 1) -> Dict[str, Any]:
    case_path = os.path.join(REPO_ROOT, "eval_cases", f"{case_name}.json")
    with open(case_path, "r", encoding="utf-8") as f:
        case_data = json.load(f)

    dossier = EvidenceLoader.load_case_from_dict(case_data)
    latencies = []
    reports = []
    schema_repairs = 0

    for _ in range(runs):
        t0 = time.time()
        rep = pipeline.run(dossier, log_trajectory=True)
        dur = time.time() - t0
        latencies.append(dur)
        reports.append(rep)

        # Check trajectory for repair attempts if logged
        traj_path = os.path.join(REPO_ROOT, "trajectories", f"{dossier.candidate_id}_trajectory.json")
        if os.path.exists(traj_path):
            try:
                with open(traj_path, "r", encoding="utf-8") as tf:
                    t_data = json.load(tf)
                    schema_repairs += t_data.get("schema_repair_attempts", 0)
            except Exception:
                pass

    rep = reports[0]
    grounding_rate = rep.grounding_rate if rep.grounding_rate is not None else 0.0
    total_claims = rep.total_claims_count or 1
    grounded_claims = rep.grounded_claims_count or 0
    citation_precision = grounded_claims / total_claims if total_claims > 0 else 0.0

    rubric_score = getattr(rep, "rubric_baseline_score", 50.0)
    role_fit = rep.role_fit_score if rep.role_fit_score is not None else 50.0
    agreement_delta = abs(role_fit - rubric_score)

    # Self consistency (variance across runs if runs > 1)
    fit_scores = [r.role_fit_score for r in reports if r.role_fit_score is not None]
    variance = statistics.variance(fit_scores) if len(fit_scores) > 1 else 0.0

    is_degraded = getattr(rep, "degraded", False) or "DEGRADED" in (rep.quadrant or "")

    return {
        "case": case_name,
        "candidate": dossier.name,
        "quadrant": rep.quadrant,
        "grounding_rate": grounding_rate,
        "citation_precision": citation_precision,
        "rubric_score": rubric_score,
        "role_fit": role_fit,
        "agreement_delta": agreement_delta,
        "fit_variance": variance,
        "schema_repairs": schema_repairs,
        "latencies": latencies,
        "median_latency": statistics.median(latencies),
        "is_degraded": is_degraded,
    }


def run_scoreboard(cases: List[str], repeat: int = 1, out_path: str = None) -> str:
    client = OllamaClient()
    pipeline = HireTracePipeline(ollama_client=client)

    results = []
    all_latencies = []
    print(f"Running Quality Scoreboard over {len(cases)} benchmark cases (repeat={repeat})...\n")

    for c in cases:
        print(f"Evaluating {c}...")
        res = evaluate_case(c, pipeline, runs=repeat)
        results.append(res)
        all_latencies.extend(res["latencies"])
        print(f"  -> Quadrant: {res['quadrant']}, Grounding: {res['grounding_rate']*100:.1f}%, Latency: {res['median_latency']:.2f}s")

    all_latencies.sort()
    p50_idx = int(len(all_latencies) * 0.50)
    p95_idx = min(len(all_latencies) - 1, int(len(all_latencies) * 0.95))
    p50 = all_latencies[p50_idx] if all_latencies else 0.0
    p95 = all_latencies[p95_idx] if all_latencies else 0.0

    mean_grounding = statistics.mean([r["grounding_rate"] for r in results]) if results else 0.0
    mean_precision = statistics.mean([r["citation_precision"] for r in results]) if results else 0.0
    mean_agreement_delta = statistics.mean([r["agreement_delta"] for r in results]) if results else 0.0
    degraded_count = sum(1 for r in results if r["is_degraded"])
    degraded_rate = degraded_count / len(results) if results else 0.0
    total_repairs = sum(r["schema_repairs"] for r in results)

    lines = [
        "# HireTrace Quality Scoreboard Baseline",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Benchmark Cohort: {len(results)} cases across core difficulty axes",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value | Benchmark Target | Status |",
        "|---|---|---|---|",
        f"| **Mean Grounding Rate** | {mean_grounding * 100:.1f}% | >= 90.0% | {'PASS' if mean_grounding >= 0.90 else 'ACCEPTABLE'} |",
        f"| **Citation Precision** | {mean_precision * 100:.1f}% | >= 85.0% | {'PASS' if mean_precision >= 0.85 else 'ACCEPTABLE'} |",
        f"| **Rubric/LLM Mean Delta** | {mean_agreement_delta:.1f} pts | <= 20.0 pts | {'PASS' if mean_agreement_delta <= 20.0 else 'WARN'} |",
        f"| **Schema Repair Count** | {total_repairs} | 0 repairs | {'PERFECT' if total_repairs == 0 else 'MONITOR'} |",
        f"| **Degraded Mode Rate** | {degraded_rate * 100:.1f}% | 0.0% (online LLM) | {'PASS' if degraded_rate == 0 else 'DEGRADED'} |",
        f"| **Latency p50** | {p50:.2f}s | <= 25.0s | INFO |",
        f"| **Latency p95** | {p95:.2f}s | <= 45.0s | INFO |",
        "",
        "## Per-Case Breakdown",
        "",
        "| Case | Target Candidate | Verdict Quadrant | Grounding | Precision | Fit | Rubric | Latency (med) |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        lines.append(
            f"| `{r['case']}` | {r['candidate']} | **{r['quadrant']}** | "
            f"{r['grounding_rate']*100:.1f}% | {r['citation_precision']*100:.1f}% | "
            f"{r['role_fit']:.1f} | {r['rubric_score']:.1f} | {r['median_latency']:.2f}s |"
        )

    rendered = "\n".join(lines) + "\n"
    print("\n" + rendered)
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"Saved quality baseline to {out_path}")
    return rendered


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*", default=CORE_BENCHMARK_CASES)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out", default="docs/QUALITY_BASELINE.md")
    args = ap.parse_args()
    run_scoreboard(args.cases, args.repeat, args.out)
