"""Project type classification for improved matching.

Classifies projects by type (webapp, api, mobile, etc.) to filter
out unsuitable project types before LLM matching.
"""

from enum import Enum
from typing import Dict, List, Tuple

from app.core.logging import get_logger

logger = get_logger("ai.project_classifier")


class ProjectType(str, Enum):
    """Types of IT projects."""

    WEBAPP = "webapp"  # Web applications, portals, SPAs
    API = "api"  # Backend APIs, microservices
    MOBILE = "mobile"  # iOS/Android apps
    DEVOPS = "devops"  # CI/CD, infrastructure
    DATA = "data"  # Databases, ETL, analytics
    LEGACY = "legacy"  # Migrations, modernization
    ADMIN = "admin"  # Admin jobs, support
    CONSULTING = "consulting"  # Pure consulting without development
    OTHER = "other"  # Uncategorized


# Keywords for each project type (all lowercase)
PROJECT_TYPE_KEYWORDS: Dict[ProjectType, List[str]] = {
    ProjectType.WEBAPP: [
        "webanwendung", "webapp", "web-app", "webapplikation",
        "portal", "webportal", "web-portal", "plattform",
        "frontend", "front-end", "spa", "single page",
        "dashboard", "admin panel", "cms", "website",
        "responsive", "progressive web", "pwa",
        "vue", "react", "angular", "nuxt", "next.js",
    ],
    ProjectType.API: [
        "api", "rest", "graphql", "backend", "back-end",
        "microservice", "microservices", "schnittstelle",
        "webservice", "web-service", "endpoint",
        "serverless", "lambda", "api gateway",
        "python backend", "node backend", "java backend",
    ],
    ProjectType.MOBILE: [
        "ios", "android", "mobile app", "mobile-app",
        "smartphone", "tablet", "app-entwicklung",
        "flutter", "react native", "ionic", "xamarin",
        "swift", "kotlin mobile", "objective-c",
    ],
    ProjectType.DEVOPS: [
        "devops", "ci/cd", "cicd", "pipeline",
        "kubernetes", "k8s", "docker", "terraform",
        "ansible", "jenkins", "gitlab ci", "github actions",
        "infrastructure", "cloud engineer", "site reliability",
        "monitoring", "prometheus", "grafana",
    ],
    ProjectType.DATA: [
        "datenbank", "database", "etl", "data warehouse",
        "analytics", "bi", "business intelligence",
        "data engineer", "data science", "machine learning",
        "big data", "hadoop", "spark", "databricks",
        "powerbi", "tableau", "reporting",
    ],
    ProjectType.LEGACY: [
        "migration", "modernisierung", "ablösung",
        "refactoring", "legacy", "altanwendung",
        "systemablösung", "technologiewechsel",
        "cobol migration", "mainframe migration",
    ],
    ProjectType.ADMIN: [
        "administrator", "admin", "support",
        "helpdesk", "service desk", "1st level", "2nd level",
        "wartung", "maintenance", "betrieb",
        "netzwerk", "firewall", "cisco",
    ],
    ProjectType.CONSULTING: [
        "berater", "consultant", "beratung", "consulting",
        "requirements", "anforderungsanalyse", "konzeption",
        "projektmanagement", "project manager", "scrum master",
    ],
}

# Project types that match the Fullstack profile
PREFERRED_TYPES: List[ProjectType] = [
    ProjectType.WEBAPP,
    ProjectType.API,
    ProjectType.DATA,  # Often includes backend work
]

# Project types to avoid
AVOID_TYPES: List[ProjectType] = [
    ProjectType.MOBILE,
    ProjectType.DEVOPS,
    ProjectType.ADMIN,
    ProjectType.CONSULTING,
]

# Neutral types - evaluate case by case
NEUTRAL_TYPES: List[ProjectType] = [
    ProjectType.LEGACY,
    ProjectType.OTHER,
]


def classify_project(title: str, description: str = "") -> ProjectType:
    """Classify project by type based on keywords.

    Args:
        title: Project title
        description: Project description

    Returns:
        ProjectType enum value
    """
    text = f"{title} {description}".lower()

    # Count keyword matches for each type
    scores: Dict[ProjectType, int] = {}
    for ptype, keywords in PROJECT_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        scores[ptype] = score

    # Return type with highest score, or OTHER if no matches
    max_score = max(scores.values())
    if max_score == 0:
        return ProjectType.OTHER

    # Return first type with max score (deterministic)
    for ptype in ProjectType:
        if scores.get(ptype, 0) == max_score:
            return ptype

    return ProjectType.OTHER


def classify_project_detailed(
    title: str, description: str = ""
) -> Tuple[ProjectType, Dict[ProjectType, int], List[str]]:
    """Classify project with detailed scoring information.

    Args:
        title: Project title
        description: Project description

    Returns:
        Tuple of (primary_type, scores_dict, matched_keywords)
    """
    text = f"{title} {description}".lower()

    scores: Dict[ProjectType, int] = {}
    all_matched: List[str] = []

    for ptype, keywords in PROJECT_TYPE_KEYWORDS.items():
        matched = [kw for kw in keywords if kw in text]
        scores[ptype] = len(matched)
        all_matched.extend(matched)

    max_score = max(scores.values()) if scores else 0
    if max_score == 0:
        return ProjectType.OTHER, scores, []

    primary_type = ProjectType.OTHER
    for ptype in ProjectType:
        if scores.get(ptype, 0) == max_score:
            primary_type = ptype
            break

    return primary_type, scores, list(set(all_matched))


def is_preferred_type(project_type: ProjectType) -> bool:
    """Check if project type is preferred for the team.

    Args:
        project_type: The classified project type

    Returns:
        True if this is a preferred project type
    """
    return project_type in PREFERRED_TYPES


def should_avoid_type(project_type: ProjectType) -> bool:
    """Check if project type should be avoided.

    Args:
        project_type: The classified project type

    Returns:
        True if this project type should be avoided
    """
    return project_type in AVOID_TYPES


def get_type_recommendation(project_type: ProjectType) -> str:
    """Get a recommendation based on project type.

    Args:
        project_type: The classified project type

    Returns:
        Recommendation string
    """
    if project_type in PREFERRED_TYPES:
        return f"Projekttyp '{project_type.value}' passt gut zum Team-Profil"
    elif project_type in AVOID_TYPES:
        return f"Projekttyp '{project_type.value}' passt nicht zum Team-Profil"
    else:
        return f"Projekttyp '{project_type.value}' - Einzelfallprüfung empfohlen"
