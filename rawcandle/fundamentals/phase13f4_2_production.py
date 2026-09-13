from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    REPORT_ROOT,
    ROOT,
    SCHEDULER_CONFIG,
    compare_production_inventory,
    database_inventory,
    rebuild_ttm,
    reconcile_canonical,
    sha256,
    stable_hash,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    ensure_candidate_schema,
    online_backup,
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13f3_1_package_recovery import instrumented_package_refresh
from rawcandle.fundamentals.phase13f3_2_successor_recovery import (
    _apply_provider_identity_links,
    archive_reconciliation,
    stage_provider_rows,
    successor_canonical_ttm_report,
)
from rawcandle.fundamentals.phase13f3_3_structural_break_contract import (
    _events,
    _structural_evidence,
    _structural_package_fingerprint,
)
from rawcandle.fundamentals.phase13f3_ticker_transition import (
    APPLIED_AT,
    REPORT_DATE,
    _apply_transition_identities,
    _areb_counts,
    _manual_rv_refresh,
    _snapshot_smoke,
    _valuation_classification_update,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position


PHASE = "PHASE13F4_2_STRUCTURAL_PRODUCTION_FULL_BACKUP_ROLLBACK"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13f4_2_structural_production"
BACKUP_ROOT = ROOT / "backups/fundamentals_v4_phase13f4_2_structural_production"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"
DEFAULT_RUN_ID = "20260913T_PHASE13F4_2_STRUCTURAL_PRODUCTION"
WRITE_ROLES = ("provider", "canonical", "analysis")
READ_ONLY_ROLES = ("market", "taxonomy")

ACCEPTED = {
    "structural_contract": "ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1",
    "structural_package_fingerprint": "4ba542c7e28c2d92ba65863f2932e2683a60b053cb4b2debe344b051a84441ad",
    "event_fingerprint": "5ec6403d231e41a52fdf04609892df1c9bdd841805180a52578b638114bf5bfd",
    "structural_source_fingerprint": "04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f",
    "package_economic_result_fingerprint": "55a9713c9f20d122e493bb3c0c3485bf729724ce1914703ad637d2a16346002d",
    "package_physical_content_fingerprint": "718e3fbe838f273775d77042fa0dbaa706c822277a3e23d5dd7eeaaa4ebb8811",
    "rv_snapshot": "1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b",
    "rv_result_fingerprint": "9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3",
}

OUTCOME_A = "OUTCOME A — STRUCTURAL-REGIME PACKAGE ACTIVE IN PRODUCTION AND VERIFIED STABLE UNDER FULL-BACKUP ROLLBACK POLICY"
OUTCOME_B = "OUTCOME B — PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED"
OUTCOME_C = "OUTCOME C — DEPLOYMENT FAILED AND COMPLETE BACKUP SET RESTORED SUCCESSFULLY"
OUTCOME_D = "OUTCOME D — PRODUCTION STATE UNRESOLVED; MANUAL RECOVERY REQUIRED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_git(args: tuple[str, ...], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=ROOT, check=check, capture_output=True, text=True)


def _git_text(args: tuple[str, ...]) -> str:
    return _run_git(args).stdout.strip()


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _sidecar_state(path: Path, suffix: str) -> dict[str, Any]:
    sidecar = Path(str(path) + suffix)
    return {
        "exists": sidecar.exists(),
        "size": sidecar.stat().st_size if sidecar.exists() else None,
        "mtime_ns": sidecar.stat().st_mtime_ns if sidecar.exists() else None,
        "sha256": sha256(sidecar) if sidecar.exists() else None,
    }


def _light_database_inventory(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with _readonly(path) as conn:
        schema = [tuple(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        )]
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256(path),
        "schema_fingerprint": stable_hash(schema),
        "row_counts": {},
        "page_count": page_count,
        "freelist_count": freelist,
        "journal_mode": journal_mode,
        "quick_check": "SKIPPED_READ_ONLY_SOURCE",
        "foreign_key_errors": "SKIPPED_READ_ONLY_SOURCE",
        "wal": _sidecar_state(path, "-wal"),
        "shm": _sidecar_state(path, "-shm"),
        "journal": _sidecar_state(path, "-journal"),
    }


def _targeted_production_inventory() -> dict[str, Any]:
    databases = {
        role: (database_inventory(path) if role in WRITE_ROLES else _light_database_inventory(path))
        for role, path in PRODUCTION.items()
    }
    reports = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(REPORT_ROOT.glob("**/*")) if path.is_file()
    }
    scheduler = {
        "exists": SCHEDULER_CONFIG.exists(),
        "sha256": sha256(SCHEDULER_CONFIG) if SCHEDULER_CONFIG.exists() else None,
        "size": SCHEDULER_CONFIG.stat().st_size if SCHEDULER_CONFIG.exists() else None,
        "mtime_ns": SCHEDULER_CONFIG.stat().st_mtime_ns if SCHEDULER_CONFIG.exists() else None,
    }
    with _readonly(PRODUCTION["analysis"]) as conn:
        from rawcandle.fundamentals.operating_income_v2.activation import assert_v2_active

        active = asdict(assert_v2_active(conn))
        relative = [dict(row) for row in conn.execute(
            "SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint"
        )]
    return {
        "databases": databases,
        "reports": reports,
        "reports_fingerprint": stable_hash(reports),
        "scheduler": scheduler,
        "active_package": active,
        "active_relative_valuation": relative,
    }


