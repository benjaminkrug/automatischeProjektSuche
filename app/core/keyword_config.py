"""Q6: Zentralisierte Keyword-Konfiguration für alle Filter und Scoring.

Single Source of Truth für Keywords, die in verschiedenen Modulen verwendet werden:
- early_filter.py (Scraper-Vorfilter)
- keyword_scoring.py (Projekt-Scoring)
- search_config.py (Portal-Suche)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Set


class KeywordCategory(Enum):
    """Kategorien für Reject-Keywords."""

    LEGACY = "legacy"      # SAP, COBOL, Mainframe
    CMS = "cms"            # PHP, WordPress
    ADMIN = "admin"        # Helpdesk, Support
    MOBILE = "mobile"      # iOS, Android, Flutter (falls nicht Kernkompetenz)
    HARDWARE = "hardware"  # Embedded, SPS
    INDUSTRY = "industry"  # Bau, Elektro, etc.
    ENTERPRISE = "enterprise"  # SharePoint, Dynamics, Salesforce


@dataclass
class RejectKeyword:
    """Definition eines Reject-Keywords mit Metadaten."""

    keyword: str
    category: KeywordCategory
    weight: int  # 30=leicht, 50=mittel, 100=stark, 150=sofort
    early_reject: bool = False  # Für early_filter.py (vor DB-Insert)


# Single Source of Truth für alle Reject-Keywords
REJECT_KEYWORDS: Dict[str, RejectKeyword] = {
    # ============================================================
    # Legacy (sofort reject)
    # ============================================================
    "sap": RejectKeyword("sap", KeywordCategory.LEGACY, 100, early_reject=True),
    "abap": RejectKeyword("abap", KeywordCategory.LEGACY, 100, early_reject=True),
    "cobol": RejectKeyword("cobol", KeywordCategory.LEGACY, 100, early_reject=True),
    "mainframe": RejectKeyword("mainframe", KeywordCategory.LEGACY, 100, early_reject=True),
    "as400": RejectKeyword("as400", KeywordCategory.LEGACY, 100, early_reject=True),

    # ============================================================
    # Enterprise (sofort reject)
    # ============================================================
    "sharepoint": RejectKeyword("sharepoint", KeywordCategory.ENTERPRISE, 100, early_reject=True),
    "dynamics": RejectKeyword("dynamics", KeywordCategory.ENTERPRISE, 100, early_reject=False),
    "dynamics 365": RejectKeyword("dynamics 365", KeywordCategory.ENTERPRISE, 100, early_reject=True),
    "salesforce": RejectKeyword("salesforce", KeywordCategory.ENTERPRISE, 100, early_reject=True),
    "salesforce administrator": RejectKeyword("salesforce administrator", KeywordCategory.ENTERPRISE, 100, early_reject=True),
    "salesforce entwickler": RejectKeyword("salesforce entwickler", KeywordCategory.ENTERPRISE, 100, early_reject=True),

    # ============================================================
    # CMS (mittel)
    # ============================================================
    "php": RejectKeyword("php", KeywordCategory.CMS, 50, early_reject=True),
    "php entwickler": RejectKeyword("php entwickler", KeywordCategory.CMS, 50, early_reject=True),
    "wordpress": RejectKeyword("wordpress", KeywordCategory.CMS, 50, early_reject=True),
    "wordpress entwickler": RejectKeyword("wordpress entwickler", KeywordCategory.CMS, 50, early_reject=True),
    "wordpress admin": RejectKeyword("wordpress admin", KeywordCategory.CMS, 50, early_reject=True),
    "drupal": RejectKeyword("drupal", KeywordCategory.CMS, 50, early_reject=True),
    "joomla": RejectKeyword("joomla", KeywordCategory.CMS, 50, early_reject=True),
    "typo3": RejectKeyword("typo3", KeywordCategory.CMS, 50, early_reject=True),

    # ============================================================
    # Admin/Support (leicht)
    # ============================================================
    "helpdesk": RejectKeyword("helpdesk", KeywordCategory.ADMIN, 30, early_reject=True),
    "support": RejectKeyword("support", KeywordCategory.ADMIN, 30, early_reject=False),
    "support techniker": RejectKeyword("support techniker", KeywordCategory.ADMIN, 30, early_reject=True),
    "1st level": RejectKeyword("1st level", KeywordCategory.ADMIN, 30, early_reject=True),
    "2nd level": RejectKeyword("2nd level", KeywordCategory.ADMIN, 30, early_reject=True),
    "systemadministrator": RejectKeyword("systemadministrator", KeywordCategory.ADMIN, 30, early_reject=True),
    "netzwerkadministrator": RejectKeyword("netzwerkadministrator", KeywordCategory.ADMIN, 30, early_reject=True),
    "admin": RejectKeyword("admin", KeywordCategory.ADMIN, 30, early_reject=False),
    "netzwerk": RejectKeyword("netzwerk", KeywordCategory.ADMIN, 30, early_reject=False),
    "firewall": RejectKeyword("firewall", KeywordCategory.ADMIN, 30, early_reject=False),
    "cisco": RejectKeyword("cisco", KeywordCategory.ADMIN, 30, early_reject=False),

    # ============================================================
    # Mobile (falls nicht Kernkompetenz)
    # ============================================================
    "ios entwickler": RejectKeyword("ios entwickler", KeywordCategory.MOBILE, 50, early_reject=True),
    "ios developer": RejectKeyword("ios developer", KeywordCategory.MOBILE, 50, early_reject=True),
    "ios app": RejectKeyword("ios app", KeywordCategory.MOBILE, 50, early_reject=True),
    "android entwickler": RejectKeyword("android entwickler", KeywordCategory.MOBILE, 50, early_reject=True),
    "android developer": RejectKeyword("android developer", KeywordCategory.MOBILE, 50, early_reject=True),
    "android app": RejectKeyword("android app", KeywordCategory.MOBILE, 50, early_reject=True),
    "mobile app entwickler": RejectKeyword("mobile app entwickler", KeywordCategory.MOBILE, 50, early_reject=True),
    "flutter entwickler": RejectKeyword("flutter entwickler", KeywordCategory.MOBILE, 50, early_reject=True),
    "react native entwickler": RejectKeyword("react native entwickler", KeywordCategory.MOBILE, 50, early_reject=True),

    # ============================================================
    # Hardware/Embedded
    # ============================================================
    "hardware": RejectKeyword("hardware", KeywordCategory.HARDWARE, 30, early_reject=False),
    "hardwareentwicklung": RejectKeyword("hardwareentwicklung", KeywordCategory.HARDWARE, 40, early_reject=True),
    "embedded": RejectKeyword("embedded", KeywordCategory.HARDWARE, 40, early_reject=False),
    "embedded entwickler": RejectKeyword("embedded entwickler", KeywordCategory.HARDWARE, 40, early_reject=True),
    "sps": RejectKeyword("sps", KeywordCategory.HARDWARE, 40, early_reject=False),
    "sps programmierer": RejectKeyword("sps programmierer", KeywordCategory.HARDWARE, 40, early_reject=True),
    "roboter": RejectKeyword("roboter", KeywordCategory.HARDWARE, 40, early_reject=False),
    "roboterprogrammierung": RejectKeyword("roboterprogrammierung", KeywordCategory.HARDWARE, 40, early_reject=True),
    "maschinenbau": RejectKeyword("maschinenbau", KeywordCategory.HARDWARE, 40, early_reject=False),
    "elektrotechnik": RejectKeyword("elektrotechnik", KeywordCategory.HARDWARE, 40, early_reject=False),

    # ============================================================
    # Industry (Bau, Elektro, etc.) - sofort reject
    # ============================================================
    # Bau/Hochbau/Tiefbau
    "bauarbeiten": RejectKeyword("bauarbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "bauleistungen": RejectKeyword("bauleistungen", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "hochbau": RejectKeyword("hochbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "tiefbau": RejectKeyword("tiefbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "rohbau": RejectKeyword("rohbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "straßenbau": RejectKeyword("straßenbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "brückenbau": RejectKeyword("brückenbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "kanalbau": RejectKeyword("kanalbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "betonarbeiten": RejectKeyword("betonarbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "mauerarbeiten": RejectKeyword("mauerarbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "dacharbeiten": RejectKeyword("dacharbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "estricharbeiten": RejectKeyword("estricharbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "putzarbeiten": RejectKeyword("putzarbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "fliesenarbeiten": RejectKeyword("fliesenarbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "trockenbau": RejectKeyword("trockenbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "gerüstbau": RejectKeyword("gerüstbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "abbrucharbeiten": RejectKeyword("abbrucharbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),

    # Elektroinstallation (nicht IT)
    "elektroinstallation": RejectKeyword("elektroinstallation", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "starkstrom": RejectKeyword("starkstrom", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "elektroanlagen": RejectKeyword("elektroanlagen", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "schaltanlagen": RejectKeyword("schaltanlagen", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "niederspannung": RejectKeyword("niederspannung", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "mittelspannung": RejectKeyword("mittelspannung", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "hochspannung": RejectKeyword("hochspannung", KeywordCategory.INDUSTRY, 150, early_reject=False),

    # Mechanik/Metallbau
    "metallbau": RejectKeyword("metallbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "stahlbau": RejectKeyword("stahlbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "schweißarbeiten": RejectKeyword("schweißarbeiten", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "rohrleitungsbau": RejectKeyword("rohrleitungsbau", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "schlosserei": RejectKeyword("schlosserei", KeywordCategory.INDUSTRY, 150, early_reject=False),

    # HVAC/TGA
    "heizungsanlage": RejectKeyword("heizungsanlage", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "lüftungsanlage": RejectKeyword("lüftungsanlage", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "klimaanlage": RejectKeyword("klimaanlage", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "sanitärinstallation": RejectKeyword("sanitärinstallation", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "kältetechnik": RejectKeyword("kältetechnik", KeywordCategory.INDUSTRY, 150, early_reject=False),

    # Facility/Reinigung
    "gebäudereinigung": RejectKeyword("gebäudereinigung", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "unterhaltsreinigung": RejectKeyword("unterhaltsreinigung", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "winterdienst": RejectKeyword("winterdienst", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "grünflächenpflege": RejectKeyword("grünflächenpflege", KeywordCategory.INDUSTRY, 150, early_reject=False),

    # Sicherheit (physisch)
    "wachdienst": RejectKeyword("wachdienst", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "objektschutz": RejectKeyword("objektschutz", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "sicherheitsdienst": RejectKeyword("sicherheitsdienst", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "pförtnerdienst": RejectKeyword("pförtnerdienst", KeywordCategory.INDUSTRY, 150, early_reject=False),

    # Druck/Büro
    "druckerzeugnisse": RejectKeyword("druckerzeugnisse", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "drucksachen": RejectKeyword("drucksachen", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "büromöbel": RejectKeyword("büromöbel", KeywordCategory.INDUSTRY, 150, early_reject=False),
    "arbeitskleidung": RejectKeyword("arbeitskleidung", KeywordCategory.INDUSTRY, 150, early_reject=False),
}


def get_early_reject_keywords() -> Set[str]:
    """Keywords für early_filter.py (vor DB-Insert).

    Diese Keywords führen zum sofortigen Ausschluss während des Scrapings.
    """
    return {k for k, v in REJECT_KEYWORDS.items() if v.early_reject}


def get_weighted_reject_keywords() -> Dict[str, int]:
    """Keywords mit Gewichtung für keyword_scoring.py.

    Gibt alle Reject-Keywords mit ihren Gewichten zurück.
    """
    return {k: v.weight for k, v in REJECT_KEYWORDS.items()}


def get_reject_keywords_by_category(category: KeywordCategory) -> Set[str]:
    """Keywords einer bestimmten Kategorie.

    Args:
        category: Die Keyword-Kategorie

    Returns:
        Set aller Keywords in dieser Kategorie
    """
    return {k for k, v in REJECT_KEYWORDS.items() if v.category == category}


def get_all_reject_keywords() -> Set[str]:
    """Alle Reject-Keywords als Set.

    Returns:
        Set aller Reject-Keywords
    """
    return set(REJECT_KEYWORDS.keys())


# ============================================================
# Context/Allow Keywords (für early_filter.py)
# ============================================================

# Keywords die erlauben, ein Projekt trotz Reject-Keywords zu behalten
CONTEXT_ALLOW_KEYWORDS: Set[str] = {
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
}


def get_context_allow_keywords() -> Set[str]:
    """Keywords die einen Projekt-Kontext als Software/IT qualifizieren.

    Returns:
        Set aller Context-Allow-Keywords
    """
    return CONTEXT_ALLOW_KEYWORDS.copy()
