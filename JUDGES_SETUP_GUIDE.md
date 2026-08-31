# HireTrace — Judges & Quickstart Reproduction Guide
> **Fast-track verification guide for hackathon judges and evaluators starting from scratch.**

---

## ⚡ Executive Summary (Choose Your Path)

| Path | Time to Run | Requirements | What It Validates |
|---|---|---|---|
| **Path A: Instant Inspection** *(Recommended)* | **< 60 seconds** | Python 3.10+, pip | Interactive UI dashboard, pre-computed 15-case benchmarks, test suites, and discrepancy visualizations without downloading any LLM weights. |
| **Path B: Full Live Pipeline** | **~5 minutes** | Python 3.10+, pip, [Ollama](https://ollama.com) | End-to-end multi-agent execution from raw text to FAISS retrieval, verification agent reasoning, and report generation via local open weights (`qwen2.5:3b`). |

---

## 🛠️ Prerequisites (For a Fresh Machine)

### 1. Python
Ensure Python 3.10, 3.11, or 3.12 is installed:
```bash
python --version
```
*(If not installed, download from [python.org](https://www.python.org/downloads/)).*

### 2. Extract Submission Archive
Extract the submitted zip archive and open your terminal in the root of the extracted folder:
```bash
cd micro1  # (or your extracted directory name)
```

### 3. (Recommended) Create a Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies ($0 Cost, Lightweight)
```bash
pip install -r requirements.txt
```
*Dependencies: `faiss-cpu`, `numpy`, `scipy`, `pytest`, `requests` (no heavyweight frameworks or paid APIs).*

---

## 🚀 Path A: Instant 60-Second Evaluation (No Model Download)

The repository includes **pre-computed, validated execution trajectories** in [`trajectories/`](trajectories/) for all 15 benchmark cases (including the centerpiece deceptive case `Alexander Sterling`).

### Step 1: Launch the Interactive Dashboard
```bash
python -m ui.server 8080
```
Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)** in your browser.

**What to inspect in the UI:**
1. **2D Quadrant Matrix:** Observe that *Role Fit* and *Evidence Consistency* are strictly decoupled.
2. **Deceptive Centerpiece (`Alexander Sterling`):** Click on candidate #15. Notice how high paper pedigree is placed in **"REVIEW REQUIRED"** because multi-source verification caught the Kafka tenure and leadership contradictions.
3. **Evidence Citations:** View atomic claims with exact quote verification and document span links.
4. **Interactive Ingestion:** Click **"+ Add Candidate"** to paste custom text or evaluate a new candidate dossier live.

### Step 2: Run Verification Test Suites
In a new terminal window:
```bash
# Run all automated tests
pytest -v

# Test deterministic CV rubric scorer (Baseline A)
pytest tests/test_rubric_scorer.py -v

# Test centerpiece case verification & trajectory integrity
pytest tests/test_centerpiece_case.py -s

# Test candidate ingestion API & dynamic evaluation
pytest tests/test_candidate_ingestion.py -v
```

---

## 🧠 Path B: Full End-to-End Live LLM Pipeline (Offline with Ollama)

If you wish to test live open-weights multi-agent generation without relying on cached trajectories:

### Step 1: Install Ollama
Download and install Ollama from **[ollama.com](https://ollama.com)** (available for Windows, macOS, and Linux).

### Step 2: Pull the Open-Weights Model
```bash
# Standard model (verified on laptop GPUs & 4GB VRAM):
ollama pull qwen2.5:3b

# Or ultra-lightweight option (for low RAM / CPU only):
ollama pull qwen2.5:1.5b
```

### Step 3: Start the Ollama Engine
In a dedicated terminal:
```bash
ollama serve
```

### Step 4: Configure Environment
Copy the example environment configuration:
```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

### Step 5: Run the Full 15-Case Benchmark Evaluation
```bash
python -m eval.run_eval
```
This script runs the entire scientific benchmark comparing:
- **Baseline A:** Deterministic Resume-Rubric Scorer
- **Baseline B:** Naive Concatenated LLM
- **HireTrace:** 4-Agent Pipeline with FAISS semantic retrieval & cross-source verification

The results will generate/update [`eval/eval_report.md`](eval/eval_report.md) and [`eval/eval_results.json`](eval/eval_results.json).

---

## 📋 Hackathon Deliverables Index for Evaluators

| Deliverable | Location | Description |
|---|---|---|
| **Solution Video Walkthrough** | [Watch 4m 30s Demo on Google Drive](https://drive.google.com/file/d/1ajwkjejxtr26-_YHMBBoYHxyitFg6k7d/view?usp=drive_link) | 4m 30s 1080p demo walkthrough ([script](docs/solution_video_script.md)). |
| **Deliverable #1: Improvement Changelog** | [`CHANGELOG.md`](CHANGELOG.md) | Granular chronological record of architectural evolutions and fixes. |
| **Deliverable #2: Architecture & Problem Framing** | [`README.md`](README.md) §1–§5 | Problem bottleneck, 2D quadrant philosophy, and multi-agent pipeline design. |
| **Deliverable #3: Benchmark & Empirical Report** | [`eval/eval_report.md`](eval/eval_report.md) & [`METHODOLOGY.md`](METHODOLOGY.md) | Formal ground truth consensus, 15 synthetic cases, Spearman ρ, Contradiction Recall/Precision. |
| **Deliverable #4: Agent Execution Trajectories** | [`trajectories/`](trajectories/) | Step-by-step LLM reasoning traces, tool inputs/outputs, and [`agent_trajectories_breakdown.md`](trajectories/agent_trajectories_breakdown.md). |
| **Interactive UI Dashboard** | `python -m ui.server 8080` | Live web dashboard with 2D quadrant visualization & dynamic candidate intake. |

---

## ❓ Troubleshooting & FAQs

- **Port 8080 already in use?**  
  Run on a different port:  
  `python -m ui.server 8088` (then visit `http://127.0.0.1:8088`).

- **PowerShell Script Execution Error?**  
  If virtual environment activation says scripts are disabled:  
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

- **Does HireTrace use any paid APIs?**  
  **No.** HireTrace is 100% offline, privacy-preserving, and runs at **$0.00 cost** using local embeddings, FAISS, and local open-weights Ollama inference.
