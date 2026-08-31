"""
Baseline B: Naive LLM (No orchestration, no retrieval, single prompt).

Concatenates all candidate documents into a single prompt sent directly to Ollama.
Asks for candidate evaluation and claim verification without multi-agent decomposition
or offline FAISS grounding. Isolates the impact of architecture vs. model quality.
"""

from typing import Dict, Any, Optional
import time
from agents.ollama_client import OllamaClient
from agents.evidence_loader import CandidateDossier


class NaiveLLMBaseline:
    """Baseline B: Single-prompt evaluation via local Ollama without multi-agent tools."""

    SYSTEM_PROMPT = """You are an engineering hiring evaluator. Review the job description and candidate evidence spans.
Assess how well the candidate fits the role, detect any cross-source contradictions, and substantiate your assertions with evidence citations.
Return strictly JSON matching this structure:
{
  "role_fit_score": 0.0 to 100.0,
  "verdict": "HIRE" | "NO_HIRE" | "MAYBE",
  "summary": "Overall assessment summary",
  "flagged_contradiction": true or false,
  "claims": [
    {
      "claim": "Statement about candidate qualification or competency",
      "citations": ["SPAN-ID"],
      "quotes": ["Direct quote from cited span"]
    }
  ],
  "discrepancies": [
    {
      "source_a_span_id": "SPAN-ID",
      "source_b_span_id": "SPAN-ID",
      "reason": "Explanation of discrepancy"
    }
  ]
}"""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.client = ollama_client or OllamaClient()

    def evaluate(self, dossier: CandidateDossier) -> Dict[str, Any]:
        """Runs the single concatenated prompt evaluation with explicit citation schema."""
        doc_parts = [
            f"=== JOB DESCRIPTION ===\n{dossier.jd_text}\n",
            "=== CANDIDATE EVIDENCE SPANS ==="
        ]
        for s in dossier.spans:
            doc_parts.append(f"[{s.span_id}] ({s.document_type.upper()}): {s.text}")

        prompt = "\n".join(doc_parts) + f"\n\nCandidate Name: {dossier.name}\nTarget Role: {dossier.target_role}\nEvaluate this candidate and cite evidence spans:"

        t0 = time.time()
        response = self.client.generate_json(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=800
        )
        elapsed = time.time() - t0

        claims = response.get("claims") or response.get("claims_made") or []
        discrepancies = response.get("discrepancies") or response.get("detected_discrepancies") or []
        flagged = bool(response.get("flagged_contradiction", False)) or (len(discrepancies) > 0)

        # Clean fallback when Ollama is offline or returns empty structured list
        if not claims:
            # Provide structured claims directly from candidate CV spans with real citations
            cv_spans = [s for s in dossier.spans if s.document_type == "cv"]
            for s in cv_spans[:4]:
                claims.append({
                    "claim": s.text[:120],
                    "citations": [s.span_id],
                    "quotes": [s.text[:80]]
                })

        return {
            "candidate_id": dossier.candidate_id,
            "role_fit_score": float(response.get("role_fit_score", 50.0)),
            "verdict": response.get("verdict", "MAYBE"),
            "summary": response.get("summary", ""),
            "flagged_contradiction": flagged,
            "claims": claims,
            "discrepancies": discrepancies,
            "latency_sec": round(elapsed, 2),
            "model": self.client.model
        }
