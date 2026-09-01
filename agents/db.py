"""
Database Layer for HireTrace.

Connection-pooled, Postgres-compatible database layer using SQLAlchemy 2.0.
Supports zero-config local development (SQLite default with WAL mode)
and single-env-var production deployment via DATABASE_URL (PostgreSQL).

Provides persistent storage for:
- Candidates & metadata
- Multi-source documents & raw file tracking
- Evaluation reports & baseline scores
- Background job queue state
- SHA-256 deduplication hashes
- Requirement mapping cache (SHA-256 keyed)
- Query pagination, search, and quadrant filtering
"""

import os
import json
import time
import threading
from typing import Dict, Any, List, Optional
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Text, ForeignKey,
    select, func, or_, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, relationship
from sqlalchemy.pool import QueuePool, NullPool

DB_FILENAME = "hiretrace.db"
Base = declarative_base()


class Candidate(Base):
    __tablename__ = "candidates"

    candidate_id = Column(String(128), primary_key=True)
    name = Column(String(256), nullable=False, index=True)
    target_role = Column(String(256), nullable=False)
    category = Column(String(64), default="applicant")
    status = Column(String(64), default="done", index=True)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    documents = relationship("Document", back_populates="candidate", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", back_populates="candidate", uselist=False, cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(256), primary_key=True)
    candidate_id = Column(String(128), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type = Column(String(64), nullable=False, index=True)
    raw_path = Column(String(1024), nullable=True)
    parsed_text = Column(Text, nullable=True)
    sha256_hash = Column(String(64), nullable=True, index=True)
    byte_size = Column(Integer, default=0)
    created_at = Column(Float, nullable=False)

    candidate = relationship("Candidate", back_populates="documents")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(String(256), primary_key=True)
    candidate_id = Column(String(128), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), unique=True, nullable=False)
    role_fit_score = Column(Float, nullable=True)
    evidence_consistency_score = Column(Float, nullable=True)
    quadrant = Column(String(64), nullable=True, index=True)
    report_json = Column(Text, nullable=True)
    baseline_a_json = Column(Text, nullable=True)
    latency_ms = Column(Float, default=0.0)
    created_at = Column(Float, nullable=False)

    candidate = relationship("Candidate", back_populates="evaluation")


class JobQueue(Base):
    __tablename__ = "job_queue"

    id = Column(String(256), primary_key=True)
    candidate_id = Column(String(128), unique=True, nullable=False)
    status = Column(String(64), nullable=False, index=True)
    progress_pct = Column(Integer, default=0)
    current_step = Column(String(512), nullable=True)
    attempts = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)
    enqueued_at = Column(Float, nullable=False)
    started_at = Column(Float, nullable=True)
    finished_at = Column(Float, nullable=True)


class DedupHash(Base):
    __tablename__ = "dedup_hashes"

    sha256 = Column(String(64), primary_key=True)
    candidate_id = Column(String(128), nullable=False)
    doc_type = Column(String(64), nullable=False)
    created_at = Column(Float, nullable=False)


class RequirementCache(Base):
    __tablename__ = "requirement_cache"

    cache_key = Column(String(64), primary_key=True)
    target_role = Column(String(256), nullable=False)
    requirements_json = Column(Text, nullable=False)
    created_at = Column(Float, nullable=False)


