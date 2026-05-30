import sqlite3

import pytest

from analysis.datacenter_indices.report_canonical_v2_orchestrator import (
    run_report_canonical_v2,
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
            group_name TEXT NOT NULL,
            parent_group_type TEXT NULL,
            parent_group_name TEXT NULL,
            timing_state TEXT NULL,
            overheat_risk_level TEXT NULL,
            return_2d REAL NULL,
            return_5d REAL NULL,
            return_30d REAL NULL,
            ema20_breadth_delta_5d REAL NULL,
            ma10_breadth_delta_5d REAL NULL,
            trend_breadth REAL NULL,
            weakness_breadth REAL NULL,
            strength_breadth REAL NULL,
            data_quality_status TEXT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            calc_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            synthetic_close REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            trend_classification TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_freshness TEXT NULL
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
            close REAL NULL,
            price_data_status TEXT NULL,
            latest_bullish_relevance_class TEXT NULL,
            latest_bearish_relevance_class TEXT NULL,
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


def _insert_group_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    group_type: str,
    group_name: str,
    parent_group_type: str | None,
    parent_group_name: str | None,
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date,
            taxonomy_version,
            signal_version,
            market,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            return_2d,
            return_5d,
            return_30d,
            ema20_breadth_delta_5d,
            ma10_breadth_delta_5d,
            trend_breadth,
            weakness_breadth,
            strength_breadth,
            data_quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            market,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            1.0,
            2.0,
            3.0,
            0.2,
            0.1,
            0.8,
            0.1,
            0.7,
            "OK",
        ),
    )


def _insert_synthetic_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    group_type: str,
    group_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date,
            taxonomy_version,
            calc_version,
            market,
            group_type,
            group_name,
            synthetic_close,
            distance_to_ema20_pct,
            distance_to_ema50_pct,
            trend_classification,
            latest_structure_label,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_OHLC_V1",
            market,
            group_type,
            group_name,
            150.0,
            1.2,
            3.4,
            "UP",
            "HL",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
        ),
    )


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    ticker: str = "NVDA",
    primary_layer: str = "Infrastructure",
    primary_subindustry: str = "Semis",
    breakout_signal: int = 0,
    pullback_signal: int = 0,
    exit_risk_signal: int = 0,
    exit_risk_severity: str | None = None,
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
            price_data_status,
            latest_bullish_relevance_class,
            latest_bearish_relevance_class,
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
            distance_to_ema20_pct,
            distance_to_ema50_pct,
            ticker_trend_state,
            latest_structure_label,
            latest_structure_freshness,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            100.0,
            "OK",
            "RELEVANT",
            None,
            breakout_signal,
            pullback_signal,
            0,
            0,
            exit_risk_signal,
            exit_risk_severity,
            "reason-token",
            1 if breakout_signal else 0,
            0,
            0,
            0,
            0,
            0,
            2.0,
            4.0,
            8.0,
            12.0,
            1.5,
            3.0,
            "UP",
            "HL",
            "FRESH",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
        ),
    )


def _seed_source_rows(
    conn: sqlite3.Connection,
    *,
    market: str = "usa",
    ticker: str = "NVDA",
    layer_name: str = "Infrastructure",
    subindustry_name: str = "Semis",
) -> None:
    for signal_date in ("2026-05-29", "2026-05-30"):
        _insert_group_row(
            conn,
            signal_date=signal_date,
            market=market,
            group_type="layer",
            group_name=layer_name,
            parent_group_type="ecosystem",
            parent_group_name="Datacenter",
        )
        _insert_group_row(
            conn,
            signal_date=signal_date,
            market=market,
            group_type="subindustry",
            group_name=subindustry_name,
            parent_group_type="layer",
            parent_group_name=layer_name,
        )
        _insert_synthetic_row(
            conn,
            signal_date=signal_date,
            market=market,
            group_type="layer",
            group_name=layer_name,
        )
        _insert_synthetic_row(
            conn,
            signal_date=signal_date,
            market=market,
            group_type="subindustry",
            group_name=subindustry_name,
        )

    _insert_ticker_row(
        conn,
        signal_date="2026-05-29",
        market=market,
        ticker=ticker,
        primary_layer=layer_name,
        primary_subindustry=subindustry_name,
        pullback_signal=1,
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-30",
        market=market,
        ticker=ticker,
        primary_layer=layer_name,
        primary_subindustry=subindustry_name,
        breakout_signal=1,
    )
    conn.commit()


