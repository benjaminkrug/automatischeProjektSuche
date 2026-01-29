"""Client enrichment with known contracting authority data.

Provides pre-populated information about known German public sector
IT clients for improved scoring and decision-making.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger("sourcing.client_enrichment")


@dataclass
class KnownClientInfo:
    """Pre-populated information about a known client."""

    name: str
    aliases: List[str] = field(default_factory=list)
    tech_affinity: str = "medium"  # low, medium, high
    preferred_stack: List[str] = field(default_factory=list)
    avg_budget: Optional[int] = None  # Typical project budget EUR
    sector: str = "bund"  # bund, land, kommune
    security_level: str = "normal"  # normal, high (BSI, ISO required)
    payment_rating: int = 3  # 1-5 stars
    notes: str = ""

    @property
    def is_high_tech(self) -> bool:
        """Check if client has high tech affinity."""
        return self.tech_affinity == "high"


# Known German public sector IT clients
KNOWN_CLIENTS: Dict[str, KnownClientInfo] = {
    # Federal IT service providers
    "ITZBund": KnownClientInfo(
        name="Informationstechnikzentrum Bund",
        aliases=[
            "itzbund",
            "it-zentrum bund",
            "informationstechnikzentrum bund",
            "bmf itzbund",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "Angular", "Spring", "Oracle", "SAP"],
        avg_budget=500000,
        sector="bund",
        security_level="high",
        payment_rating=4,
        notes="Zentraler IT-Dienstleister des Bundes. Gute Zusammenarbeit mit Beratungsunternehmen.",
    ),

    "BWI": KnownClientInfo(
        name="BWI GmbH",
        aliases=[
            "bwi",
            "bwi gmbh",
            "bundeswehr it",
            "bw informationstechnik",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "SAP", ".NET", "Oracle"],
        avg_budget=800000,
        sector="bund",
        security_level="high",
        payment_rating=4,
        notes="IT-Systemhaus der Bundeswehr. Hohe Sicherheitsanforderungen, oft VS-NfD.",
    ),

    "Dataport": KnownClientInfo(
        name="Dataport AöR",
        aliases=[
            "dataport",
            "dataport aör",
            "dataport anstalt",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "OpenSource", "Linux", "Kubernetes"],
        avg_budget=300000,
        sector="land",
        security_level="normal",
        payment_rating=5,
        notes="IT-Dienstleister für Hamburg, SH, Bremen, ST, MV. Open-Source-affin.",
    ),

    "AKDB": KnownClientInfo(
        name="AKDB Anstalt für Kommunale Datenverarbeitung in Bayern",
        aliases=[
            "akdb",
            "anstalt für kommunale datenverarbeitung",
            "kommunale datenverarbeitung bayern",
        ],
        tech_affinity="medium",
        preferred_stack=["Java", ".NET", "Oracle"],
        avg_budget=200000,
        sector="kommune",
        security_level="normal",
        payment_rating=4,
        notes="IT-Dienstleister für bayerische Kommunen.",
    ),

    "FITKO": KnownClientInfo(
        name="FITKO - Föderale IT-Kooperation",
        aliases=[
            "fitko",
            "föderale it-kooperation",
            "föderale it kooperation",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "Kubernetes", "OpenSource"],
        avg_budget=400000,
        sector="bund",
        security_level="normal",
        payment_rating=4,
        notes="Koordiniert OZG-Umsetzung. Innovative Projekte, föderale Cloud.",
    ),

    "Bundesagentur für Arbeit": KnownClientInfo(
        name="Bundesagentur für Arbeit",
        aliases=[
            "bundesagentur für arbeit",
            "ba",
            "arbeitsagentur",
            "agentur für arbeit",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "Angular", "Oracle", "Kubernetes"],
        avg_budget=600000,
        sector="bund",
        security_level="normal",
        payment_rating=4,
        notes="Großer IT-Arbeitgeber. Moderne Stack, agile Methoden.",
    ),

    "Destatis": KnownClientInfo(
        name="Statistisches Bundesamt",
        aliases=[
            "destatis",
            "statistisches bundesamt",
            "stba",
        ],
        tech_affinity="medium",
        preferred_stack=["Java", "R", "Python", "SAS"],
        avg_budget=250000,
        sector="bund",
        security_level="normal",
        payment_rating=4,
        notes="Statistik-IT. Viele Datenverarbeitungsprojekte.",
    ),

    "Bundeskartellamt": KnownClientInfo(
        name="Bundeskartellamt",
        aliases=[
            "bundeskartellamt",
            "bkarta",
            "kartellamt",
        ],
        tech_affinity="medium",
        preferred_stack=["Java", ".NET"],
        avg_budget=150000,
        sector="bund",
        security_level="normal",
        payment_rating=4,
        notes="Kleinere IT-Projekte, oft Fachverfahren.",
    ),

    "BMI": KnownClientInfo(
        name="Bundesministerium des Innern",
        aliases=[
            "bmi",
            "bundesinnenministerium",
            "bundesministerium des innern",
            "innenministerium",
        ],
        tech_affinity="high",
        preferred_stack=["Java", ".NET", "SAP"],
        avg_budget=500000,
        sector="bund",
        security_level="high",
        payment_rating=3,
        notes="Oft über Rahmenverträge. Sicherheitsanforderungen beachten.",
    ),

    "BSI": KnownClientInfo(
        name="Bundesamt für Sicherheit in der Informationstechnik",
        aliases=[
            "bsi",
            "bundesamt sicherheit informationstechnik",
            "bundesamt für sicherheit",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "Python", "Linux"],
        avg_budget=300000,
        sector="bund",
        security_level="high",
        payment_rating=4,
        notes="Höchste Sicherheitsanforderungen. Oft BSI-Grundschutz-Zertifizierung nötig.",
    ),

    "BVA": KnownClientInfo(
        name="Bundesverwaltungsamt",
        aliases=[
            "bva",
            "bundesverwaltungsamt",
        ],
        tech_affinity="medium",
        preferred_stack=["Java", ".NET", "Oracle"],
        avg_budget=250000,
        sector="bund",
        security_level="normal",
        payment_rating=4,
        notes="Viele Fachverfahren. Register-Projekte.",
    ),

    "DRV Bund": KnownClientInfo(
        name="Deutsche Rentenversicherung Bund",
        aliases=[
            "drv",
            "drv bund",
            "deutsche rentenversicherung",
            "rentenversicherung bund",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "COBOL", "DB2"],
        avg_budget=400000,
        sector="bund",
        security_level="normal",
        payment_rating=4,
        notes="Große IT-Abteilung. Mix aus Legacy und Modern.",
    ),

    "gematik": KnownClientInfo(
        name="gematik GmbH",
        aliases=[
            "gematik",
            "gematik gmbh",
        ],
        tech_affinity="high",
        preferred_stack=["Java", "Kotlin", "Kubernetes", "OpenID"],
        avg_budget=500000,
        sector="bund",
        security_level="high",
        payment_rating=3,
        notes="Telematikinfrastruktur. Hohe Sicherheit, komplexe Spezifikationen.",
    ),
}


def normalize_client_name_for_lookup(name: str) -> str:
    """Normalize client name for lookup in known clients.

    Args:
        name: Raw client name

    Returns:
        Normalized name for matching
    """
    if not name:
        return ""

    normalized = name.lower()

    # Remove common suffixes
    suffixes = ["gmbh", "ag", "aör", "e.v.", "anstalt"]
    for suffix in suffixes:
        normalized = normalized.replace(suffix, "")

    # Remove extra whitespace
    normalized = " ".join(normalized.split())

    return normalized.strip()


def find_known_client(client_name: str) -> Optional[KnownClientInfo]:
    """Find known client by name or alias.

    Args:
        client_name: Client name to look up

    Returns:
        KnownClientInfo if found, None otherwise
    """
    if not client_name:
        return None

    normalized = normalize_client_name_for_lookup(client_name)

    # Direct lookup by key
    for key, info in KNOWN_CLIENTS.items():
        if normalized == normalize_client_name_for_lookup(key):
            return info

    # Check aliases
    for info in KNOWN_CLIENTS.values():
        for alias in info.aliases:
            if normalized == alias or alias in normalized or normalized in alias:
                return info

    return None


def enrich_client(client_name: str) -> Optional[KnownClientInfo]:
    """Get enrichment data for a client.

    Args:
        client_name: Client name

    Returns:
        KnownClientInfo with pre-populated data, or None
    """
    return find_known_client(client_name)


def get_client_score_modifier(client_name: str) -> int:
    """Get score modifier based on known client data.

    Args:
        client_name: Client name

    Returns:
        Score modifier (positive or negative)
    """
    info = find_known_client(client_name)

    if not info:
        return 0

    modifier = 0

    # Tech affinity bonus
    if info.tech_affinity == "high":
        modifier += 10
    elif info.tech_affinity == "medium":
        modifier += 5

    # Payment rating bonus
    if info.payment_rating >= 4:
        modifier += 5
    elif info.payment_rating <= 2:
        modifier -= 5

    # Security level consideration
    if info.security_level == "high":
        # Could be positive (stable client) or negative (barriers)
        # Neutral for now, let eligibility check handle it
        pass

    return modifier


def get_preferred_tech_overlap(
    client_name: str,
    project_tech: List[str],
) -> int:
    """Calculate tech stack overlap with known client preferences.

    Args:
        client_name: Client name
        project_tech: Tech stack detected in project

    Returns:
        Number of matching technologies
    """
    info = find_known_client(client_name)

    if not info or not info.preferred_stack:
        return 0

    # Normalize for comparison
    client_tech = {t.lower() for t in info.preferred_stack}
    project_tech_lower = {t.lower() for t in project_tech}

    return len(client_tech & project_tech_lower)


def get_all_known_clients() -> List[KnownClientInfo]:
    """Get list of all known clients.

    Returns:
        List of KnownClientInfo
    """
    return list(KNOWN_CLIENTS.values())


def get_clients_by_sector(sector: str) -> List[KnownClientInfo]:
    """Get known clients by sector.

    Args:
        sector: Sector (bund, land, kommune)

    Returns:
        List of KnownClientInfo in that sector
    """
    return [
        info for info in KNOWN_CLIENTS.values()
        if info.sector == sector
    ]


def get_high_tech_clients() -> List[KnownClientInfo]:
    """Get clients with high tech affinity.

    Returns:
        List of tech-affine clients
    """
    return [
        info for info in KNOWN_CLIENTS.values()
        if info.tech_affinity == "high"
    ]
