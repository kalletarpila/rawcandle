from __future__ import annotations

from analysis.datacenter_indices.rolling5_pullback_classifier import (
    classify_rolling_5_pullback_row,
)


def _base_row(**overrides):
    row = {
        "ticker": "AAA",
        "last_price_data_status": "OK",
        "all_price_rows_missing": False,
        "last_ticker_trend_state": "UP",
        "current_watchlist_status": "NEUTRAL_MONITOR",
        "window_watchlist_status": "NEUTRAL_MONITOR",
        "pullback_days": 0,
        "fast_ema10_pullback_days": 0,
        "conservative_ema20_pullback_days": 0,
        "exit_risk_days": 0,
        "last_exit_risk_severity": None,
        "last_latest_bos_event_type": None,
        "last_latest_bos_freshness": None,
        "last_latest_reset_reason": None,
        "last_latest_reset_freshness": None,
        "latest_bearish_relevance_class": None,
    }
    row.update(overrides)
    return row


def test_missing_price_context_returns_insufficient_data():
    result = classify_rolling_5_pullback_row(
        _base_row(last_price_data_status="MISSING_CLOSE_AS_OF_DATE")
    )

    assert result.rolling_5_pullback_state == "INSUFFICIENT_DATA"
    assert result.primary_reason == "MISSING_PRICE_CONTEXT"
    assert result.blocking_reason == "price_data_missing"
    assert result.next_action == "WAIT_FOR_DATA"


def test_missing_ticker_returns_insufficient_data():
    result = classify_rolling_5_pullback_row(_base_row(ticker=""))

    assert result.rolling_5_pullback_state == "INSUFFICIENT_DATA"
    assert result.primary_reason == "MISSING_TICKER_CONTEXT"
    assert result.blocking_reason == "missing_ticker"
    assert result.next_action == "WAIT_FOR_DATA"


def test_no_pullback_evidence_with_fresh_bos_down_returns_short_term_breakdown():
    result = classify_rolling_5_pullback_row(
        _base_row(
            last_latest_bos_event_type="BOS_DOWN",
            last_latest_bos_freshness="FRESH",
        )
    )

    assert result.rolling_5_pullback_state == "SHORT_TERM_BREAKDOWN"
    assert result.primary_reason == "SHORT_TERM_BREAKDOWN_WITHOUT_PULLBACK_SETUP"
    assert result.blocking_reason == "recent_bos_down"
    assert result.next_action == "MONITOR_EXIT_RISK"


def test_no_pullback_evidence_without_severe_breakdown_returns_no_pullback():
    result = classify_rolling_5_pullback_row(_base_row())

    assert result.rolling_5_pullback_state == "NO_PULLBACK"
    assert result.primary_reason == "NO_MEANINGFUL_PULLBACK_EVIDENCE"
    assert result.blocking_reason == ""
    assert result.next_action == "NONE"


def test_pullback_evidence_with_blocker_returns_failed_pullback():
    result = classify_rolling_5_pullback_row(
        _base_row(
            pullback_days=2,
            last_latest_bos_event_type="BOS_DOWN",
            last_latest_bos_freshness="FRESH",
        )
    )

    assert result.rolling_5_pullback_state == "FAILED_PULLBACK"
    assert result.primary_reason == "PULLBACK_SETUP_BLOCKED"
    assert result.blocking_reason == "recent_bos_down"
    assert result.next_action == "REMOVE_FROM_PULLBACK_LIST"


def test_confirmed_pullback_candidate_returns_expected_status():
    result = classify_rolling_5_pullback_row(
        _base_row(
            pullback_days=2,
            conservative_ema20_pullback_days=1,
        )
    )

    assert result.rolling_5_pullback_state == "PULLBACK_CANDIDATE"
    assert result.primary_reason == "CONFIRMED_EMA20_PULLBACK_CONTEXT"
    assert result.blocking_reason == ""
    assert result.next_action == "REVIEW_FOR_DAILY_TRIGGER"


def test_early_pullback_returns_expected_status_for_mixed_context():
    result = classify_rolling_5_pullback_row(
        _base_row(
            pullback_days=2,
            exit_risk_days=1,
        )
    )

    assert result.rolling_5_pullback_state == "EARLY_PULLBACK"
    assert result.primary_reason == "EARLY_OR_UNCONFIRMED_PULLBACK"
    assert result.blocking_reason == "EXIT_RISK_DAYS_WITHOUT_HIGH_SEVERITY"
    assert result.next_action == "MONITOR_FOR_CONFIRMATION"


def test_reason_priority_prefers_ema20_then_ema10_then_generic_pullback():
    ema20 = classify_rolling_5_pullback_row(
        _base_row(
            pullback_days=2,
            conservative_ema20_pullback_days=1,
            fast_ema10_pullback_days=1,
        )
    )
    ema10 = classify_rolling_5_pullback_row(
        _base_row(
            pullback_days=2,
            conservative_ema20_pullback_days=0,
            fast_ema10_pullback_days=1,
        )
    )
    generic = classify_rolling_5_pullback_row(
        _base_row(
            pullback_days=2,
            current_watchlist_status="PULLBACK_CANDIDATE",
        )
    )

    assert ema20.primary_reason == "CONFIRMED_EMA20_PULLBACK_CONTEXT"
    assert ema10.primary_reason == "CONFIRMED_EMA10_PULLBACK_CONTEXT"
    assert generic.primary_reason == "PULLBACK_EVIDENCE_WITH_ACCEPTABLE_STRUCTURE"
