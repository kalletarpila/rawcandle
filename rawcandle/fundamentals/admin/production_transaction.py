"""Guarded whole-database publication for Fundamentals Administration."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths, database_inventory, online_backup
from rawcandle.fundamentals.admin.contracts import AdminOperationType, RunStage, utc_now
from rawcandle.fundamentals.operating_income_v2.full_rebuild import rebuild_v2_analysis, validate_rebuild
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import load_active_dc_memberships
from rawcandle.fundamentals.phase12d import PRODUCTION
from rawcandle.fundamentals.phase13b_foundation import database_fingerprint
from rawcandle.scheduler.config import read_scheduler_config
from rawcandle.scheduler.runner import acquire_scheduler_lock, release_scheduler_lock


ROOT = Path(__file__).resolve().parents[3]
ADMIN_LOCK = ROOT / "temp/.fundamentals_admin_production.lock"
BACKUP_ROOT = ROOT / "backups/fundamentals_admin_production"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_sqlite(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        foreign = conn.execute("PRAGMA foreign_key_check").fetchone()
    if quick != "ok" or foreign is not None:
        raise RuntimeError(f"ADMIN_BACKUP_OR_DATABASE_INVALID:{path}")
    return {"quick_check": quick, "foreign_key_check": "ok", "sha256": _sha256(path), "size": path.stat().st_size}


def _no_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise RuntimeError(f"ADMIN_PRODUCTION_SQLITE_SIDECAR_PRESENT:{path.name}{suffix}")


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


@contextmanager
def production_lock(*, lock_path: Path = ADMIN_LOCK, scheduler_log_dir: str | None = None) -> Iterator[dict[str, Any]]:
    """Kernel locks, never deleted; stale owner text has no locking authority."""
    if scheduler_log_dir is None:
        scheduler_log_dir = read_scheduler_config(str(ROOT / "scheduler_config.json")).log_dir
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("ADMIN_PRODUCTION_UPDATE_ALREADY_RUNNING") from exc
        owner = {"pid": os.getpid(), "started_at_utc": utc_now(), "scheduler_log_dir": scheduler_log_dir}
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(owner, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            scheduler_handle = acquire_scheduler_lock(scheduler_log_dir)
            try:
                yield owner
            finally:
                release_scheduler_lock(scheduler_handle)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _source_fingerprints(paths: BatchAddTickerPaths) -> dict[str, Any]:
    state = {}
    for role in ("provider", "canonical", "market", "analysis"):
        path = paths.as_dict()[role]
        _no_sidecars(path)
        state[role] = {"database": database_fingerprint(path), "content_sha256": _sha256(path)}
    _, active = load_active_dc_memberships(paths.taxonomy_db, paths.canonical_db)
    state["taxonomy"] = {"database": database_fingerprint(paths.taxonomy_db), "active": active}
    return state


def _verify_test(run_root: Path, test_run_id: str, operation: AdminOperationType, preview_fingerprint: str) -> dict[str, Any]:
    if not test_run_id or Path(test_run_id).name != test_run_id or "/" in test_run_id or ".." in test_run_id:
        raise ValueError("ADMIN_PRODUCTION_TEST_RUN_ID_REQUIRED")
    path = run_root / test_run_id / "result.json"
    if path.is_symlink() or not path.resolve().is_relative_to(run_root.resolve()):
        raise ValueError("ADMIN_PRODUCTION_TEST_PATH_INVALID")
    result = json.loads(path.read_text(encoding="utf-8"))
    downstream = result.get("downstream") or {}
    if (result.get("operation_type"), result.get("mode"), result.get("outcome"), result.get("preview_fingerprint")) != (
        operation.value, "COPY_ONLY_APPLY", "COMPLETED", preview_fingerprint,
    ) or downstream.get("invocation_counts", {}).get("full_v2_rebuild") != 1:
        raise ValueError("ADMIN_PRODUCTION_MATCHING_SUCCESSFUL_TEST_REQUIRED")
    return result


def _backup_write_set(paths: BatchAddTickerPaths, roles: tuple[str, ...], backup_dir: Path) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {}
    for role in roles:
        source = paths.as_dict()[role]
        if role != "taxonomy":
            _no_sidecars(source)
        destination = backup_dir / f"{role}.db"
        online_backup(source, destination)
        verified = _check_sqlite(destination)
        if database_inventory(destination)["quick_check"] != "ok":
            raise RuntimeError(f"ADMIN_BACKUP_INVALID:{role}")
        manifest[role] = {"source": str(source), "backup": str(destination), "verification": verified}
    return manifest


def _storage_preflight(paths: BatchAddTickerPaths, roles: tuple[str, ...], backup_root: Path) -> dict[str, Any]:
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_bytes = sum(paths.as_dict()[role].stat().st_size for role in roles)
    analysis_bytes = paths.analysis_db.stat().st_size
    requirements: dict[int, dict[str, Any]] = {}
    for location, required in (
        (backup_root, backup_bytes * 2),
        (paths.analysis_db.parent, analysis_bytes * 3),
    ):
        device = location.stat().st_dev
        entry = requirements.setdefault(device, {"paths": [], "required_bytes": 0})
        entry["paths"].append(str(location))
        entry["required_bytes"] += max(required, 8 * 1024 * 1024)
    for entry in requirements.values():
        entry["available_bytes"] = shutil.disk_usage(entry["paths"][0]).free
        if entry["available_bytes"] < entry["required_bytes"]:
            raise RuntimeError("ADMIN_INSUFFICIENT_DISK_FOR_BACKUP_REBUILD_AND_ROLLBACK")
    return {str(device): entry for device, entry in requirements.items()}


def _restore_all(paths: BatchAddTickerPaths, backups: Mapping[str, Any], *, run_dir: Path) -> dict[str, Any]:
    restored: dict[str, Any] = {}
    for role, record in backups.items():
        target = paths.as_dict()[role]
        backup = Path(record["backup"])
        if _check_sqlite(backup)["sha256"] != record["verification"]["sha256"]:
            raise RuntimeError(f"ADMIN_ROLLBACK_BACKUP_CHANGED:{role}")
        _no_sidecars(target)
        stage = target.parent / f".{target.name}.{run_dir.name}.restore"
        shutil.copy2(backup, stage)
        try:
            if _sha256(stage) != record["verification"]["sha256"]:
                raise RuntimeError(f"ADMIN_ROLLBACK_STAGE_CHANGED:{role}")
            _fsync_file(stage)
            os.replace(stage, target)
            _fsync_dir(target.parent)
            verified = _check_sqlite(target)
            if verified["sha256"] != record["verification"]["sha256"]:
                raise RuntimeError(f"ADMIN_ROLLBACK_VERIFY_FAILED:{role}")
            restored[role] = verified
        finally:
            stage.unlink(missing_ok=True)
    return {"status": "ROLLED_BACK", "roles": restored}


def _publish_candidate(
    *, candidate: Path, target: Path, rebuild: Mapping[str, Any], backup: Mapping[str, Any],
    lock_owner: Mapping[str, Any], bound_test: Mapping[str, Any], source_stable: bool,
    production_intent: bool, rehearsal: bool,
) -> dict[str, Any]:
    is_production_target = target.resolve() == PRODUCTION["analysis"].resolve()
    if is_production_target != (production_intent and not rehearsal):
        raise PermissionError("ADMIN_PUBLICATION_EXPLICIT_PRODUCTION_INTENT_REQUIRED")
    if not lock_owner or not bound_test or not source_stable:
        raise PermissionError("ADMIN_PUBLICATION_GATES_MISSING")
    if rebuild.get("status") != "READY" or Path(str(rebuild.get("target", ""))).resolve() != candidate.resolve():
        raise RuntimeError("ADMIN_CANDIDATE_READY_MARKER_MISSING")
    if candidate.resolve() == target.resolve() or candidate.is_symlink() or target.is_symlink():
        raise ValueError("ADMIN_CANDIDATE_PATH_UNSAFE")
    if candidate.stat().st_dev != target.stat().st_dev:
        raise RuntimeError("ADMIN_ATOMIC_REPLACE_CROSS_FILESYSTEM")
    if not backup or _check_sqlite(Path(backup["backup"]))["sha256"] != backup["verification"]["sha256"]:
        raise RuntimeError("ADMIN_ANALYSIS_BACKUP_NOT_VERIFIED")
    _no_sidecars(candidate)
    _no_sidecars(target)
    fingerprint = _sha256(candidate)
    _fsync_file(candidate)
    os.replace(candidate, target)
    _fsync_dir(target.parent)
    return {"status": "REPLACED", "candidate_sha256": fingerprint, "production_sha256": _sha256(target), "same_filesystem": True}


@dataclass(frozen=True)
class ProductionOperation:
    operation_type: AdminOperationType
    written_roles: tuple[str, ...]
    validate_preview: Callable[[BatchAddTickerPaths, Mapping[str, Any], str], dict[str, Any]]
    mutate_sources: Callable[[BatchAddTickerPaths, Mapping[str, Any]], dict[str, Any]]


def render_production_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Fundamentals Administration production transaction", "",
        f"Operation: {result['operation_type']}",
        f"Final status: {result['outcome']}",
        f"Requested change: {json.dumps(result.get('requested_change'), sort_keys=True, default=str)}",
        f"Preview: {result.get('preview', {}).get('payload', 'not validated')}",
        f"Preview fingerprint: {result.get('preview_fingerprint')}",
        f"Test on copies: {result.get('test_run_id') or 'not required for no-change'}",
        f"As-of date: {result.get('as_of_date') or 'not established'}", "",
        "## Guard and sources", "",
        f"Lock owner: {json.dumps(result.get('lock_owner'), sort_keys=True, default=str)}",
        f"Source state verified before publication: {result.get('source_state_verified') is True}",
        f"Source writes: {(result.get('source_writes') or {}).get('outcome', 'not run')}; tickers: {', '.join((result.get('source_writes') or {}).get('tickers') or []) or 'none'}", "",
        "## Verified backups", "",
    ]
    backups = result.get("backups") or {}
    if backups:
        for role, entry in backups.items():
            verified = entry["verification"]
            lines.append(f"- {role}: {entry['backup']} ({verified['size']} bytes; quick_check={verified['quick_check']}; foreign_key_check={verified['foreign_key_check']}; sha256={verified['sha256']})")
    else:
        lines.append("No backup was required before the write boundary.")
    rebuild = result.get("full_v2_rebuild") or {}
    package = rebuild.get("package") or {}
    validation = rebuild.get("validation") or {}
    rv = rebuild.get("rv") or {}
    taxonomy = rebuild.get("taxonomy_dependency") or {}
    lines.extend([
        "", "## Full V2 candidate", "",
        f"B1 gate: {rebuild.get('status', 'not run')}",
        f"Score/Valuation/RP counts: {json.dumps(package.get('rows'), sort_keys=True, default=str)}",
        f"RV company/peer/component rows: {rv.get('company_rows_inserted', 'not run')} / {rv.get('peer_rows_inserted', 'not run')} / {rv.get('component_rows_inserted', 'not run')}",
        f"RV input count: {validation.get('rv_input_count', 'not run')}",
        f"Taxonomy: {taxonomy.get('domain', 'not run')} / {taxonomy.get('version', 'not run')}",
        f"Taxonomy semantic fingerprint: {taxonomy.get('semantic_fingerprint', 'not run')}",
        f"Candidate validation: {json.dumps(validation, sort_keys=True, default=str)}",
        "", "## Publication and postflight", "",
        f"Atomic replacement: {json.dumps(result.get('atomic_replacement'), sort_keys=True, default=str)}",
        f"Production-path postflight: {json.dumps(result.get('postflight'), sort_keys=True, default=str)}",
        f"Rollback: {json.dumps(result.get('rollback'), sort_keys=True, default=str)}",
    ])
    if result.get("error"):
        lines.append(f"Failure at {result.get('failed_stage')}: {result['error']}")
    return "\n".join(lines) + "\n"


def run_transaction(
    operation: ProductionOperation, *, preview_payload_path: Path, preview_fingerprint: str,
    test_run_id: str, source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT, backup_root: Path | None = None,
    scheduler_log_dir: str | None = None, lock_path: Path = ADMIN_LOCK,
    production_intent: bool = False, rehearsal: bool = False,
    inject_failure_at: str | None = None,
) -> dict[str, Any]:
    production_analysis = PRODUCTION["analysis"].resolve()
    actual_production = source_paths.analysis_db.resolve() == production_analysis
    if actual_production != (production_intent and not rehearsal):
        raise PermissionError("ADMIN_EXPLICIT_PRODUCTION_INTENT_REQUIRED")
    if actual_production and any(source_paths.as_dict()[role].resolve() != PRODUCTION[role].resolve() for role in source_paths.as_dict()):
        raise PermissionError("ADMIN_EXACT_PRODUCTION_PATHS_REQUIRED")
    if not actual_production and any(path.resolve() in {p.resolve() for p in PRODUCTION.values()} for path in source_paths.as_dict().values()):
        raise PermissionError("ADMIN_REHEARSAL_MUST_USE_ONLY_COPIES")
    if actual_production and (run_root.resolve() != ADMIN_RUN_ROOT.resolve() or lock_path.resolve() != ADMIN_LOCK.resolve()):
        raise PermissionError("ADMIN_PRODUCTION_GUARD_PATH_OVERRIDE_REJECTED")
    payload_path = Path(preview_payload_path)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    run_id = stable_run_id(operation.operation_type, preview_fingerprint, suffix="production" if actual_production else "transaction_rehearsal") + "_" + secrets.token_hex(4)
    writer = AdminRunWriter(run_id, operation.operation_type, root=run_root)
    started = utc_now()
    stage = "PREFLIGHT"
    backups: dict[str, Any] = {}
    replaced = False
    publication_started = False
    source_mutation_started = False
    write_boundary_crossed = False
    candidate_owned = False
    candidate = source_paths.analysis_db.parent / f".{source_paths.analysis_db.name}.{run_id}.candidate.db"
    if candidate.exists() or candidate.is_symlink():
        raise FileExistsError("ADMIN_CANDIDATE_STAGING_PATH_EXISTS")
    backup_dir = (backup_root or BACKUP_ROOT) / run_id
    result: dict[str, Any] = {"run_id": run_id, "artifact_dir": str(writer.run_dir), "operation_type": operation.operation_type.value, "mode": "PRODUCTION_APPLY" if actual_production else "TRANSACTION_REHEARSAL", "preview_fingerprint": preview_fingerprint, "test_run_id": test_run_id, "as_of_date": None, "started_at_utc": started, "outcome": "FAILED", "write_set": list(operation.written_roles)}
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Guarded production transaction requested.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Validating Preview and Test on copies.", preview_fingerprint=preview_fingerprint)
    locks = ExitStack()
    try:
        if actual_production:
            from rawcandle.fundamentals.admin.batch_add_tickers import _assert_clean_worktree
            _assert_clean_worktree()
        preview = operation.validate_preview(source_paths, payload, preview_fingerprint)
        result["as_of_date"] = preview["as_of_date"]
        result["requested_change"] = preview.get("request") or preview.get("requested") or preview.get("taxonomy_dependency", {}).get("domain")
        result["preview"] = {"payload": str(payload_path), "fingerprint": preview_fingerprint}
        if preview.get("no_change"):
            writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="No source or analysis change required.", preview_fingerprint=preview_fingerprint)
            result.update(outcome="NO_CHANGE", completed_at_utc=utc_now(), backups={})
            return result
        test = _verify_test(run_root, test_run_id, operation.operation_type, preview_fingerprint)
        tested_taxonomy = test.get("downstream", {}).get("active_taxonomy") or {}
        preview_taxonomy = preview["taxonomy_dependency"]
        if any(tested_taxonomy.get(key) != preview_taxonomy.get(key) for key in ("domain", "version", "semantic_fingerprint")):
            raise ValueError("ADMIN_PRODUCTION_TEST_TAXONOMY_MISMATCH")
        result["test_on_copies"] = {"run_id": test_run_id, "outcome": test["outcome"]}
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Preview and Test are bound; no production write yet.", preview_fingerprint=preview_fingerprint)
        owner = locks.enter_context(production_lock(lock_path=lock_path, scheduler_log_dir=scheduler_log_dir))
        if owner:
            result["lock_owner"] = owner
            operation.validate_preview(source_paths, payload, preview_fingerprint)
            locked_source_state = _source_fingerprints(source_paths)
            stage = "BACKUP"
            result["storage_preflight"] = _storage_preflight(source_paths, operation.written_roles, backup_dir.parent)
            backups = _backup_write_set(source_paths, operation.written_roles, backup_dir)
            result["backups"] = backups
            if locked_source_state != _source_fingerprints(source_paths):
                raise RuntimeError("ADMIN_SOURCE_CHANGED_DURING_BACKUP")
            stage = "SOURCE_MUTATION"
            source_mutation_started = len(operation.written_roles) > 1
            if source_mutation_started:
                writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Authoritative source mutation starting.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
                write_boundary_crossed = True
            mutation = operation.mutate_sources(source_paths, preview)
            result["source_writes"] = mutation
            if mutation.get("outcome") == "NO_CHANGE":
                result.update(outcome="NO_CHANGE", completed_at_utc=utc_now())
                return result
            stage = "SOURCE_STABILITY"
            before_rebuild = _source_fingerprints(source_paths)
            stage = "FULL_V2_REBUILD"
            sources = {role: source_paths.as_dict()[role] for role in ("provider", "canonical", "market", "taxonomy")}
            if candidate.exists() or candidate.is_symlink():
                raise FileExistsError("ADMIN_CANDIDATE_STAGING_PATH_EXISTS")
            candidate_owned = True
            rebuild = rebuild_v2_analysis(candidate, sources, as_of_date=preview["as_of_date"], output=writer.run_dir / "full_v2_rebuild", inject_failure_at=inject_failure_at if inject_failure_at in {"v2_calculation", "validation"} else None)
            if rebuild["status"] != "READY":
                raise RuntimeError("ADMIN_FULL_V2_CANDIDATE_NOT_READY")
            result["full_v2_rebuild"] = {"status": rebuild["status"], "package": rebuild["package"], "validation": rebuild["validation"], "taxonomy_dependency": rebuild["taxonomy_dependency"], "rv": rebuild["rv"]}
            stage = "SOURCE_RECHECK"
            if before_rebuild != _source_fingerprints(source_paths):
                raise RuntimeError("ADMIN_SOURCE_CHANGED_DURING_REBUILD")
            expected_taxonomy = preview["taxonomy_dependency"]
            actual_taxonomy = rebuild["taxonomy_dependency"]
            if any(expected_taxonomy[key] != actual_taxonomy[key] for key in ("domain", "version", "semantic_fingerprint")):
                raise RuntimeError("ADMIN_ACTIVE_TAXONOMY_CHANGED_DURING_REBUILD")
            result["source_state_verified"] = True
            stage = "PUBLICATION"
            if not write_boundary_crossed:
                writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Atomic analysis replacement starting.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
                write_boundary_crossed = True
            publication_started = True
            result["atomic_replacement"] = _publish_candidate(candidate=candidate, target=source_paths.analysis_db, rebuild=rebuild, backup=backups["analysis"], lock_owner=owner, bound_test=test, source_stable=True, production_intent=production_intent, rehearsal=rehearsal)
            replaced = True
            if inject_failure_at == "post_replacement":
                raise RuntimeError("ADMIN_INJECTED_POST_REPLACEMENT_FAILURE")
            stage = "POSTFLIGHT"
            postflight = validate_rebuild(source_paths.analysis_db, as_of_date=preview["as_of_date"], taxonomy_dependency=actual_taxonomy, sources=sources)
            if _sha256(source_paths.analysis_db) != result["atomic_replacement"]["candidate_sha256"]:
                raise RuntimeError("ADMIN_PRODUCTION_PATH_FINGERPRINT_MISMATCH")
            result["postflight"] = postflight
            result.update(outcome="COMPLETED", completed_at_utc=utc_now(), rollback={"status": "NOT_REQUIRED"})
            return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["failed_stage"] = stage
        if backups and (source_mutation_started or publication_started):
            try:
                writer.checkpoint(RunStage.ROLLBACK_STARTED, message="Restoring pre-operation databases.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
                result["rollback"] = _restore_all(source_paths, backups, run_dir=writer.run_dir)
                result["outcome"] = "FAILED_ROLLED_BACK"
                writer.checkpoint(RunStage.ROLLBACK_COMPLETE, message="Pre-operation databases restored.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            except Exception as rollback_exc:
                result["rollback"] = {"status": "CRITICAL_ROLLBACK_FAILED", "error": f"{type(rollback_exc).__name__}: {rollback_exc}"}
                result["outcome"] = "CRITICAL_ROLLBACK_FAILED"
        result["completed_at_utc"] = utc_now()
        return result
    finally:
        locks.close()
        if candidate_owned:
            candidate.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(str(candidate) + suffix).unlink(missing_ok=True)
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", render_production_report(result))
        terminal = RunStage.COMPLETED if result["outcome"] in {"COMPLETED", "NO_CHANGE"} else RunStage.FAILED_AFTER_WRITE if write_boundary_crossed else RunStage.FAILED_BEFORE_WRITE
        writer.checkpoint(terminal, message=f"Production transaction {result['outcome']}.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(0 if result["outcome"] in {"COMPLETED", "NO_CHANGE"} else 3)
        writer.write_manifest()
