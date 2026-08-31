"""
Standalone Ollama Latency and Output Benchmark for HireTrace.

Run intentionally when benchmarking local model throughput:
    python benchmarks/ollama_benchmark.py
"""

import time
import json
import requests
import os

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434") + "/api/generate"

PROMPT = """You are an evidence verification engine. Cross-reference the following candidate claim against the evidence snippet.
Output ONLY valid JSON matching this schema:
{
  "claim": "Claim text",
  "status": "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT_EVIDENCE",
  "confidence": float (0.0 to 1.0),
  "evidence_span": "Exact quote or explanation"
}

Claim: Candidate has 3 years of production experience leading a team.
Evidence: CV says 'Led team for 3 years at FinFlow'. Interview notes say 'Joined FinFlow ~18 months ago as a team member'.
"""

MODELS = ["qwen2.5:3b"]


def benchmark_model(model_name: str):
    print(f"\n--- Benchmarking {model_name} on Local Ollama ---")
    payload = {
        "model": model_name,
        "prompt": PROMPT,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 256
        }
    }

    start_time = time.time()
    try:
        res = requests.post(OLLAMA_URL, json=payload, timeout=60)
        elapsed = time.time() - start_time
        if res.status_code != 200:
            print(f"Error {res.status_code}: {res.text}")
            return False, elapsed

        response_json = res.json()
        raw_text = response_json.get("response", "")
        print(f"Latency: {elapsed:.2f}s")
        print(f"Raw Output:\n{raw_text}")

        parsed = json.loads(raw_text)
        print(f"Parsed JSON: {list(parsed.keys())}")
        print(f"Detected status: {parsed.get('status')}")
        return True, elapsed
    except Exception as e:
        print(f"Benchmark failed for {model_name}: {e}")
        return False, 0.0


if __name__ == "__main__":
    for m in MODELS:
        benchmark_model(m)
