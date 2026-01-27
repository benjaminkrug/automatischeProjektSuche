#!/usr/bin/env python
"""
Entry point for running the tender acquisition pipeline.

This script runs the separate pipeline for public sector tenders
(Ausschreibungen) with specialized scoring for web/mobile projects.

Usage:
    python scripts/run_tenders.py

Features:
- Scrapes only public sector portals (DTVP, bund.de, evergabe, TED, simap)
- CPV code pre-filtering for relevant software development tenders
- Specialized scoring for agency-sized projects (50k-250k EUR)
- Eligibility checking (references, certifications, revenue requirements)
- Lot extraction for large tenders
- Outputs to review queue (no auto-apply)
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tender_orchestrator import run_tenders


def main():
    """Run the tender pipeline."""
    print("=" * 60)
    print("TENDER ACQUISITION PIPELINE")
    print("=" * 60)
    print()

    stats = run_tenders()

    print()
    print("=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    print(f"  Neue Ausschreibungen:  {stats.new_projects}")
    print(f"  Hohe Priorität:        {stats.high_priority}")
    print(f"  In Review-Queue:       {stats.review_queue}")
    print(f"  Abgelehnt:             {stats.rejected}")
    print()

    if stats.high_priority > 0:
        print("⚠️  Neue hochpriorisierte Ausschreibungen gefunden!")
        print("   Bitte Review-Queue prüfen.")

    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
