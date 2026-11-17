"""
Human Review & Quality Assurance Queue View.
Allows QA analysts to inspect, verify, flag, update, or remove price observations.
"""
from datetime import datetime, timezone
import hashlib
import re
import pandas as pd
import streamlit as st

from config import EVIDENCE_DIR
from src.matching.accuracy_engine import AccuracyEngine
from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_review_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="QA & Review Queue",
        subtitle="Human verification workflow, price anomaly inspection, and audit certification",
    )

    metrics = repo.get_summary_metrics()

    # Status summary tiles
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Pending Review</div>
                <div class="kpi-value" style="color:#D97706;">{metrics['needs_review_count']}</div>
                <div class="kpi-sub">Items requiring verification</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Verified Records</div>
                <div class="kpi-value" style="color:#059669;">{metrics['verified_prices_count']}</div>
                <div class="kpi-sub">Audit-certified observations</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Total Records</div>
                <div class="kpi-value">{metrics['total_prices_count']}</div>
                <div class="kpi-sub">Database observation rows</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c4:
        # Action button to inject a test review observation
        st.write("&nbsp;")
        if st.button("➕ Inject Test Item to Review", use_container_width=True):
            comp = repo.get_competitor_by_code("dominos")
            emirates = repo.get_all_emirates()
            channels = repo.get_all_channels()
            platforms = repo.get_all_platforms()

            cat_id = 1
            p_id = repo.get_or_create_product(comp["id"], cat_id, "Test ExtravaganZZa Special", "super_supreme")
            v_id = repo.get_or_create_variant(p_id, "Large", "large", "Pan")
            ev_id = repo.save_evidence("https://www.dominos.ae/en/pages/order/menu", notes="Simulated capture for QA test")

            obs_id = repo.record_price_observation(
                competitor_id=comp["id"],
                product_variant_id=v_id,
                emirate_id=emirates[0]["id"],
                channel_id=channels[0]["id"],
                platform_id=platforms[0]["id"],
                original_price=69.50,
                currency="AED",
                source_url="https://www.dominos.ae/en/pages/order/menu",
                evidence_id=ev_id,
                verification_status="needs_review",
                notes="Uncertain discount match - flagged for QA review.",
            )
            st.success(f"Added observation #{obs_id} to Needs Review queue.")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Filter selector
    filter_status = st.radio(
        "Queue Filter",
        options=["needs_review", "unverified", "verified", "all"],
        format_func=lambda s: {
            "needs_review": "⚠️ Needs Review Queue",
            "unverified": "❓ Unverified Queue",
            "verified": "✓ Verified Records",
            "all": "📑 All Records",
        }[s],
        horizontal=True,
        index=0 if metrics["needs_review_count"] > 0 else 3,
    )

    status_param = None if filter_status == "all" else [filter_status]
    observations = repo.get_price_observations(verification_statuses=status_param, limit=100)

    if not observations:
        st.info(f"No records currently in '{filter_status}' queue.")
        return

    st.subheader(f"Items in Queue ({len(observations)} records)")

    # Display table
    df_disp = pd.DataFrame(observations)[[
        "id", "competitor_name", "product_name", "category_name", "size_name", "emirate_name",
        "channel_name", "original_price", "verification_status", "source_url", "notes"
    ]].copy()
    df_disp.columns = [
        "Obs ID", "Brand", "Product", "Category", "Size", "Emirate",
        "Channel", "Price (AED)", "Status", "Source URL", "Notes"
    ]
    st.dataframe(df_disp, use_container_width=True, height=280)

    st.divider()

    # QA Action Panel
    st.subheader("🛠️ QA Decision & Action Console")
    obs_ids = [o["id"] for o in observations]
    sel_obs_id = st.selectbox(
        "Select Observation ID to Review",
        options=obs_ids,
        format_func=lambda oid: f"Observation #{oid} - {next((o['competitor_name'] + ' ' + o['product_name'] + ' (' + str(o['original_price']) + ' AED)' for o in observations if o['id'] == oid), '')}",
    )

    target_obs = next(o for o in observations if o["id"] == sel_obs_id)

    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.markdown(f"**Brand:** {target_obs['competitor_name']}")
        st.markdown(f"**Product:** {target_obs['product_name']} ({target_obs['size_name']})")
        st.markdown(f"**Category:** {target_obs['category_name']}")
        st.markdown(f"**Location / Emirate:** {target_obs['emirate_name']}")
        st.markdown(f"**Current Price:** **{target_obs['original_price']:.2f} AED**")
    with info_col2:
        st.markdown(f"**Current Status:** `{target_obs['verification_status'].upper()}`")
        st.markdown(f"**Source URL:** [{target_obs['source_url']}]({target_obs['source_url']})")
        st.markdown(f"**Collection Time:** {target_obs['collected_at']}")
        st.markdown(f"**Notes:** {target_obs['notes'] or 'None'}")

    st.markdown("<br>", unsafe_allow_html=True)

    action_col1, action_col2, action_col3, action_col4 = st.columns(4)

    quarantined = bool(target_obs.get("is_quarantined"))
    with action_col1:
        if st.button("✓ Approve & Verify", type="primary", use_container_width=True, disabled=quarantined):
            try:
                revision_id = repo.update_observation_status(sel_obs_id, "verified", notes="QA Analyst verified against captured source evidence.")
                st.success(f"Added verified revision #{revision_id}; source observation #{sel_obs_id} is preserved.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    with action_col2:
        if st.button("⚠️ Flag Needs Review", use_container_width=True, disabled=quarantined):
            revision_id = repo.update_observation_status(sel_obs_id, "needs_review", notes="Flagged by QA for further verification.")
            st.warning(f"Added review revision #{revision_id}; source observation #{sel_obs_id} is preserved.")
            st.rerun()

    with action_col3:
        if st.button("🚫 Mark Unavailable", use_container_width=True, disabled=quarantined):
            revision_id = repo.update_observation_status(sel_obs_id, "unavailable", notes="Item verified out of stock or branch closed.")
            st.info(f"Added unavailable revision #{revision_id}; source observation #{sel_obs_id} is preserved.")
            st.rerun()

    with action_col4:
        with st.popover("✏️ Append Price Correction"):
            new_p = st.number_input("Corrected Price (AED)", value=float(target_obs["original_price"]), step=0.5)
            edit_note = st.text_input("Correction Reason", value="Price corrected per live menu inspection.")
            correction_capture = st.file_uploader(
                "Correction source capture (required)",
                type=["png", "jpg", "jpeg", "webp", "html", "json"],
                key=f"correction_capture_{sel_obs_id}",
            )
            if st.button("Add Correction Revision", use_container_width=True, disabled=quarantined or correction_capture is None):
                EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
                safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", correction_capture.name)
                path = EVIDENCE_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{safe_name}"
                content = correction_capture.getvalue()
                path.write_bytes(content)
                digest = hashlib.sha256(content).hexdigest()
                source_evidence_id = repo.save_evidence(
                    source_url=target_obs["source_url"],
                    evidence_type="screenshot" if safe_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else "html_snapshot",
                    file_path=str(path),
                    file_hash_sha256=digest,
                    notes=f"Price correction evidence for observation #{sel_obs_id}",
                )
                result = AccuracyEngine(repo.db_path).apply_human_correction(
                    observation_id=sel_obs_id,
                    corrected_price=float(new_p),
                    reason=edit_note,
                    evidence_id=source_evidence_id,
                )
                st.success(f"Added verified correction revision #{result['revision_observation_id']}; original observation remains unchanged.")
                st.rerun()
