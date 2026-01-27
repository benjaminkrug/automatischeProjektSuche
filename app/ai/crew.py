"""CrewAI agent factory and configuration.

Note: This module is deprecated for new code. Use app.ai.matcher and
app.ai.researcher directly with structured JSON outputs instead.
"""

from crewai import Agent, LLM

from app.core.logging import get_logger
from app.settings import settings

logger = get_logger("ai.crew")


def get_llm() -> LLM:
    """Get configured LLM instance for agents.

    Returns:
        Configured CrewAI LLM instance
    """
    return LLM(
        model=settings.ai_model,
        api_key=settings.openai_api_key,
        temperature=settings.ai_temperature,
    )


def create_researcher_agent() -> Agent:
    """Create agent for client/project research.

    Deprecated: Use app.ai.researcher.research_client() instead.

    Returns:
        Configured CrewAI Agent for research
    """
    logger.debug("Creating researcher agent (deprecated - use structured outputs)")
    return Agent(
        role="Kundenrechercheur",
        goal="Recherchiere Informationen über Kunden und Projekte für eine fundierte Bewertung",
        backstory="""Du bist ein erfahrener Analyst für IT-Projekte im deutschen Markt.
        Du recherchierst Auftraggeber, bewertest deren Bonität und Seriosität,
        und identifizierst potenzielle Risiken oder Chancen für Freelancer.""",
        llm=get_llm(),
        verbose=False,
        allow_delegation=False,
    )


def create_matcher_agent() -> Agent:
    """Create agent for project-team matching.

    Deprecated: Use app.ai.matcher.match_project() instead.

    Returns:
        Configured CrewAI Agent for matching
    """
    logger.debug("Creating matcher agent (deprecated - use structured outputs)")
    return Agent(
        role="Projektmatcher",
        goal="Bewerte die Passung zwischen IT-Projekten und Freelancer-Profilen",
        backstory="""Du bist ein erfahrener IT-Personalberater mit tiefem Verständnis
        für Technologie-Stacks, Projektanforderungen und Freelancer-Fähigkeiten.
        Du bewertest objektiv die Erfolgswahrscheinlichkeit von Bewerbungen
        basierend auf technischen Skills, Erfahrung und Projektkontext.""",
        llm=get_llm(),
        verbose=False,
        allow_delegation=False,
    )
