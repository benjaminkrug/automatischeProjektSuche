"""Projektübersicht mit Filter."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
from datetime import datetime

from app.ui import queries
from app.core.constants import (
    PROJECT_STATUS_NEW,
    PROJECT_STATUS_ANALYZED,
    PROJECT_STATUS_APPLIED,
    PROJECT_STATUS_REVIEW,
    PROJECT_STATUS_REJECTED,
    PROJECT_STATUS_ERROR,
)

st.set_page_config(
    page_title="Projekte - Akquise-Bot",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Projekte")


# Rejection reason code translations
REJECTION_REASON_LABELS = {
    "BUDGET_TOO_LOW": "Budget zu niedrig",
    "TECH_STACK_MISMATCH": "Tech-Stack passt nicht",
    "EXPERIENCE_INSUFFICIENT": "Erfahrung nicht ausreichend",
    "TIMELINE_CONFLICT": "Zeitlicher Konflikt",
    "CAPACITY_FULL": "Kapazität erschöpft",
    "MANUAL_REJECT": "Manuell abgelehnt",
}


def main():
    session = queries.get_session()

    try:
        # --- Filter Section ---
        st.sidebar.header("Filter")

        # Status filter
        status_options = ["Alle"] + [
            PROJECT_STATUS_NEW,
            PROJECT_STATUS_ANALYZED,
            PROJECT_STATUS_APPLIED,
            PROJECT_STATUS_REVIEW,
            PROJECT_STATUS_REJECTED,
            PROJECT_STATUS_ERROR,
        ]
        selected_status = st.sidebar.selectbox("Status", status_options)

        # Source filter
        sources = ["Alle"] + queries.get_project_sources(session)
        selected_source = st.sidebar.selectbox("Quelle", sources)

        # Date range
        days_back = st.sidebar.slider("Tage zurück", min_value=1, max_value=90, value=30)

        # Text search
        search_text = st.sidebar.text_input("Suche", placeholder="Titel oder Beschreibung...")

        # --- Projects Table ---
        projects = queries.get_projects(
            session,
            status=selected_status if selected_status != "Alle" else None,
            source=selected_source if selected_source != "Alle" else None,
            search_text=search_text if search_text else None,
            days_back=days_back,
        )

        if not projects:
            st.info("Keine Projekte gefunden.")
            return

        st.caption(f"{len(projects)} Projekte gefunden")

        # Pre-load rejection reasons for rejected projects
        rejection_cache = {}
        rejected_ids = [p.id for p in projects if p.status == PROJECT_STATUS_REJECTED]
        for project_id in rejected_ids:
            rejection = queries.get_rejection_for_project(session, project_id)
            if rejection:
                rejection_cache[project_id] = rejection

        # Convert to dataframe for display
        data = []
        for p in projects:
            # Get rejection reason for rejected projects
            rejection_text = ""
            if p.status == PROJECT_STATUS_REJECTED and p.id in rejection_cache:
                rejection = rejection_cache[p.id]
                rejection_text = REJECTION_REASON_LABELS.get(
                    rejection.reason_code, rejection.reason_code
                )

            data.append({
                "ID": p.id,
                "Datum": p.scraped_at.strftime("%d.%m.%Y") if p.scraped_at else "-",
                "Quelle": p.source,
                "Titel": p.title[:60] + "..." if len(p.title) > 60 else p.title,
                "Status": p.status,
                "Rate (€/h)": f"{p.proposed_rate:.0f}" if p.proposed_rate else "-",
                "Ablehnung": rejection_text,
                "url": p.url,
            })

        df = pd.DataFrame(data)

        # Status color coding
        def status_color(val):
            colors = {
                PROJECT_STATUS_NEW: "background-color: #e3f2fd",
                PROJECT_STATUS_ANALYZED: "background-color: #fff3e0",
                PROJECT_STATUS_APPLIED: "background-color: #e8f5e9",
                PROJECT_STATUS_REVIEW: "background-color: #fff8e1",
                PROJECT_STATUS_REJECTED: "background-color: #ffebee",
                PROJECT_STATUS_ERROR: "background-color: #fce4ec",
            }
            return colors.get(val, "")

        # Display table with link column
        display_cols = ["ID", "Datum", "Quelle", "Titel", "Status", "Rate (€/h)"]
        if selected_status == PROJECT_STATUS_REJECTED or selected_status == "Alle":
            display_cols.append("Ablehnung")

        display_df = df[display_cols].copy()

        st.dataframe(
            display_df.style.applymap(status_color, subset=["Status"]),
            width="stretch",
            hide_index=True,
            column_config={
                "Rate (€/h)": st.column_config.TextColumn("Rate (€/h)", width="small"),
                "Ablehnung": st.column_config.TextColumn("Ablehnung", width="medium"),
            },
        )

        # --- Project Details ---
        st.markdown("---")
        st.subheader("Projektdetails")

        # Select project for details
        project_ids = [p.id for p in projects]
        selected_id = st.selectbox(
            "Projekt auswählen",
            project_ids,
            format_func=lambda x: next(
                (f"{p.id}: {p.title[:50]}" for p in projects if p.id == x),
                str(x)
            ),
        )

        if selected_id:
            project = queries.get_project_by_id(session, selected_id)
            if project:
                with st.expander("Details anzeigen", expanded=True):
                    # Link button at top
                    if project.url:
                        st.link_button(
                            "🔗 Zur Ausschreibung",
                            project.url,
                            type="primary",
                            width="content",
                        )
                        st.markdown("")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Titel:** {project.title}")
                        st.markdown(f"**Quelle:** {project.source}")
                        st.markdown(f"**Status:** {project.status}")
                        st.markdown(f"**Kunde:** {project.client_name or '-'}")
                        st.markdown(f"**Budget:** {project.budget or '-'}")

                    with col2:
                        st.markdown(f"**Ort:** {project.location or '-'}")
                        st.markdown(f"**Remote:** {'Ja' if project.remote else 'Nein'}")
                        st.markdown(f"**Öffentlicher Sektor:** {'Ja' if project.public_sector else 'Nein'}")
                        st.markdown(f"**Gescraped:** {project.scraped_at.strftime('%d.%m.%Y %H:%M') if project.scraped_at else '-'}")
                        if project.analyzed_at:
                            st.markdown(f"**Analysiert:** {project.analyzed_at.strftime('%d.%m.%Y %H:%M')}")

                    # Rate info
                    if project.proposed_rate:
                        st.markdown("---")
                        st.markdown(f"**Vorgeschlagene Rate:** {project.proposed_rate:.0f} €/h")
                        if project.rate_reasoning:
                            st.markdown("**Rate Reasoning:**")
                            st.info(project.rate_reasoning)

                    # Rejection reason
                    if project.status == PROJECT_STATUS_REJECTED:
                        rejection = queries.get_rejection_for_project(session, project.id)
                        if rejection:
                            st.markdown("---")
                            st.markdown("**Ablehnungsgrund:**")
                            reason_label = REJECTION_REASON_LABELS.get(
                                rejection.reason_code, rejection.reason_code
                            )
                            st.error(f"**{reason_label}**")
                            if rejection.explanation:
                                st.markdown(f"_{rejection.explanation}_")
                            if rejection.estimated_success_probability:
                                st.markdown(f"Geschätzte Erfolgswahrscheinlichkeit: {rejection.estimated_success_probability:.0%}")

                    if project.skills:
                        st.markdown("---")
                        st.markdown("**Skills:**")
                        st.write(", ".join(project.skills))

                    if project.description:
                        st.markdown("---")
                        st.markdown("**Beschreibung:**")
                        st.text_area(
                            "Beschreibung",
                            project.description,
                            height=200,
                            disabled=True,
                            label_visibility="collapsed",
                        )

    finally:
        session.close()


if __name__ == "__main__":
    main()