def _assert_paths() -> dict[str, str]:
    resolved: dict[str, str] = {}
    for role, path in PRODUCTION.items():
        if not path.is_absolute() or path.is_symlink() or path.resolve() != path or not path.is_file():
            raise RuntimeError(f"PHASE13F4_2_PRODUCTION_PATH_REFUSED:{role}:{path}")
        resolved[role] = str(path)
        if role in WRITE_ROLES:
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = Path(str(path) + suffix)
                if sidecar.exists() and sidecar.stat().st_size:
                    raise RuntimeError(f"PHASE13F4_2_SQLITE_SIDECAR_PRESENT:{role}:{sidecar}:{sidecar.stat().st_size}")
    if len(set(resolved.values())) != len(resolved):
        raise RuntimeError("PHASE13F4_2_DATABASE_ROLE_ALIAS")
    return resolved


def _process_inventory() -> dict[str, Any]:
    rows = subprocess.run(("ps", "-eo", "pid=,args="), check=True, capture_output=True, text=True).stdout.splitlines()
    relevant = [
        row.strip()
        for row in rows
        if any(term in row.lower() for term in ("rawcandle", "fundamental", "sharadar", "stock_update_scheduler"))
        and str(os.getpid()) not in row
    ]
    conflicts = [
        row for row in relevant
        if any(term in row for term in ("run_fundamentals_v4", "run_phase13", "run_phase12", "run_sharadar", "stock_update_scheduler"))
    ]
    return {"relevant_processes": relevant, "conflicting_writers": conflicts}


def _storage_gate(output: Path, backup_dir: Path) -> dict[str, Any]:
    write_bytes = sum(PRODUCTION[role].stat().st_size for role in WRITE_ROLES)
    required = int(write_bytes * 3.0 + 2 * 1024 * 1024 * 1024)
    locations = {ROOT, output.parent, backup_dir.parent, Path("/tmp")}
    checks = []
    for location in locations:
        existing = location
        while not existing.exists():
            existing = existing.parent
        usage = shutil.disk_usage(existing)
        checks.append({
            "path": str(existing.resolve()),
            "free_bytes": usage.free,
            "required_bytes": required,
            "ok": usage.free >= required,
        })
    if not all(row["ok"] for row in checks):
        raise RuntimeError("PHASE13F4_2_INSUFFICIENT_FREE_SPACE")
    return {"write_set_bytes": write_bytes, "required_bytes": required, "checks": checks}


def _schema_parity() -> dict[str, Any]:
    return {
        "structural_annotation": "phase10b.calculate -> rehearsal.calculate -> _annotate_structural_rows",
        "score": "phase10b.calculate uses operating_income_v2.score",
        "lifecycle": "phase10b.calculate uses operating_income_v2.rehearsal._lifecycle with structural regime checks",
        "valuation": "phase10b.calculate uses structural-aware canonical valuation source",
        "delta": "phase10b.calculate uses _same_structural_regime for compatible history",
        "diagnostics": "phase10b.apply_candidate_package persists diagnostic_flags_eight",
        "relative_position": "refresh_relative_position production entrypoint",
        "relative_valuation": "phase13f3_ticker_transition._manual_rv_refresh",
        "dependencies": "phase13b_foundation.attach_dependencies",
        "activation": "phase10b.apply_candidate_package and relative_valuation.persistence.apply_snapshot",
        "ok": True,
    }


