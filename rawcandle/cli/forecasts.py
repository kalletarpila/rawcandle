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
    forecast_daily_lock,
    health_report,
    restore_rehearsal,
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
from rawcandle.forecasts.scheduler import install_scheduler


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

    rehearsal = subparsers.add_parser(
        "restore-rehearsal", help="Restore and validate the latest forecast backup"
    )
    rehearsal.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    rehearsal.add_argument(
        "--target", default="/tmp/rawcandle_forecasts_restore_rehearsal.db"
    )

    universe = subparsers.add_parser("universe-preview", help="Preview the canonical forecast universe")
    universe.add_argument("--fundamentals-db", default=str(DEFAULT_FUNDAMENTALS_DB))
    universe.add_argument("--minimum-interval-seconds", type=float, default=0.5)

    daily = subparsers.add_parser("daily", help="Run the bounded forecast daily workflow")
    _paths(daily, fundamentals=True)
    daily_scope = daily.add_mutually_exclusive_group(required=True)
    daily_scope.add_argument(
        "--max-symbols", type=int,
        help="Required safety bound over the canonical active universe",
    )
    daily_scope.add_argument(
        "--full-bounded-universe", action="store_true",
        help="Use the complete canonical active bounded universe",
    )
    daily.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))

    scheduler = subparsers.add_parser(
        "scheduler-install", help="Install the independent forecast systemd user timer"
    )
    scheduler.add_argument("--apply", action="store_true")
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


def _compact_daily(result: dict[str, Any]) -> dict[str, Any]:
    report = result.get("report") or {}
    acquisition = report.get("acquisition") or result.get("acquisition") or {}
    statuses = (
        "SUCCESS_CHANGED", "SUCCESS_UNCHANGED", "VALID_NO_DATA",
        "PROVIDER_SYMBOL_UNAVAILABLE", "RATE_LIMITED", "TRANSIENT_FAILURE",
        "MALFORMED_OR_SCHEMA_MISMATCH",
    )
    backup = result.get("backup") or {}
    health = result.get("health") or {}
    identity = report.get("identity") or {}
    fiscal = report.get("fiscal_link") or {}
    return {
        "terminal_status": result["terminal_status"],
        "operational_signals": result.get("operational_signals", []),
        "run_id": result.get("run_id"),
        "universe": result.get("universe"),
        "family_requests_attempted": report.get("family_fetches_attempted", 0),
        "acquisition": {key: int(acquisition.get(key, 0)) for key in statuses},
        "identity": {
            key: int(identity.get(key, 0))
            for key in (
                "PROVIDER_IDENTITY", "TICKER_ALIAS_AS_OF", "CURRENT_TICKER",
                "AMBIGUOUS", "UNRESOLVED",
            )
        },
        "fiscal_links": {
            key: int(fiscal.get(key, 0))
            for key in ("LINKED", "AMBIGUOUS", "UNRESOLVED")
        },
        "provider_quality": result.get("run_provider_quality", {}),
        "runtime": result.get("runtime", {}),
        "database_growth": result.get("database_growth", {}),
        "database_quick_check": (health.get("database") or {}).get("quick_check"),
        "database_totals": {
            "runs": (health.get("recent_acquisition") or {}).get("runs"),
            "fetches": (health.get("recent_acquisition") or {}).get("fetches"),
            "snapshots_by_family": (health.get("history") or {}).get(
                "snapshot_count_by_family", {}
            ),
            "raw_evidence_bytes": (health.get("provider_quality") or {}).get(
                "raw_evidence_bytes"
            ),
        },
        "backup": {
            "path": backup.get("backup_path"),
            "manifest": backup.get("manifest_path"),
            "quick_check": backup.get("quick_check"),
            "size_bytes": backup.get("backup_size_bytes"),
        },
        "errors": result.get("errors", {}),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "migrate":
            with forecast_daily_lock(Path(args.db)):
                result = migrate_database(Path(args.db))
            print(f"MIGRATE {_compact(result)}")
        elif args.command == "acquire":
            with forecast_daily_lock(Path(args.db)):
                result = acquire_run(
                    forecast_db=Path(args.db), fundamentals_db=Path(args.fundamentals_db),
                    symbols=args.symbols, run_id=args.run_id,
                    resume_run_id=args.resume_run_id,
                )
            print(
                f"ACQUIRE run_id={result.run_id} symbols={len(result.symbols)} "
                f"counters={_compact(result.counters)}"
            )
        elif args.command == "link":
            with forecast_daily_lock(Path(args.db)):
                result = link_run(
                    args.run_id, forecast_db=Path(args.db),
                    fundamentals_db=Path(args.fundamentals_db),
                )
            print(f"LINK run_id={args.run_id} counters={_compact(result)}")
        elif args.command == "reconcile":
            with forecast_daily_lock(Path(args.db)):
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
            if args.apply:
                with forecast_daily_lock(Path(args.db)):
                    result = cleanup_raw_evidence(
                        forecast_db=Path(args.db), apply=True
                    )
            else:
                result = cleanup_raw_evidence(forecast_db=Path(args.db), apply=False)
            print(f"CLEANUP_RAW {_compact(result)}")
        elif args.command == "backup":
            print(f"BACKUP {_compact(create_backup(source=Path(args.db), destination=Path(args.backup_dir)))}")
        elif args.command == "backup-retention":
            print(f"BACKUP_RETENTION {_compact(backup_retention(backup_dir=Path(args.backup_dir), apply=args.apply))}")
        elif args.command == "restore":
            with forecast_daily_lock(Path(args.target)):
                result = restore_backup(
                    backup=Path(args.backup), target=Path(args.target),
                    apply_production=args.apply_production,
                    backup_dir=Path(args.backup_dir),
                )
            print(f"RESTORE {_compact(result)}")
        elif args.command == "restore-rehearsal":
            print(f"RESTORE_REHEARSAL {_compact(restore_rehearsal(backup_dir=Path(args.backup_dir), target=Path(args.target)))}")
        elif args.command == "universe-preview":
            preview = universe_preview(
                fundamentals_db=Path(args.fundamentals_db),
                minimum_interval_seconds=args.minimum_interval_seconds,
            )
            preview.pop("symbols", None)
            print(f"UNIVERSE {_compact(preview)}")
        elif args.command == "daily":
            if args.max_symbols is not None and args.max_symbols < 1:
                raise ValueError("--max-symbols must be positive")
            result = daily_workflow(
                max_symbols=args.max_symbols, forecast_db=Path(args.db),
                full_bounded_universe=args.full_bounded_universe,
                fundamentals_db=Path(args.fundamentals_db),
                backup_dir=Path(args.backup_dir),
            )
            print(f"DAILY {_compact(_compact_daily(result))}")
            return 0 if result["terminal_status"] == "SUCCESS" else 2
        else:
            result = install_scheduler(
                repo_root=Path(__file__).resolve().parents[2], apply=args.apply
            )
            print(f"SCHEDULER_INSTALL {_compact(result)}")
        return 0
    except Exception as exc:
        code = getattr(exc, "code", "FAILED")
        print(
            f"ERROR command={args.command} status=FAILED signal={code} "
            f"type={type(exc).__name__} message={exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
