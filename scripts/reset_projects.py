"""Reset all projects from database for fresh pipeline run.

This script deletes all projects and related data while preserving:
- team_members (Team profiles)
- clients (Auftraggeber history)
- tender_config (Configuration)
- client_research_cache (Cache)

Usage:
    python scripts/reset_projects.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import get_session
from app.db.models import (
    Project,
    TenderDecision,
    TenderLot,
    ApplicationLog,
    ReviewQueue,
    RejectionReason,
    AIUsage,
    ScraperRun,
)


def reset_projects() -> None:
    """Delete all projects and related data from the database."""
    with get_session() as session:
        # Delete in FK order to avoid constraint violations
        deleted_decisions = session.query(TenderDecision).delete()
        deleted_lots = session.query(TenderLot).delete()
        deleted_applications = session.query(ApplicationLog).delete()
        deleted_reviews = session.query(ReviewQueue).delete()
        deleted_rejections = session.query(RejectionReason).delete()
        deleted_ai_usage = session.query(AIUsage).delete()
        deleted_scraper_runs = session.query(ScraperRun).delete()
        deleted_projects = session.query(Project).delete()

        print("Deleted records:")
        print(f"  - TenderDecisions: {deleted_decisions}")
        print(f"  - TenderLots: {deleted_lots}")
        print(f"  - ApplicationLogs: {deleted_applications}")
        print(f"  - ReviewQueue: {deleted_reviews}")
        print(f"  - RejectionReasons: {deleted_rejections}")
        print(f"  - AIUsage: {deleted_ai_usage}")
        print(f"  - ScraperRuns: {deleted_scraper_runs}")
        print(f"  - Projects: {deleted_projects}")
        print()
        print("All projects and related data deleted.")


if __name__ == "__main__":
    reset_projects()
