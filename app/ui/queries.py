"""Database queries for the Streamlit UI."""

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.db.models import (
    ApplicationLog,
    Client,
    Project,
    RejectionReason,
    ReviewQueue,
    TeamMember,
    TenderDecision,
    TenderLot,
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
    project_type: Optional[str] = None,
    days_back: int = 30,
    limit: int = 100,
) -> List[Project]:
    """Get filtered projects.

    Args:
        session: Database session
        status: Filter by status (optional)
        source: Filter by source portal (optional)
        search_text: Search in title/description (optional)
        project_type: Filter by project type (freelance/tender) (optional)
        days_back: Only show projects from last N days
        limit: Maximum number of results

    Returns:
        List of Project objects
    """
    query = session.query(Project)

    # Date filter
    date_threshold = datetime.utcnow() - timedelta(days=days_back)
    query = query.filter(Project.scraped_at >= date_threshold)

    # Project type filter
    if project_type and project_type != "Alle":
        query = query.filter(Project.project_type == project_type)

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


# ============================================================
# Tender-specific Queries
# ============================================================


def get_active_tenders_count(session: Session) -> int:
    """Get count of active tender applications.

    Returns:
        Number of tenders in applied or review status
    """
    return (
        session.query(func.count(Project.id))
        .filter(
            Project.project_type == "tender",
            Project.status.in_(["applied", "review"]),
        )
        .scalar()
    ) or 0


def get_high_priority_tenders(session: Session, limit: int = 5) -> List[Project]:
    """Get high priority tenders for dashboard.

    Args:
        session: Database session
        limit: Maximum number of results

    Returns:
        List of high-scoring tender projects
    """
    return (
        session.query(Project)
        .filter(
            Project.project_type == "tender",
            Project.score >= 70,
            Project.status == "review",
        )
        .order_by(Project.score.desc())
        .limit(limit)
        .all()
    )


def get_tenders(
    session: Session,
    score_min: int = 0,
    procedure_type: Optional[str] = None,
    eligibility: Optional[str] = None,
    days_until_deadline: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Project]:
    """Get filtered tenders.

    Args:
        session: Database session
        score_min: Minimum score filter
        procedure_type: Filter by procedure type
        eligibility: Filter by eligibility status
        days_until_deadline: Filter by maximum days until deadline
        status: Filter by status
        limit: Maximum number of results

    Returns:
        List of Project objects
    """
    query = session.query(Project).filter(Project.project_type == "tender")

    if score_min > 0:
        query = query.filter(Project.score >= score_min)

    if procedure_type and procedure_type != "Alle":
        query = query.filter(Project.procedure_type == procedure_type)

    if eligibility and eligibility != "Alle":
        query = query.filter(Project.eligibility_check == eligibility)

    if days_until_deadline:
        deadline_threshold = datetime.utcnow() + timedelta(days=days_until_deadline)
        query = query.filter(Project.tender_deadline <= deadline_threshold)

    if status and status != "Alle":
        query = query.filter(Project.status == status)

    return query.order_by(Project.score.desc()).limit(limit).all()


def get_lots_for_project(session: Session, project_id: int) -> List[TenderLot]:
    """Get all lots for a tender project.

    Args:
        session: Database session
        project_id: Project ID

    Returns:
        List of TenderLot objects
    """
    return (
        session.query(TenderLot)
        .filter(TenderLot.project_id == project_id)
        .order_by(TenderLot.lot_number)
        .all()
    )


def get_tender_decision(session: Session, project_id: int) -> Optional[TenderDecision]:
    """Get tender decision for a project.

    Args:
        session: Database session
        project_id: Project ID

    Returns:
        TenderDecision or None
    """
    return (
        session.query(TenderDecision)
        .filter(TenderDecision.project_id == project_id)
        .first()
    )


