"""
Unit tests for the PizzaIntelligenceRepository CRUD operations.
"""
import tempfile
import unittest
from pathlib import Path

from src.db.init_db import initialize_database
from src.db.repository import PizzaIntelligenceRepository


class TestPizzaIntelligenceRepository(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_repo.db"
        initialize_database(self.db_path)
        self.repo = PizzaIntelligenceRepository(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_master_data(self):
        emirates = self.repo.get_all_emirates()
        self.assertEqual(len(emirates), 7)

        channels = self.repo.get_all_channels()
        self.assertEqual(len(channels), 4)

        competitors = self.repo.get_all_competitors()
        self.assertGreaterEqual(len(competitors), 4)

        comp = self.repo.get_competitor_by_code("pizza_hut")
        self.assertIsNotNone(comp)
        self.assertEqual(comp["code"], "pizza_hut")

    def test_research_run_lifecycle(self):
        comp = self.repo.get_competitor_by_code("dominos")
        run_uuid = self.repo.create_research_run(
            competitor_id=comp["id"],
            notes="Automated test run"
        )
        self.assertTrue(bool(run_uuid))

        # Update run
        self.repo.update_research_run(
            run_uuid=run_uuid,
            status="completed",
            items_extracted=12,
            items_verified=12
        )

        metrics = self.repo.get_summary_metrics()
        self.assertEqual(metrics["research_runs_count"], 1)

    def test_evidence_and_observation_recording(self):
        comp = self.repo.get_competitor_by_code("pizza_hut")
        emirates = self.repo.get_all_emirates()
        channels = self.repo.get_all_channels()
        platforms = self.repo.get_all_platforms()

        dxb_id = next(e["id"] for e in emirates if e["code"] == "DXB")
        direct_channel_id = next(c["id"] for c in channels if c["code"] == "direct_delivery")
        direct_platform_id = next(p["id"] for p in platforms if p["code"] == "direct_web")

        # 1. Save evidence
        ev_id = self.repo.save_evidence(
            source_url="https://www.pizzahut.ae/menu/pizza/super-supreme",
            evidence_type="url_log",
            notes="Audit log captured"
        )
        self.assertGreater(ev_id, 0)

        # 2. Create product & variant
        prod_id = self.repo.get_or_create_product(
            competitor_id=comp["id"],
            category_id=1,
            name="Super Supreme",
            normalized_name="super_supreme"
        )
        var_id = self.repo.get_or_create_variant(
            product_id=prod_id,
            size_name="Medium",
            normalized_size="medium",
            crust_type="Pan"
        )

        # 3. Record price observation
        obs_id = self.repo.record_price_observation(
            competitor_id=comp["id"],
            product_variant_id=var_id,
            emirate_id=dxb_id,
            channel_id=direct_channel_id,
            platform_id=direct_platform_id,
            original_price=52.0,
            currency="AED",
            source_url="https://www.pizzahut.ae/menu/pizza/super-supreme",
            evidence_id=ev_id,
            verification_status="verified",
            notes="Direct online menu price"
        )
        self.assertGreater(obs_id, 0)

        # 4. Check summary metrics
        metrics = self.repo.get_summary_metrics()
        self.assertEqual(metrics["products_count"], 1)
        self.assertEqual(metrics["total_prices_count"], 1)
        self.assertEqual(metrics["verified_prices_count"], 1)
        self.assertEqual(metrics["evidence_count"], 1)

    def test_invalid_price_or_currency_rejected(self):
        comp = self.repo.get_competitor_by_code("pizza_hut")
        emirates = self.repo.get_all_emirates()
        channels = self.repo.get_all_channels()
        platforms = self.repo.get_all_platforms()

        with self.assertRaises(ValueError):
            self.repo.record_price_observation(
                competitor_id=comp["id"],
                product_variant_id=1,
                emirate_id=emirates[0]["id"],
                channel_id=channels[0]["id"],
                platform_id=platforms[0]["id"],
                original_price=-5.0,
                source_url="https://example.com"
            )

        with self.assertRaises(ValueError):
            self.repo.record_price_observation(
                competitor_id=comp["id"],
                product_variant_id=1,
                emirate_id=emirates[0]["id"],
                channel_id=channels[0]["id"],
                platform_id=platforms[0]["id"],
                original_price=35.0,
                currency="EUR",
                source_url="https://example.com"
            )

        with self.assertRaises(ValueError):
            self.repo.record_price_observation(
                competitor_id=comp["id"],
                product_variant_id=1,
                emirate_id=emirates[0]["id"],
                channel_id=channels[0]["id"],
                platform_id=platforms[0]["id"],
                original_price=35.0,
                source_url=""
            )


if __name__ == "__main__":
    unittest.main()
