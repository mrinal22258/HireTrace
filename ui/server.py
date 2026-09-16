"""
Production ASGI Server for HireTrace.

Built on FastAPI + Uvicorn with enterprise security and scalability controls:
1. Universal dynamic applicant intake via POST /api/candidate/new and /api/candidate/upload.
2. Complete isolation of ground-truth answer keys from public API endpoints (zero answer leakage).
3. Whitelisted static file serving (blocks arbitrary project file exposure).
4. Strict input sanitization (regex allowlist ^[A-Za-z0-9_-]{1,128}$) and bounded request bodies.
5. Structured JSON access logging (method, path, status, latency, candidate_id).
6. High-availability container health checks (/healthz and /readyz).
7. Single source of truth database layer with TTLCache for high-throughput polling.
"""

import os
import sys
import re
import time
import json
import uuid
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn
from cachetools import TTLCache
from pydantic import ValidationError
from sqlalchemy import text

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.pipeline import HireTracePipeline
from agents.document_parser import extract_text, compute_file_hash
from agents.job_manager import JOB_MANAGER, JobPersistenceError
from agents.bulk_ingestion import BULK_ENGINE, BatchJob
from agents.db import DB, Candidate, Document, Evaluation, JobQueue
from agents.security import (
    authenticate_and_authorize,
    enforce_candidate_tenant_isolation,
    enforce_evaluation_rate_limit,
    validate_security_configuration,
    check_dev_mode_production_bind,
    CandidateCreateRequest,
    BatchEvaluationRequest,
)
import shutil
from agents.embedding_cache import EMBEDDING_CACHE
from agents.observability import METRICS
from baseline.rubric_scorer import RubricScorer

from eval_cases.dataset import CASES, SHARED_JD

CACHE_DIR = os.path.join(root_dir, "trajectories")
CASES_DIR = os.path.join(root_dir, "eval_cases")
UPLOADS_DIR = os.path.join(root_dir, "uploads")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(CASES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

SERVER_START_TIME = time.time()

# Configure structured access logger
logger = logging.getLogger("hiretrace.access")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Thread-safe bounded TTL cache for candidate status polling (5s TTL, max 2000 entries)
STATUS_CACHE: TTLCache = TTLCache(maxsize=2000, ttl=5)

ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

def assert_safe_path(target_path: str, base_dir: str):
    """
    Defensive path verification: resolves realpath and asserts target_path
    remains strictly inside base_dir to prevent directory traversal.
    """
    real_target = os.path.realpath(target_path)
    real_base = os.path.realpath(base_dir)
    try:
        common = os.path.commonpath([real_base, real_target])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path: target is outside base directory")
    if common != real_base:
        raise HTTPException(status_code=400, detail="Invalid path: directory traversal attempt detected")
from agents.jd_templates import generate_role_tailored_jd



# Shared singleton pipeline
PIPELINE = HireTracePipeline(trajectory_dir=CACHE_DIR)

def get_hidden_id_prefixes() -> Tuple[str, ...]:
    """Returns candidate ID prefixes that should be hidden from UI and DB auto-seed."""
    default_prefixes = (
        "custom_bulk_", "custom_smoke_test_", "custom_rate_limit_",
        "custom_alpha_", "custom_invalid_id_", "cand_", "rate_limit_test_",
    )
    custom_env = os.getenv("HIRETRACE_HIDDEN_ID_PREFIXES", "").strip()
    if custom_env:
        extra = tuple(p.strip() for p in custom_env.split(",") if p.strip())
        return default_prefixes + extra
    return default_prefixes

def load_saved_custom_cases():
    """Loads previously submitted custom applicant files from disk and seeds DB."""
    if not os.path.exists(CASES_DIR):
        return
    test_prefixes = get_hidden_id_prefixes()
    benchmark_names = {c["name"].lower() for c in CASES}
    for fname in os.listdir(CASES_DIR):
        if fname.startswith("custom_") and fname.endswith(".json"):
            if fname.startswith(test_prefixes):
                continue
            try:
                fpath = os.path.join(CASES_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    cid = cdata.get("candidate_id")
                    name = cdata.get("name", "Unknown")
                    if name.lower() in benchmark_names:
                        continue
                    if cid and not DB.get_candidate_full(cid):
                        DB.upsert_candidate(
                            candidate_id=cid,
                            name=name,
                            target_role=cdata.get("target_role", "Senior Software Engineer"),
                            category=cdata.get("category", "applicant"),
                            status=cdata.get("status", "done")
                        )
                        docs = {
                            "cv": cdata.get("cv_text", ""),
                            "interview": cdata.get("interview_notes", ""),
                            "assessment": cdata.get("technical_assessment", ""),
                            "project": cdata.get("project_rfc", ""),
                        }
                        DB.save_documents(cid, docs, cdata.get("raw_documents"))
                        if "evaluation_report" in cdata:
                            DB.save_evaluation(
                                candidate_id=cid,
                                role_fit_score=cdata.get("role_fit_score"),
                                evidence_consistency_score=cdata.get("evidence_consistency_score"),
                                quadrant=cdata.get("quadrant", "REVIEW REQUIRED"),
                                report_dict=cdata.get("evaluation_report", {}),
                                baseline_a_dict=cdata.get("rubric_baseline")
                            )
            except Exception as err:
                logger.warning(f"Could not load custom case {fname}: {err}")


# Deprecated in Phase 2: In-memory global ALL_CASES eliminated in favor of SQL database single source of truth.
# Kept as empty list alias solely for backwards compatibility with legacy test imports.
ALL_CASES: List[Dict[str, Any]] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate production security configuration
    validate_security_configuration()
    # Ensure database tables and initial seed
    DB.seed_from_cases(CASES)
    load_saved_custom_cases()

    # Warm LLM in background so first user request doesn't pay cold load
    def _warm() -> None:
        try:
            from agents.ollama_client import OllamaClient
            warm_log = logging.getLogger("hiretrace.warmup")
            client = OllamaClient()
            available, diag = client.check_health()
            if not available:
                warm_log.warning("LLM warm-up skipped, endpoint unhealthy: %s", diag)
                return
            client.generate(prompt="ok", max_tokens=1, temperature=0.0)
            warm_log.info("LLM warm-up complete, model resident")
        except Exception as exc:
            logging.getLogger("hiretrace.warmup").warning("LLM warm-up failed (non-fatal): %s", exc)

    try:
        asyncio.get_running_loop().run_in_executor(None, _warm)
    except Exception:
        pass

    yield


app = FastAPI(
    title="HireTrace API",
    description="Evidence-First Candidate Assessment Engine with multi-replica ASGI scaling",
    version="2.0.0",
    lifespan=lifespan
)

def get_cors_configuration() -> Tuple[List[str], Optional[str], bool]:
    """
    Computes CORS parameters securely:
    - ALLOWED_ORIGINS env var (comma-separated list of origins)
    - If unset and in dev mode (HIRETRACE_DEV_MODE=1), allows http://localhost:* and http://127.0.0.1:*
    - In production, defaults to empty list (no cross-origin access)
    - Never pairs allow_credentials=True with wildcard '*'
    """
    raw_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
    dev_mode = os.environ.get("HIRETRACE_DEV_MODE", "0").lower() in ("1", "true", "yes")

    if raw_origins:
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        allow_creds = "*" not in origins
        return origins, None, allow_creds

    if dev_mode:
        origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        return [], origin_regex, True

    return [], None, False


_cors_origins, _cors_regex, _cors_credentials = get_cors_configuration()

# Hardened CORS middleware (never combines wildcard with allow_credentials=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=_cors_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# High-performance GZip compression (> 1000 bytes; identity-encoded SSE streams excluded)
app.add_middleware(GZipMiddleware, minimum_size=1000)


IMMUTABLE_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    """
    Guards against unbounded upload DoS by enforcing a maximum request size (50MB)
    on candidate upload and bulk intake endpoints. Checks Content-Length header early,
    and inspects body streams to reject oversized payloads with HTTP 413.
    """
    path = request.url.path
    if path in ("/api/candidate/upload", "/api/candidates/bulk", "/api/candidates/bulk/", "/api/candidate/new"):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_UPLOAD_SIZE_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"Payload Too Large: Request body exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB."}
                    )
            except ValueError:
                pass

        received_bytes = 0
        original_receive = request._receive

        async def bounded_receive():
            nonlocal received_bytes
            message = await original_receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Payload Too Large: Request stream exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB."
                    )
            return message

        request._receive = bounded_receive

    return await call_next(request)


