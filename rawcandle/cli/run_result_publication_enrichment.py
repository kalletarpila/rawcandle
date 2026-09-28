from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rawcandle.fundamentals.admin.production_transaction import production_lock
from rawcandle.fundamentals.admin.publication_journal import (
    guard_production_writes,
    sqlite_verification,
)
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.fundamentals.result_publication import enrich_database
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_CANONICAL = ROOT / "data/fundamentals_v4.db"
DEFAULT_BACKUP_ROOT = ROOT / "backups/fundamentals_result_publication"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enrich canonical quarters with actual result-publication authority")
    parser.add_argument("--canonical-db", type=Path, default=PRODUCTION_CANONICAL)
    parser.add_argument("--from-fiscal-year", type=int, default=2025)
    parser.add_argument("--tickers", nargs="*", default=[])
    parser.add_argument("--company-ids", nargs="*", type=int, default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--report", type=Path)
    return parser


def _write_report(path: Path | None, result: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _apply(args: argparse.Namespace) -> dict[str, object]:
    target = args.canonical_db.resolve()
    production = target == PRODUCTION_CANONICAL.resolve()
    if production and not args.confirm_production:
        raise PermissionError("RESULT_PUBLICATION_PRODUCTION_CONFIRMATION_REQUIRED")

    backup: dict[str, object] | None = None
    if production:
        guard_production_writes()
        with production_lock():
            backup_path = args.backup_root / _stamp() / "fundamentals_v4.db"
            backup = online_backup(target, backup_path)
            backup["verification"] = sqlite_verification(backup_path)
            if args.schema_only:
                with sqlite3.connect(target) as connection:
                    connection.execute("PRAGMA foreign_keys=ON")
                    migration = ensure_result_publication_schema(connection)
            else:
                migration = None
                result = enrich_database(
                    target,
                    from_fiscal_year=args.from_fiscal_year,
                    tickers=args.tickers,
                    company_ids=args.company_ids,
                    apply=True,
                    refresh_existing=args.refresh_existing,
                )
            postflight = sqlite_verification(target)
    else:
        if args.schema_only:
            with sqlite3.connect(target) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                migration = ensure_result_publication_schema(connection)
        else:
            migration = None
            result = enrich_database(
                target,
                from_fiscal_year=args.from_fiscal_year,
                tickers=args.tickers,
                company_ids=args.company_ids,
                apply=True,
                refresh_existing=args.refresh_existing,
            )
        postflight = sqlite_verification(target)

    if args.schema_only:
        result = {"schema_only": True, "migration": migration}
    result.update({"production": production, "backup": backup, "postflight": postflight})
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.apply:
            result = _apply(args)
        else:
            if args.schema_only:
                raise ValueError("--schema-only requires --apply")
            result = enrich_database(
                args.canonical_db,
                from_fiscal_year=args.from_fiscal_year,
                tickers=args.tickers,
                company_ids=args.company_ids,
                apply=False,
                refresh_existing=args.refresh_existing,
            )
        _write_report(args.report, result)
        print(json.dumps(result, sort_keys=True))
        return 0 if not result.get("errors") else 1
    except Exception as exc:
        failure = {"ok": False, "error": type(exc).__name__, "reason": str(exc)}
        _write_report(args.report, failure)
        print(json.dumps(failure, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
