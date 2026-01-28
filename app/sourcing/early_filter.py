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

# Industry-Keywords - Branchen die nicht zur Software-Entwicklung passen
# Projekte mit diesen Keywords werden abgelehnt, AUSSER sie haben Software-Kontext
EARLY_REJECT_INDUSTRY_KEYWORDS: List[str] = [
    # Bau/Hochbau/Tiefbau
    "bauarbeiten", "bauleistungen", "hochbau", "tiefbau", "rohbau",
    "straßenbau", "brückenbau", "kanalbau", "betonarbeiten",
    "mauerarbeiten", "dacharbeiten", "estricharbeiten", "putzarbeiten",
    "fliesenarbeiten", "trockenbau", "gerüstbau", "abbrucharbeiten",
    "erdarbeiten", "pflasterarbeiten", "asphaltarbeiten",
    # Elektrotechnik (nicht IT)
    "elektroinstallation", "starkstrom", "elektroanlagen", "schaltanlagen",
    "niederspannung", "mittelspannung", "hochspannung", "trafostation",
    "blitzschutz", "elektromontage",
    # Mechanik/Maschinenbau
    "metallbau", "stahlbau", "schweißarbeiten", "rohrleitungsbau",
    "schlosserei", "feinmechanik", "werkzeugbau", "formenbau",
    # HVAC/TGA (Technische Gebäudeausrüstung)
    "heizungsanlage", "lüftungsanlage", "klimaanlage", "sanitärinstallation",
    "kältetechnik", "wärmepumpe", "heizungsbau", "lüftungsbau",
    "sanitär", "heizung", "lüftung", "klima",
    # Facility/Reinigung
    "gebäudereinigung", "unterhaltsreinigung", "glasreinigung",
    "winterdienst", "grünflächenpflege", "gartenpflege", "hausmeister",
    # Sicherheit (physisch)
    "wachdienst", "objektschutz", "sicherheitsdienst", "pförtnerdienst",
    "brandmeldeanlage", "einbruchmeldeanlage", "videoüberwachung",
    # Transport/Logistik (physisch)
    "spedition", "umzugsleistungen", "möbeltransport", "kurierdienst",
    # Druck/Büro/Textil
    "druckerzeugnisse", "drucksachen", "büromöbel", "büroausstattung",
    "arbeitskleidung", "textilreinigung", "wäscherei",
    # Catering/Verpflegung
    "catering", "kantinenservice", "verpflegung", "essenslieferung",
    # Medizin (nicht IT)
    "labordiagnostik", "medizinprodukte", "pflegedienstleistung",
]

# Q4: Keywords that are acceptable in context (don't reject if also has these)
# Extended list to reduce false negatives
CONTEXT_ALLOW_KEYWORDS: List[str] = [
    # Rollen
    "fullstack", "full-stack", "backend", "frontend", "api",
    "webentwicklung", "softwareentwicklung", "it-beratung",
    "entwickler", "developer", "engineer",
    # Technologien
    "python", "java", "javascript", "typescript", "vue", "react", "angular",
    "c#", ".net", "django", "spring", "node", "nodejs",
    "fastapi", "flask", "express", "nestjs",
    # Projekttypen
    "webanwendung", "webapp", "portal", "plattform", "saas",
    "digitalisierung", "e-government", "ozg",
    "webapplikation", "webportal", "online-plattform",
    # Allgemein IT
    "it-projekt", "it-system", "fachverfahren", "fachanwendung",
    "schnittstelle", "datenbank", "cloud", "microservice", "microservices",
    "docker", "kubernetes", "aws", "azure",
    # API/Integration
    "rest", "graphql", "restful", "api-entwicklung",
    # Datenbank
    "postgresql", "mongodb", "mysql", "redis",
]


def _has_software_context(text: str) -> bool:
    """Prüfe ob der Text Software/IT-Kontext enthält.

    Args:
        text: Text to check (already lowercase)

    Returns:
        True if software context is found
    """
    from app.sourcing.search_config import REQUIRED_CONTEXT_KEYWORDS

    return any(kw in text for kw in REQUIRED_CONTEXT_KEYWORDS)


def should_skip_project(
    title: str,
    description: str = "",
    check_industry: bool = True,
    require_context: bool = True,
) -> bool:
    """Check if project should be skipped during scraping.

    This is a fast, keyword-based filter that runs BEFORE:
    - Database insert
    - Embedding generation
    - LLM analysis

    Args:
        title: Project title
        description: Project description (optional, may be empty)
        check_industry: Check for industry-reject keywords (Bau, Elektro etc.)
        require_context: Require software/IT context keywords

    Returns:
        True if project should be skipped, False otherwise
    """
    text = f"{title} {description}".lower()

    # 1. Industry-Check (Bau, Elektro etc.)
    # Reject if industry keyword found AND no software context
    if check_industry:
        for keyword in EARLY_REJECT_INDUSTRY_KEYWORDS:
            if keyword in text:
                if not _has_software_context(text):
                    logger.info(
                        "Early reject (industry): '%s' (keyword: %s, no software context)",
                        title[:50],
                        keyword,
                    )
                    return True

    # 2. Context requirement - project must have software/IT context
    if require_context and not _has_software_context(text):
        logger.info(
            "Early reject (no context): '%s' (no software/IT keywords found)",
            title[:50],
        )
        return True

    # 3. Check for early reject keywords (SAP, PHP, etc.)
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


def get_skip_reason(
    title: str,
    description: str = "",
    check_industry: bool = True,
    require_context: bool = True,
) -> str | None:
    """Get the reason why a project would be skipped.

    Args:
        title: Project title
        description: Project description
        check_industry: Check for industry-reject keywords
        require_context: Require software/IT context keywords

    Returns:
        Reason string if project should be skipped, None otherwise
    """
    text = f"{title} {description}".lower()

    # 1. Industry check
    if check_industry:
        for keyword in EARLY_REJECT_INDUSTRY_KEYWORDS:
            if keyword in text:
                if not _has_software_context(text):
                    return f"Industry reject keyword: {keyword}"

    # 2. Context requirement
    if require_context and not _has_software_context(text):
        return "No software/IT context found"

    # 3. Early reject keywords
    for keyword in EARLY_REJECT_KEYWORDS:
        if keyword in text:
            # Check context
            has_context = any(kw in text for kw in CONTEXT_ALLOW_KEYWORDS)
            if not has_context:
                return f"Early reject keyword: {keyword}"

    return None
