import sqlite3

import pytest

from analysis.datacenter_indices.report_canonical_v2_rolling5_classification_writer import (
    write_report_rolling5_pullback_classification_v2,
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


def _insert_window_context_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    horizon: str = "rolling5",
    signal_date: str = "2026-05-30",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    market: str = "usa",
    current_watchlist_status: str = "NEUTRAL_MONITOR",
    window_watchlist_status: str = "NEUTRAL_MONITOR",
    pullback_days: int = 0,
    fast_ema10_pullback_days: int = 0,
    conservative_ema20_pullback_days: int = 0,
    exit_risk_days: int = 0,
    latest_bos_event_type: str | None = None,
    latest_bos_freshness: str | None = None,
    latest_reset_reason: str | None = None,
    latest_reset_freshness: str | None = None,
    price_data_status: str | None = "OK",
    exit_risk_severity: str | None = None,
    latest_bearish_relevance_class: str | None = None,
    trend_state: str | None = "UP",
    all_price_rows_missing: int = 0,
    run_id: str = "run-1",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_context_window_v2 (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            horizon,
            window_start_date,
            window_end_date,
            valid_signal_dates,
            incomplete_window,
            primary_layer,
            primary_subindustry,
            in_datacenter_ecosystem,
            is_watchlist,
            current_watchlist_status,
            window_watchlist_status,
            breakout_days,
            pullback_days,
            fast_ema10_pullback_days,
            conservative_ema20_pullback_days,
            exit_risk_days,
            high_exit_risk_days,
            medium_exit_risk_days,
            first_signal_date,
            last_signal_date,
            latest_exit_reason,
            trend_state,
            latest_structure_label,
            latest_structure_freshness,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
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
            severe_exit_risk_flag,
            context_readiness_status,
            run_id,
            created_at_utc,
            price_data_status,
            exit_risk_severity,
            latest_bearish_relevance_class,
            distance_to_ema20_pct,
            all_price_rows_missing
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            horizon,
            "2026-05-26",
            signal_date,
            5,
            0,
            "Infrastructure",
            "Semis",
            1,
            0,
            current_watchlist_status,
            window_watchlist_status,
            0,
            pullback_days,
            fast_ema10_pullback_days,
            conservative_ema20_pullback_days,
            exit_risk_days,
            0,
            0,
            "2026-05-26",
            signal_date,
            None,
            trend_state,
            "HL",
            "FRESH",
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
            0,
            0,
            0,
            1 if latest_reset_reason == "DOUBLE_BOS_DOWN" else 0,
            1 if latest_reset_reason == "DOUBLE_BOS_UP" else 0,
            1 if latest_bos_event_type is not None and latest_bos_freshness in {"FRESH", "RECENT", "CURRENT"} else 0,
            1 if latest_reset_reason not in {None, "", "NULL"} and latest_reset_freshness in {"FRESH", "RECENT", "CURRENT"} else 0,
            0,
            0,
            0,
            1 if exit_risk_severity in {"CRITICAL", "EXTREME"} else 0,
            "OK",
            run_id,
            "2026-05-30T00:00:00Z",
            price_data_status,
            exit_risk_severity,
            latest_bearish_relevance_class,
            0.05,
            all_price_rows_missing,
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


def test_rolling5_pullback_classification_rows_are_written():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(
        conn,
        ticker="NVDA",
        pullback_days=1,
        conservative_ema20_pullback_days=1,
        current_watchlist_status="PULLBACK_CANDIDATE",
        window_watchlist_status="PULLBACK_CANDIDATE",
        trend_state="UP",
    )
    conn.commit()

    summary = write_report_rolling5_pullback_classification_v2(
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
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling5", "rolling5_pullback"),
    ).fetchone()

    assert row is not None
    assert row["horizon"] == "rolling5"
    assert row["classification_type"] == "rolling5_pullback"
    assert row["classification_state"] == "PULLBACK_CANDIDATE"
    assert row["classification_status"] == "OK"
    assert row["classification_version"] == "REPORT_ROLLING5_PULLBACK_CLASSIFIER_V2_1"
    assert row["run_id"] == "run-1"
    assert row["risk_reason"] is None
    assert summary == {
        "window_context_rows_read": 1,
        "classification_rows_written": 1,
        "classification_rows_skipped": 0,
        "total_rows_written": 1,
    }


def test_classification_state_behavior_for_key_rolling5_cases():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(
        conn,
        ticker="NVDA",
        pullback_days=1,
        conservative_ema20_pullback_days=1,
        current_watchlist_status="PULLBACK_CANDIDATE",
        window_watchlist_status="PULLBACK_CANDIDATE",
        trend_state="UP",
    )
    _insert_window_context_row(
        conn,
        ticker="AMD",
        pullback_days=1,
        latest_bearish_relevance_class="RELEVANT",
    )
    _insert_window_context_row(conn, ticker="META")
    _insert_window_context_row(
        conn,
        ticker="CASH",
        price_data_status="MISSING_AS_OF_DATE",
        all_price_rows_missing=1,
    )
    conn.commit()

    write_report_rolling5_pullback_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT ticker, classification_state
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ? AND classification_type = ?
        ORDER BY ticker ASC
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling5", "rolling5_pullback"),
    ).fetchall()

    assert [(row["ticker"], row["classification_state"]) for row in rows] == [
        ("AMD", "FAILED_PULLBACK"),
        ("CASH", "INSUFFICIENT_DATA"),
        ("META", "NO_PULLBACK"),
        ("NVDA", "PULLBACK_CANDIDATE"),
    ]


def test_reason_action_parity_for_blocked_pullback_case():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(
        conn,
        ticker="NVDA",
        pullback_days=1,
        latest_bearish_relevance_class="RELEVANT",
    )
    conn.commit()

    write_report_rolling5_pullback_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT classification_state, primary_reason, blocking_reason, risk_reason, next_action
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ? AND horizon = ? AND classification_type = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "NVDA", "rolling5", "rolling5_pullback"),
    ).fetchone()

    assert row is not None
    assert row["classification_state"] == "FAILED_PULLBACK"
    assert row["primary_reason"] == "PULLBACK_SETUP_BLOCKED"
    assert row["blocking_reason"] == "relevant_bearish_context"
    assert row["risk_reason"] is None
    assert row["next_action"] == "REMOVE_FROM_PULLBACK_LIST"


