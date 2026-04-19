"""
Lead Hunter Dashboard — Streamlit Web Interface
=================================================
Interactive dashboard to visualize, filter, and export leads.

Usage:
    streamlit run dashboard.py
"""

import json
import glob
from pathlib import Path
from datetime import datetime

import streamlit as st

from config.settings import settings
from utils.export import export_csv, export_excel, load_leads_from_json

# ─── Page Config ──────────────────────────────────────────

st.set_page_config(
    page_title="Lead Hunter Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        color: white;
    }
    .main-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.7;
        font-size: 0.95rem;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .metric-card.blue { border-color: #3b82f6; }
    .metric-card.green { border-color: #10b981; }
    .metric-card.yellow { border-color: #f59e0b; }
    .metric-card.red { border-color: #ef4444; }

    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1e293b;
        line-height: 1;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 0.3rem;
    }

    /* Score badge */
    .score-high { color: #059669; font-weight: 700; }
    .score-mid { color: #d97706; font-weight: 600; }
    .score-low { color: #dc2626; font-weight: 600; }

    /* Table styling */
    .dataframe {
        font-size: 0.85rem !important;
    }

    /* Sidebar */
    .css-1d391kg { padding-top: 1rem; }

    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ─── Data Loading ─────────────────────────────────────────

@st.cache_data(ttl=30)
def load_all_leads() -> list[dict]:
    """Load all leads from the results directory."""
    results_dir = settings.project_root / "results"
    if not results_dir.exists():
        return []

    all_leads = []

    # Load from leads_*.json files (flat format)
    for leads_file in sorted(results_dir.glob("leads_*.json"), reverse=True):
        leads = load_leads_from_json(leads_file)
        for lead in leads:
            lead["_source_file"] = leads_file.name
        all_leads.extend(leads)

    # Deduplicate by (nom/name, adresse/address)
    seen = set()
    unique_leads = []
    for lead in all_leads:
        key = (
            lead.get("nom", lead.get("name", "")),
            lead.get("adresse", lead.get("address", "")),
        )
        if key not in seen:
            seen.add(key)
            unique_leads.append(lead)

    return unique_leads


@st.cache_data(ttl=30)
def load_run_summaries() -> list[dict]:
    """Load run summaries for history view."""
    results_dir = settings.project_root / "results"
    if not results_dir.exists():
        return []

    summaries = []
    for run_file in sorted(results_dir.glob("run_*.json"), reverse=True):
        with open(run_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for run in data:
            run["_file"] = run_file.name
            # Extract timestamp from filename
            ts = run_file.stem.replace("run_", "")
            try:
                run["_date"] = datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M")
            except ValueError:
                run["_date"] = ts
        summaries.extend(data)

    return summaries


# ─── Helper Functions ─────────────────────────────────────

def get_score_badge(score) -> str:
    """Return colored HTML for a score value."""
    try:
        s = int(score)
    except (ValueError, TypeError):
        return str(score)
    if s >= 8:
        return f'<span class="score-high">⬤ {s}/10</span>'
    elif s >= 5:
        return f'<span class="score-mid">⬤ {s}/10</span>'
    return f'<span class="score-low">⬤ {s}/10</span>'


def normalize_field(lead: dict, *keys, default=""):
    """Get the first non-empty value from multiple possible field names."""
    for key in keys:
        val = lead.get(key, "")
        if val:
            return val
    return default


# ─── Main App ─────────────────────────────────────────────

def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🎯 Lead Hunter Dashboard</h1>
        <p>Système Multi-Agents de Génération de Leads B2B</p>
    </div>
    """, unsafe_allow_html=True)

    # Load data
    leads = load_all_leads()
    runs = load_run_summaries()

    # ── Sidebar ────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔧 Filtres")

        # Extract unique cities and niches
        cities = sorted(set(
            normalize_field(l, "ville", "city", "_run_city")
            for l in leads if normalize_field(l, "ville", "city", "_run_city")
        ))
        niches = sorted(set(
            normalize_field(l, "niche")
            for l in leads if l.get("niche")
        ))

        selected_city = st.selectbox("📍 Ville", ["Toutes"] + cities)
        selected_niche = st.selectbox("🏷️ Niche", ["Toutes"] + niches)

        min_score = st.slider("⭐ Score minimum", 1, 10, 5)

        st.markdown("---")
        st.markdown("### 📊 Infos")
        st.markdown(f"**Mode:** `{settings.mode}`")
        st.markdown(f"**Villes config:** {len(settings.cities)}")
        st.markdown(f"**Niches config:** {len(settings.niches)}")

        st.markdown("---")

        # Refresh button
        if st.button("🔄 Rafraîchir", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── Filter leads ───────────────────────────────────────
    filtered = leads.copy()

    if selected_city != "Toutes":
        filtered = [
            l for l in filtered
            if normalize_field(l, "ville", "city", "_run_city") == selected_city
        ]

    if selected_niche != "Toutes":
        filtered = [l for l in filtered if l.get("niche") == selected_niche]

    filtered = [
        l for l in filtered
        if isinstance(l.get("score"), (int, float)) and l["score"] >= min_score
    ]

    # ── Metrics Row ────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="metric-card blue">
            <div class="metric-value">{len(leads)}</div>
            <div class="metric-label">Total Leads</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card green">
            <div class="metric-value">{len(filtered)}</div>
            <div class="metric-label">Leads Filtrés</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        avg_score = (
            sum(l.get("score", 0) for l in filtered if isinstance(l.get("score"), (int, float)))
            / max(len(filtered), 1)
        )
        st.markdown(f"""
        <div class="metric-card yellow">
            <div class="metric-value">{avg_score:.1f}</div>
            <div class="metric-label">Score Moyen</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card red">
            <div class="metric-value">{len(runs)}</div>
            <div class="metric-label">Runs Effectués</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ───────────────────────────────────────────────
    tab_leads, tab_charts, tab_history, tab_export = st.tabs([
        "📋 Leads", "📊 Graphiques", "🕐 Historique", "📥 Export"
    ])

    # ── Tab 1: Leads Table ─────────────────────────────────
    with tab_leads:
        if not filtered:
            st.info("Aucun lead ne correspond aux filtres sélectionnés.")
        else:
            # Build display dataframe
            import pandas as pd

            display_data = []
            for lead in filtered:
                socials = lead.get("reseaux_sociaux", {})
                social_str = ", ".join(socials.keys()) if isinstance(socials, dict) else ""

                display_data.append({
                    "Nom": normalize_field(lead, "nom", "name"),
                    "Ville": normalize_field(lead, "ville", "city"),
                    "Niche": lead.get("niche", ""),
                    "Score": lead.get("score", ""),
                    "Note": lead.get("rating", ""),
                    "Avis": lead.get("nb_avis", 0),
                    "Téléphone": normalize_field(lead, "telephone", "phone"),
                    "Email": lead.get("email", ""),
                    "Réseaux": social_str,
                    "Dernier Avis": lead.get("dernier_avis", ""),
                    "Site Web": "❌ Non" if not lead.get("has_website") else "✅ Oui",
                })

            df = pd.DataFrame(display_data)

            # Style the dataframe
            def color_score(val):
                try:
                    s = int(val)
                    if s >= 8:
                        return "background-color: #dcfce7; color: #059669; font-weight: bold"
                    elif s >= 5:
                        return "background-color: #fef9c3; color: #d97706; font-weight: bold"
                    return "background-color: #fee2e2; color: #dc2626; font-weight: bold"
                except (ValueError, TypeError):
                    return ""

            styled = df.style.applymap(color_score, subset=["Score"])
            st.dataframe(styled, use_container_width=True, height=500)

    # ── Tab 2: Charts ──────────────────────────────────────
    with tab_charts:
        if not filtered:
            st.info("Aucune donnée à afficher.")
        else:
            import pandas as pd

            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                st.markdown("#### 📊 Distribution des Scores")
                scores = [l.get("score", 0) for l in filtered if isinstance(l.get("score"), (int, float))]
                if scores:
                    score_counts = pd.Series(scores).value_counts().sort_index()
                    st.bar_chart(score_counts)

            with chart_col2:
                st.markdown("#### 🏙️ Leads par Ville")
                cities_data = [normalize_field(l, "ville", "city") for l in filtered]
                if cities_data:
                    city_counts = pd.Series(cities_data).value_counts()
                    st.bar_chart(city_counts)

            chart_col3, chart_col4 = st.columns(2)

            with chart_col3:
                st.markdown("#### 🏷️ Leads par Niche")
                niche_data = [l.get("niche", "") for l in filtered if l.get("niche")]
                if niche_data:
                    niche_counts = pd.Series(niche_data).value_counts()
                    st.bar_chart(niche_counts)

            with chart_col4:
                st.markdown("#### ⭐ Score Moyen par Niche")
                import pandas as pd
                niche_scores = {}
                for l in filtered:
                    n = l.get("niche", "")
                    s = l.get("score", 0)
                    if n and isinstance(s, (int, float)):
                        niche_scores.setdefault(n, []).append(s)
                if niche_scores:
                    avg_by_niche = {k: sum(v)/len(v) for k, v in niche_scores.items()}
                    st.bar_chart(pd.Series(avg_by_niche))

    # ── Tab 3: Run History ─────────────────────────────────
    with tab_history:
        if not runs:
            st.info("Aucun historique de run trouvé.")
        else:
            for run in runs:
                status_icon = "✅" if run.get("status") == "completed" else "❌"
                with st.expander(
                    f"{status_icon} {run.get('city', '?')} × {run.get('niche', '?')} — "
                    f"{run.get('_date', '?')} — {run.get('duration', '?')}s",
                    expanded=False
                ):
                    rcol1, rcol2, rcol3 = st.columns(3)
                    rcol1.metric("Qualifiés", run.get("qualified", "?"))
                    rcol2.metric("Rejetés", run.get("rejected", "?"))
                    rcol3.metric("Durée", f"{run.get('duration', '?')}s")

                    run_leads = run.get("leads", [])
                    if run_leads:
                        st.markdown(f"**{len(run_leads)} leads extraits :**")
                        for lead in run_leads:
                            name = lead.get("nom", lead.get("name", "?"))
                            score = lead.get("score", "?")
                            st.markdown(f"- **{name}** — Score: {score}/10")

    # ── Tab 4: Export ──────────────────────────────────────
    with tab_export:
        st.markdown("### 📥 Exporter les Leads")

        if not filtered:
            st.warning("Aucun lead à exporter avec les filtres actuels.")
        else:
            st.info(f"**{len(filtered)} leads** prêts à l'export avec les filtres actuels.")

            exp_col1, exp_col2, exp_col3 = st.columns(3)

            with exp_col1:
                # CSV Export
                results_dir = settings.project_root / "results"
                csv_path = results_dir / "export_leads.csv"
                export_csv(filtered, csv_path)

                with open(csv_path, "r", encoding="utf-8") as f:
                    csv_data = f.read()

                st.download_button(
                    label="📄 Télécharger CSV",
                    data=csv_data,
                    file_name="leads_export.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with exp_col2:
                # Excel Export
                xlsx_path = results_dir / "export_leads.xlsx"
                export_excel(filtered, xlsx_path)

                with open(xlsx_path, "rb") as f:
                    xlsx_data = f.read()

                st.download_button(
                    label="📊 Télécharger Excel",
                    data=xlsx_data,
                    file_name="leads_export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            with exp_col3:
                # JSON Export
                json_data = json.dumps(filtered, indent=2, default=str, ensure_ascii=False)
                st.download_button(
                    label="🔧 Télécharger JSON",
                    data=json_data,
                    file_name="leads_export.json",
                    mime="application/json",
                    use_container_width=True,
                )


if __name__ == "__main__":
    main()
