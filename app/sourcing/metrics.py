"""Scraper quality metrics tracking.

Tracks which sources deliver relevant projects and calculates
relevance rates for data-driven optimization of scraping efforts.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Project, ScraperRun

logger = get_logger("sourcing.metrics")

# Score threshold for "relevant" projects
RELEVANCE_SCORE_THRESHOLD = 50


@dataclass
class ScraperMetrics:
    """Quality metrics for a single scraper source."""

    source: str
    projects_scraped: int = 0
    projects_relevant: int = 0
    relevance_rate: float = 0.0
    avg_score: float = 0.0
    last_successful_run: Optional[datetime] = None
    total_runs: int = 0
    success_rate: float = 0.0
    avg_projects_per_run: float = 0.0
    errors_last_7_days: int = 0

    def __repr__(self) -> str:
        return (
            f"ScraperMetrics(source={self.source}, "
            f"relevance={self.relevance_rate:.0%}, "
            f"avg_score={self.avg_score:.0f})"
        )


def get_scraper_metrics(
    db: Session,
    days_back: int = 30,
) -> List[ScraperMetrics]:
    """Calculate quality metrics for all scrapers.

    Args:
        db: Database session
        days_back: Days to look back for statistics

    Returns:
        List of ScraperMetrics sorted by relevance rate
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    metrics_by_source: Dict[str, ScraperMetrics] = {}

    # Get all unique sources
    sources = db.query(Project.source).distinct().all()
    sources = [s[0] for s in sources]

    for source in sources:
        metrics = ScraperMetrics(source=source)

        # Count projects
        metrics.projects_scraped = db.query(Project).filter(
            Project.source == source,
            Project.scraped_at >= cutoff_date,
        ).count()

        # Count relevant projects (score >= threshold)
        metrics.projects_relevant = db.query(Project).filter(
            Project.source == source,
            Project.scraped_at >= cutoff_date,
            Project.score >= RELEVANCE_SCORE_THRESHOLD,
        ).count()

        # Calculate relevance rate
        if metrics.projects_scraped > 0:
            metrics.relevance_rate = metrics.projects_relevant / metrics.projects_scraped
        else:
            metrics.relevance_rate = 0.0

        # Calculate average score
        avg_score_result = db.query(func.avg(Project.score)).filter(
            Project.source == source,
            Project.scraped_at >= cutoff_date,
            Project.score.isnot(None),
        ).scalar()
        metrics.avg_score = float(avg_score_result) if avg_score_result else 0.0

        # Get scraper run statistics
        runs = db.query(ScraperRun).filter(
            ScraperRun.portal == source,
            ScraperRun.started_at >= cutoff_date,
        ).all()

        metrics.total_runs = len(runs)

        if runs:
            successful_runs = [r for r in runs if r.status == "success"]
            metrics.success_rate = len(successful_runs) / len(runs)

            # Last successful run
            for run in sorted(runs, key=lambda r: r.started_at, reverse=True):
                if run.status == "success":
                    metrics.last_successful_run = run.completed_at
                    break

            # Average projects per run
            total_found = sum(r.projects_found or 0 for r in successful_runs)
            if successful_runs:
                metrics.avg_projects_per_run = total_found / len(successful_runs)

        # Count errors in last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        metrics.errors_last_7_days = db.query(ScraperRun).filter(
            ScraperRun.portal == source,
            ScraperRun.started_at >= week_ago,
            ScraperRun.status == "error",
        ).count()

        metrics_by_source[source] = metrics

    # Sort by relevance rate descending
    sorted_metrics = sorted(
        metrics_by_source.values(),
        key=lambda m: (m.relevance_rate, m.avg_score),
        reverse=True,
    )

    return sorted_metrics