def test_full_canonical_v2_run_writes_all_expected_table_families():
    conn = _connect()
    _seed_source_rows(conn)

    summary = run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    run_row = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_run_v2").fetchone()
    group_row = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_group_v2").fetchone()
    daily_row = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_daily_v2").fetchone()
    window_row = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_window_v2").fetchone()
    classification_rows = conn.execute(
        """
        SELECT classification_type
        FROM dc_report_classification_v2
        ORDER BY classification_type
        """
    ).fetchall()

    assert run_row["row_count"] == 1
    assert group_row["row_count"] > 0
    assert daily_row["row_count"] > 0
    assert window_row["row_count"] > 0
    assert [row["classification_type"] for row in classification_rows] == [
        "daily_trigger",
        "rolling2_sell_pressure",
        "rolling30_buy",
        "rolling30_exit",
        "rolling5_pullback",
    ]
    assert summary["status"] == "OK"
    assert summary["total_context_rows_written"] > 0
    assert summary["total_classification_rows_written"] == 5


def test_run_row_persists_exact_contract_fields():
    conn = _connect()
    _seed_source_rows(conn)

    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="contract-run",
        market="usa",
        calculation_version="REPORT_CANONICAL_V2_CONTRACT",
        source_versions_json='{"signals":"DC_SWING_SIGNAL_V1"}',
        created_at_utc="2026-05-30T12:34:56Z",
        notes="contract-check",
    )

    row = conn.execute(
        """
        SELECT run_id, signal_date, taxonomy_version, market, calculation_version,
               source_versions_json, created_at_utc, status, warning_count,
               error_count, notes
        FROM dc_report_run_v2
        WHERE run_id = ?
        """,
        ("contract-run",),
    ).fetchone()

    assert row is not None
    assert dict(row) == {
        "run_id": "contract-run",
        "signal_date": "2026-05-30",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "market": "usa",
        "calculation_version": "REPORT_CANONICAL_V2_CONTRACT",
        "source_versions_json": '{"signals":"DC_SWING_SIGNAL_V1"}',
        "created_at_utc": "2026-05-30T12:34:56Z",
        "status": "OK",
        "warning_count": 0,
        "error_count": 0,
        "notes": "contract-check",
    }


def test_summary_shape_includes_steps_subdict_for_full_run():
    conn = _connect()
    _seed_source_rows(conn)

    summary = run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="summary-run",
        market="usa",
    )

    assert summary["run_id"] == "summary-run"
    assert summary["signal_date"] == "2026-05-30"
    assert summary["taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    assert summary["market"] == "usa"
    assert summary["status"] == "OK"
    assert summary["warning_count"] == 0
    assert summary["error_count"] == 0
    assert "steps" in summary
    assert "total_context_rows_written" in summary
    assert "total_classification_rows_written" in summary

    assert set(summary["steps"]) == {
        "group_context",
        "daily_context",
        "window_context",
        "daily_classification",
        "rolling2_classification",
        "rolling5_classification",
        "rolling30_classification",
    }


def test_summary_totals_match_step_totals():
    conn = _connect()
    _seed_source_rows(conn)

    summary = run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="totals-run",
        market="usa",
    )

    steps = summary["steps"]
    context_total = (
        steps["group_context"]["total_rows_written"]
        + steps["daily_context"]["total_rows_written"]
        + steps["window_context"]["total_rows_written"]
    )
    classification_total = (
        steps["daily_classification"]["total_rows_written"]
        + steps["rolling2_classification"]["total_rows_written"]
        + steps["rolling5_classification"]["total_rows_written"]
        + steps["rolling30_classification"]["total_rows_written"]
    )

    assert summary["total_context_rows_written"] == context_total
    assert summary["total_classification_rows_written"] == classification_total


