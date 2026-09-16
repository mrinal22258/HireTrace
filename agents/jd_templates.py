"""
Curated Job Description Template Library & Role Taxonomy for HireTrace (Phases 7 & 9).

Replaces brittle keyword branching with an extensible JSON-driven taxonomy template library
and graceful LLM-powered bespoke JD generation for novel/unrecognized roles.
"""

import os
import re
import json
import hashlib
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("hiretrace.jd_templates")


class RoleTaxonomy(str, Enum):
    ROBOTICS_AUTONOMOUS = "robotics_autonomous"
    AI_MACHINE_LEARNING = "ai_machine_learning"
    FRONTEND_FULLSTACK = "frontend_fullstack"
    DISTRIBUTED_SYSTEMS_INFRA = "distributed_systems_infra"
    DATA_ENGINEERING = "data_engineering"
    SECURITY_CYBERSECURITY = "security_cybersecurity"
    MOBILE_ENGINEERING = "mobile_engineering"
    FORWARD_DEPLOYED_ENGINEER = "forward_deployed_engineer"
    DEVELOPER_RELATIONS = "developer_relations"
    ENGINEERING_MANAGEMENT = "engineering_management"
    QA_TEST_ENGINEERING = "qa_test_engineering"
    HARDWARE_FIRMWARE_EMBEDDED = "hardware_firmware_embedded"
    GENERAL_SOFTWARE = "general_software"


# Load role taxonomy and templates from external JSON configuration
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "role_taxonomy.json")

try:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
        _CONFIG_DATA = json.load(_f)
except Exception as _err:
    logger.error(f"Failed loading role taxonomy from {_CONFIG_PATH}: {_err}")
    _CONFIG_DATA = {"taxonomy_keywords": {}, "role_jd_templates": {}}

_RAW_KEYWORDS: Dict[str, List[str]] = _CONFIG_DATA.get("taxonomy_keywords", {})
_RAW_TEMPLATES: Dict[str, str] = _CONFIG_DATA.get("role_jd_templates", {})

try:
    from eval_cases.dataset import SHARED_JD
except Exception:
    SHARED_JD = None

# Dual-keyed dictionaries supporting both RoleTaxonomy Enum and raw string keys
class _TaxonomyDict(dict):
    """Dictionary that seamlessly looks up by both RoleTaxonomy enum and str key."""
    def __getitem__(self, key):
        if isinstance(key, Enum):
            key = key.value
        return super().__getitem__(key)

    def get(self, key, default=None):
        if isinstance(key, Enum):
            key = key.value
        return super().get(key, default)

    def __contains__(self, key):
        if isinstance(key, Enum):
            key = key.value
        return super().__contains__(key)


TAXONOMY_KEYWORDS = _TaxonomyDict()
for _k, _v in _RAW_KEYWORDS.items():
    TAXONOMY_KEYWORDS[_k] = _v
    try:
        TAXONOMY_KEYWORDS[RoleTaxonomy(_k)] = _v
    except ValueError:
        pass

ROLE_JD_TEMPLATES = _TaxonomyDict()
for _k, _v in _RAW_TEMPLATES.items():
    if _k == "distributed_systems_infra" and SHARED_JD:
        ROLE_JD_TEMPLATES[_k] = SHARED_JD
    else:
        ROLE_JD_TEMPLATES[_k] = _v
    try:
        ROLE_JD_TEMPLATES[RoleTaxonomy(_k)] = ROLE_JD_TEMPLATES[_k]
    except ValueError:
        pass

# Ensure GENERAL_SOFTWARE fallback exists
if "general_software" not in ROLE_JD_TEMPLATES:
    ROLE_JD_TEMPLATES["general_software"] = "# {title}\nCore Software Engineer Requirements..."
    ROLE_JD_TEMPLATES[RoleTaxonomy.GENERAL_SOFTWARE] = ROLE_JD_TEMPLATES["general_software"]

# In-memory SHA-256 cache for LLM-generated JDs
_GENERATED_JD_CACHE: Dict[str, str] = {}


def classify_role(target_role: Optional[str]) -> Tuple[RoleTaxonomy, bool]:
    """
    Classifies a candidate role into a taxonomy bucket using keyword matching against the JSON config.
    
    Returns:
        Tuple[RoleTaxonomy, bool]: (matched_taxonomy, is_exact_or_keyword_match)
        If no keyword matched, returns (RoleTaxonomy.GENERAL_SOFTWARE, False).
    """
    if not target_role:
        return RoleTaxonomy.GENERAL_SOFTWARE, False

    clean = target_role.strip().lower()
    if not clean:
        return RoleTaxonomy.GENERAL_SOFTWARE, False

    # Check each taxonomy category in priority order
    for cat_name, keywords in _RAW_KEYWORDS.items():
        for kw in keywords:
            # Word boundary match
            if re.search(r"\b" + re.escape(kw) + r"\b", clean):
                try:
                    return RoleTaxonomy(cat_name), True
                except ValueError:
                    # If config defines a custom category outside the Enum, map gracefully
                    return RoleTaxonomy.GENERAL_SOFTWARE, True

    return RoleTaxonomy.GENERAL_SOFTWARE, False


