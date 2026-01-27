"""AI Cost Tracking - Erfasst Token-Verbrauch und Kosten."""

from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import AIUsage
from app.core.logging import get_logger

logger = get_logger("ai.cost_tracking")

# Preise pro 1M Tokens (Stand: Januar 2025)
MODEL_PRICES = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def log_ai_usage(
    db: Session,
    operation: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    project_id: Optional[int] = None,
) -> float:
    """Erfasse AI-Nutzung in der Datenbank.

    Args:
        db: SQLAlchemy Session
        operation: Art der Operation (embedding, research, matching)
        model: Verwendetes Modell (gpt-4o-mini, text-embedding-3-small, etc.)
        input_tokens: Anzahl Input-Tokens
        output_tokens: Anzahl Output-Tokens
        project_id: Optional zugehörige Projekt-ID

    Returns:
        Berechnete Kosten in USD
    """
    prices = MODEL_PRICES.get(model, {"input": 0.15, "output": 0.60})
    cost_usd = (
        input_tokens * prices["input"] + output_tokens * prices["output"]
    ) / 1_000_000

    usage = AIUsage(
        operation=operation,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        project_id=project_id,
    )
    db.add(usage)

    logger.debug(
        "AI-Usage: %s | %s | %d+%d tokens | $%.6f",
        operation,
        model,
        input_tokens,
        output_tokens,
        cost_usd,
    )
    return cost_usd
