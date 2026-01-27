"""Skill extraction from project text using regex patterns."""

import re
from typing import List, Set

# Skill patterns grouped by category
# Regex matches common skill names, case-insensitive
SKILL_PATTERNS = {
    # Frontend
    "vue": r"\bvue(?:\.?js)?\b",
    "react": r"\breact(?:\.?js)?\b",
    "angular": r"\bangular\b",
    "typescript": r"\btypescript\b",
    "javascript": r"\bjavascript\b",
    "nuxt": r"\bnuxt(?:\.?js)?\b",
    "html": r"\bhtml5?\b",
    "css": r"\bcss3?\b",
    "sass": r"\bsass\b",
    "tailwind": r"\btailwind(?:css)?\b",
    # Backend
    "python": r"\bpython\b",
    "django": r"\bdjango\b",
    "fastapi": r"\bfastapi\b",
    "flask": r"\bflask\b",
    "java": r"\bjava\b",
    "spring": r"\bspring(?:boot)?\b",
    "kotlin": r"\bkotlin\b",
    "node": r"\bnode(?:\.?js)?\b",
    "express": r"\bexpress(?:\.?js)?\b",
    "nestjs": r"\bnest(?:\.?js)?\b",
    "go": r"\bgolang\b|\bgo\s+(?:lang|programming)\b",
    "rust": r"\brust\b",
    "c#": r"\bc#|csharp|\.net\b",
    "php": r"\bphp\b",
    "ruby": r"\bruby\b",
    "rails": r"\brails\b",
    # Database
    "postgresql": r"\bpostgres(?:ql)?\b",
    "mysql": r"\bmysql\b",
    "mongodb": r"\bmongo(?:db)?\b",
    "redis": r"\bredis\b",
    "elasticsearch": r"\belasticsearch\b",
    "oracle": r"\boracle\s*(?:db)?\b",
    "sql": r"\bsql\b",
    # Cloud & DevOps
    "aws": r"\baws\b|amazon\s+web\s+services\b",
    "azure": r"\bazure\b",
    "gcp": r"\bgcp\b|google\s+cloud\b",
    "docker": r"\bdocker\b",
    "kubernetes": r"\bkubernetes\b|\bk8s\b",
    "terraform": r"\bterraform\b",
    "ansible": r"\bansible\b",
    "jenkins": r"\bjenkins\b",
    "gitlab": r"\bgitlab\b",
    "github": r"\bgithub\b",
    "ci/cd": r"\bci/?cd\b",
    # API & Architecture
    "rest": r"\brest(?:ful)?\s*api\b|\brest\b",
    "graphql": r"\bgraphql\b",
    "microservices": r"\bmicroservices?\b",
    "api": r"\bapi\b",
    # Tools & Misc
    "git": r"\bgit\b",
    "linux": r"\blinux\b",
    "agile": r"\bagile\b|\bscrum\b",
    "jira": r"\bjira\b",
}

# Canonical skill names for display
SKILL_NAMES = {
    "vue": "Vue.js",
    "react": "React",
    "angular": "Angular",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "nuxt": "Nuxt.js",
    "html": "HTML",
    "css": "CSS",
    "sass": "SASS",
    "tailwind": "Tailwind CSS",
    "python": "Python",
    "django": "Django",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "java": "Java",
    "spring": "Spring",
    "kotlin": "Kotlin",
    "node": "Node.js",
    "express": "Express.js",
    "nestjs": "NestJS",
    "go": "Go",
    "rust": "Rust",
    "c#": "C#/.NET",
    "php": "PHP",
    "ruby": "Ruby",
    "rails": "Ruby on Rails",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "oracle": "Oracle",
    "sql": "SQL",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "jenkins": "Jenkins",
    "gitlab": "GitLab",
    "github": "GitHub",
    "ci/cd": "CI/CD",
    "rest": "REST API",
    "graphql": "GraphQL",
    "microservices": "Microservices",
    "api": "API",
    "git": "Git",
    "linux": "Linux",
    "agile": "Agile/Scrum",
    "jira": "Jira",
}


def extract_skills(text: str) -> List[str]:
    """Extract skill names from text using regex patterns.

    Args:
        text: Text to search for skills (project description, PDF content, etc.)

    Returns:
        List of canonical skill names found, deduplicated and sorted
    """
    if not text:
        return []

    found_skills: Set[str] = set()
    text_lower = text.lower()

    for skill_key, pattern in SKILL_PATTERNS.items():
        if re.search(pattern, text_lower, re.IGNORECASE):
            # Use canonical name from lookup
            canonical_name = SKILL_NAMES.get(skill_key, skill_key)
            found_skills.add(canonical_name)

    return sorted(found_skills)


def extract_skills_from_project(
    title: str,
    description: str | None = None,
    pdf_text: str | None = None,
) -> List[str]:
    """Extract skills from all project text sources.

    Args:
        title: Project title
        description: Project description
        pdf_text: Extracted PDF text

    Returns:
        Combined deduplicated list of skills
    """
    combined_text = title
    if description:
        combined_text += " " + description
    if pdf_text:
        combined_text += " " + pdf_text

    return extract_skills(combined_text)
