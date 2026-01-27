"""Analytics Dashboard - Keyword scoring and cost tracking."""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from app.ui import queries


st.set_page_config(
    page_title="Analytics - Akquise-Bot",
    page_icon="📊",
    layout="wide",
)

st.title("📊 ANALYTICS")


def render_keyword_score_distribution(session):
    """Render keyword score distribution section."""
    st.subheader("KEYWORD-SCORE VERTEILUNG")

    try:
        from app.monitoring.keyword_analytics import get_keyword_distribution

        col1, col2 = st.columns([1, 3])

        with col1:
            lookback = st.selectbox(
                "Zeitraum",
                options=[7, 14, 30, 90],
                index=2,
                format_func=lambda x: f"{x} Tage",
            )

        distribution = get_keyword_distribution(session, lookback_days=lookback)

        with col2:
            st.metric("Analysierte Projekte", distribution["total_projects"])

        # Score distribution chart
        score_data = []
        for bucket, data in distribution["score_distribution"].items():
            score_data.append({
                "Score-Bereich": bucket,
                "Anzahl": data["count"],
                "Anteil": f"{data['percentage']:.1f}%",
            })

        score_df = pd.DataFrame(score_data)

        col_chart, col_table = st.columns([2, 1])

        with col_chart:
            st.bar_chart(
                score_df.set_index("Score-Bereich")["Anzahl"],
                use_container_width=True,
            )

        with col_table:
            st.dataframe(score_df, hide_index=True)

        # Confidence distribution
        st.markdown("**Confidence-Verteilung**")
        conf_data = []
        for level, data in distribution["confidence_distribution"].items():
            conf_data.append({
                "Confidence": level.capitalize(),
                "Anzahl": data["count"],
                "Anteil": f"{data['percentage']:.1f}%",
            })

        conf_df = pd.DataFrame(conf_data)
        st.dataframe(conf_df, hide_index=True)

        # Status by score range
        st.markdown("**Status nach Score-Bereich**")
        status_data = []
        for score_range, statuses in distribution["status_by_score_range"].items():
            row = {"Score": score_range}
            row.update(statuses)
            status_data.append(row)

        status_df = pd.DataFrame(status_data)
        st.dataframe(status_df, hide_index=True)

    except ImportError:
        st.warning("Keyword-Analytics-Modul nicht verfügbar.")
    except Exception as e:
        st.error(f"Fehler beim Laden der Keyword-Verteilung: {e}")


def render_keyword_effectiveness(session):
    """Render keyword effectiveness section."""
    st.subheader("KEYWORD-EFFEKTIVITÄT")

    try:
        from app.monitoring.keyword_analytics import get_keyword_effectiveness

        effectiveness = get_keyword_effectiveness(session, lookback_days=90)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Effektivste Keywords**")
            if effectiveness["most_effective_keywords"]:
                eff_data = []
                for kw in effectiveness["most_effective_keywords"][:10]:
                    eff_data.append({
                        "Keyword": kw["keyword"],
                        "Tier": kw["tier"].replace("tier_", "T"),
                        "Vorkommen": kw["occurrences"],
                        "Beworben": kw["applications"],
                        "Win-Rate": f"{kw['win_rate']:.0%}" if kw["wins"] > 0 else "-",
                    })
                st.dataframe(pd.DataFrame(eff_data), hide_index=True)
            else:
                st.info("Noch keine Daten verfügbar.")

        with col2:
            st.markdown("**Am wenigsten effektive Keywords**")
            if effectiveness["least_effective_keywords"]:
                least_data = []
                for kw in effectiveness["least_effective_keywords"][:10]:
                    least_data.append({
                        "Keyword": kw["keyword"],
                        "Tier": kw["tier"].replace("tier_", "T"),
                        "Vorkommen": kw["occurrences"],
                        "Bewerb-Rate": f"{kw['application_rate']:.0%}",
                    })
                st.dataframe(pd.DataFrame(least_data), hide_index=True)
            else:
                st.info("Noch keine Daten verfügbar.")

        # Best combinations
        st.markdown("**Beste Keyword-Kombinationen**")
        if effectiveness["best_combinations"]:
            combo_data = []
            for combo in effectiveness["best_combinations"][:5]:
                combo_data.append({
                    "Keywords": " + ".join(combo["keywords"]),
                    "Vorkommen": combo["occurrences"],
                    "Gewonnen": combo["wins"],
                    "Win-Rate": f"{combo['win_rate']:.0%}" if combo["wins"] > 0 else "-",
                })
            st.dataframe(pd.DataFrame(combo_data), hide_index=True)
        else:
            st.info("Noch keine Kombinationsdaten verfügbar.")

    except ImportError:
        st.warning("Keyword-Analytics-Modul nicht verfügbar.")
    except Exception as e:
        st.error(f"Fehler beim Laden der Keyword-Effektivität: {e}")


