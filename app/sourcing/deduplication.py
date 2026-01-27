"""Cross-portal duplicate detection.

Detects duplicate projects across different portals based on title similarity.
This helps avoid processing the same project multiple times when it appears
on different platforms.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Project
from app.sourcing.normalize import RawProject

logger = get_logger("sourcing.deduplication")

# Similarity threshold for considering two projects as duplicates
SIMILARITY_THRESHOLD = 0.85

# Default lookback period for finding existing duplicates
DEFAULT_LOOKBACK_DAYS = 30


@dataclass
class DuplicateMatch:
    """Represents a detected duplicate match."""

    raw_project: RawProject
    existing_project: Project
    similarity: float
    matched_on: str  # "title", "external_id", "title_normalized"


def normalize_title(title: str) -> str:
    """Normalize a project title for comparison.

    Removes:
    - Long numbers (IDs, reference numbers)
    - Date patterns (dd.mm.yyyy, yyyy-mm-dd)
    - Punctuation
    - Extra whitespace

    Args:
        title: Original project title

    Returns:
        Normalized title for comparison
    """
    # Remove long numbers (likely IDs)
    title = re.sub(r"\b\d{4,}\b", "", title)

    # Remove date patterns
    title = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", "", title)
    title = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", title)

    # Remove common prefixes/suffixes that don't add meaning
    title = re.sub(r"\b(ausschreibung|vergabe|projekt|bekanntmachung)\b", "", title, flags=re.IGNORECASE)

    # Remove punctuation and special characters
    title = re.sub(r"[^\w\s]", " ", title)

    # Normalize whitespace
    title = " ".join(title.lower().split())

    return title


def calculate_title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity between two titles.

    Uses both normalized comparison and SequenceMatcher.

    Args:
        title1: First title
        title2: Second title

    Returns:
        Similarity ratio (0.0 - 1.0)
    """
    # Normalize both titles
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    # Exact normalized match
    if norm1 == norm2:
        return 1.0

    # SequenceMatcher for fuzzy matching
    return SequenceMatcher(None, norm1, norm2).ratio()


def find_cross_portal_duplicates(
    db: Session,
    raw_projects: List[RawProject],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> Tuple[List[RawProject], List[DuplicateMatch]]:
    """Find cross-portal duplicates in a list of raw projects.

    Compares incoming projects against existing projects from the last
    `lookback_days` days using title similarity matching.

    Args:
        db: Database session
        raw_projects: List of newly scraped projects
        lookback_days: How many days back to look for duplicates

    Returns:
        Tuple of (unique_projects, duplicate_matches)
        - unique_projects: Projects that are not duplicates
        - duplicate_matches: Projects that match existing entries
    """
    if not raw_projects:
        return [], []

    # Get cutoff date
    cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

    # Load existing projects from database
    existing_projects = (
        db.query(Project)
        .filter(Project.scraped_at >= cutoff_date)
        .all()
    )

    logger.info(
        "Checking %d raw projects against %d existing projects (last %d days)",
        len(raw_projects),
        len(existing_projects),
        lookback_days,
    )

    # Build lookup structures for faster matching
    external_id_map: Dict[Tuple[str, str], Project] = {}
    title_map: Dict[str, List[Project]] = {}

    for project in existing_projects:
        # External ID index (source + external_id)
        key = (project.source, project.external_id)
        external_id_map[key] = project

        # Normalized title index
        norm_title = normalize_title(project.title)
        if norm_title not in title_map:
            title_map[norm_title] = []
        title_map[norm_title].append(project)

    unique_projects: List[RawProject] = []
    duplicate_matches: List[DuplicateMatch] = []

    for raw in raw_projects:
        match = _find_match(raw, external_id_map, title_map, existing_projects)
        if match:
            duplicate_matches.append(match)
            logger.debug(
                "Duplicate found: '%s' (%s) matches '%s' (%s) - %.2f",
                raw.title[:50],
                raw.source,
                match.existing_project.title[:50],
                match.existing_project.source,
                match.similarity,
            )
        else:
            unique_projects.append(raw)

    logger.info(
        "Deduplication result: %d unique, %d duplicates",
        len(unique_projects),
        len(duplicate_matches),
    )

    return unique_projects, duplicate_matches


def _find_match(
    raw: RawProject,
    external_id_map: Dict[Tuple[str, str], Project],
    title_map: Dict[str, List[Project]],
    all_projects: List[Project],
) -> Optional[DuplicateMatch]:
    """Find a matching existing project for a raw project.

    Args:
        raw: Raw project to check
        external_id_map: Map of (source, external_id) -> Project
        title_map: Map of normalized_title -> List[Project]
        all_projects: All existing projects for fuzzy matching

    Returns:
        DuplicateMatch if found, None otherwise
    """
    # 1. Exact external_id match (same source)
    key = (raw.source, raw.external_id)
    if key in external_id_map:
        return DuplicateMatch(
            raw_project=raw,
            existing_project=external_id_map[key],
            similarity=1.0,
            matched_on="external_id",
        )

    # 2. Exact normalized title match
    norm_title = normalize_title(raw.title)
    if norm_title in title_map:
        # Return first match (preferring same source if available)
        matches = title_map[norm_title]
        same_source = [p for p in matches if p.source == raw.source]
        if same_source:
            return DuplicateMatch(
                raw_project=raw,
                existing_project=same_source[0],
                similarity=1.0,
                matched_on="title_normalized",
            )
        return DuplicateMatch(
            raw_project=raw,
            existing_project=matches[0],
            similarity=1.0,
            matched_on="title_normalized",
        )

    # 3. Fuzzy title matching (only if title is long enough)
    if len(norm_title) >= 20:
        best_match: Optional[Project] = None
        best_similarity = 0.0

        for project in all_projects:
            # Skip same source (already checked via external_id)
            if project.source == raw.source:
                continue

            similarity = calculate_title_similarity(raw.title, project.title)
            if similarity >= SIMILARITY_THRESHOLD and similarity > best_similarity:
                best_match = project
                best_similarity = similarity

        if best_match:
            return DuplicateMatch(
                raw_project=raw,
                existing_project=best_match,
                similarity=best_similarity,
                matched_on="title",
            )

    return None


def get_duplicate_statistics(db: Session, lookback_days: int = 30) -> Dict:
    """Get statistics about duplicate detection.

    Args:
        db: Database session
        lookback_days: Days to analyze

    Returns:
        Dict with statistics
    """
    cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

    # Count projects per source
    projects = (
        db.query(Project)
        .filter(Project.scraped_at >= cutoff_date)
        .all()
    )

    source_counts: Dict[str, int] = {}
    for p in projects:
        source_counts[p.source] = source_counts.get(p.source, 0) + 1

    # Find potential cross-portal duplicates
    title_groups: Dict[str, List[Project]] = {}
    for p in projects:
        norm_title = normalize_title(p.title)
        if norm_title not in title_groups:
            title_groups[norm_title] = []
        title_groups[norm_title].append(p)

    # Count cross-portal duplicates (same title, different sources)
    cross_portal_dupes = 0
    for title, group in title_groups.items():
        sources = set(p.source for p in group)
        if len(sources) > 1:
            cross_portal_dupes += len(group) - 1

    return {
        "total_projects": len(projects),
        "projects_per_source": source_counts,
        "unique_titles": len(title_groups),
        "potential_cross_portal_duplicates": cross_portal_dupes,
        "lookback_days": lookback_days,
    }
