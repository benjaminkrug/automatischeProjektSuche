"""CPV-Code Pre-Filter for tender pipeline.

CPV (Common Procurement Vocabulary) codes are used in EU public procurement
to classify the subject of contracts. This module filters tenders based on
relevant CPV codes for web/mobile development.
"""

from dataclasses import dataclass
from typing import List, Optional


# Relevante CPV-Codes für Web/Mobile-Entwicklung
RELEVANT_CPV_CODES = {
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
}

# Ausschluss-CPV-Codes (Hardware, SAP, Lizenzen, etc.)
EXCLUDED_CPV_CODES = {
    "48000000": "Softwarepaket und Informationssysteme",  # Lizenzverkauf
    "72220000": "Systemanalyse",  # Nur Beratung
    "72240000": "Systemanalyse und Programmierung",  # Zu breit
    "30200000": "Computeranlagen und Zubehör",  # Hardware
    "32000000": "Rundfunk- und Fernsehgeräte",  # Hardware
    "48100000": "Branchenspezifisches Softwarepaket",  # Meist SAP etc.
    "72253000": "Helpdesk und Unterstützungsdienste",  # Support
    "72300000": "Datendienste",  # Hosting, nicht Entwicklung
}

# Bonus-CPV-Codes (besonders relevant)
BONUS_CPV_CODES = {
    "72212900": 10,  # Webanwendungen
    "72413000": 8,   # Website-Gestaltung
    "72230000": 5,   # Kundenspezifische Software
    "72262000": 5,   # Softwareentwicklungsdienste
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


def passes_cpv_filter(cpv_codes: Optional[List[str]]) -> CpvFilterResult:
    """Pre-Filter: Check if CPV codes indicate relevant tender.

    Args:
        cpv_codes: List of CPV codes from the tender

    Returns:
        CpvFilterResult with filter decision and details
    """
    if not cpv_codes:
        # No CPV codes - can't filter, pass through for text-based analysis
        return CpvFilterResult(
            passes=True,
            relevant_codes=[],
            excluded_codes=[],
            bonus_score=0,
            reason="Keine CPV-Codes vorhanden - Text-Analyse erforderlich",
        )

    relevant_found = []
    excluded_found = []
    bonus_score = 0

    for code in cpv_codes:
        normalized = normalize_cpv_code(code)

        # Check for relevant codes
        if normalized in RELEVANT_CPV_CODES:
            relevant_found.append(f"{normalized} ({RELEVANT_CPV_CODES[normalized]})")
            if normalized in BONUS_CPV_CODES:
                bonus_score += BONUS_CPV_CODES[normalized]

        # Check for excluded codes
        if normalized in EXCLUDED_CPV_CODES:
            excluded_found.append(f"{normalized} ({EXCLUDED_CPV_CODES[normalized]})")

    # Decision logic
    if excluded_found and not relevant_found:
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