def render_cost_tracking():
    """Render cost tracking section."""
    st.subheader("AI-KOSTEN TRACKING")

    try:
        from app.monitoring.cost_tracker import get_cost_summary, estimate_monthly_cost

        summary = get_cost_summary()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Kosten diesen Monat",
                f"{summary['total_cost_eur']:.3f}€",
                delta=None,
            )

        with col2:
            st.metric(
                "Budget genutzt",
                f"{summary['budget_utilization_percent']:.1f}%",
            )

        with col3:
            st.metric(
                "Prognose Monat",
                f"{summary['projected_monthly_cost_eur']:.3f}€",
            )

        with col4:
            st.metric(
                "Budget verbleibend",
                f"{summary['budget_remaining_eur']:.3f}€",
            )

        # Budget progress bar
        utilization = min(summary["budget_utilization_percent"] / 100, 1.0)
        if utilization >= 0.8:
            st.progress(utilization, text="⚠️ Budget-Warnung")
        else:
            st.progress(utilization)

        # Cost breakdown by operation
        st.markdown("**Kosten nach Operation**")
        if summary["by_operation"]:
            op_data = []
            for op_name, op_stats in summary["by_operation"].items():
                op_data.append({
                    "Operation": op_name.capitalize(),
                    "Anzahl": op_stats["count"],
                    "Kosten (USD)": f"${op_stats['cost_usd']:.4f}",
                    "Input Tokens": f"{op_stats['input_tokens']:,}",
                    "Output Tokens": f"{op_stats['output_tokens']:,}",
                })
            st.dataframe(pd.DataFrame(op_data), hide_index=True)
        else:
            st.info("Noch keine Kostendaten verfügbar.")

        # Cost estimation
        st.markdown("**Kostenprognose**")
        with st.expander("Kostenrechner"):
            daily_projects = st.slider(
                "Projekte pro Tag",
                min_value=10,
                max_value=200,
                value=50,
            )
            estimate = estimate_monthly_cost(daily_projects)

            st.write(f"**Geschätzte monatliche Kosten:** {estimate['monthly_cost_eur']:.3f}€")
            st.write(f"**Innerhalb Budget:** {'✅ Ja' if estimate['within_budget'] else '❌ Nein'}")

            st.markdown("Aufschlüsselung (täglich):")
            st.json(estimate["breakdown"])

    except ImportError:
        st.warning("Cost-Tracker-Modul nicht verfügbar.")
    except Exception as e:
        st.error(f"Fehler beim Laden der Kostendaten: {e}")


def render_scraper_metrics(session):
    """Render scraper metrics section."""
    st.subheader("SCRAPER-METRIKEN")

    try:
        from app.monitoring.scraper_metrics import get_scraper_statistics

        stats = get_scraper_statistics(session, lookback_days=30)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Projekte (30 Tage)", stats["total_projects"])

        with col2:
            st.metric("Projekte/Tag", f"{stats['projects_per_day']:.1f}")

        with col3:
            st.metric("Aktive Portale", len(stats["sources"]))

        # Source breakdown
        st.markdown("**Projekte pro Portal**")
        if stats["sources"]:
            source_data = []
            for source, counts in stats["sources"].items():
                source_data.append({
                    "Portal": source,
                    "Gesamt": counts["total"],
                    "Beworben": counts["applied"],
                    "Abgelehnt": counts["rejected"],
                    "Review": counts["review"],
                })

            source_df = pd.DataFrame(source_data)
            source_df = source_df.sort_values("Gesamt", ascending=False)

            col_chart, col_table = st.columns([2, 1])

            with col_chart:
                st.bar_chart(
                    source_df.set_index("Portal")["Gesamt"],
                    use_container_width=True,
                )

            with col_table:
                st.dataframe(source_df, hide_index=True)
        else:
            st.info("Noch keine Scraper-Daten verfügbar.")

    except ImportError:
        st.warning("Scraper-Metrics-Modul nicht verfügbar.")
    except Exception as e:
        st.error(f"Fehler beim Laden der Scraper-Metriken: {e}")


def render_tier_recommendations(session):
    """Render tier change recommendations."""
    st.subheader("TIER-EMPFEHLUNGEN")

    try:
        from app.monitoring.keyword_analytics import suggest_tier_changes

        recommendations = suggest_tier_changes(session, min_occurrences=10)

        if recommendations:
            for rec in recommendations[:10]:
                current = rec.current_tier.value.replace("tier_", "T")
                recommended = rec.recommended_tier.value.replace("tier_", "T")
                confidence_emoji = {
                    "high": "🟢",
                    "medium": "🟡",
                    "low": "🔴",
                }.get(rec.confidence, "⚪")

                with st.expander(f"{confidence_emoji} {rec.keyword}: {current} → {recommended}"):
                    st.write(f"**Grund:** {rec.reason}")
                    st.write(f"**Confidence:** {rec.confidence}")
                    st.write(f"**Vorkommen:** {rec.stats.occurrences}")
                    st.write(f"**Bewerbungen:** {rec.stats.applications}")
        else:
            st.info("Keine Tier-Änderungen empfohlen. Mehr Daten erforderlich.")

    except ImportError:
        st.warning("Keyword-Analytics-Modul nicht verfügbar.")
    except Exception as e:
        st.error(f"Fehler beim Laden der Empfehlungen: {e}")


def main():
    # Refresh button
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    # Get database session
    session = queries.get_session()

    try:
        # Tabs for different sections
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 Keyword-Verteilung",
            "🎯 Effektivität",
            "💰 Kosten",
            "🔧 Empfehlungen",
        ])

        with tab1:
            render_keyword_score_distribution(session)
            st.markdown("---")
            render_scraper_metrics(session)

        with tab2:
            render_keyword_effectiveness(session)

        with tab3:
            render_cost_tracking()

        with tab4:
            render_tier_recommendations(session)

    finally:
        session.close()


if __name__ == "__main__":
    main()
