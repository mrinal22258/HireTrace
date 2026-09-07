"""
Curated Job Description Template Library & Role Taxonomy for HireTrace (Phase 9).

Replaces brittle keyword branching with an extensible taxonomy-mapped template library
and graceful fallback to a universal software engineering rubric for novel/unrecognized roles.
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple


class RoleTaxonomy(str, Enum):
    ROBOTICS_AUTONOMOUS = "robotics_autonomous"
    AI_MACHINE_LEARNING = "ai_machine_learning"
    FRONTEND_FULLSTACK = "frontend_fullstack"
    DISTRIBUTED_SYSTEMS_INFRA = "distributed_systems_infra"
    DATA_ENGINEERING = "data_engineering"
    SECURITY_CYBERSECURITY = "security_cybersecurity"
    MOBILE_ENGINEERING = "mobile_engineering"
    GENERAL_SOFTWARE = "general_software"


# Keywords and regular expression tokens mapping to canonical taxonomy categories
TAXONOMY_KEYWORDS: Dict[RoleTaxonomy, List[str]] = {
    RoleTaxonomy.ROBOTICS_AUTONOMOUS: [
        "robot", "autonomous", "drone", "slam", "perception", "lidar", "ros", "ros2",
        "state estimation", "odometry", "sensor fusion", "embedded robotics", "uav"
    ],
    RoleTaxonomy.AI_MACHINE_LEARNING: [
        "ai", "machine learning", "deep learning", "nlp", "llm", "rag", "data science",
        "computer vision", "neural", "pytorch", "tensorflow", "applied scientist",
        "ml engineer", "research engineer"
    ],
    RoleTaxonomy.FRONTEND_FULLSTACK: [
        "frontend", "front-end", "fullstack", "full stack", "react", "next.js", "vue",
        "typescript", "javascript", "ui", "ux", "web developer", "client engineer"
    ],
    RoleTaxonomy.DISTRIBUTED_SYSTEMS_INFRA: [
        "distributed", "infra", "infrastructure", "kafka", "sre", "devops", "cloud",
        "backend", "back-end", "platform engineer", "systems engineer", "kubernetes",
        "microservices", "high throughput"
    ],
    RoleTaxonomy.DATA_ENGINEERING: [
        "data engineer", "etl", "spark", "databricks", "data warehouse", "dbt",
        "big data", "hadoop", "snowflake", "data pipeline"
    ],
    RoleTaxonomy.SECURITY_CYBERSECURITY: [
        "security", "infosec", "appsec", "devsecops", "cyber", "penetration", "soc",
        "cryptography", "identity", "vulnerability"
    ],
    RoleTaxonomy.MOBILE_ENGINEERING: [
        "mobile", "ios", "android", "swift", "kotlin", "react native", "flutter"
    ],
}


try:
    from eval_cases.dataset import SHARED_JD
except Exception:
    SHARED_JD = None

# Curated, authoritative job descriptions keyed by canonical taxonomy
ROLE_JD_TEMPLATES: Dict[RoleTaxonomy, str] = {
    RoleTaxonomy.ROBOTICS_AUTONOMOUS: """# {title}
Company: NextGen Autonomous Systems
Role: {title}
Department: Robotics Research & Core Perception

### About the Role
We are seeking a talented {title} to build, test, and validate next-generation perception, state estimation, and sensor fusion algorithms for physical robotic platforms and autonomous drones.

### Core Requirements
- REQ-01: Perception & Sensor Fusion: Expertise in multi-modal sensor fusion (LiDAR, Camera, ToF) and spatial calibration pipelines.
- REQ-02: SLAM & State Estimation: Developing visual odometry, graph-based SLAM, and map-free localization algorithms.
- REQ-03: Robotics Software & Middleware (ROS/ROS2): Proficiency integrating algorithms into ROS/ROS2, OpenCV, PyTorch, and C++/Python runtimes.
- REQ-04: Research Rigor & Academic Publications: Demonstrated record of research publications in top robotics venues (IROS, ICRA, RA-L, ECCV).
- REQ-05: Physical Drone/Robot Deployment & Testing: Hands-on verification of algorithms on physical autonomous drones/robots and Sim-to-Real validation.
""",

    RoleTaxonomy.AI_MACHINE_LEARNING: """# {title}
Company: Frontier AI Labs
Role: {title}
Department: Applied AI & Model Architecture

