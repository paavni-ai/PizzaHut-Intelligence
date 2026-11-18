"""Tests for source-backed menu import, matching, prices, fees and offers."""
import hashlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.db.init_db import initialize_database
from src.db.migrate import run_database_migration
from src.db.repository import PizzaIntelligenceRepository
from src.menu_mapping.matcher import score_menu_candidate
from src.menu_mapping.service import (
    approve_menu_match,
    calculate_cart_quotes,
    get_comparison_history,
    get_latest_comparison_prices,
    get_latest_fee_observations,
    get_menu_import_content,
    get_promotion_records,
    get_unmatched_menu_items,
    get_unverified_menu_prices,
    import_menu_csv,
    parse_menu_csv,
    promotion_status,
    save_fee_observation,
    save_cart_comparison,
    save_promotion,
    verify_menu_price,
)


class TestMenuMapping(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "menu.sqlite")
        initialize_database(self.db_path)
        run_database_migration(self.db_path)
        self.repo = PizzaIntelligenceRepository(self.db_path)
        self.competitor_id = self.repo.get_competitor_by_code("pizza_hut")["id"]
        self.category_id = next(c["id"] for c in self.repo.get_all_categories() if c["code"] == "pizza")
        self.emirate_id = next(e["id"] for e in self.repo.get_all_emirates() if e["code"] == "DXB")
        self.platforms = {p["code"]: p for p in self.repo.get_all_platforms()}
        self.canonical_product = self.repo.get_or_create_product(
            competitor_id=self.competitor_id,
            category_id=self.category_id,
            name="Chicken Supreme",
            normalized_name="chicken_supreme",
            ingredients="chicken, mushroom, mozzarella cheese",
        )
        self.canonical_variant = self.repo.get_or_create_variant(
            self.canonical_product, "Large", "large", "Pan"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _csv(self, item="Chicken Supreme Pizza", size="Large", price="39.50", availability="available"):
        return (
            "item_name,category,size,price,availability,crust_type,ingredients,source_url\n"
            f'"{item}",pizza,{size},{price},{availability},Pan,"chicken, mushroom, mozzarella cheese",'
            "https://www.talabat.com/uae/pizza-hut/menu\n"
        ).encode()

    def test_matcher_never_suggests_different_sizes_or_categories(self):
        source = {"normalized_name": "margherita", "normalized_size": "large", "category_id": 1}
        candidate = {"normalized_name": "margherita", "normalized_size": "medium", "category_id": 1}
        self.assertFalse(score_menu_candidate(source, candidate)["suggested"])
        candidate.update(normalized_size="large", category_id=2)
        self.assertFalse(score_menu_candidate(source, candidate)["suggested"])

    def test_csv_validation_rejects_missing_price_for_available_item(self):
        with self.assertRaisesRegex(ValueError, "available items require"):
            parse_menu_csv(self._csv(price=""))

    def test_import_suggests_but_does_not_approve_then_manual_approval_enables_comparison(self):
        result = import_menu_csv(
            self._csv(), "talabat-menu.csv", self.competitor_id,
            self.platforms["talabat"]["id"], self.emirate_id, "QA reviewer", self.db_path,
        )
        self.assertEqual(result["items_imported"], 1)
        self.assertEqual(result["prices_verified"], 0)
        item = get_unmatched_menu_items(self.competitor_id, self.platforms["talabat"]["id"], self.db_path)[0]
        self.assertEqual(item["verification_status"], "unverified")
        source_blob = get_menu_import_content(result["batch_id"], self.db_path)
        self.assertTrue(source_blob["sha256_valid"])

        from src.menu_mapping.service import get_match_suggestions
        suggestions = get_match_suggestions(item["id"], self.db_path)
        self.assertTrue(suggestions)
        self.assertEqual(suggestions[0]["status"], "suggested")
        approve_menu_match(item["id"], self.canonical_variant, "QA reviewer", db_path=self.db_path)
        prices = get_latest_comparison_prices(self.db_path)
        imported = next(r for r in prices if r["source_kind"] == "menu import")
        self.assertEqual(imported["product_variant_id"], self.canonical_variant)
        self.assertEqual(imported["price"], 39.5)
        self.assertEqual(len(get_comparison_history(self.db_path)), 1)

        unverified = get_unverified_menu_prices(self.db_path)
        verify_menu_price(unverified[0]["price_id"], "QA reviewer", self.db_path)
        self.assertFalse(get_unverified_menu_prices(self.db_path))

    def test_manual_mapping_refuses_size_mismatch(self):
        result = import_menu_csv(
            self._csv(size="Medium"), "menu.csv", self.competitor_id,
            self.platforms["talabat"]["id"], self.emirate_id, "Reviewer", self.db_path,
        )
        item = get_unmatched_menu_items(self.competitor_id, self.platforms["talabat"]["id"], self.db_path)[0]
        with self.assertRaisesRegex(ValueError, "Different sizes"):
            approve_menu_match(item["id"], self.canonical_variant, "Reviewer", db_path=self.db_path)

    def test_fee_unknowns_are_not_treated_as_zero_and_cart_total_stays_incomplete(self):
        fee_id = save_fee_observation(
            self.competitor_id, self.platforms["talabat"]["id"], self.emirate_id,
            "https://www.talabat.com/uae/pizza-hut", {"delivery_fee": 7.0}, "Reviewer",
            db_path=self.db_path,
        )
        fees = get_latest_fee_observations(self.db_path)
        self.assertEqual(fees[0]["id"], fee_id)
        self.assertEqual(fees[0]["verification_status"], "unverified")
        quotes = calculate_cart_quotes(
            self.competitor_id, self.emirate_id, {self.canonical_variant: 1},
            [{"competitor_id": self.competitor_id, "emirate_id": self.emirate_id,
              "location_id": None, "platform_id": self.platforms["talabat"]["id"],
              "platform_name": "Talabat", "product_variant_id": self.canonical_variant,
              "price": 39.5, "availability": "available"}],
            fees, [],
        )
        self.assertIsNone(quotes[0]["final_total"])
        self.assertEqual(quotes[0]["quote_status"], "incomplete")

    def test_verified_promotion_retains_source_and_weekday_schedule(self):
        today = datetime.now(ZoneInfo("Asia/Dubai")).date()
        promo_id = save_promotion(
            self.competitor_id, self.platforms["talabat"]["id"], self.emirate_id,
            "Verified 10% offer", "One selected pizza only", "percentage_discount",
            "https://www.talabat.com/uae/pizza-hut/menu", None, 10.0,
            today.isoformat(), today.isoformat(), 40.0, 15.0,
            [today.weekday()], "Reviewer", b"captured-source-evidence.html", "offer.html",
            [self.canonical_variant], self.db_path,
        )
        promotion = next(p for p in get_promotion_records(self.db_path) if p["id"] == promo_id)
        self.assertEqual(promotion["verification_status"], "verified")
        self.assertEqual(promotion["weekdays"], [today.weekday()])
        self.assertEqual(promotion_status(promotion, today), "Active")

    def test_cart_customization_charges_are_calculated_and_persisted(self):
        fee_values = {name: 0.0 for name in (
            "delivery_fee", "service_fee", "small_order_fee", "packaging_fee", "other_fee"
        )}
        save_fee_observation(
            self.competitor_id, self.platforms["talabat"]["id"], self.emirate_id,
            "https://www.talabat.com/uae/pizza-hut", fee_values, "Reviewer",
            b"checkout.png", "checkout.png", db_path=self.db_path,
        )
        prices = [{
            "competitor_id": self.competitor_id, "emirate_id": self.emirate_id,
            "location_id": None, "platform_id": self.platforms["talabat"]["id"],
            "platform_name": "Talabat", "product_variant_id": self.canonical_variant,
            "price": 39.5, "availability": "available",
        }]
        customizations = {self.canonical_variant: {"amount": 2.0, "notes": "Extra cheese"}}
        quotes = calculate_cart_quotes(
            self.competitor_id, self.emirate_id, {self.canonical_variant: 2}, prices,
            get_latest_fee_observations(self.db_path), [], platform_catalog=self.repo.get_all_platforms(),
            customizations=customizations,
        )
        quote = next(q for q in quotes if q["platform_id"] == self.platforms["talabat"]["id"])
        self.assertEqual(quote["customization_total"], 4.0)
        self.assertEqual(quote["final_total"], 83.0)
        comparison_id = save_cart_comparison(
            self.competitor_id, self.emirate_id, {self.canonical_variant: 2}, quotes,
            "Reviewer", self.db_path, customizations=customizations,
        )
        with self.repo._get_connection() as conn:
            saved = conn.execute(
                "SELECT quantity,customization_amount,customization_notes FROM cart_comparison_items WHERE comparison_id=?",
                (comparison_id,),
            ).fetchone()
        self.assertEqual((saved["quantity"], saved["customization_amount"], saved["customization_notes"]),
                         (2, 2.0, "Extra cheese"))


if __name__ == "__main__":
    unittest.main()
