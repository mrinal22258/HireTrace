"""
Observability and Telemetry Subsystem for HireTrace (Phase 7).

Provides:
1. Standard Prometheus metrics exposition (/metrics).
2. Per-agent latency tracking (histogram/summary metrics).
3. Queue depth and job execution counters.
4. Structured JSON logging across pipeline execution.
"""

import time
import json
import logging
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from agents.db import DB, JobQueue

logger = logging.getLogger("hiretrace.telemetry")
agent_logger = logging.getLogger("hiretrace.agent")


def log_agent_event(
    agent: str,
    candidate_id: str,
    duration_sec: float,
    outcome: str = "success",
    degraded: bool = False,
    details: Optional[Dict[str, Any]] = None
):
    """Logs structured JSON event for agent execution in the pipeline."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "agent_execution",
        "agent": agent,
        "candidate_id": candidate_id,
        "duration_sec": round(duration_sec, 4),
        "outcome": outcome,
        "degraded": degraded,
    }
    if details:
        payload["details"] = details
    agent_logger.info(json.dumps(payload))


class MetricsCollector:
    """Thread-safe collector for pipeline and system telemetry metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        # agent -> list of durations
        self._agent_latencies: Dict[str, List[float]] = {
            "RequirementMappingAgent": [],
            "EvidenceAggregationAgent": [],
            "CrossSourceVerificationAgent": [],
            "RecommendationWriterAgent": [],
            "RubricScorer": [],
        }
        self.pipeline_runs_total = 0
        self.pipeline_degraded_total = 0
        self.redis_ratelimit_fallbacks_total = 0

    def record_redis_ratelimit_fallback(self):
        """Records a Redis rate limiter fallback to in-memory RateLimiter."""
        with self._lock:
            self.redis_ratelimit_fallbacks_total += 1

    def record_agent_latency(self, agent: str, duration_sec: float):
        """Records an agent run duration."""
        with self._lock:
            if agent not in self._agent_latencies:
                self._agent_latencies[agent] = []
            self._agent_latencies[agent].append(duration_sec)

    def record_pipeline_run(self, degraded: bool = False):
        """Records an end-to-end pipeline run."""
        with self._lock:
            self.pipeline_runs_total += 1
            if degraded:
                self.pipeline_degraded_total += 1

    def get_agent_stats(self) -> Dict[str, Dict[str, float]]:
        """Computes summary stats per agent."""
        stats = {}
        with self._lock:
            for agent, durations in self._agent_latencies.items():
                if not durations:
                    stats[agent] = {"count": 0, "sum": 0.0, "avg": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0}
                    continue
                sorted_d = sorted(durations)
                count = len(sorted_d)
                d_sum = sum(sorted_d)
                p50 = sorted_d[int(count * 0.5)]
                p90 = sorted_d[min(count - 1, int(count * 0.9))]
                p99 = sorted_d[min(count - 1, int(count * 0.99))]
                stats[agent] = {
                    "count": count,
                    "sum": round(d_sum, 4),
                    "avg": round(d_sum / count, 4),
                    "p50": round(p50, 4),
                    "p90": round(p90, 4),
                    "p99": round(p99, 4),
                }
        return stats

    def render_prometheus(self, ollama_client=None) -> str:
        """
        Renders telemetry in Prometheus text format (version 0.0.4).
        Exposes:
        - hiretrace_queue_depth
        - hiretrace_jobs_total{status="..."}
        - hiretrace_pipeline_evaluations_total{status="..."}
        - hiretrace_agent_duration_seconds{agent="...", quantile="..."}
        - hiretrace_llm_calls_total{outcome="..."}
        - hiretrace_llm_endpoints_online
        """
        lines = []

        # 1. Job Queue Metrics
        queue_stats = {"queued": 0, "parsing": 0, "evaluating": 0, "done": 0, "failed": 0}
        try:
            with DB._get_session() as session:
                jobs = session.query(JobQueue.status).all()
                for (st,) in jobs:
                    if st in queue_stats:
                        queue_stats[st] += 1
                    else:
                        queue_stats[st] = 1
        except Exception:
            pass

        active_depth = queue_stats.get("queued", 0) + queue_stats.get("parsing", 0)

        lines.append("# HELP hiretrace_queue_depth Number of candidate assessment jobs currently waiting in queue")
        lines.append("# TYPE hiretrace_queue_depth gauge")
        lines.append(f"hiretrace_queue_depth {active_depth}")

        lines.append("# HELP hiretrace_jobs_total Total candidate assessment background jobs processed by status")
        lines.append("# TYPE hiretrace_jobs_total counter")
        for st, count in queue_stats.items():
            lines.append(f'hiretrace_jobs_total{{status="{st}"}} {count}')

        # 2. Pipeline Evaluations Metrics
        lines.append("# HELP hiretrace_pipeline_evaluations_total Total end-to-end evaluations completed")
        lines.append("# TYPE hiretrace_pipeline_evaluations_total counter")
        lines.append(f'hiretrace_pipeline_evaluations_total{{outcome="completed"}} {self.pipeline_runs_total}')
        lines.append(f'hiretrace_pipeline_evaluations_total{{outcome="degraded"}} {self.pipeline_degraded_total}')

        # 3. Agent Latencies
        agent_stats = self.get_agent_stats()
        lines.append("# HELP hiretrace_agent_duration_seconds Latency summary of individual pipeline agents in seconds")
        lines.append("# TYPE hiretrace_agent_duration_seconds summary")
        for agent, s in agent_stats.items():
            lines.append(f'hiretrace_agent_duration_seconds{{agent="{agent}",quantile="0.5"}} {s["p50"]}')
            lines.append(f'hiretrace_agent_duration_seconds{{agent="{agent}",quantile="0.9"}} {s["p90"]}')
            lines.append(f'hiretrace_agent_duration_seconds{{agent="{agent}",quantile="0.99"}} {s["p99"]}')
            lines.append(f'hiretrace_agent_duration_seconds_sum{{agent="{agent}"}} {s["sum"]}')
            lines.append(f'hiretrace_agent_duration_seconds_count{{agent="{agent}"}} {s["count"]}')

        # 4. LLM Telemetry
        if ollama_client is not None and hasattr(ollama_client, "get_telemetry"):
            telemetry = ollama_client.get_telemetry()
            lines.append("# HELP hiretrace_llm_calls_total Total calls dispatched to LLM inference backends")
            lines.append("# TYPE hiretrace_llm_calls_total counter")
            lines.append(f'hiretrace_llm_calls_total{{outcome="success"}} {telemetry.get("successful_calls", 0)}')
            lines.append(f'hiretrace_llm_calls_total{{outcome="fallback"}} {telemetry.get("fallback_calls", 0)}')

            endpoints = telemetry.get("endpoints", [])
            online_count = sum(1 for ep in endpoints if ep.get("available", False) and ep.get("circuit_state") != "open")
            lines.append("# HELP hiretrace_llm_endpoints_online Number of healthy reachable inference backend endpoints")
            lines.append("# TYPE hiretrace_llm_endpoints_online gauge")
            lines.append(f"hiretrace_llm_endpoints_online {online_count}")

            lines.append("# HELP hiretrace_llm_concurrency_capacity Max concurrent queries supported across backends")
            lines.append("# TYPE hiretrace_llm_concurrency_capacity gauge")
            lines.append(f"hiretrace_llm_concurrency_capacity {telemetry.get('total_capacity', 1)}")

        # 5. Rate Limiter Telemetry
        lines.append("# HELP hiretrace_redis_ratelimit_fallbacks_total Total fallback occurrences from Redis to in-memory rate limiter")
        lines.append("# TYPE hiretrace_redis_ratelimit_fallbacks_total counter")
        lines.append(f"hiretrace_redis_ratelimit_fallbacks_total {self.redis_ratelimit_fallbacks_total}")

        lines.append("")
        return "\n".join(lines)


# Singleton telemetry instance
METRICS = MetricsCollector()
