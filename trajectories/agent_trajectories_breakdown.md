# Agent Execution Trajectories Breakdown
**HireTrace: Evidence-First Candidate Assessment Agent**

This document traces the intermediate inputs, retrieval calls, execution steps, retry handling, and final outputs for all **4 Ollama-backed agents** operating on the centerpiece deceptive case (`case_15_deceptive_centerpiece`: Alexander Sterling).

---

## Agent 1: Requirement Mapping Agent (`RequirementMappingAgent`)

### 1.1 Input
- **Job Description:** Senior Python & Distributed Systems Engineer at CloudMesh Infrastructure
- **Target Role:** Senior Python & Distributed Systems Engineer

### 1.2 Ollama Generation Call
- **Model:** `qwen2.5:3b` (local Ollama, GPU RTX 3050 Laptop)
- **Format:** `json`
- **Temperature:** 0.1

```json
{
  "prompt": "Role: Senior Python & Distributed Systems Engineer\n\nJob Description:\n# Senior Python & Distributed Systems Engineer\nCompany: CloudMesh Infrastructure\n...\nDecompose into 4-6 key requirements:",
  "system_prompt": "You are a senior hiring architect. Analyze the provided Job Description (JD)... Output strictly JSON matching this structure..."
}
```

### 1.3 Intermediate Output
```json
{
  "requirements": [
    {
      "req_id": "REQ-01",
      "name": "Advanced Python & AsyncIO Proficiency",
      "category": "technical_skills",
      "description": "Proficiency in modern Python (3.10+), asyncio concurrency, and typing.",
      "importance": "MUST_HAVE",
      "expected_sources": ["cv", "assessment", "interview"]
    },
    {
      "req_id": "REQ-02",
      "name": "Experience with Distributed Systems and Message Queues",
      "category": "architecture",
      "description": "Experience designing, deploying, and operating Apache Kafka or RabbitMQ event pipelines.",
      "importance": "MUST_HAVE",
      "expected_sources": ["cv", "project", "interview"]
    },
    {
      "req_id": "REQ-03",
      "name": "Experience with Microservices and High Availability",
      "category": "architecture",
      "description": "Designing microservices with high uptime SLAs (99.99%), PostgreSQL partitioning, and Redis caching.",
      "importance": "MUST_HAVE",
      "expected_sources": ["cv", "interview", "project"]
    },
    {
      "req_id": "REQ-04",
      "name": "Experience with Technical Leadership",
      "category": "leadership",
      "description": "Experience leading major service migrations, authoring RFCs, and mentoring team members.",
      "importance": "IMPORTANT",
      "expected_sources": ["cv", "interview", "project"]
    },
    {
      "req_id": "REQ-05",
      "name": "Production Experience",
      "category": "production_experience",
      "description": "At least 3+ years of commercial production experience managing live services.",
      "importance": "MUST_HAVE",
      "expected_sources": ["cv", "interview"]
    }
  ]
}
```

---

## Agent 2: Evidence Aggregation Agent (`EvidenceAggregationAgent`)

### 2.1 Retrieval Calls (AegisRAG-Engine FAISS Pattern)
For each requirement query, the agent queries the in-memory FAISS vector index across candidate spans (`IndexFlatIP` on normalized embeddings):

- **Query `REQ-01`**: `"Advanced Python & AsyncIO Proficiency"` -> Retrieves:
  - `CV-004`: `"Skills: Python, AsyncIO, Apache Kafka, Distributed Architecture, PostgreSQL, Redis, Leadership."` (sim: 0.742)
  - `ASS-001`: `"Technical Assessment: High-Throughput Async Ingestion Service. Score: 84/100."` (sim: 0.688)
  - `ASS-002`: `"Struggled during follow-up to explain the async locking mechanism in his submission."` (sim: 0.651)