def test_market_safe_delete_behavior_preserves_unrelated_market_rows():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(conn, ticker="NVDA", market="usa", pullback_days=1)
    conn.commit()

    write_report_rolling5_pullback_classification_v2(
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
        horizon="rolling5",
        classification_type="rolling5_pullback",
    )
    conn.commit()

    write_report_rolling5_pullback_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT market, ticker
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ? AND classification_type = ?
        ORDER BY market, ticker
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling5", "rolling5_pullback"),
    ).fetchall()

    assert [(row["market"], row["ticker"]) for row in rows] == [("omxh", "NOKIA"), ("usa", "NVDA")]


def test_unrelated_classification_rows_are_preserved():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(conn, ticker="NVDA", pullback_days=1)
    _insert_classification_row(
        conn,
        ticker="NVDA",
        market="usa",
        horizon="rolling2",
        classification_type="rolling2_sell_pressure",
    )
    conn.commit()

    write_report_rolling5_pullback_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    rows = conn.execute(
        """
        SELECT horizon, classification_type
        FROM dc_report_classification_v2
        WHERE ticker = ?
        ORDER BY horizon, classification_type
        """,
        ("NVDA",),
    ).fetchall()

    assert [(row["horizon"], row["classification_type"]) for row in rows] == [
        ("rolling2", "rolling2_sell_pressure"),
        ("rolling5", "rolling5_pullback"),
    ]


def test_writer_is_idempotent():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(conn, ticker="NVDA", pullback_days=1)
    conn.commit()

    write_report_rolling5_pullback_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )
    write_report_rolling5_pullback_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND horizon = ? AND classification_type = ?
        """,
        ("2026-05-30", "DC_TAXONOMY_FULL_V1", "rolling5", "rolling5_pullback"),
    ).fetchone()

    assert row["row_count"] == 1


def test_missing_run_is_rejected():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(conn, ticker="NVDA", run_id="run-1", pullback_days=1)
    conn.commit()

    with pytest.raises(ValueError, match="dc_report_run_v2 row not found"):
        write_report_rolling5_pullback_classification_v2(
            conn,
            signal_date="2026-05-30",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            run_id="missing-run",
            market="usa",
        )


def test_no_dashboard_tables_are_required_and_writer_reads_only_canonical_window_context():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(conn, ticker="NVDA", pullback_days=1)
    conn.commit()

    write_report_rolling5_pullback_classification_v2(
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
        WHERE ticker = ? AND horizon = ? AND classification_type = ?
        """,
        ("NVDA", "rolling5", "rolling5_pullback"),
    ).fetchone()

    assert row is not None
    assert row["classification_state"] == "PULLBACK_CANDIDATE"


def test_non_rolling5_window_context_rows_are_ignored():
    conn = _connect()
    _insert_run(conn)
    _insert_window_context_row(conn, ticker="NVDA", horizon="rolling2", pullback_days=1)
    conn.commit()

    summary = write_report_rolling5_pullback_classification_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    row = conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM dc_report_classification_v2
        WHERE horizon = ? AND classification_type = ?
        """,
        ("rolling5", "rolling5_pullback"),
    ).fetchone()

    assert row["row_count"] == 0
    assert summary == {
        "window_context_rows_read": 0,
        "classification_rows_written": 0,
        "classification_rows_skipped": 0,
        "total_rows_written": 0,
    }