def _preflight(output: Path, backup_dir: Path, *, require_clean: bool) -> dict[str, Any]:
    paths = _assert_paths()
    git_status = _git_text(("status", "--porcelain"))
    if require_clean and git_status:
        raise RuntimeError("PHASE13F4_2_CLEAN_GIT_WORKTREE_REQUIRED")
    required = {}
    for commit in ("0804609", "34be0c6", "a01fc83"):
        required[commit] = _run_git(("cat-file", "-e", f"{commit}^{{commit}}"), check=False).returncode == 0
    if not all(required.values()):
        raise RuntimeError("PHASE13F4_2_REQUIRED_COMMIT_MISSING:" + json.dumps(required, sort_keys=True))
    process = _process_inventory()
    if process["conflicting_writers"]:
        raise RuntimeError("PHASE13F4_2_CONFLICTING_WRITER:" + " | ".join(process["conflicting_writers"]))
    inventory = _targeted_production_inventory()
    bad = {
        role: {"quick_check": row["quick_check"], "foreign_key_errors": row["foreign_key_errors"]}
        for role, row in inventory["databases"].items()
        if role in WRITE_ROLES and (row["quick_check"] != "ok" or row["foreign_key_errors"])
    }
    if bad:
        raise RuntimeError("PHASE13F4_2_INTEGRITY_PRECHECK_FAILED:" + json.dumps(bad, sort_keys=True))
    source = archive_reconciliation()
    accepted_by_dimension = {
        "ARQ": sum(int(row["ARQ_row_count"]) for row in source["reconciliation"]),
        "MRQ": sum(int(row["MRQ_row_count"]) for row in source["reconciliation"]),
    }
    if accepted_by_dimension != {"ARQ": 199, "MRQ": 202}:
        raise RuntimeError(f"PHASE13F4_2_SOURCE_RECONCILIATION_FAILED:{accepted_by_dimension}")
    return {
        "git": {
            "head": _git_text(("rev-parse", "HEAD")),
            "short_head": _git_text(("rev-parse", "--short", "HEAD")),
            "branch": _git_text(("branch", "--show-current")),
            "status_clean": not bool(git_status),
            "required_commits": required,
        },
        "paths": paths,
        "process": process,
        "storage": _storage_gate(output, backup_dir),
        "parity": _schema_parity(),
        "production_inventory": inventory,
        "source_reconciliation": {
            **{key: value for key, value in source.items() if key != "rows_by_ticker"},
            "accepted_by_dimension": accepted_by_dimension,
        },
    }


def _backup_write_set(backup_dir: Path) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for role in WRITE_ROLES:
        source = PRODUCTION[role]
        target = backup_dir / source.name
        copied = online_backup(source, target)
        copied["sha256"] = sha256(target)
        copied["inventory"] = database_inventory(target)
        if copied["inventory"]["quick_check"] != "ok" or copied["inventory"]["foreign_key_errors"]:
            raise RuntimeError(f"PHASE13F4_2_BACKUP_INTEGRITY_FAILED:{role}")
        manifest[role] = copied
    write_json(backup_dir / "backup_manifest.json", manifest)
    return manifest


def _restore_to_path(source: Path, destination: Path) -> None:
    if destination.exists():
        destination.unlink()
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def _restore_rehearsal(backup_manifest: Mapping[str, Mapping[str, Any]], output: Path) -> dict[str, Any]:
    restore_dir = output / "restore_rehearsal"
    restore_dir.mkdir(parents=True, exist_ok=True)
    rows = {}
    for role in WRITE_ROLES:
        source = Path(str(backup_manifest[role]["destination"]))
        target = restore_dir / f"{role}.restored.db"
        _restore_to_path(source, target)
        inventory = database_inventory(target)
        backup_inventory = backup_manifest[role]["inventory"]
        ok = (
            inventory["schema_fingerprint"] == backup_inventory["schema_fingerprint"]
            and inventory["row_counts"] == backup_inventory["row_counts"]
            and inventory["quick_check"] == "ok"
            and inventory["foreign_key_errors"] == 0
        )
        rows[role] = {"path": str(target), "ok": ok, "inventory": inventory}
        if not ok:
            raise RuntimeError(f"PHASE13F4_2_RESTORE_REHEARSAL_FAILED:{role}")
    return {"restore_dir": str(restore_dir), "roles": rows, "ok": True}


