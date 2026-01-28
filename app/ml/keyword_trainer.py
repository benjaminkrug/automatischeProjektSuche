"""A1: ML-basierte Keyword-Gewichtung basierend auf Application-Outcomes.

Dieses Modul analysiert historische Bewerbungsergebnisse, um die Effektivität
von Keywords zu messen und Tier-Anpassungen vorzuschlagen.

Usage:
    python -m app.ml.keyword_trainer

Oder als Script:
    python scripts/train_keywords.py
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import ApplicationLog, Project

logger = get_logger("ml.keyword_trainer")


@dataclass
class KeywordStats:
    """Statistiken für ein einzelnes Keyword."""

    keyword: str
    wins: int  # accepted, interview
    losses: int  # rejected
    total: int
    win_rate: float
    current_tier: Optional[int]  # 1, 2, 3 or None


@dataclass
class TierSuggestion:
    """Vorschlag für Tier-Änderung."""

    keyword: str
    current_tier: Optional[int]
    suggested_action: str  # "UPGRADE", "DOWNGRADE", "KEEP"
    reason: str
    confidence: str  # "high", "medium", "low"


# Minimum sample size for suggestions
MIN_SAMPLE_SIZE = 5
# Minimum sample size for high-confidence suggestions
HIGH_CONFIDENCE_SAMPLE_SIZE = 10

# Win-rate thresholds for tier adjustments
UPGRADE_THRESHOLD = 0.60  # > 60% win-rate -> consider upgrade
DOWNGRADE_THRESHOLD = 0.30  # < 30% win-rate -> consider downgrade


def calculate_keyword_success_rates(db: Session) -> Dict[str, KeywordStats]:
    """Berechne Erfolgsrate pro Keyword.

    Analysiert alle abgeschlossenen Bewerbungen und berechnet die Win-Rate
    für jedes Keyword, das in den Projekten gefunden wurde.

    Args:
        db: Database session

    Returns:
        Dict mapping keyword to KeywordStats
    """
    from app.ai.keyword_scoring import TIER_1_KEYWORDS, TIER_2_KEYWORDS, TIER_3_KEYWORDS

    keyword_data: Dict[str, Dict] = defaultdict(
        lambda: {"wins": 0, "losses": 0, "total": 0}
    )

    # Query completed applications with their projects
    completed = (
        db.query(ApplicationLog, Project)
        .join(Project, ApplicationLog.project_id == Project.id)
        .filter(ApplicationLog.outcome.isnot(None))
        .all()
    )

    logger.info("Analysiere %d abgeschlossene Bewerbungen...", len(completed))

    for log, project in completed:
        # Get keywords from project (persisted in M2)
        tier_1 = project.keyword_tier_1 or []
        tier_2 = project.keyword_tier_2 or []
        all_keywords = tier_1 + tier_2

        # Determine if this was a win
        is_win = log.outcome in ("accepted", "interview")

        for kw in all_keywords:
            kw_lower = kw.lower()
            keyword_data[kw_lower]["total"] += 1
            if is_win:
                keyword_data[kw_lower]["wins"] += 1
            else:
                keyword_data[kw_lower]["losses"] += 1

    # Convert to KeywordStats objects
    results = {}
    for kw, stats in keyword_data.items():
        if stats["total"] >= MIN_SAMPLE_SIZE:
            win_rate = stats["wins"] / stats["total"] if stats["total"] > 0 else 0.0

            # Determine current tier
            current_tier = None
            kw_lower = kw.lower()
            if kw_lower in TIER_1_KEYWORDS or kw in TIER_1_KEYWORDS:
                current_tier = 1
            elif kw_lower in TIER_2_KEYWORDS or kw in TIER_2_KEYWORDS:
                current_tier = 2
            elif kw_lower in TIER_3_KEYWORDS or kw in TIER_3_KEYWORDS:
                current_tier = 3

            results[kw] = KeywordStats(
                keyword=kw,
                wins=stats["wins"],
                losses=stats["losses"],
                total=stats["total"],
                win_rate=win_rate,
                current_tier=current_tier,
            )

    return results


def suggest_tier_adjustments(
    success_rates: Dict[str, KeywordStats]
) -> List[TierSuggestion]:
    """Schlage Tier-Änderungen basierend auf Win-Rate vor.

    Args:
        success_rates: Dict von KeywordStats aus calculate_keyword_success_rates()

    Returns:
        Liste von TierSuggestion Objekten
    """
    suggestions = []

    for kw, stats in success_rates.items():
        confidence = "high" if stats.total >= HIGH_CONFIDENCE_SAMPLE_SIZE else "medium"

        if stats.win_rate > UPGRADE_THRESHOLD:
            # High win-rate -> consider upgrade
            if stats.current_tier is None:
                action = "ADD_TIER_3"
                reason = f"Neues Keyword mit {stats.win_rate:.0%} Win-Rate ({stats.wins}/{stats.total})"
            elif stats.current_tier == 3:
                action = "UPGRADE"
                reason = f"Tier 3 -> Tier 2: {stats.win_rate:.0%} Win-Rate ({stats.wins}/{stats.total})"
            elif stats.current_tier == 2:
                action = "UPGRADE"
                reason = f"Tier 2 -> Tier 1: {stats.win_rate:.0%} Win-Rate ({stats.wins}/{stats.total})"
            else:
                action = "KEEP"
                reason = f"Bereits Tier 1 mit {stats.win_rate:.0%} Win-Rate"

            suggestions.append(
                TierSuggestion(
                    keyword=kw,
                    current_tier=stats.current_tier,
                    suggested_action=action,
                    reason=reason,
                    confidence=confidence,
                )
            )

        elif stats.win_rate < DOWNGRADE_THRESHOLD:
            # Low win-rate -> consider downgrade
            if stats.current_tier == 1:
                action = "DOWNGRADE"
                reason = f"Tier 1 -> Tier 2: nur {stats.win_rate:.0%} Win-Rate ({stats.wins}/{stats.total})"
            elif stats.current_tier == 2:
                action = "DOWNGRADE"
                reason = f"Tier 2 -> Tier 3: nur {stats.win_rate:.0%} Win-Rate ({stats.wins}/{stats.total})"
            elif stats.current_tier == 3:
                action = "REMOVE"
                reason = f"Tier 3 entfernen: nur {stats.win_rate:.0%} Win-Rate ({stats.wins}/{stats.total})"
            else:
                action = "KEEP"
                reason = f"Nicht in Tiers, {stats.win_rate:.0%} Win-Rate"

            suggestions.append(
                TierSuggestion(
                    keyword=kw,
                    current_tier=stats.current_tier,
                    suggested_action=action,
                    reason=reason,
                    confidence=confidence,
                )
            )

    # Sort by impact (upgrades first, then by confidence)
    suggestions.sort(
        key=lambda s: (
            0 if s.suggested_action == "UPGRADE" else 1,
            0 if s.confidence == "high" else 1,
        )
    )

    return suggestions


def generate_keyword_report(db: Session) -> str:
    """Generiere einen Bericht über Keyword-Performance.

    Args:
        db: Database session

    Returns:
        Formatierter Bericht als String
    """
    rates = calculate_keyword_success_rates(db)
    suggestions = suggest_tier_adjustments(rates)

    lines = []
    lines.append("=" * 60)
    lines.append("KEYWORD PERFORMANCE REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Summary
    lines.append(f"Analysierte Keywords: {len(rates)}")
    lines.append(f"Vorschläge: {len(suggestions)}")
    lines.append("")

    # Top performers
    lines.append("-" * 40)
    lines.append("TOP PERFORMER (Win-Rate > 60%)")
    lines.append("-" * 40)
    top = sorted(rates.values(), key=lambda x: x.win_rate, reverse=True)[:10]
    for stats in top:
        if stats.win_rate > 0.6:
            tier_str = f"T{stats.current_tier}" if stats.current_tier else "NEW"
            lines.append(
                f"  {stats.keyword:20} {tier_str:5} {stats.win_rate:5.0%} ({stats.wins}/{stats.total})"
            )

    # Underperformers
    lines.append("")
    lines.append("-" * 40)
    lines.append("UNDERPERFORMER (Win-Rate < 30%)")
    lines.append("-" * 40)
    bottom = sorted(rates.values(), key=lambda x: x.win_rate)[:10]
    for stats in bottom:
        if stats.win_rate < 0.3:
            tier_str = f"T{stats.current_tier}" if stats.current_tier else "NEW"
            lines.append(
                f"  {stats.keyword:20} {tier_str:5} {stats.win_rate:5.0%} ({stats.wins}/{stats.total})"
            )

    # Suggestions
    if suggestions:
        lines.append("")
        lines.append("-" * 40)
        lines.append("EMPFOHLENE ANPASSUNGEN")
        lines.append("-" * 40)
        for s in suggestions:
            confidence_marker = "*" if s.confidence == "high" else ""
            lines.append(f"  [{s.suggested_action}]{confidence_marker} {s.keyword}")
            lines.append(f"      {s.reason}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def run_training(db: Session) -> Tuple[Dict[str, KeywordStats], List[TierSuggestion]]:
    """Führe komplettes Training durch.

    Args:
        db: Database session

    Returns:
        Tuple of (success_rates, suggestions)
    """
    logger.info("Starting keyword training...")

    rates = calculate_keyword_success_rates(db)
    logger.info("Calculated success rates for %d keywords", len(rates))

    suggestions = suggest_tier_adjustments(rates)
    logger.info("Generated %d tier suggestions", len(suggestions))

    return rates, suggestions


if __name__ == "__main__":
    from app.db.session import get_session

    with get_session() as db:
        report = generate_keyword_report(db)
        print(report)
