"""Scraper metrics tracking and analysis.

Tracks success rates, error counts, and performance metrics for each
portal scraper to identify issues and optimize scraping operations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Project

logger = get_logger("monitoring.scraper_metrics")


class ErrorCategory(Enum):
    """Categories of scraper errors."""

    NETWORK = "network"  # Connection errors, timeouts
    PARSING = "parsing"  # HTML/JSON parsing failures
    RATE_LIMIT = "rate_limit"  # 429 errors, captchas
    AUTH = "auth"  # Authentication failures
    BLOCKED = "blocked"  # IP blocked, bot detection
    OTHER = "other"  # Uncategorized errors


@dataclass
class ScraperRunStats:
    """Statistics for a single scraper run."""

    portal: str
    start_time: datetime
    end_time: Optional[datetime] = None
    projects_found: int = 0
    new_projects: int = 0
    duplicates: int = 0
    errors: List[Dict] = field(default_factory=list)
    status: str = "running"  # running, success, error

    @property
    def duration_seconds(self) -> float:
        """Get run duration in seconds."""
        if self.end_time is None:
            return (datetime.utcnow() - self.start_time).total_seconds()
        return (self.end_time - self.start_time).total_seconds()

    @property
    def error_count(self) -> int:
        """Get total error count."""
        return len(self.errors)

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 - 1.0)."""
        if self.projects_found == 0:
            return 0.0 if self.errors else 1.0
        return 1.0 - (self.error_count / max(self.projects_found, 1))

    def add_error(self, category: ErrorCategory, message: str, details: Optional[Dict] = None) -> None:
        """Record an error during scraping."""
        self.errors.append({
            "category": category.value,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        })

    def complete(self, status: str = "success") -> None:
        """Mark the run as complete."""
        self.end_time = datetime.utcnow()
        self.status = status


class ScraperMetrics:
    """Tracks and aggregates scraper metrics across runs."""

    def __init__(self):
        self._runs: List[ScraperRunStats] = []
        self._current_runs: Dict[str, ScraperRunStats] = {}

    def start_run(self, portal: str) -> ScraperRunStats:
        """Start tracking a new scraper run.

        Args:
            portal: Portal name

        Returns:
            ScraperRunStats for this run
        """
        stats = ScraperRunStats(
            portal=portal,
            start_time=datetime.utcnow(),
        )
        self._current_runs[portal] = stats
        return stats

    def complete_run(
        self,
        portal: str,
        projects_found: int,
        new_projects: int,
        status: str = "success",
    ) -> Optional[ScraperRunStats]:
        """Complete a scraper run and record stats.

        Args:
            portal: Portal name
            projects_found: Total projects found
            new_projects: New projects after deduplication
            status: Run status

        Returns:
            Completed ScraperRunStats or None if no run was started
        """
        stats = self._current_runs.pop(portal, None)
        if stats is None:
            logger.warning("No run started for portal: %s", portal)
            return None

        stats.projects_found = projects_found
        stats.new_projects = new_projects
        stats.duplicates = projects_found - new_projects
        stats.complete(status)

        self._runs.append(stats)

        logger.info(
            "Scraper run completed: %s - %d projects, %d new, %d errors, %.1fs",
            portal,
            projects_found,
            new_projects,
            stats.error_count,
            stats.duration_seconds,
        )

        return stats

    def get_portal_stats(self, portal: str, lookback_days: int = 30) -> Dict:
        """Get aggregated statistics for a portal.

        Args:
            portal: Portal name
            lookback_days: Days to aggregate

        Returns:
            Dict with aggregated stats
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        portal_runs = [
            r for r in self._runs
            if r.portal == portal and r.start_time >= cutoff
        ]

        if not portal_runs:
            return {
                "portal": portal,
                "runs": 0,
                "total_projects": 0,
                "avg_projects_per_run": 0,
                "avg_success_rate": 0,
                "total_errors": 0,
                "error_breakdown": {},
            }

        total_projects = sum(r.projects_found for r in portal_runs)
        total_errors = sum(r.error_count for r in portal_runs)

        # Count errors by category
        error_breakdown: Dict[str, int] = {}
        for run in portal_runs:
            for error in run.errors:
                cat = error.get("category", "other")
                error_breakdown[cat] = error_breakdown.get(cat, 0) + 1

        return {
            "portal": portal,
            "runs": len(portal_runs),
            "total_projects": total_projects,
            "avg_projects_per_run": total_projects / len(portal_runs),
            "avg_success_rate": sum(r.success_rate for r in portal_runs) / len(portal_runs),
            "total_errors": total_errors,
            "error_breakdown": error_breakdown,
            "avg_duration_seconds": sum(r.duration_seconds for r in portal_runs) / len(portal_runs),
        }

    def get_all_portal_stats(self, lookback_days: int = 30) -> List[Dict]:
        """Get statistics for all portals.

        Args:
            lookback_days: Days to aggregate

        Returns:
            List of portal stat dicts
        """
        portals = set(r.portal for r in self._runs)
        return [self.get_portal_stats(p, lookback_days) for p in sorted(portals)]


# Global metrics instance
_metrics: Optional[ScraperMetrics] = None


def get_scraper_metrics() -> ScraperMetrics:
    """Get global scraper metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = ScraperMetrics()
    return _metrics


def record_scraper_run(
    portal: str,
    projects_found: int,
    new_projects: int,
    errors: Optional[List[Dict]] = None,
    duration_seconds: Optional[float] = None,
) -> ScraperRunStats:
    """Convenience function to record a scraper run.

    Args:
        portal: Portal name
        projects_found: Total projects found
        new_projects: New projects after deduplication
        errors: List of errors (optional)
        duration_seconds: Run duration (optional)

    Returns:
        ScraperRunStats for the run
    """
    metrics = get_scraper_metrics()

    stats = ScraperRunStats(
        portal=portal,
        start_time=datetime.utcnow() - timedelta(seconds=duration_seconds or 0),
        end_time=datetime.utcnow(),
        projects_found=projects_found,
        new_projects=new_projects,
        duplicates=projects_found - new_projects,
        status="success" if not errors else "error",
    )

    if errors:
        stats.errors = errors

    metrics._runs.append(stats)
    return stats


def get_scraper_statistics(db: Session, lookback_days: int = 30) -> Dict:
    """Get comprehensive scraper statistics from database.

    Args:
        db: Database session
        lookback_days: Days to analyze

    Returns:
        Dict with statistics
    """
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    # Get project counts per source
    projects = db.query(Project).filter(Project.scraped_at >= cutoff).all()

    source_counts: Dict[str, Dict] = {}
    for p in projects:
        if p.source not in source_counts:
            source_counts[p.source] = {
                "total": 0,
                "new": 0,
                "applied": 0,
                "rejected": 0,
                "review": 0,
            }
        source_counts[p.source]["total"] += 1
        if p.status == "applied":
            source_counts[p.source]["applied"] += 1
        elif p.status == "rejected":
            source_counts[p.source]["rejected"] += 1
        elif p.status == "review":
            source_counts[p.source]["review"] += 1
        else:
            source_counts[p.source]["new"] += 1

    # Calculate daily averages
    days_with_data = max(1, (datetime.utcnow() - cutoff).days)

    return {
        "lookback_days": lookback_days,
        "total_projects": len(projects),
        "projects_per_day": len(projects) / days_with_data,
        "sources": source_counts,
        "in_memory_metrics": get_scraper_metrics().get_all_portal_stats(lookback_days),
    }
