"""
Data Retention and Candidate Purge Lifecycle for HireTrace.

Enforces configurable retention policies (HIRETRACE_DATA_RETENTION_DAYS).
Provides the unified deletion logic for:
1. HTTP DELETE /api/candidate/{candidate_id}
2. Scheduled Celery / DB worker retention purge tasks
"""

import os
import time
import shutil
import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from agents.db import DB
from agents.embedding_cache import EMBEDDING_CACHE
from agents.observability import METRICS

logger = logging.getLogger("hiretrace.retention")

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(root_dir, "eval_cases")
UPLOADS_DIR = os.path.join(root_dir, "uploads")
CACHE_DIR = os.path.join(root_dir, "trajectories")


def get_retention_days() -> Optional[int]:
    """Returns configured retention days or None if unset/empty."""
    raw = os.environ.get("HIRETRACE_DATA_RETENTION_DAYS", "").strip()
    if not raw:
        return None
    try:
        val = int(raw)
        return val if val > 0 else None
    except ValueError:
        logger.warning(f"Invalid HIRETRACE_DATA_RETENTION_DAYS value: '{raw}'. Retention auto-purge disabled.")
        return None


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


def delete_candidate_artifacts(candidate_id: str, status_cache: Optional[Any] = None, job_manager: Optional[Any] = None) -> Dict[str, Any]:
    """
    Unified candidate deletion logic:
    1. Validates ID format and asserts safe filesystem paths.
    2. Deletes candidate rows from DB (candidates, documents, evaluations, dedup_hashes, job_queue).
    3. Deletes filesystem artifacts from UPLOADS_DIR, CASES_DIR, and CACHE_DIR.
    4. Evicts cached entries from EMBEDDING_CACHE, STATUS_CACHE, and JOB_MANAGER.
    """
    raw_cid = candidate_id.strip()

    # Reuse the dot-free regex ID pattern
    import re
    if not re.match(r"^[A-Za-z0-9_-]{1,128}$", raw_cid):
        raise HTTPException(status_code=400, detail="Invalid Candidate ID format")

    # Check existence
    db_cand = DB.get_candidate_full(raw_cid)
    disk_case = os.path.join(CASES_DIR, f"{raw_cid}.json")
    custom_upload_case = os.path.join(CASES_DIR, "custom_uploads", f"{raw_cid}.json")
    cand_upload_dir = os.path.join(UPLOADS_DIR, raw_cid)
    traj_file = os.path.join(CACHE_DIR, f"{raw_cid}_trajectory.json")

    # Path safety assertions
    assert_safe_path(disk_case, CASES_DIR)
    assert_safe_path(custom_upload_case, CASES_DIR)
    assert_safe_path(cand_upload_dir, UPLOADS_DIR)
    assert_safe_path(traj_file, CACHE_DIR)

    exists = (
        db_cand is not None or
        os.path.exists(disk_case) or
        os.path.exists(custom_upload_case) or
        os.path.exists(cand_upload_dir) or
        os.path.exists(traj_file)
    )

    if not exists:
        raise HTTPException(status_code=404, detail=f"Candidate {raw_cid} not found")

    deleted_files = []

    # 1. DB deletion
    db_summary = DB.delete_candidate(raw_cid)

    # 2. Filesystem deletion
    if os.path.exists(cand_upload_dir):
        shutil.rmtree(cand_upload_dir, ignore_errors=True)
        deleted_files.append(cand_upload_dir)

    for cfile in (disk_case, custom_upload_case):
        if os.path.exists(cfile):
            for _ in range(4):
                try:
                    os.remove(cfile)
                    deleted_files.append(cfile)
                    break
                except Exception:
                    time.sleep(0.05)

    if os.path.exists(traj_file):
        for _ in range(4):
            try:
                os.remove(traj_file)
                deleted_files.append(traj_file)
                break
            except Exception:
                time.sleep(0.05)

    # 3. Cache evictions
    EMBEDDING_CACHE.evict_candidate(raw_cid)
    if status_cache is not None:
        status_cache.pop(raw_cid, None)
    if job_manager is not None and hasattr(job_manager, "_jobs"):
        job_manager._jobs.pop(raw_cid, None)

    return {
        "candidate_id": raw_cid,
        "deleted_db_rows": db_summary,
        "deleted_paths": deleted_files,
        "status": "deleted"
    }


def purge_expired_candidates(retention_days: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Purges all candidates whose creation time exceeds the retention threshold.
    Uses the exact same delete_candidate_artifacts method.
    """
    days = retention_days if retention_days is not None else get_retention_days()
    if not days or days <= 0:
        logger.info("Data retention is not configured (HIRETRACE_DATA_RETENTION_DAYS unset). Skipping purge.")
        return []

    cutoff = time.time() - (days * 86400)
    expired_ids = DB.get_candidate_ids_older_than(cutoff)
    logger.info(f"Found {len(expired_ids)} candidates older than {days} days (cutoff={cutoff}). Purging...")

    results = []
    for cid in expired_ids:
        try:
            res = delete_candidate_artifacts(cid)
            results.append(res)
            logger.info(f"Purged expired candidate: {cid}")
        except Exception as e:
            logger.error(f"Error purging candidate {cid}: {e}")

    return results