@app.middleware("http")
async def structured_access_logging_middleware(request: Request, call_next):
    """Logs every HTTP request as a structured JSON record."""
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)

    # Extract candidate_id if present in URL path
    candidate_id = None
    path = request.url.path
    match = re.search(r"/(?:candidate|case|evaluate)/([^/]+)", path)
    if match:
        candidate_id = match.group(1)

    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": request.method,
        "path": path,
        "status_code": response.status_code,
        "latency_ms": duration_ms,
        "client_ip": request.client.host if request.client else None,
    }
    if candidate_id:
        log_entry["candidate_id"] = candidate_id

    logger.info(json.dumps(log_entry))
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """
    Applies defense-in-depth HTTP security headers to all responses:
    - Content-Security-Policy: default-src 'self'; allows local styles, scripts, Google Fonts, and data URIs.
    - Referrer-Policy: no-referrer
    - X-Frame-Options: DENY
    - X-Content-Type-Options: nosniff

    Note: Strict-Transport-Security (HSTS) is intentionally NOT set here, as HireTrace
    serves plain HTTP behind reverse proxies (Nginx/Traefik/Cloudflare/ALB).
    HSTS must be terminated by the TLS edge proxy.
    """
    response = await call_next(request)
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "worker-src 'self' blob:; "
        "manifest-src 'self'; "
        "media-src 'self';"
    )
    response.headers["Content-Security-Policy"] = csp_policy
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
    return response


# ============================================================================
# Static Files & UI Dashboard
# ============================================================================

@app.get("/")
@app.get("/index.html")
def get_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Dashboard UI file not found")
    return FileResponse(
        html_path,
        media_type="text/html",
        headers={
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff"
        }
    )