- **Query `REQ-04`**: `"Experience with Technical Leadership"` -> Retrieves:
  - `CV-002`: `"Led migration of legacy monolithic core to Apache Kafka event streams for a 7-person team."` (sim: 0.812)
  - `INT-001`: `"Interview Notes - Alexander Sterling (Technical Panel): Candidate was charming and spoke at a very high executive level."` (sim: 0.589)
  - `PRO-001`: `"Alexander Sterling served as a contributing member of the 7-person implementation team led by Principal Architect Dr. Robert Vance."` (sim: 0.795)

- **Query `REQ-05`**: `"Production Experience and Tenure"` -> Retrieves:
  - `CV-002`: `"3 years of production engineering leadership at FinFlow Technologies managing high-throughput services."` (sim: 0.765)
  - `INT-002`: `"When asked to trace the timeline at FinFlow Technologies, candidate stated: 'I joined FinFlow ~18 months ago initially on a contract basis.'"` (sim: 0.824)

### 2.2 Baseline Rubric Input (Industry Standard ATS Rubric Scorer)
- `raw_total`: `75.0 / 120`
- `normalized_score`: `62.5 / 100`

---

## Agent 3: Cross-Source Verification Agent (`CrossSourceVerificationAgent`)

### 3.1 Verification Execution & Retry Demonstration
- **Input:** Aggregated evidence spans for `REQ-04` (Leadership) and `REQ-05` (Tenure).
- **Execution Trajectory & Discrepancy Extraction:**
  The agent detects that `CV-002` claims the candidate *led* the team and migration, while `PRO-001` explicitly notes the candidate was a contributing member of a team led by *Principal Architect Dr. Robert Vance*.
  Simultaneously, `CV-002` claims 3 years of tenure, while `INT-002` notes the candidate joined ~18 months ago.

### 3.2 Output: Evidence Matrix
```json
{
  "total_requirements": 5,
  "supported_count": 0,
  "contradicted_count": 5,
  "insufficient_count": 0,
  "consistency_score": 0.0,
  "all_discrepancies": [
    {
      "discrepancy_id": "DISC-REQ-04-LEAD",
      "topic": "Leadership and Team Role Scope",
      "source_a": "cv (cv.txt)",
      "quote_a": "Led migration of legacy monolithic core to Apache Kafka event streams for a 7-person team.",
      "source_b": "project (project_doc.txt: PRO-001)",
      "quote_b": "Alexander Sterling served as a contributing member of the 7-person implementation team led by Principal Architect Dr. Robert Vance.",
      "contradiction_type": "cv_vs_project",
      "severity": "HIGH"
    },
    {
      "discrepancy_id": "DISC-REQ-05-TENURE",
      "topic": "Employment Tenure Mismatch",
      "source_a": "cv (cv.txt)",
      "quote_a": "3 years of production engineering leadership at FinFlow Technologies",
      "source_b": "interview (interview_notes.txt: INT-002)",
      "quote_b": "Interview notes state candidate joined ~18 months ago initially on a contract basis",
      "contradiction_type": "cv_vs_interview",
      "severity": "HIGH"
    }
  ]
}
```

---

## Agent 4: Recommendation Writer Agent (`RecommendationWriterAgent`)

### 4.1 Synthesis
- **Role Fit Score:** `47.9 / 100` (incorporating rubric baseline and partial skill match).
- **Evidence Consistency Score:** `0.0 / 100` (heavily penalized by multiple critical cross-source contradictions).
- **Quadrant Placement:** `[REVIEW REQUIRED]` / `[INSUFFICIENT EVIDENCE]` (strictly low consistency quadrant).
- **Recommendation:** `"Proceed to human review."` (Autonomous hire/no-hire verdict is forbidden).

### 4.2 Priority Questions Generated
1. *"Could you clarify your employment timeline at FinFlow Technologies, and resolve the discrepancy between the 3 years claimed on your CV and the 18 months stated during the interview?"*
2. *"Could you elaborate on your specific technical contributions and architecture design during the FinFlow Core Migration, specifically your role relative to Principal Architect Dr. Robert Vance?"*
3. *"Could you walk us through the async locking mechanism in your technical assessment submission and explain why that specific lock was necessary?"*
