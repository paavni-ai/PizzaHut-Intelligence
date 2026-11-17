"""
Database Migration and Audit Script.
Applies schema upgrades (new audit columns, benchmarks, accuracy tables)
and audits/quarantines unsupported seeded price records from commercial reporting.
"""
from pathlib import Path
from typing import Optional, Union

from config import DEFAULT_DB_PATH
from src.db.connection import get_connection


def run_database_migration(db_path: Optional[Union[str, Path]] = None) -> None:
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # 1. Add missing columns to price_observations if not present
        cursor.execute("PRAGMA table_info(price_observations);")
        existing_cols = {row["name"] for row in cursor.fetchall()}

        new_columns = [
            # Unknown legacy rows must not be auto-labelled as live research.
            ("data_origin", "TEXT NOT NULL DEFAULT 'manual_entry'"),
            ("is_quarantined", "INTEGER NOT NULL DEFAULT 0"),
            ("quarantine_reason", "TEXT"),
            ("service_fee", "REAL DEFAULT 0.0"),
            ("vat_amount", "REAL DEFAULT 0.0"),
            ("discount_amount", "REAL DEFAULT 0.0"),
            ("checkout_total", "REAL DEFAULT 0.0"),
        ]

        for col_name, col_def in new_columns:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE price_observations ADD COLUMN {col_name} {col_def};")

        # 2. Create Benchmarks Table if not exists
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
                product_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                normalized_size TEXT NOT NULL CHECK (normalized_size IN ('personal', 'small', 'medium', 'large', 'xlarge', 'other')),
                channel_id INTEGER NOT NULL REFERENCES ordering_channels(id) ON DELETE RESTRICT,
                emirate_id INTEGER NOT NULL REFERENCES emirates(id) ON DELETE RESTRICT,
                expected_price REAL NOT NULL CHECK (expected_price >= 0),
                currency TEXT NOT NULL DEFAULT 'AED',
                source_url TEXT NOT NULL,
                verified_by TEXT NOT NULL,
                verified_at TEXT NOT NULL DEFAULT (datetime('now')),
                effective_date TEXT NOT NULL DEFAULT (date('now')),
                notes TEXT
            );
            """
        )

        # 3. Create Accuracy Evaluations Table if not exists
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accuracy_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluation_uuid TEXT NOT NULL UNIQUE,
                run_id INTEGER REFERENCES research_runs(id) ON DELETE SET NULL,
                total_evaluated INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                incorrect_count INTEGER NOT NULL DEFAULT 0,
                missing_count INTEGER NOT NULL DEFAULT 0,
                uncertain_count INTEGER NOT NULL DEFAULT 0,
                accuracy_percentage REAL,
                evaluated_at TEXT NOT NULL DEFAULT (datetime('now')),
                details_json TEXT
            );
            """
        )

        # 4. Create Human Corrections Audit Table if not exists
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS human_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                price_observation_id INTEGER NOT NULL REFERENCES price_observations(id) ON DELETE CASCADE,
                previous_price REAL NOT NULL,
                corrected_price REAL NOT NULL,
                correction_reason TEXT NOT NULL,
                corrected_by TEXT NOT NULL,
                corrected_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        # 5. Create Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_observations_quarantine ON price_observations(is_quarantined);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_benchmarks_lookup ON benchmarks(competitor_id, normalized_name, normalized_size, channel_id, emirate_id);")

        conn.commit()
    finally:
        conn.close()


def audit_and_quarantine_seeded_records(db_path: Optional[Union[str, Path]] = None) -> int:
    """
    Priority 1 Audit:
    Examines all observations in price_observations.
    Identifies records that originated from programmatic expansion rather than
    an individual per-branch live HTTP extract, and quarantines them from commercial KPIs.
    Preserves records in database for historical regression, but tags them is_quarantined = 1.
    """
    run_database_migration(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # Flag any observation from initial seed where note mentions "menu price in"
        cursor.execute(
            """
            UPDATE price_observations
            SET is_quarantined = 1,
                verification_status = 'needs_review',
                data_origin = 'quarantined_seed',
                quarantine_reason = 'Audited: Programmatic baseline seed without branch-level live HTTP extraction.'
            WHERE data_origin = 'quarantined_seed' OR notes LIKE '%price in%' OR notes LIKE '%Talabat in%';
            """
        )
        quarantined_count = cursor.rowcount
        conn.commit()
        return quarantined_count
    finally:
        conn.close()


if __name__ == "__main__":
    print("Running database migration and audit...")
    run_database_migration()
    q_count = audit_and_quarantine_seeded_records()
    print(f"Migration completed. Quarantined {q_count} unsupported seed records from commercial reporting.")
