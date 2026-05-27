from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sqlite" / "migrations"
MIGRATION_SQL_PATH = MIGRATIONS_DIR / "002_create_datacenter_dashboard_enrichment.sql"
HIGH_EXIT_RISK_MIGRATION_SQL_PATH = (
    MIGRATIONS_DIR / "003_add_high_exit_risk_days_count_to_ticker_enrichment.sql"
)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def apply_datacenter_dashboard_enrichment_migration(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION_SQL_PATH.read_text(encoding="utf-8"))
    ticker_columns = _table_columns(conn, "dc_dashboard_ticker_enrichment_daily")
    if "high_exit_risk_days_count" not in ticker_columns:
        conn.executescript(HIGH_EXIT_RISK_MIGRATION_SQL_PATH.read_text(encoding="utf-8"))
