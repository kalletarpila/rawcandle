from __future__ import annotations

from analysis.datacenter_indices.rolling2_sell_pressure_classifier import (
    EMERGENCY_SELL_PRESSURE,
    INSUFFICIENT_DATA,
    NO_EMERGENCY,
    SHARP_2D_DROP,
    WATCH_PRESSURE,
    classify_rolling_2_sell_pressure_row,
)


def _base_row(**overrides):
    row = {
        "ticker": "AAA",
        "last_price_data_status": "OK",
        "all_price_rows_missing": False,
        "current_watchlist_status": "NEUTRAL_MONITOR",
        "window_watchlist_status": "NEUTRAL_MONITOR",
        "exit_risk_days": 0,
        "high_exit_risk_days": 0,
        "medium_exit_risk_days": 0,
        "last_exit_risk_severity": None,
        "last_exit_reason": None,
        "last_ticker_trend_state": "UP",
        "latest_bearish_relevance_class": None,
        "last_latest_structure_label": "HH",
        "last_latest_bos_event_type": None,
        "last_latest_bos_freshness": None,
        "last_latest_reset_reason": None,
        "last_latest_reset_freshness": None,
        "last_distance_to_ema20_pct": 0.05,
    }
    row.update(overrides)
    return row


def test_missing_price_context_returns_insufficient_data():
    classification = classify_rolling_2_sell_pressure_row(
        _base_row(last_price_data_status="MISSING_CLOSE_AS_OF_DATE")
    )

    assert classification.rolling_2_sell_pressure_state == INSUFFICIENT_DATA
    assert classification.primary_reason == "MISSING_PRICE_CONTEXT"
    assert classification.risk_reason == ""
    assert classification.next_action == "WAIT_FOR_DATA"


def test_missing_ticker_returns_insufficient_data():
    classification = classify_rolling_2_sell_pressure_row(_base_row(ticker=""))

    assert classification.rolling_2_sell_pressure_state == INSUFFICIENT_DATA
    assert classification.primary_reason == "MISSING_TICKER_CONTEXT"
    assert classification.risk_reason == ""
    assert classification.next_action == "WAIT_FOR_DATA"


def test_emergency_sell_pressure_matches_current_algorithm():
    classification = classify_rolling_2_sell_pressure_row(
        _base_row(
            exit_risk_days=2,
            high_exit_risk_days=2,
            last_exit_risk_severity="HIGH",
            last_exit_reason="close_below_ema20",
            last_ticker_trend_state="DOWN",
        )
    )

    assert classification.rolling_2_sell_pressure_state == EMERGENCY_SELL_PRESSURE
    assert classification.primary_reason == "CONFIRMED_TWO_DAY_SELL_PRESSURE"
    assert classification.risk_reason == "HIGH_PRESSURE_WITH_STRUCTURAL_BREAKDOWN"
    assert classification.next_action == "CHECK_STOP_OR_REDUCE"


def test_sharp_2d_drop_matches_current_algorithm():
    classification = classify_rolling_2_sell_pressure_row(
        _base_row(
            exit_risk_days=2,
            high_exit_risk_days=1,
            last_exit_risk_severity="MEDIUM",
            last_exit_reason="close_below_ema20",
            last_ticker_trend_state="NEUTRAL",
        )
    )

    assert classification.rolling_2_sell_pressure_state == SHARP_2D_DROP
    assert classification.primary_reason == "SHARP_SHORT_TERM_DROP"
    assert classification.risk_reason == "EXIT_RISK_PERSISTENT_TWO_DAYS"
    assert classification.next_action == "TIGHTEN_STOP_REVIEW_DAILY_TRIGGER"


def test_watch_pressure_matches_current_algorithm():
    classification = classify_rolling_2_sell_pressure_row(
        _base_row(
            exit_risk_days=1,
            last_exit_risk_severity=None,
            last_exit_reason=None,
            last_ticker_trend_state="NEUTRAL",
        )
    )

    assert classification.rolling_2_sell_pressure_state == WATCH_PRESSURE
    assert classification.primary_reason == "MILD_OR_UNCONFIRMED_SELL_PRESSURE"
    assert classification.risk_reason == "EXIT_RISK_PRESENT"
    assert classification.next_action == "MONITOR_NEXT_SESSION"


def test_no_emergency_matches_current_algorithm():
    classification = classify_rolling_2_sell_pressure_row(_base_row())

    assert classification.rolling_2_sell_pressure_state == NO_EMERGENCY
    assert classification.primary_reason == "NO_TWO_DAY_SELL_PRESSURE"
    assert classification.risk_reason == ""
    assert classification.next_action == "NONE"


def test_reason_priority_preserves_emergency_precedence():
    classification = classify_rolling_2_sell_pressure_row(
        _base_row(
            exit_risk_days=2,
            high_exit_risk_days=2,
            medium_exit_risk_days=1,
            last_exit_risk_severity="CRITICAL",
            last_exit_reason="close_below_ema20;return_10d_lt_minus_8pct",
            last_ticker_trend_state="DOWN",
            current_watchlist_status="HIGH_EXIT_RISK",
            last_latest_bos_event_type="BOS_DOWN",
            last_latest_bos_freshness="FRESH",
            last_latest_reset_reason="DOUBLE_BOS_DOWN",
            last_latest_reset_freshness="FRESH",
            latest_bearish_relevance_class="RELEVANT",
            last_distance_to_ema20_pct=-0.05,
        )
    )

    assert classification.rolling_2_sell_pressure_state == EMERGENCY_SELL_PRESSURE
    assert classification.risk_reason == "CRITICAL_OR_EXTREME_EXIT_SEVERITY"
    assert classification.next_action == "CHECK_STOP_OR_REDUCE"
