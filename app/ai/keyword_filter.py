"""Keyword-based project pre-filtering.

Provides fast keyword matching to:
- Boost score for good keywords (web technologies)
- Auto-reject projects with bad keywords (SAP, DevOps, etc.)

This runs BEFORE the LLM matching to save costs and time.
"""

import re
from dataclasses import dataclass
from typing import List

from app.core.logging import get_logger
from app.sourcing.search_config import (
    BOOST_KEYWORDS,
    REJECT_KEYWORDS,
    KEYWORD_BOOST_POINTS,
    KEYWORD_REJECT_THRESHOLD,
)

logger = get_logger("ai.keyword_filter")


@dataclass
class KeywordCheckResult:
    """Result of keyword check on a project."""

    boost: bool  # Has good keywords
    reject: bool  # Has bad keywords
    boost_keywords: List[str]  # Found good keywords
    reject_keywords: List[str]  # Found bad keywords
    score_modifier: int  # +10 or 0


def check_project_keywords(title: str, description: str = "") -> KeywordCheckResult:
    """Check project text for boost and reject keywords.

    Performs case-insensitive word boundary matching.

    Args:
        title: Project title
        description: Project description (optional)

    Returns:
        KeywordCheckResult with boost/reject flags and found keywords
    """
    # Combine title and description for searching
    text = f"{title} {description}".lower()

    # Find matching keywords
    boost_found = _find_keywords(text, BOOST_KEYWORDS)
    reject_found = _find_keywords(text, REJECT_KEYWORDS)

    # Determine flags
    has_boost = len(boost_found) > 0
    has_reject = len(reject_found) >= KEYWORD_REJECT_THRESHOLD

    # Calculate score modifier (only one boost, regardless of keyword count)
    score_modifier = KEYWORD_BOOST_POINTS if has_boost and not has_reject else 0

    result = KeywordCheckResult(
        boost=has_boost,
        reject=has_reject,
        boost_keywords=boost_found,
        reject_keywords=reject_found,
        score_modifier=score_modifier,
    )

    # Log for transparency
    if has_reject:
        logger.info(
            "Keyword-Reject: %s (Keywords: %s)",
            title[:50],
            ", ".join(reject_found),
        )
    elif has_boost:
        logger.debug(
            "Keyword-Boost: %s (Keywords: %s)",
            title[:50],
            ", ".join(boost_found),
        )

    return result


def _find_keywords(text: str, keywords: List[str]) -> List[str]:
    """Find all matching keywords in text using word boundary matching.

    Args:
        text: Text to search in (already lowercase)
        keywords: List of keywords to search for (already lowercase)

    Returns:
        List of found keywords
    """
    found = []
    for keyword in keywords:
        # Use word boundary regex for accurate matching
        # This ensures "api" doesn't match "capital" etc.
        pattern = rf"\b{re.escape(keyword)}\b"
        if re.search(pattern, text):
            found.append(keyword)
    return found
