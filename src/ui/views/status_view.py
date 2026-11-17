"""
System Diagnostics, Integrity Health & Maintenance View.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

from config import DEFAULT_DB_PATH
from src.db.connection import get_connection
from src.db.repository import PizzaIntelligenceRepository
from src.db.init_db import initialize_database
from src.db.validator import DatabaseValidator
from src.ui.styles import render_brand_header


def render_status_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="System Status & Diagnostics",
        subtitle="Automated database validation, foreign key audits, storage metrics, and maintenance controls",
    )

    validator = DatabaseValidator(repo.db_path)
    report = validator.validate_all()

    # Status Banner
    is_pass = report["status"] == "PASS"
    status_bg = "#ECFDF5" if is_pass else "#FEF2F2"
    status_border = "#A7F3D0" if is_pass else "#FECACA"
    status_color = "#065F46" if is_pass else "#991B1B"
    symbol = "✓" if is_pass else "✗"

    st.markdown(
        f"""
        <div style="background:{status_bg}; border:1px solid {status_border}; padding:18px 22px; border-radius:10px; margin-bottom:24px;">
            <h3 style="color:{status_color}; margin:0; font-size:1.3rem;">
                {symbol} System Integrity Status: {report['status']}
            </h3>
            <p style="color:#475569; margin:4px 0 0 0; font-size:0.9rem;">
                Database: <code>{report['db_path']}</code>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Individual Checks Grid
    st.subheader("Integrity Verification Matrix")
    c1, c2, c3, c4, c5 = st.columns(5)

    check_cols = [c1, c2, c3, c4, c5]
    check_names = ["tables", "foreign_keys", "emirates", "ordering_channels", "price_integrity"]

    for col, name in zip(check_cols, check_names):
        check_obj = report["checks"].get(name, {})
        passed = check_obj.get("passed", False)
        pass_txt = "PASSED" if passed else "FAILED"
        pass_clr = "#059669" if passed else "#DC2626"

        with col:
            st.markdown(
                f"""
                <div class="kpi-container">
                    <div class="kpi-title">{name.replace('_', ' ').title()}</div>
                    <div class="kpi-value" style="font-size:1.3rem; color:{pass_clr};">{pass_txt}</div>
                    <div class="kpi-sub">Constraint Check</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    # Database Table Storage Breakdown
    st.subheader("📊 Database Table Storage & Row Counts")
    conn = get_connection(repo.db_path)
    cursor = conn.cursor()

    tables = [
        "competitors", "emirates", "locations", "ordering_channels", "ordering_platforms",
        "categories", "products", "product_variants", "research_runs", "evidence_records",
        "price_observations", "promotions"
    ]

    table_data = []
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t};")
            cnt = cursor.fetchone()[0]
            table_data.append({"Table Name": t, "Row Count": cnt, "Type": "Master" if "price" not in t and "evidence" not in t else "Audit Log"})
        except Exception as e:
            table_data.append({"Table Name": t, "Row Count": f"Error: {e}", "Type": "Unknown"})

    conn.close()

    db_file = Path(repo.db_path or DEFAULT_DB_PATH)
    file_size_kb = db_file.stat().st_size / 1024 if db_file.exists() else 0

    st.write(f"**Database File Size on Disk:** `{file_size_kb:.1f} KB`")
    st.dataframe(pd.DataFrame(table_data), use_container_width=True)

    st.divider()

    # Database Maintenance Console
    st.subheader("⚙️ Database Maintenance Console")
    with st.expander("Master Reference Data Maintenance"):
        st.caption("This updates reference tables only. Existing observations, evidence, and benchmarks are preserved.")
        if st.button("Refresh master reference data"):
            with st.spinner("Refreshing master reference data..."):
                initialize_database(db_path=repo.db_path, reset=False)
            st.success("Master reference data refreshed; recorded research rows were left in place.")
            st.rerun()
