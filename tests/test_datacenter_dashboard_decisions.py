from __future__ import annotations

from dev_tools.datacenter_dashboard_decisions import build_datacenter_ticker_decisions
from dev_tools.datacenter_dashboard_parser import DatacenterDashboardRow


def _row(
    *,
    ticker: str,
    horizon: str,
    raw_action: str | None = None,
    raw_status: str | None = None,
    reason: str | None = None,
    trend_state: str | None = None,
    latest_structure_label: str | None = None,
    latest_bos_event_type: str | None = None,
    latest_reset_reason: str | None = None,
    distance_to_ema20: float | None = None,
    high_exit_risk_days_count: int | None = None,
    blocking_reasons: str | None = None,
    raw_fields: dict[str, str] | None = None,
) -> DatacenterDashboardRow:
    return DatacenterDashboardRow(
        ticker=ticker,
        horizon=horizon,
        source_file=f"/tmp/{ticker}_{horizon}.csv",
        section=None,
        row_kind=None,
        raw_action=raw_action,
        raw_status=raw_status,
        reason=reason,
        trend_state=trend_state,
        latest_structure_label=latest_structure_label,
        latest_bos_event_type=latest_bos_event_type,
        latest_reset_reason=latest_reset_reason,
        distance_to_ema20=distance_to_ema20,
        high_exit_risk_days_count=high_exit_risk_days_count,
        blocking_reasons=blocking_reasons,
        raw_fields=raw_fields or {},
    )


def test_sell_overrides_positive_signals():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 30d", raw_status="BUY_ZONE"),
            _row(ticker="NVDA", horizon="rolling 5d", raw_status="PULLBACK"),
            _row(ticker="NVDA", horizon="daily", raw_status="BUY_NOW"),
            _row(ticker="NVDA", horizon="daily", reason="close_below_ema20"),
        ]
    )

    assert result.decisions[0].action == "SELL"


def test_rolling_2d_bos_down_alone_is_reduce_not_sell():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN")]
    )

    assert result.decisions[0].action == "REDUCE"


def test_rolling_2d_bos_down_plus_reset_is_sell():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 2d", latest_reset_reason="RESET"),
        ]
    )

    assert result.decisions[0].action == "SELL"


def test_rolling_2d_bos_down_plus_high_exit_risk_days_count_is_sell():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 2d", high_exit_risk_days_count=1),
        ]
    )

    assert result.decisions[0].action == "SELL"


def test_rolling_2d_bos_down_plus_failed_pullback_is_sell():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 2d", raw_status="FAILED_PULLBACK"),
        ]
    )

    assert result.decisions[0].action == "SELL"


def test_rolling_2d_bos_down_plus_daily_bos_down_is_sell():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="daily", latest_bos_event_type="BOS_DOWN"),
        ]
    )

    assert result.decisions[0].action == "SELL"


def test_blocked_from_blocking_reasons_when_no_sell_exists():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="AMD", horizon="rolling 5d", blocking_reasons="HIGH_EXIT_RISK")]
    )

    assert result.decisions[0].action == "BLOCKED"
    assert result.decisions[0].severity == "HIGH"


def test_reduce_from_daily_or_rolling_2d_risk_language():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="AVGO", horizon="daily", reason="subindustry_context_risk")]
    )

    assert result.decisions[0].action == "REDUCE"


def test_reset_alone_without_hard_confirmation_is_reduce():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="AVGO", horizon="rolling 2d", latest_reset_reason="RESET")]
    )

    assert result.decisions[0].action == "REDUCE"


def test_tighten_stop_from_high_exit_risk_days_count():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="LRCX", horizon="rolling 2d", high_exit_risk_days_count=1)]
    )

    assert result.decisions[0].action == "TIGHTEN_STOP"


def test_wait_pullback_when_otherwise_positive_and_stretched():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="META", horizon="rolling 30d", raw_status="UP", distance_to_ema20=16.5)]
    )

    assert result.decisions[0].action == "WAIT_PULLBACK"


def test_blocked_outranks_wait_pullback_when_blocking_reasons_exist():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="META",
                horizon="rolling 30d",
                raw_status="UP",
                distance_to_ema20=16.5,
                blocking_reasons="STRUCTURAL_BLOCK",
            )
        ]
    )

    assert result.decisions[0].action == "BLOCKED"


def test_buy_now_only_when_multi_horizon_constructive_alignment_exists():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="TSM", horizon="rolling 30d", raw_status="BUY_ZONE"),
            _row(ticker="TSM", horizon="rolling 5d", raw_status="PULLBACK"),
            _row(ticker="TSM", horizon="daily", raw_status="BULLISH"),
        ]
    )

    assert result.decisions[0].action == "BUY_NOW"


def test_watch_when_rolling_30_positive_but_no_daily_trigger_exists():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="MRVL", horizon="rolling 30d", raw_status="LEADER")]
    )

    assert result.decisions[0].action == "WATCH"


def test_neutral_fallback():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="INTC", horizon="daily", raw_status="SIDEWAYS")]
    )

    assert result.decisions[0].action == "NEUTRAL"


def test_output_ordering_is_deterministic():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="BBB", horizon="daily", reason="close_below_ema20"),
            _row(ticker="AAA", horizon="daily", reason="close_below_ema20"),
            _row(ticker="CCC", horizon="rolling 30d", raw_status="LEADER"),
            _row(ticker="DDD", horizon="rolling 5d", blocking_reasons="STRUCTURAL_BLOCK"),
        ]
    )

    assert [(item.ticker, item.action) for item in result.decisions] == [
        ("AAA", "SELL"),
        ("BBB", "SELL"),
        ("DDD", "BLOCKED"),
        ("CCC", "WATCH"),
    ]


