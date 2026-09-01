"""
HireTrace High-Throughput Load-Test Harness.

Generates N synthetic multi-source candidate dossiers and measures:
- Total wall-clock time
- Throughput (candidates / second and candidates / hour)
- Latency distribution (min, mean, p50, p90, p95, p99, max)
- Pipeline classification outcomes (Quadrants & Fast-Triage rejects)
- Backend degradation tracking

Usage:
    python benchmarks/load_test_harness.py --count 50 --workers 8
    python benchmarks/load_test_harness.py --count 500 --workers 8
"""

import os
import sys
import time
import json
import argparse
import random
import statistics
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.pipeline import HireTracePipeline
from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.ollama_client import OllamaClient
from eval_cases.dataset import CASES, SHARED_JD

FIRST_NAMES = ["Alex", "Jordan", "Taylor", "Morgan", "Sam", "Chris", "Pat", "Riley", "Casey", "Avery", "Jamie", "Logan"]
LAST_NAMES = ["Sterling", "Chen", "Vance", "Mercer", "Novak", "Holloway", "Kim", "Patel", "Garcia", "Ross", "Kowalski", "Adeyemi"]
COMPANIES = ["FinFlow Technologies", "NexusScale Inc", "CloudMatrix", "ApexData", "QuantMetrics", "HyperScale Systems"]


def generate_synthetic_dossiers(n: int) -> List[CandidateDossier]:
    """Generates N synthetic candidate dossiers by mutating baseline templates."""
    dossiers = []
    base_cases = CASES

    for i in range(n):
        base = base_cases[i % len(base_cases)]
        fname = random.choice(FIRST_NAMES)
        lname = random.choice(LAST_NAMES)
        full_name = f"{fname} {lname} #{i+1}"
        cid = f"synth_{i+1:04d}_{fname.lower()}_{lname.lower()}"
        company = random.choice(COMPANIES)

        # Mutate document text with variations
        cv_text = base["cv_text"].replace("FinFlow Technologies", company)
        interview = base["interview_notes"].replace("FinFlow Technologies", company)
        assessment = base["technical_assessment"]
        project = base["project_rfc"]

        case_dict = {
            "candidate_id": cid,
            "name": full_name,
            "target_role": base.get("target_role", "Senior Python & Distributed Systems Engineer"),
            "category": base.get("category", "applicant"),
            "cv_text": cv_text,
            "interview_notes": interview,
            "technical_assessment": assessment,
            "project_rfc": project,
            "jd_text": SHARED_JD
        }

        dossier = EvidenceLoader.load_case_from_dict(case_dict)
        dossiers.append(dossier)

    return dossiers


def evaluate_single_candidate(pipeline: HireTracePipeline, dossier: CandidateDossier) -> Dict[str, Any]:
    """Evaluates a single candidate and records execution latency and real LLM status."""
    t0 = time.perf_counter()
    try:
        report = pipeline.run(dossier, log_trajectory=False)
        latency = time.perf_counter() - t0
        is_real = (report.degraded is False) and (report.role_fit_score is not None)
        return {
            "candidate_id": dossier.candidate_id,
            "status": "success",
            "is_real_llm": is_real,
            "latency_sec": latency,
            "quadrant": report.quadrant,
            "role_fit_score": report.role_fit_score,
            "consistency_score": report.evidence_consistency_score,
            "degraded": report.degraded,
            "degraded_reason": report.degraded_reason,
            "error": None
        }
    except Exception as e:
        latency = time.perf_counter() - t0
        return {
            "candidate_id": dossier.candidate_id,
            "status": "error",
            "is_real_llm": False,
            "latency_sec": latency,
            "quadrant": "ERROR",
            "role_fit_score": None,
            "consistency_score": None,
            "degraded": True,
            "degraded_reason": f"Execution exception: {e}",
            "error": str(e)
        }


