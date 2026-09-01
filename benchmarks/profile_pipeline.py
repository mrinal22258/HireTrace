"""
Profiler for HireTrace LLM Calls.

Measures and reports per-stage LLM metrics:
- Stage name
- Model used
- Input / Prompt tokens
- Output / Generation tokens
- Generation latency vs total latency
- Cache hit/miss
"""

import os
import sys
import time
import json
from dataclasses import dataclass
from typing import List, Dict, Any

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.evidence_loader import EvidenceLoader
from eval_cases.dataset import CASES
from agents.pipeline import HireTracePipeline
from agents.ollama_client import OllamaClient


def profile_candidate(candidate_dict: Dict[str, Any]):
    print("=" * 75)
    print(f"  HireTrace Detailed LLM Call Profiler: {candidate_dict.get('name')}")
    print("=" * 75)

    client = OllamaClient()
    dossier = EvidenceLoader.load_case_from_dict(candidate_dict)

    # Instrument Ollama client to capture individual call telemetry
    call_records = []
    original_generate = client.generate_json

    def instrumented_generate_json(*args, **kwargs):
        t0 = time.perf_counter()
        res = original_generate(*args, **kwargs)
        duration = time.perf_counter() - t0

        prompt = kwargs.get("prompt", "")
        system = kwargs.get("system_prompt", "")
        # Extract metadata
        record = {
            "prompt_length_chars": len(prompt) + len(system or ""),
            "prompt_tokens": res.get("_prompt_tokens", len(prompt) // 4),
            "output_tokens": res.get("_output_tokens", len(str(res)) // 4),
            "generation_latency_sec": res.get("_eval_duration_sec", duration),
            "total_latency_sec": duration,
            "model": res.get("_model", client.model),
            "degraded": res.get("degraded", False)
        }
        call_records.append(record)
        return res

    client.generate_json = instrumented_generate_json

    pipeline = HireTracePipeline(ollama_client=client)

    t_start = time.perf_counter()
    report = pipeline.run(dossier, log_trajectory=False)
    t_total = time.perf_counter() - t_start

    cache_stats = pipeline.req_mapper.get_cache_stats()

    print("\n--- STAGE-BY-STAGE LLM CALL BREAKDOWN ---")
    print(f"{'Call #':<8}{'Tokens In':<12}{'Tokens Out':<12}{'Gen Lat (s)':<14}{'Total Lat (s)':<14}{'Model':<12}")
    print("-" * 75)

    total_tokens_in = 0
    total_tokens_out = 0
    for idx, rec in enumerate(call_records, start=1):
        total_tokens_in += rec["prompt_tokens"]
        total_tokens_out += rec["output_tokens"]
        print(f"{idx:<8}{rec['prompt_tokens']:<12}{rec['output_tokens']:<12}{rec['generation_latency_sec']:<14.2f}{rec['total_latency_sec']:<14.2f}{rec['model']:<12}")

    print("-" * 75)
    print(f"Total Pipeline Wall Time : {t_total:.2f} s")
    print(f"Total LLM Calls Made     : {len(call_records)}")
    print(f"Total Input Tokens       : {total_tokens_in}")
    print(f"Total Output Tokens      : {total_tokens_out}")
    print(f"Req Mapping Cache        : {cache_stats['hits']} hits, {cache_stats['misses']} misses")
    print(f"Result Quadrant          : {report.quadrant}")
    print(f"Role Fit Score           : {report.role_fit_score}")
    print(f"Consistency Score        : {report.evidence_consistency_score}")
    print(f"Degraded Status          : {report.degraded}")
    print("=" * 75)

    return {
        "candidate": candidate_dict.get("name"),
        "total_time": t_total,
        "calls": call_records,
        "cache": cache_stats,
        "report": report.to_dict()
    }


if __name__ == "__main__":
    # Profile Sarah Chen (baseline clean applicant)
    profile_candidate(CASES[0])
