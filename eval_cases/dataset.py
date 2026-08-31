"""
Synthetic Candidate Dataset for HireTrace (15 Cases).
Enriched with authentic production engineering project patterns:
  - Distributed Ray Tracing & Concurrency (OpenGL/C++/Python)
  - Neural Cryptanalysis & Deep Distinguishers (ResNet, BiLSTM)
  - High-Throughput Event Streaming & Distributed Telemetry (Kafka, RabbitMQ, Redis)
  - Real conversational multi-turn interview transcripts
  - Structured technical assessment reports with test execution matrices
  - Project architecture specs and RFCs with team rosters

Fixed Role: Senior Python & Distributed Systems Engineer
Company: CloudMesh Infrastructure
"""

import json
import os
from typing import Dict, List, Any

SHARED_JD = """# Senior Python & Distributed Systems Engineer
Company: CloudMesh Infrastructure
Department: Core Infrastructure & Telemetry
Location: Remote (Global)
Employment Type: Full-Time

### About the Role
CloudMesh Infrastructure operates a distributed telemetry and workflow orchestration mesh processing upwards of 45 million real-time events per hour across multi-region clusters. We are seeking a Senior Python & Distributed Systems Engineer to take ownership of our next-generation ingestion pipelines, distributed event broker integrations, and asynchronous state synchronization engines.

### Key Responsibilities
1. Design, build, and maintain low-latency asynchronous microservices using modern Python (3.10+, AsyncIO) capable of sustaining 25k+ requests/sec under sub-80ms p99 latency SLAs.
2. Architect scalable event-driven messaging topologies using Apache Kafka, RabbitMQ, and Redis Streams, managing consumer groups, partition balancing, and idempotent event processing.
3. Manage distributed state consistency across partitioned PostgreSQL clusters, ClickHouse analytics tables, and distributed Redis caches with robust failure recovery.
4. Author comprehensive architectural RFCs, drive code quality standards, and provide senior technical mentorship to mid-level and junior backend engineers.
5. Participate in production on-call rotations, incident post-mortems, and capacity planning for mission-critical services.

### Core Requirements
- REQ-01: Advanced Modern Python & AsyncIO: Deep mastery of Python 3.10+ internal concurrency, uvloop/asyncio paradigms, memory profiling, and non-blocking I/O.
- REQ-02: Distributed Systems & Event Streaming: 3+ years hands-on production experience deploying and scaling Apache Kafka or RabbitMQ clusters, consumer rebalance handling, and event schemas (Avro/Protobuf).
- REQ-03: Microservices & Data Layer Architecture: Proven experience designing resilient distributed microservices, database sharding/partitioning (PostgreSQL), and caching strategies.
- REQ-04: Technical Leadership & System Design: Track record of authoring production RFCs, leading complex cross-team technical migrations, and conducting rigorous code reviews.
- REQ-05: Production Engineering & Operational Tenure: 3+ years of commercial production experience managing live customer-facing systems, SLO/SLA management, and telemetry monitoring (Prometheus/Grafana).
"""

