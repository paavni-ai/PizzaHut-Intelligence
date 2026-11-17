"""
Repository module providing clean, type-hinted CRUD operations for UAE Pizza Intelligence.
All data access adheres to integrity rules and maintains complete audit trails.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.db.connection import get_connection, get_db_connection


class PizzaIntelligenceRepository:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path

    def _get_connection(self):
        return get_db_connection(self.db_path)

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

    def get_all_categories(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM categories ORDER BY display_order ASC;"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_competitors(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            query = "SELECT * FROM competitors"
            if not include_inactive:
                query += " WHERE is_active = 1"
            query += " ORDER BY name ASC;"
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def get_competitor_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM competitors WHERE code = ?;", (code,)
            ).fetchone()
            return dict(row) if row else None

    def add_competitor(self, code: str, name: str, website_url: str = "", notes: str = "") -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO competitors (code, name, website_url, notes)
                VALUES (?, ?, ?, ?);
                """,
                (code, name, website_url, notes),
            )
            conn.commit()
            return cursor.lastrowid

    def update_competitor(self, comp_id: int, name: str, website_url: str, is_active: int, notes: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE competitors
                SET name = ?, website_url = ?, is_active = ?, notes = ?, updated_at = datetime('now')
                WHERE id = ?;
                """,
                (name, website_url, is_active, notes, comp_id),
            )
            conn.commit()

    # -------------------------------------------------------------------------
    # Locations and Branches
    # -------------------------------------------------------------------------
    def get_locations(self, competitor_id: Optional[int] = None, emirate_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            query = """
                SELECT l.*, c.name as competitor_name, e.name_en as emirate_name, e.code as emirate_code
                FROM locations l
                JOIN competitors c ON l.competitor_id = c.id
                JOIN emirates e ON l.emirate_id = e.id
                WHERE 1=1
            """
            params: List[Any] = []
            if competitor_id:
                query += " AND l.competitor_id = ?"
                params.append(competitor_id)
            if emirate_id:
                query += " AND l.emirate_id = ?"
                params.append(emirate_id)
            query += " ORDER BY c.name, e.display_order, l.branch_name ASC;"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def add_location(
        self,
        competitor_id: int,
        emirate_id: int,
        branch_name: str,
        area: str = "",
        address: str = "",
        phone: str = "",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO locations (competitor_id, emirate_id, branch_name, area, address, phone, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (competitor_id, emirate_id, branch_name, area, address, phone, latitude, longitude),
            )
            conn.commit()
            return cursor.lastrowid

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

    def get_research_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT r.*, c.name as competitor_name, p.name as platform_name,
                       ch.name as channel_name, e.name_en as emirate_name
                FROM research_runs r
                LEFT JOIN competitors c ON r.competitor_id = c.id
                LEFT JOIN ordering_platforms p ON r.platform_id = p.id
                LEFT JOIN ordering_channels ch ON r.channel_id = ch.id
                LEFT JOIN emirates e ON r.emirate_id = e.id
                ORDER BY r.id DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

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

    def get_evidence_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT ev.*,
                       COUNT(p.id) as linked_prices_count
                FROM evidence_records ev
                LEFT JOIN price_observations p ON p.evidence_id = ev.id
                GROUP BY ev.id
                ORDER BY ev.id DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

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

    def get_products_with_variants(
        self,
        competitor_id: Optional[int] = None,
        category_id: Optional[int] = None,
        search_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            query = """
                SELECT p.id as product_id, p.name as product_name, p.normalized_name,
                       p.is_vegetarian, p.is_spicy, p.description,
                       c.id as competitor_id, c.name as competitor_name,
                       cat.id as category_id, cat.name as category_name,
                       pv.id as variant_id, pv.size_name, pv.normalized_size,
                       pv.crust_type, pv.diameter_inches, pv.slices_count
                FROM products p
                JOIN competitors c ON p.competitor_id = c.id
                JOIN categories cat ON p.category_id = cat.id
                LEFT JOIN product_variants pv ON pv.product_id = p.id
                WHERE 1=1
            """
            params: List[Any] = []
            if competitor_id:
                query += " AND p.competitor_id = ?"
                params.append(competitor_id)
            if category_id:
                query += " AND p.category_id = ?"
                params.append(category_id)
            if search_query:
                query += " AND (p.name LIKE ? OR p.description LIKE ?)"
                params.extend([f"%{search_query}%", f"%{search_query}%"])
            query += " ORDER BY c.name, cat.display_order, p.name, pv.normalized_size;"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    # -------------------------------------------------------------------------
    # Price Observations CRUD
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

    def update_observation_status(self, obs_id: int, new_status: str, notes: Optional[str] = None) -> None:
        with self._get_connection() as conn:
            if notes is not None:
                conn.execute(
                    "UPDATE price_observations SET verification_status = ?, notes = ? WHERE id = ?;",
                    (new_status, notes, obs_id),
                )
            else:
                conn.execute(
                    "UPDATE price_observations SET verification_status = ? WHERE id = ?;",
                    (new_status, obs_id),
                )
            conn.commit()

    def update_observation_price(self, obs_id: int, new_price: float, notes: Optional[str] = None) -> None:
        if new_price < 0:
            raise ValueError("Price must be non-negative.")
        with self._get_connection() as conn:
            if notes is not None:
                conn.execute(
                    "UPDATE price_observations SET original_price = ?, notes = ? WHERE id = ?;",
                    (new_price, notes, obs_id),
                )
            else:
                conn.execute(
                    "UPDATE price_observations SET original_price = ? WHERE id = ?;",
                    (new_price, obs_id),
                )
            conn.commit()

    def delete_observation(self, obs_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM price_observations WHERE id = ?;", (obs_id,))
            conn.commit()

    def get_price_observations(
        self,
        competitor_ids: Optional[List[int]] = None,
        emirate_ids: Optional[List[int]] = None,
        channel_ids: Optional[List[int]] = None,
        verification_statuses: Optional[List[str]] = None,
        normalized_sizes: Optional[List[str]] = None,
        search_query: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            query = """
                SELECT po.id, po.original_price, po.currency, po.promo_price, po.promo_description,
                       po.delivery_fee, po.min_order_amount, po.source_url, po.verification_status,
                       po.collected_at, po.notes,
                       c.id as competitor_id, c.name as competitor_name, c.code as competitor_code,
                       p.id as product_id, p.name as product_name, p.normalized_name,
                       pv.id as variant_id, pv.size_name, pv.normalized_size, pv.crust_type,
                       e.id as emirate_id, e.name_en as emirate_name, e.code as emirate_code,
                       ch.id as channel_id, ch.name as channel_name, ch.code as channel_code,
                       pl.id as platform_id, pl.name as platform_name, pl.code as platform_code,
                       loc.branch_name, loc.area,
                       ev.id as evidence_id, ev.evidence_type, ev.captured_at as evidence_captured_at
                FROM price_observations po
                JOIN competitors c ON po.competitor_id = c.id
                JOIN product_variants pv ON po.product_variant_id = pv.id
                JOIN products p ON pv.product_id = p.id
                JOIN emirates e ON po.emirate_id = e.id
                JOIN ordering_channels ch ON po.channel_id = ch.id
                JOIN ordering_platforms pl ON po.platform_id = pl.id
                LEFT JOIN locations loc ON po.location_id = loc.id
                LEFT JOIN evidence_records ev ON po.evidence_id = ev.id
                WHERE 1=1
            """
            params: List[Any] = []
            if competitor_ids:
                placeholders = ",".join("?" for _ in competitor_ids)
                query += f" AND po.competitor_id IN ({placeholders})"
                params.extend(competitor_ids)
            if emirate_ids:
                placeholders = ",".join("?" for _ in emirate_ids)
                query += f" AND po.emirate_id IN ({placeholders})"
                params.extend(emirate_ids)
            if channel_ids:
                placeholders = ",".join("?" for _ in channel_ids)
                query += f" AND po.channel_id IN ({placeholders})"
                params.extend(channel_ids)
            if verification_statuses:
                placeholders = ",".join("?" for _ in verification_statuses)
                query += f" AND po.verification_status IN ({placeholders})"
                params.extend(verification_statuses)
            if normalized_sizes:
                placeholders = ",".join("?" for _ in normalized_sizes)
                query += f" AND pv.normalized_size IN ({placeholders})"
                params.extend(normalized_sizes)
            if search_query:
                query += " AND (p.name LIKE ? OR c.name LIKE ? OR po.notes LIKE ?)"
                params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

            query += " ORDER BY po.collected_at DESC, po.id DESC LIMIT ? OFFSET ?;"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_price_observations_df(self, **kwargs) -> pd.DataFrame:
        data = self.get_price_observations(**kwargs)
        if not data:
            return pd.DataFrame()
        return pd.DataFrame(data)

    # -------------------------------------------------------------------------
    # Comparison & Analytics Engines
    # -------------------------------------------------------------------------
    def get_price_comparison_matrix(
        self,
        normalized_size: str = "medium",
        emirate_id: Optional[int] = None,
        channel_id: Optional[int] = None,
    ) -> pd.DataFrame:
        with self._get_connection() as conn:
            query = """
                SELECT p.normalized_name as canonical_pizza,
                       p.name as item_name,
                       c.name as competitor_name,
                       c.code as competitor_code,
                       AVG(po.original_price) as avg_price,
                       COUNT(po.id) as sample_count
                FROM price_observations po
                JOIN product_variants pv ON po.product_variant_id = pv.id
                JOIN products p ON pv.product_id = p.id
                JOIN competitors c ON po.competitor_id = c.id
                WHERE pv.normalized_size = ?
            """
            params: List[Any] = [normalized_size]
            if emirate_id:
                query += " AND po.emirate_id = ?"
                params.append(emirate_id)
            if channel_id:
                query += " AND po.channel_id = ?"
                params.append(channel_id)

            query += " GROUP BY p.normalized_name, c.id ORDER BY p.normalized_name, c.name;"
            rows = conn.execute(query, params).fetchall()

            if not rows:
                return pd.DataFrame()

            records = [dict(r) for r in rows]
            df = pd.DataFrame(records)
            pivot_df = df.pivot(index="canonical_pizza", columns="competitor_name", values="avg_price")
            return pivot_df.round(2)

    def get_channel_markup_analysis(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            query = """
                SELECT c.name as competitor_name,
                       p.name as product_name,
                       pv.size_name,
                       e.name_en as emirate_name,
                       MAX(CASE WHEN ch.code = 'direct_delivery' THEN po.original_price END) as direct_price,
                       MAX(CASE WHEN ch.code = 'third_party_delivery' THEN po.original_price END) as aggregator_price
                FROM price_observations po
                JOIN competitors c ON po.competitor_id = c.id
                JOIN product_variants pv ON po.product_variant_id = pv.id
                JOIN products p ON pv.product_id = p.id
                JOIN emirates e ON po.emirate_id = e.id
                JOIN ordering_channels ch ON po.channel_id = ch.id
                GROUP BY c.id, p.id, pv.id, e.id
                HAVING direct_price IS NOT NULL AND aggregator_price IS NOT NULL;
            """
            rows = conn.execute(query).fetchall()
            results = []
            for row in rows:
                direct = row["direct_price"]
                agg = row["aggregator_price"]
                diff = agg - direct
                pct = ((agg - direct) / direct) * 100 if direct > 0 else 0
                results.append({
                    "competitor": row["competitor_name"],
                    "product": row["product_name"],
                    "size": row["size_name"],
                    "emirate": row["emirate_name"],
                    "direct_price": round(direct, 2),
                    "aggregator_price": round(agg, 2),
                    "markup_aed": round(diff, 2),
                    "markup_pct": round(pct, 1),
                })
            return results

    def get_historical_trends(
        self,
        normalized_name: Optional[str] = None,
        normalized_size: Optional[str] = None,
        emirate_id: Optional[int] = None,
    ) -> pd.DataFrame:
        with self._get_connection() as conn:
            query = """
                SELECT date(po.collected_at) as observation_date,
                       c.name as competitor_name,
                       p.name as product_name,
                       pv.size_name,
                       e.name_en as emirate_name,
                       AVG(po.original_price) as avg_price
                FROM price_observations po
                JOIN competitors c ON po.competitor_id = c.id
                JOIN product_variants pv ON po.product_variant_id = pv.id
                JOIN products p ON pv.product_id = p.id
                JOIN emirates e ON po.emirate_id = e.id
                WHERE 1=1
            """
            params: List[Any] = []
            if normalized_name:
                query += " AND p.normalized_name = ?"
                params.append(normalized_name)
            if normalized_size:
                query += " AND pv.normalized_size = ?"
                params.append(normalized_size)
            if emirate_id:
                query += " AND po.emirate_id = ?"
                params.append(emirate_id)

            query += " GROUP BY observation_date, c.name, p.name, pv.size_name ORDER BY observation_date ASC;"
            rows = conn.execute(query, params).fetchall()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([dict(r) for r in rows])

    # -------------------------------------------------------------------------
    # Promotions & Deals
    # -------------------------------------------------------------------------
    def get_promotions(self, competitor_id: Optional[int] = None, is_active: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            query = """
                SELECT pr.*, c.name as competitor_name, pl.name as platform_name, e.name_en as emirate_name
                FROM promotions pr
                JOIN competitors c ON pr.competitor_id = c.id
                LEFT JOIN ordering_platforms pl ON pr.platform_id = pl.id
                LEFT JOIN emirates e ON pr.emirate_id = e.id
                WHERE 1=1
            """
            params: List[Any] = []
            if competitor_id:
                query += " AND pr.competitor_id = ?"
                params.append(competitor_id)
            if is_active is not None:
                query += " AND pr.is_active = ?"
                params.append(is_active)
            query += " ORDER BY pr.is_active DESC, pr.id DESC;"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def add_promotion(
        self,
        competitor_id: int,
        title: str,
        promo_type: str,
        source_url: str,
        description: str = "",
        discount_amount: Optional[float] = None,
        discount_percentage: Optional[float] = None,
        promo_code: str = "",
        terms_conditions: str = "",
        platform_id: Optional[int] = None,
        emirate_id: Optional[int] = None,
        starts_at: Optional[str] = None,
        ends_at: Optional[str] = None,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO promotions (
                    competitor_id, title, promo_type, source_url, description,
                    discount_amount, discount_percentage, promo_code, terms_conditions,
                    platform_id, emirate_id, starts_at, ends_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    competitor_id,
                    title,
                    promo_type,
                    source_url,
                    description,
                    discount_amount,
                    discount_percentage,
                    promo_code,
                    terms_conditions,
                    platform_id,
                    emirate_id,
                    starts_at,
                    ends_at,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    # -------------------------------------------------------------------------
    # Summary Metrics / KPIs
    # -------------------------------------------------------------------------
    def get_summary_metrics(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            comp_count = conn.execute("SELECT COUNT(*) FROM competitors WHERE is_active = 1;").fetchone()[0]
            prod_count = conn.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
            verified_count = conn.execute(
                "SELECT COUNT(*) FROM price_observations WHERE verification_status = 'verified';"
            ).fetchone()[0]
            needs_review_count = conn.execute(
                "SELECT COUNT(*) FROM price_observations WHERE verification_status = 'needs_review';"
            ).fetchone()[0]
            total_prices = conn.execute("SELECT COUNT(*) FROM price_observations;").fetchone()[0]
            runs_count = conn.execute("SELECT COUNT(*) FROM research_runs;").fetchone()[0]
            evidence_count = conn.execute("SELECT COUNT(*) FROM evidence_records;").fetchone()[0]
            promo_count = conn.execute("SELECT COUNT(*) FROM promotions WHERE is_active = 1;").fetchone()[0]
            branch_count = conn.execute("SELECT COUNT(*) FROM locations WHERE is_active = 1;").fetchone()[0]

            # Average medium pizza price
            avg_med_row = conn.execute(
                """
                SELECT AVG(po.original_price)
                FROM price_observations po
                JOIN product_variants pv ON po.product_variant_id = pv.id
                WHERE pv.normalized_size = 'medium';
                """
            ).fetchone()
            avg_med_price = round(avg_med_row[0], 2) if (avg_med_row and avg_med_row[0]) else 0.0

            return {
                "competitors_count": comp_count,
                "products_count": prod_count,
                "verified_prices_count": verified_count,
                "needs_review_count": needs_review_count,
                "total_prices_count": total_prices,
                "research_runs_count": runs_count,
                "evidence_count": evidence_count,
                "promotions_count": promo_count,
                "branch_count": branch_count,
                "avg_medium_pizza_price": avg_med_price,
            }
