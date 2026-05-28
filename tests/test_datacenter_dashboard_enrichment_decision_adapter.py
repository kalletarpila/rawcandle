from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    build_decisions_from_ticker_enrichment_rows,
    load_ticker_enrichment_rows,
)


def test_adapter_builds_dashboard_rows_from_minimal_enrichment_row():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "NEUTRAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    assert len(rows) == 1
    assert rows[0].ticker == "NVDA"
    assert rows[0].horizon == "daily"
    assert rows[0].raw_status == "NEUTRAL"
    assert rows[0].trend_state == "UP"
    assert rows[0].raw_fields["current_status"] == "NEUTRAL"
    assert rows[0].raw_fields["horizon_source"] == "current_status"
    assert rows[0].raw_fields["latest_bos_event_type"] == "BOS_UP"


def test_adapter_expands_horizon_specific_status_fields():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "daily_status": "NEUTRAL_MONITOR",
                "rolling_2d_status": "NO_EMERGENCY",
                "rolling_5d_status": "PULLBACK_CANDIDATE",
                "rolling_30d_status": "BUY_ZONE",
            }
        ]
    )

    assert len(rows) == 4
    assert any(
        row.horizon == "daily"
        and row.raw_status == "NEUTRAL_MONITOR"
        and row.raw_fields["horizon_source"] == "daily_status"
        for row in rows
    )
    assert any(
        row.horizon == "rolling 2d"
        and row.raw_status == "NO_EMERGENCY"
        and row.raw_fields["horizon_source"] == "rolling_2d_status"
        for row in rows
    )
    assert any(
        row.horizon == "rolling 5d"
        and row.raw_status == "PULLBACK_CANDIDATE"
        and row.raw_fields["horizon_source"] == "rolling_5d_status"
        for row in rows
    )
    assert any(
        row.horizon == "rolling 30d"
        and row.raw_status == "BUY_ZONE"
        and row.raw_fields["horizon_source"] == "rolling_30d_status"
        for row in rows
    )


def test_adapter_builds_risk_horizon_rows_with_expected_statuses():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "HIGH_EXIT_RISK",
                "rolling_2d_status": "EMERGENCY_SELL_PRESSURE",
                "rolling_5d_status": "FAILED_PULLBACK",
                "rolling_30d_status": "AVOID",
            }
        ]
    )

    assert len(rows) == 4
    assert any(row.horizon == "daily" and row.raw_status == "HIGH_EXIT_RISK" for row in rows)
    assert any(
        row.horizon == "rolling 2d" and row.raw_status == "EMERGENCY_SELL_PRESSURE"
        for row in rows
    )
    assert any(row.horizon == "rolling 5d" and row.raw_status == "FAILED_PULLBACK" for row in rows)
    assert any(row.horizon == "rolling 30d" and row.raw_status == "AVOID" for row in rows)
    rolling_2d_row = next(row for row in rows if row.horizon == "rolling 2d")
    assert rolling_2d_row.raw_fields["rolling_2d_status"] == "EMERGENCY_SELL_PRESSURE"
    assert rolling_2d_row.raw_fields["horizon_source"] == "rolling_2d_status"


def test_adapter_excludes_invalid_ticker_rows():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {"ticker": "", "current_status": "NEUTRAL"},
            {"ticker": "2026-05-22", "current_status": "NEUTRAL"},
            {"ticker": "NVDA", "current_status": "NEUTRAL"},
        ]
    )

    assert [row.ticker for row in rows] == ["NVDA"]


def test_build_decisions_from_ticker_enrichment_rows_uses_existing_decision_logic():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "NEUTRAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    assert len(result.decisions) == 1
    assert result.decisions[0].ticker == "NVDA"
    assert result.decisions[0].action == "NEUTRAL"


