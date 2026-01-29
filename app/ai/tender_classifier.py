"""LLM-based tender classification for better tech/project detection.

Uses GPT-4o-mini for quick classification of tenders before scoring.
Provides structured output for project type and tech stack detection.

Cost: ~0.001€/call → ~3€/month at 100 tenders/day
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional

from openai import OpenAI

from app.core.logging import get_logger
from app.settings import settings
from app.ai.cost_tracking import log_ai_usage

logger = get_logger("ai.tender_classifier")

# Classification model
CLASSIFIER_MODEL = "gpt-4o-mini"

# Max tokens for input (title + description truncated)
MAX_INPUT_CHARS = 1000

# System prompt for classification
SYSTEM_PROMPT = """Du bist ein Experte für öffentliche IT-Ausschreibungen.
Analysiere die Ausschreibung und bestimme:
1. Ob es sich um ein Software-Projekt handelt
2. Den Projekttyp (webapp, mobile, backend, fullstack, other)
3. Die erkannten Technologien/Frameworks

Antworte NUR mit validem JSON in diesem Format:
{
  "is_software_project": true/false,
  "project_type": "webapp|mobile|backend|fullstack|other",
  "tech_stack": ["Technology1", "Technology2"],
  "confidence": 0.0-1.0,
  "reason": "Kurze Begründung"
}

Fokussiere auf konkrete Indikatoren:
- webapp: Webanwendung, Portal, SPA, responsive, Browser-basiert
- mobile: iOS, Android, App-Store, mobile App
- backend: API, Server, Datenbank, Microservices
- fullstack: Kombination aus Frontend und Backend
- other: IT aber nicht Softwareentwicklung (Hardware, Support, etc.)"""


@dataclass
class TenderClassification:
    """Result of LLM tender classification."""

    is_software_project: bool = False
    project_type: str = "other"
    tech_stack: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    error: Optional[str] = None

    @property
    def is_webapp_or_mobile(self) -> bool:
        """Check if project is webapp or mobile app."""
        return self.project_type in ("webapp", "mobile", "fullstack")


def classify_tender(
    title: str,
    description: str = "",
    db=None,
    project_id: Optional[int] = None,
) -> TenderClassification:
    """Classify a tender using LLM.

    Args:
        title: Tender title
        description: Tender description (truncated internally)
        db: Optional database session for cost tracking
        project_id: Optional project ID for tracking

    Returns:
        TenderClassification with results
    """
    # Truncate description to limit tokens
    if description and len(description) > MAX_INPUT_CHARS - len(title) - 20:
        description = description[:MAX_INPUT_CHARS - len(title) - 20] + "..."

    user_prompt = f"Titel: {title}\n\nBeschreibung: {description or 'Keine Beschreibung verfügbar'}"

    try:
        client = OpenAI(api_key=settings.openai_api_key)

        response = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # Low temperature for consistent classification
            max_tokens=200,
            response_format={"type": "json_object"},
        )

        # Parse response
        content = response.choices[0].message.content
        result = json.loads(content)

        # Track usage
        if db and response.usage:
            log_ai_usage(
                db=db,
                operation="tender_classification",
                model=CLASSIFIER_MODEL,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                project_id=project_id,
            )

        return TenderClassification(
            is_software_project=result.get("is_software_project", False),
            project_type=result.get("project_type", "other"),
            tech_stack=result.get("tech_stack", []),
            confidence=result.get("confidence", 0.5),
            reason=result.get("reason", ""),
        )

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM response as JSON: %s", e)
        return TenderClassification(error=f"JSON parse error: {e}")

    except Exception as e:
        logger.warning("LLM classification failed: %s", e)
        return TenderClassification(error=str(e))


def classify_tender_batch(
    tenders: List[dict],
    db=None,
) -> List[TenderClassification]:
    """Classify multiple tenders.

    Args:
        tenders: List of dicts with 'title' and 'description' keys
        db: Optional database session for cost tracking

    Returns:
        List of TenderClassification results
    """
    results = []

    for tender in tenders:
        result = classify_tender(
            title=tender.get("title", ""),
            description=tender.get("description", ""),
            db=db,
            project_id=tender.get("id"),
        )
        results.append(result)

    return results


def quick_software_check(title: str, description: str = "") -> bool:
    """Quick heuristic check if tender might be software-related.

    Use this as a pre-filter before LLM classification to save costs.

    Args:
        title: Tender title
        description: Tender description

    Returns:
        True if likely software-related (should be classified)
    """
    text = f"{title} {description}".lower()

    # Strong indicators for software projects
    software_keywords = [
        "software", "programmierung", "entwicklung", "anwendung",
        "webapp", "webanwendung", "webportal", "portal",
        "app ", "mobile app", "ios", "android",
        "api", "backend", "frontend", "fullstack",
        "datenbank", "cloud", "saas", "plattform",
        "digitalisierung", "it-", "edv",
        "react", "vue", "angular", "python", "java", "node",
        "microservice", "docker", "kubernetes",
    ]

    # Anti-indicators (not software development)
    non_software_keywords = [
        "hardware", "drucker", "lizenzen", "support", "helpdesk",
        "netzwerk", "firewall", "wartung", "hosting", "server-hardware",
        "möbel", "reinigung", "catering", "transport",
    ]

    # Check for software keywords
    has_software_keyword = any(kw in text for kw in software_keywords)

    # Check for anti-keywords
    has_anti_keyword = any(kw in text for kw in non_software_keywords)

    # Software keyword present and no strong anti-indicator
    return has_software_keyword and not has_anti_keyword


def enrich_project_with_classification(
    project,
    classification: TenderClassification,
) -> None:
    """Enrich project with classification results.

    Adds classification data as attributes for later scoring.

    Args:
        project: Project or RawProject to enrich
        classification: Classification result
    """
    project._llm_classification = classification
    project._is_software = classification.is_software_project
    project._project_type = classification.project_type
    project._detected_tech_stack = classification.tech_stack
    project._classification_confidence = classification.confidence

    # Add tech stack to skills if not already present
    if classification.tech_stack and hasattr(project, "skills"):
        existing_skills = set(s.lower() for s in (project.skills or []))
        for tech in classification.tech_stack:
            if tech.lower() not in existing_skills:
                if project.skills is None:
                    project.skills = []
                project.skills.append(tech)


# Score adjustments based on classification
CLASSIFICATION_SCORE_MODIFIERS = {
    "webapp": 15,      # Our core competency
    "fullstack": 12,   # Also good fit
    "mobile": 10,      # Can do but not primary
    "backend": 8,      # OK fit
    "other": 0,        # No adjustment
}


def get_classification_score_modifier(classification: TenderClassification) -> int:
    """Get score modifier based on classification.

    Args:
        classification: LLM classification result

    Returns:
        Score modifier (can be positive or negative)
    """
    if not classification.is_software_project:
        return -10  # Penalty for non-software

    base_modifier = CLASSIFICATION_SCORE_MODIFIERS.get(
        classification.project_type, 0
    )

    # Confidence adjustment
    if classification.confidence < 0.5:
        base_modifier = base_modifier // 2

    # Tech stack bonus
    known_techs = ["react", "vue", "angular", "python", "java", "typescript", "node"]
    tech_match = sum(
        1 for tech in classification.tech_stack
        if tech.lower() in known_techs
    )
    if tech_match >= 2:
        base_modifier += 5

    return base_modifier
