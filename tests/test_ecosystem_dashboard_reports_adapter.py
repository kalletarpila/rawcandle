from __future__ import annotations

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionBatchResult,
    DatacenterDecisionTrace,
    DatacenterTickerDecision,
)
from dev_tools.datacenter_dashboard_parser import DatacenterDashboardBatchParseResult
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    DatacenterReportStatus,
)
from dev_tools.ecosystem_dashboard_reports_adapter import (
    build_ecosystem_dashboard_input_from_reports_result,
    clear_reports_persistence_context,
    peek_reports_persistence_context,
)
from dev_tools.run_datacenter_dashboard_html import (
    DatacenterDashboardMarketMapRecord,
    DatacenterDashboardTickerRecord,
    DatacenterDashboardWatchlistRecord,
)


def _decision_result() -> DatacenterDecisionBatchResult:
    return DatacenterDecisionBatchResult(
        decisions=[
            DatacenterTickerDecision(
                ticker="NVDA",
                action="SELL",
                severity="CRITICAL",
                primary_reason="close_below_ema20",
                reasons=["close_below_ema20"],
                blocking_reasons=[],
                horizons_present=["daily", "rolling 30d"],
                horizon_statuses={"daily": "BREAKOUT_READY", "rolling 30d": "WATCH"},
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason=None,
                latest_bullish_signal_age_td=3,
                latest_bearish_signal_age_td=1,
                pullback_validity="NO_PULLBACK",
                pullback_reason="not a pullback",
                entry_readiness="NOT_READY",
                entry_readiness_reason="risk",
                candidate_priority=5,
                candidate_priority_label="P5_NOT_READY",
                candidate_priority_reason="risk",
                source_files=["daily.csv", "rolling30.csv"],
                decision_trace=[
                    DatacenterDecisionTrace(
                        ticker="NVDA",
                        action="SELL",
                        matched_rule="SELL_HARD_TOKEN",
                        horizon="daily",
                        field_name="reason",
                        matched_token="close_below_ema20",
                        matched_value="close_below_ema20",
                        source_file="daily.csv",
                        section="Watchlist Summary",
                        row_kind="watchlist",
                    )
                ],
            )
        ],
        action_counts={
            "SELL": 1,
            "REDUCE": 0,
            "TIGHTEN_STOP": 0,
            "BLOCKED": 0,
            "WAIT_PULLBACK": 0,
            "BUY_NOW": 0,
            "WATCH": 0,
            "NEUTRAL": 0,
        },
        pullback_counts={},
        pullback_action_counts={},
        entry_readiness_counts={},
        candidate_priority_counts={},
        warning_count=0,
        warnings=[],
    )


