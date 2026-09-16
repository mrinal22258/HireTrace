# HireTrace Quality Scoreboard Baseline

Generated: 2026-09-15 19:24:57
Benchmark Cohort: 5 cases across core difficulty axes

## Summary Metrics

| Metric | Value | Benchmark Target | Status |
|---|---|---|---|
| **Mean Grounding Rate** | 32.0% | >= 90.0% | ACCEPTABLE |
| **Citation Precision** | 32.0% | >= 85.0% | ACCEPTABLE |
| **Rubric/LLM Mean Delta** | 23.6 pts | <= 20.0 pts | WARN |
| **Schema Repair Count** | 0 | 0 repairs | PERFECT |
| **Degraded Mode Rate** | 0.0% | 0.0% (online LLM) | PASS |
| **Latency p50** | 32.20s | <= 25.0s | INFO |
| **Latency p95** | 43.39s | <= 45.0s | INFO |

## Per-Case Breakdown

| Case | Target Candidate | Verdict Quadrant | Grounding | Precision | Fit | Rubric | Latency (med) |
|---|---|---|---|---|---|---|---|
| `case_01_strong_01` | Sarah Chen | **STRONG MATCH** | 80.0% | 80.0% | 91.7 | 79.2 | 25.08s |
| `case_03_med_01` | Elena Rostova | **STRONG MATCH** | 20.0% | 20.0% | 82.0 | 55.0 | 32.20s |
| `case_06_weak_01` | Tom Bradley | **WEAK MATCH** | 0.0% | 0.0% | 70.0 | 25.0 | 42.52s |
| `case_12_adv_jd_vs_claim` | Evan Brooks | **INSUFFICIENT EVIDENCE** | 20.0% | 20.0% | 68.7 | 45.8 | 28.64s |
| `case_15_deceptive_centerpiece` | Alexander Sterling | **REVIEW REQUIRED** | 40.0% | 40.0% | 89.9 | 79.2 | 43.39s |
