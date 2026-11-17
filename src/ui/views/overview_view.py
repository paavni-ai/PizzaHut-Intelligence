"""
Overview & Executive KPI Dashboard View.
"""
import altair as alt
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_overview_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Executive Overview",
        subtitle="Market-wide pricing analytics, brand positioning & data integrity health",
    )

    # 1. Fetch live KPIs
    metrics = repo.get_summary_metrics()

    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    with kpi1:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Competitors</div>
                <div class="kpi-value">{metrics['competitors_count']}</div>
                <div class="kpi-sub">Active UAE Chains</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with kpi2:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">UAE Branches</div>
                <div class="kpi-value">{metrics['branch_count']}</div>
                <div class="kpi-sub">Across 7 Emirates</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with kpi3:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Verified Prices</div>
                <div class="kpi-value">{metrics['verified_prices_count']}</div>
                <div class="kpi-sub">Audit-backed records</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with kpi4:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Avg Medium Pizza</div>
                <div class="kpi-value">{metrics['avg_medium_pizza_price']:.1f} <span style="font-size:1rem;color:#64748B;">AED</span></div>
                <div class="kpi-sub">Direct delivery base</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with kpi5:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Active Promos</div>
                <div class="kpi-value">{metrics['promotions_count']}</div>
                <div class="kpi-sub">BOGO & meal combos</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with kpi6:
        needs_color = "#DC2626" if metrics["needs_review_count"] > 0 else "#10B981"
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Review Queue</div>
                <div class="kpi-value" style="color:{needs_color};">{metrics['needs_review_count']}</div>
                <div class="kpi-sub">Pending QA action</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # 2. Charts Section
    col_chart1, col_chart2 = st.columns([3, 2])

    with col_chart1:
        st.subheader("📊 Average Pizza Price by Brand & Size (AED)")
        df_obs = repo.get_price_observations_df(limit=2000)
        if not df_obs.empty:
            df_chart = (
                df_obs.groupby(["competitor_name", "normalized_size"])["original_price"]
                .mean()
                .reset_index()
            )
            df_chart["original_price"] = df_chart["original_price"].round(2)
            df_chart = df_chart[df_chart["normalized_size"].isin(["small", "medium", "large"])]

            chart = (
                alt.Chart(df_chart)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("competitor_name:N", title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("original_price:Q", title="Price in AED"),
                    color=alt.Color(
                        "normalized_size:N",
                        title="Size",
                        scale=alt.Scale(
                            domain=["small", "medium", "large"],
                            range=["#94A3B8", "#0A192F", "#C8102E"],
                        ),
                    ),
                    xOffset="normalized_size:N",
                    tooltip=[
                        alt.Tooltip("competitor_name:N", title="Brand"),
                        alt.Tooltip("normalized_size:N", title="Size"),
                        alt.Tooltip("original_price:Q", title="Avg AED", format=".2f"),
                    ],
                )
                .properties(height=320)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No price observations recorded yet.")

    with col_chart2:
        st.subheader("📍 Price Distribution by Emirate")
        if not df_obs.empty:
            df_em = (
                df_obs[df_obs["normalized_size"] == "medium"]
                .groupby("emirate_name")["original_price"]
                .mean()
                .reset_index()
            )
            df_em["original_price"] = df_em["original_price"].round(2)

            em_chart = (
                alt.Chart(df_em)
                .mark_bar(color="#0A192F", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    y=alt.Y("emirate_name:N", title=None, sort="-x"),
                    x=alt.X("original_price:Q", title="Avg Medium Price (AED)"),
                    tooltip=[
                        alt.Tooltip("emirate_name:N", title="Emirate"),
                        alt.Tooltip("original_price:Q", title="Avg AED", format=".2f"),
                    ],
                )
                .properties(height=320)
            )
            st.altair_chart(em_chart, use_container_width=True)

    st.divider()

    # 3. Live Filterable Observations Explorer
    st.subheader("🔍 Recent Verified Market Observations")
    st.caption("Live observations query directly from SQLite database")

    fcol1, fcol2, fcol3 = st.columns(3)
    emirates = repo.get_all_emirates()
    competitors = repo.get_all_competitors()
    channels = repo.get_all_channels()

    with fcol1:
        sel_comp = st.multiselect(
            "Filter by Competitor",
            options=[c["id"] for c in competitors],
            format_func=lambda cid: next((c["name"] for c in competitors if c["id"] == cid), str(cid)),
        )
    with fcol2:
        sel_em = st.multiselect(
            "Filter by Emirate",
            options=[e["id"] for e in emirates],
            format_func=lambda eid: next((e["name_en"] for e in emirates if e["id"] == eid), str(eid)),
        )
    with fcol3:
        search_txt = st.text_input("Search Recipe / Product", placeholder="e.g. Margherita, Pepperoni...")

    obs_list = repo.get_price_observations(
        competitor_ids=sel_comp if sel_comp else None,
        emirate_ids=sel_em if sel_em else None,
        search_query=search_txt if search_txt else None,
        limit=50,
    )

    if obs_list:
        display_data = []
        for o in obs_list:
            display_data.append({
                "Brand": o["competitor_name"],
                "Product": o["product_name"],
                "Size": o["size_name"],
                "Crust": o["crust_type"],
                "Emirate": o["emirate_name"],
                "Channel": o["channel_name"],
                "Price (AED)": f"{o['original_price']:.2f}",
                "Status": o["verification_status"].upper(),
                "Collected": o["collected_at"][:10],
                "Source URL": o["source_url"],
            })
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, height=350)
    else:
        st.warning("No price observations match the selected filters.")
