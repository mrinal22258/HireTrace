# HireTrace Observability & Metrics Architecture

HireTrace exports real-time system metrics, queue diagnostics, agent latency breakdowns, and LLM telemetry via a Prometheus-compatible endpoint (`/metrics`), accompanied by structured JSON event streams.

---

## 1. Prometheus Telemetry Endpoint: `/metrics`

Scraped by standard Prometheus collectors or OpenTelemetry Collector agents:
```http
GET /metrics
Accept: text/plain; version=0.0.4
```

### Metrics Catalog

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `hiretrace_queue_depth` | Gauge | None | Number of candidate assessment jobs currently queued or parsing |
| `hiretrace_jobs_total` | Counter | `status="queued|parsing|evaluating|done|failed"` | Cumulative background worker jobs processed |
| `hiretrace_pipeline_evaluations_total` | Counter | `outcome="completed|degraded"` | Cumulative end-to-end assessment pipelines executed |
| `hiretrace_agent_duration_seconds` | Summary | `agent="...", quantile="0.5|0.9|0.99"` | Execution latency for each of the 4 LLM pipeline agents & deterministic baseline |
| `hiretrace_agent_duration_seconds_sum` | Counter | `agent="..."` | Cumulative execution time spent in agent |
| `hiretrace_agent_duration_seconds_count` | Counter | `agent="..."` | Total invocation count per agent |
| `hiretrace_llm_calls_total` | Counter | `outcome="success|fallback"` | Total inference queries dispatched to Ollama/vLLM endpoints |
| `hiretrace_llm_endpoints_online` | Gauge | None | Number of reachable inference backend replicas currently active |
| `hiretrace_llm_concurrency_capacity` | Gauge | None | Total dynamic semaphore capacity across all endpoints |

---

## 2. Production PromQL Queries

Use these queries in Prometheus alerts and Grafana dashboards:

### 1. Assessment Pipeline Throughput (Evaluations / Minute)
```promql
rate(hiretrace_pipeline_evaluations_total{outcome="completed"}[5m]) * 60
```

### 2. LLM Degraded Rate Percentage
Alert when LLM inference drops into degraded mode:
```promql
(sum(rate(hiretrace_pipeline_evaluations_total{outcome="degraded"}[5m]))
/
sum(rate(hiretrace_pipeline_evaluations_total[5m]))) * 100 > 5
```

### 3. Queue Backlog Alarm
Trigger alert when workers are falling behind:
```promql
hiretrace_queue_depth > 20
```

### 4. 90th Percentile Latency per Agent (Seconds)
```promql
hiretrace_agent_duration_seconds{quantile="0.9"}
```

### 5. Backend Endpoint Availability
Alert if any GPU replica drops offline:
```promql
hiretrace_llm_endpoints_online < 2
```

---

## 3. Grafana Dashboard Sketch

```
+-------------------------------------------------------------------------------+
| HireTrace Production Overview                                                 |
+------------------------------------+------------------------------------------+
|  Queue Depth: [ 3 ]               |  Online LLM Endpoints: [ 2 / 2 ]         |
|  Total Evaluated: [ 1,420 ]        |  LLM Concurrency Capacity: [ 8 ]        |
+------------------------------------+------------------------------------------+
| Pipeline Throughput (jobs/min)     | Agent Latency Breakdown (p50 / p90)      |
| [==================== Line Chart ] | [ RequirementMapping: 0.8s              ] |
|                                    | [ EvidenceAggregation: 0.15s             ] |
|                                    | [ CrossSourceVerification: 1.4s         ] |
|                                    | [ RecommendationWriter: 2.1s            ] |
+------------------------------------+------------------------------------------+
| Job Status Distribution (Donut)    | LLM Calls: Success vs Fallback           |
| Done: 95% | Evaluating: 3%         | Success: 99.4%                           |
| Failed: 1% | Queued: 1%            | Fallback/Degraded: 0.6%                  |
+-------------------------------------------------------------------------------+
```

---

## 4. Structured JSON Logging

All pipeline events and web access logs are formatted as single-line JSON objects, making them directly ingestible by Datadog, ELK/OpenSearch, AWS CloudWatch, or Google Cloud Logging:

### Agent Execution Event Example
```json
{
  "timestamp": "2026-09-04T10:30:15.123456Z",
  "event": "agent_execution",
  "agent": "CrossSourceVerificationAgent",
  "candidate_id": "cand_9482_acme",
  "duration_sec": 1.4231,
  "outcome": "success",
  "degraded": false
}
```

### API Access Log Example
```json
{
  "timestamp": "2026-09-04T10:30:16.890123Z",
  "method": "POST",
  "path": "/api/evaluate/cand_9482_acme",
  "status_code": 200,
  "latency_ms": 3412.5,
  "client_ip": "10.0.4.12",
  "candidate_id": "cand_9482_acme"
}
```
