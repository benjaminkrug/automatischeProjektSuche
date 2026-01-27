"""Pydantic schemas for structured AI outputs."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.constants import REJECTION_CODES

# Budget-Limit für Bietergemeinschaft (max. Projektgröße)
MAX_BUDGET_LIMIT = 250_000  # EUR


class ResearchOutput(BaseModel):
    """Structured output for client/project research."""

    client_info: str = Field(
        description="Information about the client (industry, size, reputation)"
    )
    project_type: str = Field(
        description="Type of project (new development, maintenance, consulting)"
    )
    estimated_budget_range: str = Field(
        description="Estimated budget range based on project complexity"
    )
    red_flags: List[str] = Field(
        default_factory=list, description="Potential risks or warning signs"
    )
    opportunities: List[str] = Field(
        default_factory=list, description="Special advantages or opportunities"
    )
    recommendation: str = Field(description="Brief recommendation for application")


class ScoreBreakdown(BaseModel):
    """Breakdown of score components for transparency."""

    skill_match: int = Field(
        ge=0, le=40, default=0, description="Score for skill matching / keyword score (max 40)"
    )
    experience: int = Field(
        ge=0, le=25, default=0, description="Score for experience/seniority (max 25)"
    )
    embedding: int = Field(
        ge=0, le=15, default=0, description="Score from embedding similarity (max 15)"
    )
    market_fit: int = Field(
        ge=0, le=10, default=0, description="Score for budget/timing fit (max 10)"
    )
    risk_factors: int = Field(
        ge=0, le=10, default=0, description="Score for risk assessment (max 10)"
    )


class MatchOutput(BaseModel):
    """Structured output for project-team matching."""

    score: int = Field(ge=0, le=100, description="Match score from 0-100")
    score_breakdown: Optional[ScoreBreakdown] = Field(
        default=None, description="Breakdown of score components"
    )
    best_candidate_name: str = Field(description="Name of the best matching candidate")
    proposed_rate: float = Field(gt=0, description="Proposed hourly rate in EUR")
    rate_reasoning: str = Field(description="Reasoning for the proposed rate")
    strengths: List[str] = Field(description="Strengths supporting the application")
    weaknesses: List[str] = Field(description="Weaknesses or concerns")
    decision: Literal["apply", "review", "reject"] = Field(
        description="Decision: apply, review, or reject"
    )
    rejection_reason_code: Optional[str] = Field(
        default=None,
        description=f"Rejection code if decision is reject. One of: {', '.join(REJECTION_CODES)}",
    )


class CandidateProfile(BaseModel):
    """Team member profile for matching."""

    id: int
    name: str
    role: str
    skills: List[str]
    years_experience: int
    min_hourly_rate: float
    embedding_score: float = 0.0


class MatchResult(BaseModel):
    """Complete result of project-team matching."""

    score: int = Field(ge=0, le=100)
    score_breakdown: Optional[ScoreBreakdown] = None
    decision: Literal["apply", "review", "reject"]
    best_candidate_id: int
    best_candidate_name: str
    proposed_rate: float
    rate_reasoning: str
    strengths: List[str]
    weaknesses: List[str]
    rejection_reason_code: Optional[str] = None
    raw_analysis: str = ""


class ResearchResult(BaseModel):
    """Complete result of client/project research."""

    client_info: str
    project_type: str
    estimated_budget_range: str
    red_flags: List[str]
    opportunities: List[str]
    recommendation: str
    raw_analysis: str = ""


class ProjectFitAnalysis(BaseModel):
    """Erweiterte Analyse für Bietergemeinschaft-Eignung."""

    # Projektgröße (Budget-Limit: max €250.000)
    estimated_budget_min: Optional[float] = Field(
        default=None, description="Geschätztes Mindestbudget in EUR"
    )
    estimated_budget_max: Optional[float] = Field(
        default=None, description="Geschätztes Maximalbudget in EUR (Max: 250.000)"
    )
    budget_source: Literal["explicit", "estimated"] = Field(
        default="estimated", description="'explicit' wenn Budget genannt, sonst 'estimated'"
    )
    estimated_hours: Optional[int] = Field(
        default=None, description="Geschätzter Aufwand in Stunden"
    )
    estimated_duration_months: Optional[int] = Field(
        default=None, description="Geschätzte Projektdauer in Monaten"
    )
    budget_exceeds_limit: bool = Field(
        default=False, description="True wenn Budget über €250.000"
    )

    # Team-Passung
    min_team_size_required: int = Field(
        default=1, ge=1, description="Mindestanzahl Personen parallel nötig (1, 3, 5, 10+)"
    )
    fits_3_person_team: bool = Field(
        default=True, description="Passt das Projekt für ein 3-Personen-Team?"
    )
    parallel_workstreams: int = Field(
        default=1, ge=1, description="Wie viele Leute parallel nötig?"
    )
    team_size_reasoning: str = Field(
        default="", description="Begründung für Team-Größen-Einschätzung"
    )

    # Projekttyp
    is_webapp: bool = Field(default=False, description="Ist es eine Webanwendung?")
    is_mobile_app: bool = Field(default=False, description="Ist es eine Mobile App?")
    is_api_backend: bool = Field(default=False, description="Ist es ein API/Backend-Projekt?")
    is_infrastructure: bool = Field(
        default=False, description="Ist es ein Infrastruktur/DevOps-Projekt?"
    )

    # Ausschlusskriterien (Bietergemeinschaft)
    requires_references: bool = Field(
        default=False, description="Werden Referenzprojekte verlangt?"
    )
    min_reference_count: int = Field(
        default=0, ge=0, description="Mindestanzahl geforderter Referenzen"
    )
    requires_certifications: List[str] = Field(
        default_factory=list, description="Geforderte Zertifizierungen (ISO 27001, BSI, etc.)"
    )
    requires_security_clearance: bool = Field(
        default=False, description="Sicherheitsüberprüfung (Ü1, Ü2, NATO) erforderlich?"
    )
    requires_specific_legal_form: bool = Field(
        default=False, description="Spezifische Rechtsform verlangt (nur GmbH, keine BG)?"
    )
    legal_form_details: str = Field(
        default="", description="Details zur geforderten Rechtsform"
    )
    bietergemeinschaft_allowed: bool = Field(
        default=True, description="Sind Bietergemeinschaften zugelassen?"
    )
    min_annual_revenue: Optional[float] = Field(
        default=None, description="Geforderter Mindestumsatz in EUR"
    )
    min_employee_count: Optional[int] = Field(
        default=None, description="Geforderte Mindestmitarbeiterzahl"
    )

    # Risiko-Score
    exclusion_risk: Literal["low", "medium", "high"] = Field(
        default="low", description="Risiko durch Ausschlusskriterien"
    )
    exclusion_reasons: List[str] = Field(
        default_factory=list, description="Liste der gefundenen Barrieren"
    )


class ExtendedResearchOutput(BaseModel):
    """Kombiniertes Output mit Basis- und Fit-Analyse."""

    # Basis-Analyse (wie bisher)
    client_info: str = Field(
        description="Information about the client (industry, size, reputation)"
    )
    project_type: str = Field(
        description="Type of project (new development, maintenance, consulting)"
    )
    estimated_budget_range: str = Field(
        description="Estimated budget range based on project complexity"
    )
    red_flags: List[str] = Field(
        default_factory=list, description="Potential risks or warning signs"
    )
    opportunities: List[str] = Field(
        default_factory=list, description="Special advantages or opportunities"
    )
    recommendation: str = Field(description="Brief recommendation for application")

    # Erweiterte Fit-Analyse
    fit_analysis: ProjectFitAnalysis = Field(
        default_factory=ProjectFitAnalysis,
        description="Erweiterte Analyse für Bietergemeinschaft-Eignung"
    )


class ExtendedResearchResult(BaseModel):
    """Complete result of extended client/project research."""

    # Basis-Ergebnisse
    client_info: str
    project_type: str
    estimated_budget_range: str
    red_flags: List[str]
    opportunities: List[str]
    recommendation: str
    raw_analysis: str = ""

    # Erweiterte Fit-Analyse
    fit_analysis: Optional[ProjectFitAnalysis] = None
