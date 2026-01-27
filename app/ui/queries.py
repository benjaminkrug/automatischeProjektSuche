"""Database queries for the Streamlit UI."""

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.db.models import (
    ApplicationLog,
    Project,
    RejectionReason,
    ReviewQueue,
    TeamMember,
)
from app.db.session import SessionLocal


def get_session() -> Session:
    """Get a database session."""
    return SessionLocal()


# --- Dashboard Statistics ---


def get_today_stats(session: Session) -> dict:
    """Get statistics for today.

    Returns:
        Dict with scraped_today, new_today counts
    """
    today_start = datetime.combine(date.today(), datetime.min.time())

    scraped_today = (
        session.query(func.count(Project.id))
        .filter(Project.scraped_at >= today_start)
        .scalar()
    ) or 0

    new_today = (
        session.query(func.count(Project.id))
        .filter(
            Project.scraped_at >= today_start,
            Project.status == "new",
        )
        .scalar()
    ) or 0

    return {
        "scraped_today": scraped_today,
        "new_today": new_today,
    }


def get_total_stats(session: Session) -> dict:
    """Get total statistics.

    Returns:
        Dict with total_projects, total_applications counts
    """
    total_projects = session.query(func.count(Project.id)).scalar() or 0
    total_applications = session.query(func.count(ApplicationLog.id)).scalar() or 0

    return {
        "total_projects": total_projects,
        "total_applications": total_applications,
    }


def get_active_applications_count(session: Session) -> int:
    """Get count of active (pending) applications."""
    return (
        session.query(func.count(ApplicationLog.id))
        .filter(ApplicationLog.outcome.is_(None))
        .scalar()
    ) or 0


def get_recent_activity(session: Session, limit: int = 10) -> List[dict]:
    """Get recent activity entries.

    Returns:
        List of activity dicts with timestamp, type, and description
    """
    activities = []

    # Recent applications
    recent_apps = (
        session.query(ApplicationLog, Project)
        .join(Project, ApplicationLog.project_id == Project.id)
        .order_by(ApplicationLog.applied_at.desc())
        .limit(limit)
        .all()
    )

    for app, project in recent_apps:
        activities.append({
            "timestamp": app.applied_at,
            "type": "application",
            "description": f"Bewerbung: {project.title[:50]}...",
        })

    # Recent rejections
    recent_rejections = (
        session.query(RejectionReason, Project)
        .join(Project, RejectionReason.project_id == Project.id)
        .order_by(RejectionReason.created_at.desc())
        .limit(limit)
        .all()
    )

    for rejection, project in recent_rejections:
        activities.append({
            "timestamp": rejection.created_at,
            "type": "rejection",
            "description": f"Abgelehnt: {rejection.reason_code}",
        })

    # Sort by timestamp and return top entries
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities[:limit]


# --- Projects ---


def get_projects(
    session: Session,
    status: Optional[str] = None,
    source: Optional[str] = None,
    search_text: Optional[str] = None,
    days_back: int = 30,
    limit: int = 100,
) -> List[Project]:
    """Get filtered projects.

    Args:
        session: Database session
        status: Filter by status (optional)
        source: Filter by source portal (optional)
        search_text: Search in title/description (optional)
        days_back: Only show projects from last N days
        limit: Maximum number of results

    Returns:
        List of Project objects
    """
    query = session.query(Project)

    # Date filter
    date_threshold = datetime.utcnow() - timedelta(days=days_back)
    query = query.filter(Project.scraped_at >= date_threshold)

    # Status filter
    if status and status != "Alle":
        query = query.filter(Project.status == status)

    # Source filter
    if source and source != "Alle":
        query = query.filter(Project.source == source)

    # Text search
    if search_text:
        search_pattern = f"%{search_text}%"
        query = query.filter(
            Project.title.ilike(search_pattern)
            | Project.description.ilike(search_pattern)
        )

    return query.order_by(Project.scraped_at.desc()).limit(limit).all()


def get_project_by_id(session: Session, project_id: int) -> Optional[Project]:
    """Get a single project by ID."""
    return session.query(Project).filter(Project.id == project_id).first()


