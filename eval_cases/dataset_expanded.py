"""
Expanded 50-Case Scientific Benchmark Suite for HireTrace (Phase 3).

Spans 5 Canonical Role Taxonomies from agents.jd_templates:
1. Distributed Systems & Core Backend (15 Core Cases from dataset.py)
2. Adversarial & Injection Containment Track (8 Adversarial Cases from adversarial_cases.py)
3. AI & Machine Learning Systems (6 Cases: 2 Strong, 2 Medium, 1 Weak, 1 Contradiction)
4. Frontend & Fullstack Architecture (6 Cases: 2 Strong, 2 Medium, 1 Weak, 1 Contradiction)
5. Robotics & Autonomous Perception (5 Cases: 2 Strong, 1 Medium, 1 Weak, 1 Contradiction)
6. Data Platform & Lakehouse Engineering (5 Cases: 2 Strong, 1 Medium, 1 Weak, 1 Contradiction)
7. DevOps, SRE & Cloud Security (5 Cases: 2 Strong, 1 Medium, 1 Weak, 1 Contradiction)

Total Suite: 15 + 8 + 6 + 6 + 5 + 5 + 5 = 50 Cases with Rigorous Ground Truth.
"""

import os
import sys
from typing import Dict, List, Any

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from eval_cases.dataset import CASES as CORE_15_CASES
from eval.adversarial_cases import ADVERSARIAL_CASES


