"""Skill-Overlap-Berechnung basierend auf Keywords.

Berechnet den Overlap zwischen Projekt-Keywords und Kandidaten-Skills
ohne LLM-Call, basierend auf dem Keyword-Scoring-Ergebnis.
"""

import re
from difflib import SequenceMatcher
from typing import List, Set

from app.ai.keyword_scoring import KeywordScoreResult
from app.core.logging import get_logger

logger = get_logger("ai.skill_overlap")

# Skill-Normalisierungen (verschiedene Schreibweisen -> kanonische Form)
SKILL_NORMALIZATIONS = {
    # Vue
    "vue.js": "vue",
    "vuejs": "vue",
    "vue 3": "vue",
    "vue3": "vue",
    # React
    "reactjs": "react",
    "react.js": "react",
    "react 18": "react",
    # Node
    "node.js": "node",
    "nodejs": "node",
    # Python
    "python3": "python",
    "python 3": "python",
    # TypeScript
    "ts": "typescript",
    # JavaScript
    "js": "javascript",
    "es6": "javascript",
    "ecmascript": "javascript",
    # PostgreSQL
    "postgres": "postgresql",
    "psql": "postgresql",
    # Docker
    "docker-compose": "docker",
    "docker compose": "docker",
    # Kubernetes
    "k8s": "kubernetes",
    # REST API
    "rest-api": "rest",
    "restful": "rest",
    "rest api": "rest",
    # GraphQL
    "graphql api": "graphql",
    # Git
    "github": "git",
    "gitlab": "git",
    # AWS
    "amazon web services": "aws",
    # Azure
    "microsoft azure": "azure",
    # CI/CD
    "ci/cd": "cicd",
    "ci cd": "cicd",
    "continuous integration": "cicd",
    # Fullstack
    "full-stack": "fullstack",
    "full stack": "fullstack",
}

# Fuzzy-Match-Schwellenwert
FUZZY_THRESHOLD = 0.8


def normalize_skill(skill: str) -> str:
    """Normalisiere einen Skill-Namen zu kanonischer Form.

    Args:
        skill: Skill-Name (beliebige Schreibweise)

    Returns:
        Normalisierter Skill-Name
    """
    skill_lower = skill.lower().strip()

    # Direkte Normalisierung
    if skill_lower in SKILL_NORMALIZATIONS:
        return SKILL_NORMALIZATIONS[skill_lower]

    # Entferne Versionsangaben
    skill_clean = re.sub(r"\s*\d+(\.\d+)*\s*$", "", skill_lower)
    if skill_clean in SKILL_NORMALIZATIONS:
        return SKILL_NORMALIZATIONS[skill_clean]

    return skill_lower


def _fuzzy_match(skill: str, skill_set: Set[str], threshold: float = FUZZY_THRESHOLD) -> bool:
    """Prüfe ob ein Skill fuzzy in einem Set enthalten ist.

    Args:
        skill: Skill to search for
        skill_set: Set of skills to search in
        threshold: Minimum similarity ratio (0.0-1.0)

    Returns:
        True if a fuzzy match is found
    """
    for candidate in skill_set:
        ratio = SequenceMatcher(None, skill, candidate).ratio()
        if ratio >= threshold:
            return True
    return False


def calculate_skill_overlap_from_keywords(
    keyword_result: KeywordScoreResult,
    candidate_skills: List[str],
) -> float:
    """Berechne Skill-Overlap zwischen Projekt-Keywords und Kandidaten-Skills.

    Args:
        keyword_result: Ergebnis der Keyword-Analyse
        candidate_skills: Liste der Skills des Kandidaten

    Returns:
        Overlap-Ratio (0.0 - 1.0)
    """
    # Sammle Projekt-Skills aus Keywords (Tier 1 und Tier 2)
    project_skills = set(
        keyword_result.tier_1_keywords + keyword_result.tier_2_keywords
    )

    if not project_skills:
        # Keine Keywords = neutral (50%)
        return 0.5

    # Normalisiere Kandidaten-Skills
    candidate_skills_normalized = {normalize_skill(s) for s in candidate_skills}

    matches = 0.0
    for skill in project_skills:
        normalized_skill = normalize_skill(skill)

        if normalized_skill in candidate_skills_normalized:
            # Exakter Match
            matches += 1.0
        elif _fuzzy_match(normalized_skill, candidate_skills_normalized):
            # Fuzzy Match (halber Punkt)
            matches += 0.5

    overlap = min(1.0, matches / len(project_skills))

    logger.debug(
        "Skill-Overlap: %.2f (Projekt-Skills: %d, Matches: %.1f)",
        overlap,
        len(project_skills),
        matches,
    )

    return overlap


def calculate_team_skill_overlap(
    keyword_result: KeywordScoreResult,
    team_member_skills: List[List[str]],
) -> float:
    """Berechne kombinierten Skill-Overlap für ein Team.

    Aggregiert Skills aller Team-Mitglieder und berechnet
    den Overlap mit den Projekt-Keywords.

    Args:
        keyword_result: Ergebnis der Keyword-Analyse
        team_member_skills: Liste von Skill-Listen pro Team-Mitglied

    Returns:
        Kombinierter Overlap-Ratio (0.0 - 1.0)
    """
    # Kombiniere alle Team-Skills
    all_team_skills = []
    for member_skills in team_member_skills:
        all_team_skills.extend(member_skills)

    # Dedupliziere nach Normalisierung
    unique_skills = list({normalize_skill(s) for s in all_team_skills})

    return calculate_skill_overlap_from_keywords(keyword_result, unique_skills)


def get_missing_skills(
    keyword_result: KeywordScoreResult,
    candidate_skills: List[str],
) -> List[str]:
    """Identifiziere fehlende Skills für ein Projekt.

    Args:
        keyword_result: Ergebnis der Keyword-Analyse
        candidate_skills: Liste der Skills des Kandidaten

    Returns:
        Liste der fehlenden Projekt-Skills
    """
    project_skills = set(
        keyword_result.tier_1_keywords + keyword_result.tier_2_keywords
    )

    candidate_skills_normalized = {normalize_skill(s) for s in candidate_skills}

    missing = []
    for skill in project_skills:
        normalized_skill = normalize_skill(skill)
        if normalized_skill not in candidate_skills_normalized:
            if not _fuzzy_match(normalized_skill, candidate_skills_normalized):
                missing.append(skill)

    return missing


def get_matching_skills(
    keyword_result: KeywordScoreResult,
    candidate_skills: List[str],
) -> List[str]:
    """Identifiziere matchende Skills für ein Projekt.

    Args:
        keyword_result: Ergebnis der Keyword-Analyse
        candidate_skills: Liste der Skills des Kandidaten

    Returns:
        Liste der matchenden Skills
    """
    project_skills = set(
        keyword_result.tier_1_keywords + keyword_result.tier_2_keywords
    )

    candidate_skills_normalized = {normalize_skill(s) for s in candidate_skills}

    matching = []
    for skill in project_skills:
        normalized_skill = normalize_skill(skill)
        if normalized_skill in candidate_skills_normalized:
            matching.append(skill)
        elif _fuzzy_match(normalized_skill, candidate_skills_normalized):
            matching.append(skill)

    return matching
