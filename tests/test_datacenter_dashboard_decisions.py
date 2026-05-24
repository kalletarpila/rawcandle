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
    ma_break_status: str | None = None,
    structure_warning_overrides_bullish_signal: int | None = None,
    freshness_status: str | None = None,
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
        ma_break_status=ma_break_status,
        ema20_break_confirmed=None,
        sma50_break_confirmed=None,
        close_below_ema20=None,
        close_below_sma50=None,
        consecutive_closes_below_ema20=None,
        consecutive_closes_below_sma50=None,
        ema20_break_pct=None,
        sma50_break_pct=None,
        freshness_status=freshness_status,
        structure_warning_overrides_bullish_signal=structure_warning_overrides_bullish_signal,
        latest_bullish_signal_age_td=None,
        latest_bearish_signal_age_td=None,
        latest_bos_up_age_td=None,
        latest_bos_down_age_td=None,
        latest_reset_age_td=None,
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


def test_daily_sma50_confirmed_break_is_sell():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", ma_break_status="SMA50_CONFIRMED_BREAK")]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_SMA50_CONFIRMED_BREAK"


def test_rolling_2d_sma50_confirmed_break_is_sell():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="rolling 2d", ma_break_status="SMA50_CONFIRMED_BREAK")]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_SMA50_CONFIRMED_BREAK"


def test_daily_ema20_confirmed_break_is_sell():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", ma_break_status="EMA20_CONFIRMED_BREAK")]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_EMA20_CONFIRMED_BREAK"


def test_rolling_2d_ema20_confirmed_break_is_sell():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="rolling 2d", ma_break_status="EMA20_CONFIRMED_BREAK")]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_EMA20_CONFIRMED_BREAK"


def test_daily_ema20_warning_is_reduce():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", ma_break_status="EMA20_WARNING")]
    )

    assert result.decisions[0].action == "REDUCE"
    assert result.decisions[0].decision_trace[0].matched_rule == "REDUCE_EMA20_WARNING"


def test_rolling_2d_ema20_warning_is_reduce():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="rolling 2d", ma_break_status="EMA20_WARNING")]
    )

    assert result.decisions[0].action == "REDUCE"
    assert result.decisions[0].decision_trace[0].matched_rule == "REDUCE_EMA20_WARNING"


def test_ma_break_status_ok_with_raw_close_below_ema20_does_not_create_sell_by_itself():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", ma_break_status="OK", reason="close_below_ema20")]
    )

    assert result.decisions[0].action != "SELL"


def test_no_ma_break_status_with_raw_close_below_ema20_still_creates_sell_fallback():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", reason="close_below_ema20")]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_HARD_TOKEN"


def test_explicit_sell_still_creates_sell_even_when_ma_break_status_ok():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", ma_break_status="OK", raw_status="SELL")]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_HARD_TOKEN"


def test_return_10d_lt_minus_8pct_still_creates_sell_even_when_ma_break_status_ok():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="daily", ma_break_status="OK", reason="return_10d_lt_minus_8pct")]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_HARD_TOKEN"


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


def test_rolling_2d_bos_down_plus_rolling_30d_high_exit_risk_days_count_only_is_reduce():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 30d", high_exit_risk_days_count=12),
        ]
    )

    assert result.decisions[0].action == "REDUCE"


def test_rolling_2d_bos_down_plus_rolling_5d_high_exit_risk_days_count_only_is_reduce():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 5d", high_exit_risk_days_count=3),
        ]
    )

    assert result.decisions[0].action == "REDUCE"


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


def test_rolling_2d_bos_down_plus_daily_reset_is_sell():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="daily", latest_reset_reason="RESET"),
        ]
    )

    assert result.decisions[0].action == "SELL"


def test_rolling_2d_bos_down_plus_double_bos_down_is_sell_even_when_ma_break_status_ok():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="NVDA",
                horizon="rolling 2d",
                ma_break_status="OK",
                latest_bos_event_type="BOS_DOWN",
            ),
            _row(
                ticker="NVDA",
                horizon="rolling 2d",
                ma_break_status="OK",
                raw_status="DOUBLE_BOS_DOWN",
            ),
        ]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_BOS_DOWN_CONFIRMED_ACUTE"


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


def test_rolling_30d_reset_alone_must_not_become_sell():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="AVGO", horizon="rolling 30d", latest_reset_reason="RESET")]
    )

    assert result.decisions[0].action != "SELL"


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


def test_freshness_structure_warning_overrides_bullish_blocks_buy_now():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="TSM", horizon="rolling 30d", raw_status="BUY_ZONE"),
            _row(ticker="TSM", horizon="rolling 5d", raw_status="PULLBACK"),
            _row(ticker="TSM", horizon="daily", raw_status="BULLISH"),
            _row(
                ticker="TSM",
                horizon="daily",
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
                structure_warning_overrides_bullish_signal=1,
            ),
        ]
    )

    assert result.decisions[0].action != "BUY_NOW"


def test_freshness_structure_warning_overrides_bullish_blocks_watch():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="MRVL", horizon="rolling 30d", raw_status="LEADER"),
            _row(
                ticker="MRVL",
                horizon="daily",
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
                structure_warning_overrides_bullish_signal=1,
            ),
        ]
    )

    assert result.decisions[0].action != "WATCH"


def test_no_pullback_context_is_no_pullback():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="INTC", horizon="daily", raw_status="SIDEWAYS")]
    )

    assert result.decisions[0].pullback_validity == "NO_PULLBACK"
    assert result.decisions[0].pullback_reason == "NO_PULLBACK_CONTEXT"


