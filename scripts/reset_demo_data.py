"""
Demo Data Reset Script for HireTrace.

Resets local state to the clean 15 canonical benchmark cases:
1. Clears upload artifacts, custom JSON cases, custom trajectories, and embedding cache.
2. Wipes or resets the local database (hiretrace.db).
3. Re-seeds strictly the 15 canonical cases from eval_cases/dataset.py.
4. Confirms final candidate count is exactly 15.
"""

import os
import sys
import glob
import shutil
import logging

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from eval_cases.dataset import CASES
from agents.db import DB, Candidate, Evaluation, Document, JobQueue, DedupHash, RequirementCache
from sqlalchemy import text


def reset_demo_data():
    print("=" * 65)
    print("           HIRETRACE DEMO DATA RESET & HYGIENE")
    print("=" * 65)

    stats = {
        "uploads_deleted": 0,
        "custom_trajectories_deleted": 0,
        "custom_eval_cases_deleted": 0,
        "cache_files_deleted": 0,
        "db_rows_cleared": 0,
    }

    # 1. Clean uploads directory
    uploads_dir = os.path.join(root_dir, "uploads")
    if os.path.exists(uploads_dir):
        for item in os.listdir(uploads_dir):
            ipath = os.path.join(uploads_dir, item)
            try:
                if os.path.isfile(ipath) or os.path.islink(ipath):
                    os.unlink(ipath)
                    stats["uploads_deleted"] += 1
                elif os.path.isdir(ipath):
                    shutil.rmtree(ipath)
                    stats["uploads_deleted"] += 1
            except Exception as e:
                print(f"  [!] Warning removing {ipath}: {e}")
    os.makedirs(uploads_dir, exist_ok=True)

    # 2. Clean custom trajectories
    traj_dir = os.path.join(root_dir, "trajectories")
    for f in glob.glob(os.path.join(traj_dir, "custom_*")):
        try:
            os.remove(f)
            stats["custom_trajectories_deleted"] += 1
        except Exception as e:
            print(f"  [!] Warning removing {f}: {e}")

    for f in glob.glob(os.path.join(traj_dir, "cand_*")):
        try:
            os.remove(f)
            stats["custom_trajectories_deleted"] += 1
        except Exception as e:
            print(f"  [!] Warning removing {f}: {e}")

    for f in glob.glob(os.path.join(traj_dir, "rate_limit_test_*")):
        try:
            os.remove(f)
            stats["custom_trajectories_deleted"] += 1
        except Exception as e:
            print(f"  [!] Warning removing {f}: {e}")

    # 3. Clean custom evaluation cases and uploads
    eval_cases_dir = os.path.join(root_dir, "eval_cases")
    for f in glob.glob(os.path.join(eval_cases_dir, "custom_*.json")):
        try:
            os.remove(f)
            stats["custom_eval_cases_deleted"] += 1
        except Exception as e:
            print(f"  [!] Warning removing {f}: {e}")

    custom_uploads_dir = os.path.join(eval_cases_dir, "custom_uploads")
    if os.path.exists(custom_uploads_dir):
        try:
            shutil.rmtree(custom_uploads_dir)
            stats["custom_eval_cases_deleted"] += 1
        except Exception as e:
            print(f"  [!] Warning removing {custom_uploads_dir}: {e}")
    os.makedirs(custom_uploads_dir, exist_ok=True)

    # 4. Clean cache directory
    cache_dir = os.path.join(eval_cases_dir, "cache")
    if os.path.exists(cache_dir):
        for item in os.listdir(cache_dir):
            cpath = os.path.join(cache_dir, item)
            try:
                if os.path.isfile(cpath) or os.path.islink(cpath):
                    os.unlink(cpath)
                    stats["cache_files_deleted"] += 1
                elif os.path.isdir(cpath):
                    shutil.rmtree(cpath)
                    stats["cache_files_deleted"] += 1
            except Exception as e:
                print(f"  [!] Warning removing {cpath}: {e}")
    os.makedirs(cache_dir, exist_ok=True)

    # 5. Reset Database
    # Try deleting file first if not locked; otherwise truncate tables
    db_file = os.path.join(root_dir, "hiretrace.db")
    deleted_db_file = False
    try:
        DB.engine.dispose()
        for f in glob.glob(os.path.join(root_dir, "hiretrace.db*")):
            os.remove(f)
        deleted_db_file = True
    except Exception:
        # File is held open by a running worker/server, wipe tables directly
        with DB.session_scope() as session:
            for table in (Evaluation, Document, JobQueue, DedupHash, Candidate, RequirementCache):
                deleted_rows = session.query(table).delete()
                stats["db_rows_cleared"] += deleted_rows
        if DB.is_sqlite:
            try:
                with DB.engine.connect() as conn:
                    conn.execute(text("VACUUM"))
                    conn.commit()
            except Exception:
                pass

    # 6. Re-seed strictly 15 canonical cases
    DB._init_db()
    DB.seed_from_cases(CASES)

    # 7. Verification
    with DB.session_scope() as session:
        cand_count = session.query(Candidate).count()
        eval_count = session.query(Evaluation).count()
        doc_count = session.query(Document).count()

    print("\n[*] Cleanup & Reset Summary:")
    print(f"  - Uploaded files removed:            {stats['uploads_deleted']}")
    print(f"  - Custom trajectories removed:       {stats['custom_trajectories_deleted']}")
    print(f"  - Custom evaluation JSONs removed:   {stats['custom_eval_cases_deleted']}")
    print(f"  - Cache files removed:               {stats['cache_files_deleted']}")
    if deleted_db_file:
        print("  - Database files:                    Recreated fresh from scratch")
    else:
        print(f"  - Database rows cleared:             {stats['db_rows_cleared']}")
    print(f"\n[+] Canonical DB Re-seeding:")
    print(f"  - Canonical candidates in DB:        {cand_count} (Expected: 15)")
    print(f"  - Evaluations in DB:                 {eval_count}")
    print(f"  - Ingested documents in DB:          {doc_count}")

    if cand_count == 15:
        print("\n[SUCCESS] Clean demo state verified: exactly 15 canonical cases present.")
        return 0
    else:
        print(f"\n[WARNING] Candidate count ({cand_count}) differs from expected 15.")
        return 1


if __name__ == "__main__":
    sys.exit(reset_demo_data())