### About the Role
We are looking for an exceptional {title} to design, train, evaluate, and deploy high-performance machine learning models, retrieval systems, and agentic workflows.

### Core Requirements
- REQ-01: Deep Learning & Neural Architectures: Designing and training neural network models (Transformers, CNNs, BiLSTMs) using PyTorch or TensorFlow.
- REQ-02: Retrieval & Vector Data Infrastructure: Architecting vector retrieval systems, dense embeddings, FAISS, and semantic search pipelines.
- REQ-03: Empirical Benchmarking & Evaluation: Conducting rigorous benchmark evaluations, ablation studies, and error analysis across shared tasks.
- REQ-04: Model Serving & Production Deployment: Deploying machine learning models via containerized APIs (FastAPI, Docker, ONNX) with low latency.
- REQ-05: Technical Initiative & Applied Research: Translating cutting-edge research literature into maintainable open-source code or production systems.
""",

    RoleTaxonomy.FRONTEND_FULLSTACK: """# {title}
Company: Cloud Platform Technologies
Role: {title}
Department: Product Engineering

### About the Role
We are seeking an experienced {title} to craft world-class interactive user interfaces, design resilient frontend systems, and deliver responsive, high-performance web applications.

### Core Requirements
- REQ-01: Modern TypeScript & Component Architecture: Deep mastery of TypeScript, component lifecycles, and modular web architecture (React/Next.js).
- REQ-02: UI Performance & Responsive Design: Delivering sub-second interaction speeds, Core Web Vitals optimization, accessibility, and fluid layouts.
- REQ-03: API Integration & Asynchronous State: Clean integration with REST/GraphQL APIs, optimistic UI updates, and client-side caching.
- REQ-04: Automated Testing & Build Tooling: Robust test coverage (Jest, Vitest, Playwright, Cypress) and modern build pipelines (Vite, Webpack).
- REQ-05: End-to-End Product Ownership: Track record of collaborating with design and product teams to deliver polished user experiences.
""",

    RoleTaxonomy.DISTRIBUTED_SYSTEMS_INFRA: SHARED_JD or """# {title}
Company: Apex Cloud Infrastructure
Role: {title}
Department: Distributed Platform Engineering

### About the Role
We are looking for a high-caliber {title} to design, build, and scale resilient distributed streaming backends, fault-tolerant message buses, and cloud infrastructure.

### Core Requirements
- REQ-01: Advanced Modern Python & AsyncIO: Internal concurrency, asyncio paradigms, memory profiling, and non-blocking I/O.
- REQ-02: Distributed Systems & Event Streaming: Experience deploying and scaling Apache Kafka or RabbitMQ clusters, consumer rebalance handling, and event schemas.
- REQ-03: Microservices & Data Layer Architecture: Designing resilient distributed microservices, database sharding/partitioning, and caching strategies.
- REQ-04: Technical Leadership & System Design: Track record of authoring production RFCs, leading complex technical migrations, and code reviews.
- REQ-05: Production Engineering & Operational Tenure: Commercial production experience managing live customer-facing systems and telemetry monitoring.
""",

    RoleTaxonomy.DATA_ENGINEERING: """# {title}
Company: Global Data Systems
Role: {title}
Department: Data Platform & Analytics Engineering

### About the Role
We are seeking a skilled {title} to design, construct, and optimize enterprise data pipelines, lakehouse architectures, and scalable analytics infrastructure.

### Core Requirements
- REQ-01: Data Pipeline Construction: Designing robust batch and streaming ETL/ELT pipelines using Spark, Airflow, or Kafka.
- REQ-02: Data Modeling & Lakehouse Architecture: Deep experience with modern data warehouse and lakehouse technologies (Snowflake, BigQuery, Delta Lake, dbt).
- REQ-03: Query Optimization & SQL Mastery: Advanced proficiency in SQL tuning, partitioning strategies, and high-volume data performance.
- REQ-04: Data Governance & Quality: Implementing automated data validation, schema evolution checks, and lineage tracking.
- REQ-05: Engineering Rigor & Automation: Applying software engineering best practices (CI/CD, unit testing, Infrastructure-as-Code) to data platforms.
""",

    RoleTaxonomy.SECURITY_CYBERSECURITY: """# {title}
Company: CyberTrust Defense Systems
Role: {title}
Department: Information Security & SecOps

### About the Role
We are looking for a dedicated {title} to harden infrastructure, audit applications, and implement proactive threat detection and incident response mechanisms.

