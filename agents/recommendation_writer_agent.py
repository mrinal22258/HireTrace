"""
Recommendation Writer Agent for HireTrace.

Produces the Candidate Assessment Report centered around the 2-Dimensional Quadrant:
Role Fit vs. Evidence Consistency.

IMPORTANT:
The recommendation is ALWAYS "Proceed to human review" with priority questions.
It NEVER outputs an autonomous hire/no-hire verdict.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json
from agents.cross_source_verification_agent import EvidenceMatrix, Discrepancy
from baseline.rubric_scorer import RubricScoreBreakdown
from agents.ollama_client import OllamaClient


@dataclass
class AssessmentReport:
    """Complete Candidate Assessment Report produced by HireTrace."""
    candidate_id: str
    candidate_name: str
    target_role: str
    role_fit_score: Optional[float]    # 0 to 100, or None if degraded
    evidence_consistency_score: float  # 0 to 100 (kept separate from fit)
    quadrant: str                      # "STRONG MATCH", "REVIEW REQUIRED", "WEAK MATCH", "INSUFFICIENT EVIDENCE", "DEGRADED"
    recommendation: str                # Always "Proceed to human review."
    priority_questions: List[str]      # Specific questions for human interviewers
    key_discrepancies: List[Dict[str, Any]]
    requirement_table: List[Dict[str, Any]]
    unsupported_claim_count: int
    contradicted_claim_count: int
    rubric_baseline_score: float
    formatted_terminal_card: str
    degraded: bool = False
    degraded_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "target_role": self.target_role,
            "role_fit_score": round(self.role_fit_score, 1) if self.role_fit_score is not None else None,
            "evidence_consistency_score": round(self.evidence_consistency_score, 1),
            "quadrant": self.quadrant,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
            "recommendation": self.recommendation,
            "priority_questions": self.priority_questions,
            "key_discrepancies": self.key_discrepancies,
            "requirement_table": self.requirement_table,
            "unsupported_claim_count": self.unsupported_claim_count,
            "contradicted_claim_count": self.contradicted_claim_count,
            "rubric_baseline_score": round(self.rubric_baseline_score, 1),
            "formatted_terminal_card": self.formatted_terminal_card
        }


class RecommendationWriterAgent:
    """Agent that synthesizes the final assessment report and priority review questions."""

    SYSTEM_PROMPT = """You are a senior hiring committee advisor. Review the candidate's verified evidence matrix and discrepancy log.
