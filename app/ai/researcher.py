"""Client research using structured LLM outputs."""

from __future__ import annotations

import json
from typing import Optional, TYPE_CHECKING

from openai import OpenAI
from pydantic import ValidationError

from app.ai.cost_tracking import log_ai_usage
from app.ai.retry import llm_retry
from app.ai.schemas import (
    ExtendedResearchOutput,
    ExtendedResearchResult,
    MAX_BUDGET_LIMIT,
    ProjectFitAnalysis,
    ResearchOutput,
    ResearchResult,
)
from app.core.exceptions import AIProcessingError, ParsingError
from app.core.logging import get_logger
from app.settings import settings

if TYPE_CHECKING:
    from app.services.client_research_service import ClientResearch

logger = get_logger("ai.researcher")


def research_client(
    title: str,
    client_name: Optional[str],
    description: Optional[str],
    external_data: Optional[ClientResearch] = None,
    db=None,
    project_id: Optional[int] = None,
) -> ResearchResult:
    """Research a client and project for informed decision making.

    Args:
        title: Project title
        client_name: Name of the client/organization
        description: Project description
        external_data: Optional external research data from web scraping
        db: Optional database session for cost tracking
        project_id: Optional project ID for cost tracking

    Returns:
        ResearchResult with analysis

    Raises:
        AIProcessingError: If LLM call fails
        ParsingError: If response parsing fails
    """
    prompt = _build_research_prompt(title, client_name, description, external_data)

    try:
        research_output, input_tokens, output_tokens = _call_llm_structured(prompt)

        # Log AI usage if database session provided
        if db is not None:
            log_ai_usage(
                db=db,
                operation="research",
                model=settings.ai_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                project_id=project_id,
            )
    except Exception as e:
        logger.error("Research LLM call failed: %s", e)
        raise AIProcessingError(
            f"Research LLM call failed: {e}",
            model=settings.ai_model,
            prompt_preview=prompt[:200],
        ) from e

    return ResearchResult(
        client_info=research_output.client_info,
        project_type=research_output.project_type,
        estimated_budget_range=research_output.estimated_budget_range,
        red_flags=research_output.red_flags,
        opportunities=research_output.opportunities,
        recommendation=research_output.recommendation,
        raw_analysis=json.dumps(research_output.model_dump(), ensure_ascii=False),
    )


def _build_research_prompt(
    title: str,
    client_name: Optional[str],
    description: Optional[str],
    external_data: Optional[ClientResearch] = None,
) -> str:
    """Build the research prompt."""
    prompt = f"""Analysiere das folgende IT-Projekt.

PROJEKT
=======
Titel: {title}
Auftraggeber: {client_name or 'Nicht angegeben'}
Beschreibung: {description or 'Keine Beschreibung verfügbar'}"""

    # Add external research data if available
    if external_data and _has_external_data(external_data):
        prompt += """

EXTERNE RECHERCHE
================="""
        if external_data.website:
            prompt += f"\nUnternehmenswebseite: {external_data.website}"
        if external_data.about_text:
            # Truncate about text to avoid token limits
            about_preview = external_data.about_text[:1000]
            if len(external_data.about_text) > 1000:
                about_preview += "..."
            prompt += f"\nÜber das Unternehmen: {about_preview}"
        if external_data.hrb_number:
            prompt += f"\nHandelsregister: {external_data.hrb_number}"
        if external_data.founding_year:
            prompt += f"\nGründungsjahr: {external_data.founding_year}"
        if external_data.employee_count:
            prompt += f"\nMitarbeiter: {external_data.employee_count}"
        if external_data.kununu_rating:
            prompt += f"\nKununu-Bewertung: {external_data.kununu_rating}/5"

    prompt += """

ANALYSIERE FOLGENDES
====================
1. Kundeninformation: Was ist über den Auftraggeber bekannt? (Branche, Größe, Reputation)
2. Projekttyp: Welche Art von Projekt ist das? (Neuentwicklung, Wartung, Beratung, Migration)
3. Budget-Einschätzung: Geschätzter Budgetrahmen basierend auf Projektkomplexität
4. Red Flags: Potenzielle Risiken oder Warnsignale (max 5)
5. Chancen: Besondere Vorteile oder Möglichkeiten (max 5)
6. Empfehlung: Kurze Empfehlung zur Bewerbung

Antworte im JSON-Format mit folgenden Feldern:
- client_info: String mit Kundeninformationen
- project_type: String mit Projekttyp
- estimated_budget_range: String mit Budget-Einschätzung
- red_flags: Array von Strings (Risiken/Warnsignale)
- opportunities: Array von Strings (Chancen/Vorteile)
- recommendation: String mit Empfehlung

Antworte NUR mit dem JSON-Objekt, ohne zusätzlichen Text."""

    return prompt


