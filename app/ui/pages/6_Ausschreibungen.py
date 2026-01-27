"""Ausschreibungen - Tender-spezifische Ansicht."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
from datetime import datetime

from app.ui import queries
from app.settings import settings

st.set_page_config(
    page_title="Ausschreibungen - Akquise-Bot",
    page_icon="📑",
    layout="wide",
)

st.title("Ausschreibungen")


def render_score_breakdown(session, project):
    """Render visual score breakdown."""
    decision = queries.get_tender_decision(session, project.id)
    if not decision or not decision.feature_vector:
        return

    fv = decision.feature_vector

    breakdown = [
        ("Tech-Fit", fv.get("tech_score", 0), 40),
        ("Volumen", fv.get("volume_score", 0), 15),
        ("Vergabeart", fv.get("procedure_score", 0), 15),
        ("Zuschlag", fv.get("award_criteria_score", 0), 10),
        ("Eignung", fv.get("eligibility_score", 0), 15),
        ("Deadline", fv.get("deadline_score", 0), 10),
    ]

    for name, score, max_score in breakdown:
        pct = score / max_score if max_score > 0 else 0
        bar = "|" * int(pct * 10) + "-" * (10 - int(pct * 10))
        st.text(f"{name:12} {score:3}/{max_score:2}  [{bar}]")


def deadline_badge(tender) -> str:
    """Generate deadline badge text."""
    if not tender.tender_deadline:
        return "-"
    days_left = (tender.tender_deadline - datetime.now()).days
    return f"{days_left}d"


def main():
    session = queries.get_session()

    try:
        # --- Sidebar Filter ---
        st.sidebar.header("Filter")

        score_min = st.sidebar.slider("Min. Score", 0, 100, 50)

        # Procedure type filter
        procedure_types = ["Alle"] + queries.get_procedure_types(session)
        procedure_type = st.sidebar.selectbox("Vergabeart", procedure_types)

        # Eligibility filter
        eligibility_options = ["Alle", "pass", "unclear", "fail"]
        eligibility = st.sidebar.selectbox(
            "Eignung",
            eligibility_options,
            format_func=lambda x: {"Alle": "Alle", "pass": "OK", "unclear": "Unklar", "fail": "Nicht erfüllt"}.get(x, x),
        )

        # Deadline filter
        deadline_days = st.sidebar.slider("Max. Tage bis Deadline", 7, 60, 30)

        # Status filter
        status_options = ["Alle", "review", "applied", "rejected", "watching"]
        selected_status = st.sidebar.selectbox(
            "Status",
            status_options,
            format_func=lambda x: {
                "Alle": "Alle",
                "review": "Review",
                "applied": "Beworben",
                "rejected": "Abgelehnt",
                "watching": "Beobachten",
            }.get(x, x),
        )

        # --- Export Section ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("Export")

        if st.sidebar.button("CSV-Export"):
            df = queries.get_tenders_as_dataframe(session, score_min=score_min)
            csv = df.to_csv(index=False)
            st.sidebar.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"ausschreibungen_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

        if st.sidebar.button("Wochenreport"):
            report = queries.generate_weekly_report(session)
            st.sidebar.download_button(
                label="Download Report",
                data=report,
                file_name=f"wochenreport_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
            )

        # --- Score Distribution Chart ---
        st.subheader("Score-Verteilung (letzte 30 Tage)")

        score_data = queries.get_tender_score_distribution(session)
        if any(score_data.values()):
            chart_df = pd.DataFrame({
                "Score-Bereich": list(score_data.keys()),
                "Anzahl": list(score_data.values()),
            })
            st.bar_chart(chart_df.set_index("Score-Bereich"))
        else:
            st.info("Noch keine Score-Daten verfügbar.")

        # --- Capacity Indicator ---
        tender_count = queries.get_active_tenders_count(session)
        max_tenders = settings.max_active_tenders

        col_cap, col_count = st.columns([3, 1])
        with col_cap:
            st.progress(tender_count / max_tenders if max_tenders > 0 else 0)
        with col_count:
            st.caption(f"Aktiv: {tender_count}/{max_tenders}")

        st.markdown("---")

        # --- Tender List ---
        tenders = queries.get_tenders(
            session,
            score_min=score_min,
            procedure_type=procedure_type if procedure_type != "Alle" else None,
            eligibility=eligibility if eligibility != "Alle" else None,
            days_until_deadline=deadline_days,
            status=selected_status if selected_status != "Alle" else None,
        )

        if not tenders:
            st.info("Keine Ausschreibungen gefunden.")
            return

        st.caption(f"{len(tenders)} Ausschreibungen gefunden")

        # --- Tender Cards ---
        for tender in tenders:
            with st.expander(
                f"**{tender.title[:60]}{'...' if len(tender.title) > 60 else ''}** | "
                f"Score: {tender.score or '-'} | {deadline_badge(tender)}"
            ):
                # Basic info
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**Auftraggeber:** {tender.client_name or '-'}")
                    budget_str = f"{tender.budget_max:,}€" if tender.budget_max else tender.budget or "-"
                    st.markdown(f"**Budget:** {budget_str}")
                    st.markdown(f"**Vergabeart:** {tender.procedure_type or '-'}")

                with col2:
                    st.markdown(f"**Quelle:** {tender.source}")
                    deadline_str = tender.tender_deadline.strftime('%d.%m.%Y') if tender.tender_deadline else '-'
                    st.markdown(f"**Deadline:** {deadline_str}")

                    elig_labels = {"pass": "Erfüllt", "fail": "Nicht erfüllt", "unclear": "Unklar"}
                    elig_str = elig_labels.get(tender.eligibility_check, '-')
                    st.markdown(f"**Eignung:** {elig_str}")

                # Score breakdown
                st.markdown("---")
                st.markdown("**Score-Aufschlüsselung:**")
                render_score_breakdown(session, tender)

                # Lots view
                lots = queries.get_lots_for_project(session, tender.id)
                if lots:
                    st.markdown("---")
                    st.markdown("**Lose:**")
                    for lot in lots:
                        lot_icon = "+" if lot.score and lot.score >= 70 else "?" if lot.score and lot.score >= 50 else "-"
                        lot_score = lot.score or "-"
                        st.markdown(f"- {lot_icon} **{lot.lot_number}:** {lot.lot_title or '-'} (Score: {lot_score})")

                # Eligibility notes
                if tender.eligibility_notes:
                    st.markdown("---")
                    st.warning(f"Eignungshinweise: {tender.eligibility_notes}")

                # Link
                if tender.url:
                    st.markdown("---")
                    st.link_button("Zur Ausschreibung", tender.url)

                # Description
                if tender.description:
                    with st.expander("Vollständige Beschreibung"):
                        st.text(tender.description[:2000])
                        if len(tender.description) > 2000:
                            st.caption("... (gekürzt)")

                # Quick Actions
                st.markdown("---")
                col_a1, col_a2, col_a3, col_a4 = st.columns(4)

                with col_a1:
                    if st.button("Bewerben", key=f"apply_{tender.id}", type="primary"):
                        queries.save_tender_decision(session, tender.id, "apply")
                        st.success("Als 'Bewerben' markiert!")
                        st.rerun()

                with col_a2:
                    if st.button("Partner suchen", key=f"partner_{tender.id}"):
                        queries.save_tender_decision(session, tender.id, "partner_needed")
                        st.info("Als 'Partner suchen' markiert")
                        st.rerun()

                with col_a3:
                    if st.button("Beobachten", key=f"watch_{tender.id}"):
                        queries.add_to_watchlist(session, tender.id)
                        st.info("Zur Watchlist hinzugefügt")
                        st.rerun()

                with col_a4:
                    if st.button("Ablehnen", key=f"reject_{tender.id}"):
                        queries.save_tender_decision(session, tender.id, "skip")
                        st.info("Abgelehnt")
                        st.rerun()

    finally:
        session.close()


if __name__ == "__main__":
    main()