def run_benchmark(count: int, workers: int = 4, mode: str = "real", output_file: Optional[str] = None):
    print("=" * 70)
    print(f"  HireTrace Benchmark: N={count}, Mode={mode.upper()}, Workers={workers}")
    print("=" * 70)

    # Initialize client based on mode
    if mode == "degraded":
        print("[SETUP] Running in INTENTIONAL DEGRADED mode (unreachable endpoint)...")
        client = OllamaClient(base_url="http://127.0.0.1:59999")
    else:
        client = OllamaClient()
        is_ready, health_msg = client.check_health()
        if not is_ready:
            print("\n" + "!" * 70)
            print("  REAL LLM BENCHMARK ABORTED")
            print(f"  Reason: {health_msg}")
            print("!" * 70 + "\n")
            sys.exit(1)
        print(f"[SETUP] Local Ollama verified: {client.model} reachable at {client.base_url}")

    print(f"\n[1/3] Generating {count} synthetic candidate dossiers...")
    dossiers = generate_synthetic_dossiers(count)
    print(f"Generated {len(dossiers)} dossiers.")

    print(f"\n[2/3] Firing evaluations (workers={workers}, mode={mode})...")
    pipeline = HireTracePipeline(ollama_client=client)

    results: List[Dict[str, Any]] = []
    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(evaluate_single_candidate, pipeline, d): d.candidate_id for d in dossiers}
        completed_count = 0
        for f in as_completed(futures):
            res = f.result()
            results.append(res)
            completed_count += 1
            elapsed_so_far = time.perf_counter() - wall_start
            rate = completed_count / max(0.001, elapsed_so_far)
            status_tag = "REAL" if res["is_real_llm"] else "DEGRADED"
            print(f"  [{completed_count:>3}/{count}] ({status_tag}) cand={res['candidate_id']} in {res['latency_sec']*1000:.0f}ms | Current Rate: {rate:.2f} cand/s")

    wall_duration = time.perf_counter() - wall_start

    print(f"\n[3/3] Calculating performance & latency metrics...")
    latencies = [r["latency_sec"] for r in results]
    latencies.sort()

    p50 = statistics.median(latencies)
    mean_lat = statistics.mean(latencies)
    min_lat = latencies[0]
    max_lat = latencies[-1]

    def percentile(p: float) -> float:
        idx = int(len(latencies) * p)
        return latencies[min(idx, len(latencies) - 1)]

    p90 = percentile(0.90)
    p95 = percentile(0.95)
    p99 = percentile(0.99)

    candidates_per_sec = count / max(0.001, wall_duration)
    candidates_per_hour = candidates_per_sec * 3600.0

    real_llm_count = sum(1 for r in results if r["is_real_llm"])
    degraded_count = sum(1 for r in results if r["degraded"])
    error_count = sum(1 for r in results if r["status"] == "error")

    # Quadrant distribution
    quadrants: Dict[str, int] = {}
    for r in results:
        q = r["quadrant"]
        quadrants[q] = quadrants.get(q, 0) + 1

    # Requirement cache stats
    req_cache_stats = pipeline.req_mapper.get_cache_stats()
    telemetry = client.get_telemetry()

    summary = {
        "benchmark_mode": mode,
        "model": client.model,
        "endpoint": client.base_url,
        "candidate_count": count,
        "concurrent_workers": workers,
        "execution_outcomes": {
            "real_llm_successful": real_llm_count,
            "degraded": degraded_count,
            "errors": error_count
        },
        "wall_clock_seconds": round(wall_duration, 3),
        "throughput": {
            "candidates_per_sec": round(candidates_per_sec, 3),
            "candidates_per_hour": round(candidates_per_hour, 1)
        },
        "latency_seconds": {
            "min": round(min_lat, 4),
            "mean": round(mean_lat, 4),
            "p50": round(p50, 4),
            "p90": round(p90, 4),
            "p95": round(p95, 4),
            "p99": round(p99, 4),
            "max": round(max_lat, 4)
        },
        "requirement_cache": req_cache_stats,
        "llm_telemetry": telemetry,
        "quadrant_distribution": quadrants
    }

    print("\n" + "=" * 70)
    print(f"               BENCHMARK RESULTS REPORT (MODE: {mode.upper()})")
    print("=" * 70)
    print(f"Model                      : {client.model}")
    print(f"Endpoint                   : {client.base_url}")
    print(f"Total Candidates Evaluated : {count}")
    print(f"Real LLM Inference (Pass)  : {real_llm_count} ({real_llm_count*100/count:.1f}%)")
    print(f"Explicitly Degraded        : {degraded_count} ({degraded_count*100/count:.1f}%)")
    print(f"Errors / Exceptions        : {error_count}")
    print(f"Pipeline Workers           : {workers}")
    print(f"Total Wall-Clock Time      : {wall_duration:.2f} seconds")
    print(f"Throughput                 : {candidates_per_sec:.2f} candidates/sec")
    print(f"Hourly Capacity            : {candidates_per_hour:,.1f} candidates/hour")
    print("-" * 70)
    print("Requirement Mapping Cache Telemetry:")
    print(f"  Cache Hits               : {req_cache_stats['hits']}")
    print(f"  Cache Misses (LLM calls) : {req_cache_stats['misses']}")
    print(f"  Total LLM API Calls      : {telemetry['total_calls']} (Successful: {telemetry['successful_calls']}, Fallbacks: {telemetry['fallback_calls']})")
    print("-" * 70)
    print("Latency Distribution (per candidate):")
    print(f"  Min   : {min_lat*1000:.1f} ms")
    print(f"  Mean  : {mean_lat*1000:.1f} ms")
    print(f"  p50   : {p50*1000:.1f} ms")
    print(f"  p90   : {p90*1000:.1f} ms")
    print(f"  p95   : {p95*1000:.1f} ms")
    print(f"  p99   : {p99*1000:.1f} ms")
    print(f"  Max   : {max_lat*1000:.1f} ms")
    print("-" * 70)
    print("Quadrant Distribution:")
    for q_name, q_cnt in sorted(quadrants.items()):
        pct = (q_cnt / count) * 100
        print(f"  {q_name:<25}: {q_cnt:>4} ({pct:>5.1f}%)")
    print("=" * 70 + "\n")

    if mode == "real" and real_llm_count != count:
        print(f"[!] NOTICE: {count - real_llm_count} candidates degraded during real benchmark.")

    if output_file:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Saved JSON benchmark results to {output_file}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HireTrace Benchmark Load Test")
    parser.add_argument("--count", "--n", "-n", type=int, default=10, dest="count", help="Number of synthetic candidates (e.g. 2, 10, 50)")
    parser.add_argument("--mode", type=str, default="real", choices=["real", "degraded"], help="Benchmark mode: 'real' (requires Ollama) or 'degraded' (tests fallback)")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent pipeline workers")
    parser.add_argument("--llm-concurrency", type=int, default=1, help="Max concurrent LLM generation calls through semaphore (1 or 2)")
    parser.add_argument("--output", type=str, default=None, help="Path to save JSON benchmark results")
    args = parser.parse_args()

    from agents.ollama_client import set_max_concurrency
    set_max_concurrency(args.llm_concurrency)

    run_benchmark(count=args.count, workers=args.workers, mode=args.mode, output_file=args.output)

