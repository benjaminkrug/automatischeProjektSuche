"""Centralized search configuration for all portal scrapers."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PortalSearchConfig:
    """Configuration for a single portal scraper."""

    enabled: bool = True
    category_params: Dict[str, str] = field(default_factory=dict)
    keyword_params: Dict[str, str] = field(default_factory=dict)
    sort_params: Dict[str, str] = field(default_factory=dict)


# Portal-specific configurations
PORTAL_CONFIGS: Dict[str, PortalSearchConfig] = {
    "freelancermap": PortalSearchConfig(
        enabled=True,
        category_params={"categories[]": "1", "projektart": "1"},
        sort_params={"sort": "1"},
    ),
    "gulp": PortalSearchConfig(
        enabled=True,
        category_params={"category": "it"},
        keyword_params={"q": "Software Entwicklung Python Java DevOps"},
    ),
    "freelance.de": PortalSearchConfig(
        enabled=True,
        category_params={"category": "it-entwicklung"},
        sort_params={"sort": "date"},
    ),
    "malt": PortalSearchConfig(
        enabled=False,  # Malt ist ein Freelancer-Marktplatz ohne öffentliche Projektliste
        category_params={"expertise": "tech"},
        sort_params={"sort": "newest"},
    ),
    # Public sector portal - priority due to bonus scoring
    "bund.de": PortalSearchConfig(
        enabled=True,
    ),
    # DTVP - Deutsches Vergabeportal (public sector)
    "dtvp": PortalSearchConfig(
        enabled=True,
    ),
    # simap.ch - Swiss public procurement (REST API)
    "simap.ch": PortalSearchConfig(
        enabled=True,
    ),
    # Vergabe24 - German public procurement aggregator
    "vergabe24": PortalSearchConfig(
        enabled=False,  # Deaktiviert - liefert Informationstexte statt Ausschreibungen
    ),
    # EU public sector tender portal
    "ted": PortalSearchConfig(
        enabled=True,  # TED EU Tender API aktiv
    ),
    "linkedin": PortalSearchConfig(
        enabled=False,  # Login erforderlich, Anti-Bot Maßnahmen
    ),
    "upwork": PortalSearchConfig(
        enabled=False,  # Starker Anti-Bot Schutz, CAPTCHA
    ),
    # service.bund.de RSS Feed - lightweight public sector source
    "bund_rss": PortalSearchConfig(
        enabled=True,  # RSS-Feed, kein Playwright nötig
    ),
    # evergabe.de - German procurement aggregator
    "evergabe": PortalSearchConfig(
        enabled=True,  # Öffentliche Suche, aggregiert viele Vergabestellen
    ),
    # evergabe-online.de - 600+ public sector organizations
    "evergabe_online": PortalSearchConfig(
        enabled=True,  # Öffentliche Suche verfügbar
    ),
    # oeffentlichevergabe.de - OpenData API with 600+ Vergabestellen
    "oeffentlichevergabe": PortalSearchConfig(
        enabled=False,  # API endpoint not yet verified - disabled until fixed
    ),
    # NRW Vergabeportal - bevölkerungsreichstes Bundesland
    "nrw": PortalSearchConfig(
        enabled=False,  # Playwright selectors need adjustment - disabled until fixed
    ),
    # Bayern Vergabeportal - starker Tech-Sektor
    "bayern": PortalSearchConfig(
        enabled=False,  # Playwright selectors need adjustment - disabled until fixed
    ),
    # Baden-Württemberg Vergabeportal - IT/Automotive
    "bawue": PortalSearchConfig(
        enabled=False,  # Playwright selectors need adjustment - disabled until fixed
    ),
}


# Global exclusion keywords - projects containing these are filtered out
EXCLUDE_KEYWORDS: List[str] = [
    "Sicherheitsüberprüfung",
    "Security Clearance",
    "Clearance",
    "Vor-Ort-Pflicht",
    "keine Remote",
    "kein Homeoffice",
    "100% Onsite",
    "only onsite",
]

# Gute Keywords → Score-Bonus (alle lowercase für case-insensitive Matching)
# Fullstack-optimiert für Frontend + Backend Profil
BOOST_KEYWORDS: List[str] = [
    # Frontend
    "vue", "vuejs", "vue.js", "nuxt", "nuxtjs",
    "react", "angular", "typescript", "javascript",
    "frontend", "front-end", "spa", "responsive", "ui", "ux",
    # Backend
    "python", "django", "fastapi", "flask",
    "node", "nodejs", "node.js", "express", "nestjs",
    "java", "spring", "kotlin",
    # Fullstack
    "fullstack", "full-stack", "webentwicklung", "webanwendung",
    "portal", "webapp", "saas", "plattform", "webentwickler",
    # Datenbank
    "postgresql", "mysql", "mongodb", "redis",
    # Cloud/DevOps (light)
    "docker", "aws", "azure", "cloud",
    # API
    "api", "rest", "graphql", "microservice", "schnittstelle",
]

# Webapp/App Boost-Keywords → zusätzlicher Score-Bonus für passende Projekttypen
BOOST_KEYWORDS_WEBAPP: List[str] = [
    # Webanwendungen
    "webanwendung", "webapp", "web-app", "webportal", "web-portal",
    "webapplikation", "web-applikation", "portal", "plattform",
    "responsive", "spa", "single page", "single-page",
    "progressive web", "pwa",
    # Mobile Apps
    "mobile app", "mobile-app", "mobileapp", "ios", "android",
    "react native", "flutter", "ionic", "xamarin",
    "smartphone", "tablet", "app-entwicklung",
    # Fullstack/Kern-Skills
    "fullstack", "full-stack", "frontend", "front-end",
    "backend", "back-end", "api-entwicklung",
]

# Schlechte Keywords → Auto-Reject (alle lowercase für case-insensitive Matching)
# Fullstack-optimiert - Technologien/Bereiche die nicht passen
REJECT_KEYWORDS: List[str] = [
    # SAP/Legacy
    "sap", "abap", "cobol", "mainframe", "as400",
    # Mobile (falls nicht Kernkompetenz)
    "ios", "android", "flutter", "react native", "mobile app",
    # CMS/PHP (falls nicht gewünscht)
    "php", "wordpress", "drupal", "joomla", "typo3",
    # Enterprise/Microsoft
    "sharepoint", "dynamics", "salesforce",
    # Infrastruktur/Admin
    "netzwerk", "firewall", "cisco", "admin",
    "helpdesk", "support", "1st level", "2nd level",
    # Hardware/Embedded
    "hardware", "drucker", "client", "embedded",
    "sps", "roboter", "maschinenbau", "elektrotechnik",
]

# Legal-Reject-Keywords → Ausschlusskriterien für Bietergemeinschaft
# Projekte mit diesen Keywords werden zur Review markiert oder abgelehnt
REJECT_KEYWORDS_LEGAL: List[str] = [
    # Sicherheitsüberprüfung
    "sicherheitsüberprüfung", "ü1", "ü2", "ü3",
    "nato", "geheimschutz", "vs-vertraulich", "vs-nfd",
    "sabotageschutz", "verschlusssache",
    # Rechtsform-Einschränkungen
    "keine bietergemeinschaft", "keine bg",
    "nur einzelbieter", "keine arbeitsgemeinschaft",
    "keine arge", "bietergemeinschaften ausgeschlossen",
    "nur einzelangebote",
    # Größenanforderungen
    "mindestumsatz", "mindestmitarbeiter", "mindestmitarbeiterzahl",
    "jahresumsatz mindestens", "mindestumsatz von",
    "mindestens 50 mitarbeiter", "mindestens 100 mitarbeiter",
]

# Zertifizierungs-Keywords → für Fit-Analyse
CERTIFICATION_KEYWORDS: List[str] = [
    "iso 27001", "iso27001", "iso-27001",
    "bsi-grundschutz", "bsi grundschutz", "it-grundschutz",
    "iso 9001", "iso9001", "iso-9001",
    "tisax", "cmmi", "itil",
    "zertifizierung erforderlich", "zertifiziert",
]

# Referenz-Keywords → für Fit-Analyse
REFERENCE_KEYWORDS: List[str] = [
    "referenzprojekte", "referenzen erforderlich",
    "nachweise über referenzen", "mindestens 3 referenzen",
    "mindestens 2 referenzen", "vergleichbare projekte",
    "referenzliste", "referenzaufträge",
]

# Keyword-Scoring-Einstellungen
KEYWORD_BOOST_POINTS: int = 10      # +10 für jedes gute Keyword (max 1x)
KEYWORD_REJECT_THRESHOLD: int = 1   # 1 schlechtes Keyword = Reject

# Required Context Keywords - Projekte MÜSSEN mindestens eines dieser Keywords enthalten
# um als Software/IT-Projekt erkannt zu werden
REQUIRED_CONTEXT_KEYWORDS: List[str] = [
    # Software/Entwicklung allgemein
    "software", "softwareentwicklung", "programmierung", "entwicklung",
    "anwendung", "applikation", "application",
    # Web
    "webanwendung", "webportal", "webapp", "web-app", "website",
    "online-plattform", "webapplikation", "webentwicklung",
    "internetauftritt", "webseite",
    # Mobile
    "mobile app", "app-entwicklung", "mobilanwendung",
    # IT-Systeme
    "it-system", "informationssystem", "datenbanksystem", "fachverfahren",
    "fachanwendung", "it-lösung", "it-projekt", "it-dienstleistung",
    # Digitalisierung
    "digitalisierung", "e-government", "ozg", "onlinezugangsgesetz",
    "digital", "elektronisch",
    # Technik-Keywords
    "api", "schnittstelle", "backend", "frontend", "datenbank",
    "cloud", "server", "hosting", "plattform",
    # Programmiersprachen/Frameworks (als Kontext)
    "python", "java", "javascript", "typescript", "vue", "react",
    "angular", "node", "django", "spring", "docker", "kubernetes",
    # IT-Beratung
    "it-beratung", "systemintegration", "softwarearchitektur",
    # Allgemeinere Begriffe (oft in Ausschreibungen)
    "beratungsleistung",  # Häufig bei IT-Beratung
    "dienstleistung",     # Oft IT-Kontext bei Vergaben
    "system",             # IT-System, Informationssystem
    "portal",             # Bürgerportal, Serviceportal
]


def get_search_keywords(max_keywords: int = 8, rotate: bool = True) -> List[str]:
    """Hole Suchbegriffe aus Team-Skills oder Fallback auf TIER_1.

    Liest aktive Team-Mitglieder aus der DB und extrahiert deren Skills.
    Filtert auf bekannte TIER_1_KEYWORDS für relevante Suchergebnisse.
    Mit täglicher Rotation für mehr Projektvielfalt.

    Args:
        max_keywords: Maximale Anzahl Keywords (für URL-Länge)
        rotate: Ob tägliche Rotation aktiviert sein soll (default: True)

    Returns:
        Liste von Suchbegriffen (lowercase)
    """
    import random
    import hashlib
    from datetime import date

    from app.ai.keyword_scoring import TIER_1_KEYWORDS

    # Fallback-Keywords falls DB nicht erreichbar oder leer
    fallback = ["python", "vue", "java", "c#", "django", "spring"]

    try:
        from app.db.session import get_session
        from app.db.models import TeamMember

        with get_session() as session:
            members = session.query(TeamMember).filter(
                TeamMember.active == True
            ).all()

            if not members:
                keywords = fallback
            else:
                # Sammle alle Skills, normalisiere, dedupliziere
                all_skills: set[str] = set()
                for member in members:
                    if member.skills:
                        all_skills.update(s.lower() for s in member.skills)

                if not all_skills:
                    keywords = fallback
                else:
                    # Filter auf bekannte TIER_1 Keywords für präzise Suche
                    tier_1_lower = {kw.lower() for kw in TIER_1_KEYWORDS}
                    matched_keywords = all_skills & tier_1_lower

                    if matched_keywords:
                        keywords = sorted(matched_keywords)
                    else:
                        keywords = fallback

            # Tägliche Rotation falls aktiviert und mehr Keywords als benötigt
            if rotate and len(keywords) > max_keywords:
                # Deterministischer Seed basierend auf Datum
                seed = int(hashlib.md5(str(date.today()).encode()).hexdigest(), 16)
                rng = random.Random(seed)
                return rng.sample(keywords, max_keywords)

            return keywords[:max_keywords]

    except Exception:
        # Bei DB-Fehler: Fallback verwenden
        return fallback[:max_keywords]


def get_portal_config(source_name: str) -> PortalSearchConfig:
    """Get configuration for a portal by name.

    Args:
        source_name: Portal name (e.g., 'gulp', 'freelance.de')

    Returns:
        PortalSearchConfig for the portal, or default config if not found
    """
    return PORTAL_CONFIGS.get(source_name, PortalSearchConfig())


def is_portal_enabled(source_name: str) -> bool:
    """Check if a portal is enabled.

    Args:
        source_name: Portal name

    Returns:
        True if portal is enabled, False otherwise
    """
    config = PORTAL_CONFIGS.get(source_name)
    return config.enabled if config else True
