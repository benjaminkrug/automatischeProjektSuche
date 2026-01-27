"""Application document generator."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.ai.schemas import MatchResult, ResearchResult
from app.core.exceptions import DocumentGenerationError
from app.core.logging import get_logger
from app.db.models import Project, TeamMember
from app.documents.word_handler import fill_anschreiben, create_template_if_missing

logger = get_logger("documents.generator")

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"
CVS_DIR = PROJECT_ROOT / "cvs"


def generate_application_folder(
    project: Project,
    member: TeamMember,
    match: MatchResult,
    research: ResearchResult,
) -> Path:
    """Generate application folder with all required documents.

    Creates folder structure:
        output/YYYY-MM-DD_Client_ProjectTitle/
        - Anschreiben_MemberName.docx
        - CV_MemberName.pdf (copied from cvs/)
        - meta.txt

    Args:
        project: Project to apply for
        member: Team member applying
        match: Matching result with decision details
        research: Research result about client

    Returns:
        Path to created application folder

    Raises:
        DocumentGenerationError: If folder creation fails
    """
    # Create folder name
    date_str = datetime.now().strftime("%Y-%m-%d")
    client_name = _sanitize_filename(project.client_name or "Unbekannt")
    project_title = _sanitize_filename(project.title[:50])
    folder_name = f"{date_str}_{client_name}_{project_title}"

    folder_path = OUTPUT_DIR / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    logger.debug("Created application folder: %s", folder_path)

    # Generate Anschreiben
    _generate_anschreiben(folder_path, project, member, match, research)

    # Copy CV
    _copy_cv(folder_path, member)

    # Generate meta.txt
    _generate_meta(folder_path, project, member, match, research)

    return folder_path


def _sanitize_filename(name: str) -> str:
    """Sanitize string for use in filename."""
    # Replace problematic characters
    replacements = {
        " ": "_",
        "/": "-",
        "\\": "-",
        ":": "-",
        "*": "",
        "?": "",
        '"': "",
        "<": "",
        ">": "",
        "|": "",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
    }

    result = name
    for old, new in replacements.items():
        result = result.replace(old, new)

    # Remove any remaining problematic characters
    result = "".join(c for c in result if c.isalnum() or c in "-_.")

    return result or "Unknown"


def _generate_anschreiben(
    folder_path: Path,
    project: Project,
    member: TeamMember,
    match: MatchResult,
    research: ResearchResult,
) -> Path:
    """Generate Anschreiben document."""
    template_path = TEMPLATES_DIR / "anschreiben_template.docx"
    create_template_if_missing(template_path)

    # Prepare strengths text
    strengths_text = "\n".join([f"• {s}" for s in match.strengths[:5]])

    # Prepare brief project description
    project_desc = research.project_type
    if project.description:
        # First sentence or first 200 chars
        desc = project.description[:200]
        if "." in desc:
            desc = desc.split(".")[0] + "."
        project_desc = f"{research.project_type}. {desc}"

    # Placeholder data
    data = {
        "DATUM": datetime.now().strftime("%d.%m.%Y"),
        "AUFTRAGGEBER": project.client_name or "Sehr geehrte Damen und Herren",
        "PROJEKTTITEL": project.title,
        "KANDIDAT_NAME": member.name,
        "KANDIDAT_ROLLE": member.role or "Softwareentwickler",
        "PROJEKTBESCHREIBUNG": project_desc,
        "STAERKEN": strengths_text,
        "STUNDENSATZ": f"{match.proposed_rate:.0f}",
    }

    member_name = _sanitize_filename(member.name)
    output_path = folder_path / f"Anschreiben_{member_name}.docx"

    fill_anschreiben(template_path, output_path, data)
    logger.debug("Generated Anschreiben: %s", output_path)

    return output_path


def _copy_cv(folder_path: Path, member: TeamMember) -> Optional[Path]:
    """Copy CV to application folder."""
    if not member.cv_path:
        return None

    cv_source = PROJECT_ROOT / member.cv_path
    if not cv_source.exists():
        # Try cvs directory directly
        cv_source = CVS_DIR / Path(member.cv_path).name

    if not cv_source.exists():
        logger.warning("CV not found at %s", cv_source)
        return None

    member_name = _sanitize_filename(member.name)
    cv_dest = folder_path / f"CV_{member_name}.pdf"

    shutil.copy2(cv_source, cv_dest)
    logger.debug("Copied CV to: %s", cv_dest)
    return cv_dest


def _generate_meta(
    folder_path: Path,
    project: Project,
    member: TeamMember,
    match: MatchResult,
    research: ResearchResult,
) -> Path:
    """Generate meta.txt with application details."""
    meta_content = f"""Bewerbung generiert: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

PROJEKT
=======
Titel: {project.title}
Quelle: {project.source}
URL: {project.url}
Auftraggeber: {project.client_name or 'Unbekannt'}
Standort: {project.location or 'Nicht angegeben'}
Remote: {'Ja' if project.remote else 'Nein'}
Öffentlicher Sektor: {'Ja' if project.public_sector else 'Nein'}

KANDIDAT
========
Name: {member.name}
Rolle: {member.role}
Erfahrung: {member.years_experience} Jahre

MATCHING
========
Score: {match.score}/100
Entscheidung: {match.decision}
Stundensatz: {match.proposed_rate} €/h
Begründung: {match.rate_reasoning}

Stärken:
{chr(10).join(['- ' + s for s in match.strengths])}

Schwächen:
{chr(10).join(['- ' + w for w in match.weaknesses])}

KUNDENANALYSE
=============
Projekttyp: {research.project_type}
Budget-Einschätzung: {research.estimated_budget_range}
Kundeninfo: {research.client_info}

Red Flags:
{chr(10).join(['- ' + r for r in research.red_flags])}

Chancen:
{chr(10).join(['- ' + o for o in research.opportunities])}
"""

    meta_path = folder_path / "meta.txt"
    meta_path.write_text(meta_content, encoding="utf-8")
    logger.debug("Generated meta.txt: %s", meta_path)

    return meta_path


def list_application_folders() -> list[Path]:
    """List all application folders in output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        [p for p in OUTPUT_DIR.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
