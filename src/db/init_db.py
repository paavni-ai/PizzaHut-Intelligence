"""
Database Initialization Script.
Creates tables and seeds strictly master reference data (Emirates, Channels, Platforms, Categories, Competitor entities).
Zero fake prices or fictitious research records are inserted.
"""
from pathlib import Path
from typing import Optional, Union

from config import (
    COMPETITORS,
    DEFAULT_DB_PATH,
    ORDERING_CHANNELS,
    ORDERING_PLATFORMS,
    PROJECT_ROOT,
    UAE_EMIRATES,
)
from src.db.connection import get_connection

SCHEMA_FILE = PROJECT_ROOT / "src" / "db" / "schema.sql"

CATEGORIES = [
    {"code": "pizza", "name": "Pizzas", "display_order": 1},
    {"code": "sides", "name": "Sides & Appetizers", "display_order": 2},
    {"code": "beverages", "name": "Beverages", "display_order": 3},
    {"code": "desserts", "name": "Desserts", "display_order": 4},
    {"code": "combos", "name": "Meal Deals & Combos", "display_order": 5},
]


def initialize_database(db_path: Optional[Union[str, Path]] = None, reset: bool = False) -> None:
    """
    Initializes the SQLite database with the full schema and master reference data.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        if reset:
            # Drop tables in reverse foreign key order if reset requested
            tables = [
                "promotions",
                "price_observations",
                "evidence_records",
                "research_runs",
                "product_variants",
                "products",
                "categories",
                "ordering_platforms",
                "ordering_channels",
                "locations",
                "emirates",
                "competitors",
            ]
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table};")

        # 1. Execute schema definition
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            schema_script = f.read()
        cursor.executescript(schema_script)

        # 2. Seed Emirates (All 7 UAE Emirates)
        for emirate in UAE_EMIRATES:
            cursor.execute(
                """
                INSERT INTO emirates (code, name_en, name_ar, display_order)
                VALUES (:code, :name_en, :name_ar, :display_order)
                ON CONFLICT(code) DO UPDATE SET
                    name_en = excluded.name_en,
                    name_ar = excluded.name_ar,
                    display_order = excluded.display_order;
                """,
                emirate,
            )

        # 3. Seed Ordering Channels (The 4 distinct channels)
        for channel in ORDERING_CHANNELS:
            cursor.execute(
                """
                INSERT INTO ordering_channels (code, name, description)
                VALUES (:code, :name, :description)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description;
                """,
                channel,
            )

        # 4. Seed Ordering Platforms
        # Fetch channel IDs to link platforms properly
        cursor.execute("SELECT code, id FROM ordering_channels;")
        channel_ids = {row["code"]: row["id"] for row in cursor.fetchall()}

        for platform in ORDERING_PLATFORMS:
            # Map platform to channel
            channel_code = "third_party_delivery" if platform["platform_type"] == "aggregator" else "direct_delivery"
            channel_id = channel_ids.get(channel_code)
            
            cursor.execute(
                """
                INSERT INTO ordering_platforms (code, name, channel_id, platform_type, base_url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    channel_id = excluded.channel_id,
                    platform_type = excluded.platform_type,
                    base_url = excluded.base_url;
                """,
                (platform["code"], platform["name"], channel_id, platform["platform_type"], platform["base_url"]),
            )

        # 5. Seed Product Categories
        for cat in CATEGORIES:
            cursor.execute(
                """
                INSERT INTO categories (code, name, display_order)
                VALUES (:code, :name, :display_order)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    display_order = excluded.display_order;
                """,
                cat,
            )

        # 6. Seed Competitor Entities (Brand metadata only - NO PRICES)
        for comp in COMPETITORS:
            cursor.execute(
                """
                INSERT INTO competitors (code, name, website_url, notes)
                VALUES (:code, :name, :website_url, :notes)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    website_url = excluded.website_url,
                    notes = excluded.notes;
                """,
                comp,
            )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Initializing database at: {DEFAULT_DB_PATH}")
    initialize_database()
    print("Database initialization complete.")
