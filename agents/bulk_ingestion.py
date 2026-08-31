"""
Bulk Ingestion Engine for HireTrace.

Handles high-volume intake of applicant dossiers from:
1. ZIP archives (.zip)
2. Folder directory uploads (webkitdirectory multi-file payloads)
3. Flat batches of standalone resumes

Includes:
- Automatic folder grouping (one subfolder = one candidate dossier)
- Filename heuristic document classification (cv, interview, assessment, project)
- SHA-256 deduplication (skips re-evaluation of identical files)
- Real-time batch progress metrics (Uploaded -> Parsed -> Queued -> Evaluated)
"""

import os
import io
import re
import time
import zipfile
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from agents.document_parser import (
    extract_text,
    infer_document_type,
    compute_file_hash
)
from agents.job_manager import JOB_MANAGER, JobManager
from agents.pipeline import HireTracePipeline
from agents.db import DB



@dataclass
class BatchJob:
    batch_id: str
    total_files: int = 0
    uploaded: int = 0
    parsed: int = 0
    queued: int = 0
    evaluated: int = 0
    duplicates: int = 0
    failed: int = 0
    status: str = "processing"  # "processing", "completed", "failed"
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def progress_pct(self) -> int:
        target = self.queued
        if target <= 0:
            return 100 if self.uploaded > 0 else 0
        done_count = self.evaluated + self.failed
        return min(100, int((done_count / target) * 100))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total_files": self.total_files,
            "uploaded": self.uploaded,
            "parsed": self.parsed,
            "queued": self.queued,
            "evaluated": self.evaluated,
            "duplicates": self.duplicates,
            "failed": self.failed,
            "status": "completed" if (self.queued > 0 and (self.evaluated + self.failed) >= self.queued) else self.status,
            "progress_pct": self.progress_pct,
            "candidates": self.candidates,
            "errors": self.errors,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


def format_candidate_name(raw_name: str) -> str:
    """Formats clean human-readable name from folder or file slug."""
    clean = re.sub(r'[\-_.]+', ' ', raw_name).strip()
    clean = re.sub(r'\b(cv|resume|interview|assessment|project|rfc|doc|pdf|docx|txt|md)\b', '', clean, flags=re.IGNORECASE).strip()
    words = [w.capitalize() for w in clean.split() if w]
    return " ".join(words) if words else "Unknown Candidate"


