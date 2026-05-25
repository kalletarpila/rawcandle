from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from dev_tools.datacenter_dashboard_decisions import build_datacenter_ticker_decisions
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardBatchParseResult,
    DatacenterDashboardParseResult,
    DatacenterDashboardReportParseSummary,
    DatacenterDashboardRow,
    parse_datacenter_dashboard_text,
)
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    DatacenterReportStatus,
)
from dev_tools.ecosystem_dashboard_input_model import EcosystemDashboardInput
from dev_tools.ecosystem_dashboard_reports_adapter import (
    build_ecosystem_dashboard_input_from_reports_result,
)
from dev_tools.ecosystem_dashboard_structured_json import (
    dump_ecosystem_dashboard_input_json,
)
from dev_tools.run_datacenter_dashboard_html import (
    DatacenterDashboardMarketMapRecord,
    build_dashboard_ticker_model,
    build_dashboard_watchlist_model,
)


@dataclass(frozen=True)
class DatacenterStructuredExportReport:
    horizon: str
    markdown_path: str
    csv_text: str
    report_data: Mapping[str, object]


def _required_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"structured export requires non-empty {label}")
    return value.strip()


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object | None) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _parse_report_rows(
    reports: Sequence[DatacenterStructuredExportReport],
) -> tuple[list[DatacenterDashboardRow], DatacenterDashboardBatchParseResult]:
    parsed_rows: list[DatacenterDashboardRow] = []
    summaries: list[DatacenterDashboardReportParseSummary] = []
    total_warnings = 0

    for report in reports:
        parse_result: DatacenterDashboardParseResult = parse_datacenter_dashboard_text(
            text=report.csv_text,
            horizon=report.horizon,
            source_file=report.markdown_path,
        )
        parsed_rows.extend(parse_result.rows)
        warning_count = len(parse_result.warnings)
        total_warnings += warning_count
        summaries.append(
            DatacenterDashboardReportParseSummary(
                horizon=report.horizon,
                source_file=report.markdown_path,
                row_count=len(parse_result.rows),
                warning_count=warning_count,
            )
        )

    return parsed_rows, DatacenterDashboardBatchParseResult(
        reports=summaries,
        total_row_count=len(parsed_rows),
        total_warning_count=total_warnings,
    )


def _daily_market_map_records(
    *,
    daily_report: DatacenterStructuredExportReport,
) -> list[DatacenterDashboardMarketMapRecord]:
    group_rows = list(daily_report.report_data.get("group_rows") or [])
    ticker_rows = list(daily_report.report_data.get("ticker_rows") or [])
    subindustry_to_layer: dict[str, str] = {}
    for row in ticker_rows:
        if not isinstance(row, Mapping):
            continue
        subindustry_name = _optional_text(row.get("primary_subindustry"))
        layer_name = _optional_text(row.get("primary_layer"))
        if subindustry_name and layer_name and subindustry_name not in subindustry_to_layer:
            subindustry_to_layer[subindustry_name] = layer_name

    records: list[DatacenterDashboardMarketMapRecord] = []
    for row in group_rows:
        if not isinstance(row, Mapping):
            continue
        group_type = _required_text(row.get("group_type"), label="daily group_rows.group_type")
        group_name = _required_text(row.get("group_name"), label="daily group_rows.group_name")
        if group_type not in {"ecosystem", "layer", "subindustry"}:
            continue
        layer_name = None
        subindustry_name = None
        market_level = group_type.upper()
        if group_type == "layer":
            layer_name = group_name
        elif group_type == "subindustry":
            layer_name = subindustry_to_layer.get(group_name)
            subindustry_name = group_name
        record_name = subindustry_name or group_name
        records.append(
            DatacenterDashboardMarketMapRecord(
                market_level=market_level,
                name=record_name,
                layer=layer_name,
                current_status=_optional_text(row.get("timing_state")),
                start_status_30d=None,
                status_change_30d=None,
                status_change_5d=None,
                window_status_30d=None,
                window_status_5d=None,
                window_status_2d=None,
                overheat_risk=_optional_text(row.get("overheat_risk_level")),
                pct_above_ema20=_optional_float(row.get("pct_above_ema20")),
                pct_above_ma10=_optional_float(row.get("pct_above_ma10")),
                ema20_breadth_delta_5d=_optional_float(row.get("ema20_breadth_delta_5d")),
                return_5d=_optional_float(row.get("return_5d")),
                return_10d=_optional_float(row.get("return_10d")),
                return_20d=_optional_float(row.get("return_20d")),
                return_60d=_optional_float(row.get("return_60d")),
                dow_trend_state=None,
                dow_trend_state_age_td=None,
                latest_structure_label=None,
                latest_structure_age_td=None,
                latest_bos_event_type=None,
                latest_bos_age_td=None,
                latest_reset_reason=None,
                latest_reset_age_td=None,
                latest_candle=None,
                latest_candle_age_td=None,
                latest_divergence=None,
                latest_divergence_age_td=None,
                latest_chart_pattern=None,
                latest_chart_pattern_age_td=None,
                source_horizons="daily",
                source_files=daily_report.markdown_path,
            )
        )

    return sorted(
        records,
        key=lambda record: (
            {"ECOSYSTEM": 0, "LAYER": 1, "SUBINDUSTRY": 2}.get(record.market_level, 99),
            record.layer or "",
            record.name,
        ),
    )


