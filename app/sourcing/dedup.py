"""Cross-source deduplication for tenders appearing on multiple portals.

The same tender often appears on multiple platforms (bund.de, TED, DTVP)
with different IDs. This module detects these duplicates using fuzzy
matching on title, client, and deadline.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple, Dict

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Project

logger = get_logger("sourcing.dedup")

# Similarity threshold for title matching (0.0 - 1.0)
TITLE_SIMILARITY_THRESHOLD = 0.8

# Maximum days difference for deadline matching
DEADLINE_TOLERANCE_DAYS = 3


@dataclass
class DuplicateGroup:
    """Group of duplicate projects from different sources."""

    primary_id: int  # Oldest project ID (kept as primary)
    duplicate_ids: List[int]  # Newer duplicates
    confidence: float  # Match confidence (0.0 - 1.0)
    match_reasons: List[str]  # Why these were matched


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Args:
        text: Raw text

    Returns:
        Normalized text (lowercase, no special chars, no extra whitespace)
    """
    if not text:
        return ""

    # Lowercase
    text = text.lower()

    # Remove accents/umlauts for comparison
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # Remove special characters except spaces
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Collapse whitespace
    text = " ".join(text.split())

    return text


def normalize_client_name(name: str) -> str:
    """Normalize client/authority name for comparison.

    Args:
        name: Raw client name

    Returns:
        Normalized name
    """
    if not name:
        return ""

    normalized = normalize_text(name)

    # Remove common suffixes
    suffixes = [
        "gmbh", "ag", "kg", "ohg", "ev", "eg", "mbh", "ug", "gbr", "se",
        "bundesamt", "ministerium", "landesamt", "stadt", "kommune",
        "behoerde", "amt", "verwaltung", "des", "der", "fuer",
    ]
    for suffix in suffixes:
        normalized = re.sub(rf"\b{suffix}\b", "", normalized)

    return " ".join(normalized.split())


def jaccard_similarity(s1: str, s2: str) -> float:
    """Calculate Jaccard similarity between two strings.

    Uses word-level comparison for meaningful similarity.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not s1 or not s2:
        return 0.0

    words1 = set(s1.split())
    words2 = set(s2.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)


def ngram_similarity(s1: str, s2: str, n: int = 3) -> float:
    """Calculate n-gram similarity between two strings.

    Useful for detecting typos and minor variations.

    Args:
        s1: First string
        s2: Second string
        n: N-gram size

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not s1 or not s2:
        return 0.0

    # Generate n-grams
    def get_ngrams(s: str) -> Set[str]:
        s = s.replace(" ", "")  # Remove spaces for char-level ngrams
        if len(s) < n:
            return {s}
        return {s[i:i+n] for i in range(len(s) - n + 1)}

    ngrams1 = get_ngrams(s1)
    ngrams2 = get_ngrams(s2)

    if not ngrams1 or not ngrams2:
        return 0.0

    intersection = ngrams1 & ngrams2
    union = ngrams1 | ngrams2

    return len(intersection) / len(union)


def combined_similarity(s1: str, s2: str) -> float:
    """Calculate combined similarity using multiple methods.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Weighted average similarity
    """
    jaccard = jaccard_similarity(s1, s2)
    ngram = ngram_similarity(s1, s2)

    # Weight jaccard more heavily for meaningful word matching
    return 0.7 * jaccard + 0.3 * ngram


def deadlines_match(d1: Optional[datetime], d2: Optional[datetime]) -> bool:
    """Check if two deadlines match within tolerance.

    Args:
        d1: First deadline
        d2: Second deadline

    Returns:
        True if deadlines match or both are None
    """
    if d1 is None and d2 is None:
        return True

    if d1 is None or d2 is None:
        return False  # One has deadline, other doesn't - not a match

    diff = abs((d1 - d2).days)
    return diff <= DEADLINE_TOLERANCE_DAYS


def is_duplicate_pair(
    p1: Project,
    p2: Project,
) -> Tuple[bool, float, List[str]]:
    """Check if two projects are duplicates.

    Args:
        p1: First project
        p2: Second project

    Returns:
        Tuple of (is_duplicate, confidence, reasons)
    """
    reasons = []
    confidence = 0.0

    # Different sources is a prerequisite
    if p1.source == p2.source:
        return False, 0.0, []

    # Title similarity
    title1 = normalize_text(p1.title or "")
    title2 = normalize_text(p2.title or "")

    title_sim = combined_similarity(title1, title2)

    if title_sim < TITLE_SIMILARITY_THRESHOLD:
        return False, title_sim, ["Title similarity too low"]

    reasons.append(f"Title match: {title_sim:.0%}")
    confidence = title_sim * 0.5  # Title contributes 50%

    # Client similarity
    client1 = normalize_client_name(p1.client_name or "")
    client2 = normalize_client_name(p2.client_name or "")

    if client1 and client2:
        client_sim = combined_similarity(client1, client2)
        if client_sim >= 0.6:
            reasons.append(f"Client match: {client_sim:.0%}")
            confidence += client_sim * 0.25  # Client contributes 25%
        elif client_sim < 0.3:
            # Very different clients - likely not duplicates
            return False, confidence, ["Client names too different"]

    # Deadline match
    if deadlines_match(p1.tender_deadline, p2.tender_deadline):
        reasons.append("Deadline match")
        confidence += 0.25  # Deadline contributes 25%
    elif p1.tender_deadline and p2.tender_deadline:
        # Both have deadlines but they don't match - less likely duplicate
        confidence -= 0.1

    # Bonus: CPV code overlap
    cpv1 = set(p1.cpv_codes or [])
    cpv2 = set(p2.cpv_codes or [])
    if cpv1 and cpv2:
        cpv_overlap = cpv1 & cpv2
        if cpv_overlap:
            reasons.append(f"CPV overlap: {len(cpv_overlap)} codes")
            confidence = min(1.0, confidence + 0.1)

    # Final decision
    is_dup = confidence >= 0.7
    return is_dup, confidence, reasons


