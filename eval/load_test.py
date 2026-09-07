"""
Load and Concurrency Benchmark for HireTrace Multi-Endpoint LLM Scaling.

Benchmarks end-to-end inference throughput comparing:
  - Topology 1: Single endpoint (concurrency = 1)
  - Topology 2: Dual endpoints (concurrency = 2, least-loaded routing)

Verifies Phase 4 acceptance criteria:
Multi-endpoint routing provides meaningfully higher throughput than a single serialized endpoint.
"""

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.ollama_client import OllamaClient, EndpointState


class SimulatedBackendServer:
    """Simulates an inference server with configurable compute delay."""
    def __init__(self, latency_sec: float = 0.04):
        self.latency_sec = latency_sec

    def handle_request(self, prompt: str) -> Dict[str, Any]:
        time.sleep(self.latency_sec)
        return {"status": "ok", "role_fit_score": 85, "parsed": True}


def run_concurrency_benchmark(
    num_requests: int = 20,
    endpoint_latency: float = 0.04
) -> Dict[str, Any]:
    """Runs a batch of evaluation requests through 1 vs 2 configured endpoints."""
    server = SimulatedBackendServer(latency_sec=endpoint_latency)

    # 1. Single Endpoint Setup
    client_single = OllamaClient(
        base_urls=["http://simulated-gpu-1:11434"],
        concurrency_per_endpoint=1
    )
    client_single.is_available = lambda: True
    def _mock_gen_single(ep_url, prompt, system_prompt, temp, max_tokens):
        return server.handle_request(prompt)
    client_single._generate_vllm_on_endpoint = _mock_gen_single
    client_single.backend = "vllm"

    # 2. Dual Endpoint Setup
    client_dual = OllamaClient(
        base_urls=["http://simulated-gpu-1:11434", "http://simulated-gpu-2:11434"],
        concurrency_per_endpoint=1
    )
    client_dual.is_available = lambda: True
    def _mock_gen_dual(ep_url, prompt, system_prompt, temp, max_tokens):
        return server.handle_request(prompt)
    client_dual._generate_vllm_on_endpoint = _mock_gen_dual
    client_dual.backend = "vllm"

    # Benchmark helper
    def benchmark_client(client: OllamaClient, title: str) -> Dict[str, Any]:
        latencies = []
        t0 = time.time()

        def worker(idx: int):
            req_start = time.time()
            res = client.generate_json(
                prompt=f"Assess candidate {idx}",
                system_prompt="Return JSON"
            )
            latencies.append(time.time() - req_start)
            return res

        with ThreadPoolExecutor(max_workers=max(1, client.total_capacity * 2)) as pool:
            futures = [pool.submit(worker, i) for i in range(num_requests)]
            results = [f.result() for f in futures]

        total_time = time.time() - t0
        throughput = num_requests / total_time
        avg_latency = sum(latencies) / len(latencies)

        return {
            "title": title,
            "endpoints": len(client.endpoints),
            "max_concurrency": client.total_capacity,
            "total_time_sec": round(total_time, 3),
            "throughput_req_per_sec": round(throughput, 2),
            "avg_latency_sec": round(avg_latency, 3),
            "telemetry": client.get_telemetry()
        }

    res_single = benchmark_client(client_single, "Single GPU Endpoint (1x Replica)")
    res_dual = benchmark_client(client_dual, "Dual GPU Endpoints (2x Replicas)")

    speedup = round(res_dual["throughput_req_per_sec"] / max(0.01, res_single["throughput_req_per_sec"]), 2)

    return {
        "num_requests": num_requests,
        "single": res_single,
        "dual": res_dual,
        "speedup_factor": speedup
    }


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  HIRETRACE LLM CONCURRENCY LOAD BENCHMARK (PHASE 4)")
    print("=" * 60)

    summary = run_concurrency_benchmark(num_requests=20, endpoint_latency=0.04)

    s = summary["single"]
    d = summary["dual"]

    print(f"\nRequests Processed : {summary['num_requests']}")
    print("-" * 60)
    print(f"1x Endpoint  -> Total Time: {s['total_time_sec']}s | Throughput: {s['throughput_req_per_sec']} req/s | Avg Latency: {s['avg_latency_sec']}s")
    print(f"2x Endpoints -> Total Time: {d['total_time_sec']}s | Throughput: {d['throughput_req_per_sec']} req/s | Avg Latency: {d['avg_latency_sec']}s")
    print("-" * 60)
    print(f"Throughput Speedup with 2 Endpoints: {summary['speedup_factor']}x")
    print("=" * 60 + "\n")
