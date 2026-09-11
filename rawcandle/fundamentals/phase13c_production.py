from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.operating_income_v2.pipeline import refresh_active_package
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    REPORT_ROOT,
    ROOT,
    compare_production_inventory,
    database_inventory,
    process_inventory,
    production_inventory,
    sha256,
    stable_hash,
    write_csv,
    write_json,
)
from rawcandle.fundamentals.phase12e import _snapshot_smoke
from rawcandle.fundamentals.phase13b_foundation import (
    CONTRACT_VERSION,
    DEPENDENCY_CONTRACT_VERSION,
    CandidatePaths,
    candidate_relative_valuation_dependency_state,
    current_universe_rows,
    database_fingerprint,
    online_backup,
    run_candidate_apply,
    taxonomy_identity,
    universe_identity,
    verify_reconciliation,
)


ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13c_production"
BACKUP_ROOT = ROOT / "backups"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"
PHASE13B_ROOT = ROOT / "temp/fundamentals_v4_phase13b_foundation/20260911T_PHASE13B_RUN1"
EXPECTED_UNIVERSE_FINGERPRINT = "d21fff93d3f01a4056c0f6ed765f2e5f6169aafdb5f1e708b026d6c5ec7d4bdb"
EXPECTED_UNIVERSE_VERSION = "7f50deaa1eb83a536ae7152a759b185a"
EXPECTED_ACTIVE_PACKAGE = "f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40"
EXPECTED_ACTIVE_RV = "7edd6226bd9cc0346f24c1f92d3d4c1dabb67df18e9d4f3210550530daf68324"
EXPECTED_RV_MODEL = "76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e"

