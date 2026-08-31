"""
Deterministic Resume-Rubric Baseline (Baseline A).

Rule-based resume screening heuristic baseline:
1. Open Source & Public Code Artifacts (0-35 points)
2. Self-Directed System Projects & Architecture (0-30 points)
3. Production Engineering Tenure & Operational Scale (0-25 points)
4. Core Language & Database Skill Match (0-10 points)
5. Technical Writing, Mentorship & Bonus Signals (0-20 points)
Total Raw Max = 120 points; Normalized = 0-100.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


# Category Weight Caps (Raw Max = 120)
OPEN_SOURCE_MAX = 35
SELF_PROJECTS_MAX = 30
PRODUCTION_MAX = 25
TECHNICAL_SKILLS_MAX = 10
BONUS_POINTS_MAX = 20
TOTAL_RAW_MAX = 120


@dataclass
class CandidateCVProfile:
    """Standardized profile extracted from a candidate's CV for deterministic rubric scoring."""
    candidate_id: str
    name: str = ""
    # Open Source signals
    has_public_repo: bool = False
    open_source_prs_count: int = 0
    maintained_repos_count: int = 0
    total_repo_stars: int = 0
    
    # Self-Directed Projects signals
    has_system_project: bool = False
    has_production_architecture: bool = False  # e.g., Docker, CI/CD, message queues
    has_live_demo: bool = False
    has_test_coverage: bool = False
    
    # Production Experience signals
    years_production_experience: float = 0.0
    has_high_scale_experience: bool = False  # high throughput, SLAs, distributed scale
    
    # Technical Skills match signals
    primary_language_match: bool = False
    database_systems_match: bool = False
    distributed_cloud_match: bool = False
    
    # Bonus Points signals
    has_tech_writing_or_talks: bool = False
    has_mentorship_or_leadership: bool = False
    has_competitive_or_academic: bool = False
    has_security_or_certifications: bool = False


@dataclass
class CategoryScore:
    """Individual category score and rationale."""
    category: str
    score: float
    max_score: float
    notes: List[str] = field(default_factory=list)


@dataclass
class RubricScoreBreakdown:
    """Comprehensive rubric evaluation result."""
    candidate_id: str
    open_source: CategoryScore
    self_projects: CategoryScore
    production: CategoryScore
    technical_skills: CategoryScore
    bonus_points: CategoryScore
    raw_total: float
    normalized_score: float  # 0 to 100
    category_scores: Dict[str, float] = field(default_factory=dict)
    summary_audit: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "raw_total": round(self.raw_total, 2),
            "normalized_score": round(self.normalized_score, 2),
            "category_scores": self.category_scores,
            "summary_audit": self.summary_audit,
            "details": {
                "open_source": {"score": self.open_source.score, "max": self.open_source.max_score, "notes": self.open_source.notes},
                "self_projects": {"score": self.self_projects.score, "max": self.self_projects.max_score, "notes": self.self_projects.notes},
                "production": {"score": self.production.score, "max": self.production.max_score, "notes": self.production.notes},
                "technical_skills": {"score": self.technical_skills.score, "max": self.technical_skills.max_score, "notes": self.technical_skills.notes},
                "bonus_points": {"score": self.bonus_points.score, "max": self.bonus_points.max_score, "notes": self.bonus_points.notes},
            }
        }


