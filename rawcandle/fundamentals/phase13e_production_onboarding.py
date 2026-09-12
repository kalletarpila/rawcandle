from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.operating_income_v2.pipeline import refresh_active_package
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    ROOT,
    compare_production_inventory,
    database_inventory,
    production_inventory,
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
from rawcandle.fundamentals.phase13d1_real_source import (
    ARCHIVE_EXPECTED_SHA256,
    ARCHIVE_PATH,
    SNDK_CIK,
    SNDK_PERMATICKER,
    archive_rows_for_ticker,
    create_sndk_canonical_identity,
    sndk_identity_evidence,
    stage_sndk_archive_rows,
)
from rawcandle.fundamentals.phase13d2_complete import _readiness
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.engine import calculate_relative_valuation
from rawcandle.fundamentals.relative_valuation.persistence import (
    RelativeValuationRepository,
    apply_snapshot,
    quick_check as rv_quick_check,
    validate_snapshot,
)
from rawcandle.fundamentals.relative_valuation.source import ReadOnlySourcePaths, load_relative_valuation_source
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths


PHASE = "PHASE13E_PROTECTED_SNDK_PRODUCTION_ONBOARDING"
REPORT_DATE = "2026-09-12"
DEFAULT_RUN_ID = "20260912T_PHASE13E_SNDK_PRODUCTION_ONBOARDING"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13e_production_onboarding"
BACKUP_ROOT = ROOT / "backups/fundamentals_v4_phase13e_sndk_onboarding"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"
REQUIRED_D13D3_1_SHORT = "5f4ec74"

OUTCOME_A = "OUTCOME A — SNDK PRODUCTION ONBOARDING COMPLETE AND STABLE"
OUTCOME_B = "OUTCOME B — PRE-WRITE BLOCKER; PRODUCTION UNCHANGED"
OUTCOME_C = "OUTCOME C — DEPLOYMENT ATTEMPT FAILED AND FULLY ROLLED BACK"

WRITE_ROLES = ("provider", "canonical", "analysis")
READ_ONLY_ROLES = ("market", "taxonomy")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _run_git(args: tuple[str, ...]) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _assert_exact_production_paths() -> dict[str, str]:
    resolved: dict[str, str] = {}
    for role, path in PRODUCTION.items():
        if path.is_symlink() or not path.is_absolute() or path.resolve() != path or not path.is_file():
            raise RuntimeError(f"PHASE13E_PRODUCTION_PATH_REFUSED:{role}:{path}")
        resolved[role] = str(path)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise RuntimeError(f"PHASE13E_NONEMPTY_SQLITE_SIDECAR:{role}:{sidecar}:{sidecar.stat().st_size}")
    if len(set(resolved.values())) != len(resolved):
        raise RuntimeError("PHASE13E_DATABASE_ROLE_ALIAS")
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
        row
        for row in relevant
        if any(term in row for term in ("run_fundamentals_v4", "run_phase13", "run_phase12", "run_sharadar", "stock_update_scheduler"))
    ]
    return {"relevant_processes": relevant, "conflicting_writers": conflicts}


def _storage_gate(output: Path, backup_dir: Path) -> dict[str, Any]:
    def existing_parent(path: Path) -> Path:
        current = path
        while not current.exists():
            current = current.parent
        return current

    write_bytes = sum(PRODUCTION[role].stat().st_size for role in WRITE_ROLES)
    required = int((write_bytes * 2.25) + (1024 * 1024 * 1024))
    checks = []
    for location in {ROOT, existing_parent(output.parent), existing_parent(backup_dir.parent), Path("/tmp")}:
        usage = shutil.disk_usage(location)
        checks.append({
            "path": str(location.resolve()),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "required_bytes": required,
            "ok": usage.free >= required,
        })
    if not all(row["ok"] for row in checks):
        raise RuntimeError("PHASE13E_INSUFFICIENT_FREE_SPACE")
    return {"write_set_bytes": write_bytes, "required_bytes": required, "checks": checks}


