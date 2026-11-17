"""
Real Accuracy Evaluation and Human Correction Engine.
Strictly calculates accuracy from actual evaluated cases against verified benchmarks.
Never invents an accuracy percentage.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from config import DEFAULT_DB_PATH
from src.db.connection import get_connection
from src.db.evidence import has_valid_artifact
from src.db.repository import PizzaIntelligenceRepository
from src.matching.benchmark_service import get_all_benchmarks
from src.matching.product_classifier import is_likely_non_pizza_name


class AccuracyEngine:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path

    def evaluate_collection_accuracy(self, tolerance_aed: float = 0.50) -> Dict[str, Any]:
        """
        Compares latest active collected price observations against ground-truth benchmarks.
        Classifies cases as CORRECT, INCORRECT, MISSING, or UNCERTAIN.
        Calculates accuracy % only if evaluated cases > 0.
        """
        benchmarks = get_all_benchmarks(self.db_path)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cases: List[Dict[str, Any]] = []
        correct_count = 0
        incorrect_count = 0
        missing_count = 0
        uncertain_count = 0

        try:
            for b in benchmarks:
                # Legacy seeded rows are retained for review, but cannot act as
                # ground truth until a reviewer linked captured source evidence.
                case_detail = {
                    "benchmark_id": b["id"],
                    "competitor": b["competitor_name"],
                    "product": b["product_name"],
                    "size": b["normalized_size"].upper(),
                    "expected_price": b["expected_price"] if b["is_trusted"] else None,
                    "collected_price": None,
                    "difference_aed": None,
                    "difference_pct": None,
                    "classification": "UNCERTAIN",
                    "observation_id": None,
                    "source_url": b["source_url"],
                    "status_note": "Benchmark provenance has not been independently documented.",
                }
                if not b["is_trusted"]:
                    uncertain_count += 1
                    cases.append(case_detail)
                    continue
                provenance = b.get("provenance") or {}
                benchmark_evidence = cursor.execute(
                    "SELECT source_url, file_hash_sha256, file_path FROM evidence_records WHERE id = ?",
                    (provenance.get("evidence_id"),),
                ).fetchone()
                if (
                    not benchmark_evidence
                    or benchmark_evidence["source_url"] != b["source_url"]
                    or not has_valid_artifact(dict(benchmark_evidence))
                ):
                    case_detail["expected_price"] = None
                    case_detail["status_note"] = "Benchmark source capture is missing or does not match its source URL."
                    uncertain_count += 1
                    cases.append(case_detail)
                    continue

                # Match exact identity/market dimensions; classify category mismatches as uncertain.
                cursor.execute(
                    """
                    SELECT po.id, po.original_price, po.verification_status, po.source_url,
                           po.collected_at, po.evidence_id, po.data_origin, po.notes,
                           ev.file_hash_sha256, ev.file_path, cat.code AS category_code,
                           p.name as product_name, pv.size_name
                    FROM price_observations po
                    JOIN product_variants pv ON po.product_variant_id = pv.id
                    JOIN products p ON pv.product_id = p.id
                    JOIN categories cat ON cat.id = p.category_id
                    LEFT JOIN evidence_records ev ON ev.id = po.evidence_id
                    WHERE po.competitor_id = ?
                      AND p.normalized_name = ?
                      AND pv.normalized_size = ?
                      AND po.channel_id = ?
                      AND po.emirate_id = ?
                      AND po.is_quarantined = 0
                    ORDER BY po.collected_at DESC, po.id DESC
                    LIMIT 1;
                    """,
                    (
                        b["competitor_id"], b["normalized_name"], b["normalized_size"],
                        b["channel_id"], b["emirate_id"],
                    ),
                )
                obs = cursor.fetchone()

                if not obs:
                    case_detail["classification"] = "MISSING"
                    case_detail["status_note"] = "No active collected observation found for this benchmark."
                    missing_count += 1
                elif (
                    obs["verification_status"] != "verified"
                    or obs["evidence_id"] is None
                    or not has_valid_artifact(dict(obs))
                    or obs["data_origin"] not in {"live_extraction", "manual_entry"}
                    or obs["category_code"] != "pizza"
                    or is_likely_non_pizza_name(obs["product_name"])
                    or (
                        obs["data_origin"] == "live_extraction"
                        and not (obs["notes"] or "").startswith("Revision of observation #")
                    )
                ):
                    case_detail["classification"] = "UNCERTAIN"
                    case_detail["observation_id"] = obs["id"]
                    case_detail["collected_price"] = obs["original_price"]
                    case_detail["status_note"] = "Observation lacks a human QA revision, verified status, captured evidence, or eligible origin."
                    uncertain_count += 1
                else:
                    coll_price = float(obs["original_price"])
                    exp_price = float(b["expected_price"])
                    diff = round(coll_price - exp_price, 2)
                    diff_pct = round((diff / exp_price) * 100, 1) if exp_price > 0 else 0.0

                    case_detail["observation_id"] = obs["id"]
                    case_detail["collected_price"] = coll_price
                    case_detail["difference_aed"] = diff
                    case_detail["difference_pct"] = diff_pct

                    if abs(diff) <= tolerance_aed:
                        case_detail["classification"] = "CORRECT"
                        case_detail["status_note"] = f"Price matches benchmark within {tolerance_aed} AED tolerance."
                        correct_count += 1
                    else:
                        case_detail["classification"] = "INCORRECT"
                        case_detail["status_note"] = f"Price variance detected ({'+' if diff > 0 else ''}{diff} AED)."
                        incorrect_count += 1

                cases.append(case_detail)

            # Strictly calculate accuracy from evaluated cases
            total_evaluated = correct_count + incorrect_count
            accuracy_pct = (
                round((correct_count / total_evaluated) * 100, 1)
                if total_evaluated > 0
                else None
            )

            eval_uuid = str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()

            # Record in accuracy_evaluations table
            cursor.execute(
                """
                INSERT INTO accuracy_evaluations (
                    evaluation_uuid, total_evaluated, correct_count, incorrect_count,
                    missing_count, uncertain_count, accuracy_percentage, evaluated_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    eval_uuid,
                    total_evaluated,
                    correct_count,
                    incorrect_count,
                    missing_count,
                    uncertain_count,
                    accuracy_pct,
                    now_iso,
                    json.dumps(cases),
                ),
            )
            conn.commit()

            return {
                "evaluation_uuid": eval_uuid,
                "total_benchmarks": len(benchmarks),
                "total_evaluated": total_evaluated,
                "correct_count": correct_count,
                "incorrect_count": incorrect_count,
                "missing_count": missing_count,
                "uncertain_count": uncertain_count,
                "accuracy_percentage": accuracy_pct,
                "evaluated_at": now_iso,
                "cases": cases,
            }
        finally:
            conn.close()

    def apply_human_correction(
        self,
        observation_id: int,
        corrected_price: float,
        reason: str,
        evidence_id: int,
        user_name: str = "Lead Market Analyst",
    ) -> Dict[str, Any]:
        """
        Applies a verified human correction to an observation and logs an immutable audit trail.
        """
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT original_price, source_url, data_origin, is_quarantined FROM price_observations WHERE id = ?",
                (observation_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Observation ID {observation_id} not found.")
            if row["data_origin"] == "quarantined_seed" or row["is_quarantined"]:
                raise ValueError("Quarantined seed observations cannot be promoted or corrected.")
            evidence = conn.execute(
                "SELECT source_url, file_hash_sha256, file_path FROM evidence_records WHERE id = ?",
                (evidence_id,),
            ).fetchone()
            if (
                not evidence or evidence["source_url"] != row["source_url"]
                or not has_valid_artifact(dict(evidence))
            ):
                raise ValueError("A captured correction artifact for the same source URL is required.")
            prev_price = float(row["original_price"])
            now_iso = datetime.now(timezone.utc).isoformat()
        finally:
            conn.close()

        new_observation_id = PizzaIntelligenceRepository(self.db_path).append_observation_revision(
            observation_id,
            verification_status="verified",
            original_price=corrected_price,
            evidence_id=evidence_id,
            notes=f"Human correction by {user_name}: {reason}",
        )
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO human_corrections (
                    price_observation_id, previous_price, corrected_price,
                    correction_reason, corrected_by, corrected_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    observation_id, prev_price, corrected_price,
                    f"Revision #{new_observation_id}: {reason}", user_name, now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "observation_id": observation_id,
            "revision_observation_id": new_observation_id,
            "previous_price": prev_price,
            "corrected_price": corrected_price,
            "corrected_by": user_name,
            "corrected_at": now_iso,
        }

    def get_accuracy_history(self, limit: int = 25) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT * FROM accuracy_evaluations
                ORDER BY id DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_corrections_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT hc.*, po.source_url, p.name as product_name, c.name as competitor_name
                FROM human_corrections hc
                JOIN price_observations po ON hc.price_observation_id = po.id
                JOIN product_variants pv ON po.product_variant_id = pv.id
                JOIN products p ON pv.product_id = p.id
                JOIN competitors c ON po.competitor_id = c.id
                ORDER BY hc.id DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
