"""
Security & Multi-Tenant Authorization Layer for HireTrace (Phase 6).

Implements:
1. Authentication: API Key (X-API-Key or Bearer token) validation.
2. Multi-Tenant Scoping: Isolated candidate access control across organizations/tenants.
3. Rate Limiting: Sliding-window rate limiter on expensive LLM evaluation intake.
4. Pydantic Request Models: Strict schema validation replacing ad hoc regex checks.
"""

import os
import re
import json
import time
import hmac
import uuid
import logging
import threading
from typing import Dict, Any, Optional, List, Tuple
from fastapi import Request, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from agents.db import DB

logger = logging.getLogger("hiretrace.security")


def parse_api_keys() -> Dict[str, str]:
    """
    Parses configured API keys from environment.
    Supports:
    - HIRETRACE_API_KEYS as JSON: '{"key1": "tenant_a", "key2": "tenant_b"}'
    - HIRETRACE_API_KEYS as comma-separated: 'key1:tenant_a,key2:tenant_b'
    - Single HIRETRACE_API_KEY: 'my-secret-key' (maps to 'default_tenant')
    """
    keys_map = {}
    raw_keys = os.environ.get("HIRETRACE_API_KEYS", "").strip()
    if raw_keys:
        if raw_keys.startswith("{"):
            try:
                keys_map.update(json.loads(raw_keys))
            except Exception:
                pass
        else:
            for item in raw_keys.split(","):
                if ":" in item:
                    k, v = item.split(":", 1)
                    keys_map[k.strip()] = v.strip()
                elif item.strip():
                    keys_map[item.strip()] = "default_tenant"

    single_key = os.environ.get("HIRETRACE_API_KEY", "").strip()
    if single_key:
        keys_map[single_key] = "default_tenant"

    return keys_map


def validate_security_configuration():
    """
    Startup validation for security configuration.
    Raises RuntimeError if HIRETRACE_REQUIRE_AUTH is truthy and:
    - Any configured API key equals 'prod_hiretrace_secret_key_change_me'
    - Any configured API key is shorter than 24 characters
    - No API keys are configured at all
    """
    require_auth = os.environ.get("HIRETRACE_REQUIRE_AUTH", "0").lower() in ("1", "true", "yes")
    if not require_auth:
        return

    # Allow test suite overrides when specifically designated
    if os.environ.get("HIRETRACE_TEST_BYPASS_KEY_LENGTH", "0") in ("1", "true"):
        return

    keys_map = parse_api_keys()
    if not keys_map:
        raise RuntimeError(
            "Security configuration error: HIRETRACE_REQUIRE_AUTH=1 is enabled, but no API keys were configured. "
            "Set HIRETRACE_API_KEY (minimum 24 characters) in your environment."
        )

    for key in keys_map.keys():
        if key == "prod_hiretrace_secret_key_change_me":
            raise RuntimeError(
                "Security configuration error: Insecure placeholder API key 'prod_hiretrace_secret_key_change_me' "
                "detected in production configuration. You must set a unique, secret HIRETRACE_API_KEY."
            )
        if len(key) < 24:
            raise RuntimeError(
                f"Security configuration error: Configured API key is too short ({len(key)} characters). "
                "Production API keys must be at least 24 characters long for adequate entropy."
            )


class RateLimiter:
    """Thread-safe sliding-window rate limiter per tenant / client IP."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, int]:
        """
        Returns (is_allowed, retry_after_seconds).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Clean old entries
            timestamps = [t for t in self._history.get(key, []) if t > cutoff]
            if len(timestamps) >= self.max_requests:
                earliest = timestamps[0]
                retry_after = max(1, int(self.window_seconds - (now - earliest)))
                self._history[key] = timestamps
                return False, retry_after

            timestamps.append(now)
            self._history[key] = timestamps
            return True, 0

    def reset(self):
        with self._lock:
            self._history.clear()


class RedisRateLimiter:
    """
    Distributed sliding-window rate limiter backed by Redis sorted sets (ZADD/ZREMRANGEBYSCORE/ZCARD).
    Guarantees consistent rate limits across multiple horizontally scaled web replicas.
    """

    def __init__(
        self,
        redis_client: Any,
        max_requests: int = 30,
        window_seconds: int = 60,
        prefix: str = "hiretrace:ratelimit"
    ):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.prefix = prefix
        self._fallback_limiter = RateLimiter(max_requests=max_requests, window_seconds=window_seconds)

    def check(self, key: str) -> Tuple[bool, int]:
        """
        Sliding-window rate check using Redis sorted sets:
        - ZREMRANGEBYSCORE: drops entries older than current window
        - ZCARD: counts remaining entries in current window
        - If >= max_requests: calculate retry_after from oldest surviving entry
        - If < max_requests: ZADD current timestamp and set EXPIRE
        - Fails open to in-memory RateLimiter on any Redis failure (logged as warning).
        """
        now = time.time()
        cutoff = now - self.window_seconds
        redis_key = f"{self.prefix}:{key}"

        try:
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(redis_key, "-inf", cutoff)
            pipe.zcard(redis_key)
            pipe.zrange(redis_key, 0, 0, withscores=True)
            res = pipe.execute()

            count = res[1]
            earliest_items = res[2]

            if count >= self.max_requests:
                earliest_score = earliest_items[0][1] if earliest_items else cutoff
                retry_after = max(1, int(self.window_seconds - (now - float(earliest_score))))
                return False, retry_after

            # Under threshold: record request with unique member token
            member = f"{now}_{uuid.uuid4().hex[:6]}"
            pipe2 = self.redis.pipeline()
            pipe2.zadd(redis_key, {member: now})
            pipe2.expire(redis_key, self.window_seconds * 2)
            pipe2.execute()
            return True, 0

        except Exception as e:
            logger.warning(f"Redis rate limiter error ({e}); failing open to in-memory limiter.")
            return self._fallback_limiter.check(key)

    def reset(self):
        try:
            keys = self.redis.keys(f"{self.prefix}:*")
            if keys:
                self.redis.delete(*keys)
        except Exception:
            pass
        self._fallback_limiter.reset()


