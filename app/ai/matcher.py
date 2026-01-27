"""Project-team matching using structured LLM outputs."""

import json
from typing import List, Optional

from openai import OpenAI
from pydantic import ValidationError

from app.ai.keyword_scoring import KeywordScoreResult
from app.ai.project_classifier import (
    classify_project,
    should_avoid_type,
    is_preferred_type,
    get_type_recommendation,
)
from app.ai.cost_tracking import log_ai_usage
from app.ai.retry import llm_retry
from app.ai.schemas import (
    CandidateProfile,
    ExtendedResearchResult,
    MatchOutput,
    MatchResult,
    ProjectFitAnalysis,
    ResearchResult,
    ScoreBreakdown,
)
from app.core.exceptions import AIProcessingError, ParsingError
from app.core.logging import get_logger
from app.settings import settings

logger = get_logger("ai.matcher")

# Text-Truncation Limits (Token-Kosten kontrollieren)
MAX_DESCRIPTION_CHARS = 3000
MAX_PDF_TEXT_CHARS = 5000


def _truncate_text(text: str | None, max_chars: int) -> str:
    """Truncate text to max_chars, adding ellipsis if truncated.

    Args:
        text: Text to truncate (can be None)
        max_chars: Maximum number of characters

    Returns:
        Truncated text or empty string if None
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...]"


# Score-Anpassungen für Fit-Analyse
FIT_SCORE_MALUS_TEAM_SIZE = 30  # -30 wenn Team zu klein
FIT_SCORE_MALUS_BUDGET_HIGH = 50  # -50 wenn Budget über Limit
FIT_SCORE_MALUS_EXCLUSION_HIGH = 40  # -40 bei hohem Ausschluss-Risiko
FIT_SCORE_MALUS_EXCLUSION_MEDIUM = 15  # -15 bei mittlerem Ausschluss-Risiko
FIT_SCORE_BONUS_WEBAPP = 5  # +5 für Webapp/App-Projekte


def match_project(
    project_title: str,
    project_description: str,
    project_skills: List[str] | None,
    research: ResearchResult,
    candidates: List[CandidateProfile],
    active_applications: int,
    public_sector: bool = False,
    keyword_score_modifier: int = 0,
    pdf_text: str | None = None,
    keyword_result: Optional[KeywordScoreResult] = None,
    db=None,
    project_id: Optional[int] = None,
) -> MatchResult:
    """Match a project against team candidates using structured LLM output.

    Args:
        project_title: Title of the project
        project_description: Project description
        project_skills: Required skills (if known)
        research: Research results about client
        candidates: List of candidate profiles (pre-filtered by embedding similarity)
        active_applications: Current number of active applications
        public_sector: Whether this is a public sector project
        keyword_score_modifier: Score bonus from keyword matching (+10 for good keywords)
        pdf_text: Extracted text from PDF documents (tender documents)
        keyword_result: Pre-calculated keyword scoring result (optional)

    Returns:
        MatchResult with decision and details

    Raises:
        AIProcessingError: If LLM call fails
        ParsingError: If response parsing fails
    """
    if not candidates:
        logger.warning("No candidates provided for matching")
        return MatchResult(
            score=0,
            decision="reject",
            best_candidate_id=0,
            best_candidate_name="Keine Kandidaten",
            proposed_rate=0.0,
            rate_reasoning="Keine Kandidaten verfügbar",
            strengths=[],
            weaknesses=["Keine passenden Teammitglieder gefunden"],
            rejection_reason_code="TECH_STACK_MISMATCH",
            raw_analysis="",
        )

    # Early type check - reject obviously unsuitable project types before LLM call
    project_type = classify_project(project_title, project_description)
    if should_avoid_type(project_type):
        logger.info(
            "Project rejected due to type mismatch: %s (%s)",
            project_title[:50],
            project_type.value,
        )
        return MatchResult(
            score=0,
            decision="reject",
            best_candidate_id=candidates[0].id if candidates else 0,
            best_candidate_name=candidates[0].name if candidates else "N/A",
            proposed_rate=0.0,
            rate_reasoning=get_type_recommendation(project_type),
            strengths=[],
            weaknesses=[
                f"Projekttyp '{project_type.value}' passt nicht zum Team-Profil",
                get_type_recommendation(project_type),
            ],
            rejection_reason_code="PROJECT_TYPE_MISMATCH",
            raw_analysis="",
        )

    # Early keyword reject check - reject projects with reject keywords before LLM call
    if keyword_result and keyword_result.should_reject:
        logger.info(
            "Project rejected due to keywords: %s (Score: %d, Keywords: %s)",
            project_title[:50],
            keyword_result.reject_score,
            ", ".join(keyword_result.reject_keywords),
        )
        return MatchResult(
            score=0,
            decision="reject",
            best_candidate_id=candidates[0].id if candidates else 0,
            best_candidate_name=candidates[0].name if candidates else "N/A",
            proposed_rate=0.0,
            rate_reasoning="Projekt durch Ausschluss-Keywords abgelehnt",
            strengths=[],
            weaknesses=[
                f"Reject-Keywords gefunden: {', '.join(keyword_result.reject_keywords)}",
                "Technologiestack passt nicht zum Team-Profil",
            ],
            rejection_reason_code="KEYWORD_REJECT",
            raw_analysis="",
        )

    prompt = _build_match_prompt(
        project_title=project_title,
        project_description=project_description,
        project_skills=project_skills,
        research=research,
        candidates=candidates,
        active_applications=active_applications,
        public_sector=public_sector,
        pdf_text=pdf_text,
        keyword_result=keyword_result,
    )

    try:
        match_output, input_tokens, output_tokens = _call_llm_structured(prompt)

        # Log AI usage if database session provided
        if db is not None:
            log_ai_usage(
                db=db,
                operation="matching",
                model=settings.ai_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                project_id=project_id,
            )
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise AIProcessingError(
            f"Matching LLM call failed: {e}",
            model=settings.ai_model,
            prompt_preview=prompt[:200],
        ) from e

    return _apply_business_rules(
        match_output, candidates, public_sector, keyword_score_modifier, keyword_result
    )


def _build_match_prompt(
    project_title: str,
    project_description: str,
    project_skills: List[str] | None,
    research: ResearchResult,
    candidates: List[CandidateProfile],
    active_applications: int,
    public_sector: bool,
    pdf_text: str | None = None,
    keyword_result: Optional[KeywordScoreResult] = None,
) -> str:
    """Build the matching prompt."""
    candidates_text = "\n".join(
        [
            f"- {c.name} ({c.role}): Skills: {', '.join(c.skills[:10])}, "
            f"Erfahrung: {c.years_experience} Jahre, Min. Rate: {c.min_hourly_rate}€/h, "
            f"Embedding-Score: {c.embedding_score:.2f}"
            for c in candidates
        ]
    )

    skills_text = ", ".join(project_skills) if project_skills else "Nicht spezifiziert"

    # Truncate description and PDF text for token cost control
    description_truncated = _truncate_text(project_description, MAX_DESCRIPTION_CHARS)
    pdf_text_truncated = _truncate_text(pdf_text, MAX_PDF_TEXT_CHARS)

    # Build optional PDF section
    pdf_section = ""
    if pdf_text_truncated:
        pdf_section = f"""

