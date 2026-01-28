"""Normalize and deduplicate scraped projects."""

from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Project, ScraperRun
from app.sourcing.base import RawProject

logger = get_logger("sourcing.normalize")


def get_last_run_time(db: Session, portal: str) -> Optional[datetime]:
    """Get the last successful run time for a portal.

    Args:
        db: Database session
        portal: Portal name (e.g., 'bund.de', 'dtvp')

    Returns:
        Datetime of last successful run, or None if never run
    """
    last_run = (
        db.query(ScraperRun)
        .filter(
            ScraperRun.portal == portal,
            ScraperRun.status == "success",
        )
        .order_by(ScraperRun.completed_at.desc())
        .first()
    )
    return last_run.completed_at if last_run else None


def record_scraper_run(
    db: Session,
    portal: str,
    projects_found: int = 0,
    new_projects: int = 0,
    duplicates: int = 0,
    filtered_old: int = 0,
    status: str = "success",
    error_details: str = None,
) -> ScraperRun:
    """Record a scraper run in the database.

    Args:
        db: Database session
        portal: Portal name
        projects_found: Total projects found
        new_projects: New projects saved
        duplicates: Duplicate projects skipped
        filtered_old: Projects filtered because they were published before last run
        status: Run status (success, error)
        error_details: Error details if status is error

    Returns:
        ScraperRun object
    """
    run = ScraperRun(
        portal=portal,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        status=status,
        projects_found=projects_found,
        new_projects=new_projects,
        duplicates=duplicates,
        error_details=error_details,
    )
    db.add(run)
    db.commit()
    return run


def normalize_project(raw: RawProject) -> dict:
    """Convert RawProject to dict for Project model.

    Args:
        raw: Raw project from scraper

    Returns:
        Dict with fields matching Project model
    """
    data = {
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
        # Publication date
        "published_at": getattr(raw, "published_at", None),
        # PDF analysis fields
        "pdf_text": raw.pdf_text,
        "pdf_count": len(raw.pdf_urls) if raw.pdf_urls else 0,
        # Project type
        "project_type": getattr(raw, "project_type", "freelance"),
    }

    # Add tender-specific fields if present
    if hasattr(raw, "cpv_codes") and raw.cpv_codes:
        data["cpv_codes"] = raw.cpv_codes
    if hasattr(raw, "budget_min") and raw.budget_min:
        data["budget_min"] = raw.budget_min
    if hasattr(raw, "budget_max") and raw.budget_max:
        data["budget_max"] = raw.budget_max

    # Map deadline to tender_deadline (scrapers use "deadline", DB uses "tender_deadline")
    tender_deadline = getattr(raw, "tender_deadline", None) or getattr(raw, "deadline", None)
    if tender_deadline:
        data["tender_deadline"] = tender_deadline

    return data


def filter_old_projects(
    db: Session,
    raw_projects: List[RawProject],
    portal: str,
) -> Tuple[List[RawProject], int]:
    """Filter out projects published before the last scraper run.

    Args:
        db: Database session
        raw_projects: List of raw projects from scraper
        portal: Portal name for looking up last run

    Returns:
        Tuple of (filtered projects, count of filtered out)
    """
    if not raw_projects:
        return [], 0

    last_run = get_last_run_time(db, portal)

    if not last_run:
        # First run - keep all projects
        logger.info("First run for %s - no date filter applied", portal)
        return raw_projects, 0

    # Normalize to day start for gap-free filtering
    last_run_day_start = datetime.combine(last_run.date(), datetime.min.time())

    logger.info("Last run for %s: %s (using day start)", portal, last_run_day_start.strftime("%Y-%m-%d"))

    filtered = []
    filtered_count = 0

    for project in raw_projects:
        published = getattr(project, "published_at", None)

        if published is None:
            # No publication date - keep the project (will be deduped later if exists)
            filtered.append(project)
        elif published >= last_run_day_start:
            # Published on or after last run day - keep
            filtered.append(project)
        else:
            # Published before last run day - skip
            filtered_count += 1
            logger.debug(
                "Filtered old project: %s (published %s, last run day %s)",
                project.title[:40],
                published.strftime("%Y-%m-%d"),
                last_run_day_start.strftime("%Y-%m-%d"),
            )

    if filtered_count > 0:
        logger.info(
            "Filtered %d old projects (published before %s)",
            filtered_count,
            last_run_day_start.strftime("%Y-%m-%d"),
        )

    return filtered, filtered_count


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
