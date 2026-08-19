"""
Database Manager — Connection handling, schema initialization, and idempotent upsert logic.
Uses SQLite with WAL mode for concurrent read/write safety.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

from config.settings import DATABASE_PATH


_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """
    Create a new SQLite connection with recommended pragmas.

    Args:
        db_path: Optional override for the database file path.

    Returns:
        A configured sqlite3.Connection.
    """
    path = db_path or DATABASE_PATH
    # Ensure the directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
    conn.execute("PRAGMA journal_mode=WAL;")       # Better concurrency
    conn.execute("PRAGMA foreign_keys=ON;")         # Enforce FK constraints
    conn.execute("PRAGMA busy_timeout=5000;")       # Wait up to 5s on locks
    return conn


@contextmanager
def get_db_session(db_path: str | None = None):
    """
    Context manager for database sessions with auto-commit/rollback.

    Usage:
        with get_db_session() as conn:
            conn.execute("INSERT INTO ...")
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database(db_path: str | None = None) -> None:
    """
    Create all tables from schema.sql if they don't already exist.
    Safe to call multiple times (idempotent via IF NOT EXISTS).
    """
    schema_sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    with get_db_session(db_path) as conn:
        conn.executescript(schema_sql)


def upsert_dimension(
    conn: sqlite3.Connection,
    table: str,
    natural_key_col: str,
    natural_key_val: str,
    data: dict,
) -> int:
    """
    Idempotent upsert for SCD Type 1 dimension tables.
    If the record exists (by natural key), update it. Otherwise, insert.

    Args:
        conn: Active database connection.
        table: Table name.
        natural_key_col: Column name of the natural/business key.
        natural_key_val: Value of the natural key to match.
        data: Dict of column→value pairs to insert/update.

    Returns:
        The surrogate key (rowid) of the upserted record.
    """
    # Check if record exists
    cursor = conn.execute(
        f"SELECT rowid, * FROM {table} WHERE {natural_key_col} = ?",
        (natural_key_val,)
    )
    existing = cursor.fetchone()

    if existing:
        # Update existing record (SCD Type 1: overwrite)
        set_clause = ", ".join(f"{col} = ?" for col in data.keys())
        values = list(data.values())
        conn.execute(
            f"UPDATE {table} SET {set_clause}, updated_at = datetime('now') "
            f"WHERE {natural_key_col} = ?",
            values + [natural_key_val]
        )
        return existing[0]  # Return existing surrogate key
    else:
        # Insert new record
        data[natural_key_col] = natural_key_val
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        cursor = conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(data.values())
        )
        return cursor.lastrowid


def upsert_fact(
    conn: sqlite3.Connection,
    table: str,
    natural_key_col: str,
    natural_key_val: str,
    data: dict,
) -> int:
    """
    Idempotent upsert for fact tables.
    Uses the activity_id (natural key) to prevent duplicate loads.

    Returns:
        The surrogate key of the upserted record.
    """
    cursor = conn.execute(
        f"SELECT rowid FROM {table} WHERE {natural_key_col} = ?",
        (natural_key_val,)
    )
    existing = cursor.fetchone()

    if existing:
        # Already loaded — skip (idempotent: no duplicates)
        return existing[0]
    else:
        data[natural_key_col] = natural_key_val
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        cursor = conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(data.values())
        )
        return cursor.lastrowid


def populate_date_dimension(conn: sqlite3.Connection, start_year: int = 2024, end_year: int = 2027) -> None:
    """
    Populate dim_date with all dates from start_year to end_year.
    Idempotent: uses INSERT OR IGNORE.
    """
    import datetime

    start = datetime.date(start_year, 1, 1)
    end = datetime.date(end_year, 12, 31)
    delta = datetime.timedelta(days=1)

    current = start
    while current <= end:
        date_key = int(current.strftime("%Y%m%d"))
        conn.execute(
            """
            INSERT OR IGNORE INTO dim_date
            (date_key, full_date, day_of_week, day_name, day_of_month,
             week_of_year, month_number, month_name, quarter, year, is_weekend)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date_key,
                current.isoformat(),
                current.weekday(),
                current.strftime("%A"),
                current.day,
                current.isocalendar()[1],
                current.month,
                current.strftime("%B"),
                (current.month - 1) // 3 + 1,
                current.year,
                1 if current.weekday() >= 5 else 0,
            ),
        )
        current += delta
