from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rawcandle.forecasts.hardening import (
    DEFAULT_BACKUP_DIR,
    backup_retention,
    cleanup_raw_evidence,
    create_backup,
    daily_workflow,
    health_report,
    restore_backup,
    universe_preview,
)
from rawcandle.forecasts.operator import (
    DEFAULT_FORECAST_DB,
    DEFAULT_FUNDAMENTALS_DB,
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


def _apply_mode(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RawCandle forecast operator workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate = subparsers.add_parser("migrate", help="Create or migrate forecasts.db")
    _paths(migrate)

    acquire = subparsers.add_parser("acquire", help="Run bounded selected-symbol acquisition")
    _paths(acquire, fundamentals=True)
    acquire.add_argument("--symbols", nargs="+")
    acquire.add_argument("--run-id")
    acquire.add_argument("--resume-run-id")

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

    health = subparsers.add_parser("health", help="Report forecast operational health")
    _paths(health)
    health.add_argument("--lookback-days", type=int, default=7)

    cleanup = subparsers.add_parser("cleanup-raw", help="Clean expired raw evidence")
    _paths(cleanup)
    _apply_mode(cleanup)

    backup = subparsers.add_parser("backup", help="Create a verified forecast backup")
    _paths(backup)
    backup.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))

    retention = subparsers.add_parser("backup-retention", help="Apply forecast backup retention")
    retention.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    _apply_mode(retention)

    restore = subparsers.add_parser("restore", help="Restore a verified forecast backup")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--target", required=True)
    restore.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    restore.add_argument("--apply-production", action="store_true")

    universe = subparsers.add_parser("universe-preview", help="Preview the canonical forecast universe")
    universe.add_argument("--fundamentals-db", default=str(DEFAULT_FUNDAMENTALS_DB))
    universe.add_argument("--minimum-interval-seconds", type=float, default=0.5)

    daily = subparsers.add_parser("daily", help="Run the bounded forecast daily workflow")
    _paths(daily, fundamentals=True)
    daily.add_argument(
        "--max-symbols", type=int, required=True,
        help="Required safety bound over the canonical active universe",
    )
    daily.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
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
                symbols=args.symbols, run_id=args.run_id, resume_run_id=args.resume_run_id,
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
        elif args.command == "report":
            result = report_run(args.run_id, forecast_db=Path(args.db))
            print(_compact(result)) if args.json else _print_report(result)
        elif args.command == "health":
            print(f"HEALTH {_compact(health_report(forecast_db=Path(args.db), lookback_days=args.lookback_days))}")
        elif args.command == "cleanup-raw":
            print(f"CLEANUP_RAW {_compact(cleanup_raw_evidence(forecast_db=Path(args.db), apply=args.apply))}")
        elif args.command == "backup":
            print(f"BACKUP {_compact(create_backup(source=Path(args.db), destination=Path(args.backup_dir)))}")
        elif args.command == "backup-retention":
            print(f"BACKUP_RETENTION {_compact(backup_retention(backup_dir=Path(args.backup_dir), apply=args.apply))}")
        elif args.command == "restore":
            print(f"RESTORE {_compact(restore_backup(backup=Path(args.backup), target=Path(args.target), apply_production=args.apply_production, backup_dir=Path(args.backup_dir)))}")
        elif args.command == "universe-preview":
            preview = universe_preview(
                fundamentals_db=Path(args.fundamentals_db),
                minimum_interval_seconds=args.minimum_interval_seconds,
            )
            preview.pop("symbols", None)
            print(f"UNIVERSE {_compact(preview)}")
        else:
            if args.max_symbols < 1:
                raise ValueError("--max-symbols must be positive")
            result = daily_workflow(
                max_symbols=args.max_symbols, forecast_db=Path(args.db),
                fundamentals_db=Path(args.fundamentals_db),
                backup_dir=Path(args.backup_dir),
            )
            print(f"DAILY {_compact(result)}")
        return 0
    except Exception as exc:
        print(f"ERROR command={args.command} type={type(exc).__name__} message={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
