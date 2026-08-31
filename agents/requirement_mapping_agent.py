"""
Requirement Mapping Agent for HireTrace.

Parses the Job Description (JD) and target role profile into discrete, measurable
requirements (e.g., REQ-01 Python, REQ-02 Distributed Systems, REQ-03 Leadership).
Identifies which evidence sources (CV, Interview, Assessment, Project) should substantiate each requirement.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json
import re
from agents.ollama_client import OllamaClient


@dataclass
class JobRequirement:
    """A discrete role requirement derived from the JD."""
    req_id: str                   # e.g., "REQ-01"
    name: str                     # e.g., "Python & Async Backend"
    category: str                 # "technical_skills", "distributed_systems", "leadership", "tenure"
    description: str              # Description of expected competency
    importance: str               # "MUST_HAVE", "IMPORTANT", "NICE_TO_HAVE"
    expected_sources: List[str]   # ["cv", "interview", "assessment", "project"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "req_id": self.req_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "importance": self.importance,
            "expected_sources": self.expected_sources
        }


class RequirementMappingAgent:
    """Agent responsible for decomposing JDs into verifiable requirement records."""

    SYSTEM_PROMPT = """You are a senior hiring architect. Analyze the provided Job Description (JD).
Extract the key requirements as discrete, verifiable items.
Output strictly JSON matching this structure:
{
  "requirements": [
    {
      "req_id": "REQ-01",
      "name": "Short requirement name",
      "category": "technical_skills" | "architecture" | "leadership" | "production_experience",
      "description": "What is required",
      "importance": "MUST_HAVE" | "IMPORTANT" | "NICE_TO_HAVE",
      "expected_sources": ["cv", "interview", "assessment", "project"]
    }
  ]
}"""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.client = ollama_client or OllamaClient()

    def map_requirements(self, jd_text: str, target_role: str = "Senior Software Engineer") -> List[JobRequirement]:
        """Maps JD text into structured JobRequirement objects."""
        if not jd_text or not jd_text.strip():
            return self._default_requirements(target_role)

        prompt = f"Role: {target_role}\n\nJob Description:\n{jd_text}\n\nDecompose into 4-6 key requirements:"
        response = self.client.generate_json(prompt=prompt, system_prompt=self.SYSTEM_PROMPT, max_tokens=768)

        req_list = response.get("requirements", [])
        if not req_list and "items" in response:
            req_list = response["items"]

        requirements = []
        if isinstance(req_list, list) and len(req_list) > 0:
            for idx, item in enumerate(req_list, 1):
                if isinstance(item, dict):
                    req_id = item.get("req_id") or f"REQ-{idx:02d}"
                    name = str(item.get("name", f"Requirement {idx}")).strip()
                    
                    # Strict category validation
                    raw_cat = str(item.get("category", "technical_skills")).lower().strip()
                    valid_cats = {"technical_skills", "architecture", "leadership", "production_experience", "distributed_systems"}
                    category = raw_cat if raw_cat in valid_cats else "technical_skills"
                    
                    desc = str(item.get("description", name)).strip()
                    
                    # Strict importance validation
                    raw_imp = str(item.get("importance", "MUST_HAVE")).upper().strip()
                    valid_imps = {"MUST_HAVE", "IMPORTANT", "NICE_TO_HAVE"}
                    importance = raw_imp if raw_imp in valid_imps else ("MUST_HAVE" if idx <= 2 else "IMPORTANT")
                    
                    raw_sources = item.get("expected_sources", ["cv", "interview"])
                    valid_sources = [str(s).lower().strip() for s in raw_sources if str(s).lower().strip() in ("cv", "interview", "assessment", "project", "jd")]
                    sources = valid_sources or ["cv", "interview"]

                    requirements.append(JobRequirement(
                        req_id=req_id,
                        name=name,
                        category=category,
                        description=desc,
                        importance=importance,
                        expected_sources=sources
                    ))

        if not requirements:
            # Deterministic fallback parser from JD text
            requirements = self._fallback_parse_jd(jd_text, target_role)

        return requirements

    def _fallback_parse_jd(self, jd_text: str, target_role: str) -> List[JobRequirement]:
        """Deterministic rule-based fallback if Ollama returns empty or invalid structure."""
        requirements = []
        lines = [l.strip() for l in jd_text.splitlines() if l.strip()]
        req_idx = 1

        for line in lines:
            if line.startswith(("-", "*", "•", "1.", "2.", "3.", "4.", "5.")):
                clean = re.sub(r"^[-*•\d\.]+\s*", "", line).strip()
                if len(clean) > 10:
                    category = "technical_skills"
                    if any(k in clean.lower() for k in ["lead", "mentor", "manage", "ownership"]):
                        category = "leadership"
                    elif any(k in clean.lower() for k in ["scale", "distributed", "kafka", "architect"]):
                        category = "architecture"
                    elif any(k in clean.lower() for k in ["year", "tenure", "production", "experience"]):
                        category = "production_experience"

                    requirements.append(JobRequirement(
                        req_id=f"REQ-{req_idx:02d}",
                        name=clean[:40] + ("..." if len(clean) > 40 else ""),
                        category=category,
                        description=clean,
                        importance="MUST_HAVE" if req_idx <= 2 else "IMPORTANT",
                        expected_sources=["cv", "interview", "assessment"]
                    ))
                    req_idx += 1
                    if req_idx > 5:
                        break

        if not requirements:
            requirements = self._default_requirements(target_role)
        return requirements

    def _default_requirements(self, target_role: str) -> List[JobRequirement]:
        return [
            JobRequirement(
                req_id="REQ-01",
                name="Core Python & AsyncIO",
                category="technical_skills",
                description="Proficiency in Python 3.10+, asynchronous programming, and clean architecture.",
                importance="MUST_HAVE",
                expected_sources=["cv", "assessment", "interview"]
            ),
            JobRequirement(
                req_id="REQ-02",
                name="Distributed Systems & Message Queues",
                category="architecture",
                description="Hands-on experience designing and operating event streams (Kafka/RabbitMQ) and distributed state.",
                importance="MUST_HAVE",
                expected_sources=["cv", "project", "interview"]
            ),
            JobRequirement(
                req_id="REQ-03",
                name="Technical Leadership & Initiative",
                category="leadership",
                description="Demonstrated track record of leading migrations, architectural decisions, and mentoring engineers.",
                importance="IMPORTANT",
                expected_sources=["cv", "interview", "project"]
            ),
            JobRequirement(
                req_id="REQ-04",
                name="Production Tenure & Operational Reliability",
                category="production_experience",
                description="At least 3+ years of commercial production experience managing live services and on-call.",
                importance="MUST_HAVE",
                expected_sources=["cv", "interview"]
            )
        ]