def save_tender_decision(
    session: Session,
    project_id: int,
    manual_decision: str,
    decision_reason: Optional[str] = None,
    decision_by: Optional[str] = None,
) -> TenderDecision:
    """Save or update a tender decision.

    Args:
        session: Database session
        project_id: Project ID
        manual_decision: Decision value (apply, skip, partner_needed)
        decision_reason: Optional reason text
        decision_by: Optional user identifier

    Returns:
        TenderDecision instance
    """
    decision = (
        session.query(TenderDecision)
        .filter(TenderDecision.project_id == project_id)
        .first()
    )

    if decision:
        decision.manual_decision = manual_decision
        decision.decision_reason = decision_reason
        decision.decision_by = decision_by
        decision.decision_at = datetime.utcnow()
    else:
        decision = TenderDecision(
            project_id=project_id,
            manual_decision=manual_decision,
            decision_reason=decision_reason,
            decision_by=decision_by,
            decision_at=datetime.utcnow(),
        )
        session.add(decision)

    # Update project status based on decision
    project = session.query(Project).filter(Project.id == project_id).first()
    if project:
        if manual_decision == "apply":
            project.status = "applied"
        elif manual_decision == "skip":
            project.status = "rejected"
        # partner_needed and watch keep current status

    session.commit()
    return decision


def add_to_watchlist(session: Session, project_id: int) -> bool:
    """Add a project to the watchlist.

    Args:
        session: Database session
        project_id: Project ID

    Returns:
        True if successful
    """
    project = session.query(Project).filter(Project.id == project_id).first()
    if project:
        project.status = "watching"
        session.commit()
        return True
    return False


def get_tender_score_distribution(session: Session, days_back: int = 30) -> dict:
    """Get score distribution for tenders.

    Args:
        session: Database session
        days_back: Number of days to look back

    Returns:
        Dictionary with score ranges and counts
    """
    date_threshold = datetime.utcnow() - timedelta(days=days_back)

    scores = (
        session.query(Project.score)
        .filter(
            Project.project_type == "tender",
            Project.score.isnot(None),
            Project.scraped_at >= date_threshold,
        )
        .all()
    )

    distribution = {"0-30": 0, "31-50": 0, "51-70": 0, "71-100": 0}

    for (score,) in scores:
        if score <= 30:
            distribution["0-30"] += 1
        elif score <= 50:
            distribution["31-50"] += 1
        elif score <= 70:
            distribution["51-70"] += 1
        else:
            distribution["71-100"] += 1

    return distribution


def get_procedure_types(session: Session) -> List[str]:
    """Get all unique procedure types.

    Args:
        session: Database session

    Returns:
        List of procedure type values
    """
    types = (
        session.query(Project.procedure_type)
        .filter(
            Project.project_type == "tender",
            Project.procedure_type.isnot(None),
        )
        .distinct()
        .all()
    )
    return [t[0] for t in types if t[0]]


# ============================================================
# Client Queries
# ============================================================


def get_clients(
    session: Session,
    sector: Optional[str] = None,
    limit: int = 100,
) -> List[Client]:
    """Get filtered clients.

    Args:
        session: Database session
        sector: Filter by sector
        limit: Maximum number of results

    Returns:
        List of Client objects
    """
    query = session.query(Client)

    if sector and sector != "Alle":
        query = query.filter(Client.sector == sector)

    return query.order_by(Client.tenders_seen.desc()).limit(limit).all()


def get_top_clients(session: Session, limit: int = 3) -> List[Client]:
    """Get top clients by win rate.

    Args:
        session: Database session
        limit: Maximum number of results

    Returns:
        List of Client objects with best win rates
    """
    return (
        session.query(Client)
        .filter(
            Client.tenders_applied > 0,
            Client.win_rate.isnot(None),
        )
        .order_by(Client.win_rate.desc())
        .limit(limit)
        .all()
    )


def get_client_for_project(session: Session, project: Project) -> Optional[Client]:
    """Get client for a project.

    Args:
        session: Database session
        project: Project instance

    Returns:
        Client or None
    """
    if not project.client_name:
        return None

    from app.sourcing.client_db import find_client

    return find_client(session, project.client_name)


