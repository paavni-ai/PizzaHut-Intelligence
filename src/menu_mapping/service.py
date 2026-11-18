"""Persistence and read models for menu comparison workflows."""
import csv
import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from src.db.connection import get_connection
from src.menu_mapping.matcher import score_menu_candidate

UAE_TZ = ZoneInfo("Asia/Dubai")
SIZE_ALIASES = {
    "personal": "personal", "individual": "personal", "small": "small",
    "medium": "medium", "large": "large", "xl": "xlarge", "x-large": "xlarge",
    "xlarge": "xlarge", "extra large": "xlarge", "other": "other",
}
PROMOTION_TYPES = (
    "percentage_discount", "fixed_discount", "bogo", "free_delivery", "pizza_deal",
    "meal_deal", "combo_offer", "platform_discount", "minimum_spend", "first_order",
    "loyalty", "other",
)


def now_uae() -> str:
    return datetime.now(timezone.utc).astimezone(UAE_TZ).isoformat(timespec="seconds")


def normalize_menu_name(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", (value or "").casefold())
    ignored = {"pizza", "small", "medium", "large", "personal", "xl", "xlarge", "extra", "family"}
    return " ".join(token for token in tokens if token not in ignored)


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_menu_csv(content: bytes) -> list[dict[str, Any]]:
    """Validate a source-backed CSV before opening a database transaction."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Upload must be a UTF-8 CSV file.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV must include a header row.")
    aliases = {
        "name": "item_name", "product_name": "item_name", "size": "size_name",
        "price_aed": "price", "url": "source_url", "category_code": "category",
        "item_id": "external_id", "ingredients_list": "ingredients",
    }
    fields = {str(name).strip().casefold(): name for name in reader.fieldnames if name}

    def value(row: Mapping[str, Any], key: str, default: str = "") -> str:
        source_key = fields.get(key)
        if source_key is None:
            source_key = next((fields[a] for a, target in aliases.items() if target == key and a in fields), None)
        return str(row.get(source_key) or "").strip() if source_key else default

    normalized_sizes = {name: original for original, name in SIZE_ALIASES.items()}
    parsed: list[dict[str, Any]] = []
    seen: dict[str, tuple[Any, ...]] = {}
    errors: list[str] = []
    for row_num, row in enumerate(reader, start=2):
        if not any(str(cell or "").strip() for cell in row.values()):
            continue
        item_name = value(row, "item_name")
        category = value(row, "category").casefold()
        size_label = value(row, "size_name")
        size_key = re.sub(r"\s+", " ", size_label.casefold())
        normalized_size = SIZE_ALIASES.get(size_key)
        price_text = value(row, "price")
        source_url = value(row, "source_url")
        availability = (value(row, "availability", "unknown") or "unknown").casefold()
        if not item_name:
            errors.append(f"Row {row_num}: item_name is required.")
        if not category:
            errors.append(f"Row {row_num}: category is required.")
        if not normalized_size:
            errors.append(f"Row {row_num}: size_name must be one of personal, small, medium, large, xlarge, or other.")
        if availability not in {"available", "unavailable", "unknown"}:
            errors.append(f"Row {row_num}: availability must be available, unavailable, or unknown.")
        if not source_url or not _valid_http_url(source_url):
            errors.append(f"Row {row_num}: source_url must be an http(s) URL.")
        price: Optional[float] = None
        if price_text:
            try:
                price = float(price_text.replace(",", ""))
                if price < 0:
                    raise ValueError
            except ValueError:
                errors.append(f"Row {row_num}: price must be a non-negative AED amount.")
        elif availability == "available":
            errors.append(f"Row {row_num}: available items require an observed price; use blank price only when unavailable or unknown.")
        if errors and errors[-1].startswith(f"Row {row_num}:"):
            continue
        ingredients = value(row, "ingredients")
        crust = value(row, "crust_type")
        external_id = value(row, "external_id")
        identity = hashlib.sha256(
            "|".join((external_id, category, normalize_menu_name(item_name), normalized_size or "", crust.casefold(),
                      normalize_menu_name(ingredients))).encode("utf-8")
        ).hexdigest()
        record = {
            "source_item_key": identity,
            "item_name": item_name,
            "normalized_name": normalize_menu_name(item_name),
            "description": value(row, "description") or None,
            "category_code": category,
            "size_name": size_label,
            "normalized_size": normalized_size,
            "crust_type": crust or None,
            "ingredients": ingredients or None,
            "availability": availability,
            "price": price,
            "source_url": source_url,
            "observed_at": value(row, "observed_at") or now_uae(),
        }
        signature = (record["price"], availability, source_url)
        if identity in seen and seen[identity] != signature:
            errors.append(f"Row {row_num}: duplicate item key has conflicting price or availability.")
        elif identity not in seen:
            parsed.append(record)
            seen[identity] = signature
    if errors:
        raise ValueError("Menu CSV validation failed:\n" + "\n".join(errors[:25]))
    if not parsed:
        raise ValueError("CSV has no menu rows to import.")
    return parsed


def parse_menu_upload(content: bytes, file_name: str) -> list[dict[str, Any]]:
    """Accept CSV and XLSX uploads while preserving the exact uploaded file."""
    suffix = Path(file_name).suffix.casefold()
    if suffix == ".csv":
        return parse_menu_csv(content)
    if suffix != ".xlsx":
        raise ValueError("Upload a .csv or .xlsx file.")
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.iter_rows(values_only=True))
        workbook.close()
    except Exception as exc:
        raise ValueError("Could not read the uploaded Excel workbook.") from exc
    if not values or not values[0]:
        raise ValueError("Excel workbook must include a header row.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([str(value or "").strip() for value in values[0]])
    for row in values[1:]:
        writer.writerow([value.isoformat() if hasattr(value, "isoformat") else value for value in row])
    return parse_menu_csv(output.getvalue().encode("utf-8"))


def _candidate_rows(conn: Any, competitor_id: int, category_id: int, size: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT pv.id AS product_variant_id, p.id AS product_id, p.name,
                  p.normalized_name, p.description, p.ingredients, p.category_id,
                  pv.size_name, pv.normalized_size, pv.crust_type
           FROM products p JOIN product_variants pv ON pv.product_id = p.id
           WHERE p.competitor_id = ? AND p.category_id = ?
             AND pv.normalized_size = ? AND pv.is_active = 1
           ORDER BY p.name, pv.crust_type""",
        (competitor_id, category_id, size),
    ).fetchall()
    return [dict(row) for row in rows]


