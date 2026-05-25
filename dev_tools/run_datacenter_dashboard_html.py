from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
from pathlib import Path

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a static HTML Datacenter Dashboard from the latest reports."
    )
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--output")
    parser.add_argument("--ticker")
    parser.add_argument("--max-command-rows", type=int, default=200)
    parser.add_argument("--max-candidate-rows", type=int, default=100)
    parser.add_argument("--title", default="Datacenter Dashboard")
    return parser


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
    max_command_rows: int,
    max_candidate_rows: int,
    generated_at_utc: str | None = None,
) -> tuple[str, DatacenterDashboardStatus, DatacenterDashboardBatchParseResult, DatacenterDecisionBatchResult]:
    dashboard_status = discover_datacenter_dashboard_status(reports_dir)
    parse_result = parse_datacenter_dashboard_reports(dashboard_status.reports)
    parsed_rows = _collect_rows(dashboard_status)
    decision_result = build_datacenter_ticker_decisions(parsed_rows)
    inspector_views = _build_inspector_views(decision_result.decisions, parsed_rows)
    generated_at = generated_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")

    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    missing_reports = sum(1 for report in dashboard_status.reports if report.status != "OK")
    report_summaries = _report_summary_by_horizon(parse_result)
    newest_report_timestamp = _newest_report_timestamp(dashboard_status)
    report_paths = {
        report.horizon: report.path or ""
        for report in dashboard_status.reports
    }

    header_summary_rows = "".join(
        "<tr>"
        f"<th>{escape(label)}</th>"
        f"<td>{_html_text(value)}</td>"
        "</tr>"
        for label, value in (
            ("Generated at UTC", generated_at),
            ("Reports dir", reports_dir),
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
    @media (max-width: 960px) {{
      .detail-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <section>
    <h1>{escape(title)}</h1>
    <nav class="nav-links" aria-label="Dashboard sections">
      <a href="#summary">Summary</a>
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

  <section id="filters" class="major-section">
    <h2>Filters</h2>
    <div class="filter-box">
      <p class="filter-help">Filters apply to Candidate Pullbacks, Command Center and Inspector rows.</p>
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
          "candidate-pullbacks": 0,
          "command-center": 0,
          "inspector": 0
        }};
        var sectionTotalCounts = {{
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

        var candidateStatus = document.getElementById("candidate-filter-status");
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = Path(args.output) if args.output else Path(args.reports_dir) / "datacenter_dashboard.html"
    html, dashboard_status, parse_result, decision_result = generate_dashboard_html(
        reports_dir=args.reports_dir,
        title=args.title,
        ticker=args.ticker,
        max_command_rows=args.max_command_rows,
        max_candidate_rows=args.max_candidate_rows,
    )
    output_path.write_text(html, encoding="utf-8")

    candidate_rows = sum(
        1
        for decision in decision_result.decisions
        if decision.pullback_validity in _CANDIDATE_PULLBACK_ORDER
    )
    print(f"SUMMARY html_output={output_path}")
    print(f"SUMMARY readiness={dashboard_status.overall_status}")
    print(f"SUMMARY decision_total={len(decision_result.decisions)}")
    print(f"SUMMARY candidate_pullback_rows={candidate_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