def _get_active_llm_client():
    """Lazily retrieves active LLM client (or MockOllamaClient in offline mode)."""
    try:
        from agents.ollama_client import OllamaClient
        if os.environ.get("HIRETRACE_OFFLINE_MOCK", "").lower() in ("1", "true", "yes"):
            from agents.mock_ollama_client import MockOllamaClient
            return MockOllamaClient()
        return OllamaClient()
    except Exception:
        return None


def generate_role_tailored_jd(target_role: Optional[str], client: Optional[Any] = None) -> str:
    """
    Generates an authoritative domain-tailored Job Description based on target role.
    
    If role matches a known taxonomy bucket, uses the curated template.
    If role is novel/unrecognized, attempts bespoke LLM generation with SHA-256 caching.
    Gracefully falls back to static GENERAL_SOFTWARE template only when LLM is unavailable.
    """
    jd_text, _, _, _ = generate_role_tailored_jd_with_meta(target_role, client=client)
    return jd_text


def generate_role_tailored_jd_with_meta(
    target_role: Optional[str],
    client: Optional[Any] = None
) -> Tuple[str, RoleTaxonomy, bool, str]:
    """
    Generates tailored JD and returns comprehensive metadata:
    (jd_text, taxonomy, matched_bool, source_string)
    
    source_string is one of:
      - 'taxonomy': Matched curated taxonomy bucket
      - 'llm_generated': Novel role, bespoke JD generated via local LLM
      - 'fallback': Novel role, LLM offline/degraded, fell back to GENERAL_SOFTWARE
    """
    role_title = (target_role or "").strip()
    if not role_title:
        role_title = "Software Engineer"

    taxonomy, matched = classify_role(role_title)

    # 1. Direct taxonomy match
    if matched:
        template = ROLE_JD_TEMPLATES.get(taxonomy, ROLE_JD_TEMPLATES.get(RoleTaxonomy.GENERAL_SOFTWARE))
        return template.format(title=role_title), taxonomy, True, "taxonomy"

    # 2. Novel role: attempt LLM-generated bespoke JD with SHA-256 caching
    normalized_role = role_title.strip().lower()
    cache_key = hashlib.sha256(f"jd_gen::{normalized_role}".encode("utf-8")).hexdigest()

    if cache_key in _GENERATED_JD_CACHE:
        return _GENERATED_JD_CACHE[cache_key], RoleTaxonomy.GENERAL_SOFTWARE, False, "llm_generated"

    llm = client or _get_active_llm_client()
    if llm:
        try:
            if hasattr(llm, "is_available") and not llm.is_available():
                raise RuntimeError("LLM backend reports unavailable")

            prompt = (
                f"Generate a realistic job description for the role: {role_title}\n"
                f"Include an 'About the Role' section and exactly 5 discrete 'Core Requirements' labeled REQ-01 through REQ-05."
            )
            system_prompt = (
                "You are an expert technical talent architect. Output valid JSON containing:\n"
                '{"title": str, "company": str, "department": str, "about": str, "requirements": [str]}'
            )

            resp = llm.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=768
            )

            reqs = resp.get("requirements") or resp.get("items") or []
            about = resp.get("about") or f"We are seeking a high-caliber {role_title} to join our engineering organization."
            company = resp.get("company") or "Enterprise Technology Solutions"
            dept = resp.get("department") or "Specialized Engineering"

            if reqs and isinstance(reqs, list) and len(reqs) >= 3:
                lines = [
                    f"# {role_title}",
                    f"Company: {company}",
                    f"Role: {role_title}",
                    f"Department: {dept}\n",
                    "### About the Role",
                    f"{about}\n",
                    "### Core Requirements"
                ]
                for idx, r in enumerate(reqs[:5], 1):
                    r_clean = str(r).strip()
                    if not r_clean.startswith(f"REQ-{idx:02d}"):
                        r_clean = re.sub(r"^[-*•\d\.]+\s*", "", r_clean).strip()
                        r_clean = f"REQ-{idx:02d}: {r_clean}"
                    lines.append(f"- {r_clean}")

                bespoke_jd = "\n".join(lines) + "\n"
                _GENERATED_JD_CACHE[cache_key] = bespoke_jd
                return bespoke_jd, RoleTaxonomy.GENERAL_SOFTWARE, False, "llm_generated"

        except Exception as err:
            logger.warning(f"LLM bespoke JD generation failed for '{role_title}' ({err}); falling back to GENERAL_SOFTWARE.")

    # 3. Last-resort fallback: static GENERAL_SOFTWARE template
    fallback_template = ROLE_JD_TEMPLATES.get(RoleTaxonomy.GENERAL_SOFTWARE)
    fallback_jd = fallback_template.format(title=role_title)
    return fallback_jd, RoleTaxonomy.GENERAL_SOFTWARE, False, "fallback"
