"""
UAE Pizza Price Intelligence Platform.
Commercial SaaS Web Application for Competitor Pricing Research across all 7 Emirates.
"""
from pathlib import Path
import streamlit as st

from config import DEFAULT_DB_PATH
from src.db.init_db import initialize_database
from src.db.repository import PizzaIntelligenceRepository
from src.db.seed_verified_data import seed_verified_benchmarks
from src.ui.styles import apply_custom_styles
from src.ui.views.catalog_view import render_catalog_view
from src.ui.views.channels_view import render_channels_view
from src.ui.views.collector_view import render_collector_view
from src.ui.views.comparison_view import render_comparison_view
from src.ui.views.evidence_view import render_evidence_view
from src.ui.views.history_view import render_history_view
from src.ui.views.overview_view import render_overview_view
from src.ui.views.promotions_view import render_promotions_view
from src.ui.views.reports_view import render_reports_view
from src.ui.views.review_view import render_review_view
from src.ui.views.status_view import render_status_view

# Streamlit Page Configuration
st.set_page_config(
    page_title="Pizza Hut UAE — Competitor Price Intelligence",
    page_icon="🍕",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply Commercial SaaS Styling
apply_custom_styles()

# Auto-Initialize Database if not present
if not Path(DEFAULT_DB_PATH).exists():
    seed_verified_benchmarks()

repo = PizzaIntelligenceRepository()

# -----------------------------------------------------------------------------
# Sidebar Navigation & Branding
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 10px 0 16px 0;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:2rem;">🍕</span>
                <div>
                    <h3 style="margin:0; font-size:1.15rem; font-weight:800; color:#0F172A;">PIZZA INTELLIGENCE</h3>
                    <p style="margin:0; font-size:0.75rem; color:#64748B; font-weight:600;">UAE MARKET ANALYTICS</p>
                </div>
            </div>
            <div style="margin-top:12px; display:flex; gap:6px;">
                <span style="background:#ECFDF5; color:#065F46; padding:2px 8px; border-radius:12px; font-size:0.7rem; font-weight:700;">● 7 EMIRATES</span>
                <span style="background:#EFF6FF; color:#1E40AF; padding:2px 8px; border-radius:12px; font-size:0.7rem; font-weight:700;">● ZERO-COST</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("---")

    navigation_options = {
        "📊 Executive Overview": render_overview_view,
        "⚖️ Price & Gap Comparison": render_comparison_view,
        "📈 Historical Price Trends": render_history_view,
        "🛒 Channel Disparity & Markups": render_channels_view,
        "🌐 Research & Live Collection": render_collector_view,
        "📝 QA & Review Queue": render_review_view,
        "🗄️ Evidence Vault & Audit": render_evidence_view,
        "🏢 Catalog & Branch Manager": render_catalog_view,
        "🎁 Promotions & Deals Hub": render_promotions_view,
        "📑 Reports & Excel Export": render_reports_view,
        "⚙️ System Status & Health": render_status_view,
    }

    selected_page = st.radio(
        "Navigation",
        options=list(navigation_options.keys()),
        label_visibility="collapsed",
    )

    st.write("---")

    # Quick Summary Live Stats in Sidebar
    metrics = repo.get_summary_metrics()
    st.markdown(
        f"""
        <div style="background:#F1F5F9; padding:12px; border-radius:8px; font-size:0.8rem; color:#475569;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span>Verified Records:</span>
                <b>{metrics['verified_prices_count']}</b>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span>Active Branches:</span>
                <b>{metrics['branch_count']}</b>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span>Audit Evidence:</span>
                <b>{metrics['evidence_count']} artifacts</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Main Content Router
# -----------------------------------------------------------------------------
view_function = navigation_options[selected_page]
view_function(repo)
