"""
Structured CV Extraction Agent for HireTrace (Phase 4).

Extracts structured schema facts from raw CV text:
- employment_history: employer, title, start_date, end_date, is_current
- education: institution, degree, field_of_study, graduation_year
- skills: array of skill strings
- project_claims: project_name, description, technologies

Uses local Ollama model (or mock client) with a deterministic regex/rule parser fallback
to ensure zero-cost, offline-capable, schema-constrained structured extraction.
"""

from __future__ import annotations

import re
import json
import logging
from typing import Dict, Any, Optional, List
from agents.ollama_client import OllamaClient

logger = logging.getLogger("hiretrace.cv_extractor")


EXTRACTION_SYSTEM_PROMPT = """You are an expert CV/resume extraction system.
Extract structured factual records from the candidate's resume text matching the exact JSON schema requested.
Do not invent or extrapolate dates, companies, or claims.
Return ONLY valid JSON matching this structure:
{
  "candidate_name": "Full Name",
  "employment_history": [
    {
      "employer": "Company Name",
      "title": "Role Title",
      "start_date": "YYYY-MM or YYYY",
      "end_date": "YYYY-MM or YYYY or null",
      "is_current": true or false
    }
  ],
  "education": [
    {
      "institution": "University / College",
      "degree": "Degree attained",
      "field_of_study": "Major",
      "graduation_year": "YYYY or null"
    }
  ],
  "skills": ["skill1", "skill2"],
  "project_claims": [
    {
      "project_name": "Project name",
      "description": "Short description of accomplishments",
      "technologies": ["tech1", "tech2"]
    }
  ]
}
"""


def _normalize_date(date_str: str) -> Optional[str]:
    """Normalizes month/year expressions like 'Oct 2021' -> '2021-10', '2021' -> '2021'."""
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12"
    }
    # Pattern: Month YYYY
    m_match = re.match(r"(?i)([a-z]{3,9})\.?\s+(\d{4})", s)
    if m_match:
        m_name = m_match.group(1).lower()[:3]
        yr = m_match.group(2)
        m_num = months.get(m_name, "01")
        return f"{yr}-{m_num}"
    # Pattern: YYYY
    y_match = re.match(r"(\d{4})", s)
    if y_match:
        return y_match.group(1)
    return s


