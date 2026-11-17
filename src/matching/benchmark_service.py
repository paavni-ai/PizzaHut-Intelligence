"""Benchmark management with explicit source provenance.

Legacy benchmark rows are returned for audit but are not trusted for scoring.
New trusted rows must point to a captured evidence record for the same URL.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from config import DEFAULT_DB_PATH
from src.db.connection import get_connection
from src.db.evidence import has_valid_artifact

_TRUST_MARKER = "verified_benchmark_v1:"


def add_verified_benchmark(
    *,
    competitor_id: int,
    product_name: str,
    normalized_name: str,
    normalized_size: str,
    channel_id: int,
    emirate_id: int,
    expected_price: float,
    source_url: str,
    evidence_id: int,
    verified_by: str,
    db_path: Optional[Union[str, Path]] = None,
    notes: str = "",
) -> int:
    """Append a human-reviewed benchmark linked to captured source evidence."""
    if not product_name.strip() or not normalized_name.strip():
        raise ValueError("Product name and canonical name are required.")
    if normalized_size not in {"personal", "small", "medium", "large", "xlarge", "other"}:
        raise ValueError("Unsupported normalized size.")
    if not math.isfinite(float(expected_price)) or expected_price < 0:
        raise ValueError("Expected price must be non-negative.")
    if not verified_by.strip():
        raise ValueError("Reviewer name is required.")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Benchmark source must be an HTTPS URL.")

    conn = get_connection(db_path)
    try:
        evidence = conn.execute(
            "SELECT source_url, file_hash_sha256, file_path FROM evidence_records WHERE id = ?",
            (evidence_id,),
        ).fetchone()
        if not evidence:
            raise ValueError("The linked evidence record does not exist.")
        if evidence["source_url"] != source_url:
            raise ValueError("Evidence URL must exactly match the benchmark source URL.")
        if not has_valid_artifact(dict(evidence)):
            raise ValueError("Evidence must include a readable artifact whose SHA-256 matches the capture record.")

        provenance = {
            "evidence_id": int(evidence_id),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "reviewer_notes": notes.strip(),
        }
        cursor = conn.execute(
            """
            INSERT INTO benchmarks (
                competitor_id, product_name, normalized_name, normalized_size,
                channel_id, emirate_id, expected_price, currency, source_url,
                verified_by, verified_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'AED', ?, ?, ?, ?)
            """,
            (
                competitor_id, product_name.strip(), normalized_name.strip(), normalized_size,
                channel_id, emirate_id, float(expected_price), source_url,
                verified_by.strip(), provenance["reviewed_at"],
                _TRUST_MARKER + json.dumps(provenance, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def seed_ground_truth_benchmarks(db_path: Optional[Union[str, Path]] = None) -> int:
    """Deprecated no-op retained for callers; fabricated defaults are never seeded."""
    return 0


def get_all_benchmarks(db_path: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT b.*, c.name AS competitor_name, c.code AS competitor_code,
                   ch.name AS channel_name, e.name_en AS emirate_name
            FROM benchmarks b
            JOIN competitors c ON b.competitor_id = c.id
            JOIN ordering_channels ch ON b.channel_id = ch.id
            JOIN emirates e ON b.emirate_id = e.id
            ORDER BY c.name, b.normalized_name, b.normalized_size, b.id
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["is_trusted"] = bool(item.get("notes") and item["notes"].startswith(_TRUST_MARKER))
            if item["is_trusted"]:
                try:
                    item["provenance"] = json.loads(item["notes"][len(_TRUST_MARKER):])
                except (TypeError, ValueError):
                    item["is_trusted"] = False
                    item["provenance"] = None
            else:
                item["provenance"] = None
            result.append(item)
        return result
    finally:
        conn.close()