def test_sell_still_outranks_blocked():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="AVGO",
                horizon="daily",
                reason="close_below_ema20",
                blocking_reasons="STRUCTURAL_BLOCK",
            )
        ]
    )

    assert result.decisions[0].action == "SELL"


def test_reduce_still_outranks_blocked():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="LRCX",
                horizon="daily",
                reason="exit_risk",
                blocking_reasons="STRUCTURAL_BLOCK",
            )
        ]
    )

    assert result.decisions[0].action == "REDUCE"


def test_tighten_stop_still_outranks_blocked():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="SMCI",
                horizon="rolling 2d",
                high_exit_risk_days_count=1,
                blocking_reasons="STRUCTURAL_BLOCK",
            )
        ]
    )

    assert result.decisions[0].action == "TIGHTEN_STOP"


def test_action_counts_are_correct():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="AAA", horizon="daily", reason="close_below_ema20"),
            _row(ticker="BBB", horizon="daily", reason="exit_risk"),
            _row(ticker="CCC", horizon="rolling 2d", high_exit_risk_days_count=1),
            _row(ticker="DDD", horizon="rolling 30d", raw_status="LEADER"),
            _row(ticker="EEE", horizon="daily", raw_status="SIDEWAYS"),
        ]
    )

    assert result.action_counts["SELL"] == 1
    assert result.action_counts["REDUCE"] == 1
    assert result.action_counts["TIGHTEN_STOP"] == 1
    assert result.action_counts["WATCH"] == 1
    assert result.action_counts["NEUTRAL"] == 1


def test_action_counts_reflect_refined_bos_down_rules():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="AAA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="BBB", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="BBB", horizon="rolling 2d", latest_reset_reason="RESET"),
        ]
    )

    assert result.action_counts["SELL"] == 1
    assert result.action_counts["REDUCE"] == 1


def test_sell_trace_captures_horizon_field_token_value_and_source_file():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", reason="close_below_ema20")]
    )

    trace = result.decisions[0].decision_trace[0]
    assert result.decisions[0].action == "SELL"
    assert trace.horizon == "daily"
    assert trace.field_name == "reason"
    assert trace.matched_token == "close_below_ema20"
    assert trace.matched_value == "close_below_ema20"
    assert trace.source_file == "/tmp/NVDA_daily.csv"
    assert trace.matched_rule == "SELL_HARD_TOKEN"


def test_reduce_trace_captures_risk_token():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="AVGO", horizon="daily", reason="subindustry_context_risk")]
    )

    trace = result.decisions[0].decision_trace[0]
    assert result.decisions[0].action == "REDUCE"
    assert trace.matched_rule == "REDUCE_RISK_TOKEN"
    assert trace.matched_token == "risk"
    assert trace.field_name == "reason"


def test_tighten_stop_trace_captures_high_exit_risk_days_count():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="LRCX", horizon="rolling 2d", high_exit_risk_days_count=1)]
    )

    trace = result.decisions[0].decision_trace[0]
    assert result.decisions[0].action == "TIGHTEN_STOP"
    assert trace.field_name == "high_exit_risk_days_count"
    assert trace.matched_token == "high_exit_risk_days_count>=1"
    assert trace.matched_value == "1"


def test_wait_pullback_trace_captures_distance_to_ema20():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="META", horizon="rolling 30d", raw_status="UP", distance_to_ema20=16.5)]
    )

    trace = result.decisions[0].decision_trace[0]
    assert result.decisions[0].action == "WAIT_PULLBACK"
    assert trace.field_name == "distance_to_ema20"
    assert trace.matched_token == "distance_to_ema20>15.0"
    assert trace.matched_value == "16.5"


def test_blocked_trace_captures_blocking_reasons():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="AMD", horizon="rolling 5d", blocking_reasons="HIGH_EXIT_RISK")]
    )

    trace = result.decisions[0].decision_trace[0]
    assert result.decisions[0].action == "BLOCKED"
    assert trace.field_name == "blocking_reasons"
    assert trace.matched_token == "blocking_reasons"
    assert trace.matched_value == "HIGH_EXIT_RISK"


def test_final_action_is_unchanged_when_traces_are_added():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 30d", raw_status="BUY_ZONE"),
            _row(ticker="NVDA", horizon="rolling 5d", raw_status="PULLBACK"),
            _row(ticker="NVDA", horizon="daily", raw_status="BUY_NOW"),
            _row(ticker="NVDA", horizon="daily", reason="close_below_ema20"),
        ]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_HARD_TOKEN"


def test_confirmed_bos_down_trace_uses_sell_bos_down_confirmed():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 2d", latest_reset_reason="RESET"),
        ]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_BOS_DOWN_CONFIRMED"


def test_unconfirmed_bos_down_trace_uses_reduce_bos_down_unconfirmed():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN")]
    )

    assert result.decisions[0].action == "REDUCE"
    assert result.decisions[0].decision_trace[0].matched_rule == "REDUCE_BOS_DOWN_UNCONFIRMED"


def test_decision_ordering_is_unchanged_when_traces_are_added():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="BBB", horizon="daily", reason="close_below_ema20"),
            _row(ticker="AAA", horizon="daily", reason="close_below_ema20"),
            _row(ticker="CCC", horizon="rolling 30d", raw_status="LEADER"),
            _row(ticker="DDD", horizon="rolling 5d", blocking_reasons="STRUCTURAL_BLOCK"),
        ]
    )

    assert [(item.ticker, item.action) for item in result.decisions] == [
        ("AAA", "SELL"),
        ("BBB", "SELL"),
        ("DDD", "BLOCKED"),
        ("CCC", "WATCH"),
    ]
