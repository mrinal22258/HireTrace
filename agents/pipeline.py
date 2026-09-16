"""
HireTrace End-to-End Pipeline.

Coordinates the 4-agent workflow:
Requirement Mapping -> Retrieval & Evidence Aggregation -> Cross-Source Verification -> Recommendation Writing.
Saves agent execution trajectories and returns the complete Assessment Report.
"""

from typing import Dict, Any, Optional, List
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor

from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.retrieval_layer import EvidenceRetriever
from agents.ollama_client import OllamaClient
from agents.requirement_mapping_agent import RequirementMappingAgent, JobRequirement
from agents.evidence_aggregation_agent import EvidenceAggregationAgent
from agents.cross_source_verification_agent import CrossSourceVerificationAgent, EvidenceMatrix
from agents.recommendation_writer_agent import RecommendationWriterAgent, AssessmentReport
from agents.critic_agent import ClaimCriticAgent
from agents.observability import METRICS, log_agent_event
from baseline.rubric_scorer import RubricScorer, RubricScoreBreakdown


class HireTracePipeline:
    """End-to-end coordinator for HireTrace candidate assessments."""

    def __init__(self, ollama_client: Optional[OllamaClient] = None, trajectory_dir: str = "trajectories", enable_generic_comparator: bool = True):
        self.client = ollama_client or OllamaClient()
        self.trajectory_dir = trajectory_dir
        self.enable_generic_comparator = enable_generic_comparator
        os.makedirs(self.trajectory_dir, exist_ok=True)

        self.req_mapper = RequirementMappingAgent(self.client)
        self.verifier = CrossSourceVerificationAgent(self.client, enable_generic_comparator=enable_generic_comparator)
        self.writer = RecommendationWriterAgent(self.client)
        self.critic = ClaimCriticAgent(self.client)

    def run(
        self,
        dossier: CandidateDossier,
        log_trajectory: bool = True,
        precomputed_requirements: Optional[List[JobRequirement]] = None
    ) -> AssessmentReport:
        """Runs the complete assessment pipeline for a candidate."""
        t0 = time.time()
        trajectory: Dict[str, Any] = {
            "candidate_id": dossier.candidate_id,
            "candidate_name": dossier.name,
            "target_role": dossier.target_role,
            "steps": []
        }

        # Steps 1, 2, 3: Concurrently execute independent preparation passes
        # Step 1 (RubricScorer, CPU), Step 2 (FAISS index, CPU/embeddings), Step 3 (RequirementMapping, LLM)
        t_parallel_start = time.time()
        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_rubric = pool.submit(RubricScorer.evaluate_from_dict, dossier.structured_cv_profile)
            fut_index = pool.submit(EvidenceRetriever, dossier.spans)
            fut_reqs = (
                pool.submit(lambda: precomputed_requirements)
                if precomputed_requirements is not None
                else pool.submit(self.req_mapper.map_requirements, dossier.jd_text, dossier.target_role)
            )
            rubric_breakdown = fut_rubric.result()
            retriever = fut_index.result()
            requirements = fut_reqs.result()
        dur_prep = time.time() - t_parallel_start

        METRICS.record_agent_latency("RubricScorer", dur_prep)
        log_agent_event("RubricScorer", dossier.candidate_id, dur_prep, "success")
        trajectory["steps"].append({
            "step": "rubric_scoring",
            "agent": "RubricScorer (Deterministic Baseline A)",
            "output": rubric_breakdown.to_dict(),
            "duration_sec": round(dur_prep, 4),
            "overlapped": True,
            "wall_clock_sec": round(dur_prep, 4)
        })

        aggregator = EvidenceAggregationAgent(retriever)
        trajectory["steps"].append({
            "step": "retrieval_index_built",
            "total_spans_indexed": len(dossier.spans),
            "duration_sec": round(dur_prep, 4),
            "overlapped": True,
            "wall_clock_sec": round(dur_prep, 4)
        })

        METRICS.record_agent_latency("RequirementMappingAgent", dur_prep)
        log_agent_event("RequirementMappingAgent", dossier.candidate_id, dur_prep, "success")
        trajectory["steps"].append({
            "step": "requirement_mapping",
            "agent": "RequirementMappingAgent",
            "output": [r.to_dict() for r in requirements],
            "duration_sec": round(dur_prep, 4),
            "overlapped": True,
            "precomputed": precomputed_requirements is not None,
            "wall_clock_sec": round(dur_prep, 4)
        })

        # Step 4: Evidence Aggregation Agent
        t_agg = time.time()
        aggregated_evidence = aggregator.aggregate_all(requirements, rubric_breakdown)
        dur_agg = time.time() - t_agg
        METRICS.record_agent_latency("EvidenceAggregationAgent", dur_agg)
        log_agent_event("EvidenceAggregationAgent", dossier.candidate_id, dur_agg, "success")
        trajectory["steps"].append({
            "step": "evidence_aggregation",
            "agent": "EvidenceAggregationAgent",
            "output": [a.to_dict() for a in aggregated_evidence],
            "duration_sec": round(dur_agg, 4)
        })

        # Step 5: Cross-Source Verification Agent
        t_ver = time.time()
        evidence_matrix = self.verifier.build_matrix(dossier.candidate_id, aggregated_evidence)
        dur_ver = time.time() - t_ver
        METRICS.record_agent_latency("CrossSourceVerificationAgent", dur_ver)
        log_agent_event("CrossSourceVerificationAgent", dossier.candidate_id, dur_ver, "success")
        trajectory["steps"].append({
            "step": "cross_source_verification",
            "agent": "CrossSourceVerificationAgent",
            "output": evidence_matrix.to_dict(),
            "duration_sec": round(dur_ver, 4)
        })

        # Step 6: Recommendation Writer Agent
        from agents.jd_templates import classify_role
        custom_jd = getattr(dossier, "custom_jd_provided", False)
        if custom_jd:
            tax_matched = True
            match_note = None
        else:
            _, tax_matched = classify_role(dossier.target_role)
            if not tax_matched:
                match_note = f"No specialized rubric matched for '{dossier.target_role}' — using a generated/general evaluation. Paste a full JD for a tailored assessment."
            else:
                match_note = None

        t_wri = time.time()
        report = self.writer.generate_report(
            candidate_name=dossier.name,
            target_role=dossier.target_role,
            matrix=evidence_matrix,
            rubric=rubric_breakdown,
            taxonomy_matched=tax_matched,
            role_match_note=match_note,
            custom_jd_provided=custom_jd
        )
        dur_wri = time.time() - t_wri
        is_degraded = getattr(report, "degraded", False)
        METRICS.record_agent_latency("RecommendationWriterAgent", dur_wri)
        log_agent_event("RecommendationWriterAgent", dossier.candidate_id, dur_wri, "success" if not is_degraded else "degraded", degraded=is_degraded)
        trajectory["steps"].append({
            "step": "recommendation_writing",
            "agent": "RecommendationWriterAgent",
            "output": report.to_dict(),
            "duration_sec": round(dur_wri, 4)
        })

        # Step 7: Claim Critic Review Pass
        t_critic = time.time()
        report = self.critic.review_report(
            report=report,
            matrix=evidence_matrix,
            spans=dossier.spans
        )
        dur_critic = time.time() - t_critic
        METRICS.record_agent_latency("ClaimCriticAgent", dur_critic)
        log_agent_event("ClaimCriticAgent", dossier.candidate_id, dur_critic, "success")
        trajectory["steps"].append({
            "step": "claim_critic_review",
            "agent": "ClaimCriticAgent",
            "output": {
                "total_claims": report.total_claims_count,
                "grounded_claims": report.grounded_claims_count,
                "synthesized_inferences": report.synthesized_inferences_count,
                "grounding_rate": report.grounding_rate
            },
            "duration_sec": round(dur_critic, 4)
        })

        elapsed = round(time.time() - t0, 2)
        trajectory["pipeline_latency_sec"] = elapsed
        trajectory["degraded"] = is_degraded
        if is_degraded:
            trajectory["degraded_reason"] = getattr(report, "degraded_reason", None)

        METRICS.record_pipeline_run(degraded=is_degraded)

        if log_trajectory:
            traj_path = os.path.join(self.trajectory_dir, f"{dossier.candidate_id}_trajectory.json")
            with open(traj_path, "w", encoding="utf-8") as f:
                json.dump(trajectory, f, indent=2)

        return report
