"""Optional live PostgreSQL smoke tests; target only a disposable validation branch.

Set DATABASE_URL to the validation branch's connection string for these tests.
The write/update/retrieve probe is rolled back and leaves no record behind.
"""
import os
import unittest
import uuid
from datetime import datetime, timezone

from src.db.connection import get_connection
from src.db.repository import PizzaIntelligenceRepository
from src.db.validator import DatabaseValidator
from src.reports.excel_generator import ExcelReportGenerator


@unittest.skipUnless(os.environ.get("DATABASE_URL"), "DATABASE_URL not set")
class TestPostgresIntegration(unittest.TestCase):
    def test_migrated_history_and_repository_reads(self):
        repo = PizzaIntelligenceRepository()
        metrics = repo.get_summary_metrics()
        self.assertEqual(metrics["total_prices_count"], 840)
        self.assertEqual(metrics["evidence_count"], 41)
        self.assertEqual(metrics["research_runs_count"], 6)
        self.assertGreaterEqual(len(repo.get_evidence_records(limit=3)), 3)
        self.assertGreaterEqual(len(repo.get_research_runs(limit=3)), 3)
        first_evidence_id = repo.get_evidence_records(limit=1)[0]["id"]
        artifact = repo.get_evidence_artifact(first_evidence_id)
        self.assertIsNotNone(artifact["content"])
        self.assertEqual(repo.get_products_with_variants(search_query="Margarita")[0]["competitor_name"], "Pizza Hut UAE")
        self.assertTrue(repo.get_price_comparison_matrix().empty)
        self.assertEqual(repo.get_channel_markup_analysis(), [])
        self.assertTrue(repo.get_historical_trends(normalized_size="medium").empty)
        workbook = ExcelReportGenerator().generate_full_report().getvalue()
        self.assertTrue(workbook.startswith(b"PK"))
        self.assertEqual(DatabaseValidator().validate_all()["status"], "PASS")

    def test_transactional_insert_update_and_retrieve(self):
        conn = get_connection()
        run_uuid = str(uuid.uuid4())
        try:
            competitor = conn.execute(
                "SELECT id FROM competitors WHERE code = ?;", ("pizza_hut",)
            ).fetchone()
            self.assertIsNotNone(competitor)
            cursor = conn.execute(
                """INSERT INTO research_runs (
                       run_uuid, competitor_id, status, started_at, notes
                   ) VALUES (?, ?, 'running', ?, ?);""",
                (run_uuid, competitor["id"], datetime.now(timezone.utc).isoformat(), "temporary database adapter probe"),
            )
            inserted_id = cursor.lastrowid
            self.assertGreater(inserted_id, 0)
            conn.execute(
                "UPDATE research_runs SET status = ?, items_extracted = ? WHERE run_uuid = ?;",
                ("completed", 2, run_uuid),
            )
            row = conn.execute(
                "SELECT id, status, items_extracted FROM research_runs WHERE run_uuid = ?;",
                (run_uuid,),
            ).fetchone()
            self.assertEqual((row["id"], row["status"], row["items_extracted"]), (inserted_id, "completed", 2))
        finally:
            conn.rollback()
            conn.close()

        check = get_connection()
        try:
            self.assertIsNone(check.execute(
                "SELECT id FROM research_runs WHERE run_uuid = ?;", (run_uuid,)
            ).fetchone())
        finally:
            check.close()


if __name__ == "__main__":
    unittest.main()
