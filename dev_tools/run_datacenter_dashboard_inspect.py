from __future__ import annotations

import argparse
import sys

from dev_tools.inspect_ecosystem_dashboard import main as inspect_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DATACENTER-only compatibility wrapper for ecosystem dashboard inspect."
    )
    parser.add_argument("--dashboard-db", required=True)
    parser.add_argument("--report-date")
    parser.add_argument("--run-id")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--show-runs", action="store_true")
    parser.add_argument("--show-action-summary", action="store_true")
    parser.add_argument("--show-market-map", action="store_true")
    parser.add_argument("--show-watchlist", action="store_true")
    parser.add_argument("--show-tickers", action="store_true")
    parser.add_argument("--show-trace", action="store_true")
    parser.add_argument("--ticker")
    parser.add_argument("--market-level")
    parser.add_argument("--action")
    parser.add_argument("--format", choices=("text", "csv"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--ecosystem-code" in raw_argv:
        print("ERROR: --ecosystem-code is not supported by run_datacenter_dashboard_inspect.py; wrapper is DATACENTER-only")
        return 2
    args = build_parser().parse_args(raw_argv)
    delegated_argv = [
        "--dashboard-db",
        args.dashboard_db,
        "--ecosystem-code",
        "DATACENTER",
    ]
    if args.report_date:
        delegated_argv.extend(["--report-date", args.report_date])
    if args.run_id:
        delegated_argv.extend(["--run-id", args.run_id])
    if args.latest:
        delegated_argv.append("--latest")
    delegated_argv.extend(["--limit", str(args.limit)])
    if args.show_runs:
        delegated_argv.append("--show-runs")
    if args.show_action_summary:
        delegated_argv.append("--show-action-summary")
    if args.show_market_map:
        delegated_argv.append("--show-market-map")
    if args.show_watchlist:
        delegated_argv.append("--show-watchlist")
    if args.show_tickers:
        delegated_argv.append("--show-tickers")
    if args.show_trace:
        delegated_argv.append("--show-trace")
    if args.ticker:
        delegated_argv.extend(["--ticker", args.ticker])
    if args.market_level:
        delegated_argv.extend(["--market-level", args.market_level])
    if args.action:
        delegated_argv.extend(["--action", args.action])
    if args.format:
        delegated_argv.extend(["--format", args.format])
    return inspect_main(delegated_argv)


if __name__ == "__main__":
    raise SystemExit(main())