def get_project_sources(session: Session) -> List[str]:
    """Get all unique project sources."""
    sources = session.query(Project.source).distinct().all()
    return [s[0] for s in sources if s[0]]


def get_project_statuses(session: Session) -> List[str]:
    """Get all unique project statuses."""
    statuses = session.query(Project.status).distinct().all()
    return [s[0] for s in statuses if s[0]]


# --- Team Members ---


def get_team_members(session: Session, active_only: bool = False) -> List[TeamMember]:
    """Get all team members.

    Args:
        session: Database session
        active_only: If True, only return active members

    Returns:
        List of TeamMember objects
    """
    query = session.query(TeamMember)

    if active_only:
        query = query.filter(TeamMember.active == True)

    return query.order_by(TeamMember.name).all()


def get_team_member_by_id(session: Session, member_id: int) -> Optional[TeamMember]:
    """Get a single team member by ID."""
    return session.query(TeamMember).filter(TeamMember.id == member_id).first()


# --- Review Queue ---


def get_pending_reviews(session: Session) -> List[Tuple[ReviewQueue, Project]]:
    """Get all pending review entries with their projects.

    Returns:
        List of (ReviewQueue, Project) tuples
    """
    return (
        session.query(ReviewQueue, Project)
        .join(Project, ReviewQueue.project_id == Project.id)
        .filter(ReviewQueue.resolved_at.is_(None))
        .order_by(ReviewQueue.created_at.desc())
        .all()
    )


def resolve_review(
    session: Session,
    review_id: int,
    resolution: str,
    team_member_id: Optional[int] = None,
) -> bool:
    """Resolve a review queue entry.

    Args:
        session: Database session
        review_id: ID of the review entry
        resolution: 'apply' or 'reject'
        team_member_id: Team member ID if applying

    Returns:
        True if successful
    """
    review = session.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    if not review:
        return False

    review.resolved_at = datetime.utcnow()
    review.resolution = resolution

    # Update project status
    project = session.query(Project).filter(Project.id == review.project_id).first()
    if project:
        if resolution == "apply" and team_member_id:
            project.status = "applied"
            # Create application log
            app_log = ApplicationLog(
                project_id=project.id,
                team_member_id=team_member_id,
                public_sector=project.public_sector,
            )
            session.add(app_log)
        else:
            project.status = "rejected"
            # Create rejection reason
            rejection = RejectionReason(
                project_id=project.id,
                reason_code="MANUAL_REJECT",
                explanation="Manuell abgelehnt aus Review Queue",
            )
            session.add(rejection)

    session.commit()
    return True


# --- Application Logs ---


def get_application_logs(
    session: Session,
    outcome: Optional[str] = None,
    limit: int = 100,
) -> List[Tuple[ApplicationLog, Project, TeamMember]]:
    """Get application logs with related project and team member.

    Args:
        session: Database session
        outcome: Filter by outcome (optional)
        limit: Maximum number of results

    Returns:
        List of (ApplicationLog, Project, TeamMember) tuples
    """
    query = (
        session.query(ApplicationLog, Project, TeamMember)
        .join(Project, ApplicationLog.project_id == Project.id)
        .join(TeamMember, ApplicationLog.team_member_id == TeamMember.id)
    )

    if outcome and outcome != "Alle":
        if outcome == "Offen":
            query = query.filter(ApplicationLog.outcome.is_(None))
        else:
            query = query.filter(ApplicationLog.outcome == outcome)

    return query.order_by(ApplicationLog.applied_at.desc()).limit(limit).all()


def update_application_outcome(
    session: Session,
    application_id: int,
    outcome: str,
) -> bool:
    """Update the outcome of an application.

    Args:
        session: Database session
        application_id: ID of the application
        outcome: New outcome value

    Returns:
        True if successful
    """
    app = session.query(ApplicationLog).filter(ApplicationLog.id == application_id).first()
    if not app:
        return False

    app.outcome = outcome
    app.outcome_at = datetime.utcnow()
    session.commit()
    return True


