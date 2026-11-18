"""Credential-safe, read-only database health checks for the admin status page."""
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union

from config import DEFAULT_DB_PATH
from src.db.connection import get_connection, get_database_backend_config

EXPECTED_TABLES = (
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
    "benchmarks",
    "accuracy_evaluations",
    "human_corrections",
    "platform_menu_items",
    "menu_item_matches",
    "menu_import_batches",
    "menu_item_prices",
    "menu_fee_observations",
    "promotion_terms",
    "promotion_weekdays",
    "promotion_item_eligibility",
    "cart_comparisons",
    "cart_comparison_items",
    "cart_platform_quotes",
    "cart_quote_lines",
)
COUNT_TABLES = (
    "price_observations",
    "evidence_records",
    "research_runs",
    "benchmarks",
)


def check_database_health(db_path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """Check backend, connectivity, required tables and row counts using SELECTs only.

    Returned fields deliberately exclude URLs, hostnames, file paths and exception
    messages. PostgreSQL failures never trigger a SQLite fallback.
    """
    configured_backend, source = (
        ("sqlite", "explicit database path") if db_path is not None
        else get_database_backend_config()
    )
    result: dict[str, Any] = {
        "backend": configured_backend,
        "configuration_source": source,
        "connected": False,
        "expected_tables_accessible": False,
        "missing_tables": [],
        "counts": {},
        "error_type": None,
    }
    connection = None
    try:
        if configured_backend == "sqlite":
            path = Path(db_path) if db_path is not None else Path(DEFAULT_DB_PATH)
            if not path.is_file():
                result["error_type"] = "DatabaseFileUnavailable"
                return result
            connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        else:
            connection = get_connection()
            connection.execute("SET TRANSACTION READ ONLY")
            cursor = connection.cursor()
            cursor.execute(
                "SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )

        result["connected"] = True
        existing = {row["name"] for row in cursor.fetchall()}
        result["missing_tables"] = [name for name in EXPECTED_TABLES if name not in existing]
        result["expected_tables_accessible"] = not result["missing_tables"]
        if result["expected_tables_accessible"]:
            for table in COUNT_TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                result["counts"][table] = cursor.fetchone()[0]
        if configured_backend == "postgresql":
            connection.rollback()
    except Exception as exc:
        # Exception text from database drivers can contain endpoint or connection
        # details. Keep only the exception type for safe diagnosis.
        result["error_type"] = type(exc).__name__
        result["connected"] = False
        result["expected_tables_accessible"] = False
        result["counts"] = {}
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    return result