def _verify_source_archive() -> dict[str, Any]:
    if not ARCHIVE_PATH.exists():
        raise RuntimeError("PHASE13E_ARCHIVE_MISSING")
    archive_hash = sha256(ARCHIVE_PATH)
    if archive_hash != ARCHIVE_EXPECTED_SHA256:
        raise RuntimeError("PHASE13E_ARCHIVE_HASH_MISMATCH")
    rows = archive_rows_for_ticker("SNDK")
    if any(str(row.get("ticker") or "").upper() != "SNDK" for row in rows):
        raise RuntimeError("PHASE13E_ARCHIVE_TICKER_CONTAMINATION")
    arq_rows = sum(1 for row in rows if str(row.get("dimension") or "").upper() == "ARQ")
    return {
        "archive_path": str(ARCHIVE_PATH),
        "archive_size": ARCHIVE_PATH.stat().st_size,
        "sha256": archive_hash,
        "expected_sha256": ARCHIVE_EXPECTED_SHA256,
        "source_rows": len(rows),
        "arq_rows": arq_rows,
        "first_reportperiod": min((row.get("reportperiod") for row in rows if row.get("reportperiod")), default=None),
        "last_reportperiod": max((row.get("reportperiod") for row in rows if row.get("reportperiod")), default=None),
        "network_requests_performed": 0,
    }