Formulate 3-4 pointed, specific priority questions that a human technical interviewer must ask the candidate to resolve uncertainties and contradictions.
The recommendation MUST ALWAYS be 'Proceed to human review.'
Output strictly valid JSON matching this structure:
{
  "priority_questions": [
    "Clarify employment timeline between CV and interview statements",
    "Establish actual technical ownership and architecture design in the Kafka migration"
  ]
}"""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.client = ollama_client or OllamaClient()

    def generate_report(
        self,
        candidate_name: str,
        target_role: str,
        matrix: EvidenceMatrix,
        rubric: Optional[RubricScoreBreakdown] = None
    ) -> AssessmentReport:
        """Assembles the two-dimensional report card."""
        # Check degraded state
        is_degraded = getattr(matrix, "degraded", False)
        degraded_reason = getattr(matrix, "degraded_reason", None) if is_degraded else None

        # 1. Calculate Role Fit Score (0-100)
        # If degraded, we do NOT fabricate a fake 50.0 fit score
        if is_degraded:
            role_fit_score = None
        else:
            req_fit_points = 0.0
            for v in matrix.verifications:
                if v.status == "SUPPORTED":
                    req_fit_points += 100.0
                elif v.status == "CONTRADICTED":
                    req_fit_points += 85.0
                else:
                    req_fit_points += 20.0  # missing evidence

            avg_req_fit = req_fit_points / max(1, matrix.total_requirements)
            rubric_score = rubric.normalized_score if rubric else 50.0
            role_fit_score = (0.60 * avg_req_fit) + (0.40 * rubric_score)

        rubric_score = rubric.normalized_score if rubric else 50.0

        # 2. Evidence Consistency Score (0-100) - KEPT STRICTLY SEPARATE
        has_contradictions = (matrix.contradicted_count > 0) or (len(matrix.all_discrepancies) > 0)
        consistency_score = matrix.consistency_score
        if has_contradictions and consistency_score >= 70.0:
            consistency_score = max(10.0, 65.0 - (len(matrix.all_discrepancies) * 15.0))

        # 3. Determine Quadrant (2D Placement)
        has_insufficient = (matrix.insufficient_count >= 1)
        high_consistency = (consistency_score >= 70.0) and (not has_contradictions)

        if is_degraded:
            if has_contradictions:
                quadrant = "REVIEW REQUIRED"
            elif rubric_score < 55.0 and high_consistency:
                quadrant = "WEAK MATCH"
            else:
                quadrant = "DEGRADED"
        elif has_contradictions:
            quadrant = "REVIEW REQUIRED"
        elif has_insufficient:
            quadrant = "INSUFFICIENT EVIDENCE"
        else:
            high_fit = role_fit_score is not None and role_fit_score >= 72.0
            if high_fit and high_consistency:
                quadrant = "STRONG MATCH"
            elif not high_fit and high_consistency:
                quadrant = "WEAK MATCH"
            else:
                quadrant = "INSUFFICIENT EVIDENCE"

        # 4. Generate Priority Questions for Human Reviewer
        questions = self._generate_priority_questions(matrix, rubric, target_role)

        # 5. Format Requirement Table
        requirement_table = []
        for v in matrix.verifications:
            status_symbol = "✓ SUPPORTED" if v.status == "SUPPORTED" else ("⚠ CONFLICTING" if v.status == "CONTRADICTED" else "⚠ INSUFFICIENT")
            requirement_table.append({
                "req_id": v.req_id,
                "name": v.requirement_name,
                "status": v.status,
                "display": status_symbol,
                "confidence": v.confidence,
                "citations": v.supporting_citations,
                "citations_detail": getattr(v, "citations_detail", []),
                "synthesis": getattr(v, "synthesis", "")
            })

        # 6. Format Key Discrepancies
        key_discrepancies = [d.to_dict() for d in matrix.all_discrepancies]

        # 7. Render Terminal Card (Matches Prompt Section 10 Spec)
        terminal_card = self._render_terminal_card(
            candidate_name=candidate_name,
            target_role=target_role,
            role_fit=role_fit_score,
            consistency=consistency_score,
            quadrant=quadrant,
            req_table=requirement_table,
            discrepancies=key_discrepancies,
            questions=questions,
            unsupported_count=matrix.insufficient_count
        )

        return AssessmentReport(
            candidate_id=matrix.candidate_id,
            candidate_name=candidate_name,
            target_role=target_role,
            role_fit_score=role_fit_score,
            evidence_consistency_score=consistency_score,
            quadrant=quadrant,
            recommendation="Proceed to human review.",
            priority_questions=questions,
            key_discrepancies=key_discrepancies,
            requirement_table=requirement_table,
            unsupported_claim_count=matrix.insufficient_count,
            contradicted_claim_count=matrix.contradicted_count,
            rubric_baseline_score=rubric_score,
            formatted_terminal_card=terminal_card,
            degraded=is_degraded,
            degraded_reason=degraded_reason
        )

    def _generate_priority_questions(
        self,
        matrix: EvidenceMatrix,
        rubric: Optional[RubricScoreBreakdown],
        target_role: str = ""
    ) -> List[str]:
        """Generates targeted review questions using deterministic templates or optional Ollama generation."""
        import os
        use_llm_questions = os.getenv("USE_LLM_QUESTIONS", "false").lower() in ("true", "1", "yes")
        if use_llm_questions and matrix.all_discrepancies and self.client.is_available():
            disc_texts = [f"- {d.topic}: {d.quote_a} vs {d.quote_b}" for d in matrix.all_discrepancies]
            prompt = f"Candidate applied for '{target_role}' and has the following documented evidence discrepancies:\n" + "\n".join(disc_texts) + "\n\nProvide 3 priority interview questions:"
            resp = self.client.generate_json(prompt=prompt, system_prompt=self.SYSTEM_PROMPT, max_tokens=400)
            q_list = resp.get("priority_questions", [])
            if isinstance(q_list, list) and len(q_list) > 0:
                return [str(q) for q in q_list[:4]]

        # High-speed deterministic question generation (Grounded in discrepancies and missing requirements)
        questions = []
        for d in matrix.all_discrepancies:
            if "tenure" in d.topic.lower() or "employment" in d.topic.lower():
                questions.append("Clarify employment timeline and tenure between CV claims and interview statements")
            elif "lead" in d.topic.lower() or "role" in d.topic.lower():
                questions.append("Establish actual scope of ownership versus team participation in the architecture migration")
            elif "skill" in d.topic.lower() or "assessment" in d.topic.lower():
                questions.append("Conduct a live deep-dive on technical implementation details to validate hands-on competency")
            else:
                questions.append(f"Investigate discrepancy regarding {d.topic} with candidate")

        for v in matrix.verifications:
            if v.status == "INSUFFICIENT_EVIDENCE":
                questions.append(f"Probe concrete production evidence for requirement: {v.requirement_name}")

        if len(questions) < 3:
            role_l = (target_role or "").lower()
            if any(k in role_l for k in ["robot", "autonomous", "drone", "slam", "perception", "lidar"]):
                defaults = [
                    "Deep-dive on sensor calibration failure modes (e.g. LiDAR-camera spatial distortion under dynamic lighting)",
                    "Evaluate real-world runtime FPS constraints and compute trade-offs on embedded robotics platforms",
                    "Probe multi-robot coordination and collision avoidance edge cases in physical flight/drive tests"
                ]
            elif any(k in role_l for k in ["ai", "machine learning", "deep learning", "nlp", "llm", "rag"]):
                defaults = [
                    "Evaluate neural architecture training convergence, loss function tuning, and hyperparameter trade-offs",
                    "Probe vector index latency vs recall trade-offs and embedding retrieval failure cases",
                    "Discuss model serving latency optimizations (quantization, batching) in production"
                ]
            elif any(k in role_l for k in ["frontend", "front-end", "fullstack", "react", "web", "ui"]):
                defaults = [
                    "Discuss component rendering performance, state caching, and client-side optimization techniques",
                    "Review automated test strategy for complex asynchronous UI workflows and state management",
                    "Explore cross-browser compatibility and responsive layout failure handling"
                ]
            elif any(k in role_l for k in ["distributed", "infra", "kafka", "sre", "cloud"]):
                defaults = [
                    "Verify high-scale production trade-offs and event-streaming semantics in candidate's primary architecture project",
                    "Review code quality standards, telemetry instrumentation, and testing practices across past contributions",
                    "Assess team leadership, RFC authoring, and cross-functional communication style"
                ]
            else:
                defaults = [
                    "Verify architectural trade-offs and component modularity in candidate's primary engineering project",
                    "Review code quality standards, testing coverage, and automated CI/CD practices across past contributions",
                    "Assess technical problem-solving, debugging strategy, and engineering ownership"
                ]
            for d in defaults:
                if d not in questions:
                    questions.append(d)

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for q in questions:
            if q not in seen:
                seen.add(q)
                deduped.append(q)
        return deduped[:4]

    def _render_terminal_card(
        self,
        candidate_name: str,
        target_role: str,
        role_fit: Optional[float],
        consistency: float,
        quadrant: str,
        req_table: List[Dict[str, Any]],
        discrepancies: List[Dict[str, Any]],
        questions: List[str],
        unsupported_count: int
    ) -> str:
        border = "=" * 68
        lines = []
        lines.append(border)
        lines.append(f"                    CANDIDATE ASSESSMENT REPORT                    ")
        lines.append(f"Candidate: {candidate_name} | Role: {target_role}")
        lines.append(border)
        if role_fit is not None:
            lines.append(f"ROLE FIT                          {role_fit:5.1f} / 100")
        else:
            lines.append("ROLE FIT                          [DEGRADED - LOCAL LLM OFFLINE]")
        lines.append(f"EVIDENCE CONSISTENCY              {consistency:5.1f} / 100")
        lines.append(f"QUADRANT PLACEMENT                [{quadrant}]")
        
        disc_count = len(discrepancies)
        if disc_count > 0:
            lines.append(f"[!] {disc_count} critical discrepancy/discrepancies require verification")
        if unsupported_count > 0:
            lines.append(f"[*] {unsupported_count} requirement(s) lack sufficient cross-source backing")

        lines.append("\nREQUIREMENTS")
        for r in req_table:
            name_padded = (r['name'][:26]).ljust(28)
            disp = r['display'].replace("✓", "[PASS]").replace("⚠", "[WARN]")
            lines.append(f"  {name_padded} {disp}")
            if r.get("status") == "INSUFFICIENT_EVIDENCE" and r.get("synthesis"):
                lines.append(f"      Interpretation: {r['synthesis']}")

        if discrepancies:
            lines.append("\nKEY DISCREPANCIES")
            for idx, d in enumerate(discrepancies, 1):
                lines.append(f"  {idx:02d}  {d['topic']}")
                lines.append(f"      - {d['source_a']}: \"{d['quote_a']}\"")
                lines.append(f"      - {d['source_b']}: \"{d['quote_b']}\"")

        lines.append("\nRECOMMENDATION: Proceed to human review.")
        lines.append("Priority questions for reviewer:")
        for q in questions:
            lines.append(f"  -> {q}")
        lines.append(border)

        return "\n".join(lines)
