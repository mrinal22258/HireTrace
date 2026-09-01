"""
Mock Ollama Client for Offline Testing and CI Pipelines.

Provides deterministic, zero-GPU mocked LLM responses for:
1. Requirement Mapping
2. Unified Multi-Requirement Verification
3. Priority Review Questions
4. Contradiction Analysis

Enables 100% offline pipeline testing in GitHub Actions, container builds,
and sandboxes without running a live Ollama or vLLM daemon.
"""

from typing import Dict, Any, Optional, List, Tuple
import re
from agents.ollama_client import OllamaClient


class MockOllamaClient(OllamaClient):
    """Deterministic offline mock client mimicking local Ollama/vLLM inference."""

    def __init__(self, base_url: str = "http://mock-ollama:11434", model: str = "mock-qwen2.5:3b"):
        super().__init__(base_url=base_url, model=model)
        self.mock_mode = True

    def is_available(self) -> bool:
        return True

    def check_health(self) -> Tuple[bool, str]:
        return True, "Mock Ollama backend online (Offline / CI mode active)"

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        self.total_calls += 1
        self.successful_calls += 1
        prompt_lower = prompt.lower()

        # 1. Requirement Mapping Agent
        if "decompose into 4-6 key requirements" in prompt_lower or "job description" in prompt_lower:
            # 1a. Robotics / Perception
            if any(k in prompt_lower for k in ["robot", "autonomous", "drone", "slam", "perception", "lidar"]):
                return {
                    "requirements": [
                        {
                            "req_id": "REQ-01",
                            "name": "Perception & Sensor Fusion",
                            "category": "perception_fusion",
                            "weight": 1.4,
                            "description": "Multi-modal sensor fusion (LiDAR, Camera, ToF) and spatial calibration.",
                            "rubric": "Evaluates LiDAR-camera calibration, ToF sensing, and sensor fusion algorithms."
                        },
                        {
                            "req_id": "REQ-02",
                            "name": "SLAM & State Estimation",
                            "category": "state_estimation",
                            "weight": 1.4,
                            "description": "Visual SLAM, map-free localization, and obstacle avoidance pipelines.",
                            "rubric": "Verifies monocular/stereo SLAM, visual compass, and trajectory evaluation."
                        },
                        {
                            "req_id": "REQ-03",
                            "name": "Robotics Software & Middleware (ROS/ROS2)",
                            "category": "robotics_software",
                            "weight": 1.2,
                            "description": "Proficiency integrating perception pipelines into ROS/ROS2, OpenCV, and PyTorch.",
                            "rubric": "Assesses ROS2 package integration, node communication, and real-time inference."
                        },
                        {
                            "req_id": "REQ-04",
                            "name": "Research Rigor & Academic Publications",
                            "category": "research_publications",
                            "weight": 1.2,
                            "description": "Peer-reviewed research publications in top robotics venues (IROS, ICRA, RA-L).",
                            "rubric": "Verifies authorship on papers, benchmark metrics (ATE, ARE, F1), and novel research."
                        },
                        {
                            "req_id": "REQ-05",
                            "name": "Physical Drone/Robot Deployment & Sim-to-Real",
                            "category": "experimental_validation",
                            "weight": 1.3,
                            "description": "Empirical testing on real drones/robots and Sim-to-Real simulation pipelines.",
                            "rubric": "Evaluates hardware drone flight tests, Gazebo simulations, and robust outdoor deployment."
                        }
                    ],
                    "_latency_sec": 0.01,
                    "_model": self.model
                }

            # 1b. AI / Machine Learning
            elif any(k in prompt_lower for k in ["machine learning", "deep learning", "nlp", "llm", "rag"]):
                return {
                    "requirements": [
                        {
                            "req_id": "REQ-01",
                            "name": "Deep Learning & Neural Architectures",
                            "category": "deep_learning",
                            "weight": 1.3,
                            "description": "Modern neural architectures (Transformers, CNNs) using PyTorch or TensorFlow.",
                            "rubric": "Evaluates model design, loss function tuning, and training workflows."
                        },
                        {
                            "req_id": "REQ-02",
                            "name": "Retrieval & Vector Data Infrastructure",
                            "category": "retrieval_rag",
                            "weight": 1.3,
                            "description": "Vector databases, dense embeddings, FAISS, and semantic search pipelines.",
                            "rubric": "Verifies embedding models, chunking strategies, and vector indexing."
                        },
                        {
                            "req_id": "REQ-03",
                            "name": "Empirical Benchmarking & Evaluation",
                            "category": "benchmarking",
                            "weight": 1.1,
                            "description": "Rigorous benchmark evaluations, ablation studies, and error analysis.",
                            "rubric": "Assesses metric reporting (F1, BLEU, latency) and test set validation."
                        },
                        {
                            "req_id": "REQ-04",
                            "name": "Model Serving & Production Deployment",
                            "category": "production_ml",
                            "weight": 1.2,
                            "description": "Deploying machine learning models via containerized APIs (FastAPI, Docker, ONNX).",
                            "rubric": "Evaluates inference latency, memory footprint, and horizontal scaling."
                        },
                        {
                            "req_id": "REQ-05",
                            "name": "Applied Technical Innovation",
                            "category": "innovation",
                            "weight": 1.0,
                            "description": "Translating novel research papers into production systems and open-source packages.",
                            "rubric": "Assesses code contribution quality and engineering problem solving."
                        }
                    ],
                    "_latency_sec": 0.01,
                    "_model": self.model
                }

            # 1c. Default Distributed Systems & Software Engineering
            return {
                "requirements": [
                    {
                        "req_id": "REQ-01",
                        "name": "Advanced Python & AsyncIO Concurrency",
                        "category": "language_concurrency",
                        "weight": 1.2,
                        "description": "Deep mastery of asynchronous Python, event loop mechanics, and concurrency.",
                        "rubric": "Evaluates asyncio, uvloop, or thread/process pooling expertise."
                    },
                    {
                        "req_id": "REQ-02",
                        "name": "Distributed Systems & Streaming (Kafka)",
                        "category": "distributed_systems",
                        "weight": 1.5,
                        "description": "Hands-on experience deploying and operating Apache Kafka or event streams.",
                        "rubric": "Verifies Kafka producer/consumer tuning, partitioning, and cluster rebalancing."
                    },
                    {
                        "req_id": "REQ-03",
                        "name": "Database & High-Scale Persistence",
                        "category": "database_persistence",
                        "weight": 1.0,
                        "description": "Relational or distributed persistence (PostgreSQL, Redis, Vector DBs).",
                        "rubric": "Verifies query optimization, transaction isolation, and caching layers."
                    },
                    {
                        "req_id": "REQ-04",
                        "name": "System Architecture & Technical RFCs",
                        "category": "system_design",
                        "weight": 1.0,
                        "description": "Authoring technical specifications, system design docs, and API contracts.",
                        "rubric": "Assesses RFC quality, boundary definitions, and component interfaces."
                    },
                    {
                        "req_id": "REQ-05",
                        "name": "Production Operations & Reliability",
                        "category": "production_engineering",
                        "weight": 1.3,
                        "description": "Production on-call, telemetry, debugging distributed deadlocks and SLAs.",
                        "rubric": "Evaluates incident triage, metrics instrumentation, and zero-downtime deployments."
                    }
                ],
                "_latency_sec": 0.01,
                "_model": self.model
            }

        # 2. Unified Verification Agent (verify_all_unified)
        if "verify each requirement" in prompt_lower or "verifications" in prompt_lower:
            verifications: List[Dict[str, Any]] = []

            # Check candidate archetype signals from prompt context
            is_alexander_sterling = "alexander sterling" in prompt_lower or "case_15" in prompt_lower or "finflow" in prompt_lower
            is_hannah_scott = "hannah scott" in prompt_lower or "case_08" in prompt_lower
            is_evan_brooks = "evan brooks" in prompt_lower or "case_12" in prompt_lower
            is_jordan_hayes = "jordan hayes" in prompt_lower or "case_09" in prompt_lower

            # Extract requirement IDs requested in prompt
            req_ids = re.findall(r"(REQ-\d+)", prompt)
            unique_req_ids = list(dict.fromkeys(req_ids)) if req_ids else ["REQ-01", "REQ-02", "REQ-03", "REQ-04", "REQ-05"]

            for req_id in unique_req_ids:
                if is_alexander_sterling:
                    # Deceptive centerpiece: supported on Python/RFC, contradicted on Kafka & 8+ yrs tenure
                    if req_id in ("REQ-02", "REQ-05"):
                        status = "CONTRADICTED"
                        synthesis = "Critical cross-source contradiction between CV claims and interview/assessment evidence."
                    else:
                        status = "SUPPORTED"
                        synthesis = "Documented technical evidence satisfies requirement criteria."
                elif is_hannah_scott or is_jordan_hayes:
                    # Weak candidates
                    if req_id in ("REQ-01", "REQ-03"):
                        status = "SUPPORTED"
                        synthesis = "Found basic proficiency evidence."
                    else:
                        status = "INSUFFICIENT_EVIDENCE"
                        synthesis = "Insufficient evidence of required production scale and leadership."
                elif is_evan_brooks:
                    # Insufficient evidence archetype (lacks Kafka streaming corroboration)
                    if req_id == "REQ-02":
                        status = "INSUFFICIENT_EVIDENCE"
                        synthesis = "Missing necessary corroboration for advanced Kafka streaming and cluster rebalancing."
                    else:
                        status = "SUPPORTED"
                        synthesis = "Documented technical evidence satisfies requirement criteria."
                else:
                    # Standard strong match (Sarah Chen, Marcus Vance, etc.)
                    status = "SUPPORTED"
                    synthesis = "Consistent cross-source evidence verified across CV, Interview, and Technical documents."

                verifications.append({
                    "req_id": req_id,
                    "status": status,
                    "confidence": 0.92,
                    "synthesis": synthesis,
                    "supporting_citations": ["CV-001", "INT-001"],
                    "discrepancies": []
                })

            return {
                "verifications": verifications,
                "_latency_sec": 0.02,
                "_model": self.model
            }

        # 3. Recommendation Writer Priority Questions
        if "priority questions" in prompt_lower or "hiring committee advisor" in prompt_lower:
            return {
                "priority_questions": [
                    "Verify high-scale production trade-offs in candidate's primary architecture project",
                    "Review code quality standards and testing practices across past contributions",
                    "Assess team leadership and cross-functional communication style"
                ],
                "_latency_sec": 0.01,
                "_model": self.model
            }

        # Default generic JSON structure
        return {
            "status": "SUPPORTED",
            "confidence": 0.9,
            "synthesis": "Evidence verified successfully.",
            "_latency_sec": 0.01,
            "_model": self.model
        }
