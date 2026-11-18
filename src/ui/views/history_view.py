"""
Historical Price Tracking & Trend View.
"""
import altair as alt
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_history_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Historical Price Trends",
        subtitle="Tracking menu price shifts, inflation trends, and competitor adjustments over time",
    )

    # Filters
    col1, col2, col3 = st.columns(3)
    emirates = repo.get_all_emirates()

    with col1:
        recipes = [
            ("all", "All Pizza Recipes"),
            ("margherita", "Margherita"),
            ("pepperoni", "Pepperoni"),
            ("super_supreme", "Super Supreme / Feast"),
            ("veggie", "Veggie Lover's / Deluxe"),
            ("bbq_chicken", "BBQ Chicken"),
        ]
        sel_rec = st.selectbox(
            "Select Pizza Recipe",
            options=recipes,
            format_func=lambda r: r[1],
            index=0,
        )

    with col2:
        sel_size = st.selectbox(
            "Select Size",
            options=["medium", "large", "small"],
            format_func=lambda s: f"{s.upper()} Pizza",
            index=0,
        )

    with col3:
        em_options = [{"id": None, "name_en": "All 7 Emirates"}] + emirates
        sel_em = st.selectbox(
            "Select Emirate",
            options=em_options,
            format_func=lambda e: e["name_en"],
            index=0,
        )

    rec_filter = None if sel_rec[0] == "all" else sel_rec[0]
    trends_df = repo.get_historical_trends(
        normalized_name=rec_filter,
        normalized_size=sel_size,
        emirate_id=sel_em["id"],
    )

    if trends_df.empty:
        st.info("No human-reviewed, evidence-backed price history matches this selection yet.")
    else:
        st.subheader(f"📈 Verified Price Evolution: {sel_rec[1]} ({sel_size.upper()})")
        line_chart = (
            alt.Chart(trends_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("observation_date:T", title="Observation Date"),
                y=alt.Y("avg_price:Q", title="Price (AED)", scale=alt.Scale(zero=False)),
                color=alt.Color(
                    "competitor_name:N",
                    title="Brand",
                    scale=alt.Scale(range=["#C8102E", "#0A192F", "#0284C7", "#10B981"]),
                ),
                tooltip=[
                    alt.Tooltip("observation_date:T", title="Date"),
                    alt.Tooltip("competitor_name:N", title="Brand"),
                    alt.Tooltip("product_name:N", title="Product"),
                    alt.Tooltip("avg_price:Q", title="Price AED", format=".2f"),
                ],
            )
            .properties(height=380)
        )
        st.altair_chart(line_chart, use_container_width=True)

    # Detailed Log
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📋 Price Audit Records")
    obs_df = repo.get_price_observations_df(
        normalized_sizes=[sel_size],
        emirate_ids=[sel_em["id"]] if sel_em["id"] else None,
        limit=100,
    )
    if not obs_df.empty:
        disp = obs_df[[
            "collected_at", "competitor_name", "product_name", "size_name",
            "emirate_name", "channel_name", "original_price", "verification_status", "source_url"
        ]].copy()
        disp.columns = ["Date & Time", "Brand", "Product", "Size", "Emirate", "Channel", "Price (AED)", "Status", "Source URL"]
        st.dataframe(disp, use_container_width=True, height=300)
