import sqlite3

import pytest

from analysis.datacenter_indices.report_canonical_v2_window_context_builder import (
    build_report_window_context_v2,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            market TEXT NULL,
            ticker TEXT NOT NULL,
            primary_layer TEXT NULL,
            primary_subindustry TEXT NULL,
            price_data_status TEXT NULL,
            breakout_signal INTEGER NULL,
            pullback_signal INTEGER NULL,
            fast_ema10_pullback_signal INTEGER NULL,
            conservative_ema20_pullback_signal INTEGER NULL,
            exit_risk_signal INTEGER NULL,
            exit_risk_severity TEXT NULL,
            exit_reason TEXT NULL,
            latest_bearish_relevance_class TEXT NULL,
            return_10d REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            ticker_trend_state TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_freshness TEXT NULL
        )
        """
    )
    return conn


def _insert_run(conn: sqlite3.Connection, run_id: str = "run-1") -> None:
    conn.execute(
        """
        INSERT INTO dc_report_run_v2 (
            run_id, signal_date, taxonomy_version, market, calculation_version,
            source_versions_json, created_at_utc, status, warning_count, error_count, notes
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
    conn.commit()


def _insert_valid_date(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str = "usa",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, signal_version, market, group_type, group_name
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            "DC_SWING_SIGNAL_V1",
            market,
            "layer",
            "Infrastructure",
        ),
    )


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    ticker: str = "NVDA",
    market: str = "usa",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    primary_layer: str = "Infrastructure",
    primary_subindustry: str = "Semis",
    breakout_signal: int = 0,
    pullback_signal: int = 0,
    fast_pullback: int = 0,
    conservative_pullback: int = 0,
    exit_risk_signal: int = 0,
    exit_risk_severity: str | None = None,
    price_data_status: str | None = "OK",
    return_10d: float | None = 1.0,
    distance_to_ema20_pct: float | None = 1.0,
    distance_to_ema50_pct: float | None = 2.0,
    latest_bearish_relevance_class: str | None = None,
    trend_state: str = "UP",
    latest_structure_label: str = "HL",
    latest_structure_freshness: str = "FRESH",
    latest_bos_event_type: str | None = "BOS_UP",
    latest_bos_freshness: str | None = "FRESH",
    latest_reset_reason: str | None = "NONE",
    latest_reset_freshness: str | None = "STALE",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, signal_version, market, ticker,
            primary_layer, primary_subindustry, price_data_status, breakout_signal,
            pullback_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
            exit_risk_signal, exit_risk_severity, exit_reason, latest_bearish_relevance_class, return_10d,
            distance_to_ema20_pct, distance_to_ema50_pct, ticker_trend_state,
            latest_structure_label, latest_structure_freshness, latest_bos_event_type,
            latest_bos_freshness, latest_reset_reason, latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            "DC_SWING_SIGNAL_V1",
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            price_data_status,
            breakout_signal,
            pullback_signal,
            fast_pullback,
            conservative_pullback,
            exit_risk_signal,
            exit_risk_severity,
            "reason-token",
            latest_bearish_relevance_class,
            return_10d,
            distance_to_ema20_pct,
            distance_to_ema50_pct,
            trend_state,
            latest_structure_label,
            latest_structure_freshness,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
        ),
    )


