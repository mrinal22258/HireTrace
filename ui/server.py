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
from typing import Dict, Any, List, Optional

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.pipeline import HireTracePipeline
from baseline.rubric_scorer import RubricScorer
from eval_cases.dataset import CASES, SHARED_JD

CACHE_DIR = os.path.join(root_dir, "trajectories")
CASES_DIR = os.path.join(root_dir, "eval_cases")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(CASES_DIR, exist_ok=True)

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

        # 2. Public Candidate List (Zero Ground-Truth Answer Leakage)
        elif path == "/api/cases":
            summary_list = []
            for c in ALL_CASES:
                cid = c["candidate_id"]
                traj_file = os.path.join(CACHE_DIR, f"{cid}_trajectory.json")
                fit_score = 50.0
                consistency_score = 50.0
                quadrant = "EVALUATING"
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

                summary_list.append({
                    "candidate_id": cid,
                    "name": c["name"],
                    "category": c.get("category", "applicant"),
                    "target_role": c.get("target_role", "Senior Software Engineer"),
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

            case = next((c for c in ALL_CASES if c["candidate_id"] == raw_cid), None)
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

        # Security: Strict static file serving (block arbitrary project file exposure)
        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        force_rerun = query.get("force", ["false"])[0].lower() == "true"

        # Security: Safe Content-Length parsing & 10MB limit
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_error(400, "Malformed Content-Length header")
            return

        if content_length > 10 * 1024 * 1024:
            self.send_error(413, "Payload Too Large: Max 10MB allowed")
            return

        # Endpoint: Ingest a brand-new live applicant
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
