"""Read-only database health report tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.db.health import COUNT_TABLES, check_database_health
from src.db.init_db import initialize_database
from src.db.migrate import run_database_migration


class TestDatabaseHealth(unittest.TestCase):
    def test_sqlite_health_reports_backend_tables_and_counts_without_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "health.sqlite"
            initialize_database(path)
            run_database_migration(path)
            before = path.stat().st_mtime_ns

            report = check_database_health(path)

            self.assertEqual(report["backend"], "sqlite")
            self.assertTrue(report["connected"])
            self.assertTrue(report["expected_tables_accessible"])
            self.assertEqual(set(report["counts"]), set(COUNT_TABLES))
            self.assertTrue(all(count == 0 for count in report["counts"].values()))
            self.assertEqual(path.stat().st_mtime_ns, before)
            self.assertNotIn(str(path), str(report))

    def test_postgres_connection_failure_is_safe_and_does_not_fallback(self):
        marker = "synthetic-test-marker"
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://redacted.invalid/database"
        try:
            with patch("src.db.health.get_connection", side_effect=RuntimeError(marker)):
                report = check_database_health()
            self.assertEqual(report["backend"], "postgresql")
            self.assertFalse(report["connected"])
            self.assertEqual(report["error_type"], "RuntimeError")
            self.assertNotIn(marker, str(report))
            self.assertEqual(report["counts"], {})
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous


if __name__ == "__main__":
    unittest.main()