def _insert_group_context_row(
    conn: sqlite3.Connection,
    *,
    horizon: str,
    group_type: str,
    group_name: str,
    market: str = "usa",
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
    risk_status: str = "NO",
    run_id: str = "run-1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date, taxonomy_version, market, horizon, group_type, group_name,
            timing_state, overheat_risk_level, group_context_risk_status,
            group_context_readiness_status, group_current_status, group_window_status,
            group_status_change, window_start_date, window_end_date, valid_signal_dates,
            run_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OK', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            market,
            horizon,
            group_type,
            group_name,
            timing_state,
            overheat_risk_level,
            risk_status,
            timing_state,
            timing_state,
            None,
            "2026-05-29",
            signal_date,
            2 if horizon == "rolling2" else 5 if horizon == "rolling5" else 30,
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def test_rolling2_window_rows_are_written():
    conn = _connect()
    _insert_run(conn)
    _insert_valid_date(conn, signal_date="2026-05-29")
    _insert_valid_date(conn, signal_date="2026-05-30")
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis", risk_status="YES")
    _insert_ticker_row(conn, signal_date="2026-05-29", breakout_signal=1)
    _insert_ticker_row(conn, signal_date="2026-05-30", pullback_signal=1, conservative_pullback=1)
    conn.commit()

    summary = build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    row = conn.execute(
        """
        SELECT *
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling2"),
    ).fetchone()

    assert row is not None
    assert row["window_start_date"] == "2026-05-29"
    assert row["window_end_date"] == "2026-05-30"
    assert row["valid_signal_dates"] == 2
    assert row["incomplete_window"] == 0
    assert row["breakout_days"] == 1
    assert row["pullback_days"] == 1
    assert row["conservative_ema20_pullback_days"] == 1
    assert row["first_signal_date"] == "2026-05-29"
    assert row["last_signal_date"] == "2026-05-30"
    assert row["trend_state"] == "UP"
    assert row["latest_structure_label"] == "HL"
    assert row["layer_timing_state"] == "BUY_ZONE"
    assert row["subindustry_context_risk_status"] == "YES"
    assert row["current_watchlist_status"] == "PULLBACK_CANDIDATE"
    assert row["window_watchlist_status"] == "BREAKOUT_CANDIDATE"
    assert row["context_readiness_status"] == "OK"
    assert summary["rolling2_rows_written"] == 1
    assert summary["total_rows_written"] == 1


def test_rolling2_classifier_input_fields_are_persisted_from_source_to_canonical():
    conn = _connect()
    _insert_run(conn)
    _insert_valid_date(conn, signal_date="2026-05-29")
    _insert_valid_date(conn, signal_date="2026-05-30")
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis")
    _insert_ticker_row(
        conn,
        signal_date="2026-05-29",
        ticker="NVDA",
        price_data_status="OK",
        exit_risk_severity="MEDIUM",
        latest_bearish_relevance_class="WEAK_CONTEXT",
        distance_to_ema20_pct=0.5,
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-30",
        ticker="NVDA",
        price_data_status="MISSING_AS_OF_DATE",
        exit_risk_severity="HIGH",
        latest_bearish_relevance_class="RELEVANT",
        distance_to_ema20_pct=-1.25,
    )
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    row = conn.execute(
        """
        SELECT
            price_data_status,
            exit_risk_severity,
            latest_bearish_relevance_class,
            distance_to_ema20_pct,
            all_price_rows_missing
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling2"),
    ).fetchone()

    assert row is not None
    assert row["price_data_status"] == "MISSING_AS_OF_DATE"
    assert row["exit_risk_severity"] == "HIGH"
    assert row["latest_bearish_relevance_class"] == "RELEVANT"
    assert row["distance_to_ema20_pct"] == pytest.approx(-1.25)
    assert row["all_price_rows_missing"] == 0


def test_rolling5_and_rolling30_can_be_requested_together():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-28", "2026-05-29", "2026-05-30"):
        _insert_valid_date(conn, signal_date=date_value)
        _insert_ticker_row(conn, signal_date=date_value, breakout_signal=1 if date_value == "2026-05-28" else 0)
    for horizon in ("rolling5", "rolling30"):
        _insert_group_context_row(conn, horizon=horizon, group_type="layer", group_name="Infrastructure")
        _insert_group_context_row(conn, horizon=horizon, group_type="subindustry", group_name="Semis")
    conn.commit()

    summary = build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling5", "rolling30"),
    )

    rows = conn.execute(
        """
        SELECT horizon, valid_signal_dates, incomplete_window, context_readiness_status
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY horizon ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1"),
    ).fetchall()

    assert [(row["horizon"], row["valid_signal_dates"], row["incomplete_window"], row["context_readiness_status"]) for row in rows] == [
        ("rolling30", 3, 1, "PARTIAL_WINDOW"),
        ("rolling5", 3, 1, "PARTIAL_WINDOW"),
    ]
    assert summary["rolling5_rows_written"] == 1
    assert summary["rolling30_rows_written"] == 1


def test_missing_group_context_readiness_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_valid_date(conn, signal_date="2026-05-29")
    _insert_valid_date(conn, signal_date="2026-05-30")
    _insert_ticker_row(conn, signal_date="2026-05-29")
    _insert_ticker_row(conn, signal_date="2026-05-30")
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    row = conn.execute(
        """
        SELECT context_readiness_status, layer_timing_state, subindustry_timing_state
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling2"),
    ).fetchone()

    assert row is not None
    assert row["context_readiness_status"] == "MISSING_GROUP_CONTEXT"
    assert row["layer_timing_state"] is None
    assert row["subindustry_timing_state"] is None


