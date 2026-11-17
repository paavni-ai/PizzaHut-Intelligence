"""
Side-by-Side Competitor Price & Gap Comparison Matrix View.
"""
import altair as alt
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_comparison_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Price Comparison & Gap Analysis",
        subtitle="Side-by-side pricing matrices benchmarked against Pizza Hut UAE",
    )

    # Filter Bar
    col1, col2, col3 = st.columns(3)
    emirates = repo.get_all_emirates()
    channels = repo.get_all_channels()

    with col1:
        sel_size = st.selectbox(
            "Select Pizza Size",
            options=["medium", "large", "small"],
            format_func=lambda s: f"{s.upper()} Pizza",
            index=0,
        )

    with col2:
        em_options = [{"id": None, "name_en": "All 7 Emirates (National Average)"}] + emirates
        sel_em = st.selectbox(
            "Select Emirate",
            options=em_options,
            format_func=lambda e: e["name_en"],
            index=0,
        )

    with col3:
        ch_options = [{"id": None, "name": "All Ordering Channels"}] + channels
        sel_ch = st.selectbox(
            "Select Ordering Channel",
            options=ch_options,
            format_func=lambda c: c["name"],
            index=0,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Fetch comparison matrix
    matrix_df = repo.get_price_comparison_matrix(
        normalized_size=sel_size,
        emirate_id=sel_em["id"],
        channel_id=sel_ch["id"],
    )

    if matrix_df.empty:
        st.info("No comparative pricing data available for this filter selection.")
        return

    # 1. Price Gap Calculation relative to Pizza Hut UAE
    st.subheader(f"📊 {sel_size.upper()} Pizza Price Matrix (AED)")
    st.caption("Benchmark reference: Pizza Hut UAE")

    # Format table for display
    display_matrix = matrix_df.copy()
    display_matrix.index = [str(i).replace("_", " ").title() for i in display_matrix.index]
    display_matrix.index.name = "Pizza Recipe"

    st.dataframe(
        display_matrix.style.format("{:.2f} AED", na_rep="-").highlight_min(
            axis=1, color="#DCFCE7"
        ).highlight_max(axis=1, color="#FEE2E2"),
        use_container_width=True,
    )

    st.divider()

    # 2. Competitor Price Gap Analysis
    ph_col = next((c for c in matrix_df.columns if "Pizza Hut" in c), None)

    if ph_col:
        st.subheader("⚖️ Price Gap vs Pizza Hut UAE Benchmark")
        gap_cols = [c for c in matrix_df.columns if c != ph_col]

        gap_cards = st.columns(len(gap_cols))
        for idx, comp in enumerate(gap_cols):
            with gap_cards[idx]:
                valid_pairs = matrix_df[[ph_col, comp]].dropna()
                if not valid_pairs.empty:
                    diff_aed = (valid_pairs[comp] - valid_pairs[ph_col]).mean()
                    diff_pct = ((valid_pairs[comp] - valid_pairs[ph_col]) / valid_pairs[ph_col]).mean() * 100

                    if diff_aed > 0:
                        status_class = "gap-expensive"
                        symbol = "▲ +"
                        desc = "more expensive than Pizza Hut"
                    elif diff_aed < 0:
                        status_class = "gap-cheaper"
                        symbol = "▼ "
                        desc = "cheaper than Pizza Hut"
                    else:
                        status_class = "gap-equal"
                        symbol = "="
                        desc = "equal to Pizza Hut"

                    st.markdown(
                        f"""
                        <div class="kpi-container">
                            <div class="kpi-title">{comp}</div>
                            <div class="kpi-value {status_class}">{symbol}{abs(diff_aed):.2f} AED</div>
                            <div class="kpi-sub {status_class}"><b>{symbol}{abs(diff_pct):.1f}%</b> {desc}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    # 3. Visual Comparison Chart
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📈 Direct Price Comparison by Recipe")

    # Melt dataframe for Altair
    reset_df = matrix_df.reset_index().melt(
        id_vars=["canonical_pizza"], var_name="Competitor", value_name="Price_AED"
    )
    reset_df["canonical_pizza"] = reset_df["canonical_pizza"].apply(lambda x: str(x).replace("_", " ").title())
    reset_df = reset_df.dropna()

    chart = (
        alt.Chart(reset_df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("canonical_pizza:N", title="Pizza Recipe", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Price_AED:Q", title="Price in AED"),
            color=alt.Color(
                "Competitor:N",
                scale=alt.Scale(
                    range=["#C8102E", "#0A192F", "#0284C7", "#10B981"]
                ),
            ),
            xOffset="Competitor:N",
            tooltip=[
                alt.Tooltip("canonical_pizza:N", title="Recipe"),
                alt.Tooltip("Competitor:N", title="Brand"),
                alt.Tooltip("Price_AED:Q", title="Price AED", format=".2f"),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(chart, use_container_width=True)