def _preflight(output: Path, backup_dir: Path, *, require_clean: bool) -> dict[str, Any]:
    resolved_paths = _assert_exact_production_paths()
    git_status = _run_git(("status", "--porcelain"))
    git_head = _run_git(("rev-parse", "HEAD"))
    short_head = _run_git(("rev-parse", "--short", "HEAD"))
    branch = _run_git(("branch", "--show-current"))
    upstream = _run_git(("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"))
    ahead_behind = _run_git(("rev-list", "--left-right", "--count", f"{branch}...{upstream}"))
    if require_clean and git_status:
        raise RuntimeError("PHASE13E_CLEAN_GIT_WORKTREE_REQUIRED")
    contains_required = subprocess.run(
        ("git", "merge-base", "--is-ancestor", REQUIRED_D13D3_1_SHORT, "HEAD"),
        cwd=ROOT,
        check=False,
    ).returncode == 0
    if not contains_required:
        raise RuntimeError(f"PHASE13E_REQUIRED_REVIEWED_COMMIT_MISSING:{REQUIRED_D13D3_1_SHORT}")
    behind = int(ahead_behind.split()[1])
    if behind:
        raise RuntimeError(f"PHASE13E_BRANCH_BEHIND_UPSTREAM:{ahead_behind}")
    git_dir = ROOT / ".git"
    interrupted = [
        name for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")
        if (git_dir / name).exists()
    ]
    interrupted.extend(name for name in ("rebase-merge", "rebase-apply") if (git_dir / name).exists())
    if interrupted:
        raise RuntimeError("PHASE13E_INTERRUPTED_GIT_OPERATION:" + ",".join(interrupted))
    process = _process_inventory()
    if process["conflicting_writers"]:
        raise RuntimeError("PHASE13E_CONFLICTING_WRITER:" + " | ".join(process["conflicting_writers"]))
    inventory = production_inventory()
    bad_dbs = {
        role: {
            "quick_check": item["quick_check"],
            "foreign_key_errors": item["foreign_key_errors"],
        }
        for role, item in inventory["databases"].items()
        if item["quick_check"] != "ok" or item["foreign_key_errors"]
    }
    if bad_dbs:
        raise RuntimeError("PHASE13E_PRODUCTION_INTEGRITY_PRECHECK_FAILED:" + json.dumps(bad_dbs, sort_keys=True))
    return {
        "git": {
            "head": git_head,
            "short_head": short_head,
            "contains_required_phase13d3_1_commit": contains_required,
            "branch": branch,
            "upstream": upstream,
            "ahead_behind": ahead_behind,
            "status_clean": not bool(git_status),
        },
        "resolved_paths": resolved_paths,
        "source": _verify_source_archive(),
        "identity": sndk_identity_evidence(),
        "process": process,
        "storage": _storage_gate(output, backup_dir),
        "production_inventory": inventory,
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
            raise RuntimeError(f"PHASE13E_BACKUP_INTEGRITY_FAILED:{role}")
        manifest[role] = copied
    write_json(backup_dir / "backup_manifest.json", manifest)
    return manifest


def _restore_backups(backup_manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    restored = {}
    for role in WRITE_ROLES:
        source = Path(str(backup_manifest[role]["destination"]))
        destination = PRODUCTION[role]
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
        restored[role] = database_inventory(destination)
        if restored[role]["quick_check"] != "ok" or restored[role]["foreign_key_errors"]:
            raise RuntimeError(f"PHASE13E_RESTORE_INTEGRITY_FAILED:{role}")
    return restored


def _diagnostic_endpoint_gate() -> dict[str, Any]:
    with _readonly(PRODUCTION["analysis"]) as conn:
        package = conn.execute(
            "SELECT package_id,model_fingerprint,evaluation_count FROM diagnostic_flag_package "
            "WHERE model_fingerprint='0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904' "
            "ORDER BY applied_at_utc DESC LIMIT 1"
        ).fetchone()
        if package is None:
            return {"active_diagnostic_package_id": None, "ok": False, "reason": "ACTIVE_DIAGNOSTIC_PACKAGE_NOT_FOUND"}
        row = conn.execute(
            "SELECT COUNT(*) AS endpoints,COALESCE(SUM(eval_count),0) AS evaluations,"
            "MIN(eval_count) AS min_eval,MAX(eval_count) AS max_eval,"
            "SUM(CASE WHEN eval_count=8 THEN 1 ELSE 0 END) AS eight_endpoints,"
            "SUM(CASE WHEN eval_count<>8 THEN 1 ELSE 0 END) AS non_eight_endpoints "
            "FROM ("
            "  SELECT e.endpoint_id,COUNT(v.flag_id) AS eval_count "
            "  FROM diagnostic_flag_endpoint e "
            "  LEFT JOIN diagnostic_flag_evaluation v USING(endpoint_id) "
            "  WHERE e.package_id=? "
            "  GROUP BY e.endpoint_id"
            ")",
            (package["package_id"],),
        ).fetchone()
    endpoints = int(row["endpoints"])
    evaluations = int(row["evaluations"])
    return {
        "active_diagnostic_package_id": int(package["package_id"]),
        "model_fingerprint": str(package["model_fingerprint"]),
        "endpoint_rows": endpoints,
        "evaluation_rows": evaluations,
        "package_evaluation_count": int(package["evaluation_count"]),
        "min_evaluations_per_endpoint": int(row["min_eval"] or 0),
        "max_evaluations_per_endpoint": int(row["max_eval"] or 0),
        "eight_evaluation_endpoints": int(row["eight_endpoints"] or 0),
        "non_eight_evaluation_endpoints": int(row["non_eight_endpoints"] or 0),
        "ok": endpoints > 0 and evaluations == int(package["evaluation_count"]) and int(row["non_eight_endpoints"] or 0) == 0,
    }


def _counts_for_sndk() -> dict[str, Any]:
    with _readonly(PRODUCTION["canonical"]) as canonical:
        identity = canonical.execute(
            "SELECT c.company_id,s.security_id,s.current_ticker,s.active FROM security s JOIN company c USING(company_id) "
            "WHERE UPPER(s.current_ticker)='SNDK'"
        ).fetchone()
        sndk1 = canonical.execute(
            "SELECT c.company_id,s.security_id,s.current_ticker,s.active FROM security s JOIN company c USING(company_id) "
            "WHERE UPPER(s.current_ticker)='SNDK1'"
        ).fetchall()
    if identity is None:
        return {"identity_status": "NOT_PRESENT"}
    company_id = int(identity["company_id"])
    with _readonly(PRODUCTION["provider"]) as provider, _readonly(PRODUCTION["canonical"]) as canonical, _readonly(PRODUCTION["analysis"]) as analysis:
        return {
            "identity_status": "RESOLVED_DISTINCT_SECURITY_WITH_CORPORATE_LINEAGE",
            "company_id": company_id,
            "security_id": int(identity["security_id"]),
            "sndk1_rows": [dict(row) for row in sndk1],
            "provider_observations": int(provider.execute(
                "SELECT COUNT(*) FROM provider_observation WHERE UPPER(provider_ticker)='SNDK'"
            ).fetchone()[0]),
            "provider_arq_observations": int(provider.execute(
                "SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE UPPER(ticker)='SNDK' AND dimension='ARQ'"
            ).fetchone()[0]),
            "canonical_quarters": int(canonical.execute(
                "SELECT COUNT(*) FROM v4_quarter WHERE company_id=?", (company_id,)
            ).fetchone()[0]),
            "ttm_endpoints": int(canonical.execute(
                "SELECT COUNT(*) FROM v4_ttm_values WHERE company_id=?", (company_id,)
            ).fetchone()[0]),
            "relative_position_rows": int(analysis.execute(
                "SELECT COUNT(*) FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) WHERE r.company_id=?",
                (company_id,),
            ).fetchone()[0]),
            "relative_valuation_rows": int(analysis.execute(
                "SELECT COUNT(*) FROM relative_valuation_company_result r JOIN relative_valuation_active_snapshot a USING(snapshot_id) WHERE r.company_id=?",
                (company_id,),
            ).fetchone()[0]),
        }


def _verify_sndk_taxonomy_readonly() -> dict[str, Any]:
    before = taxonomy_identity(PRODUCTION["taxonomy"])
    with _readonly(PRODUCTION["taxonomy"]) as conn:
        entity = conn.execute(
            "SELECT entity_id,entity_code,entity_name,ticker,status FROM ec_entity "
            "WHERE UPPER(ticker)='SNDK' OR UPPER(entity_code)='SNDK' ORDER BY entity_id LIMIT 1"
        ).fetchone()
        if entity is None:
            return {"outcome": "TAXONOMY_REVIEW_REQUIRED", "reason": "SNDK taxonomy entity missing", "before": before, "after": before}
        memberships = [dict(row) for row in conn.execute(
            "SELECT parent.entity_code,parent.entity_name,m.membership_type,m.membership_role,m.is_primary,m.status "
            "FROM ec_membership m JOIN ec_entity parent ON parent.entity_id=m.parent_entity_id "
            "WHERE m.child_entity_id=? AND m.status='ACTIVE' ORDER BY parent.entity_code,m.membership_id",
            (int(entity["entity_id"]),),
        )]
    after = taxonomy_identity(PRODUCTION["taxonomy"])
    return {
        "outcome": "CONNECTED_EXISTING_MEMBERSHIP" if memberships else "TAXONOMY_REVIEW_REQUIRED",
        "entity": dict(entity),
        "memberships": memberships,
        "write_performed": False,
        "created_duplicate_memberships": 0,
        "before": before,
        "after": after,
        "economic_fingerprint_changed": before["taxonomy_economic_fingerprint"] != after["taxonomy_economic_fingerprint"],
        "presentation_fingerprint_changed": before["taxonomy_presentation_fingerprint"] != after["taxonomy_presentation_fingerprint"],
    }


def _snapshot_smoke(output: Path) -> dict[str, Any]:
    report_dir = output / "snapshot_smoke"
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = SnapshotPaths(PRODUCTION["canonical"], PRODUCTION["analysis"], PRODUCTION["market"], PRODUCTION["taxonomy"], PRODUCTION["provider"])
    first = generate_active_company_snapshot(paths, ticker="SNDK", report_date=REPORT_DATE, output_dir=report_dir, overwrite=True)
    text1 = Path(first["output_path"]).read_text(encoding="utf-8")
    second = generate_active_company_snapshot(paths, ticker="SNDK", report_date=REPORT_DATE, output_dir=report_dir, overwrite=True)
    text2 = Path(second["output_path"]).read_text(encoding="utf-8")
    return {
        "status": first["status"],
        "output_path": first["output_path"],
        "fingerprint": first["report_content_fingerprint"],
        "second_fingerprint": second["report_content_fingerprint"],
        "deterministic_content": text1 == text2 and first["report_content_fingerprint"] == second["report_content_fingerprint"],
        "contains_sndk1": "SNDK1" in text1,
        "leaks_internal_database_ids": any(token in text1 for token in ("company_id=", "security_id=", "snapshot_id=")),
    }


def _manual_rv_refresh(output: Path, *, applied_at_utc: str) -> dict[str, Any]:
    source = load_relative_valuation_source(
        ReadOnlySourcePaths(PRODUCTION["analysis"], PRODUCTION["canonical"], PRODUCTION["market"], PRODUCTION["taxonomy"]),
        as_of_date=REPORT_DATE,
    )
    snapshot = calculate_relative_valuation(
        source.inputs,
        as_of_date=REPORT_DATE,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    content, physical = validate_snapshot(snapshot, source.inputs)
    with sqlite3.connect(PRODUCTION["analysis"]) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        first = apply_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at_utc)
        check = rv_quick_check(conn)
        repo = RelativeValuationRepository(conn)
        active = repo.active_metadata(model_fingerprint=RV_MODEL_FINGERPRINT)
        before_second = database_inventory(PRODUCTION["analysis"])
        second = apply_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at_utc)
        after_second = database_inventory(PRODUCTION["analysis"])
    result = {
        "source_metadata": source.metadata,
        "snapshot": {
            "snapshot_id": first.snapshot_id,
            "as_of_date": REPORT_DATE,
            "source_fingerprint": snapshot.source_fingerprint,
            "result_fingerprint": snapshot.result_fingerprint,
            "physical_content_fingerprint": physical,
            "company_count": len(content["companies"]),
            "peer_rows": len(content["peers"]),
            "own_history_rows": len(content["own_history"]),
            "component_rows": len(content["components"]),
        },
        "first_apply": asdict(first),
        "second_apply": asdict(second),
        "second_analysis_inventory_no_change": before_second == after_second,
        "quick_check": check,
        "active_metadata": active,
    }
    write_json(output / "relative_valuation_manual_refresh.json", result)
    return result


def _apply_sndk(output: Path, *, applied_at_utc: str) -> dict[str, Any]:
    rows = archive_rows_for_ticker("SNDK")
    identity = create_sndk_canonical_identity(PRODUCTION["canonical"], now=applied_at_utc)
    if str(sndk_identity_evidence()["permanent_provider_identity"]["permaticker"]) != SNDK_PERMATICKER:
        raise RuntimeError("PHASE13E_SNDK_IDENTITY_DRIFT")
    stage = stage_sndk_archive_rows(
        PRODUCTION["provider"],
        rows,
        company_id=int(identity["company_id"]),
        security_id=int(identity["security_id"]),
        now=applied_at_utc,
    )
    taxonomy = _verify_sndk_taxonomy_readonly()
    if taxonomy["outcome"] != "CONNECTED_EXISTING_MEMBERSHIP":
        raise RuntimeError(f"PHASE13E_TAXONOMY_NOT_READY:{taxonomy['outcome']}")
    if taxonomy["economic_fingerprint_changed"] or taxonomy["presentation_fingerprint_changed"]:
        raise RuntimeError("PHASE13E_TAXONOMY_CHANGED_DURING_READONLY_VERIFICATION")
    canonical = reconcile_canonical(PRODUCTION["provider"], PRODUCTION["canonical"], applied_at=applied_at_utc)
    ttm = rebuild_ttm(PRODUCTION["canonical"], applied_at=applied_at_utc)
    package = refresh_active_package(PRODUCTION)
    paths = CandidatePaths(
        canonical_db=PRODUCTION["canonical"],
        analysis_db=PRODUCTION["analysis"],
        taxonomy_db=PRODUCTION["taxonomy"],
        provider_db=PRODUCTION["provider"],
        market_db=PRODUCTION["market"],
    )
    schema = ensure_candidate_schema(paths, applied_at_utc=applied_at_utc, apply=True, allow_production=True)
    universe = backfill_universe(paths, applied_at_utc=applied_at_utc, apply=True, allow_production=True)
    rp = refresh_relative_position(
        canonical_db=PRODUCTION["canonical"],
        analysis_db=PRODUCTION["analysis"],
        market_db=PRODUCTION["market"],
        taxonomy_db=PRODUCTION["taxonomy"],
        snapshot_date=REPORT_DATE,
        model_fingerprint=RP_MODEL_FINGERPRINT,
        applied_at_utc=applied_at_utc,
    )
    taxonomy_identity_after = taxonomy_identity(PRODUCTION["taxonomy"])
    pre_refresh = candidate_relative_valuation_dependency_state(
        PRODUCTION["analysis"],
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy_identity_after["taxonomy_economic_fingerprint"],
    )
    if pre_refresh["state"] != "OPERATIONAL_UNIVERSE_MISMATCH":
        raise RuntimeError(f"PHASE13E_REQUIRED_RV_MISMATCH_NOT_OBSERVED:{pre_refresh}")
    rv = _manual_rv_refresh(output, applied_at_utc=applied_at_utc)
    dependencies = attach_dependencies(
        paths,
        universe=universe["identity"],
        applied_at_utc=applied_at_utc,
        apply=True,
        allow_production=True,
    )
    post_refresh = candidate_relative_valuation_dependency_state(
        PRODUCTION["analysis"],
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy_identity_after["taxonomy_economic_fingerprint"],
    )
    if post_refresh["state"] != "COMPATIBLE":
        raise RuntimeError(f"PHASE13E_RV_COMPATIBILITY_NOT_RESTORED:{post_refresh}")
    snapshot = _snapshot_smoke(output)
    diagnostic_gate = _diagnostic_endpoint_gate()
    if not diagnostic_gate["ok"]:
        raise RuntimeError("PHASE13E_DIAGNOSTIC_EIGHT_GATE_FAILED")
    readiness = _readiness(
        type("ProductionCopies", (), {
            "provider": PRODUCTION["provider"],
            "canonical": PRODUCTION["canonical"],
            "analysis": PRODUCTION["analysis"],
            "market": PRODUCTION["market"],
            "taxonomy": PRODUCTION["taxonomy"],
        })(),
        "SNDK",
    )
    return {
        "identity": identity,
        "stage": stage,
        "taxonomy": taxonomy,
        "canonical": canonical,
        "ttm": ttm,
        "package": package,
        "schema": schema,
        "universe": universe,
        "relative_position": asdict(rp),
        "pre_refresh_compatibility": pre_refresh,
        "relative_valuation": rv,
        "dependencies": dependencies,
        "post_refresh_compatibility": post_refresh,
        "snapshot": snapshot,
        "diagnostics": diagnostic_gate,
        "sndk_counts": _counts_for_sndk(),
        "readiness": readiness,
    }


def run_phase13e(output: Path | None = None, *, apply: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    backup_dir = BACKUP_ROOT / output.name
    output.mkdir(parents=True, exist_ok=True)
    try:
        preflight = _preflight(output, backup_dir, require_clean=apply)
    except Exception as exc:
        result = {"outcome": OUTCOME_B, "artifact_dir": str(output), "error": type(exc).__name__, "reason": str(exc)}
        write_json(output / "phase13e_result.json", result)
        return result
    write_json(output / "production_preflight.json", preflight)
    if not apply:
        result = {
            "outcome": OUTCOME_B,
            "mode": "DRY_RUN",
            "artifact_dir": str(output),
            "prewrite_blocker": None,
            "write_set": list(WRITE_ROLES),
            "read_only_roles": list(READ_ONLY_ROLES),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        write_json(output / "phase13e_result.json", result)
        return result
    backup_manifest: dict[str, Any] | None = None
    lock_handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup_manifest = _backup_write_set(backup_dir)
        write_json(output / "backup_manifest.json", backup_manifest)
        applied_at = utc_now()
        before_apply = production_inventory()
        first = _apply_sndk(output, applied_at_utc=applied_at)
        second_before = production_inventory()
        second = _apply_sndk(output, applied_at_utc=applied_at)
        second_after = production_inventory()
        second_no_change = {
            "provider_inserted_rows": second["stage"]["inserted_rows"],
            "canonical_outcome": second["canonical"].get("NEW_HISTORY", 0) == 0 and second["canonical"].get("REVISED_OVERLAP", 0) == 0,
            "ttm_outcome": second["ttm"]["outcome"],
            "package_outcome": second["package"]["outcome"],
            "universe_outcome": second["universe"]["outcome"],
            "relative_position_outcome": second["relative_position"]["apply"]["outcome"],
            "relative_valuation_second_apply": second["relative_valuation"]["first_apply"]["outcome"],
            "inventory_exact_no_change": second_before == second_after,
        }
        postflight = production_inventory()
        compare = compare_production_inventory(before_apply, postflight)
        final_integrity = {role: database_inventory(path) for role, path in PRODUCTION.items()}
        result = {
            "outcome": OUTCOME_A,
            "mode": "APPLY",
            "artifact_dir": str(output),
            "backup_dir": str(backup_dir),
            "activation_timestamp": applied_at,
            "source": preflight["source"],
            "identity": {
                "ticker": "SNDK",
                "permaticker": SNDK_PERMATICKER,
                "cik": SNDK_CIK,
                "status": "RESOLVED_DISTINCT_SECURITY_WITH_CORPORATE_LINEAGE",
                "predecessor": "SNDK1/permaticker 197210",
            },
            "first_apply": first,
            "second_apply_no_change": second_no_change,
            "backup_manifest": backup_manifest,
            "production_compare": compare,
            "production_postflight": postflight,
            "final_integrity": final_integrity,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        write_json(output / "first_apply.json", first)
        write_json(output / "second_apply_no_change.json", second_no_change)
        write_json(output / "production_postflight.json", postflight)
        write_json(output / "phase13e_result.json", result)
        return result
    except Exception as exc:
        restored = None
        if backup_manifest is not None:
            restored = _restore_backups(backup_manifest)
        result = {
            "outcome": OUTCOME_C if backup_manifest is not None else OUTCOME_B,
            "mode": "APPLY",
            "artifact_dir": str(output),
            "backup_dir": str(backup_dir),
            "error": type(exc).__name__,
            "reason": str(exc),
            "restored": restored,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        write_json(output / "phase13e_result.json", result)
        return result
    finally:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        finally:
            lock_handle.close()