def test_missing_layer_context_readiness_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_valid_date(conn, signal_date="2026-05-29")
    _insert_valid_date(conn, signal_date="2026-05-30")
    _insert_ticker_row(conn, signal_date="2026-05-29")
    _insert_ticker_row(conn, signal_date="2026-05-30")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis")
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    row = conn.execute(
        """
        SELECT context_readiness_status, layer_timing_state, subindustry_timing_state
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling2"),
    ).fetchone()

    assert row is not None
    assert row["context_readiness_status"] == "MISSING_LAYER_CONTEXT"
    assert row["layer_timing_state"] is None
    assert row["subindustry_timing_state"] == "BUY_ZONE"


def test_missing_subindustry_context_readiness_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_valid_date(conn, signal_date="2026-05-29")
    _insert_valid_date(conn, signal_date="2026-05-30")
    _insert_ticker_row(conn, signal_date="2026-05-29")
    _insert_ticker_row(conn, signal_date="2026-05-30")
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    row = conn.execute(
        """
        SELECT context_readiness_status, layer_timing_state, subindustry_timing_state
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling2"),
    ).fetchone()

    assert row is not None
    assert row["context_readiness_status"] == "MISSING_SUBINDUSTRY_CONTEXT"
    assert row["layer_timing_state"] == "BUY_ZONE"
    assert row["subindustry_timing_state"] is None


def test_explicit_signal_flags_are_written_deterministically():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-29", "2026-05-30"):
        _insert_valid_date(conn, signal_date=date_value)
    _insert_group_context_row(
        conn,
        horizon="rolling2",
        group_type="layer",
        group_name="Infrastructure",
        overheat_risk_level="HIGH",
    )
    _insert_group_context_row(
        conn,
        horizon="rolling2",
        group_type="subindustry",
        group_name="Semis",
        overheat_risk_level="EXTREME",
    )
    _insert_ticker_row(conn, signal_date="2026-05-29", ticker="NVDA")
    _insert_ticker_row(
        conn,
        signal_date="2026-05-30",
        ticker="NVDA",
        exit_risk_signal=1,
        exit_risk_severity="CRITICAL",
        return_10d=-9.0,
        distance_to_ema20_pct=-1.5,
        distance_to_ema50_pct=-2.5,
        latest_structure_freshness="AGING",
        latest_bos_event_type="BOS_DOWN",
        latest_bos_freshness="CURRENT",
        latest_reset_reason="DOUBLE_BOS_DOWN",
        latest_reset_freshness="CURRENT",
    )
    _insert_ticker_row(conn, signal_date="2026-05-29", ticker="AMD")
    _insert_ticker_row(
        conn,
        signal_date="2026-05-30",
        ticker="AMD",
        latest_reset_reason="DOUBLE_BOS_UP",
        latest_reset_freshness="CURRENT",
    )
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    nvda_row = conn.execute(
        """
        SELECT
            close_below_ema20_flag,
            close_below_ema50_flag,
            return_10d_lt_minus_8pct_flag,
            double_bos_down_flag,
            double_bos_up_flag,
            fresh_bos_flag,
            fresh_reset_flag,
            stale_structure_flag,
            layer_overheat_risk_flag,
            subindustry_overheat_risk_flag,
            severe_exit_risk_flag
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling2"),
    ).fetchone()
    amd_row = conn.execute(
        """
        SELECT double_bos_down_flag, double_bos_up_flag, fresh_reset_flag
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "AMD", "rolling2"),
    ).fetchone()

    assert nvda_row is not None
    assert nvda_row["close_below_ema20_flag"] == 1
    assert nvda_row["close_below_ema50_flag"] == 1
    assert nvda_row["return_10d_lt_minus_8pct_flag"] == 1
    assert nvda_row["double_bos_down_flag"] == 1
    assert nvda_row["double_bos_up_flag"] == 0
    assert nvda_row["fresh_bos_flag"] == 1
    assert nvda_row["fresh_reset_flag"] == 1
    assert nvda_row["stale_structure_flag"] == 1
    assert nvda_row["layer_overheat_risk_flag"] == 1
    assert nvda_row["subindustry_overheat_risk_flag"] == 1
    assert nvda_row["severe_exit_risk_flag"] == 1

    assert amd_row is not None
    assert amd_row["double_bos_down_flag"] == 0
    assert amd_row["double_bos_up_flag"] == 1
    assert amd_row["fresh_reset_flag"] == 1


