import sqlite3

import pytest

from analysis.datacenter_indices.report_canonical_v2_daily_context_builder import (
    build_report_daily_context_v2,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)
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
            close REAL NULL,
            ema10 REAL NULL,
            ema20 REAL NULL,
            volume_vs_avg20 REAL NULL,
            price_data_status TEXT NULL,
            latest_bullish_relevance_class TEXT NULL,
            latest_bullish_relevance_reason TEXT NULL,
            latest_bearish_relevance_class TEXT NULL,
            latest_bearish_relevance_reason TEXT NULL,
            breakout_signal INTEGER NULL,
            pullback_signal INTEGER NULL,
            fast_ema10_pullback_signal INTEGER NULL,
            conservative_ema20_pullback_signal INTEGER NULL,
            exit_risk_signal INTEGER NULL,
            exit_risk_severity TEXT NULL,
            exit_reason TEXT NULL,
            bullish_candle_signal INTEGER NULL,
            bullish_divergence_signal INTEGER NULL,
            hidden_bullish_divergence_signal INTEGER NULL,
            bearish_candle_signal INTEGER NULL,
            bearish_divergence_signal INTEGER NULL,
            hidden_bearish_divergence_signal INTEGER NULL,
            return_5d REAL NULL,
            return_10d REAL NULL,
            return_20d REAL NULL,
            return_60d REAL NULL,
            distance_to_ema10_pct REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            ticker_trend_state TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_structure_age_trading_days INTEGER NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_age_trading_days INTEGER NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_age_trading_days INTEGER NULL,
            latest_reset_freshness TEXT NULL
        )
        """
    )
    return conn


def _insert_run(conn: sqlite3.Connection, run_id: str = "run-1") -> None:
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
    conn.commit()


def _insert_group_context_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    market: str = "usa",
    group_type: str,
    group_name: str,
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
    risk_status: str = "NO",
    run_id: str = "run-1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date,
            taxonomy_version,
            market,
            horizon,
            group_type,
            group_name,
            timing_state,
            overheat_risk_level,
            group_context_risk_status,
            group_context_readiness_status,
            group_current_status,
            group_window_status,
            group_status_change,
            window_start_date,
            window_end_date,
            valid_signal_dates,
            run_id,
            created_at_utc
        ) VALUES (?, ?, ?, 'daily', ?, ?, ?, ?, ?, 'OK', ?, NULL, NULL, NULL, ?, NULL, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            market,
            group_type,
            group_name,
            timing_state,
            overheat_risk_level,
            risk_status,
            timing_state,
            signal_date,
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    ticker: str = "NVDA",
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    market: str = "usa",
    primary_layer: str = "Infrastructure",
    primary_subindustry: str = "Semis",
    breakout_signal: int = 1,
    pullback_signal: int = 0,
    exit_risk_signal: int = 0,
    exit_risk_severity: str | None = None,
    price_data_status: str | None = "OK",
    close: float | None = 100.0,
    ema10: float | None = 98.5,
    ema20: float | None = 96.25,
    volume_vs_avg20: float | None = 1.8,
    latest_bullish_relevance_class: str | None = None,
    latest_bullish_relevance_reason: str | None = None,
    latest_bearish_relevance_class: str | None = None,
    latest_bearish_relevance_reason: str | None = None,
    bullish_candle_signal: int = 0,
    bullish_divergence_signal: int = 0,
    hidden_bullish_divergence_signal: int = 0,
    bearish_candle_signal: int = 0,
    bearish_divergence_signal: int = 0,
    hidden_bearish_divergence_signal: int = 0,
    distance_to_ema10_pct: float | None = 0.7,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date,
            taxonomy_version,
            signal_version,
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            close,
            ema10,
            ema20,
            volume_vs_avg20,
            price_data_status,
            latest_bullish_relevance_class,
            latest_bullish_relevance_reason,
            latest_bearish_relevance_class,
            latest_bearish_relevance_reason,
            breakout_signal,
            pullback_signal,
            fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal,
            exit_risk_signal,
            exit_risk_severity,
            exit_reason,
            bullish_candle_signal,
            bullish_divergence_signal,
            hidden_bullish_divergence_signal,
            bearish_candle_signal,
            bearish_divergence_signal,
            hidden_bearish_divergence_signal,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            distance_to_ema10_pct,
            distance_to_ema20_pct,
            distance_to_ema50_pct,
            ticker_trend_state,
            latest_structure_label,
            latest_structure_age_trading_days,
            latest_structure_freshness,
            latest_bos_event_type,
            latest_bos_age_trading_days,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_age_trading_days,
            latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            "DC_SWING_SIGNAL_V1",
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            close,
            ema10,
            ema20,
            volume_vs_avg20,
            price_data_status,
            latest_bullish_relevance_class,
            latest_bullish_relevance_reason,
            latest_bearish_relevance_class,
            latest_bearish_relevance_reason,
            breakout_signal,
            pullback_signal,
            0,
            1,
            exit_risk_signal,
            exit_risk_severity,
            "reason-token",
            bullish_candle_signal,
            bullish_divergence_signal,
            hidden_bullish_divergence_signal,
            bearish_candle_signal,
            bearish_divergence_signal,
            hidden_bearish_divergence_signal,
            2.5,
            5.0,
            8.5,
            15.0,
            distance_to_ema10_pct,
            1.1,
            4.4,
            "UP",
            "HL",
            6,
            "FRESH",
            "BOS_UP",
            2,
            "FRESH",
            "NONE",
            4,
            "STALE",
        ),
    )


def test_daily_ticker_context_rows_are_written():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis", risk_status="YES")
    _insert_ticker_row(conn)
    conn.commit()

    summary = build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT *
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["market"] == "usa"
    assert row["primary_layer"] == "Infrastructure"
    assert row["primary_subindustry"] == "Semis"
    assert row["price_data_status"] == "OK"
    assert row["close"] == 100.0
    assert row["ema10"] == 98.5
    assert row["ema20"] == 96.25
    assert row["volume_vs_avg20"] == 1.8
    assert row["breakout_signal"] == 1
    assert row["pullback_signal"] == 0
    assert row["conservative_ema20_pullback_signal"] == 1
    assert row["latest_exit_reason"] == "reason-token"
    assert row["latest_bullish_relevance_class"] is None
    assert row["latest_bearish_relevance_class"] is None
    assert row["bullish_candle_signal"] == 0
    assert row["bullish_divergence_signal"] == 0
    assert row["hidden_bullish_divergence_signal"] == 0
    assert row["bearish_candle_signal"] == 0
    assert row["bearish_divergence_signal"] == 0
    assert row["hidden_bearish_divergence_signal"] == 0
    assert row["return_5d"] == 2.5
    assert row["distance_to_ema10_pct"] == 0.7
    assert row["distance_to_ema20_pct"] == 1.1
    assert row["trend_state"] == "UP"
    assert row["latest_structure_label"] == "HL"
    assert row["latest_structure_age_trading_days"] == 6
    assert row["latest_bos_event_type"] == "BOS_UP"
    assert row["latest_bos_age_trading_days"] == 2
    assert row["latest_reset_reason"] == "NONE"
    assert row["latest_reset_age_trading_days"] == 4
    assert row["layer_timing_state"] == "BUY_ZONE"
    assert row["subindustry_timing_state"] == "BUY_ZONE"
    assert row["layer_context_risk_status"] == "NO"
    assert row["subindustry_context_risk_status"] == "YES"
    assert row["context_readiness_status"] == "OK"
    assert summary["source_ticker_rows_read"] == 1
    assert summary["daily_rows_written"] == 1
    assert summary["group_context_rows_read"] == 2
    assert summary["rows_missing_group_context"] == 0


def test_new_daily_trigger_input_fields_are_copied_from_source():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(
        conn,
        ticker="NVDA",
        price_data_status="MISSING_AS_OF_DATE",
        close=None,
        latest_bullish_relevance_class="RELEVANT",
        latest_bullish_relevance_reason="BULLISH_STACK",
        latest_bearish_relevance_class="WEAK_CONTEXT",
        latest_bearish_relevance_reason="MINOR_BEARISH_SIGNAL",
        bullish_candle_signal=1,
        bullish_divergence_signal=1,
        hidden_bullish_divergence_signal=1,
        bearish_candle_signal=1,
        bearish_divergence_signal=1,
        hidden_bearish_divergence_signal=1,
    )
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT
            price_data_status,
            close,
            latest_bullish_relevance_class,
            latest_bullish_relevance_reason,
            latest_bearish_relevance_class,
            latest_bearish_relevance_reason,
            bullish_candle_signal,
            bullish_divergence_signal,
            hidden_bullish_divergence_signal,
            bearish_candle_signal,
            bearish_divergence_signal,
            hidden_bearish_divergence_signal
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["price_data_status"] == "MISSING_AS_OF_DATE"
    assert row["close"] is None
    assert row["latest_bullish_relevance_class"] == "RELEVANT"
    assert row["latest_bullish_relevance_reason"] == "BULLISH_STACK"
    assert row["latest_bearish_relevance_class"] == "WEAK_CONTEXT"
    assert row["latest_bearish_relevance_reason"] == "MINOR_BEARISH_SIGNAL"
    assert row["bullish_candle_signal"] == 1
    assert row["bullish_divergence_signal"] == 1
    assert row["hidden_bullish_divergence_signal"] == 1
    assert row["bearish_candle_signal"] == 1
    assert row["bearish_divergence_signal"] == 1
    assert row["hidden_bearish_divergence_signal"] == 1


def test_missing_optional_daily_trigger_source_columns_default_deterministically():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)
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
            breakout_signal INTEGER NULL,
            pullback_signal INTEGER NULL,
            fast_ema10_pullback_signal INTEGER NULL,
            conservative_ema20_pullback_signal INTEGER NULL,
            exit_risk_signal INTEGER NULL,
            exit_risk_severity TEXT NULL,
            exit_reason TEXT NULL,
            return_5d REAL NULL,
            return_10d REAL NULL,
            return_20d REAL NULL,
            return_60d REAL NULL,
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
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date,
            taxonomy_version,
            signal_version,
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            breakout_signal,
            pullback_signal,
            fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal,
            exit_risk_signal,
            exit_risk_severity,
            exit_reason,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            distance_to_ema20_pct,
            distance_to_ema50_pct,
            ticker_trend_state,
            latest_structure_label,
            latest_structure_freshness,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            "usa",
            "NVDA",
            "Infrastructure",
            "Semis",
            1,
            0,
            0,
            1,
            0,
            None,
            "reason-token",
            2.5,
            5.0,
            8.5,
            15.0,
            1.1,
            4.4,
            "UP",
            "HL",
            "FRESH",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
        ),
    )
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT
            price_data_status,
            close,
            latest_bullish_relevance_class,
            latest_bearish_relevance_class,
            bullish_candle_signal,
            bullish_divergence_signal,
            hidden_bullish_divergence_signal,
            bearish_candle_signal,
            bearish_divergence_signal,
            hidden_bearish_divergence_signal,
            ema10,
            distance_to_ema10_pct
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["price_data_status"] is None
    assert row["close"] is None
    assert row["latest_bullish_relevance_class"] is None
    assert row["latest_bearish_relevance_class"] is None
    assert row["bullish_candle_signal"] == 0
    assert row["bullish_divergence_signal"] == 0
    assert row["hidden_bullish_divergence_signal"] == 0
    assert row["bearish_candle_signal"] == 0
    assert row["bearish_divergence_signal"] == 0
    assert row["hidden_bearish_divergence_signal"] == 0
    assert row["ema10"] is None
    assert row["distance_to_ema10_pct"] is None


def test_missing_group_context_readiness_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_ticker_row(conn)
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT context_readiness_status, layer_timing_state, subindustry_timing_state
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["context_readiness_status"] == "MISSING_GROUP_CONTEXT"
    assert row["layer_timing_state"] is None
    assert row["subindustry_timing_state"] is None


def test_explicit_ecosystem_membership_is_respected():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, ticker="NVDA")
    _insert_ticker_row(conn, ticker="AMD")
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        ecosystem_tickers={"NVDA"},
    )

    rows = conn.execute(
        """
        SELECT ticker, in_datacenter_ecosystem
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1"),
    ).fetchall()

    assert [(row["ticker"], row["in_datacenter_ecosystem"]) for row in rows] == [("AMD", 0), ("NVDA", 1)]