def _has_external_data(external_data: Optional[ClientResearch]) -> bool:
    """Check if external data contains any useful information."""
    if not external_data:
        return False

    return any([
        external_data.website,
        external_data.about_text,
        external_data.hrb_number,
        external_data.founding_year,
        external_data.employee_count,
        external_data.kununu_rating,
    ])


@llm_retry
def _call_llm_structured(prompt: str) -> tuple[ResearchOutput, int, int]:
    """Call LLM with JSON mode and parse response.

    Returns:
        Tuple of (ResearchOutput, input_tokens, output_tokens)
    """
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.ai_model,
        messages=[
            {
                "role": "system",
                "content": "Du bist ein erfahrener Analyst für IT-Projekte im deutschen Markt. Antworte immer im validen JSON-Format.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=settings.ai_temperature,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content or "{}"
    logger.debug("Research LLM raw response: %s", raw_content[:500])

    # Extract token usage
    input_tokens = response.usage.prompt_tokens if response.usage else 0
    output_tokens = response.usage.completion_tokens if response.usage else 0

    try:
        data = json.loads(raw_content)
        return ResearchOutput(**data), input_tokens, output_tokens
    except json.JSONDecodeError as e:
        raise ParsingError(
            f"Invalid JSON from LLM: {e}",
            raw_output=raw_content,
            expected_schema="ResearchOutput",
        ) from e
    except ValidationError as e:
        raise ParsingError(
            f"Response validation failed: {e}",
            raw_output=raw_content,
            expected_schema="ResearchOutput",
        ) from e


def research_client_extended(
    title: str,
    client_name: Optional[str],
    description: Optional[str],
    external_data: Optional[ClientResearch] = None,
    db=None,
    project_id: Optional[int] = None,
) -> ExtendedResearchResult:
    """Erweiterte Analyse für Bietergemeinschaft-Eignung.

    Führt zusätzlich zur Basis-Analyse eine detaillierte Prüfung durch:
    - Budget-Schätzung (explizit oder geschätzt)
    - Team-Größen-Eignung (passt für 3-Personen-Team?)
    - Projekttyp-Klassifizierung (Webapp, App, Backend, etc.)
    - Ausschlusskriterien (Referenzen, Zertifizierungen, Rechtsform)

    Args:
        title: Project title
        client_name: Name of the client/organization
        description: Project description
        external_data: Optional external research data from web scraping
        db: Optional database session for cost tracking
        project_id: Optional project ID for cost tracking

    Returns:
        ExtendedResearchResult with basis and fit analysis

    Raises:
        AIProcessingError: If LLM call fails
        ParsingError: If response parsing fails
    """
    prompt = _build_extended_research_prompt(title, client_name, description, external_data)

    try:
        research_output, input_tokens, output_tokens = _call_llm_extended(prompt)

        # Log AI usage if database session provided
        if db is not None:
            log_ai_usage(
                db=db,
                operation="research_extended",
                model=settings.ai_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                project_id=project_id,
            )
    except Exception as e:
        logger.error("Extended research LLM call failed: %s", e)
        raise AIProcessingError(
            f"Extended research LLM call failed: {e}",
            model=settings.ai_model,
            prompt_preview=prompt[:200],
        ) from e

    return ExtendedResearchResult(
        client_info=research_output.client_info,
        project_type=research_output.project_type,
        estimated_budget_range=research_output.estimated_budget_range,
        red_flags=research_output.red_flags,
        opportunities=research_output.opportunities,
        recommendation=research_output.recommendation,
        raw_analysis=json.dumps(research_output.model_dump(), ensure_ascii=False),
        fit_analysis=research_output.fit_analysis,
    )


def _build_extended_research_prompt(
    title: str,
    client_name: Optional[str],
    description: Optional[str],
    external_data: Optional[ClientResearch] = None,
) -> str:
    """Build the extended research prompt with fit analysis."""
    prompt = f"""Analysiere das folgende IT-Projekt für eine kleine 3-Personen-Bietergemeinschaft.

PROJEKT
=======
Titel: {title}
Auftraggeber: {client_name or 'Nicht angegeben'}
Beschreibung: {description or 'Keine Beschreibung verfügbar'}"""

    # Add external research data if available
    if external_data and _has_external_data(external_data):
        prompt += """

EXTERNE RECHERCHE
================="""
        if external_data.website:
            prompt += f"\nUnternehmenswebseite: {external_data.website}"
        if external_data.about_text:
            about_preview = external_data.about_text[:1000]
            if len(external_data.about_text) > 1000:
                about_preview += "..."
            prompt += f"\nÜber das Unternehmen: {about_preview}"
        if external_data.hrb_number:
            prompt += f"\nHandelsregister: {external_data.hrb_number}"
        if external_data.founding_year:
            prompt += f"\nGründungsjahr: {external_data.founding_year}"
        if external_data.employee_count:
            prompt += f"\nMitarbeiter: {external_data.employee_count}"
        if external_data.kununu_rating:
            prompt += f"\nKununu-Bewertung: {external_data.kununu_rating}/5"

    prompt += f"""

ANALYSIERE FOLGENDES
====================

TEIL 1: BASIS-ANALYSE
---------------------
1. Kundeninformation: Was ist über den Auftraggeber bekannt? (Branche, Größe, Reputation)
2. Projekttyp: Welche Art von Projekt ist das? (Neuentwicklung, Wartung, Beratung, Migration)
3. Budget-Einschätzung: Geschätzter Budgetrahmen basierend auf Projektkomplexität
4. Red Flags: Potenzielle Risiken oder Warnsignale (max 5)
5. Chancen: Besondere Vorteile oder Möglichkeiten (max 5)
6. Empfehlung: Kurze Empfehlung zur Bewerbung

TEIL 2: PROJEKT-EIGNUNG FÜR KLEINE FIRMA (3-PERSONEN-TEAM)
----------------------------------------------------------
A) Budget (EUR):
   - Wenn explizit genannt: Min und Max extrahieren (budget_source: "explicit")
   - Wenn NICHT genannt: Schätzen basierend auf (budget_source: "estimated"):
     * Projektumfang/Komplexität
     * Anzahl genannter Module/Features
     * Zeitrahmen falls genannt
     * Vergleichbare Projekterfahrung
   - Budget-Limit: Max €{MAX_BUDGET_LIMIT:,} (größere Projekte ablehnen)
   - budget_exceeds_limit: true wenn geschätztes Budget > €{MAX_BUDGET_LIMIT:,}

B) Geschätzter Aufwand:
   - estimated_hours: Gesamtstunden-Schätzung
   - estimated_duration_months: Projektdauer in Monaten

C) Team-Größe:
   - min_team_size_required: Wie viele Personen minimal parallel nötig? (1, 2, 3, 5, 10)
   - fits_3_person_team: true/false - Kann ein 3-Personen-Team das Projekt stemmen?
   - parallel_workstreams: Wie viele parallele Arbeitsstränge?
   - team_size_reasoning: Kurze Begründung

D) Projekttyp-Klassifizierung:
   - is_webapp: Ist es eine Webanwendung/Webportal?
   - is_mobile_app: Ist es eine Mobile App (iOS/Android)?
   - is_api_backend: Ist es ein API/Backend-Projekt?
   - is_infrastructure: Ist es ein Infrastruktur/DevOps-Projekt?

TEIL 3: AUSSCHLUSSKRITERIEN (BIETERGEMEINSCHAFT)
------------------------------------------------
Analysiere den Text auf folgende Barrieren:

A) Referenzen:
   - requires_references: Werden Referenzprojekte verlangt?
   - min_reference_count: Wie viele Referenzen werden gefordert?

B) Zertifizierungen:
   - requires_certifications: Liste der geforderten Zertifizierungen
     (z.B. ISO 27001, BSI-Grundschutz, TISAX, ISO 9001)

C) Sicherheitsüberprüfung:
   - requires_security_clearance: Wird Ü1, Ü2, Ü3, NATO-Clearance verlangt?

D) Rechtsform:
   - requires_specific_legal_form: Wird GmbH, AG verlangt oder ist BG ausgeschlossen?
   - legal_form_details: Details (z.B. "nur GmbH", "keine Bietergemeinschaft")
   - bietergemeinschaft_allowed: true/false

E) Mindestgröße:
   - min_annual_revenue: Geforderter Mindestumsatz in EUR (null wenn nicht genannt)
   - min_employee_count: Geforderte Mindestmitarbeiterzahl (null wenn nicht genannt)

F) Risiko-Bewertung:
   - exclusion_risk: "low" / "medium" / "high"
     * low: Keine Barrieren erkennbar
     * medium: Einige Anforderungen, aber möglicherweise erfüllbar
     * high: Klare Ausschlusskriterien vorhanden
   - exclusion_reasons: Liste der gefundenen Barrieren als Strings

Antworte im JSON-Format mit folgender Struktur:
{{
  "client_info": "...",
  "project_type": "...",
  "estimated_budget_range": "...",
  "red_flags": ["...", "..."],
  "opportunities": ["...", "..."],
  "recommendation": "...",
  "fit_analysis": {{
    "estimated_budget_min": 50000,
    "estimated_budget_max": 100000,
    "budget_source": "estimated",
    "estimated_hours": 800,
    "estimated_duration_months": 6,
    "budget_exceeds_limit": false,
    "min_team_size_required": 2,
    "fits_3_person_team": true,
    "parallel_workstreams": 2,
    "team_size_reasoning": "...",
    "is_webapp": true,
    "is_mobile_app": false,
    "is_api_backend": true,
    "is_infrastructure": false,
    "requires_references": true,
    "min_reference_count": 2,
    "requires_certifications": [],
    "requires_security_clearance": false,
    "requires_specific_legal_form": false,
    "legal_form_details": "",
    "bietergemeinschaft_allowed": true,
    "min_annual_revenue": null,
    "min_employee_count": null,
    "exclusion_risk": "medium",
    "exclusion_reasons": ["2 Referenzprojekte erforderlich"]
  }}
}}

Antworte NUR mit dem JSON-Objekt, ohne zusätzlichen Text."""

    return prompt


@llm_retry
def _call_llm_extended(prompt: str) -> tuple[ExtendedResearchOutput, int, int]:
    """Call LLM with JSON mode for extended analysis and parse response.

    Returns:
        Tuple of (ExtendedResearchOutput, input_tokens, output_tokens)
    """
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.ai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein erfahrener Analyst für IT-Ausschreibungen im deutschen öffentlichen Sektor. "
                    "Du analysierst Projekte für eine kleine 3-Personen-Bietergemeinschaft (Freelancer-Team). "
                    "Sei kritisch bei der Bewertung von Ausschlusskriterien - lieber einmal mehr auf Barrieren "
                    "hinweisen als wichtige Einschränkungen zu übersehen. "
                    "Antworte immer im validen JSON-Format."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=settings.ai_temperature,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content or "{}"
    logger.debug("Extended research LLM raw response: %s", raw_content[:500])

    # Extract token usage
    input_tokens = response.usage.prompt_tokens if response.usage else 0
    output_tokens = response.usage.completion_tokens if response.usage else 0

    try:
        data = json.loads(raw_content)
        return ExtendedResearchOutput(**data), input_tokens, output_tokens
    except json.JSONDecodeError as e:
        raise ParsingError(
            f"Invalid JSON from LLM: {e}",
            raw_output=raw_content,
            expected_schema="ExtendedResearchOutput",
        ) from e
    except ValidationError as e:
        raise ParsingError(
            f"Response validation failed: {e}",
            raw_output=raw_content,
            expected_schema="ExtendedResearchOutput",
        ) from e
