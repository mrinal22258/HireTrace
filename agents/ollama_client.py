"""
Local LLM Client for HireTrace.

ZERO PAID API DEPENDENCIES. All LLM calls must go through a local, self-hosted open-weights
model (Ollama or vLLM). No commercial API keys (OpenAI, Anthropic, etc.) are permitted.
Includes retry handling, JSON validation, and execution timing.
Propagates an explicit DEGRADED state when the backend is unavailable (no silent fallback).
"""

import os
import time
import json
import logging
import threading
from typing import Dict, Any, Optional, Tuple
import requests

logger = logging.getLogger("hiretrace.ollama")

# Authoritative configuration defaults (Single source of truth)
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90.0"))
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()  # "ollama" or "vllm"
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
MAX_LLM_CONCURRENCY = int(os.getenv("MAX_LLM_CONCURRENCY", "1"))

# Shared bounded semaphore to serialize local GPU inference
_LLM_SEMAPHORE = threading.Semaphore(MAX_LLM_CONCURRENCY)


def set_max_concurrency(n: int):
    """Dynamically updates the bounded LLM semaphore concurrency limit."""
    global _LLM_SEMAPHORE, MAX_LLM_CONCURRENCY
    MAX_LLM_CONCURRENCY = max(1, n)
    _LLM_SEMAPHORE = threading.Semaphore(MAX_LLM_CONCURRENCY)


