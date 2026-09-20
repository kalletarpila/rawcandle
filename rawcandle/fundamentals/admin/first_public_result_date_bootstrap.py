"""One-time first-public-result-date bootstrap for the canonical V4 database."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.production_transaction import BACKUP_ROOT, production_lock
from rawcandle.fundamentals.admin.publication_journal import (
    ACTIVE_JOURNAL_PATH,
    fsync_directory,
    fsync_file,
    guard_production_writes,
    sha256_file,
    sqlite_verification,
)
from rawcandle.fundamentals.phase12d import REPORT_ROOT, ROOT
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.io_atomic import write_text_atomic


CONTRACT_VERSION = "PHASE13G3_6_FIRST_PUBLIC_RESULT_DATE_BOOTSTRAP_V1"
RUN_ROOT = REPORT_ROOT / "maintenance_runs/first_public_result_date_bootstrap"
TEMP_ROOT = ROOT / "temp/first_public_result_date_bootstrap"
BOOTSTRAP_BACKUP_ROOT = BACKUP_ROOT / "first_public_result_date_bootstrap"
REQUIRED_QUARTER_COLUMNS = {
    "quarter_id", "company_id", "fiscal_year", "fiscal_quarter",
    "source_availability_date", "first_public_result_date",
}


class StaleBootstrapPreview(RuntimeError):
    pass


class BootstrapValidationError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_id(mode: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}_first_public_result_date_bootstrap_{mode.lower()}"


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _hash_rows(rows: Any) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(tuple(row), separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    return _hash_rows(connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ))


def _identity_fingerprint(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for query in (
        "SELECT * FROM company ORDER BY company_id",
        "SELECT * FROM security ORDER BY security_id",
        "SELECT quarter_id,company_id,fiscal_year,fiscal_quarter FROM v4_quarter "
        "ORDER BY company_id,fiscal_year,fiscal_quarter,quarter_id",
    ):
        digest.update(_hash_rows(connection.execute(query)).encode("ascii"))
    return digest.hexdigest()


def _date_state_fingerprint(connection: sqlite3.Connection) -> str:
    return _hash_rows(connection.execute(
        "SELECT company_id,fiscal_year,fiscal_quarter,source_availability_date,"
        "first_public_result_date FROM v4_quarter "
        "ORDER BY company_id,fiscal_year,fiscal_quarter"
    ))


def _source_availability_fingerprint(connection: sqlite3.Connection) -> str:
    return _hash_rows(connection.execute(
        "SELECT company_id,fiscal_year,fiscal_quarter,source_availability_date "
        "FROM v4_quarter ORDER BY company_id,fiscal_year,fiscal_quarter"
    ))


def _established_first_public_values(path: Path) -> dict[tuple[int, int, str], str]:
    with _readonly(path) as connection:
        return {
            (int(row[0]), int(row[1]), str(row[2])): str(row[3])
            for row in connection.execute(
                "SELECT company_id,fiscal_year,fiscal_quarter,first_public_result_date "
                "FROM v4_quarter WHERE first_public_result_date IS NOT NULL"
            )
        }


def _non_target_fingerprint(connection: sqlite3.Connection) -> str:
    """Fingerprint all canonical state except the intended target column."""
    digest = hashlib.sha256()
    tables = [str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    for table in tables:
        columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]
        if table == "v4_quarter":
            columns = [name for name in columns if name != "first_public_result_date"]
        quoted = ",".join(f'"{name}"' for name in columns)
        digest.update(table.encode("utf-8"))
        digest.update(_hash_rows(connection.execute(
            f'SELECT {quoted} FROM "{table}" ORDER BY rowid'
        )).encode("ascii"))
    return digest.hexdigest()


def _valid_iso(value: Any) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _file_state(path: Path, *, content_hash: bool) -> dict[str, Any]:
    stat = path.stat()
    result = {
        "path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
    }
    if content_hash:
        result["sha256"] = sha256_file(path)
    return result


def production_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    return {
        role: _file_state(path, content_hash=role in {"provider", "canonical", "analysis"})
        for role, path in paths.as_dict().items()
    }


def _refresh_state(path: Path) -> dict[str, Any]:
    with _readonly(path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='sharadar_refresh_state'"
        ).fetchone() is not None
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM sharadar_refresh_state ORDER BY singleton_id"
        )] if exists else []
    return {"table_exists": exists, "rows": rows}


def audit_canonical(path: Path, *, include_non_target_fingerprint: bool = True) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise BootstrapValidationError(f"CANONICAL_PATH_INVALID:{path}")
    state = _file_state(path, content_hash=True)
    blockers: list[str] = []
    with _readonly(path) as connection:
        tables = {str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        )}
        if "v4_quarter" not in tables:
            raise BootstrapValidationError("CANONICAL_SCHEMA_MISSING_V4_QUARTER")
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(v4_quarter)")}
        missing = sorted(REQUIRED_QUARTER_COLUMNS - columns)
        if missing:
            raise BootstrapValidationError(f"CANONICAL_SCHEMA_MISSING_COLUMNS:{','.join(missing)}")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        if quick != "ok":
            blockers.append("SQLITE_QUICK_CHECK_FAILED")
        if foreign:
            blockers.append("FOREIGN_KEY_INTEGRITY_FAILED")
        counts = dict(connection.execute(
            "SELECT COUNT(*) total_rows,"
            "SUM(first_public_result_date IS NULL) null_first_public,"
            "SUM(first_public_result_date IS NOT NULL) established_first_public,"
            "SUM(first_public_result_date IS NULL AND source_availability_date IS NOT NULL) eligible,"
            "SUM(first_public_result_date IS NULL AND source_availability_date IS NULL) unresolved,"
            "SUM(first_public_result_date IS NOT NULL AND source_availability_date IS NOT NULL "
            "AND first_public_result_date<>source_availability_date) established_source_differences "
            "FROM v4_quarter"
        ).fetchone())
        counts = {key: int(value or 0) for key, value in counts.items()}
        duplicates = [dict(row) for row in connection.execute(
            "SELECT company_id,fiscal_year,fiscal_quarter,COUNT(*) row_count FROM v4_quarter "
            "GROUP BY company_id,fiscal_year,fiscal_quarter HAVING COUNT(*)<>1 LIMIT 25"
        )]
        null_identity = int(connection.execute(
            "SELECT COUNT(*) FROM v4_quarter WHERE company_id IS NULL OR fiscal_year IS NULL "
            "OR fiscal_quarter IS NULL"
        ).fetchone()[0])
        date_rows = connection.execute(
            "SELECT quarter_id,source_availability_date,first_public_result_date FROM v4_quarter "
            "WHERE source_availability_date IS NOT NULL OR first_public_result_date IS NOT NULL"
        )
        malformed = []
        for row in date_rows:
            for field in ("source_availability_date", "first_public_result_date"):
                value = row[field]
                if value is not None and not _valid_iso(value):
                    malformed.append({"quarter_id": int(row["quarter_id"]), "field": field, "value": value})
                    if len(malformed) >= 25:
                        break
            if len(malformed) >= 25:
                break
        if duplicates:
            blockers.append("DUPLICATE_STABLE_QUARTER_IDENTITY")
        if null_identity:
            blockers.append("NULL_STABLE_QUARTER_IDENTITY")
        if malformed:
            blockers.append("MALFORMED_PUBLICATION_DATE")
        if counts["unresolved"]:
            blockers.append("NULL_SOURCE_AVAILABILITY_DATE")
        partial = counts["eligible"] > 0 and counts["established_first_public"] > 0
        if blockers:
            outcome = "BLOCKED"
        elif partial:
            outcome = "REVIEW_REQUIRED"
        elif counts["eligible"] == 0:
            outcome = "ALREADY_BOOTSTRAPPED"
        else:
            outcome = "READY"
        result = {
            "contract_version": CONTRACT_VERSION,
            "outcome": outcome,
            "canonical": state,
            "schema_fingerprint": _schema_fingerprint(connection),
            "counts": counts,
            "expected_post_bootstrap_non_null": counts["established_first_public"] + counts["eligible"],
            "expected_remaining_null": counts["unresolved"],
            "duplicate_stable_identities": duplicates,
            "null_identity_components": null_identity,
            "malformed_dates": malformed,
            "blockers": blockers,
            "partial_bootstrap": partial,
            "quick_check": quick,
            "foreign_key_errors": foreign,
            "identity_fingerprint": _identity_fingerprint(connection),
            "date_state_fingerprint": _date_state_fingerprint(connection),
            "source_availability_fingerprint": _source_availability_fingerprint(connection),
        }
        if include_non_target_fingerprint:
            result["non_target_canonical_fingerprint"] = _non_target_fingerprint(connection)
    return result


def _binding(audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical": dict(audit["canonical"]),
        "schema_fingerprint": audit["schema_fingerprint"],
        "row_count": audit["counts"]["total_rows"],
        "eligible_count": audit["counts"]["eligible"],
        "date_state_fingerprint": audit["date_state_fingerprint"],
        "identity_fingerprint": audit["identity_fingerprint"],
    }


def _assert_binding(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    if dict(expected) != _binding(actual):
        raise StaleBootstrapPreview("FIRST_PUBLIC_BOOTSTRAP_STALE_PREVIEW")


def _assert_semantic_binding(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    comparable = {
        key: expected[key]
        for key in (
            "schema_fingerprint", "row_count", "eligible_count",
            "date_state_fingerprint", "identity_fingerprint",
        )
    }
    candidate = _binding(actual)
    if any(candidate[key] != value for key, value in comparable.items()):
        raise StaleBootstrapPreview("FIRST_PUBLIC_BOOTSTRAP_COPY_BINDING_MISMATCH")


def _load_evidence(path: Path, expected_mode: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BootstrapValidationError("BOOTSTRAP_EVIDENCE_PATH_INVALID")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract_version") != CONTRACT_VERSION or payload.get("mode") != expected_mode:
        raise BootstrapValidationError("BOOTSTRAP_EVIDENCE_CONTRACT_MISMATCH")
    return payload


def _render_report(result: Mapping[str, Any]) -> str:
    audit = result.get("audit") or result.get("before_audit") or result.get("after_audit") or {}
    counts = audit.get("counts") or {}
    after_counts = (result.get("after_audit") or {}).get("counts") or {}
    validation = result.get("validation") or {}
    lines = [
        "# first_public_result_date Bootstrap",
        "", "## Executive Summary", "",
        f"- mode: {result.get('mode')}",
        f"- outcome: {result.get('outcome')}",
        f"- production changed: {'Yes' if result.get('production_changed') else 'No'}",
        "", "## Canonical State", "",
        f"- total rows: {counts.get('total_rows')}",
        f"- established dates: {counts.get('established_first_public')}",
        f"- eligible: {counts.get('eligible')}",
        f"- unresolved: {counts.get('unresolved')}",
        f"- established dates after Test/Production: {after_counts.get('established_first_public')}",
        f"- updated rows: {result.get('updated_count')}",
        "", "## Validation", "",
        f"- identity unchanged: {validation.get('identity_unchanged')}",
        f"- non-target canonical data unchanged: {validation.get('non_target_unchanged')}",
        f"- source availability unchanged: {validation.get('source_availability_unchanged')}",
        f"- SQLite integrity: {audit.get('quick_check')}",
        "", "## Safety", "",
        f"- production state unchanged: {result.get('production_state_unchanged')}",
        f"- Test copy cleaned: {result.get('test_copy_cleaned')}",
        "", "## Next Step", "",
        "Production bootstrap NOT executed. Operator review and explicit authorization required."
        if result.get("mode") != "PRODUCTION" else "Production bootstrap completed under explicit authorization.",
        "",
    ]
    return "\n".join(lines)


def run_preview(
    *, paths: BatchAddTickerPaths | None = None, run_root: Path = RUN_ROOT,
) -> dict[str, Any]:
    paths = paths or BatchAddTickerPaths()
    started = _utc_now()
    before = production_state(paths)
    refresh_before = _refresh_state(paths.provider_db)
    audit = audit_canonical(paths.canonical_db)
    after = production_state(paths)
    result = {
        "contract_version": CONTRACT_VERSION, "run_id": _run_id("preview"), "mode": "PREVIEW",
        "started_at_utc": started, "completed_at_utc": _utc_now(), "outcome": audit["outcome"],
        "audit": audit, "binding": _binding(audit), "production_state_before": before,
        "production_state_after": after, "production_state_unchanged": before == after,
        "refresh_state_unchanged": refresh_before == _refresh_state(paths.provider_db),
        "publication_journal_created": False, "production_changed": False,
    }
    run_dir = run_root / result["run_id"]
    _atomic_json(run_dir / "bootstrap_result.json", result)
    write_text_atomic(run_dir / "bootstrap_preview_report.md", _render_report(result))
    result["artifact_dir"] = str(run_dir.resolve())
    return result


def _apply_bootstrap(connection: sqlite3.Connection) -> int:
    cursor = connection.execute(
        "UPDATE v4_quarter SET first_public_result_date=source_availability_date "
        "WHERE first_public_result_date IS NULL AND source_availability_date IS NOT NULL"
    )
    return int(cursor.rowcount)


def run_test(
    *, preview_result_path: Path, paths: BatchAddTickerPaths | None = None,
    run_root: Path = RUN_ROOT, temp_root: Path = TEMP_ROOT,
) -> dict[str, Any]:
    paths = paths or BatchAddTickerPaths()
    preview = _load_evidence(preview_result_path, "PREVIEW")
    if preview.get("outcome") not in {"READY", "ALREADY_BOOTSTRAPPED"}:
        raise BootstrapValidationError("BOOTSTRAP_PREVIEW_NOT_AUTHORIZED")
    before_state = production_state(paths)
    refresh_before = _refresh_state(paths.provider_db)
    current = audit_canonical(paths.canonical_db)
    _assert_binding(preview["binding"], current)  # Must happen before creating the copy.
    run_id = _run_id("test")
    run_dir = run_root / run_id
    copy_dir = temp_root / run_id
    copy_path = copy_dir / "canonical_test.db"
    updated = 0
    sample: list[dict[str, Any]] = []
    copy_cleaned = False
    try:
        copy_dir.mkdir(parents=True, exist_ok=False)
        online_backup(paths.canonical_db, copy_path)
        copy_before = audit_canonical(copy_path)
        _assert_semantic_binding(preview["binding"], copy_before)
        established_before = _established_first_public_values(copy_path)
        with sqlite3.connect(copy_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            rows = [dict(row) for row in connection.execute(
                "SELECT company_id,fiscal_year,fiscal_quarter,source_availability_date,"
                "first_public_result_date first_public_before FROM v4_quarter "
                "WHERE first_public_result_date IS NULL AND source_availability_date IS NOT NULL "
                "ORDER BY company_id,fiscal_year,fiscal_quarter LIMIT 5"
            )]
            updated = _apply_bootstrap(connection)
            for row in rows:
                row["first_public_after"] = row["source_availability_date"]
            sample = rows
            connection.commit()
        copy_after = audit_canonical(copy_path)
        established_after = _established_first_public_values(copy_path)
        expected_after = copy_before["counts"]["established_first_public"] + copy_before["counts"]["eligible"]
        validation = {
            "updated_count_matches": updated == copy_before["counts"]["eligible"],
            "row_count_unchanged": copy_before["counts"]["total_rows"] == copy_after["counts"]["total_rows"],
            "identity_unchanged": copy_before["identity_fingerprint"] == copy_after["identity_fingerprint"],
            "non_target_unchanged": copy_before["non_target_canonical_fingerprint"] == copy_after["non_target_canonical_fingerprint"],
            "source_availability_unchanged": copy_before["source_availability_fingerprint"] == copy_after["source_availability_fingerprint"],
            "bootstrapped_values_equal_source": (
                copy_after["counts"]["established_source_differences"]
                == copy_before["counts"]["established_source_differences"]
            ),
            "preexisting_established_values_preserved": all(
                established_after.get(key) == value for key, value in established_before.items()
            ),
            "established_count_expected": copy_after["counts"]["established_first_public"] == expected_after,
            "remaining_null_expected": copy_after["counts"]["null_first_public"] == copy_before["counts"]["unresolved"],
            "sqlite_integrity": copy_after["quick_check"] == "ok" and copy_after["foreign_key_errors"] == 0,
        }
        if not all(validation.values()):
            raise BootstrapValidationError("BOOTSTRAP_TEST_POSTFLIGHT_FAILED")
        result = {
            "contract_version": CONTRACT_VERSION, "run_id": run_id, "mode": "TEST",
            "started_at_utc": _utc_now(), "completed_at_utc": _utc_now(), "outcome": "COMPLETED",
            "preview_run_id": preview["run_id"], "preview_binding": preview["binding"],
            "before_audit": copy_before, "after_audit": copy_after, "updated_count": updated,
            "skipped_already_established": copy_before["counts"]["established_first_public"],
            "unresolved_count": copy_before["counts"]["unresolved"], "sample": sample,
            "validation": validation, "production_state_before": before_state,
            "production_changed": False,
        }
    finally:
        shutil.rmtree(copy_dir, ignore_errors=True)
        copy_cleaned = not copy_dir.exists()
    after_state = production_state(paths)
    result["production_state_after"] = after_state
    result["production_state_unchanged"] = before_state == after_state
    result["refresh_state_unchanged"] = refresh_before == _refresh_state(paths.provider_db)
    result["test_copy_cleaned"] = copy_cleaned
    if not result["production_state_unchanged"] or not result["refresh_state_unchanged"] or not copy_cleaned:
        raise BootstrapValidationError("BOOTSTRAP_TEST_PRODUCTION_ISOLATION_FAILED")
    run_dir.mkdir(parents=True, exist_ok=False)
    _atomic_json(run_dir / "bootstrap_result.json", result)
    write_text_atomic(run_dir / "bootstrap_test_report.md", _render_report(result))
    result["artifact_dir"] = str(run_dir.resolve())
    return result


def _verified_backup(source: Path, backup: Path) -> dict[str, Any]:
    if backup.exists():
        raise BootstrapValidationError("BOOTSTRAP_BACKUP_ALREADY_EXISTS")
    online_backup(source, backup)
    fsync_file(backup)
    fsync_directory(backup.parent)
    verification = sqlite_verification(backup)
    if verification["sha256"] != sha256_file(source):
        # Online SQLite backups need not be byte-identical; verify semantic binding too.
        source_audit = audit_canonical(source)
        backup_audit = audit_canonical(backup)
        _assert_semantic_binding(_binding(source_audit), backup_audit)
        if source_audit["non_target_canonical_fingerprint"] != backup_audit["non_target_canonical_fingerprint"]:
            raise BootstrapValidationError("BOOTSTRAP_BACKUP_NON_TARGET_MISMATCH")
    return {"path": str(backup.resolve()), "verification": verification}


def _restore_backup(backup: Path, target: Path) -> None:
    restore = target.parent / f".{target.name}.bootstrap-restore-{os.getpid()}.db"
    try:
        online_backup(backup, restore)
        sqlite_verification(restore)
        fsync_file(restore)
        os.replace(restore, target)
        fsync_file(target)
        fsync_directory(target.parent)
    finally:
        restore.unlink(missing_ok=True)


def run_production(
    *, preview_result_path: Path, test_result_path: Path, confirm_production: bool,
    paths: BatchAddTickerPaths | None = None, run_root: Path = RUN_ROOT,
    backup_root: Path = BOOTSTRAP_BACKUP_ROOT, journal_path: Path = ACTIVE_JOURNAL_PATH,
    fault_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not confirm_production:
        raise BootstrapValidationError("BOOTSTRAP_PRODUCTION_EXPLICIT_CONFIRMATION_REQUIRED")
    paths = paths or BatchAddTickerPaths()
    preview = _load_evidence(preview_result_path, "PREVIEW")
    test = _load_evidence(test_result_path, "TEST")
    if preview.get("outcome") not in {"READY", "ALREADY_BOOTSTRAPPED"}:
        raise BootstrapValidationError("BOOTSTRAP_PREVIEW_NOT_AUTHORIZED")
    if test.get("outcome") != "COMPLETED" or test.get("preview_run_id") != preview.get("run_id"):
        raise BootstrapValidationError("BOOTSTRAP_MATCHING_SUCCESSFUL_TEST_REQUIRED")
    if test.get("preview_binding") != preview.get("binding") or not all((test.get("validation") or {}).values()):
        raise BootstrapValidationError("BOOTSTRAP_TEST_BINDING_MISMATCH")
    run_id = _run_id("production")
    backup_dir = backup_root / run_id
    backup_path = backup_dir / "canonical.db"
    fault = fault_injector or (lambda _point: None)
    result: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "run_id": run_id, "mode": "PRODUCTION",
        "outcome": "FAILED", "production_changed": False,
    }
    backup: dict[str, Any] | None = None
    committed = False
    with production_lock():
        guard_production_writes(journal_path)
        current = audit_canonical(paths.canonical_db)
        _assert_binding(preview["binding"], current)
        established_before = _established_first_public_values(paths.canonical_db)
        if shutil.disk_usage(backup_root.parent).free < paths.canonical_db.stat().st_size * 2:
            raise BootstrapValidationError("BOOTSTRAP_INSUFFICIENT_STORAGE")
        backup_dir.mkdir(parents=True, exist_ok=False)
        fsync_directory(backup_dir.parent)
        backup = _verified_backup(paths.canonical_db, backup_path)
        fault("BEFORE_TRANSACTION")
        try:
            with sqlite3.connect(paths.canonical_db) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
                fault("AFTER_BEGIN")
                inside = {
                    "total_rows": int(connection.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0]),
                    "eligible": int(connection.execute(
                        "SELECT COUNT(*) FROM v4_quarter WHERE first_public_result_date IS NULL "
                        "AND source_availability_date IS NOT NULL"
                    ).fetchone()[0]),
                    "date_state_fingerprint": _date_state_fingerprint(connection),
                    "identity_fingerprint": _identity_fingerprint(connection),
                }
                expected = preview["binding"]
                if (inside["total_rows"], inside["eligible"], inside["date_state_fingerprint"], inside["identity_fingerprint"]) != (
                    expected["row_count"], expected["eligible_count"], expected["date_state_fingerprint"], expected["identity_fingerprint"]
                ):
                    raise StaleBootstrapPreview("FIRST_PUBLIC_BOOTSTRAP_STALE_INSIDE_TRANSACTION")
                updated = _apply_bootstrap(connection)
                fault("AFTER_UPDATE")
                remaining = int(connection.execute(
                    "SELECT COUNT(*) FROM v4_quarter WHERE first_public_result_date IS NULL"
                ).fetchone()[0])
                if updated != expected["eligible_count"] or remaining != current["counts"]["unresolved"]:
                    raise BootstrapValidationError("BOOTSTRAP_TRANSACTION_VALIDATION_FAILED")
                fault("AFTER_VALIDATION")
                connection.commit()
                committed = True
            fsync_file(paths.canonical_db)
            fsync_directory(paths.canonical_db.parent)
            fault("AFTER_COMMIT")
            after = audit_canonical(paths.canonical_db)
            established_after = _established_first_public_values(paths.canonical_db)
            validation = {
                "identity_unchanged": current["identity_fingerprint"] == after["identity_fingerprint"],
                "non_target_unchanged": current["non_target_canonical_fingerprint"] == after["non_target_canonical_fingerprint"],
                "source_availability_unchanged": current["source_availability_fingerprint"] == after["source_availability_fingerprint"],
                "bootstrapped_values_equal_source": (
                    after["counts"]["established_source_differences"]
                    == current["counts"]["established_source_differences"]
                ),
                "preexisting_established_values_preserved": all(
                    established_after.get(key) == value for key, value in established_before.items()
                ),
                "updated_count_matches": updated == current["counts"]["eligible"],
                "sqlite_integrity": after["quick_check"] == "ok" and after["foreign_key_errors"] == 0,
            }
            fault("POSTFLIGHT")
            if not all(validation.values()):
                raise BootstrapValidationError("BOOTSTRAP_PRODUCTION_POSTFLIGHT_FAILED")
            result.update({
                "outcome": "COMPLETED", "production_changed": updated > 0, "updated_count": updated,
                "after_audit": after, "validation": validation, "backup": backup,
            })
        except BaseException:
            if committed:
                _restore_backup(backup_path, paths.canonical_db)
                restored = audit_canonical(paths.canonical_db)
                _assert_semantic_binding(preview["binding"], restored)
                result["outcome"] = "ROLLED_BACK"
            raise
    run_dir = run_root / run_id
    _atomic_json(run_dir / "bootstrap_result.json", result)
    write_text_atomic(run_dir / "bootstrap_production_report.md", _render_report(result))
    result["artifact_dir"] = str(run_dir.resolve())
    return result
