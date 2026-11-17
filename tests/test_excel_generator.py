"""
Unit tests for the Excel Report Generator.
"""
import io
import tempfile
import unittest
from pathlib import Path
import openpyxl

from src.db.init_db import initialize_database
from src.reports.excel_generator import ExcelReportGenerator


class TestExcelReportGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_excel.db"
        initialize_database(self.db_path)
        self.generator = ExcelReportGenerator(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_full_report_stream(self):
        stream = self.generator.generate_full_report()
        self.assertIsInstance(stream, io.BytesIO)
        self.assertGreater(stream.getbuffer().nbytes, 5000)

        # Validate sheets
        wb = openpyxl.load_workbook(stream)
        expected_sheets = [
            "Executive Summary",
            "Price Comparison Matrix",
            "Channel Disparity",
            "Price Observations",
            "Active Promotions",
            "Competitor Branches",
        ]
        for sheet_name in expected_sheets:
            self.assertIn(sheet_name, wb.sheetnames)

        # Verify summary sheet has title
        ws_sum = wb["Executive Summary"]
        self.assertIn("UAE PIZZA PRICE INTELLIGENCE", ws_sum["A1"].value)

    def test_save_report_to_disk(self):
        out_file = Path(self.temp_dir.name) / "custom_report.xlsx"
        buffer = self.generator.generate_full_report()
        with open(out_file, "wb") as f:
            f.write(buffer.getvalue())
        self.assertTrue(out_file.exists())
        self.assertGreater(out_file.stat().st_size, 5000)


if __name__ == "__main__":
    unittest.main()
