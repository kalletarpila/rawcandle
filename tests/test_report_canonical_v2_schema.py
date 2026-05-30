import sqlite3

import pytest

from analysis.database_manager import DatabaseManager
from rawcandle.report_canonical_v2_migration import (
    MIGRATION_SQL_PATH,
    apply_report_canonical_v2_migration,
)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _primary_key_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in sorted(rows, key=lambda row: int(row[5])) if int(row[5]) > 0]


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    apply_report_canonical_v2_migration(conn)
    return conn


def _connect_through_007() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    from rawcandle.report_canonical_v2_migration import MIGRATION_SQL_PATHS

    conn.executescript(MIGRATION_SQL_PATHS[0].read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_SQL_PATHS[1].read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_SQL_PATHS[3].read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_SQL_PATHS[2].read_text(encoding="utf-8"))
    return conn


def _insert_run(conn: sqlite3.Connection, *, run_id: str = "run-1") -> str:
    conn.execute(
        """
        INSERT INTO dc_report_run_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            market,
            calculation_version,
            source_versions_json,
            created_at_utc,
            status,
            warning_count,
            error_count,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "usa",
            "REPORT_CANONICAL_V2",
            None,
            "2026-05-30T00:00:00Z",
            "OK",
            0,
            0,
            None,
        ),
    )
    return run_id


def test_migration_file_exists():
    assert MIGRATION_SQL_PATH.is_file()


def test_database_manager_initializes_report_canonical_v2_tables(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    conn = manager.get_connection()

    assert _table_exists(conn, "dc_report_run_v2")
    assert _table_exists(conn, "dc_report_context_group_v2")
    assert _table_exists(conn, "dc_report_context_daily_v2")
    assert _table_exists(conn, "dc_report_context_window_v2")
    assert _table_exists(conn, "dc_report_classification_v2")

    manager.close()


def test_migration_creates_expected_primary_keys_and_columns():
    conn = _connect()

    assert _primary_key_columns(conn, "dc_report_run_v2") == ["run_id"]
    assert _primary_key_columns(conn, "dc_report_context_group_v2") == [
        "signal_date",
        "taxonomy_version",
        "horizon",
        "group_type",
        "group_name",
    ]
    assert _primary_key_columns(conn, "dc_report_context_daily_v2") == [
        "signal_date",
        "taxonomy_version",
        "ticker",
    ]
    assert _primary_key_columns(conn, "dc_report_context_window_v2") == [
        "signal_date",
        "taxonomy_version",
        "ticker",
        "horizon",
    ]
    assert _primary_key_columns(conn, "dc_report_classification_v2") == [
        "signal_date",
        "taxonomy_version",
        "ticker",
        "horizon",
        "classification_type",
    ]

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "market",
        "calculation_version",
        "source_versions_json",
        "created_at_utc",
        "status",
        "warning_count",
        "error_count",
        "notes",
    }.issubset(_table_columns(conn, "dc_report_run_v2"))

    assert {
        "signal_date",
        "taxonomy_version",
        "market",
        "horizon",
        "group_type",
        "group_name",
        "return_10d",
        "return_20d",
        "return_60d",
        "pct_above_ema20",
        "ema20_breadth_delta_5d",
        "timing_reason",
        "data_quality_status",
        "synthetic_ema20",
        "synthetic_latest_structure_age_trading_days",
        "synthetic_latest_bos_event_date",
        "synthetic_latest_bos_age_trading_days",
        "synthetic_relative_close_extension_20",
        "group_current_status",
        "group_window_status",
        "group_status_change",
        "window_start_date",
        "window_end_date",
        "valid_signal_dates",
        "run_id",
        "created_at_utc",
    }.issubset(_table_columns(conn, "dc_report_context_group_v2"))

    assert {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "in_datacenter_ecosystem",
        "is_watchlist",
        "current_watchlist_status",
        "price_data_status",
        "close",
        "ema10",
        "ema20",
        "volume_vs_avg20",
        "distance_to_ema10_pct",
        "breakout_signal",
        "pullback_signal",
        "latest_structure_age_trading_days",
        "latest_bos_age_trading_days",
        "latest_reset_age_trading_days",
        "latest_bullish_relevance_class",
        "latest_bullish_relevance_reason",
        "latest_bearish_relevance_class",
        "latest_bearish_relevance_reason",
        "bullish_candle_signal",
        "bullish_divergence_signal",
        "hidden_bullish_divergence_signal",
        "bearish_candle_signal",
        "bearish_divergence_signal",
        "hidden_bearish_divergence_signal",
        "exit_risk_signal",
        "ma_break_status",
        "freshness_status",
        "context_readiness_status",
        "run_id",
        "created_at_utc",
    }.issubset(_table_columns(conn, "dc_report_context_daily_v2"))

    assert {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "horizon",
        "window_start_date",
        "window_end_date",
        "valid_signal_dates",
        "incomplete_window",
        "current_watchlist_status",
        "window_watchlist_status",
        "price_data_status",
        "exit_risk_severity",
        "latest_bearish_relevance_class",
        "distance_to_ema20_pct",
        "all_price_rows_missing",
        "close_below_ema20_flag",
        "double_bos_down_flag",
        "severe_exit_risk_flag",
        "context_readiness_status",
        "run_id",
        "created_at_utc",
    }.issubset(_table_columns(conn, "dc_report_context_window_v2"))

    assert {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "horizon",
        "classification_type",
        "classification_state",
        "primary_reason",
        "blocking_reason",
        "risk_reason",
        "next_action",
        "classification_status",
        "classification_version",
        "run_id",
        "created_at_utc",
    }.issubset(_table_columns(conn, "dc_report_classification_v2"))


def test_migration_creates_expected_indexes():
    conn = _connect()

    assert {
        "idx_dc_report_context_group_v2_date_horizon",
        "idx_dc_report_context_group_v2_group",
    }.issubset(_index_names(conn, "dc_report_context_group_v2"))

    assert {
        "idx_dc_report_context_daily_v2_date",
        "idx_dc_report_context_daily_v2_ticker",
    }.issubset(_index_names(conn, "dc_report_context_daily_v2"))

    assert {
        "idx_dc_report_context_window_v2_date_horizon",
        "idx_dc_report_context_window_v2_ticker_horizon",
    }.issubset(_index_names(conn, "dc_report_context_window_v2"))

    assert {
        "idx_dc_report_classification_v2_date_horizon",
        "idx_dc_report_classification_v2_ticker",
    }.issubset(_index_names(conn, "dc_report_classification_v2"))


def test_migration_008_fresh_migration_creates_representative_fields():
    conn = _connect()

    daily_columns = _table_columns(conn, "dc_report_context_daily_v2")
    group_columns = _table_columns(conn, "dc_report_context_group_v2")

    assert "ema10" in daily_columns
    assert "return_10d" in group_columns
    assert "synthetic_ema20" in group_columns


def test_migration_008_partial_daily_side_only_state_is_repaired():
    conn = _connect_through_007()
    conn.execute("ALTER TABLE dc_report_context_daily_v2 ADD COLUMN ema10 REAL NULL;")

    apply_report_canonical_v2_migration(conn)

    daily_columns = _table_columns(conn, "dc_report_context_daily_v2")
    group_columns = _table_columns(conn, "dc_report_context_group_v2")

    assert "ema10" in daily_columns
    assert "return_10d" in group_columns
    assert "synthetic_ema20" in group_columns


def test_migration_008_partial_group_side_only_state_is_repaired():
    conn = _connect_through_007()
    conn.execute("ALTER TABLE dc_report_context_group_v2 ADD COLUMN return_10d REAL NULL;")

    apply_report_canonical_v2_migration(conn)

    daily_columns = _table_columns(conn, "dc_report_context_daily_v2")
    group_columns = _table_columns(conn, "dc_report_context_group_v2")

    assert "ema10" in daily_columns
    assert "return_10d" in group_columns
    assert "synthetic_ema20" in group_columns


def test_group_context_horizon_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_group_v2 (
                signal_date, taxonomy_version, market, horizon, group_type, group_name,
                group_context_readiness_status, window_end_date, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "rolling99",
                "layer",
                "Infrastructure",
                "READY",
                "2026-05-30",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_daily_context_new_signal_boolean_checks_reject_invalid_values():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_daily_v2 (
                signal_date,
                taxonomy_version,
                market,
                ticker,
                bullish_candle_signal,
                context_readiness_status,
                run_id,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                2,
                "OK",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_window_context_horizon_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_window_v2 (
                signal_date, taxonomy_version, market, ticker, horizon,
                window_start_date, window_end_date, valid_signal_dates,
                context_readiness_status, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "daily",
                "2026-05-29",
                "2026-05-30",
                2,
                "READY",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_window_context_all_price_rows_missing_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_window_v2 (
                signal_date, taxonomy_version, market, ticker, horizon,
                window_start_date, window_end_date, valid_signal_dates,
                all_price_rows_missing, context_readiness_status, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "rolling2",
                "2026-05-29",
                "2026-05-30",
                2,
                2,
                "OK",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_classification_horizon_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_classification_v2 (
                signal_date, taxonomy_version, market, ticker, horizon, classification_type,
                classification_state, classification_status, classification_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "rolling99",
                "rolling30_buy",
                "BUY_ZONE",
                "OK",
                "V2",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_classification_type_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_classification_v2 (
                signal_date, taxonomy_version, market, ticker, horizon, classification_type,
                classification_state, classification_status, classification_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "rolling30",
                "rolling30_priority",
                "BUY_ZONE",
                "OK",
                "V2",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_run_status_check_rejects_invalid_value():
    conn = _connect()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_run_v2 (
                run_id,
                signal_date,
                taxonomy_version,
                market,
                calculation_version,
                source_versions_json,
                created_at_utc,
                status,
                warning_count,
                error_count,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-invalid-status",
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "REPORT_CANONICAL_V2",
                None,
                "2026-05-30T00:00:00Z",
                "READY",
                0,
                0,
                None,
            ),
        )


def test_run_warning_count_check_rejects_negative_value():
    conn = _connect()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_run_v2 (
                run_id,
                signal_date,
                taxonomy_version,
                market,
                calculation_version,
                source_versions_json,
                created_at_utc,
                status,
                warning_count,
                error_count,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-negative-warning-count",
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "REPORT_CANONICAL_V2",
                None,
                "2026-05-30T00:00:00Z",
                "OK",
                -1,
                0,
                None,
            ),
        )


def test_run_error_count_check_rejects_negative_value():
    conn = _connect()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_run_v2 (
                run_id,
                signal_date,
                taxonomy_version,
                market,
                calculation_version,
                source_versions_json,
                created_at_utc,
                status,
                warning_count,
                error_count,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-negative-error-count",
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "REPORT_CANONICAL_V2",
                None,
                "2026-05-30T00:00:00Z",
                "OK",
                0,
                -1,
                None,
            ),
        )


def test_classification_status_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_classification_v2 (
                signal_date, taxonomy_version, market, ticker, horizon, classification_type,
                classification_state, classification_status, classification_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "rolling30",
                "rolling30_buy",
                "BUY_ZONE",
                "READY",
                "V2",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_group_valid_signal_dates_check_rejects_negative_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_group_v2 (
                signal_date, taxonomy_version, market, horizon, group_type, group_name,
                group_context_readiness_status, window_end_date, valid_signal_dates, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "rolling30",
                "layer",
                "Infrastructure",
                "READY",
                "2026-05-30",
                -1,
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_daily_boolean_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_daily_v2 (
                signal_date, taxonomy_version, market, ticker,
                in_datacenter_ecosystem, context_readiness_status, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                2,
                "READY",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_boolean_flag_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_window_v2 (
                signal_date, taxonomy_version, market, ticker, horizon,
                window_start_date, window_end_date, valid_signal_dates,
                close_below_ema20_flag, context_readiness_status, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "rolling30",
                "2026-05-01",
                "2026-05-30",
                30,
                2,
                "READY",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")

    apply_report_canonical_v2_migration(conn)
    apply_report_canonical_v2_migration(conn)

    assert _table_exists(conn, "dc_report_run_v2")
    assert _table_exists(conn, "dc_report_context_group_v2")
    assert _table_exists(conn, "dc_report_context_daily_v2")
    assert _table_exists(conn, "dc_report_context_window_v2")
    assert _table_exists(conn, "dc_report_classification_v2")


def test_negative_count_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_window_v2 (
                signal_date, taxonomy_version, market, ticker, horizon,
                window_start_date, window_end_date, valid_signal_dates,
                breakout_days, context_readiness_status, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "rolling5",
                "2026-05-24",
                "2026-05-30",
                5,
                -1,
                "READY",
                run_id,
                "2026-05-30T00:00:00Z",
            ),
        )


def test_foreign_key_to_run_table_is_enforced():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO dc_report_context_daily_v2 (
                signal_date, taxonomy_version, market, ticker,
                context_readiness_status, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-30",
                "DC_TAXONOMY_FULL_V1",
                "usa",
                "NVDA",
                "READY",
                "missing-run",
                "2026-05-30T00:00:00Z",
            ),
        )
