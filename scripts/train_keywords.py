#!/usr/bin/env python
"""A1: Wöchentlicher Keyword-Training Job.

Analysiert historische Bewerbungsergebnisse und schlägt
Anpassungen an den Keyword-Tiers vor.

Usage:
    python scripts/train_keywords.py

Ausgabe:
    - Keyword Performance Report mit Win-Rates
    - Vorschläge für Tier-Änderungen
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import get_session
from app.ml.keyword_trainer import (
    generate_keyword_report,
    run_training,
    suggest_tier_adjustments,
)


def main():
    """Führe Keyword-Training durch und zeige Report."""
    print("Keyword Training - Akquise-Bot")
    print("=" * 60)
    print()

    with get_session() as db:
        # Generate and print full report
        report = generate_keyword_report(db)
        print(report)

        # Also run training for potential programmatic use
        rates, suggestions = run_training(db)

        print()
        print(f"Zusammenfassung:")
        print(f"  - {len(rates)} Keywords analysiert")
        print(f"  - {len(suggestions)} Anpassungen vorgeschlagen")

        # Count by action type
        upgrades = sum(1 for s in suggestions if "UPGRADE" in s.suggested_action)
        downgrades = sum(1 for s in suggestions if "DOWNGRADE" in s.suggested_action)
        removes = sum(1 for s in suggestions if "REMOVE" in s.suggested_action)
        adds = sum(1 for s in suggestions if "ADD" in s.suggested_action)

        if suggestions:
            print()
            print("  Vorgeschlagene Aktionen:")
            if upgrades:
                print(f"    - {upgrades}x UPGRADE")
            if downgrades:
                print(f"    - {downgrades}x DOWNGRADE")
            if removes:
                print(f"    - {removes}x REMOVE")
            if adds:
                print(f"    - {adds}x ADD")


if __name__ == "__main__":
    main()
