# HireTrace Horizontal Scaling & Sizing Guide (`SCALING.md`)

This guide outlines production sizing formulas, horizontal scaling dimensions, bottleneck identification, and operational monitoring for HireTrace deployments running across multi-container and multi-GPU topologies.

---

## 1. System Topology Overview

HireTrace decomposes candidate evaluation into an asynchronous, horizontally scalable architecture:

```
                      [ Load Balancer (Nginx / ALB) ]
                                    │
            ┌───────────────────────┴───────────────────────┐
            ▼                                               ▼
   [ Web API Replica 1 ]                           [ Web API Replica 2 ]
   (Stateless FastAPI/ASGI)                        (Stateless FastAPI/ASGI)
            │                                               │
            ├───────────────────────┬───────────────────────┤
            ▼                       ▼                       ▼
    [ Redis Job Broker ]    [ PostgreSQL DB ]     [ S3 / Shared Storage ]
            │              (Single Source Truth)    (Dossiers & Vectors)
    ┌───────┴───────┐
    ▼               ▼
[ Worker 1 ]   [ Worker 2 ]
(Celery/RQ)    (Celery/RQ)
    │               │
    └───────┬───────┘
            ▼
[ Multi-Endpoint LLM Inference Pool ]
├── Ollama/vLLM Replica 1 (GPU Node 0:11434)
└── Ollama/vLLM Replica 2 (GPU Node 1:11434)
```

---

## 2. Horizontal Scaling Dimensions

HireTrace provides three independent scaling knobs:

| Knob | Component | Scale Trigger | Primary Constraint |
|---|---|---|---|
| **$W$ (Web Tier)** | `ui/server.py` | High HTTP request rates, candidate dossier intake | CPU / Network I/O |
| **$K$ (Worker Tier)** | `worker.py` (Celery) | Growing queue depth (`hiretrace_queue_depth > 5`) | Memory / Redis connection count |
| **$M$ (LLM Tier)** | Ollama / vLLM replicas | High pipeline job duration / GPU saturation | GPU VRAM / Inference compute |

---

## 3. Sizing Rules of Thumb & Formulas

### Formula 1: LLM Inference Capacity
Total sustainable concurrent inferences across the cluster:
$$\text{Capacity}_{\text{LLM}} = \sum_{i=1}^{M} (\text{Safe Concurrency}_i)$$

*Rule of thumb:* For local GPU inference with `qwen2.5:3b` or `7b`, set `CONCURRENCY_PER_ENDPOINT=1` (or 2 if using high-end 24GB GPUs with KV cache headroom). 
With $M=4$ Ollama instances, $\text{Capacity}_{\text{LLM}} = 4 \times 1 = 4$ concurrent agent calls.

### Formula 2: Worker Tier Sizing ($K$)
Workers run the 4-agent evaluation pipeline. Because workers spend ~75% of job time awaiting LLM generation and 25% on vector retrieval / rubric scoring:
$$K = \min\left(\lceil \text{Peak Ingestion Rate (cands/min)} \times \frac{\text{Duration}_{\text{avg}} (\text{min})}{1} \rceil, \; 1.5 \times \text{Capacity}_{\text{LLM}}\right)$$

*Example:*
- Average evaluation time per candidate: 24 seconds (0.4 minutes).
- Peak intake: 10 candidates/minute.
- Target workers: $10 \times 0.4 = 4$ workers.
- Supported by $M=3$ Ollama endpoints ($\text{Capacity} = 3 \times 1 = 3$).

### Model Sizing & VRAM Requirements Table

| Model | Quantization | Min GPU VRAM | Recommended GPUs | Batch Ingest Latency / Cand |
|---|---|---|---|---|
| **Qwen 2.5 3B** | Q4_K_M | 2.2 GB | 1x RTX 3050 (4GB) or CPU | ~18s |
| **Qwen 2.5 7B** | Q4_K_M | 4.8 GB | 1x RTX 3060 / 4060 (8GB) | ~34s |
| **Llama 3.1 8B** | Q4_K_M | 5.4 GB | 1x RTX 3090 / 4090 (24GB) | ~42s |
| **Qwen 2.5 14B** | Q4_K_M | 9.2 GB | 2x RTX 4090 or A100 | ~65s |

---

## 4. What to Scale First Under Load?

When traffic spikes, follow this prioritized triage:

1. **First: Scale the LLM Pool ($M$)**
   - Symptom: `hiretrace_agent_duration_seconds` increases while CPU usage on workers remains low.
   - Action: Spin up additional Ollama/vLLM containers on available GPU nodes and append their URLs to `OLLAMA_BASE_URLS="http://gpu1:11434,http://gpu2:11434"`.
   - Result: HireTrace automatically activates least-connections routing and scales the semaphore dynamically.

2. **Second: Scale Workers ($K$)**
   - Symptom: `hiretrace_queue_depth` is growing, but existing workers report normal step execution times.
   - Action: Increase Celery worker replicas:
     ```bash
     docker compose -f docker-compose.prod.yml up -d --scale worker=4
     ```

3. **Third: Scale Web API Replicas ($W$)**
   - Symptom: HTTP response latency on `/api/candidate/new` or `/api/cases` degrades.
   - Action: Increase web instances behind your reverse proxy:
     ```bash
     docker compose -f docker-compose.prod.yml up -d --scale web=3
     ```

---

## 5. Metrics to Watch & Prometheus Queries

All metrics are exposed at `/metrics` (Phase 7):

| Alert / Metric | PromQL Expression | Threshold / SRE Trigger |
|---|---|---|
| **High Queue Backlog** | `hiretrace_queue_depth{status="queued"} > 10` | Scale worker tier ($K$) |
| **LLM Circuit Tripped** | `hiretrace_llm_circuit_breaker_open == 1` | GPU node down / Ollama crashed |
| **Degraded Pipeline Rate** | `rate(hiretrace_llm_calls_total{status="fallback"}[5m]) > 0` | LLM cluster saturated / failing |
| **Pipeline Failure Spike** | `rate(hiretrace_jobs_total{status="failed"}[5m]) > 0.05` | Investigate unhandled parsing exceptions |
| **p95 Evaluation Latency** | `histogram_quantile(0.95, sum(rate(hiretrace_agent_duration_seconds_bucket[5m])) by (le))` | Exceeds SLA (e.g. > 90s) |

---

## 6. High-Availability & Disaster Recovery

1. **Zero Data Loss on Deployments:**
   - Celery tasks use `acks_late=True` and `task_reject_on_worker_lost=True`.
   - If a worker container crashes or is preempted mid-evaluation, the message remains unacknowledged in Redis and is automatically reassigned to an active worker.
2. **Database Resilience:**
   - PostgreSQL schema changes are version-controlled via Alembic (`alembic upgrade head`).
   - SQLite fallback retains atomic thread-safe WAL journaling for single-node deployments.
3. **Storage Durability:**
   - Persistent volume mounts (`hiretrace_uploads`, `hiretrace_trajectories`) or S3 storage guarantee dossiers and vector indices survive container teardowns.