def test_pullback_context_plus_fresh_rolling_2d_bos_down_is_structure_blocked_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="NVDA",
                horizon="rolling 2d",
                raw_status="PULLBACK_CANDIDATE",
                latest_bos_event_type="BOS_DOWN",
                raw_fields={"latest_bos_freshness": "FRESH"},
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"
    assert result.decisions[0].pullback_reason == "FRESH_BOS_DOWN_BLOCKS_PULLBACK"


def test_pullback_context_plus_fresh_rolling_2d_double_bos_down_is_structure_blocked_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="NVDA",
                horizon="rolling 2d",
                raw_status="PULLBACK_CANDIDATE",
                latest_reset_reason="DOUBLE_BOS_DOWN",
                raw_fields={"latest_reset_freshness": "FRESH"},
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"
    assert result.decisions[0].pullback_reason == "FRESH_DOUBLE_BOS_DOWN_BLOCKS_PULLBACK"


def test_pullback_context_plus_structure_override_flag_is_structure_blocked_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="TSM",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                structure_warning_overrides_bullish_signal=1,
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"
    assert result.decisions[0].pullback_reason == "STRUCTURE_WARNING_OVERRIDES_BULLISH_SIGNAL"


def test_pullback_context_plus_daily_ema20_confirmed_break_is_breakdown_not_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="AMD",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="EMA20_CONFIRMED_BREAK",
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "BREAKDOWN_NOT_PULLBACK"
    assert result.decisions[0].pullback_reason == "EMA20_CONFIRMED_BREAK"


def test_pullback_context_plus_rolling_2d_sma50_confirmed_break_is_breakdown_not_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="AMD",
                horizon="rolling 2d",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="SMA50_CONFIRMED_BREAK",
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "BREAKDOWN_NOT_PULLBACK"
    assert result.decisions[0].pullback_reason == "SMA50_CONFIRMED_BREAK"


def test_pullback_context_plus_fresh_bullish_signal_and_ok_ma_is_valid_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="TSM",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="OK",
                freshness_status="FRESH_BULLISH_SIGNAL",
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "VALID_PULLBACK"
    assert result.decisions[0].pullback_reason == "FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK"


def test_pullback_context_plus_ema20_warning_and_fresh_bullish_signal_is_valid_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="TSM",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="EMA20_WARNING",
                freshness_status="FRESH_BULLISH_SIGNAL",
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "VALID_PULLBACK"


def test_pullback_context_without_block_and_without_bullish_confirmation_is_early_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="TSM",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="OK",
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "EARLY_PULLBACK"
    assert result.decisions[0].pullback_reason == "WAIT_FOR_BULLISH_CONFIRMATION"


def test_structure_blocked_pullback_outranks_breakdown_not_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="NVDA",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="EMA20_CONFIRMED_BREAK",
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
                structure_warning_overrides_bullish_signal=1,
            )
        ]
    )

    assert result.decisions[0].pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"


def test_breakdown_not_pullback_outranks_early_pullback():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="AMD",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="EMA20_CONFIRMED_BREAK",
            ),
            _row(
                ticker="AMD",
                horizon="rolling 5d",
                raw_status="EARLY_PULLBACK",
            ),
        ]
    )

    assert result.decisions[0].pullback_validity == "BREAKDOWN_NOT_PULLBACK"


def test_final_action_is_unchanged_by_pullback_validity():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="NVDA",
                horizon="rolling 2d",
                raw_status="PULLBACK_CANDIDATE DOUBLE_BOS_DOWN",
                latest_bos_event_type="BOS_DOWN",
                ma_break_status="OK",
            )
        ]
    )

    assert result.decisions[0].action == "SELL"
    assert result.decisions[0].pullback_validity in {"STRUCTURE_BLOCKED_PULLBACK", "EARLY_PULLBACK", "VALID_PULLBACK", "BREAKDOWN_NOT_PULLBACK", "NO_PULLBACK", "INSUFFICIENT_DATA"}


def test_pullback_validity_respects_deterministic_horizon_priority():
    result = build_datacenter_ticker_decisions(
        [
            _row(
                ticker="NVDA",
                horizon="rolling 2d",
                raw_status="PULLBACK_CANDIDATE",
                ma_break_status="EMA20_CONFIRMED_BREAK",
            ),
            _row(
                ticker="NVDA",
                horizon="daily",
                raw_status="PULLBACK_CANDIDATE",
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
                structure_warning_overrides_bullish_signal=1,
            ),
        ]
    )

    assert result.decisions[0].pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"
    assert result.decisions[0].pullback_reason == "STRUCTURE_WARNING_OVERRIDES_BULLISH_SIGNAL"


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
    assert result.decisions[0].decision_trace[0].matched_rule == "SELL_BOS_DOWN_CONFIRMED_ACUTE"


def test_unconfirmed_bos_down_trace_uses_reduce_bos_down_unconfirmed():
    result = build_datacenter_ticker_decisions(
        [_row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN")]
    )

    assert result.decisions[0].action == "REDUCE"
    assert result.decisions[0].decision_trace[0].matched_rule == "REDUCE_BOS_DOWN_UNCONFIRMED"


def test_long_context_only_bos_down_trace_uses_reduce_bos_down_long_context_only():
    result = build_datacenter_ticker_decisions(
        [
            _row(ticker="NVDA", horizon="rolling 2d", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 30d", high_exit_risk_days_count=12),
        ]
    )

    assert result.decisions[0].action == "REDUCE"
    assert result.decisions[0].decision_trace[0].matched_rule == "REDUCE_BOS_DOWN_LONG_CONTEXT_ONLY"


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
