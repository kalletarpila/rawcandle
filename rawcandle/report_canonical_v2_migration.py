from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sqlite" / "migrations"
MIGRATION_SQL_PATH = MIGRATIONS_DIR / "004_create_datacenter_report_canonical_v2.sql"
MIGRATION_SQL_PATHS = (
    MIGRATIONS_DIR / "004_create_datacenter_report_canonical_v2.sql",
    MIGRATIONS_DIR / "005_add_daily_trigger_inputs_to_report_context_daily_v2.sql",
)


def apply_report_canonical_v2_migration(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION_SQL_PATHS[0].read_text(encoding="utf-8"))
    existing_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(dc_report_context_daily_v2)").fetchall()
    }
    if "price_data_status" not in existing_columns:
        conn.executescript(MIGRATION_SQL_PATHS[1].read_text(encoding="utf-8"))
