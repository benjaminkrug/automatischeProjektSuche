"""Tender scoring and filtering for public sector tenders.

This module provides specialized scoring for public tenders (Ausschreibungen)
with focus on web/mobile development projects.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Tuple

from app.settings import (
    settings,
    ACCESSIBILITY_CAPABILITIES,
    SECURITY_CAPABILITIES,
)


# ============================================================
# Data Classes
# ============================================================


@dataclass
class TechAnalysisResult:
    """Result of technology requirements analysis."""
    requires_webapp: bool = False
    webapp_evidence: Optional[str] = None
    requires_mobile: bool = False
    mobile_evidence: Optional[str] = None
    tech_stack_matches: List[str] = field(default_factory=list)


@dataclass
class AccessibilityResult:
    """Result of accessibility requirements check."""
    required: List[str] = field(default_factory=list)
    can_deliver: bool = True
    score_impact: int = 0


@dataclass
class SecurityResult:
    """Result of security requirements check."""
    required: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    can_deliver: bool = True


@dataclass
class ConsortiumResult:
    """Result of consortium/SME suitability check."""
    consortium_allowed: bool = True
    consortium_encouraged: bool = False
    needs_consortium_for_eligibility: bool = False
    sme_friendly: bool = False
    recommendation: Optional[str] = None


@dataclass
class AwardCriteria:
    """Extracted award criteria from tender."""
    price_weight: Optional[int] = None
    quality_weight: Optional[int] = None
    favors_quality: bool = False


@dataclass
class TenderScore:
    """Final scoring result for a tender."""
    total: int = 0
    normalized: int = 0  # 0-100 scale
    reasons: List[str] = field(default_factory=list)
    skip: bool = False
    skip_reason: Optional[str] = None

    # Score breakdown
    tech_score: int = 0
    volume_score: int = 0
    procedure_score: int = 0
    award_criteria_score: int = 0
    eligibility_score: int = 0
    accessibility_score: int = 0
    security_score: int = 0
    consortium_score: int = 0
    client_score: int = 0
    deadline_score: int = 0


# ============================================================
# Pattern Definitions
# ============================================================


def _create_fuzzy_pattern(base: str) -> str:
    """M3: Erstelle Regex mit deutschen Verb-Varianten.

    Ermöglicht flexibleres Matching von deutschen Wörtern:
    - entwicklung → entwickl(ung|en|t|te|eln)
    - programmierung → programm(ierung|ieren|iert)

    Args:
        base: Basiswort (z.B. "entwicklung")

    Returns:
        Regex-Pattern mit Varianten
    """
    # Deutsche Verb-Suffixe
    if base.endswith("ung"):
        stem = base[:-3]
        return rf"{stem}(ung|en|t|te|eln)"
    elif base.endswith("ierung"):
        stem = base[:-6]
        return rf"{stem}(ierung|ieren|iert)"
    elif base.endswith("tion"):
        stem = base[:-4]
        return rf"{stem}(tion|tionen)"
    return base


# M3: Fuzzy-Patterns für häufige deutsche Begriffe
FUZZY_ENTWICKLUNG = _create_fuzzy_pattern("entwicklung")
FUZZY_PROGRAMMIERUNG = _create_fuzzy_pattern("programmierung")
FUZZY_ERSTELLUNG = _create_fuzzy_pattern("erstellung")
FUZZY_GESTALTUNG = _create_fuzzy_pattern("gestaltung")


# Webanwendung-Indikatoren (explizite Forderung)
# M3: Mit Fuzzy-Matching für deutsche Verben
WEBAPP_PATTERNS = [
    # Einfache Keyword-Patterns (Fallback - höchste Priorität)
    r"\bwebanwendung\b",
    r"\bwebapplikation\b",
    r"\bwebportal\b",
    r"\bweb-anwendung\b",
    r"\bweb-applikation\b",
    # M3: Fuzzy-Patterns für flexible Verb-Erkennung
    rf"{FUZZY_ENTWICKLUNG}\s+.{{0,30}}webanwendung",  # Erlaubt bis zu 30 Zeichen dazwischen
    rf"webanwendung\s+({FUZZY_ERSTELLUNG}|{FUZZY_ENTWICKLUNG}|{FUZZY_PROGRAMMIERUNG}|soll|muss)",
    rf"webapplikation\s+(soll|muss|ist\s+zu|{FUZZY_ERSTELLUNG}|{FUZZY_ENTWICKLUNG})",
    r"webbasiert(e|es|en)?\s+(portal|system|anwendung|lösung|plattform)",
    r"browser-basiert",
    rf"responsive\s+.{{0,20}}(web|anwendung|applikation)",  # Flexibler
    rf"frontend[- ]?{FUZZY_ENTWICKLUNG}",
    rf"(react|vue|angular|next\.?js|nuxt)\s+(anwendung|applikation|{FUZZY_ENTWICKLUNG})",
    rf"web[- ]?(app|application|portal)\s+({FUZZY_ENTWICKLUNG}|{FUZZY_ERSTELLUNG}|{FUZZY_PROGRAMMIERUNG})",
    r"online[- ]?(portal|plattform|anwendung)",
    r"single[- ]page[- ]application",
    r"progressive[- ]web[- ]app",
    # Webseiten-Erkennung (klassische Websites, nicht nur Web-Apps)
    rf"({FUZZY_ERSTELLUNG}|{FUZZY_ENTWICKLUNG}|{FUZZY_PROGRAMMIERUNG}|relaunch|neu{FUZZY_GESTALTUNG})\s+.{{0,20}}(web(site|seite)|homepage|internetseite)",
    rf"(web(site|seite)|homepage|internetseite|internetauftritt)\s+({FUZZY_ERSTELLUNG}|{FUZZY_ENTWICKLUNG}|{FUZZY_PROGRAMMIERUNG}|neugestalten|relaunchen)",
    r"landingpage",
    rf"(web(site|seite)|homepage)[- ]?(design|{FUZZY_ENTWICKLUNG}|{FUZZY_ERSTELLUNG}|relaunch)",
    # M3: Zusätzliche Fuzzy-Patterns
    rf"software[- ]?{FUZZY_ENTWICKLUNG}",
    rf"anwendungs[- ]?{FUZZY_ENTWICKLUNG}",
    rf"portal[- ]?{FUZZY_ENTWICKLUNG}",
    rf"plattform[- ]?{FUZZY_ENTWICKLUNG}",
    # === NEU: Cloud & Plattform ===
    rf"plattform[- ]?(?:{FUZZY_ENTWICKLUNG}|konzept|lösung)",
    r"digitale?\s+(?:lösung|plattform|anwendung)",
    r"cloud[- ]?(?:lösung|anwendung|system|basiert)",
    r"saas[- ]?(?:lösung|anwendung|plattform)",
    # === NEU: Informationssysteme ===
    r"informations?system.*(?:web|online|cloud|browser)",
    r"(?:fach|verwaltungs|management)[- ]?system.*(?:web|online)",
    # === NEU: Portale ===
    r"(?:behörden|service|bürger|kunden|mitarbeiter)[- ]?portal",
    r"self[- ]?service[- ]?portal",
    # === NEU: Digitalisierung ===
    r"digitalisierung.*(?:prozess|verwaltung|service)",
    r"e[- ]?government",
    r"(?:web|browser)[- ]?basiert(?:e|es)?\s+(?:anwendung|system|lösung)",

    # === NEU: Verwaltungssysteme (häufig in öffentlichen Ausschreibungen) ===
    r"(?:fach|sachbearbeitungs)[- ]?verfahren",
    r"verwaltungs[- ]?system",
    r"case[- ]?management[- ]?system",
    r"(?:document|dokument)[- ]?management",
    r"(?:dms|dokumenten[- ]?verwaltung)",

    # === NEU: Business-Systeme ===
    r"(?:cms|content[- ]?management)",
    r"(?:crm|customer[- ]?relationship)",
    r"(?:erp|enterprise[- ]?resource)",
    r"(?:hr|personal)[- ]?management[- ]?system",
    r"(?:workflow|prozess)[- ]?(?:management|automation)",

    # === NEU: Portale & Services ===
    r"(?:bürger|citizen)[- ]?(?:portal|service)",
    r"(?:service)[- ]?portal",
    r"(?:intranet|extranet)",
    r"(?:collaboration|teamwork)[- ]?(?:plattform|lösung)",

    # === NEU: Analytics & Reporting ===
    r"(?:data|business|analytics)[- ]?dashboard",
    r"(?:reporting|auswertungs)[- ]?(?:tool|system)",
    r"(?:bi|business[- ]?intelligence)",

    # === NEU: Modernisierung (oft Web-Migration) ===
    r"(?:modernisierung|ablösung|migration)\s+.{0,30}(?:system|anwendung|software)",
    r"(?:neuausschreibung|erneuerung)\s+.{0,20}(?:system|anwendung)",

    # === NEU: Learning & Training ===
    r"(?:e[- ]?)?learning[- ]?(?:plattform|system)",
    r"(?:lms|learning[- ]?management)",
    r"(?:schulungs|training)[- ]?(?:portal|plattform)",
]

# Mobile App-Indikatoren (explizite Forderung)
# M3: Mit Fuzzy-Matching
MOBILE_PATTERNS = [
    rf"(mobile|native)\s+app\s+({FUZZY_ENTWICKLUNG}|{FUZZY_ERSTELLUNG}|{FUZZY_PROGRAMMIERUNG})",
    r"ios[- ]und[- ]android",
    r"(ios|android)[- ]app",
    r"smartphone[- ]app",
    rf"(flutter|react\s*native|kotlin|swift)\s+(app|anwendung|{FUZZY_ENTWICKLUNG})",
    r"app\s+für\s+(ios|android|mobile\s+endgeräte|smartphones?)",
    r"mobile\s+(anwendung|applikation|lösung)",
    r"(tablet|ipad|android)[- ]?(app|anwendung)",
    rf"cross[- ]?platform[- ]?(app|{FUZZY_ENTWICKLUNG})",
    # M3: Zusätzliche Mobile-Patterns
    rf"app[- ]?{FUZZY_ENTWICKLUNG}",
    rf"mobile[- ]?{FUZZY_ENTWICKLUNG}",

    # === NEU: Deutsche Varianten ===
    r"(?:smartphone|handy)[- ]?(?:app|anwendung|applikation)",
    r"(?:tablet|ipad)[- ]?(?:tauglich|optimiert|kompatibel)",
    r"(?:ios|android)[- ]?(?:kompatibel|fähig|unterstützung)",
    r"touch[- ]?(?:optimiert|fähig|bedienung)",
    r"(?:mobil|mobile)[- ]?(?:nutzung|zugriff|version)",
    r"(?:responsive|adaptiv)[- ]?(?:design|layout|darstellung)",
    r"(?:pwa|progressive\s+web\s+app)",
    r"offline[- ]?(?:fähig|nutzung|modus)",
    r"(?:push|benachrichtigungs)[- ]?(?:funktion|dienst)",
    r"(?:geräte|device)[- ]?(?:unabhängig|übergreifend)",

    # === NEU: App-Store & Distribution ===
    r"app[- ]?store",
    r"(?:google\s+)?play\s+store",
    r"(?:apple\s+)?app\s+store",

    # === NEU: Mobile-spezifische Funktionen ===
    r"(?:gps|standort)[- ]?(?:basiert|funktion|dienst)",
    r"(?:kamera|foto)[- ]?(?:funktion|integration)",
    r"(?:qr|barcode)[- ]?(?:scan|reader|erkennung)",
    r"nfc[- ]?(?:funktion|fähig|unterstützung)",
    r"biometr(?:ie|isch)[- ]?(?:authentifizierung|login|zugang)",

    # === NEU: Mobile-First & Responsive ===
    r"mobile[- ]?first",
    r"(?:mobil|mobile)[- ]?(?:endgerät|device|plattform)",
    r"(?:smartphone|tablet)[- ]?(?:version|variante|ansicht)",
]

# Pre-compiled regex patterns for performance
COMPILED_WEBAPP_PATTERNS = [re.compile(p, re.IGNORECASE) for p in WEBAPP_PATTERNS]
COMPILED_MOBILE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in MOBILE_PATTERNS]

# Tech-Stack Keywords
TECH_STACK_KEYWORDS = [
    "react", "vue", "angular", "typescript", "node.js", "nodejs",
    "flutter", "kotlin", "swift", "react native", "ionic",
    "python", "django", "fastapi", "flask",
    "postgresql", "mongodb", "mysql",
    "docker", "kubernetes", "aws", "azure",
    "graphql", "rest api", "restful",
    "next.js", "nuxt", "gatsby",
]

# Vergabeart-Scoring
PROCEDURE_SCORES = {
    "verhandlungsverfahren": 15,       # Beste Chance
    "wettbewerblicher_dialog": 12,
    "beschraenkte_ausschreibung": 10,
    "innovationspartnerschaft": 10,
    "offenes_verfahren": 0,            # Viele Bieter
    "direktvergabe": -10,              # Meist schon vergeben
    "unknown": 0,
}

# Sicherheitsanforderungen
SECURITY_REQUIREMENTS = {
    "bsi_grundschutz": ["bsi-grundschutz", "bsi grundschutz", "it-grundschutz"],
    "iso_27001": ["iso 27001", "iso27001", "isms"],
    "dsgvo_konform": ["dsgvo", "datenschutz-grundverordnung", "gdpr"],
    "penetrationstest": ["pentest", "penetrationstest", "security audit"],
}

# Barrierefreiheits-Keywords
ACCESSIBILITY_KEYWORDS = {
    "bitv_2.0": ["bitv", "bitv 2.0", "bitv 2.1"],
    "wcag_2.1_aa": ["wcag 2.1 aa", "wcag aa", "wcag 2.0 aa"],
    "wcag_2.1_aaa": ["wcag 2.1 aaa", "wcag aaa"],
    "general": ["barrierefreiheit", "barrierefrei", "screen reader", "screenreader",
                "eu-richtlinie 2016/2102"],
}


# ============================================================
# Helper Functions
# ============================================================


def find_pattern_matches(text: str, patterns: List[str]) -> List[str]:
    """Find all pattern matches in text."""
    matches = []
    for pattern in patterns:
        found = re.findall(pattern, text, re.IGNORECASE)
        if found:
            # Get the actual matched string
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                matches.append(match.group(0))
    return matches


def find_compiled_pattern_matches(text: str, compiled_patterns: list) -> List[str]:
    """Find all pattern matches using pre-compiled regex patterns."""
    matches = []
    for pattern in compiled_patterns:
        match = pattern.search(text)
        if match:
            matches.append(match.group(0))
    return matches


def find_percentage(text: str, keyword: str) -> Optional[int]:
    """Find percentage value associated with a keyword."""
    pattern = rf"{keyword}[:\s]+(\d+)\s*%"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


# ============================================================
# Analysis Functions
# ============================================================


def analyze_tech_requirements(description: str, pdf_text: str = "") -> TechAnalysisResult:
    """Analyze whether web/mobile development is explicitly required.

    Args:
        description: Project description
        pdf_text: Optional text extracted from PDF documents

    Returns:
        TechAnalysisResult with analysis details
    """
    combined_text = f"{description} {pdf_text}".lower()

    webapp_matches = find_compiled_pattern_matches(combined_text, COMPILED_WEBAPP_PATTERNS)
    mobile_matches = find_compiled_pattern_matches(combined_text, COMPILED_MOBILE_PATTERNS)

    # Tech-Stack-Erkennung
    stack_matches = [kw for kw in TECH_STACK_KEYWORDS if kw.lower() in combined_text]

    return TechAnalysisResult(
        requires_webapp=len(webapp_matches) > 0,
        webapp_evidence=webapp_matches[0] if webapp_matches else None,
        requires_mobile=len(mobile_matches) > 0,
        mobile_evidence=mobile_matches[0] if mobile_matches else None,
        tech_stack_matches=stack_matches,
    )


def detect_procedure_type(description: str) -> str:
    """Detect procurement procedure type from description."""
    desc_lower = description.lower()

    if "verhandlungsverfahren" in desc_lower:
        return "verhandlungsverfahren"
    elif "beschränkte ausschreibung" in desc_lower or "nichtoffenes verfahren" in desc_lower:
        return "beschraenkte_ausschreibung"
    elif "offenes verfahren" in desc_lower or "öffentliche ausschreibung" in desc_lower:
        return "offenes_verfahren"
    elif "wettbewerblicher dialog" in desc_lower:
        return "wettbewerblicher_dialog"
    elif "innovationspartnerschaft" in desc_lower:
        return "innovationspartnerschaft"
    elif "direktvergabe" in desc_lower or "freihändige vergabe" in desc_lower:
        return "direktvergabe"

    return "unknown"


def extract_award_criteria(text: str) -> AwardCriteria:
    """Extract award criteria (price vs. quality) from tender text."""
    text_lower = text.lower()

    price_weight = find_percentage(text_lower, "preis")
    quality_weight = find_percentage(text_lower, "qualität")
    concept_weight = find_percentage(text_lower, "konzept")

    # If only price found, assume rest is quality
    if price_weight and not quality_weight:
        quality_weight = 100 - price_weight

    # If concept found, add to quality
    if concept_weight and not quality_weight:
        quality_weight = concept_weight

    favors_quality = quality_weight is not None and quality_weight > 50

    return AwardCriteria(
        price_weight=price_weight,
        quality_weight=quality_weight,
        favors_quality=favors_quality,
    )


def check_accessibility_requirements(description: str, pdf_text: str = "") -> AccessibilityResult:
    """Check accessibility requirements (BITV/WCAG)."""
    combined_text = f"{description} {pdf_text}".lower()
    required = []

    for req_name, keywords in ACCESSIBILITY_KEYWORDS.items():
        if any(kw in combined_text for kw in keywords):
            if req_name != "general":
                required.append(req_name)

    # If general accessibility mentioned but no specific standard
    if not required and any(kw in combined_text for kw in ACCESSIBILITY_KEYWORDS["general"]):
        required.append("wcag_2.1_aa")  # Assume standard level

    can_deliver = all(
        ACCESSIBILITY_CAPABILITIES.get(req, False)
        for req in required
    )

    score_impact = 5 if can_deliver and required else 0

    return AccessibilityResult(
        required=required,
        can_deliver=can_deliver,
        score_impact=score_impact,
    )


def check_security_requirements(description: str, pdf_text: str = "") -> SecurityResult:
    """Check security requirements (BSI/ISO)."""
    combined_text = f"{description} {pdf_text}".lower()
    required = []

    for req_name, keywords in SECURITY_REQUIREMENTS.items():
        if any(kw in combined_text for kw in keywords):
            required.append(req_name)

    blockers = [r for r in required if not SECURITY_CAPABILITIES.get(r, False)]

    return SecurityResult(
        required=required,
        blockers=blockers,
        can_deliver=len(blockers) == 0,
    )


def check_consortium_suitability(description: str, budget_max: Optional[int] = None) -> ConsortiumResult:
    """Check if tender is suitable for small companies via consortium."""
    desc_lower = description.lower()

    # Bietergemeinschaft erlaubt?
    consortium_blocked_phrases = [
        "keine bietergemeinschaft",
        "bietergemeinschaften nicht zugelassen",
        "bietergemeinschaften ausgeschlossen",
    ]
    consortium_allowed = not any(phrase in desc_lower for phrase in consortium_blocked_phrases)

    # Explizit erlaubt?
    consortium_encouraged_phrases = [
        "bietergemeinschaften zugelassen",
        "bietergemeinschaft möglich",
        "konsortium",
        "arbeitsgemeinschaft",
    ]
    consortium_encouraged = any(phrase in desc_lower for phrase in consortium_encouraged_phrases)

    # Umsatzanforderungen prüfen
    revenue_req = extract_revenue_requirement(desc_lower)
    needs_consortium = revenue_req and revenue_req > 500000

    # KMU-Förderung?
    sme_phrases = [
        "kmu", "kleine und mittlere unternehmen",
        "mittelstandsfreundlich", "losaufteilung",
        "förderung kleiner unternehmen",
    ]
    sme_friendly = any(phrase in desc_lower for phrase in sme_phrases)

    recommendation = None
    if needs_consortium and consortium_allowed:
        recommendation = "Bietergemeinschaft empfohlen"
    elif needs_consortium and not consortium_allowed:
        recommendation = "Nicht erreichbar ohne Partner"

    return ConsortiumResult(
        consortium_allowed=consortium_allowed,
        consortium_encouraged=consortium_encouraged,
        needs_consortium_for_eligibility=needs_consortium,
        sme_friendly=sme_friendly,
        recommendation=recommendation,
    )


def extract_revenue_requirement(text: str) -> Optional[int]:
    """Extract minimum revenue requirement from text."""
    patterns = [
        r"mindestumsatz[:\s]+(\d+(?:\.\d+)?)\s*(mio|million|tsd|tausend)?",
        r"umsatz[:\s]+mind(?:estens)?[:\s]+(\d+(?:\.\d+)?)\s*(mio|million|tsd|tausend)?",
        r"jahresumsatz[:\s]+(\d+(?:\.\d+)?)\s*(mio|million|tsd|tausend)?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower() if match.group(2) else ""

            if "mio" in unit or "million" in unit:
                return int(value * 1_000_000)
            elif "tsd" in unit or "tausend" in unit:
                return int(value * 1_000)
            else:
                # Assume EUR if value is large
                if value > 1000:
                    return int(value)
                else:
                    # Likely millions
                    return int(value * 1_000_000)

    return None


def check_eligibility(description: str, pdf_text: str = "") -> Tuple[str, str]:
    """Check eligibility requirements.

    Returns:
        Tuple of (status, notes) where status is "pass", "fail", or "unclear"
    """
    combined_text = f"{description} {pdf_text}".lower()

    # Definite blockers
    blockers = []

    # ISO 27001 required?
    if "iso 27001" in combined_text and "zertifizierung" in combined_text:
        blockers.append("ISO 27001 Zertifizierung gefordert")

    # BSI Grundschutz required?
    if "bsi-grundschutz" in combined_text and "zertifizierung" in combined_text:
        blockers.append("BSI Grundschutz Zertifizierung gefordert")

    # Very high revenue requirement?
    revenue_req = extract_revenue_requirement(combined_text)
    if revenue_req and revenue_req > 2_000_000:
        blockers.append(f"Mindestumsatz {revenue_req:,}€ gefordert")

    if blockers:
        return "fail", "; ".join(blockers)

    # Unclear cases
    unclear = []

    # PQ-Verzeichnis mentioned?
    if "präqualifikation" in combined_text or "pq-verzeichnis" in combined_text:
        unclear.append("Präqualifikation erwähnt")

    # Specific certifications mentioned?
    if "zertifizierung" in combined_text:
        unclear.append("Zertifizierungen erwähnt - Details prüfen")

    if unclear:
        return "unclear", "; ".join(unclear)

    return "pass", ""


# ============================================================
# Budget Extraction
# ============================================================

# German number: "50.000" or "100.000,00" or "75000" or "75000,00"
_DE_NUMBER = r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d{4,}(?:,\d{2})?)"

# Pre-compiled budget patterns for German formats
_BUDGET_PATTERNS = [
    # Range: "50.000 bis 250.000 EUR"
    re.compile(
        _DE_NUMBER + r"\s*(?:bis|-)\s*" + _DE_NUMBER + r"\s*(?:EUR|€|Euro)",
        re.IGNORECASE,
    ),
    # Single value: "100.000 EUR" or "75000 Euro"
    re.compile(
        _DE_NUMBER + r"\s*(?:EUR|€|Euro)",
        re.IGNORECASE,
    ),
    # Mio format: "1,5 Mio. EUR"
    re.compile(
        r"(\d{1,3}(?:,\d{1,2})?)\s*(?:Mio\.?|Million(?:en)?)\s*(?:EUR|€|Euro)?",
        re.IGNORECASE,
    ),
    # === NEU: Alternative Begriffe ===
    # geschätzter Wert: 100.000 EUR
    re.compile(
        r"geschätzter?\s+(?:wert|preis|umfang)[:\s]*" + _DE_NUMBER + r"\s*(?:EUR|€|Euro)?",
        re.IGNORECASE,
    ),
    # Gesamtwert/Auftragswert: 100.000 EUR
    re.compile(
        r"(?:gesamt|auftrags?)[- ]?wert[:\s]*" + _DE_NUMBER + r"\s*(?:EUR|€|Euro)?",
        re.IGNORECASE,
    ),
    # Netto/Brutto-Preis: 100.000 EUR
    re.compile(
        r"(?:netto|brutto)[- ]?(?:preis|wert|summe)[:\s]*" + _DE_NUMBER + r"\s*(?:EUR|€|Euro)?",
        re.IGNORECASE,
    ),
    # Volumen: 100.000 EUR
    re.compile(
        r"(?:auftrags?)?volumen[:\s]*" + _DE_NUMBER + r"\s*(?:EUR|€|Euro)?",
        re.IGNORECASE,
    ),
    # Investitionssumme: 100.000 EUR
    re.compile(
        r"investitions?(?:summe|volumen)[:\s]*" + _DE_NUMBER + r"\s*(?:EUR|€|Euro)?",
        re.IGNORECASE,
    ),
    # === NEU: Kurzformen ===
    # "150k EUR" or "150 Tsd. EUR"
    re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(?:k|tsd\.?)\s*(?:EUR|€|Euro)",
        re.IGNORECASE,
    ),
]


def extract_budget_from_text(text: str) -> Optional[int]:
    """Extract budget/volume from German-format text.

    Supports formats like:
    - "50.000 bis 250.000 EUR" (returns max)
    - "100.000,00 €"
    - "1,5 Mio. EUR"
    - "geschätzter Wert: 100.000 EUR"
    - "Gesamtwert: 100.000 EUR"
    - "150k EUR" or "150 Tsd. EUR"

    Returns:
        Budget in EUR as integer, or None if not found.
    """
    if not text:
        return None

    # Range pattern (return max value) - Index 0
    match = _BUDGET_PATTERNS[0].search(text)
    if match:
        max_val = match.group(2).replace(".", "").replace(",", ".")
        return int(float(max_val))

    # Single value - Index 1
    match = _BUDGET_PATTERNS[1].search(text)
    if match:
        val = match.group(1).replace(".", "").replace(",", ".")
        return int(float(val))

    # Mio format - Index 2
    match = _BUDGET_PATTERNS[2].search(text)
    if match:
        val = float(match.group(1).replace(",", "."))
        return int(val * 1_000_000)

    # Kurzform (k/Tsd.) - Index 8 (letztes Pattern)
    match = _BUDGET_PATTERNS[8].search(text)
    if match:
        val = float(match.group(1).replace(",", "."))
        return int(val * 1_000)

    # Alternative Begriffe (geschätzter Wert, Gesamtwert, etc.) - Index 3-7
    for i in range(3, 8):
        match = _BUDGET_PATTERNS[i].search(text)
        if match:
            val = match.group(1).replace(".", "").replace(",", ".")
            return int(float(val))

    return None


# ============================================================
# Scoring Functions
# ============================================================


def score_procedure_type(procedure: str) -> int:
    """Score based on procurement procedure type."""
    return PROCEDURE_SCORES.get(procedure, 0)


def score_award_criteria(criteria: AwardCriteria) -> int:
    """Score based on award criteria (quality vs. price focus)."""
    if criteria.favors_quality:
        return 10  # Bonus for quality-focused tenders
    elif criteria.price_weight and criteria.price_weight > 70:
        return -5  # Penalty for pure price competition
    return 0


def score_consortium(result: ConsortiumResult) -> int:
    """Score based on consortium/SME suitability."""
    if result.sme_friendly:
        return 10  # KMU-friendly is good
    if result.needs_consortium_for_eligibility and not result.consortium_allowed:
        return -20  # Can't reach eligibility
    if result.needs_consortium_for_eligibility and result.consortium_allowed:
        return 5  # Possible with partner
    return 0


def score_client(
    client_name: Optional[str],
    win_rate: Optional[float] = None,
    tenders_applied: int = 0,
    payment_rating: Optional[int] = None,
) -> int:
    """Score based on client history."""
    if not client_name:
        return 0

    score = 0

    # Win-rate bonus (require minimum 3 historical projects for full bonus)
    if win_rate and win_rate > 0.3:
        if tenders_applied >= 3:
            score += 15  # Full bonus with sufficient data
        else:
            score += 5  # Reduced bonus with limited data

    # Known client
    if tenders_applied > 0:
        score += 5  # Experience exists

    # Payment rating
    if payment_rating and payment_rating >= 4:
        score += 5

    return min(score, 15)  # Cap at max 15


def score_tender(
    description: str,
    pdf_text: str = "",
    budget_max: Optional[int] = None,
    tender_deadline: Optional[datetime] = None,
    client_name: Optional[str] = None,
    client_win_rate: Optional[float] = None,
    client_tenders_applied: int = 0,
    client_payment_rating: Optional[int] = None,
    cpv_bonus: int = 0,
    title: str = "",
) -> TenderScore:
    """Calculate comprehensive tender score.

    Args:
        description: Project description
        pdf_text: Text extracted from PDF documents
        budget_max: Maximum budget in EUR
        tender_deadline: Submission deadline
        client_name: Name of contracting authority
        client_win_rate: Historical win rate with this client
        client_tenders_applied: Number of previous applications
        client_payment_rating: Payment rating (1-5)
        cpv_bonus: Bonus from CPV code filter
        title: Project title (used for software fallback detection)

    Returns:
        TenderScore with detailed breakdown
    """
    score = TenderScore()
    combined_text = f"{title} {description} {pdf_text}"

    # ============================================================
    # TECH-FIT (40 Punkte) - HÖCHSTE GEWICHTUNG
    # ============================================================
    tech_result = analyze_tech_requirements(description, pdf_text)

    if tech_result.requires_webapp:
        score.tech_score += 75  # Erhöht: garantiert Review-Queue
        score.reasons.append(f"Webanwendung: {tech_result.webapp_evidence}")

    if tech_result.requires_mobile:
        score.tech_score += 75  # Erhöht: garantiert Review-Queue
        score.reasons.append(f"Mobile App: {tech_result.mobile_evidence}")

    # Tech-Stack bonus
    if tech_result.tech_stack_matches:
        stack_bonus = min(10, len(tech_result.tech_stack_matches) * 2)
        score.tech_score += stack_bonus
        score.reasons.append(f"Tech-Stack: {', '.join(tech_result.tech_stack_matches[:5])}")

    # EARLY EXIT: No tech fit = check for software fallback
    if not tech_result.requires_webapp and not tech_result.requires_mobile:
        # Fallback: Prüfe ob generische Software-Keywords vorhanden
        software_fallback_keywords = [
            # Generisch (matcht "Software für...", "Softwarelösung", etc.)
            "software",
            # Spezifisch
            "anwendungsentwicklung", "applikation",
            "digitale lösung", "it-system", "fachverfahren", "individualsoftware",
            "fachanwendung", "it-dienstleistung", "management-system",
            "informationssystem", "dokumentation", "plattform",
            # === NEU: Erweiterte Keywords ===
            "it-projekt", "onlinedienst", "e-service",
            "registeranwendung", "meldesystem", "buchungssystem",
            "verwaltungsanwendung", "behördensoftware", "amtssystem",
            "onlineverfahren", "digitaldienst", "e-akte",
            "digitalisierungsprojekt", "softwareprojekt",
            "webbasiert", "browserbasiert", "cloudbasiert",
        ]
        combined_lower = combined_text.lower()
        has_software_hint = any(kw in combined_lower for kw in software_fallback_keywords)

        if not has_software_hint:
            score.skip = True
            score.skip_reason = "Keine Web/Mobile-Entwicklung gefordert"
            return score
        else:
            # Software-Keywords gefunden - in Review-Queue zur manuellen Prüfung
            score.reasons.append("Tech-Fit unklar - Software-Keywords gefunden -> Review")
            score.tech_score = 50  # Garantiert Review-Queue (Schwelle = 50)

    # ============================================================
    # VOLUMEN (DEAKTIVIERT - nicht relevant für erste Sichtung)
    # ============================================================
    # Budget wird nur noch informativ angezeigt, fließt aber nicht in Score ein
    if not budget_max:
        budget_max = extract_budget_from_text(combined_text)
    if budget_max:
        score.reasons.append(f"Budget (Info): {budget_max:,}€")
    # score.volume_score bleibt 0

    # ============================================================
    # VERGABEART (DEAKTIVIERT - nicht relevant für erste Sichtung)
    # ============================================================
    # Vergabeart wird nur noch informativ angezeigt
    procedure = detect_procedure_type(combined_text)
    if procedure != "unknown":
        score.reasons.append(f"Vergabeart (Info): {procedure}")
    # score.procedure_score bleibt 0

    # ============================================================
    # ZUSCHLAGSKRITERIEN (10 Punkte)
    # ============================================================
    award = extract_award_criteria(combined_text)
    score.award_criteria_score = score_award_criteria(award)
    if award.favors_quality:
        score.reasons.append(f"Qualitätsorientiert: {award.quality_weight}%")

    # ============================================================
    # EIGNUNG (15 Punkte)
    # ============================================================
    eligibility_status, eligibility_notes = check_eligibility(description, pdf_text)
    if eligibility_status == "pass":
        score.eligibility_score = 15
    elif eligibility_status == "unclear":
        score.eligibility_score = 8
        score.reasons.append(f"Eignung unklar: {eligibility_notes}")
    else:
        score.eligibility_score = 0
        score.reasons.append(f"Eignung FAIL: {eligibility_notes}")

    # ============================================================
    # BARRIEREFREIHEIT (5 Punkte)
    # ============================================================
    accessibility = check_accessibility_requirements(description, pdf_text)
    score.accessibility_score = accessibility.score_impact
    if accessibility.required and accessibility.can_deliver:
        score.reasons.append(f"Barrierefreiheit: {', '.join(accessibility.required)}")
    elif accessibility.required and not accessibility.can_deliver:
        score.reasons.append(f"Barrierefreiheit nicht lieferbar: {', '.join(accessibility.required)}")

    # ============================================================
    # SICHERHEIT (0/-20 Punkte) - nur Blocker
    # ============================================================
    security = check_security_requirements(description, pdf_text)
    if security.blockers:
        score.security_score = -20
        score.skip = True
        score.skip_reason = f"Sicherheitsanforderung nicht erfüllbar: {', '.join(security.blockers)}"
        return score

    # ============================================================
    # BIETERGEMEINSCHAFT (10 Punkte)
    # ============================================================
    consortium = check_consortium_suitability(description, budget_max)
    score.consortium_score = score_consortium(consortium)
    if consortium.sme_friendly:
        score.reasons.append("KMU-freundlich")
    if consortium.recommendation:
        score.reasons.append(consortium.recommendation)

    # Check for blocking consortium requirement
    if consortium.needs_consortium_for_eligibility and not consortium.consortium_allowed:
        score.skip = True
        score.skip_reason = "Bietergemeinschaft nötig aber nicht erlaubt"
        return score

    # ============================================================
    # AUFTRAGGEBER (15 Punkte)
    # ============================================================
    score.client_score = score_client(
        client_name,
        client_win_rate,
        client_tenders_applied,
        client_payment_rating,
    )
    if score.client_score > 0:
        score.reasons.append(f"Bekannter Auftraggeber: +{score.client_score}P")

    # ============================================================
    # DEADLINE (10 Punkte) mit Ampel-System
    # ============================================================
    if tender_deadline:
        days_until = (tender_deadline - datetime.now()).days
        if days_until >= 21:
            score.deadline_score = 10
            score.reasons.append(f"Deadline OK: {days_until} Tage")
        elif days_until >= 14:
            score.deadline_score = 5
            score.reasons.append(f"Deadline GELB: {days_until} Tage")
        elif days_until >= 7:
            score.deadline_score = 2
            score.reasons.append(f"Deadline ROT: {days_until} Tage")
        else:
            score.deadline_score = 0
            score.reasons.append(f"Deadline KRITISCH: {days_until} Tage")

    # ============================================================
    # TOTAL & NORMALIZATION
    # ============================================================
    score.total = (
        score.tech_score +
        score.volume_score +
        score.procedure_score +
        score.award_criteria_score +
        score.eligibility_score +
        score.accessibility_score +
        score.security_score +
        score.consortium_score +
        score.client_score +
        score.deadline_score +
        cpv_bonus
    )

    # Normalize to 0-100
    # Vereinfacht: Tech 150 (max Web+Mobile) + Stack 10 + Eligibility 15 +
    #              Accessibility 5 + Consortium 10 + Client 15 + Deadline 10 = 215
    # Plus potential CPV bonus (up to 10)
    # Aber: Tech allein (75) soll schon ~70% ergeben → max_score = 100
    max_score = 100
    score.normalized = min(100, int((score.total / max_score) * 100))

    return score


def get_deadline_urgency(tender_deadline: Optional[datetime]) -> str:
    """Return deadline urgency level for UI display.

    Returns:
        'green', 'yellow', 'red', or 'critical'
    """
    if not tender_deadline:
        return "green"
    days = (tender_deadline - datetime.now()).days
    if days >= 21:
        return "green"
    if days >= 14:
        return "yellow"
    if days >= 7:
        return "red"
    return "critical"
