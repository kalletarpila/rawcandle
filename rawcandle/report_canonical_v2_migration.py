from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sqlite" / "migrations"
MIGRATION_SQL_PATH = MIGRATIONS_DIR / "004_create_datacenter_report_canonical_v2.sql"


def apply_report_canonical_v2_migration(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION_SQL_PATH.read_text(encoding="utf-8"))
