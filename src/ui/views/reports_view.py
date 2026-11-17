"""
Excel Report Exporter & Data Download View.
"""
from datetime import datetime
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.reports.excel_generator import ExcelReportGenerator
from src.ui.styles import render_brand_header


def render_reports_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Executive Reports & Export",
        subtitle="Generate formatted multi-sheet Excel intelligence workbooks and audit datasets",
    )

    generator = ExcelReportGenerator(db_path=repo.db_path)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")

    col_info, col_export = st.columns([3, 2])

    with col_info:
        st.subheader("📑 Commercial Excel Workbook Package")
        st.markdown("""
        The generated spreadsheet includes **6 dedicated, styled worksheets**:
        
        1. **Executive Summary**: High-level KPIs, market benchmarks, and average prices by brand & size.
        2. **Price Comparison Matrix**: Side-by-side pizza pricing with Pizza Hut UAE benchmark gaps.
        3. **Channel Disparity**: Direct restaurant delivery vs. Aggregator (Talabat / Deliveroo) price markups.
        4. **Price Observations Log**: Full audit trail with source URLs, collection timestamps, and verification flags.
        5. **Active Promotions**: Tracked combo deals, BOGO offers, and discount codes.
        6. **Competitor & Branch Directory**: Comprehensive branch location directory across all 7 UAE Emirates.
        """)

    with col_export:
        st.subheader("📥 Export Downloads")
        st.markdown("<br>", unsafe_allow_html=True)

        # Excel Download
        excel_filename = f"UAE_Pizza_Intelligence_{timestamp_str}.xlsx"
        try:
            excel_bytes = generator.generate_full_report()
            st.download_button(
                label="📊 Download Complete Excel Workbook (.xlsx)",
                data=excel_bytes,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Error generating Excel workbook: {e}")

        st.write("")

        # CSV Download
        obs_df = repo.get_price_observations_df(limit=2000)
        if not obs_df.empty:
            csv_data = obs_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📄 Export Raw Price Observations (.csv)",
                data=csv_data,
                file_name=f"UAE_Price_Observations_{timestamp_str}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.divider()

    # Live Preview of Data
    st.subheader("👁️ Preview: Master Price Observations Sample")
    if not obs_df.empty:
        st.dataframe(obs_df.head(25), use_container_width=True, height=350)
