"""Auftraggeber - Vergabestellen-Datenbank."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

from app.ui import queries

st.set_page_config(
    page_title="Auftraggeber - Akquise-Bot",
    page_icon="📋",
    layout="wide",
)

st.title("Auftraggeber-Datenbank")


def main():
    session = queries.get_session()

    try:
        # --- Statistics ---
        stats = queries.get_client_stats(session)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Auftraggeber", stats["total_clients"])

        with col2:
            st.metric("Mit Bewerbungen", stats["active_clients"])

        with col3:
            win_rate_str = f"{stats['overall_win_rate']:.0%}" if stats['overall_win_rate'] else "-"
            st.metric("Gesamt Win-Rate", win_rate_str)

        with col4:
            st.metric("Ausschreibungen gesehen", stats["total_tenders_seen"])

        st.markdown("---")

        # --- Sector Filter ---
        sector_options = ["Alle", "bund", "land", "kommune", "eu", "unknown"]
        sector_labels = {
            "Alle": "Alle",
            "bund": "Bund",
            "land": "Land",
            "kommune": "Kommune",
            "eu": "EU",
            "unknown": "Unbekannt",
        }
        sector_filter = st.selectbox(
            "Sektor",
            sector_options,
            format_func=lambda x: sector_labels.get(x, x),
        )

        # --- Client List ---
        clients = queries.get_clients(
            session,
            sector=sector_filter if sector_filter != "Alle" else None,
        )

        if not clients:
            st.info("Keine Auftraggeber gefunden.")
            return

        st.caption(f"{len(clients)} Auftraggeber")

        # --- Client Cards ---
        for client in clients:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

                with col1:
                    st.markdown(f"### {client.name}")
                    sector_emoji = {
                        "bund": "[D]",
                        "land": "[L]",
                        "kommune": "[K]",
                        "eu": "[EU]",
                    }
                    sector_display = sector_emoji.get(client.sector, "[?]")
                    st.caption(f"{sector_display} {sector_labels.get(client.sector, 'Unbekannt')}")

                with col2:
                    st.metric("Gesehen", client.tenders_seen or 0)

                with col3:
                    st.metric("Beworben", client.tenders_applied or 0)

                with col4:
                    win_rate = f"{client.win_rate:.0%}" if client.win_rate else "-"
                    st.metric("Win-Rate", win_rate)

                # Details expander
                with st.expander("Details"):
                    # Notes
                    if client.notes:
                        st.markdown(f"**Notizen:** {client.notes}")

                    # Payment rating
                    if client.payment_rating:
                        stars = "*" * client.payment_rating
                        st.markdown(f"**Zahlungsmoral:** {stars} ({client.payment_rating}/5)")

                    # Communication rating
                    if client.communication_rating:
                        stars = "*" * client.communication_rating
                        st.markdown(f"**Kommunikation:** {stars} ({client.communication_rating}/5)")

                    # Known contacts
                    if client.known_contacts:
                        st.markdown("**Bekannte Kontakte:**")
                        for contact in client.known_contacts:
                            name = contact.get("name", "-")
                            email = contact.get("email", "-")
                            role = contact.get("role", "")
                            role_str = f" ({role})" if role else ""
                            st.markdown(f"- {name}{role_str}: {email}")

                    # Aliases
                    if client.aliases:
                        st.markdown(f"**Aliase:** {', '.join(client.aliases)}")

                    st.markdown("---")

                    # Edit section
                    st.markdown("**Bewertung aktualisieren:**")

                    col_rating1, col_rating2 = st.columns(2)

                    with col_rating1:
                        new_payment_rating = st.slider(
                            "Zahlungsmoral",
                            1, 5,
                            value=client.payment_rating or 3,
                            key=f"payment_{client.id}",
                        )

                    with col_rating2:
                        new_comm_rating = st.slider(
                            "Kommunikation",
                            1, 5,
                            value=client.communication_rating or 3,
                            key=f"comm_{client.id}",
                        )

                    new_notes = st.text_area(
                        "Notizen",
                        value=client.notes or "",
                        key=f"notes_{client.id}",
                        height=100,
                    )

                    if st.button("Speichern", key=f"save_{client.id}"):
                        success = queries.update_client(
                            session,
                            client.id,
                            payment_rating=new_payment_rating,
                            communication_rating=new_comm_rating,
                            notes=new_notes,
                        )
                        if success:
                            st.success("Gespeichert!")
                            st.rerun()
                        else:
                            st.error("Fehler beim Speichern")

        # --- Top Clients Section ---
        st.markdown("---")
        st.subheader("Top Auftraggeber nach Win-Rate")

        top_clients = queries.get_top_clients(session, limit=5)

        if top_clients:
            for i, client in enumerate(top_clients, 1):
                win_rate = f"{client.win_rate:.0%}" if client.win_rate else "-"
                st.markdown(
                    f"{i}. **{client.name}** - "
                    f"Win-Rate: {win_rate} "
                    f"({client.tenders_won or 0}/{client.tenders_applied or 0})"
                )
        else:
            st.info("Noch keine Auftraggeber mit Bewerbungen.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
