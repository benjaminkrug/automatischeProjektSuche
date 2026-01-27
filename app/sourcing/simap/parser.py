"""Parser for simap.ch API responses."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.sourcing.base import RawProject


def parse_project(project_data: Dict[str, Any]) -> Optional[RawProject]:
    """Parse a single project from simap.ch API response.

    Args:
        project_data: Project dictionary from API response

    Returns:
        RawProject object or None if parsing fails
    """
    try:
        # Extract project ID
        project_id = project_data.get("projectId")
        if not project_id:
            return None

        # Extract header information
        header = project_data.get("projectHeader", {})
        title = header.get("title", "")
        description = header.get("description", "")

        if not title:
            return None

        # Extract client/procuring office
        proc_office = project_data.get("procOffice", {})
        client_name = proc_office.get("name")

        # Extract location from order address
        order_address = project_data.get("orderAddress", {})
        location = order_address.get("city")
        country = order_address.get("country", "CH")

        # Combine location with country
        if location and country:
            location = f"{location}, {country}"
        elif not location and country:
            location = country

        # Extract deadline
        deadline = _parse_deadline(header.get("deadline"))

        # Build URL to project detail page
        url = f"https://www.simap.ch/shabforms/COMMON/simap/content/start.jsp?projectId={project_id}"

        # Extract CPV codes as skills
        skills = _extract_cpv_skills(project_data.get("cpvCodes", []))

        # Check for remote work indicators
        remote = _check_remote_indicators(title, description)

        return RawProject(
            source="simap.ch",
            external_id=str(project_id),
            url=url,
            title=title,
            client_name=client_name,
            description=description if description else None,
            skills=skills,
            budget=None,  # Budget usually not disclosed in search results
            location=location,
            remote=remote,
            public_sector=True,  # simap.ch is always public sector
            deadline=deadline,
        )

    except Exception:
        return None


def parse_projects(projects_data: List[Dict[str, Any]]) -> List[RawProject]:
    """Parse multiple projects from API response.

    Args:
        projects_data: List of project dictionaries

    Returns:
        List of successfully parsed RawProject objects
    """
    results = []
    for project_data in projects_data:
        parsed = parse_project(project_data)
        if parsed:
            results.append(parsed)
    return results


def _parse_deadline(deadline_str: Optional[str]) -> Optional[datetime]:
    """Parse deadline string to datetime.

    Args:
        deadline_str: Deadline string in various formats

    Returns:
        Parsed datetime or None
    """
    if not deadline_str:
        return None

    # Try ISO format first (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    iso_patterns = [
        r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})",
        r"(\d{4})-(\d{2})-(\d{2})",
    ]

    for pattern in iso_patterns:
        match = re.search(pattern, deadline_str)
        if match:
            groups = match.groups()
            try:
                if len(groups) >= 6:
                    return datetime(
                        int(groups[0]), int(groups[1]), int(groups[2]),
                        int(groups[3]), int(groups[4]), int(groups[5])
                    )
                else:
                    return datetime(
                        int(groups[0]), int(groups[1]), int(groups[2])
                    )
            except ValueError:
                continue

    # Try German/Swiss format (DD.MM.YYYY)
    german_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", deadline_str)
    if german_match:
        try:
            return datetime(
                int(german_match.group(3)),
                int(german_match.group(2)),
                int(german_match.group(1)),
            )
        except ValueError:
            pass

    return None


def _extract_cpv_skills(cpv_codes: List[Dict[str, Any]]) -> List[str]:
    """Extract skill keywords from CPV codes.

    Args:
        cpv_codes: List of CPV code dictionaries

    Returns:
        List of skill keywords
    """
    skills = []

    # Common IT CPV code mappings
    cpv_skill_map = {
        "72000000": "IT-Dienstleistungen",
        "72200000": "Software",
        "72210000": "Programmierung",
        "72220000": "Systemanalyse",
        "72230000": "Softwareentwicklung",
        "72240000": "Systemanalyse",
        "72250000": "Wartung",
        "72260000": "Softwareberatung",
        "72300000": "Datendienste",
        "72400000": "Internet",
        "72500000": "Computerservices",
        "72600000": "IT-Support",
    }

    for cpv in cpv_codes:
        code = cpv.get("code", "")
        # Match by prefix (first 8 digits)
        for prefix, skill in cpv_skill_map.items():
            if code.startswith(prefix[:5]):  # Match first 5 digits
                if skill not in skills:
                    skills.append(skill)

        # Also extract description if available
        description = cpv.get("description", "")
        if description:
            # Extract capitalized words as potential skills
            words = re.findall(r"[A-ZÄÖÜ][a-zäöüß]+(?:[-][A-Za-zäöüß]+)?", description)
            for word in words[:3]:  # Limit to first 3 words
                if word not in skills and len(word) > 3:
                    skills.append(word)

    return skills[:10]  # Limit total skills


def _check_remote_indicators(title: str, description: str) -> bool:
    """Check if project allows remote work.

    Args:
        title: Project title
        description: Project description

    Returns:
        True if remote work is indicated
    """
    text = f"{title} {description}".lower()
    remote_terms = [
        "remote", "homeoffice", "home-office", "telearbeit",
        "ortsunabhängig", "mobiles arbeiten", "fernarbeit",
    ]
    return any(term in text for term in remote_terms)
