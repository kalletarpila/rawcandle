from __future__ import annotations

from analysis.datacenter_indices.rolling30_watchlist_classifier import (
    build_rolling_30_role_rows_from_base_rows,
    classify_rolling_30_buy_row,
    classify_rolling_30_exit_row,
)


def _base_row(**overrides):
    row = {
        "ticker": "AAA",
        "primary_layer": "Compute",
        "primary_subindustry": "Networking",
        "window_watchlist_status": "NEUTRAL_MONITOR",
        "current_watchlist_status": "NEUTRAL_MONITOR",
        "breakout_days": 0,
        "pullback_days": 0,
        "exit_risk_days": 0,
        "high_exit_risk_days": 0,
        "medium_exit_risk_days": 0,
        "last_price_data_status": "OK",
        "all_price_rows_missing": False,
        "last_exit_risk_severity": None,
        "last_exit_reason": None,
        "last_ticker_trend_state": "UP",
        "last_latest_structure_label": "HH",
        "last_latest_bos_event_type": "BOS_UP",
        "last_latest_bos_freshness": "AGING",
        "last_latest_reset_reason": None,
        "last_latest_reset_freshness": None,
        "latest_bullish_relevance_class": "RELEVANT",
        "latest_bullish_relevance_reason": "ok",
        "latest_bearish_relevance_class": None,
        "latest_bearish_relevance_reason": None,
        "last_subindustry_overheat_risk_level": None,
    }
    row.update(overrides)
    return row


def test_positive_pullback_context_preserves_pullback_days_and_buy_zone():
    classification = classify_rolling_30_buy_row(
        _base_row(pullback_days=2, current_watchlist_status="ADD_ON_PULLBACK")
    )

    assert classification.rolling_30_buy_state == "BUY_ZONE"
    assert classification.primary_reason == "UP_STRUCTURE_WITH_PULLBACK_CONTEXT"
    assert classification.blocking_reason == ""


def test_breakout_context_maps_to_repeated_buy_signal_reason():
    classification = classify_rolling_30_buy_row(_base_row(breakout_days=3))

    assert classification.rolling_30_buy_state == "BUY_ZONE"
    assert classification.primary_reason == "UP_STRUCTURE_WITH_REPEATED_BUY_SIGNAL"
    assert classification.blocking_reason == ""


def test_exit_risk_blocker_context_maps_to_avoid_with_exact_reason():
    classification = classify_rolling_30_buy_row(
        _base_row(
            pullback_days=2,
            current_watchlist_status="HIGH_EXIT_RISK",
            last_exit_risk_severity="HIGH",
        )
    )

    assert classification.rolling_30_buy_state == "AVOID"
    assert classification.primary_reason == "clear_structural_or_exit_block"
    assert classification.blocking_reason == "CURRENT_HIGH_EXIT_RISK"


def test_no_meaningful_setup_stays_watch_zone():
    classification = classify_rolling_30_buy_row(
        _base_row(
            breakout_days=0,
            pullback_days=0,
            current_watchlist_status="NORMAL",
            window_watchlist_status="NORMAL",
            last_ticker_trend_state="NEUTRAL",
        )
    )

    assert classification.rolling_30_buy_state == "WATCH_ZONE"
    assert classification.primary_reason == "MIXED_OR_UNCONFIRMED_STRUCTURE"
    assert classification.blocking_reason == ""


def test_exact_reason_priority_prefers_recent_bos_down_over_other_blockers():
    classification = classify_rolling_30_buy_row(
        _base_row(
            pullback_days=2,
            last_ticker_trend_state="DOWN",
            current_watchlist_status="HIGH_EXIT_RISK",
            latest_bearish_relevance_class="RELEVANT",
            last_latest_bos_event_type="BOS_DOWN",
            last_latest_bos_freshness="FRESH",
        )
    )

    assert classification.rolling_30_buy_state == "AVOID"
    assert classification.blocking_reason == "recent_bos_down"


def test_build_role_rows_preserves_report_row_shape_for_buy_context():
    buy_rows, exit_rows = build_rolling_30_role_rows_from_base_rows(
        [_base_row(pullback_days=2, current_watchlist_status="ADD_ON_PULLBACK")]
    )

    assert len(buy_rows) == 1
    assert len(exit_rows) == 1
    assert buy_rows[0]["ticker"] == "AAA"
    assert buy_rows[0]["rolling_30_buy_state"] == "BUY_ZONE"
    assert buy_rows[0]["pullback_days"] == 2
    assert buy_rows[0]["primary_reason"] == "UP_STRUCTURE_WITH_PULLBACK_CONTEXT"
    assert buy_rows[0]["blocking_reason"] == ""


def test_exit_classification_extreme_severity_still_maps_to_extreme():
    classification = classify_rolling_30_exit_row(
        _base_row(exit_risk_days=1, last_exit_risk_severity="CRITICAL")
    )

    assert classification.rolling_30_exit_state == "EXTREME"
    assert classification.primary_reason == "EXTREME_EXIT_RISK"
    assert classification.risk_reason == "CRITICAL_EXIT_RISK_SEVERITY"
