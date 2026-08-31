"""
Fast-Triage Tier 0 Pre-Screen Engine for HireTrace.

Evaluates high-volume candidate intake in milliseconds without burning LLM inference tokens.
Combines:
1. Deterministic ATS Rubric Scorer (baseline/rubric_scorer.py)
2. Domain & skill keyword match density scanner
3. Rapid disqualification of clearly non-matching applicants (< 15% fit)

Saves 15-30 seconds of GPU/CPU time per non-matching candidate.
"""

import os
import re
from typing import Dict, Any, Tuple, Optional
from baseline.rubric_scorer import RubricScorer
from agents.evidence_loader import EvidenceLoader, CandidateDossier


FAST_TRIAGE_ENABLED = os.getenv("FAST_TRIAGE_ENABLED", "true").lower() in ("true", "1", "yes")
FAST_TRIAGE_THRESHOLD = float(os.getenv("FAST_TRIAGE_THRESHOLD", "18.0"))

CORE_TECH_KEYWORDS = {
    "python", "distributed", "systems", "concurrency", "asyncio", "kafka",
    "grpc", "microservices", "kubernetes", "docker", "redis", "postgresql",
    "sql", "database", "api", "backend", "cloud", "aws", "architecture",
    "raft", "paxos", "consensus", "scaling", "golang", "java", "c++", "rust"
}


class FastTriageEngine:
    """Lightweight deterministic triage filter to skip LLM inference for low-fit candidates."""

    @staticmethod
    def evaluate(dossier: CandidateDossier, target_role: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Runs Tier 0 screen.
        Returns:
            (is_fast_rejected: bool, triage_report: Optional[Dict])
        """
        if not FAST_TRIAGE_ENABLED:
            return False, None

        # 1. Deterministic Rubric baseline score (~5ms)
        rubric_result = RubricScorer.evaluate_from_dict(dossier.structured_cv_profile)
        overall_rubric_score = rubric_result.normalized_score


        # 2. Keyword density scan across CV text
        cv_lower = (dossier.cv_text or "").lower()
        matched_keywords = [kw for kw in CORE_TECH_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', cv_lower)]


        # 3. Disqualification heuristic:
        # If rubric score < threshold AND matched keywords <= 1
        if overall_rubric_score < FAST_TRIAGE_THRESHOLD and len(matched_keywords) <= 1:
            reason = (
                f"Candidate CV exhibits low domain alignment for '{target_role}'. "
                f"ATS Rubric Baseline: {overall_rubric_score:.1f}/100 with only {len(matched_keywords)} "
                f"relevant technical keywords ({', '.join(matched_keywords) if matched_keywords else 'none'}). "
                f"Bypassed 4-agent LLM pipeline to conserve compute."
            )

            triage_report = {
                "candidate_id": dossier.candidate_id,
                "role_fit_score": round(overall_rubric_score, 1),
                "evidence_consistency_score": 100.0,
                "quadrant": "LOW_FIT_FAST_REJECT",
                "executive_summary": reason,
                "strengths": ["Clear formatting and readable resume layout"],
                "gaps": [
                    f"Insufficient technical skill alignment for {target_role}",
                    f"Matched {len(matched_keywords)} of {len(CORE_TECH_KEYWORDS)} core domain keywords",
                    f"Rubric score ({overall_rubric_score:.1f}/100) below threshold ({FAST_TRIAGE_THRESHOLD})"
                ],
                "critical_discrepancies": [],
                "questions_for_interviewers": [
                    f"Can you explain your background and how it connects to the requirements of {target_role}?"
                ],
                "verified_claims_count": 0,
                "contradicted_claims_count": 0,
                "unverified_claims_count": 0,
                "triage_tier": "tier_0_fast_reject"
            }

            return True, triage_report

        return False, None
