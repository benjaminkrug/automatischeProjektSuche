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


# Webanwendung-Indikatoren (explizite Forderung)
WEBAPP_PATTERNS = [
    r"entwicklung\s+(einer?\s+)?webanwendung",
    r"webanwendung\s+(erstellen|entwickeln|programmieren|soll|muss)",
    r"webapplikation\s+(soll|muss|ist\s+zu|erstellen|entwickeln)",
    r"webbasiert(e|es|en)?\s+(portal|system|anwendung|lösung|plattform)",
    r"browser-basiert",
    r"responsive\s+web(design|anwendung|applikation)",
    r"frontend[- ]entwicklung",
    r"(react|vue|angular|next\.?js|nuxt)\s+(anwendung|applikation|entwicklung)",
    r"web[- ]?(app|application|portal)\s+(entwicklung|erstellen|programmieren)",
    r"online[- ]?(portal|plattform|anwendung)",
    r"single[- ]page[- ]application",
    r"progressive[- ]web[- ]app",
    # Webseiten-Erkennung (klassische Websites, nicht nur Web-Apps)
    r"(erstellung|entwicklung|programmierung|relaunch|neugestaltung)\s+(einer?\s+)?(web(site|seite)|homepage|internetseite)",
    r"(web(site|seite)|homepage|internetseite|internetauftritt)\s+(erstellen|entwickeln|programmieren|neugestalten|relaunchen)",
    r"landingpage",
    r"(web(site|seite)|homepage)[- ]?(design|entwicklung|erstellung|relaunch)",
]

# Mobile App-Indikatoren (explizite Forderung)
MOBILE_PATTERNS = [
    r"(mobile|native)\s+app\s+(entwicklung|erstellen|programmieren)",
    r"ios[- ]und[- ]android",
    r"(ios|android)[- ]app",
    r"smartphone[- ]app",
    r"(flutter|react\s*native|kotlin|swift)\s+(app|anwendung|entwicklung)",
    r"app\s+für\s+(ios|android|mobile\s+endgeräte|smartphones?)",
    r"mobile\s+(anwendung|applikation|lösung)",
    r"(tablet|ipad|android)[- ]?(app|anwendung)",
    r"cross[- ]?platform[- ]?(app|entwicklung)",
]

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

    webapp_matches = find_pattern_matches(combined_text, WEBAPP_PATTERNS)
    mobile_matches = find_pattern_matches(combined_text, MOBILE_PATTERNS)

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

    # Win-rate bonus
    if win_rate and win_rate > 0.3:
        score += 15  # Good success rate

    # Known client
    if tenders_applied > 0:
        score += 5  # Experience exists

    # Payment rating
    if payment_rating and payment_rating >= 4:
        score += 5

    return score


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

    Returns:
        TenderScore with detailed breakdown
    """
    score = TenderScore()
    combined_text = f"{description} {pdf_text}"

    # ============================================================
    # TECH-FIT (40 Punkte) - HÖCHSTE GEWICHTUNG
    # ============================================================
    tech_result = analyze_tech_requirements(description, pdf_text)

    if tech_result.requires_webapp:
        score.tech_score += 20
        score.reasons.append(f"Webanwendung: {tech_result.webapp_evidence}")

    if tech_result.requires_mobile:
        score.tech_score += 20
        score.reasons.append(f"Mobile App: {tech_result.mobile_evidence}")

    # Tech-Stack bonus
    if tech_result.tech_stack_matches:
        stack_bonus = min(10, len(tech_result.tech_stack_matches) * 2)
        score.tech_score += stack_bonus
        score.reasons.append(f"Tech-Stack: {', '.join(tech_result.tech_stack_matches[:5])}")

    # EARLY EXIT: No tech fit = not relevant
    if not tech_result.requires_webapp and not tech_result.requires_mobile:
        score.skip = True
        score.skip_reason = "Keine Web/Mobile-Entwicklung gefordert"
        return score

    # ============================================================
    # VOLUMEN (15 Punkte)
    # ============================================================
    if budget_max:
        if settings.tender_budget_min <= budget_max <= settings.tender_budget_max:
            score.volume_score = 15
            score.reasons.append(f"Budget optimal: {budget_max:,}€")
        elif budget_max > settings.tender_budget_max:
            score.volume_score = 10
            score.reasons.append(f"Großprojekt: {budget_max:,}€")
        else:
            score.volume_score = 5
            score.reasons.append(f"Kleineres Projekt: {budget_max:,}€")

    # ============================================================
    # VERGABEART (15 Punkte)
    # ============================================================
    procedure = detect_procedure_type(combined_text)
    score.procedure_score = score_procedure_type(procedure)
    if score.procedure_score > 0:
        score.reasons.append(f"Vergabeart günstig: {procedure}")
    elif score.procedure_score < 0:
        score.reasons.append(f"Vergabeart ungünstig: {procedure}")

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
    # DEADLINE (10 Punkte)
    # ============================================================
    if tender_deadline:
        days_until = (tender_deadline - datetime.now()).days
        if days_until >= 21:
            score.deadline_score = 10
            score.reasons.append(f"Deadline: {days_until} Tage")
        elif days_until >= settings.tender_deadline_min_days:
            score.deadline_score = 5
            score.reasons.append(f"Deadline knapp: {days_until} Tage")
        else:
            score.deadline_score = 0
            score.reasons.append(f"Deadline zu kurz: {days_until} Tage")

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

    # Normalize to 0-100 (max theoretical score ~145)
    max_score = 145
    score.normalized = min(100, int((score.total / max_score) * 100))

    return score
