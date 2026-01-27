"""Review Queue - Manuelle Entscheidungen."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

from app.ui import queries

st.set_page_config(
    page_title="Review Queue - Akquise-Bot",
    page_icon="📝",
    layout="wide",
)

st.title("📝 Review Queue")


def main():
    session = queries.get_session()

    try:
        # --- Pending Reviews ---
        reviews = queries.get_pending_reviews(session)

        if not reviews:
            st.success("Keine offenen Reviews.")
            return

        st.warning(f"{len(reviews)} Projekte warten auf Review")

        # Get team members for selection
        team_members = queries.get_team_members(session, active_only=True)
        member_options = {m.id: m.name for m in team_members}

        # --- Review Cards ---
        for review, project in reviews:
            with st.container(border=True):
                # Header with title and link button
                col_header, col_link, col_date = st.columns([3, 1, 1])
                with col_header:
                    st.subheader(project.title[:60] + ("..." if len(project.title) > 60 else ""))
                with col_link:
                    if project.url:
                        st.link_button(
                            "🔗 Ausschreibung",
                            project.url,
                            type="primary",
                        )
                with col_date:
                    st.caption(f"Erstellt: {review.created_at.strftime('%d.%m.%Y')}")

                # Match score if available (from proposed_rate as indicator)
                if project.proposed_rate:
                    st.markdown(f"**Vorgeschlagene Rate:** {project.proposed_rate:.0f} €/h")

                # Project info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Quelle:** {project.source}")
                    st.markdown(f"**Kunde:** {project.client_name or '-'}")
                with col2:
                    st.markdown(f"**Budget:** {project.budget or '-'}")
                    st.markdown(f"**Remote:** {'Ja' if project.remote else 'Nein'}")
                with col3:
                    st.markdown(f"**Öff. Sektor:** {'Ja' if project.public_sector else 'Nein'}")
                    st.markdown(f"**Ort:** {project.location or '-'}")

                # Review reason
                st.markdown(f"**Grund für Review:** {review.reason or '-'}")

                # Rate reasoning if available
                if project.rate_reasoning:
                    with st.expander("Rate Reasoning"):
                        st.info(project.rate_reasoning)

                # Skills
                if project.skills:
                    st.markdown(f"**Skills:** {', '.join(project.skills[:8])}" +
                               ("..." if len(project.skills) > 8 else ""))

                # Full description (expandable)
                if project.description:
                    with st.expander("Vollständige Beschreibung"):
                        st.text(project.description)

                # --- Decision Buttons ---
                st.markdown("---")

                col_member, col_apply, col_reject = st.columns([3, 1, 1])

                with col_member:
                    if member_options:
                        selected_member = st.selectbox(
                            "Teammitglied für Bewerbung",
                            list(member_options.keys()),
                            format_func=lambda x: member_options.get(x, str(x)),
                            key=f"member_{review.id}",
                        )
                    else:
                        st.warning("Keine aktiven Teammitglieder verfügbar")
                        selected_member = None

                with col_apply:
                    if st.button(
                        "✅ Bewerben",
                        key=f"apply_{review.id}",
                        type="primary",
                        disabled=not selected_member,
                    ):
                        if queries.resolve_review(
                            session,
                            review.id,
                            "apply",
                            team_member_id=selected_member,
                        ):
                            st.success("Bewerbung angelegt!")
                            st.rerun()
                        else:
                            st.error("Fehler beim Speichern")

                with col_reject:
                    if st.button(
                        "❌ Ablehnen",
                        key=f"reject_{review.id}",
                    ):
                        if queries.resolve_review(session, review.id, "reject"):
                            st.info("Projekt abgelehnt")
                            st.rerun()
                        else:
                            st.error("Fehler beim Speichern")

                st.markdown("")  # Spacing

    finally:
        session.close()


if __name__ == "__main__":
    main()
