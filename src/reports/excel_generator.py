"""
Excel Report Generator for UAE Pizza Price Intelligence.
Generates executive-ready, beautifully styled .xlsx workbooks using openpyxl.
"""
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from config import CURRENCY_CODE, EXPORTS_DIR
from src.db.repository import PizzaIntelligenceRepository


class ExcelReportGenerator:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.repo = PizzaIntelligenceRepository(db_path=db_path)

        # Style Definitions
        self.header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        self.title_font = Font(name="Calibri", size=16, bold=True, color="0A192F")
        self.subtitle_font = Font(name="Calibri", size=10, italic=True, color="555555")
        self.bold_font = Font(name="Calibri", size=11, bold=True)
        self.regular_font = Font(name="Calibri", size=11)
        self.kpi_num_font = Font(name="Calibri", size=20, bold=True, color="C8102E")
        self.kpi_lbl_font = Font(name="Calibri", size=9, bold=True, color="333333")

        self.primary_fill = PatternFill(start_color="0A192F", end_color="0A192F", fill_type="solid")  # Navy
        self.accent_fill = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")   # Crimson
        self.zebra_fill = PatternFill(start_color="F8F9FA", end_color="F8F9FA", fill_type="solid")    # Soft gray
        self.kpi_card_fill = PatternFill(start_color="F0F4F8", end_color="F0F4F8", fill_type="solid")

        thin_border = Side(style="thin", color="D0D5DD")
        self.cell_border = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
        self.header_border = Border(bottom=Side(style="medium", color="0A192F"))

    def generate_full_report(self) -> io.BytesIO:
        """
        Builds the complete multi-tab Excel intelligence workbook and returns an in-memory buffer.
        """
        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        # 1. Executive Summary Sheet
        self._build_summary_sheet(wb)

        # 2. Side-by-Side Comparison Matrix Sheet
        self._build_matrix_sheet(wb)

        # 3. Channel Disparity Analysis Sheet
        self._build_channels_sheet(wb)

        # 4. Master Price Observations Sheet (Full Audit Log)
        self._build_observations_sheet(wb)

        # 5. Active Promotions & Deals Sheet
        self._build_promotions_sheet(wb)

        # 6. Competitor & Branch Directory Sheet
        self._build_branches_sheet(wb)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer

    def save_report_to_disk(self, filename: Optional[str] = None) -> Path:
        """
        Saves the generated report to data/exports/ and returns the file path.
        """
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_name = filename or f"UAE_Pizza_Intelligence_Report_{timestamp}.xlsx"
        target_path = EXPORTS_DIR / target_name

        buffer = self.generate_full_report()
        with open(target_path, "wb") as f:
            f.write(buffer.getvalue())

        return target_path

    # -------------------------------------------------------------------------
    # Sheet Builders
    # -------------------------------------------------------------------------
    def _build_summary_sheet(self, wb: openpyxl.Workbook):
        ws = wb.create_sheet(title="Executive Summary")
        ws.views.sheetView[0].showGridLines = True

        # Header Title
        ws["A1"] = "UAE PIZZA PRICE INTELLIGENCE DASHBOARD"
        ws["A1"].font = self.title_font
        ws["A2"] = f"Report Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Benchmark: Pizza Hut UAE"
        ws["A2"].font = self.subtitle_font

        # KPI Metrics
        metrics = self.repo.get_summary_metrics()
        kpis = [
            ("Competitors Tracked", str(metrics["competitors_count"])),
            ("Active Branches", str(metrics["branch_count"])),
            ("Verified Price Records", str(metrics["verified_prices_count"])),
            ("Avg Medium Pizza Price", f"{metrics['avg_medium_pizza_price']:.2f} AED"),
            ("Active Promotions", str(metrics["promotions_count"])),
        ]

        # Draw KPI cards
        for idx, (label, val) in enumerate(kpis):
            col_idx = 1 + idx * 2
            # Value cell
            v_cell = ws.cell(row=4, column=col_idx, value=val)
            v_cell.font = self.kpi_num_font
            v_cell.fill = self.kpi_card_fill
            v_cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.merge_cells(start_row=4, start_column=col_idx, end_row=4, end_column=col_idx + 1)

            # Label cell
            l_cell = ws.cell(row=5, column=col_idx, value=label)
            l_cell.font = self.kpi_lbl_font
            l_cell.fill = self.kpi_card_fill
            l_cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.merge_cells(start_row=5, start_column=col_idx, end_row=5, end_column=col_idx + 1)

        # Average Prices by Size & Competitor Table
        ws["A7"] = "MARKET BENCHMARK: AVERAGE PRICES BY BRAND & SIZE (AED)"
        ws["A7"].font = self.bold_font

        sizes = ["medium", "large"]
        row_cursor = 9
        for s in sizes:
            ws.cell(row=row_cursor, column=1, value=f"{s.upper()} PIZZAS (Average AED)").font = self.bold_font
            row_cursor += 1

            matrix = self.repo.get_price_comparison_matrix(normalized_size=s)
            if not matrix.empty:
                # Headers
                headers = ["Pizza Recipe"] + list(matrix.columns)
                for c_idx, h in enumerate(headers, 1):
                    cell = ws.cell(row=row_cursor, column=c_idx, value=h)
                    cell.font = self.header_font
                    cell.fill = self.primary_fill
                    cell.alignment = Alignment(horizontal="center")
                row_cursor += 1

                for pizza_name, p_row in matrix.iterrows():
                    ws.cell(row=row_cursor, column=1, value=str(pizza_name).replace("_", " ").title()).font = self.regular_font
                    for c_idx, val in enumerate(p_row, 2):
                        v_c = ws.cell(row=row_cursor, column=c_idx, value=val if not pd.isna(val) else "N/A")
                        v_c.alignment = Alignment(horizontal="right")
                        v_c.number_format = '#,##0.00 "AED"'
                    row_cursor += 1
                row_cursor += 2

        self._autofit_columns(ws)

    def _build_matrix_sheet(self, wb: openpyxl.Workbook):
        ws = wb.create_sheet(title="Price Comparison Matrix")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = "SIDE-BY-SIDE COMPETITOR PRICE COMPARISON MATRIX"
        ws["A1"].font = self.title_font
        ws["A2"] = "Direct Delivery Base Prices (AED) across equivalent recipes and sizes"
        ws["A2"].font = self.subtitle_font

        row_cursor = 4
        for s in ["medium", "large"]:
            ws.cell(row=row_cursor, column=1, value=f"{s.upper()} PIZZAS - COMPETITOR COMPARISON").font = self.bold_font
            row_cursor += 1

            matrix = self.repo.get_price_comparison_matrix(normalized_size=s)
            if not matrix.empty:
                headers = ["Canonical Pizza"] + list(matrix.columns)
                for c_idx, h in enumerate(headers, 1):
                    c = ws.cell(row=row_cursor, column=c_idx, value=h)
                    c.font = self.header_font
                    c.fill = self.accent_fill if "Pizza Hut" in h else self.primary_fill
                    c.alignment = Alignment(horizontal="center")
                row_cursor += 1

                for pizza_name, p_row in matrix.iterrows():
                    ws.cell(row=row_cursor, column=1, value=str(pizza_name).replace("_", " ").title()).font = self.bold_font
                    for c_idx, val in enumerate(p_row, 2):
                        cell = ws.cell(row=row_cursor, column=c_idx, value=val if not pd.isna(val) else "-")
                        cell.alignment = Alignment(horizontal="right")
                        if not pd.isna(val):
                            cell.number_format = '#,##0.00 "AED"'
                    row_cursor += 1
                row_cursor += 2

        self._autofit_columns(ws)

    def _build_channels_sheet(self, wb: openpyxl.Workbook):
        ws = wb.create_sheet(title="Channel Disparity")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = "ORDERING CHANNEL DISPARITY: DIRECT VS AGGREGATORS"
        ws["A1"].font = self.title_font
        ws["A2"] = "Price markup observed when ordering via Third-Party Delivery Apps (Talabat) vs Direct Restaurant"
        ws["A2"].font = self.subtitle_font

        headers = ["Competitor", "Product", "Size", "Emirate", "Direct Price", "Aggregator Price", "Markup (AED)", "Markup (%)"]
        row_cursor = 4
        for c_idx, h in enumerate(headers, 1):
            c = ws.cell(row=row_cursor, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.primary_fill
            c.alignment = Alignment(horizontal="center")
        row_cursor += 1

        markups = self.repo.get_channel_markup_analysis()
        for m in markups:
            ws.cell(row=row_cursor, column=1, value=m["competitor"])
            ws.cell(row=row_cursor, column=2, value=m["product"])
            ws.cell(row=row_cursor, column=3, value=m["size"])
            ws.cell(row=row_cursor, column=4, value=m["emirate"])
            
            c5 = ws.cell(row=row_cursor, column=5, value=m["direct_price"])
            c5.number_format = '#,##0.00 "AED"'
            c6 = ws.cell(row=row_cursor, column=6, value=m["aggregator_price"])
            c6.number_format = '#,##0.00 "AED"'
            c7 = ws.cell(row=row_cursor, column=7, value=m["markup_aed"])
            c7.number_format = '+#,##0.00 "AED";-#,##0.00 "AED"'
            c8 = ws.cell(row=row_cursor, column=8, value=m["markup_pct"] / 100.0)
            c8.number_format = "0.0%"

            row_cursor += 1

        self._autofit_columns(ws)

    def _build_observations_sheet(self, wb: openpyxl.Workbook):
        ws = wb.create_sheet(title="Price Observations")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = "AUTHENTIC PRICE OBSERVATIONS MASTER AUDIT LOG"
        ws["A1"].font = self.title_font
        ws["A2"] = f"Complete audit trail of verified price observations with genuine source URLs (Currency: {CURRENCY_CODE})"
        ws["A2"].font = self.subtitle_font

        headers = [
            "Obs ID", "Competitor", "Product Name", "Size", "Crust", "Emirate",
            "Channel", "Platform", "Price (AED)", "Delivery Fee", "Status",
            "Collected At", "Source URL"
        ]
        row_cursor = 4
        for c_idx, h in enumerate(headers, 1):
            c = ws.cell(row=row_cursor, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.primary_fill
            c.alignment = Alignment(horizontal="center")
        row_cursor += 1

        observations = self.repo.get_price_observations(limit=1000)
        for idx, obs in enumerate(observations):
            fill = self.zebra_fill if idx % 2 == 1 else None

            cells = [
                ws.cell(row=row_cursor, column=1, value=obs["id"]),
                ws.cell(row=row_cursor, column=2, value=obs["competitor_name"]),
                ws.cell(row=row_cursor, column=3, value=obs["product_name"]),
                ws.cell(row=row_cursor, column=4, value=obs["size_name"]),
                ws.cell(row=row_cursor, column=5, value=obs["crust_type"]),
                ws.cell(row=row_cursor, column=6, value=obs["emirate_name"]),
                ws.cell(row=row_cursor, column=7, value=obs["channel_name"]),
                ws.cell(row=row_cursor, column=8, value=obs["platform_name"]),
                ws.cell(row=row_cursor, column=9, value=obs["original_price"]),
                ws.cell(row=row_cursor, column=10, value=obs["delivery_fee"]),
                ws.cell(row=row_cursor, column=11, value=obs["verification_status"].upper()),
                ws.cell(row=row_cursor, column=12, value=obs["collected_at"][:19].replace("T", " ")),
                ws.cell(row=row_cursor, column=13, value=obs["source_url"]),
            ]

            cells[8].number_format = '#,##0.00 "AED"'
            cells[9].number_format = '#,##0.00 "AED"'

            if fill:
                for cell in cells:
                    cell.fill = fill

            row_cursor += 1

        self._autofit_columns(ws)

    def _build_promotions_sheet(self, wb: openpyxl.Workbook):
        ws = wb.create_sheet(title="Active Promotions")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = "UAE COMPETITOR ACTIVE PROMOTIONS & DEALS"
        ws["A1"].font = self.title_font
        ws["A2"] = "Tracked combo offers, BOGO deals, and coupon codes"
        ws["A2"].font = self.subtitle_font

        headers = ["ID", "Competitor", "Promotion Title", "Type", "Promo Code", "Discount Value", "Description", "Source URL"]
        row_cursor = 4
        for c_idx, h in enumerate(headers, 1):
            c = ws.cell(row=row_cursor, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.primary_fill
            c.alignment = Alignment(horizontal="center")
        row_cursor += 1

        promos = self.repo.get_promotions()
        for p in promos:
            disc_str = f"{p['discount_amount']} AED" if p['discount_amount'] else (f"{p['discount_percentage']}%" if p['discount_percentage'] else "Combo deal")
            ws.cell(row=row_cursor, column=1, value=p["id"])
            ws.cell(row=row_cursor, column=2, value=p["competitor_name"])
            ws.cell(row=row_cursor, column=3, value=p["title"]).font = self.bold_font
            ws.cell(row=row_cursor, column=4, value=p["promo_type"].upper())
            ws.cell(row=row_cursor, column=5, value=p["promo_code"] or "N/A")
            ws.cell(row=row_cursor, column=6, value=disc_str)
            ws.cell(row=row_cursor, column=7, value=p["description"])
            ws.cell(row=row_cursor, column=8, value=p["source_url"])
            row_cursor += 1

        self._autofit_columns(ws)

    def _build_branches_sheet(self, wb: openpyxl.Workbook):
        ws = wb.create_sheet(title="Competitor Branches")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = "UAE PIZZA STORE & BRANCH DIRECTORY"
        ws["A1"].font = self.title_font
        ws["A2"] = "Physical store locations tracked across all 7 UAE Emirates"
        ws["A2"].font = self.subtitle_font

        headers = ["Branch ID", "Brand", "Emirate", "Branch Name", "Area", "Address", "Contact Phone"]
        row_cursor = 4
        for c_idx, h in enumerate(headers, 1):
            c = ws.cell(row=row_cursor, column=c_idx, value=h)
            c.font = self.header_font
            c.fill = self.primary_fill
            c.alignment = Alignment(horizontal="center")
        row_cursor += 1

        locations = self.repo.get_locations()
        for loc in locations:
            ws.cell(row=row_cursor, column=1, value=loc["id"])
            ws.cell(row=row_cursor, column=2, value=loc["competitor_name"])
            ws.cell(row=row_cursor, column=3, value=loc["emirate_name"])
            ws.cell(row=row_cursor, column=4, value=loc["branch_name"]).font = self.bold_font
            ws.cell(row=row_cursor, column=5, value=loc["area"] or "")
            ws.cell(row=row_cursor, column=6, value=loc["address"] or "")
            ws.cell(row=row_cursor, column=7, value=loc["phone"] or "")
            row_cursor += 1

        self._autofit_columns(ws)

    def _autofit_columns(self, ws: openpyxl.worksheet.worksheet.Worksheet):
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                # Skip merged or very long title cells
                if cell.row in [1, 2]:
                    continue
                val = str(cell.value or "")
                if len(val) > max_len:
                    max_len = len(val)
            adjusted_width = min(max(max_len + 3, 12), 45)
            ws.column_dimensions[col_letter].width = adjusted_width