CANONICAL_ECONOMIC_TABLES = (
    "company",
    "security",
    "ticker_alias",
    "v4_quarter",
    "v4_quarter_financials",
    "v4_ttm_values",
    "v4_ttm_input_quarter",
)
ANALYSIS_ECONOMIC_TABLES = (
    "fundamentals_active_model_family",
    "operating_income_v2_package_manifest",
    "score_result",
    "score_component",
    "lifecycle_revised_result",
    "valuation_revised_result",
    "fundamental_delta_result",
    "fundamental_delta_component",
    "diagnostic_flag_endpoint",
    "diagnostic_flag_evaluation",
    "operating_income_v2_diagnostic_evidence_field",
    "relative_position_snapshot",
    "relative_position_active_snapshot",
    "relative_position_result",
    "relative_position_coverage",
    "relative_valuation_snapshot",
    "relative_valuation_active_snapshot",
    "relative_valuation_company_result",
    "relative_valuation_peer_position",
    "relative_valuation_own_history",
    "relative_valuation_component_history",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _table_hash(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    columns = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]
    if not columns:
        raise RuntimeError(f"PHASE13C_TABLE_MISSING:{table}")
    quoted = ",".join(f'"{column}"' for column in columns)
    order = ",".join(f'"{column}"' for column in columns)
    digest = hashlib.sha256()
    count = 0
    for row in conn.execute(f'SELECT {quoted} FROM "{table}" ORDER BY {order}'):
        digest.update(json.dumps(tuple(row), separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")
        count += 1
    return {"row_count": count, "sha256": digest.hexdigest()}


def economic_fingerprint() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for role, tables in (("canonical", CANONICAL_ECONOMIC_TABLES), ("analysis", ANALYSIS_ECONOMIC_TABLES)):
        with sqlite3.connect(f"file:{PRODUCTION[role].resolve()}?mode=ro", uri=True) as conn:
            result[role] = {table: _table_hash(conn, table) for table in tables}
    result["reports_fingerprint"] = stable_hash({
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(REPORT_ROOT.rglob("*"))
        if path.is_file()
    })
    return result


def exact_production_paths() -> dict[str, str]:
    resolved = {name: str(path.resolve()) for name, path in PRODUCTION.items()}
    if len(set(resolved.values())) != len(resolved):
        raise PermissionError("PHASE13C_PRODUCTION_PATHS_MUST_BE_DISTINCT")
    for name, path in PRODUCTION.items():
        if path.is_symlink() or not path.is_file():
            raise PermissionError(f"PHASE13C_INVALID_PRODUCTION_PATH:{name}:{path}")
    return resolved


def validate_phase13b_evidence() -> dict[str, Any]:
    decision = json.loads((PHASE13B_ROOT / "decision.json").read_text(encoding="utf-8"))
    replay = json.loads((PHASE13B_ROOT / "corrected_idempotency_replay.json").read_text(encoding="utf-8"))
    first = json.loads((PHASE13B_ROOT / "migration_first_apply.json").read_text(encoding="utf-8"))
    failures = json.loads((PHASE13B_ROOT / "failure_injection_results.json").read_text(encoding="utf-8"))
    identity = first["universe"]["identity"]
    ok = (
        decision["outcome"] == "OUTCOME A — UNIVERSE AND TAXONOMY DEPENDENCY FOUNDATION READY FOR PRODUCTION MIGRATION"
        and replay["logical_no_change"]
        and replay["physical_no_change"]
        and identity["economic_result_fingerprint"] == EXPECTED_UNIVERSE_FINGERPRINT
        and identity["member_count"] == 2458
        and identity["active_security_count"] == 2453
        and identity["zero_active_company_count"] == 16
        and identity["multi_active_company_count"] == 11
        and all(row["restored_copy_quick_check_ok"] for row in failures)
    )
    if not ok:
        raise RuntimeError("PHASE13C_PHASE13B_EVIDENCE_GATE_FAILED")
    return {"decision": decision, "corrected_replay": replay, "first_identity": identity, "failure_boundaries": failures}


def validate_preflight_state(paths: CandidatePaths) -> dict[str, Any]:
    members, aliases = current_universe_rows(paths.canonical_db, now="PHASE13C_PREFLIGHT")
    identity = universe_identity(members, aliases, as_of_date="PHASE13C_P")
    taxonomy = taxonomy_identity(paths.taxonomy_db)
    reconciliation = verify_reconciliation(paths, identity)
    if identity["economic_result_fingerprint"] != EXPECTED_UNIVERSE_FINGERPRINT:
        raise RuntimeError(f"PHASE13C_UNIVERSE_DRIFT:{identity['economic_result_fingerprint']}")
    if identity["member_count"] != 2458 or identity["active_security_count"] != 2453 or identity["zero_active_company_count"] != 16 or identity["multi_active_company_count"] != 11:
        raise RuntimeError("PHASE13C_UNIVERSE_COUNT_GATE_FAILED")
    if not reconciliation["ok"]:
        raise RuntimeError("PHASE13C_BASELINE_RECONCILIATION_FAILED")
    with sqlite3.connect(f"file:{paths.analysis_db.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        active_package = conn.execute("SELECT persistence_fingerprint FROM fundamentals_active_model_family WHERE singleton=1").fetchone()[0]
        active_rv = conn.execute(
            "SELECT snapshot_id FROM relative_valuation_active_snapshot WHERE model_fingerprint=?",
            (EXPECTED_RV_MODEL,),
        ).fetchone()[0]
    if str(active_package) != EXPECTED_ACTIVE_PACKAGE or str(active_rv) != EXPECTED_ACTIVE_RV:
        raise RuntimeError("PHASE13C_ACTIVE_POINTER_DRIFT")
    return {"universe": identity, "taxonomy": taxonomy, "reconciliation": reconciliation}


def disk_gate(output: Path) -> dict[str, Any]:
    production_bytes = sum(path.stat().st_size for path in PRODUCTION.values())
    backup_bytes = production_bytes
    restore_bytes = production_bytes
    growth = 256 * 1024 * 1024
    journal = max(PRODUCTION["canonical"].stat().st_size + PRODUCTION["analysis"].stat().st_size, 512 * 1024 * 1024)
    artifacts = 512 * 1024 * 1024
    required = int((backup_bytes + restore_bytes + growth + journal + artifacts) * 1.20)
    checks = []
    for location in {ROOT, BACKUP_ROOT, output.parent}:
        free = shutil.disk_usage(location).free
        checks.append({"path": str(location.resolve()), "free_bytes": free, "required_bytes": required, "ok": free >= required})
    if not all(row["ok"] for row in checks):
        raise RuntimeError("PHASE13C_DISK_GATE_FAILED")
    return {"production_bytes": production_bytes, "backup_bytes": backup_bytes, "restore_bytes": restore_bytes, "estimated_growth_bytes": growth, "estimated_journal_bytes": journal, "artifact_bytes": artifacts, "required_bytes": required, "checks": checks}


def take_backups(output: Path, stamp: str) -> dict[str, Any]:
    backup_dir = BACKUP_ROOT / f"fundamentals_v4_phase13c_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifests = {}
    for name, path in PRODUCTION.items():
        destination = backup_dir / f"{path.stem}.before_phase13c.db"
        manifest = online_backup(path, destination)
        manifest["sha256"] = sha256(destination)
        manifest["inventory"] = database_inventory(destination)
        manifests[name] = manifest
    write_json(output / "backup_manifest.json", manifests)
    return manifests


def restore_rehearsal(output: Path, backups: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    result = {}
    restore_dir = output / "restore_rehearsal"
    for name, manifest in backups.items():
        source = Path(str(manifest["destination"]))
        restored = restore_dir / f"{name}.restored.db"
        copy = online_backup(source, restored)
        restored_inventory = database_inventory(restored)
        source_inventory = database_inventory(source)
        equal = (
            restored_inventory["sha256"] == source_inventory["sha256"]
            and restored_inventory["schema_fingerprint"] == source_inventory["schema_fingerprint"]
            and restored_inventory["row_counts"] == source_inventory["row_counts"]
            and restored_inventory["quick_check"] == "ok"
            and restored_inventory["foreign_key_errors"] == 0
        )
        if not equal:
            raise RuntimeError(f"PHASE13C_RESTORE_REHEARSAL_FAILED:{name}")
        result[name] = {"backup": copy, "logical_equal": True, "source_sha256": source_inventory["sha256"]}
    write_json(output / "rollback_rehearsal.json", result)
    return result


def restore_modified_databases(backups: Mapping[str, Mapping[str, Any]], output: Path) -> dict[str, Any]:
    restored = {}
    for name in ("canonical", "analysis"):
        source = Path(str(backups[name]["destination"]))
        prepared = output / f"restore_{name}.phase13c.db"
        shutil.copy2(source, prepared)
        with sqlite3.connect(PRODUCTION[name]) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        os.replace(prepared, PRODUCTION[name])
        restored[name] = database_inventory(PRODUCTION[name])
    write_json(output / "failure_full_restore.json", restored)
    return restored


class SidecarMonitor:
    def __init__(self) -> None:
        self.maximum = {f"{name}{suffix}": 0 for name in ("canonical", "analysis") for suffix in ("-wal", "-journal")}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            for name in ("canonical", "analysis"):
                for suffix in ("-wal", "-journal"):
                    path = Path(str(PRODUCTION[name]) + suffix)
                    if path.exists():
                        self.maximum[f"{name}{suffix}"] = max(self.maximum[f"{name}{suffix}"], path.stat().st_size)
            self._stop.wait(0.01)

    def __enter__(self) -> "SidecarMonitor":
        self._thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._stop.set()
        self._thread.join()


def write_reconciliation_artifacts(output: Path, paths: CandidatePaths, first: Mapping[str, Any]) -> None:
    members, _aliases = current_universe_rows(paths.canonical_db, now="PHASE13C")
    write_csv(output / "operational_universe_reconciliation.csv", members)
    with sqlite3.connect(f"file:{paths.analysis_db.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        write_csv(output / "dependency_reconciliation.csv", [dict(row) for row in conn.execute("SELECT * FROM fundamentals_result_dependency ORDER BY consumer_family,consumer_object_type,consumer_object_id")])
        write_csv(output / "relative_valuation_dependency_reconciliation.csv", [dict(row) for row in conn.execute("SELECT * FROM relative_valuation_snapshot_dependency ORDER BY snapshot_id")])
    write_json(output / "taxonomy_dependency_reconciliation.json", first["dependencies"]["taxonomy"])


def compatibility_checks(paths: CandidatePaths, universe: Mapping[str, Any], taxonomy: Mapping[str, Any]) -> dict[str, Any]:
    compatible = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date="2026-09-12",
        expected_universe_fingerprint=universe["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    universe_mismatch = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date="2026-09-12",
        expected_universe_fingerprint="wrong",
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    taxonomy_mismatch = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date="2026-09-12",
        expected_universe_fingerprint=universe["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint="wrong",
    )
    future_guard = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date="2026-09-09",
        expected_universe_fingerprint=universe["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    checks = {
        "compatible": compatible,
        "operational_universe_mismatch": universe_mismatch,
        "economic_taxonomy_mismatch": taxonomy_mismatch,
        "non_future_selection_guard": future_guard,
    }
    if compatible["state"] != "COMPATIBLE" or universe_mismatch["state"] != "OPERATIONAL_UNIVERSE_MISMATCH" or taxonomy_mismatch["state"] != "ECONOMIC_TAXONOMY_MISMATCH":
        raise RuntimeError("PHASE13C_COMPATIBILITY_CHECK_FAILED")
    return checks


def run(output: Path, *, apply: bool, confirm_production: bool) -> dict[str, Any]:
    output = output.resolve()
    if ARTIFACT_ROOT.resolve() not in output.parents or output.exists():
        raise PermissionError("PHASE13C_NEW_ARTIFACT_PATH_REQUIRED")
    if apply and not confirm_production:
        raise PermissionError("PHASE13C_PRODUCTION_CONFIRMATION_REQUIRED")
    if _git("status", "--porcelain"):
        raise RuntimeError("PHASE13C_CLEAN_WORKTREE_REQUIRED")
    output.mkdir(parents=True)
    started = time.perf_counter()
    paths = CandidatePaths(PRODUCTION["canonical"], PRODUCTION["analysis"], PRODUCTION["taxonomy"], PRODUCTION["provider"], PRODUCTION["market"])
    git = {"head": _git("rev-parse", "HEAD"), "branch": _git("branch", "--show-current"), "status": _git("status", "--short"), "upstream": _git("status", "-sb")}
    phase13b = validate_phase13b_evidence()
    production_paths = exact_production_paths()
    processes = process_inventory()
    if processes["conflicting_writers"]:
        raise RuntimeError("PHASE13C_CONFLICTING_WRITER")
    disk = disk_gate(output)
    preflight = production_inventory()
    preflight_state = validate_preflight_state(paths)
    economic_before = economic_fingerprint()
    write_json(output / "preflight.json", {"git": git, "production_paths": production_paths, "phase13b": phase13b, "processes": processes, "disk": disk, "production": preflight, "state": preflight_state, "economic_fingerprint": economic_before})
    if not apply:
        return {"outcome": "PHASE 13C BLOCKED — NO PRODUCTION WRITE PERFORMED", "reason": "dry_run", "output": str(output)}

    lock_handle = LOCK_PATH.open("w")
    backups: dict[str, Any] | None = None
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_handle.close()
        raise RuntimeError("PHASE13C_MAINTENANCE_LOCK_HELD") from exc
    try:
        locked_processes = process_inventory()
        write_json(output / "locked_process_inventory.json", locked_processes)
        if locked_processes["conflicting_writers"]:
            raise RuntimeError("PHASE13C_CONFLICTING_WRITER_AFTER_LOCK")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backups = take_backups(output, stamp)
        rollback = restore_rehearsal(output, backups)
        applied_at = utc_now()
        before_apply = {"canonical": database_fingerprint(PRODUCTION["canonical"]), "analysis": database_fingerprint(PRODUCTION["analysis"])}
        with SidecarMonitor() as monitor:
            first = run_candidate_apply(paths, apply=True, applied_at_utc=applied_at, allow_production=True)
            reconciliation = verify_reconciliation(paths, first["universe"]["identity"])
            if not reconciliation["ok"] or first["universe"]["identity"]["economic_result_fingerprint"] != EXPECTED_UNIVERSE_FINGERPRINT:
                raise RuntimeError("PHASE13C_FIRST_APPLY_RECONCILIATION_FAILED")
            compatibility = compatibility_checks(paths, first["universe"]["identity"], first["dependencies"]["taxonomy"])
            after_first = {"canonical": database_fingerprint(PRODUCTION["canonical"]), "analysis": database_fingerprint(PRODUCTION["analysis"])}
            second = run_candidate_apply(paths, apply=True, applied_at_utc=applied_at, allow_production=True)
            after_second = {"canonical": database_fingerprint(PRODUCTION["canonical"]), "analysis": database_fingerprint(PRODUCTION["analysis"])}
            second_no_change = (
                after_first == after_second
                and second["schema"]["outcome"] == "NO_CHANGE"
                and second["universe"]["outcome"] == "NO_CHANGE"
                and second["dependencies"]["outcome"] == "NO_CHANGE"
            )
            if not second_no_change:
                raise RuntimeError("PHASE13C_SECOND_APPLY_NOT_NO_CHANGE")
            pipeline = refresh_active_package(PRODUCTION)
            if pipeline["outcome"] != "NO_CHANGE" or pipeline["logical_changes"]:
                raise RuntimeError("PHASE13C_PIPELINE_NOT_NO_CHANGE")
        journal = {"sampling_interval_seconds": 0.01, "measured_peak_bytes": monitor.maximum, "maximum_any_bytes": max(monitor.maximum.values())}
        smoke = _snapshot_smoke(output, "2026-09-12")
        economic_after = economic_fingerprint()
        if economic_before != economic_after:
            raise RuntimeError("PHASE13C_ECONOMIC_FINGERPRINT_CHANGED")
        postflight = production_inventory()
        production_compare = compare_production_inventory(preflight, postflight)
        for name in ("provider", "market", "taxonomy"):
            if preflight["databases"][name]["sha256"] != postflight["databases"][name]["sha256"]:
                raise RuntimeError(f"PHASE13C_PROTECTED_DATABASE_CHANGED:{name}")
        if preflight["reports_fingerprint"] != postflight["reports_fingerprint"]:
            raise RuntimeError("PHASE13C_PRODUCTION_REPORTS_CHANGED")
        for name in ("canonical", "analysis"):
            if postflight["databases"][name]["quick_check"] != "ok" or postflight["databases"][name]["foreign_key_errors"]:
                raise RuntimeError(f"PHASE13C_POSTFLIGHT_INTEGRITY_FAILED:{name}")
        write_reconciliation_artifacts(output, paths, first)
        result = {
            "outcome": "PHASE 13C COMPLETE — UNIVERSE AND DEPENDENCY FOUNDATION ACTIVE IN PRODUCTION",
            "git": git,
            "production_databases_written": [str(PRODUCTION["canonical"].resolve()), str(PRODUCTION["analysis"].resolve())],
            "backup_manifest": backups,
            "rollback_rehearsal": rollback,
            "first_apply": first,
            "second_apply": second,
            "second_no_change": True,
            "before_apply": before_apply,
            "after_first": after_first,
            "after_second": after_second,
            "reconciliation": reconciliation,
            "compatibility": compatibility,
            "pipeline_smoke": pipeline,
            "snapshot_ui_smoke": smoke,
            "journal": journal,
            "economic_immutability": {"before": economic_before, "after": economic_after, "unchanged": True},
            "production_preflight_postflight": production_compare,
            "production_postflight": postflight,
            "duration_seconds": time.perf_counter() - started,
        }
        write_json(output / "deployment_result.json", result)
        write_json(output / "production_postflight.json", postflight)
        write_json(output / "economic_immutability.json", result["economic_immutability"])
        write_json(output / "first_apply.json", first)
        write_json(output / "second_no_change.json", {"second_apply": second, "passed": True, "after_first": after_first, "after_second": after_second})
        write_json(output / "reader_compatibility.json", compatibility)
        write_json(output / "pipeline_smoke.json", pipeline)
        write_json(output / "snapshot_ui_smoke.json", smoke)
        write_json(output / "journal_peak.json", journal)
        write_json(output / "production_preflight_postflight.json", production_compare)
        (output / "commands_run.txt").write_text(
            "python3 -m rawcandle.cli.run_phase13c_production_migration --output <phase13c-temp-dir> --apply --confirm-production\n",
            encoding="utf-8",
        )
        (output / "PHASE13C_PRODUCTION_MIGRATION_REPORT.md").write_text(build_report(result), encoding="utf-8")
        return result
    except Exception:
        if backups is not None:
            restore_modified_databases(backups, output)
        raise
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def build_report(result: Mapping[str, Any]) -> str:
    universe = result["first_apply"]["universe"]["identity"]
    taxonomy = result["first_apply"]["dependencies"]["taxonomy"]
    return f"""# Phase 13C Production Migration Report

Outcome: **{result['outcome']}**.

Production writes were limited to canonical and analysis Fundamentals databases.
Provider, market, taxonomy and existing production reports remained content-identical.

## Operational Universe

- Members: {universe['member_count']}
- Active securities represented: {universe['active_security_count']}
- Zero-active companies: {universe['zero_active_company_count']}
- Multi-active companies: {universe['multi_active_company_count']}
- Universe version: `{universe['universe_version_id']}`
- Universe fingerprint: `{universe['economic_result_fingerprint']}`

The count relationship remains: 2,458 companies minus 16 zero-active companies
plus 11 additional active share-class securities equals 2,453 active securities.

## Dependencies

- Taxonomy source version: `{taxonomy['taxonomy_source_version']}`
- Taxonomy economic fingerprint: `{taxonomy['taxonomy_economic_fingerprint']}`
- Active Relative Valuation compatibility: `{result['compatibility']['compatible']['state']}`
- Active package compatibility rows were recorded in `fundamentals_result_dependency`.

## Stability

- Second apply no-change: {result['second_no_change']}
- Economic immutability: {result['economic_immutability']['unchanged']}
- Pipeline smoke: {result['pipeline_smoke']['outcome']}
- Snapshot/UI smoke batch: {result['snapshot_ui_smoke']['batch_status']}
- Rollback rehearsal: verified database-level restore from backups.

Phase 13D remains Add Tickers and Taxonomy Update backend/CLI implementation and rehearsal only.
"""

