"""SQLite and PostgreSQL connection management.

SQLite remains the local default. Set ``DATABASE_URL`` to use PostgreSQL (Neon
in production). Queries in the existing repository use SQLite's qmark
parameters, so the small PostgreSQL adapter keeps that interface while
returning mapping rows that also support the existing ``row[0]`` calls.
"""
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Union

from config import DEFAULT_DB_PATH, PROJECT_ROOT


def get_database_url() -> Optional[str]:
    """Read the runtime URL without ever logging its value.

    Streamlit Cloud secrets are supported, followed by injected environment
    variables and the gitignored local ``.env.local`` used by Neon CLI.
    """
    if os.environ.get("PIZZA_DATABASE_BACKEND", "").strip().lower() == "sqlite":
        return None
    value = os.environ.get("DATABASE_URL")
    if value:
        return value.strip().strip("\"'")

    env_file = PROJECT_ROOT / ".env.local"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("DATABASE_URL="):
                value = stripped.split("=", 1)[1].strip().strip("\"'")
                if value:
                    return value

    try:
        import streamlit as st

        value = st.secrets.get("DATABASE_URL")
        return str(value).strip() if value else None
    except Exception:
        # Streamlit secrets are unavailable to scripts and local unit tests.
        return None


def get_database_backend_config() -> tuple[str, str]:
    """Return safe backend metadata without returning or displaying credentials."""
    if os.environ.get("PIZZA_DATABASE_BACKEND", "").strip().lower() == "sqlite":
        return "sqlite", "explicit local override"
    if os.environ.get("DATABASE_URL", "").strip():
        return "postgresql", "environment secret"
    env_file = PROJECT_ROOT / ".env.local"
    if env_file.is_file():
        try:
            if any(
                line.strip().startswith("DATABASE_URL=")
                and line.split("=", 1)[1].strip().strip("\"'")
                for line in env_file.read_text(encoding="utf-8").splitlines()
            ):
                return "postgresql", "local environment file"
        except (OSError, IndexError):
            pass
    try:
        import streamlit as st

        if st.secrets.get("DATABASE_URL"):
            return "postgresql", "Streamlit secrets"
    except Exception:
        pass
    return "sqlite", "default local database (no DATABASE_URL configured)"


class _HybridRow(dict):
    """Dictionary row with SQLite-compatible integer indexing."""

    def __init__(self, names, values):
        super().__init__(zip(names, values))
        self._names = names

    def __getitem__(self, key):
        if isinstance(key, int):
            key = self._names[key]
        return super().__getitem__(key)


def _hybrid_row_factory(cursor):
    names = tuple(column.name for column in (cursor.description or ()))

    def make_row(values):
        return _HybridRow(names, values)

    return make_row


def _translate_sql(sql: str, params: Any = None) -> str:
    """Translate the small SQLite SQL subset used by this repository."""
    translated = re.sub(r"datetime\s*\(\s*'now'\s*\)", "CURRENT_TIMESTAMP", sql, flags=re.I)
    translated = re.sub(r"date\s*\(\s*'now'\s*\)", "CURRENT_DATE", translated, flags=re.I)
    translated = re.sub(
        r"date\s*\(\s*po\.collected_at\s*\)",
        "CAST(SUBSTRING(po.collected_at FROM 1 FOR 10) AS DATE)",
        translated,
        flags=re.I,
    )
    translated = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        translated,
        flags=re.I,
    )
    translated = re.sub(r"\bREAL\b", "DOUBLE PRECISION", translated, flags=re.I)
    translated = re.sub(r"\bBLOB\b", "BYTEA", translated, flags=re.I)
    # SQLite LIKE is ASCII case-insensitive by default; retain that behavior.
    translated = re.sub(r"\bLIKE\b", "ILIKE", translated, flags=re.I)

    if params is not None:
        # Psycopg treats percent signs in SQL literals as part of its pyformat
        # placeholder syntax whenever a parameter sequence is supplied.
        out = []
        quote = None
        i = 0
        while i < len(translated):
            char = translated[i]
            if quote:
                if char == "%":
                    out.append("%%")
                else:
                    out.append(char)
                if char == quote:
                    if i + 1 < len(translated) and translated[i + 1] == quote:
                        out.append(translated[i + 1])
                        i += 1
                    else:
                        quote = None
            elif char in ("'", '"'):
                quote = char
                out.append(char)
            else:
                out.append(char)
            i += 1
        translated = "".join(out)

    if isinstance(params, dict):
        return re.sub(r"(?<!:):([A-Za-z_]\w*)", r"%(\1)s", translated)

    # Qmark parameters are only substituted outside SQL string and identifier
    # literals, so a question mark in a product or note remains literal text.
    out = []
    quote = None
    i = 0
    while i < len(translated):
        char = translated[i]
        if quote:
            out.append(char)
            if char == quote:
                if i + 1 < len(translated) and translated[i + 1] == quote:
                    out.append(translated[i + 1])
                    i += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            out.append(char)
        elif char == "?":
            out.append("%s")
        else:
            out.append(char)
        i += 1
    return "".join(out)


class _PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._lastrowid = None

    def execute(self, sql, params=None):
        statement = _translate_sql(sql, params)
        is_insert = bool(re.match(r"\s*INSERT\s+INTO\b", statement, flags=re.I))
        has_returning = bool(re.search(r"\bRETURNING\b", statement, flags=re.I))
        if is_insert and not has_returning:
            statement = statement.rstrip().rstrip(";") + " RETURNING id"
        self._cursor.execute(statement, params)
        self._lastrowid = None
        if is_insert and not has_returning:
            row = self._cursor.fetchone()
            self._lastrowid = row["id"] if row else None
        return self

    def executescript(self, script):
        """Execute a SQL script using SQLite's SQL-aware statement splitter."""
        buffer = ""
        for line in script.splitlines(keepends=True):
            buffer += line
            if sqlite3.complete_statement(buffer):
                statement = buffer.strip()
                buffer = ""
                without_leading_comments = re.sub(
                    r"\A(?:\s*--[^\n]*(?:\n|$)|\s*/\*.*?\*/)*",
                    "",
                    statement,
                    flags=re.S,
                ).lstrip()
                if without_leading_comments and not re.match(r"PRAGMA\b", without_leading_comments, flags=re.I):
                    self.execute(statement)
        if buffer.strip():
            self.execute(buffer)
        return self

    def executemany(self, sql, params_seq):
        statement = _translate_sql(sql)
        self._cursor.executemany(statement, params_seq)
        self._lastrowid = None
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description


class _PostgresConnection:
    is_postgres = True

    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def cursor(self):
        return _PostgresCursor(self._connection.cursor(row_factory=_hybrid_row_factory))

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()


def get_connection(db_path: Optional[Union[str, Path]] = None):
    """Create a configured SQLite or PostgreSQL connection.

    An explicit ``db_path`` always selects SQLite, which keeps local tests and
    migration tooling isolated from the deployed database.
    """
    database_url = None if db_path is not None else get_database_url()
    if database_url:
        try:
            import psycopg
            from psycopg.rows import tuple_row
        except ImportError as exc:
            raise RuntimeError("DATABASE_URL is set but psycopg is not installed.") from exc
        connection = psycopg.connect(
            database_url,
            row_factory=tuple_row,
            connect_timeout=10,
            sslmode="require",
        )
        return _PostgresConnection(connection)

    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if str(target_path) != ":memory:":
        target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(target_path),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if str(target_path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def get_db_connection(db_path: Optional[Union[str, Path]] = None) -> Generator[Any, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_cursor(db_path: Optional[Union[str, Path]] = None) -> Generator[Any, None, None]:
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