def test_multi_horizon_positive_case_produces_buy_now_with_expected_horizons():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "BUY_NOW",
                "daily_status": "BUY_NOW",
                "rolling_5d_status": "PULLBACK_CANDIDATE",
                "rolling_30d_status": "BUY_ZONE",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.ticker == "NVDA"
    assert decision.action == "BUY_NOW"
    assert set(decision.horizons_present) >= {"daily", "rolling 5d", "rolling 30d"}
    assert len(decision.decision_trace) >= 1


def test_pullback_readiness_outputs_come_from_existing_decision_logic():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "NVDA",
                "current_status": "NEUTRAL",
                "daily_status": "NEUTRAL_MONITOR",
                "ma_break_status": "OK",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
                "pullback_days": "2",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.pullback_validity == "VALID_PULLBACK"
    assert decision.entry_readiness == "READY_TO_WATCH"
    assert decision.candidate_priority is not None
    assert decision.candidate_priority_label == "P1_READY_TO_WATCH"


def test_adapter_synthesizes_pullback_days_from_rolling_5d_status():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "PULLBACK_CANDIDATE",
                "rolling_5d_status": "PULLBACK_CANDIDATE",
                "ma_break_status": "OK",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    rolling_row = next(row for row in rows if row.horizon == "rolling 5d")
    assert rolling_row.raw_fields["pullback_days"] == "1"


def test_adapter_synthesizes_bullish_signal_age_from_freshness_status():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "NEUTRAL_MONITOR",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
            }
        ]
    )

    daily_row = next(row for row in rows if row.horizon == "daily")
    assert daily_row.raw_fields["latest_bullish_signal_age_td"] == "0"


def test_adapter_exposes_upstream_rolling5_payload_fields_in_raw_fields():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "NEUTRAL_MONITOR",
                "rolling_5d_status": "EARLY_PULLBACK",
                "source_run_ids": "UPSTREAM_ROLLING5_JSON:" + json.dumps(
                    {
                        "pullback_days": 3,
                        "fast_ema10_pullback_days": 2,
                        "conservative_ema20_pullback_days": 1,
                        "latest_bos_freshness": "FRESH",
                        "rolling_5d_blocking_reason": "STRUCTURE_BLOCKED",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            }
        ]
    )

    rolling_row = next(row for row in rows if row.horizon == "rolling 5d")
    assert rolling_row.raw_fields["pullback_days"] == "3"
    assert rolling_row.raw_fields["fast_ema10_pullback_days"] == "2"
    assert rolling_row.raw_fields["conservative_ema20_pullback_days"] == "1"
    assert rolling_row.raw_fields["latest_bos_freshness"] == "FRESH"
    assert rolling_row.raw_fields["rolling_5d_blocking_reason"] == "STRUCTURE_BLOCKED"


def test_decision_integration_uses_writer_visible_pullback_context():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "PULLBACK_CANDIDATE",
                "rolling_5d_status": "PULLBACK_CANDIDATE",
                "ma_break_status": "OK",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.pullback_validity != "INSUFFICIENT_DATA"
    assert decision.pullback_validity == "VALID_PULLBACK"


