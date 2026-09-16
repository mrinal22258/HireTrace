"""
Claim Critic Agent for HireTrace.

Performs a chain-of-verification / critic self-check pass on the final assessment report:
1. Verifies that every claim asserted as 'grounded' carries valid citations to actual evidence spans.
2. Enforces exact substring containment between quoted citations and source evidence spans.
3. Invokes an LLM-based verification check when available to detect hallucinated assertions.
4. Downgrades any claim that fails citation validity or quote containment to 'synthesized_inference'.
5. Updates report grounding tallies, grounding rate, and terminal card visualization.
"""

from typing import Dict, Any, List, Optional
import time
import re
from agents.evidence_loader import EvidenceSpan
from agents.cross_source_verification_agent import EvidenceMatrix
from agents.recommendation_writer_agent import AssessmentReport
from agents.ollama_client import OllamaClient


class ClaimCriticAgent:
    """Lightweight critic / self-check pass for candidate assessment reports."""

    CRITIC_SYSTEM_PROMPT = """You are a rigorous evidence auditor and factual consistency critic.
Given a list of claimed requirement evaluations and their cited evidence spans:
Determine whether each claim is strictly grounded in the cited source evidence.
If a claim contains unsupported extrapolations, mark it as ungrounded.
Output strictly valid JSON matching this schema:
{
  "evaluations": [
    {
      "req_id": "REQ-01",
      "grounded": true,
      "critique": "Directly supported by cited text"
    }
  ]
}"""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.client = ollama_client or OllamaClient()

    def review_report(
        self,
        report: AssessmentReport,
        matrix: EvidenceMatrix,
        spans: Optional[List[EvidenceSpan]] = None
    ) -> AssessmentReport:
        """
        Audits all requirement claims in the report against source spans.
        Downgrades failing grounded claims to synthesized inferences.
        """
        # Build span lookup table
        span_lookup: Dict[str, EvidenceSpan] = {}
        if spans:
            for s in spans:
                span_lookup[s.span_id] = s

        critic_log: List[Dict[str, Any]] = []
        downgraded_count = 0
        confirmed_count = 0

        # LLM critic pass if client is available
        llm_critique_map: Dict[str, bool] = {}
        if self.client.is_available() and report.requirement_table:
            grounded_items = [
                r for r in report.requirement_table
                if r.get("claim_type") == "grounded" and r.get("citations")
            ]
            if grounded_items:
                prompt_claims = []
                for item in grounded_items:
                    c_details = item.get("citations_detail", [])
                    quotes = [c.get("quote", "") for c in c_details if c.get("quote")]
                    prompt_claims.append(
                        f"Req ID: {item.get('req_id')} ({item.get('name')})\n"
                        f"Status: {item.get('status')}\n"
                        f"Cited Quotes: {' | '.join(quotes)}"
                    )
                prompt = (
                    f"Audit the following {len(grounded_items)} requirement evaluation claims:\n\n"
                    + "\n\n".join(prompt_claims)
                    + "\n\nVerify if each claim is strictly grounded. Output JSON with evaluations array."
                )
                try:
                    resp = self.client.generate_json(
                        prompt=prompt,
                        system_prompt=self.CRITIC_SYSTEM_PROMPT,
                        max_tokens=600
                    )
                    evals = resp.get("evaluations", [])
                    if isinstance(evals, list):
                        for ev in evals:
                            if isinstance(ev, dict) and "req_id" in ev and "grounded" in ev:
                                llm_critique_map[ev["req_id"]] = bool(ev["grounded"])
                except Exception:
                    # Non-fatal: rely on deterministic validation
                    pass

        # Deterministic verification & containment pass
        for req in report.requirement_table:
            c_type = req.get("claim_type", "grounded")
            citations = req.get("citations", [])
            citations_detail = req.get("citations_detail", [])

            if c_type == "grounded":
                is_valid = True
                failure_reasons = []

                if not citations:
                    is_valid = False
                    failure_reasons.append("No citations provided")
                else:
                    # Check citation existence and quote containment
                    if span_lookup:
                        for cit_id in citations:
                            if cit_id not in span_lookup:
                                is_valid = False
                                failure_reasons.append(f"Citation {cit_id} not found in candidate dossier spans")

                    # Check quote containment from citations_detail
                    for detail in citations_detail:
                        cit_id = detail.get("span_id", "")
                        quote = detail.get("quote", "").strip()
                        if cit_id and cit_id in span_lookup and quote:
                            source_text = span_lookup[cit_id].text
                            clean_quote = " ".join(quote.split())
                            clean_source = " ".join(source_text.split())
                            if clean_quote not in clean_source:
                                is_valid = False
                                failure_reasons.append(
                                    f"Quote for {cit_id} not an exact substring of source span"
                                )

                # Check semantic overlap and polarity compatibility
                req_title = req.get("requirement_name") or req.get("name", "")
                claim_words = [
                    w for w in re.findall(r"\b[A-Za-z0-9_-]{4,}\b", req_title.lower())
                    if w not in ("candidate", "experience", "senior", "engineer", "software", "production", "years", "proven", "demonstrates")
                ]
                has_semantic_support = False
                for cit_id in citations:
                    if cit_id in span_lookup:
                        span_lower = span_lookup[cit_id].text.lower()
                        # Check polarity
                        if any(neg in span_lower for neg in ["no commercial experience", "no experience with", "failed to demonstrate", "admitted during technical interview that they have no"]):
                            is_valid = False
                            failure_reasons.append(f"Span {cit_id} explicitly disclaims or negates experience")
                            break
                        if claim_words:
                            overlap = sum(1 for w in claim_words if w in span_lower) / len(claim_words)
                            if overlap >= 0.15 or any(w in span_lower for w in claim_words if w in ("python", "kafka", "rabbitmq", "asyncio", "postgres", "concurrency", "distributed", "fastapi", "docker", "kubernetes", "leadership", "mentoring", "tenure", "sharding", "architecture", "rfc", "operations", "reliability")):
                                has_semantic_support = True
                        else:
                            has_semantic_support = True

                if not has_semantic_support and is_valid:
                    is_valid = False
                    failure_reasons.append("Cited spans lack substantive semantic overlap with requirement keywords")

                # Check LLM critic verdict if available
                req_id = req.get("req_id", "")
                if req_id in llm_critique_map and not llm_critique_map[req_id]:
                    is_valid = False
                    failure_reasons.append("Flagged by LLM critic as insufficiently grounded in context")

                if not is_valid:
                    req["claim_type"] = "synthesized_inference"
                    req["is_grounded"] = False
                    critique_note = f"Critic downgrade: {'; '.join(failure_reasons)}"
                    req["grounding_rationale"] = critique_note
                    critic_log.append({
                        "req_id": req_id,
                        "action": "downgrade",
                        "reasons": failure_reasons
                    })
                    downgraded_count += 1
                else:
                    req["is_grounded"] = True
                    req["grounding_rationale"] = "Confirmed grounded by critic verification pass"
                    critic_log.append({
                        "req_id": req_id,
                        "action": "confirmed",
                        "citations": citations
                    })
                    confirmed_count += 1
            else:
                req["is_grounded"] = False
                if not req.get("grounding_rationale"):
                    req["grounding_rationale"] = "Synthesized inference (no direct 1:1 citation asserted)"

        # Recalculate totals
        total_claims = len(report.requirement_table)
        grounded_claims = sum(1 for r in report.requirement_table if r.get("is_grounded"))
        synthesized_count = total_claims - grounded_claims
        grounding_rate = (grounded_claims / total_claims) if total_claims > 0 else 1.0

        report.total_claims_count = total_claims
        report.grounded_claims_count = grounded_claims
        report.synthesized_inferences_count = synthesized_count
        report.grounding_rate = grounding_rate

        # If any claim was downgraded, refresh terminal card visualization
        if downgraded_count > 0:
            lines = report.formatted_terminal_card.split("\n")
            # Update requirement section tags in terminal card
            new_lines = []
            for line in lines:
                matched_req = None
                for r in report.requirement_table:
                    if r.get("name") and r["name"][:20] in line:
                        matched_req = r
                        break
                if matched_req:
                    name_padded = (matched_req['name'][:26]).ljust(28)
                    disp = matched_req['display'].replace("✓", "[PASS]").replace("⚠", "[WARN]")
                    tag = (
                        f"[GROUNDED: {', '.join(matched_req['citations'])}]"
                        if matched_req.get('is_grounded') and matched_req.get('citations')
                        else "[SYNTHESIS]"
                    )
                    new_lines.append(f"  {name_padded} {disp} {tag}")
                else:
                    new_lines.append(line)
            report.formatted_terminal_card = "\n".join(new_lines)

        return report
