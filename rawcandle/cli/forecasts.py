from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rawcandle.forecasts.operator import (
    DEFAULT_FORECAST_DB,
    DEFAULT_FUNDAMENTALS_DB,
    DEFAULT_PILOT_SYMBOLS,
    acquire_run,
    link_run,
    migrate_database,
    reconcile_run,
    report_run,
)


def _paths(parser: argparse.ArgumentParser, *, fundamentals: bool = False) -> None:
    parser.add_argument("--db", default=str(DEFAULT_FORECAST_DB), help="Forecast database path")
    if fundamentals:
        parser.add_argument(
            "--fundamentals-db", default=str(DEFAULT_FUNDAMENTALS_DB),
            help="Read-only Fundamentals V4 database path",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RawCandle forecast operator workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate = subparsers.add_parser("migrate", help="Create or migrate forecasts.db")
    _paths(migrate)

    acquire = subparsers.add_parser("acquire", help="Run bounded selected-symbol acquisition")
    _paths(acquire, fundamentals=True)
    acquire.add_argument("--symbols", nargs="+", default=list(DEFAULT_PILOT_SYMBOLS))
    acquire.add_argument("--run-id")

    link = subparsers.add_parser("link", help="Create AS_KNOWN fiscal links for a run")
    _paths(link, fundamentals=True)
    link.add_argument("--run-id", required=True)

    reconcile = subparsers.add_parser(
        "reconcile", help="Create CURRENT_RECONCILED fiscal links for a run"
    )
    _paths(reconcile, fundamentals=True)
    reconcile.add_argument("--run-id", required=True)

    report = subparsers.add_parser("report", help="Print compact run report")
    _paths(report)
    report.add_argument("--run-id", required=True)
    report.add_argument("--json", action="store_true", help="Emit compact JSON")
    return parser


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _print_report(report: dict[str, Any]) -> None:
    print(
        f"RUN id={report['run_id']} status={report['run_status']} "
        f"symbols={report['symbols_attempted']} fetches={report['family_fetches_attempted']}"
    )
    for key in (
        "acquisition", "acquisition_by_family", "identity", "fiscal_link",
        "reconciliation", "end_date", "provider_quality",
    ):
        print(f"{key.upper()} {_compact(report[key])}")
    print(f"ANNUAL_MAPPINGS count={len(report['annual_mappings'])}")
    for item in report["annual_mappings"]:
        print(
            "ANNUAL "
            f"symbol={item['symbol']} horizon={item['provider_horizon']} "
            f"end_date={item['provider_end_date']} fiscal_year={item['fiscal_year']} "
            f"status={item['status']} reasons={','.join(item['reason_codes'])}"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "migrate":
            result = migrate_database(Path(args.db))
            print(f"MIGRATE {_compact(result)}")
        elif args.command == "acquire":
            result = acquire_run(
                forecast_db=Path(args.db), fundamentals_db=Path(args.fundamentals_db),
                symbols=args.symbols, run_id=args.run_id,
            )
            print(
                f"ACQUIRE run_id={result.run_id} symbols={len(result.symbols)} "
                f"counters={_compact(result.counters)}"
            )
        elif args.command == "link":
            result = link_run(
                args.run_id, forecast_db=Path(args.db),
                fundamentals_db=Path(args.fundamentals_db),
            )
            print(f"LINK run_id={args.run_id} counters={_compact(result)}")
        elif args.command == "reconcile":
            result = reconcile_run(
                args.run_id, forecast_db=Path(args.db),
                fundamentals_db=Path(args.fundamentals_db),
            )
            print(f"RECONCILE run_id={args.run_id} counters={_compact(result)}")
        else:
            result = report_run(args.run_id, forecast_db=Path(args.db))
            print(_compact(result)) if args.json else _print_report(result)
        return 0
    except Exception as exc:
        print(f"ERROR command={args.command} type={type(exc).__name__} message={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
