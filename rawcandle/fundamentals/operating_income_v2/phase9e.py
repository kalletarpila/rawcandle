from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT as DELTA_V1
from rawcandle.fundamentals.diagnostic_flags.engine import MODEL_FINGERPRINT as DIAGNOSTIC_V1
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_V1
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RELATIVE_V1
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_V1
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.ui_service import FundamentalsSnapshotUIService, resolve_report_download
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_V1

from . import contract, delta, diagnostic_flags, lifecycle, relative_position, score, snapshot, valuation
from .activation import activate_v2, assert_v2_active, deactivate_v2
from .persistence import MODEL_MAP, PACKAGE_FINGERPRINT, apply_package, row_counts
from .phase9d import PRODUCTION, compare_production_integrity, deep_reconcile, production_integrity
from .pipeline import refresh_active_package
from .readers import ActiveModelRepository, ParallelModelRepository
from .rehearsal import calculate


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BACKUP_DIR = ROOT / "backups"
LOCK_PATH = ROOT / "temp" / ".fundamentals_phase9e.lock"
EXPECTED_MODELS = {name: fingerprint for name, (_version, fingerprint) in MODEL_MAP.items()}
EXPECTED_REFERENCE = {
    "AMZN": (56.08, 18.43), "GOOG": (77.53, 27.82), "NVDA": (96.94, 27.02),
    "CRMD": (91.08, 100.0), "APD": (26.96, 0.0),
}
DATABASE_TYPES = {
    "canonical": "v4_ttm_values", "analysis": "score_result", "market": "osakedata",
    "provider": "provider_observation", "taxonomy": "ec_entity",
}


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def validate_request(args: argparse.Namespace) -> None:
    for name, expected in PRODUCTION.items():
        supplied = getattr(args, f"{name}_db")
        if not supplied.is_absolute() or supplied.is_symlink() or supplied.resolve() != expected.resolve():
            raise PermissionError(f"PHASE9E_EXACT_PRODUCTION_{name.upper()}_PATH_REQUIRED")
        if not supplied.is_file():
            raise FileNotFoundError(supplied)
        with sqlite3.connect(f"file:{supplied.resolve()}?mode=ro", uri=True) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (DATABASE_TYPES[name],)).fetchone():
                raise ValueError(f"PHASE9E_WRONG_{name.upper()}_DATABASE_TYPE")
    if not args.full_universe:
        raise ValueError("PHASE9E_FULL_UNIVERSE_REQUIRED")
    if args.package_fingerprint != PACKAGE_FINGERPRINT:
        raise ValueError("PHASE9E_PACKAGE_FINGERPRINT_MISMATCH")
    supplied_models = {
        "score": args.score_fingerprint, "lifecycle": args.lifecycle_fingerprint,
        "valuation": args.valuation_fingerprint, "delta": args.delta_fingerprint,
        "relative_position": args.relative_fingerprint,
        "diagnostic_flags": args.diagnostic_fingerprint, "snapshot": args.snapshot_fingerprint,
    }
    if supplied_models != EXPECTED_MODELS:
        raise ValueError("PHASE9E_MODEL_PACKAGE_MISMATCH")
    if args.apply and not args.confirm_production:
        raise PermissionError("PHASE9E_PRODUCTION_CONFIRMATION_REQUIRED")
    if args.apply and _git("status", "--porcelain"):
        raise RuntimeError("PHASE9E_CLEAN_GIT_WORKTREE_REQUIRED")


def _process_inventory() -> dict[str, Any]:
    ps = subprocess.run(("ps", "-eo", "pid=,args="), check=True, capture_output=True, text=True).stdout.splitlines()
    relevant = [line.strip() for line in ps if any(term in line.lower() for term in ("rawcandle", "fundamental", "sharadar", "stock_update_scheduler"))]
    holders: dict[str, list[str]] = {}
    for name, path in PRODUCTION.items():
        command = subprocess.run(("lsof", str(path), str(path) + "-wal", str(path) + "-shm"), capture_output=True, text=True)
        holders[name] = command.stdout.splitlines()
    conflicts = [line for line in relevant if str(os.getpid()) not in line and any(term in line for term in ("run_fundamentals_v4", "run_stock_update_scheduler", "run_sharadar"))]
    if conflicts:
        raise RuntimeError("PHASE9E_CONFLICTING_PROCESS:" + " | ".join(conflicts))
    return {"relevant_processes": relevant, "database_holders": holders, "conflicting_writers": conflicts}


