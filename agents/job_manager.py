"""
Asynchronous Job Manager for HireTrace.

Coordinates background execution of candidate evaluations across bounded worker threads
or distributed Celery workers backed by Redis.
Persists job states to the JobQueue database table:
  queued -> parsing -> evaluating -> done / failed
"""

import time
import os
import json
import asyncio
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable

from agents.db import DB
from agents.pipeline import HireTracePipeline

logger = logging.getLogger("hiretrace.job_manager")


class JobPersistenceError(RuntimeError):
    """Raised when job persistence to the database fails after retries."""
    pass


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
    degraded: bool = False
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
            "degraded": self.degraded,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class JobManager:
    """
    Hybrid Async/Distributed Worker Pool for HireTrace.
    
    Supports:
      1. Celery distributed tasks over Redis for horizontal worker scaling across nodes.
      2. In-process bounded asyncio worker pool for local, single-node or zero-config execution.
    
    Every status transition is persisted to the JobQueue database table so that any API
    replica or worker process sees consistent, surviving job state.
    """

    def __init__(self, max_workers: Optional[int] = None):
        if max_workers is None:
            max_workers = int(os.getenv("CONCURRENCY_WORKERS", "4"))
        self.max_workers = max(1, max_workers)
        self._jobs: Dict[str, CandidateJob] = {}
        self._lock = threading.Lock()

        # Determine queue backend
        self.queue_backend = os.getenv("HIRETRACE_QUEUE_BACKEND", "auto").lower()
        self.use_celery = False
        redis_url = os.getenv("REDIS_URL")

        if self.queue_backend in ("celery", "redis"):
            self.use_celery = True
        elif self.queue_backend == "auto" and redis_url:
            try:
                import redis
                r = redis.Redis.from_url(redis_url, socket_connect_timeout=1.0)
                r.ping()
                self.use_celery = True
                logger.info(f"Connected to Redis broker at {redis_url}; using Celery task queue.")
            except Exception as e:
                logger.info(f"Redis not reachable ({e}); using local bounded worker pool.")
                self.use_celery = False

        # Dedicated background asyncio event loop and worker tasks for local mode
        self._loop = asyncio.new_event_loop()
        self._queue: Optional[asyncio.Queue] = None
        self._ready_event = threading.Event()
        self._loop_thread = threading.Thread(target=self._run_loop, name="hiretrace_async_loop", daemon=True)
        self._loop_thread.start()
        self._ready_event.wait(timeout=5.0)

    def _run_loop(self):
        """Dedicated background thread running the asyncio event loop."""
        asyncio.set_event_loop(self._loop)
        self._queue = asyncio.Queue()
        for i in range(self.max_workers):
            self._loop.create_task(self._async_worker(i))
        self._ready_event.set()
        self._loop.run_forever()

    async def _async_worker(self, worker_id: int):
        """Asynchronous worker pulling tasks from the queue and executing evaluations concurrently."""
        while True:
            try:
                task_args = await self._queue.get()
                cid, case_data, pipeline, cases_dir, all_cases_list, on_complete = task_args
                await asyncio.to_thread(
                    self._run_job_worker,
                    cid,
                    case_data,
                    pipeline,
                    cases_dir,
                    all_cases_list,
                    on_complete
                )
            except Exception as e:
                logger.error(f"Async worker exception: {e}", exc_info=True)
            finally:
                if self._queue:
                    self._queue.task_done()

    def create_job(self, candidate_id: str, name: str, target_role: str) -> CandidateJob:
        """Initializes a new job both in-memory and persistently in the JobQueue table."""
        step = "Ingested document payload. Queued for evaluation."

        # Persist to database with retries before committing to in-memory state
        delays = (0.2, 0.5, 1.0)
        last_err = None
        for attempt, delay in enumerate(delays):
            try:
                DB.save_job(
                    candidate_id=candidate_id,
                    status="queued",
                    progress_pct=10,
                    current_step=step
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt < len(delays) - 1:
                    logger.warning(f"Failed to persist job creation to DB (retrying in {delay}s): {e}")
                    time.sleep(delay)

        if last_err is not None:
            logger.error(f"Exhausted DB retries creating job for candidate {candidate_id}: {last_err}")
            raise JobPersistenceError(
                f"Failed to persist job {candidate_id} to database after 3 retries: {last_err}"
            )

        with self._lock:
            job = CandidateJob(
                candidate_id=candidate_id,
                name=name,
                target_role=target_role,
                status="queued",
                progress_pct=10,
                current_step=step
            )
            self._jobs[candidate_id] = job

        return job

    def get_job(self, candidate_id: str) -> Optional[CandidateJob]:
        """
        Retrieves job status from in-memory cache or restores from the JobQueue database table.
        Ensures multi-replica and horizontal worker state visibility.
        """
        with self._lock:
            cached_job = self._jobs.get(candidate_id)

        # Check DB for true cross-worker state
        try:
            db_job = DB.get_job(candidate_id)
        except Exception:
            db_job = None

        if db_job:
            db_status = db_job.get("status", "queued")
            # Lazy stale check for self-healing even if worker is not running
            stale_timeout = float(os.getenv("HIRETRACE_JOB_STALE_TIMEOUT_SECONDS", "300"))
            if db_status == "evaluating":
                last_activity = db_job.get("updated_at") or db_job.get("started_at") or db_job.get("enqueued_at") or 0.0
                if (time.time() - last_activity) > stale_timeout:
                    err_msg = "Job timed out — worker may have crashed. Please retry."
                    DB.save_job(
                        candidate_id=candidate_id,
                        status="failed",
                        progress_pct=db_job.get("progress_pct", 0),
                        current_step="Failed: Execution timed out",
                        error_msg=err_msg
                    )
                    db_status = "failed"
                    db_job["status"] = "failed"
                    db_job["error_msg"] = err_msg

            # If DB has a newer or completed state, return synchronized object
            db_eval = DB.get_evaluation(candidate_id)
            cand = DB.get_candidate_full(candidate_id)

            cand_name = (cand.get("name") if cand else None) or (cached_job.name if cached_job else "")
            cand_role = (cand.get("target_role") if cand else None) or (cached_job.target_role if cached_job else "Senior Software Engineer")
            rep = db_eval.get("report") if db_eval else (cached_job.report if cached_job else None)
            base_a = db_eval.get("baseline_a") if db_eval else (cached_job.baseline_a if cached_job else None)
            is_deg = rep.get("degraded", False) if isinstance(rep, dict) else False

            synced_job = CandidateJob(
                candidate_id=candidate_id,
                name=cand_name,
                target_role=cand_role,
                status=db_status,
                progress_pct=db_job.get("progress_pct", 0),
                current_step=db_job.get("current_step", ""),
                report=rep,
                baseline_a=base_a,
                error=db_job.get("error_msg") or (cached_job.error if cached_job else None),
                degraded=is_deg,
                created_at=db_job.get("enqueued_at") or (cached_job.created_at if cached_job else time.time()),
                updated_at=db_job.get("finished_at") or (cached_job.updated_at if cached_job else time.time())
            )
            with self._lock:
                self._jobs[candidate_id] = synced_job
            return synced_job

        return cached_job

    def update_job(self, candidate_id: str, **kwargs):
        """Updates job state in memory and persists to the JobQueue database table."""
        with self._lock:
            job = self._jobs.get(candidate_id)
            if job:
                incoming_pct = kwargs.get("progress_pct")
                incoming_status = kwargs.get("status", job.status)
                if incoming_status == "evaluating" and job.status == "evaluating" and incoming_pct is not None:
                    if (job.progress_pct or 0) > incoming_pct:
                        logger.warning(
                            f"In-memory monotonicity guard preserved {job.progress_pct}% over incoming {incoming_pct}% for {candidate_id}"
                        )
                        kwargs["progress_pct"] = job.progress_pct

                for k, v in kwargs.items():
                    if hasattr(job, k):
                        setattr(job, k, v)
                job.updated_at = time.time()
                status = job.status
                progress_pct = job.progress_pct
                current_step = job.current_step
                error = job.error
            else:
                status = kwargs.get("status", "evaluating")
                progress_pct = kwargs.get("progress_pct", 0)
                current_step = kwargs.get("current_step", "")
                error = kwargs.get("error")

        try:
            DB.save_job(
                candidate_id=candidate_id,
                status=status,
                progress_pct=progress_pct,
                current_step=current_step,
                error_msg=error
            )
        except Exception as e:
            logger.warning(f"Failed to persist job update to DB: {e}")

    def _on_task_progress(self, cid: str, updates: Dict[str, Any]):
        """Callback to sync progress from core task worker into JobManager."""
        self.update_job(cid, **updates)

    def submit_evaluation(
        self,
        case_data: Dict[str, Any],
        pipeline: Optional[HireTracePipeline] = None,
        cases_dir: Optional[str] = None,
        all_cases_list: Optional[list] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> CandidateJob:
        """
        Enqueues candidate evaluation with a single-flight idempotency guard.
        If a job is already queued or evaluating for this candidate, returns the existing job.
        """
        cid = case_data.get("candidate_id")
        if not cid:
            raise ValueError("case_data must contain 'candidate_id'")

        # Single-flight idempotency guard
        existing = self.get_job(cid)
        if existing and existing.status in ("queued", "evaluating", "retrying"):
            logger.info(f"Evaluation already active for candidate {cid} (status={existing.status}, progress={existing.progress_pct}%). Attaching to existing job.")
            return existing

        name = case_data.get("name", "Unknown Candidate")
        target_role = case_data.get("target_role", "Senior Software Engineer")

        job = self.create_job(cid, name, target_role)

        if cases_dir is None:
            cases_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval_cases", "custom_uploads")

        if self.use_celery:
            try:
                from agents.tasks import evaluate_candidate_celery_task
                evaluate_candidate_celery_task.delay(case_data, cases_dir)
                logger.info(f"Dispatched candidate {cid} to Celery distributed worker queue.")
                return job
            except Exception as e:
                logger.warning(f"Failed to dispatch to Celery ({e}); falling back to local thread pool.")

        # Local fallback execution via async worker pool
        task_payload = (cid, case_data, pipeline, cases_dir, all_cases_list, on_complete)
        if self._loop and self._queue and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._queue.put(task_payload), self._loop)
        else:
            threading.Thread(
                target=self._run_job_worker,
                args=task_payload,
                daemon=True,
            ).start()
        return job

    def _run_job_worker(
        self,
        cid: str,
        case_data: Dict[str, Any],
        pipeline: Optional[HireTracePipeline],
        cases_dir: str,
        all_cases_list: Optional[list],
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """Worker thread executing the evaluation workflow."""
        from agents.tasks import run_candidate_evaluation_core

        try:
            self.update_job(cid, status="evaluating", progress_pct=15, current_step="Claimed by worker pool. Starting evaluation...")
            evaluated_case = run_candidate_evaluation_core(
                cid=cid,
                case_data=case_data,
                cases_dir=cases_dir,
                update_callback=self._on_task_progress,
                pipeline=pipeline
            )

            # Evaluation result is persisted to DB (single source of truth) by run_candidate_evaluation_core

            if on_complete:
                try:
                    on_complete(evaluated_case)
                except Exception:
                    pass

        except Exception as err:
            logger.error(f"Worker job execution failed for {cid}: {err}", exc_info=True)


# Global singleton job manager
JOB_MANAGER = JobManager()
