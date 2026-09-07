"""
HireTrace Horizontal Worker Entrypoint.

Starts a background worker process to consume candidate evaluation jobs.
Supports:
  1. Celery distributed worker mode (backed by Redis broker)
  2. Standalone DB-polling worker mode (zero broker dependency, horizontally scalable via DB state)
"""

import os
import sys
import time
import signal
import logging
import argparse
from typing import Optional

# Ensure project root is in sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.tasks import celery_app, run_candidate_evaluation_core
from agents.db import DB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s"
)
logger = logging.getLogger("hiretrace.worker")


def run_standalone_db_worker(concurrency: int = 2, poll_interval: float = 1.0, cases_dir: Optional[str] = None):
    """
    Consumes queued jobs directly from the JobQueue database table.
    Enables horizontal worker scaling even when Redis broker is not provisioned.
    """
    if not cases_dir:
        cases_dir = os.path.join(root_dir, "eval_cases", "custom_uploads")

    logger.info(f"Starting standalone DB worker (poll_interval={poll_interval}s, cases_dir={cases_dir})")
    running = True

    def _sig_handler(sig, frame):
        nonlocal running
        logger.info("Worker received shutdown signal. Terminating cleanly...")
        running = False

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    while running:
        try:
            # Atomically claim next queued job (no check-then-act race across workers)
            claimed_job = DB.claim_next_queued_job()
            if not claimed_job:
                time.sleep(poll_interval)
                continue

            cid = claimed_job["candidate_id"]
            logger.info(f"Worker claimed job: {cid}")

            # Load candidate details
            cand = DB.get_candidate_full(cid)
            if not cand:
                logger.error(f"Candidate {cid} not found in DB. Marking job failed.")
                DB.save_job(cid, status="failed", progress_pct=100, current_step="Candidate record missing in DB", error_msg="Candidate not found")
                continue

            case_data = {
                "candidate_id": cid,
                "name": cand.get("name", "Unknown Candidate"),
                "target_role": cand.get("target_role", "Senior Software Engineer"),
                "documents": cand.get("documents", {}),
                "metadata": cand.get("raw_document_metadata", {})
            }

            try:
                run_candidate_evaluation_core(cid, case_data, cases_dir)
                logger.info(f"Successfully evaluated candidate {cid}")
            except Exception as eval_err:
                logger.error(f"Failed evaluation for candidate {cid}: {eval_err}")

        except Exception as loop_err:
            logger.error(f"Unexpected worker loop exception: {loop_err}", exc_info=True)
            time.sleep(poll_interval)

    logger.info("Standalone DB worker stopped.")


def run_celery_worker(concurrency: Optional[int] = None):
    """Launches the Celery distributed worker consuming from Redis broker."""
    concurrency_str = str(concurrency) if concurrency else os.getenv("CONCURRENCY_WORKERS", "4")
    logger.info(f"Starting Celery distributed worker (concurrency={concurrency_str})")

    # Select pool: Windows doesn't support prefork gracefully, use solo or threads
    pool = "solo" if sys.platform.startswith("win") else "prefork"

    argv = [
        "worker",
        "--loglevel=INFO",
        f"--concurrency={concurrency_str}",
        f"--pool={pool}",
        "-Q", "celery",
    ]
    celery_app.worker_main(argv=argv)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HireTrace Evaluation Worker")
    parser.add_argument("--mode", "-m", choices=["celery", "db", "auto"], default="auto",
                        help="Worker mode: 'celery' (Redis), 'db' (DB polling), or 'auto' (checks Redis)")
    parser.add_argument("--concurrency", "-c", type=int, default=None,
                        help="Number of concurrent worker threads")
    parser.add_argument("--poll-interval", type=float, default=1.0,
                        help="Poll interval for DB worker in seconds")

    args = parser.parse_args()

    mode = args.mode
    if mode == "auto":
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                r = redis.Redis.from_url(redis_url, socket_connect_timeout=1.0)
                r.ping()
                mode = "celery"
                logger.info(f"Redis reachable at {redis_url}; running in Celery worker mode.")
            except Exception:
                logger.info("Redis unreachable; defaulting to standalone DB worker mode.")
                mode = "db"
        else:
            mode = "db"

    if mode == "celery":
        run_celery_worker(concurrency=args.concurrency)
    else:
        run_standalone_db_worker(concurrency=args.concurrency or 2, poll_interval=args.poll_interval)
