from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import re
from typing import Sequence

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionBatchResult,
    DatacenterTickerDecision,
    build_datacenter_ticker_decisions,
)
from dev_tools.datacenter_dashboard_inspector import (
    DatacenterTickerInspectorView,
    build_datacenter_ticker_inspector_view,
)
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardBatchParseResult,
    DatacenterDashboardReportParseSummary,
    DatacenterDashboardRow,
    parse_datacenter_dashboard_file,
    parse_datacenter_dashboard_reports,
)
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    DatacenterReportStatus,
    discover_datacenter_dashboard_status,
)

_ACTION_ORDER = (
    "SELL",
    "REDUCE",
    "TIGHTEN_STOP",
    "BLOCKED",
    "WAIT_PULLBACK",
    "BUY_NOW",
    "WATCH",
    "NEUTRAL",
)
_PULLBACK_ORDER = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK",
    "INSUFFICIENT_DATA",
)
_ENTRY_READINESS_ORDER = (
    "READY_TO_WATCH",
    "NEEDS_STOP_STABILIZATION",
    "NEEDS_RISK_CLEARANCE",
    "EARLY_MONITOR",
    "NOT_READY",
    "INSUFFICIENT_DATA",
)
_CANDIDATE_PRIORITY_LABEL_ORDER = (
    "P1_READY_TO_WATCH",
    "P2_STOP_STABILIZATION",
    "P3_RISK_CLEARANCE",
    "P4_EARLY_MONITOR",
    "P5_NOT_READY",
    "P9_NOT_CANDIDATE",
)
_CANDIDATE_PULLBACK_ORDER = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
)
_CANDIDATE_ACTION_ORDER = (
    "WATCH",
    "NEUTRAL",
    "TIGHTEN_STOP",
    "REDUCE",
    "SELL",
    "BLOCKED",
    "WAIT_PULLBACK",
    "BUY_NOW",
)
_HORIZON_PRIORITY = {
    "daily": 0,
    "rolling 2d": 1,
    "rolling 5d": 2,
    "rolling 30d": 3,
}
_COMMAND_CENTER_GROUPS = (
    ("Critical exits", ("SELL", "REDUCE", "TIGHTEN_STOP")),
    ("Buy candidates", ("BUY_NOW", "WATCH", "WAIT_PULLBACK")),
    ("Blocked / neutral", ("BLOCKED", "NEUTRAL")),
)
_SOURCE_FILE_HORIZON_ORDER = ("rolling 30d", "rolling 5d", "rolling 2d", "daily")
_WATCHLIST_SECTION_NAME = "watchlist summary"
_REPORT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MARKDOWN_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*$")
_MARKET_MAP_EMPTY = "No market map rows found in the selected reports."


@dataclass(frozen=True)
class _MarkdownTable:
    section: str | None
    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class _MarketMapRow:
    scope: str
    horizon: str
    name: str
    layer: str
    subindustry: str
    current_status: str
    window_status: str
    overheat_risk_level: str
    pct_above_ema20: str
    pct_above_ma10: str
    ema20_breadth_delta_5d: str
    return_5d: str
    return_10d: str
    return_20d: str
    return_60d: str
    source_file: str


@dataclass(frozen=True)
class _EcosystemContextRow:
    horizon: str
    name: str
    current_status: str
    start_status_30d: str
    overheat_risk_level: str
    pct_above_ema20: str
    pct_above_ma10: str
    ema20_breadth_delta_5d: str
    return_5d: str
    return_10d: str
    return_20d: str
    return_60d: str
    dow_trend_state: str
    latest_structure_label: str
    latest_bos_event_type: str
    latest_reset_reason: str
    latest_relevant_pattern: str
    latest_relevant_pattern_age_td: str
    source_file: str


@dataclass(frozen=True)
class _CombinedEcosystemRow:
    name: str
    current_status: str
    start_status_30d: str
    status_change_30d: str
    overheat_risk_level: str
    pct_above_ema20: str
    pct_above_ma10: str
    ema20_breadth_delta_5d: str
    return_5d: str
    return_10d: str
    return_20d: str
    return_60d: str
    dow_trend_state: str
    latest_structure_label: str
    latest_bos_event_type: str
    latest_reset_reason: str
    latest_relevant_pattern: str
    latest_relevant_pattern_age_td: str
    source_horizons: str
    source_files: str


@dataclass(frozen=True)
class DatacenterDashboardHtmlGenerationResult:
    output_path: str
    report_date: str
    selection_mode: str
    readiness: str
    found_reports: int
    missing_reports: int
    decision_total: int
    candidate_pullback_rows: int
    summary_lines: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a static HTML Datacenter Dashboard from the latest reports."
    )
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--output")
    parser.add_argument("--report-date")
    parser.add_argument("--ticker")
    parser.add_argument("--max-command-rows", type=int, default=200)
    parser.add_argument("--max-candidate-rows", type=int, default=100)
    parser.add_argument("--title", default="Datacenter Dashboard")
    return parser


def resolve_dashboard_html_output_path(
    *,
    reports_dir: str,
    output: str | None,
    report_date: str | None,
) -> Path:
    if output:
        return Path(output)
    reports_dir_path = Path(reports_dir)
    if report_date:
        return reports_dir_path / f"datacenter_dashboard_{report_date}.html"
    return reports_dir_path / "datacenter_dashboard.html"