class RubricScorer:
    """Deterministic, dependency-free rubric scorer based on weighted evaluation categories."""

    @classmethod
    def score_open_source(cls, profile: CandidateCVProfile) -> CategoryScore:
        score = 0.0
        notes = []
        
        if profile.has_public_repo:
            score += 5.0
            notes.append("Public repository/profile present (+5)")
            
        pr_pts = min(profile.open_source_prs_count * 2.0, 10.0)
        if pr_pts > 0:
            score += pr_pts
            notes.append(f"Merged open-source contributions/PRs: {profile.open_source_prs_count} (+{pr_pts:.1f})")
            
        maintained_pts = min(profile.maintained_repos_count * 5.0, 10.0)
        if maintained_pts > 0:
            score += maintained_pts
            notes.append(f"Maintained open-source repos: {profile.maintained_repos_count} (+{maintained_pts:.1f})")
            
        if profile.total_repo_stars >= 50:
            score += 10.0
            notes.append(f"Authored work has significant community traction (stars >= 50: {profile.total_repo_stars}) (+10)")
        elif profile.total_repo_stars >= 10:
            score += 5.0
            notes.append(f"Authored work has community traction (stars >= 10: {profile.total_repo_stars}) (+5)")
            
        capped_score = min(score, float(OPEN_SOURCE_MAX))
        return CategoryScore(category="open_source", score=capped_score, max_score=OPEN_SOURCE_MAX, notes=notes)

    @classmethod
    def score_self_projects(cls, profile: CandidateCVProfile) -> CategoryScore:
        score = 0.0
        notes = []
        
        if profile.has_system_project:
            score += 10.0
            notes.append("End-to-end architecture/system project (+10)")
            
        if profile.has_production_architecture:
            score += 10.0
            notes.append("Production-grade setup (containers, CI/CD, messaging) (+10)")
            
        if profile.has_live_demo:
            score += 5.0
            notes.append("Publicly accessible live demo/deployment (+5)")
            
        if profile.has_test_coverage:
            score += 5.0
            notes.append("Comprehensive automated test suite (+5)")
            
        capped_score = min(score, float(SELF_PROJECTS_MAX))
        return CategoryScore(category="self_projects", score=capped_score, max_score=SELF_PROJECTS_MAX, notes=notes)

    @classmethod
    def score_production(cls, profile: CandidateCVProfile) -> CategoryScore:
        score = 0.0
        notes = []
        years = profile.years_production_experience
        
        if years >= 5.0:
            score += 20.0
            notes.append(f"Senior production tenure: {years:.1f} years (+20)")
        elif years >= 3.0:
            score += 16.0
            notes.append(f"Mid-to-senior production tenure: {years:.1f} years (+16)")
        elif years >= 1.0:
            score += 8.0
            notes.append(f"Junior/early production tenure: {years:.1f} years (+8)")
        elif years > 0.0:
            score += 4.0
            notes.append(f"Internship or <1 year production tenure: {years:.1f} years (+4)")
        else:
            notes.append("No commercial production experience documented (+0)")
            
        if profile.has_high_scale_experience:
            score += 5.0
            notes.append("High-throughput / mission-critical SLA experience (+5)")
            
        capped_score = min(score, float(PRODUCTION_MAX))
        return CategoryScore(category="production", score=capped_score, max_score=PRODUCTION_MAX, notes=notes)

    @classmethod
    def score_technical_skills(cls, profile: CandidateCVProfile) -> CategoryScore:
        score = 0.0
        notes = []
        
        if profile.primary_language_match:
            score += 4.0
            notes.append("Primary core language and runtime alignment (+4)")
        if profile.database_systems_match:
            score += 3.0
            notes.append("Database & persistence systems alignment (+3)")
        if profile.distributed_cloud_match:
            score += 3.0
            notes.append("Distributed systems & cloud infrastructure alignment (+3)")
            
        capped_score = min(score, float(TECHNICAL_SKILLS_MAX))
        return CategoryScore(category="technical_skills", score=capped_score, max_score=TECHNICAL_SKILLS_MAX, notes=notes)

    @classmethod
    def score_bonus_points(cls, profile: CandidateCVProfile) -> CategoryScore:
        score = 0.0
        notes = []
        
        if profile.has_tech_writing_or_talks:
            score += 5.0
            notes.append("Technical writing, publications, or conference presentations (+5)")
        if profile.has_mentorship_or_leadership:
            score += 5.0
            notes.append("Formal engineering mentorship or team leadership (+5)")
        if profile.has_competitive_or_academic:
            score += 5.0
            notes.append("Academic achievements or competitive programming record (+5)")
        if profile.has_security_or_certifications:
            score += 5.0
            notes.append("Security engineering practices or verified certifications (+5)")
            
        capped_score = min(score, float(BONUS_POINTS_MAX))
        return CategoryScore(category="bonus_points", score=capped_score, max_score=BONUS_POINTS_MAX, notes=notes)

    @classmethod
    def evaluate(cls, profile: CandidateCVProfile) -> RubricScoreBreakdown:
        os_score = cls.score_open_source(profile)
        sp_score = cls.score_self_projects(profile)
        prod_score = cls.score_production(profile)
        ts_score = cls.score_technical_skills(profile)
        bp_score = cls.score_bonus_points(profile)
        
        raw_total = os_score.score + sp_score.score + prod_score.score + ts_score.score + bp_score.score
        # Raw points maximum is 120; normalize to a standard 0-100 scale
        normalized_score = min(max((raw_total / float(TOTAL_RAW_MAX)) * 100.0, 0.0), 100.0)
        
        category_scores = {
            "open_source": os_score.score,
            "self_projects": sp_score.score,
            "production": prod_score.score,
            "technical_skills": ts_score.score,
            "bonus_points": bp_score.score
        }
        
        summary_audit = []
        for cat in [os_score, sp_score, prod_score, ts_score, bp_score]:
            summary_audit.extend(cat.notes)
            
        return RubricScoreBreakdown(
            candidate_id=profile.candidate_id,
            open_source=os_score,
            self_projects=sp_score,
            production=prod_score,
            technical_skills=ts_score,
            bonus_points=bp_score,
            raw_total=raw_total,
            normalized_score=normalized_score,
            category_scores=category_scores,
            summary_audit=summary_audit
        )

    # Alias for explicit profile evaluation
    evaluate_from_profile = evaluate

    @classmethod
    def evaluate_from_dict(cls, data: Dict[str, Any]) -> RubricScoreBreakdown:
        """Helper to evaluate raw dictionary data directly."""
        profile = CandidateCVProfile(
            candidate_id=str(data.get("candidate_id", "unknown")),
            name=str(data.get("name", "")),
            has_public_repo=bool(data.get("has_public_repo", False)),
            open_source_prs_count=int(data.get("open_source_prs_count", 0)),
            maintained_repos_count=int(data.get("maintained_repos_count", 0)),
            total_repo_stars=int(data.get("total_repo_stars", 0)),
            has_system_project=bool(data.get("has_system_project", False)),
            has_production_architecture=bool(data.get("has_production_architecture", False)),
            has_live_demo=bool(data.get("has_live_demo", False)),
            has_test_coverage=bool(data.get("has_test_coverage", False)),
            years_production_experience=float(data.get("years_production_experience", 0.0)),
            has_high_scale_experience=bool(data.get("has_high_scale_experience", False)),
            primary_language_match=bool(data.get("primary_language_match", False)),
            database_systems_match=bool(data.get("database_systems_match", False)),
            distributed_cloud_match=bool(data.get("distributed_cloud_match", False)),
            has_tech_writing_or_talks=bool(data.get("has_tech_writing_or_talks", False)),
            has_mentorship_or_leadership=bool(data.get("has_mentorship_or_leadership", False)),
            has_competitive_or_academic=bool(data.get("has_competitive_or_academic", False)),
            has_security_or_certifications=bool(data.get("has_security_or_certifications", False)),
        )
        return cls.evaluate(profile)
