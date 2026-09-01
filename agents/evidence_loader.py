"""
Evidence Loader for HireTrace.

Parses Job Descriptions (JDs), CVs, Interview Transcripts, Technical Assessments,
and Project Portfolios into structured, citable evidence spans.
Follows the ResumeExtractBench pattern for clean structured extraction from CV text.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import json
import re


@dataclass
class EvidenceSpan:
    """An atomic, citable segment of text from a candidate or role document."""
    span_id: str
    source_file: str          # e.g., "cv.txt", "interview_notes.txt"
    document_type: str        # "cv", "interview", "assessment", "project", "jd"
    section: str              # e.g., "experience", "education", "technical_q_and_a"
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "source_file": self.source_file,
            "document_type": self.document_type,
            "section": self.section,
            "text": self.text,
            "metadata": self.metadata
        }


@dataclass
class CandidateDossier:
    """Complete bundle of raw documents and parsed evidence spans for a candidate."""
    candidate_id: str
    name: str
    target_role: str
    jd_text: str
    cv_text: str
    interview_text: Optional[str] = None
    assessment_text: Optional[str] = None
    project_text: Optional[str] = None
    spans: List[EvidenceSpan] = field(default_factory=list)
    structured_cv_profile: Dict[str, Any] = field(default_factory=dict)

    def get_spans_by_doc_type(self, doc_type: str) -> List[EvidenceSpan]:
        return [s for s in self.spans if s.document_type == doc_type]


class EvidenceLoader:
    """Loads and segments multi-source candidate evidence into citable spans."""

    @staticmethod
    def chunk_text(text: str, source_file: str, doc_type: str, section_prefix: str = "general") -> List[EvidenceSpan]:
        """Segments text into paragraph or bullet-level evidence spans with unique IDs."""
        spans = []
        if not text or not text.strip():
            return spans

        # Split by double newlines or major section markers
        raw_blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        current_section = section_prefix
        idx = 1

        for block in raw_blocks:
            # Check if block looks like a section header (e.g., "# Experience" or "EXPERIENCE:")
            header_match = re.match(r"^(?:#+\s*|[A-Z\s]{3,}:)(.*)", block)
            if header_match and len(block.splitlines()) == 1:
                current_section = block.strip("#: \t").lower().replace(" ", "_")
                continue

            # Split paragraphs with bullet points into individual sentences or bullet items if long
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if len(lines) > 1 and any(l.startswith(("-", "*", "•", "1.", "2.", "3.")) for l in lines):
                for sub_line in lines:
                    cleaned_line = re.sub(r"^[-*•\d\.]+\s*", "", sub_line).strip()
                    if cleaned_line:
                        span_id = f"{doc_type[:3].upper()}-{idx:03d}"
                        spans.append(EvidenceSpan(
                            span_id=span_id,
                            source_file=source_file,
                            document_type=doc_type,
                            section=current_section,
                            text=cleaned_line,
                            metadata={"raw_line": sub_line}
                        ))
                        idx += 1
            else:
                span_id = f"{doc_type[:3].upper()}-{idx:03d}"
                spans.append(EvidenceSpan(
                    span_id=span_id,
                    source_file=source_file,
                    document_type=doc_type,
                    section=current_section,
                    text=block,
                    metadata={}
                ))
                idx += 1

        return spans

    @classmethod
    def extract_structured_cv_profile(cls, cv_text: str, candidate_id: str, name: str = "") -> Dict[str, Any]:
        """
        Extracts structured signals from CV text matching the ResumeExtractBench pattern.
        Provides inputs for the deterministic Rubric Scorer.
        """
        lower = cv_text.lower()
        
        # 1. Open source signals
        has_public_repo = bool(re.search(r"(github\.com|gitlab\.com|open[- ]source)", lower))
        pr_matches = re.findall(r"(\d+)\+?\s*(?:merged\s*)?(?:prs|pull requests|contributions)", lower)
        pr_count = max([int(m) for m in pr_matches], default=0)
        if not pr_count and ("merged pr" in lower or "pull request" in lower):
            pr_count = 2

        repo_matches = re.findall(r"(\d+)\+?\s*(?:maintained|authored)?\s*(?:repos|repositories|packages)", lower)
        repo_count = max([int(m) for m in repo_matches], default=0)
        if not repo_count and ("maintainer" in lower or "creator of" in lower):
            repo_count = 1

        star_matches = re.findall(r"(\d+)\+?\s*stars", lower)
        star_count = max([int(m) for m in star_matches], default=0)

        # 2. Self-directed projects
        has_system_project = bool(re.search(r"(distributed|microservice|architecture|backend system|engine|pipeline)", lower))
        has_production_architecture = bool(re.search(r"(docker|kubernetes|ci/cd|kafka|redis|rabbitmq|terraform|aws)", lower))
        has_live_demo = bool(re.search(r"(live demo|deployed at|hosted on|vercel\.app|fly\.io|production url)", lower))
        has_test_coverage = bool(re.search(r"(pytest|unit tests|test coverage|\d+%\s*coverage|tdd)", lower))

        # Helper to check for positive presence while rejecting negations
        def _has_positive_mention(pattern: str, text: str) -> bool:
            for m in re.finditer(pattern, text):
                start_idx = max(0, m.start() - 30)
                prefix = text[start_idx:m.start()].lower()
                if re.search(r"\b(no|not|lacks?|lacking|without|zero|never|minimal|limited)\b", prefix):
                    continue
                return True
            return False

        # 3. Production experience
        # Priority 1: Explicit statements like "5+ years of experience" or "4 years of production engineering"
        tenure_matches = re.findall(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|production|engineering|tenure)", lower)
        tenure_years = max([float(m) for m in tenure_matches], default=0.0)
        
        # Priority 2: Date intervals within Experience / Work History sections ONLY
        # (Explicitly exclude Education, Academics, Extracurricular, Societies, and Student Club dates)
        if not tenure_years:
            exp_match = re.search(
                r"(?:^|\n)#*\s*(?:work\s+experience|professional\s+experience|employment\s+history|experience)\b(.*?)(?=\n#*\s*(?:education|academics|projects|certifications|awards|skills|positions|extracurricular|societies|clubs|$))",
                cv_text,
                re.DOTALL | re.IGNORECASE
            )
            if exp_match:
                exp_scope = exp_match.group(1).lower()
            else:
                cleaned_cv = re.sub(
                    r"(?:education|academics|positions|extracurricular|societies|clubs)\b.*?(?=\n\n|\n#|[A-Z][a-z]+:|$)",
                    "",
                    cv_text,
                    flags=re.DOTALL | re.IGNORECASE
                )
                exp_scope = cleaned_cv.lower()

            year_ranges = re.findall(r"(201\d|202\d)\s*[-–—]\s*(201\d|202\d|present|current)", exp_scope)
            if year_ranges:
                intervals = []
                for start, end in year_ranges:
                    start_yr = int(start)
                    end_yr = 2026 if end in ("present", "current") else int(end)
                    if end_yr >= start_yr:
                        intervals.append((start_yr, end_yr))
                
                if intervals:
                    intervals.sort(key=lambda x: x[0])
                    merged = [intervals[0]]
                    for current in intervals[1:]:
                        prev_start, prev_end = merged[-1]
                        if current[0] <= prev_end:
                            merged[-1] = (prev_start, max(prev_end, current[1]))
                        else:
                            merged.append(current)
                    total_span = sum(float(end - start) for start, end in merged)
                    tenure_years = min(total_span, 15.0)
            else:
                # Check for month-level internship / research durations e.g. "Jan 2025 - Apr 2025"
                month_pairs = re.findall(
                    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(201\d|202\d)\s*[-–—]\s*(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*)?(201\d|202\d|present|current)",
                    exp_scope
                )
                if month_pairs:
                    tenure_years = 0.3

        has_high_scale = _has_positive_mention(r"(high[- ]throughput|sla|millions? of requests|uptime|qps|tb of data)", lower)

        # 4. Technical skills (negation-aware)
        primary_lang = _has_positive_mention(r"(python|asyncio|fastapi|django|flask)", lower)
        database_sys = _has_positive_mention(r"(postgresql|postgres|mysql|sqlite|redis|mongodb|cassandra|\bsql\b|\bdbms\b|vector\s+database|neo4j|nosql|faiss|elasticsearch|dynamodb|clickhouse)", lower)
        distributed_sys = _has_positive_mention(r"(distributed|kafka|grpc|event[- ]driven|load balancer|concurrency|spark|hadoop|docker|kubernetes|k8s|cloud|aws|gcp|azure|decentralized|rabbitmq|pubsub)", lower)

        # 5. Bonus points
        has_writing = _has_positive_mention(r"(blog|medium\.com|substack|whitepaper|talk|speaker|conference)", lower)
        has_mentorship = _has_positive_mention(r"(mentored|mentor|led team|lead|tech lead|coached|core member|coordinator|organizer)", lower)
        has_academic = _has_positive_mention(r"(master's|phd|thesis|publication|ieee|acm|patent|competition|hackathon winner|researcher|research|benchmark|shared task|award|prize|olympiad)", lower)
        has_security = _has_positive_mention(r"(security|owasp|soc2|encryption|oauth|auth0|penetration|cipher|cryptanalysis|cryptography|certif(?:ied|icate|ication|ications))", lower)

        return {
            "candidate_id": candidate_id,
            "name": name,
            "has_public_repo": has_public_repo,
            "open_source_prs_count": pr_count,
            "maintained_repos_count": repo_count,
            "total_repo_stars": star_count,
            "has_system_project": has_system_project,
            "has_production_architecture": has_production_architecture,
            "has_live_demo": has_live_demo,
            "has_test_coverage": has_test_coverage,
            "years_production_experience": tenure_years,
            "has_high_scale_experience": has_high_scale,
            "primary_language_match": primary_lang,
            "database_systems_match": database_sys,
            "distributed_cloud_match": distributed_sys,
            "has_tech_writing_or_talks": has_writing,
            "has_mentorship_or_leadership": has_mentorship,
            "has_competitive_or_academic": has_academic,
            "has_security_or_certifications": has_security,
        }

    @classmethod
    def load_case_from_files(
        cls,
        candidate_id: str,
        name: str,
        target_role: str,
        jd_text: str,
        cv_text: str,
        interview_text: Optional[str] = None,
        assessment_text: Optional[str] = None,
        project_text: Optional[str] = None,
    ) -> CandidateDossier:
        """Constructs a complete CandidateDossier from document strings."""
        spans: List[EvidenceSpan] = []
        # Chunk JD
        if jd_text:
            spans.extend(cls.chunk_text(jd_text, "job_description.txt", "jd", "job_description"))

        # Chunk CV
        spans.extend(cls.chunk_text(cv_text, "cv.txt", "cv", "resume"))

        # Chunk Interview
        if interview_text:
            spans.extend(cls.chunk_text(interview_text, "interview_notes.txt", "interview", "interview"))

        # Chunk Assessment
        if assessment_text:
            spans.extend(cls.chunk_text(assessment_text, "assessment_report.txt", "assessment", "assessment"))

        # Chunk Project
        if project_text:
            spans.extend(cls.chunk_text(project_text, "project_doc.txt", "project", "project"))

        # Extract structured CV profile
        cv_profile = cls.extract_structured_cv_profile(cv_text, candidate_id=candidate_id, name=name)

        return CandidateDossier(
            candidate_id=candidate_id,
            name=name,
            target_role=target_role,
            jd_text=jd_text,
            cv_text=cv_text,
            interview_text=interview_text,
            assessment_text=assessment_text,
            project_text=project_text,
            spans=spans,
            structured_cv_profile=cv_profile
        )

    @classmethod
    def load_case_from_dict(cls, data: Dict[str, Any]) -> CandidateDossier:
        """Helper to construct dossier directly from test case JSON/dictionary."""
        return cls.load_case_from_files(
            candidate_id=data.get("candidate_id", "c_unknown"),
            name=data.get("name", "Unknown Candidate"),
            target_role=data.get("target_role", "Senior Software Engineer"),
            jd_text=data.get("jd_text", ""),
            cv_text=data.get("cv_text", ""),
            interview_text=data.get("interview_text") or data.get("interview_notes"),
            assessment_text=data.get("assessment_text") or data.get("technical_assessment"),
            project_text=data.get("project_text") or data.get("project_rfc")
        )
