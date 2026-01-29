"""CPV-Code Pre-Filter for tender pipeline.

CPV (Common Procurement Vocabulary) codes are used in EU public procurement
to classify the subject of contracts. This module filters tenders based on
relevant CPV codes for web/mobile development.

M1: Added hierarchical CPV code matching for better coverage.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger("sourcing.cpv_filter")


# Relevante CPV-Codes für Web/Mobile-Entwicklung
RELEVANT_CPV_CODES = {
    # === 72xxx Softwareentwicklung (bestehend) ===
    "72200000": "Softwareprogrammierung und -beratung",
    "72210000": "Programmierung von Softwarepaketen",
    "72211000": "Programmierung von System- und Anwendersoftware",
    "72212000": "Programmierung von Anwendersoftware",
    "72212100": "Branchenspezifische Softwareentwicklung",
    "72212500": "Entwicklung von Kommunikations-/Multimedia-Software",
    "72212900": "Diverse Softwareentwicklung (Webanwendungen)",
    "72230000": "Entwicklung von kundenspezifischer Software",
    "72232000": "Entwicklung von Transaktionsverarbeitungssoftware",
    "72260000": "Softwarebezogene Dienstleistungen",
    "72262000": "Softwareentwicklungsdienste",
    "72413000": "Website-Gestaltung",
    "72414000": "Suchmaschinen für Datenabfrage",
    "72415000": "Hosting für Website-Betrieb",
    "72416000": "Application Service Provider",
    # === 72xxx Internet & Web (neu) ===
    "72400000": "Internetdienste",
    "72420000": "Internet-Entwicklungsdienste",
    "72421000": "Internet/Intranet-Client-Anwendungsentwicklung",
    "72422000": "Internet/Intranet-Server-Anwendungsentwicklung",
    # === 72xxx Beratung & Analyse (neu) ===
    "72220000": "Systemberatung und technische Beratung",
    "72222000": "Beratung im Bereich Informationstechnologie",
    "72222300": "IT-Beratungsdienste",
    "72227000": "Beratung im Bereich Software-Integration",
    "72240000": "Systemanalyse und Programmierung",
    # === 72xxx Software-Lifecycle (neu) ===
    "72263000": "Software-Implementierung",
    "72254000": "Softwaretest",
    "72265000": "Software-Konfiguration",
    "72266000": "Software-Beratung",
    "72267000": "Software-Wartung und -Reparatur",
    "72320000": "Datenbankdienste",
    # === 48xxx Softwarepakete & Systeme (neu) ===
    "48200000": "Software für Vernetzung, Internet und Intranet",
    "48220000": "Internet-Softwarepaket",
    "48400000": "Software für Geschäftstransaktionen",
    "48500000": "Kommunikations- und Multimedia-Software",
    "48600000": "Datenbank- und Betriebssoftware",
    "48610000": "Datenbanksysteme",
    "48700000": "Softwarepaket-Dienstprogramme",
    "48800000": "Informationssysteme und Server",
    "48810000": "Informationssysteme",
}

# Ausschluss-CPV-Codes (Hardware, SAP, Lizenzen, etc.)
# Note: Don't exclude too aggressively - let text analysis decide
# 48000000 entfernt - zu breit, relevante Untercodes sind jetzt in RELEVANT
EXCLUDED_CPV_CODES = {
    "30200000": "Computeranlagen und Zubehör",  # Hardware
    "32000000": "Rundfunk- und Fernsehgeräte",  # Hardware
    "48100000": "Branchenspezifisches Softwarepaket",  # Meist SAP etc.
    "72253000": "Helpdesk und Unterstützungsdienste",  # Support
}

# Bonus-CPV-Codes (besonders relevant)
BONUS_CPV_CODES = {
    "72212900": 10,  # Webanwendungen
    "72413000": 8,   # Website-Gestaltung
    "72230000": 5,   # Kundenspezifische Software
    "72262000": 5,   # Softwareentwicklungsdienste
    # Neue Bonus-Codes
    "72420000": 10,  # Internet-Entwicklungsdienste
    "72421000": 8,   # Client-Entwicklung
    "72422000": 8,   # Server-Entwicklung
    "48220000": 5,   # Internet-Softwarepaket
    "48810000": 5,   # Informationssysteme
}


@dataclass
class CpvFilterResult:
    """Result of CPV code filtering."""
    passes: bool
    relevant_codes: List[str]
    excluded_codes: List[str]
    bonus_score: int
    reason: Optional[str]


def normalize_cpv_code(code: str) -> str:
    """Normalize CPV code to 8-digit format without check digit.

    CPV codes can be:
    - 8 digits: 72200000
    - 8 digits + check digit: 72200000-7
    - Partial codes: 722
    """
    # Remove check digit suffix if present
    code = code.split("-")[0].strip()
    # Pad with zeros if partial
    if len(code) < 8:
        code = code.ljust(8, "0")
    return code[:8]


# M1: CPV-Code Hierarchie-Prefixe für relevante Bereiche
# Erste 2-5 Ziffern definieren die Kategorie
CPV_HIERARCHY_PREFIXES = {
    "72": "IT-Dienstleistungen",           # Alle IT-Services
    "722": "Softwareprogrammierung",        # Software allgemein
    "7220": "Softwareentwicklung",          # Entwicklung spezifisch
    "7221": "Anwendersoftware",             # Anwendungsentwicklung
    "7226": "Softwaredienstleistungen",     # Software-Services
    "7241": "Webdienste",                   # Web-Services
    # Neue Hierarchie-Prefixe
    "724": "Internetdienste",               # Internet-Services
    "7242": "Internet-Entwicklung",         # Internet-Entwicklung
    "482": "Internet/Netzwerk-Software",    # Netzwerk-Software
    "486": "Datenbank-Software",            # Datenbank-Software
    "488": "Informationssysteme",           # Informationssysteme
}


def _matches_cpv_hierarchy(code: str) -> Tuple[bool, int, str]:
    """M1: Prüfe ob CPV-Code hierarchisch relevant ist.

    Verwendet Prefix-Matching für übergeordnete CPV-Kategorien.

    Args:
        code: Normalisierter 8-stelliger CPV-Code

    Returns:
        Tuple (is_match, bonus_score, description)
    """
    # Prüfe Prefixe von lang nach kurz
    for prefix_len in [5, 4, 3, 2]:
        prefix = code[:prefix_len]
        if prefix in CPV_HIERARCHY_PREFIXES:
            # Reduzierter Bonus für Hierarchie-Match (weniger spezifisch)
            bonus = max(1, 5 - prefix_len)  # Kürzerer Prefix = niedrigerer Bonus
            desc = f"Hierarchie ({prefix}): {CPV_HIERARCHY_PREFIXES[prefix]}"
            logger.debug("CPV hierarchy match: %s -> %s", code, desc)
            return True, bonus, desc

    return False, 0, ""


def passes_cpv_filter(
    cpv_codes: Optional[List[str]],
    title: str = "",
    description: str = "",
) -> CpvFilterResult:
    """Pre-Filter: Check if CPV codes indicate relevant tender.

    Args:
        cpv_codes: List of CPV codes from the tender
        title: Project title for text-based fallback
        description: Project description for text-based fallback

    Returns:
        CpvFilterResult with filter decision and details
    """
    if not cpv_codes:
        # Text-basierter Fallback statt Bypass
        text = f"{title} {description}".lower()
        software_keywords = [
            # Bestehend
            "software", "entwicklung", "webapp", "portal",
            "anwendung", "plattform", "app", "webentwicklung",
            "programmierung", "it-system", "digitalisierung",
            "webanwendung", "applikation", "fachverfahren",
            # === NEU ===
            "informationssystem", "datenbank", "schnittstelle",
            "api", "backend", "frontend", "cloud", "saas",
            "e-government", "onlinedienst", "serviceportal",
            "digitale lösung", "it-dienstleistung", "softwarelösung",
            "individualsoftware", "branchensoftware", "fachanwendung",
        ]
        if any(kw in text for kw in software_keywords):
            return CpvFilterResult(
                passes=True,
                relevant_codes=[],
                excluded_codes=[],
                bonus_score=0,
                reason="Text-Fallback: Software-Keywords gefunden",
            )
        return CpvFilterResult(
            passes=False,
            relevant_codes=[],
            excluded_codes=[],
            bonus_score=0,
            reason="Keine CPV-Codes und keine Software-Keywords im Text",
        )

    relevant_found = []
    excluded_found = []
    hierarchy_matches = []
    bonus_score = 0

    for code in cpv_codes:
        normalized = normalize_cpv_code(code)

        # Check for relevant codes (exact match - highest priority)
        if normalized in RELEVANT_CPV_CODES:
            relevant_found.append(f"{normalized} ({RELEVANT_CPV_CODES[normalized]})")
            if normalized in BONUS_CPV_CODES:
                bonus_score += BONUS_CPV_CODES[normalized]
            continue  # Skip hierarchy check for exact matches

        # Check for excluded codes
        if normalized in EXCLUDED_CPV_CODES:
            excluded_found.append(f"{normalized} ({EXCLUDED_CPV_CODES[normalized]})")
            continue  # Skip hierarchy check for excluded codes

        # M1: Check for hierarchical matches (prefix-based)
        is_hierarchy_match, hierarchy_bonus, hierarchy_desc = _matches_cpv_hierarchy(normalized)
        if is_hierarchy_match:
            hierarchy_matches.append(f"{normalized} ({hierarchy_desc})")
            bonus_score += hierarchy_bonus

    # Decision logic
    if excluded_found and not relevant_found and not hierarchy_matches:
        return CpvFilterResult(
            passes=False,
            relevant_codes=relevant_found,
            excluded_codes=excluded_found,
            bonus_score=0,
            reason=f"Nur Ausschluss-CPV-Codes: {', '.join(excluded_found)}",
        )

    if relevant_found:
        return CpvFilterResult(
            passes=True,
            relevant_codes=relevant_found,
            excluded_codes=excluded_found,
            bonus_score=bonus_score,
            reason=f"Relevante CPV-Codes: {', '.join(relevant_found)}",
        )

    # M1: Check for hierarchy matches
    if hierarchy_matches:
        return CpvFilterResult(
            passes=True,
            relevant_codes=hierarchy_matches,  # Use hierarchy matches as relevant
            excluded_codes=excluded_found,
            bonus_score=bonus_score,
            reason=f"CPV-Hierarchie-Match: {', '.join(hierarchy_matches)}",
        )

    # No relevant or excluded codes - pass through for text analysis
    return CpvFilterResult(
        passes=True,
        relevant_codes=[],
        excluded_codes=[],
        bonus_score=0,
        reason="Keine bekannten CPV-Codes - Text-Analyse erforderlich",
    )


def get_cpv_code_description(code: str) -> Optional[str]:
    """Get description for a CPV code."""
    normalized = normalize_cpv_code(code)
    if normalized in RELEVANT_CPV_CODES:
        return RELEVANT_CPV_CODES[normalized]
    if normalized in EXCLUDED_CPV_CODES:
        return EXCLUDED_CPV_CODES[normalized]
    return None