def import_menu_csv(
    content: bytes,
    file_name: str,
    competitor_id: int,
    platform_id: int,
    emirate_id: int,
    imported_by: str,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a source-backed manual import and its unverified price history."""
    if not imported_by.strip():
        raise ValueError("Importer name is required for the audit log.")
    rows = parse_menu_upload(content, file_name)
    timestamp = now_uae()
    file_hash = hashlib.sha256(content).hexdigest()
    run_uuid = str(uuid.uuid4())
    conn = get_connection(db_path)
    try:
        platform = conn.execute(
            "SELECT id, name, channel_id FROM ordering_platforms WHERE id = ? AND is_active = 1",
            (platform_id,),
        ).fetchone()
        competitor = conn.execute("SELECT id FROM competitors WHERE id = ?", (competitor_id,)).fetchone()
        emirate = conn.execute("SELECT id FROM emirates WHERE id = ?", (emirate_id,)).fetchone()
        if not platform or not competitor or not emirate:
            raise ValueError("Select an existing competitor, active platform, and emirate.")
        category_ids = {r["code"].casefold(): r["id"] for r in conn.execute("SELECT id, code FROM categories").fetchall()}
        missing_categories = sorted({r["category_code"] for r in rows} - category_ids.keys())
        if missing_categories:
            raise ValueError("Unknown categories: " + ", ".join(missing_categories))

        run = conn.execute(
            """INSERT INTO research_runs
               (run_uuid, competitor_id, platform_id, channel_id, emirate_id, status,
                items_extracted, items_verified, started_at, completed_at, notes)
               VALUES (?, ?, ?, ?, ?, 'completed', ?, 0, ?, ?, ?)""",
            (run_uuid, competitor_id, platform_id, platform["channel_id"], emirate_id,
             len(rows), timestamp, timestamp, "Manual CSV menu import; imported prices remain unverified until reviewed."),
        )
        run_id = run.lastrowid
        batch = conn.execute(
            """INSERT INTO menu_import_batches
               (research_run_id, file_name, source_url, file_sha256, file_content,
                imported_rows, imported_at, imported_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, Path(file_name).name[:255] or "menu-import.csv", rows[0]["source_url"],
             file_hash, content, len(rows), timestamp, imported_by.strip()),
        )
        batch_id = batch.lastrowid
        item_ids = []
        suggestions_added = 0
        for row in rows:
            category_id = category_ids[row["category_code"]]
            item = conn.execute(
                """INSERT INTO platform_menu_items
                   (competitor_id, platform_id, emirate_id, source_item_key, item_name,
                    normalized_name, description, category_id, size_name, normalized_size,
                    crust_type, ingredients, availability, source_url, first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(competitor_id, platform_id, emirate_id, source_item_key)
                   DO UPDATE SET item_name=excluded.item_name, normalized_name=excluded.normalized_name,
                     description=excluded.description, category_id=excluded.category_id,
                     size_name=excluded.size_name, normalized_size=excluded.normalized_size,
                     crust_type=excluded.crust_type, ingredients=excluded.ingredients,
                     availability=excluded.availability, source_url=excluded.source_url,
                     last_seen_at=excluded.last_seen_at""",
                (competitor_id, platform_id, emirate_id, row["source_item_key"], row["item_name"],
                 row["normalized_name"], row["description"], category_id, row["size_name"],
                 row["normalized_size"], row["crust_type"], row["ingredients"], row["availability"],
                 row["source_url"], timestamp, timestamp),
            )
            item_id = item.lastrowid
            item_ids.append(item_id)
            conn.execute(
                """INSERT INTO menu_item_prices
                   (platform_menu_item_id, research_run_id, import_batch_id, price, currency,
                    availability, observed_at, source_url, verification_status)
                   VALUES (?, ?, ?, ?, 'AED', ?, ?, ?, 'unverified')""",
                (item_id, run_id, batch_id, row["price"], row["availability"], row["observed_at"], row["source_url"]),
            )
            source = {**row, "category_id": category_id}
            for candidate in _candidate_rows(conn, competitor_id, category_id, row["normalized_size"]):
                result = score_menu_candidate(source, candidate)
                if result["suggested"]:
                    cursor = conn.execute(
                        """INSERT INTO menu_item_matches
                           (platform_menu_item_id, product_variant_id, confidence_score, status, matching_details)
                           VALUES (?, ?, ?, 'suggested', ?)
                           ON CONFLICT(platform_menu_item_id, product_variant_id) DO NOTHING""",
                        (item_id, candidate["product_variant_id"], result["score"], result["reason"]),
                    )
                    suggestions_added += max(cursor.rowcount, 0)

        conn.commit()
        return {
            "research_run_id": run_id,
            "run_uuid": run_uuid,
            "batch_id": batch_id,
            "items_imported": len(item_ids),
            "match_suggestions": suggestions_added,
            "prices_verified": 0,
            "file_sha256": file_hash,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_unmatched_menu_items(
    competitor_id: Optional[int] = None,
    platform_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    sql = """SELECT mi.*, c.name AS competitor_name, op.name AS platform_name,
                     e.name_en AS emirate_name, cat.name AS category_name,
                     mip.price, mip.availability AS observed_availability,
                     mip.observed_at, mip.verification_status
              FROM platform_menu_items mi
              JOIN competitors c ON c.id=mi.competitor_id
              JOIN ordering_platforms op ON op.id=mi.platform_id
              JOIN emirates e ON e.id=mi.emirate_id
              JOIN categories cat ON cat.id=mi.category_id
              LEFT JOIN menu_item_prices mip ON mip.id=(
                  SELECT p2.id FROM menu_item_prices p2
                  WHERE p2.platform_menu_item_id=mi.id ORDER BY p2.observed_at DESC, p2.id DESC LIMIT 1)
              WHERE NOT EXISTS (SELECT 1 FROM menu_item_matches mm
                                WHERE mm.platform_menu_item_id=mi.id AND mm.status='approved')"""
    params: list[Any] = []
    if competitor_id is not None:
        sql += " AND mi.competitor_id=?"
        params.append(competitor_id)
    if platform_id is not None:
        sql += " AND mi.platform_id=?"
        params.append(platform_id)
    sql += " ORDER BY mi.last_seen_at DESC, mi.item_name"
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def get_approved_menu_matches(db_path: Optional[str] = None) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT mm.id AS match_id,mm.confidence_score,mm.reviewed_by,mm.reviewed_at,
                      mi.id AS menu_item_id,mi.item_name,mi.size_name,mi.crust_type,
                      op.name AS platform_name,p.name AS canonical_name,pv.size_name AS canonical_size,
                      pv.crust_type AS canonical_crust
               FROM menu_item_matches mm JOIN platform_menu_items mi ON mi.id=mm.platform_menu_item_id
               JOIN product_variants pv ON pv.id=mm.product_variant_id
               JOIN products p ON p.id=pv.product_id JOIN ordering_platforms op ON op.id=mi.platform_id
               WHERE mm.status='approved' ORDER BY mi.item_name,op.name"""
        ).fetchall()]
    finally:
        conn.close()


def get_recent_menu_imports(db_path: Optional[str] = None, limit: int = 25) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT b.id,b.file_name,b.source_url,b.file_sha256,b.imported_rows,
                      b.imported_at,b.imported_by,r.status,r.items_verified
               FROM menu_import_batches b JOIN research_runs r ON r.id=b.research_run_id
               ORDER BY b.imported_at DESC LIMIT ?""", (limit,)
        ).fetchall()]
    finally:
        conn.close()


