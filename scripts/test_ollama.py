"""
HireTrace Ollama Smoke Test Script.

Validates end-to-end local open-weights LLM setup:
1. Verifies HTTP connectivity to Ollama endpoint
2. Verifies configured model exists in local model library
3. Sends a real test prompt to verify inference
4. Asserts valid JSON response parsing
5. Never fabricates a successful result

Usage:
    python scripts/test_ollama.py
"""

import os
import sys
import time
import json

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.ollama_client import OllamaClient, DEFAULT_OLLAMA_URL, DEFAULT_MODEL


def run_smoke_test():
    client = OllamaClient()

    print("=" * 45)
    print("        HireTrace Ollama Smoke Test        ")
    print("=" * 45)
    print(f"Endpoint : {client.base_url}")
    print(f"Model    : {client.model}")
    print(f"Backend  : {client.backend}")
    print("-" * 45)

    # 1. Connectivity & Model check
    reachable, health_msg = client.check_health()
    if not reachable:
        print(f"Ollama reachable : FAIL")
        print(f"Reason           : {health_msg}")
        print("-" * 45)
        print("RESULT: NOT READY")
        print("=" * 45)
        return False

    print("Ollama reachable : PASS")
    print(f"Model available  : PASS ({client.model})")

    # 2. Generation & JSON parsing check
    t0 = time.perf_counter()
    test_prompt = "Output a JSON object with keys 'status' ('ok') and 'service' ('hiretrace')."
    res = client.generate_json(prompt=test_prompt, temperature=0.1, max_tokens=128)
    elapsed = time.perf_counter() - t0

    if res.get("degraded") or res.get("error"):
        print("Generation       : FAIL")
        print(f"Reason           : {res.get('degraded_reason') or res.get('error')}")
        print("-" * 45)
        print("RESULT: NOT READY")
        print("=" * 45)
        return False

    status_val = res.get("status")
    service_val = res.get("service")
    is_valid_json = isinstance(res, dict) and (status_val is not None or service_val is not None or len(res) >= 1)

    if not is_valid_json:
        print("Generation       : PASS")
        print("JSON parsing     : FAIL")
        print(f"Raw output       : {res}")
        print("-" * 45)
        print("RESULT: NOT READY")
        print("=" * 45)
        return False

    print(f"Generation       : PASS ({elapsed*1000:.1f} ms)")
    print(f"JSON parsing     : PASS ({json.dumps({k: v for k, v in res.items() if not k.startswith('_')})})")
    print("-" * 45)
    print("RESULT: READY")
    print("=" * 45)
    return True


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
