from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dev_tools.datacenter_dashboard_decisions import build_datacenter_ticker_decisions
from dev_tools.datacenter_dashboard_parser import parse_datacenter_dashboard_reports
from dev_tools.datacenter_dashboard_support import discover_datacenter_dashboard_status
from dev_tools.ecosystem_dashboard_persistence import (
    persist_ecosystem_dashboard_input,
)
from dev_tools.ecosystem_dashboard_reports_adapter import (
    build_ecosystem_dashboard_input_from_reports_result,
)
from dev_tools.run_datacenter_dashboard_html import (
    _REPORT_DATE_RE,
    _collect_rows,
    build_dashboard_market_map_model,
    build_dashboard_ticker_model,
    build_dashboard_watchlist_model,
    generate_datacenter_dashboard_html_file,
)

DEFAULT_DASHBOARD_DB = "/home/kalle/projects/rawcandle/data/ecosystem_dashboard.db"
SUPPORTED_ECOSYSTEM_CODES = ("DATACENTER",)
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and persist ecosystem dashboard snapshots into a separate SQLite DB."
    )
    parser.add_argument("--dashboard-db", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--input-mode", default="reports")
    parser.add_argument("--mode", choices=("replace-date", "insert"), default="replace-date")
    parser.add_argument("--run-id")
    parser.add_argument("--render-html", action="store_true")
    parser.add_argument("--html-output")
    parser.add_argument("--title")
    return parser


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_run_id(ecosystem_code: str, report_date: str, generated_at_utc: str) -> str:
    timestamp = generated_at_utc.replace("-", "").replace(":", "")
    return f"ECO_DASHBOARD_{ecosystem_code}_{report_date}_{timestamp}"


def _validate_ecosystem_code(ecosystem_code: str) -> str:
    normalized = ecosystem_code.strip().upper()
    if normalized not in SUPPORTED_ECOSYSTEM_CODES:
        raise ValueError(
            f"unsupported ecosystem_code={ecosystem_code}; currently supported: DATACENTER"
        )
    return normalized


def _validate_input_mode(input_mode: str) -> str:
    normalized = input_mode.strip().lower()
    if normalized != "reports":
        raise ValueError(f"unsupported input_mode={input_mode}; currently supported: reports")
    return normalized


def generate_ecosystem_dashboard_build(
    *,
    dashboard_db: str,
    ecosystem_code: str,
    reports_dir: str,
    report_date: str,
    input_mode: str = "reports",
    mode: str,
    run_id: str | None = None,
) -> tuple[str, list[str]]:
    normalized_report_date = report_date.strip()
    if not _REPORT_DATE_RE.match(normalized_report_date):
        raise ValueError(f"invalid report_date format: {normalized_report_date}")

    normalized_ecosystem_code = _validate_ecosystem_code(ecosystem_code)
    normalized_input_mode = _validate_input_mode(input_mode)

    dashboard_status = discover_datacenter_dashboard_status(
        reports_dir,
        report_date=normalized_report_date,
    )
    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    missing_reports = sum(1 for report in dashboard_status.reports if report.status != "OK")
    if found_reports == 0:
        raise FileNotFoundError(
            f"no reports found for report_date={normalized_report_date} in {reports_dir}"
        )

    parse_result = parse_datacenter_dashboard_reports(dashboard_status.reports)
    parsed_rows = _collect_rows(dashboard_status)
    decision_result = build_datacenter_ticker_decisions(parsed_rows)
    market_map_rows = build_dashboard_market_map_model(dashboard_status)
    watchlist_rows = build_dashboard_watchlist_model(parsed_rows, decision_result.decisions)
    ticker_rows = build_dashboard_ticker_model(parsed_rows, decision_result.decisions)
    trace_rows = [
        (decision.ticker, trace_index, trace)
        for decision in decision_result.decisions
        for trace_index, trace in enumerate(decision.decision_trace)
    ]
    dashboard_input = build_ecosystem_dashboard_input_from_reports_result(
        ecosystem_code=normalized_ecosystem_code,
        report_date=normalized_report_date,
        reports_dir=reports_dir,
        dashboard_status=dashboard_status,
        parse_result=parse_result,
        decision_result=decision_result,
        market_map_rows=market_map_rows,
        watchlist_rows=watchlist_rows,
        ticker_rows=ticker_rows,
    )

    generated_at_utc = _utc_now_text()
    selected_run_id = run_id or _default_run_id(
        normalized_ecosystem_code,
        normalized_report_date,
        generated_at_utc,
    )
    persist_ecosystem_dashboard_input(
        dashboard_db=dashboard_db,
        dashboard_input=dashboard_input,
        mode=mode,
        run_id=selected_run_id,
    )

    summary_lines = [
        "SUMMARY ecosystem_dashboard_build.status=OK",
        f"SUMMARY ecosystem_dashboard_build.run_id={selected_run_id}",
        f"SUMMARY ecosystem_dashboard_build.ecosystem_code={normalized_ecosystem_code}",
        f"SUMMARY ecosystem_dashboard_build.report_date={normalized_report_date}",
        f"SUMMARY ecosystem_dashboard_build.input_mode={normalized_input_mode}",
        "SUMMARY ecosystem_dashboard_build.persistence_input=structured",
        f"SUMMARY ecosystem_dashboard_build.dashboard_db={dashboard_db}",
        f"SUMMARY ecosystem_dashboard_build.reports_dir={reports_dir}",
        f"SUMMARY ecosystem_dashboard_build.readiness={dashboard_status.overall_status}",
        f"SUMMARY ecosystem_dashboard_build.source_reports_count={len(dashboard_status.reports)}",
        f"SUMMARY ecosystem_dashboard_build.total_parsed_rows={parse_result.total_row_count}",
        f"SUMMARY ecosystem_dashboard_build.total_parse_warnings={parse_result.total_warning_count}",
        f"SUMMARY ecosystem_dashboard_build.decision_total={len(decision_result.decisions)}",
        f"SUMMARY ecosystem_dashboard_build.market_map_rows={len(market_map_rows)}",
        f"SUMMARY ecosystem_dashboard_build.watchlist_rows={len(watchlist_rows)}",
        f"SUMMARY ecosystem_dashboard_build.ticker_rows={len(ticker_rows)}",
        f"SUMMARY ecosystem_dashboard_build.trace_rows={len(trace_rows)}",
        f"SUMMARY ecosystem_dashboard_build.mode={mode}",
    ]
    return selected_run_id, summary_lines


def _validate_render_html_args(
    *,
    render_html: bool,
    html_output: str | None,
    ecosystem_code: str,
) -> str | None:
    normalized_output = html_output.strip() if html_output is not None and html_output.strip() else None
    if render_html and normalized_output is None:
        raise ValueError("--html-output is required when --render-html is provided")
    if not render_html and normalized_output is not None:
        raise ValueError("--html-output requires --render-html")
    if not render_html:
        return None
    if ecosystem_code.strip().upper() != "DATACENTER":
        raise ValueError(
            f"--render-html is currently supported only for ecosystem_code=DATACENTER; got {ecosystem_code}"
        )
    output_parent = Path(normalized_output).parent
    if not output_parent.exists():
        raise ValueError(f"html output parent directory does not exist: {output_parent}")
    return normalized_output


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        normalized_html_output = _validate_render_html_args(
            render_html=args.render_html,
            html_output=args.html_output,
            ecosystem_code=args.ecosystem_code,
        )
        built_run_id, summary_lines = generate_ecosystem_dashboard_build(
            dashboard_db=args.dashboard_db,
            ecosystem_code=args.ecosystem_code,
            reports_dir=args.reports_dir,
            report_date=args.report_date,
            input_mode=args.input_mode,
            mode=args.mode,
            run_id=args.run_id,
        )
    except ValueError as exc:
        print("SUMMARY ecosystem_dashboard_build.status=FAILED")
        print(f"ERROR: {exc}")
        return 2
    except (FileNotFoundError, sqlite3.DatabaseError, OSError) as exc:
        print("SUMMARY ecosystem_dashboard_build.status=FAILED")
        print(f"ERROR: {exc}")
        return 1
    if args.render_html:
        try:
            generate_datacenter_dashboard_html_file(
                dashboard_db=args.dashboard_db,
                ecosystem_code="DATACENTER",
                run_id=built_run_id,
                output=normalized_html_output,
                report_date=None,
                title=args.title,
            )
        except (ValueError, FileNotFoundError, sqlite3.DatabaseError, OSError) as exc:
            for line in summary_lines:
                print(line)
            print("SUMMARY ecosystem_dashboard_build.render_html_requested=1")
            print(f"SUMMARY ecosystem_dashboard_build.html_output_path={normalized_html_output}")
            print(f"ERROR: HTML render failed after successful build: {exc}")
            return 1
    for line in summary_lines:
        print(line)
    if args.render_html:
        print("SUMMARY ecosystem_dashboard_build.render_html_requested=1")
        print(f"SUMMARY ecosystem_dashboard_build.html_output_path={normalized_html_output}")
        print("SUMMARY ecosystem_dashboard_build.html_render_status=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