def update_client(
    session: Session,
    client_id: int,
    payment_rating: Optional[int] = None,
    communication_rating: Optional[int] = None,
    notes: Optional[str] = None,
) -> bool:
    """Update client information.

    Args:
        session: Database session
        client_id: Client ID
        payment_rating: Optional payment rating (1-5)
        communication_rating: Optional communication rating (1-5)
        notes: Optional notes

    Returns:
        True if successful
    """
    client = session.query(Client).filter(Client.id == client_id).first()
    if not client:
        return False

    if payment_rating is not None:
        client.payment_rating = payment_rating
    if communication_rating is not None:
        client.communication_rating = communication_rating
    if notes is not None:
        client.notes = notes

    client.updated_at = datetime.utcnow()
    session.commit()
    return True


def get_client_stats(session: Session) -> dict:
    """Get overall client statistics.

    Args:
        session: Database session

    Returns:
        Dictionary with statistics
    """
    total_clients = session.query(func.count(Client.id)).scalar() or 0

    active_clients = (
        session.query(func.count(Client.id))
        .filter(Client.tenders_applied > 0)
        .scalar()
    ) or 0

    total_seen = (
        session.query(func.sum(Client.tenders_seen)).scalar()
    ) or 0

    total_applied = (
        session.query(func.sum(Client.tenders_applied)).scalar()
    ) or 0

    total_won = (
        session.query(func.sum(Client.tenders_won)).scalar()
    ) or 0

    overall_win_rate = (total_won / total_applied) if total_applied > 0 else 0

    return {
        "total_clients": total_clients,
        "active_clients": active_clients,
        "total_tenders_seen": total_seen,
        "total_applications": total_applied,
        "total_won": total_won,
        "overall_win_rate": overall_win_rate,
    }


# ============================================================
# Export Functions
# ============================================================


def get_tenders_as_dataframe(
    session: Session,
    score_min: int = 0,
) -> pd.DataFrame:
    """Export tenders as pandas DataFrame.

    Args:
        session: Database session
        score_min: Minimum score filter

    Returns:
        DataFrame with tender data
    """
    tenders = get_tenders(session, score_min=score_min)

    data = []
    for t in tenders:
        data.append({
            "Titel": t.title,
            "Auftraggeber": t.client_name,
            "Score": t.score,
            "Budget_Min": t.budget_min,
            "Budget_Max": t.budget_max,
            "Vergabeart": t.procedure_type,
            "Eignung": t.eligibility_check,
            "Deadline": t.tender_deadline,
            "Status": t.status,
            "Quelle": t.source,
            "URL": t.url,
        })

    return pd.DataFrame(data)


def generate_weekly_report(session: Session) -> str:
    """Generate a weekly tender report.

    Args:
        session: Database session

    Returns:
        Markdown formatted report
    """
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # Get statistics
    new_tenders = (
        session.query(func.count(Project.id))
        .filter(
            Project.project_type == "tender",
            Project.scraped_at >= week_ago,
        )
        .scalar()
    ) or 0

    high_priority = (
        session.query(func.count(Project.id))
        .filter(
            Project.project_type == "tender",
            Project.scraped_at >= week_ago,
            Project.score >= 70,
        )
        .scalar()
    ) or 0

    decisions_made = (
        session.query(func.count(TenderDecision.id))
        .filter(TenderDecision.decision_at >= week_ago)
        .scalar()
    ) or 0

    # Build report
    report = f"""# Wochenreport Ausschreibungen

**Zeitraum:** {week_ago.strftime('%d.%m.%Y')} - {now.strftime('%d.%m.%Y')}

## Zusammenfassung

- **Neue Ausschreibungen:** {new_tenders}
- **Hochpriorisiert (Score >= 70):** {high_priority}
- **Entscheidungen getroffen:** {decisions_made}

## Top 5 Ausschreibungen

"""

    top_tenders = get_high_priority_tenders(session, limit=5)
    for i, t in enumerate(top_tenders, 1):
        deadline_str = t.tender_deadline.strftime('%d.%m.%Y') if t.tender_deadline else '-'
        report += f"{i}. **{t.title[:60]}**\n"
        report += f"   - Score: {t.score} | Deadline: {deadline_str}\n"
        report += f"   - Auftraggeber: {t.client_name or '-'}\n\n"

    return report
