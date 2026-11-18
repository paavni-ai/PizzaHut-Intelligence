"""One-time, guarded migration of the existing SQLite research history to Neon.

The target is selected by Neon branch name rather than a printed/stored URL.
Only an empty target is accepted. The source database is opened immutable and
read-only; its row counts and values are compared with PostgreSQL before the
write transaction commits. Captured evidence bytes are copied into Postgres so
verification still works when the app host has no durable local filesystem.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from config import PROJECT_ROOT
from src.db.connection import get_connection
from src.db.init_db import initialize_database
from src.db.migrate import run_database_migration


TABLE_ORDER = (
    "competitors", "emirates", "ordering_channels", "categories",
    "locations", "ordering_platforms", "products", "product_variants",
    "research_runs", "evidence_records", "price_observations",
    "promotions", "benchmarks", "accuracy_evaluations", "human_corrections",
)


def _project_id(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    context = PROJECT_ROOT / ".neon"
    if context.is_file():
        data = json.loads(context.read_text(encoding="utf-8"))
        if data.get("projectId"):
            return str(data["projectId"])
    raise ValueError("Pass --project-id or link this project with the Neon CLI first.")


def _set_branch_url(branch: str, project_id: str) -> None:
    result = subprocess.run(
        ["neon", "connection-string", branch, "--project-id", project_id],
        check=True,
        capture_output=True,
        text=True,
    )
    url = result.stdout.strip()
    if not url.startswith(("postgres://", "postgresql://")):
        raise ValueError("Neon did not return a PostgreSQL connection URL.")
    # Keep this secret in process memory. Never print it or write it to a file.
    os.environ["DATABASE_URL"] = url


def _target_tables(conn) -> List[str]:
    return [row["name"] for row in conn.execute(
        "SELECT table_name AS name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name;"
    ).fetchall()]


def _resolve_artifact(path: Optional[str], evidence_dir: Path) -> Optional[Path]:
    if not path:
        return None
    original = Path(path)
    if original.is_file():
        return original
    candidate = evidence_dir / original.name
    return candidate if candidate.is_file() else None


def _source_tables(source) -> List[str]:
    found = {row[0] for row in source.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    ).fetchall()}
    unknown = found - set(TABLE_ORDER)
    missing = set(TABLE_ORDER) - found
    if unknown or missing:
        raise ValueError(
            f"Unexpected SQLite table inventory (unknown={sorted(unknown)}, missing={sorted(missing)})."
        )
    return [name for name in TABLE_ORDER if name in found]


def _normalize(value: Any) -> Any:
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def _migrate(source_path: Path, evidence_dir: Path) -> Dict[str, int]:
    if not source_path.is_file():
        raise FileNotFoundError("The requested SQLite source file does not exist.")

    source_uri = "file:" + str(source_path.resolve()) + "?mode=ro&immutable=1"
    source = sqlite3.connect(source_uri, uri=True)
    source.row_factory = sqlite3.Row
    target = None
    try:
        tables = _source_tables(source)
        # Refuse any public table in the target rather than merging into an
        # unknown state or replacing records.
        target = get_connection()
        occupied = _target_tables(target)
        if occupied:
            raise ValueError(f"Target is not empty; refusing to modify it ({len(occupied)} tables exist).")
        target.close()
        target = None

        initialize_database(seed_reference_data=False)
        run_database_migration()
        target = get_connection()

        expected_counts: Dict[str, int] = {}
        for table in tables:
            source_columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
            target_columns = {
                row["name"] for row in target.execute(
                    "SELECT column_name AS name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = ?;",
                    (table,),
                ).fetchall()
            }
            columns = list(source_columns)
            if table == "evidence_records" and "artifact_content" in target_columns and "artifact_content" not in columns:
                columns.append("artifact_content")
            absent = set(source_columns) - target_columns
            if absent:
                raise ValueError(f"Target schema is missing columns from {table}: {sorted(absent)}")

            source_rows = source.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
            expected_counts[table] = len(source_rows)
            insert_sql = (
                f'INSERT INTO "{table}" ('
                + ", ".join(f'"{column}"' for column in columns)
                + ") VALUES ("
                + ", ".join("?" for _ in columns)
                + ");"
            )
            rows_to_insert = []
            for source_row in source_rows:
                values = [source_row[column] for column in source_columns]
                if table == "evidence_records" and "artifact_content" in columns:
                    artifact_path = _resolve_artifact(source_row["file_path"], evidence_dir)
                    artifact = artifact_path.read_bytes() if artifact_path else None
                    expected_hash = source_row["file_hash_sha256"]
                    if artifact is not None and expected_hash:
                        actual_hash = hashlib.sha256(artifact).hexdigest()
                        if actual_hash.casefold() != str(expected_hash).casefold():
                            raise ValueError(f"Evidence hash mismatch for record {source_row['id']}.")
                    if source_row["file_path"] and artifact is None:
                        raise ValueError(f"Evidence artifact for record {source_row['id']} cannot be located.")
                    values.append(artifact)
                rows_to_insert.append(tuple(values))

            if rows_to_insert:
                target.cursor().executemany(insert_sql, rows_to_insert)

        # Verify table counts, each original row value, and captured artifact
        # hashes inside the same transaction before committing any imported row.
        for table in tables:
            source_columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
            quoted = ", ".join(f'"{column}"' for column in source_columns)
            original_rows = source.execute(f'SELECT {quoted} FROM "{table}" ORDER BY id').fetchall()
            migrated_rows = target.execute(f'SELECT {quoted} FROM "{table}" ORDER BY id').fetchall()
            if len(original_rows) != len(migrated_rows):
                raise ValueError(f"Row count mismatch in {table}.")
            for original, migrated in zip(original_rows, migrated_rows):
                for column in source_columns:
                    if _normalize(original[column]) != _normalize(migrated[column]):
                        raise ValueError(f"Data mismatch in {table}.{column} at id {original['id']}.")

            target.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{table}\"), 1), "
                f"EXISTS(SELECT 1 FROM \"{table}\"));",
                (table,),
            )

        target.execute("SET CONSTRAINTS ALL IMMEDIATE;")
        target.commit()
        return expected_counts
    except Exception:
        if target is not None:
            target.rollback()
        raise
    finally:
        if target is not None:
            target.close()
        source.close()


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path, help="Read-only SQLite snapshot to migrate")
    parser.add_argument("--evidence-dir", required=True, type=Path, help="Directory containing captured evidence artifacts")
    parser.add_argument("--branch", required=True, help="Neon branch name; this is an additive import into an empty branch")
    parser.add_argument("--project-id", help="Neon project ID (defaults to the linked .neon project)")
    args = parser.parse_args(argv)

    try:
        _set_branch_url(args.branch, _project_id(args.project_id))
        counts = _migrate(args.source_db, args.evidence_dir)
        print(f"Migration verified on branch {args.branch}.")
        for table, count in counts.items():
            print(f"{table}: {count}")
        return 0
    except Exception as exc:
        # Database URLs can appear in low-level exception messages; only emit
        # the exception class so no credential can reach logs.
        diagnostic = str(exc)
        diagnostic = re.sub(r"(?i)postgres(?:ql)?://[^\s'\"]+", "[redacted database URL]", diagnostic)
        diagnostic = re.sub(r"(?i)(password\s*[=:]\s*)[^\s,;]+", r"\1[redacted]", diagnostic)
        print(
            f"Migration failed safely ({type(exc).__name__}): {diagnostic[:400]}; "
            "imported rows were rolled back.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