def get_menu_import_content(batch_id: int, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT file_name,file_content,file_sha256 FROM menu_import_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not row:
            return None
        content = bytes(row["file_content"])
        return {"file_name": row["file_name"], "content": content,
                "sha256_valid": hashlib.sha256(content).hexdigest().casefold() == str(row["file_sha256"]).casefold()}
    finally:
        conn.close()


def get_unverified_menu_prices(db_path: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT mip.id AS price_id,mip.price,mip.availability,mip.observed_at,
                      mip.source_url,mip.verification_status,mi.id AS menu_item_id,
                      mi.item_name,mi.size_name,mi.crust_type,op.name AS platform_name,
                      e.name_en AS emirate_name,b.file_name,b.id AS batch_id
               FROM menu_item_prices mip JOIN platform_menu_items mi ON mi.id=mip.platform_menu_item_id
               JOIN ordering_platforms op ON op.id=mi.platform_id JOIN emirates e ON e.id=mi.emirate_id
               LEFT JOIN menu_import_batches b ON b.id=mip.import_batch_id
               WHERE mip.verification_status<>'verified'
               ORDER BY mip.observed_at DESC LIMIT ?""", (limit,)
        ).fetchall()]
    finally:
        conn.close()


def verify_menu_price(price_id: int, reviewer: str, db_path: Optional[str] = None) -> None:
    if not reviewer.strip():
        raise ValueError("Reviewer name is required.")
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id,source_url,import_batch_id,research_run_id,verification_status FROM menu_item_prices WHERE id=?", (price_id,)
        ).fetchone()
        if not row or not _valid_http_url(row["source_url"]):
            raise ValueError("Price observation or its source URL is unavailable.")
        if not row["import_batch_id"]:
            raise ValueError("A retained import file is required before verifying this price.")
        conn.execute(
            "UPDATE menu_item_prices SET verification_status='verified',verified_by=?,verified_at=? WHERE id=?",
            (reviewer.strip(),now_uae(),price_id),
        )
        if row["verification_status"] != "verified":
            conn.execute("UPDATE research_runs SET items_verified=items_verified+1 WHERE id=?", (row["research_run_id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_match_suggestions(menu_item_id: int, db_path: Optional[str] = None) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT mm.id AS match_id, mm.confidence_score, mm.status, mm.matching_details,
                      p.name AS product_name, pv.size_name, pv.crust_type,
                      pv.normalized_size, pv.id AS product_variant_id
               FROM menu_item_matches mm
               JOIN product_variants pv ON pv.id=mm.product_variant_id
               JOIN products p ON p.id=pv.product_id
               WHERE mm.platform_menu_item_id=? AND mm.status<>'rejected'
               ORDER BY mm.confidence_score DESC, p.name""",
            (menu_item_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def approve_menu_match(
    menu_item_id: int,
    product_variant_id: int,
    reviewer: str,
    confirm_variation: bool = False,
    db_path: Optional[str] = None,
) -> None:
    if not reviewer.strip():
        raise ValueError("Reviewer name is required.")
    conn = get_connection(db_path)
    try:
        source = conn.execute("SELECT * FROM platform_menu_items WHERE id=?", (menu_item_id,)).fetchone()
        target = conn.execute(
            """SELECT pv.id, pv.normalized_size, pv.crust_type, p.category_id,
                      p.name, p.ingredients, p.normalized_name
               FROM product_variants pv JOIN products p ON p.id=pv.product_id WHERE pv.id=?""",
            (product_variant_id,),
        ).fetchone()
        if not source or not target:
            raise ValueError("Selected menu item or canonical variant no longer exists.")
        if source["normalized_size"] != target["normalized_size"]:
            raise ValueError("Different sizes cannot be mapped as equivalent.")
        if source["category_id"] != target["category_id"]:
            raise ValueError("Different food categories cannot be mapped as equivalent.")
        crust_differs = bool(source["crust_type"] and target["crust_type"] and source["crust_type"].casefold() != target["crust_type"].casefold())
        ingredient_differs = bool(source["ingredients"] and target["ingredients"] and source["ingredients"].casefold() != target["ingredients"].casefold())
        if (crust_differs or ingredient_differs) and not confirm_variation:
            raise ValueError("Crust or ingredients differ. Confirm the variation after reviewing it.")
        score = score_menu_candidate(dict(source), dict(target))
        details = "Manual reviewer approved; " + score["reason"]
        conn.execute(
            """INSERT INTO menu_item_matches
               (platform_menu_item_id, product_variant_id, confidence_score, status,
                matching_details, reviewed_by, reviewed_at)
               VALUES (?, ?, ?, 'approved', ?, ?, ?)
               ON CONFLICT(platform_menu_item_id, product_variant_id)
               DO UPDATE SET confidence_score=excluded.confidence_score, status='approved',
                 matching_details=excluded.matching_details, reviewed_by=excluded.reviewed_by,
                 reviewed_at=excluded.reviewed_at""",
            (menu_item_id, product_variant_id, score["score"], details, reviewer.strip(), now_uae()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reject_menu_match(match_id: int, reviewer: str, db_path: Optional[str] = None) -> None:
    if not reviewer.strip():
        raise ValueError("Reviewer name is required.")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE menu_item_matches SET status='rejected', reviewed_by=?, reviewed_at=? WHERE id=? AND status IN ('suggested','approved')",
            (reviewer.strip(), now_uae(), match_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_latest_comparison_prices(db_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Return latest comparable source prices; legacy rows map by exact variant id."""
    sql = """WITH all_prices AS (
          SELECT po.id AS record_id, NULL AS platform_menu_item_id, po.competitor_id, po.platform_id, po.emirate_id,
                 po.location_id, po.product_variant_id, po.original_price AS price,
                 po.collected_at AS observed_at, po.source_url, po.verification_status,
                 'unknown' AS availability, 'research history' AS source_kind
          FROM price_observations po
          WHERE COALESCE(po.is_quarantined,0)=0
            AND po.verification_status <> 'quarantined'
          UNION ALL
          SELECT mip.id AS record_id, mi.id AS platform_menu_item_id, mi.competitor_id, mi.platform_id, mi.emirate_id,
                 mi.location_id, mm.product_variant_id, mip.price, mip.observed_at,
                 mip.source_url, mip.verification_status, mip.availability,
                 'menu import' AS source_kind
          FROM menu_item_prices mip
          JOIN platform_menu_items mi ON mi.id=mip.platform_menu_item_id
          JOIN menu_item_matches mm ON mm.platform_menu_item_id=mi.id AND mm.status='approved'
      ), ranked AS (
          SELECT ap.*, ROW_NUMBER() OVER (
              PARTITION BY competitor_id, platform_id, emirate_id, COALESCE(location_id,0), product_variant_id
              ORDER BY observed_at DESC, record_id DESC
          ) AS recency_rank
          FROM all_prices ap
      )
      SELECT r.record_id, r.platform_menu_item_id, r.competitor_id, c.name AS competitor_name,
             r.platform_id, op.code AS platform_code, op.name AS platform_name,
             r.emirate_id, e.name_en AS emirate_name, r.location_id,
             l.branch_name AS location_name, r.product_variant_id,
             p.id AS product_id, p.name AS item_name, p.normalized_name,
             p.ingredients, cat.id AS category_id, cat.code AS category_code,
             cat.name AS category_name, pv.size_name, pv.normalized_size,
             pv.crust_type, r.price, r.availability, r.observed_at,
             r.source_url, r.verification_status, r.source_kind
      FROM ranked r
      JOIN competitors c ON c.id=r.competitor_id
      JOIN ordering_platforms op ON op.id=r.platform_id
      JOIN emirates e ON e.id=r.emirate_id
      LEFT JOIN locations l ON l.id=r.location_id
      JOIN product_variants pv ON pv.id=r.product_variant_id
      JOIN products p ON p.id=pv.product_id
      JOIN categories cat ON cat.id=p.category_id
      WHERE r.recency_rank=1
      ORDER BY c.name, cat.display_order, p.name, pv.normalized_size, op.name"""
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def get_comparison_history(db_path: Optional[str] = None, limit: int = 5000) -> list[dict[str, Any]]:
    """Return real historical price events for trend charts."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT po.id, po.competitor_id, c.name AS competitor_name,
                      po.platform_id, op.name AS platform_name, po.emirate_id,
                      e.name_en AS emirate_name, po.location_id, l.branch_name AS location_name,
                      po.product_variant_id,
                      p.name AS item_name, cat.name AS category_name,
                      pv.size_name, pv.normalized_size, pv.crust_type,
                      po.original_price AS price, po.collected_at AS observed_at,
                      po.verification_status, po.source_url, 'research history' AS source_kind
               FROM price_observations po
               JOIN competitors c ON c.id=po.competitor_id
               JOIN ordering_platforms op ON op.id=po.platform_id
               JOIN emirates e ON e.id=po.emirate_id
               LEFT JOIN locations l ON l.id=po.location_id
               JOIN product_variants pv ON pv.id=po.product_variant_id
               JOIN products p ON p.id=pv.product_id
               JOIN categories cat ON cat.id=p.category_id
               WHERE COALESCE(po.is_quarantined,0)=0
               ORDER BY po.collected_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        legacy = [dict(r) for r in rows]
        imported = conn.execute(
            """SELECT mip.id, mi.competitor_id, c.name AS competitor_name,
                      mi.platform_id, op.name AS platform_name, mi.emirate_id,
                      e.name_en AS emirate_name, mi.location_id, l.branch_name AS location_name,
                      mm.product_variant_id,
                      p.name AS item_name, cat.name AS category_name,
                      pv.size_name, pv.normalized_size, pv.crust_type,
                      mip.price, mip.observed_at, mip.verification_status,
                      mip.source_url, 'menu import' AS source_kind
               FROM menu_item_prices mip
               JOIN platform_menu_items mi ON mi.id=mip.platform_menu_item_id
               JOIN menu_item_matches mm ON mm.platform_menu_item_id=mi.id AND mm.status='approved'
               JOIN competitors c ON c.id=mi.competitor_id
               JOIN ordering_platforms op ON op.id=mi.platform_id
               JOIN emirates e ON e.id=mi.emirate_id
               LEFT JOIN locations l ON l.id=mi.location_id
               JOIN product_variants pv ON pv.id=mm.product_variant_id
               JOIN products p ON p.id=pv.product_id
               JOIN categories cat ON cat.id=p.category_id
               ORDER BY mip.observed_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return sorted(legacy + [dict(r) for r in imported], key=lambda r: str(r["observed_at"]), reverse=True)[:limit]
    finally:
        conn.close()


def get_latest_fee_observations(db_path: Optional[str] = None) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """WITH ranked AS (
                   SELECT f.*, ROW_NUMBER() OVER (
                       PARTITION BY f.competitor_id,f.platform_id,f.emirate_id,COALESCE(f.location_id,0)
                       ORDER BY f.observed_at DESC,f.id DESC) AS rn
                   FROM menu_fee_observations f)
               SELECT r.*, c.name AS competitor_name, op.name AS platform_name,
                      e.name_en AS emirate_name, l.branch_name AS location_name
               FROM ranked r JOIN competitors c ON c.id=r.competitor_id
               JOIN ordering_platforms op ON op.id=r.platform_id
               JOIN emirates e ON e.id=r.emirate_id
               LEFT JOIN locations l ON l.id=r.location_id WHERE r.rn=1
               ORDER BY c.name,op.name,e.display_order"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_fee_observation(
    competitor_id: int, platform_id: int, emirate_id: int, source_url: str,
    fees: Mapping[str, Optional[float]], observed_by: str,
    evidence_content: Optional[bytes] = None, evidence_name: Optional[str] = None,
    location_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> int:
    if not observed_by.strip() or not _valid_http_url(source_url):
        raise ValueError("A reviewer name and valid source URL are required.")
    if not any(v is not None for v in fees.values()):
        raise ValueError("Enter at least one observed fee or minimum order value.")
    timestamp = now_uae()
    conn = get_connection(db_path)
    try:
        platform = conn.execute("SELECT channel_id FROM ordering_platforms WHERE id=?", (platform_id,)).fetchone()
        if not platform:
            raise ValueError("Selected platform is unavailable.")
        run = conn.execute(
            """INSERT INTO research_runs (run_uuid,competitor_id,platform_id,channel_id,
                  emirate_id,status,items_extracted,items_verified,started_at,completed_at,notes)
               VALUES (?,?,?,?,?,'completed',1,0,?,?,?)""",
            (str(uuid.uuid4()),competitor_id,platform_id,platform["channel_id"],emirate_id,
             timestamp,timestamp,"Manual checkout-fee observation; verification requires retained evidence."),
        )
        run_id = run.lastrowid
        evidence_id = None
        verified = "unverified"
        if evidence_content:
            digest = hashlib.sha256(evidence_content).hexdigest()
            ext = Path(evidence_name or "").suffix.casefold()
            evidence_type = "screenshot" if ext in {".png", ".jpg", ".jpeg", ".webp"} else "html_snapshot"
            evidence = conn.execute(
                """INSERT INTO evidence_records (run_id,evidence_type,source_url,artifact_content,
                      file_hash_sha256,captured_at,notes) VALUES (?,?,?,?,?,?,?)""",
                (run_id,evidence_type,source_url,evidence_content,digest,timestamp,
                 "Manually uploaded checkout evidence; retained as supplied."),
            )
            evidence_id = evidence.lastrowid
            verified = "verified"
        row = conn.execute(
            """INSERT INTO menu_fee_observations
               (competitor_id,platform_id,emirate_id,location_id,research_run_id,delivery_fee,service_fee,
                small_order_fee,packaging_fee,other_fee,minimum_order_amount,observed_at,
                source_url,evidence_id,verification_status,verified_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (competitor_id,platform_id,emirate_id,location_id,run_id,fees.get("delivery_fee"),fees.get("service_fee"),
             fees.get("small_order_fee"),fees.get("packaging_fee"),fees.get("other_fee"),
             fees.get("minimum_order_amount"),timestamp,source_url,evidence_id,verified,
             observed_by.strip() if verified == "verified" else None),
        )
        if verified == "verified":
            conn.execute("UPDATE research_runs SET items_verified=1 WHERE id=?", (run_id,))
        conn.commit()
        return row.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_promotion(
    competitor_id: int, platform_id: Optional[int], emirate_id: Optional[int],
    title: str, description: str, promotion_type: str, source_url: str,
    discount_amount: Optional[float], discount_percentage: Optional[float],
    starts_at: Optional[str], ends_at: Optional[str], minimum_order_value: Optional[float],
    maximum_discount: Optional[float], weekdays: Sequence[int], reviewer: str,
    evidence_content: Optional[bytes] = None, evidence_name: Optional[str] = None,
    eligible_variant_ids: Sequence[int] = (), db_path: Optional[str] = None,
    promo_code: Optional[str] = None,
) -> int:
    if promotion_type not in PROMOTION_TYPES:
        raise ValueError("Unsupported promotion type.")
    if not title.strip() or not reviewer.strip() or not _valid_http_url(source_url):
        raise ValueError("Promotion title, reviewer, and valid source URL are required.")
    if starts_at and ends_at and starts_at > ends_at:
        raise ValueError("Promotion end date must be on or after its start date.")
    if any(day < 0 or day > 6 for day in weekdays):
        raise ValueError("Weekday values must be 0 (Monday) through 6 (Sunday).")
    timestamp = now_uae()
    conn = get_connection(db_path)
    try:
        channel_id = None
        if platform_id is not None:
            platform = conn.execute("SELECT channel_id FROM ordering_platforms WHERE id=?", (platform_id,)).fetchone()
            if not platform:
                raise ValueError("Selected platform is unavailable.")
            channel_id = platform["channel_id"]
        # Existing promotions preserve their constrained legacy type; the detail
        # row stores the full new vocabulary without rewriting old promotion rows.
        legacy_type = {
            "percentage_discount": "percentage_discount", "fixed_discount": "flat_discount",
            "bogo": "bogo", "free_delivery": "free_item", "pizza_deal": "combo",
            "meal_deal": "meal_deal", "combo_offer": "combo", "platform_discount": "other",
            "minimum_spend": "other", "first_order": "other", "loyalty": "other", "other": "other",
        }[promotion_type]
        run = conn.execute(
            """INSERT INTO research_runs (run_uuid,competitor_id,platform_id,channel_id,
                  emirate_id,status,items_extracted,items_verified,started_at,completed_at,notes)
               VALUES (?,?,?,?,?,'completed',1,0,?,?,?)""",
            (str(uuid.uuid4()),competitor_id,platform_id,channel_id,emirate_id,timestamp,timestamp,
             "Manual promotion record; status is verified only when source evidence is attached."),
        )
        run_id = run.lastrowid
        evidence_id = None
        verification_status = "unverified"
        if evidence_content:
            digest = hashlib.sha256(evidence_content).hexdigest()
            ext = Path(evidence_name or "").suffix.casefold()
            evidence_type = "screenshot" if ext in {".png", ".jpg", ".jpeg", ".webp"} else "html_snapshot"
            evidence = conn.execute(
                """INSERT INTO evidence_records (run_id,evidence_type,source_url,artifact_content,
                      file_hash_sha256,captured_at,notes) VALUES (?,?,?,?,?,?,?)""",
                (run_id,evidence_type,source_url,evidence_content,digest,timestamp,
                 "Manually uploaded promotion evidence; retained as supplied."),
            )
            evidence_id = evidence.lastrowid
            verification_status = "verified"
        promo = conn.execute(
            """INSERT INTO promotions (competitor_id,platform_id,emirate_id,title,description,
                 promo_type,discount_amount,discount_percentage,promo_code,starts_at,ends_at,source_url,
                 evidence_id,is_active,terms_conditions)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
            (competitor_id,platform_id,emirate_id,title.strip(),description.strip() or None,legacy_type,
             discount_amount,discount_percentage,promo_code.strip() if promo_code else None,
             starts_at,ends_at,source_url,evidence_id,description.strip() or None),
        )
        promo_id = promo.lastrowid
        conn.execute(
            """INSERT INTO promotion_terms (promotion_id,promotion_type,minimum_order_value,
                 maximum_discount,last_verified_at,verified_by,verification_status,notes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (promo_id,promotion_type,minimum_order_value,maximum_discount,
             timestamp if evidence_content else None,reviewer.strip(),verification_status,
             "Source evidence attached." if evidence_content else "Awaiting retained source evidence."),
        )
        for weekday in sorted(set(weekdays)):
            conn.execute("INSERT INTO promotion_weekdays (promotion_id,weekday) VALUES (?,?)", (promo_id,weekday))
        for variant_id in sorted(set(eligible_variant_ids)):
            conn.execute(
                "INSERT INTO promotion_item_eligibility (promotion_id,product_variant_id) VALUES (?,?)",
                (promo_id,variant_id),
            )
        if verification_status == "verified":
            conn.execute("UPDATE research_runs SET items_verified=1 WHERE id=?", (run_id,))
        conn.commit()
        return promo_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_promotion_records(db_path: Optional[str] = None) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT p.*, c.name AS competitor_name, op.name AS platform_name,
                      e.name_en AS emirate_name, t.promotion_type, t.minimum_order_value,
                      t.maximum_discount, t.last_verified_at, t.verified_by,
                      COALESCE(t.verification_status,'unverified') AS verification_status,
                      t.notes AS verification_notes
               FROM promotions p JOIN competitors c ON c.id=p.competitor_id
               LEFT JOIN ordering_platforms op ON op.id=p.platform_id
               LEFT JOIN emirates e ON e.id=p.emirate_id
               LEFT JOIN promotion_terms t ON t.promotion_id=p.id
               ORDER BY p.starts_at DESC,p.id DESC"""
        ).fetchall()
        result = [dict(r) for r in rows]
        for promo in result:
            promo["weekdays"] = [r["weekday"] for r in conn.execute(
                "SELECT weekday FROM promotion_weekdays WHERE promotion_id=? ORDER BY weekday",
                (promo["id"],),
            ).fetchall()]
            promo["eligible_variant_ids"] = [r["product_variant_id"] for r in conn.execute(
                "SELECT product_variant_id FROM promotion_item_eligibility WHERE promotion_id=? AND product_variant_id IS NOT NULL",
                (promo["id"],),
            ).fetchall()]
        return result
    finally:
        conn.close()


def promotion_status(promotion: Mapping[str, Any], today=None) -> str:
    today = today or datetime.now(UAE_TZ).date()
    if promotion.get("verification_status") != "verified" or not promotion.get("last_verified_at"):
        return "Unverified"
    try:
        verified_date = datetime.fromisoformat(str(promotion["last_verified_at"])).date()
        start = date.fromisoformat(str(promotion["starts_at"])[:10]) if promotion.get("starts_at") else None
        end = date.fromisoformat(str(promotion["ends_at"])[:10]) if promotion.get("ends_at") else None
    except ValueError:
        return "Needs review"
    if end and end < today:
        return "Expired"
    if start and start > today:
        return "Upcoming"
    if (today - verified_date).days > 7:
        return "Stale"
    return "Active" if promotion.get("is_active") else "Expired"


def get_canonical_variants(
    competitor_id: Optional[int] = None, db_path: Optional[str] = None
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        sql = """SELECT pv.id AS product_variant_id,p.id AS product_id,p.name AS item_name,
                        p.normalized_name,p.description,p.ingredients,p.competitor_id,
                        c.name AS competitor_name,cat.id AS category_id,cat.code AS category_code,
                        cat.name AS category_name,pv.size_name,pv.normalized_size,pv.crust_type
                 FROM product_variants pv JOIN products p ON p.id=pv.product_id
                 JOIN competitors c ON c.id=p.competitor_id
                 JOIN categories cat ON cat.id=p.category_id
                 WHERE pv.is_active=1"""
        params: list[Any] = []
        if competitor_id is not None:
            sql += " AND p.competitor_id=?"
            params.append(competitor_id)
        sql += " ORDER BY c.name,cat.display_order,p.name,pv.normalized_size,pv.crust_type"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def calculate_cart_quotes(
    competitor_id: int,
    emirate_id: int,
    quantities: Mapping[int, int],
    comparison_rows: Sequence[Mapping[str, Any]],
    fee_rows: Sequence[Mapping[str, Any]],
    promotions: Sequence[Mapping[str, Any]],
    location_id: Optional[int] = None,
    platform_catalog: Sequence[Mapping[str, Any]] = (),
    customizations: Optional[Mapping[int, Mapping[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Calculate item/fee estimates; unknown inputs keep final_total unset."""
    if not quantities:
        return []
    relevant_prices = [
        row for row in comparison_rows
        if row["competitor_id"] == competitor_id and row["emirate_id"] == emirate_id
        and row.get("location_id") == location_id
    ]
    price_index = {(r["platform_id"], r["product_variant_id"]): r for r in relevant_prices}
    platform_names = {r["platform_id"]: r["platform_name"] for r in relevant_prices}
    platform_names.update({p["id"]: p["name"] for p in platform_catalog})
    platforms = sorted(platform_names, key=lambda pid: platform_names[pid])
    result = []
    customizations = customizations or {}
    today = datetime.now(UAE_TZ).date()
    for platform_id in platforms:
        platform_name = platform_names[platform_id]
        lines = []
        subtotal = 0.0
        customization_total = 0.0
        all_prices_known = True
        all_available = True
        selected_promos = []
        for variant_id, quantity in quantities.items():
            customization = customizations.get(variant_id, {})
            customization_amount = float(customization.get("amount") or 0)
            if customization_amount < 0:
                raise ValueError("Customization charges cannot be negative.")
            customization_total += customization_amount * quantity
            row = price_index.get((platform_id, variant_id))
            if not row or row.get("price") is None:
                all_prices_known = False
                lines.append({"product_variant_id": variant_id, "unit_price": None, "availability": "unknown",
                              "customization_amount": customization_amount,
                              "customization_notes": customization.get("notes")})
                continue
            availability = row.get("availability") or "unknown"
            if availability != "available":
                all_available = False
            subtotal += float(row["price"]) * quantity
            lines.append({
                "product_variant_id": variant_id,
                "platform_menu_item_id": row.get("platform_menu_item_id"),
                "unit_price": float(row["price"]),
                "availability": availability,
                "customization_amount": customization_amount,
                "customization_notes": customization.get("notes"),
            })

        fees = next((f for f in fee_rows if f["competitor_id"] == competitor_id
                     and f["platform_id"] == platform_id and f["emirate_id"] == emirate_id
                     and f.get("location_id") == location_id and f["verification_status"] == "verified"), None)
        fee_fields = ("delivery_fee", "service_fee", "small_order_fee", "packaging_fee", "other_fee")
        fee_values = {key: (fees.get(key) if fees else None) for key in fee_fields}
        fees_known = all(value is not None for value in fee_values.values())
        minimum_order = fees.get("minimum_order_amount") if fees else None

        for promo in promotions:
            if promotion_status(promo, today) != "Active":
                continue
            if promo.get("platform_id") not in (None, platform_id):
                continue
            if promo.get("emirate_id") not in (None, emirate_id):
                continue
            weekdays = promo.get("weekdays") or []
            if weekdays and today.weekday() not in weekdays:
                continue
            min_order = promo.get("minimum_order_value")
            if min_order is not None and (not all_prices_known or subtotal + customization_total < float(min_order)):
                continue
            eligible = set(promo.get("eligible_variant_ids") or [])
            eligible_subtotal = sum(
                (line["unit_price"] or 0) * int(quantities[line["product_variant_id"]])
                for line in lines if line["product_variant_id"] in eligible
            )
            kind = promo.get("promotion_type")
            discount = 0.0
            if kind == "percentage_discount" and eligible:
                discount = eligible_subtotal * float(promo.get("discount_percentage") or 0) / 100
            elif kind == "fixed_discount" and eligible:
                discount = min(eligible_subtotal, float(promo.get("discount_amount") or 0))
            elif kind == "bogo" and eligible:
                discount = sum(
                    (line["unit_price"] or 0) * (int(quantities[line["product_variant_id"]]) // 2)
                    for line in lines if line["product_variant_id"] in eligible
                )
            elif kind == "free_delivery" and fees and fees.get("delivery_fee") is not None:
                discount = float(fees["delivery_fee"])
            if promo.get("maximum_discount") is not None:
                discount = min(discount, float(promo["maximum_discount"]))
            if discount > 0:
                selected_promos.append((discount, promo["title"]))

        discount, promo_title = max(selected_promos, default=(0.0, None), key=lambda row: row[0])
        if promo_title:
            for line in lines:
                line["promotion_discount"] = 0.0
            # A cart-level offer is recorded in the quote. The per-item discount
            # is intentionally not allocated where terms don't specify allocation.
        complete = all_prices_known and all_available and fees_known
        if minimum_order is not None and all_prices_known and subtotal + customization_total < float(minimum_order):
            complete = False
        known_charges = sum(float(value) for value in fee_values.values() if value is not None)
        final_total = subtotal + customization_total - discount + known_charges if complete else None
        result.append({
            "platform_id": platform_id,
            "platform_name": platform_name,
            "quote_status": "estimate" if complete else "incomplete",
            "item_subtotal": round(subtotal, 2) if all_prices_known else None,
            "customization_total": round(customization_total, 2),
            "promotion_discount": round(discount, 2),
            **fee_values,
            "minimum_order_amount": minimum_order,
            "final_total": round(final_total, 2) if final_total is not None else None,
            "promotion_title": promo_title,
            "notes": (
                "Estimate from latest recorded menu prices and verified fees; not a checkout quote. "
                "Unverified promotions are not applied."
                if complete else
                "Incomplete: required item price, availability, or verified fee data is missing. "
                "No checkout total is asserted."
            ),
            "lines": lines,
        })
    return result


def save_cart_comparison(
    competitor_id: int, emirate_id: int, quantities: Mapping[int, int],
    quotes: Sequence[Mapping[str, Any]], created_by: str,
    db_path: Optional[str] = None,
    location_id: Optional[int] = None,
    customizations: Optional[Mapping[int, Mapping[str, Any]]] = None,
) -> int:
    """Persist a priced cart snapshot; incomplete totals stay NULL."""
    if not quantities or any(qty <= 0 for qty in quantities.values()):
        raise ValueError("Choose at least one item with a positive quantity.")
    conn = get_connection(db_path)
    timestamp = now_uae()
    customizations = customizations or {}
    try:
        comparison = conn.execute(
            "INSERT INTO cart_comparisons (competitor_id,emirate_id,location_id,created_at,created_by) VALUES (?,?,?,?,?)",
            (competitor_id,emirate_id,location_id,timestamp,created_by.strip() or None),
        )
        comparison_id = comparison.lastrowid
        item_ids: dict[int, int] = {}
        for variant_id, quantity in quantities.items():
            cursor = conn.execute(
                "INSERT INTO cart_comparison_items (comparison_id,product_variant_id,quantity,customization_notes,customization_amount) VALUES (?,?,?,?,?)",
                (comparison_id,variant_id,quantity,customizations.get(variant_id,{}).get("notes"),
                 float(customizations.get(variant_id,{}).get("amount") or 0)),
            )
            item_ids[variant_id] = cursor.lastrowid
        for quote in quotes:
            cursor = conn.execute(
                """INSERT INTO cart_platform_quotes
                   (comparison_id,platform_id,quote_status,item_subtotal,customization_total,
                    promotion_discount,delivery_fee,service_fee,small_order_fee,packaging_fee,
                    other_fee,minimum_order_amount,final_total,observed_at,notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (comparison_id,quote["platform_id"],quote["quote_status"],quote.get("item_subtotal"),
                 quote.get("customization_total",0),quote.get("promotion_discount"),quote.get("delivery_fee"),
                 quote.get("service_fee"),quote.get("small_order_fee"),quote.get("packaging_fee"),
                 quote.get("other_fee"),quote.get("minimum_order_amount"),quote.get("final_total"),
                 timestamp,quote.get("notes")),
            )
            quote_id = cursor.lastrowid
            for line in quote.get("lines", []):
                conn.execute(
                    """INSERT INTO cart_quote_lines
                       (quote_id,comparison_item_id,platform_menu_item_id,unit_price,
                        customization_amount,promotion_discount,availability)
                       VALUES (?,?,?,?,?,?,?)""",
                    (quote_id,item_ids[line["product_variant_id"]],line.get("platform_menu_item_id"),
                     line.get("unit_price"),line.get("customization_amount",0),
                     line.get("promotion_discount",0),line.get("availability","unknown")),
                )
        conn.commit()
        return comparison_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