def _assert_write_lock_available(path: Path) -> None:
    conn = sqlite3.connect(path, timeout=0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("PHASE9E_CONFLICTING_SQLITE_WRITER") from exc
    finally:
        conn.close()


def _disk_gate(backup_dir: Path, artifact_dir: Path) -> dict[str, Any]:
    analysis_size = PRODUCTION["analysis"].stat().st_size
    permanent = 476 * 1024 * 1024
    peak_wal = 600 * 1024 * 1024
    temporary = 256 * 1024 * 1024
    required = int((analysis_size + permanent + peak_wal + temporary) * 1.25)
    checks = []
    for location in (PRODUCTION["analysis"].parent, backup_dir.parent, artifact_dir.parent):
        free = shutil.disk_usage(location).free
        checks.append({"filesystem_location": str(location.resolve()), "free_bytes": free, "required_bytes": required, "ok": free >= required})
    if not all(item["ok"] for item in checks):
        raise RuntimeError("PHASE9E_INSUFFICIENT_FREE_SPACE")
    return {"analysis_size": analysis_size, "assumptions": {"permanent_growth": permanent, "peak_wal": peak_wal, "temporary": temporary, "contingency": 0.25}, "required_bytes": required, "checks": checks}


def _backup(source: Path, backup_dir: Path, stamp: str) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"fundamentals_analysis.phase9e.{stamp}.db"
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    with sqlite3.connect(f"file:{destination.resolve()}?mode=ro", uri=True) as conn:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        foreign = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
        objects = [row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
        critical_tables = (
            "score_result", "lifecycle_revised_result", "valuation_revised_result",
            "diagnostic_flag_package", "diagnostic_flag_endpoint",
            "diagnostic_flag_evaluation", "operating_income_v2_package_manifest",
            "fundamentals_active_model_family",
        )
        counts = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in critical_tables if table in objects
        }
    if quick != "ok" or foreign:
        raise RuntimeError("PHASE9E_BACKUP_VERIFICATION_FAILED")
    return {"source_path": str(source), "backup_path": str(destination), "source_size": source.stat().st_size, "backup_size": destination.stat().st_size, "sha256": _sha256(destination), "quick_check": quick, "foreign_key_check": foreign, "key_schema_objects": objects, "key_row_counts": counts, "independently_openable": True}


def _v1_state(conn: sqlite3.Connection) -> dict[str, Any]:
    queries = {
        "score": ("SELECT COUNT(*) FROM score_result WHERE model_fingerprint=?", SCORE_V1),
        "lifecycle": ("SELECT COUNT(*) FROM lifecycle_revised_result WHERE model_fingerprint=?", LIFECYCLE_V1),
        "valuation": ("SELECT COUNT(*) FROM valuation_revised_result WHERE model_fingerprint=?", VALUATION_V1),
        "delta": ("SELECT COUNT(*) FROM fundamental_delta_package WHERE model_fingerprint=?", DELTA_V1),
        "diagnostic": ("SELECT COUNT(*) FROM diagnostic_flag_package WHERE model_fingerprint=?", DIAGNOSTIC_V1),
        "relative": ("SELECT COUNT(*) FROM relative_position_snapshot WHERE model_fingerprint=?", RELATIVE_V1),
    }
    counts = {name: conn.execute(sql, (fp,)).fetchone()[0] for name, (sql, fp) in queries.items()}
    digest = hashlib.sha256()
    def columns(table: str, excluded: frozenset[str] = frozenset()) -> str:
        names = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})") if str(row[1]) not in excluded]
        return ",".join(f'"{name}"' for name in names)

    lifecycle_columns = columns("lifecycle_revised_result", frozenset({"operating_margin_ttm", "operating_margin_direction"}))
    valuation_columns = columns("valuation_revised_result", frozenset({"ttm_operating_income", "operating_income_yield", "operating_income_points"}))
    content_queries = (
        ("score", "SELECT r.*,c.* FROM score_result r LEFT JOIN score_component c USING(score_result_id) WHERE r.model_fingerprint=? ORDER BY r.company_id,r.quarter_id,c.component_name", SCORE_V1),
        ("lifecycle", f"SELECT {lifecycle_columns} FROM lifecycle_revised_result WHERE model_fingerprint=? ORDER BY company_id,fiscal_sequence", LIFECYCLE_V1),
        ("valuation", f"SELECT {valuation_columns} FROM valuation_revised_result WHERE model_fingerprint=? ORDER BY company_id,fiscal_sequence", VALUATION_V1),
        ("delta", "SELECT r.*,c.* FROM fundamental_delta_result r JOIN fundamental_delta_package p USING(package_id) LEFT JOIN fundamental_delta_component c USING(endpoint_id) WHERE p.model_fingerprint=? ORDER BY r.company_id,r.fiscal_sequence,c.component_id", DELTA_V1),
        ("diagnostic", "SELECT e.*,v.* FROM diagnostic_flag_endpoint e JOIN diagnostic_flag_package p USING(package_id) LEFT JOIN diagnostic_flag_evaluation v USING(endpoint_id) WHERE p.model_fingerprint=? ORDER BY e.company_id,e.fiscal_sequence,v.flag_id", DIAGNOSTIC_V1),
        ("relative", "SELECT r.* FROM relative_position_result r JOIN relative_position_snapshot s USING(snapshot_id) WHERE s.model_fingerprint=? ORDER BY r.measure,r.peer_scope,r.peer_group_id,r.company_id", RELATIVE_V1),
    )
    for name, sql, fingerprint in content_queries:
        digest.update(name.encode("ascii"))
        for row in conn.execute(sql, (fingerprint,)):
            digest.update(json.dumps(tuple(row), separators=(",", ":"), default=str).encode("utf-8"))
            digest.update(b"\n")
    return {"fingerprints": {"score": SCORE_V1, "lifecycle": LIFECYCLE_V1, "valuation": VALUATION_V1, "delta": DELTA_V1, "diagnostic": DIAGNOSTIC_V1, "relative": RELATIVE_V1}, "counts": counts, "content_fingerprint": digest.hexdigest()}


