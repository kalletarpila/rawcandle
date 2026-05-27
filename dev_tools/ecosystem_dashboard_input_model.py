from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EcosystemDashboardSourceReportInput:
    source_report_path: str | None
    source_report_type: str | None
    source_report_date: str | None
    loaded_row_count: int | None
    status: str | None


@dataclass(frozen=True)
class EcosystemDashboardActionSummaryInput:
    action_bucket: str | None
    action_label: str | None
    ticker_count: int | None
    weight_sum: float | None
    notes: str | None


@dataclass(frozen=True)
class EcosystemDashboardMarketMapInput:
    layer_order: int | None
    subindustry_order: int | None
    layer_name: str | None
    subindustry_name: str | None
    ticker_count: int | None
    watchlist_count: int | None
    avg_return_5d: float | None
    avg_return_20d: float | None
    avg_return_60d: float | None
    avg_trend_score: float | None
    avg_action_score: float | None
    dominant_action_bucket: str | None
    market_level: str | None = None
    name: str | None = None
    parent_name: str | None = None
    taxonomy_path: str | None = None


@dataclass(frozen=True)
class EcosystemDashboardWatchlistInput:
    ticker: str
    company_name: str | None
    layer_name: str | None
    subindustry_name: str | None
    action_bucket: str | None
    action_label: str | None
    watchlist_reason: str | None
    last_close: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    trend_state: str | None
    latest_structure_label: str | None
    latest_bos_event_type: str | None
    latest_reset_reason: str | None
    bullish_candle_signal: int | None
    bullish_divergence_signal: int | None
    hidden_bullish_divergence_signal: int | None
    data_status: str | None


@dataclass(frozen=True)
class EcosystemDashboardTickerStatusInput:
    ticker: str
    company_name: str | None
    layer_name: str | None
    subindustry_name: str | None
    last_close: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    trend_state: str | None
    latest_structure_label: str | None
    latest_bos_event_type: str | None
    latest_bos_freshness: str | None
    latest_reset_reason: str | None
    latest_reset_freshness: str | None
    bullish_candle_signal: int | None
    bullish_divergence_signal: int | None
    hidden_bullish_divergence_signal: int | None
    pullback_validity: str | None = None
    entry_readiness: str | None = None
    candidate_priority: int | None = None
    candidate_priority_label: str | None = None
    action_bucket: str | None = None
    action_label: str | None = None
    data_status: str | None = None


@dataclass(frozen=True)
class EcosystemDashboardDecisionTraceInput:
    ticker: str
    trace_order: int
    rule_group: str | None
    rule_name: str | None
    input_value: str | None
    decision: str | None
    reason: str | None


@dataclass(frozen=True)
class EcosystemDashboardInput:
    ecosystem_code: str
    report_date: str
    source_reports: list[EcosystemDashboardSourceReportInput]
    action_summary: list[EcosystemDashboardActionSummaryInput]
    market_map: list[EcosystemDashboardMarketMapInput]
    watchlist: list[EcosystemDashboardWatchlistInput]
    tickers: list[EcosystemDashboardTickerStatusInput]
    decision_trace: list[EcosystemDashboardDecisionTraceInput]
    readiness: str | None
    total_parsed_rows: int | None
    total_parse_warnings: int | None