def _restore_backups(backup_manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    restored = {}
    for role in WRITE_ROLES:
        source = Path(str(backup_manifest[role]["destination"]))
        _restore_to_path(source, PRODUCTION[role])
        restored[role] = database_inventory(PRODUCTION[role])
        if restored[role]["quick_check"] != "ok" or restored[role]["foreign_key_errors"]:
            raise RuntimeError(f"PHASE13F4_2_RESTORE_INTEGRITY_FAILED:{role}")
    return restored


def _structural_dependency_metadata(structural_contract: Mapping[str, Any], structural_package_fingerprint: str) -> dict[str, Any]:
    return {
        "structural_contract_version": structural_break.CONTRACT_VERSION,
        "structural_package_fingerprint": structural_package_fingerprint,
        "structural_event_fingerprint": structural_contract["economic_event_fingerprint"],
        "structural_source_fingerprint": structural_contract["regime_fingerprint"],
        "structural_event_count": structural_contract["event_count"],
        "structural_quarter_regime_count": structural_contract["quarter_regime_count"],
        "structural_ttm_regime_count": structural_contract["ttm_regime_count"],
    }


def _apply_pipeline(output: Path, *, source: Mapping[str, Any], applied_at: str) -> dict[str, Any]:
    paths = CandidatePaths(
        PRODUCTION["canonical"],
        PRODUCTION["analysis"],
        PRODUCTION["taxonomy"],
        provider_db=PRODUCTION["provider"],
        market_db=PRODUCTION["market"],
    )
    result: dict[str, Any] = {"applied_at_utc": applied_at}
    result["provider_identity_links"] = _apply_provider_identity_links(PRODUCTION["canonical"], allow_production=True)
    result["transition_identities"] = _apply_transition_identities(PRODUCTION["canonical"], allow_production=True)
    result["provider_staging"] = stage_provider_rows(
        PRODUCTION["provider"],
        PRODUCTION["canonical"],
        source["rows_by_ticker"],
        allow_production=True,
    )
    result["provider_staging_replay"] = stage_provider_rows(
        PRODUCTION["provider"],
        PRODUCTION["canonical"],
        source["rows_by_ticker"],
        allow_production=True,
    )
    result["canonical"] = reconcile_canonical(PRODUCTION["provider"], PRODUCTION["canonical"], applied_at=applied_at)
    result["ttm"] = rebuild_ttm(PRODUCTION["canonical"], applied_at=applied_at)
    result["successor_canonical_ttm"] = successor_canonical_ttm_report(PRODUCTION["canonical"])
    result["structural_contract"] = structural_break.apply_contract(
        PRODUCTION["canonical"],
        events=_events(),
        applied_at_utc=applied_at,
    )
    result["structural_evidence"] = _structural_evidence(PRODUCTION["canonical"])
    structural_package_fingerprint = _structural_package_fingerprint(result["structural_contract"])
    result["structural_package_fingerprint"] = structural_package_fingerprint
    result["valuation_classification"] = _valuation_classification_update(
        PRODUCTION["analysis"],
        PRODUCTION["market"],
        PRODUCTION["canonical"],
        allow_production=True,
    )
    result["schema"] = ensure_candidate_schema(paths, applied_at_utc=applied_at, apply=True, allow_production=True)
    universe = backfill_universe(paths, applied_at_utc=applied_at, apply=True, allow_production=True)
    result["universe"] = universe
    result["package"] = instrumented_package_refresh(
        {
            "provider": PRODUCTION["provider"],
            "canonical": PRODUCTION["canonical"],
            "analysis": PRODUCTION["analysis"],
            "market": PRODUCTION["market"],
            "taxonomy": PRODUCTION["taxonomy"],
        },
        output,
        allow_production=True,
    )
    result["relative_position"] = asdict(refresh_relative_position(
        canonical_db=PRODUCTION["canonical"],
        analysis_db=PRODUCTION["analysis"],
        market_db=PRODUCTION["market"],
        taxonomy_db=PRODUCTION["taxonomy"],
        snapshot_date=REPORT_DATE,
        model_fingerprint=RP_MODEL_FINGERPRINT,
        applied_at_utc=applied_at,
    ))
    taxonomy = taxonomy_identity(PRODUCTION["taxonomy"])
    result["pre_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        PRODUCTION["analysis"],
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    result["relative_valuation"] = _manual_rv_refresh(paths, output=output)
    structural_metadata = _structural_dependency_metadata(result["structural_contract"], structural_package_fingerprint)
    result["dependencies"] = attach_dependencies(
        paths,
        universe=universe["identity"],
        applied_at_utc=applied_at,
        apply=True,
        allow_production=True,
        structural_metadata=structural_metadata,
    )
    result["post_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        PRODUCTION["analysis"],
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    result["snapshots"] = _snapshot_smoke(paths, output)
    result["areb"] = _areb_counts(PRODUCTION["analysis"])
    return result


def _acceptance_blockers(result: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if result["provider_staging_replay"]["logical_changes"] != 0:
        blockers.append("PROVIDER_STAGING_REPLAY_NOT_NO_CHANGE")
    if result["structural_contract"]["event_count"] != 5:
        blockers.append("STRUCTURAL_EVENT_COUNT")
    if result["structural_contract"]["quarter_regime_count"] != 197:
        blockers.append("STRUCTURAL_QUARTER_REGIME_COUNT")
    if result["structural_contract"]["ttm_regime_count"] != 197:
        blockers.append("STRUCTURAL_TTM_REGIME_COUNT")
    if result["structural_package_fingerprint"] != ACCEPTED["structural_package_fingerprint"]:
        blockers.append("STRUCTURAL_PACKAGE_FINGERPRINT")
    if result["structural_contract"]["economic_event_fingerprint"] != ACCEPTED["event_fingerprint"]:
        blockers.append("STRUCTURAL_EVENT_FINGERPRINT")
    if result["structural_contract"]["regime_fingerprint"] != ACCEPTED["structural_source_fingerprint"]:
        blockers.append("STRUCTURAL_SOURCE_FINGERPRINT")
    package = result["package"]["first_apply"]
    if package["economic_result_fingerprint"] != ACCEPTED["package_economic_result_fingerprint"]:
        blockers.append("PACKAGE_ECONOMIC_FINGERPRINT")
    if package["physical_content_fingerprint"] != ACCEPTED["package_physical_content_fingerprint"]:
        blockers.append("PACKAGE_PHYSICAL_FINGERPRINT")
    rv = result.get("relative_valuation", {}).get("snapshot", {})
    rv_apply = result.get("relative_valuation", {}).get("first_apply", {})
    rv_snapshot_id = rv_apply.get("snapshot_id")
    if not rv_snapshot_id:
        blockers.append("RV_SNAPSHOT_ID_MISSING")
    elif rv_snapshot_id != ACCEPTED["rv_snapshot"]:
        blockers.append("RV_SNAPSHOT_ID")
    rv_result = rv.get("result_fingerprint")
    if not rv_result:
        blockers.append("RV_RESULT_FINGERPRINT_MISSING")
    elif rv_result != ACCEPTED["rv_result_fingerprint"]:
        blockers.append("RV_RESULT_FINGERPRINT")
    compatibility = result.get("post_refresh_compatibility", {}).get("state")
    if compatibility != "COMPATIBLE":
        blockers.append(f"POST_REFRESH_COMPATIBILITY:{compatibility}")
    if int(result["areb"]["post_delisting_relative_valuation_rows"]) != 0:
        blockers.append("AREB_POST_DELISTING_RV_ROWS")
    return blockers


def _second_no_change(first: Mapping[str, Any], second: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    compare = compare_production_inventory(before, after)
    return {
        "provider_replay_changes": second["provider_staging_replay"]["logical_changes"],
        "package_outcome": second["package"]["first_apply"]["outcome"],
        "package_second_apply_outcome": second["package"]["second_apply"]["outcome"],
        "relative_position_outcome": second["relative_position"]["apply"]["outcome"],
        "relative_valuation_outcome": second["relative_valuation"]["first_apply"]["outcome"],
        "relative_valuation_second_outcome": second["relative_valuation"]["second_apply"]["outcome"],
        "inventory_exact_no_change": before == after,
        "inventory_normalized_no_change": compare["identical"],
        "inventory_compare": compare,
    }


def run_phase13f4_2(
    output: Path | None = None,
    *,
    apply: bool = False,
    phase: str = PHASE,
    artifact_root: Path = ARTIFACT_ROOT,
    backup_root: Path = BACKUP_ROOT,
    default_run_id: str = DEFAULT_RUN_ID,
    result_filename: str = "phase13f4_2_result.json",
) -> dict[str, Any]:
    started = time.monotonic()
    output = (output or artifact_root / default_run_id).resolve()
    backup_dir = backup_root / output.name
    output.mkdir(parents=True, exist_ok=True)
    try:
        preflight = _preflight(output, backup_dir, require_clean=apply)
    except Exception as exc:
        result = {"phase": phase, "outcome": OUTCOME_B, "artifact_dir": str(output), "error": type(exc).__name__, "reason": str(exc)}
        write_json(output / result_filename, result)
        return result
    source = archive_reconciliation()
    write_json(output / "production_preflight.json", preflight)
    if not apply:
        result = {
            "phase": phase,
            "outcome": OUTCOME_B,
            "mode": "DRY_RUN",
            "artifact_dir": str(output),
            "preflight": preflight,
            "write_set": list(WRITE_ROLES),
            "read_only_roles": list(READ_ONLY_ROLES),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / result_filename, result)
        return result

    backup_manifest: dict[str, Any] | None = None
    lock_handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup_manifest = _backup_write_set(backup_dir)
        restore_rehearsal = _restore_rehearsal(backup_manifest, output)
        before_apply = _targeted_production_inventory()
        applied_at = utc_now()
        first = _apply_pipeline(output / "first_apply", source=source, applied_at=applied_at)
        blockers = _acceptance_blockers(first)
        if blockers:
            raise RuntimeError("PHASE13F4_2_ACCEPTANCE_BLOCKERS:" + ",".join(blockers))
        second_before = _targeted_production_inventory()
        second = _apply_pipeline(output / "second_apply", source=source, applied_at=applied_at)
        second_after = _targeted_production_inventory()
        no_change = _second_no_change(first, second, second_before, second_after)
        if not (
            no_change["provider_replay_changes"] == 0
            and no_change["package_outcome"] == "NO_CHANGE"
            and no_change["relative_valuation_outcome"] == "NO_CHANGE"
            and no_change["inventory_normalized_no_change"]
        ):
            raise RuntimeError("PHASE13F4_2_SECOND_RUN_NOT_NO_CHANGE:" + json.dumps(no_change, sort_keys=True, default=str))
        postflight = _targeted_production_inventory()
        final_integrity = {
            role: (database_inventory(path) if role in WRITE_ROLES else _light_database_inventory(path))
            for role, path in PRODUCTION.items()
        }
        result = {
            "phase": phase,
            "outcome": OUTCOME_A,
            "artifact_dir": str(output),
            "backup_dir": str(backup_dir),
            "activation_timestamp": applied_at,
            "preflight": preflight,
            "backup_manifest": backup_manifest,
            "restore_rehearsal": restore_rehearsal,
            "first_apply": first,
            "acceptance_blockers": blockers,
            "second_apply": second,
            "second_no_change": no_change,
            "production_compare": compare_production_inventory(before_apply, postflight),
            "production_postflight": postflight,
            "final_integrity": final_integrity,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / result_filename, result)
        return result
    except Exception as exc:
        restored = None
        restore_error = None
        if backup_manifest is not None:
            try:
                restored = _restore_backups(backup_manifest)
            except Exception as restore_exc:  # pragma: no cover - production recovery path
                restore_error = {"type": type(restore_exc).__name__, "message": str(restore_exc), "traceback": traceback.format_exc()}
        outcome = OUTCOME_C if restored is not None and restore_error is None else (OUTCOME_B if backup_manifest is None else OUTCOME_D)
        result = {
            "phase": phase,
            "outcome": outcome,
            "artifact_dir": str(output),
            "backup_dir": str(backup_dir) if backup_manifest else None,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
            "backup_manifest": backup_manifest,
            "restored": restored,
            "restore_error": restore_error,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / result_filename, result)
        return result
    finally:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        finally:
            lock_handle.close()