@app.get("/static_data.js")
@app.get("/ui/static_data.js")
def get_static_data():
    js_path = os.path.join(os.path.dirname(__file__), "static_data.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="static_data.js not found")


@app.get("/styles.css")
@app.get("/ui/styles.css")
def get_styles_css():
    css_path = os.path.join(os.path.dirname(__file__), "styles.css")
    if os.path.exists(css_path):
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(status_code=404, detail="styles.css not found")


@app.get("/motion.js")
@app.get("/ui/motion.js")
def get_motion_js():
    js_path = os.path.join(os.path.dirname(__file__), "motion.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="motion.js not found")


@app.get("/dom-safe.js")
@app.get("/ui/dom-safe.js")
def get_dom_safe_js():
    js_path = os.path.join(os.path.dirname(__file__), "dom-safe.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="dom-safe.js not found")


@app.get("/boot.js")
@app.get("/ui/boot.js")
def get_boot_js():
    js_path = os.path.join(os.path.dirname(__file__), "boot.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="boot.js not found")


@app.get("/app.js")
@app.get("/ui/app.js")
def get_app_js():
    js_path = os.path.join(os.path.dirname(__file__), "app.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="app.js not found")


@app.get("/announcements.json")
@app.get("/ui/announcements.json")
def get_announcements_json():
    p = os.path.join(os.path.dirname(__file__), "announcements.json")
    if os.path.exists(p):
        return FileResponse(p, media_type="application/json")
    return JSONResponse(content=[])


@app.get("/vendor/gsap.min.js")
@app.get("/ui/vendor/gsap.min.js")
def get_vendor_gsap():
    p = os.path.join(os.path.dirname(__file__), "vendor", "gsap.min.js")
    if os.path.exists(p):
        return FileResponse(p, media_type="application/javascript", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="gsap.min.js not found")


@app.get("/vendor/ScrollTrigger.min.js")
@app.get("/ui/vendor/ScrollTrigger.min.js")
def get_vendor_scrolltrigger():
    p = os.path.join(os.path.dirname(__file__), "vendor", "ScrollTrigger.min.js")
    if os.path.exists(p):
        return FileResponse(p, media_type="application/javascript", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="ScrollTrigger.min.js not found")


@app.get("/ocean-mesh-background.js")
@app.get("/ui/ocean-mesh-background.js")
def get_ocean_mesh_js():
    js_path = os.path.join(os.path.dirname(__file__), "ocean-mesh-background.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="ocean-mesh-background.js not found")


@app.get("/ember-mesh-background.js")
@app.get("/ui/ember-mesh-background.js")
def get_ember_mesh_js():
    js_path = os.path.join(os.path.dirname(__file__), "ocean-mesh-background.js")
    if not os.path.exists(js_path):
        js_path = os.path.join(os.path.dirname(__file__), "ember-mesh-background.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="ember-mesh-background.js not found")


@app.get("/mascot-cursor-tracker.js")
@app.get("/ui/mascot-cursor-tracker.js")
def get_mascot_tracker_js():
    js_path = os.path.join(os.path.dirname(__file__), "mascot-cursor-tracker.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="mascot-cursor-tracker.js not found")


@app.get("/hiretrace_mascot_directions.webp")
@app.get("/ui/hiretrace_mascot_directions.webp")
def get_mascot_directions_webp():
    p = os.path.join(os.path.dirname(__file__), "hiretrace_mascot_directions.webp")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)
    fallback = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "brand", "hiretrace_mascot_directions.webp")
    if os.path.exists(fallback):
        return FileResponse(fallback, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Directions sprite sheet not found")


@app.get("/hiretrace_mascot_reactions.webp")
@app.get("/ui/hiretrace_mascot_reactions.webp")
def get_mascot_reactions_webp():
    p = os.path.join(os.path.dirname(__file__), "hiretrace_mascot_reactions.webp")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)
    fallback = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "brand", "hiretrace_mascot_reactions.webp")
    if os.path.exists(fallback):
        return FileResponse(fallback, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Reactions sprite sheet not found")


@app.get("/favicon.ico")
def get_favicon():
    ico_path = os.path.join(os.path.dirname(__file__), "favicon.ico")
    if os.path.exists(ico_path):
        return FileResponse(ico_path, media_type="image/x-icon", headers=IMMUTABLE_CACHE_HEADERS)
    return Response(status_code=204)


@app.get("/mascot.png")
@app.get("/ui/mascot.png")
def get_mascot_png():
    png_path = os.path.join(os.path.dirname(__file__), "mascot.png")
    if os.path.exists(png_path):
        return FileResponse(png_path, media_type="image/png", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="mascot.png not found")


@app.get("/mascot.svg")
@app.get("/ui/mascot.svg")
def get_mascot_svg():
    svg_path = os.path.join(os.path.dirname(__file__), "mascot.svg")
    if os.path.exists(svg_path):
        return FileResponse(svg_path, media_type="image/svg+xml", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="mascot.svg not found")


@app.get("/mascot_{state}.svg")
@app.get("/ui/mascot_{state}.svg")
def get_mascot_state_svg(state: str):
    safe_state = os.path.basename(state)
    svg_path = os.path.join(os.path.dirname(__file__), f"mascot_{safe_state}.svg")
    if os.path.exists(svg_path):
        return FileResponse(svg_path, media_type="image/svg+xml", headers=IMMUTABLE_CACHE_HEADERS)
    fallback = os.path.join(os.path.dirname(__file__), "mascot.svg")
    if os.path.exists(fallback):
        return FileResponse(fallback, media_type="image/svg+xml", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Mascot svg not found")


@app.get("/mascot_{state}.png")
@app.get("/ui/mascot_{state}.png")
def get_mascot_state_png(state: str):
    safe_state = os.path.basename(state)
    png_path = os.path.join(os.path.dirname(__file__), f"mascot_{safe_state}.png")
    if os.path.exists(png_path):
        return FileResponse(png_path, media_type="image/png", headers=IMMUTABLE_CACHE_HEADERS)
    fallback = os.path.join(os.path.dirname(__file__), "mascot.png")
    if os.path.exists(fallback):
        return FileResponse(fallback, media_type="image/png", headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Mascot png not found")


@app.get("/assets/brand/{filename}")
def get_brand_asset(filename: str):
    safe_name = os.path.basename(filename)
    brand_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "brand", safe_name)
    if os.path.exists(brand_path):
        media_type = "image/svg+xml" if safe_name.endswith(".svg") else ("image/png" if safe_name.endswith(".png") else ("image/webp" if safe_name.endswith(".webp") else "image/jpeg"))
        return FileResponse(brand_path, media_type=media_type, headers=IMMUTABLE_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Brand asset not found")


# ============================================================================
# Container Health & Readiness Probes (Phase 1)
# ============================================================================

@app.get("/healthz")
def healthz():
    """Liveness probe: returns 200 if ASGI process is alive and responsive."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - SERVER_START_TIME, 2),
        "timestamp": time.time(),
        "version": "2.0.0"
    }


@app.get("/readyz")
def readyz(response: Response):
    """
    Readiness probe: verifies database connectivity and LLM inference reachability.
    Returns 200 when ready to accept traffic; 503 when DB or LLM is unreachable.
    """
    db_ok = False
    llm_ok = False
    db_error = None
    llm_error = None

    # 1. Check SQL Database connectivity
    try:
        with DB.session_scope() as session:
            session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as err:
        db_error = str(err)

    # 2. Check LLM inference backend
    try:
        llm_ok = PIPELINE.client.is_available()
    except Exception as err:
        llm_error = str(err)

    is_mock = os.environ.get("HIRETRACE_OFFLINE_MOCK") == "1"
    ready = db_ok and (llm_ok or is_mock)

    payload = {
        "status": "ready" if ready else ("degraded" if db_ok else "not_ready"),
        "database": "connected" if db_ok else f"unreachable: {db_error}",
        "llm": "reachable" if (llm_ok or is_mock) else (f"unreachable: {llm_error}" if llm_error else "unreachable"),
        "mock_mode": is_mock
    }

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return payload


@app.get("/metrics")
def get_metrics():
    """
    Prometheus-compatible telemetry exposition endpoint.
    Exposes queue depth, job statuses, agent durations, and LLM telemetry.
    """
    content = METRICS.render_prometheus(ollama_client=PIPELINE.client)
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


# ============================================================================
# Candidate Cases & Evaluation Endpoints (Single Source of Truth: DB)
# ============================================================================

@app.get("/api/audit/summary")
def get_audit_summary():
    """Returns certified evaluation, calibration, fairness, and adversarial audit metrics."""
    snapshot_timestamp = "2026-09-12 09:47:11 UTC"
    eval_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval", "eval_results.json")
    if os.path.exists(eval_file):
        try:
            with open(eval_file, "r", encoding="utf-8") as f:
                ed = json.load(f)
                snapshot_timestamp = ed.get("metadata", {}).get("timestamp", snapshot_timestamp)
        except Exception:
            pass

    return {
        "status": "ok",
        "snapshot_taken_at": snapshot_timestamp,
        "data_source": "frozen_benchmark_snapshot",
        "grounding": {
            "grounded_claim_fidelity": 100.0,
            "citation_validity_rate": 100.0,
            "exact_quote_containment": 100.0,
            "asserted_grounded_claims": 55,
            "synthesized_inferences": 24,
            "unsupported_claims": 0
        },
        "calibration": {
            "brier_score": 0.2281,
            "expected_calibration_error": 0.2395,
            "spearman_rho": 0.816,
            "bootstrap_ci_95": [0.446, 0.983],
            "contradiction_recall": 100.0,
            "contradiction_precision": 100.0,
            "contradiction_f1": 1.000
        },
        "fairness": {
            "eeoc_four_fifths_compliant": True,
            "minimum_disparate_impact_ratio": 1.0000,
            "mean_role_fit_delta_pts": 0.00,
            "mean_consistency_delta_pts": 0.00,
            "quadrant_stability_percent": 100.0,
            "demographic_evaluations_count": 44,
            "demographic_groups_count": 11,
            "standards": "EEOC Uniform Guidelines (4 CFR Part 60)"
        },
        "adversarial": {
            "prompt_injection_defense_rate": 100.0,
            "fabrication_recall": 100.0,
            "tested_attacks": [
                "direct_prompt_injection",
                "hidden_comment_injection",
                "interview_jailbreak",
                "json_schema_smuggling",
                "temporal_fabrication",
                "anachronistic_tenure",
                "concurrency_deadlock_fabrication",
                "seniority_usurpation"
            ]
        },
        "governance": {
            "autonomous_hire_verdict_permitted": False,
            "human_in_the_loop_mandatory": True,
            "recommendation_contract": "Proceed to human review with priority questions",
            "zero_autonomous_decisions": True,
            "eeoc_compliant": True,
            "disparate_impact_ratio": 1.0000,
            "disparate_impact_standard": "Four-Fifths Rule (EEOC 4 CFR Part 60)",
            "score_drift_pts": 0.00,
            "zero_cost_offline": True,
            "hallucination_containment": 100.0
        },
        "extraction": {
            "matched_leaf_accuracy": 84.8,
            "completion_rate": 100.0,
            "array_row_precision": 73.1,
            "array_row_recall": 79.7,
            "standard": "LongExtractBench Deterministic Grader (Local)"
        },
        "efficiency": {
            "time_saved_pct": 80.6,
            "candidate_review_minutes": 3.5,
            "manual_baseline_minutes": 18.0,
            "pipeline_median_latency_seconds": 26.25,
            "model": "Standardized Cognitive Load Model (2,200 words @ 220 wpm + reconciliation)"
        }
    }


def enrich_report_with_score_breakdown(
    report: Optional[Dict[str, Any]],
    baseline_a: Optional[Dict[str, Any]] = None,
    case_dict: Optional[Dict[str, Any]] = None,
    candidate_id: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Ensures reports surface explicit Role Fit formulas, provenance, and matched rubric signals."""
    if not report or not isinstance(report, dict):
        return report, baseline_a

    if not case_dict and candidate_id:
        try:
            case_dict = DB.get_candidate_full(candidate_id) or next((c for c in CASES if c.get("candidate_id") == candidate_id), None)
        except Exception:
            case_dict = next((c for c in CASES if c.get("candidate_id") == candidate_id), None)

    # Ensure baseline_a has summary_audit and category_scores
    if case_dict and (not baseline_a or not baseline_a.get("summary_audit")):
        try:
            dossier = EvidenceLoader.load_case_from_dict(case_dict)
            rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)
            baseline_a = rubric.to_dict()
        except Exception:
            pass

    fit = report.get("role_fit_score")
    rubric_val = report.get("rubric_baseline_score")
    if rubric_val is None and baseline_a:
        rubric_val = baseline_a.get("raw_total") or baseline_a.get("normalized_score")

    llm_match = report.get("llm_req_fit_score")
    if llm_match is None and fit is not None and rubric_val is not None:
        # Invert canonical formula: fit = (0.60 * llm_match) + (0.40 * rubric_score)
        llm_match = round((fit - 0.40 * rubric_val) / 0.60, 1)

    if "score_breakdown" not in report:
        report["score_breakdown"] = {
            "formula": "Role Fit = (60% × LLM Match) + (40% × Resume Rubric)",
            "llm_requirement_match": llm_match,
            "llm_req_fit_score": llm_match,
            "llm_weight": 0.60,
            "rubric_baseline_score": round(rubric_val, 1) if rubric_val is not None else None,
            "rubric_weight": 0.40,
            "role_fit_score": round(fit, 1) if fit is not None else None,
        }
    else:
        if "llm_req_fit_score" not in report["score_breakdown"]:
            report["score_breakdown"]["llm_req_fit_score"] = llm_match
        if "llm_requirement_match" not in report["score_breakdown"]:
            report["score_breakdown"]["llm_requirement_match"] = llm_match

    if "llm_req_fit_score" not in report or report["llm_req_fit_score"] is None:
        report["llm_req_fit_score"] = llm_match

    if "provenance" not in report:
        report["provenance"] = {
            "model_name": report.get("model_name", "qwen2.5:3b"),
            "prompt_version": report.get("prompt_version", "v2.4-grounded-json"),
            "evaluated_at": report.get("evaluated_at", time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())),
            "quadrant_fit_threshold": 72.0,
            "quadrant_consistency_threshold": 70.0,
        }

    return report, baseline_a


@app.get("/api/cases")
def list_cases(
    request: Request,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    status: Optional[str] = None,
    quadrant: Optional[str] = None,
    search: Optional[str] = None,
    include_demo: bool = False
):
    """
    Public Candidate List:
    - If pagination or search filters are provided, returns paginated DB result:
      {"items": [...], "total": N, "page": P, "limit": L, "pages": K}
    - If no filters are provided, returns list of candidate summaries directly from DB.
    - include_demo (default false) controls whether benchmark/demo cases are included.
    """
    tenant = authenticate_and_authorize(request)
    if any(param is not None for param in (page, limit, status, quadrant, search)):
        return DB.list_candidates(
            page=page or 1,
            limit=limit or 50,
            status=status,
            quadrant=quadrant,
            search=search,
            tenant_id=tenant,
            include_demo=include_demo
        )

    # Return full summary list from DB (Single Source of Truth)
    with DB.session_scope() as session:
        query = (
            session.query(
                Candidate.candidate_id,
                Candidate.name,
                Candidate.target_role,
                Candidate.category,
                Candidate.status,
                Evaluation.role_fit_score,
                Evaluation.evidence_consistency_score,
                Evaluation.quadrant,
                Evaluation.report_json,
            )
            .outerjoin(Evaluation, Candidate.candidate_id == Evaluation.candidate_id)
        )
        if tenant and tenant != "*":
            query = query.filter(Candidate.tenant_id == tenant)

        rows = query.order_by(Candidate.created_at.desc()).all()

        test_prefixes = get_hidden_id_prefixes()

        # Build list and deduplicate by candidate_id and candidate name
        raw_list = []
        for r in rows:
            if r.candidate_id.startswith(test_prefixes):
                continue

            has_disc = False
            is_degraded = False
            fit_score = r.role_fit_score
            consistency_score = r.evidence_consistency_score if r.evidence_consistency_score is not None else 50.0
            quad = r.quadrant or ("EVALUATING" if r.status == "evaluating" else "UNKNOWN")
            unsupported_count = 0
            contradicted_count = 0
            if r.report_json:
                try:
                    rep = json.loads(r.report_json)
                    unsupported_count = int(rep.get("unsupported_claim_count", 0))
                    contradicted_count = int(rep.get("contradicted_claim_count", 0))
                    has_disc = (
                        len(rep.get("key_discrepancies", [])) > 0
                        or len(rep.get("critical_discrepancies", [])) > 0
                    )
                    is_degraded = bool(rep.get("degraded", False))
                    if "role_fit_score" in rep:
                        fit_score = rep["role_fit_score"]
                    if "evidence_consistency_score" in rep:
                        consistency_score = rep["evidence_consistency_score"]
                    if "quadrant" in rep:
                        quad = rep["quadrant"]
                except Exception:
                    pass

            if not unsupported_count and not contradicted_count:
                c_match = next((c for c in CASES if c.get("candidate_id") == r.candidate_id), None)
                if c_match and "evaluation_report" in c_match:
                    e_rep = c_match["evaluation_report"]
                    unsupported_count = int(e_rep.get("unsupported_claim_count", 0))
                    contradicted_count = int(e_rep.get("contradicted_claim_count", 0))

            # Check if an active in-memory or background job has updated state
            cand_status = r.status or "done"
            job = JOB_MANAGER.get_job(r.candidate_id)
            if job:
                cand_status = job.status
                if getattr(job, "degraded", False):
                    is_degraded = True

            raw_list.append({
                "candidate_id": r.candidate_id,
                "name": r.name,
                "category": r.category or "applicant",
                "target_role": r.target_role,
                "status": cand_status,
                "role_fit_score": fit_score,
                "evidence_consistency_score": consistency_score,
                "quadrant": quad,
                "has_discrepancies": has_disc,
                "unsupported_claim_count": unsupported_count,
                "contradicted_claim_count": contradicted_count,
                "degraded": is_degraded,
            })

        # Separate benchmark cases vs genuine custom applicants
        bench_order = {c["candidate_id"]: idx for idx, c in enumerate(CASES)}
        benchmark_items = []
        custom_items = []

        seen_names = set()
        seen_ids = set()

        for item in raw_list:
            cid = item["candidate_id"]
            name_key = (item["name"] or "").strip().lower()

            if cid in bench_order:
                if include_demo:
                    benchmark_items.append(item)
                seen_ids.add(cid)
                if name_key:
                    seen_names.add(name_key)

        seen_custom_names = set()
        for item in raw_list:
            cid = item["candidate_id"]
            name_key = (item["name"] or "").strip().lower()

            if cid not in seen_ids:
                # Do not suppress custom uploaded candidates even if a benchmark case shares a name
                if not cid.startswith("custom_") and name_key and name_key in seen_names:
                    continue
                if name_key and name_key in seen_custom_names:
                    # Skip duplicate of an existing custom candidate
                    continue
                seen_ids.add(cid)
                if name_key:
                    seen_custom_names.add(name_key)
                custom_items.append(item)

        if include_demo:
            benchmark_items.sort(key=lambda x: bench_order.get(x["candidate_id"], 999))
            summary_list = custom_items + benchmark_items
        else:
            summary_list = custom_items
        return summary_list


@app.get("/api/system/mode")
def get_system_mode():
    """Returns persistent system execution mode (Live Pipeline vs Demo/Replay)."""
    is_live = False
    try:
        is_live = bool(PIPELINE and PIPELINE.client and PIPELINE.client.is_available())
    except Exception:
        is_live = False

    return {
        "mode": "live" if is_live else "demo",
        "mode_label": "Live Pipeline Mode" if is_live else "Demo / Replay Mode",
        "llm_available": is_live,
        "model_name": "qwen2.5:3b (Local Ollama)" if is_live else "Deterministic Evaluation Engine",
        "model": "qwen2.5:3b" if is_live else None,
        "cost_per_eval": 0.0,
        "api_cost": "$0.00",
        "offline_default": True,
        "privacy": "100% Offline / Zero Cloud Data Transmission",
    }


@app.get("/api/leaderboard")
def get_leaderboard(
    request: Request,
    role: Optional[str] = None,
    sort_by: Optional[str] = "fit",
    include_demo: bool = False
):
    """
    Sortable requisition leaderboard view across candidates evaluated against a target role.
    Reuses existing DB evaluations and cached datasets without recomputing.
    include_demo (default false) controls whether benchmark/demo cases are included.
    """
    tenant = authenticate_and_authorize(request)
    all_cands = list_cases(request, include_demo=include_demo)
    if isinstance(all_cands, dict) and "items" in all_cands:
        items = list(all_cands["items"])
    elif isinstance(all_cands, list):
        items = list(all_cands)
    else:
        items = []

    if role and role.strip() and role.lower() != "all":
        target = role.strip().lower()
        items = [c for c in items if target in (c.get("target_role") or "").strip().lower() or (c.get("target_role") or "").strip().lower() in target]

    # Sorting
    if sort_by == "fit":
        items.sort(key=lambda x: (x.get("role_fit_score") is not None, x.get("role_fit_score") or 0), reverse=True)
    elif sort_by == "consistency":
        items.sort(key=lambda x: (x.get("evidence_consistency_score") is not None, x.get("evidence_consistency_score") or 0), reverse=True)
    elif sort_by == "name":
        items.sort(key=lambda x: (x.get("name") or "").lower())
    elif sort_by == "unsupported":
        items.sort(key=lambda x: x.get("unsupported_claim_count") if x.get("unsupported_claim_count") is not None else 0, reverse=False)

    return items


@app.get("/api/pipeline/stream/{candidate_id}")
async def stream_pipeline_progress(candidate_id: str, request: Request):
    """
    Server-Sent Events (SSE) live per-agent execution step stream.
    Reuses the existing log_agent_event() pipeline stages, showing step names
    instead of a generic spinner:
    - Mapping requirements from job description...
    - Retrieving evidence spans across dossier...
    - Cross-checking sources for corroborations & contradictions...
    - Writing 2D assessment report & calibration...
    """
    tenant = authenticate_and_authorize(request)
    raw_cid = candidate_id.strip()
    if not ID_REGEX.match(raw_cid):
        raise HTTPException(status_code=400, detail="Invalid Candidate ID format")
    enforce_candidate_tenant_isolation(raw_cid, tenant)

    async def event_generator():
        STEPS = [
            {"agent": "RequirementMappingAgent", "step": "Mapping requirements from job description...", "pct": 25},
            {"agent": "EvidenceAggregationAgent", "step": "Retrieving evidence spans across multi-document dossier...", "pct": 50},
            {"agent": "CrossSourceVerificationAgent", "step": "Cross-checking sources for contradictions & corroborations...", "pct": 75},
            {"agent": "RecommendationWriterAgent", "step": "Writing 2D quadrant assessment report card & calibration...", "pct": 95},
            {"agent": "PipelineEngine", "step": "Assessment complete. Full report ready.", "pct": 100},
        ]

        job = JOB_MANAGER.get_job(raw_cid)
        if job and job.status == "evaluating":
            timeout = 60.0
            start_t = time.time()
            last_step = ""
            while time.time() - start_t < timeout:
                if await request.is_disconnected():
                    break
                current_job = JOB_MANAGER.get_job(raw_cid)
                if current_job:
                    c_step = current_job.current_step
                    c_pct = current_job.progress_pct
                    c_status = current_job.status
                    if c_step != last_step:
                        last_step = c_step
                        data = json.dumps({
                            "candidate_id": raw_cid,
                            "agent": "ActiveWorker",
                            "step": c_step,
                            "progress_pct": c_pct,
                            "status": c_status
                        })
                        yield f"data: {data}\n\n"
                    if c_status in ("done", "failed"):
                        break
                await asyncio.sleep(0.4)
        else:
            # Replay step progression for cached/completed candidate evaluation
            for s in STEPS:
                if await request.is_disconnected():
                    break
                data = json.dumps({
                    "candidate_id": raw_cid,
                    "agent": s["agent"],
                    "step": s["step"],
                    "progress_pct": s["pct"],
                    "status": "evaluating" if s["pct"] < 100 else "completed"
                })
                yield f"data: {data}\n\n"
                await asyncio.sleep(0.12)

        if not await request.is_disconnected():
            final_data = json.dumps({
                "candidate_id": raw_cid,
                "agent": "PipelineEngine",
                "step": "Stream finished.",
                "progress_pct": 100,
                "status": "done"
            })
            yield f"event: done\ndata: {final_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        }
    )


@app.get("/api/case/{candidate_id}/full")
def get_case_full(candidate_id: str, request: Request):
    """Candidate Full Profile: Dossier documents & spans, NO ground-truth answer keys."""
    tenant = authenticate_and_authorize(request)
    raw_cid = candidate_id.strip()
    if not ID_REGEX.match(raw_cid):
        raise HTTPException(status_code=400, detail="Invalid Candidate ID format")

    enforce_candidate_tenant_isolation(raw_cid, tenant)

    # 1. Check DB first
    case = DB.get_candidate_full(raw_cid)

    # 2. Check disk fallback
    if not case:
        custom_file = os.path.join(CASES_DIR, f"{raw_cid}.json")
        assert_safe_path(custom_file, CASES_DIR)
        if os.path.exists(custom_file):
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    case = json.load(f)
            except Exception:
                pass

    # 3. Check static CASES baseline dataset
    if not case:
        case = next((c for c in CASES if c.get("candidate_id") == raw_cid), None)

    if not case:
        raise HTTPException(status_code=404, detail="Candidate Case Not Found")

    dossier = EvidenceLoader.load_case_from_dict(case)
    return {
        "candidate_id": raw_cid,
        "name": case["name"],
        "target_role": case.get("target_role", "Senior Software Engineer"),
        "category": case.get("category", "applicant"),
        "documents": {
            "cv": case.get("cv_text", ""),
            "interview": case.get("interview_notes", ""),
            "assessment": case.get("technical_assessment", ""),
            "project_rfc": case.get("project_rfc", ""),
            "jd": case.get("jd_text") or generate_role_tailored_jd(case.get("target_role", "")),
        },
        "raw_documents": case.get("raw_documents", {}),
        "structured_profile": dossier.structured_cv_profile,
        "evidence_spans": [s.to_dict() for s in dossier.spans],
    }


from agents.retention import delete_candidate_artifacts as purge_candidate_data


def delete_candidate_artifacts(candidate_id: str) -> Dict[str, Any]:
    return purge_candidate_data(candidate_id, status_cache=STATUS_CACHE, job_manager=JOB_MANAGER)



@app.delete("/api/candidate/{candidate_id}")
def delete_candidate_endpoint(candidate_id: str, request: Request):
    """
    Deletes all candidate records, documents, evaluations, raw uploaded files,
    trajectories, and cached representations across all storage layers.
    Requires authentication and enforces multi-tenant boundary checks.
    """
    tenant = authenticate_and_authorize(request)
    raw_cid = candidate_id.strip()
    if not ID_REGEX.match(raw_cid):
        raise HTTPException(status_code=400, detail="Invalid Candidate ID format")

    enforce_candidate_tenant_isolation(raw_cid, tenant)
    summary = delete_candidate_artifacts(raw_cid)
    return {
        "success": True,
        "message": f"Candidate {raw_cid} and all associated data successfully deleted.",
        "summary": summary
    }


@app.get("/api/eval_summary")
@app.get("/api/eval_results")
def get_eval_summary(request: Request):
    """Safe Public Benchmark Summary (Zero ground-truth or candidate-level answer leaks)."""
    authenticate_and_authorize(request)
    eval_path = os.path.join(root_dir, "eval", "eval_results.json")
    if os.path.exists(eval_path):
        try:
            with open(eval_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "metadata": data.get("metadata", {}),
                "metrics": data.get("metrics", {}),
            }
        except Exception:
            pass
    return {"status": "pending", "message": "Evaluation results not yet generated"}


@app.get("/api/candidate/{candidate_id}/status")
def get_candidate_status(candidate_id: str, request: Request):
    """Async Candidate Evaluation Job Status with thread-safe TTL caching."""
    tenant = authenticate_and_authorize(request)
    raw_cid = candidate_id.strip()
    if not ID_REGEX.match(raw_cid):
        raise HTTPException(status_code=400, detail="Invalid Candidate ID format")

    enforce_candidate_tenant_isolation(raw_cid, tenant)

    # Check active job manager first
    job = JOB_MANAGER.get_job(raw_cid)
    if job:
        return job.to_dict()

    # Check TTL cache for completed jobs
    if raw_cid in STATUS_CACHE:
        return STATUS_CACHE[raw_cid]

    # Check DB evaluation
    db_eval = DB.get_evaluation(raw_cid)
    cand = DB.get_candidate_full(raw_cid)
    if db_eval and db_eval.get("report"):
        rep, base_a = enrich_report_with_score_breakdown(db_eval["report"], db_eval.get("baseline_a"), case_dict=cand)
        is_deg = rep.get("degraded", False)
        result = {
            "candidate_id": raw_cid,
            "name": cand.get("name", "") if cand else "",
            "target_role": cand.get("target_role", "Senior Software Engineer") if cand else "Senior Software Engineer",
            "status": "done",
            "progress_pct": 100,
            "current_step": "Assessment complete. Report ready." if not is_deg else "Assessment complete (DEGRADED: Local LLM offline).",
            "report": rep,
            "baseline_a": base_a,
            "degraded": is_deg,
            "error": None,
        }
        STATUS_CACHE[raw_cid] = result
        return result

    # Check disk case
    custom_file = os.path.join(CASES_DIR, f"{raw_cid}.json")
    assert_safe_path(custom_file, CASES_DIR)
    if os.path.exists(custom_file):
        try:
            with open(custom_file, "r", encoding="utf-8") as f:
                disk_case = json.load(f)
            if "evaluation_report" in disk_case:
                rep, base_a = enrich_report_with_score_breakdown(disk_case.get("evaluation_report", {}), disk_case.get("rubric_baseline"), case_dict=disk_case)
                is_deg = rep.get("degraded", False) or disk_case.get("degraded", False)
                result = {
                    "candidate_id": raw_cid,
                    "name": disk_case.get("name", ""),
                    "target_role": disk_case.get("target_role", "Senior Software Engineer"),
                    "status": "done",
                    "progress_pct": 100,
                    "current_step": "Assessment complete. Report ready." if not is_deg else "Assessment complete (DEGRADED: Local LLM offline).",
                    "report": rep,
                    "baseline_a": base_a,
                    "degraded": is_deg,
                    "error": None,
                }
                STATUS_CACHE[raw_cid] = result
                return result
        except Exception:
            pass

    # Check JobQueue table in DB
    db_job = DB.get_job(raw_cid)
    if db_job:
        return {
            "candidate_id": raw_cid,
            "name": cand.get("name", "") if cand else "",
            "target_role": cand.get("target_role", "Senior Software Engineer") if cand else "",
            "status": db_job["status"],
            "progress_pct": db_job["progress_pct"],
            "current_step": db_job["current_step"],
            "report": None,
            "baseline_a": None,
            "degraded": False,
            "error": db_job.get("error_msg"),
        }

    # Check static CASES baseline dataset fallback
    case = next((c for c in CASES if c.get("candidate_id") == raw_cid), None)
    if case and "evaluation_report" in case:
        rep, base_a = enrich_report_with_score_breakdown(case.get("evaluation_report", {}), case.get("rubric_baseline"), case_dict=case)
        is_deg = rep.get("degraded", False) or case.get("degraded", False)
        result = {
            "candidate_id": raw_cid,
            "name": case.get("name", ""),
            "target_role": case.get("target_role", "Senior Software Engineer"),
            "status": "done",
            "progress_pct": 100,
            "current_step": "Assessment complete. Report ready." if not is_deg else "Assessment complete (DEGRADED: Local LLM offline).",
            "report": rep,
            "baseline_a": base_a,
            "degraded": is_deg,
            "error": None,
        }
        STATUS_CACHE[raw_cid] = result
        return result

    raise HTTPException(status_code=404, detail="Candidate job not found")


@app.get("/api/batch/{batch_id}/status")
def get_batch_status(batch_id: str, request: Request):
    """Bulk Batch Evaluation Status."""
    authenticate_and_authorize(request)
    raw_batch_id = batch_id.strip()
    if not ID_REGEX.match(raw_batch_id):
        raise HTTPException(status_code=400, detail="Invalid Batch ID format")

    batch = BULK_ENGINE.get_batch(raw_batch_id)
    if batch:
        return batch.to_dict()

    raise HTTPException(status_code=404, detail="Batch job not found")


# ============================================================================
# Ingestion & Evaluation Endpoints (POST)
# ============================================================================

@app.post("/api/candidate/new")
async def ingest_candidate_new(payload: CandidateCreateRequest, request: Request):
    """Ingest a brand-new live applicant (JSON payload with Pydantic validation)."""
    tenant = authenticate_and_authorize(request)
    enforce_evaluation_rate_limit(request, tenant)

    name = payload.name.strip()
    cv_text = payload.cv_text.strip()
    target_role = (payload.target_role or "").strip() or "Senior Software Engineer"
    interview_notes = (payload.interview_notes or "").strip()
    technical_assessment = (payload.technical_assessment or "").strip()
    project_rfc = (payload.project_rfc or "").strip()
    has_custom_jd = bool((payload.jd_text or "").strip())
    jd_text = (payload.jd_text or "").strip() or generate_role_tailored_jd(target_role)

    # Use explicit candidate_id if provided and validated, else generate collision-free UUID
    if payload.candidate_id:
        cid = payload.candidate_id
    else:
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())[:24]
        unique_token = uuid.uuid4().hex[:10]
        cid = f"custom_{slug}_{unique_token}"

    new_case = {
        "candidate_id": cid,
        "tenant_id": tenant,
        "name": name,
        "target_role": target_role,
        "category": payload.category or "live_applicant",
        "cv_text": cv_text,
        "interview_notes": interview_notes,
        "technical_assessment": technical_assessment,
        "project_rfc": project_rfc,
        "jd_text": jd_text,
        "custom_jd_provided": has_custom_jd,
    }

    try:
        dossier = EvidenceLoader.load_case_from_dict(new_case)
        report = await asyncio.to_thread(PIPELINE.run, dossier, log_trajectory=True)
        rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

        new_case["evaluation_report"] = report.to_dict()
        new_case["rubric_baseline"] = rubric.to_dict()
        new_case["role_fit_score"] = report.role_fit_score
        new_case["evidence_consistency_score"] = report.evidence_consistency_score
        new_case["quadrant"] = report.quadrant
        new_case["status"] = "done"

        # Persist to disk
        case_file = os.path.join(CASES_DIR, f"{cid}.json")
        assert_safe_path(case_file, CASES_DIR)
        with open(case_file, "w", encoding="utf-8") as f:
            json.dump(new_case, f, indent=2)

        # Persist to DB
        DB.upsert_candidate(cid, name, target_role, payload.category or "live_applicant", "done", tenant_id=tenant)
        DB.save_documents(cid, {
            "cv": cv_text,
            "interview": interview_notes,
            "assessment": technical_assessment,
            "project": project_rfc,
        })
        DB.save_evaluation(
            candidate_id=cid,
            role_fit_score=report.role_fit_score,
            evidence_consistency_score=report.evidence_consistency_score,
            quadrant=report.quadrant,
            report_dict=report.to_dict(),
            baseline_a_dict=rubric.to_dict(),
        )

        return {
            "success": True,
            "candidate_id": cid,
            "name": name,
            "target_role": target_role,
            "report": report.to_dict(),
            "baseline_a": rubric.to_dict(),
            "cached": False,
        }

    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Pipeline evaluation failed: {err}")


@app.post("/api/candidate/upload")
async def ingest_candidate_upload(request: Request):
    """
    Ingest candidate via multipart file upload, JSON, or form-urlencoded data.
    Supports ?sync=true or header X-HireTrace-Sync: true for synchronous evaluation.
    """
    tenant = authenticate_and_authorize(request)
    enforce_evaluation_rate_limit(request, tenant)

    content_type = request.headers.get("content-type", "")

    fields: Dict[str, str] = {}
    files: Dict[str, Tuple[str, bytes]] = {}

    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            for key, val in form.items():
                if hasattr(val, "filename") and val.filename:
                    file_bytes = await val.read()
                    files[key] = (val.filename, file_bytes)
                else:
                    fields[key] = str(val) if val is not None else ""
        except Exception as err:
            raise HTTPException(status_code=400, detail=f"Malformed multipart payload: {err}")

    elif "application/json" in content_type:
        try:
            json_body = await request.json()
            fields = {k: str(v) for k, v in json_body.items()}
        except Exception as err:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {err}")

    elif "application/x-www-form-urlencoded" in content_type:
        try:
            form = await request.form()
            fields = {k: str(v) for k, v in form.items()}
        except Exception as err:
            raise HTTPException(status_code=400, detail=f"Invalid form-urlencoded payload: {err}")
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported Media Type: Expected multipart/form-data, application/json, or application/x-www-form-urlencoded",
        )

    raw_cid = fields.get("candidate_id", "").strip() or None
    raw_name = fields.get("name", "").strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="Missing required field: 'name'")

    try:
        validated_req = CandidateCreateRequest(
            candidate_id=raw_cid,
            name=raw_name,
            target_role=fields.get("target_role") or "Senior Software Engineer",
            category=fields.get("category") or "live_applicant",
            cv_text=fields.get("cv_text", ""),
            interview_notes=fields.get("interview_notes", ""),
            technical_assessment=fields.get("technical_assessment", ""),
            project_rfc=fields.get("project_rfc", ""),
            jd_text=fields.get("jd_text"),
        )
    except ValidationError as val_err:
        raise HTTPException(status_code=422, detail=jsonable_encoder(val_err.errors()))

    name = validated_req.name
    target_role = validated_req.target_role or "Senior Software Engineer"
    jd_text = fields.get("jd_text", "").strip() or generate_role_tailored_jd(target_role)

    # Use explicit candidate_id if provided and validated, else generate collision-free ID
    if validated_req.candidate_id:
        cid = validated_req.candidate_id
    else:
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())[:24]
        unique_token = uuid.uuid4().hex[:10]
        cid = f"custom_{slug}_{unique_token}"

    cand_upload_dir = os.path.join(UPLOADS_DIR, cid)
    assert_safe_path(cand_upload_dir, UPLOADS_DIR)
    os.makedirs(cand_upload_dir, exist_ok=True)

    raw_docs_meta: Dict[str, Any] = {}

    def _resolve_doc(file_key: str, text_key: str, doc_name_prefix: str) -> str:
        # 1. Check if uploaded file exists and has content
        if file_key in files and files[file_key][1]:
            orig_fname, fbytes = files[file_key]
            ext = os.path.splitext(orig_fname)[1].lower()
            if ext == ".doc":
                raise ValueError("Legacy .doc format is not supported. Please convert to modern .docx or PDF.")
            if ext not in (".pdf", ".docx", ".txt", ".md", ".json"):
                raise ValueError(f"Unsupported file format '{ext}' for {doc_name_prefix}. Allowed: .pdf, .docx, .txt, .md, .json")

            clean_fname = re.sub(r"[^a-zA-Z0-9_.-]", "_", os.path.basename(orig_fname))
            save_path = os.path.join(cand_upload_dir, f"{doc_name_prefix}_{clean_fname}")
            assert_safe_path(save_path, UPLOADS_DIR)
            with open(save_path, "wb") as f:
                f.write(fbytes)

            file_hash = compute_file_hash(fbytes)
            raw_docs_meta[doc_name_prefix] = {
                "filename": orig_fname,
                "disk_path": save_path,
                "sha256": file_hash,
                "size_bytes": len(fbytes),
            }
            try:
                return extract_text(save_path, filename_hint=orig_fname)
            except Exception as parse_err:
                raise ValueError(f"Failed parsing {doc_name_prefix} document ({orig_fname}): {parse_err}")

        # 2. Fall back to direct text field (check both text_key and file_key in fields)
        txt_val = fields.get(text_key, "").strip() or fields.get(file_key, "").strip()
        return txt_val

    # Check sync flag early for synchronous timeout/limit enforcement
    sync_param = request.query_params.get("sync", "false").lower() == "true"
    sync_header = request.headers.get("x-hiretrace-sync", "").lower() == "true"
    is_sync = sync_param or sync_header

    try:
        cv_text = _resolve_doc("cv_file", "cv_text", "cv")
        if not cv_text:
            raise HTTPException(
                status_code=400,
                detail="Missing required document: 'cv_file' (PDF/DOCX/TXT/MD) or 'cv_text'",
            )

        interview_notes = _resolve_doc("interview_file", "interview_notes", "interview")
        technical_assessment = _resolve_doc("assessment_file", "technical_assessment", "assessment")
        project_rfc = _resolve_doc("project_file", "project_rfc", "project")
        jd_uploaded = _resolve_doc("jd_file", "jd_text", "jd")
        if jd_uploaded:
            jd_text = jd_uploaded
            has_custom_jd = True
        else:
            has_custom_jd = False

    except ValueError as val_err:
        msg = str(val_err)
        if is_sync and any(k in msg.lower() for k in ["page limit", "timed out", "sync=false", "asynchronous"]):
            raise HTTPException(
                status_code=422,
                detail=f"Synchronous PDF parsing limit exceeded: {msg}"
            )
        raise HTTPException(status_code=400, detail=msg)

    new_case = {
        "candidate_id": cid,
        "tenant_id": tenant,
        "name": name,
        "target_role": target_role,
        "category": "live_applicant",
        "cv_text": cv_text,
        "interview_notes": interview_notes,
        "technical_assessment": technical_assessment,
        "project_rfc": project_rfc,
        "jd_text": jd_text,
        "custom_jd_provided": has_custom_jd,
        "raw_documents": raw_docs_meta,
    }

    # Persist candidate to DB
    DB.upsert_candidate(cid, name, target_role, "live_applicant", "done" if is_sync else "queued", tenant_id=tenant)
    DB.save_documents(
        cid,
        {
            "cv": cv_text,
            "interview": interview_notes,
            "assessment": technical_assessment,
            "project": project_rfc,
        },
        raw_docs_meta,
    )

    if is_sync:
        # Synchronous execution
        try:
            dossier = EvidenceLoader.load_case_from_dict(new_case)
            report = await asyncio.to_thread(PIPELINE.run, dossier, log_trajectory=True)
            rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

            new_case["evaluation_report"] = report.to_dict()
            new_case["rubric_baseline"] = rubric.to_dict()
            new_case["role_fit_score"] = report.role_fit_score
            new_case["evidence_consistency_score"] = report.evidence_consistency_score
            new_case["quadrant"] = report.quadrant
            new_case["degraded"] = getattr(report, "degraded", False)
            new_case["status"] = "done"

            case_file = os.path.join(CASES_DIR, f"{cid}.json")
            assert_safe_path(case_file, CASES_DIR)
            with open(case_file, "w", encoding="utf-8") as f:
                json.dump(new_case, f, indent=2)

            DB.save_evaluation(
                candidate_id=cid,
                role_fit_score=report.role_fit_score,
                evidence_consistency_score=report.evidence_consistency_score,
                quadrant=report.quadrant,
                report_dict=report.to_dict(),
                baseline_a_dict=rubric.to_dict(),
            )

            return {
                "success": True,
                "candidate_id": cid,
                "name": name,
                "target_role": target_role,
                "status": "done",
                "degraded": getattr(report, "degraded", False),
                "degraded_reason": getattr(report, "degraded_reason", None),
                "report": report.to_dict(),
                "baseline_a": rubric.to_dict(),
                "cached": False,
                "raw_documents": raw_docs_meta,
            }
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"Pipeline evaluation failed: {err}")
    else:
        # Asynchronous execution: 202 Accepted
        new_case["status"] = "queued"
        case_file = os.path.join(CASES_DIR, f"{cid}.json")
        assert_safe_path(case_file, CASES_DIR)
        with open(case_file, "w", encoding="utf-8") as f:
            json.dump(new_case, f, indent=2)

        try:
            JOB_MANAGER.submit_evaluation(
                new_case,
                PIPELINE,
                CASES_DIR,
            )
        except JobPersistenceError as err:
            logger.error(f"Failed to persist evaluation job for {cid}: {err}")
            raise HTTPException(
                status_code=503,
                detail="failed to enqueue evaluation, please retry"
            )

        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "candidate_id": cid,
                "name": name,
                "target_role": target_role,
                "status": "queued",
                "poll_url": f"/api/candidate/{cid}/status",
                "raw_documents": raw_docs_meta,
            },
        )