def test_build_ecosystem_dashboard_input_from_reports_result_preserves_key_fields():
    dashboard_status = DatacenterDashboardStatus(
        overall_status="PARTIAL",
        reports=[
            DatacenterReportStatus(
                horizon="daily",
                status="OK",
                path="/tmp/reports/datacenter_daily_2026-05-22_0000_full.csv",
                modified_at="2026-05-25T12:00:00",
            ),
            DatacenterReportStatus(
                horizon="rolling 30d",
                status="MISSING",
                path=None,
                modified_at=None,
            ),
        ],
    )
    parse_result = DatacenterDashboardBatchParseResult(
        reports=[],
        total_row_count=17,
        total_warning_count=2,
    )
    market_map_rows = [
        DatacenterDashboardMarketMapRecord(
            market_level="SUBINDUSTRY",
            name="Semiconductors",
            layer="Technology",
            current_status="BUY_ZONE",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BUY_ZONE",
            status_change_5d=None,
            window_status_30d="BUY_ZONE",
            window_status_5d=None,
            window_status_2d=None,
            overheat_risk="LOW",
            pct_above_ema20=70.0,
            pct_above_ma10=65.0,
            ema20_breadth_delta_5d=5.0,
            return_5d=0.2,
            return_10d=0.3,
            return_20d=0.4,
            return_60d=0.8,
            dow_trend_state="UP",
            dow_trend_state_age_td=6,
            latest_structure_label="HL",
            latest_structure_age_td=2,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=1,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle=None,
            latest_candle_age_td=None,
            latest_divergence=None,
            latest_divergence_age_td=None,
            latest_chart_pattern="PULLBACK",
            latest_chart_pattern_age_td=2,
            source_horizons="rolling 30d",
            source_files="rolling30.md",
        )
    ]
    watchlist_rows = [
        DatacenterDashboardWatchlistRecord(
            ticker="NVDA",
            action="SELL",
            severity="CRITICAL",
            primary_reason="close_below_ema20",
            current_status="BREAKOUT_READY",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BREAKOUT_READY",
            status_change_5d="PULLBACK_WINDOW -> BREAKOUT_READY",
            window_status_30d="WATCH",
            window_status_5d="PULLBACK_WINDOW",
            window_status_2d="BREAKOUT_READY",
            ma_break_status="EMA20_WARNING",
            freshness_status="FRESH_BULLISH_SIGNAL",
            trend_state="UP",
            trend_state_age_td=12,
            latest_structure_label="HH",
            latest_structure_age_td=3,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=2,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle="Hammer",
            latest_candle_age_td=4,
            latest_divergence="Bearish Divergence",
            latest_divergence_age_td=2,
            latest_chart_pattern="BASE_BREAKOUT",
            latest_chart_pattern_age_td=5,
            pullback_validity="NO_PULLBACK",
            entry_readiness="NOT_READY",
            candidate_priority=5,
            candidate_priority_label="P5_NOT_READY",
            daily_status="BREAKOUT_READY",
            rolling_2d_status=None,
            rolling_5d_status=None,
            rolling_30d_status="WATCH",
            horizons_present="daily, rolling 30d",
            source_files=2,
        )
    ]
    ticker_rows = [
        DatacenterDashboardTickerRecord(
            ticker="AMD",
            action="WATCH",
            severity="LOW",
            primary_reason="trend_ok",
            current_status="BUY_ZONE",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BUY_ZONE",
            status_change_5d=None,
            window_status_30d="BUY_ZONE",
            window_status_5d=None,
            window_status_2d=None,
            ma_break_status="OK",
            freshness_status="FRESH_BULLISH_SIGNAL",
            trend_state="UP",
            trend_state_age_td=7,
            latest_structure_label="HL",
            latest_structure_age_td=2,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=1,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle=None,
            latest_candle_age_td=None,
            latest_divergence=None,
            latest_divergence_age_td=None,
            latest_chart_pattern="PULLBACK",
            latest_chart_pattern_age_td=2,
            pullback_validity="VALID_PULLBACK",
            entry_readiness="READY_TO_WATCH",
            candidate_priority=1,
            candidate_priority_label="P1_READY_TO_WATCH",
            daily_status=None,
            rolling_2d_status=None,
            rolling_5d_status=None,
            rolling_30d_status="BUY_ZONE",
            horizons_present="rolling 30d",
            source_files=1,
            is_watchlist=0,
        )
    ]

    dashboard_input = build_ecosystem_dashboard_input_from_reports_result(
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
        reports_dir="/tmp/reports",
        dashboard_status=dashboard_status,
        parse_result=parse_result,
        decision_result=_decision_result(),
        market_map_rows=market_map_rows,
        watchlist_rows=watchlist_rows,
        ticker_rows=ticker_rows,
    )

    assert dashboard_input.ecosystem_code == "DATACENTER"
    assert dashboard_input.report_date == "2026-05-22"
    assert dashboard_input.readiness == "PARTIAL"
    assert dashboard_input.total_parsed_rows == 17
    assert dashboard_input.total_parse_warnings == 2
    assert len(dashboard_input.source_reports) == 2
    assert dashboard_input.source_reports[0].source_report_type == "daily"
    assert dashboard_input.source_reports[1].status == "MISSING"
    assert len(dashboard_input.action_summary) == 8
    assert dashboard_input.action_summary[0].action_bucket == "SELL"
    assert dashboard_input.action_summary[0].ticker_count == 1
    assert len(dashboard_input.market_map) == 1
    assert dashboard_input.market_map[0].layer_name == "Technology"
    assert dashboard_input.market_map[0].subindustry_name == "Semiconductors"
    assert len(dashboard_input.watchlist) == 1
    assert dashboard_input.watchlist[0].ticker == "NVDA"
    assert dashboard_input.watchlist[0].latest_structure_label == "HH"
    assert len(dashboard_input.tickers) == 1
    assert dashboard_input.tickers[0].ticker == "AMD"
    assert dashboard_input.tickers[0].action_bucket == "WATCH"
    assert len(dashboard_input.decision_trace) == 1
    assert dashboard_input.decision_trace[0].ticker == "NVDA"
    assert dashboard_input.decision_trace[0].rule_name == "SELL_HARD_TOKEN"

    context = peek_reports_persistence_context(dashboard_input)
    assert context is not None
    assert context.reports_dir == "/tmp/reports"
    clear_reports_persistence_context(dashboard_input)
    assert peek_reports_persistence_context(dashboard_input) is None
