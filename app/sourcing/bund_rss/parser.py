"""Parser for service.bund.de RSS feed entries."""

import re
import hashlib
from datetime import datetime
from typing import Optional
from html import unescape

import feedparser

from app.sourcing.base import RawProject


def parse_rss_entry(entry: feedparser.FeedParserDict) -> Optional[RawProject]:
    """Parse a single RSS feed entry into a RawProject.

    Args:
        entry: feedparser entry object

    Returns:
        RawProject or None if parsing fails
    """
    # Extract required fields
    title = _clean_text(entry.get("title", ""))
    link = entry.get("link", "")

    if not title or not link:
        return None

    # Generate external_id from link (URL hash)
    external_id = _generate_id(link)

    # Extract description
    description = _clean_text(entry.get("summary", "") or entry.get("description", ""))

    # Try to extract client name from title or description
    client_name = _extract_client(title, description)

    # Extract deadline from title or description
    deadline = _extract_deadline(title, description, entry)

    # Check for IT-relevance keywords
    combined_text = f"{title} {description}".lower()
    if not _is_it_relevant(combined_text):
        return None

    return RawProject(
        source="bund_rss",
        external_id=external_id,
        url=link,
        title=title,
        client_name=client_name,
        description=description,
        skills=_extract_skills(combined_text),
        public_sector=True,
        deadline=deadline,
        remote=_check_remote(combined_text),
    )


def _clean_text(text: str) -> str:
    """Clean HTML entities and whitespace from text."""
    if not text:
        return ""
    # Unescape HTML entities
    text = unescape(text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _generate_id(url: str) -> str:
    """Generate a unique ID from URL."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _extract_client(title: str, description: str) -> Optional[str]:
    """Try to extract client/organization name."""
    # Common patterns in bund.de RSS
    patterns = [
        r"(?:Auftraggeber|Vergabestelle|Behörde)[:\s]+([^,\n]+)",
        r"(?:für|im Auftrag von)[:\s]+([^,\n]+)",
        r"^([A-Z][^-–]+?)(?:\s*[-–])",  # Title starting with org name
    ]

    for pattern in patterns:
        for text in [title, description]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                client = match.group(1).strip()
                if len(client) > 3 and len(client) < 100:
                    return client
    return None


def _extract_deadline(
    title: str, description: str, entry: feedparser.FeedParserDict
) -> Optional[datetime]:
    """Extract submission deadline."""
    # Try structured date fields first
    for field in ["published_parsed", "updated_parsed"]:
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime(*parsed[:6])
            except (ValueError, TypeError):
                pass

    # Try to extract from text
    combined = f"{title} {description}"
    date_patterns = [
        r"(?:Abgabefrist|Frist|Deadline|bis)[:\s]+(\d{1,2})[./](\d{1,2})[./](\d{4})",
        r"(\d{1,2})[./](\d{1,2})[./](\d{4})",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            try:
                day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return datetime(year, month, day)
            except ValueError:
                continue

    return None


def _is_it_relevant(text: str) -> bool:
    """Check if project is IT-related."""
    it_keywords = [
        "software", "it-", "entwicklung", "programmier", "digital",
        "datenbank", "cloud", "server", "netzwerk", "web", "app",
        "system", "portal", "plattform", "api", "schnittstelle",
        "informatik", "edv", "dv-", "fachverfahren",
        "python", "java", "javascript", "sql", "frontend", "backend",
    ]
    return any(kw in text for kw in it_keywords)


def _extract_skills(text: str) -> list[str]:
    """Extract mentioned technologies/skills."""
    skills = []
    skill_patterns = [
        "python", "java", "javascript", "typescript", "sql",
        "react", "vue", "angular", "docker", "kubernetes",
        "aws", "azure", "postgresql", "mysql", "mongodb",
        "linux", "windows server", "agile", "scrum",
    ]

    for skill in skill_patterns:
        if skill in text:
            skills.append(skill.title() if len(skill) > 3 else skill.upper())

    return list(set(skills))


def _check_remote(text: str) -> bool:
    """Check if remote work is mentioned."""
    remote_indicators = ["remote", "homeoffice", "home-office", "home office", "mobiles arbeiten"]
    return any(ind in text for ind in remote_indicators)
