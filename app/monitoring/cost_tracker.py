"""AI cost tracking for monitoring API usage.

Tracks token usage and costs per operation to stay within
the target budget of <2 EUR/month.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger("monitoring.cost_tracker")


class OperationType(Enum):
    """Types of AI operations."""

    EMBEDDING = "embedding"
    RESEARCH = "research"
    MATCHING = "matching"
    SKILL_EXTRACTION = "skill_extraction"


# Pricing per 1M tokens (as of 2024)
# GPT-4o-mini pricing
PRICING_GPT4O_MINI = {
    "input": 0.15,   # $0.15 per 1M input tokens
    "output": 0.60,  # $0.60 per 1M output tokens
}

# text-embedding-3-small pricing
PRICING_EMBEDDING = {
    "input": 0.02,   # $0.02 per 1M tokens
}

# EUR/USD exchange rate (approximate)
EUR_USD_RATE = 0.92


@dataclass
class AIUsageRecord:
    """Record of a single AI operation."""

    operation: OperationType
    timestamp: datetime
    input_tokens: int
    output_tokens: int = 0
    model: str = "gpt-4o-mini"
    cost_usd: float = 0.0

    def calculate_cost(self) -> float:
        """Calculate cost in USD based on token counts."""
        if "embedding" in self.model.lower():
            cost = (self.input_tokens / 1_000_000) * PRICING_EMBEDDING["input"]
        else:
            # GPT model
            input_cost = (self.input_tokens / 1_000_000) * PRICING_GPT4O_MINI["input"]
            output_cost = (self.output_tokens / 1_000_000) * PRICING_GPT4O_MINI["output"]
            cost = input_cost + output_cost

        self.cost_usd = cost
        return cost


@dataclass
class DailyCostSummary:
    """Cost summary for a single day."""

    date: datetime
    total_cost_usd: float = 0.0
    total_cost_eur: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    operations_count: int = 0
    by_operation: Dict[str, float] = field(default_factory=dict)


class CostTracker:
    """Tracks AI costs across operations."""

    def __init__(self, monthly_budget_eur: float = 2.0):
        """Initialize cost tracker.

        Args:
            monthly_budget_eur: Monthly budget target in EUR
        """
        self._records: List[AIUsageRecord] = []
        self._monthly_budget_eur = monthly_budget_eur

    def record(
        self,
        operation: OperationType,
        input_tokens: int,
        output_tokens: int = 0,
        model: str = "gpt-4o-mini",
    ) -> AIUsageRecord:
        """Record an AI operation.

        Args:
            operation: Type of operation
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model used

        Returns:
            AIUsageRecord with calculated cost
        """
        record = AIUsageRecord(
            operation=operation,
            timestamp=datetime.utcnow(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
        )
        record.calculate_cost()
        self._records.append(record)

        logger.debug(
            "AI usage: %s - %d in, %d out - $%.4f",
            operation.value,
            input_tokens,
            output_tokens,
            record.cost_usd,
        )

        return record

    def get_daily_summary(self, date: Optional[datetime] = None) -> DailyCostSummary:
        """Get cost summary for a specific day.

        Args:
            date: Date to summarize (default: today)

        Returns:
            DailyCostSummary
        """
        if date is None:
            date = datetime.utcnow()

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        day_records = [
            r for r in self._records
            if start_of_day <= r.timestamp < end_of_day
        ]

        summary = DailyCostSummary(date=start_of_day)

        by_operation: Dict[str, float] = {}
        for record in day_records:
            summary.total_cost_usd += record.cost_usd
            summary.total_input_tokens += record.input_tokens
            summary.total_output_tokens += record.output_tokens
            summary.operations_count += 1

            op_name = record.operation.value
            by_operation[op_name] = by_operation.get(op_name, 0) + record.cost_usd

        summary.total_cost_eur = summary.total_cost_usd * EUR_USD_RATE
        summary.by_operation = by_operation

        return summary

    def get_monthly_summary(self, year: Optional[int] = None, month: Optional[int] = None) -> Dict:
        """Get cost summary for a month.

        Args:
            year: Year (default: current)
            month: Month (default: current)

        Returns:
            Dict with monthly statistics
        """
        now = datetime.utcnow()
        year = year or now.year
        month = month or now.month

        # Get all records for the month
        month_start = datetime(year, month, 1)
        if month == 12:
            month_end = datetime(year + 1, 1, 1)
        else:
            month_end = datetime(year, month + 1, 1)

        month_records = [
            r for r in self._records
            if month_start <= r.timestamp < month_end
        ]

        total_cost_usd = sum(r.cost_usd for r in month_records)
        total_cost_eur = total_cost_usd * EUR_USD_RATE

        by_operation: Dict[str, Dict] = {}
        for record in month_records:
            op_name = record.operation.value
            if op_name not in by_operation:
                by_operation[op_name] = {
                    "count": 0,
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            by_operation[op_name]["count"] += 1
            by_operation[op_name]["cost_usd"] += record.cost_usd
            by_operation[op_name]["input_tokens"] += record.input_tokens
            by_operation[op_name]["output_tokens"] += record.output_tokens

        # Calculate days elapsed and project monthly cost
        days_elapsed = (min(now, month_end) - month_start).days + 1
        days_in_month = (month_end - month_start).days
        projected_cost_eur = (total_cost_eur / max(1, days_elapsed)) * days_in_month

        return {
            "year": year,
            "month": month,
            "days_elapsed": days_elapsed,
            "days_in_month": days_in_month,
            "total_cost_usd": total_cost_usd,
            "total_cost_eur": total_cost_eur,
            "projected_monthly_cost_eur": projected_cost_eur,
            "budget_eur": self._monthly_budget_eur,
            "budget_remaining_eur": self._monthly_budget_eur - total_cost_eur,
            "budget_utilization_percent": (total_cost_eur / self._monthly_budget_eur) * 100,
            "total_operations": len(month_records),
            "by_operation": by_operation,
        }

    def is_within_budget(self) -> bool:
        """Check if current month spending is within budget."""
        summary = self.get_monthly_summary()
        return summary["total_cost_eur"] < self._monthly_budget_eur

    def get_budget_warning(self) -> Optional[str]:
        """Get budget warning message if approaching limit.

        Returns:
            Warning message or None if within safe limits
        """
        summary = self.get_monthly_summary()
        utilization = summary["budget_utilization_percent"]

        if utilization >= 100:
            return f"BUDGET EXCEEDED: {utilization:.1f}% ({summary['total_cost_eur']:.2f}€/{self._monthly_budget_eur}€)"
        elif utilization >= 80:
            return f"Budget warning: {utilization:.1f}% used ({summary['total_cost_eur']:.2f}€/{self._monthly_budget_eur}€)"
        elif summary["projected_monthly_cost_eur"] > self._monthly_budget_eur:
            return f"Projected to exceed budget: {summary['projected_monthly_cost_eur']:.2f}€ projected"

        return None


# Global tracker instance
_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get global cost tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def record_ai_usage(
    operation: OperationType,
    input_tokens: int,
    output_tokens: int = 0,
    model: str = "gpt-4o-mini",
) -> AIUsageRecord:
    """Convenience function to record AI usage.

    Args:
        operation: Type of operation
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model used

    Returns:
        AIUsageRecord
    """
    return get_cost_tracker().record(operation, input_tokens, output_tokens, model)


def get_cost_summary() -> Dict:
    """Get current month's cost summary."""
    return get_cost_tracker().get_monthly_summary()