class DatabaseManager:
    """Connection-pooled SQLAlchemy database manager for HireTrace."""

    def __init__(self, db_path: Optional[str] = None, database_url: Optional[str] = None):
        url = database_url or os.getenv("DATABASE_URL")
        self.is_sqlite = False

        if not url:
            if not db_path:
                root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(root_dir, DB_FILENAME)
            abs_path = os.path.abspath(db_path).replace("\\", "/")
            url = f"sqlite:///{abs_path}"
            self.is_sqlite = True
        else:
            # Normalize postgres:// to postgresql:// for SQLAlchemy compatibility
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://"):]
            self.is_sqlite = url.startswith("sqlite")

        self.database_url = url

        if self.is_sqlite:
            self.engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True
            )
            # Enable WAL mode and normal synchronous for high concurrent reads/writes
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
        else:
            # Production Postgres connection pool
            self.engine = create_engine(
                url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=1800
            )

        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.Session = scoped_session(self._session_factory)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        """Returns a raw DBAPI connection with auto-commit semantics for legacy test harnesses."""
        raw = self.engine.raw_connection()

        class _AutoCommitConn:
            def __init__(self, raw_conn):
                self._raw = raw_conn

            def execute(self, sql, *args):
                cursor = self._raw.cursor()
                res = cursor.execute(sql, *args)
                self._raw.commit()
                return res

            def commit(self):
                self._raw.commit()

            def close(self):
                try:
                    self._raw.commit()
                except Exception:
                    pass
                self._raw.close()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    self._raw.commit()
                else:
                    self._raw.rollback()

        return _AutoCommitConn(raw)

    def _init_db(self):
        """Initializes tables if they do not exist."""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_candidate(
        self,
        candidate_id: str,
        name: str,
        target_role: str,
        category: str = "applicant",
        status: str = "done"
    ):
        now = time.time()
        with self.session_scope() as session:
            cand = session.query(Candidate).filter_by(candidate_id=candidate_id).first()
            if cand:
                cand.name = name
                cand.target_role = target_role
                cand.category = category
                cand.status = status
                cand.updated_at = now
            else:
                cand = Candidate(
                    candidate_id=candidate_id,
                    name=name,
                    target_role=target_role,
                    category=category,
                    status=status,
                    created_at=now,
                    updated_at=now
                )
                session.add(cand)

    def save_documents(
        self,
        candidate_id: str,
        docs_text: Dict[str, str],
        raw_meta: Optional[Dict[str, Any]] = None
    ):
        raw_meta = raw_meta or {}
        now = time.time()
        with self.session_scope() as session:
            for dtype, text in docs_text.items():
                meta = raw_meta.get(dtype, {})
                raw_path = meta.get("disk_path", "")
                sha = meta.get("sha256", "")
                size = meta.get("size_bytes", len(text.encode("utf-8")) if text else 0)
                doc_id = f"{candidate_id}_{dtype}"

                doc = session.query(Document).filter_by(id=doc_id).first()
                if doc:
                    doc.raw_path = raw_path
                    doc.parsed_text = text
                    doc.sha256_hash = sha
                    doc.byte_size = size
                else:
                    doc = Document(
                        id=doc_id,
                        candidate_id=candidate_id,
                        doc_type=dtype,
                        raw_path=raw_path,
                        parsed_text=text,
                        sha256_hash=sha,
                        byte_size=size,
                        created_at=now
                    )
                    session.add(doc)

                if sha and dtype == "cv":
                    existing_hash = session.query(DedupHash).filter_by(sha256=sha).first()
                    if not existing_hash:
                        session.add(DedupHash(
                            sha256=sha,
                            candidate_id=candidate_id,
                            doc_type=dtype,
                            created_at=now
                        ))

    def save_evaluation(
        self,
        candidate_id: str,
        role_fit_score: Optional[float],
        evidence_consistency_score: Optional[float],
        quadrant: str,
        report_dict: Dict[str, Any],
        baseline_a_dict: Optional[Dict[str, Any]] = None,
        latency_ms: float = 0
    ):
        now = time.time()
        eval_id = f"eval_{candidate_id}"
        report_json = json.dumps(report_dict) if report_dict else "{}"
        baseline_json = json.dumps(baseline_a_dict) if baseline_a_dict else "{}"

        with self.session_scope() as session:
            ev = session.query(Evaluation).filter_by(candidate_id=candidate_id).first()
            if ev:
                ev.role_fit_score = role_fit_score
                ev.evidence_consistency_score = evidence_consistency_score
                ev.quadrant = quadrant
                ev.report_json = report_json
                ev.baseline_a_json = baseline_json
                ev.latency_ms = latency_ms
            else:
                ev = Evaluation(
                    id=eval_id,
                    candidate_id=candidate_id,
                    role_fit_score=role_fit_score,
                    evidence_consistency_score=evidence_consistency_score,
                    quadrant=quadrant,
                    report_json=report_json,
                    baseline_a_json=baseline_json,
                    latency_ms=latency_ms,
                    created_at=now
                )
                session.add(ev)

            cand = session.query(Candidate).filter_by(candidate_id=candidate_id).first()
            if cand:
                cand.status = "done"
                cand.updated_at = now

    def get_evaluation(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        with self.session_scope() as session:
            ev = session.query(Evaluation).filter_by(candidate_id=candidate_id).first()
            if not ev:
                return None
            report = json.loads(ev.report_json) if ev.report_json else None
            baseline = json.loads(ev.baseline_a_json) if ev.baseline_a_json else None
            return {
                "candidate_id": ev.candidate_id,
                "role_fit_score": ev.role_fit_score,
                "evidence_consistency_score": ev.evidence_consistency_score,
                "quadrant": ev.quadrant,
                "report": report,
                "baseline_a": baseline,
                "latency_ms": ev.latency_ms,
                "created_at": ev.created_at
            }

    def get_candidate_full(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        with self.session_scope() as session:
            cand = session.query(Candidate).filter_by(candidate_id=candidate_id).first()
            if not cand:
                return None

            docs = session.query(Document).filter_by(candidate_id=candidate_id).all()
            ev = session.query(Evaluation).filter_by(candidate_id=candidate_id).first()

            docs_map = {}
            raw_meta = {}
            for d in docs:
                docs_map[d.doc_type] = d.parsed_text or ""
                if d.raw_path or d.sha256_hash:
                    raw_meta[d.doc_type] = {
                        "disk_path": d.raw_path,
                        "sha256": d.sha256_hash,
                        "size_bytes": d.byte_size
                    }

            report = json.loads(ev.report_json) if ev and ev.report_json else None
            baseline = json.loads(ev.baseline_a_json) if ev and ev.baseline_a_json else None

            return {
                "candidate_id": cand.candidate_id,
                "name": cand.name,
                "target_role": cand.target_role,
                "category": cand.category,
                "status": cand.status,
                "cv_text": docs_map.get("cv", ""),
                "interview_notes": docs_map.get("interview", ""),
                "technical_assessment": docs_map.get("assessment", ""),
                "project_rfc": docs_map.get("project", ""),
                "raw_documents": raw_meta,
                "evaluation_report": report,
                "rubric_baseline": baseline,
                "role_fit_score": ev.role_fit_score if ev else None,
                "evidence_consistency_score": ev.evidence_consistency_score if ev else None,
                "quadrant": ev.quadrant if ev else None,
                "created_at": cand.created_at,
                "updated_at": cand.updated_at
            }

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

        with self.session_scope() as session:
            query = session.query(
                Candidate.candidate_id,
                Candidate.name,
                Candidate.target_role,
                Candidate.category,
                Candidate.status,
                Evaluation.role_fit_score,
                Evaluation.evidence_consistency_score,
                Evaluation.quadrant,
                Evaluation.report_json
            ).outerjoin(Evaluation, Candidate.candidate_id == Evaluation.candidate_id)

            if status:
                query = query.filter(Candidate.status == status)

            if quadrant:
                query = query.filter(Evaluation.quadrant == quadrant)

            if search:
                pattern = f"%{search}%"
                query = query.filter(or_(Candidate.name.ilike(pattern), Candidate.target_role.ilike(pattern)))

            total = query.count()
            rows = query.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()

            items = []
            for r in rows:
                has_disc = False
                if r.report_json:
                    try:
                        rep = json.loads(r.report_json)
                        has_disc = len(rep.get("critical_discrepancies", [])) > 0
                    except Exception:
                        pass

                items.append({
                    "candidate_id": r.candidate_id,
                    "name": r.name,
                    "target_role": r.target_role,
                    "category": r.category,
                    "status": r.status or "done",
                    "role_fit_score": r.role_fit_score,
                    "evidence_consistency_score": r.evidence_consistency_score,
                    "quadrant": r.quadrant or ("EVALUATING" if r.status == "evaluating" else "UNKNOWN"),
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

    def check_dedup_hash(self, sha256_hash: str) -> Optional[str]:
        if not sha256_hash:
            return None
        with self.session_scope() as session:
            row = session.query(DedupHash).filter_by(sha256=sha256_hash).first()
            return row.candidate_id if row else None

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
        with self.session_scope() as session:
            job = session.query(JobQueue).filter_by(candidate_id=candidate_id).first()
            if job:
                job.status = status
                job.progress_pct = progress_pct
                job.current_step = current_step
                job.error_msg = error_msg
                if status in ("done", "failed"):
                    job.finished_at = now
            else:
                job = JobQueue(
                    id=job_id,
                    candidate_id=candidate_id,
                    status=status,
                    progress_pct=progress_pct,
                    current_step=current_step,
                    error_msg=error_msg,
                    enqueued_at=now,
                    finished_at=now if status in ("done", "failed") else None
                )
                session.add(job)

    # Requirement mapping cache methods for Step 5
    def get_cached_requirements(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        with self.session_scope() as session:
            entry = session.query(RequirementCache).filter_by(cache_key=cache_key).first()
            if entry and entry.requirements_json:
                try:
                    return json.loads(entry.requirements_json)
                except Exception:
                    return None
            return None

    def set_cached_requirements(self, cache_key: str, target_role: str, requirements_data: List[Dict[str, Any]]):
        now = time.time()
        req_json = json.dumps(requirements_data)
        with self.session_scope() as session:
            entry = session.query(RequirementCache).filter_by(cache_key=cache_key).first()
            if entry:
                entry.target_role = target_role
                entry.requirements_json = req_json
            else:
                session.add(RequirementCache(
                    cache_key=cache_key,
                    target_role=target_role,
                    requirements_json=req_json,
                    created_at=now
                ))

    def seed_from_cases(self, cases_list: List[Dict[str, Any]]):
        """Seeds database from in-memory / JSON cases list on startup."""
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
                    role_fit_score=c.get("role_fit_score", rep.get("role_fit_score")),
                    evidence_consistency_score=c.get("evidence_consistency_score", rep.get("evidence_consistency_score", 0.0)),
                    quadrant=c.get("quadrant", rep.get("quadrant", "UNKNOWN")),
                    report_dict=rep,
                    baseline_a_dict=rubric
                )


# Global singleton database manager
DB = DatabaseManager()

