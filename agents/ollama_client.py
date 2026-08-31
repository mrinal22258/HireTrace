"""
Local Ollama Client for HireTrace.

Zero paid API dependencies. Handles structured JSON calls to local Ollama instances
running on consumer hardware (e.g. RTX 3050 Laptop with 4GB VRAM).
Includes retry handling, JSON validation, and execution timing.
"""

import os
import time
import json
import logging
from typing import Dict, Any, Optional, Union
import requests

logger = logging.getLogger("hiretrace.ollama")

DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


class OllamaClient:
    """Client for querying local Ollama models with enforced JSON structure."""

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.generate_endpoint = f"{self.base_url}/api/generate"
        self.total_calls = 0
        self.successful_calls = 0
        self.fallback_calls = 0

    def is_available(self) -> bool:
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=1.0)
            return res.status_code == 200
        except Exception:
            return False

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "fallback_calls": self.fallback_calls
        }

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Sends prompt to local Ollama with format="json" and validates valid dictionary output.
        Retries if parsing fails.
        """
        self.total_calls += 1
        if not self.is_available():
            self.fallback_calls += 1
            return {
                "error": "Ollama server unavailable",
                "role_fit_score": 50.0,
                "_latency_sec": 0.0,
                "_model": self.model
            }
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        last_error = None
        for attempt in range(1 + max_retries):
            start_time = time.time()
            try:
                res = requests.post(self.generate_endpoint, json=payload, timeout=90)
                elapsed = time.time() - start_time
                if res.status_code != 200:
                    last_error = f"HTTP {res.status_code}: {res.text}"
                    time.sleep(1.0)
                    continue

                response_data = res.json()
                raw_text = response_data.get("response", "").strip()

                # Clean markdown blocks if present
                if raw_text.startswith("```"):
                    lines = raw_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    raw_text = "\n".join(lines).strip()

                parsed = json.loads(raw_text)
                if isinstance(parsed, dict):
                    self.successful_calls += 1
                    parsed["_latency_sec"] = round(elapsed, 2)
                    parsed["_model"] = self.model
                    return parsed
                elif isinstance(parsed, list):
                    self.successful_calls += 1
                    return {"items": parsed, "_latency_sec": round(elapsed, 2), "_model": self.model}
                else:
                    last_error = f"Output is not a JSON object: {type(parsed)}"

            except json.JSONDecodeError as jde:
                last_error = f"JSON parse error on attempt {attempt+1}: {jde}"
                # Append guidance to prompt on retry
                payload["prompt"] += "\nEnsure your response is valid JSON strictly without additional commentary."
            except Exception as exc:
                last_error = f"Network or execution error: {exc}"
                time.sleep(1.0)

        self.fallback_calls += 1
        logger.error(f"Failed to obtain valid JSON from Ollama ({self.model}): {last_error}")
        return {
            "error": str(last_error),
            "raw_output": raw_text if 'raw_text' in locals() else "",
            "_latency_sec": 0.0,
            "_model": self.model
        }
