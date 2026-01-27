"""Keyword analytics for effectiveness tracking.

Analyzes which keywords lead to successful applications and
suggests tier changes based on historical data.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.ai.keyword_scoring import (
    TIER_1_KEYWORDS,
    TIER_2_KEYWORDS,
    TIER_3_KEYWORDS,
    KeywordTier,
    calculate_keyword_score,
)
from app.core.logging import get_logger
from app.db.models import ApplicationLog, Project

logger = get_logger("monitoring.keyword_analytics")


@dataclass
class KeywordStats:
    """Statistics for a single keyword."""

    keyword: str
    tier: KeywordTier
    occurrences: int = 0
    applications: int = 0
    wins: int = 0
    losses: int = 0

    @property
    def win_rate(self) -> float:
        """Calculate win rate for this keyword."""
        total = self.wins + self.losses
        if total == 0:
            return 0.0
        return self.wins / total

    @property
    def application_rate(self) -> float:
        """Calculate rate of occurrences that led to applications."""
        if self.occurrences == 0:
            return 0.0
        return self.applications / self.occurrences


@dataclass
class TierChangeRecommendation:
    """Recommendation to change a keyword's tier."""

    keyword: str
    current_tier: KeywordTier
    recommended_tier: KeywordTier
    reason: str
    confidence: str  # "high", "medium", "low"
    stats: KeywordStats


def get_keyword_effectiveness(
    db: Session,
    lookback_days: int = 90,
) -> Dict:
    """Analyze which keywords lead to successful applications.

    Args:
        db: Database session
        lookback_days: Days to analyze

    Returns:
        Dict with keyword effectiveness data
    """
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    # Get all projects with outcomes
    projects = (
        db.query(Project)
        .filter(Project.scraped_at >= cutoff)
        .all()
    )

    # Get application logs with outcomes
    app_logs = (
        db.query(ApplicationLog)
        .filter(ApplicationLog.applied_at >= cutoff)
        .filter(ApplicationLog.outcome.isnot(None))
        .all()
    )

    # Build project outcome map
    project_outcomes: Dict[int, str] = {}
    for log in app_logs:
        project_outcomes[log.project_id] = log.outcome

    # Analyze keywords
    keyword_stats: Dict[str, KeywordStats] = {}

    # Initialize stats for all known keywords
    for kw in TIER_1_KEYWORDS:
        keyword_stats[kw] = KeywordStats(keyword=kw, tier=KeywordTier.TIER_1)
    for kw in TIER_2_KEYWORDS:
        keyword_stats[kw] = KeywordStats(keyword=kw, tier=KeywordTier.TIER_2)
    for kw in TIER_3_KEYWORDS:
        keyword_stats[kw] = KeywordStats(keyword=kw, tier=KeywordTier.TIER_3)

    # Process each project
    for project in projects:
        score_result = calculate_keyword_score(
            title=project.title,
            description=project.description or "",
            pdf_text=project.pdf_text or "",
        )

        all_found = (
            score_result.tier_1_keywords +
            score_result.tier_2_keywords +
            score_result.tier_3_keywords
        )

        for kw in all_found:
            if kw not in keyword_stats:
                # Dynamic keyword not in predefined lists
                keyword_stats[kw] = KeywordStats(keyword=kw, tier=KeywordTier.TIER_3)

            keyword_stats[kw].occurrences += 1

            # Check if this project had an application
            if project.status == "applied":
                keyword_stats[kw].applications += 1

                # Check outcome if available
                outcome = project_outcomes.get(project.id)
                if outcome == "won":
                    keyword_stats[kw].wins += 1
                elif outcome in ("lost", "rejected"):
                    keyword_stats[kw].losses += 1

    # Calculate most and least effective keywords
    keywords_with_data = [s for s in keyword_stats.values() if s.occurrences >= 5]

    most_effective = sorted(
        keywords_with_data,
        key=lambda s: (s.win_rate, s.application_rate),
        reverse=True,
    )[:10]

    least_effective = sorted(
        keywords_with_data,
        key=lambda s: (s.application_rate, s.win_rate),
    )[:10]

    # Find best combinations
    combo_stats = _analyze_keyword_combinations(projects, project_outcomes)

    return {
        "lookback_days": lookback_days,
        "total_projects": len(projects),
        "projects_with_outcomes": len(project_outcomes),
        "most_effective_keywords": [
            {
                "keyword": s.keyword,
                "tier": s.tier.value,
                "occurrences": s.occurrences,
                "applications": s.applications,
                "wins": s.wins,
                "win_rate": s.win_rate,
                "application_rate": s.application_rate,
            }
            for s in most_effective
        ],
        "least_effective_keywords": [
            {
                "keyword": s.keyword,
                "tier": s.tier.value,
                "occurrences": s.occurrences,
                "applications": s.applications,
                "win_rate": s.win_rate,
                "application_rate": s.application_rate,
            }
            for s in least_effective
        ],
        "best_combinations": combo_stats[:5],
        "keyword_count": len(keyword_stats),
    }


