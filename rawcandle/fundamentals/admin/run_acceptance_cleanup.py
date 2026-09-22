"""Run-specific acceptance and verified rollback-backup cleanup."""

from __future__ import annotations

import json
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
    path = root / run_id
    if path.is_symlink() or not path.is_dir() or path.resolve().parent != root:
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
    return state, None


def _validated_manifest(
    result: Mapping[str, Any],
    *,
    run_id: str,
    backup_root: Path,
    live_paths: Mapping[str, Path],
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
        source = record.get("source")
        if source and Path(str(source)).resolve() != expected_live:
            raise RunAcceptanceCleanupError(f"CLEANUP_LIVE_SOURCE_MISMATCH:{role}")
        validated[role] = dict(record) | {
            "path": resolved,
            "live_path": expected_live,
        }
        owned_directories.add(resolved.parent)
    if len(owned_directories) != 1:
        raise RunAcceptanceCleanupError("CLEANUP_BACKUP_OWNERSHIP_UNPROVEN:mixed_directories")
    return validated


def inspect_cleanup_eligibility(
    run_id: str,
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    backup_root: Path = BACKUP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH,
    live_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Return cheap detail-view eligibility without hashing backup files."""
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
        result = _load_json(directory / "result.json")
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
        manifest = _validated_manifest(
            result, run_id=run_id, backup_root=backup_root, live_paths=live_paths
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
            "eligible": True,
            "reason": "Eligible for explicit operator acceptance",
            "backup_count": len(manifest),
            "bytes_freed": sum(sizes),
            "backup_files": [str(record["path"]) for record in manifest.values()],
            "journal_state": state,
        }
    except (OSError, KeyError, TypeError, AttributeError, RunAcceptanceCleanupError) as exc:
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
    result = _load_json(directory / "result.json")
    manifest = _validated_manifest(
        result, run_id=run_id, backup_root=backup_root, live_paths=live_paths
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
    current = _load_json(directory / "result.json")
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
