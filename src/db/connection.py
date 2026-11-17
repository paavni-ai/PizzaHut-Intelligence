"""
SQLite Database Connection Manager.
Configures connection pooling, foreign keys, and row factories.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Union

from config import DEFAULT_DB_PATH


def get_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """
    Creates and configures an SQLite database connection.
    Enforces foreign keys, WAL mode, and row factory.
    """
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    
    # Ensure parent directory exists if using a file path
    if str(target_path) != ":memory:":
        target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    
    # Enforce SQLite foreign key constraints and performance pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    if str(target_path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        
    return conn


@contextmanager
def get_db_cursor(db_path: Optional[Union[str, Path]] = None) -> Generator[sqlite3.Cursor, None, None]:
    """
    Context manager that yields a cursor and manages transactions.
    Automatically commits on success or rolls back on exception.
    """
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
