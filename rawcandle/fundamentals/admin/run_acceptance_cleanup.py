"""Run-specific acceptance and verified rollback-backup cleanup."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, sha256_file
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import utc_now
from rawcandle.fundamentals.admin.production_transaction import BACKUP_ROOT, production_lock
from rawcandle.fundamentals.admin.publication_journal import (
    ACTIVE_JOURNAL_PATH,
    INCOMPLETE_STATES,
    PublicationRecoveryError,
    load_journal,
)
from rawcandle.io_atomic import write_text_atomic


CLEANUP_EVIDENCE_NAME = "backup_cleanup.json"
KNOWN_ROLES = {"provider", "canonical", "analysis"}
_REASONS = {
    "CLEANUP_NO_RETAINED_BACKUPS": "No retained backups",
    "CLEANUP_BACKUP_MANIFEST_INVALID": "Backup ownership cannot be proven",
    "CLEANUP_PRIOR_EVIDENCE_INVALID": "Prior cleanup evidence is invalid",
    "CLEANUP_RUN_RESULT_MISMATCH": "Run evidence does not match the selected run",
}


class RunAcceptanceCleanupError(RuntimeError):
    pass


def _operator_reason(error: Exception) -> str:
    detail = str(error)
    if detail in _REASONS:
        return _REASONS[detail]
    if detail.startswith("CLEANUP_BACKUP_OWNERSHIP_UNPROVEN"):
        return "Backup ownership cannot be proven"
    if detail.startswith("CLEANUP_BACKUP_EVIDENCE_INCOMPLETE"):
        return "Backup hashes or fingerprints are missing"
    if detail.startswith("CLEANUP_BACKUP_VERIFICATION_MISSING"):
        return "Backup hashes or fingerprints are missing"
    return detail


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RunAcceptanceCleanupError(f"CLEANUP_EVIDENCE_INVALID:{path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunAcceptanceCleanupError(f"CLEANUP_EVIDENCE_INVALID:{path.name}") from exc
    if not isinstance(payload, dict):
        raise RunAcceptanceCleanupError(f"CLEANUP_EVIDENCE_INVALID:{path.name}")
    return payload


def _run_dir(run_id: str, run_root: Path) -> Path:
    if not run_id or Path(run_id).name != run_id or "/" in run_id or "\\" in run_id:
        raise RunAcceptanceCleanupError("CLEANUP_RUN_ID_INVALID")
    root = run_root.resolve()
    roots = [root]
    # Only the established sibling operation directory, never a recursive search.
    if root.name == "admin_runs":
        roots.append(root.parent / "publication_drains")
    candidates = [base / run_id for base in roots
                  if (base / run_id).exists() or (base / run_id).is_symlink()]
    if len(candidates) != 1:
        raise RunAcceptanceCleanupError("CLEANUP_RUN_DIRECTORY_INVALID")
    path = candidates[0]
    if path.is_symlink() or path.parent.is_symlink() or not path.is_dir() or path.resolve().parent != path.parent.resolve():
        raise RunAcceptanceCleanupError("CLEANUP_RUN_DIRECTORY_INVALID")
    return path.resolve()


def _successful_cleanup(run_dir: Path, run_id: str) -> dict[str, Any] | None:
    path = run_dir / CLEANUP_EVIDENCE_NAME
    if not path.exists():
        return None
    evidence = _load_json(path)
    if evidence.get("source_production_run_id") != run_id or evidence.get("cleanup_outcome") != "COMPLETED":
        raise RunAcceptanceCleanupError("CLEANUP_PRIOR_EVIDENCE_INVALID")
    return evidence


def _backup_records(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    backups = result.get("backups")
    if isinstance(backups, Mapping):
        for raw_role, raw_record in backups.items():
            role = str(raw_role)
            if role not in KNOWN_ROLES or not isinstance(raw_record, Mapping):
                raise RunAcceptanceCleanupError("CLEANUP_BACKUP_MANIFEST_INVALID")
            verification = raw_record.get("verification")
            if not isinstance(verification, Mapping):
                raise RunAcceptanceCleanupError(f"CLEANUP_BACKUP_VERIFICATION_MISSING:{role}")
            records[role] = {
                "path": raw_record.get("backup"),
                "source": raw_record.get("source"),
                "sha256": verification.get("sha256"),
                "recorded_size": verification.get("size"),
            }
    single = result.get("backup")
    if not records and isinstance(single, Mapping):
        verification = single.get("verification")
        if not isinstance(verification, Mapping):
            raise RunAcceptanceCleanupError("CLEANUP_BACKUP_VERIFICATION_MISSING:canonical")
        records["canonical"] = {
            "path": single.get("path"),
            "source": single.get("source"),
            "sha256": verification.get("sha256"),
            "recorded_size": verification.get("size"),
        }
    return records


def _publication_complete(result: Mapping[str, Any]) -> bool:
    postflight = result.get("postflight")
    atomic = result.get("atomic_replacement")
    journal = result.get("journal")
    if isinstance(postflight, Mapping) and postflight:
        if isinstance(atomic, Mapping) and atomic.get("status") == "REPLACED":
            return True
        if isinstance(journal, Mapping) and journal.get("state") == "COMPLETED" and journal.get("postflight_state") == "PASSED":
            return True
    validation = result.get("validation")
    return bool(
        isinstance(result.get("after_audit"), Mapping)
        and isinstance(validation, Mapping)
        and validation.get("published_binding_matches_candidate") is True
        and validation.get("non_target_canonical_unchanged") is True
        and validation.get("provider_unchanged") is True
        and validation.get("analysis_unchanged") is True
    )


def _journal_state(journal_path: Path) -> tuple[str, str | None]:
    try:
        journal = load_journal(journal_path)
    except PublicationRecoveryError as exc:
        return "INVALID", str(exc)
    if journal is None:
        return "CLEAR", None
    state = str(journal.get("state"))
    if state in INCOMPLETE_STATES or state == "RECOVERY_FAILED":
        return state, "Recovery journal still active"
    if state != "COMPLETED":
        return state, "Recovery or rollback journal is not clean"
    return state, None


def _generation_publication_sources(
    result: Mapping[str, Any], *, run_id: str,
) -> dict[str, Path] | None:
    journal = result.get("journal")
    if not isinstance(journal, Mapping) or journal.get("publication_mode") != "GENERATION_POINTER":
        return None
    required = {
        "state": "COMPLETED",
        "current_publication_step": "COMPLETED",
        "postflight_state": "PASSED",
        "rollback_recovery_state": "NOT_REQUIRED",
        "generation_activation_state": "ACTIVATED_AND_VERIFIED",
        "production_run_id": run_id,
    }
    if any(journal.get(key) != expected for key, expected in required.items()):
        raise RunAcceptanceCleanupError("Generation publication evidence is incomplete")
    old_generation = journal.get("old_generation")
    roles = old_generation.get("roles") if isinstance(old_generation, Mapping) else None
    if (
        not isinstance(old_generation, Mapping)
        or old_generation.get("layout") != "GENERATION_DIRECTORY"
        or not isinstance(roles, Mapping)
        or set(roles) != KNOWN_ROLES
    ):
        raise RunAcceptanceCleanupError("Generation backup source ownership is invalid")
    cleanup = result.get("terminal_cleanup")
    if cleanup is not None:
        verification = cleanup.get("cleanup_verification") if isinstance(cleanup, Mapping) else None
        retained = cleanup.get("intentionally_retained") if isinstance(cleanup, Mapping) else None
        retained_backups = retained.get("rollback_backups") if isinstance(retained, Mapping) else None
        if (
            not isinstance(cleanup, Mapping)
            or cleanup.get("status") != "COMPLETED"
            or cleanup.get("operator_acceptance_required_for_rollback_backup_deletion") != "YES"
            or not isinstance(verification, Mapping)
            or verification.get("status") != "PASSED"
            or not isinstance(retained_backups, list)
        ):
            raise RunAcceptanceCleanupError("Generation terminal cleanup evidence is incomplete")
        recorded_paths = {
            str(Path(str(item.get("path") or "")).resolve())
            for item in retained_backups
            if isinstance(item, Mapping)
        }
        backup_paths = {
            str(Path(str(record.get("backup") or "")).resolve())
            for record in (result.get("backups") or {}).values()
            if isinstance(record, Mapping)
        }
        if (
            int(retained.get("rollback_backup_count") or -1) != len(KNOWN_ROLES)
            or recorded_paths != backup_paths
        ):
            raise RunAcceptanceCleanupError("Generation retained backup evidence does not match")
    return {role: Path(str(roles[role])).resolve() for role in KNOWN_ROLES}


def _validated_manifest(
    result: Mapping[str, Any],
    *,
    run_id: str,
    backup_root: Path,
    live_paths: Mapping[str, Path],
    source_paths: Mapping[str, Path] | None = None,
) -> dict[str, dict[str, Any]]:
    records = _backup_records(result)
    if not records:
        raise RunAcceptanceCleanupError("CLEANUP_NO_RETAINED_BACKUPS")
    root = backup_root.resolve()
    validated: dict[str, dict[str, Any]] = {}
    owned_directories: set[Path] = set()
    for role, record in records.items():
        raw_path = str(record.get("path") or "")
        expected_hash = str(record.get("sha256") or "")
        if not raw_path or len(expected_hash) != 64:
            raise RunAcceptanceCleanupError(f"CLEANUP_BACKUP_EVIDENCE_INCOMPLETE:{role}")
        path = Path(raw_path)
        resolved = path.resolve()
        parent = path.absolute().parent
        symlinked_parent = False
        while parent != root and root in parent.resolve().parents:
            if parent.is_symlink():
                symlinked_parent = True
                break
            parent = parent.parent
        if (
            path.is_symlink()
            or symlinked_parent
            or root not in resolved.parents
            or resolved.parent.name != run_id
            or resolved.name != f"{role}.db"
        ):
            raise RunAcceptanceCleanupError(f"CLEANUP_BACKUP_OWNERSHIP_UNPROVEN:{role}")
        expected_live = Path(live_paths[role]).resolve()
        expected_source = Path((source_paths or live_paths)[role]).resolve()
        source = record.get("source")
        if source and Path(str(source)).resolve() != expected_source:
            raise RunAcceptanceCleanupError(f"CLEANUP_LIVE_SOURCE_MISMATCH:{role}")
        validated[role] = dict(record) | {
            "path": resolved,
            "live_path": expected_live,
        }
        owned_directories.add(resolved.parent)
    if len(owned_directories) != 1:
        raise RunAcceptanceCleanupError("CLEANUP_BACKUP_OWNERSHIP_UNPROVEN:mixed_directories")
    return validated


def _drain_check(condition: bool, reason: str) -> None:
    if not condition:
        raise RunAcceptanceCleanupError("PUBLICATION_DRAIN_" + reason)


def _drain_verification(record: Mapping[str, Any]) -> None:
    _drain_check(isinstance(record, Mapping)
                 and record.get("quick_check") == "ok"
                 and type(record.get("foreign_key_errors")) is int
                 and record["foreign_key_errors"] == 0
                 and type(record.get("size")) is int and record["size"] > 0
                 and re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))) is not None,
                 "VERIFICATION_INVALID")


def _publication_drain_result(result, *, run_id, journal_path, backup_root, live_paths):
    """Read-only adapter; the existing acceptance function owns all deletion."""
    _drain_check(("mode" not in result or result["mode"] == "PRODUCTION_APPLY")
                 and ("outcome" not in result or result["outcome"] == "COMPLETED"), "RESULT_DISAGREEMENT")
    _drain_check(result.get("run_id") == run_id and result.get("apply") is True
                 and result.get("status") == "SUCCESS" and result.get("journal_state") == "COMPLETED"
                 and result.get("rollback") == {"status": "NOT_REQUIRED"}, "TERMINAL_EVIDENCE_INVALID")
    journal = load_journal(journal_path)
    _drain_check(isinstance(journal, dict), "JOURNAL_MISSING")
    _drain_check(journal.get("operation_type") == "RESULT_PUBLICATION_BACKLOG_DRAIN"
                 and journal.get("production_run_id") == run_id
                 and journal.get("publication_mode") == "GENERATION_POINTER", "JOURNAL_RUN_MISMATCH")
    _drain_check(all(journal.get(k) == v for k,v in {
        "state":"COMPLETED", "current_publication_step":"COMPLETED", "postflight_state":"PASSED",
        "generation_activation_state":"ACTIVATED_AND_VERIFIED", "rollback_recovery_state":"NOT_REQUIRED",
    }.items()), "JOURNAL_NOT_TERMINAL")
    # An embedded or archived alternative is never silently preferred over the canonical journal.
    _drain_check("journal" not in result or result["journal"] == journal, "JOURNAL_DISAGREEMENT")
    _drain_check(result.get("activated_generation") == journal.get("new_generation_id") == run_id,
                 "GENERATION_MISMATCH")
    reviewed = result.get("reviewed_plan")
    scope = result.get("scope_evidence")
    _drain_check(isinstance(reviewed, dict) and reviewed.get("scope_mode") == "REVIEWED_APPLY_PLAN"
                 and isinstance(scope, dict) and scope == journal.get("scope_evidence")
                 and all(scope.get(k) == v for k,v in reviewed.items())
                 and re.fullmatch(r"[0-9a-f]{64}",str(reviewed.get("plan_fingerprint", ""))) is not None,
                 "REVIEWED_SCOPE_MISMATCH")
    publication = result.get("publication", {})
    count = reviewed.get("prepared_key_count")
    selected = scope.get("selected_natural_keys")
    _drain_check(type(count) is int and count > 0 and isinstance(selected,list)
                 and len(selected) == count and len({tuple(k) for k in selected}) == count
                 and publication.get("status") == "SUCCESS"
                 and all(publication.get(k) == count for k in ("total_processed","new_verified","applied_count"))
                 and publication.get("unprocessed_selected") == 0
                 and publication.get("skipped_error_natural_keys") == []
                 and publication.get("applied_natural_keys") == scope.get("applied_natural_keys") == selected
                 and scope.get("selected_count") == scope.get("applied_count") == count
                 and hashlib.sha256(json.dumps(selected,separators=(",", ":"),ensure_ascii=True).encode()).hexdigest()
                     == reviewed.get("prepared_keys_fingerprint"), "PUBLICATION_SCOPE_MISMATCH")
    old = journal.get("old_generation", {})
    _drain_check(old.get("generation_id") == result.get("source_generation")
                 and old.get("layout") == "GENERATION_DIRECTORY", "OLD_GENERATION_MISMATCH")
    active_path = Path(journal["active_generation_manifest_path"])
    active = _load_json(active_path)
    new_dir = Path(journal["new_generation_dir"])
    old_dir = Path(old["generation_dir"])
    generation_root = active_path.parent / "fundamentals_generations"
    _drain_check(new_dir == generation_root / run_id and not new_dir.is_symlink()
                 and old_dir.parent == generation_root and old_dir.name == old["generation_id"]
                 and not old_dir.is_symlink() and new_dir != old_dir, "GENERATION_PATH_INVALID")
    published = _load_json(new_dir / "generation_manifest.json")
    original = _load_json(old_dir / "generation_manifest.json")
    _drain_check(active == published == journal.get("new_generation_manifest")
                 and published.get("generation_id") == run_id
                 and original == old.get("manifest") and original.get("generation_id") == old["generation_id"],
                 "GENERATION_MANIFEST_MISMATCH")
    for item in (published.get("roles"), original.get("roles"), old.get("roles"),
                 result.get("backups"), result.get("source_verification"), result.get("postflight"), journal.get("roles")):
        _drain_check(isinstance(item, dict) and set(item) == KNOWN_ROLES, "ROLE_SET_INVALID")
    expected_dir = backup_root.resolve() / run_id
    _drain_check(not expected_dir.is_symlink() and expected_dir.is_dir()
                 and {p.name for p in expected_dir.iterdir()} == {role+".db" for role in KNOWN_ROLES},
                 "BACKUP_INVENTORY_INVALID")
    sources = _generation_publication_sources(dict(result, journal=journal), run_id=run_id)
    manifest = _validated_manifest(result, run_id=run_id, backup_root=backup_root,
                                   live_paths=live_paths, source_paths=sources)
    for role in sorted(KNOWN_ROLES):
        backup = result["backups"][role]; verification = backup["verification"]
        source = result["source_verification"][role]; post = result["postflight"][role]; jr = journal["roles"][role]
        for record in (verification, source, post):
            _drain_verification(record)
        old_name, new_name = original["roles"][role], published["roles"][role]
        _drain_check(isinstance(old_name,str) and Path(old_name).name == old_name
                     and isinstance(new_name,str) and Path(new_name).name == new_name, "ROLE_PATH_INVALID")
        old_path, new_path = old_dir / old_name, new_dir / new_name
        expected_backup = expected_dir / (role+".db")
        _drain_check(sources[role] == old_path.resolve() and backup.get("source") == str(old_path)
                     and Path(live_paths[role]).resolve() == new_path.resolve()
                     and backup.get("backup") == jr.get("backup_path") == str(expected_backup)
                     and jr.get("production_path") == str(new_path), "ROLE_LINEAGE_MISMATCH")
        _drain_check(verification["sha256"] == source["sha256"] == backup.get("source_sha256")
                     == jr.get("old_production_fingerprint") == jr.get("verified_backup_fingerprint")
                     and verification["size"] == source["size"]
                     and post["sha256"] == jr.get("candidate_fingerprint")
                     and jr.get("candidate_replacement_verified") is True
                     and jr.get("replacement_state") == "GENERATION_ACTIVATED_AND_VERIFIED",
                     "ROLE_EVIDENCE_MISMATCH")
        for generation,record in ((original,source),(published,post)):
            proof=generation["role_verification"][role]
            _drain_check(proof.get("sha256") == record["sha256"] and proof.get("size_bytes") == record["size"]
                         and proof.get("quick_check") == "ok", "MANIFEST_ROLE_MISMATCH")
        path=manifest[role]["path"]
        _drain_check(path.stat().st_size == verification["size"]
                     and sha256_file(path) == verification["sha256"], "BACKUP_HASH_OR_SIZE_MISMATCH")
        _integrity(path)
        _integrity(new_path)
        _drain_check(sha256_file(new_path) == post["sha256"] and new_path.stat().st_size == post["size"],
                     "PUBLISHED_ROLE_CHANGED")
    _drain_check(load_journal(journal_path) == journal and _load_json(active_path) == active,
                 "JOURNAL_OR_ACTIVE_MANIFEST_CHANGED")
    # In-memory view only. Neither the historical result nor its journal is rewritten.
    return dict(result, mode="PRODUCTION_APPLY", outcome="COMPLETED", journal=journal,
                acceptance_run_kind="PUBLICATION_DRAIN")


def _acceptance_result(result, *, directory, run_id, journal_path, backup_root, live_paths):
    if result.get("operation") == "RESULT_PUBLICATION_BACKLOG_DRAIN":
        return _publication_drain_result(result, run_id=run_id, journal_path=journal_path,
                                         backup_root=backup_root, live_paths=live_paths)
    if directory.parent.name == "publication_drains":
        raise RunAcceptanceCleanupError("CLEANUP_RUN_KIND_UNKNOWN")
    return dict(result, acceptance_run_kind="ADMIN_PRODUCTION_APPLY")


def inspect_cleanup_eligibility(
    run_id: str,
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    backup_root: Path = BACKUP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH,
    live_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Inspect one explicit run; publication drains additionally verify exact bytes/integrity."""
    live_paths = live_paths or BatchAddTickerPaths().as_dict()
    try:
        directory = _run_dir(run_id, run_root)
        prior = _successful_cleanup(directory, run_id)
        if prior is not None:
            return {
                "run_id": run_id,
                "status": "ALREADY_CLEANED",
                "eligible": False,
                "reason": "Accepted / backups cleaned",
                "backup_count": len(prior.get("files_deleted") or []),
                "bytes_freed": int(prior.get("bytes_freed") or 0),
            }
        result = _acceptance_result(_load_json(directory / "result.json"), directory=directory,
                                    run_id=run_id, journal_path=journal_path,
                                    backup_root=backup_root, live_paths=live_paths)
        if result.get("run_id") != run_id:
            raise RunAcceptanceCleanupError("CLEANUP_RUN_RESULT_MISMATCH")
        if result.get("mode") != "PRODUCTION_APPLY":
            raise RunAcceptanceCleanupError("Run is not a Production update")
        if result.get("outcome") != "COMPLETED":
            raise RunAcceptanceCleanupError("Run is not terminal COMPLETED")
        rollback = result.get("rollback")
        if not isinstance(rollback, Mapping) or rollback.get("status") != "NOT_REQUIRED":
            raise RunAcceptanceCleanupError("Rollback was required")
        if not _publication_complete(result):
            raise RunAcceptanceCleanupError("Publication or postflight evidence is incomplete")
        source_paths = _generation_publication_sources(result, run_id=run_id)
        manifest = _validated_manifest(
            result,
            run_id=run_id,
            backup_root=backup_root,
            live_paths=live_paths,
            source_paths=source_paths,
        )
        missing = [role for role, record in manifest.items() if not record["path"].is_file()]
        if missing:
            raise RunAcceptanceCleanupError("Backup verification failed: missing " + ", ".join(missing))
        state, journal_error = _journal_state(journal_path)
        if journal_error:
            raise RunAcceptanceCleanupError(journal_error)
        sizes = [record["path"].stat().st_size for record in manifest.values()]
        return {
            "run_id": run_id,
            "status": "ELIGIBLE",
            "run_kind": result["acceptance_run_kind"],
            "eligible": True,
            "reason": "Eligible for explicit operator acceptance",
            "backup_count": len(manifest),
            "bytes_freed": sum(sizes),
            "backup_files": [str(record["path"]) for record in manifest.values()],
            "journal_state": state,
        }
    except (OSError, KeyError, TypeError, AttributeError, ValueError, PublicationRecoveryError, RunAcceptanceCleanupError) as exc:
        return {
            "run_id": run_id,
            "status": "NOT_ELIGIBLE",
            "eligible": False,
            "reason": _operator_reason(exc),
            "backup_count": 0,
            "bytes_freed": 0,
        }


