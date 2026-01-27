"""Monitoring module for scraper metrics, cost tracking, and analytics."""

from app.monitoring.scraper_metrics import (
    ScraperMetrics,
    ScraperRunStats,
    record_scraper_run,
    get_scraper_statistics,
)
from app.monitoring.cost_tracker import (
    CostTracker,
    record_ai_usage,
    get_cost_summary,
    estimate_monthly_cost,
)
from app.monitoring.keyword_analytics import (
    get_keyword_effectiveness,
    get_keyword_distribution,
    suggest_tier_changes,
)

__all__ = [
    # Scraper metrics
    "ScraperMetrics",
    "ScraperRunStats",
    "record_scraper_run",
    "get_scraper_statistics",
    # Cost tracking
    "CostTracker",
    "record_ai_usage",
    "get_cost_summary",
    "estimate_monthly_cost",
    # Keyword analytics
    "get_keyword_effectiveness",
    "get_keyword_distribution",
    "suggest_tier_changes",
]
