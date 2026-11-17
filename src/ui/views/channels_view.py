"""
Multi-Channel Price Disparity & Aggregator Markup Analysis View.
"""
import altair as alt
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_channels_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Channel Disparity & Markups",
        subtitle="Tracking price markups across Direct Delivery, Pickup, Dine-in, and Aggregator apps",
    )

    markups = repo.get_channel_markup_analysis()
    if not markups:
        st.info("No matching cross-channel price pairs available for markup comparison.")
        return

    df_markups = pd.DataFrame(markups)

    # Top KPI tiles for markups
    avg_markup_aed = df_markups["markup_aed"].mean()
    avg_markup_pct = df_markups["markup_pct"].mean()
    max_markup_aed = df_markups["markup_aed"].max()

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Avg Aggregator Markup</div>
                <div class="kpi-value gap-expensive">+{avg_markup_aed:.2f} <span style="font-size:1rem;">AED</span></div>
                <div class="kpi-sub">Third-party delivery premium</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Average Markup %</div>
                <div class="kpi-value gap-expensive">+{avg_markup_pct:.1f}%</div>
                <div class="kpi-sub">Across Talabat & Deliveroo</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Max Single Item Markup</div>
                <div class="kpi-value gap-expensive">+{max_markup_aed:.2f} AED</div>
                <div class="kpi-sub">Highest premium observed</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Compared Product Pairs</div>
                <div class="kpi-value">{len(df_markups)}</div>
                <div class="kpi-sub">Exact size & flavor matches</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Markup Chart
    st.subheader("📊 Aggregator Markup by Brand & Pizza Size (AED)")
    agg_chart = (
        alt.Chart(df_markups)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("competitor:N", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("mean(markup_aed):Q", title="Avg Markup (AED)"),
            color=alt.Color(
                "size:N",
                scale=alt.Scale(domain=["Medium", "Large"], range=["#0A192F", "#C8102E"]),
            ),
            xOffset="size:N",
            tooltip=[
                alt.Tooltip("competitor:N", title="Brand"),
                alt.Tooltip("size:N", title="Size"),
                alt.Tooltip("mean(markup_aed):Q", title="Avg Markup AED", format=".2f"),
                alt.Tooltip("mean(markup_pct):Q", title="Avg Markup %", format=".1f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(agg_chart, use_container_width=True)

    st.divider()

    # Detailed Table
    st.subheader("📋 Identical Item Price Disparity Log")
    st.caption("Side-by-side verification between restaurant direct ordering and aggregator listings")

    display_df = df_markups.copy()
    display_df.columns = [
        "Competitor", "Product", "Size", "Emirate", "Direct Price (AED)",
        "Aggregator Price (AED)", "Markup (AED)", "Markup (%)"
    ]
    st.dataframe(
        display_df.style.format({
            "Direct Price (AED)": "{:.2f}",
            "Aggregator Price (AED)": "{:.2f}",
            "Markup (AED)": "+{:.2f}",
            "Markup (%)": "+{:.1f}%",
        }),
        use_container_width=True,
        height=380,
    )
