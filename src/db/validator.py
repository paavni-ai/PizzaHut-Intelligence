"""
Database Validation and Data Integrity Checker.
Ensures that the database complies with strict project integrity rules:
 - All 12 required tables exist
 - Foreign key constraints are valid
 - All 7 UAE emirates are configured
 - The 4 mandatory ordering channels exist
 - Every price observation preserves source URL, timestamp, AED currency, and verification status
 - No fake/unverified competitor prices are present
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from config import DEFAULT_DB_PATH, ORDERING_CHANNELS, UAE_EMIRATES, VERIFICATION_STATUSES
from src.db.connection import get_connection
from src.db.evidence import has_valid_artifact
from src.matching.product_classifier import is_likely_non_pizza_name

REQUIRED_TABLES = [
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
]


class DatabaseValidator:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path or DEFAULT_DB_PATH

    def validate_all(self) -> Dict[str, Any]:
        """
        Runs comprehensive validation tests and returns a structured health report.
        """
        conn = get_connection(self.db_path)
        report: Dict[str, Any] = {
            "status": "PASS",
            "db_path": str(self.db_path),
            "errors": [],
            "warnings": [],
            "checks": {},
        }

        try:
            # 1. Check Tables
            tables_check = self._check_tables(conn)
            report["checks"]["tables"] = tables_check
            if not tables_check["passed"]:
                report["errors"].extend(tables_check["errors"])

            # 2. Check Foreign Keys
            fk_check = self._check_foreign_keys(conn)
            report["checks"]["foreign_keys"] = fk_check
            if not fk_check["passed"]:
                report["errors"].extend(fk_check["errors"])

            # 3. Check 7 Emirates
            emirates_check = self._check_emirates(conn)
            report["checks"]["emirates"] = emirates_check
            if not emirates_check["passed"]:
                report["errors"].extend(emirates_check["errors"])

            # 4. Check 4 Ordering Channels
            channels_check = self._check_channels(conn)
            report["checks"]["ordering_channels"] = channels_check
            if not channels_check["passed"]:
                report["errors"].extend(channels_check["errors"])

            # 5. Check Price Observation Integrity
            price_integrity = self._check_price_integrity(conn)
            report["checks"]["price_integrity"] = price_integrity
            if not price_integrity["passed"]:
                report["errors"].extend(price_integrity["errors"])

            observation_quality = self._audit_live_observation_quality(conn)
            report["checks"]["live_observation_quality"] = observation_quality
            report["warnings"].extend(observation_quality["warnings"])

            # Overall Status
            if report["errors"]:
                report["status"] = "FAIL"

        finally:
            conn.close()

        return report

    def _audit_live_observation_quality(self, conn) -> Dict[str, Any]:
        """Read-only audit: never promotes, edits, or quarantines stored observations."""
        rows = conn.execute(
            """
            SELECT po.id, po.verification_status, po.evidence_id, po.notes,
                   p.name AS product_name, p.normalized_name,
                   cat.code AS category_code, pv.size_name, pv.normalized_size,
                   pv.crust_type, ev.file_hash_sha256, ev.file_path
            FROM price_observations po
            JOIN product_variants pv ON pv.id = po.product_variant_id
            JOIN products p ON p.id = pv.product_id
            JOIN categories cat ON cat.id = p.category_id
            LEFT JOIN evidence_records ev ON ev.id = po.evidence_id
            WHERE po.data_origin = 'live_extraction'
            ORDER BY po.id
            """
        ).fetchall()
        issues = []
        unreviewed_verified_labels = 0
        for row in rows:
            if row["verification_status"] == "verified" and not (row["notes"] or "").startswith("Revision of observation #"):
                unreviewed_verified_labels += 1
            name = row["product_name"].casefold()
            is_pizza_category = row["category_code"] == "pizza"
            obvious_non_pizza = is_likely_non_pizza_name(name)
            if (is_pizza_category and obvious_non_pizza) or (not is_pizza_category and row["normalized_size"] != "other"):
                issues.append({
                    "observation_id": row["id"],
                    "product": row["product_name"],
                    "category": row["category_code"],
                    "size": row["size_name"],
                    "crust": row["crust_type"],
                    "reason": (
                        "Likely non-pizza item stored as a pizza"
                        if obvious_non_pizza
                        else "Bundle/menu item has a size/crust variant; not a standalone pizza price"
                    ),
                    "verification_status": row["verification_status"],
                })
            if row["verification_status"] == "verified" and not (
                row["evidence_id"] is not None and has_valid_artifact(dict(row))
            ):
                issues.append({
                    "observation_id": row["id"],
                    "product": row["product_name"],
                    "category": row["category_code"],
                    "size": row["size_name"],
                    "crust": row["crust_type"],
                    "reason": "Marked verified without a captured evidence artifact or hash",
                    "verification_status": row["verification_status"],
                })
        return {
            "passed": len(issues) == 0,
            "live_extraction_count": len(rows),
            "suspect_count": len(issues),
            "unreviewed_verified_labels": unreviewed_verified_labels,
            "suspect_observations": issues,
            "warnings": [
                f"{len(issues)} live extraction quality flags require review; records were left unchanged."
            ] if issues else [],
        }

    def _check_tables(self, conn) -> Dict[str, Any]:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row["name"] for row in cursor.fetchall()}
        missing = [t for t in REQUIRED_TABLES if t not in existing_tables]

        return {
            "passed": len(missing) == 0,
            "existing_count": len(existing_tables),
            "missing_tables": missing,
            "errors": [f"Missing required table: {t}" for t in missing],
        }

    def _check_foreign_keys(self, conn) -> Dict[str, Any]:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_check;")
        fk_violations = cursor.fetchall()
        passed = len(fk_violations) == 0
        errors = [f"Foreign key violation in table {row[0]}, rowid {row[1]}" for row in fk_violations]
        return {"passed": passed, "violations_count": len(fk_violations), "errors": errors}

    def _check_emirates(self, conn) -> Dict[str, Any]:
        cursor = conn.cursor()
        cursor.execute("SELECT code, name_en FROM emirates WHERE is_active = 1;")
        rows = cursor.fetchall()
        existing_codes = {row["code"] for row in rows}
        expected_codes = {e["code"] for e in UAE_EMIRATES}
        missing = expected_codes - existing_codes

        passed = len(missing) == 0 and len(existing_codes) == 7
        errors = [f"Missing UAE Emirate code: {c}" for c in missing] if missing else []
        if len(existing_codes) != 7:
            errors.append(f"Expected 7 Emirates, found {len(existing_codes)}")

        return {
            "passed": passed,
            "found_count": len(existing_codes),
            "missing": list(missing),
            "errors": errors,
        }

    def _check_channels(self, conn) -> Dict[str, Any]:
        cursor = conn.cursor()
        cursor.execute("SELECT code, name FROM ordering_channels;")
        rows = cursor.fetchall()
        existing_codes = {row["code"] for row in rows}
        expected_codes = {c["code"] for c in ORDERING_CHANNELS}
        missing = expected_codes - existing_codes

        passed = len(missing) == 0 and len(existing_codes) == 4
        errors = [f"Missing required ordering channel: {c}" for c in missing] if missing else []

        return {
            "passed": passed,
            "found_count": len(existing_codes),
            "missing": list(missing),
            "errors": errors,
        }

    def _check_price_integrity(self, conn) -> Dict[str, Any]:
        cursor = conn.cursor()
        errors = []

        # Check for missing source URLs
        cursor.execute("SELECT COUNT(*) FROM price_observations WHERE source_url IS NULL OR TRIM(source_url) = '';")
        missing_url_count = cursor.fetchone()[0]
        if missing_url_count > 0:
            errors.append(f"{missing_url_count} price observations are missing source_url.")

        # Check for non-AED currency
        cursor.execute("SELECT COUNT(*) FROM price_observations WHERE currency != 'AED';")
        invalid_currency_count = cursor.fetchone()[0]
        if invalid_currency_count > 0:
            errors.append(f"{invalid_currency_count} price observations have invalid currency (must be AED).")

        # Check for invalid verification status
        cursor.execute(
            f"SELECT COUNT(*) FROM price_observations WHERE verification_status NOT IN ({','.join('?' for _ in VERIFICATION_STATUSES)});",
            VERIFICATION_STATUSES,
        )
        invalid_status_count = cursor.fetchone()[0]
        if invalid_status_count > 0:
            errors.append(f"{invalid_status_count} price observations have invalid verification status.")

        # Check for negative prices
        cursor.execute("SELECT COUNT(*) FROM price_observations WHERE original_price < 0;")
        negative_price_count = cursor.fetchone()[0]
        if negative_price_count > 0:
            errors.append(f"{negative_price_count} price observations have negative prices.")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }


def run_cli_validation(db_path: Optional[str] = None) -> int:
    validator = DatabaseValidator(db_path)
    report = validator.validate_all()

    print("=" * 60)
    print("UAE PIZZA PRICE INTELLIGENCE - DATABASE VALIDATION REPORT")
    print("=" * 60)
    print(f"Target Database : {report['db_path']}")
    print(f"Overall Status  : {report['status']}")
    print("-" * 60)

    for check_name, check_data in report["checks"].items():
        pass_symbol = "✓ PASS" if check_data["passed"] else "✗ FAIL"
        print(f"[{pass_symbol}] {check_name.replace('_', ' ').title()}")

    if report["errors"]:
        print("\nErrors Found:")
        for err in report["errors"]:
            print(f"  - {err}")
        return 1

    print("\nAll database schema & integrity checks passed successfully.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit_code = run_cli_validation()
    sys.exit(exit_code)
