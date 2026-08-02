from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sqlite" / "migrations"
MIGRATION_SQL_PATHS = (
    MIGRATIONS_DIR / "019_create_ec_sidecar_schema.sql",
    MIGRATIONS_DIR / "020_harden_ec_sidecar_schema.sql",
    MIGRATIONS_DIR / "021_patch_ec_signal_calendar_p0_fields.sql",
    MIGRATIONS_DIR / "022_create_ec_fact_tables.sql",
    MIGRATIONS_DIR / "023_patch_ec_fact_schema_for_dc_parity.sql",
    MIGRATIONS_DIR / "024_patch_ec_group_index_counts.sql",
    MIGRATIONS_DIR / "025_create_ec_watchlist_reconciliation_audit.sql",
    MIGRATIONS_DIR / "026_create_taxonomy_replacement_audit.sql",
)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


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


def _add_column_if_missing(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name in _table_columns(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def _patch_ec_fact_schema_for_dc_parity_if_needed(conn: sqlite3.Connection) -> None:
    for column_name, column_sql in (
        ("volume", "volume REAL NULL"),
        ("ma10", "ma10 REAL NULL"),
        ("ema10", "ema10 REAL NULL"),
        ("ema20", "ema20 REAL NULL"),
        ("distance_to_ema10_pct", "distance_to_ema10_pct REAL NULL"),
        ("above_ma10", "above_ma10 INTEGER NULL"),
        ("above_ema10", "above_ema10 INTEGER NULL"),
        ("above_ema20", "above_ema20 INTEGER NULL"),
        ("ema10_slope_positive", "ema10_slope_positive INTEGER NULL"),
        ("ema20_slope_positive", "ema20_slope_positive INTEGER NULL"),
        ("ema10_slope_lookback", "ema10_slope_lookback INTEGER NULL"),
        ("ema20_slope_lookback", "ema20_slope_lookback INTEGER NULL"),
        ("highest_close_20d", "highest_close_20d REAL NULL"),
        ("volume_avg_20d", "volume_avg_20d REAL NULL"),
        ("volume_vs_avg20", "volume_vs_avg20 REAL NULL"),
        ("latest_structure_age_trading_days", "latest_structure_age_trading_days INTEGER NULL"),
        ("structure_epoch_id", "structure_epoch_id TEXT NULL"),
        ("latest_bos_confirmed_as_of_date", "latest_bos_confirmed_as_of_date TEXT NULL"),
        ("latest_bos_age_trading_days", "latest_bos_age_trading_days INTEGER NULL"),
        ("latest_reset_confirmed_as_of_date", "latest_reset_confirmed_as_of_date TEXT NULL"),
        ("latest_reset_age_trading_days", "latest_reset_age_trading_days INTEGER NULL"),
        ("bullish_divergence_signal", "bullish_divergence_signal INTEGER NULL"),
        ("bearish_divergence_signal", "bearish_divergence_signal INTEGER NULL"),
        ("hidden_bullish_divergence_signal", "hidden_bullish_divergence_signal INTEGER NULL"),
        ("hidden_bearish_divergence_signal", "hidden_bearish_divergence_signal INTEGER NULL"),
        ("bullish_candle_signal", "bullish_candle_signal INTEGER NULL"),
        ("bearish_candle_signal", "bearish_candle_signal INTEGER NULL"),
    ):
        _add_column_if_missing(conn, "ec_ticker_signal_daily", column_name, column_sql)

    _add_column_if_missing(
        conn,
        "ec_group_signal_daily",
        "pct_above_rising_ema20",
        "pct_above_rising_ema20 REAL NULL",
    )

    for column_name, column_sql in (
        ("member_count", "member_count INTEGER NULL"),
        ("eligible_count", "eligible_count INTEGER NULL"),
        ("ma20", "ma20 REAL NULL"),
        ("ema20", "ema20 REAL NULL"),
        ("distance_to_ema20_pct", "distance_to_ema20_pct REAL NULL"),
        ("volatility_20d", "volatility_20d REAL NULL"),
        ("pivot_radius", "pivot_radius INTEGER NULL"),
        ("latest_pivot_high_date", "latest_pivot_high_date TEXT NULL"),
        ("latest_pivot_high_value", "latest_pivot_high_value REAL NULL"),
        ("latest_pivot_low_date", "latest_pivot_low_date TEXT NULL"),
        ("latest_pivot_low_value", "latest_pivot_low_value REAL NULL"),
        ("relative_base_window", "relative_base_window INTEGER NULL"),
        ("relative_open_20", "relative_open_20 REAL NULL"),
        ("relative_high_20", "relative_high_20 REAL NULL"),
        ("relative_low_20", "relative_low_20 REAL NULL"),
        ("relative_close_20", "relative_close_20 REAL NULL"),
        ("relative_upper_wick_20", "relative_upper_wick_20 REAL NULL"),
        ("relative_lower_wick_20", "relative_lower_wick_20 REAL NULL"),
        ("relative_close_extension_20", "relative_close_extension_20 REAL NULL"),
        ("relative_high_extension_20", "relative_high_extension_20 REAL NULL"),
        ("relative_low_extension_20", "relative_low_extension_20 REAL NULL"),
        ("relative_eligible_count", "relative_eligible_count INTEGER NULL"),
        ("latest_structure_age_trading_days", "latest_structure_age_trading_days INTEGER NULL"),
        ("latest_bos_confirmed_as_of_date", "latest_bos_confirmed_as_of_date TEXT NULL"),
        ("latest_bos_age_trading_days", "latest_bos_age_trading_days INTEGER NULL"),
        ("latest_reset_confirmed_as_of_date", "latest_reset_confirmed_as_of_date TEXT NULL"),
        ("latest_reset_age_trading_days", "latest_reset_age_trading_days INTEGER NULL"),
    ):
        _add_column_if_missing(conn, "ec_group_synthetic_ohlc_daily", column_name, column_sql)

    for column_name, column_sql in (
        ("ma50_eligible_count", "ma50_eligible_count INTEGER NULL"),
        ("ma200_eligible_count", "ma200_eligible_count INTEGER NULL"),
        ("median_return", "median_return REAL NULL"),
        ("pct_positive", "pct_positive REAL NULL"),
        ("pct_above_ma50", "pct_above_ma50 REAL NULL"),
        ("pct_above_ma200", "pct_above_ma200 REAL NULL"),
        ("volatility_60d", "volatility_60d REAL NULL"),
        ("relative_strength_spy_60d", "relative_strength_spy_60d REAL NULL"),
        ("relative_strength_qqq_60d", "relative_strength_qqq_60d REAL NULL"),
    ):
        _add_column_if_missing(conn, "ec_group_index_daily", column_name, column_sql)


def _patch_ec_group_index_counts_if_needed(conn: sqlite3.Connection) -> None:
    for column_name, column_sql in (
        ("member_count", "member_count INTEGER NULL"),
        ("eligible_count", "eligible_count INTEGER NULL"),
    ):
        _add_column_if_missing(conn, "ec_group_index_daily", column_name, column_sql)


def _patch_taxonomy_replacement_schema_if_needed(conn: sqlite3.Connection) -> None:
    if "ec_pipeline_watermark" in _table_names(conn):
        _add_column_if_missing(
            conn,
            "ec_pipeline_watermark",
            "taxonomy_version_id",
            "taxonomy_version_id INTEGER NULL",
        )


def _apply_ec_sidecar_migration_to_connection(conn: sqlite3.Connection) -> None:
    for migration_sql_path in MIGRATION_SQL_PATHS:
        conn.executescript(migration_sql_path.read_text(encoding="utf-8"))
    _harden_ec_sidecar_schema(conn)
    _patch_ec_fact_schema_for_dc_parity_if_needed(conn)
    _patch_ec_group_index_counts_if_needed(conn)
    _patch_taxonomy_replacement_schema_if_needed(conn)


def apply_ec_sidecar_migration(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _apply_ec_sidecar_migration_to_connection(conn)
        conn.commit()
    finally:
        conn.close()