def get_win_rate(session: Session) -> dict:
    """Calculate win rate statistics.

    Returns:
        Dict with total, won, lost, pending counts and win_rate percentage
    """
    total = session.query(func.count(ApplicationLog.id)).scalar() or 0
    won = (
        session.query(func.count(ApplicationLog.id))
        .filter(ApplicationLog.outcome == "won")
        .scalar()
    ) or 0
    lost = (
        session.query(func.count(ApplicationLog.id))
        .filter(ApplicationLog.outcome == "lost")
        .scalar()
    ) or 0
    pending = (
        session.query(func.count(ApplicationLog.id))
        .filter(ApplicationLog.outcome.is_(None))
        .scalar()
    ) or 0

    completed = won + lost
    win_rate = (won / completed * 100) if completed > 0 else 0

    return {
        "total": total,
        "won": won,
        "lost": lost,
        "pending": pending,
        "win_rate": round(win_rate, 1),
    }


# --- Portal Statistics ---


def get_portal_stats(session: Session) -> List[dict]:
    """Get project counts and win rates per portal/source.

    Returns:
        List of dicts with source, total, applied, won, win_rate
    """
    # Get all sources
    sources = session.query(Project.source).distinct().all()

    stats = []
    for (source,) in sources:
        if not source:
            continue

        total = (
            session.query(func.count(Project.id))
            .filter(Project.source == source)
            .scalar()
        ) or 0

        applied = (
            session.query(func.count(Project.id))
            .filter(Project.source == source, Project.status == "applied")
            .scalar()
        ) or 0

        # Get applications for this source
        source_apps = (
            session.query(ApplicationLog)
            .join(Project, ApplicationLog.project_id == Project.id)
            .filter(Project.source == source)
        )

        won = source_apps.filter(ApplicationLog.outcome == "won").count()
        lost = source_apps.filter(ApplicationLog.outcome == "lost").count()
        completed = won + lost
        win_rate = (won / completed * 100) if completed > 0 else 0

        stats.append({
            "source": source,
            "total": total,
            "applied": applied,
            "won": won,
            "lost": lost,
            "win_rate": round(win_rate, 1),
        })

    # Sort by total projects descending
    stats.sort(key=lambda x: x["total"], reverse=True)
    return stats


def get_portal_counts(session: Session) -> dict:
    """Get simple project counts per source.

    Returns:
        Dict mapping source -> count
    """
    counts = (
        session.query(Project.source, func.count(Project.id))
        .group_by(Project.source)
        .all()
    )
    return {source: count for source, count in counts if source}


# --- Rejection Reasons ---


def get_rejection_for_project(session: Session, project_id: int) -> Optional[RejectionReason]:
    """Get rejection reason for a specific project.

    Args:
        session: Database session
        project_id: Project ID

    Returns:
        RejectionReason or None
    """
    return (
        session.query(RejectionReason)
        .filter(RejectionReason.project_id == project_id)
        .order_by(RejectionReason.created_at.desc())
        .first()
    )


def get_rejection_stats(session: Session) -> List[dict]:
    """Get rejection counts by reason code.

    Returns:
        List of dicts with reason_code and count
    """
    stats = (
        session.query(RejectionReason.reason_code, func.count(RejectionReason.id))
        .group_by(RejectionReason.reason_code)
        .order_by(func.count(RejectionReason.id).desc())
        .all()
    )
    return [{"reason_code": code, "count": count} for code, count in stats]


# --- Review Queue with Match Score ---


def get_pending_reviews_with_score(session: Session) -> List[Tuple[ReviewQueue, Project, Optional[float]]]:
    """Get pending reviews with match scores if available.

    Returns:
        List of (ReviewQueue, Project, match_score) tuples
    """
    reviews = get_pending_reviews(session)

    results = []
    for review, project in reviews:
        # Try to get match score from application log if exists
        app_log = (
            session.query(ApplicationLog)
            .filter(ApplicationLog.project_id == project.id)
            .first()
        )
        match_score = app_log.match_score if app_log else None
        results.append((review, project, match_score))

    return results
