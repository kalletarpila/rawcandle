from __future__ import annotations

import argparse

from dev_tools.run_ecosystem_dashboard_build import (
    DEFAULT_DASHBOARD_DB,
    generate_ecosystem_dashboard_build,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for Datacenter dashboard build."
    )
    parser.add_argument("--dashboard-db", default=DEFAULT_DASHBOARD_DB)
    parser.add_argument("--analysis-db")
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--mode", choices=("replace-date", "insert"), default="replace-date")
    parser.add_argument("--run-id")
    parser.add_argument("--title")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.analysis_db:
        print("WARNING --analysis-db is deprecated for dashboard build; use --dashboard-db")
    try:
        _run_id, summary_lines = generate_ecosystem_dashboard_build(
            dashboard_db=args.dashboard_db,
            ecosystem_code="DATACENTER",
            reports_dir=args.reports_dir,
            report_date=args.report_date,
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
    for line in summary_lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
