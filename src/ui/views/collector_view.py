"""
Research Runs, Live URL Auditor & Price Collector View.
"""
from datetime import datetime, timezone
import hashlib
import re
import pandas as pd
import streamlit as st

from config import EVIDENCE_DIR
from src.db.repository import PizzaIntelligenceRepository
from src.scrapers.genuine_collector import GenuineResearchCollector
from src.ui.styles import render_brand_header


def render_collector_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Research & Collection Hub",
        subtitle="Live URL auditing, genuine price collection runs, and research session logs",
    )

    collector = GenuineResearchCollector(db_path=repo.db_path)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🌐 Live URL Auditor & Target Prober",
        "📝 Submit Price Observation",
        "📜 Research Runs History",
        "🍕 Pizza Hut UAE Menu",
        "🎯 Benchmarks & Accuracy",
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
                value="https://www.pizzahut-me.com/fullmenu/pizzas-country-AE",
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
                categories = repo.get_all_categories()
                f_category = st.selectbox(
                    "Product Category",
                    options=categories,
                    format_func=lambda c: c["name"],
                )

            with f_col2:
                f_prod_name = st.text_input("Product Name", placeholder="e.g. Classic Margherita")
                f_norm_name = st.selectbox(
                    "Canonical Product Match Key",
                    options=["margherita", "pepperoni", "super_supreme", "veggie", "bbq_chicken", "other"],
                    format_func=lambda n: n.replace("_", " ").title(),
                    index=5,
                )
                if f_category["code"] == "pizza":
                    f_size = st.selectbox(
                        "Pizza Size",
                        options=["small", "medium", "large", "personal", "xlarge"],
                        format_func=lambda s: s.upper(),
                    )
                    f_crust = st.text_input("Crust (as shown by source)", value="Not stated")
                else:
                    f_size = "other"
                    f_crust = "Not applicable"
                    st.caption("Size and crust are not assigned to non-pizza products.")

            f_col3, f_col4, f_col5 = st.columns(3)
            with f_col3:
                f_price = st.number_input("Price in AED (Mandatory)", min_value=0.0, value=45.0, step=0.5)
            with f_col4:
                f_delivery_fee = st.number_input("Delivery Fee (AED)", min_value=0.0, value=7.0, step=1.0)
            with f_col5:
                f_status = st.selectbox(
                    "Verification Status",
                    options=["needs_review", "unverified", "unavailable", "verified"],
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
            f_evidence = st.file_uploader(
                "Source capture (screenshot or saved page; required for verified status)",
                type=["png", "jpg", "jpeg", "webp", "html", "json"],
            )

            submit_btn = st.form_submit_button("Record Observation for QA", type="primary", use_container_width=True)

        if submit_btn:
            if not f_url.strip():
                st.error("Error: Source URL is strictly mandatory per project integrity rules.")
            elif not f_prod_name.strip():
                st.error("Error: Product name is required.")
            else:
                try:
                    # 1. Save evidence
                    evidence_path = None
                    evidence_hash = None
                    evidence_type = "url_log"
                    if f_evidence is not None:
                        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
                        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f_evidence.name)
                        evidence_path = EVIDENCE_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{safe_name}"
                        evidence_bytes = f_evidence.getvalue()
                        evidence_path.write_bytes(evidence_bytes)
                        evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
                        evidence_type = "screenshot" if safe_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else "html_snapshot"
                    selected_status = f_status
                    if selected_status == "verified" and not evidence_hash:
                        selected_status = "needs_review"
                    ev_id = repo.save_evidence(
                        source_url=f_url.strip(),
                        evidence_type=evidence_type,
                        file_path=str(evidence_path) if evidence_path else None,
                        file_hash_sha256=evidence_hash,
                        notes=f_notes,
                    )
                    # 2. Get or create product & variant
                    prod_id = repo.get_or_create_product(
                        competitor_id=f_comp["id"],
                        category_id=f_category["id"],
                        name=f_prod_name.strip(),
                        normalized_name=f_norm_name,
                    )
                    var_id = repo.get_or_create_variant(
                        product_id=prod_id,
                        size_name=f_size.upper() if f_size != "other" else "Not applicable",
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
                        verification_status=selected_status,
                        notes=f_notes,
                        data_origin="manual_entry",
                    )
                    st.success(f"Observation #{obs_id} recorded as {selected_status.upper()} and linked to Evidence #{ev_id}.")
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

    with tab4:
        st.subheader("Pizza Hut UAE public pizza menu extraction")
        st.caption(
            "Reads the public regional menu and saves page snapshots. It does not place an order or claim branch-specific checkout prices. "
            "Every extracted item enters QA as needs_review."
        )
        st.markdown(
            "Sources: [official regional menu](https://www.pizzahut-me.com/fullmenu/pizzas-country-AE) · "
            "[official online ordering](https://uae.pizzahut.me/en/home)"
        )
        emirates = repo.get_all_emirates()
        selected_emirate = st.selectbox(
            "Emirate context for QA",
            options=emirates,
            format_func=lambda e: f"{e['name_en']} ({e['code']})",
            key="pizzahut_menu_emirate",
        )
        if st.button("Run now — collect Pizza Hut UAE public menu", type="primary"):
            from src.scrapers.pizzahut_scraper import PizzaHutMenuScraper
            try:
                with st.spinner("Capturing public menu pages and prices…"):
                    result = PizzaHutMenuScraper(db_path=repo.db_path).run_live_extraction(selected_emirate["code"])
                st.info(
                    f"Run {result['status']}: {result['items_extracted']} price variants extracted, "
                    f"{result['items_verified']} verified. Run ID: {result['run_uuid']}. All extracted rows require QA."
                )
                if result.get("errors"):
                    st.warning("\n".join(result["errors"]))
            except Exception as exc:
                st.error(f"Collection failed ({type(exc).__name__}). Check System Status and the research run log.")

        from src.db.validator import DatabaseValidator
        audit = DatabaseValidator(repo.db_path).validate_all()["checks"]["live_observation_quality"]
        st.markdown("#### Existing live extraction audit (read only)")
        st.caption("This audit flags suspicious mappings without changing any stored observation or verification label.")
        audit_col1, audit_col2 = st.columns(2)
        audit_col1.metric("Type/variant flags", audit["suspect_count"], help=f"{audit['live_extraction_count']} total live_extraction rows")
        audit_col2.metric("Verified labels without a QA revision", audit["unreviewed_verified_labels"])
        if audit["suspect_observations"]:
            st.dataframe(pd.DataFrame(audit["suspect_observations"]), use_container_width=True, height=300)
        else:
            st.success("No obvious product-type or evidence issues found in live extraction rows.")

    with tab5:
        from src.matching.accuracy_engine import AccuracyEngine
        from src.matching.benchmark_service import add_verified_benchmark, get_all_benchmarks

        st.subheader("Evidence-backed manual benchmark cases")
        st.caption(
            "Older benchmark rows remain stored, but the evaluator treats them as uncertain until a reviewer creates a new case linked to a captured source artifact."
        )
        evidence_records = [
            item for item in repo.get_evidence_records(limit=500)
            if item.get("file_hash_sha256") or item.get("file_path")
        ]
        with st.form("benchmark_case_form"):
            bm_comp = st.selectbox("Competitor", competitors, format_func=lambda item: item["name"], key="bm_comp")
            bm_product = st.text_input("Exact product name")
            bm_canonical = st.text_input("Canonical match key", placeholder="margherita")
            bm_size = st.selectbox("Size", ["small", "medium", "large", "personal", "xlarge", "other"], key="bm_size")
            bm_channel = st.selectbox("Ordering channel", channels, format_func=lambda item: item["name"], key="bm_channel")
            bm_emirate = st.selectbox("Emirate", emirates, format_func=lambda item: item["name_en"], key="bm_emirate")
            bm_price = st.number_input("Observed price (AED)", min_value=0.0, step=0.5, key="bm_price")
            bm_url = st.text_input("Exact source URL", key="bm_url")
            bm_evidence = st.selectbox(
                "Captured evidence for this URL",
                options=evidence_records,
                format_func=lambda item: f"#{item['id']} · {item['source_url']} · {item['captured_at']}",
                index=0 if evidence_records else None,
                disabled=not evidence_records,
                key="bm_evidence",
            )
            bm_reviewer = st.text_input("Reviewer")
            bm_notes = st.text_area("Review notes")
            add_benchmark = st.form_submit_button("Add benchmark case")
        if add_benchmark:
            if not evidence_records or bm_evidence is None:
                st.error("Capture a screenshot or saved source page before adding a benchmark.")
            else:
                try:
                    benchmark_id = add_verified_benchmark(
                        competitor_id=bm_comp["id"], product_name=bm_product,
                        normalized_name=bm_canonical, normalized_size=bm_size,
                        channel_id=bm_channel["id"], emirate_id=bm_emirate["id"],
                        expected_price=float(bm_price), source_url=bm_url.strip(),
                        evidence_id=bm_evidence["id"], verified_by=bm_reviewer,
                        db_path=repo.db_path, notes=bm_notes,
                    )
                    st.success(f"Added benchmark case #{benchmark_id}; it is append-only and ready for evaluation.")
                except (ValueError, Exception) as exc:
                    st.error(f"Benchmark was not added: {exc}")

        if st.button("Evaluate latest observations against reviewed benchmarks", type="primary"):
            result = AccuracyEngine(repo.db_path).evaluate_collection_accuracy()
            st.session_state["latest_accuracy_evaluation"] = result
        result = st.session_state.get("latest_accuracy_evaluation")
        if result:
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Accuracy", f"{result['accuracy_percentage']}%" if result["accuracy_percentage"] is not None else "—")
            m2.metric("Correct", result["correct_count"])
            m3.metric("Incorrect", result["incorrect_count"])
            m4.metric("Missing", result["missing_count"])
            m5.metric("Uncertain", result["uncertain_count"])
            if result["cases"]:
                st.dataframe(pd.DataFrame(result["cases"]), use_container_width=True, height=300)
            else:
                st.info("No benchmark cases have been created yet; no accuracy percentage is available.")