def test_daily_only_run_does_not_create_rolling_rows():
    conn = _connect()
    _seed_source_rows(conn)

    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="daily-run",
        market="usa",
        horizons=("daily",),
    )

    daily_context = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_daily_v2").fetchone()
    window_context = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_window_v2").fetchone()
    daily_classifications = conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM dc_report_classification_v2
        WHERE classification_type = 'daily_trigger'
        """
    ).fetchone()
    rolling_classifications = conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM dc_report_classification_v2
        WHERE classification_type IN (
            'rolling2_sell_pressure', 'rolling5_pullback', 'rolling30_buy', 'rolling30_exit'
        )
        """
    ).fetchone()

    assert daily_context["row_count"] == 1
    assert window_context["row_count"] == 0
    assert daily_classifications["row_count"] == 1
    assert rolling_classifications["row_count"] == 0


def test_rolling_only_run_does_not_create_daily_rows():
    conn = _connect()
    _seed_source_rows(conn)

    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="rolling-run",
        market="usa",
        horizons=("rolling2", "rolling5", "rolling30"),
    )

    daily_context = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_daily_v2").fetchone()
    daily_classifications = conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM dc_report_classification_v2
        WHERE classification_type = 'daily_trigger'
        """
    ).fetchone()
    window_context = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_window_v2").fetchone()
    rolling_classifications = conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM dc_report_classification_v2
        WHERE classification_type IN (
            'rolling2_sell_pressure', 'rolling5_pullback', 'rolling30_buy', 'rolling30_exit'
        )
        """
    ).fetchone()

    assert daily_context["row_count"] == 0
    assert daily_classifications["row_count"] == 0
    assert window_context["row_count"] > 0
    assert rolling_classifications["row_count"] == 4


def test_selected_horizon_behavior_only_writes_requested_rolling2_rows():
    conn = _connect()
    _seed_source_rows(conn)

    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="rolling2-run",
        market="usa",
        horizons=("rolling2",),
    )

    classification_rows = conn.execute(
        """
        SELECT classification_type
        FROM dc_report_classification_v2
        ORDER BY classification_type
        """
    ).fetchall()

    assert [row["classification_type"] for row in classification_rows] == [
        "rolling2_sell_pressure",
    ]


def test_idempotency_for_same_run_date_taxonomy_and_market():
    conn = _connect()
    _seed_source_rows(conn)

    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )
    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    run_rows = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_run_v2 WHERE run_id = ?", ("run-1",)).fetchone()
    group_rows = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_group_v2 WHERE market = ?", ("usa",)).fetchone()
    daily_rows = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_daily_v2 WHERE market = ?", ("usa",)).fetchone()
    window_rows = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_context_window_v2 WHERE market = ?", ("usa",)).fetchone()
    classification_rows = conn.execute("SELECT COUNT(*) AS row_count FROM dc_report_classification_v2 WHERE market = ?", ("usa",)).fetchone()

    assert run_rows["row_count"] == 1
    assert group_rows["row_count"] == 8
    assert daily_rows["row_count"] == 1
    assert window_rows["row_count"] == 3
    assert classification_rows["row_count"] == 5


def test_market_safe_behavior_preserves_unrelated_market_rows():
    conn = _connect()
    _seed_source_rows(conn, market="usa", ticker="NVDA")
    _seed_source_rows(
        conn,
        market="omxh",
        ticker="NOKIA",
        layer_name="NordicInfra",
        subindustry_name="Telecom",
    )

    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="usa-run",
        market="usa",
    )
    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="omxh-run",
        market="omxh",
    )
    run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="usa-run",
        market="usa",
    )

    market_counts = conn.execute(
        """
        SELECT market, COUNT(*) AS row_count
        FROM dc_report_classification_v2
        GROUP BY market
        ORDER BY market
        """
    ).fetchall()

    assert [(row["market"], row["row_count"]) for row in market_counts] == [
        ("omxh", 5),
        ("usa", 5),
    ]


def test_unsupported_horizon_is_rejected():
    conn = _connect()

    with pytest.raises(ValueError, match="Unsupported horizons"):
        run_report_canonical_v2(
            conn,
            signal_date="2026-05-30",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            run_id="bad-run",
            horizons=("daily", "monthly"),
        )


def test_no_dashboard_tables_are_required():
    conn = _connect()
    _seed_source_rows(conn)

    summary = run_report_canonical_v2(
        conn,
        signal_date="2026-05-30",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        run_id="run-1",
        market="usa",
    )

    assert summary["status"] == "OK"
    assert summary["total_classification_rows_written"] == 5