ADDITIONAL_DOMAIN_CASES: List[Dict[str, Any]] = [
    # =========================================================================
    # AI & MACHINE LEARNING SYSTEMS (6 Cases)
    # =========================================================================
    {
        "candidate_id": "case_16_aiml_strong_01",
        "name": "Dr. Linnea Holmgren",
        "target_role": "Senior Applied AI & Model Architect",
        "category": "aiml_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 96.0,
            "expert_scores": {"reviewer_1": 94, "reviewer_2": 95, "reviewer_3": 96}
        },
        "cv_text": """# Dr. Linnea Holmgren - Senior AI Research Scientist
PhD in Computational Intelligence (ETH Zurich, 2021). 4+ years industry experience scaling transformer models.
## Experience
Staff Applied Scientist at NeuroScale Labs (2021 - Present | 3.8 years)
- Trained and distilled 14B parameter multimodal embedding models using PyTorch FSDP across 128 H100 GPUs.
- Designed vector retrieval architecture indexing 80M documents using FAISS and ScaNN, reducing p99 search latency to 28ms.
- Authored 3 NeurIPS/ICLR papers on parameter-efficient fine-tuning (LoRA/QLoRA) and uncertainty calibration.
""",
        "interview_notes": """# Technical Interview: Dr. Linnea Holmgren
Interviewer: Dr. Aris Thorne
Aris: "How did you handle memory fragmentation during PyTorch distributed training?"
Linnea: "We implemented custom PyTorch CUDA memory allocators and activated flash-attention-v2 with gradient checkpointing, reducing per-node VRAM overhead by 42%."
""",
        "technical_assessment": """# Technical Assessment: Dr. Linnea Holmgren
Score: 96 / 100 | Result: Exceptional
Successfully implemented custom LoRA projection kernel and optimized vector index recall to 98.4% under latency constraints.
"""
    },
    {
        "candidate_id": "case_17_aiml_strong_02",
        "name": "Tariq Mansour",
        "target_role": "Senior Applied AI & Model Architect",
        "category": "aiml_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 95.0,
            "expert_scores": {"reviewer_1": 92, "reviewer_2": 93, "reviewer_3": 91}
        },
        "cv_text": """# Tariq Mansour, Senior ML Systems Engineer
## Experience
Lead ML Engineer at TensorWave Systems (2020 - Present | 4.5 years)
- Productionized high-throughput LLM serving clusters using vLLM and TensorRT-LLM delivering 4,200 tokens/sec.
- Architected semantic chunking and dense-sparse hybrid retrieval pipelines for enterprise financial compliance.
""",
        "interview_notes": """# Technical Interview: Tariq Mansour
Interviewer: Dr. Aris Thorne
Aris: "Tell us about continuous batching in vLLM."
Tariq: "PagedAttention eliminated memory fragmentation. We paired dynamic request scheduling with speculative decoding using draft models, doubling sustained concurrency."
""",
        "technical_assessment": """# Technical Assessment: Tariq Mansour
Score: 92 / 100
High marks on model serving infrastructure, tensor parallelism, and batching dynamics.
"""
    },
    {
        "candidate_id": "case_18_aiml_med_01",
        "name": "Clara Vane",
        "target_role": "Senior Applied AI & Model Architect",
        "category": "aiml_med",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 90.0,
            "expert_scores": {"reviewer_1": 78, "reviewer_2": 80, "reviewer_3": 79}
        },
        "cv_text": """# Clara Vane - Machine Learning Engineer
3 years experience developing computer vision and NLP classification models using PyTorch and HuggingFace.
Experience at VisionCorp (2022 - Present | 2.5 years) building ResNet and BERT classifiers.
""",
        "interview_notes": """# Interview: Clara Vane
Interviewer: Dr. Aris Thorne
Clara demonstrated solid classical ML modeling and scikit-learn/PyTorch fluency, but had limited exposure to multi-node distributed training (FSDP/Megatron).
""",
        "technical_assessment": """# Technical Assessment: Clara Vane
Score: 80 / 100
Passed classification and feature engineering tests. Basic transformer fine-tuning completed.
"""
    },
    {
        "candidate_id": "case_19_aiml_med_02",
        "name": "Rohan Gupta",
        "target_role": "Senior Applied AI & Model Architect",
        "category": "aiml_med",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 88.0,
            "expert_scores": {"reviewer_1": 75, "reviewer_2": 76, "reviewer_3": 77}
        },
        "cv_text": """# Rohan Gupta - Applied ML Engineer
2.5 years experience implementing RAG applications with LangChain, ChromaDB, and OpenAI API wrappers.
Senior Associate at DataMinds (2022 - Present).
""",
        "interview_notes": """# Interview: Rohan Gupta
Rohan demonstrated good understanding of prompt engineering and document loaders, but lacks low-level GPU kernel optimization or open-weights model fine-tuning depth.
""",
        "technical_assessment": """# Technical Assessment: Rohan Gupta
Score: 76 / 100
Clean RAG pipeline setup, but basic understanding of quantization and KV cache dynamics.
"""
    },
    {
        "candidate_id": "case_20_aiml_weak_01",
        "name": "Felix Baum",
        "target_role": "Senior Applied AI & Model Architect",
        "category": "aiml_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 90.0,
            "expert_scores": {"reviewer_1": 45, "reviewer_2": 42, "reviewer_3": 44}
        },
        "cv_text": """# Felix Baum - AI Enthusiast & Junior Developer
Self-taught developer. 6 months experience experimenting with ChatGPT prompts and creating simple Streamlit demos.
""",
        "interview_notes": """# Interview: Felix Baum
Felix was unable to explain how backpropagation works, could not describe gradient descent, and has never trained a model from scratch.
""",
        "technical_assessment": """# Technical Assessment: Felix Baum
Score: 35 / 100
Failed basic PyTorch tensor manipulation and model training loop implementation.
"""
    },
    {
        "candidate_id": "case_21_aiml_contradiction_01",
        "name": "Zackary Stone",
        "target_role": "Senior Applied AI & Model Architect",
        "category": "aiml_contradiction",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "tenure_conflict",
            "expected_consistency": 25.0,
            "expert_scores": {"reviewer_1": 48, "reviewer_2": 50, "reviewer_3": 52}
        },
        "cv_text": """# Zackary Stone - Principal AI Architect
Senior Principal Architect at CognitionAI (Jan 2018 - Present | 7+ years)
- Led development of CognitionAI foundation model training cluster and authored company patents.
""",
        "interview_notes": """# Interview Notes: Zackary Stone
Interviewer: Dr. Aris Thorne
Aris: "Can you confirm your tenure at CognitionAI?"
Zackary: "I actually joined CognitionAI 8 months ago as a junior contractor."
""",
        "technical_assessment": """# Technical Assessment: Zackary Stone
Score: 70 / 100
Candidate completed basic model deployment, but interview revealed serious cross-source tenure discrepancy.
"""
    },

    # =========================================================================
    # FRONTEND & FULLSTACK ARCHITECTURE (6 Cases)
    # =========================================================================
    {
        "candidate_id": "case_22_fe_strong_01",
        "name": "Maya Lindqvist",
        "target_role": "Senior Frontend & Web Platform Architect",
        "category": "frontend_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 97.0,
            "expert_scores": {"reviewer_1": 95, "reviewer_2": 96, "reviewer_3": 95}
        },
        "cv_text": """# Maya Lindqvist - Senior Frontend Architect
5+ years experience building high-performance web applications with React, Next.js, and TypeScript.
## Experience
Senior Frontend Engineer at Omnichannel Web (2020 - Present | 4.5 years)
- Architected enterprise Next.js App Router migration, improving Core Web Vitals (LCP reduced from 3.8s to 0.9s).
- Implemented state architecture with Zustand and TanStack Query with optimistic UI mutations and offline synchronization.
- Authored design system component library with 100% WCAG 2.1 AA accessibility compliance.
""",
        "interview_notes": """# Interview: Maya Lindqvist
Maya gave exceptionally detailed explanations of React Server Components, hydration boundaries, streaming SSR, and virtualized windowing for 50k item grids.
""",
        "technical_assessment": """# Technical Assessment: Maya Lindqvist
Score: 98 / 100
Flawless TypeScript component implementation with sub-millisecond render benchmarks and comprehensive Vitest test coverage.
"""
    },
    {
        "candidate_id": "case_23_fe_strong_02",
        "name": "Derek O'Connor",
        "target_role": "Senior Frontend & Web Platform Architect",
        "category": "frontend_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 95.0,
            "expert_scores": {"reviewer_1": 92, "reviewer_2": 91, "reviewer_3": 93}
        },
        "cv_text": """# Derek O'Connor, Senior Fullstack Engineer
4 years experience building distributed web apps with TypeScript, React, Tailwind CSS, and Node.js microservices.
Experience at FinApp Platforms (2021 - Present | 3.5 years).
""",
        "interview_notes": """# Interview: Derek O'Connor
Derek articulated deep understanding of bundle splitting, tree shaking in Vite, and Web Workers for heavy client-side computations.
""",
        "technical_assessment": """# Technical Assessment: Derek O'Connor
Score: 93 / 100
Clean component structure, responsive mobile-first layouts, and resilient error boundary integration.
"""
    },
    {
        "candidate_id": "case_24_fe_med_01",
        "name": "Kavita Rao",
        "target_role": "Senior Frontend & Web Platform Architect",
        "category": "frontend_med",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 92.0,
            "expert_scores": {"reviewer_1": 81, "reviewer_2": 82, "reviewer_3": 80}
        },
        "cv_text": """# Kavita Rao - Frontend Developer
3 years commercial experience building React single-page applications with Redux Toolkit and CSS Modules.
Developer at RetailTech (2022 - Present | 2.5 years).
""",
        "interview_notes": """# Interview: Kavita Rao
Solid React fundamentals and responsive CSS styling, but unfamiliar with Next.js App Router server components.
""",
        "technical_assessment": """# Technical Assessment: Kavita Rao
Score: 82 / 100
Passed all UI widget tests and form validation suites.
"""
    },
    {
        "candidate_id": "case_25_fe_med_02",
        "name": "Julian Becker",
        "target_role": "Senior Frontend & Web Platform Architect",
        "category": "frontend_med",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 89.0,
            "expert_scores": {"reviewer_1": 77, "reviewer_2": 79, "reviewer_3": 78}
        },
        "cv_text": """# Julian Becker - Web Developer
2.5 years building Vue.js and React applications for digital marketing agency.
""",
        "interview_notes": """# Interview: Julian Becker
Good eye for visual aesthetics and CSS animations, but limited experience with automated end-to-end testing (Playwright/Cypress).
""",
        "technical_assessment": """# Technical Assessment: Julian Becker
Score: 78 / 100
Solid UI implementation, minor gaps in accessibility ARIA tags.
"""
    },
    {
        "candidate_id": "case_26_fe_weak_01",
        "name": "Brian Connolly",
        "target_role": "Senior Frontend & Web Platform Architect",
        "category": "frontend_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 90.0,
            "expert_scores": {"reviewer_1": 42, "reviewer_2": 45, "reviewer_3": 40}
        },
        "cv_text": """# Brian Connolly - Junior HTML Designer
6 months experience maintaining WordPress blogs and modifying basic CSS colors.
""",
        "interview_notes": """# Interview: Brian Connolly
Candidate has never written TypeScript, does not know how React state works, and cannot explain DOM event delegation.
""",
        "technical_assessment": """# Technical Assessment: Brian Connolly
Score: 32 / 100
Failed React component interactive coding exercise.
"""
    },
    {
        "candidate_id": "case_27_fe_contradiction_01",
        "name": "Trevor Vance",
        "target_role": "Senior Frontend & Web Platform Architect",
        "category": "frontend_contradiction",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "tenure_conflict",
            "expected_consistency": 25.0,
            "expert_scores": {"reviewer_1": 50, "reviewer_2": 48, "reviewer_3": 52}
        },
        "cv_text": """# Trevor Vance - Principal Frontend Architect
VP of Web Architecture at CloudPortal (2017 - Present | 7.5 years)
- Led 45 frontend engineers rebuilding customer portal in React.
""",
        "interview_notes": """# Interview: Trevor Vance
Interviewer: "How long were you with CloudPortal?"
Trevor: "I started with CloudPortal 10 months ago when they hired contractors."
""",
        "technical_assessment": """# Technical Assessment: Trevor Vance
Score: 75 / 100
Candidate knows basic React, but interview reveals major tenure inflation.
"""
    },

    # =========================================================================
    # ROBOTICS & AUTONOMOUS PERCEPTION (5 Cases)
    # =========================================================================
    {
        "candidate_id": "case_28_robotics_strong_01",
        "name": "Dr. Kenji Takahashi",
        "target_role": "Autonomous Systems Perception Engineer",
        "category": "robotics_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 97.0,
            "expert_scores": {"reviewer_1": 96, "reviewer_2": 97, "reviewer_3": 95}
        },
        "cv_text": """# Dr. Kenji Takahashi - Robotics Perception Scientist
PhD in Robotics (Tokyo Institute of Technology, 2020). 4+ years production robotics experience.
## Experience
Senior Perception Engineer at DroneNav Autonomous (2020 - Present | 4.2 years)
- Engineered multi-sensor LiDAR-camera calibration and visual-inertial odometry (VIO) on physical hexacopter platforms.
- Deployed real-time obstacle avoidance algorithms running at 60 FPS on NVIDIA Jetson Orin with ROS2.
- 4 papers published in IEEE ICRA and IROS on map-free autonomous navigation.
""",
        "interview_notes": """# Interview: Dr. Kenji Takahashi
Kenji demonstrated flawless mastery of Kalman Filtering (EKF/UKF), graph-based SLAM factor graphs (GTSAM), and real-time Sim-to-Real sensor calibration.
""",
        "technical_assessment": """# Technical Assessment: Dr. Kenji Takahashi
Score: 97 / 100
Flawless point cloud registration implementation and robust ROS2 node latency profiling.
"""
    },
    {
        "candidate_id": "case_29_robotics_strong_02",
        "name": "Ingrid Bergman",
        "target_role": "Autonomous Systems Perception Engineer",
        "category": "robotics_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 94.0,
            "expert_scores": {"reviewer_1": 90, "reviewer_2": 92, "reviewer_3": 91}
        },
        "cv_text": """# Ingrid Bergman, Autonomous Systems Engineer
MS in Robotics (KTH Royal Institute, 2021). 3.5 years experience developing SLAM and point cloud perception for ground AGVs.
Experience at AutoLogistics (2021 - Present | 3.5 years).
""",
        "interview_notes": """# Interview: Ingrid Bergman
Deep knowledge of LiDAR point cloud clustering, bounding box estimation with PointNet++, and C++ ROS2 node development.
""",
        "technical_assessment": """# Technical Assessment: Ingrid Bergman
Score: 92 / 100
Passed sensor fusion benchmark and real-time obstacle tracking simulations.
"""
    },
    {
        "candidate_id": "case_30_robotics_med_01",
        "name": "Carlos Gomez",
        "target_role": "Autonomous Systems Perception Engineer",
        "category": "robotics_med",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 91.0,
            "expert_scores": {"reviewer_1": 79, "reviewer_2": 81, "reviewer_3": 80}
        },
        "cv_text": """# Carlos Gomez - Robotics Software Engineer
2.5 years experience writing Python scripts and OpenCV computer vision for warehouse robot prototypes.
""",
        "interview_notes": """# Interview: Carlos Gomez
Good understanding of basic camera geometry and OpenCV, but limited experience with 3D LiDAR point clouds or embedded C++ runtimes.
""",
        "technical_assessment": """# Technical Assessment: Carlos Gomez
Score: 80 / 100
Completed 2D camera calibration and contour detection tasks cleanly.
"""
    },
    {
        "candidate_id": "case_31_robotics_weak_01",
        "name": "Darren Fletcher",
        "target_role": "Autonomous Systems Perception Engineer",
        "category": "robotics_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 92.0,
            "expert_scores": {"reviewer_1": 44, "reviewer_2": 42, "reviewer_3": 46}
        },
        "cv_text": """# Darren Fletcher - Drone Hobbyist
Assembled hobby FPV racing drones from pre-built kits. Basic hobbyist tinkering with Arduino.
""",
        "interview_notes": """# Interview: Darren Fletcher
Candidate has no experience with SLAM, cannot formulate state estimation equations, and has no C++ or ROS experience.
""",
        "technical_assessment": """# Technical Assessment: Darren Fletcher
Score: 30 / 100
Failed spatial transformation and coordinate frame conversion exercises.
"""
    },
    {
        "candidate_id": "case_32_robotics_contradiction_01",
        "name": "Simon Kroll",
        "target_role": "Autonomous Systems Perception Engineer",
        "category": "robotics_contradiction",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "tenure_conflict",
            "expected_consistency": 25.0,
            "expert_scores": {"reviewer_1": 52, "reviewer_2": 50, "reviewer_3": 49}
        },
        "cv_text": """# Simon Kroll - Chief Robotics Architect
Head of Perception at SkyRobotics (2018 - Present | 6.5 years)
- Authored flight control and LiDAR perception stack across entire autonomous drone fleet.
""",
        "interview_notes": """# Interview: Simon Kroll
Interviewer: "How long have you been with SkyRobotics?"
Simon: "I started with SkyRobotics 11 months ago as an external software tester."
""",
        "technical_assessment": """# Technical Assessment: Simon Kroll
Score: 72 / 100
Candidate possesses elementary robotics knowledge, but tenure claims are heavily contradicted.
"""
    },

    # =========================================================================
    # DATA PLATFORM & LAKEHOUSE ENGINEERING (5 Cases)
    # =========================================================================
    {
        "candidate_id": "case_33_data_strong_01",
        "name": "Amina Diop",
        "target_role": "Principal Data Platform Architect",
        "category": "data_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 96.0,
            "expert_scores": {"reviewer_1": 95, "reviewer_2": 94, "reviewer_3": 96}
        },
        "cv_text": """# Amina Diop - Principal Data Platform Engineer
5+ years experience building petabyte-scale lakehouses with Apache Spark, Delta Lake, Snowflake, and dbt.
## Experience
Lead Data Platform Architect at FinData Mesh (2020 - Present | 4.5 years)
- Built streaming data lakehouse processing 25TB of daily financial transactions with sub-minute ingestion latency.
- Optimized distributed Spark SQL queries reducing daily analytics compute costs by $340k annually.
- Spearheaded enterprise data governance, lineage tracking, and schema contract enforcement with OpenLineage.
""",
        "interview_notes": """# Interview: Amina Diop
Amina showed comprehensive expertise in Spark shuffle partitions, Delta Lake compaction/vacuuming, Iceberg metadata catalogs, and data contract testing.
""",
        "technical_assessment": """# Technical Assessment: Amina Diop
Score: 97 / 100
Flawless execution on distributed ETL pipeline construction, partition pruning, and complex window functions.
"""
    },
    {
        "candidate_id": "case_34_data_strong_02",
        "name": "Liam Murphy",
        "target_role": "Principal Data Platform Architect",
        "category": "data_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 94.0,
            "expert_scores": {"reviewer_1": 91, "reviewer_2": 92, "reviewer_3": 90}
        },
        "cv_text": """# Liam Murphy, Senior Data Engineer
4 years experience building automated batch pipelines with PySpark, Airflow, and BigQuery.
Senior Data Engineer at StreamMetrics (2021 - Present | 3.8 years).
""",
        "interview_notes": """# Interview: Liam Murphy
Deep proficiency in Airflow DAG optimization, backfilling strategies, and columnar database storage schemas.
""",
        "technical_assessment": """# Technical Assessment: Liam Murphy
Score: 91 / 100
Passed lakehouse data modeling benchmark and SQL performance tuning challenges.
"""
    },
    {
        "candidate_id": "case_35_data_med_01",
        "name": "Yuki Tanaka",
        "target_role": "Principal Data Platform Architect",
        "category": "data_med",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 90.0,
            "expert_scores": {"reviewer_1": 80, "reviewer_2": 82, "reviewer_3": 81}
        },
        "cv_text": """# Yuki Tanaka - Data Analyst & SQL Developer
3 years experience writing SQL queries, building Tableau dashboards, and maintaining small Airflow ETL tasks.
""",
        "interview_notes": """# Interview: Yuki Tanaka
Excellent SQL modeling knowledge, but limited experience with distributed Spark clusters or streaming architectures.
""",
        "technical_assessment": """# Technical Assessment: Yuki Tanaka
Score: 82 / 100
Passed all relational SQL challenges with optimal execution plans.
"""
    },
    {
        "candidate_id": "case_36_data_weak_01",
        "name": "Gary Walsh",
        "target_role": "Principal Data Platform Architect",
        "category": "data_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 92.0,
            "expert_scores": {"reviewer_1": 45, "reviewer_2": 43, "reviewer_3": 44}
        },
        "cv_text": """# Gary Walsh - Excel Specialist
1 year experience maintaining financial Excel spreadsheets and running VLOOKUP functions.
""",
        "interview_notes": """# Interview: Gary Walsh
Candidate does not know SQL, has never used a database or terminal, and has no programming experience.
""",
        "technical_assessment": """# Technical Assessment: Gary Walsh
Score: 28 / 100
Failed data engineering and query optimization test suites.
"""
    },
    {
        "candidate_id": "case_37_data_contradiction_01",
        "name": "Samantha Cross",
        "target_role": "Principal Data Platform Architect",
        "category": "data_contradiction",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "tenure_conflict",
            "expected_consistency": 25.0,
            "expert_scores": {"reviewer_1": 51, "reviewer_2": 49, "reviewer_3": 50}
        },
        "cv_text": """# Samantha Cross - Chief Data Architect
VP of Data Engineering at LakehouseCorp (2017 - Present | 7.5 years)
- Built entire enterprise data platform from scratch.
""",
        "interview_notes": """# Interview: Samantha Cross
Interviewer: "How long were you with LakehouseCorp?"
Samantha: "I started with LakehouseCorp 12 months ago as a contractor."
""",
        "technical_assessment": """# Technical Assessment: Samantha Cross
Score: 74 / 100
Candidate demonstrated basic SQL capability, but tenure claims are severely contradicted.
"""
    },

    # =========================================================================
    # DEVOPS, SRE & CLOUD SECURITY (5 Cases)
    # =========================================================================
    {
        "candidate_id": "case_38_sre_strong_01",
        "name": "Henrik Lindholm",
        "target_role": "Lead Site Reliability & Cloud Infrastructure Engineer",
        "category": "sre_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 97.0,
            "expert_scores": {"reviewer_1": 95, "reviewer_2": 96, "reviewer_3": 95}
        },
        "cv_text": """# Henrik Lindholm - Lead SRE Engineer
5+ years experience managing multi-region Kubernetes clusters, Terraform infrastructure, and 99.99% SLAs.
## Experience
Lead Site Reliability Engineer at CloudGrid SRE (2020 - Present | 4.5 years)
- Architected multi-region Kubernetes deployment across AWS and GCP spanning 450 nodes with automated failover.
- Authored eBPF-based telemetry monitoring using Cilium and OpenTelemetry, slashing MTTR during incidents by 65%.
- Maintained production on-call rotation with zero SLA breaches over 24 consecutive months.
""",
        "interview_notes": """# Interview: Henrik Lindholm
Henrik gave masterclass explanations of Linux kernel cgroups v2, network namespaces, BGP routing, and automated chaos engineering with Chaos Mesh.
""",
        "technical_assessment": """# Technical Assessment: Henrik Lindholm
Score: 98 / 100
Completed complex Kubernetes networking debugging and automated Terraform module generation flawlessly.
"""
    },
    {
        "candidate_id": "case_39_sre_strong_02",
        "name": "Zoe Kravitz-Vance",
        "target_role": "Lead Site Reliability & Cloud Infrastructure Engineer",
        "category": "sre_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 94.0,
            "expert_scores": {"reviewer_1": 92, "reviewer_2": 93, "reviewer_3": 91}
        },
        "cv_text": """# Zoe Kravitz-Vance, Senior Cloud DevOps Engineer
4 years experience building automated CI/CD pipelines and managing AWS infrastructure via Terraform and ArgoCD.
Senior DevOps Engineer at InfraMesh (2021 - Present | 3.6 years).
""",
        "interview_notes": """# Interview: Zoe Kravitz-Vance
Strong grasp of GitOps principles, progressive delivery with Argo Rollouts, and IAM least-privilege security controls.
""",
        "technical_assessment": """# Technical Assessment: Zoe Kravitz-Vance
Score: 93 / 100
High marks on infrastructure-as-code linting, container security scanning, and automated deployment pipelines.
"""
    },
    {
        "candidate_id": "case_40_sre_med_01",
        "name": "Faisal Al-Mansoor",
        "target_role": "Lead Site Reliability & Cloud Infrastructure Engineer",
        "category": "sre_med",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 91.0,
            "expert_scores": {"reviewer_1": 80, "reviewer_2": 82, "reviewer_3": 81}
        },
        "cv_text": """# Faisal Al-Mansoor - Systems Administrator
3 years experience managing Linux servers, bash scripting, and basic Docker containers.
""",
        "interview_notes": """# Interview: Faisal Al-Mansoor
Solid Linux administration and troubleshooting skills, but limited experience with distributed Kubernetes orchestration.
""",
        "technical_assessment": """# Technical Assessment: Faisal Al-Mansoor
Score: 82 / 100
Clean Linux server troubleshooting and shell scripting.
"""
    },
    {
        "candidate_id": "case_41_sre_weak_01",
        "name": "Timothy O'Neal",
        "target_role": "Lead Site Reliability & Cloud Infrastructure Engineer",
        "category": "sre_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 92.0,
            "expert_scores": {"reviewer_1": 42, "reviewer_2": 44, "reviewer_3": 40}
        },
        "cv_text": """# Timothy O'Neal - IT Helpdesk Support
6 months experience setting up Windows office printers and resetting employee passwords.
""",
        "interview_notes": """# Interview: Timothy O'Neal
Candidate has never used Docker, Linux terminal, or cloud providers.
""",
        "technical_assessment": """# Technical Assessment: Timothy O'Neal
Score: 30 / 100
Failed cloud infrastructure and networking challenges.
"""
    },
    {
        "candidate_id": "case_42_sre_contradiction_01",
        "name": "Lucas Sterling",
        "target_role": "Lead Site Reliability & Cloud Infrastructure Engineer",
        "category": "sre_contradiction",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "tenure_conflict",
            "expected_consistency": 25.0,
            "expert_scores": {"reviewer_1": 50, "reviewer_2": 48, "reviewer_3": 51}
        },
        "cv_text": """# Lucas Sterling - VP of Cloud Operations
Head of Cloud Infrastructure at MultiCloud Ltd (2017 - Present | 7.5 years)
- Architected enterprise cloud infrastructure and directed global SRE organization.
""",
        "interview_notes": """# Interview: Lucas Sterling
Interviewer: "How long were you with MultiCloud Ltd?"
Lucas: "I joined MultiCloud Ltd 10 months ago on a short-term contract."
""",
        "technical_assessment": """# Technical Assessment: Lucas Sterling
Score: 72 / 100
Candidate knows basic Docker and cloud commands, but tenure claims are heavily contradicted.
"""
    },

    # =========================================================================
    # FORWARD DEPLOYED & SOLUTIONS ENGINEERING (2 Cases)
    # =========================================================================
    {
        "candidate_id": "case_43_fde_strong_01",
        "name": "Maya Chen",
        "target_role": "Forward Deployed Engineer",
        "category": "fde_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 95.0,
            "expert_scores": {"reviewer_1": 93, "reviewer_2": 95, "reviewer_3": 94}
        },
        "cv_text": """# Maya Chen - Lead Forward Deployed Engineer
5+ years experience deploying mission-critical analytics platforms on-prem and in customer cloud environments.
## Experience
Lead Solutions & Forward Deployed Engineer at Palantir-Style Platforms (2020 - Present | 4.2 years)
- Embedded on-site with Fortune 50 clients to design and deploy real-time ETL pipelines and custom API connectors under tight delivery deadlines.
- Triaged live customer production outages, debugging distributed log streams, Kubernetes ingress bottlenecks, and database replication lag.
- Rapidly prototyped specialized API adapters and Python microservices under high-pressure customer SLAs, driving 99.8% customer satisfaction.
- Partnered with enterprise client executives and engineering leads to define technical RFCs and overcome ambiguous legacy architecture constraints.
""",
        "interview_notes": """# Technical Interview: Maya Chen
Interviewer: Alex Vance
Alex: "How do you approach deploying into an ambiguous, poorly-documented customer environment under high pressure?"
Maya: "I first map boundary APIs and network topology with tracing probes, isolate dependency failure modes, and build containerized mock harnesses so we can iterate rapidly without breaking live client systems."
""",
        "technical_assessment": """# Technical Assessment: Maya Chen
Score: 94 / 100 | Result: Exceptional
Exemplary execution of live customer troubleshooting scenario, rapid Python connector prototyping, and robust ambiguity tolerance.
"""
    },
    {
        "candidate_id": "case_44_fde_weak_01",
        "name": "Julian Ross",
        "target_role": "Forward Deployed Engineer",
        "category": "fde_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 88.0,
            "expert_scores": {"reviewer_1": 42, "reviewer_2": 45, "reviewer_3": 40}
        },
        "cv_text": """# Julian Ross - Pure Theoretical Computer Science Researcher
Pure academic background focusing on theoretical complexity classes (P vs NP, circuit lower bounds).
## Experience
Postdoctoral Researcher at Institute for Advanced Mathematics (2021 - Present | 3.5 years)
- Proved structural theorems on Boolean circuit complexity and algebraic graph properties.
- Authored theoretical papers in STOC and FOCS conferences.
- No commercial software development experience; zero customer interaction or on-site deployment experience.
""",
        "interview_notes": """# Technical Interview: Julian Ross
Interviewer: Alex Vance
Alex: "Have you ever deployed software to an enterprise customer environment or managed a live incident?"
Julian: "No, my work is exclusively theoretical pencil-and-paper proofs. I prefer not to engage with customers or work with time-pressured production systems."
""",
        "technical_assessment": """# Technical Assessment: Julian Ross
Score: 45 / 100 | Result: Not Recommended for FDE
Theoretical mathematics is brilliant, but candidate has zero practical customer deployment skills, no rapid prototyping capability, and low tolerance for operational ambiguity.
"""
    },

    # =========================================================================
    # NOVEL ROLE ADVERSARIAL TRACK (1 Case - No JD Provided)
    # =========================================================================
    {
        "candidate_id": "case_45_novel_adversarial_01",
        "name": "Dr. Zephyr Orion",
        "target_role": "Chief Spacecraft Orbital Trajectory Optimizer",
        "category": "novel_role_adversarial",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 92.0,
            "expert_scores": {"reviewer_1": 90, "reviewer_2": 91, "reviewer_3": 92}
        },
        "cv_text": """# Dr. Zephyr Orion - Lead Astrodynamics & Spacecraft Trajectory Architect
PhD in Aerospace Engineering & Celestial Mechanics (Caltech, 2019). 6+ years designing orbital trajectory solutions.
## Experience
Staff Astrodynamics Specialist at Orbital Flight Dynamics (2019 - Present | 5.5 years)
- Developed high-precision orbital trajectory optimization algorithms using collocation and multi-body gravitational perturbation models.
- Architected interplanetary low-thrust trajectory planners calculating optimal delta-v burns across lunar and Martian transit corridors.
- Validated numerical orbital propagation simulations against real flight telemetry data from deep space missions.
""",
        "interview_notes": """# Technical Interview: Dr. Zephyr Orion
Interviewer: Dr. Evelyn Reed
Evelyn: "How do you handle gravity-assist flyby optimization across multi-body gravitational fields?"
Zephyr: "We formulate the flyby as a patched-conic initial guess refined through nonlinear programming (NLP) with Runge-Kutta 8th order ephemeris integration."
""",
        "technical_assessment": """# Technical Assessment: Dr. Zephyr Orion
Score: 92 / 100 | Result: Exceptional
Flawless demonstration of orbital mechanics numerical modeling, trajectory optimization, and astrodynamics problem solving.
"""
    }
]