def test_default_ecosystem_membership_fallback_marks_source_rows_in_ecosystem():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, ticker="NVDA")
    _insert_ticker_row(conn, ticker="AMD")
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT ticker, in_datacenter_ecosystem
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1"),
    ).fetchall()

    assert [(row["ticker"], row["in_datacenter_ecosystem"]) for row in rows] == [("AMD", 1), ("NVDA", 1)]


def test_default_watchlist_behavior_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, ticker="NVDA")
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        watchlist_tickers=None,
    )

    row = conn.execute(
        """
        SELECT is_watchlist
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["is_watchlist"] == 0


def test_missing_layer_context_readiness_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn)
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT context_readiness_status, layer_timing_state, subindustry_timing_state
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["context_readiness_status"] == "MISSING_LAYER_CONTEXT"
    assert row["layer_timing_state"] is None
    assert row["subindustry_timing_state"] == "BUY_ZONE"


def test_missing_subindustry_context_readiness_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_ticker_row(conn)
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT context_readiness_status, layer_timing_state, subindustry_timing_state
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["context_readiness_status"] == "MISSING_SUBINDUSTRY_CONTEXT"
    assert row["layer_timing_state"] == "BUY_ZONE"
    assert row["subindustry_timing_state"] is None


def test_market_safe_delete_behavior_preserves_unrelated_market_rows():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, market="usa", group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, market="usa", group_type="subindustry", group_name="Semis")
    _insert_group_context_row(conn, market="omxh", group_type="layer", group_name="NordicInfra")
    _insert_group_context_row(conn, market="omxh", group_type="subindustry", group_name="NordicSemis")
    _insert_ticker_row(conn, ticker="NVDA", market="usa", primary_layer="Infrastructure", primary_subindustry="Semis")
    _insert_ticker_row(conn, ticker="NOKIA", market="omxh", primary_layer="NordicInfra", primary_subindustry="NordicSemis")
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )
    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="omxh",
    )
    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT market, ticker
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY market ASC, ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1"),
    ).fetchall()

    assert [(row["market"], row["ticker"]) for row in rows] == [("omxh", "NOKIA"), ("usa", "NVDA")]


def test_builder_is_idempotent():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn)
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )
    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()[0]
    assert row_count == 1


def test_builder_requires_existing_run():
    conn = _connect()
    _insert_ticker_row(conn)
    conn.commit()

    with pytest.raises(ValueError, match="dc_report_run_v2 row not found"):
        build_report_daily_context_v2(
            conn,
            signal_date="2026-05-30",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            run_id="missing-run",
            market="usa",
        )


def test_builder_does_not_require_dashboard_tables():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn)
    conn.commit()

    dashboard_tables = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name LIKE 'dc_dashboard_%'
        """
    ).fetchall()
    assert dashboard_tables == []

    summary = build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    assert summary["daily_rows_written"] == 1


def test_technical_relevance_remains_null():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn)
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT technical_relevance_status, technical_relevance_reason, ma_break_status, freshness_status
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchone()

    assert row is not None
    assert row["technical_relevance_status"] is None
    assert row["technical_relevance_reason"] is None
    assert row["ma_break_status"] is None
    assert row["freshness_status"] is None


def test_watchlist_input_behavior_is_deterministic():
    conn = _connect()
    _insert_run(conn)
    _insert_group_context_row(conn, group_type="layer", group_name="Infrastructure")
    _insert_group_context_row(conn, group_type="subindustry", group_name="Semis")
    _insert_ticker_row(conn, ticker="NVDA")
    _insert_ticker_row(conn, ticker="AMD", breakout_signal=0, pullback_signal=1)
    conn.commit()

    build_report_daily_context_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
        watchlist_tickers={"NVDA"},
    )

    rows = conn.execute(
        """
        SELECT ticker, is_watchlist, current_watchlist_status
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1"),
    ).fetchall()

    assert [(row["ticker"], row["is_watchlist"]) for row in rows] == [("AMD", 0), ("NVDA", 1)]
    assert [row["current_watchlist_status"] for row in rows] == ["PULLBACK_CANDIDATE", "BREAKOUT_CANDIDATE"]