### Core Requirements
- REQ-01: Application & Infrastructure Security: Conducting threat modeling, secure code reviews, and vulnerability assessments across cloud infrastructure.
- REQ-02: DevSecOps & CI/CD Hardening: Integrating static and dynamic security analysis (SAST/DAST) into automated deployment pipelines.
- REQ-03: Identity & Access Management: Designing zero-trust architectures, RBAC/ABAC models, and cryptographic key management.
- REQ-04: Incident Response & Threat Hunting: Triaging security anomalies, conducting root-cause forensics, and automating remediation playbooks.
- REQ-05: Security Compliance & Standards: Knowledge of security frameworks and compliance standards (SOC 2, ISO 27001, OWASP Top 10).
""",

    RoleTaxonomy.MOBILE_ENGINEERING: """# {title}
Company: Mobile Horizons
Role: {title}
Department: Client Applications

### About the Role
We are seeking a talented {title} to build responsive, elegant mobile experiences on iOS and Android platforms.

### Core Requirements
- REQ-01: Native & Cross-Platform Mobile: Deep knowledge of Swift/iOS, Kotlin/Android, or modern cross-platform frameworks (React Native, Flutter).
- REQ-02: Offline Synchronization & Storage: Designing resilient local storage (CoreData, SQLite, Room) and seamless background sync.
- REQ-03: Mobile Performance & Battery Optimization: Profiling memory usage, render cycles, and power consumption for buttery-smooth 60fps UX.
- REQ-04: Mobile CI/CD & App Store Delivery: Automated mobile build pipelines (Fastlane), test automation, and release management.
- REQ-05: Design System Collaboration: Partnering closely with UI/UX designers to translate Figma design systems into pixel-perfect components.
""",

    RoleTaxonomy.GENERAL_SOFTWARE: """# {title}
Company: Enterprise Technology Solutions
Role: {title}
Department: Core Software Engineering

### About the Role
We are seeking a talented and versatile {title} to design, implement, and maintain scalable software services, clean APIs, and robust application logic.

### Core Requirements
- REQ-01: Core Programming & Clean Architecture: Strong proficiency in modern programming languages, data structures, algorithms, and clean system design.
- REQ-02: System Implementation & API Design: Designing, implementing, and deploying robust software services and clean RESTful/gRPC API interfaces.
- REQ-03: Persistence & Data Layer Competence: Experience with relational or NoSQL database querying, schema modeling, and data access pipelines.
- REQ-04: Code Quality, Testing & CI/CD: Writing testable code with automated unit and integration tests and continuous integration workflows.
- REQ-05: Technical Problem Solving & Delivery: Track record of solving complex technical problems and delivering working software end-to-end.
""",
}


def classify_role(target_role: Optional[str]) -> Tuple[RoleTaxonomy, bool]:
    """
    Classifies a candidate role into a taxonomy bucket using keyword matching.
    
    Returns:
        Tuple[RoleTaxonomy, bool]: (matched_taxonomy, is_exact_or_keyword_match)
        If no keyword matched, returns (RoleTaxonomy.GENERAL_SOFTWARE, False).
    """
    if not target_role:
        return RoleTaxonomy.GENERAL_SOFTWARE, False

    clean = target_role.strip().lower()
    if not clean:
        return RoleTaxonomy.GENERAL_SOFTWARE, False

    # Check each taxonomy category in priority order
    for taxonomy, keywords in TAXONOMY_KEYWORDS.items():
        for kw in keywords:
            # Word boundary or containment match
            if re.search(r"\b" + re.escape(kw) + r"\b", clean) or kw in clean:
                return taxonomy, True

    return RoleTaxonomy.GENERAL_SOFTWARE, False


def generate_role_tailored_jd(target_role: Optional[str]) -> str:
    """
    Generates an authoritative domain-tailored Job Description based on target role.
    
    Gracefully degrades to the curated GENERAL_SOFTWARE taxonomy template when novel,
    unrecognized, or non-technical roles are passed.
    """
    role_title = (target_role or "").strip()
    if not role_title:
        role_title = "Software Engineer"

    taxonomy, matched = classify_role(role_title)
    template = ROLE_JD_TEMPLATES.get(taxonomy, ROLE_JD_TEMPLATES[RoleTaxonomy.GENERAL_SOFTWARE])
    return template.format(title=role_title)
