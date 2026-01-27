"""Bewerbungen - Application Logs."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd

from app.ui import queries

st.set_page_config(
    page_title="Bewerbungen - Akquise-Bot",
    page_icon="📨",
    layout="wide",
)

st.title("📨 Bewerbungen")


def main():
    session = queries.get_session()

    try:
        # --- Win Rate Stats ---
        stats = queries.get_win_rate(session)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Gesamt", stats["total"])
        with col2:
            st.metric("Gewonnen", stats["won"])
        with col3:
            st.metric("Verloren", stats["lost"])
        with col4:
            st.metric("Offen", stats["pending"])
        with col5:
            st.metric("Win-Rate", f"{stats['win_rate']}%")

        # --- Filter ---
        st.markdown("---")

        outcome_options = ["Alle", "Offen", "won", "lost"]
        selected_outcome = st.selectbox("Status filtern", outcome_options)

        # --- Applications Table ---
        applications = queries.get_application_logs(
            session,
            outcome=selected_outcome if selected_outcome != "Alle" else None,
        )

        if not applications:
            st.info("Keine Bewerbungen gefunden.")
            return

        st.caption(f"{len(applications)} Bewerbungen")

        # Convert to dataframe
        data = []
        for app, project, member in applications:
            data.append({
                "ID": app.id,
                "Datum": app.applied_at.strftime("%d.%m.%Y") if app.applied_at else "-",
                "Projekt": project.title[:40] + "..." if len(project.title) > 40 else project.title,
                "Quelle": project.source,
                "Teammitglied": member.name,
                "Score": f"{app.match_score:.0f}" if app.match_score else "-",
                "Rate": f"{app.proposed_rate:.0f}€" if app.proposed_rate else "-",
                "Outcome": app.outcome or "offen",
                "project_id": project.id,
                "project_url": project.url,
            })

        df = pd.DataFrame(data)

        # Outcome color coding
        def outcome_color(val):
            colors = {
                "won": "background-color: #c8e6c9",
                "lost": "background-color: #ffcdd2",
                "offen": "background-color: #fff9c4",
            }
            return colors.get(val, "")

        # Display table (without internal columns)
        display_df = df.drop(columns=["project_id", "project_url"])
        st.dataframe(
            display_df.style.applymap(outcome_color, subset=["Outcome"]),
            width="stretch",
            hide_index=True,
            column_config={
                "Score": st.column_config.TextColumn("Score", width="small"),
                "Rate": st.column_config.TextColumn("Rate", width="small"),
                "Quelle": st.column_config.TextColumn("Quelle", width="small"),
            },
        )

        # --- Update Outcome ---
        st.markdown("---")
        st.subheader("Outcome aktualisieren")

        # Only show open applications for update
        open_apps = [a for a in applications if a[0].outcome is None]

        if not open_apps:
            st.info("Keine offenen Bewerbungen zum Aktualisieren.")
        else:
            app_options = {
                a[0].id: f"{a[0].id}: {a[1].title[:30]}... ({a[2].name})"
                for a in open_apps
            }

            col_select, col_outcome, col_btn = st.columns([3, 2, 1])

            with col_select:
                selected_app_id = st.selectbox(
                    "Bewerbung auswählen",
                    list(app_options.keys()),
                    format_func=lambda x: app_options.get(x, str(x)),
                )

            with col_outcome:
                new_outcome = st.selectbox(
                    "Neuer Status",
                    ["won", "lost"],
                )

            with col_btn:
                st.write("")  # Spacing
                st.write("")  # Spacing
                if st.button("Speichern", type="primary"):
                    if queries.update_application_outcome(
                        session,
                        selected_app_id,
                        new_outcome,
                    ):
                        st.success(f"Outcome auf '{new_outcome}' gesetzt!")
                        st.rerun()
                    else:
                        st.error("Fehler beim Speichern")

        # --- Application Details ---
        st.markdown("---")
        st.subheader("Bewerbungsdetails")

        all_app_options = {
            a[0].id: f"{a[0].id}: {a[1].title[:30]}... ({a[2].name})"
            for a in applications
        }

        if all_app_options:
            detail_app_id = st.selectbox(
                "Bewerbung für Details",
                list(all_app_options.keys()),
                format_func=lambda x: all_app_options.get(x, str(x)),
                key="detail_select",
            )

            # Find selected application
            selected = next((a for a in applications if a[0].id == detail_app_id), None)

            if selected:
                app, project, member = selected

                with st.expander("Details anzeigen", expanded=True):
                    # Link button at top
                    if project.url:
                        st.link_button(
                            "🔗 Zur Ausschreibung",
                            project.url,
                            type="primary",
                        )
                        st.markdown("")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**Projekt:**")
                        st.markdown(f"- Titel: {project.title}")
                        st.markdown(f"- Quelle: {project.source}")
                        st.markdown(f"- Kunde: {project.client_name or '-'}")
                        st.markdown(f"- Budget: {project.budget or '-'}")
                        st.markdown(f"- Öff. Sektor: {'Ja' if project.public_sector else 'Nein'}")

                    with col2:
                        st.markdown("**Bewerbung:**")
                        st.markdown(f"- Teammitglied: {member.name}")
                        st.markdown(f"- Match-Score: {app.match_score or '-'}")
                        st.markdown(f"- Vorgeschlagene Rate: {app.proposed_rate or '-'}€/h")
                        st.markdown(f"- Beworben am: {app.applied_at.strftime('%d.%m.%Y %H:%M') if app.applied_at else '-'}")
                        st.markdown(f"- Outcome: {app.outcome or 'offen'}")
                        if app.outcome_at:
                            st.markdown(f"- Outcome am: {app.outcome_at.strftime('%d.%m.%Y')}")

                    # Rate reasoning
                    if project.rate_reasoning:
                        st.markdown("---")
                        st.markdown("**Rate Reasoning:**")
                        st.info(project.rate_reasoning)

                    # Output folder link
                    output_folder = Path("output") / f"project_{project.id}"
                    if output_folder.exists():
                        st.markdown("---")
                        st.markdown(f"📁 Output-Ordner: `{output_folder}`")

    finally:
        session.close()


if __name__ == "__main__":
    main()
