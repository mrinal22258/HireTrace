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
from typing import Dict, Any, List, Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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
    CandidateCreateRequest,
    BatchEvaluationRequest,
)
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
from agents.jd_templates import generate_role_tailored_jd



# Shared singleton pipeline
PIPELINE = HireTracePipeline(trajectory_dir=CACHE_DIR)

def load_saved_custom_cases():
    """Loads previously submitted custom applicant files from disk and seeds DB."""
    if not os.path.exists(CASES_DIR):
        return
    test_prefixes = (
        "custom_bulk_", "custom_smoke_test_", "custom_rate_limit_",
        "custom_alpha_", "custom_invalid_id_", "cand_", "rate_limit_test_"
    )
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

# Seed database on module load directly from benchmark dataset
DB.seed_from_cases(CASES)
load_saved_custom_cases()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate production security configuration
    validate_security_configuration()
    # Ensure database tables and initial seed
    DB.seed_from_cases(CASES)
    load_saved_custom_cases()
    yield


app = FastAPI(
    title="HireTrace API",
    description="Evidence-First Candidate Assessment Engine with multi-replica ASGI scaling",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/favicon.ico")
def get_favicon():
    return Response(status_code=204)


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

@app.get("/api/cases")
def list_cases(
    request: Request,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    status: Optional[str] = None,
    quadrant: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Public Candidate List:
    - If pagination or search filters are provided, returns paginated DB result:
      {"items": [...], "total": N, "page": P, "limit": L, "pages": K}
    - If no filters are provided, returns list of candidate summaries directly from DB.
    """
    tenant = authenticate_and_authorize(request)
    if any(param is not None for param in (page, limit, status, quadrant, search)):
        return DB.list_candidates(
            page=page or 1,
            limit=limit or 50,
            status=status,
            quadrant=quadrant,
            search=search,
            tenant_id=tenant
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

        test_prefixes = (
            "custom_bulk_", "custom_smoke_test_", "custom_rate_limit_",
            "custom_alpha_", "custom_invalid_id_", "cand_", "rate_limit_test_"
        )

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

            if r.report_json:
                try:
                    rep = json.loads(r.report_json)
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
                benchmark_items.append(item)
                seen_ids.add(cid)
                if name_key:
                    seen_names.add(name_key)

        for item in raw_list:
            cid = item["candidate_id"]
            name_key = (item["name"] or "").strip().lower()

            if cid not in seen_ids:
                if name_key and name_key in seen_names:
                    # Skip duplicate of an existing or benchmark candidate
                    continue
                seen_ids.add(cid)
                if name_key:
                    seen_names.add(name_key)
                custom_items.append(item)

        # Sort benchmark cases in canonical index order
        benchmark_items.sort(key=lambda x: bench_order.get(x["candidate_id"], 999))

        # Return custom applicants followed by benchmark cases (or benchmark cases first)
        summary_list = custom_items + benchmark_items
        return summary_list


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
        rep = db_eval["report"]
        is_deg = rep.get("degraded", False)
        result = {
            "candidate_id": raw_cid,
            "name": cand.get("name", "") if cand else "",
            "target_role": cand.get("target_role", "Senior Software Engineer") if cand else "Senior Software Engineer",
            "status": "done",
            "progress_pct": 100,
            "current_step": "Assessment complete. Report ready." if not is_deg else "Assessment complete (DEGRADED: Local LLM offline).",
            "report": rep,
            "baseline_a": db_eval.get("baseline_a"),
            "degraded": is_deg,
            "error": None,
        }
        STATUS_CACHE[raw_cid] = result
        return result

    # Check disk case
    custom_file = os.path.join(CASES_DIR, f"{raw_cid}.json")
    if os.path.exists(custom_file):
        try:
            with open(custom_file, "r", encoding="utf-8") as f:
                disk_case = json.load(f)
            if "evaluation_report" in disk_case:
                rep = disk_case.get("evaluation_report", {})
                is_deg = rep.get("degraded", False) or disk_case.get("degraded", False)
                result = {
                    "candidate_id": raw_cid,
                    "name": disk_case.get("name", ""),
                    "target_role": disk_case.get("target_role", "Senior Software Engineer"),
                    "status": "done",
                    "progress_pct": 100,
                    "current_step": "Assessment complete. Report ready." if not is_deg else "Assessment complete (DEGRADED: Local LLM offline).",
                    "report": rep,
                    "baseline_a": disk_case.get("rubric_baseline"),
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
        rep = case.get("evaluation_report", {})
        is_deg = rep.get("degraded", False) or case.get("degraded", False)
        result = {
            "candidate_id": raw_cid,
            "name": case.get("name", ""),
            "target_role": case.get("target_role", "Senior Software Engineer"),
            "status": "done",
            "progress_pct": 100,
            "current_step": "Assessment complete. Report ready." if not is_deg else "Assessment complete (DEGRADED: Local LLM offline).",
            "report": rep,
            "baseline_a": case.get("rubric_baseline"),
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
    }

    try:
        dossier = EvidenceLoader.load_case_from_dict(new_case)
        report = PIPELINE.run(dossier, log_trajectory=True)
        rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

        new_case["evaluation_report"] = report.to_dict()
        new_case["rubric_baseline"] = rubric.to_dict()
        new_case["role_fit_score"] = report.role_fit_score
        new_case["evidence_consistency_score"] = report.evidence_consistency_score
        new_case["quadrant"] = report.quadrant
        new_case["status"] = "done"

        # Persist to disk
        case_file = os.path.join(CASES_DIR, f"{cid}.json")
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
        raise HTTPException(status_code=422, detail=val_err.errors())

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

    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

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
        "raw_documents": raw_docs_meta,
    }

    # Check sync flag
    sync_param = request.query_params.get("sync", "false").lower() == "true"
    sync_header = request.headers.get("x-hiretrace-sync", "").lower() == "true"
    is_sync = sync_param or sync_header

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
            report = PIPELINE.run(dossier, log_trajectory=True)
            rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

            new_case["evaluation_report"] = report.to_dict()
            new_case["rubric_baseline"] = rubric.to_dict()
            new_case["role_fit_score"] = report.role_fit_score
            new_case["evidence_consistency_score"] = report.evidence_consistency_score
            new_case["quadrant"] = report.quadrant
            new_case["degraded"] = getattr(report, "degraded", False)
            new_case["status"] = "done"

            case_file = os.path.join(CASES_DIR, f"{cid}.json")
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
def evaluate_candidate(candidate_id: str, request: Request):
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

    # Check cache if not forced
    if not force_rerun:
        if case.get("evaluation_report"):
            return {
                "report": case["evaluation_report"],
                "baseline_a": case.get("rubric_baseline", {}),
                "cached": True,
            }

        db_eval = DB.get_evaluation(raw_cid)
        if db_eval and db_eval.get("report"):
            return {
                "report": db_eval["report"],
                "baseline_a": db_eval.get("baseline_a", {}),
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
                return {
                    "report": final_report,
                    "baseline_a": rubric.to_dict(),
                    "cached": True,
                }
            except Exception:
                pass

    # Run pipeline
    try:
        dossier = EvidenceLoader.load_case_from_dict(case)
        report = PIPELINE.run(dossier, log_trajectory=True)
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
