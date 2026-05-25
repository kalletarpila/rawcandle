from __future__ import annotations

import argparse

from dev_tools.run_ecosystem_dashboard_build import (
    DEFAULT_DASHBOARD_DB,
    _validate_render_html_args,
    generate_ecosystem_dashboard_build,
)
from dev_tools.run_datacenter_dashboard_html import generate_datacenter_dashboard_html_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for Datacenter dashboard build."
    )
    parser.add_argument("--dashboard-db", default=DEFAULT_DASHBOARD_DB)
    parser.add_argument("--analysis-db")
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.analysis_db:
        print("WARNING --analysis-db is deprecated for dashboard build; use --dashboard-db")
    try:
        normalized_html_output = _validate_render_html_args(
            render_html=args.render_html,
            html_output=args.html_output,
            ecosystem_code="DATACENTER",
        )
        built_run_id, summary_lines = generate_ecosystem_dashboard_build(
            dashboard_db=args.dashboard_db,
            ecosystem_code="DATACENTER",
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
    except FileNotFoundError as exc:
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
        except (ValueError, FileNotFoundError, OSError) as exc:
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