def get_source_metrics(
    db: Session,
    source: str,
    days_back: int = 30,
) -> ScraperMetrics:
    """Get metrics for a specific source.

    Args:
        db: Database session
        source: Source name
        days_back: Days to look back

    Returns:
        ScraperMetrics for the source
    """
    all_metrics = get_scraper_metrics(db, days_back)
    for m in all_metrics:
        if m.source == source:
            return m
    return ScraperMetrics(source=source)


def log_metrics_summary(db: Session, days_back: int = 30) -> None:
    """Log a summary of scraper quality metrics.

    Args:
        db: Database session
        days_back: Days to look back
    """
    metrics = get_scraper_metrics(db, days_back)

    logger.info("=" * 60)
    logger.info("SCRAPER QUALITY METRICS (last %d days)", days_back)
    logger.info("=" * 60)
    logger.info(
        "%-20s %8s %8s %10s %8s",
        "Source", "Scraped", "Relevant", "Rate", "Avg Score",
    )
    logger.info("-" * 60)

    for m in metrics:
        logger.info(
            "%-20s %8d %8d %9.0f%% %8.0f",
            m.source[:20],
            m.projects_scraped,
            m.projects_relevant,
            m.relevance_rate * 100,
            m.avg_score,
        )

    logger.info("=" * 60)


def update_metrics_after_scoring(
    db: Session,
    source: str,
    projects_scored: int,
    projects_relevant: int,
    avg_score: float,
) -> None:
    """Update metrics after scoring a batch of projects.

    This can be called from the orchestrator after scoring
    to maintain running statistics.

    Args:
        db: Database session
        source: Source name
        projects_scored: Number of projects scored
        projects_relevant: Number with score >= threshold
        avg_score: Average score of batch
    """
    logger.debug(
        "Metrics update for %s: %d scored, %d relevant (%.0f%%), avg score %.0f",
        source,
        projects_scored,
        projects_relevant,
        (projects_relevant / projects_scored * 100) if projects_scored > 0 else 0,
        avg_score,
    )


def get_recommended_sources(
    db: Session,
    min_relevance_rate: float = 0.1,
    min_projects: int = 10,
) -> List[str]:
    """Get list of sources worth scraping based on metrics.

    Args:
        db: Database session
        min_relevance_rate: Minimum relevance rate to include
        min_projects: Minimum projects needed for reliable rate

    Returns:
        List of source names sorted by effectiveness
    """
    metrics = get_scraper_metrics(db)

    recommended = []
    for m in metrics:
        # Include if either:
        # 1. Good relevance rate with enough data
        # 2. Too few projects to judge (give it a chance)
        if m.projects_scraped < min_projects:
            recommended.append(m.source)
        elif m.relevance_rate >= min_relevance_rate:
            recommended.append(m.source)

    return recommended


def get_problematic_sources(
    db: Session,
    max_relevance_rate: float = 0.05,
    max_success_rate: float = 0.5,
    min_projects: int = 20,
) -> List[ScraperMetrics]:
    """Get sources with quality problems for review.

    Args:
        db: Database session
        max_relevance_rate: Below this = low relevance problem
        max_success_rate: Below this = reliability problem
        min_projects: Minimum projects to make judgment

    Returns:
        List of problematic ScraperMetrics
    """
    metrics = get_scraper_metrics(db)

    problematic = []
    for m in metrics:
        if m.projects_scraped < min_projects:
            continue  # Not enough data

        is_problematic = False
        reasons = []

        if m.relevance_rate < max_relevance_rate:
            is_problematic = True
            reasons.append(f"low relevance ({m.relevance_rate:.0%})")

        if m.success_rate < max_success_rate and m.total_runs >= 5:
            is_problematic = True
            reasons.append(f"low success rate ({m.success_rate:.0%})")

        if m.errors_last_7_days >= 3:
            is_problematic = True
            reasons.append(f"frequent errors ({m.errors_last_7_days} in 7 days)")

        if is_problematic:
            logger.warning(
                "Source %s has issues: %s",
                m.source,
                ", ".join(reasons),
            )
            problematic.append(m)

    return problematic