def _integrity(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RunAcceptanceCleanupError(f"CLEANUP_LIVE_DATABASE_INVALID:{path}")
    before = path.stat()
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    except sqlite3.Error as exc:
        raise RunAcceptanceCleanupError(f"CLEANUP_LIVE_DATABASE_INVALID:{path}") from exc
    if quick_check != "ok" or foreign_key_errors:
        raise RunAcceptanceCleanupError(f"CLEANUP_LIVE_DATABASE_INTEGRITY_FAILED:{path}")
    return {
        "path": str(path.resolve()),
        "size": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "quick_check": quick_check,
        "foreign_key_errors": foreign_key_errors,
    }


def _accept_run_and_cleanup_backups_locked(
    run_id: str,
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    backup_root: Path = BACKUP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH,
    live_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Verify and delete only one accepted Production run's rollback backups."""
    live_paths = live_paths or BatchAddTickerPaths().as_dict()
    directory = _run_dir(run_id, run_root)
    prior = _successful_cleanup(directory, run_id)
    if prior is not None:
        return dict(prior) | {"status": "ALREADY_CLEANED"}

    eligibility = inspect_cleanup_eligibility(
        run_id,
        run_root=run_root,
        backup_root=backup_root,
        journal_path=journal_path,
        live_paths=live_paths,
    )
    if not eligibility.get("eligible"):
        raise RunAcceptanceCleanupError(str(eligibility.get("reason") or "CLEANUP_NOT_ELIGIBLE"))
    result = _acceptance_result(_load_json(directory / "result.json"), directory=directory,
                                run_id=run_id, journal_path=journal_path,
                                backup_root=backup_root, live_paths=live_paths)
    source_paths = _generation_publication_sources(result, run_id=run_id)
    manifest = _validated_manifest(
        result,
        run_id=run_id,
        backup_root=backup_root,
        live_paths=live_paths,
        source_paths=source_paths,
    )
    state, journal_error = _journal_state(journal_path)
    if journal_error:
        raise RunAcceptanceCleanupError(journal_error)

    verified: dict[str, Any] = {}
    live_before: dict[str, Any] = {}
    for role, record in manifest.items():
        path = record["path"]
        if not path.is_file() or path.is_symlink():
            raise RunAcceptanceCleanupError(f"CLEANUP_BACKUP_MISSING:{role}")
        actual_hash = sha256_file(path)
        if actual_hash != record["sha256"]:
            raise RunAcceptanceCleanupError(f"CLEANUP_BACKUP_HASH_MISMATCH:{role}")
        backup_integrity = _integrity(path)
        live_integrity = _integrity(record["live_path"])
        verified[role] = {
            "path": str(path),
            "recorded_sha256": record["sha256"],
            "verified_sha256": actual_hash,
            "size": path.stat().st_size,
            "quick_check": backup_integrity["quick_check"],
            "foreign_key_errors": backup_integrity["foreign_key_errors"],
        }
        live_before[role] = live_integrity

    # Re-read terminal evidence and journal immediately before crossing the delete boundary.
    current = _acceptance_result(_load_json(directory / "result.json"), directory=directory,
                                 run_id=run_id, journal_path=journal_path,
                                 backup_root=backup_root, live_paths=live_paths)
    if current != result:
        raise RunAcceptanceCleanupError("CLEANUP_RUN_RESULT_CHANGED")
    state, journal_error = _journal_state(journal_path)
    if journal_error:
        raise RunAcceptanceCleanupError(journal_error)

    deleted: list[str] = []
    bytes_freed = 0
    for role in sorted(manifest):
        path = manifest[role]["path"]
        bytes_freed += path.stat().st_size
        path.unlink()
        deleted.append(str(path))
    backup_directory = next(iter(manifest.values()))["path"].parent
    if not any(backup_directory.iterdir()):
        backup_directory.rmdir()

    live_after = {role: _integrity(record["live_path"]) for role, record in manifest.items()}
    if live_after != live_before:
        raise RunAcceptanceCleanupError("CLEANUP_LIVE_DATABASE_CHANGED")
    evidence = {
        "source_production_run_id": run_id,
        "cleanup_timestamp_utc": utc_now(),
        "operator_action_type": "ACCEPT_RUN_AND_CLEANUP_BACKUPS",
        "status": "COMPLETED",
        "cleanup_outcome": "COMPLETED",
        "files_deleted": deleted,
        "recorded_backup_hashes": {role: item["recorded_sha256"] for role, item in verified.items()},
        "hashes_verified_before_deletion": True,
        "backup_verification": verified,
        "bytes_freed": bytes_freed,
        "live_db_integrity": live_after,
        "live_databases_unchanged": True,
        "publication_journal_state": state,
        "backup_directory_removed": not backup_directory.exists(),
    }
    write_text_atomic(
        directory / CLEANUP_EVIDENCE_NAME,
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    return evidence


def accept_run_and_cleanup_backups(
    run_id: str,
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    backup_root: Path = BACKUP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH,
    live_paths: Mapping[str, Path] | None = None,
    lock_factory: Callable[[], AbstractContextManager[Any]] | None = None,
) -> dict[str, Any]:
    """Serialize accepted-backup cleanup with all Production-writing workflows."""
    factory = lock_factory or production_lock
    with factory():
        return _accept_run_and_cleanup_backups_locked(
            run_id,
            run_root=run_root,
            backup_root=backup_root,
            journal_path=journal_path,
            live_paths=live_paths,
        )
