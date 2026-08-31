"""
SQLite Database Layer for HireTrace.

Provides persistent, indexed storage for:
- Candidates & metadata
- Multi-source documents & raw file tracking
- Evaluation reports & baseline scores
- Background job queue state
- SHA-256 deduplication hashes
- Query pagination, search, and quadrant filtering
"""

import os
import re
import json
import time
import uuid
import sqlite3
import threading
from typing import Dict, Any, List, Optional, Tuple

DB_FILENAME = "hiretrace.db"


class DatabaseManager:
    """Thread-safe SQLite database manager for HireTrace."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(root_dir, DB_FILENAME)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    # 1. Candidates table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS candidates (
                            candidate_id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            target_role TEXT NOT NULL,
                            category TEXT DEFAULT 'applicant',
                            status TEXT DEFAULT 'done',
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_name ON candidates(name);")

                    # 2. Documents table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS documents (
                            id TEXT PRIMARY KEY,
                            candidate_id TEXT NOT NULL,
                            doc_type TEXT NOT NULL,
                            raw_path TEXT,
                            parsed_text TEXT,
                            sha256_hash TEXT,
                            byte_size INTEGER DEFAULT 0,
                            created_at REAL NOT NULL,
                            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_cand_type ON documents(candidate_id, doc_type);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_hash ON documents(sha256_hash);")

                    # 3. Evaluations table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS evaluations (
                            id TEXT PRIMARY KEY,
                            candidate_id TEXT UNIQUE NOT NULL,
                            role_fit_score REAL,
                            evidence_consistency_score REAL,
                            quadrant TEXT,
                            report_json TEXT,
                            baseline_a_json TEXT,
                            latency_ms REAL DEFAULT 0,
                            created_at REAL NOT NULL,
                            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_evals_quadrant ON evaluations(quadrant);")

                    # 4. Job queue table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS job_queue (
                            id TEXT PRIMARY KEY,
                            candidate_id TEXT UNIQUE NOT NULL,
                            status TEXT NOT NULL,
                            progress_pct INTEGER DEFAULT 0,
                            current_step TEXT,
                            attempts INTEGER DEFAULT 0,
                            error_msg TEXT,
                            enqueued_at REAL NOT NULL,
                            started_at REAL,
                            finished_at REAL
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_queue(status);")

                    # 5. Deduplication hashes table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS dedup_hashes (
                            sha256 TEXT PRIMARY KEY,
                            candidate_id TEXT NOT NULL,
                            doc_type TEXT NOT NULL,
                            created_at REAL NOT NULL
                        );
                    """)
            finally:
                conn.close()

    def upsert_candidate(
        self,
        candidate_id: str,
        name: str,
        target_role: str,
        category: str = "applicant",
        status: str = "done"
    ):
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO candidates (candidate_id, name, target_role, category, status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(candidate_id) DO UPDATE SET
                            name=excluded.name,
                            target_role=excluded.target_role,
                            category=excluded.category,
                            status=excluded.status,
                            updated_at=excluded.updated_at;
                    """, (candidate_id, name, target_role, category, status, now, now))
            finally:
                conn.close()

    def save_documents(
        self,
        candidate_id: str,
        docs_text: Dict[str, str],
        raw_meta: Optional[Dict[str, Any]] = None
    ):
        raw_meta = raw_meta or {}
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    for dtype, text in docs_text.items():
                        meta = raw_meta.get(dtype, {})
                        raw_path = meta.get("disk_path", "")
                        sha = meta.get("sha256", "")
                        size = meta.get("size_bytes", len(text.encode("utf-8")) if text else 0)
                        doc_id = f"{candidate_id}_{dtype}"

                        conn.execute("""
                            INSERT INTO documents (id, candidate_id, doc_type, raw_path, parsed_text, sha256_hash, byte_size, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                raw_path=excluded.raw_path,
                                parsed_text=excluded.parsed_text,
                                sha256_hash=excluded.sha256_hash,
                                byte_size=excluded.byte_size;
                        """, (doc_id, candidate_id, dtype, raw_path, text, sha, size, now))

                        if sha and dtype == "cv":
                            conn.execute("""
                                INSERT INTO dedup_hashes (sha256, candidate_id, doc_type, created_at)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(sha256) DO NOTHING;
                            """, (sha, candidate_id, dtype, now))
            finally:
                conn.close()

    def save_evaluation(
        self,
        candidate_id: str,
        role_fit_score: float,
        evidence_consistency_score: float,
        quadrant: str,
        report_dict: Dict[str, Any],
        baseline_a_dict: Optional[Dict[str, Any]] = None,
        latency_ms: float = 0
    ):
        now = time.time()
        eval_id = f"eval_{candidate_id}"
        report_json = json.dumps(report_dict) if report_dict else "{}"
        baseline_json = json.dumps(baseline_a_dict) if baseline_a_dict else "{}"

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO evaluations (id, candidate_id, role_fit_score, evidence_consistency_score, quadrant, report_json, baseline_a_json, latency_ms, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(candidate_id) DO UPDATE SET
                            role_fit_score=excluded.role_fit_score,
                            evidence_consistency_score=excluded.evidence_consistency_score,
                            quadrant=excluded.quadrant,
                            report_json=excluded.report_json,
                            baseline_a_json=excluded.baseline_a_json,
                            latency_ms=excluded.latency_ms;
                    """, (eval_id, candidate_id, role_fit_score, evidence_consistency_score, quadrant, report_json, baseline_json, latency_ms, now))

                    # Update candidate status to done
                    conn.execute("UPDATE candidates SET status='done', updated_at=? WHERE candidate_id=?;", (now, candidate_id))
            finally:
                conn.close()

    def get_candidate_full(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                cand_row = conn.execute("SELECT * FROM candidates WHERE candidate_id=?;", (candidate_id,)).fetchone()
                if not cand_row:
                    return None

                doc_rows = conn.execute("SELECT * FROM documents WHERE candidate_id=?;", (candidate_id,)).fetchall()
                eval_row = conn.execute("SELECT * FROM evaluations WHERE candidate_id=?;", (candidate_id,)).fetchone()

                docs_map = {}
                raw_meta = {}
                for d in doc_rows:
                    dtype = d["doc_type"]
                    docs_map[dtype] = d["parsed_text"] or ""
                    if d["raw_path"] or d["sha256_hash"]:
                        raw_meta[dtype] = {
                            "disk_path": d["raw_path"],
                            "sha256": d["sha256_hash"],
                            "size_bytes": d["byte_size"]
                        }

                report = json.loads(eval_row["report_json"]) if eval_row and eval_row["report_json"] else None
                baseline = json.loads(eval_row["baseline_a_json"]) if eval_row and eval_row["baseline_a_json"] else None

                return {
                    "candidate_id": cand_row["candidate_id"],
                    "name": cand_row["name"],
                    "target_role": cand_row["target_role"],
                    "category": cand_row["category"],
                    "status": cand_row["status"],
                    "cv_text": docs_map.get("cv", ""),
                    "interview_notes": docs_map.get("interview", ""),
                    "technical_assessment": docs_map.get("assessment", ""),
                    "project_rfc": docs_map.get("project", ""),
                    "raw_documents": raw_meta,
                    "evaluation_report": report,
                    "rubric_baseline": baseline,
                    "role_fit_score": eval_row["role_fit_score"] if eval_row else None,
                    "evidence_consistency_score": eval_row["evidence_consistency_score"] if eval_row else None,
                    "quadrant": eval_row["quadrant"] if eval_row else None,
                    "created_at": cand_row["created_at"],
                    "updated_at": cand_row["updated_at"]
                }
            finally:
                conn.close()

    def list_candidates(
        self,
        page: int = 1,
        limit: int = 50,
        status: Optional[str] = None,
        quadrant: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """Paginated, filtered candidate summary query."""
        page = max(1, page)
        limit = max(1, min(200, limit))
        offset = (page - 1) * limit

        where_clauses = []
        params: List[Any] = []

        if status:
            where_clauses.append("c.status = ?")
            params.append(status)

        if quadrant:
            where_clauses.append("e.quadrant = ?")
            params.append(quadrant)

        if search:
            where_clauses.append("(c.name LIKE ? OR c.target_role LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with self._lock:
            conn = self._get_connection()
            try:
                # Count total
                count_query = f"""
                    SELECT COUNT(*) as cnt
                    FROM candidates c
                    LEFT JOIN evaluations e ON c.candidate_id = e.candidate_id
                    {where_sql};
                """
                total = conn.execute(count_query, params).fetchone()["cnt"]

                # Fetch page items
                data_query = f"""
                    SELECT
                        c.candidate_id,
                        c.name,
                        c.target_role,
                        c.category,
                        c.status,
                        e.role_fit_score,
                        e.evidence_consistency_score,
                        e.quadrant,
                        e.report_json
                    FROM candidates c
                    LEFT JOIN evaluations e ON c.candidate_id = e.candidate_id
                    {where_sql}
                    ORDER BY c.created_at DESC
                    LIMIT ? OFFSET ?;
                """
                rows = conn.execute(data_query, params + [limit, offset]).fetchall()

                items = []
                for r in rows:
                    has_disc = False
                    if r["report_json"]:
                        try:
                            rep = json.loads(r["report_json"])
                            has_disc = len(rep.get("critical_discrepancies", [])) > 0
                        except Exception:
                            pass

                    items.append({
                        "candidate_id": r["candidate_id"],
                        "name": r["name"],
                        "target_role": r["target_role"],
                        "category": r["category"],
                        "status": r["status"] or "done",
                        "role_fit_score": r["role_fit_score"],
                        "evidence_consistency_score": r["evidence_consistency_score"],
                        "quadrant": r["quadrant"] or ("EVALUATING" if r["status"] == "evaluating" else "UNKNOWN"),
                        "has_discrepancies": has_disc
                    })

                pages = (total + limit - 1) // limit if total > 0 else 1
                return {
                    "items": items,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "pages": pages
                }
            finally:
                conn.close()

    def check_dedup_hash(self, sha256_hash: str) -> Optional[str]:
        if not sha256_hash:
            return None
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("SELECT candidate_id FROM dedup_hashes WHERE sha256=?;", (sha256_hash,)).fetchone()
                return row["candidate_id"] if row else None
            finally:
                conn.close()

    def save_job(
        self,
        candidate_id: str,
        status: str,
        progress_pct: int = 0,
        current_step: str = "",
        error_msg: Optional[str] = None
    ):
        now = time.time()
        job_id = f"job_{candidate_id}"
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO job_queue (id, candidate_id, status, progress_pct, current_step, error_msg, enqueued_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(candidate_id) DO UPDATE SET
                            status=excluded.status,
                            progress_pct=excluded.progress_pct,
                            current_step=excluded.current_step,
                            error_msg=excluded.error_msg,
                            finished_at=CASE WHEN excluded.status IN ('done', 'failed') THEN ? ELSE finished_at END;
                    """ if False else """
                        INSERT INTO job_queue (id, candidate_id, status, progress_pct, current_step, error_msg, enqueued_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(candidate_id) DO UPDATE SET
                            status=excluded.status,
                            progress_pct=excluded.progress_pct,
                            current_step=excluded.current_step,
                            error_msg=excluded.error_msg,
                            finished_at=CASE WHEN excluded.status IN ('done', 'failed') THEN ? ELSE finished_at END;
                    """, (job_id, candidate_id, status, progress_pct, current_step, error_msg, now, now))
            finally:
                conn.close()

    def seed_from_cases(self, cases_list: List[Dict[str, Any]]):
        """Seeds SQLite database from in-memory / JSON cases list on startup."""
        for c in cases_list:
            cid = c.get("candidate_id")
            if not cid:
                continue

            self.upsert_candidate(
                candidate_id=cid,
                name=c.get("name", "Unknown Candidate"),
                target_role=c.get("target_role", "Senior Software Engineer"),
                category=c.get("category", "applicant"),
                status=c.get("status", "done")
            )

            # Documents
            docs_text = {
                "cv": c.get("cv_text", ""),
                "interview": c.get("interview_notes", ""),
                "assessment": c.get("technical_assessment", ""),
                "project": c.get("project_rfc", "")
            }
            self.save_documents(cid, docs_text, c.get("raw_documents"))

            # Evaluations
            rep = c.get("evaluation_report")
            rubric = c.get("rubric_baseline")
            if rep:
                self.save_evaluation(
                    candidate_id=cid,
                    role_fit_score=c.get("role_fit_score", rep.get("role_fit_score", 0.0)),
                    evidence_consistency_score=c.get("evidence_consistency_score", rep.get("evidence_consistency_score", 0.0)),
                    quadrant=c.get("quadrant", rep.get("quadrant", "UNKNOWN")),
                    report_dict=rep,
                    baseline_a_dict=rubric
                )


# Global singleton database manager
DB = DatabaseManager()
