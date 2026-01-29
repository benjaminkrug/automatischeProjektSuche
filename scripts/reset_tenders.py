"""Reset all tender projects from database for fresh pipeline run.

This script deletes only tender projects (project_type='tender') and related data.
Preserves:
- Freelance projects (project_type='freelance' or NULL)
- team_members (Team profiles)
- clients (Auftraggeber history)
- tender_config (Configuration)
- client_research_cache (Cache)

Usage:
    python scripts/reset_tenders.py
    python scripts/reset_tenders.py --dry-run  # Preview without deleting
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_
from app.db.session import get_session
from app.db.models import (
    Project,
    TenderDecision,
    TenderLot,
    ApplicationLog,
    ReviewQueue,
    RejectionReason,
    ScraperRun,
)


def reset_tenders(dry_run: bool = False) -> None:
    """Delete all tender projects and related data from the database.

    Args:
        dry_run: If True, only show what would be deleted without actually deleting.
    """
    with get_session() as session:
        # Get all tender project IDs first
        tender_projects = session.query(Project).filter(
            Project.project_type == "tender"
        ).all()

        tender_ids = [p.id for p in tender_projects]

        if not tender_ids:
            print("No tender projects found in database.")
            return

        print(f"Found {len(tender_ids)} tender projects")
        print()

        if dry_run:
            print("DRY RUN - No data will be deleted")
            print()

        # Count related records
        decisions_count = session.query(TenderDecision).filter(
            TenderDecision.project_id.in_(tender_ids)
        ).count()

        lots_count = session.query(TenderLot).filter(
            TenderLot.project_id.in_(tender_ids)
        ).count()

        applications_count = session.query(ApplicationLog).filter(
            ApplicationLog.project_id.in_(tender_ids)
        ).count()

        reviews_count = session.query(ReviewQueue).filter(
            ReviewQueue.project_id.in_(tender_ids)
        ).count()

        rejections_count = session.query(RejectionReason).filter(
            RejectionReason.project_id.in_(tender_ids)
        ).count()

        # Count tender-related scraper runs
        tender_portals = ["bund.de", "bund_rss", "dtvp", "evergabe", "evergabe_online",
                         "simap", "ted", "oeffentlichevergabe", "nrw", "bayern", "bawue"]
        scraper_runs_count = session.query(ScraperRun).filter(
            ScraperRun.portal.in_(tender_portals)
        ).count()

        print("Records to delete:" if dry_run else "Deleting records:")
        print(f"  - TenderDecisions: {decisions_count}")
        print(f"  - TenderLots: {lots_count}")
        print(f"  - ApplicationLogs: {applications_count}")
        print(f"  - ReviewQueue: {reviews_count}")
        print(f"  - RejectionReasons: {rejections_count}")
        print(f"  - ScraperRuns (tender portals): {scraper_runs_count}")
        print(f"  - Projects (tender): {len(tender_ids)}")
        print()

        if dry_run:
            print("Run without --dry-run to actually delete.")
            return

        # Delete in FK order to avoid constraint violations
        deleted_decisions = session.query(TenderDecision).filter(
            TenderDecision.project_id.in_(tender_ids)
        ).delete(synchronize_session=False)

        deleted_lots = session.query(TenderLot).filter(
            TenderLot.project_id.in_(tender_ids)
        ).delete(synchronize_session=False)

        deleted_applications = session.query(ApplicationLog).filter(
            ApplicationLog.project_id.in_(tender_ids)
        ).delete(synchronize_session=False)

        deleted_reviews = session.query(ReviewQueue).filter(
            ReviewQueue.project_id.in_(tender_ids)
        ).delete(synchronize_session=False)

        deleted_rejections = session.query(RejectionReason).filter(
            RejectionReason.project_id.in_(tender_ids)
        ).delete(synchronize_session=False)

        deleted_scraper_runs = session.query(ScraperRun).filter(
            ScraperRun.portal.in_(tender_portals)
        ).delete(synchronize_session=False)

        deleted_projects = session.query(Project).filter(
            Project.project_type == "tender"
        ).delete(synchronize_session=False)

        print("Deleted:")
        print(f"  - TenderDecisions: {deleted_decisions}")
        print(f"  - TenderLots: {deleted_lots}")
        print(f"  - ApplicationLogs: {deleted_applications}")
        print(f"  - ReviewQueue: {deleted_reviews}")
        print(f"  - RejectionReasons: {deleted_rejections}")
        print(f"  - ScraperRuns: {deleted_scraper_runs}")
        print(f"  - Projects: {deleted_projects}")
        print()
        print("All tender projects and related data deleted.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    reset_tenders(dry_run=dry_run)
