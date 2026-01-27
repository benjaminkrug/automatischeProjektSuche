"""Embedding-based search using pgvector."""

from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.schemas import CandidateProfile
from app.core.logging import get_logger
from app.db.models import TeamMember
from app.services.embedding_service import create_embedding

logger = get_logger("ai.embedding_search")


def find_top_matching_members(
    db: Session,
    description: str,
    limit: int = 3,
) -> List[Tuple[TeamMember, float]]:
    """Find top matching team members using embedding similarity.

    Uses pgvector's cosine distance operator for efficient vector search.

    Args:
        db: Database session
        description: Project description to match against
        limit: Maximum number of candidates to return

    Returns:
        List of (TeamMember, similarity_score) tuples sorted by similarity
    """
    # Create embedding for the project description
    logger.debug("Creating embedding for project description...")
    query_embedding = create_embedding(description)

    # Query using pgvector cosine distance
    # The <=> operator computes cosine distance (1 - cosine_similarity)
    results = db.execute(
        text(
            """
            SELECT
                id,
                name,
                role,
                skills,
                years_experience,
                min_hourly_rate,
                cv_path,
                active,
                1 - (profile_embedding <=> :embedding) as similarity
            FROM team_members
            WHERE active = true
              AND profile_embedding IS NOT NULL
            ORDER BY profile_embedding <=> :embedding
            LIMIT :limit
        """
        ),
        {"embedding": str(query_embedding), "limit": limit},
    ).fetchall()

    logger.debug("Found %d matching team members", len(results))

    # Return (TeamMember, similarity_score) tuples
    members_with_scores = []
    for row in results:
        member = (
            db.query(TeamMember).filter(TeamMember.id == row.id).first()
        )
        if member:
            similarity = float(row.similarity) if row.similarity else 0.0
            members_with_scores.append((member, similarity))
            logger.debug(
                "  %s: similarity=%.3f", member.name, similarity
            )

    return members_with_scores


def find_similar_projects(
    db: Session,
    project_id: int,
    limit: int = 5,
) -> List[int]:
    """Find similar projects based on description embedding.

    Args:
        db: Database session
        project_id: ID of the reference project
        limit: Maximum number of similar projects to return

    Returns:
        List of similar project IDs
    """
    # This would require project embeddings - placeholder for future extension
    # For now, return empty list
    logger.debug("find_similar_projects not yet implemented")
    return []
