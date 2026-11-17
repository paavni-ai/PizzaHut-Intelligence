"""
Repository module providing clean, type-hinted CRUD operations for UAE Pizza Intelligence.
All data access adheres to integrity rules and maintains complete audit trails.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from src.db.connection import get_connection


class PizzaIntelligenceRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _get_connection(self):
        return get_connection(self.db_path)

    # -------------------------------------------------------------------------
    # Master Lookups
    # -------------------------------------------------------------------------
    def get_all_emirates(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM emirates WHERE is_active = 1 ORDER BY display_order ASC;"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_channels(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ordering_channels ORDER BY id ASC;"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_platforms(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT p.*, c.code as channel_code, c.name as channel_name "
                "FROM ordering_platforms p "
                "JOIN ordering_channels c ON p.channel_id = c.id "
                "WHERE p.is_active = 1 ORDER BY p.id ASC;"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_competitors(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM competitors WHERE is_active = 1 ORDER BY name ASC;"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_competitor_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM competitors WHERE code = ?;", (code,)
            ).fetchone()
            return dict(row) if row else None

    # -------------------------------------------------------------------------
    # Research Runs
    # -------------------------------------------------------------------------
    def create_research_run(
        self,
        competitor_id: Optional[int] = None,
        platform_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        emirate_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> str:
        run_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_runs (
                    run_uuid, competitor_id, platform_id, channel_id, emirate_id,
                    status, started_at, notes
                ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?);
                """,
                (run_uuid, competitor_id, platform_id, channel_id, emirate_id, now, notes),
            )
            conn.commit()
        return run_uuid

    def update_research_run(
        self,
        run_uuid: str,
        status: str,
        items_extracted: int = 0,
        items_verified: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE research_runs
                SET status = ?, items_extracted = ?, items_verified = ?,
                    completed_at = ?, error_message = ?
                WHERE run_uuid = ?;
                """,
                (status, items_extracted, items_verified, now, error_message, run_uuid),
            )
            conn.commit()

    # -------------------------------------------------------------------------
    # Evidence Management
    # -------------------------------------------------------------------------
    def save_evidence(
        self,
        source_url: str,
        evidence_type: str = "url_log",
        run_id: Optional[int] = None,
        file_path: Optional[str] = None,
        file_hash_sha256: Optional[str] = None,
        http_status: Optional[int] = 200,
        notes: Optional[str] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO evidence_records (
                    run_id, evidence_type, source_url, file_path,
                    file_hash_sha256, http_status, captured_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    evidence_type,
                    source_url,
                    file_path,
                    file_hash_sha256,
                    http_status,
                    now,
                    notes,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    # -------------------------------------------------------------------------
    # Product & Variant Management
    # -------------------------------------------------------------------------
    def get_or_create_product(
        self,
        competitor_id: int,
        category_id: int,
        name: str,
        normalized_name: Optional[str] = None,
        description: Optional[str] = None,
        is_vegetarian: bool = False,
        is_spicy: bool = False,
    ) -> int:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM products WHERE competitor_id = ? AND name = ?;",
                (competitor_id, name),
            ).fetchone()
            if row:
                return row["id"]

            cursor = conn.execute(
                """
                INSERT INTO products (
                    competitor_id, category_id, name, normalized_name,
                    description, is_vegetarian, is_spicy
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    competitor_id,
                    category_id,
                    name,
                    normalized_name,
                    description,
                    1 if is_vegetarian else 0,
                    1 if is_spicy else 0,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_or_create_variant(
        self,
        product_id: int,
        size_name: str,
        normalized_size: str,
        crust_type: str = "Standard",
        diameter_inches: Optional[float] = None,
        slices_count: Optional[int] = None,
        serves_count: Optional[int] = None,
    ) -> int:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM product_variants
                WHERE product_id = ? AND size_name = ? AND crust_type = ?;
                """,
                (product_id, size_name, crust_type),
            ).fetchone()
            if row:
                return row["id"]

            cursor = conn.execute(
                """
                INSERT INTO product_variants (
                    product_id, size_name, normalized_size, crust_type,
                    diameter_inches, slices_count, serves_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    product_id,
                    size_name,
                    normalized_size,
                    crust_type,
                    diameter_inches,
                    slices_count,
                    serves_count,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    # -------------------------------------------------------------------------
    # Price Observations
    # -------------------------------------------------------------------------
    def record_price_observation(
        self,
        competitor_id: int,
        product_variant_id: int,
        emirate_id: int,
        channel_id: int,
        platform_id: int,
        original_price: float,
        source_url: str,
        currency: str = "AED",
        promo_price: Optional[float] = None,
        promo_description: Optional[str] = None,
        delivery_fee: float = 0.0,
        min_order_amount: float = 0.0,
        location_id: Optional[int] = None,
        run_id: Optional[int] = None,
        evidence_id: Optional[int] = None,
        verification_status: str = "unverified",
        collected_at: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Records an authentic price observation.
        Validates all required parameters to ensure complete audit trail.
        """
        if not source_url:
            raise ValueError("source_url is mandatory for every price observation.")
        if original_price < 0:
            raise ValueError("original_price must be non-negative.")
        if currency != "AED":
            raise ValueError(f"Currency must be AED, received '{currency}'.")

        timestamp = collected_at or datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO price_observations (
                    run_id, competitor_id, product_variant_id, emirate_id,
                    location_id, channel_id, platform_id, original_price,
                    currency, promo_price, promo_description, delivery_fee,
                    min_order_amount, source_url, evidence_id,
                    verification_status, collected_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    competitor_id,
                    product_variant_id,
                    emirate_id,
                    location_id,
                    channel_id,
                    platform_id,
                    original_price,
                    currency,
                    promo_price,
                    promo_description,
                    delivery_fee,
                    min_order_amount,
                    source_url,
                    evidence_id,
                    verification_status,
                    timestamp,
                    notes,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    # -------------------------------------------------------------------------
    # Analytics & Summary Queries
    # -------------------------------------------------------------------------
    def get_summary_metrics(self) -> Dict[str, int]:
        with self._get_connection() as conn:
            comp_count = conn.execute("SELECT COUNT(*) FROM competitors WHERE is_active = 1;").fetchone()[0]
            prod_count = conn.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
            verified_count = conn.execute(
                "SELECT COUNT(*) FROM price_observations WHERE verification_status = 'verified';"
            ).fetchone()[0]
            total_prices = conn.execute("SELECT COUNT(*) FROM price_observations;").fetchone()[0]
            runs_count = conn.execute("SELECT COUNT(*) FROM research_runs;").fetchone()[0]
            evidence_count = conn.execute("SELECT COUNT(*) FROM evidence_records;").fetchone()[0]

            return {
                "competitors_count": comp_count,
                "products_count": prod_count,
                "verified_prices_count": verified_count,
                "total_prices_count": total_prices,
                "research_runs_count": runs_count,
                "evidence_count": evidence_count,
            }