def find_cross_source_duplicates(
    db: Session,
    days_back: int = 30,
) -> List[DuplicateGroup]:
    """Find duplicate tenders from different sources.

    Args:
        db: Database session
        days_back: Only check projects from last N days

    Returns:
        List of DuplicateGroup objects
    """
    logger.info("Searching for cross-source duplicates...")

    # Get recent tender projects
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)

    projects = db.query(Project).filter(
        Project.project_type == "tender",
        Project.scraped_at >= cutoff_date,
    ).order_by(Project.scraped_at.asc()).all()

    logger.info("Checking %d projects for duplicates", len(projects))

    # Track which projects are already in a group
    assigned: Set[int] = set()
    groups: List[DuplicateGroup] = []

    # Compare all pairs (O(n^2) but n is limited by days_back)
    for i, p1 in enumerate(projects):
        if p1.id in assigned:
            continue

        duplicates = []
        best_confidence = 0.0
        all_reasons = []

        for p2 in projects[i + 1:]:
            if p2.id in assigned:
                continue

            is_dup, confidence, reasons = is_duplicate_pair(p1, p2)

            if is_dup:
                duplicates.append(p2.id)
                best_confidence = max(best_confidence, confidence)
                all_reasons.extend(reasons)
                assigned.add(p2.id)

        if duplicates:
            assigned.add(p1.id)
            groups.append(DuplicateGroup(
                primary_id=p1.id,
                duplicate_ids=duplicates,
                confidence=best_confidence,
                match_reasons=list(set(all_reasons)),
            ))

            logger.debug(
                "Found duplicate group: %d + %s (confidence: %.0f%%)",
                p1.id,
                duplicates,
                best_confidence * 100,
            )

    logger.info("Found %d duplicate groups", len(groups))
    return groups


def mark_duplicates(
    db: Session,
    groups: List[DuplicateGroup],
    dry_run: bool = True,
) -> int:
    """Mark duplicate projects in the database.

    Keeps the primary (oldest) project and marks duplicates as
    'duplicate' status with reference to primary.

    Args:
        db: Database session
        groups: Duplicate groups to process
        dry_run: If True, don't actually update database

    Returns:
        Number of duplicates marked
    """
    marked = 0

    for group in groups:
        for dup_id in group.duplicate_ids:
            if not dry_run:
                dup_project = db.query(Project).filter(Project.id == dup_id).first()
                if dup_project:
                    dup_project.status = "duplicate"
                    # Store reference to primary in description
                    note = f"\n[DUPLICATE of project #{group.primary_id}]"
                    if dup_project.description:
                        dup_project.description += note
                    else:
                        dup_project.description = note[1:]  # Remove leading newline

            marked += 1

    if not dry_run:
        db.commit()

    logger.info(
        "%s %d duplicates (dry_run=%s)",
        "Would mark" if dry_run else "Marked",
        marked,
        dry_run,
    )
    return marked


def dedupe_incoming_projects(
    db: Session,
    new_projects: List[Project],
) -> Tuple[List[Project], List[Project]]:
    """Check new projects against existing ones for duplicates.

    Args:
        db: Database session
        new_projects: List of new projects to check

    Returns:
        Tuple of (unique_projects, duplicate_projects)
    """
    unique = []
    duplicates = []

    # Get recent existing projects
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    existing = db.query(Project).filter(
        Project.project_type == "tender",
        Project.scraped_at >= cutoff_date,
        Project.status != "duplicate",
    ).all()

    for new_p in new_projects:
        is_dup = False

        for existing_p in existing:
            is_match, confidence, _ = is_duplicate_pair(new_p, existing_p)
            if is_match:
                logger.debug(
                    "New project '%s' (%s) is duplicate of '%s' (%s)",
                    new_p.title[:40],
                    new_p.source,
                    existing_p.title[:40],
                    existing_p.source,
                )
                duplicates.append(new_p)
                is_dup = True
                break

        if not is_dup:
            unique.append(new_p)

    return unique, duplicates
