"""
Local LLM Client for HireTrace with Multi-Endpoint Load Balancing & Circuit Breaking.

ZERO PAID API DEPENDENCIES. All LLM calls go through local, self-hosted open-weights
models (Ollama or vLLM). No commercial API keys (OpenAI, Anthropic, etc.) are permitted.

Features:
- Multi-endpoint routing: least-loaded and round-robin dispatch across multiple GPU/host replicas.
- Dynamic concurrency: scales semaphore capacity with available inference endpoints.
- Circuit breaker per endpoint: fails fast and cools down unhealthy replicas without blocking the pool.
- Full DEGRADED state propagation: never fabricates a score when backends are offline.
"""

import os
import time
import json
import logging
import threading
from typing import Dict, Any, Optional, Tuple, List
import requests

logger = logging.getLogger("hiretrace.ollama")

# Authoritative configuration defaults (Single source of truth)
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90.0"))
DEFAULT_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")  # "-1" pins forever
DEFAULT_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
DEFAULT_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "0"))  # 0 = let Ollama decide
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()  # "ollama" or "vllm"
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
CONCURRENCY_PER_ENDPOINT = int(os.getenv("CONCURRENCY_PER_ENDPOINT", "1"))

# Parse initial base URLs
def parse_base_urls(urls_str: Optional[str] = None) -> List[str]:
    raw = urls_str or os.getenv("OLLAMA_BASE_URLS") or DEFAULT_OLLAMA_URL
    endpoints = [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
    return endpoints or [DEFAULT_OLLAMA_URL]


INITIAL_ENDPOINTS = parse_base_urls()
MAX_LLM_CONCURRENCY = int(os.getenv("MAX_LLM_CONCURRENCY", str(len(INITIAL_ENDPOINTS) * CONCURRENCY_PER_ENDPOINT)))

# Global bounded semaphore to serialize local GPU inference
_LLM_SEMAPHORE = threading.Semaphore(max(1, MAX_LLM_CONCURRENCY))


def set_max_concurrency(n: int):
    """Dynamically updates the bounded LLM semaphore concurrency limit."""
    global _LLM_SEMAPHORE, MAX_LLM_CONCURRENCY
    MAX_LLM_CONCURRENCY = max(1, n)
    _LLM_SEMAPHORE = threading.Semaphore(MAX_LLM_CONCURRENCY)


class EndpointState:
    """Tracks in-flight load, latency, and circuit breaker status for a single LLM endpoint."""

    def __init__(self, url: str, failure_threshold: int = 3, cooldown_sec: float = 15.0):
        self.url = url.rstrip("/")
        self.in_flight = 0
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_opened_at = 0.0
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.last_latency = 0.0
        self.last_error = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """Returns True if the circuit is closed or if cooldown expired (allowing a probe)."""
        with self._lock:
            if not self.circuit_open:
                return True
            if time.time() - self.circuit_opened_at >= self.cooldown_sec:
                # Half-open: allow a trial request
                return True
            return False

    def record_start(self):
        with self._lock:
            self.in_flight += 1
            self.total_calls += 1

    def record_success(self, latency: float):
        with self._lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.consecutive_failures = 0
            self.circuit_open = False
            self.successful_calls += 1
            self.last_latency = latency
            self.last_error = None

    def record_failure(self, error_msg: str):
        with self._lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.failed_calls += 1
            self.consecutive_failures += 1
            self.last_error = error_msg
            if self.consecutive_failures >= self.failure_threshold:
                if not self.circuit_open:
                    self.circuit_open = True
                    self.circuit_opened_at = time.time()
                    logger.warning(
                        f"Circuit breaker tripped for {self.url} after {self.consecutive_failures} failures. "
                        f"Cooldown: {self.cooldown_sec}s."
                    )

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "url": self.url,
                "in_flight": self.in_flight,
                "consecutive_failures": self.consecutive_failures,
                "circuit_open": self.circuit_open,
                "total_calls": self.total_calls,
                "successful_calls": self.successful_calls,
                "failed_calls": self.failed_calls,
                "last_latency": self.last_latency,
                "last_error": self.last_error
            }


def _extract_json_schema(model: Any) -> Optional[Dict[str, Any]]:
    """Extracts JSON schema from a Pydantic model or returns dict schema."""
    if model is None:
        return None
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()
    if hasattr(model, "schema"):
        return model.schema()
    return None


def _validate_with_model(model: Any, data: Any) -> Any:
    """Validates data against a Pydantic model class."""
    if model is None:
        return data
    if hasattr(model, "model_validate"):
        return model.model_validate(data)
    if hasattr(model, "parse_obj"):
        return model.parse_obj(data)
    return data