def fallback_deterministic_extractor(cv_text: str, candidate_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic regex/rule-based extractor for CV text.
    Provides offline, local fallback scoring without network or paid API spend.
    """
    name = candidate_name
    if not name:
        # Search for first header # Name
        m = re.search(r"^#\s+([A-Za-z0-9\.\s\-]+?)(?:,|\n|\|)", cv_text)
        if m:
            name = m.group(1).strip()
        else:
            name = "Candidate"

    # Extract skills
    skills: List[str] = []
    skills_sec = re.search(r"(?i)##?\s*Technical Skills.*?\n(.*?)(?=\n##|\Z)", cv_text, re.DOTALL)
    if skills_sec:
        sec_text = skills_sec.group(1)
        # Split by commas or bullets
        raw_items = re.split(r"[,•\-\n:]+", sec_text)
        for item in raw_items:
            clean = re.sub(r"\(.*?\)", "", item).strip()
            clean = re.sub(r"^(Languages|Distributed Systems|Databases|Storage|Infrastructure|Core Languages|Distributed Messaging|Storage & Data Layer):?", "", clean, flags=re.IGNORECASE).strip()
            if clean and len(clean) > 1 and len(clean) < 35 and clean.lower() not in ("and", "or", "expert"):
                if clean not in skills:
                    skills.append(clean)

    # Extract employment history
    employment: List[Dict[str, Any]] = []
    # Match patterns like: "Senior Backend Engineer | CloudFlux Solutions (Jan 2022 - Present | 3.5 years)"
    # or "Staff Applied Scientist at NeuroScale Labs (2021 - Present | 3.8 years)"
    emp_pattern = re.compile(
        r"(?i)([A-Za-z\s]+?)\s+(?:\||at)\s+([A-Za-z0-9\s]+?)\s*\((.*?)\)",
        re.MULTILINE
    )
    for match in emp_pattern.finditer(cv_text):
        title = match.group(1).strip()
        employer = match.group(2).strip()
        date_block = match.group(3).strip()

        # Skip headers or skills lines that match accidentally
        if any(skip in title.lower() for skip in ["technical skills", "languages", "education", "github", "linkedin"]):
            continue
        if len(title) > 50 or len(employer) > 50:
            continue

        # Parse date block: "Jan 2022 - Present | 3.5 years"
        date_parts = re.split(r"\s*-\s*", date_block.split("|")[0])
        start_date = _normalize_date(date_parts[0]) if len(date_parts) > 0 else "2020"
        end_date_str = date_parts[1].strip() if len(date_parts) > 1 else "Present"

        is_curr = bool(re.search(r"(?i)present|current|now", end_date_str))
        end_date = None if is_curr else _normalize_date(end_date_str)

        if start_date:
            employment.append({
                "employer": employer,
                "title": title,
                "start_date": start_date,
                "end_date": end_date,
                "is_current": is_curr
            })

    # Extract education
    education: List[Dict[str, Any]] = []
    edu_match = re.search(r"(?i)(PhD|MS|BS|BA|Master|Bachelor)\s+in\s+([A-Za-z\s]+?)\s*\((.*?)(?:,\s*(\d{4}))?\)", cv_text)
    if edu_match:
        deg = edu_match.group(1)
        field = edu_match.group(2).strip()
        inst = edu_match.group(3).strip()
        yr = edu_match.group(4)
        education.append({
            "institution": inst,
            "degree": deg,
            "field_of_study": field,
            "graduation_year": int(yr) if yr and yr.isdigit() else None
        })

    # Extract project claims
    projects: List[Dict[str, Any]] = []
    proj_sec = re.search(r"(?i)##?\s*(?:Notable Open Source & Projects|Projects|Open Source & Publications).*?\n(.*?)(?=\n##|\Z)", cv_text, re.DOTALL)
    if proj_sec:
        bullet_lines = [l.strip() for l in proj_sec.group(1).split("\n") if l.strip().startswith(("-", "*", "`"))]
        for line in bullet_lines:
            # e.g., "- `async-kafka-batcher` (url): Python library for high-throughput..."
            m_proj = re.match(r"^[\-\*`\s]*`?([a-zA-Z0-9_\-]+)`?\s*(?:\(.*?\))?:\s*(.*)", line)
            if m_proj:
                p_name = m_proj.group(1)
                p_desc = m_proj.group(2)
                projects.append({
                    "project_name": p_name,
                    "description": p_desc,
                    "technologies": []
                })

    return {
        "candidate_name": name,
        "employment_history": employment,
        "education": education,
        "skills": skills,
        "project_claims": projects
    }


_CACHED_CLIENT: Optional[OllamaClient] = None


def get_default_client() -> OllamaClient:
    global _CACHED_CLIENT
    if _CACHED_CLIENT is None:
        _CACHED_CLIENT = OllamaClient()
    return _CACHED_CLIENT


def extract_structured_cv(
    cv_text: str,
    candidate_name: Optional[str] = None,
    client: Optional[OllamaClient] = None
) -> Dict[str, Any]:
    """
    Extracts structured schema-constrained facts from raw CV text.
    First attempts local Ollama LLM extraction if available; falls back to deterministic rule extraction.
    """
    if not cv_text or not cv_text.strip():
        return {
            "candidate_name": candidate_name or "Unknown",
            "employment_history": [],
            "education": [],
            "skills": [],
            "project_claims": []
        }

    ollama = client or get_default_client()
    if ollama.is_available() and getattr(ollama, "backend", "") != "mock":
        prompt = f"Candidate Name: {candidate_name or 'Not specified'}\n\nResume Text:\n{cv_text}"
        try:
            res = ollama.generate_json(
                prompt=prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=1500
            )
            if isinstance(res, dict) and "employment_history" in res:
                # Ensure fields are valid
                return {
                    "candidate_name": res.get("candidate_name") or candidate_name or "Candidate",
                    "employment_history": res.get("employment_history", []),
                    "education": res.get("education", []),
                    "skills": res.get("skills", []),
                    "project_claims": res.get("project_claims", [])
                }
        except Exception as err:
            logger.warning(f"Ollama structured extraction failed, falling back to deterministic: {err}")

    # Deterministic fallback parser
    return fallback_deterministic_extractor(cv_text, candidate_name=candidate_name)
