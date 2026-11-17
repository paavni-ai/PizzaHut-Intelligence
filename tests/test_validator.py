"""
Unit tests for the Database Integrity Validator.
"""
import tempfile
import unittest
from pathlib import Path

from src.db.connection import get_connection
from src.db.init_db import initialize_database
from src.db.validator import DatabaseValidator


class TestDatabaseValidator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_pizza_val.db"
        initialize_database(self.db_path)
        self.validator = DatabaseValidator(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_initialized_db_passes(self):
        report = self.validator.validate_all()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(report["errors"]), 0)
        self.assertTrue(report["checks"]["tables"]["passed"])
        self.assertTrue(report["checks"]["foreign_keys"]["passed"])
        self.assertTrue(report["checks"]["emirates"]["passed"])
        self.assertTrue(report["checks"]["ordering_channels"]["passed"])
        self.assertTrue(report["checks"]["price_integrity"]["passed"])

    def test_missing_table_fails_validation(self):
        conn = get_connection(self.db_path)
        conn.execute("DROP TABLE promotions;")
        conn.close()

        report = self.validator.validate_all()
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["checks"]["tables"]["passed"])
        self.assertIn("promotions", report["checks"]["tables"]["missing_tables"])

    def test_missing_emirate_fails_validation(self):
        conn = get_connection(self.db_path)
        conn.execute("DELETE FROM emirates WHERE code = 'DXB';")
        conn.commit()
        conn.close()

        report = self.validator.validate_all()
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["checks"]["emirates"]["passed"])
        self.assertIn("DXB", report["checks"]["emirates"]["missing"])


if __name__ == "__main__":
    unittest.main()
