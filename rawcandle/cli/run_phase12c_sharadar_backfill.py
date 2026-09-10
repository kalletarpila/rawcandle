from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rawcandle.fundamentals.schema.phase12c_backfill import (
    HISTORY_YEARS, Phase12CPaths, create_verified_backup, database_inventory,
    disk_gate, import_staged, isolation_inventory, provider_counts,
    staged_provider_reconciliation, validate_staged_source,
)
from rawcandle.fundamentals.schema.production_bootstrap import download_sharadar_bulk, target_tickers
from rawcandle.fundamentals.schema.prototype import write_csv, write_json


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = {
    "provider": ROOT / "data/fundamentals_provider.db",
    "canonical": ROOT / "data/fundamentals_v4.db",
    "analysis": ROOT / "data/fundamentals_analysis.db",
    "market": ROOT / "data/osakedata.db",
    "taxonomy": ROOT / "data/analysis.db",
}
BACKUP_DIR = ROOT / "backups"
CONFIRMATION = "CONFIRM_PHASE12C_PROVIDER_ONLY_10Y_BACKFILL"


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def phase_paths(args: argparse.Namespace) -> Phase12CPaths:
    return Phase12CPaths(
        ROOT, args.output.resolve(), args.provider_db.resolve(), args.canonical_db.resolve(),
        args.analysis_db.resolve(), args.market_db.resolve(), args.taxonomy_db.resolve(),
        (ROOT / "fundamental_reports").resolve(), args.bootstrap_csv.resolve(), args.backup_dir.resolve(),
    )


def validate_request(args: argparse.Namespace) -> None:
    supplied = (args.provider_db, args.canonical_db, args.analysis_db, args.market_db, args.taxonomy_db)
    expected = tuple(PRODUCTION.values())
    if any(actual.resolve() != wanted.resolve() for actual, wanted in zip(supplied, expected)):
        raise RuntimeError("PHASE12C_EXACT_PRODUCTION_PATHS_REQUIRED")
    if args.backup_dir.resolve() != BACKUP_DIR.resolve():
        raise RuntimeError("PHASE12C_EXACT_BACKUP_PATH_REQUIRED")
    if any(path.is_symlink() or not path.is_file() for path in expected):
        raise RuntimeError("PHASE12C_REGULAR_PRODUCTION_DATABASES_REQUIRED")
    output = args.output.resolve()
    allowed = (ROOT / "temp/fundamentals_v4_phase12c").resolve()
    if allowed not in output.parents or output.exists() or args.output.is_symlink():
        raise RuntimeError("PHASE12C_NEW_OUTPUT_UNDER_TEMP_REQUIRED")
    if not args.bootstrap_csv.resolve().is_file() or args.bootstrap_csv.is_symlink():
        raise RuntimeError("PHASE12C_REGULAR_BOOTSTRAP_UNIVERSE_REQUIRED")
    if args.apply and args.confirm != CONFIRMATION:
        raise RuntimeError("PHASE12C_EXPLICIT_CONFIRMATION_REQUIRED")


