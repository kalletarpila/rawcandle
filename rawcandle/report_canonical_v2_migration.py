from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sqlite" / "migrations"
MIGRATION_SQL_PATH = MIGRATIONS_DIR / "004_create_datacenter_report_canonical_v2.sql"
MIGRATION_SQL_PATHS = (
    MIGRATIONS_DIR / "004_create_datacenter_report_canonical_v2.sql",
    MIGRATIONS_DIR / "005_add_daily_trigger_inputs_to_report_context_daily_v2.sql",
    MIGRATIONS_DIR / "006_add_rolling2_classifier_inputs_to_report_context_window_v2.sql",
    MIGRATIONS_DIR / "007_add_daily_distance_to_ema10_to_report_context_daily_v2.sql",
    MIGRATIONS_DIR / "008_add_daily_formatter_source_fields_to_report_context_v2.sql",
    MIGRATIONS_DIR / "009_create_report_window_metadata_v2.sql",
    MIGRATIONS_DIR / "010_create_report_ticker_coverage_v2.sql",
    MIGRATIONS_DIR / "011_create_report_relevance_quality_v2.sql",
)

MIGRATION_008_COLUMNS = (
    (
        "dc_report_context_group_v2",
        "return_10d",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN return_10d REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "return_20d",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN return_20d REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "return_60d",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN return_60d REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "pct_above_ema20",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN pct_above_ema20 REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "pct_above_ma10",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN pct_above_ma10 REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "ema20_breadth_delta_5d",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN ema20_breadth_delta_5d REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "ma10_breadth_delta_5d",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN ma10_breadth_delta_5d REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "trend_breadth",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN trend_breadth REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "weakness_breadth",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN weakness_breadth REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "strength_breadth",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN strength_breadth REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "timing_reason",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN timing_reason TEXT NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "data_quality_status",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN data_quality_status TEXT NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_ema20",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_ema20 REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_volatility_20d",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_volatility_20d REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_latest_structure_age_trading_days",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_latest_structure_age_trading_days INTEGER NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_latest_bos_event_date",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_latest_bos_event_date TEXT NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_latest_bos_age_trading_days",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_latest_bos_age_trading_days INTEGER NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_latest_reset_event_date",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_latest_reset_event_date TEXT NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_latest_reset_age_trading_days",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_latest_reset_age_trading_days INTEGER NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_relative_close_extension_20",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_relative_close_extension_20 REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_relative_upper_wick_20",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_relative_upper_wick_20 REAL NULL;",
    ),
    (
        "dc_report_context_group_v2",
        "synthetic_relative_lower_wick_20",
        "ALTER TABLE dc_report_context_group_v2 ADD COLUMN synthetic_relative_lower_wick_20 REAL NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "ema10",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN ema10 REAL NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "ema20",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN ema20 REAL NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "volume_vs_avg20",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN volume_vs_avg20 REAL NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "latest_structure_age_trading_days",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN latest_structure_age_trading_days INTEGER NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "latest_bos_age_trading_days",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN latest_bos_age_trading_days INTEGER NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "latest_reset_age_trading_days",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN latest_reset_age_trading_days INTEGER NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "latest_bullish_relevance_reason",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN latest_bullish_relevance_reason TEXT NULL;",
    ),
    (
        "dc_report_context_daily_v2",
        "latest_bearish_relevance_reason",
        "ALTER TABLE dc_report_context_daily_v2 ADD COLUMN latest_bearish_relevance_reason TEXT NULL;",
    ),
)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _apply_migration_008_columns_individually(conn: sqlite3.Connection) -> None:
    existing_group_columns = _table_columns(conn, "dc_report_context_group_v2")
    existing_daily_columns = _table_columns(conn, "dc_report_context_daily_v2")
    for table_name, column_name, sql in MIGRATION_008_COLUMNS:
        existing_columns = existing_group_columns if table_name == "dc_report_context_group_v2" else existing_daily_columns
        if column_name in existing_columns:
            continue
        conn.execute(sql)
        existing_columns.add(column_name)


def apply_report_canonical_v2_migration(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION_SQL_PATHS[0].read_text(encoding="utf-8"))
    existing_columns = _table_columns(conn, "dc_report_context_daily_v2")
    if "price_data_status" not in existing_columns:
        conn.executescript(MIGRATION_SQL_PATHS[1].read_text(encoding="utf-8"))
        existing_columns = _table_columns(conn, "dc_report_context_daily_v2")
    if "distance_to_ema10_pct" not in existing_columns:
        conn.executescript(MIGRATION_SQL_PATHS[3].read_text(encoding="utf-8"))
    existing_daily_columns = _table_columns(conn, "dc_report_context_daily_v2")
    existing_group_columns = _table_columns(conn, "dc_report_context_group_v2")
    if not {
        "ema10",
    }.issubset(existing_daily_columns) or not {
        "return_10d",
        "synthetic_ema20",
    }.issubset(existing_group_columns):
        _apply_migration_008_columns_individually(conn)
    existing_window_columns = _table_columns(conn, "dc_report_context_window_v2")
    if "price_data_status" not in existing_window_columns:
        conn.executescript(MIGRATION_SQL_PATHS[2].read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_SQL_PATHS[5].read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_SQL_PATHS[6].read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_SQL_PATHS[7].read_text(encoding="utf-8"))
