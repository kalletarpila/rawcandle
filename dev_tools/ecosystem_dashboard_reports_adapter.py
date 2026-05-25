from __future__ import annotations

from dataclasses import dataclass

from dev_tools.datacenter_dashboard_decisions import DatacenterDecisionBatchResult
from dev_tools.datacenter_dashboard_parser import DatacenterDashboardBatchParseResult
from dev_tools.datacenter_dashboard_support import DatacenterDashboardStatus
from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardDecisionTraceInput,
    EcosystemDashboardInput,
    EcosystemDashboardMarketMapInput,
    EcosystemDashboardSourceReportInput,
    EcosystemDashboardTickerStatusInput,
    EcosystemDashboardWatchlistInput,
)
from dev_tools.run_datacenter_dashboard_html import (
    DatacenterDashboardMarketMapRecord,
    DatacenterDashboardTickerRecord,
    DatacenterDashboardWatchlistRecord,
)

ACTION_ORDER = (
    "SELL",
    "REDUCE",
    "TIGHTEN_STOP",
    "BLOCKED",
    "WAIT_PULLBACK",
    "BUY_NOW",
    "WATCH",
    "NEUTRAL",
)


@dataclass(frozen=True)
class ReportsPersistenceContext:
    reports_dir: str
    dashboard_status: DatacenterDashboardStatus
    parse_result: DatacenterDashboardBatchParseResult
    decision_result: DatacenterDecisionBatchResult
    market_map_rows: list[DatacenterDashboardMarketMapRecord]
    watchlist_rows: list[DatacenterDashboardWatchlistRecord]
    ticker_rows: list[DatacenterDashboardTickerRecord]


_PERSISTENCE_CONTEXT_BY_INPUT_ID: dict[int, ReportsPersistenceContext] = {}


def build_ecosystem_dashboard_input_from_reports_result(
    *,
    ecosystem_code: str,
    report_date: str,
    reports_dir: str,
    dashboard_status: DatacenterDashboardStatus,
    parse_result: DatacenterDashboardBatchParseResult,
    decision_result: DatacenterDecisionBatchResult,
    market_map_rows: list[DatacenterDashboardMarketMapRecord],
    watchlist_rows: list[DatacenterDashboardWatchlistRecord],
    ticker_rows: list[DatacenterDashboardTickerRecord],
) -> EcosystemDashboardInput:
    dashboard_input = EcosystemDashboardInput(
        ecosystem_code=ecosystem_code,
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path=report.path,
                source_report_type=report.horizon,
                source_report_date=report_date,
                loaded_row_count=None,
                status=report.status,
            )
            for report in dashboard_status.reports
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket=action,
                action_label=action,
                ticker_count=decision_result.action_counts.get(action, 0),
                weight_sum=None,
                notes=None,
            )
            for action in ACTION_ORDER
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=None,
                subindustry_order=None,
                layer_name=row.layer,
                subindustry_name=row.name if row.market_level == "SUBINDUSTRY" else None,
                ticker_count=None,
                watchlist_count=None,
                avg_return_5d=row.return_5d,
                avg_return_20d=row.return_20d,
                avg_return_60d=row.return_60d,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=row.current_status,
            )
            for row in market_map_rows
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker=row.ticker,
                company_name=None,
                layer_name=None,
                subindustry_name=None,
                action_bucket=row.action,
                action_label=row.severity,
                watchlist_reason=row.primary_reason,
                last_close=None,
                return_5d=None,
                return_20d=None,
                return_60d=None,
                trend_state=row.trend_state,
                latest_structure_label=row.latest_structure_label,
                latest_bos_event_type=row.latest_bos_event_type,
                latest_reset_reason=row.latest_reset_reason,
                bullish_candle_signal=row.latest_candle_age_td,
                bullish_divergence_signal=row.latest_divergence_age_td,
                hidden_bullish_divergence_signal=row.latest_chart_pattern_age_td,
                data_status=row.current_status,
            )
            for row in watchlist_rows
        ],
        tickers=[
            EcosystemDashboardTickerStatusInput(
                ticker=row.ticker,
                company_name=None,
                layer_name=None,
                subindustry_name=None,
                last_close=None,
                return_5d=None,
                return_20d=None,
                return_60d=None,
                trend_state=row.trend_state,
                latest_structure_label=row.latest_structure_label,
                latest_bos_event_type=row.latest_bos_event_type,
                latest_bos_freshness=row.freshness_status,
                latest_reset_reason=row.latest_reset_reason,
                latest_reset_freshness=row.freshness_status,
                bullish_candle_signal=row.latest_candle_age_td,
                bullish_divergence_signal=row.latest_divergence_age_td,
                hidden_bullish_divergence_signal=row.latest_chart_pattern_age_td,
                action_bucket=row.action,
                action_label=row.severity,
                data_status=row.current_status,
            )
            for row in ticker_rows
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker=decision.ticker,
                trace_order=trace_index,
                rule_group=trace.horizon,
                rule_name=trace.matched_rule,
                input_value=trace.matched_value,
                decision=trace.action,
                reason=trace.field_name,
            )
            for decision in decision_result.decisions
            for trace_index, trace in enumerate(decision.decision_trace)
        ],
        readiness=dashboard_status.overall_status,
        total_parsed_rows=parse_result.total_row_count,
        total_parse_warnings=parse_result.total_warning_count,
    )
    _PERSISTENCE_CONTEXT_BY_INPUT_ID[id(dashboard_input)] = ReportsPersistenceContext(
        reports_dir=reports_dir,
        dashboard_status=dashboard_status,
        parse_result=parse_result,
        decision_result=decision_result,
        market_map_rows=list(market_map_rows),
        watchlist_rows=list(watchlist_rows),
        ticker_rows=list(ticker_rows),
    )
    return dashboard_input


def peek_reports_persistence_context(
    dashboard_input: EcosystemDashboardInput,
) -> ReportsPersistenceContext | None:
    return _PERSISTENCE_CONTEXT_BY_INPUT_ID.get(id(dashboard_input))


def clear_reports_persistence_context(
    dashboard_input: EcosystemDashboardInput,
) -> None:
    _PERSISTENCE_CONTEXT_BY_INPUT_ID.pop(id(dashboard_input), None)
