"""Skill-Overlap-Berechnung basierend auf Keywords.

Berechnet den Overlap zwischen Projekt-Keywords und Kandidaten-Skills
ohne LLM-Call, basierend auf dem Keyword-Scoring-Ergebnis.
"""

import re
from difflib import SequenceMatcher
from typing import Dict, List, Set

from app.ai.keyword_scoring import KeywordScoreResult
from app.core.logging import get_logger

logger = get_logger("ai.skill_overlap")

# Skill-Normalisierungen (verschiedene Schreibweisen -> kanonische Form)
SKILL_NORMALIZATIONS: Dict[str, str] = {
    # Vue
    "vue.js": "vue",
    "vuejs": "vue",
    "vue 3": "vue",
    "vue3": "vue",
    "vue js": "vue",
    "vue 2": "vue",
    # React
    "reactjs": "react",
    "react.js": "react",
    "react 18": "react",
    "react js": "react",
    "react 17": "react",
    # Node
    "node.js": "node",
    "nodejs": "node",
    # Python
    "python3": "python",
    "python 3": "python",
    "python 3.11": "python",
    "python developer": "python",
    "python entwickler": "python",
    # Java
    "java developer": "java",
    "java entwickler": "java",
    # C#/.NET
    "c# entwickler": "c#",
    "c# developer": "c#",
    ".net entwickler": "c#",
    ".net developer": "c#",
    "dotnet": "c#",
    "entity framework": "c#",
    "asp.net": "c#",
    # TypeScript
    "ts": "typescript",
    # JavaScript
    "js": "javascript",
    "es6": "javascript",
    "ecmascript": "javascript",
    # PostgreSQL
    "postgres": "postgresql",
    "psql": "postgresql",
    "postgresql datenbank": "postgresql",
    "postgres datenbank": "postgresql",
    # SQL
    "ms sql": "sql",
    "mssql": "sql",
    "sql server": "sql",
    "t-sql": "sql",
    "mysql datenbank": "mysql",
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

# Skill-Hierarchie: Überbegriffe → konkrete Skills die das Team beherrscht
# Wenn ein Überbegriff im Projekt-Text vorkommt, werden diese Skills als Match gewertet
SKILL_HIERARCHY: Dict[str, Set[str]] = {
    # Deutsche Überbegriffe - Frontend
    "frontend-entwickler": {"vue", "react", "angular", "javascript", "typescript"},
    "frontend entwickler": {"vue", "react", "angular", "javascript", "typescript"},
    "frontend-entwicklung": {"vue", "react", "angular", "javascript", "typescript"},
    "frontendentwicklung": {"vue", "react", "angular", "javascript", "typescript"},
    "ui-entwickler": {"vue", "react", "javascript", "css"},
    "ui entwickler": {"vue", "react", "javascript", "css"},
    "ui-entwicklung": {"vue", "react", "javascript", "css"},
    # Deutsche Überbegriffe - Backend
    "backend-entwickler": {"python", "java", "c#", "node", "django", "fastapi", "spring"},
    "backend entwickler": {"python", "java", "c#", "node", "django", "fastapi", "spring"},
    "backend-entwicklung": {"python", "java", "c#", "node", "django", "fastapi", "spring"},
    "backendentwicklung": {"python", "java", "c#", "node", "django", "fastapi", "spring"},
    # Deutsche Überbegriffe - Fullstack
    "fullstack-entwickler": {"vue", "react", "python", "java", "node", "postgresql"},
    "fullstack entwickler": {"vue", "react", "python", "java", "node", "postgresql"},
    "full-stack-entwickler": {"vue", "react", "python", "java", "node", "postgresql"},
    "fullstackentwickler": {"vue", "react", "python", "java", "node", "postgresql"},
    # Deutsche Überbegriffe - Web
    "webentwickler": {"vue", "react", "javascript", "python", "node", "html", "css"},
    "webentwicklung": {"vue", "react", "javascript", "python", "node", "html", "css"},
    "web-entwickler": {"vue", "react", "javascript", "python", "node", "html", "css"},
    "web-entwicklung": {"vue", "react", "javascript", "python", "node", "html", "css"},
    # Deutsche Überbegriffe - Software
    "softwareentwickler": {"python", "java", "c#", "javascript", "typescript"},
    "softwareentwicklung": {"python", "java", "c#", "javascript", "typescript"},
    "software-entwickler": {"python", "java", "c#", "javascript", "typescript"},
    "software-entwicklung": {"python", "java", "c#", "javascript", "typescript"},
    # Deutsche Überbegriffe - Datenbank
    "datenbankentwickler": {"postgresql", "mysql", "sql", "mongodb"},
    "datenbankentwicklung": {"postgresql", "mysql", "sql", "mongodb"},
    "datenbank-entwickler": {"postgresql", "mysql", "sql", "mongodb"},
    "datenbank-entwicklung": {"postgresql", "mysql", "sql", "mongodb"},
    # DevOps
    "devops-engineer": {"docker", "kubernetes", "jenkins", "gitlab", "cicd", "aws", "azure"},
    "devops engineer": {"docker", "kubernetes", "jenkins", "gitlab", "cicd", "aws", "azure"},
    "devops": {"docker", "kubernetes", "jenkins", "gitlab", "cicd"},
    "devops-entwickler": {"docker", "kubernetes", "jenkins", "gitlab", "cicd"},
    # Cloud
    "cloud-entwickler": {"aws", "azure", "docker", "kubernetes"},
    "cloud entwickler": {"aws", "azure", "docker", "kubernetes"},
    "cloud-architekt": {"aws", "azure", "docker", "kubernetes"},
    "cloud architekt": {"aws", "azure", "docker", "kubernetes"},
    # API
    "api-entwickler": {"rest", "graphql", "python", "node", "fastapi"},
    "api entwickler": {"rest", "graphql", "python", "node", "fastapi"},
    "api-entwicklung": {"rest", "graphql", "python", "node", "fastapi"},
    # Englische Überbegriffe
    "frontend developer": {"vue", "react", "angular", "javascript", "typescript"},
    "backend developer": {"python", "java", "c#", "node", "django", "fastapi", "spring"},
    "fullstack developer": {"vue", "react", "python", "java", "node", "postgresql"},
    "full stack developer": {"vue", "react", "python", "java", "node", "postgresql"},
    "web developer": {"vue", "react", "javascript", "python", "node"},
    "software developer": {"python", "java", "c#", "javascript", "typescript"},
    "software engineer": {"python", "java", "c#", "javascript", "typescript"},
}

# Fuzzy-Match-Schwellenwert
FUZZY_THRESHOLD = 0.8


def expand_skill_terms(text: str) -> Set[str]:
    """Expandiere Überbegriffe zu konkreten Skills.

    Wenn der Text z.B. "Frontend-Entwickler" enthält, werden die
    konkreten Skills (Vue, React, JavaScript etc.) zurückgegeben.

    Args:
        text: Projekt-Text (sollte bereits lowercase sein)

    Returns:
        Set von konkreten Skills die durch Überbegriffe impliziert werden
    """
    expanded: Set[str] = set()
    text_lower = text.lower()

    for term, skills in SKILL_HIERARCHY.items():
        if term in text_lower:
            expanded.update(skills)
            logger.debug(
                "Skill expansion: '%s' -> %s",
                term,
                ", ".join(skills),
            )

    return expanded


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