class BulkIngestionEngine:
    """Coordinates batch unpacking, grouping, deduplication, and pipeline dispatch."""

    def __init__(self):
        self._batches: Dict[str, BatchJob] = {}
        self._dedup_hashes: Dict[str, str] = {}  # sha256 -> candidate_id
        self._lock = threading.Lock()

    def register_existing_hash(self, sha256_hash: str, candidate_id: str):
        with self._lock:
            self._dedup_hashes[sha256_hash] = candidate_id

    def get_batch(self, batch_id: str) -> Optional[BatchJob]:
        with self._lock:
            return self._batches.get(batch_id)

    def _is_noise_file(self, filename: str) -> bool:
        base = os.path.basename(filename)
        return (
            base.startswith(".") or
            base.startswith("~") or
            "__MACOSX" in filename or
            base in ("Thumbs.db", "desktop.ini", ".DS_Store")
        )

    def process_archive(
        self,
        zip_bytes: bytes,
        batch_id: str,
        target_role: str,
        uploads_root: str,
        cases_dir: str,
        pipeline: HireTracePipeline,
        all_cases_list: list
    ) -> BatchJob:
        """Unpacks a .zip archive, groups candidate dossiers, and queues unique evaluations."""
        with self._lock:
            batch = BatchJob(batch_id=batch_id)
            self._batches[batch_id] = batch

        files_map: Dict[str, bytes] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                for info in z.infolist():
                    if info.is_dir() or self._is_noise_file(info.filename):
                        continue
                    files_map[info.filename.replace("\\", "/")] = z.read(info.filename)
        except Exception as err:
            batch.status = "failed"
            batch.errors.append(f"Failed to read ZIP archive: {err}")
            return batch

        return self.process_file_tree(
            files_map=files_map,
            batch_id=batch_id,
            target_role=target_role,
            uploads_root=uploads_root,
            cases_dir=cases_dir,
            pipeline=pipeline,
            all_cases_list=all_cases_list
        )

    def process_file_tree(
        self,
        files_map: Dict[str, bytes],
        batch_id: str,
        target_role: str,
        uploads_root: str,
        cases_dir: str,
        pipeline: HireTracePipeline,
        all_cases_list: list
    ) -> BatchJob:
        """Groups files by subfolder or standalone resume, dedupes, and submits to worker pool."""
        with self._lock:
            if batch_id not in self._batches:
                self._batches[batch_id] = BatchJob(batch_id=batch_id)
            batch = self._batches[batch_id]

        batch.total_files = len(files_map)
        batch.uploaded = len(files_map)

        # 1. Group files by candidate folder
        # Supported structures:
        #   applicants/jane_doe/cv.pdf, applicants/jane_doe/interview.txt
        #   jane_doe/cv.pdf
        #   flat: jane_doe.pdf, john_smith.docx
        candidate_groups: Dict[str, List[Tuple[str, bytes]]] = {}

        for path_str, data in files_map.items():
            if self._is_noise_file(path_str):
                continue

            parts = [p for p in path_str.strip("/").split("/") if p]
            if len(parts) >= 2:
                # Subfolder structure: ignore top generic folder like "applicants" or "resumes"
                if len(parts) >= 3 and parts[0].lower() in ("applicants", "resumes", "candidates", "eval_cases", "batch"):
                    cand_key = parts[1]
                else:
                    cand_key = parts[0]
            else:
                # Flat file structure: file name without extension is candidate key
                cand_key = os.path.splitext(parts[0])[0]

            if cand_key not in candidate_groups:
                candidate_groups[cand_key] = []
            candidate_groups[cand_key].append((path_str, data))

        # 2. Process each candidate dossier
        for cand_key, file_items in candidate_groups.items():
            cand_name = format_candidate_name(cand_key)
            slug = re.sub(r'[^a-zA-Z0-9_]', '_', cand_key.lower())[:24]
            unique_token = time.strftime("%H%M%S") + os.urandom(2).hex()
            cid = f"custom_bulk_{slug}_{unique_token}"

            cand_upload_dir = os.path.join(uploads_root, cid)
            raw_docs_meta: Dict[str, Any] = {}
            doc_texts: Dict[str, str] = {
                "cv": "",
                "interview": "",
                "assessment": "",
                "project": ""
            }

            cv_hash = ""
            has_cv = False

            # Sort items so CV is processed first if possible
            sorted_items = sorted(
                file_items,
                key=lambda item: 0 if infer_document_type(item[0]) == "cv" else 1
            )

            for rel_path, fbytes in sorted_items:
                orig_fname = os.path.basename(rel_path)
                ext = os.path.splitext(orig_fname)[1].lower()
                if ext not in (".pdf", ".docx", ".txt", ".md"):
                    continue

                dtype = infer_document_type(orig_fname)
                fhash = compute_file_hash(fbytes)

                if dtype == "cv" and not has_cv:
                    cv_hash = fhash
                    has_cv = True

                # Save raw source document to disk
                os.makedirs(cand_upload_dir, exist_ok=True)
                clean_fname = re.sub(r'[^a-zA-Z0-9_.-]', '_', orig_fname)
                save_path = os.path.join(cand_upload_dir, f"{dtype}_{clean_fname}")
                with open(save_path, "wb") as f:
                    f.write(fbytes)

                raw_docs_meta[dtype] = {
                    "filename": orig_fname,
                    "disk_path": save_path,
                    "sha256": fhash,
                    "size_bytes": len(fbytes)
                }

                # Extract text
                try:
                    text_val = extract_text(save_path, filename_hint=orig_fname)
                    doc_texts[dtype] = text_val
                except Exception as ex:
                    batch.errors.append(f"Extraction failed for {orig_fname}: {ex}")

            # If no explicit CV was identified but files exist, use the first file as CV
            if not doc_texts["cv"]:
                for dt, txt in doc_texts.items():
                    if txt:
                        doc_texts["cv"] = txt
                        if not cv_hash and dt in raw_docs_meta:
                            cv_hash = raw_docs_meta[dt]["sha256"]
                        break

            if not doc_texts["cv"]:
                batch.errors.append(f"Candidate {cand_name} has no parseable CV document.")
                continue

            batch.parsed += 1

            # 3. Deduplication Check via SHA-256
            is_dup = False
            with self._lock:
                if cv_hash and cv_hash in self._dedup_hashes:
                    existing_cid = self._dedup_hashes[cv_hash]
                    is_dup = True
                elif cv_hash:
                    # Check SQLite DB
                    db_cid = DB.check_dedup_hash(cv_hash)
                    if db_cid:
                        cfile = os.path.join(cases_dir, f"{db_cid}.json")
                        if os.path.exists(cfile):
                            self._dedup_hashes[cv_hash] = db_cid
                            existing_cid = db_cid
                            is_dup = True

                    if not is_dup:
                        # Also check ALL_CASES if file exists on disk
                        for existing_case in all_cases_list:
                            existing_meta = existing_case.get("raw_documents", {})
                            if existing_meta.get("cv", {}).get("sha256") == cv_hash:
                                existing_cid = existing_case.get("candidate_id")
                                if existing_cid:
                                    cfile = os.path.join(cases_dir, f"{existing_cid}.json")
                                    if os.path.exists(cfile):
                                        self._dedup_hashes[cv_hash] = existing_cid
                                        is_dup = True
                                        break

            if is_dup:
                batch.duplicates += 1
                batch.candidates.append({
                    "candidate_id": existing_cid,
                    "name": cand_name,
                    "status": "duplicate_skipped",
                    "existing_candidate_id": existing_cid,
                    "sha256": cv_hash
                })
                continue

            # Register hash
            if cv_hash:
                with self._lock:
                    self._dedup_hashes[cv_hash] = cid

            # 4. Create new candidate dossier & Enqueue
            new_case = {
                "candidate_id": cid,
                "name": cand_name,
                "target_role": target_role or "Senior Python & Distributed Systems Engineer",
                "category": "live_applicant",
                "cv_text": doc_texts["cv"],
                "interview_notes": doc_texts["interview"],
                "technical_assessment": doc_texts["assessment"],
                "project_rfc": doc_texts["project"],
                "jd_text": "",
                "raw_documents": raw_docs_meta,
                "status": "queued"
            }

            # Persist initial stub to disk and SQLite DB
            case_file = os.path.join(cases_dir, f"{cid}.json")
            import json
            with open(case_file, "w", encoding="utf-8") as f:
                json.dump(new_case, f, indent=2)

            DB.upsert_candidate(cid, cand_name, target_role, "live_applicant", "queued")
            DB.save_documents(cid, doc_texts, raw_docs_meta)


            all_cases_list.append(new_case)
            batch.queued += 1
            batch.candidates.append({
                "candidate_id": cid,
                "name": cand_name,
                "status": "queued",
                "sha256": cv_hash
            })

            # Submit to background worker pool
            def make_on_complete(b: BatchJob, target_cid: str):
                def _callback(completed_case):
                    b.evaluated += 1
                    b.updated_at = time.time()
                    for cand_entry in b.candidates:
                        if cand_entry.get("candidate_id") == target_cid:
                            cand_entry["status"] = "done"
                            cand_entry["role_fit_score"] = completed_case.get("role_fit_score")
                            cand_entry["evidence_consistency_score"] = completed_case.get("evidence_consistency_score")
                            cand_entry["quadrant"] = completed_case.get("quadrant")
                            break
                return _callback

            JOB_MANAGER.submit_evaluation(
                new_case,
                pipeline,
                cases_dir,
                all_cases_list,
                on_complete=make_on_complete(batch, cid)
            )

        batch.updated_at = time.time()
        return batch


# Global singleton bulk ingestion engine
BULK_ENGINE = BulkIngestionEngine()