def estimate_monthly_cost(daily_projects: int = 50) -> Dict:
    """Estimate monthly costs based on project volume.

    Args:
        daily_projects: Expected projects per day

    Returns:
        Dict with cost estimates
    """
    # Average tokens per operation (estimated)
    TOKENS_PER_EMBEDDING = 500
    TOKENS_PER_RESEARCH = 2000
    TOKENS_PER_MATCHING = 3000

    # Assume 30% of projects go through full matching (70% filtered by keywords)
    matching_rate = 0.30

    daily_embeddings = daily_projects * TOKENS_PER_EMBEDDING
    daily_research = daily_projects * matching_rate * TOKENS_PER_RESEARCH
    daily_matching = daily_projects * matching_rate * TOKENS_PER_MATCHING

    # Calculate costs
    embedding_cost = (daily_embeddings / 1_000_000) * PRICING_EMBEDDING["input"]
    research_cost = (daily_research / 1_000_000) * (PRICING_GPT4O_MINI["input"] + PRICING_GPT4O_MINI["output"])
    matching_cost = (daily_matching / 1_000_000) * (PRICING_GPT4O_MINI["input"] + PRICING_GPT4O_MINI["output"])

    daily_total_usd = embedding_cost + research_cost + matching_cost
    monthly_total_usd = daily_total_usd * 30
    monthly_total_eur = monthly_total_usd * EUR_USD_RATE

    return {
        "daily_projects": daily_projects,
        "matching_rate": matching_rate,
        "daily_cost_usd": daily_total_usd,
        "monthly_cost_usd": monthly_total_usd,
        "monthly_cost_eur": monthly_total_eur,
        "within_budget": monthly_total_eur < 2.0,
        "breakdown": {
            "embedding_daily_usd": embedding_cost,
            "research_daily_usd": research_cost,
            "matching_daily_usd": matching_cost,
        },
    }
