"""
Repository module providing clean, type-hinted CRUD operations for UAE Pizza Intelligence.
All data access adheres to integrity rules and maintains complete audit trails.
"""
import uuid
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.db.connection import get_connection, get_db_connection
from src.db.evidence import has_valid_artifact


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
        artifact_content = None
        if file_path:
            local_artifact = Path(file_path)
            if local_artifact.is_file():
                artifact_content = local_artifact.read_bytes()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO evidence_records (
                    run_id, evidence_type, source_url, file_path, artifact_content,
                    file_hash_sha256, http_status, captured_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    evidence_type,
                    source_url,
                    file_path,
                    artifact_content,
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
                SELECT ev.id, ev.run_id, ev.evidence_type, ev.source_url,
                       ev.file_path, ev.file_hash_sha256, ev.http_status,
                       ev.captured_at, ev.notes,
                       COUNT(p.id) as linked_prices_count
                FROM evidence_records ev
                LEFT JOIN price_observations p ON p.evidence_id = ev.id
                GROUP BY ev.id
                ORDER BY ev.id DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_evidence_artifact(self, evidence_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve one captured artifact without loading blobs in the evidence list."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT file_path, artifact_content, file_hash_sha256 FROM evidence_records WHERE id = ?;",
                (evidence_id,),
            ).fetchone()
        if not row:
            return None
        content = row["artifact_content"]
        if content is not None:
            content = bytes(content)
        elif row["file_path"] and Path(row["file_path"]).is_file():
            content = Path(row["file_path"]).read_bytes()
        else:
            content = None
        return {"content": content, "file_hash_sha256": row["file_hash_sha256"], "file_path": row["file_path"]}

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
                "SELECT id FROM products WHERE competitor_id = ? AND category_id = ? AND name = ?;",
                (competitor_id, category_id, name),
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
        data_origin: str = "manual_entry",
    ) -> int:
        if not source_url:
            raise ValueError("source_url is mandatory for every price observation.")
        if not math.isfinite(float(original_price)) or original_price < 0:
            raise ValueError("original_price must be non-negative.")
        if currency != "AED":
            raise ValueError(f"Currency must be AED, received '{currency}'.")

        timestamp = collected_at or datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            if verification_status == "verified":
                evidence = conn.execute(
                    "SELECT source_url, file_path, artifact_content, file_hash_sha256 "
                    "FROM evidence_records WHERE id = ?;",
                    (evidence_id,),
                ).fetchone() if evidence_id is not None else None
                if (
                    not evidence
                    or evidence["source_url"] != source_url
                    or not has_valid_artifact(dict(evidence))
                ):
                    raise ValueError("Verified observations require hash-valid captured evidence for the same source URL.")
            cursor = conn.execute(
                """
                INSERT INTO price_observations (
                    run_id, competitor_id, product_variant_id, emirate_id,
                    location_id, channel_id, platform_id, original_price,
                    currency, promo_price, promo_description, delivery_fee,
                    min_order_amount, source_url, evidence_id, data_origin,
                    verification_status, collected_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    data_origin,
                    verification_status,
                    timestamp,
                    notes,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def append_observation_revision(
        self,
        obs_id: int,
        *,
        verification_status: Optional[str] = None,
        original_price: Optional[float] = None,
        evidence_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """Append a reviewed observation revision while retaining the source row."""
        with self._get_connection() as conn:
            source = conn.execute("SELECT * FROM price_observations WHERE id = ?", (obs_id,)).fetchone()
            if not source:
                raise ValueError(f"Observation ID {obs_id} not found.")
            if source["data_origin"] == "quarantined_seed" or source["is_quarantined"]:
                raise ValueError("Quarantined seed observations cannot be promoted or revised into active data.")

            next_status = verification_status or source["verification_status"]
            next_price = source["original_price"] if original_price is None else float(original_price)
            if not math.isfinite(next_price) or next_price < 0:
                raise ValueError("Price must be non-negative.")
            next_evidence_id = evidence_id if evidence_id is not None else source["evidence_id"]
            evidence = None
            if next_evidence_id is not None:
                evidence = conn.execute(
                    "SELECT source_url, file_hash_sha256, file_path FROM evidence_records WHERE id = ?",
                    (next_evidence_id,),
                ).fetchone()
            if next_status == "verified" and (
                not evidence
                or evidence["source_url"] != source["source_url"]
                or not has_valid_artifact(dict(evidence))
            ):
                raise ValueError("Verified revisions require captured evidence for the same source URL.")

            revision_notes = f"Revision of observation #{obs_id}. {notes or ''}".strip()
            cursor = conn.execute(
                """
                INSERT INTO price_observations (
                    run_id, competitor_id, product_variant_id, emirate_id, location_id,
                    channel_id, platform_id, original_price, currency, promo_price,
                    promo_description, delivery_fee, service_fee, vat_amount,
                    discount_amount, checkout_total, min_order_amount, source_url,
                    evidence_id, verification_status, data_origin, is_quarantined,
                    quarantine_reason, collected_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                """,
                (
                    source["run_id"], source["competitor_id"], source["product_variant_id"],
                    source["emirate_id"], source["location_id"], source["channel_id"],
                    source["platform_id"], next_price, source["currency"], source["promo_price"],
                    source["promo_description"], source["delivery_fee"], source["service_fee"],
                    source["vat_amount"], source["discount_amount"], source["checkout_total"],
                    source["min_order_amount"], source["source_url"], next_evidence_id,
                    next_status, source["data_origin"], source["is_quarantined"],
                    source["quarantine_reason"], revision_notes,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_observation_status(self, obs_id: int, new_status: str, notes: Optional[str] = None) -> int:
        """Compatibility API; writes a new revision rather than modifying history."""
        return self.append_observation_revision(
            obs_id, verification_status=new_status, notes=notes or "QA status change",
        )

    def update_observation_price(self, obs_id: int, new_price: float, notes: Optional[str] = None) -> None:
        return self.append_observation_revision(obs_id, original_price=new_price, notes=notes)

    def delete_observation(self, obs_id: int) -> None:
        raise RuntimeError("Price observations are append-only and cannot be deleted.")

    def get_price_observations(
        self,
        competitor_ids: Optional[List[int]] = None,
        emirate_ids: Optional[List[int]] = None,
        channel_ids: Optional[List[int]] = None,
        verification_statuses: Optional[List[str]] = None,
        normalized_sizes: Optional[List[str]] = None,
        search_query: Optional[str] = None,
        trusted_only: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            query = """
                SELECT po.id, po.original_price, po.currency, po.promo_price, po.promo_description,
                       po.delivery_fee, po.min_order_amount, po.source_url, po.verification_status,
                       po.data_origin, po.is_quarantined,
                       po.collected_at, po.notes,
                       c.id as competitor_id, c.name as competitor_name, c.code as competitor_code,
                       p.id as product_id, p.name as product_name, p.normalized_name,
                       cat.code as category_code, cat.name as category_name,
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
                JOIN categories cat ON cat.id = p.category_id
                JOIN emirates e ON po.emirate_id = e.id
                JOIN ordering_channels ch ON po.channel_id = ch.id
                JOIN ordering_platforms pl ON po.platform_id = pl.id
                LEFT JOIN locations loc ON po.location_id = loc.id
                LEFT JOIN evidence_records ev ON po.evidence_id = ev.id
                WHERE 1=1
            """
            params: List[Any] = []
            if trusted_only:
                query += """
                    AND po.verification_status = 'verified'
                    AND po.is_quarantined = 0
                    AND po.evidence_id IS NOT NULL
                    AND ev.file_hash_sha256 IS NOT NULL
                    AND (
                        (po.data_origin = 'live_extraction' AND po.notes LIKE 'Revision of observation #%')
                        OR po.data_origin = 'manual_entry'
                    )
                """
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

            rows = [dict(row) for row in conn.execute(query, params).fetchall()]
            if trusted_only and rows:
                evidence_ids = {row["evidence_id"] for row in rows if row["evidence_id"] is not None}
                valid_evidence = {}
                for evidence_id in evidence_ids:
                    evidence = conn.execute(
                        "SELECT file_path, artifact_content, file_hash_sha256 FROM evidence_records WHERE id = ?;",
                        (evidence_id,),
                    ).fetchone()
                    valid_evidence[evidence_id] = bool(evidence and has_valid_artifact(dict(evidence)))
                rows = [row for row in rows if valid_evidence.get(row["evidence_id"], False)]
            return rows

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
                       c.name as competitor_name,
                       c.code as competitor_code,
                       AVG(po.original_price) as avg_price,
                       COUNT(po.id) as sample_count
                FROM price_observations po
                JOIN product_variants pv ON po.product_variant_id = pv.id
                JOIN products p ON pv.product_id = p.id
                JOIN categories cat ON cat.id = p.category_id
                JOIN competitors c ON po.competitor_id = c.id
                JOIN evidence_records ev ON ev.id = po.evidence_id
                WHERE pv.normalized_size = ?
                  AND cat.code = 'pizza'
                  AND po.verification_status = 'verified'
                  AND po.is_quarantined = 0
                  AND po.evidence_id IS NOT NULL
                  AND ev.file_hash_sha256 IS NOT NULL
                  AND (po.data_origin = 'manual_entry' OR (po.data_origin = 'live_extraction' AND po.notes LIKE 'Revision of observation #%'))
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
                JOIN evidence_records ev ON ev.id = po.evidence_id
                WHERE po.verification_status = 'verified'
                  AND po.is_quarantined = 0
                  AND ev.file_hash_sha256 IS NOT NULL
                  AND (po.data_origin = 'manual_entry' OR (po.data_origin = 'live_extraction' AND po.notes LIKE 'Revision of observation #%'))
                GROUP BY c.id, p.id, pv.id, e.id
                HAVING MAX(CASE WHEN ch.code = 'direct_delivery' THEN po.original_price END) IS NOT NULL
                   AND MAX(CASE WHEN ch.code = 'third_party_delivery' THEN po.original_price END) IS NOT NULL;
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
        data = self.get_price_observations(
            emirate_ids=[emirate_id] if emirate_id else None,
            normalized_sizes=[normalized_size] if normalized_size else None,
            trusted_only=True,
            limit=5000,
        )
        if normalized_name:
            data = [row for row in data if row["normalized_name"] == normalized_name]
        if not data:
            return pd.DataFrame()
        frame = pd.DataFrame(data)
        frame["observation_date"] = pd.to_datetime(frame["collected_at"], utc=True).dt.date
        return (
            frame.groupby(
                ["observation_date", "competitor_name", "product_name", "size_name", "emirate_name"],
                as_index=False,
            )["original_price"]
            .mean()
            .rename(columns={"original_price": "avg_price"})
            .sort_values("observation_date")
        )

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
            eligible_verified_rows = conn.execute(
                """SELECT po.id, po.evidence_id
                   FROM price_observations po
                   WHERE po.verification_status = 'verified'
                     AND po.is_quarantined = 0
                     AND po.evidence_id IS NOT NULL
                     AND (po.data_origin = 'manual_entry' OR
                          (po.data_origin = 'live_extraction' AND po.notes LIKE 'Revision of observation #%'));"""
            ).fetchall()
            evidence_validity = {}
            for evidence_id in {row["evidence_id"] for row in eligible_verified_rows}:
                evidence = conn.execute(
                    "SELECT file_path, artifact_content, file_hash_sha256 FROM evidence_records WHERE id = ?;",
                    (evidence_id,),
                ).fetchone()
                evidence_validity[evidence_id] = bool(evidence and has_valid_artifact(dict(evidence)))
            verified_count = sum(
                1 for row in eligible_verified_rows if evidence_validity.get(row["evidence_id"], False)
            )
            needs_review_count = conn.execute(
                "SELECT COUNT(*) FROM price_observations WHERE verification_status = 'needs_review';"
            ).fetchone()[0]
            total_prices = conn.execute("SELECT COUNT(*) FROM price_observations;").fetchone()[0]
            runs_count = conn.execute("SELECT COUNT(*) FROM research_runs;").fetchone()[0]
            evidence_count = conn.execute("SELECT COUNT(*) FROM evidence_records;").fetchone()[0]
            promo_count = conn.execute("SELECT COUNT(*) FROM promotions WHERE is_active = 1;").fetchone()[0]
            branch_count = conn.execute("SELECT COUNT(*) FROM locations WHERE is_active = 1;").fetchone()[0]

            # Average medium pizza price
            medium_rows = conn.execute(
                """SELECT po.original_price, po.evidence_id, ev.file_path,
                          ev.artifact_content, ev.file_hash_sha256
                   FROM price_observations po
                   JOIN product_variants pv ON po.product_variant_id = pv.id
                   JOIN products p ON pv.product_id = p.id
                   JOIN categories cat ON cat.id = p.category_id
                   JOIN evidence_records ev ON ev.id = po.evidence_id
                   WHERE pv.normalized_size = 'medium'
                     AND cat.code = 'pizza'
                     AND po.verification_status = 'verified'
                     AND po.is_quarantined = 0
                     AND (po.data_origin = 'manual_entry' OR
                          (po.data_origin = 'live_extraction' AND po.notes LIKE 'Revision of observation #%'));"""
            ).fetchall()
            medium_prices = [
                row["original_price"] for row in medium_rows
                if has_valid_artifact(dict(row))
            ]
            avg_med_price = round(sum(medium_prices) / len(medium_prices), 2) if medium_prices else None

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
