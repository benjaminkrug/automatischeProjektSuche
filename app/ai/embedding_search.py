"""Embedding-based search using pgvector."""

from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.schemas import CandidateProfile
from app.core.logging import get_logger
from app.db.models import TeamMember
from app.services.embedding_service import create_embedding

logger = get_logger("ai.embedding_search")

# Minimum embedding similarity threshold (25%)
# Candidates below this threshold are considered weak matches and skipped
MIN_EMBEDDING_SIMILARITY = 0.25


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
    # Q1 Fix: Construct TeamMember directly from row to avoid N+1 queries
    # Q2 Fix: Apply minimum similarity threshold to skip weak matches
    members_with_scores = []
    for row in results:
        similarity = float(row.similarity) if row.similarity else 0.0

        # Q2: Skip weak matches below threshold
        if similarity < MIN_EMBEDDING_SIMILARITY:
            logger.debug(
                "Skipping weak match: %s (%.3f < %.3f threshold)",
                row.name,
                similarity,
                MIN_EMBEDDING_SIMILARITY,
            )
            continue

        # Q1 Fix: Construct TeamMember directly from SQL result
        # This avoids N separate queries for each result
        member = TeamMember(
            id=row.id,
            name=row.name,
            role=row.role,
            skills=row.skills,
            years_experience=row.years_experience,
            min_hourly_rate=row.min_hourly_rate,
            cv_path=row.cv_path,
            active=row.active,
        )
        members_with_scores.append((member, similarity))
        logger.debug("  %s: similarity=%.3f", member.name, similarity)

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