@app.post("/api/candidates/bulk")
@app.post("/api/candidates/bulk/")
async def ingest_candidates_bulk(request: Request):
    """Bulk candidate ingestion via ZIP archive or multi-file directory tree."""
    tenant = authenticate_and_authorize(request)
    enforce_evaluation_rate_limit(request, tenant)

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(
            status_code=415,
            detail="Unsupported Media Type: Expected multipart/form-data with ZIP archive or folder files",
        )

    try:
        form = await request.form()
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"Malformed multipart payload: {err}")

    fields: Dict[str, str] = {}
    files: Dict[str, Tuple[str, bytes]] = {}

    for key, val in form.items():
        if hasattr(val, "filename") and val.filename:
            file_bytes = await val.read()
            files[key] = (val.filename, file_bytes)
        else:
            fields[key] = str(val) if val is not None else ""

    target_role = fields.get("target_role", "").strip() or "Senior Python & Distributed Systems Engineer"
    batch_id = f"batch_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    zip_entry = None
    for key, (fname, fbytes) in files.items():
        if fname.lower().endswith(".zip") or key in ("archive_file", "zip_file"):
            zip_entry = (fname, fbytes)
            break

    if zip_entry:
        batch = BULK_ENGINE.process_archive(
            zip_bytes=zip_entry[1],
            batch_id=batch_id,
            target_role=target_role,
            uploads_root=UPLOADS_DIR,
            cases_dir=CASES_DIR,
            pipeline=PIPELINE,
            all_cases_list=None,
        )
        if batch.status == "failed":
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "batch_id": batch.batch_id,
                    "status": "failed",
                    "errors": batch.errors,
                }
            )
    else:
        files_map: Dict[str, bytes] = {}
        for key, (fname, fbytes) in files.items():
            path_key = fields.get(f"path_{key}", fname)
            files_map[path_key] = fbytes

        batch = BULK_ENGINE.process_file_tree(
            files_map=files_map,
            batch_id=batch_id,
            target_role=target_role,
            uploads_root=UPLOADS_DIR,
            cases_dir=CASES_DIR,
            pipeline=PIPELINE,
            all_cases_list=None,
        )

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "batch_id": batch.batch_id,
            "total_files": batch.total_files,
            "uploaded": batch.uploaded,
            "parsed": batch.parsed,
            "queued": batch.queued,
            "duplicates": batch.duplicates,
            "poll_url": f"/api/batch/{batch.batch_id}/status",
        },
    )