def _safe_text(value: object | None, *, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text if text else fallback


def _safe_attr(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


def _html_text(value: object | None, *, fallback: str = "-") -> str:
    return escape(_safe_text(value, fallback=fallback))


def _html_attr(value: object | None) -> str:
    return escape(_safe_attr(value), quote=True)


def _normalize_md_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _collect_rows(dashboard_status: DatacenterDashboardStatus) -> list[DatacenterDashboardRow]:
    parsed_rows: list[DatacenterDashboardRow] = []
    for report in dashboard_status.reports:
        if not report.path:
            continue
        parsed_rows.extend(
            parse_datacenter_dashboard_file(
                path=report.path,
                horizon=report.horizon,
            ).rows
        )
    return parsed_rows


def _parse_markdown_tables(path: str) -> list[_MarkdownTable]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    lines = text.splitlines()
    tables: list[_MarkdownTable] = []
    current_section: str | None = None
    line_index = 0
    while line_index < len(lines):
        current_line = lines[line_index].strip()
        heading_match = _MARKDOWN_HEADING_RE.match(current_line)
        if heading_match:
            current_section = heading_match.group(1).strip() or current_section
            line_index += 1
            continue
        if "|" not in current_line or line_index + 1 >= len(lines):
            line_index += 1
            continue
        separator_line = lines[line_index + 1].strip()
        if not _MARKDOWN_SEPARATOR_RE.match(separator_line):
            line_index += 1
            continue
        headers = tuple(
            _normalize_md_header(cell)
            for cell in current_line.strip("|").split("|")
        )
        line_index += 2
        rows: list[dict[str, str]] = []
        while line_index < len(lines):
            row_line = lines[line_index].strip()
            if not row_line or "|" not in row_line:
                break
            values = [cell.strip() for cell in row_line.strip("|").split("|")]
            padded_values = values[: len(headers)] + [""] * max(0, len(headers) - len(values))
            rows.append(
                {
                    header: value.strip()
                    for header, value in zip(headers, padded_values)
                }
            )
            line_index += 1
        tables.append(
            _MarkdownTable(
                section=current_section,
                headers=headers,
                rows=tuple(rows),
            )
        )
    return tables


def _first_table(
    tables: Sequence[_MarkdownTable],
    *,
    section_name: str,
    required_headers: Sequence[str],
) -> _MarkdownTable | None:
    normalized_section = section_name.strip().lower()
    required = set(required_headers)
    for table in tables:
        if (table.section or "").strip().lower() != normalized_section:
            continue
        if required.issubset(set(table.headers)):
            return table
    return None


def _tables_with_headers(
    tables: Sequence[_MarkdownTable],
    *,
    required_headers: Sequence[str],
) -> list[_MarkdownTable]:
    required = set(required_headers)
    return [table for table in tables if required.issubset(set(table.headers))]


def _metric_value_map(table: _MarkdownTable, *, key_field: str, value_field: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in table.rows:
        key = row.get(key_field, "").strip()
        if not key:
            continue
        output[key] = row.get(value_field, "").strip()
    return output


def _group_status_class(value: str) -> str:
    normalized = (value or "").strip().upper()
    if normalized in {"EXIT_ZONE", "HIGH", "EXTREME"}:
        return "risk-high"
    if normalized in {"TRIM_WATCH", "WATCH", "ELEVATED", "MEDIUM"}:
        return "risk-medium"
    if normalized in {"BUY_ZONE", "ADD_ON_PULLBACK"}:
        return "status-positive"
    if normalized in {"NEUTRAL", "NORMAL", "LOW"}:
        return "status-neutral"
    return ""


def _render_market_status_cell(value: str) -> str:
    css_class = _group_status_class(value)
    class_attr = f' class="{css_class}"' if css_class else ""
    return f"<td{class_attr}>{_html_text(value)}</td>"


def _non_empty_value(*values: str) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _candidate_pattern_value(
    data: dict[str, str],
) -> tuple[str, str]:
    pattern_candidates = (
        ("latest_bearish_divergence", "bearish_divergence_age_td", 0),
        ("bearish_divergence_signal", "bearish_divergence_age_td", 0),
        ("latest_bearish_candle", "bearish_candle_age_td", 0),
        ("bearish_candle_signal", "bearish_candle_age_td", 0),
        ("latest_bullish_divergence", "bullish_divergence_age_td", 1),
        ("bullish_divergence_signal", "bullish_divergence_age_td", 1),
        ("latest_bullish_candle", "bullish_candle_age_td", 1),
        ("bullish_candle_signal", "bullish_candle_age_td", 1),
        ("latest_hidden_bearish_divergence", "hidden_bearish_divergence_age_td", 2),
        ("latest_hidden_bullish_divergence", "hidden_bullish_divergence_age_td", 3),
        ("latest_chart_pattern", "", 4),
        ("chart_pattern", "", 4),
    )
    ranked: list[tuple[int, int, str, str]] = []
    for value_key, age_key, priority in pattern_candidates:
        value = data.get(value_key, "").strip()
        if not value:
            continue
        age_text = data.get(age_key, "").strip() if age_key else ""
        try:
            age_rank = int(age_text)
        except ValueError:
            age_rank = 10**9
        ranked.append((age_rank, priority, value, age_text))
    if not ranked:
        return "", ""
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    _age_rank, _priority, value, age_text = ranked[0]
    return value, age_text


def _extract_ecosystem_context_rows(
    dashboard_status: DatacenterDashboardStatus,
) -> list[_EcosystemContextRow]:
    rows: list[_EcosystemContextRow] = []
    for report in dashboard_status.reports:
        if not report.path:
            continue
        tables = _parse_markdown_tables(report.path)
        horizon = report.horizon
        metrics: dict[str, str] = {}
        first_values: dict[str, str] = {}
        if horizon == "daily":
            dashboard_table = _first_table(
                tables,
                section_name="3. Dashboard",
                required_headers=("metric", "value"),
            )
            if dashboard_table is None:
                continue
            metrics = _metric_value_map(dashboard_table, key_field="metric", value_field="value")
        else:
            ecosystem_change_table = _first_table(
                tables,
                section_name="4. Ecosystem window change",
                required_headers=("metric", "last_value"),
            )
            if ecosystem_change_table is None:
                continue
            metrics = _metric_value_map(
                ecosystem_change_table,
                key_field="metric",
                value_field="last_value",
            )
            first_values = _metric_value_map(
                ecosystem_change_table,
                key_field="metric",
                value_field="first_value",
            )
        latest_relevant_pattern, latest_relevant_pattern_age_td = _candidate_pattern_value(metrics)
        rows.append(
            _EcosystemContextRow(
                horizon=horizon,
                name=metrics.get("ecosystem_name", "") or "DC_ECOSYSTEM_TOTAL",
                current_status=_non_empty_value(
                    metrics.get("timing_state", ""),
                    metrics.get("current_status", ""),
                ),
                start_status_30d=(
                    first_values.get("timing_state", "").strip()
                    if horizon == "rolling 30d"
                    else ""
                ),
                overheat_risk_level=_non_empty_value(
                    metrics.get("ecosystem_overheat_risk_level", ""),
                    metrics.get("overheat_risk_level", ""),
                ),
                pct_above_ema20=_non_empty_value(
                    metrics.get("ecosystem_pct_above_ema20", ""),
                    metrics.get("pct_above_ema20", ""),
                ),
                pct_above_ma10=_non_empty_value(
                    metrics.get("ecosystem_pct_above_ma10", ""),
                    metrics.get("pct_above_ma10", ""),
                ),
                ema20_breadth_delta_5d=_non_empty_value(
                    metrics.get("ecosystem_ema20_breadth_delta_5d", ""),
                    metrics.get("ema20_breadth_delta_5d", ""),
                ),
                return_5d=_non_empty_value(
                    metrics.get("ecosystem_return_5d", ""),
                    metrics.get("return_5d", ""),
                ),
                return_10d=_non_empty_value(
                    metrics.get("ecosystem_return_10d", ""),
                    metrics.get("return_10d", ""),
                ),
                return_20d=_non_empty_value(
                    metrics.get("ecosystem_return_20d", ""),
                    metrics.get("return_20d", ""),
                ),
                return_60d=_non_empty_value(
                    metrics.get("ecosystem_return_60d", ""),
                    metrics.get("return_60d", ""),
                ),
                dow_trend_state=_non_empty_value(
                    metrics.get("trend_state", ""),
                    metrics.get("trend_classification", ""),
                    metrics.get("ticker_trend_state", ""),
                    metrics.get("latest_ticker_trend_state", ""),
                    metrics.get("ecosystem_trend_state", ""),
                ),
                latest_structure_label=_non_empty_value(
                    metrics.get("latest_structure_label", ""),
                    metrics.get("structure_label", ""),
                ),
                latest_bos_event_type=_non_empty_value(
                    metrics.get("latest_bos_event_type", ""),
                    metrics.get("bos_event_type", ""),
                ),
                latest_reset_reason=_non_empty_value(
                    metrics.get("latest_reset_reason", ""),
                    metrics.get("reset_reason", ""),
                ),
                latest_relevant_pattern=latest_relevant_pattern,
                latest_relevant_pattern_age_td=latest_relevant_pattern_age_td,
                source_file=report.path,
            )
        )
    return sorted(rows, key=lambda row: (_HORIZON_PRIORITY.get(row.horizon, 99), row.source_file))


def _combine_ecosystem_context_rows(
    rows: Sequence[_EcosystemContextRow],
) -> _CombinedEcosystemRow | None:
    if not rows:
        return None

    def _preferred(field_name: str) -> str:
        for horizon in ("daily", "rolling 2d", "rolling 5d", "rolling 30d"):
            for row in rows:
                if row.horizon != horizon:
                    continue
                value = getattr(row, field_name)
                if str(value).strip():
                    return str(value).strip()
        return ""

    current_status = _preferred("current_status")
    start_status_30d = ""
    for row in rows:
        if row.horizon == "rolling 30d" and row.start_status_30d.strip():
            start_status_30d = row.start_status_30d.strip()
            break
    status_change_30d = (
        f"{start_status_30d} -> {current_status}"
        if start_status_30d and current_status
        else ""
    )

    pattern_ranked: list[tuple[int, int, str, str]] = []
    for row in rows:
        pattern = row.latest_relevant_pattern.strip()
        if not pattern:
            continue
        age_text = row.latest_relevant_pattern_age_td.strip()
        try:
            age_rank = int(age_text)
        except ValueError:
            age_rank = 10**9
        pattern_upper = pattern.upper()
        if "BEARISH" in pattern_upper and "HIDDEN" not in pattern_upper:
            priority = 0
        elif "BULLISH" in pattern_upper and "HIDDEN" not in pattern_upper:
            priority = 1
        elif "HIDDEN_BEARISH" in pattern_upper or ("HIDDEN" in pattern_upper and "BEARISH" in pattern_upper):
            priority = 2
        elif "HIDDEN_BULLISH" in pattern_upper or ("HIDDEN" in pattern_upper and "BULLISH" in pattern_upper):
            priority = 3
        else:
            priority = 4
        pattern_ranked.append((age_rank, priority, pattern, age_text))
    if pattern_ranked:
        pattern_ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        _age_rank, _priority, latest_pattern, latest_pattern_age = pattern_ranked[0]
    else:
        latest_pattern = ""
        latest_pattern_age = ""

    source_horizons = ", ".join(
        row.horizon
        for row in rows
    )
    source_files = ", ".join(
        Path(row.source_file).name
        for row in rows
        if row.source_file
    )
    return _CombinedEcosystemRow(
        name=rows[0].name,
        current_status=current_status,
        start_status_30d=start_status_30d,
        status_change_30d=status_change_30d,
        overheat_risk_level=_preferred("overheat_risk_level"),
        pct_above_ema20=_preferred("pct_above_ema20"),
        pct_above_ma10=_preferred("pct_above_ma10"),
        ema20_breadth_delta_5d=_preferred("ema20_breadth_delta_5d"),
        return_5d=_preferred("return_5d"),
        return_10d=_preferred("return_10d"),
        return_20d=_preferred("return_20d"),
        return_60d=_preferred("return_60d"),
        dow_trend_state=_preferred("dow_trend_state"),
        latest_structure_label=_preferred("latest_structure_label"),
        latest_bos_event_type=_preferred("latest_bos_event_type"),
        latest_reset_reason=_preferred("latest_reset_reason"),
        latest_relevant_pattern=latest_pattern,
        latest_relevant_pattern_age_td=latest_pattern_age,
        source_horizons=source_horizons,
        source_files=source_files,
    )


def _ecosystem_filter_text(row: _CombinedEcosystemRow) -> str:
    return " ".join(
        part
        for part in (
            row.name,
            row.current_status,
            row.start_status_30d,
            row.status_change_30d,
            row.overheat_risk_level,
            row.dow_trend_state,
            row.latest_relevant_pattern,
            row.source_horizons,
        )
        if part
    ).lower()


def _render_combined_ecosystem_row(row: _CombinedEcosystemRow) -> str:
    return (
        "<tr"
        f' data-filter-row="1"'
        f' data-section="market-map"'
        f' data-action="{_html_attr(row.current_status)}"'
        f' data-pullback-validity=""'
        f' data-entry-readiness=""'
        f' data-candidate-priority=""'
        f' data-filter-text="{_html_attr(_ecosystem_filter_text(row))}"'
        ">"
        f"<td>{_html_text(row.name)}</td>"
        + _render_market_status_cell(row.current_status)
        + _render_market_status_cell(row.start_status_30d)
        + f"<td>{_html_text(row.status_change_30d)}</td>"
        + _render_market_status_cell(row.overheat_risk_level)
        + f"<td>{_html_text(row.pct_above_ema20)}</td>"
        + f"<td>{_html_text(row.pct_above_ma10)}</td>"
        + f"<td>{_html_text(row.ema20_breadth_delta_5d)}</td>"
        + f"<td>{_html_text(row.return_5d)}</td>"
        + f"<td>{_html_text(row.return_10d)}</td>"
        + f"<td>{_html_text(row.return_20d)}</td>"
        + f"<td>{_html_text(row.return_60d)}</td>"
        + f"<td>{_html_text(row.dow_trend_state)}</td>"
        + f"<td>{_html_text(row.latest_structure_label)}</td>"
        + f"<td>{_html_text(row.latest_bos_event_type)}</td>"
        + f"<td>{_html_text(row.latest_reset_reason)}</td>"
        + f"<td>{_html_text(row.latest_relevant_pattern)}</td>"
        + f"<td>{_html_text(row.latest_relevant_pattern_age_td)}</td>"
        + f"<td>{_html_text(row.source_horizons)}</td>"
        + f"<td>{_html_text(row.source_files)}</td>"
        + "</tr>"
    )


def _extract_market_map_rows(
    dashboard_status: DatacenterDashboardStatus,
) -> list[_MarketMapRow]:
    rows: list[_MarketMapRow] = []
    for report in dashboard_status.reports:
        if not report.path:
            continue
        tables = _parse_markdown_tables(report.path)
        horizon = report.horizon

        if horizon == "daily":
            dashboard_table = _first_table(
                tables,
                section_name="3. Dashboard",
                required_headers=("metric", "value"),
            )
            if dashboard_table is not None:
                metrics = _metric_value_map(dashboard_table, key_field="metric", value_field="value")
                rows.append(
                    _MarketMapRow(
                        scope="ecosystem",
                        horizon=horizon,
                        name="DC_ECOSYSTEM_TOTAL",
                        layer="",
                        subindustry="",
                        current_status=metrics.get("timing_state", ""),
                        window_status="",
                        overheat_risk_level=metrics.get("ecosystem_overheat_risk_level", ""),
                        pct_above_ema20=metrics.get("ecosystem_pct_above_ema20", ""),
                        pct_above_ma10=metrics.get("ecosystem_pct_above_ma10", ""),
                        ema20_breadth_delta_5d=metrics.get("ecosystem_ema20_breadth_delta_5d", ""),
                        return_5d=metrics.get("ecosystem_return_5d", ""),
                        return_10d=metrics.get("ecosystem_return_10d", ""),
                        return_20d=metrics.get("ecosystem_return_20d", ""),
                        return_60d=metrics.get("ecosystem_return_60d", ""),
                        source_file=report.path,
                    )
                )

            overheat_table = _first_table(
                tables,
                section_name="4. Rotation Risk / Overheat Index",
                required_headers=(
                    "group_type",
                    "group_name",
                    "overheat_risk_level",
                ),
            )
            subindustry_timing_table = _first_table(
                tables,
                section_name="5. Subindustry Timing States",
                required_headers=("group_name", "timing_state"),
            )
            timing_by_subindustry = {
                row.get("group_name", "").strip(): row
                for row in (subindustry_timing_table.rows if subindustry_timing_table else ())
                if row.get("group_name", "").strip()
            }
            overheat_by_group = {
                (row.get("group_type", "").strip(), row.get("group_name", "").strip()): row
                for row in (overheat_table.rows if overheat_table else ())
                if row.get("group_type", "").strip() and row.get("group_name", "").strip()
            }
            for table in _tables_with_headers(
                tables,
                required_headers=("row_type", "layer", "subindustry", "ticker"),
            ):
                for row in table.rows:
                    row_type = row.get("row_type", "").strip().upper()
                    ticker_value = row.get("ticker", "").strip()
                    if ticker_value:
                        continue
                    if row_type == "LAYER":
                        layer_name = row.get("layer", "").strip()
                        overheat_row = overheat_by_group.get(("layer", layer_name), {})
                        rows.append(
                            _MarketMapRow(
                                scope="layer",
                                horizon=horizon,
                                name=layer_name,
                                layer=layer_name,
                                subindustry="",
                                current_status=row.get("status", "").strip(),
                                window_status="",
                                overheat_risk_level=overheat_row.get("overheat_risk_level", "").strip(),
                                pct_above_ema20=overheat_row.get("pct_above_ema20", "").strip(),
                                pct_above_ma10=overheat_row.get("ma10_breadth_delta_5d", "").strip(),
                                ema20_breadth_delta_5d=overheat_row.get("ema20_breadth_delta_5d", "").strip(),
                                return_5d=row.get("return_5d", "").strip(),
                                return_10d=overheat_row.get("return_10d", "").strip(),
                                return_20d=row.get("return_20d", "").strip() or overheat_row.get("return_20d", "").strip(),
                                return_60d="",
                                source_file=report.path,
                            )
                        )
                    elif row_type == "SUBINDUSTRY":
                        subindustry_name = row.get("subindustry", "").strip()
                        overheat_row = overheat_by_group.get(("subindustry", subindustry_name), {})
                        timing_row = timing_by_subindustry.get(subindustry_name, {})
                        rows.append(
                            _MarketMapRow(
                                scope="subindustry",
                                horizon=horizon,
                                name=subindustry_name,
                                layer=row.get("layer", "").strip(),
                                subindustry=subindustry_name,
                                current_status=row.get("status", "").strip() or timing_row.get("timing_state", "").strip(),
                                window_status="",
                                overheat_risk_level=overheat_row.get("overheat_risk_level", "").strip(),
                                pct_above_ema20=timing_row.get("pct_above_ema20", "").strip() or overheat_row.get("pct_above_ema20", "").strip(),
                                pct_above_ma10=overheat_row.get("ma10_breadth_delta_5d", "").strip(),
                                ema20_breadth_delta_5d=timing_row.get("ema20_breadth_delta_5d", "").strip() or overheat_row.get("ema20_breadth_delta_5d", "").strip(),
                                return_5d=row.get("return_5d", "").strip() or timing_row.get("return_5d", "").strip(),
                                return_10d=timing_row.get("return_10d", "").strip() or overheat_row.get("return_10d", "").strip(),
                                return_20d=row.get("return_20d", "").strip() or timing_row.get("return_20d", "").strip() or overheat_row.get("return_20d", "").strip(),
                                return_60d=timing_row.get("return_60d", "").strip(),
                                source_file=report.path,
                            )
                        )
        else:
            ecosystem_change_table = _first_table(
                tables,
                section_name="4. Ecosystem window change",
                required_headers=("metric", "last_value"),
            )
            if ecosystem_change_table is not None:
                metrics = _metric_value_map(
                    ecosystem_change_table,
                    key_field="metric",
                    value_field="last_value",
                )
                rows.append(
                    _MarketMapRow(
                        scope="ecosystem",
                        horizon=horizon,
                        name="DC_ECOSYSTEM_TOTAL",
                        layer="",
                        subindustry="",
                        current_status=metrics.get("timing_state", ""),
                        window_status="",
                        overheat_risk_level=metrics.get("overheat_risk_level", ""),
                        pct_above_ema20=metrics.get("pct_above_ema20", ""),
                        pct_above_ma10=metrics.get("pct_above_ma10", ""),
                        ema20_breadth_delta_5d=metrics.get("ema20_breadth_delta_5d", ""),
                        return_5d=metrics.get("return_5d", ""),
                        return_10d=metrics.get("return_10d", ""),
                        return_20d=metrics.get("return_20d", ""),
                        return_60d="",
                        source_file=report.path,
                    )
                )

            structure_tables = _tables_with_headers(
                tables,
                required_headers=("group_type", "group_name", "timing_state", "overheat_risk_level"),
            )
            structure_by_group: dict[tuple[str, str], dict[str, str]] = {}
            for table in structure_tables:
                for row in table.rows:
                    group_type = row.get("group_type", "").strip()
                    group_name = row.get("group_name", "").strip()
                    if not group_type or not group_name:
                        continue
                    structure_by_group[(group_type, group_name)] = row
            for table in _tables_with_headers(
                tables,
                required_headers=("row_type", "layer", "subindustry", "ticker", "current_status", "window_status"),
            ):
                for row in table.rows:
                    row_type = row.get("row_type", "").strip().upper()
                    ticker_value = row.get("ticker", "").strip()
                    if ticker_value:
                        continue
                    if row_type == "LAYER":
                        layer_name = row.get("layer", "").strip()
                        structure_row = structure_by_group.get(("layer", layer_name), {})
                        rows.append(
                            _MarketMapRow(
                                scope="layer",
                                horizon=horizon,
                                name=layer_name,
                                layer=layer_name,
                                subindustry="",
                                current_status=row.get("current_status", "").strip() or structure_row.get("timing_state", "").strip(),
                                window_status=row.get("window_status", "").strip(),
                                overheat_risk_level=structure_row.get("overheat_risk_level", "").strip(),
                                pct_above_ema20="",
                                pct_above_ma10="",
                                ema20_breadth_delta_5d="",
                                return_5d="",
                                return_10d="",
                                return_20d="",
                                return_60d="",
                                source_file=report.path,
                            )
                        )
                    elif row_type == "SUBINDUSTRY":
                        subindustry_name = row.get("subindustry", "").strip()
                        structure_row = structure_by_group.get(("subindustry", subindustry_name), {})
                        rows.append(
                            _MarketMapRow(
                                scope="subindustry",
                                horizon=horizon,
                                name=subindustry_name,
                                layer=row.get("layer", "").strip(),
                                subindustry=subindustry_name,
                                current_status=row.get("current_status", "").strip() or structure_row.get("timing_state", "").strip(),
                                window_status=row.get("window_status", "").strip(),
                                overheat_risk_level=structure_row.get("overheat_risk_level", "").strip(),
                                pct_above_ema20="",
                                pct_above_ma10="",
                                ema20_breadth_delta_5d="",
                                return_5d="",
                                return_10d="",
                                return_20d="",
                                return_60d="",
                                source_file=report.path,
                            )
                        )
    return sorted(
        rows,
        key=lambda row: (
            {"ecosystem": 0, "layer": 1, "subindustry": 2}.get(row.scope, 99),
            _HORIZON_PRIORITY.get(row.horizon, 99),
            row.layer,
            row.subindustry,
            row.name,
            row.source_file,
        ),
    )


def _market_map_filter_text(row: _MarketMapRow) -> str:
    return " ".join(
        part
        for part in (
            row.scope,
            row.horizon,
            row.name,
            row.layer,
            row.subindustry,
            row.current_status,
            row.window_status,
            row.overheat_risk_level,
        )
        if part
    ).lower()


def _render_market_map_rows(
    rows: Sequence[_MarketMapRow],
    *,
    include_layer_column: bool,
) -> str:
    rendered_rows: list[str] = []
    for row in rows:
        rendered_rows.append(
            "<tr"
            f' data-filter-row="1"'
            f' data-section="market-map"'
            f' data-action="{_html_attr(row.current_status)}"'
            f' data-pullback-validity=""'
            f' data-entry-readiness=""'
            f' data-candidate-priority=""'
            f' data-filter-text="{_html_attr(_market_map_filter_text(row))}"'
            ">"
            f"<td>{_html_text(row.name)}</td>"
            + (f"<td>{_html_text(row.layer)}</td>" if include_layer_column else "")
            + f"<td>{_html_text(row.horizon)}</td>"
            + _render_market_status_cell(row.current_status)
            + _render_market_status_cell(row.window_status)
            + _render_market_status_cell(row.overheat_risk_level)
            + f"<td>{_html_text(row.pct_above_ema20)}</td>"
            + f"<td>{_html_text(row.pct_above_ma10)}</td>"
            + f"<td>{_html_text(row.ema20_breadth_delta_5d)}</td>"
            + f"<td>{_html_text(row.return_5d)}</td>"
            + f"<td>{_html_text(row.return_10d)}</td>"
            + f"<td>{_html_text(row.return_20d)}</td>"
            + f"<td>{_html_text(row.return_60d)}</td>"
            + f"<td>{_html_text(Path(row.source_file).name if row.source_file else '')}</td>"
            + "</tr>"
        )
    return "".join(rendered_rows)


def _build_inspector_views(
    decisions: list[DatacenterTickerDecision],
    rows: list[DatacenterDashboardRow],
) -> dict[str, DatacenterTickerInspectorView]:
    return {
        decision.ticker: build_datacenter_ticker_inspector_view(
            decision=decision,
            rows=rows,
        )
        for decision in decisions
    }


def _rows_for_ticker(rows: list[DatacenterDashboardRow], ticker: str) -> list[DatacenterDashboardRow]:
    matching_rows = [row for row in rows if row.ticker.upper() == ticker.upper()]
    return sorted(
        matching_rows,
        key=lambda row: (
            _HORIZON_PRIORITY.get(row.horizon, 99),
            row.source_file or "",
            row.section or "",
            row.row_kind or "",
        ),
    )


def _first_non_empty_context_value(
    rows: list[DatacenterDashboardRow],
    ticker: str,
    field_name: str,
) -> str:
    for row in _rows_for_ticker(rows, ticker):
        value = getattr(row, field_name, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _count_dict_lines(prefix: str, ordered_keys: tuple[str, ...], counts: dict[str, int]) -> str:
    return "\n".join(
        f"{prefix}{key}={counts.get(key, 0)}"
        for key in ordered_keys
    )


def _count_table(title: str, prefix: str, ordered_keys: tuple[str, ...], counts: dict[str, int]) -> str:
    rows = "".join(
        "<tr>"
        f"<th>{escape(key)}</th>"
        f"<td>{counts.get(key, 0)}</td>"
        "</tr>"
        for key in ordered_keys
    )
    return (
        '<section class="card">'
        f"<h3>{escape(title)}</h3>"
        '<table class="compact-table">'
        "<tbody>"
        f"{rows}"
        "</tbody>"
        "</table>"
        "</section>"
    )


def _command_center_sort_key(decision: DatacenterTickerDecision) -> tuple[int, str]:
    return (_ACTION_ORDER.index(decision.action), decision.ticker)


def _candidate_sort_key(decision: DatacenterTickerDecision) -> tuple[int, int, int, int, int, str]:
    bullish_age = (
        decision.latest_bullish_signal_age_td
        if decision.latest_bullish_signal_age_td is not None
        else 10**9
    )
    return (
        decision.candidate_priority if decision.candidate_priority is not None else 9,
        _CANDIDATE_PULLBACK_ORDER.index(
            decision.pullback_validity
            if decision.pullback_validity in _CANDIDATE_PULLBACK_ORDER
            else "EARLY_PULLBACK"
        ),
        _ENTRY_READINESS_ORDER.index(
            decision.entry_readiness
            if decision.entry_readiness in _ENTRY_READINESS_ORDER
            else "INSUFFICIENT_DATA"
        ),
        _CANDIDATE_ACTION_ORDER.index(decision.action),
        bullish_age,
        decision.ticker,
    )


def _report_summary_by_horizon(
    parse_result: DatacenterDashboardBatchParseResult,
) -> dict[str, DatacenterDashboardReportParseSummary]:
    return {report.horizon: report for report in parse_result.reports}


def _action_class(action: str) -> str:
    if action == "SELL":
        return "action-sell"
    if action == "REDUCE":
        return "action-reduce"
    if action == "TIGHTEN_STOP":
        return "action-tighten"
    if action in {"BUY_NOW", "WATCH", "WAIT_PULLBACK"}:
        return "action-watch"
    return "action-neutral"


def _is_watchlist_row(row: DatacenterDashboardRow) -> bool:
    section_text = (row.section or "").strip().lower()
    return section_text == _WATCHLIST_SECTION_NAME


def _watchlist_horizon_status(row: DatacenterDashboardRow) -> str:
    for field_name in (
        "watchlist_status",
        "current_watchlist_status",
        "window_watchlist_status",
        "current_status",
        "window_status",
    ):
        value = row.raw_fields.get(field_name, "")
        if value.strip():
            return value.strip()
    return ""


def _first_trace(decision: DatacenterTickerDecision) -> tuple[str, str]:
    if not decision.decision_trace:
        return "", ""
    first_trace = decision.decision_trace[0]
    return first_trace.matched_rule or "", first_trace.matched_token or ""


def _newest_report_timestamp(dashboard_status: DatacenterDashboardStatus) -> str:
    timestamps = [
        report.modified_at
        for report in dashboard_status.reports
        if report.modified_at
    ]
    if not timestamps:
        return ""
    return max(timestamps)


def generate_dashboard_html(
    *,
    reports_dir: str,
    title: str,
    ticker: str | None,
    report_date: str | None,
    max_command_rows: int,
    max_candidate_rows: int,
    generated_at_utc: str | None = None,
) -> tuple[str, DatacenterDashboardStatus, DatacenterDashboardBatchParseResult, DatacenterDecisionBatchResult]:
    dashboard_status = discover_datacenter_dashboard_status(reports_dir, report_date=report_date)
    parse_result = parse_datacenter_dashboard_reports(dashboard_status.reports)
    parsed_rows = _collect_rows(dashboard_status)
    decision_result = build_datacenter_ticker_decisions(parsed_rows)
    inspector_views = _build_inspector_views(decision_result.decisions, parsed_rows)
    generated_at = generated_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    selection_mode = "report_date" if report_date else "newest"
    selected_report_date = report_date or "newest"

    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    missing_reports = sum(1 for report in dashboard_status.reports if report.status != "OK")
    report_summaries = _report_summary_by_horizon(parse_result)
    newest_report_timestamp = _newest_report_timestamp(dashboard_status)
    report_paths = {
        report.horizon: report.path or ""
        for report in dashboard_status.reports
    }
    market_map_rows = _extract_market_map_rows(dashboard_status)
    ecosystem_context_rows = _extract_ecosystem_context_rows(dashboard_status)
    watchlist_rows_by_ticker: dict[str, list[DatacenterDashboardRow]] = {}
    for row in parsed_rows:
        if not _is_watchlist_row(row):
            continue
        watchlist_rows_by_ticker.setdefault(row.ticker, []).append(row)

    header_summary_rows = "".join(
        "<tr>"
        f"<th>{escape(label)}</th>"
        f"<td>{_html_text(value)}</td>"
        "</tr>"
        for label, value in (
            ("Generated at UTC", generated_at),
            ("Reports dir", reports_dir),
            ("Selected report date", selected_report_date),
            ("Selection mode", selection_mode),
            ("Readiness", dashboard_status.overall_status),
            ("Found reports", found_reports),
            ("Missing reports", missing_reports),
            ("Total parsed rows", parse_result.total_row_count),
            ("Total parse warnings", parse_result.total_warning_count),
        )
    )
    report_source_rows = "".join(
        "<tr>"
        f"<th>{escape(label)}</th>"
        f"<td>{_html_text(value)}</td>"
        "</tr>"
        for label, value in (
            ("generated_at_utc", generated_at),
            ("reports_dir", reports_dir),
            ("selected_report_date", selected_report_date),
            ("selection_mode", selection_mode),
            ("newest_report_timestamp", newest_report_timestamp or "unknown"),
            ("daily_report_path", report_paths.get("daily", "")),
            ("rolling_2d_report_path", report_paths.get("rolling 2d", "")),
            ("rolling_5d_report_path", report_paths.get("rolling 5d", "")),
            ("rolling_30d_report_path", report_paths.get("rolling 30d", "")),
        )
    )

    command_center_html_parts: list[str] = []
    command_center_rows_rendered = 0
    sorted_decisions = sorted(decision_result.decisions, key=_command_center_sort_key)
    for group_label, actions in _COMMAND_CENTER_GROUPS:
        rows_html: list[str] = []
        for decision in sorted_decisions:
            if decision.action not in actions:
                continue
            if command_center_rows_rendered >= max_command_rows:
                break
            rows_html.append(
                "<tr"
                f' data-filter-row="1"'
                f' data-section="command-center"'
                f' data-action="{_html_attr(decision.action)}"'
                f' data-pullback-validity="{_html_attr(decision.pullback_validity)}"'
                f' data-entry-readiness="{_html_attr(decision.entry_readiness)}"'
                f' data-candidate-priority="{_html_attr(decision.candidate_priority_label)}"'
                f' data-filter-text="{_html_attr(" ".join(filter(None, [decision.ticker, decision.action, decision.primary_reason or "", decision.pullback_validity or "", decision.entry_readiness or "", decision.candidate_priority_label or ""])).lower())}"'
                ">"
                f'<td class="{_action_class(decision.action)}">{_html_text(decision.ticker)}</td>'
                f"<td>{_html_text(decision.action)}</td>"
                f"<td>{_html_text(decision.severity)}</td>"
                f"<td>{_html_text(decision.primary_reason)}</td>"
                f"<td>{_html_text(decision.pullback_validity)}</td>"
                f"<td>{_html_text(decision.entry_readiness)}</td>"
                f"<td>{_html_text(decision.candidate_priority_label)}</td>"
                f"<td>{_html_text(_first_non_empty_context_value(parsed_rows, decision.ticker, 'ma_break_status'))}</td>"
                f"<td>{_html_text(_first_non_empty_context_value(parsed_rows, decision.ticker, 'freshness_status'))}</td>"
                f"<td>{_html_text(decision.trend_state)}</td>"
                f"<td>{_html_text(decision.latest_structure_label)}</td>"
                f"<td>{_html_text(decision.latest_bos_event_type)}</td>"
                f"<td>{_html_text(decision.latest_reset_reason)}</td>"
                f"<td>{_html_text(', '.join(decision.horizons_present))}</td>"
                f"<td>{len(decision.source_files)}</td>"
                "</tr>"
            )
            command_center_rows_rendered += 1
        if rows_html:
            command_center_html_parts.append(
                "<section class=\"group-section\">"
                f"<h3>{escape(group_label)}</h3>"
                "<div class=\"table-scroll\">"
                "<table class=\"sticky-table\">"
                "<thead><tr>"
                "<th>Ticker</th><th>Action</th><th>Severity</th><th>Primary reason</th>"
                "<th>Pullback validity</th><th>Entry readiness</th><th>Candidate priority</th>"
                "<th>MA break</th><th>Freshness</th><th>Trend state</th>"
                "<th>Latest structure</th><th>Latest BOS</th><th>Latest reset</th>"
                "<th>Horizons</th><th>Source files</th>"
                "</tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody>"
                "</table>"
                "</div>"
                "</section>"
            )

    candidate_decisions = [
        decision
        for decision in decision_result.decisions
        if decision.pullback_validity in _CANDIDATE_PULLBACK_ORDER
    ]
    candidate_decisions = sorted(candidate_decisions, key=_candidate_sort_key)[:max_candidate_rows]
    candidate_rows_html = "".join(
        "<tr"
        f' data-filter-row="1"'
        f' data-section="candidate-pullbacks"'
        f' data-action="{_html_attr(decision.action)}"'
        f' data-pullback-validity="{_html_attr(decision.pullback_validity)}"'
        f' data-entry-readiness="{_html_attr(decision.entry_readiness)}"'
        f' data-candidate-priority="{_html_attr(decision.candidate_priority_label)}"'
        f' data-filter-text="{_html_attr(" ".join(filter(None, [decision.ticker, decision.action, decision.primary_reason or "", decision.pullback_reason or "", decision.entry_readiness or "", decision.candidate_priority_label or ""])).lower())}"'
        ">"
        f'<td class="{_action_class(decision.action)}">{_html_text(decision.ticker)}</td>'
        f"<td>{decision.candidate_priority if decision.candidate_priority is not None else '-'}</td>"
        f"<td>{_html_text(decision.candidate_priority_label)}</td>"
        f"<td>{_html_text(decision.entry_readiness)}</td>"
        f"<td>{_html_text(decision.entry_readiness_reason)}</td>"
        f"<td>{_html_text(decision.action)}</td>"
        f"<td>{_html_text(decision.severity)}</td>"
        f"<td>{_html_text(decision.primary_reason)}</td>"
        f"<td>{_html_text(decision.pullback_reason)}</td>"
        f"<td>{_html_text(_first_non_empty_context_value(parsed_rows, decision.ticker, 'ma_break_status'))}</td>"
        f"<td>{_html_text(_first_non_empty_context_value(parsed_rows, decision.ticker, 'freshness_status'))}</td>"
        f"<td>{_html_text(decision.latest_bullish_signal_age_td)}</td>"
        f"<td>{_html_text(decision.latest_bearish_signal_age_td)}</td>"
        f"<td>{_html_text(_first_trace(decision)[0])}</td>"
        f"<td>{_html_text(_first_trace(decision)[1])}</td>"
        "</tr>"
        for decision in candidate_decisions
    )

    watchlist_decisions = [
        decision
        for decision in decision_result.decisions
        if decision.ticker in watchlist_rows_by_ticker
    ]
    watchlist_decisions = sorted(
        watchlist_decisions,
        key=lambda decision: (
            _ACTION_ORDER.index(decision.action),
            decision.candidate_priority if decision.candidate_priority is not None else 10**9,
            decision.ticker,
        ),
    )
    watchlist_rows_html_parts: list[str] = []
    for decision in watchlist_decisions:
        horizon_status_by_name = {
            row.horizon: _watchlist_horizon_status(row)
            for row in _rows_for_ticker(parsed_rows, decision.ticker)
            if _is_watchlist_row(row)
        }
        watchlist_rows_html_parts.append(
            "<tr"
            f' data-filter-row="1"'
            f' data-section="watchlist-status"'
            f' data-action="{_html_attr(decision.action)}"'
            f' data-pullback-validity="{_html_attr(decision.pullback_validity)}"'
            f' data-entry-readiness="{_html_attr(decision.entry_readiness)}"'
            f' data-candidate-priority="{_html_attr(decision.candidate_priority_label)}"'
            f' data-filter-text="{_html_attr(" ".join(filter(None, [decision.ticker, decision.action, decision.primary_reason or "", decision.pullback_validity or "", decision.entry_readiness or "", decision.candidate_priority_label or ""])).lower())}"'
            ">"
            f'<td class="{_action_class(decision.action)}">{_html_text(decision.ticker)}</td>'
            f"<td>{_html_text(decision.action)}</td>"
            f"<td>{_html_text(decision.severity)}</td>"
            f"<td>{_html_text(decision.primary_reason)}</td>"
            f"<td>{_html_text(decision.pullback_validity)}</td>"
            f"<td>{_html_text(decision.entry_readiness)}</td>"
            f"<td>{_html_text(decision.candidate_priority_label)}</td>"
            f"<td>{_html_text(_first_non_empty_context_value(parsed_rows, decision.ticker, 'ma_break_status'))}</td>"
            f"<td>{_html_text(_first_non_empty_context_value(parsed_rows, decision.ticker, 'freshness_status'))}</td>"
            f"<td>{_html_text(decision.trend_state)}</td>"
            f"<td>{_html_text(decision.latest_structure_label)}</td>"
            f"<td>{_html_text(decision.latest_bos_event_type)}</td>"
            f"<td>{_html_text(decision.latest_reset_reason)}</td>"
            f"<td>{_html_text(', '.join(decision.horizons_present))}</td>"
            f"<td>{len(decision.source_files)}</td>"
            f"<td>{_html_text(horizon_status_by_name.get('daily'))}</td>"
            f"<td>{_html_text(horizon_status_by_name.get('rolling 2d'))}</td>"
            f"<td>{_html_text(horizon_status_by_name.get('rolling 5d'))}</td>"
            f"<td>{_html_text(horizon_status_by_name.get('rolling 30d'))}</td>"
            "</tr>"
        )
    watchlist_rows_html = "".join(watchlist_rows_html_parts)

    combined_ecosystem_row = _combine_ecosystem_context_rows(ecosystem_context_rows)
    layer_market_rows = [row for row in market_map_rows if row.scope == "layer"]
    subindustry_market_rows = [row for row in market_map_rows if row.scope == "subindustry"]
    ecosystem_market_rows_html = (
        _render_combined_ecosystem_row(combined_ecosystem_row)
        if combined_ecosystem_row is not None
        else ""
    )
    layer_market_rows_html = _render_market_map_rows(
        layer_market_rows,
        include_layer_column=False,
    )
    subindustry_market_rows_html = _render_market_map_rows(
        subindustry_market_rows,
        include_layer_column=True,
    )

    detail_sections: list[str] = []
    for decision in sorted(decision_result.decisions, key=lambda item: item.ticker):
        inspector = inspector_views.get(decision.ticker)
        detail_rows = "".join(
            "<tr>"
            f"<th>{escape(label)}</th>"
            f"<td>{_html_text(value)}</td>"
            "</tr>"
            for label, value in (
                ("Ticker", decision.ticker),
                ("Final action", decision.action),
                ("Severity", decision.severity),
                ("Primary reason", decision.primary_reason),
                ("Conflict detected", inspector.conflict_detected if inspector else None),
                ("Supporting signals", ", ".join(inspector.supporting_signals) if inspector else None),
                ("Conflicting signals", ", ".join(inspector.conflicting_signals) if inspector else None),
                ("Override explanation", inspector.override_explanation if inspector else None),
                ("Pullback validity", decision.pullback_validity),
                ("Pullback reason", decision.pullback_reason),
                ("Entry readiness", decision.entry_readiness),
                ("Entry readiness reason", decision.entry_readiness_reason),
                ("Candidate priority", decision.candidate_priority_label),
                ("Candidate priority reason", decision.candidate_priority_reason),
            )
        )
        trace_rows = "".join(
            "<tr>"
            f"<td>{_html_text(trace.matched_rule)}</td>"
            f"<td>{_html_text(trace.horizon)}</td>"
            f"<td>{_html_text(trace.field_name)}</td>"
            f"<td>{_html_text(trace.matched_token)}</td>"
            f"<td>{_html_text(trace.matched_value)}</td>"
            f"<td>{_html_text(trace.section)}</td>"
            f"<td>{_html_text(trace.row_kind)}</td>"
            "</tr>"
            for trace in decision.decision_trace
        ) or (
            "<tr><td colspan=\"7\">-</td></tr>"
        )
        filter_text = " ".join(
            part
            for part in (
                decision.ticker,
                decision.action,
                decision.severity,
                decision.primary_reason or "",
                decision.pullback_validity or "",
                decision.entry_readiness or "",
            )
            if part
        )
        is_selected = ticker is not None and decision.ticker.upper() == ticker.strip().upper()
        detail_sections.append(
            f'<details class="ticker-detail{" selected" if is_selected else ""}" '
            f' data-filter-row="1"'
            f' data-section="inspector"'
            f'data-filter-text="{_html_attr(filter_text.lower())}"'
            f' data-action="{_html_attr(decision.action)}"'
            f' data-pullback-validity="{_html_attr(decision.pullback_validity)}"'
            f' data-entry-readiness="{_html_attr(decision.entry_readiness)}"'
            f' data-candidate-priority="{_html_attr(decision.candidate_priority_label)}"'
            f'{" open" if is_selected else ""}>'
            f"<summary>{_html_text(decision.ticker)} | {_html_text(decision.action)} | {_html_text(decision.severity)} | {_html_text(decision.primary_reason)}</summary>"
            '<div class="detail-grid">'
            '<div class="table-scroll"><table class="detail-table"><tbody>'
            f"{detail_rows}"
            "</tbody></table></div>"
            '<div class="table-scroll"><table class="trace-table"><thead><tr>'
            "<th>Rule</th><th>Horizon</th><th>Field</th><th>Token</th><th>Value</th><th>Section</th><th>Row kind</th>"
            "</tr></thead><tbody>"
            f"{trace_rows}"
            "</tbody></table></div>"
            "</div>"
            "</details>"
        )

    source_file_rows = "".join(
        "<tr>"
        f"<td>{_html_text(horizon)}</td>"
        f"<td>{_html_text(report.status)}</td>"
        f"<td>{_html_text(report.path)}</td>"
        f"<td>{report_summaries.get(horizon).row_count if report_summaries.get(horizon) else 0}</td>"
        f"<td>{report_summaries.get(horizon).warning_count if report_summaries.get(horizon) else 0}</td>"
        "</tr>"
        for horizon in _SOURCE_FILE_HORIZON_ORDER
        for report in dashboard_status.reports
        if report.horizon == horizon
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 20px;
      background: #f5f6f8;
      color: #1f2933;
    }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    section {{ margin-bottom: 24px; }}
    .page-header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: #f5f6f8;
      padding-bottom: 12px;
      margin-bottom: 24px;
      box-shadow: 0 2px 0 rgba(216, 222, 228, 0.9);
    }}
    .major-section {{ margin-top: 28px; }}
    .meta-table, .compact-table, table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
    }}
    .sticky-table thead th {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #eef2f6;
    }}
    th, td {{
      border: 1px solid #d8dee4;
      padding: 6px 8px;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{
      background: #eef2f6;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .nav-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin: 12px 0 18px;
      font-size: 14px;
    }}
    .nav-links a {{
      color: #0b57d0;
      text-decoration: none;
      font-weight: 600;
    }}
    .nav-links a:hover {{
      text-decoration: underline;
    }}
    .card {{
      background: #fff;
      border: 1px solid #d8dee4;
      padding: 12px;
    }}
    .action-sell {{ background: #fde8e8; }}
    .action-reduce {{ background: #fff2df; }}
    .action-tighten {{ background: #fff8c5; }}
    .action-watch {{ background: #e8f5e9; }}
    .action-neutral {{ background: #f1f3f5; }}
    .risk-high {{ background: #fde8e8; }}
    .risk-medium {{ background: #fff2df; }}
    .status-positive {{ background: #e8f5e9; }}
    .status-neutral {{ background: #f1f3f5; }}
    .filter-box {{
      margin: 8px 0 16px;
      padding: 12px;
      border: 1px solid #d8dee4;
      background: #fff;
    }}
    .filter-help {{
      margin: 0 0 10px;
      font-size: 13px;
      color: #4b5563;
    }}
    .filter-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 10px;
      align-items: end;
    }}
    .filter-box input,
    .filter-box select {{
      width: 100%;
      padding: 8px;
      font-size: 14px;
      box-sizing: border-box;
    }}
    .filter-status {{
      margin-top: 10px;
      font-size: 13px;
      color: #4b5563;
    }}
    .section-status {{
      margin: 0 0 10px;
      font-size: 13px;
      color: #4b5563;
    }}
    .ticker-detail {{
      margin-bottom: 10px;
      border: 1px solid #d8dee4;
      background: #fff;
      padding: 8px;
    }}
    .ticker-detail.selected {{
      border-color: #0b57d0;
      box-shadow: 0 0 0 1px #0b57d0 inset;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: minmax(280px, 420px) 1fr;
      gap: 12px;
      margin-top: 8px;
    }}
    .group-section {{
      margin-bottom: 18px;
    }}
    .table-scroll {{
      overflow-x: auto;
      max-width: 100%;
    }}
    .table-scroll table {{
      width: max-content;
      min-width: 100%;
    }}
    .table-scroll th,
    .table-scroll td {{
      white-space: nowrap;
    }}
    @media (max-width: 960px) {{
      .detail-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <section class="page-header">
    <h1>{escape(title)}</h1>
    <nav class="nav-links" aria-label="Dashboard sections">
      <a href="#summary">Summary</a>
      <a href="#market-map">Market Map</a>
      <a href="#watchlist-status">Watchlist Status</a>
      <a href="#candidate-pullbacks">Candidate Pullbacks</a>
      <a href="#command-center">Command Center</a>
      <a href="#inspector">Inspector</a>
      <a href="#source-files">Source Files</a>
    </nav>
    <table class="meta-table">
      <tbody>
        {header_summary_rows}
      </tbody>
    </table>
  </section>

  <section>
    <h2>Report Source</h2>
    <table class="meta-table">
      <tbody>
        {report_source_rows}
      </tbody>
    </table>
  </section>

  <section id="summary">
    <h2>Summary</h2>
    <div class="summary-grid">
      <section class="card">
        <h3>Decision Total</h3>
        <div>{len(decision_result.decisions)}</div>
      </section>
      {_count_table("Action Counts", "action.", _ACTION_ORDER, decision_result.action_counts)}
      {_count_table("Pullback Counts", "pullback.", _PULLBACK_ORDER, decision_result.pullback_counts)}
      {_count_table("Entry Readiness Counts", "entry_readiness.", _ENTRY_READINESS_ORDER, decision_result.entry_readiness_counts)}
      {_count_table("Candidate Priority Counts", "candidate_priority.", _CANDIDATE_PRIORITY_LABEL_ORDER, decision_result.candidate_priority_counts)}
    </div>
  </section>

  <section id="market-map" class="major-section">
    <h2>Market Map</h2>
    <div id="market-map-filter-status" class="section-status">Market Map rows: 0 / 0</div>
    {(
      '<section class="group-section">'
      '<h3>Ecosystem Summary</h3>'
      '<div class="table-scroll"><table class="sticky-table"><thead><tr>'
      '<th>Ecosystem</th><th>Current status</th><th>Start status 30d</th><th>Status change 30d</th>'
      '<th>Overheat risk</th><th>% above EMA20</th><th>% above MA10</th>'
      '<th>EMA20 breadth delta 5d</th><th>Return 5d</th><th>Return 10d</th>'
      '<th>Return 20d</th><th>Return 60d</th><th>Dow trend state</th><th>Latest structure</th>'
      '<th>Latest BOS</th><th>Latest reset</th><th>Latest relevant pattern</th>'
      '<th>Pattern age td</th><th>Source horizons</th><th>Source files</th>'
      '</tr></thead><tbody>'
      + ecosystem_market_rows_html +
      '</tbody></table></div>'
      '</section>'
      if ecosystem_market_rows_html else ''
    )}{(
      '<section class="group-section">'
      '<h3>Layers</h3>'
      '<div class="table-scroll"><table class="sticky-table"><thead><tr>'
      '<th>Layer</th><th>Horizon</th><th>Current status</th><th>Window status</th>'
      '<th>Overheat risk</th><th>% above EMA20</th><th>% above MA10</th>'
      '<th>EMA20 breadth delta 5d</th><th>Return 5d</th><th>Return 10d</th>'
      '<th>Return 20d</th><th>Return 60d</th><th>Source file</th>'
      '</tr></thead><tbody>'
      + layer_market_rows_html +
      '</tbody></table></div>'
      '</section>'
      if layer_market_rows_html else ''
    )}{(
      '<section class="group-section">'
      '<h3>Subindustries</h3>'
      '<div class="table-scroll"><table class="sticky-table"><thead><tr>'
      '<th>Subindustry</th><th>Layer</th><th>Horizon</th><th>Current status</th><th>Window status</th>'
      '<th>Overheat risk</th><th>% above EMA20</th><th>% above MA10</th>'
      '<th>EMA20 breadth delta 5d</th><th>Return 5d</th><th>Return 10d</th>'
      '<th>Return 20d</th><th>Return 60d</th><th>Source file</th>'
      '</tr></thead><tbody>'
      + subindustry_market_rows_html +
      '</tbody></table></div>'
      '</section>'
      if subindustry_market_rows_html else ''
    ) if market_map_rows else '<p>No market map rows found in the selected reports.</p>'}
  </section>

  <section id="watchlist-status" class="major-section">
    <h2>Watchlist Status</h2>
    <div id="watchlist-filter-status" class="section-status">Watchlist rows: 0 / 0</div>
    {(
      '<div class="table-scroll"><table class="sticky-table"><thead><tr>'
      '<th>Ticker</th><th>Action</th><th>Severity</th><th>Primary reason</th>'
      '<th>Pullback validity</th><th>Entry readiness</th><th>Candidate priority</th>'
      '<th>MA break</th><th>Freshness</th><th>Trend state</th>'
      '<th>Latest structure</th><th>Latest BOS</th><th>Latest reset</th>'
      '<th>Horizons</th><th>Source files</th>'
      '<th>Daily status</th><th>Rolling 2d status</th><th>Rolling 5d status</th><th>Rolling 30d status</th>'
      '</tr></thead><tbody>'
      + watchlist_rows_html +
      '</tbody></table></div>'
    ) if watchlist_rows_html else '<p>No watchlist rows found in the selected reports.</p>'}
  </section>

  <section id="filters" class="major-section">
    <h2>Filters</h2>
    <div class="filter-box">
      <p class="filter-help">Filters apply to Market Map, Watchlist Status, Candidate Pullbacks, Command Center and Inspector rows.</p>
      <div class="filter-grid">
        <label>Text filter
          <input id="ticker-filter" type="text" placeholder="e.g. NVDA, SELL, pullback" />
        </label>
        <label>Action
          <select id="action-filter">
            <option value="ALL">ALL</option>
            <option value="SELL">SELL</option>
            <option value="REDUCE">REDUCE</option>
            <option value="TIGHTEN_STOP">TIGHTEN_STOP</option>
            <option value="BLOCKED">BLOCKED</option>
            <option value="WAIT_PULLBACK">WAIT_PULLBACK</option>
            <option value="BUY_NOW">BUY_NOW</option>
            <option value="WATCH">WATCH</option>
            <option value="NEUTRAL">NEUTRAL</option>
          </select>
        </label>
        <label>Pullback validity
          <select id="pullback-filter">
            <option value="ALL">ALL</option>
            <option value="VALID_PULLBACK">VALID_PULLBACK</option>
            <option value="EARLY_PULLBACK">EARLY_PULLBACK</option>
            <option value="STRUCTURE_BLOCKED_PULLBACK">STRUCTURE_BLOCKED_PULLBACK</option>
            <option value="BREAKDOWN_NOT_PULLBACK">BREAKDOWN_NOT_PULLBACK</option>
            <option value="NO_PULLBACK">NO_PULLBACK</option>
            <option value="INSUFFICIENT_DATA">INSUFFICIENT_DATA</option>
          </select>
        </label>
        <label>Entry readiness
          <select id="entry-readiness-filter">
            <option value="ALL">ALL</option>
            <option value="READY_TO_WATCH">READY_TO_WATCH</option>
            <option value="NEEDS_STOP_STABILIZATION">NEEDS_STOP_STABILIZATION</option>
            <option value="NEEDS_RISK_CLEARANCE">NEEDS_RISK_CLEARANCE</option>
            <option value="EARLY_MONITOR">EARLY_MONITOR</option>
            <option value="NOT_READY">NOT_READY</option>
            <option value="INSUFFICIENT_DATA">INSUFFICIENT_DATA</option>
          </select>
        </label>
        <label>Candidate priority
          <select id="candidate-priority-filter">
            <option value="ALL">ALL</option>
            <option value="P1_READY_TO_WATCH">P1_READY_TO_WATCH</option>
            <option value="P2_STOP_STABILIZATION">P2_STOP_STABILIZATION</option>
            <option value="P3_RISK_CLEARANCE">P3_RISK_CLEARANCE</option>
            <option value="P4_EARLY_MONITOR">P4_EARLY_MONITOR</option>
            <option value="P5_NOT_READY">P5_NOT_READY</option>
            <option value="P9_NOT_CANDIDATE">P9_NOT_CANDIDATE</option>
          </select>
        </label>
      </div>
      <div id="filter-status" class="filter-status">Visible filtered rows: 0 / 0</div>
    </div>
  </section>

  <section id="candidate-pullbacks" class="major-section">
    <h2>Candidate Pullbacks</h2>
    <div id="candidate-filter-status" class="section-status">Candidate rows: 0 / 0</div>
    <div class="table-scroll">
    <table class="sticky-table">
      <thead>
        <tr>
          <th>Ticker</th><th>Priority</th><th>Priority label</th><th>Entry readiness</th>
          <th>Entry reason</th><th>Action</th><th>Severity</th><th>Primary reason</th>
          <th>Pullback reason</th><th>MA break</th><th>Freshness</th>
          <th>Latest bullish age</th><th>Latest bearish age</th>
          <th>First trace rule</th><th>First trace token</th>
        </tr>
      </thead>
      <tbody>
        {candidate_rows_html or '<tr><td colspan="15">-</td></tr>'}
      </tbody>
    </table>
    </div>
  </section>

  <section id="command-center" class="major-section">
    <h2>Command Center</h2>
    <div id="command-center-filter-status" class="section-status">Command Center rows: 0 / 0</div>
    {''.join(command_center_html_parts) or '<p>-</p>'}
  </section>

  <section id="inspector" class="major-section">
    <h2>Ticker Inspector / Details</h2>
    <div id="inspector-filter-status" class="section-status">Inspector rows: 0 / 0</div>
    {''.join(detail_sections)}
  </section>

  <section id="source-files" class="major-section">
    <h2>Source Files / Report Status</h2>
    <div class="table-scroll">
    <table class="sticky-table">
      <thead>
        <tr>
          <th>Horizon</th><th>Status</th><th>Path</th><th>Parsed rows</th><th>Warnings</th>
        </tr>
      </thead>
      <tbody>
        {source_file_rows}
      </tbody>
    </table>
    </div>
  </section>

  <script>
    (function() {{
      function matchesFilter(value, expected) {{
        return expected === "ALL" || value === expected;
      }}

      function applyFilters() {{
        var textNeedle = (document.getElementById("ticker-filter").value || "").toLowerCase();
        var actionValue = document.getElementById("action-filter").value;
        var pullbackValue = document.getElementById("pullback-filter").value;
        var entryReadinessValue = document.getElementById("entry-readiness-filter").value;
        var candidatePriorityValue = document.getElementById("candidate-priority-filter").value;
        var rows = document.querySelectorAll("[data-filter-row='1']");
        var visibleRows = 0;
        var sectionVisibleCounts = {{
          "market-map": 0,
          "watchlist-status": 0,
          "candidate-pullbacks": 0,
          "command-center": 0,
          "inspector": 0
        }};
        var sectionTotalCounts = {{
          "market-map": 0,
          "watchlist-status": 0,
          "candidate-pullbacks": 0,
          "command-center": 0,
          "inspector": 0
        }};

        rows.forEach(function (row) {{
          var section = row.getAttribute("data-section") || "";
          if (sectionTotalCounts.hasOwnProperty(section)) {{
            sectionTotalCounts[section] += 1;
          }}
          var haystack = (row.getAttribute("data-filter-text") || "").toLowerCase();
          var isVisible =
            (!textNeedle || haystack.indexOf(textNeedle) !== -1) &&
            matchesFilter(row.getAttribute("data-action") || "", actionValue) &&
            matchesFilter(row.getAttribute("data-pullback-validity") || "", pullbackValue) &&
            matchesFilter(row.getAttribute("data-entry-readiness") || "", entryReadinessValue) &&
            matchesFilter(row.getAttribute("data-candidate-priority") || "", candidatePriorityValue);
          row.style.display = isVisible ? "" : "none";
          if (isVisible) {{
            visibleRows += 1;
            if (sectionVisibleCounts.hasOwnProperty(section)) {{
              sectionVisibleCounts[section] += 1;
            }}
          }}
        }});

        var details = document.querySelectorAll(".ticker-detail");
        details.forEach(function (item) {{
          if (!item.hasAttribute("data-filter-row")) {{
            return;
          }}
        }});

        var status = document.getElementById("filter-status");
        if (status) {{
          status.textContent = "Visible filtered rows: " + visibleRows + " / " + rows.length;
        }}

        var marketMapStatus = document.getElementById("market-map-filter-status");
        if (marketMapStatus) {{
          marketMapStatus.textContent =
            "Market Map rows: " +
            sectionVisibleCounts["market-map"] +
            " / " +
            sectionTotalCounts["market-map"];
        }}
        var candidateStatus = document.getElementById("candidate-filter-status");
        var watchlistStatus = document.getElementById("watchlist-filter-status");
        if (watchlistStatus) {{
          watchlistStatus.textContent =
            "Watchlist rows: " +
            sectionVisibleCounts["watchlist-status"] +
            " / " +
            sectionTotalCounts["watchlist-status"];
        }}
        if (candidateStatus) {{
          candidateStatus.textContent =
            "Candidate rows: " +
            sectionVisibleCounts["candidate-pullbacks"] +
            " / " +
            sectionTotalCounts["candidate-pullbacks"];
        }}
        var commandCenterStatus = document.getElementById("command-center-filter-status");
        if (commandCenterStatus) {{
          commandCenterStatus.textContent =
            "Command Center rows: " +
            sectionVisibleCounts["command-center"] +
            " / " +
            sectionTotalCounts["command-center"];
        }}
        var inspectorStatus = document.getElementById("inspector-filter-status");
        if (inspectorStatus) {{
          inspectorStatus.textContent =
            "Inspector rows: " +
            sectionVisibleCounts["inspector"] +
            " / " +
            sectionTotalCounts["inspector"];
        }}
      }}

      ["ticker-filter", "action-filter", "pullback-filter", "entry-readiness-filter", "candidate-priority-filter"].forEach(function (id) {{
        var control = document.getElementById(id);
        if (!control) return;
        control.addEventListener("input", applyFilters);
        control.addEventListener("change", applyFilters);
      }});

      applyFilters();
    }})();
  </script>
</body>
</html>
"""
    return html, dashboard_status, parse_result, decision_result


def generate_datacenter_dashboard_html_file(
    *,
    reports_dir: str,
    output: str | None = None,
    report_date: str | None = None,
    title: str | None = None,
    ticker: str | None = None,
    max_command_rows: int = 200,
    max_candidate_rows: int = 100,
    generated_at_utc: str | None = None,
) -> DatacenterDashboardHtmlGenerationResult:
    normalized_report_date = report_date.strip() if report_date is not None and report_date.strip() else None
    if normalized_report_date is not None and not _REPORT_DATE_RE.match(normalized_report_date):
        raise ValueError(f"invalid report_date format: {normalized_report_date}")

    dashboard_status = discover_datacenter_dashboard_status(
        reports_dir,
        report_date=normalized_report_date,
    )
    if normalized_report_date and all(report.status != "OK" for report in dashboard_status.reports):
        raise FileNotFoundError(
            f"no reports found for report_date={normalized_report_date} in {reports_dir}"
        )

    selected_title = title or "Datacenter Dashboard"
    if normalized_report_date and selected_title == "Datacenter Dashboard":
        selected_title = f"{selected_title} — {normalized_report_date}"

    output_path = resolve_dashboard_html_output_path(
        reports_dir=reports_dir,
        output=output,
        report_date=normalized_report_date,
    )
    html, dashboard_status, _parse_result, decision_result = generate_dashboard_html(
        reports_dir=reports_dir,
        title=selected_title,
        ticker=ticker,
        report_date=normalized_report_date,
        max_command_rows=max_command_rows,
        max_candidate_rows=max_candidate_rows,
        generated_at_utc=generated_at_utc,
    )
    output_path.write_text(html, encoding="utf-8")

    candidate_rows = sum(
        1
        for decision in decision_result.decisions
        if decision.pullback_validity in _CANDIDATE_PULLBACK_ORDER
    )
    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    missing_reports = sum(1 for report in dashboard_status.reports if report.status != "OK")
    selection_mode = "report_date" if normalized_report_date else "newest"
    summary_lines = (
        f"SUMMARY reports_dir={reports_dir}",
        f"SUMMARY report_date={normalized_report_date or 'newest'}",
        f"SUMMARY selection_mode={selection_mode}",
        f"SUMMARY html_output={output_path}",
        f"SUMMARY readiness={dashboard_status.overall_status}",
        f"SUMMARY found_reports={found_reports}",
        f"SUMMARY missing_reports={missing_reports}",
        f"SUMMARY decision_total={len(decision_result.decisions)}",
        f"SUMMARY candidate_pullback_rows={candidate_rows}",
    )
    return DatacenterDashboardHtmlGenerationResult(
        output_path=str(output_path),
        report_date=normalized_report_date or "newest",
        selection_mode=selection_mode,
        readiness=dashboard_status.overall_status,
        found_reports=found_reports,
        missing_reports=missing_reports,
        decision_total=len(decision_result.decisions),
        candidate_pullback_rows=candidate_rows,
        summary_lines=summary_lines,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = generate_datacenter_dashboard_html_file(
            reports_dir=args.reports_dir,
            output=args.output,
            report_date=args.report_date,
            title=args.title,
            ticker=args.ticker,
            max_command_rows=args.max_command_rows,
            max_candidate_rows=args.max_candidate_rows,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1
    for line in result.summary_lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
