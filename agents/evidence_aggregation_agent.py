"""
Deterministic Evidence Aggregation Layer for HireTrace.

Aggregates retrieved evidence spans per requirement across multiple sources:
CV, Interview notes, Assessment results, Project documents, and the Baseline Rubric Scorer.
Assembles structured requirement bundles deterministically via FAISS cosine retrieval (no LLM inference required).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from agents.requirement_mapping_agent import JobRequirement
from agents.retrieval_layer import EvidenceRetriever, RetrievedSpan
from baseline.rubric_scorer import RubricScorer, RubricScoreBreakdown, CandidateCVProfile


@dataclass
class AggregatedEvidence:
    """Aggregated multi-source evidence for a single job requirement."""
    requirement: JobRequirement
    cv_spans: List[RetrievedSpan] = field(default_factory=list)
    interview_spans: List[RetrievedSpan] = field(default_factory=list)
    assessment_spans: List[RetrievedSpan] = field(default_factory=list)
    project_spans: List[RetrievedSpan] = field(default_factory=list)
    jd_spans: List[RetrievedSpan] = field(default_factory=list)
    rubric_signal: Optional[Dict[str, Any]] = None
    sources_present: List[str] = field(default_factory=list)
    total_spans_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "req_id": self.requirement.req_id,
            "requirement_name": self.requirement.name,
            "sources_present": self.sources_present,
            "total_spans_count": self.total_spans_count,
            "cv_spans": [s.to_dict() for s in self.cv_spans],
            "interview_spans": [s.to_dict() for s in self.interview_spans],
            "assessment_spans": [s.to_dict() for s in self.assessment_spans],
            "project_spans": [s.to_dict() for s in self.project_spans],
            "jd_spans": [s.to_dict() for s in self.jd_spans],
            "rubric_signal": self.rubric_signal
        }


class EvidenceAggregationAgent:
    """Agent that queries the FAISS retrieval layer and deterministic rubric to build requirement bundles."""

    def __init__(self, retriever: EvidenceRetriever):
        self.retriever = retriever

    def aggregate_requirement(
        self,
        requirement: JobRequirement,
        rubric_breakdown: Optional[RubricScoreBreakdown] = None
    ) -> AggregatedEvidence:
        """Retrieves and groups candidate evidence across all sources for a specific requirement."""
        # Retrieve spans per source using requirement name + description query
        query = f"{requirement.name} {requirement.description}"
        source_spans = self.retriever.retrieve_per_source(query=query, top_k_per_source=4)

        cv_spans = source_spans.get("cv", [])
        int_spans = source_spans.get("interview", [])
        ass_spans = source_spans.get("assessment", [])
        proj_spans = source_spans.get("project", [])
        jd_spans = source_spans.get("jd", [])

        sources_present = []
        if cv_spans:
            sources_present.append("cv")
        if int_spans:
            sources_present.append("interview")
        if ass_spans:
            sources_present.append("assessment")
        if proj_spans:
            sources_present.append("project")
        if jd_spans:
            sources_present.append("jd")

        # Map relevant deterministic rubric category score
        rubric_signal = None
        if rubric_breakdown:
            cat_map = {
                "technical_skills": "technical_skills",
                "architecture": "self_projects",
                "leadership": "bonus_points",
                "production_experience": "production"
            }
            target_cat = cat_map.get(requirement.category, "technical_skills")
            cat_score = rubric_breakdown.category_scores.get(target_cat, 0.0)
            rubric_signal = {
                "category": target_cat,
                "score": cat_score,
                "normalized_total": rubric_breakdown.normalized_score
            }

        total_count = len(cv_spans) + len(int_spans) + len(ass_spans) + len(proj_spans) + len(jd_spans)

        return AggregatedEvidence(
            requirement=requirement,
            cv_spans=cv_spans,
            interview_spans=int_spans,
            assessment_spans=ass_spans,
            project_spans=proj_spans,
            jd_spans=jd_spans,
            rubric_signal=rubric_signal,
            sources_present=sources_present,
            total_spans_count=total_count
        )

    def aggregate_all(
        self,
        requirements: List[JobRequirement],
        rubric_breakdown: Optional[RubricScoreBreakdown] = None
    ) -> List[AggregatedEvidence]:
        return [self.aggregate_requirement(req, rubric_breakdown) for req in requirements]
