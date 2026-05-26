from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATION_SQL_PATH = (
    Path(__file__).resolve().parent
    / "sqlite"
    / "migrations"
    / "002_create_datacenter_dashboard_enrichment.sql"
)


def apply_datacenter_dashboard_enrichment_migration(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION_SQL_PATH.read_text(encoding="utf-8"))