def test_missing_price_status_drives_current_and_window_watchlist_status():
    conn = _connect()
    _insert_run(conn)
    _insert_valid_date(conn, signal_date="2026-05-29")
    _insert_valid_date(conn, signal_date="2026-05-30")
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, signal_date="2026-05-29", price_data_status="MISSING_AS_OF_DATE")
    _insert_ticker_row(conn, signal_date="2026-05-30", price_data_status="MISSING_CLOSE_AS_OF_DATE")
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    row = conn.execute(
        """
        SELECT current_watchlist_status, window_watchlist_status, all_price_rows_missing
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling2"),
    ).fetchone()

    assert row is not None
    assert row["current_watchlist_status"] == "MISSING_PRICE"
    assert row["window_watchlist_status"] == "MISSING_PRICE"
    assert row["all_price_rows_missing"] == 1


def test_market_safe_delete_behavior_preserves_unrelated_market_rows():
    conn = _connect()
    _insert_run(conn)
    for market in ("usa", "omxh"):
        _insert_valid_date(conn, signal_date="2026-05-29", market=market)
        _insert_valid_date(conn, signal_date="2026-05-30", market=market)
    _insert_ticker_row(conn, signal_date="2026-05-29", market="usa", ticker="NVDA")
    _insert_ticker_row(conn, signal_date="2026-05-30", market="usa", ticker="NVDA")
    _insert_ticker_row(conn, signal_date="2026-05-29", market="omxh", ticker="NOKIA", primary_layer="NordicInfra", primary_subindustry="NordicSemis")
    _insert_ticker_row(conn, signal_date="2026-05-30", market="omxh", ticker="NOKIA", primary_layer="NordicInfra", primary_subindustry="NordicSemis")
    _insert_group_context_row(conn, horizon="rolling2", market="usa", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", market="usa", group_type="subindustry", group_name="Semis")
    _insert_group_context_row(conn, horizon="rolling2", market="omxh", group_type="layer", group_name="NordicInfra")
    _insert_group_context_row(conn, horizon="rolling2", market="omxh", group_type="subindustry", group_name="NordicSemis")
    conn.commit()

    build_report_window_context_v2(conn, signal_date="2026-05-30", taxonomy_version="DC_TAXONOMY_FULL_V1", run_id="run-1", market="usa", horizons=("rolling2",))
    build_report_window_context_v2(conn, signal_date="2026-05-30", taxonomy_version="DC_TAXONOMY_FULL_V1", run_id="run-1", market="omxh", horizons=("rolling2",))
    build_report_window_context_v2(conn, signal_date="2026-05-30", taxonomy_version="DC_TAXONOMY_FULL_V1", run_id="run-1", market="usa", horizons=("rolling2",))

    rows = conn.execute(
        """
        SELECT market, ticker
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        ORDER BY market ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling2"),
    ).fetchall()

    assert [(row["market"], row["ticker"]) for row in rows] == [("omxh", "NOKIA"), ("usa", "NVDA")]


