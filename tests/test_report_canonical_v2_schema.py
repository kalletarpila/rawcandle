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


def _utc_timestamp(value: str = "2026-05-30T00:00:00Z") -> str:
    return value


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


def _insert_watchlist_ticker(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "daily",
    ticker: str = "NVDA",
    coverage_status: str = "OK",
    is_included: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_watchlist_ticker_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            ticker,
            watchlist_source,
            primary_layer,
            primary_subindustry,
            coverage_status,
            is_included,
            missing_reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            ticker,
            "watchlist",
            "AI",
            "Semiconductors",
            coverage_status,
            is_included,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_taxonomy_ticker_coverage(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    ticker: str = "NVDA",
    coverage_status: str = "OK",
    has_instrument: int = 1,
    has_price_data: int = 1,
    has_daily_signal: int = 1,
    has_rolling_context: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_taxonomy_ticker_coverage_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            ticker,
            primary_layer,
            primary_subindustry,
            coverage_status,
            has_instrument,
            has_price_data,
            has_daily_signal,
            has_rolling_context,
            missing_reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            ticker,
            "AI",
            "Semiconductors",
            coverage_status,
            has_instrument,
            has_price_data,
            has_daily_signal,
            has_rolling_context,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_technical_relevance_context(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "daily",
    ticker: str = "NVDA",
    signal_name: str = "bullish_divergence",
    signal_confirmed_as_of_date: str = "2026-05-30",
    relevance_class: str = "RELEVANT",
    signal_direction: str | None = "BULLISH",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_technical_relevance_context_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            ticker,
            timeframe,
            signal_name,
            signal_source_id,
            signal_direction,
            signal_family,
            signal_confirmed_as_of_date,
            relevance_class,
            relevance_reason,
            trend_state,
            dow_context,
            bos_context,
            reset_context,
            trend_alignment,
            counter_trend_context,
            source_run_id,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            ticker,
            "daily",
            signal_name,
            "src-1",
            signal_direction,
            "divergence",
            signal_confirmed_as_of_date,
            relevance_class,
            "Aligned with trend",
            "UPTREND",
            "EARLY",
            "CONFIRMED",
            "NONE",
            "ALIGNED",
            None,
            "source-run-1",
            _utc_timestamp(),
        ),
    )


def _insert_data_quality_summary(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "daily",
    quality_scope: str = "RUN",
    scope_key: str = "GLOBAL",
    quality_status: str = "OK",
    expected_count: int | None = 10,
    actual_count: int | None = 10,
    missing_count: int | None = 0,
    incomplete_count: int | None = 0,
    stale_count: int | None = 0,
    warning_count: int | None = 0,
    error_count: int | None = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_data_quality_summary_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            quality_scope,
            scope_key,
            quality_status,
            expected_count,
            actual_count,
            missing_count,
            incomplete_count,
            stale_count,
            warning_count,
            error_count,
            detail,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            quality_scope,
            scope_key,
            quality_status,
            expected_count,
            actual_count,
            missing_count,
            incomplete_count,
            stale_count,
            warning_count,
            error_count,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_ecosystem_window_change(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "rolling30",
    group_scope: str = "LAYER",
    group_key: str = "AI",
    change_type: str = "IMPROVED",
    status: str = "OK",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_ecosystem_window_change_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            primary_layer,
            primary_subindustry,
            change_type,
            previous_value,
            current_value,
            delta_value,
            delta_pct,
            rank_previous,
            rank_current,
            rank_delta,
            status,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            "AI",
            "Semiconductors",
            change_type,
            1.0,
            2.0,
            1.0,
            100.0,
            5,
            2,
            -3,
            status,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_group_overheat_progression(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "rolling30",
    group_scope: str = "LAYER",
    group_key: str = "AI",
    overheat_status: str = "LOW",
    rotation_risk_status: str = "LOW",
    progression_class: str = "STABLE",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_group_overheat_progression_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            primary_layer,
            primary_subindustry,
            overheat_status,
            rotation_risk_status,
            previous_overheat_score,
            current_overheat_score,
            overheat_delta,
            previous_rotation_risk_score,
            current_rotation_risk_score,
            rotation_risk_delta,
            progression_class,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            "AI",
            "Semiconductors",
            overheat_status,
            rotation_risk_status,
            0.2,
            0.3,
            0.1,
            0.2,
            0.4,
            0.2,
            progression_class,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_group_relative_change(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "rolling30",
    group_scope: str = "LAYER",
    group_key: str = "AI",
    metric_name: str = "breadth",
    direction: str = "IMPROVING",
    status: str = "OK",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_group_relative_change_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            primary_layer,
            primary_subindustry,
            metric_name,
            previous_value,
            current_value,
            delta_value,
            delta_pct,
            direction,
            relative_rank,
            relative_rank_delta,
            status,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            "AI",
            "Semiconductors",
            metric_name,
            1.0,
            2.0,
            1.0,
            100.0,
            direction,
            3,
            -1,
            status,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_group_timing_persistence(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "rolling30",
    group_scope: str = "LAYER",
    group_key: str = "AI",
    timing_signal_name: str = "momentum_timing",
    persistence_class: str = "PERSISTENT",
    persistence_days: int | None = 5,
    status: str = "OK",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_group_timing_persistence_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            primary_layer,
            primary_subindustry,
            timing_signal_name,
            persistence_class,
            persistence_days,
            first_seen_date,
            last_seen_date,
            previous_state,
            current_state,
            state_delta,
            status,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            group_scope,
            group_key,
            "AI",
            "Semiconductors",
            timing_signal_name,
            persistence_class,
            persistence_days,
            "2026-05-25",
            "2026-05-30",
            "EARLY",
            "PERSISTING",
            "STABLE",
            status,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_ma_break_status(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "rolling30",
    entity_scope: str = "TICKER",
    entity_key: str = "NVDA",
    ma_name: str = "ema20",
    ma_period: int | None = 20,
    break_status: str = "ABOVE",
    break_direction: str = "UP",
    days_since_break: int | None = 2,
    status: str = "OK",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_ma_break_status_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            entity_scope,
            entity_key,
            ticker,
            primary_layer,
            primary_subindustry,
            ma_name,
            ma_period,
            break_status,
            break_direction,
            break_date,
            days_since_break,
            close_value,
            ma_value,
            distance_pct,
            status,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            entity_scope,
            entity_key,
            "NVDA" if entity_scope == "TICKER" else None,
            "AI",
            "Semiconductors",
            ma_name,
            ma_period,
            break_status,
            break_direction,
            "2026-05-28",
            days_since_break,
            100.0,
            95.0,
            5.26,
            status,
            None,
            _utc_timestamp(),
        ),
    )


def _insert_signal_freshness(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "rolling30",
    entity_scope: str = "TICKER",
    entity_key: str = "NVDA",
    signal_name: str = "bullish_divergence",
    freshness_class: str = "FRESH",
    age_trading_days: int | None = 1,
    age_calendar_days: int | None = 2,
    max_fresh_trading_days: int | None = 5,
    max_fresh_calendar_days: int | None = 7,
    is_fresh: int = 1,
    status: str = "OK",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_signal_freshness_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            entity_scope,
            entity_key,
            ticker,
            primary_layer,
            primary_subindustry,
            signal_name,
            signal_family,
            signal_date_observed,
            freshness_class,
            age_trading_days,
            age_calendar_days,
            max_fresh_trading_days,
            max_fresh_calendar_days,
            is_fresh,
            status,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            entity_scope,
            entity_key,
            "NVDA" if entity_scope == "TICKER" else None,
            "AI",
            "Semiconductors",
            signal_name,
            "divergence",
            "2026-05-29",
            freshness_class,
            age_trading_days,
            age_calendar_days,
            max_fresh_trading_days,
            max_fresh_calendar_days,
            is_fresh,
            status,
            None,
            _utc_timestamp(),
        ),
    )


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
    assert _table_exists(conn, "dc_report_valid_signal_date_v2")
    assert _table_exists(conn, "dc_report_watchlist_ticker_v2")
    assert _table_exists(conn, "dc_report_taxonomy_ticker_coverage_v2")
    assert _table_exists(conn, "dc_report_technical_relevance_context_v2")
    assert _table_exists(conn, "dc_report_data_quality_summary_v2")
    assert _table_exists(conn, "dc_report_ecosystem_window_change_v2")
    assert _table_exists(conn, "dc_report_group_overheat_progression_v2")
    assert _table_exists(conn, "dc_report_group_relative_change_v2")
    assert _table_exists(conn, "dc_report_group_timing_persistence_v2")
    assert _table_exists(conn, "dc_report_ma_break_status_v2")
    assert _table_exists(conn, "dc_report_signal_freshness_v2")

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
    assert _primary_key_columns(conn, "dc_report_valid_signal_date_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
    ]
    assert _primary_key_columns(conn, "dc_report_watchlist_ticker_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "ticker",
    ]
    assert _primary_key_columns(conn, "dc_report_taxonomy_ticker_coverage_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "ticker",
    ]
    assert _primary_key_columns(conn, "dc_report_technical_relevance_context_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "ticker",
        "signal_name",
        "signal_confirmed_as_of_date",
    ]
    assert _primary_key_columns(conn, "dc_report_data_quality_summary_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "quality_scope",
        "scope_key",
    ]
    assert _primary_key_columns(conn, "dc_report_ecosystem_window_change_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
        "change_type",
    ]
    assert _primary_key_columns(conn, "dc_report_group_overheat_progression_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
    ]
    assert _primary_key_columns(conn, "dc_report_group_relative_change_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
        "metric_name",
    ]
    assert _primary_key_columns(conn, "dc_report_group_timing_persistence_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
        "timing_signal_name",
    ]
    assert _primary_key_columns(conn, "dc_report_ma_break_status_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "entity_scope",
        "entity_key",
        "ma_name",
    ]
    assert _primary_key_columns(conn, "dc_report_signal_freshness_v2") == [
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "entity_scope",
        "entity_key",
        "signal_name",
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

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "source_run_id",
        "source_signal_date",
        "is_valid",
        "status",
        "reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_valid_signal_date_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "ticker",
        "watchlist_source",
        "primary_layer",
        "primary_subindustry",
        "coverage_status",
        "is_included",
        "missing_reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_watchlist_ticker_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "ticker",
        "primary_layer",
        "primary_subindustry",
        "coverage_status",
        "has_instrument",
        "has_price_data",
        "has_daily_signal",
        "has_rolling_context",
        "missing_reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_taxonomy_ticker_coverage_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "ticker",
        "timeframe",
        "signal_name",
        "signal_source_id",
        "signal_direction",
        "signal_family",
        "signal_confirmed_as_of_date",
        "relevance_class",
        "relevance_reason",
        "trend_state",
        "dow_context",
        "bos_context",
        "reset_context",
        "trend_alignment",
        "counter_trend_context",
        "source_run_id",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_technical_relevance_context_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "quality_scope",
        "scope_key",
        "quality_status",
        "expected_count",
        "actual_count",
        "missing_count",
        "incomplete_count",
        "stale_count",
        "warning_count",
        "error_count",
        "detail",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_data_quality_summary_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
        "primary_layer",
        "primary_subindustry",
        "change_type",
        "previous_value",
        "current_value",
        "delta_value",
        "delta_pct",
        "rank_previous",
        "rank_current",
        "rank_delta",
        "status",
        "reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_ecosystem_window_change_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
        "primary_layer",
        "primary_subindustry",
        "overheat_status",
        "rotation_risk_status",
        "previous_overheat_score",
        "current_overheat_score",
        "overheat_delta",
        "previous_rotation_risk_score",
        "current_rotation_risk_score",
        "rotation_risk_delta",
        "progression_class",
        "reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_group_overheat_progression_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
        "primary_layer",
        "primary_subindustry",
        "metric_name",
        "previous_value",
        "current_value",
        "delta_value",
        "delta_pct",
        "direction",
        "relative_rank",
        "relative_rank_delta",
        "status",
        "reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_group_relative_change_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "group_scope",
        "group_key",
        "primary_layer",
        "primary_subindustry",
        "timing_signal_name",
        "persistence_class",
        "persistence_days",
        "first_seen_date",
        "last_seen_date",
        "previous_state",
        "current_state",
        "state_delta",
        "status",
        "reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_group_timing_persistence_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "entity_scope",
        "entity_key",
        "ticker",
        "primary_layer",
        "primary_subindustry",
        "ma_name",
        "ma_period",
        "break_status",
        "break_direction",
        "break_date",
        "days_since_break",
        "close_value",
        "ma_value",
        "distance_pct",
        "status",
        "reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_ma_break_status_v2"))

    assert {
        "run_id",
        "signal_date",
        "taxonomy_version",
        "report_window",
        "entity_scope",
        "entity_key",
        "ticker",
        "primary_layer",
        "primary_subindustry",
        "signal_name",
        "signal_family",
        "signal_date_observed",
        "freshness_class",
        "age_trading_days",
        "age_calendar_days",
        "max_fresh_trading_days",
        "max_fresh_calendar_days",
        "is_fresh",
        "status",
        "reason",
        "created_at",
    }.issubset(_table_columns(conn, "dc_report_signal_freshness_v2"))


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

    assert {
        "idx_dc_report_valid_signal_date_v2_date_taxonomy_window",
    }.issubset(_index_names(conn, "dc_report_valid_signal_date_v2"))

    assert {
        "idx_dc_report_watchlist_ticker_v2_date_taxonomy_window_status",
        "idx_dc_report_watchlist_ticker_v2_ticker",
    }.issubset(_index_names(conn, "dc_report_watchlist_ticker_v2"))

    assert {
        "idx_dc_report_taxonomy_ticker_coverage_v2_date_taxonomy_status",
        "idx_dc_report_taxonomy_ticker_coverage_v2_ticker",
    }.issubset(_index_names(conn, "dc_report_taxonomy_ticker_coverage_v2"))

    assert {
        "idx_dc_report_technical_relevance_context_v2_date_taxonomy_window_ticker",
        "idx_dc_report_technical_relevance_context_v2_relevance_family",
    }.issubset(_index_names(conn, "dc_report_technical_relevance_context_v2"))

    assert {
        "idx_dc_report_data_quality_summary_v2_date_taxonomy_window_status",
        "idx_dc_report_data_quality_summary_v2_scope",
    }.issubset(_index_names(conn, "dc_report_data_quality_summary_v2"))

    assert {
        "idx_dc_report_ecosystem_window_change_v2_date_taxonomy_window_scope",
        "idx_dc_report_ecosystem_window_change_v2_change_status",
    }.issubset(_index_names(conn, "dc_report_ecosystem_window_change_v2"))

    assert {
        "idx_dc_report_group_overheat_progression_v2_date_taxonomy_window_scope",
        "idx_dc_report_group_overheat_progression_v2_progression",
    }.issubset(_index_names(conn, "dc_report_group_overheat_progression_v2"))

    assert {
        "idx_dc_report_group_relative_change_v2_date_taxonomy_window_scope",
        "idx_dc_report_group_relative_change_v2_metric_direction",
    }.issubset(_index_names(conn, "dc_report_group_relative_change_v2"))

    assert {
        "idx_dc_report_group_timing_persistence_v2_date_taxonomy_window_scope",
        "idx_dc_report_group_timing_persistence_v2_persistence_status",
    }.issubset(_index_names(conn, "dc_report_group_timing_persistence_v2"))

    assert {
        "idx_dc_report_ma_break_status_v2_date_taxonomy_window_scope",
        "idx_dc_report_ma_break_status_v2_break_status",
    }.issubset(_index_names(conn, "dc_report_ma_break_status_v2"))

    assert {
        "idx_dc_report_signal_freshness_v2_date_taxonomy_window_scope",
        "idx_dc_report_signal_freshness_v2_freshness_status",
    }.issubset(_index_names(conn, "dc_report_signal_freshness_v2"))


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
    assert _table_exists(conn, "dc_report_valid_signal_date_v2")
    assert _table_exists(conn, "dc_report_watchlist_ticker_v2")
    assert _table_exists(conn, "dc_report_taxonomy_ticker_coverage_v2")
    assert _table_exists(conn, "dc_report_technical_relevance_context_v2")
    assert _table_exists(conn, "dc_report_data_quality_summary_v2")
    assert _table_exists(conn, "dc_report_ecosystem_window_change_v2")
    assert _table_exists(conn, "dc_report_group_overheat_progression_v2")
    assert _table_exists(conn, "dc_report_group_relative_change_v2")
    assert _table_exists(conn, "dc_report_group_timing_persistence_v2")
    assert _table_exists(conn, "dc_report_ma_break_status_v2")
    assert _table_exists(conn, "dc_report_signal_freshness_v2")


def test_group_timing_persistence_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_group_timing_persistence(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_timing_persistence(conn, run_id=run_id)


def test_ma_break_status_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_ma_break_status(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ma_break_status(conn, run_id=run_id)


def test_signal_freshness_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_signal_freshness(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_signal_freshness(conn, run_id=run_id)


@pytest.mark.parametrize("report_window", ["daily", "rolling2", "rolling5", "rolling30"])
def test_timing_freshness_tables_report_window_accept_known_values(report_window: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-tf-{report_window}")

    _insert_group_timing_persistence(conn, run_id=run_id, report_window=report_window, group_key=f"G{report_window}")
    _insert_ma_break_status(conn, run_id=run_id, report_window=report_window, entity_key=f"M{report_window}")
    _insert_signal_freshness(conn, run_id=run_id, report_window=report_window, entity_key=f"S{report_window}")


def test_timing_freshness_tables_report_window_reject_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_timing_persistence(conn, run_id=run_id, report_window="rolling99")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ma_break_status(conn, run_id=run_id, report_window="rolling99", entity_key="M2")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_signal_freshness(conn, run_id=run_id, report_window="rolling99", entity_key="S2")


@pytest.mark.parametrize("group_scope", ["LAYER", "SUBINDUSTRY", "ECOSYSTEM", "WATCHLIST", "MARKET"])
def test_group_timing_persistence_group_scope_accepts_known_values(group_scope: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-timing-scope-{group_scope}")

    _insert_group_timing_persistence(conn, run_id=run_id, group_scope=group_scope, group_key=f"G{group_scope}")


def test_group_timing_persistence_group_scope_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_timing_persistence(conn, run_id=run_id, group_scope="GROUP")


@pytest.mark.parametrize("entity_scope", ["TICKER", "LAYER", "SUBINDUSTRY", "ECOSYSTEM", "WATCHLIST", "MARKET"])
def test_timing_freshness_entity_scope_accepts_known_values(entity_scope: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-entity-scope-{entity_scope}")

    _insert_ma_break_status(conn, run_id=run_id, entity_scope=entity_scope, entity_key=f"M{entity_scope}")
    _insert_signal_freshness(conn, run_id=run_id, entity_scope=entity_scope, entity_key=f"S{entity_scope}")


def test_timing_freshness_entity_scope_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ma_break_status(conn, run_id=run_id, entity_scope="GROUP")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_signal_freshness(conn, run_id=run_id, entity_scope="GROUP", entity_key="S3")


@pytest.mark.parametrize(
    "persistence_class",
    ["PERSISTENT", "IMPROVING", "DETERIORATING", "FADING", "NEW", "LOST", "UNSTABLE", "UNKNOWN"],
)
def test_group_timing_persistence_class_accepts_known_values(persistence_class: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-persistence-{persistence_class}")

    _insert_group_timing_persistence(
        conn,
        run_id=run_id,
        group_key=f"P{persistence_class}",
        timing_signal_name=f"signal_{persistence_class.lower()}",
        persistence_class=persistence_class,
    )


def test_group_timing_persistence_class_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_timing_persistence(conn, run_id=run_id, persistence_class="STICKY")


@pytest.mark.parametrize(
    "break_status",
    ["ABOVE", "BELOW", "BROKEN_UP", "BROKEN_DOWN", "TESTING", "RECLAIMED", "LOST", "NO_BREAK", "UNKNOWN"],
)
def test_ma_break_status_accepts_known_values(break_status: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-break-status-{break_status}")

    _insert_ma_break_status(
        conn,
        run_id=run_id,
        entity_key=f"B{break_status}",
        ma_name=f"ma_{break_status.lower()}",
        break_status=break_status,
    )


def test_ma_break_status_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ma_break_status(conn, run_id=run_id, break_status="CROSSED")


@pytest.mark.parametrize("break_direction", ["UP", "DOWN", "FLAT", "MIXED", "NONE", "UNKNOWN"])
def test_ma_break_direction_accepts_known_values(break_direction: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-break-dir-{break_direction}")

    _insert_ma_break_status(
        conn,
        run_id=run_id,
        entity_key=f"D{break_direction}",
        ma_name=f"ma_dir_{break_direction.lower()}",
        break_direction=break_direction,
    )


def test_ma_break_direction_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ma_break_status(conn, run_id=run_id, break_direction="SIDEWAYS")


@pytest.mark.parametrize("freshness_class", ["FRESH", "AGING", "STALE", "EXPIRED", "MISSING", "UNKNOWN"])
def test_signal_freshness_class_accepts_known_values(freshness_class: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-freshness-{freshness_class}")

    _insert_signal_freshness(
        conn,
        run_id=run_id,
        entity_key=f"F{freshness_class}",
        signal_name=f"signal_{freshness_class.lower()}",
        freshness_class=freshness_class,
    )


def test_signal_freshness_class_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_signal_freshness(conn, run_id=run_id, freshness_class="RECENT")


def test_signal_freshness_is_fresh_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_signal_freshness(conn, run_id=run_id, is_fresh=2)


@pytest.mark.parametrize(
    ("field_name", "builder"),
    [
        ("persistence_days", "_insert_group_timing_persistence"),
        ("ma_period", "_insert_ma_break_status"),
        ("days_since_break", "_insert_ma_break_status"),
        ("age_trading_days", "_insert_signal_freshness"),
        ("age_calendar_days", "_insert_signal_freshness"),
        ("max_fresh_trading_days", "_insert_signal_freshness"),
        ("max_fresh_calendar_days", "_insert_signal_freshness"),
    ],
)
def test_timing_freshness_negative_numeric_fields_reject_invalid_values(field_name: str, builder: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-negative-{field_name}")

    kwargs = {field_name: -1}

    with pytest.raises(sqlite3.IntegrityError):
        globals()[builder](conn, run_id=run_id, **kwargs)


def test_ecosystem_window_change_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_ecosystem_window_change(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ecosystem_window_change(conn, run_id=run_id)


def test_group_overheat_progression_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_group_overheat_progression(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_overheat_progression(conn, run_id=run_id)


def test_group_relative_change_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_group_relative_change(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_relative_change(conn, run_id=run_id)


@pytest.mark.parametrize("report_window", ["daily", "rolling2", "rolling5", "rolling30"])
def test_group_progression_tables_report_window_accept_known_values(report_window: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-prog-{report_window}")

    _insert_ecosystem_window_change(conn, run_id=run_id, report_window=report_window, group_key=f"E{report_window}")
    _insert_group_overheat_progression(conn, run_id=run_id, report_window=report_window, group_key=f"O{report_window}")
    _insert_group_relative_change(conn, run_id=run_id, report_window=report_window, group_key=f"R{report_window}")


def test_group_progression_tables_report_window_reject_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ecosystem_window_change(conn, run_id=run_id, report_window="rolling99")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_overheat_progression(conn, run_id=run_id, report_window="rolling99", group_key="O2")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_relative_change(conn, run_id=run_id, report_window="rolling99", group_key="R2")


@pytest.mark.parametrize("group_scope", ["LAYER", "SUBINDUSTRY", "ECOSYSTEM", "WATCHLIST", "MARKET"])
def test_group_progression_tables_group_scope_accept_known_values(group_scope: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-scope-{group_scope}")

    _insert_ecosystem_window_change(conn, run_id=run_id, group_scope=group_scope, group_key=f"E{group_scope}")
    _insert_group_overheat_progression(conn, run_id=run_id, group_scope=group_scope, group_key=f"O{group_scope}")
    _insert_group_relative_change(conn, run_id=run_id, group_scope=group_scope, group_key=f"R{group_scope}")


def test_group_progression_tables_group_scope_reject_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ecosystem_window_change(conn, run_id=run_id, group_scope="GROUP")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_overheat_progression(conn, run_id=run_id, group_scope="GROUP", group_key="O3")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_group_relative_change(conn, run_id=run_id, group_scope="GROUP", group_key="R3")


@pytest.mark.parametrize(
    "change_type",
    [
        "IMPROVED",
        "DETERIORATED",
        "APPEARED",
        "DISAPPEARED",
        "UNCHANGED",
        "WORSENED",
        "RECOVERED",
        "ROTATED_IN",
        "ROTATED_OUT",
        "UNKNOWN",
    ],
)
def test_ecosystem_window_change_change_type_accepts_known_values(change_type: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-change-{change_type}")

    _insert_ecosystem_window_change(
        conn,
        run_id=run_id,
        group_key=f"C{change_type}",
        change_type=change_type,
    )


def test_ecosystem_window_change_change_type_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_ecosystem_window_change(conn, run_id=run_id, change_type="SHIFTED")


@pytest.mark.parametrize("overheat_status", ["NONE", "LOW", "MODERATE", "HIGH", "EXTREME", "UNKNOWN"])
def test_group_overheat_progression_overheat_status_accepts_known_values(overheat_status: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-overheat-{overheat_status}")

    _insert_group_overheat_progression(
        conn,
        run_id=run_id,
        group_key=f"H{overheat_status}",
        overheat_status=overheat_status,
    )


@pytest.mark.parametrize("rotation_risk_status", ["NONE", "LOW", "MODERATE", "HIGH", "EXTREME", "UNKNOWN"])
def test_group_overheat_progression_rotation_risk_status_accepts_known_values(rotation_risk_status: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-rotation-{rotation_risk_status}")

    _insert_group_overheat_progression(
        conn,
        run_id=run_id,
        group_key=f"RR{rotation_risk_status}",
        rotation_risk_status=rotation_risk_status,
    )


@pytest.mark.parametrize(
    "progression_class",
    [
        "HEATING_UP",
        "COOLING_DOWN",
        "STABLE",
        "ROTATION_RISK_INCREASING",
        "ROTATION_RISK_DECREASING",
        "NORMALIZING",
        "UNKNOWN",
    ],
)
def test_group_overheat_progression_class_accepts_known_values(progression_class: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-progression-{progression_class}")

    _insert_group_overheat_progression(
        conn,
        run_id=run_id,
        group_key=f"P{progression_class}",
        progression_class=progression_class,
    )


@pytest.mark.parametrize("direction", ["IMPROVING", "DETERIORATING", "FLAT", "MIXED", "UNKNOWN"])
def test_group_relative_change_direction_accepts_known_values(direction: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-direction-{direction}")

    _insert_group_relative_change(
        conn,
        run_id=run_id,
        group_key=f"D{direction}",
        metric_name=f"metric_{direction.lower()}",
        direction=direction,
    )


@pytest.mark.parametrize("status", ["OK", "WARN", "ERROR", "MISSING", "INCOMPLETE", "UNKNOWN"])
def test_group_progression_status_accepts_known_values(status: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-status-{status}")

    _insert_ecosystem_window_change(conn, run_id=run_id, group_key=f"SE{status}", status=status)
    _insert_group_relative_change(
        conn,
        run_id=run_id,
        group_key=f"SR{status}",
        metric_name=f"metric_status_{status.lower()}",
        status=status,
    )


def test_technical_relevance_context_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_technical_relevance_context(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_technical_relevance_context(conn, run_id=run_id)


def test_data_quality_summary_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_data_quality_summary(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_data_quality_summary(conn, run_id=run_id)


@pytest.mark.parametrize("report_window", ["daily", "rolling2", "rolling5", "rolling30"])
def test_technical_relevance_context_report_window_accepts_known_values(report_window: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-tech-{report_window}")

    _insert_technical_relevance_context(
        conn,
        run_id=run_id,
        report_window=report_window,
        ticker=f"T{report_window}",
        signal_name=f"signal_{report_window}",
    )


def test_technical_relevance_context_report_window_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_technical_relevance_context(conn, run_id=run_id, report_window="rolling99")


@pytest.mark.parametrize(
    "relevance_class",
    ["RELEVANT", "NOT_RELEVANT", "CONTEXTUAL", "CONFIRMING", "COUNTER_TREND", "STALE", "UNKNOWN"],
)
def test_technical_relevance_context_relevance_class_accepts_known_values(relevance_class: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-tech-rel-{relevance_class}")

    _insert_technical_relevance_context(
        conn,
        run_id=run_id,
        ticker=f"T{len(relevance_class)}{relevance_class[0]}",
        signal_name=f"signal_{relevance_class.lower()}",
        relevance_class=relevance_class,
    )


def test_technical_relevance_context_relevance_class_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_technical_relevance_context(conn, run_id=run_id, relevance_class="PRIORITY")


@pytest.mark.parametrize("signal_direction", ["BULLISH", "BEARISH", "NEUTRAL", "MIXED", "UNKNOWN"])
def test_technical_relevance_context_signal_direction_accepts_known_values(signal_direction: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-tech-dir-{signal_direction}")

    _insert_technical_relevance_context(
        conn,
        run_id=run_id,
        ticker=f"D{len(signal_direction)}{signal_direction[0]}",
        signal_name=f"dir_{signal_direction.lower()}",
        signal_direction=signal_direction,
    )


def test_technical_relevance_context_signal_direction_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_technical_relevance_context(conn, run_id=run_id, signal_direction="LONG")


@pytest.mark.parametrize("report_window", ["daily", "rolling2", "rolling5", "rolling30"])
def test_data_quality_summary_report_window_accepts_known_values(report_window: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-quality-{report_window}")

    _insert_data_quality_summary(
        conn,
        run_id=run_id,
        report_window=report_window,
        scope_key=f"scope_{report_window}",
    )


def test_data_quality_summary_report_window_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_data_quality_summary(conn, run_id=run_id, report_window="rolling99")


@pytest.mark.parametrize("quality_scope", ["RUN", "WINDOW", "TAXONOMY", "WATCHLIST", "LAYER", "SUBINDUSTRY", "TICKER", "SOURCE"])
def test_data_quality_summary_quality_scope_accepts_known_values(quality_scope: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-quality-scope-{quality_scope}")

    _insert_data_quality_summary(
        conn,
        run_id=run_id,
        quality_scope=quality_scope,
        scope_key=f"scope_{quality_scope.lower()}",
    )


def test_data_quality_summary_quality_scope_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_data_quality_summary(conn, run_id=run_id, quality_scope="GROUP")


@pytest.mark.parametrize("quality_status", ["OK", "WARN", "ERROR", "MISSING", "INCOMPLETE", "STALE", "UNKNOWN"])
def test_data_quality_summary_quality_status_accepts_known_values(quality_status: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-quality-status-{quality_status}")

    _insert_data_quality_summary(
        conn,
        run_id=run_id,
        quality_status=quality_status,
        scope_key=f"status_{quality_status.lower()}",
    )


def test_data_quality_summary_quality_status_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_data_quality_summary(conn, run_id=run_id, quality_status="DEGRADED")


@pytest.mark.parametrize(
    "field_name",
    [
        "expected_count",
        "actual_count",
        "missing_count",
        "incomplete_count",
        "stale_count",
        "warning_count",
        "error_count",
    ],
)
def test_data_quality_summary_negative_counts_reject_invalid_values(field_name: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-negative-{field_name}")

    kwargs = {field_name: -1, "scope_key": f"neg_{field_name}"}

    with pytest.raises(sqlite3.IntegrityError):
        _insert_data_quality_summary(conn, run_id=run_id, **kwargs)


def test_watchlist_ticker_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_watchlist_ticker(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_watchlist_ticker(conn, run_id=run_id)


def test_taxonomy_ticker_coverage_primary_key_rejects_duplicate_row():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_taxonomy_ticker_coverage(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_taxonomy_ticker_coverage(conn, run_id=run_id)


@pytest.mark.parametrize("report_window", ["daily", "rolling2", "rolling5", "rolling30"])
def test_watchlist_ticker_report_window_accepts_known_values(report_window: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-{report_window}")

    _insert_watchlist_ticker(conn, run_id=run_id, report_window=report_window, ticker=f"T{report_window}")


def test_watchlist_ticker_report_window_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_watchlist_ticker(conn, run_id=run_id, report_window="rolling99")


def test_watchlist_ticker_boolean_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_watchlist_ticker(conn, run_id=run_id, is_included=2)


@pytest.mark.parametrize(
    "coverage_status",
    [
        "OK",
        "MISSING_INSTRUMENT",
        "MISSING_PRICE_DATA",
        "MISSING_DAILY_SIGNAL",
        "MISSING_ROLLING_CONTEXT",
        "WATCHLIST_ONLY",
        "EXCLUDED",
    ],
)
def test_watchlist_ticker_coverage_status_accepts_known_values(coverage_status: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-watchlist-{coverage_status}")

    _insert_watchlist_ticker(
        conn,
        run_id=run_id,
        ticker=f"T{abs(hash(coverage_status))}",
        coverage_status=coverage_status,
    )


def test_watchlist_ticker_coverage_status_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_watchlist_ticker(conn, run_id=run_id, coverage_status="UNKNOWN")


def test_taxonomy_ticker_boolean_checks_reject_invalid_values():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_taxonomy_ticker_coverage(conn, run_id=run_id, has_instrument=2)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_taxonomy_ticker_coverage(conn, run_id=run_id, ticker="AAPL", has_price_data=2)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_taxonomy_ticker_coverage(conn, run_id=run_id, ticker="MSFT", has_daily_signal=2)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_taxonomy_ticker_coverage(conn, run_id=run_id, ticker="AMD", has_rolling_context=2)


@pytest.mark.parametrize(
    "coverage_status",
    [
        "OK",
        "MISSING_INSTRUMENT",
        "MISSING_PRICE_DATA",
        "MISSING_DAILY_SIGNAL",
        "MISSING_ROLLING_CONTEXT",
        "TAXONOMY_ONLY",
    ],
)
def test_taxonomy_ticker_coverage_status_accepts_known_values(coverage_status: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-taxonomy-{coverage_status}")

    _insert_taxonomy_ticker_coverage(
        conn,
        run_id=run_id,
        ticker=f"T{abs(hash((coverage_status, 'taxonomy')))}",
        coverage_status=coverage_status,
    )


def test_taxonomy_ticker_coverage_status_rejects_unknown_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_taxonomy_ticker_coverage(conn, run_id=run_id, coverage_status="UNKNOWN")


def _insert_valid_signal_date(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    report_window: str = "rolling30",
    is_valid: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_valid_signal_date_v2 (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            source_run_id,
            source_signal_date,
            is_valid,
            status,
            reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signal_date,
            taxonomy_version,
            report_window,
            "source-run-1",
            signal_date,
            is_valid,
            "READY",
            None,
        ),
    )


def test_valid_signal_date_primary_key_rejects_duplicate_rows():
    conn = _connect()
    run_id = _insert_run(conn)

    _insert_valid_signal_date(conn, run_id=run_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_valid_signal_date(conn, run_id=run_id)


def test_valid_signal_date_is_valid_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_valid_signal_date(conn, run_id=run_id, is_valid=2)


@pytest.mark.parametrize("report_window", ["daily", "rolling2", "rolling5", "rolling30"])
def test_valid_signal_date_report_window_accepts_known_values(report_window: str):
    conn = _connect()
    run_id = _insert_run(conn, run_id=f"run-{report_window}")

    _insert_valid_signal_date(conn, run_id=run_id, report_window=report_window)

    row = conn.execute(
        """
        SELECT report_window
        FROM dc_report_valid_signal_date_v2
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()

    assert row == (report_window,)


def test_valid_signal_date_report_window_check_rejects_invalid_value():
    conn = _connect()
    run_id = _insert_run(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_valid_signal_date(conn, run_id=run_id, report_window="rolling99")


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
