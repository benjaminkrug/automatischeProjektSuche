"""AI service for research and matching operations."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

from app.ai.keyword_scoring import KeywordScoreResult
from app.ai.matcher import match_project
from app.ai.researcher import research_client
from app.ai.schemas import CandidateProfile, MatchResult, ResearchResult
from app.core.exceptions import AIProcessingError
from app.core.logging import get_logger
from app.db.models import TeamMember
from app.settings import Settings, settings as default_settings

if TYPE_CHECKING:
    from app.services.client_research_service import ClientResearch

logger = get_logger("services.ai")


class AIService:
    """Service for AI-powered research and matching operations."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize AI service.

        Args:
            settings: Optional settings instance
        """
        self._settings = settings or default_settings

    def research_project(
        self,
        title: str,
        client_name: Optional[str],
        description: Optional[str],
        external_data: Optional[ClientResearch] = None,
    ) -> ResearchResult:
        """Research a project and client.

        Args:
            title: Project title
            client_name: Client name
            description: Project description
            external_data: Optional external research from web scraping

        Returns:
            ResearchResult with analysis
        """
        logger.info("Researching project: %s", title[:50])
        if external_data:
            logger.debug(
                "Using external data: website=%s, rating=%s",
                "yes" if external_data.website else "no",
                external_data.kununu_rating,
            )
        return research_client(title, client_name, description, external_data)

    def match_project_to_team(
        self,
        project_title: str,
        project_description: str,
        project_skills: Optional[List[str]],
        research: ResearchResult,
        candidates: List[CandidateProfile],
        active_applications: int,
        public_sector: bool = False,
        keyword_score_modifier: int = 0,
        pdf_text: Optional[str] = None,
        keyword_result: Optional[KeywordScoreResult] = None,
    ) -> MatchResult:
        """Match a project against team candidates.

        Args:
            project_title: Project title
            project_description: Project description
            project_skills: Required skills
            research: Research results
            candidates: List of candidate profiles
            active_applications: Current active application count
            public_sector: Whether this is public sector
            keyword_score_modifier: Score bonus from keyword matching (legacy)
            pdf_text: Extracted text from PDF documents (tender documents)
            keyword_result: Pre-calculated keyword scoring result

        Returns:
            MatchResult with decision
        """
        logger.info("Matching project: %s", project_title[:50])
        if pdf_text:
            logger.debug("Including PDF text (%d chars)", len(pdf_text))
        if keyword_result:
            logger.debug(
                "Using keyword score: %d/40 [%s]",
                keyword_result.total_score,
                keyword_result.confidence,
            )
        return match_project(
            project_title=project_title,
            project_description=project_description,
            project_skills=project_skills,
            research=research,
            candidates=candidates,
            active_applications=active_applications,
            public_sector=public_sector,
            keyword_score_modifier=keyword_score_modifier,
            pdf_text=pdf_text,
            keyword_result=keyword_result,
        )

    def create_candidate_profiles(
        self,
        members: List[TeamMember],
        embedding_scores: Optional[List[float]] = None,
    ) -> List[CandidateProfile]:
        """Convert TeamMember objects to CandidateProfile for matching.

        Args:
            members: List of team members
            embedding_scores: Optional embedding similarity scores

        Returns:
            List of CandidateProfile objects
        """
        if embedding_scores is None:
            embedding_scores = [0.0] * len(members)

        profiles = []
        for member, score in zip(members, embedding_scores):
            profile = CandidateProfile(
                id=member.id,
                name=member.name,
                role=member.role or "Softwareentwickler",
                skills=member.skills or [],
                years_experience=member.years_experience or 0,
                min_hourly_rate=member.min_hourly_rate or 80.0,
                embedding_score=score,
            )
            profiles.append(profile)

        return profiles


# Default instance for convenience
_default_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get default AI service instance."""
    global _default_service
    if _default_service is None:
        _default_service = AIService()
    return _default_service
