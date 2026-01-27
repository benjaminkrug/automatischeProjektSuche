"""Hauptseite - Akquise-Bot Dashboard."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
from datetime import datetime

from app.settings import settings
from app.ui import queries


st.set_page_config(
    page_title="Akquise-Bot",
    page_icon="🎯",
    layout="wide",
)

st.title("AKQUISE-BOT")


def main():
    # Refresh button in header
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    # Get database session
    session = queries.get_session()

    try:
        # --- Metrics Row ---
        st.markdown("---")

        col_today, col_total, col_capacity = st.columns(3)

        # Today stats
        today_stats = queries.get_today_stats(session)
        with col_today:
            st.subheader("HEUTE")
            st.metric("Gescraped", today_stats["scraped_today"])
            st.metric("Neu", today_stats["new_today"])

        # Total stats
        total_stats = queries.get_total_stats(session)
        with col_total:
            st.subheader("GESAMT")
            st.metric("Projekte", total_stats["total_projects"])
            st.metric("Bewerbungen", total_stats["total_applications"])

        # Capacity
        active_count = queries.get_active_applications_count(session)
        max_apps = settings.max_active_applications
        with col_capacity:
            st.subheader("KAPAZITÄT")
            st.metric("Aktive Bewerbungen", f"{active_count}/{max_apps}")
            # Progress bar for capacity
            capacity_pct = active_count / max_apps if max_apps > 0 else 0
            st.progress(min(capacity_pct, 1.0))

        # --- Portal Overview ---
        st.markdown("---")
        st.subheader("PORTAL-ÜBERSICHT")

        portal_stats = queries.get_portal_stats(session)

        if portal_stats:
            # Create dataframe for portal stats
            portal_data = []
            for ps in portal_stats:
                portal_data.append({
                    "Portal": ps["source"],
                    "Projekte": ps["total"],
                    "Beworben": ps["applied"],
                    "Gewonnen": ps["won"],
                    "Verloren": ps["lost"],
                    "Win-Rate": f"{ps['win_rate']}%" if ps["won"] + ps["lost"] > 0 else "-",
                })

            portal_df = pd.DataFrame(portal_data)

            st.dataframe(
                portal_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Portal": st.column_config.TextColumn("Portal", width="medium"),
                    "Projekte": st.column_config.NumberColumn("Projekte", width="small"),
                    "Beworben": st.column_config.NumberColumn("Beworben", width="small"),
                    "Gewonnen": st.column_config.NumberColumn("Gewonnen", width="small"),
                    "Verloren": st.column_config.NumberColumn("Verloren", width="small"),
                    "Win-Rate": st.column_config.TextColumn("Win-Rate", width="small"),
                },
            )

            # Summary row
            total_projects = sum(ps["total"] for ps in portal_stats)
            total_applied = sum(ps["applied"] for ps in portal_stats)
            total_won = sum(ps["won"] for ps in portal_stats)

            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                st.metric("Portale aktiv", len(portal_stats))
            with col_p2:
                st.metric("Projekte gesamt", total_projects)
            with col_p3:
                if total_applied > 0:
                    overall_win_rate = (total_won / total_applied * 100) if total_applied > 0 else 0
                    st.metric("Gesamt Win-Rate", f"{overall_win_rate:.1f}%")
        else:
            st.info("Noch keine Projekte gescraped.")

        # --- Pipeline Button ---
        st.markdown("---")

        col_btn, col_status = st.columns([2, 4])

        with col_btn:
            if st.button("▶ Pipeline starten", type="primary", width="stretch"):
                with st.spinner("Pipeline läuft..."):
                    try:
                        from app.orchestrator import run_daily
                        stats = run_daily()
                        st.success(
                            f"Pipeline abgeschlossen: {stats.new_projects} neue Projekte, "
                            f"{stats.applied} Bewerbungen"
                        )
                    except Exception as e:
                        st.error(f"Fehler: {e}")

        with col_status:
            st.caption(f"Letzte Aktualisierung: {datetime.now().strftime('%H:%M:%S')}")

        # --- Recent Activity ---
        st.markdown("---")
        st.subheader("LETZTE AKTIVITÄT")

        activities = queries.get_recent_activity(session, limit=10)

        if activities:
            for activity in activities:
                time_str = activity["timestamp"].strftime("%H:%M")
                icon = "📝" if activity["type"] == "application" else "❌"
                st.text(f"{icon} {time_str} {activity['description']}")
        else:
            st.info("Keine Aktivitäten vorhanden.")

        # --- Quick Links ---
        st.markdown("---")
        st.subheader("SCHNELLZUGRIFF")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            pending_reviews = len(queries.get_pending_reviews(session))
            st.metric("Offene Reviews", pending_reviews)

        with col2:
            win_stats = queries.get_win_rate(session)
            st.metric("Win-Rate", f"{win_stats['win_rate']}%")

        with col3:
            team_members = len(queries.get_team_members(session, active_only=True))
            st.metric("Team-Mitglieder", team_members)

        with col4:
            st.metric("Schwellenwert", f"{settings.match_threshold_apply}+")

    finally:
        session.close()


if __name__ == "__main__":
    main()
