"""Normalize and deduplicate scraped projects."""

from datetime import datetime
from typing import List, Set, Tuple

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Project
from app.sourcing.base import RawProject

logger = get_logger("sourcing.normalize")


def normalize_project(raw: RawProject) -> dict:
    """Convert RawProject to dict for Project model.

    Args:
        raw: Raw project from scraper

    Returns:
        Dict with fields matching Project model
    """
    return {
        "source": raw.source,
        "external_id": raw.external_id,
        "url": raw.url,
        "title": raw.title,
        "client_name": raw.client_name,
        "description": raw.description,
        "skills": raw.skills if raw.skills else None,
        "budget": raw.budget,
        "location": raw.location,
        "remote": raw.remote,
        "public_sector": raw.public_sector,
        "status": "new",
        "scraped_at": raw.scraped_at or datetime.utcnow(),
        # PDF analysis fields
        "pdf_text": raw.pdf_text,
        "pdf_count": len(raw.pdf_urls) if raw.pdf_urls else 0,
    }


def dedupe_projects(db: Session, raw_projects: List[RawProject]) -> List[RawProject]:
    """Filter out projects that already exist in database.

    Uses (source, external_id) unique constraint for deduplication.
    Optimized: Uses single batch query instead of N individual queries.

    Args:
        db: Database session
        raw_projects: List of raw projects from scraper

    Returns:
        List of new projects not yet in database
    """
    if not raw_projects:
        return []

    # Build list of (source, external_id) pairs to check
    pairs_to_check: List[Tuple[str, str]] = [
        (raw.source, raw.external_id) for raw in raw_projects
    ]

    # Single batch query to find all existing pairs
    existing_query = db.query(Project.source, Project.external_id).filter(
        tuple_(Project.source, Project.external_id).in_(pairs_to_check)
    )
    existing_pairs: Set[Tuple[str, str]] = set(existing_query.all())

    logger.debug(
        "Deduplication: %d candidates, %d already exist",
        len(pairs_to_check),
        len(existing_pairs),
    )

    # Filter to only new projects
    new_projects = [
        raw
        for raw in raw_projects
        if (raw.source, raw.external_id) not in existing_pairs
    ]

    return new_projects


def save_projects(db: Session, raw_projects: List[RawProject]) -> List[Project]:
    """Save raw projects to database after normalization and deduplication.

    Args:
        db: Database session
        raw_projects: List of raw projects from scraper

    Returns:
        List of saved Project objects
    """
    new_projects = dedupe_projects(db, raw_projects)

    if not new_projects:
        logger.debug("No new projects to save after deduplication")
        return []

    saved = []
    for raw in new_projects:
        project_data = normalize_project(raw)
        project = Project(**project_data)
        db.add(project)
        saved.append(project)

    if saved:
        db.commit()
        for p in saved:
            db.refresh(p)
        logger.info("Saved %d new projects to database", len(saved))

    return saved