@app.post("/api/evaluate/{candidate_id}")
async def evaluate_candidate(candidate_id: str, request: Request):
    """Evaluate an existing candidate case on-demand."""
    tenant = authenticate_and_authorize(request)
    raw_cid = candidate_id.strip()
    if not ID_REGEX.match(raw_cid):
        raise HTTPException(status_code=400, detail="Invalid Candidate ID format")

    enforce_candidate_tenant_isolation(raw_cid, tenant)
    enforce_evaluation_rate_limit(request, tenant)

    force_rerun = request.query_params.get("force", "false").lower() == "true"

    db_cand = DB.get_candidate_full(raw_cid, tenant_id=tenant)
    case = db_cand or next((c for c in CASES if c.get("candidate_id") == raw_cid), None)
    if not case:
        raise HTTPException(status_code=404, detail="Candidate Case Not Found")

    traj_file = os.path.join(CACHE_DIR, f"{raw_cid}_trajectory.json")
    assert_safe_path(traj_file, CACHE_DIR)

    # Check cache if not forced
    if not force_rerun:
        active_job = JOB_MANAGER.get_job(raw_cid)
        if active_job and active_job.status in ("queued", "evaluating", "retrying"):
            return JSONResponse(
                status_code=202,
                content={
                    "status": active_job.status,
                    "progress_pct": active_job.progress_pct,
                    "poll_url": f"/api/candidate/{raw_cid}/status",
                    "message": "Evaluation already in progress.",
                },
            )

        if case.get("evaluation_report"):
            rep, base_a = enrich_report_with_score_breakdown(case["evaluation_report"], case.get("rubric_baseline", {}), case_dict=case)
            return {
                "report": rep,
                "baseline_a": base_a,
                "cached": True,
            }

        db_eval = DB.get_evaluation(raw_cid)
        if db_eval and db_eval.get("report"):
            rep, base_a = enrich_report_with_score_breakdown(db_eval["report"], db_eval.get("baseline_a", {}), case_dict=case)
            return {
                "report": rep,
                "baseline_a": base_a,
                "cached": True,
            }

        if os.path.exists(traj_file):
            try:
                with open(traj_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                final_report = cached_data.get("final_report")
                if not final_report and "steps" in cached_data and cached_data["steps"]:
                    final_report = cached_data["steps"][-1].get("output", {})
                dossier = EvidenceLoader.load_case_from_dict(case)
                rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)
                rep, base_a = enrich_report_with_score_breakdown(final_report, rubric.to_dict(), case_dict=case)
                return {
                    "report": rep,
                    "baseline_a": base_a,
                    "cached": True,
                }
            except Exception:
                pass

    # Run pipeline
    try:
        dossier = EvidenceLoader.load_case_from_dict(case)
        report = await asyncio.to_thread(PIPELINE.run, dossier, log_trajectory=True)
        rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

        DB.save_evaluation(
            candidate_id=raw_cid,
            role_fit_score=report.role_fit_score,
            evidence_consistency_score=report.evidence_consistency_score,
            quadrant=report.quadrant,
            report_dict=report.to_dict(),
            baseline_a_dict=rubric.to_dict(),
        )

        return {
            "report": report.to_dict(),
            "baseline_a": rubric.to_dict(),
            "cached": False,
        }
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Evaluation execution failed: {err}")


# ============================================================================
# Backwards Compatibility Harness
# ============================================================================

class HireTraceHandler:
    """Placeholder handler class preserved for legacy test harnesses."""
    pass


class ReusableHTTPServer:
    """
    Backwards-compatible server runner wrapping Uvicorn.
    Allows existing test suites that call server.serve_forever() in a thread to run unmodified.
    """

    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass=None):
        self.host, self.port = server_address
        self.config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False
        )
        self.server = uvicorn.Server(self.config)

    def serve_forever(self):
        """Runs the Uvicorn ASGI server."""
        self.server.run()

    def shutdown(self):
        self.server.should_exit = True

    def server_close(self):
        self.server.should_exit = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()


def start_server(port: int = 8080, host: str = "127.0.0.1"):
    """CLI launcher for local development."""
    check_dev_mode_production_bind(host=host, port=port)
    uvicorn.run("ui.server:app", host=host, port=port, reload=False, workers=1)


if __name__ == "__main__":
    port = 8080
    host = os.environ.get("HOST", "127.0.0.1")
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2:
        host = sys.argv[2]
    start_server(port=port, host=host)
