from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sqlite" / "migrations"
MIGRATION_SQL_PATHS = (
    MIGRATIONS_DIR / "019_create_ec_sidecar_schema.sql",
)


def _apply_ec_sidecar_migration_to_connection(conn: sqlite3.Connection) -> None:
    for migration_sql_path in MIGRATION_SQL_PATHS:
        conn.executescript(migration_sql_path.read_text(encoding="utf-8"))


def apply_ec_sidecar_migration(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _apply_ec_sidecar_migration_to_connection(conn)
        conn.commit()
    finally:
        conn.close()