AUSSCHREIBUNGSUNTERLAGEN (PDF)
==============================
{pdf_text_truncated}
"""

    # Build keyword analysis section
    keyword_section = ""
    if keyword_result:
        tier_1_kw = ", ".join(keyword_result.tier_1_keywords) if keyword_result.tier_1_keywords else "keine"
        tier_2_kw = ", ".join(keyword_result.tier_2_keywords) if keyword_result.tier_2_keywords else "keine"
        keyword_section = f"""

KEYWORD-ANALYSE (vorberechnet)
==============================
Keyword-Score: {keyword_result.total_score}/70 Punkte
Tier-1 Keywords (Kernkompetenz): {tier_1_kw}
Tier-2 Keywords (starke Passung): {tier_2_kw}
Combo-Bonus: +{keyword_result.combo_bonus} Punkte
Confidence: {keyword_result.confidence}
WICHTIG: Übernimm diesen Score für skill_match!
"""

    return f"""Bewerte die Passung zwischen diesem Projekt und den Kandidaten.

PROJEKT
=======
Titel: {project_title}
Beschreibung: {description_truncated or 'Keine Beschreibung'}
Geforderte Skills: {skills_text}
{pdf_section}{keyword_section}
KUNDENANALYSE
=============
Projekttyp: {research.project_type}
Budget-Einschätzung: {research.estimated_budget_range}
Red Flags: {', '.join(research.red_flags) if research.red_flags else 'Keine'}
Chancen: {', '.join(research.opportunities) if research.opportunities else 'Keine'}

