"""
Source Evidence Vault & Cryptographic Audit Explorer View.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_evidence_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Evidence Vault & Audit Trail",
        subtitle="Cryptographic proof, HTTP response hashes, timestamps, and verifiable source URLs",
    )

    evidence_records = repo.get_evidence_records(limit=200)

    if not evidence_records:
        st.info("No evidence records currently logged in the vault.")
        return

    # Metrics
    total_ev = len(evidence_records)
    total_linked = sum(e["linked_prices_count"] for e in evidence_records)
    linked_evidence_count = sum(bool(e["linked_prices_count"]) for e in evidence_records)
    avg_linked = total_linked / total_ev if total_ev > 0 else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Evidence Artifacts</div>
                <div class="kpi-value">{total_ev}</div>
                <div class="kpi-sub">Cryptographic log entries</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Linked Observations</div>
                <div class="kpi-value">{total_linked}</div>
                <div class="kpi-sub">Price records linked to captured artifacts</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""<div class="kpi-container">
                <div class="kpi-title">Audit Coverage Ratio</div>
                <div class="kpi-value">{linked_evidence_count / max(total_ev, 1) * 100:.0f}%</div>
                <div class="kpi-sub">Evidence records linked to an observation</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Evidence Table
    st.subheader("📜 Evidence Artifacts Master Log")
    df_ev = pd.DataFrame(evidence_records)[[
        "id", "evidence_type", "http_status", "captured_at",
        "linked_prices_count", "source_url", "file_hash_sha256", "notes"
    ]].copy()
    df_ev.columns = [
        "Evidence ID", "Type", "HTTP Status", "Captured At",
        "Linked Prices", "Source URL", "SHA-256 Hash", "Notes"
    ]
    st.dataframe(df_ev, use_container_width=True, height=320)

    st.divider()

    # Evidence Deep Inspector
    st.subheader("🔍 Deep Evidence Inspector")
    ev_ids = [e["id"] for e in evidence_records]
    sel_id = st.selectbox(
        "Select Evidence Record to Inspect",
        options=ev_ids,
        format_func=lambda eid: f"Evidence #{eid} - {next((e['source_url'] for e in evidence_records if e['id'] == eid), '')}",
    )

    ev_item = next(e for e in evidence_records if e["id"] == sel_id)

    detail_col1, detail_col2 = st.columns(2)
    with detail_col1:
        st.markdown(f"**Evidence ID:** `{ev_item['id']}`")
        st.markdown(f"**Evidence Type:** `{ev_item['evidence_type']}`")
        st.markdown(f"**HTTP Response Status:** `{ev_item['http_status']}`")
        st.markdown(f"**Capture Timestamp:** `{ev_item['captured_at']}`")
        st.markdown(f"**Linked Prices Count:** `{ev_item['linked_prices_count']}`")
    with detail_col2:
        st.markdown(f"**Target URL:** [{ev_item['source_url']}]({ev_item['source_url']})")
        st.markdown(f"**SHA-256 Checksum:**")
        st.code(ev_item["file_hash_sha256"] or "N/A", language="text")
        st.markdown(f"**Audit Notes:** {ev_item['notes'] or 'None'}")

    artifact = repo.get_evidence_artifact(sel_id)
    if artifact and artifact["content"] is not None:
        file_name = Path(artifact.get("file_path") or f"evidence-{sel_id}.bin").name
        st.download_button(
            "Download captured evidence",
            data=artifact["content"],
            file_name=file_name,
            mime="text/html" if file_name.lower().endswith((".html", ".htm")) else "application/octet-stream",
            key=f"download_evidence_{sel_id}",
        )
    else:
        st.info("This record has no retained file artifact; its source URL and capture metadata remain available.")

    # Linked Observations Sub-table
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"##### Price Observations Certified by Evidence #{ev_item['id']}")
    linked_obs = repo.get_price_observations(limit=50)
    linked_to_this = [o for o in linked_obs if o.get("evidence_id") == sel_id]
    if linked_to_this:
        df_linked = pd.DataFrame(linked_to_this)[[
            "id", "competitor_name", "product_name", "size_name",
            "emirate_name", "channel_name", "original_price", "verification_status"
        ]].copy()
        df_linked.columns = ["Obs ID", "Brand", "Product", "Size", "Emirate", "Channel", "Price AED", "Status"]
        st.dataframe(df_linked, use_container_width=True)
    else:
        st.info("No price observations currently linked directly to this specific evidence record.")
