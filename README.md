# HireTrace — Evidence-First Candidate Assessment Agent
> **"Every recommendation traces back to evidence."**  
> *micro1 Agentic Workflows Hackathon Submission*

> **Submission Deliverables Quick-Index:**
> - **Judges & Fresh Setup Guide:** [`JUDGES_SETUP_GUIDE.md`](JUDGES_SETUP_GUIDE.md) *(<60s Instant Inspection vs. Full Live LLM Pipeline)*
> - **Solution Video Walkthrough:** [Watch 4m 30s Demo on Google Drive](https://drive.google.com/file/d/1ajwkjejxtr26-_YHMBBoYHxyitFg6k7d/view?usp=drive_link) *(script in [`docs/solution_video_script.md`](docs/solution_video_script.md))*
> - **Deliverable #1 (Improvement Changelog):** [`CHANGELOG.md`](CHANGELOG.md)
> - **Deliverable #2 (Architecture & Problem Framing):** §1–§5 below
> - **Deliverable #3 (Evaluation Harness & Empirical Report):** §6–§7 below & [`eval/eval_report.md`](eval/eval_report.md)
> - **Deliverable #4 (Agent Execution Trajectories):** [`trajectories/`](trajectories/) & [`trajectories/agent_trajectories_breakdown.md`](trajectories/agent_trajectories_breakdown.md)

---

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

## 4. Architecture

```
                        JD + Target Profile
                                │
                                ▼
                    Requirement Mapping Agent (Ollama)
                    → REQ-01 Python: evidence in {CV, interview, assessment}
                    → REQ-02 Distributed systems: evidence in {project, interview}
                    → REQ-03 Leadership: evidence in {interview}
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                        │
   Evidence Loader      Retrieval Layer (FAISS,     Deterministic
   CV / interview        AegisRAG-Engine pattern:    Rubric Scorer
   / assessment          chunk + match JD reqs        (clean rewrite
   parsing               to evidence spans            of CareerCheck
   (ResumeExtractBench                                 weights, NO LLM)
   pattern)
        │                       │                        │
        └───────────────────────┼────────────────────────┘
                                ▼
                    Evidence Aggregation Layer (FAISS + Rubric, No LLM)
                                │
                                ▼
                  Cross-Source Verification Agent (Ollama)
                  → per claim: SUPPORTED / CONTRADICTED / INSUFFICIENT EVIDENCE
                  → confidence score per claim
                                │
                                ▼
                          Evidence Matrix
                    (requirement × source × status × confidence)
                                │
                                ▼
                  Recommendation Writer Agent (Ollama)
                                │
                                ▼
                     Candidate Assessment Report
                     - Role fit score
                     - Evidence consistency score  (kept SEPARATE from fit)
                     - Per-requirement status table
                     - Key discrepancies with source citations
                     - Unsupported-claim count
                     - Priority questions for the human reviewer
```

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
| **1. Spearman Rank Correlation (ρ)** | 0.579 `[0.119, 0.898]` | 0.862 `[0.645, 0.950]` | **0.813** `[0.455, 0.978]` | Solid rank correlation under local open-weights inference (`qwen2.5:3b`) |
| **2. Contradiction Detection Recall (Task A)** | 0.0% (N/A) | 100.0% (4/4) | **100.0% (4/4)** | HireTrace detects 100% of planted cross-source contradictions |
| **3. Contradiction Precision / FPR (Task A)** | N/A | 30.8% Precision (**81.8% FPR**) | **100.0% Precision (0.0% FPR)** | Baseline B triggers 9 false alarms on clean controls; HireTrace has **0 false alarms** |
| **4. Contradiction F1 Score** | 0.000 | 0.471 | **1.000** | Perfect harmonic balance between precision and recall |
| **5. Evidence Sufficiency Recall (Task B)** | N/A | N/A | **100.0% (3/3)** | Identifies incomplete dossiers without confusing missing data for factual conflict |
| **6. Claim Grounding & Quote Fidelity** | N/A | 88.9% Grounding (32/36), 79.1% Quotes | **66.7% Grounding (54/81), 100.0% Quotes** | 100% citation validity & quote containment (0% hallucinations); see Granularity Note below |
| **7. Estimated Reviewer Time** | 18.0 min (manual) | 12.5 min | **3.5 min** | **+80.6% estimated time saved** (Modeled estimate from standardized reading rate of 220 wpm across 2,200 words + reconciliation time; not an empirical clock study) |

*Note on Grounding Rate (66.7% vs 88.9%) & Quote Fidelity: HireTrace emits over 2.25× more atomic claims than Baseline B (81 claims vs 36), resulting in 54 verified grounded claims compared to Baseline B's 32. Baseline B outputs coarse, un-cited paragraphs that superficially match broad resume terms, but fabricates quotes 20.9% of the time (79.1% containment). HireTrace breaks evaluation down into granular per-competency claims; when the Recommendation Writer synthesizes holistic cross-source conclusions, claims lacking an exact 1:1 single-span quote are conservatively flagged as ungrounded by the automated evaluator. Crucially, 100.0% of citations emitted by HireTrace reference valid document span IDs (100% validity) and 100.0% of extracted quotes match source text verbatim (100% containment) — completely eliminating fabricated evidence.*

*Execution Mode: Baseline B and HireTrace Agent ran on the exact same local open-weights model (`qwen2.5:3b`) via local Ollama with zero paid APIs (`execution_mode: "local_ollama_open_weights"`, 79/79 successful LLM calls, 0 fallbacks).*

---

## 7. Component Ablation on the 15-case benchmark

| Variant | Source-Isolated Retrieval | Multi-Agent Decomposition | Normalized Comparator | Spearman ρ | Contradiction Recall | Grounding Rate |
|---|---|---|---|---|---|---|
| **A (Deterministic Resume-Rubric)** | ❌ | ❌ | ❌ | 0.579 | 0% | 0% |
| **B (Retrieval-Augmented LLM)** | ✅ | ❌ | ❌ | 0.699 | 25% | 76% |
| **C (Multi-Agent Decomposition)** | ✅ | ✅ | ❌ | 0.712 | 25% | 61% |
| **D (Full HireTrace Architecture)** | ✅ | ✅ | ✅ | **0.813** | **100%** | **67%** |

---

## 8. Clean Reproduction Guide ($0 Cost, 100% Offline)

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

## 9. Hot Take

> **"Verification can establish consistency, not truth."**  
> If a candidate's CV, interview transcript, and assessment report all state that they architected a distributed system, the evidence is **internally consistent across recorded documents** — it is not automatically true in the physical world.
>
> An automated system can flag disagreements and unverified assertions with exceptional precision; it cannot confirm absolute truth on its own. This is why autonomous hire/no-hire AI tools are dangerous and fundamentally flawed. HireTrace never makes a hiring decision: it surfaces discrepancies, separates Role Fit from Evidence Consistency, and routes every candidate to a qualified human reviewer armed with the exact questions that need asking.
