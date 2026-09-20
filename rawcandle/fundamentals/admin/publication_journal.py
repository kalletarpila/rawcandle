"""Durable journal and restore-old recovery for multi-database publication."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.contracts import utc_now
from rawcandle.fundamentals.phase12d import ROOT


JOURNAL_FORMAT_VERSION = 1
ACTIVE_JOURNAL_PATH = ROOT / "data/.fundamentals_admin_publication_journal.json"
PUBLICATION_ROLES = ("provider", "canonical", "analysis")
TERMINAL_STATES = {"COMPLETED", "ROLLED_BACK", "RECOVERED", "RECOVERY_FAILED"}
INCOMPLETE_STATES = {
    "PREPARED", "PUBLISHING", "POSTFLIGHT", "ROLLING_BACK", "RECOVERING",
}


class PublicationRecoveryError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sqlite_verification(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise PublicationRecoveryError(f"PUBLICATION_DATABASE_PATH_INVALID:{path}")
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
    if quick != "ok" or foreign:
        raise PublicationRecoveryError(f"PUBLICATION_DATABASE_VALIDATION_FAILED:{path}")
    return {
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
        "quick_check": quick,
        "foreign_key_errors": len(foreign),
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    data = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def load_journal(path: Path = ACTIVE_JOURNAL_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise PublicationRecoveryError("PUBLICATION_JOURNAL_PATH_INVALID")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationRecoveryError("PUBLICATION_JOURNAL_UNREADABLE") from exc
    if not isinstance(payload, dict) or payload.get("journal_format_version") != JOURNAL_FORMAT_VERSION:
        raise PublicationRecoveryError("PUBLICATION_JOURNAL_FORMAT_INVALID")
    if payload.get("state") not in TERMINAL_STATES | INCOMPLETE_STATES:
        raise PublicationRecoveryError("PUBLICATION_JOURNAL_STATE_INVALID")
    return payload


def write_journal(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(payload)
    record["updated_at_utc"] = utc_now()
    _atomic_json(path, record)
    return record


def update_journal(path: Path, journal: Mapping[str, Any], **changes: Any) -> dict[str, Any]:
    updated = dict(journal)
    updated.update(changes)
    return write_journal(path, updated)


def prepare_journal(
    *,
    path: Path,
    operation_type: str,
    run_id: str,
    preview_run_id: str,
    test_run_id: str,
    refresh_set_fingerprint: str,
    old_source_watermark: str | None,
    new_source_watermark: str,
    source_schema_fingerprint: str,
    roles: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    prior = load_journal(path)
    if prior and prior["state"] in INCOMPLETE_STATES:
        raise PublicationRecoveryError("INCOMPLETE_PUBLICATION_RECOVERY_REQUIRED")
    if set(roles) != set(PUBLICATION_ROLES):
        raise ValueError("PUBLICATION_JOURNAL_ROLE_SET_INVALID")
    created = utc_now()
    payload = {
        "journal_format_version": JOURNAL_FORMAT_VERSION,
        "operation_type": operation_type,
        "production_run_id": run_id,
        "preview_run_id": preview_run_id,
        "test_run_id": test_run_id,
        "refresh_set_fingerprint": refresh_set_fingerprint,
        "old_source_watermark": old_source_watermark,
        "new_source_watermark": new_source_watermark,
        "source_schema_fingerprint": source_schema_fingerprint,
        "state": "PREPARED",
        "created_at_utc": created,
        "updated_at_utc": created,
        "current_publication_step": "NONE",
        "postflight_state": "NOT_STARTED",
        "rollback_recovery_state": "NOT_REQUIRED",
        "roles": {role: dict(roles[role]) for role in PUBLICATION_ROLES},
    }
    return write_journal(path, payload)


def is_incomplete(journal: Mapping[str, Any] | None) -> bool:
    return bool(journal and journal.get("state") in INCOMPLETE_STATES)


def safety_status(path: Path = ACTIVE_JOURNAL_PATH) -> dict[str, Any]:
    try:
        journal = load_journal(path)
    except PublicationRecoveryError as exc:
        return {"status": "RECOVERY_FAILED", "production_writes_blocked": True, "error": str(exc)}
    if journal is None:
        return {"status": "CLEAR", "production_writes_blocked": False}
    state = str(journal["state"])
    return {
        "status": state,
        "production_writes_blocked": state in INCOMPLETE_STATES | {"RECOVERY_FAILED"},
        "run_id": journal.get("production_run_id"),
    }


def _validate_backup(role: str, record: Mapping[str, Any]) -> tuple[Path, str]:
    backup = Path(str(record.get("backup_path") or ""))
    expected = str(record.get("verified_backup_fingerprint") or "")
    if not expected:
        raise PublicationRecoveryError(f"RECOVERY_BACKUP_FINGERPRINT_MISSING:{role}")
    actual = sqlite_verification(backup)
    if actual["sha256"] != expected:
        raise PublicationRecoveryError(f"RECOVERY_BACKUP_FINGERPRINT_MISMATCH:{role}")
    return backup, expected


def restore_old_generation(
    journal: Mapping[str, Any], *, journal_path: Path = ACTIVE_JOURNAL_PATH,
    role_order: Sequence[str] = PUBLICATION_ROLES,
) -> dict[str, Any]:
    if set(role_order) != set(PUBLICATION_ROLES):
        raise ValueError("RECOVERY_ROLE_ORDER_INVALID")
    current = update_journal(
        journal_path, journal, state="RECOVERING",
        rollback_recovery_state="RESTORING_OLD_GENERATION",
    )
    restored: dict[str, Any] = {}
    try:
        validated = {
            role: _validate_backup(role, current["roles"][role])
            for role in role_order
        }
        for role in role_order:
            record = current["roles"][role]
            current = update_journal(
                journal_path, current,
                current_publication_step=f"RESTORING_{role.upper()}",
                rollback_recovery_state="RESTORING_OLD_GENERATION",
            )
            target = Path(str(record["production_path"]))
            backup, expected = validated[role]
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = target.parent / f".{target.name}.{current['production_run_id']}.recovery"
            stage.unlink(missing_ok=True)
            shutil.copy2(backup, stage)
            fsync_file(stage)
            if sha256_file(stage) != expected:
                raise PublicationRecoveryError(f"RECOVERY_STAGE_FINGERPRINT_MISMATCH:{role}")
            os.replace(stage, target)
            fsync_file(target)
            fsync_directory(target.parent)
            verification = sqlite_verification(target)
            if verification["sha256"] != expected:
                raise PublicationRecoveryError(f"RECOVERY_PRODUCTION_FINGERPRINT_MISMATCH:{role}")
            restored[role] = verification
            role_record = dict(record)
            role_record["replacement_state"] = "OLD_GENERATION_RESTORED"
            roles = dict(current["roles"])
            roles[role] = role_record
            current = update_journal(
                journal_path, current, roles=roles,
                current_publication_step=f"RESTORED_{role.upper()}",
            )
        current = update_journal(
            journal_path, current, state="RECOVERED",
            rollback_recovery_state="OLD_GENERATION_RESTORED_AND_VERIFIED",
            postflight_state="OLD_GENERATION_VERIFIED",
        )
        return {"status": "RECOVERED", "roles": restored, "journal": current}
    except Exception as exc:
        failed = update_journal(
            journal_path, current, state="RECOVERY_FAILED",
            rollback_recovery_state="RECOVERY_FAILED",
            recovery_error=f"{type(exc).__name__}: {exc}",
        )
        raise PublicationRecoveryError("CRITICAL_RECOVERY_FAILED") from exc


def recover_if_required(path: Path = ACTIVE_JOURNAL_PATH) -> dict[str, Any]:
    journal = load_journal(path)
    if journal is None:
        return {"status": "NO_JOURNAL", "recovered": False}
    if journal["state"] == "RECOVERY_FAILED":
        raise PublicationRecoveryError("FUNDAMENTALS_PRODUCTION_WRITES_BLOCKED_RECOVERY_FAILED")
    if journal["state"] not in INCOMPLETE_STATES:
        return {"status": journal["state"], "recovered": False}
    result = restore_old_generation(journal, journal_path=path)
    return {"status": result["status"], "recovered": True, "roles": result["roles"]}


def guard_production_writes(path: Path = ACTIVE_JOURNAL_PATH) -> dict[str, Any]:
    """Recover an incomplete generation, then require a fresh production invocation."""
    result = recover_if_required(path)
    if result.get("recovered"):
        raise PublicationRecoveryError("INCOMPLETE_PUBLICATION_RECOVERED_RETRY_REQUIRED")
    return result
