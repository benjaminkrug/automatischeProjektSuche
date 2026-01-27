"""AI module - structured LLM outputs and embedding search."""

from app.ai.schemas import (
    CandidateProfile,
    MatchOutput,
    MatchResult,
    ResearchOutput,
    ResearchResult,
)
from app.ai.researcher import research_client
from app.ai.matcher import match_project
from app.ai.embedding_search import find_top_matching_members

__all__ = [
    # Schemas
    "CandidateProfile",
    "MatchOutput",
    "MatchResult",
    "ResearchOutput",
    "ResearchResult",
    # Functions
    "research_client",
    "match_project",
    "find_top_matching_members",
]
