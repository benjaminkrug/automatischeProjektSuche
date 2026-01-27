"""Teammitglieder-Übersicht."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

from app.ui import queries

st.set_page_config(
    page_title="Team - Akquise-Bot",
    page_icon="👥",
    layout="wide",
)

st.title("👥 Team")


def main():
    session = queries.get_session()

    try:
        # --- Filter ---
        show_inactive = st.checkbox("Inaktive anzeigen", value=False)

        # --- Team Members ---
        members = queries.get_team_members(session, active_only=not show_inactive)

        if not members:
            st.info("Keine Teammitglieder gefunden.")
            return

        st.caption(f"{len(members)} Teammitglieder")

        # Display as cards
        cols = st.columns(3)

        for i, member in enumerate(members):
            col = cols[i % 3]

            with col:
                with st.container(border=True):
                    # Header
                    status_icon = "🟢" if member.active else "⚪"
                    st.subheader(f"{status_icon} {member.name}")

                    # Role and seniority
                    role_text = member.role or "Keine Rolle"
                    if member.seniority:
                        role_text += f" ({member.seniority})"
                    st.caption(role_text)

                    # Experience
                    if member.years_experience:
                        st.markdown(f"**Erfahrung:** {member.years_experience} Jahre")

                    # Min rate
                    if member.min_hourly_rate:
                        st.markdown(f"**Min. Stundensatz:** {member.min_hourly_rate:.0f}€")

                    # Skills
                    if member.skills:
                        st.markdown("**Skills:**")
                        skills_text = ", ".join(member.skills[:5])
                        if len(member.skills) > 5:
                            skills_text += f" (+{len(member.skills) - 5})"
                        st.write(skills_text)

                    # Industries
                    if member.industries:
                        st.markdown("**Branchen:**")
                        st.write(", ".join(member.industries[:3]))

                    # Languages
                    if member.languages:
                        st.markdown("**Sprachen:**")
                        st.write(", ".join(member.languages))

                    # Embedding status
                    has_embedding = member.profile_embedding is not None
                    embedding_status = "✅ Embedding" if has_embedding else "❌ Kein Embedding"
                    st.caption(embedding_status)

                    # CV link
                    if member.cv_path:
                        st.caption(f"📄 CV: {member.cv_path}")

        # --- Detail View ---
        st.markdown("---")
        st.subheader("Detailansicht")

        member_names = {m.id: m.name for m in members}
        selected_id = st.selectbox(
            "Teammitglied auswählen",
            list(member_names.keys()),
            format_func=lambda x: member_names.get(x, str(x)),
        )

        if selected_id:
            member = queries.get_team_member_by_id(session, selected_id)
            if member:
                with st.expander("Vollständiges Profil", expanded=True):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Name:** {member.name}")
                        st.markdown(f"**Rolle:** {member.role or '-'}")
                        st.markdown(f"**Seniority:** {member.seniority or '-'}")
                        st.markdown(f"**Erfahrung:** {member.years_experience or '-'} Jahre")
                        st.markdown(f"**Min. Stundensatz:** {member.min_hourly_rate or '-'}€")
                        st.markdown(f"**Aktiv:** {'Ja' if member.active else 'Nein'}")

                    with col2:
                        st.markdown("**Skills:**")
                        if member.skills:
                            st.write(", ".join(member.skills))
                        else:
                            st.write("-")

                        st.markdown("**Branchen:**")
                        if member.industries:
                            st.write(", ".join(member.industries))
                        else:
                            st.write("-")

                        st.markdown("**Sprachen:**")
                        if member.languages:
                            st.write(", ".join(member.languages))
                        else:
                            st.write("-")

                    if member.profile_text:
                        st.markdown("**Profiltext:**")
                        st.text_area(
                            "Profiltext",
                            member.profile_text,
                            height=150,
                            disabled=True,
                            label_visibility="collapsed",
                        )

    finally:
        session.close()


if __name__ == "__main__":
    main()
