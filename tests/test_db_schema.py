"""
Unit tests for Database Schema, Master Reference Data, and Constraints.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.db.connection import get_connection
from src.db.init_db import initialize_database


class TestDatabaseSchema(unittest.TestCase):
    def setUp(self):
        # Create a temporary database for each test to keep tests isolated
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_pizza.db"
        initialize_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_all_twelve_tables_exist(self):
        expected_tables = {
            "competitors",
            "emirates",
            "locations",
            "ordering_channels",
            "ordering_platforms",
            "categories",
            "products",
            "product_variants",
            "research_runs",
            "evidence_records",
            "price_observations",
            "promotions",
        }
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row["name"] for row in cursor.fetchall()}
        conn.close()

        self.assertTrue(expected_tables.issubset(existing_tables))

    def test_seven_emirates_seeded_accurately(self):
        expected_codes = {"DXB", "AUH", "SHJ", "AJM", "RAK", "FUJ", "UAQ"}
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT code, name_en FROM emirates WHERE is_active = 1;")
        rows = cursor.fetchall()
        codes = {row["code"] for row in rows}
        conn.close()

        self.assertEqual(len(rows), 7)
        self.assertEqual(codes, expected_codes)

    def test_four_mandatory_ordering_channels_seeded(self):
        expected_channels = {
            "direct_delivery",
            "direct_pickup",
            "dine_in",
            "third_party_delivery",
        }
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM ordering_channels;")
        channels = {row["code"] for row in cursor.fetchall()}
        conn.close()

        self.assertEqual(channels, expected_channels)

    def test_no_fake_prices_seeded(self):
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM price_observations;")
        price_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM promotions;")
        promo_count = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(price_count, 0, "No prices should be pre-seeded!")
        self.assertEqual(promo_count, 0, "No promotions should be pre-seeded!")

    def test_foreign_key_enforcement(self):
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        # Inserting a location with non-existent competitor should fail
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO locations (competitor_id, emirate_id, branch_name)
                VALUES (99999, 1, 'Nonexistent Branch');
                """
            )
        conn.close()

    def test_price_observation_constraints(self):
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        # Seed 1 competitor, 1 category, 1 product, 1 variant, 1 platform
        cursor.execute("SELECT id FROM competitors LIMIT 1;")
        comp_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM categories LIMIT 1;")
        cat_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM emirates LIMIT 1;")
        emirate_id = cursor.fetchone()[0]
        cursor.execute("SELECT id, channel_id FROM ordering_platforms LIMIT 1;")
        platform_row = cursor.fetchone()
        platform_id = platform_row["id"]
        channel_id = platform_row["channel_id"]

        cursor.execute(
            "INSERT INTO products (competitor_id, category_id, name) VALUES (?, ?, ?);",
            (comp_id, cat_id, "Test Pizza"),
        )
        prod_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO product_variants (product_id, size_name, normalized_size) VALUES (?, ?, ?);",
            (prod_id, "Medium", "medium"),
        )
        variant_id = cursor.lastrowid
        conn.commit()

        # 1. Negative price should fail
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO price_observations (
                    competitor_id, product_variant_id, emirate_id, channel_id, platform_id,
                    original_price, currency, source_url
                ) VALUES (?, ?, ?, ?, ?, -10.0, 'AED', 'https://example.com');
                """,
                (comp_id, variant_id, emirate_id, channel_id, platform_id),
            )

        # 2. Non-AED currency should fail
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO price_observations (
                    competitor_id, product_variant_id, emirate_id, channel_id, platform_id,
                    original_price, currency, source_url
                ) VALUES (?, ?, ?, ?, ?, 35.0, 'USD', 'https://example.com');
                """,
                (comp_id, variant_id, emirate_id, channel_id, platform_id),
            )

        # 3. Missing source_url should fail
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO price_observations (
                    competitor_id, product_variant_id, emirate_id, channel_id, platform_id,
                    original_price, currency, source_url
                ) VALUES (?, ?, ?, ?, ?, 35.0, 'AED', NULL);
                """,
                (comp_id, variant_id, emirate_id, channel_id, platform_id),
            )

        conn.close()


if __name__ == "__main__":
    unittest.main()
