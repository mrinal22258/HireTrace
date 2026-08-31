# HireTrace Evaluation Methodology & Benchmark Protocol

This document defines the formal ground-truth methodology, expert consensus protocol, and evaluation criteria for the HireTrace benchmark.

---

## 1. Ground-Truth Dataset Design

The benchmark consists of **15 fully articulated candidate dossiers** evaluated against a unified, fixed production Job Description:
- **Role:** Senior Python & Distributed Systems Engineer
- **Company:** CloudMesh Infrastructure
- **Scale:** 45M events/hour, 25k req/sec, sub-80ms p99 latency SLA
- **Stack:** Python 3.11/AsyncIO, Apache Kafka, Redis Streams, PostgreSQL sharding, KEDA/Kubernetes

### Candidate Distribution
| Cohort | Count | Case IDs | Ground Truth Characteristics |
|---|---|---|---|
| **Normal Strong** | 2 | `case_01`, `case_02` | Consistent cross-source evidence, proven high-scale architecture, high open-source & operational tenure. |
| **Normal Medium** | 3 | `case_03`, `case_04`, `case_05` | Consistent cross-source evidence, solid mid/senior engineering, moderate scale or minor gaps in niche areas. |
| **Normal Weak** | 3 | `case_06`, `case_07`, `case_08` | Consistent evidence, junior/mid experience, low production scale, lacking distributed systems tenure. |
| **Planted Contradictions (Task A)** | 4 | `case_09`, `case_10`, `case_11`, `case_15` | Planted factual contradictions across document pairs: tenure mismatch, skill mastery vs assessment failure, interview confidence vs assessment concurrency deadlock, and team role leadership vs contributor misrepresentation. |
| **Incomplete / Missing Evidence (Task B)** | 3 | `case_12`, `case_13`, `case_14` | Partial dossiers / missing requirements (case 12 missing required Kafka skill, case 13 missing interview notes, case 14 missing coding assessment) to test uncertainty handling without raising false contradiction alarms. |
| **Deceptive Centerpiece** | 1 | `case_15` | **Alexander Sterling:** Flawless on-paper CV claiming Kafka leadership and 3.5 years tenure, but project architecture doc reveals secondary contributor role and interview reveals ~18 months tenure. Included in Task A planted contradictions. |

---

## 2. Expert-Authored Reference Ground Truth & Scoring Protocol

To establish a gold-standard ranking independent of model bias, reference scores were constructed using an expert-authored rubric representing senior engineering consensus:

### Reference Evaluation Archetypes
Ground-truth scores are constructed to model the calibrated assessments of three distinct senior technical roles:
- **Reviewer Archetype 1 (Principal Systems Architect):** Focuses on distributed state, concurrency, AsyncIO correctness, and RFC authorship.
- **Reviewer Archetype 2 (Engineering Hiring Director):** Focuses on overall role fit balance, team leadership scope, and employment tenure integrity.
- **Reviewer Archetype 3 (Staff Reliability Engineer):** Focuses on operational maturity, incident management, telemetry, and assessment rigor.

### Reference Score & Rank Formation
1. Each synthetic candidate dossier contains expert-authored reference scores (`reviewer_1`, `reviewer_2`, `reviewer_3`) stored in `eval_cases/dataset.py`.
2. The arithmetic mean of these scores forms the `expert_composite_score`.
3. Ground-truth ranks are derived dynamically from composite scores using `scipy.stats.rankdata([-score], method="average")` to handle ties impartially.
4. **Treatment of Deceptive Profiles:** Candidates with planted cross-source factual misrepresentations (e.g., Alexander Sterling) receive low consistency scores, placing their composite reference rank in the bottom quartile (Ranks 12–15) despite strong on-paper CV credentials.

---

## 3. Metrics Definition

### A. Spearman Rank Correlation ($\rho$)
Measures the monotonic ranking alignment between a system's candidate ranking and the expert consensus ranking:
$$\rho = 1 - \frac{6 \sum d_i^2}{n(n^2 - 1)}$$
- **Uncertainty Quantification:** 95% Confidence Intervals are calculated using **1,000 bootstrap resamples** with replacement across the evaluation dataset.

### B. Task A: Contradiction Detection Rigor
Evaluated strictly against planted contradiction cases (4 Positives: Cases 09, 10, 11, 15) and clean negative control cases (11 Negatives: Cases 01–08, 12, 13, 14):
- **True Positive (TP):** System detects a discrepancy matching the planted contradiction topic and document source pair.
- **False Positive (FP):** System flags a contradiction on a clean, consistent candidate where evidence agrees.
- **False Negative (FN):** System fails to detect a planted contradiction.
- **True Negative (TN):** System correctly reports no contradiction on a clean candidate.
- **Metrics Reported:** Recall $\left(\frac{\text{TP}}{\text{TP} + \text{FN}}\right)$, Precision $\left(\frac{\text{TP}}{\text{TP} + \text{FP}}\right)$, F1 Score, and False Positive Rate $\left(\frac{\text{FP}}{\text{FP} + \text{TN}}\right)$.

### C. Task B: Evidence Sufficiency Handling
- Evaluates whether systems distinguish between factual conflict and missing evidence.
- Tested on incomplete cases (Cases 12, 13, 14) requiring `INSUFFICIENT_EVIDENCE` status rather than a spurious contradiction flag.

### D. Citation-Grounded Claim Rate
- **Citation-Grounded Claim Rate:** Percentage of generated claims that are substantiated by valid cited evidence spans, entity presence, polarity consistency, and semantic alignment. Evaluates whether model claims reliably trace back to cited dossier evidence rather than asserting ungrounded hallucinations.
- **Citation Span Validity:** Percentage of cited span IDs (e.g., `CV-002`, `INT-004`) that map directly to genuine, extant evidence spans in the candidate dossier.
- **Exact Quote Containment:** Percentage of extracted quote text verified via normalized substring containment (`normalize(quote) in normalize(span.text)`) inside the raw text of the cited evidence span.

---

## 4. Hardware & Environmental Reproducibility

- **LLM Engine:** Local Ollama (`qwen2.5:3b`) running at `http://127.0.0.1:11434`. All inference and retrieval run locally after the model is provisioned; no paid external AI APIs are required.
- **Vector Retrieval:** Deterministic hashed lexical/n-gram projection + local `faiss-cpu`.
- **Operating System:** Tested on Windows 11 / Linux x86_64.
- **External API Calls:** Exactly 0. Total Cost: $0.00.
