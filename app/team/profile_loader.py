"""Parse team profiles from Markdown file."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TeamProfile:
    """Parsed team member profile."""
    name: str
    organization: str
    position: str
    role: str
    skills: list[str] = field(default_factory=list)
    years_experience: int = 0
    industries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    min_hourly_rate: float = 80.0
    cv_filename: str = ""
    profile_text: str = ""


def parse_team_profiles_md(filepath: str | Path = None) -> list[TeamProfile]:
    """Parse Teamprofile_ZusammenZuhause.md and extract team member profiles."""
    if filepath is None:
        filepath = Path(__file__).parent.parent.parent / "team" / "Teamprofile_ZusammenZuhause.md"

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    profiles = []

    # Split by profile sections (## Profil X:)
    profile_sections = re.split(r"## Profil \d+:", content)

    for section in profile_sections[1:]:  # Skip the header part
        profile = _parse_profile_section(section)
        if profile:
            profiles.append(profile)

    return profiles


def _parse_profile_section(section: str) -> TeamProfile | None:
    """Parse a single profile section."""
    lines = section.strip().split("\n")

    # Extract name from first line
    name_match = re.match(r"\s*(.+)", lines[0])
    if not name_match:
        return None

    name = name_match.group(1).strip()

    # Initialize defaults
    organization = ""
    position = ""
    role = ""
    skills = []
    years_experience = 0
    industries = []

    # Extract personal data
    personal_data_match = re.search(
        r"### Persönliche Daten\s*\n(.*?)(?=###|\Z)",
        section,
        re.DOTALL
    )
    if personal_data_match:
        data = personal_data_match.group(1)
        org_match = re.search(r"\*\*Organisation:\*\*\s*(.+)", data)
        if org_match:
            organization = org_match.group(1).strip()
        pos_match = re.search(r"\*\*Position:\*\*\s*(.+)", data)
        if pos_match:
            position = pos_match.group(1).strip()
        role_match = re.search(r"\*\*Rolle im Projekt:\*\*\s*(.+)", data)
        if role_match:
            role = role_match.group(1).strip()

    # Extract technical expertise
    tech_match = re.search(
        r"\*\*Technische Expertise:\*\*\s*\n(.*?)(?=\*\*Erfahrung|\Z)",
        section,
        re.DOTALL
    )
    if tech_match:
        tech_text = tech_match.group(1)
        # Extract skills from bullet points
        skill_items = re.findall(r"- ([^\n]+)", tech_text)
        for item in skill_items:
            # Split by common delimiters and clean up
            parts = re.split(r"[,()]", item)
            for part in parts:
                part = part.strip()
                if part and len(part) > 1:
                    skills.append(part)

    # Extract years of experience
    exp_match = re.search(r"\*\*(\d+)\+?\s*Jahre\*\*.*(?:Berufserfahrung|Erfahrung|Web|App)", section)
    if exp_match:
        years_experience = int(exp_match.group(1))
    else:
        # Try alternative pattern
        exp_match = re.search(r"(\d+)\+?\s*Jahre.*?Erfahrung", section)
        if exp_match:
            years_experience = int(exp_match.group(1))

    # Extract industries from project experience
    if "öffentlichen Sektor" in section.lower() or "public sector" in section.lower():
        industries.append("Öffentlicher Sektor")
    if "Logistik" in section:
        industries.append("Logistik")
    if "Life Sciences" in section:
        industries.append("Life Sciences")
    if "Energie" in section or "Entega" in section:
        industries.append("Energie")

    # Build profile text for embedding
    profile_text = _build_profile_text(name, role, skills, section)

    # Map CV filenames
    cv_mapping = {
        "Benjamin Krug": "Lebenslauf_Benjamin_Krug.pdf",
        "Viktor Eigenseer": "Lebenslauf Viktor Eigenseer.pdf",
        "Souhail Sehli": "Lebenslauf Souhail Sehli_details (2).pdf",
    }

    return TeamProfile(
        name=name,
        organization=organization,
        position=position,
        role=role,
        skills=skills,
        years_experience=years_experience,
        industries=industries,
        languages=["Deutsch", "Englisch"],  # Default languages
        min_hourly_rate=80.0,  # Default rate
        cv_filename=cv_mapping.get(name, ""),
        profile_text=profile_text,
    )


def _build_profile_text(name: str, role: str, skills: list[str], section: str) -> str:
    """Build a text representation for embedding."""
    # Extract relevant project descriptions
    projects = []
    project_matches = re.findall(
        r"\*\*Projekt \d+:.*?\*\*\s*\n.*?\*\*Beschreibung:\*\*\s*([^\n]+)",
        section
    )
    projects.extend(project_matches)

    skills_text = ", ".join(skills) if skills else ""
    projects_text = " ".join(projects) if projects else ""

    profile_text = f"""
Name: {name}
Rolle: {role}
Technische Skills: {skills_text}
Projekterfahrung: {projects_text}
""".strip()

    return profile_text