def _report_inventory() -> dict[str, str]:
    directory = ROOT / "fundamental_reports"
    if not directory.exists():
        return {}
    return {path.name: _sha256(path) for path in sorted(directory.glob("*.md")) if path.is_file() and not path.is_symlink()}


def _reference_rows(calculated: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    values = {row["ticker"]: row for row in calculated["valuation_current"]}
    for row in calculated["score_current"]:
        if row["ticker"] not in EXPECTED_REFERENCE:
            continue
        expected_score, expected_value = EXPECTED_REFERENCE[row["ticker"]]
        value = values[row["ticker"]]
        ok = abs(row["v2_score"] - expected_score) <= .02 and abs(value["v2_score"] - expected_value) <= .02
        output.append({"ticker": row["ticker"], "score_v2": row["v2_score"], "valuation_v2": value["v2_score"], "expected_score": expected_score, "expected_valuation": expected_value, "ok": ok})
    if len(output) != len(EXPECTED_REFERENCE) or not all(row["ok"] for row in output):
        raise RuntimeError("PHASE9E_REFERENCE_COMPANY_MISMATCH")
    return sorted(output, key=lambda row: row["ticker"])


def run(args: argparse.Namespace) -> dict[str, Any]:
    validate_request(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or ROOT / "temp/fundamentals_v4_operating_income_v2_phase9e" / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands = [" ".join(subprocess.list2cmdline([part]) for part in __import__("sys").argv)]
    process = _process_inventory()
    disk = _disk_gate(args.backup_dir, output)
    before = production_integrity()
    reports_before = _report_inventory()
    preflight = {"git_head": _git("rev-parse", "HEAD"), "branch": _git("branch", "--show-current"), "git_status": _git("status", "--porcelain"), "paths": {name: str(path.resolve()) for name, path in PRODUCTION.items()}, "full_universe": True, "apply": args.apply, "locked_package_fingerprint": PACKAGE_FINGERPRINT, "locked_models": EXPECTED_MODELS}
    _json(output / "preflight.json", preflight)
    _json(output / "disk_space_gate.json", disk)
    _json(output / "process_and_wal_inventory.json", process)
    _json(output / "database_inventory_before.json", before)

    calculated = calculate(PRODUCTION)
    references = _reference_rows(calculated)
    dry_run = {"writes": False, "economic_result_fingerprint": __import__("rawcandle.fundamentals.operating_income_v2.persistence", fromlist=["economic_fingerprint"]).economic_fingerprint(calculated), "source_result_fingerprints": calculated["fingerprints"], "expected_rows": {"score": len(calculated["score_v2"]), "score_component": sum(len(row["components"]) for row in calculated["score_v2"]), "lifecycle": len(calculated["lifecycle_v2"]), "valuation": len(calculated["valuation_v2"]), "delta": len(calculated["delta_results"]), "delta_component": len(calculated["delta_results"]) * 7, "diagnostic_endpoint": len(calculated["diagnostics_full"]) // 7, "diagnostic_evaluation": len(calculated["diagnostics_full"]), "relative_result": len(calculated["relative"].results), "relative_coverage": len(calculated["relative"].coverage)}, "reference_companies": references}
    _json(output / "production_dry_run.json", dry_run)
    _csv(output / "reference_company_checks.csv", references)
    if not args.apply:
        _json(output / "backup_manifest.json", {"status": "NOT_CREATED_DRY_RUN"})
        return {"mode": "DRY_RUN", "output": str(output), **dry_run}

    _assert_write_lock_available(PRODUCTION["analysis"])
    lock_handle = LOCK_PATH.open("w")
    activated = False
    previous_activation: tuple[Any, ...] | None = None
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_handle.close()
        raise RuntimeError("PHASE9E_MAINTENANCE_LOCK_HELD") from exc
    try:
        backup = _backup(PRODUCTION["analysis"], args.backup_dir.resolve(), stamp)
        _json(output / "backup_manifest.json", backup)
        with sqlite3.connect(PRODUCTION["analysis"]) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            previous_activation_row = conn.execute(
                "SELECT * FROM fundamentals_active_model_family WHERE singleton=1"
            ).fetchone()
            previous_activation = (
                tuple(previous_activation_row) if previous_activation_row else None
            )
            v1_before = _v1_state(conn)
            first = apply_package(conn, calculated, applied_at=stamp)
            deep = deep_reconcile(conn, calculated)
            second_size = PRODUCTION["analysis"].stat().st_size
            second = apply_package(conn, calculated, applied_at=stamp)
            if not deep["ok"] or second.outcome != "NO_CHANGE" or second.logical_changes:
                raise RuntimeError("PHASE9E_RECONCILIATION_OR_NOOP_FAILED")
            if PRODUCTION["analysis"].stat().st_size != second_size:
                raise RuntimeError("PHASE9E_SECOND_APPLY_DATABASE_GROWTH")
            if _v1_state(conn) != v1_before:
                raise RuntimeError("PHASE9E_V1_STATE_CHANGED")
            conn.execute("BEGIN IMMEDIATE")
            active = activate_v2(conn, activated_at=stamp)
            conn.commit()
            activated = True
            default = ActiveModelRepository(conn)
            explicit = ParallelModelRepository(conn)
            company_id = conn.execute("SELECT company_id FROM lifecycle_revised_result WHERE model_fingerprint=? AND ticker='NVDA' LIMIT 1", (lifecycle.MODEL_FINGERPRINT,)).fetchone()[0]
            reader_smoke = {"default_score": default.score_current(company_id)["model_fingerprint"], "explicit_v2_score": explicit.score_current(company_id, model_fingerprint=score.MODEL_FINGERPRINT)["model_fingerprint"], "explicit_v1_score": explicit.score_current(company_id, model_fingerprint=SCORE_V1)["model_fingerprint"]}
        _json(output / "first_apply.json", first.__dict__)
        _json(output / "deep_reconciliation.json", deep)
        _json(output / "second_apply.json", second.__dict__)
        _json(output / "activation_manifest.json", {**active.__dict__, "models": MODEL_MAP, "reader_smoke": reader_smoke})

        report_paths = SnapshotPaths(PRODUCTION["canonical"], PRODUCTION["analysis"], PRODUCTION["market"], PRODUCTION["taxonomy"], PRODUCTION["provider"])
        report_dir = output / "company_snapshots_v2"
        case_tickers = ["AMZN", "NVDA", "CRMD", "APD", "AAT"]
        not_ready = next((row["ticker"] for row in calculated["score_current"] if row["v2_status"] != "SCORE_FULL"), None)
        candidate = next((row["ticker"] for row in calculated["lifecycle_current"] if calculated["lifecycle_v2"][(row["company_id"], row["quarter_id"])].candidate_state is not None), None)
        case_tickers.extend(value for value in (not_ready, candidate) if value)
        case_tickers = list(dict.fromkeys(case_tickers))
        snapshots = []
        for ticker in case_tickers:
            first_report = generate_active_company_snapshot(report_paths, ticker=ticker, report_date=datetime.now(timezone.utc).date().isoformat(), output_dir=report_dir)
            second_report = generate_active_company_snapshot(report_paths, ticker=ticker, report_date=datetime.now(timezone.utc).date().isoformat(), output_dir=report_dir)
            if second_report["status"] != "NO_CHANGE":
                raise RuntimeError("PHASE9E_SNAPSHOT_NOT_DETERMINISTIC")
            snapshots.append({"ticker": ticker, "first": first_report["status"], "second": second_report["status"], "sha256": _sha256(Path(first_report["output_path"]))})

        ui_dir = output / "ui_smoke"
        service = FundamentalsSnapshotUIService(paths=report_paths, output_dir=ui_dir)
        batch = service.generate_batch(ticker_input="NVDA, ZZZZZPHASE9E", report_date_input=datetime.now(timezone.utc).date().isoformat())
        generated = next(item for item in batch.results if item.ticker == "NVDA")
        download = resolve_report_download(generated.filename, ui_dir)
        ui_smoke = {"batch_status": batch.status, "created": batch.summary.created, "not_generated": batch.summary.not_generated, "download_sha256": _sha256(download), "traversal_rejected": False, "snapshots": snapshots}
        try:
            resolve_report_download("../fundamentals_analysis.db", ui_dir)
        except (ValueError, FileNotFoundError):
            ui_smoke["traversal_rejected"] = True
        if not ui_smoke["traversal_rejected"] or batch.summary.created != 1 or batch.summary.not_generated != 1:
            raise RuntimeError("PHASE9E_UI_SERVICE_SMOKE_FAILED")
        _json(output / "ui_smoke.json", ui_smoke)

        pipeline_smoke = refresh_active_package(PRODUCTION)
        if pipeline_smoke["outcome"] != "NO_CHANGE" or pipeline_smoke["logical_changes"]:
            raise RuntimeError("PHASE9E_PIPELINE_SMOKE_NOT_NO_CHANGE")
        _json(output / "pipeline_smoke.json", pipeline_smoke)
        after = production_integrity()
        _json(output / "database_inventory_after.json", after)
        source_comparison = compare_production_integrity(
            {name: value for name, value in before.items() if name != "analysis"},
            {name: value for name, value in after.items() if name != "analysis"},
        )
        source_changes = source_comparison["differences"]
        if source_changes:
            raise RuntimeError("PHASE9E_SOURCE_DATABASE_CHANGED")
        if _report_inventory() != reports_before:
            raise RuntimeError("PHASE9E_EXISTING_PRODUCTION_REPORT_CHANGED")
        with sqlite3.connect(f"file:{PRODUCTION['analysis'].resolve()}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            assert_v2_active(conn)
            counts = row_counts(conn)
            v1 = _v1_state(conn)
            distributions = {
                "score_status": dict(Counter(row["v2_status"] for row in calculated["score_current"])),
                "lifecycle_v2": dict(Counter(row["v2_final"] or "UNCLASSIFIED" for row in calculated["lifecycle_current"])),
                "valuation_status": dict(Counter(row["v2_status"] for row in calculated["valuation_current"])),
            }
        _csv(output / "v1_v2_production_counts.csv", [{"family": "V1", **v1["counts"]}, {"family": "V2", **counts}])
        _csv(output / "v1_v2_current_comparison.csv", sorted(calculated["score_current"], key=lambda row: (row["ticker"], row["company_id"])))
        rollback = {"activation_only": f"sqlite3 {PRODUCTION['analysis']} \"DELETE FROM fundamentals_active_model_family WHERE singleton=1;\"", "database_restore": f"Stop writers, retain the failed database, then restore with sqlite3.Connection.backup() from {backup['backup_path']}", "v2_rows_deleted": False}
        _json(output / "rollback_plan.json", rollback)
        _json(output / "post_deployment_summary.json", {"counts": counts, "distributions": distributions, "source_database_changes": source_changes, "allowed_source_read_lock_metadata_changes": source_comparison["allowed_read_lock_metadata_changes"], "existing_reports_regenerated": False, "existing_report_count": len(reports_before)})
        report = f"# Phase 9E Production Deployment\n\nOperating-Income V2 was deployed and activated at `{stamp}` from code commit `{preflight['git_head']}`. The first apply was `{first.outcome}`; the mandatory second apply and provider-disabled pipeline smoke were both `NO_CHANGE`. Deep reconciliation passed with zero differences. V1 remains stored and explicitly readable, frozen at this deployment boundary. Only `{PRODUCTION['analysis']}` was modified. Backup: `{backup['backup_path']}` (`{backup['sha256']}`). Existing production Markdown reports were not regenerated.\n"
        (output / "PHASE9E_PRODUCTION_DEPLOYMENT_REPORT.md").write_text(report, encoding="utf-8")
        (output / "commands_run.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
        for path in output.glob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
        for path in output.glob("*.csv"):
            with path.open(newline="", encoding="utf-8") as handle:
                list(csv.reader(handle))
        return {"mode": "APPLIED_AND_ACTIVATED", "output": str(output), "first_apply": first.outcome, "second_apply": second.outcome, "pipeline_smoke": pipeline_smoke["outcome"], "counts": counts, "backup": backup["backup_path"]}
    except Exception:
        if activated:
            with sqlite3.connect(PRODUCTION["analysis"]) as conn:
                conn.execute("BEGIN IMMEDIATE")
                if previous_activation is None:
                    deactivate_v2(conn)
                else:
                    conn.execute(
                        "INSERT OR REPLACE INTO fundamentals_active_model_family "
                        "VALUES(?,?,?,?,?,?)",
                        previous_activation,
                    )
                    assert_v2_active(conn)
                conn.commit()
        raise
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy and atomically activate the complete Operating-Income V2 package")
    for name, path in PRODUCTION.items():
        parser.add_argument(f"--{name}-db", type=Path, default=path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--package-fingerprint", required=True)
    parser.add_argument("--score-fingerprint", required=True)
    parser.add_argument("--lifecycle-fingerprint", required=True)
    parser.add_argument("--valuation-fingerprint", required=True)
    parser.add_argument("--delta-fingerprint", required=True)
    parser.add_argument("--relative-fingerprint", required=True)
    parser.add_argument("--diagnostic-fingerprint", required=True)
    parser.add_argument("--snapshot-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(run(args), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
