"""
HireTrace End-to-End Pipeline.

Coordinates the 4-agent workflow:
Requirement Mapping -> Retrieval & Evidence Aggregation -> Cross-Source Verification -> Recommendation Writing.
Saves agent execution trajectories and returns the complete Assessment Report.
"""

from typing import Dict, Any, Optional
import os
import json
import time

from agents.evidence_loader import EvidenceLoader, CandidateDossier
from agents.retrieval_layer import EvidenceRetriever
from agents.ollama_client import OllamaClient
from agents.requirement_mapping_agent import RequirementMappingAgent
from agents.evidence_aggregation_agent import EvidenceAggregationAgent
from agents.cross_source_verification_agent import CrossSourceVerificationAgent, EvidenceMatrix
from agents.recommendation_writer_agent import RecommendationWriterAgent, AssessmentReport
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

    def run(self, dossier: CandidateDossier, log_trajectory: bool = True) -> AssessmentReport:
        """Runs the complete assessment pipeline for a candidate."""
        t0 = time.time()
        trajectory: Dict[str, Any] = {
            "candidate_id": dossier.candidate_id,
            "candidate_name": dossier.name,
            "target_role": dossier.target_role,
            "steps": []
        }

        # Step 1: Baseline Rubric Scoring (Deterministic, no LLM)
        rubric_breakdown = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)
        trajectory["steps"].append({
            "step": "rubric_scoring",
            "agent": "RubricScorer (Deterministic Baseline A)",
            "output": rubric_breakdown.to_dict()
        })

        # Step 2: Build FAISS Vector Index over evidence spans
        retriever = EvidenceRetriever(dossier.spans)
        aggregator = EvidenceAggregationAgent(retriever)
        trajectory["steps"].append({
            "step": "retrieval_index_built",
            "total_spans_indexed": len(dossier.spans)
        })

        # Step 3: Requirement Mapping Agent
        requirements = self.req_mapper.map_requirements(dossier.jd_text, dossier.target_role)
        trajectory["steps"].append({
            "step": "requirement_mapping",
            "agent": "RequirementMappingAgent",
            "output": [r.to_dict() for r in requirements]
        })

        # Step 4: Evidence Aggregation Agent
        aggregated_evidence = aggregator.aggregate_all(requirements, rubric_breakdown)
        trajectory["steps"].append({
            "step": "evidence_aggregation",
            "agent": "EvidenceAggregationAgent",
            "output": [a.to_dict() for a in aggregated_evidence]
        })

        # Step 5: Cross-Source Verification Agent
        evidence_matrix = self.verifier.build_matrix(dossier.candidate_id, aggregated_evidence)
        trajectory["steps"].append({
            "step": "cross_source_verification",
            "agent": "CrossSourceVerificationAgent",
            "output": evidence_matrix.to_dict()
        })

        # Step 6: Recommendation Writer Agent
        report = self.writer.generate_report(
            candidate_name=dossier.name,
            target_role=dossier.target_role,
            matrix=evidence_matrix,
            rubric=rubric_breakdown
        )
        trajectory["steps"].append({
            "step": "recommendation_writing",
            "agent": "RecommendationWriterAgent",
            "output": report.to_dict()
        })

        elapsed = round(time.time() - t0, 2)
        trajectory["pipeline_latency_sec"] = elapsed
        trajectory["degraded"] = getattr(report, "degraded", False)
        if getattr(report, "degraded", False):
            trajectory["degraded_reason"] = getattr(report, "degraded_reason", None)

        if log_trajectory:
            traj_path = os.path.join(self.trajectory_dir, f"{dossier.candidate_id}_trajectory.json")
            with open(traj_path, "w", encoding="utf-8") as f:
                json.dump(trajectory, f, indent=2)

        return report
