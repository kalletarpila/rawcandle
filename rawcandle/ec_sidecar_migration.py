from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sqlite" / "migrations"
MIGRATION_SQL_PATHS = (
    MIGRATIONS_DIR / "019_create_ec_sidecar_schema.sql",
    MIGRATIONS_DIR / "020_harden_ec_sidecar_schema.sql",
    MIGRATIONS_DIR / "021_patch_ec_signal_calendar_p0_fields.sql",
)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _rebuild_ec_entity_alias_if_needed(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(ec_entity_alias)").fetchall()
    source_system_row = next((row for row in rows if str(row[1]) == "source_system"), None)
    if source_system_row is not None and int(source_system_row[3]) == 1 and source_system_row[4] == "'UNKNOWN'":
        return

    conn.executescript(
        """
        CREATE TABLE ec_entity_alias__new (
            entity_alias_id INTEGER PRIMARY KEY,
            ecosystem_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            alias_type TEXT NOT NULL CHECK (alias_type IN ('DC_GROUP_NAME', 'TICKER', 'DISPLAY_NAME', 'LEGACY_CODE')),
            alias_value TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'UNKNOWN',
            status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
            active_from TEXT NULL,
            active_to TEXT NULL,
            created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (ecosystem_id, alias_type, alias_value, source_system),
            FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
            FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id)
        );

        INSERT INTO ec_entity_alias__new (
            entity_alias_id,
            ecosystem_id,
            entity_id,
            alias_type,
            alias_value,
            source_system,
            status,
            active_from,
            active_to,
            created_at_utc
        )
        SELECT
            entity_alias_id,
            ecosystem_id,
            entity_id,
            alias_type,
            alias_value,
            COALESCE(source_system, 'UNKNOWN'),
            status,
            active_from,
            active_to,
            created_at_utc
        FROM ec_entity_alias;

        DROP TABLE ec_entity_alias;
        ALTER TABLE ec_entity_alias__new RENAME TO ec_entity_alias;
        CREATE INDEX idx_ec_entity_alias_lookup
        ON ec_entity_alias (ecosystem_id, alias_type, alias_value);
        """
    )


def _rebuild_ec_watchlist_member_if_needed(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(ec_watchlist_member)").fetchall()
    active_from_row = next((row for row in rows if str(row[1]) == "active_from"), None)
    if active_from_row is not None and int(active_from_row[3]) == 1 and active_from_row[4] == "'1900-01-01'":
        return

    conn.executescript(
        """
        CREATE TABLE ec_watchlist_member__new (
            watchlist_member_id INTEGER PRIMARY KEY,
            watchlist_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            member_role TEXT NULL,
            status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
            active_from TEXT NOT NULL DEFAULT '1900-01-01',
            active_to TEXT NULL,
            notes TEXT NULL,
            created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (watchlist_id, entity_id, active_from),
            FOREIGN KEY (watchlist_id) REFERENCES ec_watchlist (watchlist_id),
            FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id)
        );

        INSERT INTO ec_watchlist_member__new (
            watchlist_member_id,
            watchlist_id,
            entity_id,
            member_role,
            status,
            active_from,
            active_to,
            notes,
            created_at_utc
        )
        SELECT
            watchlist_member_id,
            watchlist_id,
            entity_id,
            member_role,
            status,
            COALESCE(active_from, '1900-01-01'),
            active_to,
            notes,
            created_at_utc
        FROM ec_watchlist_member;

        DROP TABLE ec_watchlist_member;
        ALTER TABLE ec_watchlist_member__new RENAME TO ec_watchlist_member;
        CREATE INDEX idx_ec_watchlist_member_watchlist
        ON ec_watchlist_member (watchlist_id);
        """
    )


def _harden_ec_sidecar_schema(conn: sqlite3.Connection) -> None:
    entity_columns = _table_columns(conn, "ec_entity")
    if "entity_level" not in entity_columns:
        conn.execute("ALTER TABLE ec_entity ADD COLUMN entity_level INTEGER NULL")
    if "entity_role_code" not in entity_columns:
        conn.execute("ALTER TABLE ec_entity ADD COLUMN entity_role_code TEXT NULL")

    _rebuild_ec_entity_alias_if_needed(conn)
    _rebuild_ec_watchlist_member_if_needed(conn)
    _patch_ec_signal_calendar_if_needed(conn)


def _patch_ec_signal_calendar_if_needed(conn: sqlite3.Connection) -> None:
    calendar_columns = _table_columns(conn, "ec_signal_calendar")
    if "is_market_open" not in calendar_columns:
        conn.execute(
            """
            ALTER TABLE ec_signal_calendar
            ADD COLUMN is_market_open INTEGER NOT NULL DEFAULT 0 CHECK (is_market_open IN (0, 1))
            """
        )
    if "has_required_source_data" not in calendar_columns:
        conn.execute(
            """
            ALTER TABLE ec_signal_calendar
            ADD COLUMN has_required_source_data INTEGER NOT NULL DEFAULT 0
            CHECK (has_required_source_data IN (0, 1))
            """
        )
    if "valid_signal_seq" not in calendar_columns:
        conn.execute(
            """
            ALTER TABLE ec_signal_calendar
            ADD COLUMN valid_signal_seq INTEGER NULL
            """
        )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ec_signal_calendar_valid_signal_seq
        ON ec_signal_calendar (ecosystem_id, valid_signal_seq)
        """
    )


def _apply_ec_sidecar_migration_to_connection(conn: sqlite3.Connection) -> None:
    for migration_sql_path in MIGRATION_SQL_PATHS:
        conn.executescript(migration_sql_path.read_text(encoding="utf-8"))
    _harden_ec_sidecar_schema(conn)


def apply_ec_sidecar_migration(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _apply_ec_sidecar_migration_to_connection(conn)
        conn.commit()
    finally:
        conn.close()
