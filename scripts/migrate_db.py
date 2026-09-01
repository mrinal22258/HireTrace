"""
Database Migration Script for HireTrace.

Transfers schema and existing data between database backends (e.g. SQLite -> PostgreSQL).
Usage:
    python scripts/migrate_db.py --check
    python scripts/migrate_db.py --source sqlite:///hiretrace.db --target postgresql://user:pass@localhost:5432/hiretrace
"""

import os
import sys
import argparse
import time
from typing import Optional

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from agents.db import (
    Base, Candidate, Document, Evaluation, JobQueue, DedupHash, RequirementCache,
    DB_FILENAME
)


def run_migration(source_url: str, target_url: str):
    print(f"=== HireTrace Database Migration ===")
    print(f"Source: {source_url}")
    print(f"Target: {target_url}")

    if target_url.startswith("postgres://"):
        target_url = "postgresql://" + target_url[len("postgres://"):]
    if source_url.startswith("postgres://"):
        source_url = "postgresql://" + source_url[len("postgres://"):]

    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)

    # 1. Create all tables on target
    print("\n[1/3] Initializing schema on target database...")
    Base.metadata.create_all(tgt_engine)
    print("Schema initialized successfully.")

    SrcSession = sessionmaker(bind=src_engine)
    TgtSession = sessionmaker(bind=tgt_engine)

    src_sess = SrcSession()
    tgt_sess = TgtSession()

    try:
        print("\n[2/3] Migrating table data...")
        tables = [
            ("Candidates", Candidate),
            ("Documents", Document),
            ("Evaluations", Evaluation),
            ("JobQueue", JobQueue),
            ("DedupHash", DedupHash),
            ("RequirementCache", RequirementCache)
        ]

        total_migrated = 0
        for name, model in tables:
            try:
                rows = src_sess.query(model).all()
                count = 0
                for r in rows:
                    # Detach from source session
                    src_sess.expunge(r)
                    tgt_sess.merge(r)
                    count += 1
                tgt_sess.commit()
                print(f"  -> {name}: {count} records migrated")
                total_migrated += count
            except Exception as e:
                tgt_sess.rollback()
                print(f"  -> {name}: Skipped / Error: {e}")

        print(f"\n[3/3] Migration finished: {total_migrated} total records transferred.")

    finally:
        src_sess.close()
        tgt_sess.close()


def check_connection(target_url: Optional[str] = None):
    url = target_url or os.getenv("DATABASE_URL")
    if not url:
        abs_db = os.path.join(root_dir, DB_FILENAME).replace("\\", "/")
        url = f"sqlite:///{abs_db}"
        print(f"No DATABASE_URL configured. Using zero-config local SQLite: {url}")
    else:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        print(f"Configured DATABASE_URL: {url}")

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            print("Successfully connected to database!")
            Base.metadata.create_all(engine)
            print("Schema verified: All HireTrace tables exist.")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HireTrace Database Migration Utility")
    parser.add_argument("--check", action="store_true", help="Verify database connection and schema")
    parser.add_argument("--source", type=str, default=None, help="Source database URL")
    parser.add_argument("--target", type=str, default=None, help="Target database URL")

    args = parser.parse_args()

    if args.check:
        check_connection(args.target)
    else:
        src = args.source or f"sqlite:///{os.path.join(root_dir, DB_FILENAME).replace('\\', '/')}"
        tgt = args.target or os.getenv("DATABASE_URL")
        if not tgt:
            print("Error: Specify --target <db_url> or set DATABASE_URL environment variable.")
            sys.exit(1)
        run_migration(src, tgt)