KANDIDATEN
==========
{candidates_text}

KONTEXT
=======
Aktive Bewerbungen: {active_applications}/{settings.max_active_applications}
Öffentlicher Sektor: {'Ja (bevorzugt)' if public_sector else 'Nein'}

BEWERTUNGSKRITERIEN (Gewichtung beachten)
=========================================
- Keyword-Score (vorberechnet): 70%
  (Falls KEYWORD-ANALYSE oben vorhanden: ÜBERNIMM den Wert direkt für skill_match!)
  (Falls keine KEYWORD-ANALYSE: bewerte Skills manuell 0-70)
- Erfahrung & Seniorität: 12%
  (Jahre Erfahrung, Projektrelevanz, Branchenkenntnisse)
- Embedding-Score (Profil-Projekt-Ähnlichkeit): 8%
  (Der vorberechnete Ähnlichkeitswert - höher ist besser)
- Markt-Fit (Budget, Timing): 5%
  (Passt das Budget zum Stundensatz? Ist der Zeitrahmen realistisch?)
- Risikofaktoren (Red Flags, Kapazität): 5%
  (Gibt es Warnzeichen? Ist ausreichend Kapazität vorhanden?)

ENTSCHEIDUNGSSCHWELLEN
======================
- Score <{settings.match_threshold_reject}: reject
- Score {settings.match_threshold_reject}-{settings.match_threshold_review}: review
- Score ≥{settings.match_threshold_apply}: apply

Antworte im JSON-Format mit folgenden Feldern:
- score: Zahl 0-100 (Erfolgswahrscheinlichkeit)
- score_breakdown: Objekt mit Aufschlüsselung:
  - skill_match: Keyword-Score oder manuelle Bewertung (0-70)
  - experience: Punkte für Erfahrung/Seniorität (0-12)
  - embedding: Punkte aus Embedding-Score (0-8)
  - market_fit: Punkte für Markt-Fit (0-5)
  - risk_factors: Punkte für Risikobewertung (0-5)
- best_candidate_name: Name des besten Kandidaten
- proposed_rate: Empfohlener Stundensatz (unteres Marktsegment, über Mindestrate)
- rate_reasoning: Begründung für den Stundensatz
- strengths: Liste von Stärken (max 5)
- weaknesses: Liste von Schwächen (max 5)
- decision: "apply", "review", oder "reject"
- rejection_reason_code: Bei reject einer von: BUDGET_TOO_LOW, TECH_STACK_MISMATCH, EXPERIENCE_INSUFFICIENT, TIMELINE_CONFLICT, CAPACITY_FULL

