import sqlite3

import pytest

from analysis.datacenter_indices.report_canonical_v2_daily_classification_writer import (
    write_report_daily_trigger_classification_v2,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_report_canonical_v2_migration(conn)
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


def _insert_daily_context_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    market: str = "usa",
    primary_layer: str = "Infrastructure",
    primary_subindustry: str = "Semis",
    current_watchlist_status: str = "NEUTRAL_MONITOR",
    breakout_signal: int = 0,
    pullback_signal: int = 0,
    exit_risk_signal: int = 0,
    exit_risk_severity: str | None = None,
    latest_exit_reason: str | None = None,
    distance_to_ema20_pct: float | None = 0.05,
    trend_state: str | None = "UP",
    latest_structure_label: str | None = "HL",
    latest_bos_event_type: str | None = None,
    latest_bos_freshness: str | None = None,
    latest_reset_reason: str | None = None,
    latest_reset_freshness: str | None = None,
    run_id: str = "run-1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_daily_v2 (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            in_datacenter_ecosystem,
            is_watchlist,
            current_watchlist_status,
            breakout_signal,
            pullback_signal,
            fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal,
            exit_risk_signal,
            exit_risk_severity,
            latest_exit_reason,
            distance_to_ema20_pct,
            trend_state,
            latest_structure_label,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
            context_readiness_status,
            run_id,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            1,
            0,
            current_watchlist_status,
            breakout_signal,
            pullback_signal,
            0,
            0,
            exit_risk_signal,
            exit_risk_severity,
            latest_exit_reason,
            distance_to_ema20_pct,
            trend_state,
            latest_structure_label,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
            "OK",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def _insert_classification_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    market: str,
    horizon: str,
    classification_type: str,
    classification_state: str = "EXISTING",
    run_id: str = "run-1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            horizon,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            classification_status,
            classification_version,
            run_id,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-30",
            "DC_TAXONOMY_FULL_V1",
            market,
            ticker,
            horizon,
            classification_type,
            classification_state,
            None,
            None,
            None,
            None,
            "OK",
            "EXISTING_V1",
            run_id,
            "2026-05-30T00:00:00Z",
        ),
    )


def test_daily_trigger_classification_rows_are_written():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", breakout_signal=1, current_watchlist_status="BREAKOUT_CANDIDATE")
    conn.commit()

    summary = write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT *
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ? AND classification_type = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "daily", "daily_trigger"),
    ).fetchone()

    assert row is not None
    assert row["horizon"] == "daily"
    assert row["classification_type"] == "daily_trigger"
    assert row["classification_state"] == "BUY_WATCH"
    assert row["classification_status"] == "OK"
    assert row["classification_version"] == "REPORT_DAILY_TRIGGER_CLASSIFIER_V2_1"
    assert row["run_id"] == "run-1"
    assert summary == {
        "daily_context_rows_read": 1,
        "classification_rows_written": 1,
        "classification_rows_skipped": 0,
        "total_rows_written": 1,
    }


def test_classification_state_behavior_for_key_daily_cases():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", breakout_signal=1, current_watchlist_status="BREAKOUT_CANDIDATE")
    _insert_daily_context_row(conn, ticker="AMD", pullback_signal=1, current_watchlist_status="PULLBACK_CANDIDATE")
    _insert_daily_context_row(
        conn,
        ticker="TSLA",
        exit_risk_signal=1,
        exit_risk_severity="MEDIUM",
        current_watchlist_status="MEDIUM_EXIT_RISK",
    )
    _insert_daily_context_row(conn, ticker="CASH", current_watchlist_status="NEUTRAL_MONITOR")
    conn.commit()

    write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT ticker, classification_state, primary_reason, blocking_reason, next_action
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ? AND classification_type = ?
        ORDER BY ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "daily", "daily_trigger"),
    ).fetchall()

    assert [(row["ticker"], row["classification_state"], row["primary_reason"], row["blocking_reason"], row["next_action"]) for row in rows] == [
        ("AMD", "BUY_WATCH", "BULLISH_SETUP_NEEDS_CONFIRMATION", None, "MONITOR_FOR_DAILY_CONFIRMATION"),
        ("CASH", "NO_TRIGGER", "NO_MEANINGFUL_DAILY_TRIGGER", None, "NONE"),
        ("NVDA", "BUY_WATCH", "BULLISH_SETUP_NEEDS_CONFIRMATION", None, "MONITOR_FOR_DAILY_CONFIRMATION"),
        ("TSLA", "SELL_TRIGGER", "DAILY_SELL_TRIGGER", "EXIT_RISK_SIGNAL_MEDIUM_OR_HIGH", "REVIEW_SELL_OR_TIGHTEN_STOP"),
    ]


def test_market_safe_delete_behavior_preserves_unrelated_market_rows():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", market="usa", breakout_signal=1)
    conn.commit()

    write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )
    _insert_classification_row(
        conn,
        ticker="NOKIA",
        market="omxh",
        horizon="daily",
        classification_type="daily_trigger",
    )
    conn.commit()

    write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT market, ticker, classification_type
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ?
        ORDER BY market ASC, ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "daily"),
    ).fetchall()

    assert [(row["market"], row["ticker"], row["classification_type"]) for row in rows] == [
        ("omxh", "NOKIA", "daily_trigger"),
        ("usa", "NVDA", "daily_trigger"),
    ]


def test_unrelated_classification_preservation():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", breakout_signal=1)
    _insert_classification_row(
        conn,
        ticker="NVDA",
        market="usa",
        horizon="rolling2",
        classification_type="rolling2_sell_pressure",
    )
    conn.commit()

    write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT horizon, classification_type, classification_state
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
        ORDER BY horizon ASC, classification_type ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA"),
    ).fetchall()

    assert [(row["horizon"], row["classification_type"], row["classification_state"]) for row in rows] == [
        ("daily", "daily_trigger", "BUY_WATCH"),
        ("rolling2", "rolling2_sell_pressure", "EXISTING"),
    ]


def test_writer_is_idempotent():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", breakout_signal=1)
    conn.commit()

    write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )
    write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ? AND classification_type = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "daily", "daily_trigger"),
    ).fetchone()[0]
    assert row_count == 1


def test_writer_requires_existing_run():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", breakout_signal=1)
    conn.commit()

    with pytest.raises(ValueError, match="dc_report_run_v2 row not found"):
        write_report_daily_trigger_classification_v2(
            conn,
            signal_date="2026-05-30",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            run_id="missing-run",
            market="usa",
        )


def test_writer_does_not_require_dashboard_tables():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", breakout_signal=1)
    conn.commit()

    dashboard_tables = conn.execute(
        """
        SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'dc_dashboard_%'
        """
    ).fetchall()
    assert dashboard_tables == []

    summary = write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )
    assert summary["classification_rows_written"] == 1


def test_writer_reads_only_canonical_daily_context():
    conn = _connect()
    _insert_run(conn)
    _insert_daily_context_row(conn, ticker="NVDA", breakout_signal=1)
    conn.commit()

    source_tables = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name IN ('dc_ticker_swing_signal_daily', 'dc_group_swing_signal_daily')
        ORDER BY name ASC
        """
    ).fetchall()
    assert source_tables == []

    row_count_before = conn.execute(
        """
        SELECT COUNT(*) FROM dc_report_classification_v2
        """
    ).fetchone()[0]
    assert row_count_before == 0

    summary = write_report_daily_trigger_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT classification_state
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ? AND classification_type = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "daily", "daily_trigger"),
    ).fetchone()
    assert row is not None
    assert row["classification_state"] == "BUY_WATCH"
    assert summary["daily_context_rows_read"] == 1
