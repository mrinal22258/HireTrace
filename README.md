---
title: HireTrace
emoji: 🔍
colorFrom: pink
colorTo: purple
sdk: static
pinned: false
---

# HireTrace — Evidence-First Candidate Assessment Agent
> **"Every recommendation traces back to evidence."**  
> *micro1 Agentic Workflows Hackathon Submission*

[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Live%20Demo-ffcc4d?style=for-the-badge&logo=huggingface&logoColor=black)](https://huggingface.co/spaces/mrinal22258/HireTrace)
[![GitHub](https://img.shields.io/badge/GitHub-HireTrace-181717?style=for-the-badge&logo=github)](https://github.com/mrinal22258/HireTrace)

> **Quick-Access Links & Deliverables:**
> - 🚀 **Live Interactive Demo (Hugging Face Space):** [https://huggingface.co/spaces/mrinal22258/HireTrace](https://huggingface.co/spaces/mrinal22258/HireTrace)
> - 💻 **GitHub Repository:** [https://github.com/mrinal22258/HireTrace](https://github.com/mrinal22258/HireTrace)
> - 🎥 **Solution Video Walkthrough:** [Watch 4m 30s Demo on Google Drive](https://drive.google.com/file/d/1ajwkjejxtr26-_YHMBBoYHxyitFg6k7d/view?usp=drive_link) *(script in [`docs/solution_video_script.md`](docs/solution_video_script.md))*
> - ⚡ **Fresh Setup & Inspection Guide:** [`JUDGES_SETUP_GUIDE.md`](JUDGES_SETUP_GUIDE.md) *(<60s Instant Inspection vs. Full Live LLM Pipeline)*
> - 📋 **Deliverable #1 (Improvement Changelog):** [`CHANGELOG.md`](CHANGELOG.md)
> - 🏛️ **Deliverable #2 (Architecture & Problem Framing):** §1–§5 below
> - 📊 **Deliverable #3 (Evaluation Harness & Empirical Report):** §6–§7 below & [`eval/eval_report.md`](eval/eval_report.md)
> - 🧭 **Deliverable #4 (Agent Execution Trajectories):** [`trajectories/`](trajectories/) & [`trajectories/agent_trajectories_breakdown.md`](trajectories/agent_trajectories_breakdown.md)

---

## 🚀 Deployment Modes: Demo / Replay Mode vs. Live Product Mode

HireTrace supports two distinct operational modes:

### Mode A: Demo / Replay Mode (Static Web / Hugging Face Spaces)
- **Environment**: Hugging Face Spaces (static hosting) or any static HTTP file server.
- **Capabilities**: Replays pre-computed evaluation trajectories, interactive evidence citations, 2D quadrant scatter, and pre-screened synthetic candidate dossiers without requiring a GPU or server process.
- **Limitation**: **Cannot run live, real-time candidate evaluation.** A static Hugging Face Space has no backend compute or local Ollama/vLLM weights. Uploading a new candidate in static replay mode displays mock ingestion or directs the user to the local self-hosted deployment.
- **Static Bundle Generation**: Root-level static files (`index.html`, `static_data.js`, `app.js`, `styles.css`, etc.) required by Hugging Face Spaces are generated automatically from `ui/` by `python scripts/build_static.py`. They should never be hand-edited — always edit the canonical source files in `ui/` and rebuild with `python scripts/build_static.py`.

### Mode B: Production Scalable Architecture (Self-Hosted Web, Workers & Multi-GPU LLMs)
- **Environment**: Distributed or single-host Linux/macOS/Windows cluster featuring stateless ASGI Web API containers, independent Celery workers, Redis job broker, PostgreSQL database, persistent storage volumes, and a multi-endpoint local LLM pool (`qwen2.5:3b`, `qwen2.5:7b`, or `llama3.1:8b`).
- **Architecture Highlights**:
  - **Stateless Web Tier (`web`)**: FastAPI ASGI server with JSON access logging, API key / tenant isolation, sliding-window rate limiting, `/healthz` (liveness), and `/readyz` (readiness).
  - **Distributed Task Queue (`worker`)**: Celery workers backed by Redis with late acknowledgment (`acks_late=True`) and unacknowledged job re-delivery on failure.
  - **Single Source of Truth (`postgres`)**: PostgreSQL database with Alembic schema migrations (`alembic upgrade head`) replacing in-process memory state.
  - **Multi-Endpoint LLM Inference (`ollama` / `vllm`)**: Round-robin and least-connections routing across multiple GPU endpoints with dynamic concurrency semaphores and circuit breaking.
  - **Persistent Storage Provider**: Named Docker volumes or S3-compatible object storage for candidate dossiers, vector indices, and execution trajectories.
  - **Observability**: Prometheus `/metrics` endpoint exposing queue depth, latency histograms, and LLM telemetry.

- **Quickstart (Standard Production Docker Compose)**:
  ```bash
  # Spin up Web API, Celery Worker, PostgreSQL, Redis, and Ollama:
  docker compose up -d --build

  # Pull the default open-weights model into Ollama:
  docker exec -it hiretrace_ollama ollama pull qwen2.5:3b
  ```

- **Horizontal Scaling Commands**:
  ```bash
  # Scale to 3 Web replicas and 4 Celery workers independently:
  docker compose --scale web=3 --scale worker=4 up -d

  # Scale LLM inference horizontally across 2 GPU nodes:
  export OLLAMA_BASE_URLS="http://gpu-node-01:11434,http://gpu-node-02:11434"
  docker compose restart worker
  ```

- **Local Zero-Config Dev Quickstart (SQLite + Thread Pool Fallback)**:
  ```bash
  pip install -r requirements.txt
  export HIRETRACE_DEV_MODE=1  # (On Windows: $env:HIRETRACE_DEV_MODE="1")
  python ui/server.py --port 8000
  ```
  *(In local development, HireTrace automatically detects missing Redis/Postgres and falls back gracefully to WAL-mode SQLite and an in-process thread pool, requiring zero external services to run. Setting `HIRETRACE_DEV_MODE=1` enables frictionless local testing without requiring API keys. In production, authentication is required by default, and `HIRETRACE_API_KEY` (minimum 24 characters) and `POSTGRES_PASSWORD` must be configured.)*

  > [!IMPORTANT]
  > **Deterministic Demo Mode vs. Live Model Scoring**:  
  > If local Ollama is not installed or `qwen2.5:3b` is not pulled, HireTrace **safely and intentionally runs in deterministic-only demo mode**. It scores candidates using validated deterministic rubrics (Baseline A) and refuses to fabricate LLM role-fit scores (displaying `N/A — LLM offline` on AI gauges). **This is expected, evidence-first behavior, not a bug.**
  > 
  > To enable live LLM evaluation:
  > 1. Install [Ollama](https://ollama.ai) and run:
  >    ```bash
  >    ollama serve
  >    ollama pull qwen2.5:3b
  >    ```
  > 2. Verify the model endpoint is reachable:
  >    ```bash
  >    curl http://localhost:11434/api/tags
  >    ```
  > Once Ollama is reachable, `/api/system/mode` automatically transitions to **Live Mode**, unlocking real-time multi-agent reasoning.


- **Dependency Management & Reproducible Builds**:
  HireTrace uses exact pins in `requirements.txt` and a fully resolved transitive lockfile in `requirements-lock.txt` for deterministic production builds:
  - **Deterministic Installation**: `pip install -r requirements-lock.txt`
  - **Upgrading Dependencies**:
    1. Update the target package version in `requirements.txt`.
    2. Install the updated package and run the test suite: `pytest -v`.
    3. Re-generate `requirements-lock.txt` (`pip freeze` or `pip-compile`).
    4. Commit both `requirements.txt` and `requirements-lock.txt`.

- **Production Security Headers & Edge TLS**:
  HireTrace sets defense-in-depth security response headers via an ASGI middleware on all routes:
  - `Content-Security-Policy`: Restricts scripts, styles, images, and fonts (`default-src 'self' ...`).
  - `Referrer-Policy`: `no-referrer` to eliminate leakage of candidate or tenant identifiers in outbound referrer headers.
  - `X-Frame-Options`: `DENY` to prevent clickjacking.
  - `X-Content-Type-Options`: `nosniff` to prevent MIME-sniffing exploits.
  - **Strict-Transport-Security (HSTS) Notice**: HSTS is intentionally **not** set by the internal application server, because HireTrace runs as plain HTTP behind a TLS-terminating reverse proxy / load balancer (e.g. Nginx, Caddy, Cloudflare, AWS ALB, or Kubernetes Ingress). **HSTS must be terminated and configured at your edge reverse proxy layer.**

- **Candidate Data Deletion & Retention Policies**:
  HireTrace provides GDPR/CCPA-compliant data lifecycle controls:
  - **On-Demand Candidate Deletion Endpoint (`DELETE /api/candidate/{candidate_id}`)**:
    - **Authentication**: Requires the same API key authorization and enforces tenant isolation.
    - **Path Traversal Guarded**: Validates `ID_REGEX` and asserts resolved paths before accessing the filesystem.
    - **What is Removed**: Atomically deletes the candidate record across all database tables (`candidates`, `documents`, `evaluations`, `dedup_hashes`, `job_queue`), purges all physical files from `uploads/{candidate_id}/`, `eval_cases/{candidate_id}.json`, and `trajectories/{candidate_id}_trajectory.json`, and evicts in-memory/disk caches (`EMBEDDING_CACHE`, `STATUS_CACHE`, and active `JOB_MANAGER` jobs).
    - **Irreversibility**: Deletion is immediate and permanent. Deleted candidate files cannot be recovered.
  - **Automated Data Retention Purge (`HIRETRACE_DATA_RETENTION_DAYS`)**:
    - **Default Behavior**: Unset (no automatic deletion; records persist indefinitely so existing deployments do not lose data on upgrade).
    - **Enabling Retention**: Set `HIRETRACE_DATA_RETENTION_DAYS=30` (or desired day window) in your environment.
    - **Execution**: Both Celery workers (via Celery Beat schedule) and the standalone DB polling worker check and purge candidate records older than the configured window on a scheduled basis, executing through the exact same unified deletion pipeline.

- **Candidate Browsing & Profile UI (Netflix-Style IA)**:
  - **Candidate Grid (`#/candidates`)**: Primary browsing surface presenting applicants as responsive cards featuring deterministic colorful initials avatars, quadrant placement badges, and compact inline meters for Role Fit and Evidence Consistency. Includes a persistent `+ New Candidate` intake tile, real-time search, quadrant dropdown, and quick filters (`All`, `Adversarial`, `Strong`, `Weak`).
  - **Sample / Demo Data Filter**: A "Show sample data" toggle in the grid toolbar filters synthetic benchmark candidates (`case_*`) from the active list via `/api/cases?include_demo=false` (default: off). When toggled on, benchmark cases appear in a distinct, collapsed-by-default group (`🧪 Demo & Benchmark Cases`) with `DEMO` corner ribbons.
  - **Decluttered Profile View (`#/candidates/{id}`)**: Full-page dedicated profile with sticky hero header, dynamic plain-English verdict sentence, 4-stat at-a-glance score row (Role Fit, Consistency, Unsupported Claims, Contradictions), and collapsed-by-default accordion sections (with persistent open state via `localStorage`). Includes an irreversible candidate deletion action calling `DELETE /api/candidate/{id}`.
  - **Ocean Depth Design System & Living Surfaces**: Built-in theme switcher with contrast-verified Ocean Light (Surface Water `#F2F7FA`) and micro1 pure-black Abyssal Dark (`#000000`). Features a site-wide WebGL2 living surface mesh (`#oceanMeshCanvas`), universal iridescent liquid glass buttons (`.btn`, `.btn-liquid-glass`) with cursor-following specular glints, and an interactive 3×3 direction-tracking mascot owl with continuous subpixel lean.

- **Configuration & Environment Variables**:

| Variable | Default | Purpose / Description |
|---|---|---|
| `HIRETRACE_DEV_MODE` | `0` (production) | When `1`, disables API key requirements and allows CORS localhost development origins. |
| `HIRETRACE_API_KEY` | *(Required in prod)* | Secret key for API authentication (minimum 24 characters). |
| `REDIS_PASSWORD` | *(Required in prod)* | Password for production Redis service authentication (`--requirepass`). |
| `REDIS_URL` | `redis://localhost:6379/0` | Connection URL for Redis rate limiting and Celery message broker. |
| `DATABASE_URL` | `sqlite:///hiretrace.db` | Connection URL for PostgreSQL (`postgresql+psycopg2://...`) or SQLite. |
| `HIRETRACE_MAX_PDF_PAGES` | `200` | Maximum page ceiling for synchronous PDF parsing; rejects oversized files to prevent DoS. |
| `HIRETRACE_PDF_PARSE_TIMEOUT_SECONDS` | `15` | Wall-clock timeout for synchronous PDF parsing before failing over with HTTP 422 to use `sync=false`. |
| `HIRETRACE_DATA_RETENTION_DAYS` | *(Unset)* | Automated candidate data retention window in days; purges older records across DB and disk. |
| `HIRETRACE_RATE_LIMIT_MAX_KEYS` | `10000` | Maximum in-memory LRU cache entries for rate limiter tracking keys. |
| `EMBEDDING_CACHE_MAX_ENTRIES` | `10000` | Maximum LRU cache entries for FAISS vector chunk embeddings. |
| `OLLAMA_BASE_URLS` | `http://localhost:11434` | Comma-separated list of Ollama inference endpoints for load balancing. |
| `HIRETRACE_MAX_UPLOAD_BYTES` | `52428800` (50MB) | Global request body streaming cap enforced via ASGI middleware. |
| `OLLAMA_KEEP_ALIVE` | `30m` | Model residency window in Ollama; prevents cold-start model reloading between evaluations. |
| `OLLAMA_NUM_CTX` | `8192` | Explicit LLM context window; eliminates silent dossier truncation and JSON schema breakage. |
| `OLLAMA_NUM_THREAD` | `0` | Thread count for Ollama compute; `0` lets Ollama auto-detect CPU cores. |
| `EMBEDDING_BACKEND` | `minilm` | Retrieval embedding provider: `minilm` (default transformer), `static` / `model2vec` (100x CPU lookup), `hashed`, or `auto`. |
| `PARSER_BACKEND` | `legacy` | Document parsing engine: `legacy` (default PyMuPDF/docx), `docling` (layout-aware with table recovery), or `auto`. |
| `PIXELRAG_FALLBACK` | `0` | When `1`, activates local image-only document fallback rendering pipeline (see `docs/PIXELRAG_FALLBACK.md`). |

*Query Parameter Note: `GET /api/cases` and `GET /api/leaderboard` accept `include_demo=false` (default) or `include_demo=true` to control whether synthetic benchmark candidates from `dataset.py` are returned.*





## 1. Problem Framing

- **Who has this problem:** Technical recruiters and engineering hiring managers deciding whether a candidate fits a role, using evidence spread across JDs, target profiles, CVs, interview notes, coding assessments, and project portfolios.
- **The Bottleneck:** Reviewing each source in isolation makes it easy to miss subtle contradictions or overweight a single signal (e.g., prestigious CV pedigree masking a failed hands-on assessment, or interview enthusiasm masking timeline fabrications). A single warning sign is never proof on its own, and isolated reviews obscure whether claims align across independent records.
- **How HireTrace Solves It:**
  1. Consolidates multi-source evidence into a single, citable review.
  2. Decomposes JD requirements into concrete verifiable competencies via a dedicated **Requirement Mapping Agent**.
  3. Indexes and retrieves atomic evidence spans using offline FAISS vector search (**AegisRAG-Engine pattern**).
  4. Cross-checks candidate claims across independent sources (**Cross-Source Verification Agent**).
  5. Reports **Role Fit** and **Evidence Consistency** as **two strictly separate dimensions** on a quadrant, rather than a blended score.
  6. **Never outputs an autonomous hire/no-hire verdict:** Output always routes to *"Proceed to human review"*, equipped with pointed, evidence-backed priority questions for the interviewer.
- **Reproducibility:** 100% offline, running locally on open weights via Ollama (`qwen2.5:3b` or `qwen2.5:1.5b`). Zero paid API dependencies ($0.00 cost), with synthetic candidate datasets only.

---

## 2. Reused Work vs. New Contributions

| Component | Origin | Attribution & Implementation Details |
|---|---|---|
| **Deterministic Rubric Scorer (`/baseline/rubric_scorer.py`)** | Adapted from CareerCheck | The category weights (`open_source` 0–35, `self_projects` 0–30, `production` 0–25, `technical_skills` 0–10, `bonus_points` 0–20; raw max = 120) are adapted from an earlier prototype (CareerCheck). **The scoring implementation here is a completely clean, dependency-free rewrite, not a port.** CareerCheck had duplicate scoring engines, insecure IDs, committed DB files, and broken CI. None of its database, Next.js, or FastAPI code is imported. |
| **Evidence Loader (`/agents/evidence_loader.py`)** | ResumeExtractBench | Reused the CV-to-structured-fields extraction pattern cleanly for deterministic profile extraction and span chunking. |
| **Retrieval Layer (`/agents/retrieval_layer.py`)** | AegisRAG-Engine | Reused the offline FAISS + semantic chunking retrieval pattern for matching JD requirements against candidate evidence spans. |
| **Multi-Agent Pipeline (`/agents/`)** | **New (HireTrace Core)** | 4-agent pipeline (Requirement Mapper, Evidence Aggregator, Cross-Source Verifier, Recommendation Writer) with 2D quadrant evaluation, discrepancy extraction, and source citation engine. |

---

## 3. Two-Dimensional Quadrant

HireTrace's signature differentiator is keeping **Role Fit** and **Evidence Consistency** strictly separate:

```
                    EVIDENCE CONSISTENCY
                 LOW                 HIGH
HIGH FIT   ┌───────────────┬───────────────┐
           │ REVIEW        │ STRONG MATCH  │
           │ REQUIRED      │               │
           ├───────────────┼───────────────┤
LOW FIT    │ INSUFFICIENT  │ WEAK MATCH    │
           │ EVIDENCE      │               │
           └───────────────┴───────────────┘
```

- **Strong Match:** High Role Fit + High Consistency. (Candidate meets requirements and claims hold up across all independent sources).
- **Review Required:** High Role Fit + Low Consistency. (Candidate appears stellar on paper, but multi-source evidence contradicts claims. *e.g., Alexander Sterling centerpiece case*).
- **Weak Match:** Low Role Fit + High Consistency. (Candidate lacks required experience, but is completely honest across all documents).
- **Insufficient Evidence:** Low Role Fit + Low Consistency. (Minimal evidence provided, or severe contradictions across core criteria).

---

## 4. Multi-Agent Architecture (7-Step Concurrent Pipeline)

```
                                JD + Target Profile
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │ (Step 1 - Concurrent CPU)     │ (Step 2 - Concurrent CPU)     │ (Step 3 - Concurrent LLM)
        ▼                               ▼                               ▼
   RubricScorer                 EvidenceRetriever           RequirementMappingAgent
   (Deterministic CV profile,   (Offline FAISS index build, (Local Ollama qwen2.5:3b
    normalized score out of      semantic span chunking,     with SQLite persistence
    100, zero LLM dependency)   model2vec/MiniLM backend)   and requisition hoisting)
        │                               │                               │
        └───────────────────────────────┼───────────────────────────────┘
                                        ▼
                       Step 4: EvidenceAggregationAgent
                       (Correlates requirements with indexed spans & rubric baseline)
                                        │
                                        ▼
                  Step 5: CrossSourceVerificationAgent (Ollama)
                  → Cross-checks claims across CV, interview notes, and code assessment
                  → Emits per-claim status: SUPPORTED / CONTRADICTED / INSUFFICIENT
                  → Multi-turn self-consistency voting and confidence calibration
                                        │
                                        ▼
                  Step 6: RecommendationWriterAgent (Ollama)
                  → Synthesizes 2D Quadrant verdict: Role Fit vs Evidence Consistency
                  → Generates priority cross-examination questions for human interviewer
                                        │
                                        ▼
                        Step 7: ClaimCriticAgent (Ollama)
                  → Audits drafted assertions with strict verbatim quote containment
                  → Flags ungrounded claims and downgrades them to synthesized inferences
                                        │
                                        ▼
                           Candidate Assessment Report
                           - Role Fit Score (0–100) & Evidence Consistency (0–100)
                           - 2D Quadrant Placement (Strong Match, Review Required, etc.)
                           - Verbatim Evidence Citations with Exact Quote Offsets
                           - Contradiction Table & Planted Discrepancy Alerts
                           - Priority Questions for the Human Reviewer
```

### V2 Latency & Architecture Upgrades
1. **Concurrent Pipeline Execution (Steps 1–3 Parallelized):** Step 1 (RubricScorer), Step 2 (FAISS index generation), and Step 3 (Requirement Mapping) execute simultaneously via `concurrent.futures.ThreadPoolExecutor(max_workers=3)`, hiding vector indexing and rubric compute completely behind the initial LLM call.
2. **Persistent SQLite Job Requirement Cache:** Requirements are a pure function of `(jd_text, target_role)`. The mapper checks a persistent SQLite database (`requirement_cache`) with model and prompt-SHA invalidation. In bulk candidate processing (`run_bulk`), requirements are resolved once per requisition, eliminating up to 49 redundant LLM calls per 50 candidates.
3. **Ollama Residency & Startup Warmup:** Pinned `keep_alive: 30m` prevents model unloading between evaluations, while a background warmup pass on FastAPI startup eliminates the 5–10s cold-load delay on the first user request.
4. **Static-First Prompt Ordering for KV-Cache Reuse:** Prompt templates position static system instructions, schemas, and JDs first, maximizing llama.cpp KV-cache hit rates during candidate evaluation runs.
5. **Layout-Aware Parsing Backend (`Docling`):** Optional `PARSER_BACKEND=docling` recovers two-column resume reading order and table structure with seamless fallback to PyMuPDF.
6. **Fast Distilled Embeddings (`model2vec`):** Optional `EMBEDDING_BACKEND=static` provides ~100x faster CPU embedding lookups via static token distillation tables.

---

## 5. Baselines

- **Baseline A (Deterministic, No LLM):** Clean rewrite of CareerCheck rubric run on the parsed CV alone (`/baseline/rubric_scorer.py`). Raw score out of 120, normalized to 0–100. Serves as one input signal to the aggregator, not ground truth.
- **Baseline B (Naive LLM, No Tools):** Single Ollama prompt with all raw candidate documents concatenated (`/baseline/naive_llm.py`), asking for candidate evaluation. Uses the exact same local model (`qwen2.5:3b`) to isolate the impact of architecture from model quality. While it can produce apparently grounded individual claims, it lacks the cross-source verification machinery needed to reliably detect contradictions.
- **HireTrace Agent:** The full 4-agent pipeline with FAISS retrieval and cross-source verification.

---

## 6. Evaluation Dataset & Metrics (15 Synthetic Cases)

Located under [`eval_cases/`](eval_cases/):
- **8 Normal Cases:** Ranging from weak to medium to strong fit for a Senior Python & Distributed Systems Engineer role (`case_01` to `case_08`).
- **4 Planted Contradiction Cases (Task A):**
  1. `case_09`: CV vs. Interview (Tenure length: CV claims 3 years, interview states ~18 months).
  2. `case_10`: CV vs. Assessment (Skill claim: claims Kafka/Async expert, assessment reveals fatal deadlock failures).
  3. `case_11`: Interview vs. Assessment (Claims deep concurrency debugging, assessment reveals deadlocks).
  4. `case_15` (Deceptive Centerpiece): Multi-source contradiction on project leadership vs team contributor role.
- **3 Incomplete / Missing Evidence Cases (Task B):**
  1. `case_12`: Incomplete Evidence / Missing JD Requirement (Truthfully states relational background; lacks required Kafka experience demanded by JD).
  2. `case_13`: Missing interview notes.
  3. `case_14`: Missing technical assessment report.
- **1 Deceptive Centerpiece Case (`case_15_deceptive_centerpiece`):**
  - Alexander Sterling: Scores 62.5/120 on rubric, 250 GitHub stars, impressive CV. But hides critical multi-source contradictions:
    - CV: *"Led migration of legacy monolithic core to Apache Kafka for a 7-person team."*
    - Interview: Joined ~18 months ago, learned Kafka on the job.
    - Project Architecture RFC: Proves he was a contributing member of a 7-engineer team led by Principal Architect Dr. Robert Vance (contradicts "Led").
- **Live Demo / Ephemeral Intake Artifacts:**
  - Any files prefixed with `custom_*` in `eval_cases/` or `trajectories/` are ephemeral demo artifacts generated dynamically when reviewers use the **"+ Add Candidate"** live intake modal in the web UI or during integration testing (`tests/test_candidate_ingestion.py`). The canonical scientific benchmark comprises solely the 15 standardized cases (`case_01` through `case_15`).

### Benchmark Results (Empirically Measured across 15 Ground-Truth Cases)

| Metric | Baseline A (Resume Rubric) | Baseline B (Naive LLM) | HireTrace Agent (Full Architecture) | Scientific Impact |
|---|---|---|---|---|
| **1. Spearman Rank Correlation (ρ)** | 0.579 `[0.119, 0.898]` | 0.862 `[0.645, 0.950]` | **0.816** `[0.446, 0.983]` | Strong rank agreement with senior reviewer consensus under local open-weights (`qwen2.5:3b`) |
| **2. Contradiction Detection Recall (Task A)** | 0.0% (N/A) | 100.0% (4/4) | **100.0% (4/4)** | HireTrace detects 100% of planted cross-source contradictions |
| **3. Contradiction Precision / FPR (Task A)** | N/A | 30.8% Precision (**81.8% FPR**) | **100.0% Precision (0.0% FPR)** | Baseline B triggers 9 false alarms on clean controls; HireTrace has **0 false alarms** |
| **4. Contradiction F1 Score** | 0.000 | 0.471 | **1.000** | Perfect harmonic balance between precision and recall |
| **5. Evidence Sufficiency Recall (Task B)** | N/A | N/A | **100.0% (3/3)** | Identifies incomplete dossiers without confusing missing data for factual conflict |
| **6. Claim Grounding & Quote Fidelity** | N/A | 88.9% Grounding (32/36), 79.1% Quotes | **66.7% Grounding (54/81), 100.0% Quotes** | 100% citation validity & quote containment (0% hallucinations); see Granularity Note below |
| **7. Estimated Reviewer Time** | 18.0 min (manual) | 12.5 min | **3.5 min** | **+80.6% estimated time saved** (Standardized cognitive load model: 2,200 words @ 220 wpm + reconciliation) |
| **8. Pipeline Median Latency (p50)** | ~40s+ (cold load) | ~35s | **26.25s** | Concurrency (Steps 1–3 parallel) + warm model cache drops wall-clock evaluation time |

*Note on Grounding Rate (66.7% vs 88.9%) & Quote Fidelity: HireTrace emits over 2.25× more atomic claims than Baseline B (81 claims vs 36), resulting in 54 verified grounded claims compared to Baseline B's 32. Baseline B outputs coarse, un-cited paragraphs that superficially match broad resume terms, but fabricates quotes 20.9% of the time (79.1% containment). HireTrace breaks evaluation down into granular per-competency claims; when the Recommendation Writer synthesizes holistic cross-source conclusions, claims lacking an exact 1:1 single-span quote are conservatively flagged as ungrounded by the automated evaluator. Crucially, 100.0% of citations emitted by HireTrace reference valid document span IDs (100% validity) and 100.0% of extracted quotes match source text verbatim (100% containment) — completely eliminating fabricated evidence.*

*Execution Mode: Baseline B and HireTrace Agent ran on the exact same local open-weights model (`qwen2.5:3b`) via local Ollama with zero paid APIs (`execution_mode: "local_ollama_open_weights"`, 79/79 successful LLM calls, 0 fallbacks).*

### Structured CV Extraction Benchmark (`LongExtractBench`)
Deterministic scoring of local schema-constrained CV extraction against hand-labeled ground-truth records across 16 documents:
- **Completion Rate:** **100.0%** (16/16 documents successfully parsed without schema failures)
- **Matched Leaf Accuracy:** **84.8%** (exceeds strict &ge; 80.0% benchmark standard for job titles, dates, employers, degrees)
- **Array Row Precision / Recall:** **73.1% precision / 79.7% recall**
- **Zero Paid Cost:** 100% local extraction using `qwen2.5:3b` with layout-aware `Docling` fallback recovery.

---

## 7. Governance, EEOC Defensibility & Human-in-the-Loop Contract

HireTrace is built from the ground up to prevent the civil rights and compliance risks inherent in autonomous hiring algorithms:

1. **Zero-Autonomy Design (HITL Mandatory):**
   - **Autonomous Hire Verdicts:** **Strictly Prohibited** (`autonomous_hire_verdict_permitted: False`).
   - **Human-in-the-Loop:** **Mandatory Gate** (`human_in_the_loop_mandatory: True`).
   - **Recommendation Contract:** *"Proceed to human review with priority questions"*. The system acts strictly as an evidence retrieval, audit, and cross-examination tool to empower human decision-makers, never substituting for human judgment.

2. **Algorithmic Fairness & EEOC Four-Fifths Compliance:**
   - Evaluated under EEOC Uniform Guidelines on Employee Selection Procedures (4 CFR Part 60) across 44 counterfactual demographic mutations spanning 11 protected classes.
   - **Mean Role Fit Score Drift:** **0.00 pts**
   - **Mean Consistency Score Drift:** **0.00 pts**
   - **Minimum Disparate Impact Ratio (DIR):** **1.0000** (far exceeding the 0.8000 EEOC threshold)
   - **Quadrant Stability:** **100.0% Invariant** across demographic mutations.

3. **Zero-Hallucination & Anti-Fabrication Guarantee:**
   - **Citation Validity Rate:** **100.0%** (every citation maps directly to a valid candidate document span ID).
   - **Exact Quote Containment:** **100.0%** (every quote attributed to candidate materials matches source text verbatim).
   - **Adversarial Red-Teaming:** **100% Defense Rate** across 8 attack vectors (prompt injection, delimiter escaping, conversational interview jailbreaks, JSON schema smuggling, tenure fabrication, and seniority usurpation).

4. **Air-Gapped Confidentiality ($0.00 External Cost):**
   - Resumes, interview transcripts, and evaluation scores never leave the self-hosted environment. Zero telemetry or inference is routed to third-party proprietary APIs.

---

## 8. Component Ablation on the 15-case benchmark

| Variant | Source-Isolated Retrieval | Multi-Agent Decomposition | Normalized Comparator | Spearman ρ | Contradiction Recall | Grounding Rate |
|---|---|---|---|---|---|---|
| **A (Deterministic Resume-Rubric)** | ❌ | ❌ | ❌ | 0.579 | 0% | 0% |
| **B (Retrieval-Augmented LLM)** | ✅ | ❌ | ❌ | 0.699 | 25% | 76% |
| **C (Multi-Agent Decomposition)** | ✅ | ✅ | ❌ | 0.712 | 25% | 61% |
| **D (Full HireTrace Architecture)** | ✅ | ✅ | ✅ | **0.816** | **100%** | **67%** |

---

## 9. Clean Reproduction Guide ($0 Cost, 100% Offline)

### Step 1: Install and Launch Ollama
1. Download Ollama from [ollama.com](https://ollama.com).
2. Pull the target model (verified on RTX 3050 Laptop / 4GB VRAM):
   ```bash
   ollama pull qwen2.5:3b
   # Or for ultra-low VRAM / high speed:
   ollama pull qwen2.5:1.5b
   ```
3. Start Ollama:
   ```bash
   ollama serve
   ```

### Step 2: Environment Setup
```bash
# Extract the submission zip archive and navigate into the folder:
cd micro1  # (or your extracted folder name)
cp .env.example .env            # On Windows: copy .env.example .env
pip install -r requirements.txt  # faiss-cpu, scipy, numpy, pytest, requests
```

### Step 3: Run Baselines, Tests, and Evaluations
- **Run Baseline A Tests:**
  ```bash
  pytest tests/test_rubric_scorer.py -v
  ```
- **Run Centerpiece Case Pipeline Test:**
  ```bash
  pytest tests/test_centerpiece_case.py -s
  ```
- **Run Full 15-Case Evaluation Matrix:**
  ```bash
  python -m eval.run_eval
  ```
- **Launch Interactive Web Dashboard:**
  ```bash
  python -m ui.server 8080
  ```
  Open `http://127.0.0.1:8080` in your browser to inspect the 2D Quadrant and candidate reports.

---

## 10. Hot Take

> **"Verification can establish consistency, not truth."**  
> If a candidate's CV, interview transcript, and assessment report all state that they architected a distributed system, the evidence is **internally consistent across recorded documents** — it is not automatically true in the physical world.
>
> An automated system can flag disagreements and unverified assertions with exceptional precision; it cannot confirm absolute truth on its own. This is why autonomous hire/no-hire AI tools are dangerous and fundamentally flawed. HireTrace never makes a hiring decision: it surfaces discrepancies, separates Role Fit from Evidence Consistency, and routes every candidate to a qualified human reviewer armed with the exact questions that need asking.

---

## 11. License

HireTrace is open-source software licensed under the [MIT License](LICENSE). You are free to inspect, adapt, fork, and build upon this codebase.