def _build_dashboard_status(
    reports: Sequence[DatacenterStructuredExportReport],
) -> DatacenterDashboardStatus:
    return DatacenterDashboardStatus(
        overall_status="READY",
        reports=[
            DatacenterReportStatus(
                horizon=report.horizon,
                status="OK",
                path=report.markdown_path,
                modified_at=None,
            )
            for report in reports
        ],
    )


def build_datacenter_dashboard_input_from_pipeline_reports(
    *,
    ecosystem_code: str,
    report_date: str,
    reports_dir: str,
    daily_report: DatacenterStructuredExportReport,
    rolling_30_report: DatacenterStructuredExportReport,
    rolling_5_report: DatacenterStructuredExportReport,
    rolling_2_report: DatacenterStructuredExportReport,
) -> tuple[EcosystemDashboardInput, list[str]]:
    reports = [daily_report, rolling_30_report, rolling_5_report, rolling_2_report]
    parsed_rows, parse_result = _parse_report_rows(reports)
    if not parsed_rows:
        raise ValueError(
            "structured export could not produce dashboard rows from in-memory report CSV text"
        )

    decision_result = build_datacenter_ticker_decisions(parsed_rows)
    market_map_rows = _daily_market_map_records(daily_report=daily_report)
    watchlist_rows = build_dashboard_watchlist_model(parsed_rows, decision_result.decisions)
    ticker_rows = build_dashboard_ticker_model(parsed_rows, decision_result.decisions)
    dashboard_input = build_ecosystem_dashboard_input_from_reports_result(
        ecosystem_code=ecosystem_code,
        report_date=report_date,
        reports_dir=reports_dir,
        dashboard_status=_build_dashboard_status(reports),
        parse_result=parse_result,
        decision_result=decision_result,
        market_map_rows=market_map_rows,
        watchlist_rows=watchlist_rows,
        ticker_rows=ticker_rows,
    )
    summary_lines = [
        "SUMMARY datacenter_dashboard_structured_export.status=OK",
        f"SUMMARY datacenter_dashboard_structured_export.ecosystem_code={ecosystem_code}",
        f"SUMMARY datacenter_dashboard_structured_export.report_date={report_date}",
        f"SUMMARY datacenter_dashboard_structured_export.source_reports={len(dashboard_input.source_reports)}",
        f"SUMMARY datacenter_dashboard_structured_export.action_summary={len(dashboard_input.action_summary)}",
        f"SUMMARY datacenter_dashboard_structured_export.market_map={len(dashboard_input.market_map)}",
        f"SUMMARY datacenter_dashboard_structured_export.watchlist={len(dashboard_input.watchlist)}",
        f"SUMMARY datacenter_dashboard_structured_export.tickers={len(dashboard_input.tickers)}",
        f"SUMMARY datacenter_dashboard_structured_export.decision_trace={len(dashboard_input.decision_trace)}",
    ]
    return dashboard_input, summary_lines


def write_datacenter_dashboard_input_json_from_pipeline_reports(
    *,
    ecosystem_code: str,
    report_date: str,
    reports_dir: str,
    output_json: str,
    daily_report: DatacenterStructuredExportReport,
    rolling_30_report: DatacenterStructuredExportReport,
    rolling_5_report: DatacenterStructuredExportReport,
    rolling_2_report: DatacenterStructuredExportReport,
) -> tuple[EcosystemDashboardInput, list[str]]:
    dashboard_input, summary_lines = build_datacenter_dashboard_input_from_pipeline_reports(
        ecosystem_code=ecosystem_code,
        report_date=report_date,
        reports_dir=reports_dir,
        daily_report=daily_report,
        rolling_30_report=rolling_30_report,
        rolling_5_report=rolling_5_report,
        rolling_2_report=rolling_2_report,
    )
    dump_ecosystem_dashboard_input_json(dashboard_input, output_json)
    return dashboard_input, [
        *summary_lines[:3],
        f"SUMMARY datacenter_dashboard_structured_export.output_json={output_json}",
        *summary_lines[3:],
    ]