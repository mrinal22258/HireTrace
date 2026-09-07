"""
Distributed Task Definitions and Celery Configuration for HireTrace.

Provides Celery-backed distributed task execution for horizontal worker scaling.
Ensures job state persistence in JobQueue database table and handles worker failovers.
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any, Optional, Callable
from celery import Celery

from agents.evidence_loader import EvidenceLoader
from agents.pipeline import HireTracePipeline
from agents.fast_triage import FastTriageEngine
from agents.db import DB
from baseline.rubric_scorer import RubricScorer

logger = logging.getLogger("hiretrace.tasks")

# Broker configuration with Redis
REDIS_URL = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
CELERY_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

celery_app = Celery(
    "hiretrace",
    broker=REDIS_URL,
    backend=CELERY_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,                     # Do not acknowledge message until task completes
    task_reject_on_worker_lost=True,         # Re-queue task if worker dies mid-execution
    worker_prefetch_multiplier=1,            # Bounded dispatch: don't buffer heavy LLM tasks
    task_track_started=True,
    broker_connection_retry_on_startup=True
)

# Cached pipeline instance for worker process
_GLOBAL_PIPELINE: Optional[HireTracePipeline] = None


def get_worker_pipeline() -> HireTracePipeline:
    """Returns or lazily creates a cached HireTracePipeline instance for this worker."""
    global _GLOBAL_PIPELINE
    if _GLOBAL_PIPELINE is None:
        _GLOBAL_PIPELINE = HireTracePipeline()
    return _GLOBAL_PIPELINE


def run_candidate_evaluation_core(
    cid: str,
    case_data: Dict[str, Any],
    cases_dir: str,
    update_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    pipeline: Optional[HireTracePipeline] = None
) -> Dict[str, Any]:
    """
    Core candidate evaluation workflow executed by local or Celery workers.
    Updates JobQueue table in DB at each step and handles failures gracefully.
    """
    # Defense-in-depth idempotency guard:
    # If job exists in DB, ensure it is in 'evaluating' state and has not been finished or reclaimed
    job_record = DB.get_job(cid)
    if job_record:
        job_status = job_record.get("status")
        if job_status != "evaluating":
            logger.warning(
                f"Idempotency guard: candidate {cid} has status '{job_status}' (not 'evaluating'). Aborting evaluation to prevent double-processing."
            )
            return case_data
    else:
        # Direct execution without prior queue record: initialize as evaluating
        DB.save_job(cid, status="evaluating", progress_pct=10, current_step="Starting evaluation...")

    try:
        # Step 1: Chunking & Dossier Construction
        current_step = "Chunking evidence spans & building candidate dossier..."
        DB.save_job(cid, status="evaluating", progress_pct=20, current_step=current_step)
        if update_callback:
            update_callback(cid, {"status": "evaluating", "progress_pct": 20, "current_step": current_step})

        dossier = EvidenceLoader.load_case_from_dict(case_data)
        target_role = case_data.get("target_role", "Senior Software Engineer")

        # Step 1.5: Tier-0 Fast-Triage Pre-screen Filter
        is_fast_rejected, triage_report = FastTriageEngine.evaluate(dossier, target_role)
        if is_fast_rejected:
            rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)
            case_data["evaluation_report"] = triage_report
            case_data["rubric_baseline"] = rubric.to_dict()
            case_data["role_fit_score"] = triage_report["role_fit_score"]
            case_data["evidence_consistency_score"] = triage_report["evidence_consistency_score"]
            case_data["quadrant"] = triage_report["quadrant"]
            case_data["status"] = "done"

            # Persist to disk JSON
            if cases_dir:
                os.makedirs(cases_dir, exist_ok=True)
                case_file = os.path.join(cases_dir, f"{cid}.json")
                with open(case_file, "w", encoding="utf-8") as f:
                    json.dump(case_data, f, indent=2)

            # Persist evaluation in DB
            DB.save_evaluation(
                candidate_id=cid,
                role_fit_score=triage_report["role_fit_score"],
                evidence_consistency_score=triage_report["evidence_consistency_score"],
                quadrant=triage_report["quadrant"],
                report_dict=triage_report,
                baseline_a_dict=rubric.to_dict()
            )

            finish_step = "Tier-0 Fast Triage Complete: Low Domain Fit (Bypassed LLM)"
            DB.save_job(cid, status="done", progress_pct=100, current_step=finish_step)
            if update_callback:
                update_callback(cid, {
                    "status": "done",
                    "progress_pct": 100,
                    "current_step": finish_step,
                    "report": triage_report,
                    "baseline_a": rubric.to_dict()
                })
            return case_data

        # Step 2: Deterministic Baseline Rubric
        current_step = "Calculating deterministic CareerCheck rubric baseline..."
        DB.save_job(cid, status="evaluating", progress_pct=40, current_step=current_step)
        if update_callback:
            update_callback(cid, {"status": "evaluating", "progress_pct": 40, "current_step": current_step})

        rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

        # Step 3: Run Multi-Agent Verification Pipeline
        current_step = "Retrieval indexing & cross-source contradiction verification..."
        DB.save_job(cid, status="evaluating", progress_pct=60, current_step=current_step)
        if update_callback:
            update_callback(cid, {"status": "evaluating", "progress_pct": 60, "current_step": current_step})

        pipe = pipeline or get_worker_pipeline()
        report = pipe.run(dossier, log_trajectory=True)

        current_step = "Writing 2D quadrant assessment report card..."
        DB.save_job(cid, status="evaluating", progress_pct=90, current_step=current_step)
        if update_callback:
            update_callback(cid, {"status": "evaluating", "progress_pct": 90, "current_step": current_step})

        # Step 4: Persist Evaluated Case to Disk & DB
        case_data["evaluation_report"] = report.to_dict()
        case_data["rubric_baseline"] = rubric.to_dict()
        case_data["role_fit_score"] = report.role_fit_score
        case_data["evidence_consistency_score"] = report.evidence_consistency_score
        case_data["quadrant"] = report.quadrant
        case_data["status"] = "done"

        if cases_dir:
            os.makedirs(cases_dir, exist_ok=True)
            case_file = os.path.join(cases_dir, f"{cid}.json")
            with open(case_file, "w", encoding="utf-8") as f:
                json.dump(case_data, f, indent=2)

        DB.save_evaluation(
            candidate_id=cid,
            role_fit_score=report.role_fit_score,
            evidence_consistency_score=report.evidence_consistency_score,
            quadrant=report.quadrant,
            report_dict=report.to_dict(),
            baseline_a_dict=rubric.to_dict()
        )

        is_degraded = getattr(report, "degraded", False)
        done_step = "Assessment complete. Report ready." if not is_degraded else "Assessment complete (DEGRADED: Local LLM offline)."
        DB.save_job(cid, status="done", progress_pct=100, current_step=done_step)
        if update_callback:
            update_callback(cid, {
                "status": "done",
                "progress_pct": 100,
                "current_step": done_step,
                "report": report.to_dict(),
                "baseline_a": rubric.to_dict(),
                "degraded": is_degraded
            })

        return case_data

    except Exception as err:
        err_msg = str(err)
        logger.error(f"Error evaluating candidate {cid}: {err_msg}", exc_info=True)
        fail_step = f"Evaluation failed: {err_msg}"
        DB.save_job(cid, status="failed", progress_pct=100, current_step=fail_step, error_msg=err_msg)
        if update_callback:
            update_callback(cid, {
                "status": "failed",
                "progress_pct": 100,
                "current_step": fail_step,
                "error": err_msg
            })
        raise err


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5, acks_late=True)
def evaluate_candidate_celery_task(self, case_data: Dict[str, Any], cases_dir: str):
    """
    Celery task wrapper for candidate evaluation.
    Supports automatic retry on worker failure and late ACKs.
    """
    cid = case_data.get("candidate_id")
    DB.save_job(cid, status="evaluating", progress_pct=15, current_step="Claimed by Celery worker. Starting evaluation...")
    try:
        return run_candidate_evaluation_core(cid, case_data, cases_dir)
    except Exception as exc:
        if self.request.retries < self.max_retries:
            retry_step = f"Worker transient failure. Retrying attempt {self.request.retries + 1}/{self.max_retries}..."
            DB.save_job(cid, status="queued", progress_pct=10, current_step=retry_step, error_msg=str(exc))
            raise self.retry(exc=exc)
        else:
            DB.save_job(cid, status="failed", progress_pct=100, current_step=f"Evaluation failed permanently: {str(exc)}", error_msg=str(exc))
            raise exc