class OllamaClient:
    """Client for querying local Ollama or local vLLM instances with enforced JSON structure."""

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL, model: str = DEFAULT_MODEL, timeout: float = DEFAULT_TIMEOUT, mock: bool = False):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.generate_endpoint = f"{self.base_url}/api/generate"
        is_default_url = (self.base_url == DEFAULT_OLLAMA_URL or "mock" in self.base_url)
        self.backend = "mock" if (mock or (is_default_url and os.getenv("HIRETRACE_OFFLINE_MOCK", "").lower() in ("1", "true", "yes"))) else LLM_BACKEND
        self.total_calls = 0
        self.successful_calls = 0
        self.fallback_calls = 0
        self._mock_delegate = None

    def check_health(self) -> Tuple[bool, str]:
        """
        Detailed diagnostic check of backend reachability and model existence.
        Returns (is_ready, diagnosis_message).
        """
        if self.backend == "mock":
            return True, "Mock Ollama backend online (Offline / CI mode active)"

        try:
            if self.backend == "vllm":
                res = requests.get(f"{VLLM_BASE_URL}/models", timeout=3.0)
                if res.status_code == 200:
                    return True, "vLLM reachable and ready"
                return False, f"[HTTP_ERROR] vLLM health check returned status {res.status_code}"
            else:
                res = requests.get(f"{self.base_url}/api/tags", timeout=3.0)
                if res.status_code != 200:
                    return False, f"[HTTP_ERROR] Ollama returned HTTP {res.status_code}"

                data = res.json()
                installed = [m.get("name") for m in data.get("models", [])]
                # Check if model exists (exact or prefix match e.g. qwen2.5:3b in qwen2.5:3b-instruct)
                model_base = self.model.split(":")[0]
                matched = any(self.model in m or m.startswith(self.model) or model_base in m for m in installed)
                if not matched and installed:
                    return False, f"[MODEL_NOT_FOUND] Model '{self.model}' not installed in local Ollama (Available: {', '.join(installed)})"
                elif not installed:
                    return False, f"[MODEL_NOT_FOUND] No models installed in local Ollama. Please run: ollama pull {self.model}"

                return True, f"Ollama reachable with model '{self.model}'"
        except requests.exceptions.ConnectionError:
            return False, f"[CONNECTION_ERROR] Ollama server unreachable at {self.base_url} (Connection refused)"
        except requests.exceptions.Timeout:
            return False, f"[TIMEOUT] Ollama health check timed out at {self.base_url}"
        except Exception as e:
            return False, f"[UNKNOWN_ERROR] Ollama diagnostic check failed: {type(e).__name__}: {e}"

    def is_available(self) -> bool:
        """Checks whether the configured local open-weights backend is reachable (cached 5s)."""
        now = time.time()
        if hasattr(self, "_cached_available") and (now - getattr(self, "_cached_available_time", 0) < 5.0):
            return self._cached_available

        ready, msg = self.check_health()
        self._cached_available = ready
        self._cached_available_time = now
        self._last_health_msg = msg
        return ready

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "fallback_calls": self.fallback_calls
        }

    def _generate_vllm(self, prompt: str, system_prompt: Optional[str], temperature: float, max_tokens: int) -> Dict[str, Any]:
        """Queries local self-hosted vLLM endpoint (OpenAI-compatible protocol, 100% self-hosted)."""
        url = f"{VLLM_BASE_URL}/chat/completions"
        headers = {"Content-Type": "application/json"}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        res = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()
        raw_text = data["choices"][0]["message"]["content"]
        return json.loads(raw_text)

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Sends prompt to local open-weights backend (Ollama or self-hosted vLLM) and returns validated dictionary output.
        If the backend is unavailable, explicitly flags degraded state with granular diagnostic failure reason.
        NEVER outputs a fabricated score.
        """
        self.total_calls += 1

        if self.backend == "mock":
            if self._mock_delegate is None:
                from agents.mock_ollama_client import MockOllamaClient
                self._mock_delegate = MockOllamaClient(base_url=self.base_url, model=self.model)
            return self._mock_delegate.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=max_retries
            )

        if not self.is_available():
            self.fallback_calls += 1
            reason = getattr(self, "_last_health_msg", f"[CONNECTION_ERROR] Local LLM backend ({self.backend}) unavailable")
            logger.warning("Local LLM backend unavailable: %s. Propagating DEGRADED state.", reason)
            return {
                "error": reason,
                "error_code": "BACKEND_UNAVAILABLE",
                "degraded": True,
                "degraded_reason": reason,
                "role_fit_score": None,
                "_latency_sec": 0.0,
                "_model": self.model
            }

        # Serialize GPU inference via bounded semaphore
        with _LLM_SEMAPHORE:
            # Local vLLM path
            if self.backend == "vllm":
                try:
                    start_time = time.time()
                    out = self._generate_vllm(prompt, system_prompt, temperature, max_tokens)
                    elapsed = time.time() - start_time
                    self.successful_calls += 1
                    out["_latency_sec"] = round(elapsed, 2)
                    out["_model"] = self.model
                    return out
                except requests.exceptions.ConnectionError as ce:
                    err_msg = f"[CONNECTION_ERROR] vLLM connection error at {VLLM_BASE_URL}: {ce}"
                    code = "CONNECTION_ERROR"
                except requests.exceptions.Timeout as te:
                    err_msg = f"[TIMEOUT] vLLM call timed out after {self.timeout}s: {te}"
                    code = "TIMEOUT"
                except Exception as e:
                    err_msg = f"[HTTP_ERROR] vLLM call failed: {e}"
                    code = "HTTP_ERROR"

                self.fallback_calls += 1
                return {
                    "error": err_msg,
                    "error_code": code,
                    "degraded": True,
                    "degraded_reason": err_msg,
                    "role_fit_score": None,
                    "_latency_sec": 0.0,
                    "_model": self.model
                }

            # Local Ollama path
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
            last_code = "UNKNOWN_ERROR"
            raw_text = ""

            for attempt in range(1 + max_retries):
                start_time = time.time()
                try:
                    res = requests.post(self.generate_endpoint, json=payload, timeout=self.timeout)
                    elapsed = time.time() - start_time

                    if res.status_code == 404:
                        last_error = f"[MODEL_NOT_FOUND] Model '{self.model}' not found in Ollama (HTTP 404)"
                        last_code = "MODEL_NOT_FOUND"
                        break  # Retrying won't help if model isn't downloaded
                    elif res.status_code != 200:
                        last_error = f"[HTTP_ERROR] Ollama returned HTTP {res.status_code}: {res.text[:120]}"
                        last_code = "HTTP_ERROR"
                        time.sleep(0.5)
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
                    prompt_eval_count = response_data.get("prompt_eval_count", 0)
                    eval_count = response_data.get("eval_count", 0)
                    eval_duration_sec = round(response_data.get("eval_duration", 0) / 1e9, 3)
                    total_duration_sec = round(response_data.get("total_duration", 0) / 1e9, 3)

                    if isinstance(parsed, dict):
                        self.successful_calls += 1
                        parsed["_latency_sec"] = round(elapsed, 2)
                        parsed["_model"] = self.model
                        parsed["_prompt_tokens"] = prompt_eval_count
                        parsed["_output_tokens"] = eval_count
                        parsed["_eval_duration_sec"] = eval_duration_sec
                        parsed["_total_duration_sec"] = total_duration_sec
                        return parsed
                    elif isinstance(parsed, list):
                        self.successful_calls += 1
                        return {
                            "items": parsed,
                            "_latency_sec": round(elapsed, 2),
                            "_model": self.model,
                            "_prompt_tokens": prompt_eval_count,
                            "_output_tokens": eval_count,
                            "_eval_duration_sec": eval_duration_sec,
                            "_total_duration_sec": total_duration_sec
                        }
                    else:
                        last_error = f"[INVALID_RESPONSE] Output is {type(parsed).__name__}, expected JSON object"
                        last_code = "INVALID_RESPONSE"

                except requests.exceptions.ConnectionError as ce:
                    last_error = f"[CONNECTION_ERROR] Connection refused to Ollama at {self.base_url}"
                    last_code = "CONNECTION_ERROR"
                    time.sleep(0.5)
                except requests.exceptions.Timeout:
                    last_error = f"[TIMEOUT] Ollama inference timed out after {self.timeout}s"
                    last_code = "TIMEOUT"
                except json.JSONDecodeError as jde:
                    last_error = f"[JSON_PARSE_ERROR] Failed to parse model output as JSON: {jde}"
                    last_code = "JSON_PARSE_ERROR"
                    payload["prompt"] += "\nEnsure your response is strictly valid JSON."
                except Exception as exc:
                    last_error = f"[UNKNOWN_ERROR] Unexpected error: {exc}"
                    last_code = "UNKNOWN_ERROR"
                    time.sleep(0.5)

            self.fallback_calls += 1
            logger.error("Ollama inference failed (%s): %s", self.model, last_error)
            return {
                "error": str(last_error),
                "error_code": last_code,
                "degraded": True,
                "degraded_reason": str(last_error),
                "role_fit_score": None,
                "_latency_sec": 0.0,
                "_model": self.model
            }