def run(args: argparse.Namespace) -> dict[str, object]:
    validate_request(args)
    paths = phase_paths(args)
    paths.output.mkdir(parents=True)
    before_counts = provider_counts(paths.provider_db)
    preflight = {
        "head": _git("rev-parse", "HEAD"), "branch": _git("branch", "--show-current"),
        "status": _git("status", "--porcelain"), "branch_state": _git("status", "-sb").splitlines()[0],
        "paths": {name: str(path.resolve()) for name, path in PRODUCTION.items()},
        "provider_before": database_inventory(paths.provider_db),
        "provider_counts_before": before_counts, "disk_gate": disk_gate(paths), "apply": args.apply,
    }
    write_json(paths.output / "preflight.json", preflight)
    old_arq = next(row["oldest"] for row in before_counts["by_dimension"] if row["dimension"] == "ARQ")
    if args.staged_source:
        source = args.staged_source.resolve()
        if not source.is_file() or source.is_symlink():
            raise RuntimeError("PHASE12C_REGULAR_STAGED_SOURCE_REQUIRED")
        shutil.copyfile(source, paths.staged_csv)
        manifest = {"status": "REUSED_STAGED_SOURCE", "history_scope": "years=10",
                    "extracted_path": str(paths.staged_csv)}
    else:
        manifest = download_sharadar_bulk(
            paths.production_paths(), years=HISTORY_YEARS,
            manifest_name="sharadar_10y_bulk_manifest.json", timeout_seconds=args.timeout,
        )
        if manifest.get("status") != "SUCCESS":
            raise RuntimeError("PHASE12C_DOWNLOAD_FAILED:" + json.dumps(manifest, sort_keys=True))
    write_json(paths.output / "download_manifest.json", manifest)
    validation = validate_staged_source(
        paths.staged_csv, target=target_tickers(paths.bootstrap_csv), old_oldest_arq=old_arq,
    )
    write_json(paths.output / "staged_validation.json", validation)
    reconciliation = staged_provider_reconciliation(
        paths.staged_csv, paths.provider_db, target=target_tickers(paths.bootstrap_csv),
    )
    write_json(paths.output / "staged_provider_reconciliation.json", reconciliation)
    write_csv(paths.output / "rows_by_year.csv", validation["rows_by_year"])
    write_csv(paths.output / "rows_by_fiscal_quarter.csv", validation["rows_by_fiscal_quarter"])
    write_csv(paths.output / "ticker_coverage_by_year.csv", validation["ticker_coverage_by_year"])
    if not args.apply:
        return {"outcome": "STAGED_VALIDATED", "output": str(paths.output),
                "validation": validation, "reconciliation": reconciliation}

    isolation_before = isolation_inventory(paths)
    write_json(paths.output / "production_isolation_before.json", isolation_before)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = create_verified_backup(paths.provider_db, paths.backup_dir, stamp)
    write_json(paths.output / "backup_manifest.json", backup)
    first = import_staged(paths, validation)
    write_json(paths.output / "first_import.json", first)
    after_first = database_inventory(paths.provider_db)
    second = import_staged(paths, validation)
    after_second = database_inventory(paths.provider_db)
    second["physical_noop"] = {key: after_first[key] == after_second[key] for key in (
        "size", "mtime_ns", "page_count", "freelist_count", "sha256", "wal_exists", "shm_exists",
    )}
    if second["logical_changes"] or not all(second["physical_noop"].values()):
        raise RuntimeError("PHASE12C_SECOND_IMPORT_NOT_NOOP")
    write_json(paths.output / "second_import.json", second)
    isolation_after = isolation_inventory(paths)
    if isolation_before["fingerprint"] != isolation_after["fingerprint"]:
        raise RuntimeError("PHASE12C_NON_PROVIDER_PRODUCTION_CHANGED")
    write_json(paths.output / "production_isolation_after.json", isolation_after)
    post = {"provider_after": after_second, "provider_counts_after": provider_counts(paths.provider_db)}
    write_json(paths.output / "post_import.json", post)
    result = {"outcome": "PROVIDER_BACKFILL_COMPLETE", "output": str(paths.output),
              "first_import": first, "second_import": second, "backup": backup,
              "validation": validation, **post}
    write_json(paths.output / "phase12c_result.json", result)
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Stage and import the provider-only Sharadar 10-year backfill")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    value.add_argument("--provider-db", type=Path, default=PRODUCTION["provider"])
    value.add_argument("--canonical-db", type=Path, default=PRODUCTION["canonical"])
    value.add_argument("--analysis-db", type=Path, default=PRODUCTION["analysis"])
    value.add_argument("--market-db", type=Path, default=PRODUCTION["market"])
    value.add_argument("--taxonomy-db", type=Path, default=PRODUCTION["taxonomy"])
    value.add_argument("--bootstrap-csv", type=Path, required=True)
    value.add_argument("--backup-dir", type=Path, default=BACKUP_DIR)
    value.add_argument("--output", type=Path, default=ROOT / "temp/fundamentals_v4_phase12c" / stamp)
    value.add_argument("--staged-source", type=Path)
    value.add_argument("--timeout", type=float, default=600.0)
    value.add_argument("--apply", action="store_true")
    value.add_argument("--confirm")
    return value


def main() -> int:
    try:
        print(json.dumps(run(parser().parse_args()), sort_keys=True, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"outcome": "FAILED", "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