CASES: List[Dict[str, Any]] = [
    # =========================================================================
    # 8 NORMAL CASES (Varied strength, perfectly consistent across sources)
    # =========================================================================
    {
        "candidate_id": "case_01_strong_01",
        "name": "Sarah Chen",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 98.0,
            "expert_scores": {"reviewer_1": 95, "reviewer_2": 94, "reviewer_3": 96}
        },
        "cv_text": """# Sarah Chen, Senior Backend Systems Engineer
Email: sarah.chen@devmail.org | GitHub: github.com/schen-dist (4 repositories, 140+ stars, 28 merged PRs)
LinkedIn: linkedin.com/in/sarah-chen-dist-systems | Location: Seattle, WA

## Professional Summary
Senior Distributed Systems Engineer with 5+ years of production experience architecting event-driven microservices in Python, AsyncIO, and Apache Kafka. Proven track record scaling real-time ingestion pipelines from 2M to 35M daily events while maintaining 99.99% availability. Active contributor to open-source asyncio ecosystems.

## Technical Skills
- Languages: Python 3.11/3.12 (Expert, AsyncIO, uvloop, Cython), Go, SQL, C++
- Distributed Systems: Apache Kafka (Kafka Streams, Schema Registry, Confluent Python), RabbitMQ, Redis Cluster
- Databases & Storage: PostgreSQL (Declarative Partitioning, TimescaleDB), Redis, ClickHouse
- Infrastructure: Docker, Kubernetes, Helm, Terraform, Prometheus, Grafana, OpenTelemetry

## Work Experience
Senior Infrastructure Engineer | ScaleMatrix Telemetry (Oct 2021 - Present | 4+ years)
- Architected a distributed telemetry ingestion pipeline in Python 3.11 (AsyncIO, FastAPI, aiokafka) processing 35M events/day with p99 response times < 45ms.
- Engineered dynamic Kafka consumer group scaling using Kubernetes KEDA, reducing message lag during peak traffic spikes by 82%.
- Designed database partitioning strategy on a 6TB PostgreSQL cluster, reducing query times for 30-day time-series aggregations from 8.2s to 310ms.
- Authored RFC-108 ("Dynamic Schema Validation for Kafka Topics") and mentored 4 mid-level engineers through production release.

Backend Software Engineer | DataPulse Networks (Jun 2019 - Sep 2021 | 2.3 years)
- Developed asynchronous microservices for real-time network anomaly detection using Python, Redis Streams, and PostgreSQL.
- Implemented Celery-based asynchronous background processing pipelines handling 500k daily analytical jobs.

## Notable Open Source & Projects
- `async-kafka-batcher` (github.com/schen-dist/async-kafka-batcher): Python library for high-throughput micro-batching over aiokafka. 92 stars, 18 contributors.
- `pg-partition-watch` (github.com/schen-dist/pg-partition-watch): Automated maintenance utility for PostgreSQL time-based partition creation and detaching.
""",
        "interview_notes": """# Technical Interview Transcript: Sarah Chen
Interviewer: Alex Mercer (Principal Architect, CloudMesh)
Date: 2025-02-14 | Duration: 60 minutes

Alex: "Welcome Sarah. Can you walk me through the architecture of the telemetry ingestion service at ScaleMatrix?"
Sarah: "Certainly. When I joined in late 2021, the ingestion tier was built on synchronous Flask workers backed by RabbitMQ, which suffered CPU saturation during burst traffic. I designed our v2 pipeline using Python 3.11 with AsyncIO and uvloop. We ingest events over HTTP/gRPC via FastAPI, validate them against Avro schemas in-memory, and produce directly into a 12-partition Kafka cluster using aiokafka with snappy compression."

Alex: "How do you avoid blocking the asyncio event loop when dealing with disk writes or heavy cryptographic operations?"
Sarah: "That was actually one of our key performance hurdles. We strictly run CPU-bound schema deserialization in a `ProcessPoolExecutor` with zero-copy shared memory buffers, while all network I/O remains non-blocking inside the event loop. We also set up custom Prometheus alerts monitoring event loop lag (`loop.slow_callback_duration`)."

Alex: "Tell me about your role on RFC-108."
Sarah: "I was the primary author and technical lead. We had cross-team issues where downstream consumers broke due to unannounced payload schema changes. I drafted RFC-108 proposing a centralized schema registry with backward-transitive compatibility rules. I ran design reviews with 3 engineering teams, incorporated feedback, and oversaw implementation over two sprints."

Alex: "What is your experience participating in on-call rotations?"
Sarah: "I have been on an active 24/7 on-call tier (1 week every 5 weeks) at ScaleMatrix since November 2021. I've led incident resolution for 14 major production outages, including network split-brain recoveries and Kafka broker failovers."
""",
        "technical_assessment": """# Technical Assessment Report: Sarah Chen
Assessment Challenge: "Distributed High-Throughput Event Ingestion Engine"
Score: 96 / 100 | Grade: Exceptional (Tier: Legend)

## Test Execution Matrix
- Concurrency & Load Stress Test (50,000 req/sec over 120s): PASSED (0 dropped packets, p99 = 38ms)
- Deadlock & Race Condition Suite (100 parallel async workers): PASSED (100% thread/task safety)
- Distributed Idempotency Validation (Duplicate UUID injections): PASSED (Zero duplicate ledger writes)
- Memory Profiling (Tracer leak inspection): PASSED (Stable at 84MB heap over 1-hour soak test)

## Evaluator Notes
"Immaculate codebase. Clean separation of concerns with asynchronous queue decoupling, typed Pydantic v2 schemas, proper signal trapping for graceful container termination, and comprehensive unit/integration test suite (94% coverage)."
""",
        "project_rfc": """# Project RFC-108: Centralized Event Ingestion Schema Governance
Company: ScaleMatrix Telemetry
Lead Author: Sarah Chen (Senior Infrastructure Engineer)
Reviewers: David Miller (VP Eng), Alex Rivera (Data Platform Lead)
Status: Approved & Deployed to Production (March 2023)

## Abstract
This document specifies the architecture for real-time schema enforcement across all Kafka producer microservices. 

## Implementation Team
- Sarah Chen: Architecture Lead & Core AsyncIO Producer Implementation
- Marcus Bell: Schema Registry Deployment & CI/CD Validation
- Elena Gomez: Downstream Analytics Consumer Migration
"""
    },

    {
        "candidate_id": "case_02_strong_02",
        "name": "Marcus Vance",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_strong",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 96.0,
            "expert_scores": {"reviewer_1": 91, "reviewer_2": 89, "reviewer_3": 92}
        },
        "cv_text": """# Marcus Vance, Distributed Systems Engineer
Email: m.vance@coredev.io | GitHub: github.com/marcus-vance (5 repos, 110 stars)
LinkedIn: linkedin.com/in/marcus-vance-systems | Location: Austin, TX

## Summary
Distributed Systems Software Engineer with 4.5 years commercial experience specializing in asynchronous Python architectures, high-performance messaging (Kafka/RabbitMQ), and database scalability.

## Technical Skills
- Python 3.10/3.11, Cython, AsyncIO, Aiohttp, FastAPI, Celery
- Apache Kafka, RabbitMQ, Redis Cluster, Distributed Locking (Redlock)
- PostgreSQL (B-Tree, BRIN indexing, partitioning), Redis, Docker, Kubernetes

## Experience
Senior Backend Engineer | CloudFlux Solutions (Jan 2022 - Present | 3.5 years)
- Built distributed asynchronous order-processing orchestrator in Python/AsyncIO processing 12,000 transactions/sec.
- Deployed multi-broker Kafka messaging architecture with zero message-loss guarantees (acks=all, min.insync.replicas=2).
- Led operational migration of 14 monolithic endpoints into event-driven microservices.

Software Engineer | Apex FinTech Systems (Jul 2020 - Dec 2021 | 1.5 years)
- Implemented RabbitMQ messaging queues and background tasks for high-frequency financial statement reconciliation.
- Maintained production on-call rotation with 99.98% service uptime compliance.
""",
        "interview_notes": """# Technical Interview: Marcus Vance
Interviewer: Rachel Torres (Staff Engineer)
Date: 2025-02-18 | Duration: 55 minutes

Rachel: "Marcus, how do you handle Kafka partition rebalances in Python without creating message duplication?"
Marcus: "In our CloudFlux pipelines, we use cooperative sticky rebalancing with manual offset commit loops. We ensure that in-flight asynchronous tasks flush their local buffers and commit offsets before relinquishing partition ownership during consumer group rebalance events."
Rachel: "Tell me about your on-call experience."
Marcus: "I have been in the on-call pager rotation at CloudFlux for over 3 years. We take secondary on-call shifts every 4 weeks. I've resolved cluster split-brains and PostgreSQL connection pool exhaustions."
""",
        "technical_assessment": """# Technical Assessment: Marcus Vance
Score: 92 / 100 | Grade: Superior (Tier: Legend)
- Concurrency & Throughput Test: PASSED (p99 = 48ms under 30k req/s)
- Error Handling & Recovery: PASSED (Gracefully handled broker dropouts)
- Code Architecture: Solid AsyncIO design with typing and clean modularity.
""",
        "project_rfc": """# Project RFC-054: Distributed Order Processing Topology
Company: CloudFlux Solutions
Author: Marcus Vance (Senior Backend Engineer)
Status: Implemented (August 2022)
Team: Marcus Vance (Lead), Kevin Cho (DevOps), Maya Patel (QA)
"""
    },

    {
        "candidate_id": "case_03_med_01",
        "name": "Elena Rostova",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_medium",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 94.0,
            "expert_scores": {"reviewer_1": 84, "reviewer_2": 82, "reviewer_3": 85}
        },
        "cv_text": """# Elena Rostova, Backend Software Engineer
Email: elena.rostova@techmail.io | GitHub: github.com/elena-rostova (3 repos, 45 stars)
Location: Boston, MA

## Experience
Backend Engineer | Omnilink Media (Feb 2022 - Present | 3.5 years)
- Developed asynchronous Python backend services using FastAPI and PostgreSQL.
- Implemented RabbitMQ messaging workers handling video rendering job dispatches.
- Configured Redis caching layers reducing database load by 35%.

Junior Backend Engineer | CoreStack Labs (Sep 2020 - Jan 2022 | 1.4 years)
- Maintained Python REST APIs and participated in weekly code reviews and database tuning.
""",
        "interview_notes": """# Technical Interview: Elena Rostova
Interviewer: Alex Mercer (Principal Architect)
Date: 2025-02-20

Elena demonstrated strong proficiency in modern Python 3.10 and AsyncIO. Her experience with RabbitMQ is solid, though her Kafka exposure has been primarily consumption rather than architecting multi-broker clusters from scratch. She has 3.5 years of continuous production experience with regular on-call participation.
""",
        "technical_assessment": """# Technical Assessment: Elena Rostova
Score: 84 / 100 | Grade: Good (Tier: Gold)
- Asynchronous API endpoints implemented cleanly.
- Redis caching logic properly implemented with TTL.
- Minor latency jitter under peak 40k req/s load test.
""",
        "project_rfc": """# RFC-022: Asynchronous Media Dispatch Service
Company: Omnilink Media
Author: Elena Rostova | Status: Production Active
"""
    },

    {
        "candidate_id": "case_04_med_02",
        "name": "David Kim",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_medium",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 92.0,
            "expert_scores": {"reviewer_1": 80, "reviewer_2": 81, "reviewer_3": 79}
        },
        "cv_text": """# David Kim, Systems Engineer
Email: david.kim@cloudsys.net | Location: San Jose, CA

## Experience
Systems Engineer | Veloce Networks (2021 - Present | 4 years)
- Built Python and AsyncIO services for network telemetry monitoring.
- Managed Kafka event consumer instances and ClickHouse analytical storage.
- 4 years production deployment and on-call rotation experience.
""",
        "interview_notes": """# Interview: David Kim
Demonstrated clear, practical knowledge of Python asyncio and Kafka consumer lag monitoring. Confirmed 4 years of continuous production experience and on-call support.
""",
        "technical_assessment": """# Technical Assessment: David Kim
Score: 81 / 100 | Grade: Good (Tier: Gold)
Passed all functional test suites with clean, readable async Python code.
""",
        "project_rfc": """# RFC-19: Telemetry Monitoring Collector
Company: Veloce Networks | Author: David Kim
"""
    },

    {
        "candidate_id": "case_05_med_03",
        "name": "Priya Patel",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_medium",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 90.0,
            "expert_scores": {"reviewer_1": 77, "reviewer_2": 78, "reviewer_3": 76}
        },
        "cv_text": """# Priya Patel, Python Backend Developer
Email: priya.patel@datahub.co | Location: Chicago, IL

## Experience
Backend Engineer | DataHub Analytics (2022 - Present | 3 years)
- Built data processing microservices with Python, FastAPI, and PostgreSQL.
- Implemented event streaming using RabbitMQ and Redis pub/sub.
- 3 years production experience with on-call duties.
""",
        "interview_notes": """# Interview: Priya Patel
Solid knowledge of Python asynchronous programming. Good understanding of database indexes and messaging queues.
""",
        "technical_assessment": """# Technical Assessment: Priya Patel
Score: 78 / 100 | Grade: Competent (Tier: Silver)
Functional code delivered on time. Handled test scenarios cleanly.
""",
        "project_rfc": """# RFC-31: Event Pipeline Architecture
Company: DataHub Analytics | Author: Priya Patel
"""
    },

    {
        "candidate_id": "case_06_weak_01",
        "name": "Tom Bradley",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 88.0,
            "expert_scores": {"reviewer_1": 58, "reviewer_2": 60, "reviewer_3": 56}
        },
        "cv_text": """# Tom Bradley, Junior-Mid Backend Engineer
Location: Denver, CO | Experience: 1.8 years total
- Built REST endpoints using Django and SQLite/PostgreSQL.
- Basic familiarity with Python and Docker.
- No commercial Kafka or large-scale distributed systems experience.
""",
        "interview_notes": """# Interview: Tom Bradley
Candidate was candid about having limited distributed systems experience. Has primarily built monolithic Django applications and has not operated production Kafka or participated in high-severity on-call rotations.
""",
        "technical_assessment": """# Technical Assessment: Tom Bradley
Score: 58 / 100 | Grade: Below Threshold (Tier: Bronze)
Failed asynchronous stress test; endpoints blocked during concurrent database calls.
""",
        "project_rfc": """# RFC-04: Internal Dashboard API
Author: Tom Bradley | Status: Prototype
"""
    },

    {
        "candidate_id": "case_07_weak_02",
        "name": "Jessica Lee",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 89.0,
            "expert_scores": {"reviewer_1": 52, "reviewer_2": 50, "reviewer_3": 54}
        },
        "cv_text": """# Jessica Lee, Web Developer
Location: Portland, OR | Experience: 1.5 years
- Frontend React developer transitioning into backend Python Flask development.
- Basic scripting knowledge, no production distributed systems tenure.
""",
        "interview_notes": """# Interview: Jessica Lee
Strong frontend knowledge, but junior in backend distributed architectures. Lacks experience with Kafka and AsyncIO concurrency.
""",
        "technical_assessment": """# Technical Assessment: Jessica Lee
Score: 50 / 100 | Grade: Below Threshold (Tier: Bronze)
Basic API completed, failed distributed synchronization tests.
""",
        "project_rfc": """# RFC-01: User Profile Service Migration
Author: Jessica Lee
"""
    },

    {
        "candidate_id": "case_08_weak_03",
        "name": "Lucas Meyer",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "normal_weak",
        "ground_truth": {
            "expected_quadrant": "WEAK MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "expected_consistency": 91.0,
            "expert_scores": {"reviewer_1": 46, "reviewer_2": 44, "reviewer_3": 48}
        },
        "cv_text": """# Lucas Meyer, Data Analyst / Junior Scripting Developer
Location: Austin, TX | Experience: 1 year
- Wrote automated ETL scripts in Python using Pandas and cron jobs.
- No commercial experience with microservices, Kafka, or production on-call.
""",
        "interview_notes": """# Interview: Lucas Meyer
Candidate admitted during technical screening that he has only used Python for offline data scripting and has never built or deployed an asynchronous distributed service.
""",
        "technical_assessment": """# Technical Assessment: Lucas Meyer
Score: 45 / 100 | Grade: Fail (Tier: Bronze)
Could not complete the AsyncIO event loop challenge.
""",
        "project_rfc": """# RFC-Draft: Script Scheduler Automation
Author: Lucas Meyer
"""
    },

    # =========================================================================
    # 4 ADVERSARIAL CASES (Planted contradictions across sources)
    # =========================================================================
    {
        "candidate_id": "case_09_adv_cv_vs_interview",
        "name": "Jordan Hayes",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "adversarial",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "tenure_mismatch_cv_vs_interview",
            "expected_consistency": 25.0,
            "expert_scores": {"reviewer_1": 60, "reviewer_2": 58, "reviewer_3": 62}
        },
        "cv_text": """# Jordan Hayes, Lead Distributed Systems Architect
Email: j.hayes@cloudinfra.net | Location: New York, NY

## Experience
Lead Systems Architect | FinTech Cloud (2021 - Present | 4 years full-time)
- Headed core infrastructure team for 4 continuous years designing Kafka streaming engines.
- 4 years of senior leadership and 24/7 on-call tier ownership.
""",
        "interview_notes": """# Technical Interview: Jordan Hayes
Interviewer: Alex Mercer (Principal Architect)

Alex: "Your CV mentions 4 years as Lead Systems Architect at FinTech Cloud starting in early 2021. Can you walk me through that timeline?"
Jordan: "Oh, to clarify, I was actually an independent contractor working on other client contracts until mid-2023. I joined FinTech Cloud full-time about 14 months ago in late 2023 as a mid-level contractor before converting."
""",
        "technical_assessment": """# Technical Assessment: Jordan Hayes
Score: 82 / 100 | Grade: Pass
Implemented asynchronous queue endpoints with satisfactory throughput.
""",
        "project_rfc": """# RFC-12: Event Ingestion Bridge
Company: FinTech Cloud | Author: Jordan Hayes
"""
    },

    {
        "candidate_id": "case_10_adv_cv_vs_assessment",
        "name": "Ryan Mercer",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "adversarial",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "skill_claim_vs_assessment_failure",
            "expected_consistency": 20.0,
            "expert_scores": {"reviewer_1": 45, "reviewer_2": 42, "reviewer_3": 48}
        },
        "cv_text": """# Ryan Mercer, Principal AsyncIO & Python Architect
Email: ryan.mercer@deepkernel.org | Location: Chicago, IL

## Technical Summary
- Recognized world-class authority on Python AsyncIO internals, uvloop runtime, and low-latency non-blocking network programming.
- Author of high-throughput async microservices processing millions of concurrent connections.
""",
        "interview_notes": """# Interview: Ryan Mercer
Discussed high-level async theory fluently and claimed deep expertise in debugging deadlocks and event loop starvation.
""",
        "technical_assessment": """# Technical Assessment: Ryan Mercer
Challenge: "Asynchronous Deadlock Resolution & Concurrency Pipeline"
Score: 22 / 100 | Grade: Critical Failure (Tier: Bronze)

## Test Results
- Concurrency Suite: FAILED (Produced immediate event loop deadlocks under 50 concurrent requests)
- Unhandled Exception Trap: FAILED (Fatal unhandled exceptions crashed Python runtime)
- Memory Profiling: FAILED (Rapid memory leak exceeding 2GB within 90 seconds)
Evaluator Note: "Code displayed catastrophic misunderstanding of async task scheduling; used blocking time.sleep() inside async coroutines, freezing the entire event loop."
""",
        "project_rfc": """# RFC-88: High Performance Microservices
Author: Ryan Mercer
"""
    },

    {
        "candidate_id": "case_11_adv_interview_vs_assessment",
        "name": "Chloe Bennett",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "adversarial",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "interview_claim_vs_assessment_deadlock",
            "expected_consistency": 22.0,
            "expert_scores": {"reviewer_1": 48, "reviewer_2": 46, "reviewer_3": 50}
        },
        "cv_text": """# Chloe Bennett, Backend Engineer
Experience: 3 years at Distributed Data Systems working on Python backend services.
""",
        "interview_notes": """# Interview: Chloe Bennett
Interviewer: "How do you guarantee your async pipelines are free of concurrency race conditions?"
Chloe: "I have perfected race condition prevention. In my production services, I guarantee 100% deadlock-free execution through strict lock hierarchy ordering and non-blocking synchronization primitives."
""",
        "technical_assessment": """# Technical Assessment: Chloe Bennett
Score: 35 / 100 | Grade: Critical Failure
Test Suite: FAILED. The submitted code entered an irreversible deadlock within 4 seconds of execution due to circular lock acquisition between two coroutines.
""",
        "project_rfc": """# RFC-33: Concurrency Engine Specification
Author: Chloe Bennett
"""
    },

    {
        "candidate_id": "case_12_adv_jd_vs_claim",
        "name": "Evan Brooks",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "incomplete",
        "ground_truth": {
            "expected_quadrant": "INSUFFICIENT EVIDENCE",
            "has_contradiction": False,
            "contradiction_type": None,
            "has_insufficient_evidence": True,
            "missing_requirements": ["REQ-02"],
            "expected_consistency": 55.0,
            "expert_scores": {"reviewer_1": 35, "reviewer_2": 32, "reviewer_3": 38},
            "expert_composite_score": 35.0
        },
        "cv_text": """# Evan Brooks, Senior Architect
Email: evan.brooks@cloudsys.net | Location: Chicago, IL

## Experience
Senior Architect | CloudSys Solutions (2020 - Present | 4 years)
- Architected enterprise relational data storage and microservice APIs using Python and FastAPI.
- Maintained 99.9% uptime across production web services with synchronous PostgreSQL backends.
- No experience with Kafka, RabbitMQ, or distributed event streaming architectures.
""",
        "interview_notes": """# Interview: Evan Brooks
Interviewer: "The JD specifies hands-on experience scaling Apache Kafka event streaming clusters. Have you deployed Kafka in production?"
Evan: "No, in my past roles at CloudSys we strictly utilized relational databases and synchronous REST endpoints. I have never configured or operated a Kafka broker or managed partition topologies."
""",
        "technical_assessment": """# Technical Assessment: Evan Brooks
Score: 75 / 100 | Grade: Pass (Synchronous Track)
Successfully implemented async HTTP request routing. Candidate skipped the optional Kafka streaming module as he has no streaming background.
""",
        "project_rfc": """# RFC-02: Microservice API Gateway Architecture
Company: CloudSys Solutions | Author: Evan Brooks
"""
    },

    # =========================================================================
    # 2 INCOMPLETE CASES (Missing one primary evaluation source)
    # =========================================================================
    {
        "candidate_id": "case_13_incomplete_no_interview",
        "name": "Nathaniel Reed",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "incomplete",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "has_insufficient_evidence": True,
            "missing_document": "interview_notes",
            "expected_consistency": 85.0,
            "expert_scores": {"reviewer_1": 75, "reviewer_2": 72, "reviewer_3": 76}
        },
        "cv_text": """# Nathaniel Reed, Distributed Systems Engineer
GitHub: github.com/n-reed (3 repos, 60 stars) | Location: Atlanta, GA
3.5 years experience developing asynchronous backend services in Python, aiokafka, and PostgreSQL at GridScale.
""",
        "interview_notes": "",  # Incomplete: Interview notes unavailable
        "technical_assessment": """# Technical Assessment: Nathaniel Reed
Score: 88 / 100 | Grade: Superior
Passed all async concurrency and message ingestion benchmarks cleanly.
""",
        "project_rfc": """# RFC-10: Ingestion Scaling Spec
Author: Nathaniel Reed | Company: GridScale
"""
    },

    {
        "candidate_id": "case_14_incomplete_no_assessment",
        "name": "Maya Lin",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "incomplete",
        "ground_truth": {
            "expected_quadrant": "STRONG MATCH",
            "has_contradiction": False,
            "contradiction_type": None,
            "has_insufficient_evidence": True,
            "missing_document": "technical_assessment",
            "expected_consistency": 85.0,
            "expert_scores": {"reviewer_1": 74, "reviewer_2": 73, "reviewer_3": 75}
        },
        "cv_text": """# Maya Lin, Senior Backend Engineer
Location: San Francisco, CA | 4 years experience at DataStream
Engineered Kafka event streaming services in Python and Go processing 20M events/day.
""",
        "interview_notes": """# Technical Interview: Maya Lin
Demonstrated high technical depth in distributed event systems, offset management, and PostgreSQL optimization. 4 years of continuous production on-call experience verified.
""",
        "technical_assessment": "",  # Incomplete: Take-home assessment waived/pending
        "project_rfc": """# RFC-71: Multi-Region Event Streaming
Author: Maya Lin | Company: DataStream
"""
    },

    # =========================================================================
    # 1 DECEPTIVE CENTERPIECE CASE (Alexander Sterling)
    # High on-paper fit, stellar buzzwords, severe multi-source contradictions
    # =========================================================================
    {
        "candidate_id": "case_15_deceptive_centerpiece",
        "name": "Alexander Sterling",
        "target_role": "Senior Python & Distributed Systems Engineer",
        "category": "centerpiece_deceptive",
        "ground_truth": {
            "expected_quadrant": "REVIEW REQUIRED",
            "has_contradiction": True,
            "contradiction_type": "deceptive_leadership_and_tenure_fabrication",
            "expected_consistency": 0.0,
            "expert_scores": {"reviewer_1": 55, "reviewer_2": 52, "reviewer_3": 50}
        },
        "cv_text": """# Alexander Sterling, Lead Distributed Systems Architect
Email: alexander.sterling@finflow-tech.internal | GitHub: github.com/asterling-core (6 repos, 250+ stars)
LinkedIn: linkedin.com/in/alexander-sterling-dist | Location: San Francisco, CA

## Executive Summary
Visionary Distributed Systems Leader with over 8 years of engineering mastery across high-throughput financial architectures, asynchronous Python systems, and real-time Kafka event streams. Renowned for orchestrating zero-downtime enterprise transformations and mentoring high-performing engineering organizations.

## Technical Skills Matrix
- Core Languages: Python 3.10/3.11/3.12 (Expert, AsyncIO, uvloop, C-Extensions), Go, Rust, C++
- Distributed Messaging: Apache Kafka (Enterprise Architecture, Kafka Connect, KSQL), RabbitMQ, Redis Cluster
- Storage & Data Layer: PostgreSQL (Custom Partitioning, Logical Replication), ClickHouse, CockroachDB
- Systems Leadership: Author of Enterprise RFCs, Head of System Architecture, 24/7 On-Call Escalation Commander

## Professional Experience
Lead Distributed Systems Architect | FinFlow Technologies (Jan 2022 - Present | 3.5 years continuous tenure)
- Led migration of legacy monolithic core to Apache Kafka for a 7-person team, authoring the master architectural blueprint and decommissioning legacy systems with 100% data integrity.
- Designed distributed event mesh processing 40M financial events/day with guaranteed exactly-once processing semantics.
- 3.5 years of continuous production engineering leadership managing live high-throughput microservices and serving as primary incident commander for tier-1 production outages.

Senior Backend Engineer | Apex Distributed Solutions (Mar 2019 - Dec 2021 | 2.8 years)
- Architected asynchronous event ingestion pipelines using Python, AsyncIO, and Redis Streams.
- Optimized database indexing and PostgreSQL connection pooling across multi-region deployments.

## Open Source & Publications
- `distributed-raft-py` (github.com/asterling-core/distributed-raft-py): Python implementation of the Raft consensus algorithm with asyncio network transport. 250+ GitHub stars.
- Author of technical whitepapers on high-throughput event sourcing.
""",
        "interview_notes": """# Technical Screening & Architectural Interview: Alexander Sterling
Candidate: Alexander Sterling
Interviewers: Dr. Sarah Vance (Director of Infrastructure) & Alex Mercer (Principal Architect)
Date: 2025-02-22 | Duration: 65 minutes | Format: Video & Live Architecture Review

[00:05] Alex: "Welcome Alexander. Your CV presents an extraordinary background in Kafka and distributed architecture at FinFlow. Can you start by clarifying your timeline at FinFlow Technologies?"
[00:08] Alexander: "Certainly. At FinFlow I took charge of our core modernization. I joined initially on a specialized contractor basis around 18 months ago, before transitioning to help drive the Kafka initiative."
[00:10] Sarah: "Wait, your CV lists your title as 'Lead Distributed Systems Architect' from January 2022 to the present, which would be over 3.5 years. But you just mentioned you joined ~18 months ago on a contract basis?"
[00:12] Alexander: "Well, yes, my formal involvement with the FinFlow project started ~18 months ago initially on a contract basis through my consulting entity. The earlier dates represent preliminary external advisory discussions regarding their architecture."

[00:25] Alex: "Let's dive into the core migration project mentioned on your CV: 'Led migration of legacy monolithic core to Apache Kafka for a 7-person team.' What was your specific architectural authority and leadership scope?"
[00:28] Alexander: "I was deeply involved with the Kafka rollout. I actually learned Kafka on the job after joining FinFlow, diving into consumer group rebalancing and Avro schemas to support the core transition."
[00:30] Sarah: "You learned Kafka on the job after joining 18 months ago? But your CV describes you as having 8+ years of distributed systems and Kafka mastery leading the migration."
[00:32] Alexander: "I meant that while I understood the theoretical messaging paradigms previously, FinFlow was where I first executed commercial Kafka streaming at scale."

[00:45] Alex: "In production, how did you configure Kafka consumer group offset commits to prevent duplicate processing?"
[00:48] Alexander: "We relied on the default automated commits in the library configuration with a 5-second interval."
[00:50] Alex: "Default auto-commit with a 5-second interval will cause data duplication during sudden consumer worker crashes or rebalances. Did you implement idempotent consumer keys or manual offset management?"
[00:52] Alexander: "The core framework layer was configured by our principal architect, Dr. Vance; my focus was primarily writing the message serialization wrappers."
""",
        "technical_assessment": """# Technical Assessment Report: Alexander Sterling
Assessment Challenge: "Async Distributed Task Broker with Partition Rebalance Handling"
Submitted: 2025-02-23 | Evaluator: Staff Infrastructure Engineer
Score: 78 / 100 | Grade: Competent (Tier: Silver)

## Test Results
- Asynchronous API Structure: PASSED (Clean FastAPI async endpoints with Pydantic validation)
- Basic Message Ingestion: PASSED (Successfully pushed events into Redis queue)
- Partition Rebalance Stress Test: FAILED (Produced 14 duplicate message processing events due to unhandled offset commits during simulated worker crashes)
- Memory Footprint: PASSED (Stable memory usage at 95MB)

## Evaluator Comments
"The candidate clearly knows how to write clean, idiomatic Python code and uses modern AsyncIO syntax effectively. However, the implementation revealed surprising gaps in distributed systems edge cases: partition rebalance signals were ignored, and offset committing was left to default timers, leading to duplicate event processing under failure simulation."
""",
        "project_rfc": """# Project RFC-042: FinFlow Core Monolith to Kafka Streaming Migration
Project: Core Banking & Transaction Telemetry Migration
Document ID: FIN-RFC-2023-042 | Version: 2.4 | Classification: Internal Confidential
Company: FinFlow Technologies Inc.

## Project Leadership & Engineering Team Roster
- Principal System Architect & Project Lead: Dr. Robert Vance, PhD (Architecture Lead, Kafka Core Topology)
- Technical Project Manager: Claire Dubois
- Senior Infrastructure Engineer: Vikram Malhotra (Kafka Cluster Operations & SRE)
- Software Engineer (Core Services): Alexander Sterling (Contributing member responsible for secondary message schema serialization and endpoint mapping)
- Backend Engineer: Kevin Zhang
- Backend Engineer: Priya Sharma
- QA & Reliability Engineer: Marcus Brody

## Executive Project Charter
Under the leadership of Principal Architect Dr. Robert Vance, the 7-person Core Services team was chartered in August 2023 to decouple the legacy monolithic ledger into an event-driven architecture using Apache Kafka. 

Alexander Sterling served as a contributing member of the 7-person implementation team led by Principal Architect Dr. Robert Vance. Alexander was tasked with developing Python serialization adapters for legacy message formats under the technical direction of Dr. Vance.
"""
    }
]

# Ensure expert_composite_score is explicitly calculated and stored for every case
for _c in CASES:
    _gt = _c.get("ground_truth", {})
    if "expert_scores" in _gt and "expert_composite_score" not in _gt:
        _scores = list(_gt["expert_scores"].values())
        _gt["expert_composite_score"] = round(sum(_scores) / len(_scores), 2)


def export_cases_to_disk(target_dir: str = "eval_cases"):
    """Exports all 15 benchmark cases to individual JSON files."""
    import json
    import os
    os.makedirs(target_dir, exist_ok=True)
    for c in CASES:
        fpath = os.path.join(target_dir, f"{c['candidate_id']}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2)


