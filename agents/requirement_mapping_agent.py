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
import hashlib
from agents.ollama_client import OllamaClient
from agents.db import DB


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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobRequirement":
        return cls(
            req_id=data.get("req_id", "REQ-01"),
            name=data.get("name", "Requirement"),
            category=data.get("category", "technical_skills"),
            description=data.get("description", ""),
            importance=data.get("importance", "MUST_HAVE"),
            expected_sources=data.get("expected_sources", ["cv", "interview"])
        )


class RequirementMappingAgent:
    """Agent responsible for decomposing JDs into verifiable requirement records with SHA-256 caching."""

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
        self._memory_cache: Dict[str, List[JobRequirement]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def compute_cache_key(self, jd_text: str, target_role: str) -> str:
        """Generates deterministic SHA-256 key from normalized role + JD content."""
        content = f"{target_role.strip().lower()}::{jd_text.strip()}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_cache_stats(self) -> Dict[str, int]:
        return {
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "size": len(self._memory_cache)
        }

    def map_requirements(self, jd_text: str, target_role: str = "Senior Software Engineer") -> List[JobRequirement]:
        """Maps JD text into structured JobRequirement objects with SHA-256 caching."""
        if not jd_text or not jd_text.strip():
            return self._default_requirements(target_role)

        cache_key = self.compute_cache_key(jd_text, target_role)

        # 1. Tier-1: In-memory cache hit
        if cache_key in self._memory_cache:
            self.cache_hits += 1
            return self._memory_cache[cache_key]

        # 2. Tier-2: Persistent DB cache hit
        try:
            db_cached = DB.get_cached_requirements(cache_key)
            if db_cached:
                reqs = [JobRequirement.from_dict(item) for item in db_cached]
                self._memory_cache[cache_key] = reqs
                self.cache_hits += 1
                return reqs
        except Exception:
            pass

        # 3. Cache miss: Compute via LLM or deterministic fallback
        self.cache_misses += 1
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

        # Store in both memory and persistent DB cache
        self._memory_cache[cache_key] = requirements
        try:
            DB.set_cached_requirements(cache_key, target_role, [r.to_dict() for r in requirements])
        except Exception:
            pass

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
        role_lower = (target_role or "").lower()

        # 1. Robotics & Perception / Autonomous Systems
        if any(k in role_lower for k in ["robot", "autonomous", "drone", "slam", "perception", "lidar"]):
            return [
                JobRequirement(
                    req_id="REQ-01",
                    name="Perception & Sensor Fusion",
                    category="technical_skills",
                    description="Expertise in multi-modal sensor fusion (LiDAR, Camera, ToF) and spatial calibration pipelines.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "assessment"]
                ),
                JobRequirement(
                    req_id="REQ-02",
                    name="SLAM & State Estimation",
                    category="architecture",
                    description="Developing visual odometry, graph-based SLAM, and map-free localization algorithms.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-03",
                    name="Robotics Software & Middleware (ROS/ROS2)",
                    category="technical_skills",
                    description="Proficiency integrating algorithms into ROS/ROS2, OpenCV, PyTorch, and C++/Python runtimes.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "assessment", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-04",
                    name="Research Rigor & Academic Publications",
                    category="leadership",
                    description="Demonstrated record of research publications in top robotics venues (IROS, ICRA, RA-L, ECCV).",
                    importance="IMPORTANT",
                    expected_sources=["cv", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-05",
                    name="Physical Drone/Robot Deployment & Testing",
                    category="production_experience",
                    description="Hands-on verification of algorithms on physical autonomous drones/robots and Sim-to-Real validation.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                )
            ]

        # 2. AI / Machine Learning / Deep Learning / LLM
        elif any(k in role_lower for k in ["ai", "machine learning", "deep learning", "nlp", "llm", "rag", "data science"]):
            return [
                JobRequirement(
                    req_id="REQ-01",
                    name="Deep Learning & Neural Architectures",
                    category="technical_skills",
                    description="Designing and training neural network models (Transformers, CNNs, BiLSTMs) using PyTorch or TensorFlow.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "assessment", "project"]
                ),
                JobRequirement(
                    req_id="REQ-02",
                    name="Retrieval & Vector Data Infrastructure",
                    category="architecture",
                    description="Architecting vector retrieval systems, dense embeddings, FAISS, and semantic search pipelines.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-03",
                    name="Empirical Benchmarking & Evaluation",
                    category="technical_skills",
                    description="Conducting rigorous benchmark evaluations, ablation studies, and error analysis across shared tasks.",
                    importance="IMPORTANT",
                    expected_sources=["cv", "interview", "assessment"]
                ),
                JobRequirement(
                    req_id="REQ-04",
                    name="Model Serving & Production Deployment",
                    category="production_experience",
                    description="Deploying machine learning models via containerized APIs (FastAPI, Docker, ONNX) with low latency.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-05",
                    name="Technical Initiative & Applied Research",
                    category="leadership",
                    description="Translating cutting-edge research literature into maintainable open-source code or production systems.",
                    importance="IMPORTANT",
                    expected_sources=["cv", "interview"]
                )
            ]

        # 3. Frontend & Full-Stack
        elif any(k in role_lower for k in ["frontend", "front-end", "fullstack", "full stack", "react", "web"]):
            return [
                JobRequirement(
                    req_id="REQ-01",
                    name="Modern TypeScript & Component Architecture",
                    category="technical_skills",
                    description="Proficiency in modern TypeScript, component lifecycles, and modular web architecture (React/Next.js).",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "assessment", "project"]
                ),
                JobRequirement(
                    req_id="REQ-02",
                    name="UI Performance & Responsive Design",
                    category="technical_skills",
                    description="Optimizing Core Web Vitals, sub-second rendering, accessibility standards, and fluid responsive layouts.",
                    importance="IMPORTANT",
                    expected_sources=["cv", "assessment", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-03",
                    name="API Integration & Asynchronous State",
                    category="architecture",
                    description="Clean integration with backend REST/GraphQL APIs, optimistic UI updates, and client-side caching.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-04",
                    name="Automated Testing & Build Tooling",
                    category="production_experience",
                    description="Comprehensive testing (Jest, Playwright, Cypress) and modern build pipelines (Vite, Webpack).",
                    importance="IMPORTANT",
                    expected_sources=["cv", "assessment"]
                ),
                JobRequirement(
                    req_id="REQ-05",
                    name="End-to-End Product Ownership",
                    category="leadership",
                    description="Track record of collaborating with design and product teams to deliver polished user experiences.",
                    importance="IMPORTANT",
                    expected_sources=["cv", "interview"]
                )
            ]

        # 4. Distributed Systems & Infrastructure
        elif any(k in role_lower for k in ["distributed", "infra", "kafka", "sre", "devops", "cloud", "backend"]):
            return [
                JobRequirement(
                    req_id="REQ-01",
                    name="Core Python & AsyncIO Concurrency",
                    category="technical_skills",
                    description="Proficiency in Python 3.10+, asynchronous programming, uvloop, and internal concurrency models.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "assessment", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-02",
                    name="Distributed Systems & Event Streaming",
                    category="architecture",
                    description="Hands-on experience deploying and operating event streams (Kafka/RabbitMQ) and partitioned event logs.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-03",
                    name="Database Sharding & Data Consistency",
                    category="architecture",
                    description="Managing distributed state consistency across partitioned databases and distributed caches.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-04",
                    name="Technical Architecture & RFC Writing",
                    category="leadership",
                    description="Authoring production RFCs, defining component boundaries, and leading cross-service migrations.",
                    importance="IMPORTANT",
                    expected_sources=["cv", "interview", "project"]
                ),
                JobRequirement(
                    req_id="REQ-05",
                    name="Production Operations & Reliability",
                    category="production_experience",
                    description="Managing live customer-facing systems, telemetry instrumentation, and production incident response.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "interview"]
                )
            ]

        # 5. General Software Engineer (Universal Default)
        else:
            return [
                JobRequirement(
                    req_id="REQ-01",
                    name="Core Programming & Clean Architecture",
                    category="technical_skills",
                    description="Strong proficiency in modern programming languages, data structures, algorithms, and clean design.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "assessment", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-02",
                    name="System Implementation & API Design",
                    category="architecture",
                    description="Designing, implementing, and deploying robust software services and clean API interfaces.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "project", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-03",
                    name="Persistence & Data Layer Competence",
                    category="technical_skills",
                    description="Experience with relational or NoSQL database querying, schema modeling, and data pipelines.",
                    importance="IMPORTANT",
                    expected_sources=["cv", "assessment", "project"]
                ),
                JobRequirement(
                    req_id="REQ-04",
                    name="Code Quality, Testing & CI/CD",
                    category="production_experience",
                    description="Writing testable code with automated unit and integration tests and continuous integration workflows.",
                    importance="MUST_HAVE",
                    expected_sources=["cv", "assessment", "interview"]
                ),
                JobRequirement(
                    req_id="REQ-05",
                    name="Technical Problem Solving & Delivery",
                    category="leadership",
                    description="Track record of solving complex technical problems and delivering working software end-to-end.",
                    importance="IMPORTANT",
                    expected_sources=["cv", "interview", "project"]
                )
            ]
