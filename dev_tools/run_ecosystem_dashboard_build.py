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
from dev_tools.ecosystem_dashboard_structured_json import (
    load_ecosystem_dashboard_input_json,
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
    parser.add_argument("--reports-dir")
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--input-mode", default="reports")
    parser.add_argument("--structured-input-json")
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
    if normalized not in {"reports", "structured"}:
        raise ValueError(
            f"unsupported input_mode={input_mode}; currently supported: reports, structured"
        )
    return normalized


def _validate_input_mode_args(
    *,
    input_mode: str,
    reports_dir: str | None,
    structured_input_json: str | None,
) -> tuple[str | None, str | None]:
    normalized_reports_dir = reports_dir.strip() if reports_dir and reports_dir.strip() else None
    normalized_structured_input_json = (
        structured_input_json.strip()
        if structured_input_json and structured_input_json.strip()
        else None
    )
    if input_mode == "reports":
        if normalized_reports_dir is None:
            raise ValueError("--reports-dir is required when --input-mode=reports")
        if normalized_structured_input_json is not None:
            raise ValueError(
                "--structured-input-json is not allowed when --input-mode=reports"
            )
        return normalized_reports_dir, None
    if normalized_structured_input_json is None:
        raise ValueError(
            "--structured-input-json is required when --input-mode=structured"
        )
    if normalized_reports_dir is not None:
        raise ValueError("--reports-dir is not allowed when --input-mode=structured")
    return None, normalized_structured_input_json


def generate_ecosystem_dashboard_build(
    *,
    dashboard_db: str,
    ecosystem_code: str,
    reports_dir: str | None,
    report_date: str,
    input_mode: str = "reports",
    structured_input_json: str | None = None,
    mode: str,
    run_id: str | None = None,
) -> tuple[str, list[str]]:
    normalized_report_date = report_date.strip()
    if not _REPORT_DATE_RE.match(normalized_report_date):
        raise ValueError(f"invalid report_date format: {normalized_report_date}")

    normalized_ecosystem_code = _validate_ecosystem_code(ecosystem_code)
    normalized_input_mode = _validate_input_mode(input_mode)
    normalized_reports_dir, normalized_structured_input_json = _validate_input_mode_args(
        input_mode=normalized_input_mode,
        reports_dir=reports_dir,
        structured_input_json=structured_input_json,
    )

    reports_dir_summary = normalized_reports_dir or ""
    structured_input_json_summary = normalized_structured_input_json

    if normalized_input_mode == "reports":
        dashboard_status = discover_datacenter_dashboard_status(
            normalized_reports_dir,
            report_date=normalized_report_date,
        )
        found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
        missing_reports = sum(1 for report in dashboard_status.reports if report.status != "OK")
        if found_reports == 0:
            raise FileNotFoundError(
                f"no reports found for report_date={normalized_report_date} in {normalized_reports_dir}"
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
            reports_dir=normalized_reports_dir,
            dashboard_status=dashboard_status,
            parse_result=parse_result,
            decision_result=decision_result,
            market_map_rows=market_map_rows,
            watchlist_rows=watchlist_rows,
            ticker_rows=ticker_rows,
        )
        readiness = dashboard_status.overall_status
        source_reports_count = len(dashboard_status.reports)
        total_parsed_rows = parse_result.total_row_count
        total_parse_warnings = parse_result.total_warning_count
        decision_total = len(decision_result.decisions)
        market_map_count = len(market_map_rows)
        watchlist_count = len(watchlist_rows)
        ticker_count = len(ticker_rows)
        trace_count = len(trace_rows)
    else:
        dashboard_input = load_ecosystem_dashboard_input_json(normalized_structured_input_json)
        if dashboard_input.ecosystem_code != normalized_ecosystem_code:
            raise ValueError(
                "structured input ecosystem_code does not match CLI "
                f"--ecosystem-code: {dashboard_input.ecosystem_code} != {normalized_ecosystem_code}"
            )
        if dashboard_input.report_date != normalized_report_date:
            raise ValueError(
                "structured input report_date does not match CLI "
                f"--report-date: {dashboard_input.report_date} != {normalized_report_date}"
            )
        readiness = dashboard_input.readiness or "UNKNOWN"
        source_reports_count = len(dashboard_input.source_reports)
        total_parsed_rows = dashboard_input.total_parsed_rows or 0
        total_parse_warnings = dashboard_input.total_parse_warnings or 0
        decision_total = len(dashboard_input.tickers)
        market_map_count = len(dashboard_input.market_map)
        watchlist_count = len(dashboard_input.watchlist)
        ticker_count = len(dashboard_input.tickers)
        trace_count = len(dashboard_input.decision_trace)

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
        f"SUMMARY ecosystem_dashboard_build.reports_dir={reports_dir_summary}",
        f"SUMMARY ecosystem_dashboard_build.readiness={readiness}",
        f"SUMMARY ecosystem_dashboard_build.source_reports_count={source_reports_count}",
        f"SUMMARY ecosystem_dashboard_build.total_parsed_rows={total_parsed_rows}",
        f"SUMMARY ecosystem_dashboard_build.total_parse_warnings={total_parse_warnings}",
        f"SUMMARY ecosystem_dashboard_build.decision_total={decision_total}",
        f"SUMMARY ecosystem_dashboard_build.market_map_rows={market_map_count}",
        f"SUMMARY ecosystem_dashboard_build.watchlist_rows={watchlist_count}",
        f"SUMMARY ecosystem_dashboard_build.ticker_rows={ticker_count}",
        f"SUMMARY ecosystem_dashboard_build.trace_rows={trace_count}",
        f"SUMMARY ecosystem_dashboard_build.mode={mode}",
    ]
    if normalized_structured_input_json is not None:
        summary_lines.append(
            f"SUMMARY ecosystem_dashboard_build.structured_input_json={normalized_structured_input_json}"
        )
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
            structured_input_json=args.structured_input_json,
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
