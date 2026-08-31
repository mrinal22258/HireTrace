"""
Production UI Server for HireTrace.

Serves the light-pinkish assessment dashboard with strict security controls:
1. Universal dynamic applicant intake via POST /api/candidate/new with UUID generation and disk persistence.
2. Complete isolation of ground-truth answer keys from public API endpoints (zero answer leakage).
3. Whitelisted static file serving (blocks arbitrary project file exposure).
4. Strict input sanitization (regex allowlist ^[A-Za-z0-9_-]{1,128}$) and 10MB bounded body reads.
5. Reusable socket bindings to prevent WinError 10048.
"""

import http.server
from http.server import SimpleHTTPRequestHandler
import socketserver
import json
import os
import sys
import re
import time
import uuid
import urllib.parse
import email
import email.policy
from email.parser import BytesParser
from typing import Dict, Any, List, Optional, Tuple

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.pipeline import HireTracePipeline
from agents.document_parser import extract_text, compute_file_hash
from agents.job_manager import JOB_MANAGER
from agents.bulk_ingestion import BULK_ENGINE, BatchJob
from agents.db import DB
from baseline.rubric_scorer import RubricScorer

from eval_cases.dataset import CASES, SHARED_JD

CACHE_DIR = os.path.join(root_dir, "trajectories")
CASES_DIR = os.path.join(root_dir, "eval_cases")
UPLOADS_DIR = os.path.join(root_dir, "uploads")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(CASES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Shared singleton pipeline
PIPELINE = HireTracePipeline(trajectory_dir=CACHE_DIR)

# Combined in-memory candidate pool
ALL_CASES = list(CASES)

def load_saved_custom_cases():
    """Loads previously submitted custom applicant files from disk."""
    if not os.path.exists(CASES_DIR):
        return
    for fname in os.listdir(CASES_DIR):
        if fname.startswith("custom_") and fname.endswith(".json"):
            try:
                fpath = os.path.join(CASES_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    if not any(c["candidate_id"] == cdata["candidate_id"] for c in ALL_CASES):
                        ALL_CASES.append(cdata)
            except Exception as err:
                print(f"Warning: could not load custom case {fname}: {err}")

load_saved_custom_cases()

# Seed SQLite database on startup
DB.seed_from_cases(ALL_CASES)



def parse_multipart_payload(content_type: str, body: bytes) -> Tuple[Dict[str, str], Dict[str, Tuple[str, bytes]]]:
    """Parses multipart/form-data payload into fields and uploaded files."""
    form_fields: Dict[str, str] = {}
    files: Dict[str, Tuple[str, bytes]] = {}

    raw_mime = b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body
    msg = BytesParser(policy=email.policy.default).parsebytes(raw_mime)

    for part in msg.iter_parts():
        name = part.get_param("name", header="Content-Disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True)

        if not name:
            continue

        if filename:
            files[name] = (filename, payload or b"")
        else:
            charset = part.get_content_charset() or "utf-8"
            try:
                form_fields[name] = (payload or b"").decode(charset)
            except Exception:
                form_fields[name] = (payload or b"").decode("utf-8", errors="replace")

    return form_fields, files


class ReusableHTTPServer(socketserver.TCPServer):
    allow_reuse_address = True


class HireTraceHandler(SimpleHTTPRequestHandler):
    """Hardened HTTP request handler for HireTrace assessment dashboard."""

    def _send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)


        # 1. Main Dashboard UI
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            html_path = os.path.join(os.path.dirname(__file__), "index.html")
            with open(html_path, "rb") as f:
                self.wfile.write(f.read())
            return

        # Static precomputed data bundle
        elif path in ("/static_data.js", "/ui/static_data.js"):
            js_path = os.path.join(os.path.dirname(__file__), "static_data.js")
            if os.path.exists(js_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.end_headers()
                with open(js_path, "rb") as f:
                    self.wfile.write(f.read())
                return


        # 2. Public Candidate List (Zero Ground-Truth Answer Leakage, Paginated / Filterable)
        elif path == "/api/cases":
            # Check if pagination, quadrant, search, or status filters are requested
            if any(k in query for k in ("page", "limit", "quadrant", "status", "search")):
                page_val = int(query.get("page", ["1"])[0])
                limit_val = int(query.get("limit", ["50"])[0])
                status_val = query.get("status", [None])[0]
                quad_val = query.get("quadrant", [None])[0]
                search_val = query.get("search", [None])[0]

                res = DB.list_candidates(
                    page=page_val,
                    limit=limit_val,
                    status=status_val,
                    quadrant=quad_val,
                    search=search_val
                )
                self._send_json(res)
                return

            summary_list = []
            for c in ALL_CASES:
                cid = c["candidate_id"]
                traj_file = os.path.join(CACHE_DIR, f"{cid}_trajectory.json")
                fit_score = c.get("role_fit_score", 50.0)
                consistency_score = c.get("evidence_consistency_score", 50.0)
                quadrant = c.get("quadrant", "EVALUATING")
                has_disc = False

                if os.path.exists(traj_file):
                    try:
                        with open(traj_file, "r", encoding="utf-8") as f:
                            tdata = json.load(f)
                        for step in reversed(tdata.get("steps", [])):
                            if step.get("step") == "recommendation_writing":
                                out = step.get("output", {})
                                fit_score = out.get("role_fit_score", 50.0)
                                consistency_score = out.get("evidence_consistency_score", 50.0)
                                quadrant = out.get("quadrant", "REVIEW REQUIRED")
                                has_disc = len(out.get("key_discrepancies", [])) > 0
                                break
                    except Exception:
                        pass

                # Determine current candidate status
                cand_status = c.get("status")
                if not cand_status:
                    job = JOB_MANAGER.get_job(cid)
                    cand_status = job.status if job else "done"

                summary_list.append({
                    "candidate_id": cid,
                    "name": c["name"],
                    "category": c.get("category", "applicant"),
                    "target_role": c.get("target_role", "Senior Software Engineer"),
                    "status": cand_status,
                    "role_fit_score": fit_score,
                    "evidence_consistency_score": consistency_score,
                    "quadrant": quadrant,
                    "has_discrepancies": has_disc
                })
            self._send_json(summary_list)
            return

        # 3. Candidate Full Profile (Dossier documents & spans, NO answer keys)
        elif path.startswith("/api/case/") and path.endswith("/full"):
            raw_cid = path.replace("/api/case/", "").replace("/full", "").strip()
            if not re.match(r'^[A-Za-z0-9_-]{1,128}$', raw_cid):
                self.send_error(400, "Invalid Candidate ID format")
                return

            db_cand = DB.get_candidate_full(raw_cid)
            case = db_cand or next((c for c in ALL_CASES if c["candidate_id"] == raw_cid), None)
            if not case:
                self.send_error(404, "Candidate Case Not Found")
                return

            dossier = EvidenceLoader.load_case_from_dict(case)
            full_payload = {
                "candidate_id": raw_cid,
                "name": case["name"],
                "target_role": case.get("target_role", "Senior Software Engineer"),
                "category": case.get("category", "applicant"),
                "documents": {
                    "cv": case.get("cv_text", ""),
                    "interview": case.get("interview_notes", ""),
                    "assessment": case.get("technical_assessment", ""),
                    "project_rfc": case.get("project_rfc", ""),
                    "jd": case.get("jd_text", SHARED_JD)
                },
                "raw_documents": case.get("raw_documents", {}),
                "structured_profile": dossier.structured_cv_profile,
                "evidence_spans": [s.to_dict() for s in dossier.spans]
            }
            self._send_json(full_payload)
            return


        # 4. Safe Public Benchmark Summary (Zero ground-truth or candidate-level answer leaks)
        elif path in ("/api/eval_summary", "/api/eval_results"):
            eval_path = os.path.join(root_dir, "eval", "eval_results.json")
            if os.path.exists(eval_path):
                with open(eval_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                safe_summary = {
                    "metadata": data.get("metadata", {}),
                    "metrics": data.get("metrics", {})
                }
                self._send_json(safe_summary)
                return
            else:
                self._send_json({"status": "pending", "message": "Evaluation results not yet generated"})
                return

        # 5. Async Candidate Evaluation Job Status
        elif path.startswith("/api/candidate/") and path.endswith("/status"):
            raw_cid = path.replace("/api/candidate/", "").replace("/status", "").strip()
            if not re.match(r'^[A-Za-z0-9_-]{1,128}$', raw_cid):
                self.send_error(400, "Invalid Candidate ID format")
                return

            job = JOB_MANAGER.get_job(raw_cid)
            if job:
                self._send_json(job.to_dict())
                return

            # If not in active memory, check if already completed on disk / in ALL_CASES
            case = next((c for c in ALL_CASES if c.get("candidate_id") == raw_cid), None)
            if case and "evaluation_report" in case:
                self._send_json({
                    "candidate_id": raw_cid,
                    "name": case.get("name", ""),
                    "target_role": case.get("target_role", "Senior Software Engineer"),
                    "status": "done",
                    "progress_pct": 100,
                    "current_step": "Assessment complete. Report ready.",
                    "report": case.get("evaluation_report"),
                    "baseline_a": case.get("rubric_baseline"),
                    "error": None
                })
                return

            self.send_error(404, "Candidate job not found")
            return

        # 6. Bulk Batch Evaluation Status
        elif path.startswith("/api/batch/") and path.endswith("/status"):
            raw_batch_id = path.replace("/api/batch/", "").replace("/status", "").strip()
            if not re.match(r'^[A-Za-z0-9_-]{1,128}$', raw_batch_id):
                self.send_error(400, "Invalid Batch ID format")
                return

            batch = BULK_ENGINE.get_batch(raw_batch_id)
            if batch:
                self._send_json(batch.to_dict())
                return

            self.send_error(404, "Batch job not found")
            return

        # Security: Strict static file serving (block arbitrary project file exposure)
        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        force_rerun = query.get("force", ["false"])[0].lower() == "true"

        # Security: Safe Content-Length parsing & bounded reads (100MB for bulk, 15MB for single)
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_error(400, "Malformed Content-Length header")
            return

        max_limit = 100 * 1024 * 1024 if "bulk" in path else 15 * 1024 * 1024
        if content_length > max_limit:
            self.send_error(413, f"Payload Too Large: Max {max_limit // (1024 * 1024)}MB allowed")
            return

        # Endpoint: Bulk candidate ingestion (Folder or ZIP archive)
        if path in ("/api/candidates/bulk", "/api/candidates/bulk/"):
            content_type = self.headers.get("Content-Type", "")
            raw_body = self.rfile.read(content_length)

            fields: Dict[str, str] = {}
            files: Dict[str, Tuple[str, bytes]] = {}

            if "multipart/form-data" in content_type:
                try:
                    fields, files = parse_multipart_payload(content_type, raw_body)
                except Exception as err:
                    self.send_error(400, f"Malformed multipart payload: {err}")
                    return
            else:
                self.send_error(415, "Unsupported Media Type: Expected multipart/form-data with ZIP archive or folder files")
                return

            target_role = fields.get("target_role", "").strip() or "Senior Python & Distributed Systems Engineer"
            batch_id = f"batch_{int(time.time())}_{uuid.uuid4().hex[:6]}"

            # Check if an archive was uploaded
            zip_entry = None
            for key, (fname, fbytes) in files.items():
                if fname.lower().endswith(".zip") or key in ("archive_file", "zip_file"):
                    zip_entry = (fname, fbytes)
                    break

            if zip_entry:
                batch = BULK_ENGINE.process_archive(
                    zip_bytes=zip_entry[1],
                    batch_id=batch_id,
                    target_role=target_role,
                    uploads_root=UPLOADS_DIR,
                    cases_dir=CASES_DIR,
                    pipeline=PIPELINE,
                    all_cases_list=ALL_CASES
                )
            else:
                # Multi-file folder drop
                files_map: Dict[str, bytes] = {}
                for key, (fname, fbytes) in files.items():
                    # Check if relative path was supplied in fields
                    path_key = fields.get(f"path_{key}", fname)
                    files_map[path_key] = fbytes

                batch = BULK_ENGINE.process_file_tree(
                    files_map=files_map,
                    batch_id=batch_id,
                    target_role=target_role,
                    uploads_root=UPLOADS_DIR,
                    cases_dir=CASES_DIR,
                    pipeline=PIPELINE,
                    all_cases_list=ALL_CASES
                )

            output = {
                "success": True,
                "batch_id": batch.batch_id,
                "total_files": batch.total_files,
                "uploaded": batch.uploaded,
                "parsed": batch.parsed,
                "queued": batch.queued,
                "duplicates": batch.duplicates,
                "poll_url": f"/api/batch/{batch.batch_id}/status"
            }
            self._send_json(output, status=202)
            return

        # Endpoint: Ingest candidate via multipart file upload or mixed file/text
        if path in ("/api/candidate/upload", "/api/candidate/upload/"):
            content_type = self.headers.get("Content-Type", "")
            raw_body = self.rfile.read(content_length)


            fields: Dict[str, str] = {}
            files: Dict[str, Tuple[str, bytes]] = {}

            if "multipart/form-data" in content_type:
                try:
                    fields, files = parse_multipart_payload(content_type, raw_body)
                except Exception as err:
                    self.send_error(400, f"Malformed multipart payload: {err}")
                    return
            elif "application/json" in content_type:
                try:
                    fields = json.loads(raw_body.decode("utf-8"))
                except Exception as err:
                    self.send_error(400, f"Invalid JSON payload: {err}")
                    return
            elif "application/x-www-form-urlencoded" in content_type:
                try:
                    parsed_qs = urllib.parse.parse_qs(raw_body.decode("utf-8"))
                    fields = {k: v[0] for k, v in parsed_qs.items() if v}
                except Exception as err:
                    self.send_error(400, f"Invalid form-urlencoded payload: {err}")
                    return
            else:
                self.send_error(415, "Unsupported Media Type: Expected multipart/form-data, application/json, or application/x-www-form-urlencoded")
                return


            name = fields.get("name", "").strip()
            if not name:
                self.send_error(400, "Missing required field: 'name'")
                return

            target_role = fields.get("target_role", "").strip() or "Senior Python & Distributed Systems Engineer"
            jd_text = fields.get("jd_text", "").strip() or SHARED_JD

            # Safe collision-free candidate ID
            slug = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:24]
            unique_token = uuid.uuid4().hex[:10]
            cid = f"custom_{slug}_{unique_token}"

            cand_upload_dir = os.path.join(UPLOADS_DIR, cid)
            os.makedirs(cand_upload_dir, exist_ok=True)

            raw_docs_meta: Dict[str, Any] = {}

            def _resolve_doc(file_key: str, text_key: str, doc_name_prefix: str) -> str:
                # 1. Check if uploaded file exists and has content
                if file_key in files and files[file_key][1]:
                    orig_fname, fbytes = files[file_key]
                    clean_fname = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(orig_fname))
                    save_path = os.path.join(cand_upload_dir, f"{doc_name_prefix}_{clean_fname}")
                    with open(save_path, "wb") as f:
                        f.write(fbytes)

                    file_hash = compute_file_hash(fbytes)
                    raw_docs_meta[doc_name_prefix] = {
                        "filename": orig_fname,
                        "disk_path": save_path,
                        "sha256": file_hash,
                        "size_bytes": len(fbytes)
                    }
                    try:
                        return extract_text(save_path, filename_hint=orig_fname)
                    except Exception as parse_err:
                        raise ValueError(f"Failed parsing {doc_name_prefix} document ({orig_fname}): {parse_err}")

                # 2. Fall back to direct text field
                txt_val = fields.get(text_key, "").strip()
                return txt_val

            try:
                cv_text = _resolve_doc("cv_file", "cv_text", "cv")
                if not cv_text:
                    self.send_error(400, "Missing required document: 'cv_file' (PDF/DOCX/TXT/MD) or 'cv_text'")
                    return

                interview_notes = _resolve_doc("interview_file", "interview_notes", "interview")
                technical_assessment = _resolve_doc("assessment_file", "technical_assessment", "assessment")
                project_rfc = _resolve_doc("project_file", "project_rfc", "project")

            except ValueError as val_err:
                self.send_error(400, str(val_err))
                return

            new_case = {
                "candidate_id": cid,
                "name": name,
                "target_role": target_role,
                "category": "live_applicant",
                "cv_text": cv_text,
                "interview_notes": interview_notes,
                "technical_assessment": technical_assessment,
                "project_rfc": project_rfc,
                "jd_text": jd_text,
                "raw_documents": raw_docs_meta
            }

            # Check synchronous execution flag (?sync=true or header X-HireTrace-Sync: true)
            is_sync = (query.get("sync", ["false"])[0].lower() == "true" or
                       self.headers.get("X-HireTrace-Sync", "").lower() == "true")

            # Persist to SQLite DB
            DB.upsert_candidate(cid, name, target_role, "live_applicant", "done" if is_sync else "queued")
            DB.save_documents(cid, {
                "cv": cv_text,
                "interview": interview_notes,
                "assessment": technical_assessment,
                "project": project_rfc
            }, raw_docs_meta)

            if is_sync:
                # Synchronous execution (for test harnesses and direct programmatic scripts)
                try:
                    dossier = EvidenceLoader.load_case_from_dict(new_case)
                    report = PIPELINE.run(dossier, log_trajectory=True)
                    rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

                    new_case["evaluation_report"] = report.to_dict()
                    new_case["rubric_baseline"] = rubric.to_dict()
                    new_case["role_fit_score"] = report.role_fit_score
                    new_case["evidence_consistency_score"] = report.evidence_consistency_score
                    new_case["quadrant"] = report.quadrant
                    new_case["status"] = "done"

                    case_file = os.path.join(CASES_DIR, f"{cid}.json")
                    with open(case_file, "w", encoding="utf-8") as f:
                        json.dump(new_case, f, indent=2)

                    DB.save_evaluation(
                        candidate_id=cid,
                        role_fit_score=report.role_fit_score,
                        evidence_consistency_score=report.evidence_consistency_score,
                        quadrant=report.quadrant,
                        report_dict=report.to_dict(),
                        baseline_a_dict=rubric.to_dict()
                    )

                    ALL_CASES.append(new_case)


                    output = {
                        "success": True,
                        "candidate_id": cid,
                        "name": name,
                        "target_role": target_role,
                        "status": "done",
                        "report": report.to_dict(),
                        "baseline_a": rubric.to_dict(),
                        "cached": False,
                        "raw_documents": raw_docs_meta
                    }
                    self._send_json(output)
                    return
                except Exception as err:
                    self.send_error(500, f"Pipeline evaluation failed: {err}")
                    return
            else:
                # Asynchronous execution: Return instantly with 202 Accepted, worker evaluates in background
                new_case["status"] = "queued"
                case_file = os.path.join(CASES_DIR, f"{cid}.json")
                with open(case_file, "w", encoding="utf-8") as f:
                    json.dump(new_case, f, indent=2)

                ALL_CASES.append(new_case)

                JOB_MANAGER.submit_evaluation(
                    new_case,
                    PIPELINE,
                    CASES_DIR,
                    ALL_CASES
                )

                output = {
                    "success": True,
                    "candidate_id": cid,
                    "name": name,
                    "target_role": target_role,
                    "status": "queued",
                    "poll_url": f"/api/candidate/{cid}/status",
                    "raw_documents": raw_docs_meta
                }
                self._send_json(output, status=202)
                return


        # Endpoint: Ingest a brand-new live applicant (Legacy JSON)
        if path == "/api/candidate/new":
            try:
                body = self.rfile.read(content_length).decode("utf-8")

                data = json.loads(body)
            except Exception as err:
                self.send_error(400, f"Invalid JSON payload: {err}")
                return

            name = data.get("name", "").strip()
            if not name:
                self.send_error(400, "Missing required field: 'name'")
                return

            cv_text = data.get("cv_text", "").strip()
            if not cv_text:
                self.send_error(400, "Missing required field: 'cv_text'")
                return

            target_role = data.get("target_role", "").strip() or "Senior Python & Distributed Systems Engineer"
            interview_notes = data.get("interview_notes", "").strip()
            technical_assessment = data.get("technical_assessment", "").strip()
            project_rfc = data.get("project_rfc", "").strip()
            jd_text = data.get("jd_text", "").strip() or SHARED_JD

            # Safe, collision-free UUID candidate ID
            slug = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:24]
            unique_token = uuid.uuid4().hex[:10]
            cid = f"custom_{slug}_{unique_token}"

            new_case = {
                "candidate_id": cid,
                "name": name,
                "target_role": target_role,
                "category": "live_applicant",
                "cv_text": cv_text,
                "interview_notes": interview_notes,
                "technical_assessment": technical_assessment,
                "project_rfc": project_rfc,
                "jd_text": jd_text
            }

            # Run full HireTrace pipeline
            try:
                dossier = EvidenceLoader.load_case_from_dict(new_case)
                report = PIPELINE.run(dossier, log_trajectory=True)
                rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

                # Persist to disk with final evaluated report
                new_case["evaluation_report"] = report.to_dict()
                new_case["rubric_baseline"] = rubric.to_dict()
                new_case["role_fit_score"] = report.role_fit_score
                new_case["evidence_consistency_score"] = report.evidence_consistency_score
                new_case["quadrant"] = report.quadrant

                case_file = os.path.join(CASES_DIR, f"{cid}.json")
                with open(case_file, "w", encoding="utf-8") as f:
                    json.dump(new_case, f, indent=2)

                # Add to runtime cases pool
                ALL_CASES.append(new_case)

                output = {
                    "success": True,
                    "candidate_id": cid,
                    "name": name,
                    "target_role": target_role,
                    "report": report.to_dict(),
                    "baseline_a": rubric.to_dict(),
                    "cached": False
                }
                self._send_json(output)
                return

            except Exception as err:
                self.send_error(500, f"Pipeline evaluation failed: {err}")
                return

        # Endpoint: Evaluate existing candidate
        elif path.startswith("/api/evaluate/"):
            raw_cid = path.replace("/api/evaluate/", "").strip()
            if not re.match(r'^[A-Za-z0-9_-]{1,128}$', raw_cid):
                self.send_error(400, "Invalid Candidate ID format")
                return

            case = next((c for c in ALL_CASES if c["candidate_id"] == raw_cid), None)
            if not case:
                self.send_error(404, "Candidate Case Not Found")
                return

            traj_file = os.path.join(CACHE_DIR, f"{raw_cid}_trajectory.json")

            # Check cache if not forcing rerun
            if not force_rerun and os.path.exists(traj_file):
                try:
                    with open(traj_file, "r", encoding="utf-8") as f:
                        cached_data = json.load(f)
                    final_report = cached_data.get("final_report")
                    if not final_report and "steps" in cached_data and cached_data["steps"]:
                        final_report = cached_data["steps"][-1].get("output", {})
                    dossier = EvidenceLoader.load_case_from_dict(case)
                    rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

                    output = {
                        "report": final_report,
                        "baseline_a": rubric.to_dict(),
                        "cached": True
                    }
                    self._send_json(output)
                    return
                except Exception:
                    pass

            # Run full HireTrace pipeline
            try:
                dossier = EvidenceLoader.load_case_from_dict(case)
                report = PIPELINE.run(dossier, log_trajectory=True)
                rubric = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)

                output = {
                    "report": report.to_dict(),
                    "baseline_a": rubric.to_dict(),
                    "cached": False
                }
                self._send_json(output)
                return
            except Exception as err:
                self.send_error(500, f"Evaluation execution failed: {err}")
                return

        self.send_error(404, "Endpoint not found")


def start_server(port: int = 8080):
    handler = HireTraceHandler
    with ReusableHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"HireTrace Dashboard running at http://127.0.0.1:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port)