Antworte NUR mit dem JSON-Objekt, ohne zusätzlichen Text."""


def _clamp_score_breakdown(data: dict) -> dict:
    """Clamp score_breakdown values to valid ranges before Pydantic validation.

    This prevents LLM outputs with out-of-range values from causing validation errors.
    """
    if "score_breakdown" in data and isinstance(data["score_breakdown"], dict):
        breakdown = data["score_breakdown"]
        # Define max values for each component
        max_values = {
            "skill_match": 70,
            "experience": 12,
            "embedding": 8,
            "market_fit": 5,
            "risk_factors": 5,
        }
        for key, max_val in max_values.items():
            if key in breakdown and isinstance(breakdown[key], (int, float)):
                original = breakdown[key]
                breakdown[key] = max(0, min(int(original), max_val))
                if breakdown[key] != original:
                    logger.warning(
                        "Clamped %s from %s to %d (valid range: 0-%d)",
                        key, original, breakdown[key], max_val
                    )
    return data


@llm_retry
def _call_llm_structured(prompt: str) -> tuple[MatchOutput, int, int]:
    """Call LLM with JSON mode and parse response.

    Returns:
        Tuple of (MatchOutput, input_tokens, output_tokens)
    """
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.ai_model,
        messages=[
            {
                "role": "system",
                "content": "Du bist ein erfahrener IT-Personalberater. Antworte immer im validen JSON-Format.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=settings.ai_temperature,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content or "{}"
    logger.debug("LLM raw response: %s", raw_content[:500])

    # Extract token usage
    input_tokens = response.usage.prompt_tokens if response.usage else 0
    output_tokens = response.usage.completion_tokens if response.usage else 0

    try:
        data = json.loads(raw_content)
        # Clamp score_breakdown values to valid ranges
        data = _clamp_score_breakdown(data)
        return MatchOutput(**data), input_tokens, output_tokens
    except json.JSONDecodeError as e:
        raise ParsingError(
            f"Invalid JSON from LLM: {e}",
            raw_output=raw_content,
            expected_schema="MatchOutput",
        ) from e
    except ValidationError as e:
        raise ParsingError(
            f"Response validation failed: {e}",
            raw_output=raw_content,
            expected_schema="MatchOutput",
        ) from e


def _apply_business_rules(
    match_output: MatchOutput,
    candidates: List[CandidateProfile],
    public_sector: bool,
    keyword_score_modifier: int = 0,
    keyword_result: Optional[KeywordScoreResult] = None,
) -> MatchResult:
    """Apply business rules and find best candidate.

    If keyword_result is provided, the skill_match component is replaced with
    the pre-calculated keyword score for consistency.
    """
    # Build adjusted score breakdown if keyword_result available
    score_breakdown = match_output.score_breakdown
    if keyword_result and score_breakdown:
        # Override skill_match with keyword score
        adjusted_breakdown = ScoreBreakdown(
            skill_match=keyword_result.total_score,
            experience=score_breakdown.experience,
            embedding=score_breakdown.embedding,
            market_fit=score_breakdown.market_fit,
            risk_factors=score_breakdown.risk_factors,
        )
        score_breakdown = adjusted_breakdown

        # Recalculate total score from breakdown
        score = (
            keyword_result.total_score +
            score_breakdown.experience +
            score_breakdown.embedding +
            score_breakdown.market_fit +
            score_breakdown.risk_factors
        )
        logger.debug(
            "Score recalculated with keyword override: %d (kw=%d, exp=%d, emb=%d, mkt=%d, risk=%d)",
            score,
            keyword_result.total_score,
            score_breakdown.experience,
            score_breakdown.embedding,
            score_breakdown.market_fit,
            score_breakdown.risk_factors,
        )
    else:
        score = match_output.score

        # Legacy keyword bonus (for backwards compatibility)
        if keyword_score_modifier > 0:
            score = min(100, score + keyword_score_modifier)
            logger.debug("Applied legacy keyword bonus: +%d", keyword_score_modifier)

    # Public sector bonus
    if public_sector:
        score = min(100, score + settings.public_sector_bonus)
        logger.debug("Applied public sector bonus: +%d", settings.public_sector_bonus)

    # Determine decision based on score thresholds
    if score >= settings.match_threshold_apply:
        decision = "apply"
    elif score >= settings.match_threshold_reject:
        decision = "review"
    else:
        decision = "reject"

    # Find best candidate by name
    best_candidate = candidates[0]  # Default to first
    for c in candidates:
        if c.name.lower() == match_output.best_candidate_name.lower():
            best_candidate = c
            break

    # Ensure proposed rate is above minimum
    proposed_rate = match_output.proposed_rate
    if proposed_rate < best_candidate.min_hourly_rate:
        proposed_rate = best_candidate.min_hourly_rate
        logger.debug(
            "Adjusted rate from %.2f to minimum %.2f",
            match_output.proposed_rate,
            proposed_rate,
        )

    return MatchResult(
        score=score,
        score_breakdown=score_breakdown,
        decision=decision,
        best_candidate_id=best_candidate.id,
        best_candidate_name=best_candidate.name,
        proposed_rate=proposed_rate,
        rate_reasoning=match_output.rate_reasoning,
        strengths=match_output.strengths,
        weaknesses=match_output.weaknesses,
        rejection_reason_code=(
            match_output.rejection_reason_code if decision == "reject" else None
        ),
        raw_analysis=json.dumps(match_output.model_dump(), ensure_ascii=False),
    )


def match_project_extended(
    project_title: str,
    project_description: str,
    project_skills: List[str] | None,
    research: ExtendedResearchResult,
    candidates: List[CandidateProfile],
    active_applications: int,
    public_sector: bool = False,
    keyword_score_modifier: int = 0,
    pdf_text: str | None = None,
    keyword_result: Optional[KeywordScoreResult] = None,
    db=None,
    project_id: Optional[int] = None,
) -> MatchResult:
    """Match a project with extended fit analysis for Bietergemeinschaft.

    This function extends the base matching with additional scoring based on:
    - Team size requirements (3-person team fit)
    - Budget limits (max €250.000)
    - Exclusion criteria (references, certifications, legal form)
    - Project type (webapp/app bonus)

    Args:
        project_title: Title of the project
        project_description: Project description
        project_skills: Required skills (if known)
        research: Extended research results with fit_analysis
        candidates: List of candidate profiles
        active_applications: Current number of active applications
        public_sector: Whether this is a public sector project
        keyword_score_modifier: Score bonus from keyword matching
        pdf_text: Extracted text from PDF documents (tender documents)
        keyword_result: Pre-calculated keyword scoring result (optional)

    Returns:
        MatchResult with decision and details
    """
    # Check for hard exclusion criteria first (before LLM call)
    fit = research.fit_analysis
    if fit:
        exclusion_result = _check_hard_exclusions(fit)
        if exclusion_result:
            logger.info(
                "Project rejected due to hard exclusion: %s",
                exclusion_result["reason_code"]
            )
            return MatchResult(
                score=0,
                decision="reject",
                best_candidate_id=candidates[0].id if candidates else 0,
                best_candidate_name=candidates[0].name if candidates else "N/A",
                proposed_rate=0.0,
                rate_reasoning="Projekt durch Ausschlusskriterium abgelehnt",
                strengths=[],
                weaknesses=exclusion_result["weaknesses"],
                rejection_reason_code=exclusion_result["reason_code"],
                raw_analysis="",
            )

    # Convert ExtendedResearchResult to ResearchResult for base matching
    base_research = ResearchResult(
        client_info=research.client_info,
        project_type=research.project_type,
        estimated_budget_range=research.estimated_budget_range,
        red_flags=research.red_flags,
        opportunities=research.opportunities,
        recommendation=research.recommendation,
        raw_analysis=research.raw_analysis,
    )

    # Call base matching
    base_result = match_project(
        project_title=project_title,
        project_description=project_description,
        project_skills=project_skills,
        research=base_research,
        candidates=candidates,
        active_applications=active_applications,
        public_sector=public_sector,
        keyword_score_modifier=keyword_score_modifier,
        pdf_text=pdf_text,
        keyword_result=keyword_result,
        db=db,
        project_id=project_id,
    )

    # Apply fit-based score adjustments
    if fit:
        adjusted_result = _apply_fit_adjustments(base_result, fit)
        return adjusted_result

    return base_result


def _check_hard_exclusions(fit: ProjectFitAnalysis) -> Optional[dict]:
    """Check for hard exclusion criteria that should auto-reject.

    Returns:
        Dict with reason_code and weaknesses if excluded, None otherwise
    """
    # Bietergemeinschaft nicht erlaubt
    if not fit.bietergemeinschaft_allowed:
        return {
            "reason_code": "BG_NOT_ALLOWED",
            "weaknesses": [
                "Bietergemeinschaft ausgeschlossen",
                fit.legal_form_details or "Nur Einzelbieter zugelassen",
            ],
        }

    # Sicherheitsüberprüfung erforderlich
    if fit.requires_security_clearance:
        return {
            "reason_code": "SECURITY_CLEARANCE",
            "weaknesses": [
                "Sicherheitsüberprüfung (Ü1/Ü2/Ü3) erforderlich",
                "Team hat keine Sicherheitsfreigabe",
            ],
        }

    # Budget deutlich über Limit (>300.000 = sicher zu groß)
    if fit.budget_exceeds_limit and fit.estimated_budget_max:
        if fit.estimated_budget_max > 300_000:
            return {
                "reason_code": "BUDGET_TOO_HIGH",
                "weaknesses": [
                    f"Budget €{fit.estimated_budget_max:,.0f} über Limit (€250.000)",
                    "Projektumfang für kleines Team nicht machbar",
                ],
            }

    # Team-Größe >5 erforderlich
    if fit.min_team_size_required > 5:
        return {
            "reason_code": "TEAM_SIZE_MISMATCH",
            "weaknesses": [
                f"Mindestens {fit.min_team_size_required} Personen erforderlich",
                "3-Personen-Team nicht ausreichend",
                fit.team_size_reasoning or "",
            ],
        }

    return None


def _apply_fit_adjustments(result: MatchResult, fit: ProjectFitAnalysis) -> MatchResult:
    """Apply score adjustments based on fit analysis.

    Args:
        result: Base match result
        fit: Fit analysis from extended research

    Returns:
        Adjusted MatchResult
    """
    score = result.score
    weaknesses = list(result.weaknesses)
    rejection_reason_code = result.rejection_reason_code

    # Team-Size-Mismatch (soft, nicht auto-reject)
    if not fit.fits_3_person_team and fit.min_team_size_required <= 5:
        score = max(0, score - FIT_SCORE_MALUS_TEAM_SIZE)
        weaknesses.append(
            f"Team-Größe kritisch: {fit.min_team_size_required} Personen empfohlen"
        )
        logger.debug("Applied team size malus: -%d", FIT_SCORE_MALUS_TEAM_SIZE)

    # Budget-Grenze (soft, wenn knapp über Limit)
    if fit.budget_exceeds_limit and fit.estimated_budget_max:
        if fit.estimated_budget_max <= 300_000:
            score = max(0, score - FIT_SCORE_MALUS_BUDGET_HIGH // 2)
            weaknesses.append(
                f"Budget €{fit.estimated_budget_max:,.0f} knapp über Limit"
            )

    # Ausschluss-Risiko
    if fit.exclusion_risk == "high":
        score = max(0, score - FIT_SCORE_MALUS_EXCLUSION_HIGH)
        weaknesses.extend(fit.exclusion_reasons[:3])
        if score < settings.match_threshold_reject and not rejection_reason_code:
            rejection_reason_code = _determine_rejection_code(fit)
        logger.debug("Applied high exclusion risk malus: -%d", FIT_SCORE_MALUS_EXCLUSION_HIGH)
    elif fit.exclusion_risk == "medium":
        score = max(0, score - FIT_SCORE_MALUS_EXCLUSION_MEDIUM)
        weaknesses.extend(fit.exclusion_reasons[:2])
        logger.debug("Applied medium exclusion risk malus: -%d", FIT_SCORE_MALUS_EXCLUSION_MEDIUM)

    # Webapp/App Bonus
    if fit.is_webapp or fit.is_mobile_app or fit.is_api_backend:
        score = min(100, score + FIT_SCORE_BONUS_WEBAPP)
        logger.debug("Applied webapp/app bonus: +%d", FIT_SCORE_BONUS_WEBAPP)

    # Recalculate decision based on adjusted score
    if score >= settings.match_threshold_apply:
        decision = "apply"
    elif score >= settings.match_threshold_reject:
        decision = "review"
    else:
        decision = "reject"

    return MatchResult(
        score=score,
        score_breakdown=result.score_breakdown,
        decision=decision,
        best_candidate_id=result.best_candidate_id,
        best_candidate_name=result.best_candidate_name,
        proposed_rate=result.proposed_rate,
        rate_reasoning=result.rate_reasoning,
        strengths=result.strengths,
        weaknesses=weaknesses,
        rejection_reason_code=rejection_reason_code if decision == "reject" else None,
        raw_analysis=result.raw_analysis,
    )


def _determine_rejection_code(fit: ProjectFitAnalysis) -> str:
    """Determine the most appropriate rejection code based on fit analysis."""
    if not fit.bietergemeinschaft_allowed:
        return "BG_NOT_ALLOWED"
    if fit.requires_security_clearance:
        return "SECURITY_CLEARANCE"
    if fit.requires_certifications:
        return "CERTIFICATION_REQUIRED"
    if fit.requires_references and fit.min_reference_count >= 3:
        return "REFERENCES_REQUIRED"
    if fit.requires_specific_legal_form:
        return "LEGAL_FORM_MISMATCH"
    if fit.min_annual_revenue or fit.min_employee_count:
        return "MIN_SIZE_NOT_MET"
    if not fit.fits_3_person_team:
        return "TEAM_SIZE_MISMATCH"
    if fit.budget_exceeds_limit:
        return "BUDGET_TOO_HIGH"
    return "PROJECT_TOO_LARGE"
