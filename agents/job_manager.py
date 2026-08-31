"""
Asynchronous Job Manager for HireTrace.

Coordinates background execution of candidate evaluations using a bounded thread pool.
Maintains in-memory job states and step-by-step progress tracking:
  queued -> parsing -> evaluating -> done / failed

Avoids saturating GPU/CPU resources by capping concurrent local LLM inference.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, Callable
import json
import os

from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.pipeline import HireTracePipeline
from agents.fast_triage import FastTriageEngine
from agents.db import DB
from baseline.rubric_scorer import RubricScorer



@dataclass
class CandidateJob:
    candidate_id: str
    name: str
    target_role: str
    status: str = "queued"  # "queued", "parsing", "evaluating", "done", "failed"
    progress_pct: int = 0
    current_step: str = "Queued in evaluation pool"
    report: Optional[Dict[str, Any]] = None
    baseline_a: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "target_role": self.target_role,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "current_step": self.current_step,
            "report": self.report,
            "baseline_a": self.baseline_a,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class JobManager:
    """Thread-safe background task queue and status monitor for HireTrace pipeline."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hiretrace_worker")
        self._jobs: Dict[str, CandidateJob] = {}
        self._lock = threading.Lock()

    def create_job(self, candidate_id: str, name: str, target_role: str) -> CandidateJob:
        with self._lock:
            job = CandidateJob(
                candidate_id=candidate_id,
                name=name,
                target_role=target_role,
                status="queued",
                progress_pct=10,
                current_step="Ingested document payload. Queued for evaluation."
            )
            self._jobs[candidate_id] = job
            return job

    def get_job(self, candidate_id: str) -> Optional[CandidateJob]:
        with self._lock:
            return self._jobs.get(candidate_id)

    def update_job(self, candidate_id: str, **kwargs):
        with self._lock:
            job = self._jobs.get(candidate_id)
            if job:
                for k, v in kwargs.items():
                    if hasattr(job, k):
                        setattr(job, k, v)
                job.updated_at = time.time()

    def submit_evaluation(
        self,
        case_data: Dict[str, Any],
        pipeline: HireTracePipeline,
        cases_dir: str,
        all_cases_list: list,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """Enqueues candidate evaluation on the background worker pool."""
        cid = case_data["candidate_id"]
        name = case_data["name"]
        target_role = case_data.get("target_role", "Senior Software Engineer")

        self.create_job(cid, name, target_role)
        self._executor.submit(
            self._run_job_worker,
            cid,
            case_data,
            pipeline,
            cases_dir,
            all_cases_list,
            on_complete
        )

    def _run_job_worker(
        self,
        cid: str,
        case_data: Dict[str, Any],
        pipeline: HireTracePipeline,
        cases_dir: str,
        all_cases_list: list,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """Worker thread executing the 4-agent verification pipeline with Tier-0 Fast Triage."""
        try:
            # Step 1: Chunking & Dossier Construction
            self.update_job(
                cid,
                status="evaluating",
                progress_pct=20,
                current_step="Chunking evidence spans & building candidate dossier..."
            )
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

                # Persist to disk and SQLite database
                case_file = os.path.join(cases_dir, f"{cid}.json")
                with open(case_file, "w", encoding="utf-8") as f:
                    json.dump(case_data, f, indent=2)

                DB.save_evaluation(
                    candidate_id=cid,
                    role_fit_score=triage_report["role_fit_score"],
                    evidence_consistency_score=triage_report["evidence_consistency_score"],
                    quadrant=triage_report["quadrant"],
                    report_dict=triage_report,
                    baseline_a_dict=rubric.to_dict()
                )

                found = False
                for idx, existing in enumerate(all_cases_list):
                    if existing.get("candidate_id") == cid:
                        all_cases_list[idx] = case_data
                        found = True
                        break
                if not found:
                    all_cases_list.append(case_data)

                self.update_job(
                    cid,
                    status="done",
                    progress_pct=100,
                    current_step="Tier-0 Fast Triage Complete: Low Domain Fit (Bypassed LLM)",
                    report=triage_report,
                    baseline_a=rubric.to_dict()
                )
                if on_complete:
                    try:
                        on_complete(case_data)
                    except Exception:
                        pass
                return

            # Step 2: Deterministic Baseline Rubric
            self.update_job(
                cid,
                progress_pct=40,
                current_step="Calculating deterministic CareerCheck rubric baseline..."
            )
            rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

            # Step 3: Run Multi-Agent Verification Pipeline
            self.update_job(
                cid,
                progress_pct=60,
                current_step="Retrieval indexing & cross-source contradiction verification..."
            )
            report = pipeline.run(dossier, log_trajectory=True)

            self.update_job(
                cid,
                progress_pct=90,
                current_step="Writing 2D quadrant assessment report card..."
            )

            # Step 4: Persist Evaluated Case to Disk & DB
            case_data["evaluation_report"] = report.to_dict()
            case_data["rubric_baseline"] = rubric.to_dict()
            case_data["role_fit_score"] = report.role_fit_score
            case_data["evidence_consistency_score"] = report.evidence_consistency_score
            case_data["quadrant"] = report.quadrant
            case_data["status"] = "done"

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

            # Update in-memory cases pool
            found = False
            for idx, existing in enumerate(all_cases_list):
                if existing.get("candidate_id") == cid:
                    all_cases_list[idx] = case_data
                    found = True
                    break
            if not found:
                all_cases_list.append(case_data)

            # Mark job complete
            self.update_job(

                cid,
                status="done",
                progress_pct=100,
                current_step="Assessment complete. Report ready.",
                report=report.to_dict(),
                baseline_a=rubric.to_dict()
            )

            if on_complete:
                try:
                    on_complete(case_data)
                except Exception:
                    pass

        except Exception as err:
            self.update_job(
                cid,
                status="failed",
                progress_pct=100,
                current_step=f"Evaluation failed: {str(err)}",
                error=str(err)
            )


# Global singleton job manager
JOB_MANAGER = JobManager(max_workers=2)
