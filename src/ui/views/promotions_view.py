"""
Promotions, Discounts & Meal Combos Hub View.
"""
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_promotions_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Promotions & Deals Hub",
        subtitle="Competitor promotional tracking, combo packages, discount codes, and voucher analysis",
    )

    promotions = repo.get_promotions()

    # Filter Bar
    competitors = repo.get_all_competitors()
    f_c1, f_c2 = st.columns(2)
    with f_c1:
        comp_opts = [{"id": None, "name": "All Brands"}] + competitors
        sel_comp = st.selectbox("Filter by Brand", options=comp_opts, format_func=lambda c: c["name"])
    with f_c2:
        types = ["all", "bogo", "combo", "percentage_discount", "flat_discount"]
        sel_type = st.selectbox(
            "Filter by Promo Type",
            options=types,
            format_func=lambda t: t.upper() if t != "all" else "All Types",
        )

    filtered_promos = promotions
    if sel_comp["id"]:
        filtered_promos = [p for p in filtered_promos if p["competitor_id"] == sel_comp["id"]]
    if sel_type != "all":
        filtered_promos = [p for p in filtered_promos if p["promo_type"] == sel_type]

    # Promo Cards Grid
    if filtered_promos:
        st.subheader(f"Active Market Promotions ({len(filtered_promos)} deals)")
        cols = st.columns(2)
        for idx, p in enumerate(filtered_promos):
            with cols[idx % 2]:
                disc_badge = f"{p['discount_amount']} AED OFF" if p['discount_amount'] else (f"{p['discount_percentage']}% OFF" if p['discount_percentage'] else "COMBO DEAL")
                st.markdown(
                    f"""
                    <div class="kpi-container" style="border-left: 4px solid #C8102E;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span class="kpi-title">{p['competitor_name']}</span>
                            <span class="badge badge-verified">{p['promo_type'].upper()}</span>
                        </div>
                        <h4 style="margin: 8px 0 4px 0; font-size:1.15rem; color:#0F172A;">{p['title']}</h4>
                        <p style="color:#64748B; font-size:0.9rem; margin-bottom:10px;">{p['description'] or 'No description provided.'}</p>
                        <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.85rem; color:#334155;">
                            <span><b>Code:</b> <code>{p['promo_code'] or 'Automatic'}</code></span>
                            <span style="font-weight:700; color:#C8102E;">{disc_badge}</span>
                        </div>
                        <div style="margin-top:8px; font-size:0.75rem;">
                            <a href="{p['source_url']}" target="_blank" style="color:#2563EB;">🔗 Verify Source Link</a>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.info("No promotions match the selected filter.")

    st.divider()

    # Add Promotion Form
    with st.expander("➕ Add Genuine Competitor Promotion"):
        with st.form("add_promo_form"):
            ap_c1, ap_c2 = st.columns(2)
            with ap_c1:
                p_brand = st.selectbox("Competitor Brand", options=competitors, format_func=lambda c: c["name"])
                p_title = st.text_input("Deal Title", placeholder="e.g. 2 Medium Pizzas for AED 69")
                p_type_sel = st.selectbox("Promo Type", options=["combo", "bogo", "percentage_discount", "flat_discount", "free_item"])
                p_code = st.text_input("Promo Code (if any)", placeholder="e.g. 2MED69")
            with ap_c2:
                p_disc_amt = st.number_input("Discount Value in AED (Optional)", min_value=0.0, value=0.0, step=1.0)
                p_disc_pct = st.number_input("Discount Percentage (Optional)", min_value=0.0, max_value=100.0, value=0.0, step=5.0)
                p_src_url = st.text_input("Source URL (Mandatory)", placeholder="https://www.dominos.ae/en/pages/order/deals")
                p_desc = st.text_area("Promotion Terms / Description", placeholder="Valid for medium pizzas on delivery.")

            p_submit = st.form_submit_button("Save Promotion", type="primary")

            if p_submit:
                if not p_title.strip() or not p_src_url.strip():
                    st.error("Title and Source URL are required.")
                else:
                    try:
                        pr_id = repo.add_promotion(
                            competitor_id=p_brand["id"],
                            title=p_title.strip(),
                            promo_type=p_type_sel,
                            source_url=p_src_url.strip(),
                            description=p_desc.strip(),
                            discount_amount=float(p_disc_amt) if p_disc_amt > 0 else None,
                            discount_percentage=float(p_disc_pct) if p_disc_pct > 0 else None,
                            promo_code=p_code.strip(),
                        )
                        st.success(f"Promotion #{pr_id} saved successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error saving promotion: {e}")
