from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import (
    EcosystemDashboardSnapshot,
    load_dashboard_snapshot,
)
from dev_tools.run_datacenter_dashboard_html import _REPORT_DATE_RE

_MARKET_MAP_COLUMNS = (
    "market_level",
    "name",
    "layer",
    "subindustry",
    "current_status",
    "start_status_30d",
    "status_change_30d",
    "status_change_5d",
    "window_status_30d",
    "window_status_5d",
    "window_status_2d",
    "overheat_risk",
    "pct_above_ema20",
    "pct_above_ma10",
    "ema20_breadth_delta_5d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "trend_state",
    "latest_structure_label",
    "latest_bos_event_type",
    "latest_reset_reason",
    "source_horizons",
    "source_files",
)
_WATCHLIST_COLUMNS = (
    "ticker",
    "action",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority_label",
    "trend_state",
    "latest_structure_label",
    "ma_break_status",
    "freshness_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "current_status",
    "window_status_30d",
    "window_status_5d",
    "window_status_2d",
)
_TICKER_COLUMNS = (
    "ticker",
    "action",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority_label",
    "layer",
    "subindustry",
    "trend_state",
    "latest_structure_label",
    "ma_break_status",
    "freshness_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "current_status",
    "window_status_30d",
    "window_status_5d",
    "window_status_2d",
)
_DECISION_TRACE_COLUMNS = (
    "ticker",
    "trace_index",
    "action",
    "matched_rule",
    "matched_token",
    "matched_value",
    "horizon",
    "field",
)


@dataclass(frozen=True)
class DatacenterDashboardMarkdownGenerationResult:
    output_path: str
    report_date: str
    run_id: str
    summary_lines: tuple[str, ...]


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _escape_markdown_cell(value: object | None) -> str:
    return _normalize_text(value).replace("|", "\\|")


def _display_label(name: str) -> str:
    return name.replace("_", " ")


def _render_markdown_table(
    *,
    rows: list[dict[str, object]],
    columns: tuple[str, ...],
    empty_message: str,
) -> list[str]:
    if not rows:
        return [empty_message]
    headers = " | ".join(_display_label(column) for column in columns)
    separators = " | ".join("---" for _ in columns)
    output = [f"| {headers} |", f"| {separators} |"]
    for row in rows:
        values = " | ".join(_escape_markdown_cell(row.get(column)) for column in columns)
        output.append(f"| {values} |")
    return output


def _render_run_summary(
    *,
    snapshot: EcosystemDashboardSnapshot,
    dashboard_db: str,
) -> list[str]:
    run = snapshot.run
    summary_rows = [
        ("ecosystem_code", run.ecosystem_code),
        ("report_date", run.report_date),
        ("run_id", run.run_id),
        ("selection_mode", run.mode or ""),
        ("readiness", run.status or ""),
        ("created_at_utc", run.created_at_utc or ""),
        ("dashboard_db", dashboard_db),
    ]
    output = ["## Run Summary", ""]
    for key, value in summary_rows:
        output.append(f"- {key}: {_normalize_text(value)}")
    return output


def _render_decision_trace(rows: list[dict[str, object]]) -> list[str]:
    output = ["## Decision Trace", ""]
    if not rows:
        output.append("No decision trace rows.")
        return output
    visible_rows = rows
    if len(rows) > 100:
        visible_rows = rows[:50]
        output.append(f"Decision trace truncated: showing 50 of {len(rows)} rows.")
        output.append("")
    output.extend(
        _render_markdown_table(
            rows=visible_rows,
            columns=_DECISION_TRACE_COLUMNS,
            empty_message="No decision trace rows.",
        )
    )
    return output


def render_datacenter_dashboard_markdown(
    *,
    snapshot: EcosystemDashboardSnapshot,
    dashboard_db: str,
    title: str | None = None,
) -> str:
    selected_title = title or "Datacenter Dashboard"
    output = [
        f"# {selected_title} - {snapshot.run.report_date}",
        "",
        *_render_run_summary(snapshot=snapshot, dashboard_db=dashboard_db),
        "",
        "## Action Summary",
        "",
        *_render_markdown_table(
            rows=snapshot.action_summary,
            columns=("action", "count"),
            empty_message="No action summary rows.",
        ),
        "",
        "## Market Map",
        "",
        *_render_markdown_table(
            rows=snapshot.market_map,
            columns=_MARKET_MAP_COLUMNS,
            empty_message="No market map rows.",
        ),
        "",
        "## Watchlist",
        "",
        *_render_markdown_table(
            rows=snapshot.watchlist,
            columns=_WATCHLIST_COLUMNS,
            empty_message="No watchlist rows.",
        ),
        "",
        "## Tickers",
        "",
        *_render_markdown_table(
            rows=snapshot.tickers,
            columns=_TICKER_COLUMNS,
            empty_message="No ticker rows.",
        ),
        "",
        *_render_decision_trace(snapshot.decision_trace),
        "",
    ]
    return "\n".join(output)


def generate_datacenter_dashboard_markdown_file(
    *,
    dashboard_db: str,
    output_path: str,
    ecosystem_code: str = "DATACENTER",
    report_date: str | None = None,
    run_id: str | None = None,
    title: str | None = None,
) -> DatacenterDashboardMarkdownGenerationResult:
    normalized_report_date = report_date.strip() if report_date and report_date.strip() else None
    if normalized_report_date is not None and not _REPORT_DATE_RE.match(normalized_report_date):
        raise ValueError(f"invalid report_date format: {normalized_report_date}")
    normalized_run_id = run_id.strip() if run_id and run_id.strip() else None
    if normalized_run_id is None and normalized_report_date is None:
        raise ValueError("markdown renderer requires --run-id or --report-date")

    snapshot = load_dashboard_snapshot(
        dashboard_db=dashboard_db,
        ecosystem_code=ecosystem_code,
        report_date=normalized_report_date,
        run_id=normalized_run_id,
    )
    markdown = render_datacenter_dashboard_markdown(
        snapshot=snapshot,
        dashboard_db=dashboard_db,
        title=title,
    )
    resolved_output_path = Path(output_path)
    resolved_output_path.write_text(markdown, encoding="utf-8")
    summary_lines = (
        "SUMMARY datacenter_dashboard_markdown.input_mode=dashboard_db",
        f"SUMMARY datacenter_dashboard_markdown.ecosystem_code={snapshot.run.ecosystem_code}",
        f"SUMMARY datacenter_dashboard_markdown.report_date={snapshot.run.report_date}",
        f"SUMMARY datacenter_dashboard_markdown.run_id={snapshot.run.run_id}",
        f"SUMMARY datacenter_dashboard_markdown.output_path={resolved_output_path}",
        "SUMMARY datacenter_dashboard_markdown.status=OK",
    )
    return DatacenterDashboardMarkdownGenerationResult(
        output_path=str(resolved_output_path),
        report_date=snapshot.run.report_date,
        run_id=snapshot.run.run_id,
        summary_lines=summary_lines,
    )
