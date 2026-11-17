"""
Research Runs, Live URL Auditor & Price Collector View.
"""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.scrapers.genuine_collector import GenuineResearchCollector
from src.ui.styles import render_brand_header


def render_collector_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Research & Collection Hub",
        subtitle="Live URL auditing, genuine price collection runs, and research session logs",
    )

    collector = GenuineResearchCollector(db_path=repo.db_path)

    tab1, tab2, tab3 = st.tabs([
        "🌐 Live URL Auditor & Target Prober",
        "📝 Submit Verified Price Observation",
        "📜 Research Runs History",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Live URL Target Prober
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("Target Accessibility & SSL Probe")
        st.caption("Verifies HTTP accessibility, response latency, and security headers without bypassing anti-bot challenges.")

        col_url, col_btn = st.columns([4, 1])
        with col_url:
            target_url = st.text_input(
                "Competitor Target URL",
                value="https://www.dominos.ae",
                placeholder="https://www.papajohns.ae/menu/pizza",
            )
        with col_btn:
            st.write("&nbsp;")
            probe_btn = st.button("Probe Target", use_container_width=True, type="primary")

        if probe_btn and target_url:
            with st.spinner("Probing target endpoint..."):
                result = collector.audit_url_target(target_url)

            p1, p2, p3, p4 = st.columns(4)
            with p1:
                status_color = "#059669" if result["accessible"] else "#DC2626"
                st.markdown(
                    f"""<div class="kpi-container">
                        <div class="kpi-title">HTTP Status</div>
                        <div class="kpi-value" style="color:{status_color};">{result['status_code'] or 'ERR'}</div>
                        <div class="kpi-sub">{'Accessible' if result['accessible'] else 'Blocked / Error'}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with p2:
                st.markdown(
                    f"""<div class="kpi-container">
                        <div class="kpi-title">Response Latency</div>
                        <div class="kpi-value">{result['latency_ms'] or '-'} <span style="font-size:1rem;">ms</span></div>
                        <div class="kpi-sub">Round-trip latency</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with p3:
                size_kb = (result["content_length"] or 0) / 1024
                st.markdown(
                    f"""<div class="kpi-container">
                        <div class="kpi-title">Payload Size</div>
                        <div class="kpi-value">{size_kb:.1f} <span style="font-size:1rem;">KB</span></div>
                        <div class="kpi-sub">Uncompressed body</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with p4:
                hash_short = result["content_hash"][:10] + "..." if result["content_hash"] else "None"
                st.markdown(
                    f"""<div class="kpi-container">
                        <div class="kpi-title">SHA-256 Hash</div>
                        <div class="kpi-value" style="font-size:1.1rem;word-break:break-all;">{hash_short}</div>
                        <div class="kpi-sub">Cryptographic audit proof</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

            if result["blocked"]:
                st.warning(f"⚠️ Access Restriction: {result.get('error')}. Per project rules, anti-bot gates are respected and not bypassed.")
            elif result["accessible"]:
                st.success(f"✓ Target endpoint is publicly accessible (HTTP 200). Ready for verified research extraction.")

    # -------------------------------------------------------------------------
    # TAB 2: Submit Verified Price Observation Form
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("Manual Verified Observation Entry")
        st.caption("Record genuine competitor observations. Every entry requires a source URL and is audit-logged.")

        competitors = repo.get_all_competitors()
        emirates = repo.get_all_emirates()
        channels = repo.get_all_channels()
        platforms = repo.get_all_platforms()

        with st.form("manual_price_form", clear_on_submit=False):
            f_col1, f_col2 = st.columns(2)

            with f_col1:
                f_comp = st.selectbox(
                    "Competitor Brand",
                    options=competitors,
                    format_func=lambda c: c["name"],
                )
                f_em = st.selectbox(
                    "Emirate",
                    options=emirates,
                    format_func=lambda e: f"{e['name_en']} ({e['code']})",
                )
                f_ch = st.selectbox(
                    "Ordering Channel",
                    options=channels,
                    format_func=lambda c: c["name"],
                )
                f_pl = st.selectbox(
                    "Ordering Platform",
                    options=platforms,
                    format_func=lambda p: p["name"],
                )

            with f_col2:
                f_prod_name = st.text_input("Product Name", placeholder="e.g. Classic Margherita")
                f_norm_name = st.selectbox(
                    "Canonical Recipe Category",
                    options=["margherita", "pepperoni", "super_supreme", "veggie", "bbq_chicken", "other"],
                    format_func=lambda n: n.replace("_", " ").title(),
                )
                f_size = st.selectbox(
                    "Size",
                    options=["medium", "large", "small", "personal", "xlarge"],
                    format_func=lambda s: s.upper(),
                )
                f_crust = st.text_input("Crust Type", value="Standard / Pan")

            f_col3, f_col4, f_col5 = st.columns(3)
            with f_col3:
                f_price = st.number_input("Price in AED (Mandatory)", min_value=0.0, value=45.0, step=0.5)
            with f_col4:
                f_delivery_fee = st.number_input("Delivery Fee (AED)", min_value=0.0, value=7.0, step=1.0)
            with f_col5:
                f_status = st.selectbox(
                    "Verification Status",
                    options=["verified", "needs_review", "unverified", "unavailable"],
                    format_func=lambda s: s.upper(),
                )

            f_url = st.text_input(
                "Source URL (Mandatory)",
                placeholder="https://www.papajohns.ae/menu/pizza/margherita",
            )
            f_notes = st.text_area(
                "Audit Notes / Evidence Description",
                placeholder="Observed on direct web delivery checkout page for Dubai Marina branch.",
            )

            submit_btn = st.form_submit_button("Record Verified Observation", type="primary", use_container_width=True)

        if submit_btn:
            if not f_url.strip():
                st.error("Error: Source URL is strictly mandatory per project integrity rules.")
            elif not f_prod_name.strip():
                st.error("Error: Product name is required.")
            else:
                try:
                    # 1. Save evidence
                    ev_id = repo.save_evidence(
                        source_url=f_url.strip(),
                        evidence_type="url_log",
                        notes=f_notes,
                    )
                    # 2. Get or create product & variant
                    cat_id = 1  # Pizza category
                    prod_id = repo.get_or_create_product(
                        competitor_id=f_comp["id"],
                        category_id=cat_id,
                        name=f_prod_name.strip(),
                        normalized_name=f_norm_name,
                    )
                    var_id = repo.get_or_create_variant(
                        product_id=prod_id,
                        size_name=f_size.upper(),
                        normalized_size=f_size,
                        crust_type=f_crust.strip(),
                    )
                    # 3. Record price
                    obs_id = repo.record_price_observation(
                        competitor_id=f_comp["id"],
                        product_variant_id=var_id,
                        emirate_id=f_em["id"],
                        channel_id=f_ch["id"],
                        platform_id=f_pl["id"],
                        original_price=float(f_price),
                        currency="AED",
                        delivery_fee=float(f_delivery_fee),
                        source_url=f_url.strip(),
                        evidence_id=ev_id,
                        verification_status=f_status,
                        notes=f_notes,
                    )
                    st.success(f"✓ Observation #{obs_id} successfully recorded and linked to Evidence #{ev_id}.")
                except Exception as e:
                    st.error(f"Failed to record observation: {e}")

    # -------------------------------------------------------------------------
    # TAB 3: Research Runs History
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("Research Runs & Execution Audit Trail")
        runs = repo.get_research_runs(limit=100)
        if runs:
            df_runs = pd.DataFrame(runs)
            display_runs = df_runs[[
                "run_uuid", "status", "competitor_name", "emirate_name", "channel_name",
                "items_extracted", "items_verified", "started_at", "completed_at", "notes"
            ]].copy()
            display_runs.columns = [
                "Run UUID", "Status", "Competitor", "Emirate", "Channel",
                "Extracted", "Verified", "Started At", "Completed At", "Notes"
            ]
            st.dataframe(display_runs, use_container_width=True, height=400)
        else:
            st.info("No research runs logged yet.")