# Compute expert_composite_score for domain cases
for _c in ADDITIONAL_DOMAIN_CASES:
    _gt = _c.get("ground_truth", {})
    if "expert_scores" in _gt and "expert_composite_score" not in _gt:
        _scores = list(_gt["expert_scores"].values())
        _gt["expert_composite_score"] = round(sum(_scores) / len(_scores), 2)

# Full 50-Case Comprehensive Benchmark Suite
# 15 Core + 8 Adversarial + 27 Domain Archetypes = 50 Cases
EXPANDED_50_CASES: List[Dict[str, Any]] = (
    CORE_15_CASES +
    ADVERSARIAL_CASES +
    ADDITIONAL_DOMAIN_CASES
)


def get_expanded_cases() -> List[Dict[str, Any]]:
    """Returns the full 50-case benchmark dataset."""
    return EXPANDED_50_CASES


def export_expanded_cases_to_disk(target_dir: str = "eval_cases"):
    """Exports all 50 cases to JSON files in target_dir."""
    import json
    os.makedirs(target_dir, exist_ok=True)
    for c in EXPANDED_50_CASES:
        fpath = os.path.join(target_dir, f"{c['candidate_id']}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2)
    print(f"Exported {len(EXPANDED_50_CASES)} cases to {target_dir}")


if __name__ == "__main__":
    print(f"Loaded {len(EXPANDED_50_CASES)} comprehensive benchmark cases:")
    print(f"  - Core Distributed Systems: {len(CORE_15_CASES)}")
    print(f"  - Adversarial & Injections: {len(ADVERSARIAL_CASES)}")
    print(f"  - Domain Taxonomies (AI, FE, Robotics, Data, SRE): {len(ADDITIONAL_DOMAIN_CASES)}")
    print(f"Total: {len(EXPANDED_50_CASES)} cases")
    export_expanded_cases_to_disk()