def test_decision_integration_accepts_upstream_rolling5_context_with_payload():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "NEUTRAL_MONITOR",
                "rolling_5d_status": "EARLY_PULLBACK",
                "ma_break_status": "OK",
                "freshness_status": "FRESH_BULLISH_SIGNAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
                "source_run_ids": "UPSTREAM_ROLLING5_JSON:" + json.dumps(
                    {
                        "pullback_days": 3,
                        "rolling_5_pullback_state": "EARLY_PULLBACK",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.pullback_validity != "INSUFFICIENT_DATA"


def test_ma_break_fields_are_visible_to_decision_logic_and_produce_sell():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "HIGH_EXIT_RISK",
                "current_status": "RISK",
                "ma_break_status": "SMA50_CONFIRMED_BREAK",
                "trend_state": "DOWN",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.action == "SELL"
    assert decision.primary_reason == "SELL_SIGNAL_DETECTED"


def test_ema20_confirmed_break_is_visible_to_decision_logic_and_produce_sell():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "HIGH_EXIT_RISK",
                "current_status": "RISK",
                "ma_break_status": "EMA20_CONFIRMED_BREAK",
                "trend_state": "DOWN",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.action == "SELL"
    assert decision.primary_reason == "SELL_SIGNAL_DETECTED"


def test_risk_fields_are_visible_to_decision_logic_trace():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "EXIT_ZONE",
                "rolling_2d_status": "BOS_DOWN",
                "rolling_30d_status": "BUY_ZONE",
                "latest_bos_event_type": "BOS_DOWN",
                "latest_reset_reason": "DOUBLE_BOS_DOWN",
                "trend_state": "DOWN",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.action in {"SELL", "REDUCE"}
    assert any(
        "bos_down" in (trace.matched_value or "").lower()
        or "double_bos_down" in (trace.matched_value or "").lower()
        for trace in decision.decision_trace
    )


def test_rolling_2d_emergency_sell_pressure_produces_non_neutral_decision():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "HIGH_EXIT_RISK",
                "rolling_2d_status": "EMERGENCY_SELL_PRESSURE",
                "latest_bos_event_type": "BOS_DOWN",
                "latest_reset_reason": "DOUBLE_BOS_DOWN",
                "trend_state": "DOWN",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.action not in {"", "NEUTRAL"}


def test_return_10d_hard_sell_token_in_window_status_2d_can_produce_sell():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "NEUTRAL_MONITOR",
                "window_status_2d": "return_10d_lt_minus_8pct",
                "trend_state": "DOWN",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.action == "SELL"


def test_close_below_ema20_token_is_visible_in_adapter_raw_fields():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "daily_status": "NEUTRAL_MONITOR",
                "window_status_2d": "close_below_ema20",
            }
        ]
    )

    daily_row = next(row for row in rows if row.horizon == "daily")
    assert daily_row.raw_fields["window_status_2d"] == "close_below_ema20"


def test_high_exit_risk_days_count_is_exposed_in_raw_fields_and_seen_by_decision_logic():
    rows = build_dashboard_rows_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "rolling_2d_status": "WATCH_PRESSURE",
                "high_exit_risk_days_count": 1,
            }
        ]
    )

    rolling_row = next(row for row in rows if row.horizon == "rolling 2d")
    assert rolling_row.high_exit_risk_days_count == 1
    assert rolling_row.raw_fields["high_exit_risk_days_count"] == "1"

    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "rolling_2d_status": "WATCH_PRESSURE",
                "high_exit_risk_days_count": 1,
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.action in {"TIGHTEN_STOP", "REDUCE", "SELL"}


def test_final_action_does_not_self_feed_into_decision_logic():
    result = build_decisions_from_ticker_enrichment_rows(
        [
            {
                "ticker": "AAA",
                "action": "SELL",
            }
        ]
    )

    decision = result.decisions[0]
    assert decision.action == "NEUTRAL"


def test_loader_reads_rows_read_only_and_missing_db_fails_clearly(tmp_path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                current_status TEXT,
                high_exit_risk_days_count INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, current_status
            ) VALUES (?, ?, ?, ?)
            """,
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "NVDA", "NEUTRAL"),
        )
        before_count = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]

    rows = load_ticker_enrichment_rows(
        str(db_path),
        "2026-05-22",
        "DC_TAXONOMY_FULL_V1",
    )

    assert len(rows) == 1
    assert rows[0]["ticker"] == "NVDA"

    with sqlite3.connect(db_path) as conn:
        after_count = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
    assert before_count == after_count

    missing_path = tmp_path / "missing.db"
    try:
        load_ticker_enrichment_rows(
            str(missing_path),
            "2026-05-22",
            "DC_TAXONOMY_FULL_V1",
        )
    except FileNotFoundError as exc:
        assert "analysis_db not found:" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected FileNotFoundError for missing analysis_db")