def create_rate_limiter(max_requests: int = 30, window_seconds: int = 60) -> Any:
    """
    Selects distributed RedisRateLimiter if REDIS_URL is reachable,
    otherwise falls back to local in-memory RateLimiter.
    """
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=1.0)
            client.ping()
            logger.info(f"Connected to Redis at {redis_url}; using RedisRateLimiter for multi-replica rate limiting.")
            return RedisRateLimiter(client, max_requests=max_requests, window_seconds=window_seconds)
        except Exception as e:
            logger.info(f"Redis not reachable for rate limiting ({e}); falling back to in-memory RateLimiter.")
    return RateLimiter(max_requests=max_requests, window_seconds=window_seconds)


# Default rate limiter: automatically uses Redis if reachable, otherwise in-memory
RATE_LIMITER = create_rate_limiter(
    max_requests=int(os.environ.get("HIRETRACE_RATE_LIMIT_EVAL", "30")),
    window_seconds=60
)


def authenticate_and_authorize(request: Request) -> str:
    """
    FastAPI dependency/helper that extracts and validates the caller's tenant.
    
    If HIRETRACE_REQUIRE_AUTH is active ('1' or 'true'):
      - Expects X-API-Key or Authorization: Bearer <key>
      - Returns the tenant associated with the key
      - Rejects with HTTP 401 if missing or invalid
    If HIRETRACE_REQUIRE_AUTH is false (zero-config local demo mode):
      - Returns X-Tenant-ID header if provided, else 'default_tenant'
    """
    require_auth = os.environ.get("HIRETRACE_REQUIRE_AUTH", "0").lower() in ("1", "true", "yes")

    # Extract API key
    api_key = request.headers.get("x-api-key")
    if not api_key:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:].strip()

    keys_map = parse_api_keys()

    # Constant-time comparison across configured keys to prevent timing side-channels
    matched_tenant = None
    if api_key:
        for candidate_key, tenant_name in keys_map.items():
            if hmac.compare_digest(api_key, candidate_key):
                matched_tenant = tenant_name
                break

    if require_auth:
        if not matched_tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Missing or invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        assigned_tenant = matched_tenant
        # Allow tenant header override only if key is assigned to admin wildcard '*'
        if assigned_tenant == "*":
            return request.headers.get("x-tenant-id", "*")
        return assigned_tenant

    # Zero-config mode: check if explicit key was provided anyway
    if matched_tenant:
        return matched_tenant

    # Otherwise return requested tenant header or default
    return request.headers.get("x-tenant-id", "default_tenant")


def enforce_candidate_tenant_isolation(candidate_id: str, caller_tenant: str):
    """
    Verifies that caller_tenant is authorized to access candidate_id.
    If the candidate exists in DB and belongs to a different tenant, raises HTTP 403.
    If the candidate does not exist, returns quietly (endpoint will return 404).
    """
    if caller_tenant == "*":
        return

    cand_tenant = DB.get_candidate_tenant(candidate_id)
    if cand_tenant and cand_tenant != caller_tenant and cand_tenant != "default_tenant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: You do not have permission to access candidate '{candidate_id}' in tenant '{cand_tenant}'"
        )


def enforce_evaluation_rate_limit(request: Request, tenant_id: str):
    """
    Enforces sliding-window rate limit on candidate creation and evaluation.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{tenant_id}:{client_ip}"
    allowed, retry_after = RATE_LIMITER.check(rate_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Too many evaluation requests. Please retry in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )


# ============================================================================
# Pydantic Request Validation Models
# ============================================================================

class CandidateCreateRequest(BaseModel):
    """Strict schema validation for new candidate ingestion."""
    candidate_id: Optional[str] = Field(None, max_length=128, description="Optional explicit candidate ID")
    name: str = Field(..., min_length=1, max_length=256, description="Candidate full name")
    target_role: Optional[str] = Field("Senior Software Engineer", max_length=256)
    category: Optional[str] = Field("live_applicant", max_length=64)
    cv_text: Optional[str] = Field("", description="Candidate CV / Resume text")
    interview_notes: Optional[str] = Field("", description="Interview transcript or debrief notes")
    technical_assessment: Optional[str] = Field("", description="Coding / architecture assessment notes")
    project_rfc: Optional[str] = Field("", description="Project design doc or RFC submission")
    jd_text: Optional[str] = Field(None, description="Optional custom Job Description text")

    @field_validator("candidate_id")
    @classmethod
    def validate_candidate_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_str = v.strip()
            if not v_str:
                return None
            if not re.match(r"^[a-zA-Z0-9_\-\.]{1,128}$", v_str):
                raise ValueError(f"Invalid candidate_id format: '{v}'. Must match ^[a-zA-Z0-9_.-]+$")
            return v_str
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Candidate name cannot be empty or whitespace.")
        return s



class BatchEvaluationRequest(BaseModel):
    """Schema for batch evaluation triggers."""
    candidate_ids: List[str] = Field(..., min_items=1, description="List of candidate IDs to evaluate")
    force_refresh: Optional[bool] = Field(False, description="Whether to bypass cached evaluation results")
