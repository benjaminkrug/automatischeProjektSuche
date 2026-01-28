"""Erweitertes Keyword-Scoring mit Kategorien, Gewichtung und Kombinationen.

Dieses Modul implementiert ein tiered Keyword-Scoring-System (40% des Gesamt-Scores):
- Tier 1: Kernkompetenzen (20 Punkte pro Keyword, max 32)
- Tier 2: Starke Passung (12 Punkte pro Keyword, max 17)
- Tier 3: Nice-to-have (6 Punkte pro Keyword, max 12)
- Combo-Bonus: Wertvolle Kombinationen (+2 bis +6, max 11)
- Reject: Gewichtete Ausschluss-Keywords
- Gesamt-Maximum: 40 Punkte

Ersetzt/erweitert das einfache Keyword-Filtering in keyword_filter.py
mit einem detaillierten Score-Breakdown für die Matching-Entscheidung.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, List, Set, Tuple

from app.core.logging import get_logger

logger = get_logger("ai.keyword_scoring")


class KeywordTier(Enum):
    """Keyword-Prioritätsstufen."""

    TIER_1 = "tier_1"  # Kernkompetenz -> +16 pro Keyword
    TIER_2 = "tier_2"  # Gute Passung -> +10 pro Keyword
    TIER_3 = "tier_3"  # Nice-to-have -> +4 pro Keyword
    REJECT = "reject"  # Auto-Reject


# Tier 1: Kernkompetenzen des Teams (höchste Punktzahl)
TIER_1_KEYWORDS: Set[str] = {
    # Frontend Core
    "vue",
    "vue.js",
    "vuejs",
    "nuxt",
    "nuxtjs",
    # Backend Core - Python
    "python",
    "django",
    "fastapi",
    # Backend Core - .NET (Benjamin & Viktor)
    "c#",
    ".net",
    "dotnet",
    "asp.net",
    "blazor",
    # Backend Core - Java (Souhail)
    "java",
    "spring",
    "spring boot",
    "springboot",
    # Fullstack
    "fullstack",
    "full-stack",
    #Backend
    "backend",
    #Frontend
    "frontend",
}

# Tier 2: Starke Passung
TIER_2_KEYWORDS: Set[str] = {
    # Frontend
    "react",
    "angular",
    "typescript",
    "javascript",
    "frontend",
    "front-end",
    # Frontend Erweitert
    "html",
    "css",
    "scss",
    "sass",
    "tailwind",
    "bootstrap",
    "webpack",
    "vite",
    "next.js",
    "nextjs",
    "ui",
    "ux",
    "ui/ux",
    # Backend
    "node",
    "nodejs",
    "node.js",
    "express",
    "nestjs",
    "flask",
    # .NET Ecosystem
    "entity framework",
    "ef core",
    "ms sql",
    "mssql",
    "sql server",
    "wpf",
    "winforms",
    ".net core",
    "maui",
    # Java Ecosystem
    "kotlin",
    "jpa",
    "hibernate",
    "maven",
    "gradle",
    # Datenbank
    "postgresql",
    "mongodb",
    "redis",
    # API
    "rest",
    "graphql",
    "api",
    "microservice",
    "microservices",
    # Auth/Security
    "jwt",
    "oauth",
    "oauth2",
    "authentifizierung",
    "autorisierung",
    # Compliance
    "dsgvo",
    "datenschutz",
    "gdpr",
    # Cloud
    "docker",
    "aws",
    "azure",
    "kubernetes",
    # Deployment & Infrastructure
    "terraform",
    "ansible",
    "helm",
    "argocd",
    "github actions",
    "azure devops",
    "bitbucket",
    "vercel",
    "netlify",
    "heroku",
    "gcp",
    "google cloud",
    # Vue.js Libraries
    "vuex",
    "pinia",
    "vue router",
    "vuetify",
    "quasar",
    # React Libraries
    "redux",
    "zustand",
    "react query",
    "mobx",
    # .NET Libraries
    "automapper",
    "dapper",
    "serilog",
    "mediatr",
    "fluentvalidation",
    "xunit",
    "nunit",
    # Java Libraries
    "lombok",
    "junit",
    "mockito",
}

# Tier 3: Nice-to-have
TIER_3_KEYWORDS: Set[str] = {
    "agile",
    "scrum",
    "devops",
    "ci/cd",
    "cicd",
    "git",
    "responsive",
    "spa",
    "pwa",
    "webentwicklung",
    "mysql",
    "elasticsearch",
    "rabbitmq",
    "kafka",
    "linux",
    "jenkins",
    "gitlab",
    # Frontend Tools
    "figma",
    "storybook",
    "jest",
    "cypress",
    "playwright",
    "less",
    "styled-components",
    "material-ui",
    "mui",
    "svelte",
    "web components",
    # General Libraries
    "axios",
    "lodash",
    "swagger",
    "openapi",
}

# Punktwerte pro Tier (skaliert für 40% Gewichtung)
TIER_POINTS: Dict[KeywordTier, int] = {
    KeywordTier.TIER_1: 18,  # Kernkompetenz
    KeywordTier.TIER_2: 10,  # Gute Passung
    KeywordTier.TIER_3: 5,   # Nice-to-have
}

# Maximale Punkte pro Tier (Deckelung)
TIER_MAX_POINTS: Dict[KeywordTier, int] = {
    KeywordTier.TIER_1: 32,  # Max ~1.6 Tier-1 Keywords zählen voll
    KeywordTier.TIER_2: 17,  # Max ~1.4 Tier-2 Keywords zählen voll
    KeywordTier.TIER_3: 12,  # Max 2 Tier-3 Keywords zählen
}

# GESAMT-MAXIMUM für Keyword-Score
KEYWORD_SCORE_MAX = 40  # Entspricht 40% des Gesamt-Scores

# Q5: Wertvolle Kombinationen -> Extra-Bonus (reduziert auf 20 wirkungsvollste)
# Fokus auf Team-Kernkompetenzen: Vue, Python, C#/.NET, Java
COMBO_BONUSES: Dict[FrozenSet[str], int] = {
    # Fullstack-Combos (höchste Priorität - Team-Kernkompetenz)
    frozenset({"vue", "python"}): 8,
    frozenset({"vue", "django"}): 8,
    frozenset({"vue", "c#"}): 8,
    frozenset({"vue", ".net"}): 8,
    frozenset({"react", "python"}): 6,
    frozenset({"react", "node"}): 6,
    frozenset({"angular", "java"}): 6,
    frozenset({"angular", "spring"}): 6,
    # Backend-Stack Combos
    frozenset({"python", "postgresql"}): 5,
    frozenset({"java", "spring"}): 6,
    frozenset({"c#", "asp.net"}): 6,
    frozenset({".net", "sql server"}): 5,
    # Frontend-TypeScript Combos
    frozenset({"vue", "typescript"}): 5,
    frozenset({"react", "typescript"}): 5,
    # Cloud/DevOps Combos
    frozenset({"docker", "kubernetes"}): 4,
    frozenset({"python", "docker"}): 3,
    frozenset({"java", "docker"}): 3,
    # API Combos
    frozenset({"graphql", "vue"}): 5,
    frozenset({"graphql", "react"}): 5,
    frozenset({"rest", "python"}): 3,
}

# Maximum combo bonus
COMBO_BONUS_MAX = 11

# Reject-Keywords mit Schweregrad (gewichtet)
REJECT_KEYWORDS_WEIGHTED: Dict[str, int] = {
    # Absolute No-Gos (sofort reject bei einem)
    "sap": 100,
    "abap": 100,
    "cobol": 100,
    "mainframe": 100,
    "as400": 100,
    "sharepoint": 100,
    "dynamics": 100,
    "salesforce": 100,
    # Starke Ablehnung (reject wenn > 1 oder Score > 100)
    "php": 50,
    "wordpress": 50,
    "drupal": 50,
    "joomla": 50,
    "typo3": 50,
    # Note: kotlin removed - now in TIER_2 as Java ecosystem keyword
    # Leichte Ablehnung (reject wenn Summe > 100)
    "helpdesk": 30,
    "support": 30,
    "admin": 30,
    "1st level": 30,
    "2nd level": 30,
    "hardware": 30,
    "netzwerk": 30,
    "firewall": 30,
    "cisco": 30,
    # Embedded/Industrial
    "sps": 40,
    "roboter": 40,
    "maschinenbau": 40,
    "elektrotechnik": 40,
    "embedded": 40,
    # --- Industry Rejects (Bau, Elektro, Mechanik etc.) ---
    # Bau/Hochbau/Tiefbau (sofort reject)
    "bauarbeiten": 150,
    "bauleistungen": 150,
    "hochbau": 150,
    "tiefbau": 150,
    "rohbau": 150,
    "straßenbau": 150,
    "brückenbau": 150,
    "kanalbau": 150,
    "betonarbeiten": 150,
    "mauerarbeiten": 150,
    "dacharbeiten": 150,
    "estricharbeiten": 150,
    "putzarbeiten": 150,
    "fliesenarbeiten": 150,
    "trockenbau": 150,
    "gerüstbau": 150,
    "abbrucharbeiten": 150,
    # Elektroinstallation (nicht IT)
    "elektroinstallation": 150,
    "starkstrom": 150,
    "elektroanlagen": 150,
    "schaltanlagen": 150,
    "niederspannung": 150,
    "mittelspannung": 150,
    "hochspannung": 150,
    # Mechanik/Metallbau
    "metallbau": 150,
    "stahlbau": 150,
    "schweißarbeiten": 150,
    "rohrleitungsbau": 150,
    "schlosserei": 150,
    # HVAC/TGA
    "heizungsanlage": 150,
    "lüftungsanlage": 150,
    "klimaanlage": 150,
    "sanitärinstallation": 150,
    "kältetechnik": 150,
    # Facility/Reinigung
    "gebäudereinigung": 150,
    "unterhaltsreinigung": 150,
    "winterdienst": 150,
    "grünflächenpflege": 150,
    # Sicherheit (physisch)
    "wachdienst": 150,
    "objektschutz": 150,
    "sicherheitsdienst": 150,
    "pförtnerdienst": 150,
    # Druck/Büro
    "druckerzeugnisse": 150,
    "drucksachen": 150,
    "büromöbel": 150,
    "arbeitskleidung": 150,
}

# Threshold für Auto-Reject (Summe der Reject-Punkte)
REJECT_THRESHOLD = 100


@dataclass
class KeywordScoreResult:
    """Detailliertes Ergebnis der Keyword-Analyse."""

    total_score: int  # Gesamt-Keyword-Score (0-40)
    tier_1_keywords: List[str]  # Gefundene Tier-1 Keywords
    tier_2_keywords: List[str]  # Gefundene Tier-2 Keywords
    tier_3_keywords: List[str]  # Gefundene Tier-3 Keywords
    reject_keywords: List[str]  # Gefundene Reject Keywords
    tier_1_score: int  # Punkte aus Tier 1
    tier_2_score: int  # Punkte aus Tier 2
    tier_3_score: int  # Punkte aus Tier 3
    combo_bonus: int  # Bonus für Keyword-Kombinationen
    reject_score: int  # Gewichteter Reject-Score
    should_reject: bool  # Auto-Reject?
    confidence: str  # "high", "medium", "low"


def calculate_keyword_score(
    title: str,
    description: str,
    pdf_text: str = "",
) -> KeywordScoreResult:
    """Berechne detaillierten Keyword-Score.

    Args:
        title: Projekttitel
        description: Projektbeschreibung
        pdf_text: Extrahierter Text aus PDF-Dokumenten (optional)

    Returns:
        KeywordScoreResult mit detaillierter Aufschlüsselung
    """
    # Kombiniere alle Texte für Suche
    text = f"{title} {description} {pdf_text}".lower()

    # Finde Keywords pro Tier
    tier_1_found = _find_keywords(text, TIER_1_KEYWORDS)
    tier_2_found = _find_keywords(text, TIER_2_KEYWORDS)
    tier_3_found = _find_keywords(text, TIER_3_KEYWORDS)

    # Berechne Reject-Score (gewichtet)
    reject_score, reject_found = _calculate_reject_score(text)

    # Berechne Punkte pro Tier (mit Deckelung)
    tier_1_score = min(
        len(tier_1_found) * TIER_POINTS[KeywordTier.TIER_1],
        TIER_MAX_POINTS[KeywordTier.TIER_1],
    )
    tier_2_score = min(
        len(tier_2_found) * TIER_POINTS[KeywordTier.TIER_2],
        TIER_MAX_POINTS[KeywordTier.TIER_2],
    )
    tier_3_score = min(
        len(tier_3_found) * TIER_POINTS[KeywordTier.TIER_3],
        TIER_MAX_POINTS[KeywordTier.TIER_3],
    )

    # Combo-Bonus für bestimmte Kombinationen
    combo_bonus = _calculate_combo_bonus(tier_1_found, tier_2_found)

    # Gesamt-Score (gedeckelt)
    total_score = min(
        tier_1_score + tier_2_score + tier_3_score + combo_bonus,
        KEYWORD_SCORE_MAX,
    )

    # Should reject?
    should_reject = reject_score >= REJECT_THRESHOLD

    # Confidence basierend auf Keyword-Dichte
    total_keywords = len(tier_1_found) + len(tier_2_found) + len(tier_3_found)
    if total_keywords >= 5:
        confidence = "high"
    elif total_keywords >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    result = KeywordScoreResult(
        total_score=total_score,
        tier_1_keywords=tier_1_found,
        tier_2_keywords=tier_2_found,
        tier_3_keywords=tier_3_found,
        reject_keywords=reject_found,
        tier_1_score=tier_1_score,
        tier_2_score=tier_2_score,
        tier_3_score=tier_3_score,
        combo_bonus=combo_bonus,
        reject_score=reject_score,
        should_reject=should_reject,
        confidence=confidence,
    )

    # Log for transparency
    _log_result(title, result)

    return result


def _find_keywords(text: str, keywords: Set[str]) -> List[str]:
    """Find all matching keywords in text using word boundary matching.

    Args:
        text: Text to search in (already lowercase)
        keywords: Set of keywords to search for

    Returns:
        List of found keywords
    """
    found = []
    for keyword in keywords:
        # Use word boundary regex for accurate matching
        # This ensures "api" doesn't match "capital" etc.
        # Special handling for keywords ending with non-word characters (like c#)
        if keyword.endswith("#") or keyword.startswith("."):
            # Use lookahead/lookbehind for non-alphanumeric boundaries
            pattern = rf"(?<![a-zA-Z0-9]){re.escape(keyword)}(?![a-zA-Z0-9])"
        else:
            pattern = rf"\b{re.escape(keyword)}\b"
        if re.search(pattern, text):
            found.append(keyword)
    return found


def _calculate_reject_score(text: str) -> Tuple[int, List[str]]:
    """Berechne gewichteten Reject-Score.

    Args:
        text: Text to search in (already lowercase)

    Returns:
        Tuple of (total_score, list_of_found_keywords)
    """
    score = 0
    found = []

    for keyword, weight in REJECT_KEYWORDS_WEIGHTED.items():
        pattern = rf"\b{re.escape(keyword)}\b"
        if re.search(pattern, text):
            score += weight
            found.append(keyword)

    return score, found


def _calculate_combo_bonus(tier_1: List[str], tier_2: List[str]) -> int:
    """Berechne Bonus für wertvolle Keyword-Kombinationen.

    Args:
        tier_1: Found tier 1 keywords
        tier_2: Found tier 2 keywords

    Returns:
        Combo bonus points (max 10)
    """
    all_keywords = set(tier_1 + tier_2)
    bonus = 0

    for combo, points in COMBO_BONUSES.items():
        if combo.issubset(all_keywords):
            bonus += points

    # Maximal COMBO_BONUS_MAX Combo-Punkte
    return min(bonus, COMBO_BONUS_MAX)


def _log_result(title: str, result: KeywordScoreResult) -> None:
    """Log keyword scoring result for transparency."""
    title_short = title[:50] if len(title) > 50 else title

    if result.should_reject:
        logger.info(
            "Keyword-REJECT: '%s' (Reject-Score: %d, Keywords: %s)",
            title_short,
            result.reject_score,
            ", ".join(result.reject_keywords),
        )
    elif result.total_score >= 20:
        logger.info(
            "Keyword-Score HIGH: '%s' -> %d (T1=%d, T2=%d, T3=%d, Combo=%d) [%s]",
            title_short,
            result.total_score,
            result.tier_1_score,
            result.tier_2_score,
            result.tier_3_score,
            result.combo_bonus,
            result.confidence,
        )
    elif result.total_score >= 10:
        logger.debug(
            "Keyword-Score MEDIUM: '%s' -> %d [%s]",
            title_short,
            result.total_score,
            result.confidence,
        )
    else:
        logger.debug(
            "Keyword-Score LOW: '%s' -> %d [%s]",
            title_short,
            result.total_score,
            result.confidence,
        )


def get_keyword_tier(keyword: str) -> KeywordTier | None:
    """Get the tier for a specific keyword.

    Args:
        keyword: Keyword to look up (case-insensitive)

    Returns:
        KeywordTier or None if not found
    """
    keyword_lower = keyword.lower()

    if keyword_lower in TIER_1_KEYWORDS:
        return KeywordTier.TIER_1
    elif keyword_lower in TIER_2_KEYWORDS:
        return KeywordTier.TIER_2
    elif keyword_lower in TIER_3_KEYWORDS:
        return KeywordTier.TIER_3
    elif keyword_lower in REJECT_KEYWORDS_WEIGHTED:
        return KeywordTier.REJECT

    return None


def get_all_positive_keywords() -> Dict[str, KeywordTier]:
    """Get all positive keywords with their tiers.

    Returns:
        Dict mapping keyword to tier
    """
    result = {}
    for kw in TIER_1_KEYWORDS:
        result[kw] = KeywordTier.TIER_1
    for kw in TIER_2_KEYWORDS:
        result[kw] = KeywordTier.TIER_2
    for kw in TIER_3_KEYWORDS:
        result[kw] = KeywordTier.TIER_3
    return result