def test_unrelated_horizon_preservation():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-29", "2026-05-30"):
        _insert_valid_date(conn, signal_date=date_value)
        _insert_ticker_row(conn, signal_date=date_value)
    for horizon in ("rolling2", "rolling5"):
        _insert_group_context_row(conn, horizon=horizon, group_type="layer", group_name="Infrastructure")
        _insert_group_context_row(conn, horizon=horizon, group_type="subindustry", group_name="Semis")
    conn.commit()

    build_report_window_context_v2(conn, signal_date="2026-05-30", taxonomy_version="DC_TAXONOMY_FULL_V1", run_id="run-1", market="usa", horizons=("rolling2", "rolling5"))
    build_report_window_context_v2(conn, signal_date="2026-05-30", taxonomy_version="DC_TAXONOMY_FULL_V1", run_id="run-1", market="usa", horizons=("rolling2",))

    rows = conn.execute(
        """
        SELECT horizon, COUNT(*)
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        GROUP BY horizon
        ORDER BY horizon ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1"),
    ).fetchall()

    assert [(row[0], row[1]) for row in rows] == [("rolling2", 1), ("rolling5", 1)]


def test_builder_is_idempotent():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-29", "2026-05-30"):
        _insert_valid_date(conn, signal_date=date_value)
        _insert_ticker_row(conn, signal_date=date_value)
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis")
    conn.commit()

    build_report_window_context_v2(conn, signal_date="2026-05-30", taxonomy_version="DC_TAXONOMY_FULL_V1", run_id="run-1", market="usa", horizons=("rolling2",))
    build_report_window_context_v2(conn, signal_date="2026-05-30", taxonomy_version="DC_TAXONOMY_FULL_V1", run_id="run-1", market="usa", horizons=("rolling2",))

    row_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling2"),
    ).fetchone()[0]
    assert row_count == 1


def test_builder_requires_existing_run():
    conn = _connect()
    _insert_valid_date(conn, signal_date="2026-05-29")
    _insert_valid_date(conn, signal_date="2026-05-30")
    _insert_ticker_row(conn, signal_date="2026-05-29")
    _insert_ticker_row(conn, signal_date="2026-05-30")
    conn.commit()

    with pytest.raises(ValueError, match="dc_report_run_v2 row not found"):
        build_report_window_context_v2(
            conn,
            signal_date="2026-05-30",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            run_id="missing-run",
            market="usa",
            horizons=("rolling2",),
        )


def test_builder_does_not_require_dashboard_tables():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-29", "2026-05-30"):
        _insert_valid_date(conn, signal_date=date_value)
        _insert_ticker_row(conn, signal_date=date_value)
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis")
    conn.commit()

    dashboard_tables = conn.execute(
        """
        SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'dc_dashboard_%'
        """
    ).fetchall()
    assert dashboard_tables == []

    summary = build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )
    assert summary["rolling2_rows_written"] == 1


def test_ecosystem_and_watchlist_behavior_is_explicit_and_defaulted():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-29", "2026-05-30"):
        _insert_valid_date(conn, signal_date=date_value)
        _insert_ticker_row(conn, signal_date=date_value, ticker="NVDA")
        _insert_ticker_row(conn, signal_date=date_value, ticker="AMD", breakout_signal=1)
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis")
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
        ecosystem_tickers={"NVDA"},
        watchlist_tickers={"AMD"},
    )

    rows = conn.execute(
        """
        SELECT ticker, in_datacenter_ecosystem, is_watchlist
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        ORDER BY ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling2"),
    ).fetchall()
    assert [(row["ticker"], row["in_datacenter_ecosystem"], row["is_watchlist"]) for row in rows] == [
        ("AMD", 0, 1),
        ("NVDA", 1, 0),
    ]

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )
    rows = conn.execute(
        """
        SELECT ticker, in_datacenter_ecosystem, is_watchlist
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        ORDER BY ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling2"),
    ).fetchall()
    assert [(row["ticker"], row["in_datacenter_ecosystem"], row["is_watchlist"]) for row in rows] == [
        ("AMD", 1, 0),
        ("NVDA", 1, 0),
    ]


def test_deferred_fields_remain_null():
    conn = _connect()
    _insert_run(conn)
    for date_value in ("2026-05-29", "2026-05-30"):
        _insert_valid_date(conn, signal_date=date_value)
        _insert_ticker_row(conn, signal_date=date_value)
    _insert_group_context_row(conn, horizon="rolling2", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, horizon="rolling2", group_type="subindustry", group_name="Semis")
    conn.commit()

    build_report_window_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        horizons=("rolling2",),
    )

    row = conn.execute(
        """
        SELECT ma_break_status, freshness_status, technical_relevance_status, technical_relevance_reason
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling2"),
    ).fetchone()
    assert row is not None
    assert row["ma_break_status"] is None
    assert row["freshness_status"] is None
    assert row["technical_relevance_status"] is None
    assert row["technical_relevance_reason"] is None
