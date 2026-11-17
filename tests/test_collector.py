"""
Unit tests for the GenuineResearchCollector.
"""
import tempfile
import unittest
from pathlib import Path

from src.db.init_db import initialize_database
from src.scrapers.genuine_collector import GenuineResearchCollector


class TestGenuineCollector(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_collector.db"
        initialize_database(self.db_path)
        self.collector = GenuineResearchCollector(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_audit_url_target_invalid(self):
        result = self.collector.audit_url_target("https://invalid-non-existent-domain-12345.xyz")
        self.assertFalse(result["accessible"])
        self.assertIsNotNone(result["error"])

    def test_execute_collection_run(self):
        sample_observations = [
            {
                "product_name": "Test Supreme Delight",
                "normalized_name": "super_supreme",
                "size_name": "Medium",
                "normalized_size": "medium",
                "price": 49.0,
                "crust_type": "Pan",
                "verification_status": "verified",
                "notes": "Verified test collection",
            }
        ]

        run_result = self.collector.execute_collection_run(
            competitor_code="pizza_hut",
            emirate_code="DXB",
            channel_code="direct_delivery",
            platform_code="direct_web",
            target_url="https://www.talabat.com/uae/pizza-hut",
            observations=sample_observations,
            notes="Test execution run",
        )

        self.assertIn("run_uuid", run_result)
        self.assertEqual(run_result["items_extracted"], 1)
        self.assertEqual(run_result["items_verified"], 1)
        self.assertEqual(run_result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
