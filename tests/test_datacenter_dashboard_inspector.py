from __future__ import annotations

from dev_tools.datacenter_dashboard_decisions import build_datacenter_ticker_decisions
from dev_tools.datacenter_dashboard_inspector import (
    build_datacenter_ticker_inspector_view,
)
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


def _inspector(rows: list[DatacenterDashboardRow], ticker: str):
    decision = next(
        item for item in build_datacenter_ticker_decisions(rows).decisions if item.ticker == ticker
    )
    return build_datacenter_ticker_inspector_view(decision=decision, rows=rows)


def test_sell_with_bos_down_and_pullback_candidate_reports_conflict():
    inspector = _inspector(
        [
            _row(ticker="NVDA", horizon="daily", reason="close_below_ema20", latest_bos_event_type="BOS_DOWN"),
            _row(ticker="NVDA", horizon="rolling 5d", raw_status="PULLBACK_CANDIDATE"),
        ],
        "NVDA",
    )

    assert "BOS_DOWN" in inspector.supporting_signals
    assert "PULLBACK_CANDIDATE" in inspector.conflicting_signals
    assert inspector.conflict_detected is True
    assert inspector.override_explanation == (
        "Bearish structural/risk signals override constructive pullback labels."
    )


def test_blocked_with_buy_zone_conflict_reports_blocking_override():
    inspector = _inspector(
        [
            _row(ticker="META", horizon="rolling 30d", raw_status="BUY_ZONE", blocking_reasons="STRUCTURAL_BLOCK"),
        ],
        "META",
    )

    assert inspector.action == "BLOCKED"
    assert inspector.supporting_signals == ["STRUCTURAL_BLOCK"]
    assert "BUY_ZONE" in inspector.conflicting_signals
    assert inspector.override_explanation == (
        "Blocking reasons override constructive setup labels."
    )


def test_wait_pullback_reports_stretched_distance_explanation():
    inspector = _inspector(
        [
            _row(ticker="TSM", horizon="rolling 30d", raw_status="BUY_ZONE", distance_to_ema20=16.2),
        ],
        "TSM",
    )

    assert inspector.action == "WAIT_PULLBACK"
    assert "rolling 30d positive context" in inspector.supporting_signals
    assert "distance_to_ema20>15.0" in inspector.supporting_signals
    assert inspector.override_explanation == (
        "Constructive setup is present, but EMA20 distance is stretched."
    )


def test_buy_now_with_constructive_alignment_has_support_without_bearish_conflicts():
    inspector = _inspector(
        [
            _row(ticker="AMD", horizon="rolling 30d", raw_status="BUY_ZONE"),
            _row(ticker="AMD", horizon="rolling 5d", raw_status="PULLBACK"),
            _row(ticker="AMD", horizon="daily", raw_status="BULLISH"),
        ],
        "AMD",
    )

    assert inspector.action == "BUY_NOW"
    assert inspector.supporting_signals == [
        "rolling 30d positive context",
        "rolling 5d constructive context",
        "daily positive trigger",
    ]
    assert inspector.conflicting_signals == []
    assert inspector.conflict_detected is False


def test_no_conflict_case_is_deterministic():
    inspector = _inspector(
        [_row(ticker="INTC", horizon="daily", raw_status="SIDEWAYS")],
        "INTC",
    )

    assert inspector.action == "NEUTRAL"
    assert inspector.supporting_signals == []
    assert inspector.conflicting_signals == []
    assert inspector.override_explanation is None
    assert inspector.conflict_detected is False


def test_explanation_generation_does_not_change_final_action():
    rows = [
        _row(ticker="AVGO", horizon="daily", reason="exit_risk"),
        _row(ticker="AVGO", horizon="rolling 30d", raw_status="BUY_ZONE"),
    ]
    decision = next(item for item in build_datacenter_ticker_decisions(rows).decisions if item.ticker == "AVGO")
    inspector = build_datacenter_ticker_inspector_view(decision=decision, rows=rows)

    assert decision.action == "REDUCE"
    assert inspector.action == "REDUCE"


def test_supporting_and_conflicting_signal_order_is_deterministic():
    inspector = _inspector(
        [
            _row(
                ticker="SMCI",
                horizon="daily",
                reason="close_below_ema20 return_10d_lt_minus_8pct",
                latest_bos_event_type="DOUBLE_BOS_DOWN",
            ),
            _row(
                ticker="SMCI",
                horizon="rolling 5d",
                raw_status="BUY_ZONE PULLBACK_CANDIDATE BULLISH",
            ),
        ],
        "SMCI",
    )

    assert inspector.supporting_signals == [
        "close_below_ema20",
        "return_10d_lt_minus_8pct",
        "DOUBLE_BOS_DOWN",
    ]
    assert inspector.conflicting_signals == [
        "PULLBACK_CANDIDATE",
        "BUY_ZONE",
        "BULLISH",
    ]


def test_inspector_exposes_structure_blocked_pullback_fields():
    inspector = _inspector(
        [
            _row(
                ticker="NVDA",
                horizon="rolling 2d",
                raw_status="PULLBACK_CANDIDATE",
                latest_bos_event_type="BOS_DOWN",
                raw_fields={"latest_bos_freshness": "FRESH"},
            ),
        ],
        "NVDA",
    )

    assert inspector.pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"
    assert inspector.pullback_reason == "FRESH_BOS_DOWN_BLOCKS_PULLBACK"


def test_inspector_exposes_no_pullback_fields_when_context_missing():
    inspector = _inspector(
        [_row(ticker="INTC", horizon="daily", raw_status="SIDEWAYS")],
        "INTC",
    )

    assert inspector.pullback_validity == "NO_PULLBACK"
    assert inspector.pullback_reason == "NO_PULLBACK_CONTEXT"
