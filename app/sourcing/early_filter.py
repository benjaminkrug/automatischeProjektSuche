"""Early rejection filter for scrapers.

Filters out obviously unsuitable projects BEFORE storing in DB.
This saves API costs and processing time.
"""

from typing import List

from app.core.logging import get_logger

logger = get_logger("sourcing.early_filter")

# Keywords that immediately disqualify a project (all lowercase)
# These are checked during scraping, before any DB insert or API call
EARLY_REJECT_KEYWORDS: List[str] = [
    # SAP/Legacy - definitiv nicht passend
    "sap", "abap", "cobol", "mainframe", "as400",
    # Mobile Apps (falls nicht Kernkompetenz)
    "ios entwickler", "ios developer", "ios app",
    "android entwickler", "android developer", "android app",
    "mobile app entwickler", "flutter entwickler", "react native entwickler",
    # CMS/PHP
    "php entwickler", "wordpress entwickler", "wordpress admin",
    "drupal", "typo3", "joomla",
    # Enterprise/Microsoft
    "sharepoint", "dynamics 365", "salesforce administrator", "salesforce entwickler",
    # Admin/Support
    "helpdesk", "1st level", "2nd level", "support techniker",
    "systemadministrator", "netzwerkadministrator",
    # Hardware/Embedded
    "hardwareentwicklung", "embedded entwickler",
    "sps programmierer", "roboterprogrammierung",
]

# Keywords that are acceptable in context (don't reject if also has these)
CONTEXT_ALLOW_KEYWORDS: List[str] = [
    "fullstack", "full-stack", "webentwicklung", "webanwendung",
    "python", "javascript", "typescript", "vue", "react",
    "backend", "frontend", "api",
]


def should_skip_project(title: str, description: str = "") -> bool:
    """Check if project should be skipped during scraping.

    This is a fast, keyword-based filter that runs BEFORE:
    - Database insert
    - Embedding generation
    - LLM analysis

    Args:
        title: Project title
        description: Project description (optional, may be empty)

    Returns:
        True if project should be skipped, False otherwise
    """
    text = f"{title} {description}".lower()

    # Check for early reject keywords
    reject_found = []
    for keyword in EARLY_REJECT_KEYWORDS:
        if keyword in text:
            reject_found.append(keyword)

    if not reject_found:
        return False

    # Check if context allows the project despite reject keywords
    # e.g., "Fullstack mit API-Anbindung an SAP" might still be relevant
    for allow_keyword in CONTEXT_ALLOW_KEYWORDS:
        if allow_keyword in text:
            # Has both reject and allow keywords - don't skip
            logger.debug(
                "Project has reject keyword '%s' but also '%s' - keeping",
                reject_found[0],
                allow_keyword,
            )
            return False

    # No context keywords found - reject
    logger.info(
        "Early reject: '%s' (keywords: %s)",
        title[:50],
        ", ".join(reject_found[:3]),
    )
    return True


def get_skip_reason(title: str, description: str = "") -> str | None:
    """Get the reason why a project would be skipped.

    Args:
        title: Project title
        description: Project description

    Returns:
        Reason string if project should be skipped, None otherwise
    """
    text = f"{title} {description}".lower()

    for keyword in EARLY_REJECT_KEYWORDS:
        if keyword in text:
            # Check context
            has_context = any(kw in text for kw in CONTEXT_ALLOW_KEYWORDS)
            if not has_context:
                return f"Early reject keyword: {keyword}"

    return None
