"""Review Queue - Manuelle Entscheidungen."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
from datetime import datetime

from app.ui import queries

st.set_page_config(
    page_title="Review Queue - Akquise-Bot",
    page_icon="📝",
    layout="wide",
)

st.title("Review Queue")


def render_score_breakdown(session, project):
    """Render visual score breakdown for a tender."""
    decision = queries.get_tender_decision(session, project.id)
    if not decision or not decision.feature_vector:
        st.info("Keine Score-Details verfügbar.")
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


def render_deadline_badge(tender) -> str:
    """Render deadline badge text."""
    if not tender.tender_deadline:
        return "-"
    days_left = (tender.tender_deadline - datetime.now()).days
    return f"{days_left}d"


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
                # Determine if this is a tender
                is_tender = project.project_type == "tender"

                # Header with title and link button
                col_header, col_link, col_date = st.columns([3, 1, 1])
                with col_header:
                    type_badge = "[A]" if is_tender else "[F]"
                    st.subheader(f"{type_badge} {project.title[:55]}{'...' if len(project.title) > 55 else ''}")
                with col_link:
                    if project.url:
                        st.link_button(
                            "Link",
                            project.url,
                            type="primary",
                        )
                with col_date:
                    st.caption(f"Erstellt: {review.created_at.strftime('%d.%m.%Y')}")

                # --- Tender-specific header section ---
                if is_tender:
                    col_score, col_deadline, col_eligibility = st.columns(3)
                    with col_score:
                        score_val = project.score or 0
                        st.metric("Score", f"{score_val}/100")
                    with col_deadline:
                        if project.tender_deadline:
                            days_left = (project.tender_deadline - datetime.now()).days
                            if days_left >= 21:
                                st.success(f"Deadline: {days_left}d")
                            elif days_left >= 14:
                                st.warning(f"Deadline: {days_left}d")
                            else:
                                st.error(f"Deadline: {days_left}d")
                        else:
                            st.caption("Deadline: -")
                    with col_eligibility:
                        elig_badges = {"pass": "OK", "fail": "Fail", "unclear": "Prüfen"}
                        elig_val = elig_badges.get(project.eligibility_check, '-')
                        st.info(f"Eignung: {elig_val}")

                    # Score breakdown
                    with st.expander("Score-Aufschlüsselung"):
                        render_score_breakdown(session, project)

                    # Eligibility notes
                    if project.eligibility_notes:
                        st.warning(f"Eignungshinweise: {project.eligibility_notes}")

                    # Client info
                    client = queries.get_client_for_project(session, project)
                    if client:
                        win_rate_str = f"{client.win_rate:.0%}" if client.win_rate else "N/A"
                        st.info(f"Auftraggeber: {client.name} - {client.tenders_seen} Ausschreibungen, Win-Rate: {win_rate_str}")

                # Match score if available (freelance)
                if not is_tender and project.proposed_rate:
                    st.markdown(f"**Vorgeschlagene Rate:** {project.proposed_rate:.0f} €/h")

                # Project info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Quelle:** {project.source}")
                    st.markdown(f"**Kunde:** {project.client_name or '-'}")
                with col2:
                    if is_tender:
                        budget_str = f"{project.budget_max:,}€" if project.budget_max else project.budget or '-'
                        st.markdown(f"**Budget:** {budget_str}")
                        st.markdown(f"**Vergabeart:** {project.procedure_type or '-'}")
                    else:
                        st.markdown(f"**Budget:** {project.budget or '-'}")
                        st.markdown(f"**Remote:** {'Ja' if project.remote else 'Nein'}")
                with col3:
                    st.markdown(f"**Öff. Sektor:** {'Ja' if project.public_sector else 'Nein'}")
                    st.markdown(f"**Ort:** {project.location or '-'}")

                # Review reason
                st.markdown(f"**Grund für Review:** {review.reason or '-'}")

                # Rate reasoning if available (freelance)
                if not is_tender and project.rate_reasoning:
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

                if is_tender:
                    # Tender-specific actions
                    col_a1, col_a2, col_a3, col_a4 = st.columns(4)

                    with col_a1:
                        if st.button("Bewerben", key=f"apply_{review.id}", type="primary"):
                            queries.save_tender_decision(session, project.id, "apply")
                            queries.resolve_review(session, review.id, "apply")
                            st.success("Bewerbung markiert!")
                            st.rerun()

                    with col_a2:
                        if st.button("Partner suchen", key=f"partner_{review.id}"):
                            queries.save_tender_decision(session, project.id, "partner_needed")
                            st.info("Als 'Partner suchen' markiert")
                            st.rerun()

                    with col_a3:
                        if st.button("Beobachten", key=f"watch_{review.id}"):
                            queries.add_to_watchlist(session, project.id)
                            st.info("Zur Watchlist hinzugefügt")
                            st.rerun()

                    with col_a4:
                        if st.button("Ablehnen", key=f"reject_{review.id}"):
                            queries.save_tender_decision(session, project.id, "skip")
                            queries.resolve_review(session, review.id, "reject")
                            st.info("Abgelehnt")
                            st.rerun()
                else:
                    # Freelance actions
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
                            "Bewerben",
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
                            "Ablehnen",
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