def _analyze_keyword_combinations(
    projects: List[Project],
    project_outcomes: Dict[int, str],
) -> List[Dict]:
    """Analyze which keyword combinations have highest success rates."""
    combo_stats: Dict[Tuple[str, ...], Dict] = defaultdict(
        lambda: {"occurrences": 0, "wins": 0, "losses": 0}
    )

    for project in projects:
        score_result = calculate_keyword_score(
            title=project.title,
            description=project.description or "",
            pdf_text=project.pdf_text or "",
        )

        # Focus on Tier 1 + Tier 2 combinations
        key_keywords = sorted(
            score_result.tier_1_keywords[:2] + score_result.tier_2_keywords[:2]
        )

        if len(key_keywords) >= 2:
            combo = tuple(key_keywords[:3])  # Max 3 keywords
            combo_stats[combo]["occurrences"] += 1

            outcome = project_outcomes.get(project.id)
            if outcome == "won":
                combo_stats[combo]["wins"] += 1
            elif outcome in ("lost", "rejected"):
                combo_stats[combo]["losses"] += 1

    # Calculate win rates and sort
    results = []
    for combo, stats in combo_stats.items():
        total = stats["wins"] + stats["losses"]
        if stats["occurrences"] >= 3:  # Minimum sample size
            results.append({
                "keywords": list(combo),
                "occurrences": stats["occurrences"],
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": stats["wins"] / max(1, total),
            })

    return sorted(results, key=lambda x: (x["win_rate"], x["occurrences"]), reverse=True)


def get_keyword_distribution(db: Session, lookback_days: int = 30) -> Dict:
    """Get distribution of keyword scores across projects.

    Args:
        db: Database session
        lookback_days: Days to analyze

    Returns:
        Dict with score distribution data
    """
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    projects = (
        db.query(Project)
        .filter(Project.scraped_at >= cutoff)
        .all()
    )

    # Score buckets
    buckets = {
        "0-9": 0,
        "10-19": 0,
        "20-29": 0,
        "30-40": 0,
    }

    # Confidence distribution
    confidence_counts = {"high": 0, "medium": 0, "low": 0}

    # Status distribution by score range
    status_by_score: Dict[str, Dict[str, int]] = {
        "0-9": {"applied": 0, "rejected": 0, "review": 0, "new": 0},
        "10-19": {"applied": 0, "rejected": 0, "review": 0, "new": 0},
        "20-29": {"applied": 0, "rejected": 0, "review": 0, "new": 0},
        "30-40": {"applied": 0, "rejected": 0, "review": 0, "new": 0},
    }

    for project in projects:
        score_result = calculate_keyword_score(
            title=project.title,
            description=project.description or "",
            pdf_text=project.pdf_text or "",
        )

        # Determine bucket
        score = score_result.total_score
        if score < 10:
            bucket = "0-9"
        elif score < 20:
            bucket = "10-19"
        elif score < 30:
            bucket = "20-29"
        else:
            bucket = "30-40"

        buckets[bucket] += 1
        confidence_counts[score_result.confidence] += 1

        status = project.status or "new"
        if status in status_by_score[bucket]:
            status_by_score[bucket][status] += 1

    total = len(projects) or 1

    return {
        "lookback_days": lookback_days,
        "total_projects": len(projects),
        "score_distribution": {
            bucket: {
                "count": count,
                "percentage": (count / total) * 100,
            }
            for bucket, count in buckets.items()
        },
        "confidence_distribution": {
            level: {
                "count": count,
                "percentage": (count / total) * 100,
            }
            for level, count in confidence_counts.items()
        },
        "status_by_score_range": status_by_score,
    }


def suggest_tier_changes(
    db: Session,
    min_occurrences: int = 10,
    lookback_days: int = 90,
) -> List[TierChangeRecommendation]:
    """Suggest keyword tier changes based on effectiveness.

    Args:
        db: Database session
        min_occurrences: Minimum occurrences to consider
        lookback_days: Days to analyze

    Returns:
        List of tier change recommendations
    """
    effectiveness = get_keyword_effectiveness(db, lookback_days)

    recommendations = []

    # Process most effective keywords
    for kw_data in effectiveness["most_effective_keywords"]:
        current_tier = KeywordTier(kw_data["tier"])
        stats = KeywordStats(
            keyword=kw_data["keyword"],
            tier=current_tier,
            occurrences=kw_data["occurrences"],
            applications=kw_data["applications"],
            wins=kw_data["wins"],
        )

        # High performing Tier 2/3 -> recommend Tier 1
        if current_tier != KeywordTier.TIER_1 and kw_data["win_rate"] >= 0.5:
            if kw_data["occurrences"] >= min_occurrences:
                recommendations.append(TierChangeRecommendation(
                    keyword=kw_data["keyword"],
                    current_tier=current_tier,
                    recommended_tier=KeywordTier.TIER_1,
                    reason=f"High win rate ({kw_data['win_rate']:.0%}) with {kw_data['occurrences']} occurrences",
                    confidence="high" if kw_data["occurrences"] >= 20 else "medium",
                    stats=stats,
                ))

    # Process least effective keywords
    for kw_data in effectiveness["least_effective_keywords"]:
        current_tier = KeywordTier(kw_data["tier"])
        stats = KeywordStats(
            keyword=kw_data["keyword"],
            tier=current_tier,
            occurrences=kw_data["occurrences"],
            applications=kw_data["applications"],
        )

        # Low performing Tier 1 -> recommend Tier 2
        if current_tier == KeywordTier.TIER_1 and kw_data["application_rate"] < 0.3:
            if kw_data["occurrences"] >= min_occurrences:
                recommendations.append(TierChangeRecommendation(
                    keyword=kw_data["keyword"],
                    current_tier=current_tier,
                    recommended_tier=KeywordTier.TIER_2,
                    reason=f"Low application rate ({kw_data['application_rate']:.0%}) despite Tier-1 status",
                    confidence="medium",
                    stats=stats,
                ))

        # Very low performing -> consider removal
        if kw_data["application_rate"] < 0.1 and kw_data["occurrences"] >= min_occurrences:
            recommendations.append(TierChangeRecommendation(
                keyword=kw_data["keyword"],
                current_tier=current_tier,
                recommended_tier=KeywordTier.TIER_3,
                reason=f"Very low application rate ({kw_data['application_rate']:.0%})",
                confidence="low",
                stats=stats,
            ))

    return recommendations