class OllamaClient:
    """
    High-throughput Client for querying local Ollama or local vLLM instances.
    Supports multi-endpoint round-robin/least-loaded routing and per-endpoint circuit breaking.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        base_urls: Optional[List[str]] = None,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        mock: bool = False,
        concurrency_per_endpoint: int = CONCURRENCY_PER_ENDPOINT,
        backend: Optional[str] = None
    ):
        if base_urls:
            self.endpoints = [EndpointState(u) for u in base_urls if u.strip()]
        elif base_url:
            self.endpoints = [EndpointState(base_url)]
        else:
            self.endpoints = [EndpointState(u) for u in parse_base_urls()]

        if not self.endpoints:
            self.endpoints = [EndpointState(DEFAULT_OLLAMA_URL)]

        self.base_url = self.endpoints[0].url
        self.model = model
        self.timeout = timeout
        self.concurrency_per_endpoint = max(1, concurrency_per_endpoint)

        # Dynamic semaphore sized to total backend capacity
        self.total_capacity = max(1, len(self.endpoints) * self.concurrency_per_endpoint)
        self.semaphore = threading.Semaphore(self.total_capacity)

        explicit_url_provided = (base_url is not None) or (base_urls is not None)
        is_mock_env = os.getenv("HIRETRACE_OFFLINE_MOCK", "").lower() in ("1", "true", "yes")
        has_mock_url = any("mock" in ep.url.lower() for ep in self.endpoints)

        # Only use mock backend if:
        # 1. mock=True explicitly requested
        # 2. Endpoint URL explicitly specifies mock (e.g. mock://...)
        # 3. Running in mock/CI environment AND caller did not pass an explicit custom non-mock endpoint URL
        if mock or has_mock_url or (is_mock_env and not explicit_url_provided):
            self.backend = "mock"
        else:
            self.backend = (backend or LLM_BACKEND or "ollama").lower()

        self.total_calls = 0
        self.successful_calls = 0
        self.fallback_calls = 0
        self._mock_delegate = None
        self._routing_lock = threading.Lock()
        self._rr_index = 0

    def _get_best_endpoint(self) -> Optional[EndpointState]:
        """Selects the least-loaded healthy endpoint using least-connections and round-robin."""
        with self._routing_lock:
            healthy = [ep for ep in self.endpoints if ep.is_available()]
            if not healthy:
                return None

            healthy.sort(key=lambda ep: ep.in_flight)
            min_in_flight = healthy[0].in_flight
            candidates = [ep for ep in healthy if ep.in_flight == min_in_flight]

            chosen = candidates[self._rr_index % len(candidates)]
            self._rr_index += 1
            return chosen

    def check_health(self) -> Tuple[bool, str]:
        """
        Diagnostic health check across all configured endpoints.
        Returns (is_ready, diagnosis_message).
        """
        if self.backend == "mock":
            return True, "Mock Ollama backend online (Offline / CI mode active)"

        healthy_count = 0
        diagnostics = []

        for ep in self.endpoints:
            try:
                if self.backend == "vllm":
                    res = requests.get(f"{ep.url}/models", timeout=3.0)
                    if res.status_code == 200:
                        healthy_count += 1
                        diagnostics.append(f"{ep.url}: OK")
                    else:
                        diagnostics.append(f"{ep.url}: HTTP {res.status_code}")
                else:
                    res = requests.get(f"{ep.url}/api/tags", timeout=3.0)
                    if res.status_code == 200:
                        data = res.json()
                        installed = [m.get("name") for m in data.get("models", [])]
                        model_base = self.model.split(":")[0]
                        matched = any(self.model in m or m.startswith(self.model) or model_base in m for m in installed)
                        if matched or not installed:
                            healthy_count += 1
                            diagnostics.append(f"{ep.url}: OK")
                        else:
                            diagnostics.append(f"{ep.url}: Model {self.model} not found")
                    else:
                        diagnostics.append(f"{ep.url}: HTTP {res.status_code}")
            except Exception as e:
                diagnostics.append(f"{ep.url}: {type(e).__name__}")

        total = len(self.endpoints)
        if healthy_count > 0:
            return True, f"{healthy_count}/{total} endpoints online ({'; '.join(diagnostics)})"
        return False, f"0/{total} endpoints reachable ({'; '.join(diagnostics)})"

    def is_available(self) -> bool:
        """Checks whether at least one backend endpoint is healthy (cached 5s online, 60s offline)."""
        now = time.time()
        ttl = 60.0 if not getattr(self, "_cached_available", True) else 5.0
        if hasattr(self, "_cached_available") and (now - getattr(self, "_cached_available_time", 0) < ttl):
            return self._cached_available

        ready, msg = self.check_health()
        self._cached_available = ready
        self._cached_available_time = now
        self._last_health_msg = msg
        return ready

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns comprehensive telemetry including per-endpoint routing stats."""
        return {
            "backend": self.backend,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "fallback_calls": self.fallback_calls,
            "configured_endpoints": len(self.endpoints),
            "max_concurrency": self.total_capacity,
            "endpoints": [ep.to_dict() for ep in self.endpoints]
        }

    def _generate_vllm_on_endpoint(
        self,
        endpoint_url: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        schema_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Queries self-hosted vLLM endpoint (OpenAI protocol) with optional schema constraint."""
        url = f"{endpoint_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object", "schema": schema_dict} if schema_dict else {"type": "json_object"},
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
        max_retries: int = 2,
        schema: Optional[Dict[str, Any]] = None,
        schema_model: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Sends prompt to local open-weights backend with load balancing across available endpoints,
        structured output enforcement (JSON schema), and a Pydantic validate-and-repair retry loop.
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
                max_retries=max_retries,
                schema=schema,
                schema_model=schema_model
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

        schema_dict = schema if isinstance(schema, dict) else _extract_json_schema(schema_model)
        current_prompt = prompt

        # Bounded acquisition matching total configured multi-endpoint capacity
        with self.semaphore:
            last_error = None
            last_code = "UNKNOWN_ERROR"

            for attempt in range(1 + max_retries):
                ep = self._get_best_endpoint()
                if not ep:
                    last_error = "All inference endpoints are down or circuit-broken"
                    last_code = "CIRCUITS_OPEN"
                    break

                ep.record_start()
                start_time = time.time()

                try:
                    if self.backend == "vllm":
                        out = self._generate_vllm_on_endpoint(ep.url, current_prompt, system_prompt, temperature, max_tokens, schema_dict)
                        elapsed = time.time() - start_time
                        
                        # Validate with model if schema_model provided
                        if schema_model:
                            try:
                                _validate_with_model(schema_model, out)
                            except Exception as val_err:
                                last_error = f"[SCHEMA_VALIDATION_ERROR] {val_err}"
                                last_code = "SCHEMA_VALIDATION_ERROR"
                                logger.warning("Attempt %d validation failure on vLLM: %s", attempt + 1, val_err)
                                current_prompt = f"{prompt}\n\n[REPAIR: Output failed validation: {val_err}. Please output valid JSON strictly conforming to the requested schema.]"
                                ep.record_failure(last_error)
                                time.sleep(0.3 * (2 ** attempt))
                                continue

                        ep.record_success(elapsed)
                        self.successful_calls += 1
                        out["_latency_sec"] = round(elapsed, 2)
                        out["_model"] = self.model
                        out["_endpoint"] = ep.url
                        return out

                    # Ollama generation path with structured format schema
                    generate_url = f"{ep.url}/api/generate"
                    payload = {
                        "model": self.model,
                        "prompt": current_prompt,
                        "format": schema_dict if schema_dict else "json",
                        "stream": False,
                        # Keeps the model resident between calls. Without this Ollama unloads
                        # after ~5 minutes idle and every evaluation pays a cold load.
                        "keep_alive": DEFAULT_KEEP_ALIVE,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                            # Explicit context window. The Ollama default is small enough that
                            # long dossiers were being silently truncated.
                            "num_ctx": DEFAULT_NUM_CTX,
                            # Deterministic sampling for a scoring product. top_k/top_p are
                            # pinned so two runs of the same dossier give the same verdict.
                            "top_k": 1 if temperature <= 0.01 else 40,
                            "top_p": 1.0 if temperature <= 0.01 else 0.9,
                            "repeat_penalty": 1.05,
                            "num_batch": 512,
                            **({"num_thread": DEFAULT_NUM_THREAD} if DEFAULT_NUM_THREAD > 0 else {}),
                        },
                    }
                    if system_prompt:
                        payload["system"] = system_prompt

                    res = requests.post(generate_url, json=payload, timeout=self.timeout)
                    elapsed = time.time() - start_time

                    if res.status_code == 404:
                        last_error = f"[MODEL_NOT_FOUND] Model '{self.model}' not found at {ep.url} (HTTP 404)"
                        last_code = "MODEL_NOT_FOUND"
                        ep.record_failure(last_error)
                        break

                    if res.status_code != 200:
                        last_error = f"[HTTP_ERROR] {ep.url} returned HTTP {res.status_code}: {res.text[:120]}"
                        last_code = "HTTP_ERROR"
                        ep.record_failure(last_error)
                        time.sleep(0.3)
                        continue

                    response_data = res.json()
                    raw_text = response_data.get("response", "").strip()

                    # Strip markdown blocks if returned
                    if raw_text.startswith("```"):
                        lines = raw_text.splitlines()
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        raw_text = "\n".join(lines).strip()

                    parsed = json.loads(raw_text)

                    # Pydantic Validate-and-Repair check
                    if schema_model:
                        try:
                            _validate_with_model(schema_model, parsed)
                        except Exception as val_err:
                            last_error = f"[SCHEMA_VALIDATION_ERROR] {val_err}"
                            last_code = "SCHEMA_VALIDATION_ERROR"
                            logger.warning("Attempt %d validation failure on Ollama: %s", attempt + 1, val_err)
                            current_prompt = f"{prompt}\n\n[REPAIR: Output failed validation: {val_err}. Please output valid JSON strictly conforming to the requested schema.]"
                            ep.record_failure(last_error)
                            time.sleep(0.3 * (2 ** attempt))
                            continue

                    ep.record_success(elapsed)
                    self.successful_calls += 1

                    prompt_eval_count = response_data.get("prompt_eval_count", 0)
                    eval_count = response_data.get("eval_count", 0)
                    eval_duration_sec = round(response_data.get("eval_duration", 0) / 1e9, 3)
                    total_duration_sec = round(response_data.get("total_duration", 0) / 1e9, 3)

                    if isinstance(parsed, dict):
                        parsed["_latency_sec"] = round(elapsed, 2)
                        parsed["_model"] = self.model
                        parsed["_endpoint"] = ep.url
                        parsed["_prompt_tokens"] = prompt_eval_count
                        parsed["_output_tokens"] = eval_count
                        parsed["_eval_duration_sec"] = eval_duration_sec
                        parsed["_total_duration_sec"] = total_duration_sec
                        parsed["schema_repair_attempts"] = attempt
                        return parsed
                    elif isinstance(parsed, list):
                        return {
                            "items": parsed,
                            "_latency_sec": round(elapsed, 2),
                            "_model": self.model,
                            "_endpoint": ep.url,
                            "_prompt_tokens": prompt_eval_count,
                            "_output_tokens": eval_count,
                            "_eval_duration_sec": eval_duration_sec,
                            "_total_duration_sec": total_duration_sec,
                            "schema_repair_attempts": attempt
                        }
                    else:
                        last_error = f"[INVALID_RESPONSE] Output is {type(parsed).__name__}, expected JSON object"
                        last_code = "INVALID_RESPONSE"

                except requests.exceptions.ConnectionError as ce:
                    last_error = f"[CONNECTION_ERROR] Connection refused to {ep.url}: {ce}"
                    last_code = "CONNECTION_ERROR"
                    ep.record_failure(last_error)
                    time.sleep(0.3)
                except requests.exceptions.Timeout:
                    last_error = f"[TIMEOUT] Inference timed out at {ep.url} after {self.timeout}s"
                    last_code = "TIMEOUT"
                    ep.record_failure(last_error)
                except json.JSONDecodeError as jde:
                    last_error = f"[JSON_PARSE_ERROR] Failed to parse model output as JSON from {ep.url}: {jde}"
                    last_code = "JSON_PARSE_ERROR"
                    current_prompt = f"{prompt}\n\n[REPAIR: The previous output was not valid JSON ({jde}). Output strictly valid JSON.]"
                except Exception as exc:
                    last_error = f"[UNKNOWN_ERROR] Unexpected error at {ep.url}: {exc}"
                    last_code = "UNKNOWN_ERROR"
                    ep.record_failure(last_error)
                    time.sleep(0.3)

            self.fallback_calls += 1
            logger.error("All inference attempts failed: %s (%s)", last_error, last_code)
            return {
                "error": str(last_error),
                "error_code": last_code,
                "degraded": True,
                "degraded_reason": str(last_error),
                "role_fit_score": None,
                "_latency_sec": 0.0,
                "_model": self.model
            }

    def generate(self, prompt: str = "ok", max_tokens: int = 16, temperature: float = 0.0) -> str:
        """Raw generation helper for model probing and boot-time warming."""
        if self.backend == "mock":
            return "ok"
        if not self.endpoints:
            return ""
        ep = self._get_best_endpoint() or self.endpoints[0]
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": DEFAULT_KEEP_ALIVE,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_ctx": DEFAULT_NUM_CTX,
            }
        }
        try:
            res = requests.post(f"{ep.url}/api/generate", json=payload, timeout=min(10.0, self.timeout))
            if res.status_code == 200:
                return res.json().get("response", "").strip()
        except Exception as exc:
            logger.debug("Raw generate error: %s", exc)
        return ""


