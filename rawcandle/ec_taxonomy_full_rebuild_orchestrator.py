from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

from rawcandle.cli.plan_ec_source_layer_backfill import MAX_RANGE_DAYS, plan_ec_source_layer_backfill
from rawcandle.cli.run_ec_source_layer_backfill import run_ec_source_layer_backfill
from rawcandle.datacenter_taxonomy_replacement import (
    CANONICAL_EC_WATERMARK_SCOPES,
    apply_datacenter_taxonomy_rebuild_evidence,
    summarize_taxonomy_csv,
    validate_rebuild_stale_rows,
)
from rawcandle.ec_pipeline_watermark_loader import advance_ec_pipeline_watermarks_after_historical_backfill


REBUILD_MODE = "TAXONOMY_FULL_REBUILD"
PROGRESS_FILENAME = "ec_taxonomy_full_rebuild_progress.json"
SUCCESS_CHUNK_STATUSES = {"BACKFILL_COMPLETED", "BACKFILL_SKIPPED"}
BACKUP_MODE_ORCHESTRATOR_CREATED = "ORCHESTRATOR_CREATED"
BACKUP_MODE_EXISTING = "EXISTING_BACKUP"
CRITICAL_BACKUP_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_taxonomy_change_deployment",
    "ec_pipeline_watermark",
    "ec_ticker_signal_daily",
    "ec_group_signal_daily",
    "ec_group_synthetic_ohlc_daily",
    "ec_group_index_daily",
    "dc_ticker_swing_signal_daily",
    "dc_group_swing_signal_daily",
    "dc_group_synthetic_ohlc_daily",
    "dc_group_index_daily",
)


@dataclass(frozen=True)
class RebuildChunk:
    chunk_index: int
    chunk_start: str
    chunk_end: str
    chunk_span_days: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must parse as YYYY-MM-DD") from exc


def build_ec_taxonomy_rebuild_chunks(
    *,
    date_from: str,
    date_to: str,
    max_range_days: int = MAX_RANGE_DAYS,
) -> list[RebuildChunk]:
    start = _parse_iso_date(date_from, "date_from")
    end = _parse_iso_date(date_to, "date_to")
    if start > end:
        raise ValueError("date_from must be less than or equal to date_to")
    if max_range_days <= 0:
        raise ValueError("max_range_days must be positive")

    chunks: list[RebuildChunk] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=max_range_days - 1), end)
        chunks.append(
            RebuildChunk(
                chunk_index=len(chunks) + 1,
                chunk_start=cursor.isoformat(),
                chunk_end=chunk_end.isoformat(),
                chunk_span_days=(chunk_end - cursor).days + 1,
            )
        )
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _canonical_chunk_payload(chunks: list[RebuildChunk]) -> list[dict[str, object]]:
    return [
        {
            "chunk_index": chunk.chunk_index,
            "chunk_start": chunk.chunk_start,
            "chunk_end": chunk.chunk_end,
            "chunk_span_days": chunk.chunk_span_days,
        }
        for chunk in chunks
    ]


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_readwrite(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def _fetch_deployment(
    conn: sqlite3.Connection,
    *,
    deployment_id: int,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT *
        FROM ec_taxonomy_change_deployment
        WHERE taxonomy_change_id = ?
          AND ecosystem_code = ?
          AND proposed_taxonomy_version = ?
        """,
        (deployment_id, ecosystem_code, taxonomy_version_code),
    ).fetchone()
    return dict(row) if row is not None else None


def _fetch_taxonomy(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT tv.taxonomy_version_id, tv.taxonomy_version_code, tv.source_hash,
               tv.source_reference, tv.status, tv.is_active, e.ecosystem_id
        FROM ec_taxonomy_version tv
        JOIN ec_ecosystem e ON e.ecosystem_id = tv.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    return dict(row) if row is not None else None


def _fetch_active_taxonomy(conn: sqlite3.Connection, *, ecosystem_code: str) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT tv.taxonomy_version_id, tv.taxonomy_version_code, tv.source_hash,
               tv.source_reference, tv.status, tv.is_active
        FROM ec_taxonomy_version tv
        JOIN ec_ecosystem e ON e.ecosystem_id = tv.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.is_active = 1
        ORDER BY tv.taxonomy_version_id DESC
        LIMIT 1
        """,
        (ecosystem_code,),
    ).fetchone()
    return dict(row) if row is not None else None


def _resolve_temp_path(path: str | Path, *, repo_root: str | Path) -> Path:
    resolved = Path(path).resolve()
    temp_root = (Path(repo_root).resolve() / "temp").resolve()
    try:
        resolved.relative_to(temp_root)
    except ValueError as exc:
        raise ValueError(f"path must be under repository temp/: {resolved}") from exc
    return resolved


def _backup_summary_from_path(
    backup_path: Path,
    *,
    backup_mode: str,
    backup_created_by_orchestrator: bool,
    backup_reused: bool,
) -> dict[str, object]:
    stat = backup_path.stat()
    return {
        "backup_mode": backup_mode,
        "backup_path": str(backup_path),
        "backup_created_by_orchestrator": backup_created_by_orchestrator,
        "backup_reused": backup_reused,
        "backup_validation_status": "OK",
        "backup_size": stat.st_size,
        "backup_mtime": _iso_from_timestamp(stat.st_mtime),
        "backup_sha256": _file_sha256(backup_path),
        "backup_error": None,
        "backup_created_at": _iso_from_timestamp(stat.st_mtime),
    }


def _backup_error_summary(
    *,
    backup_mode: str,
    backup_path: str | None,
    error: str,
) -> dict[str, object]:
    return {
        "backup_mode": backup_mode,
        "backup_path": backup_path,
        "backup_created_by_orchestrator": False,
        "backup_reused": backup_mode == BACKUP_MODE_EXISTING,
        "backup_validation_status": "FAILED",
        "backup_size": 0,
        "backup_mtime": None,
        "backup_sha256": None,
        "backup_error": error,
    }


def _schema_fingerprint(conn: sqlite3.Connection, table_names: tuple[str, ...]) -> dict[str, list[dict[str, object]]]:
    fingerprint: dict[str, list[dict[str, object]]] = {}
    existing_tables = _table_names(conn)
    for table_name in table_names:
        if table_name not in existing_tables:
            fingerprint[table_name] = []
            continue
        fingerprint[table_name] = [
            {
                "cid": int(row[0]),
                "name": str(row[1]),
                "type": str(row[2]),
                "notnull": int(row[3]),
                "default": row[4],
                "pk": int(row[5]),
            }
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        ]
    return fingerprint


def validate_existing_backup(
    *,
    existing_backup_path: str,
    confirm_existing_backup_path: str,
    db_path: str,
    repo_root: str | Path,
    orchestrator_started_at_utc: datetime,
) -> dict[str, object]:
    backup_mode = BACKUP_MODE_EXISTING
    try:
        resolved = _resolve_temp_path(existing_backup_path, repo_root=repo_root)
        confirmed = Path(confirm_existing_backup_path).resolve()
        if confirmed != resolved:
            return _backup_error_summary(
                backup_mode=backup_mode,
                backup_path=str(resolved),
                error="--confirm-existing-backup-path must exactly match normalized --existing-backup-path",
            )
        live_db = Path(db_path).resolve()
        if resolved == live_db:
            return _backup_error_summary(
                backup_mode=backup_mode,
                backup_path=str(resolved),
                error="existing backup path must not be the live production DB",
            )
        if resolved.name.endswith(("-wal", "-shm")):
            return _backup_error_summary(
                backup_mode=backup_mode,
                backup_path=str(resolved),
                error="existing backup path must not be a WAL or SHM file",
            )
        if not resolved.exists():
            return _backup_error_summary(backup_mode=backup_mode, backup_path=str(resolved), error="existing backup path does not exist")
        if not resolved.is_file():
            return _backup_error_summary(backup_mode=backup_mode, backup_path=str(resolved), error="existing backup path is not a regular file")
        stat = resolved.stat()
        if stat.st_size <= 0:
            return _backup_error_summary(backup_mode=backup_mode, backup_path=str(resolved), error="existing backup is empty")
        if datetime.fromtimestamp(stat.st_mtime, timezone.utc) > orchestrator_started_at_utc:
            return _backup_error_summary(
                backup_mode=backup_mode,
                backup_path=str(resolved),
                error="existing backup file is newer than orchestrator start time",
            )
        backup_conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
        try:
            integrity = str(backup_conn.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity.lower() != "ok":
                return _backup_error_summary(
                    backup_mode=backup_mode,
                    backup_path=str(resolved),
                    error=f"existing backup integrity_check failed: {integrity}",
                )
            backup_tables = _table_names(backup_conn)
            missing_tables = [table_name for table_name in CRITICAL_BACKUP_TABLES if table_name not in backup_tables]
            if missing_tables:
                return _backup_error_summary(
                    backup_mode=backup_mode,
                    backup_path=str(resolved),
                    error="existing backup missing critical tables: " + ", ".join(missing_tables),
                )
            backup_schema = _schema_fingerprint(backup_conn, CRITICAL_BACKUP_TABLES)
        finally:
            backup_conn.close()

        live_conn = _connect_readonly(db_path)
        try:
            live_tables = _table_names(live_conn)
            missing_live_tables = [table_name for table_name in CRITICAL_BACKUP_TABLES if table_name not in live_tables]
            if missing_live_tables:
                return _backup_error_summary(
                    backup_mode=backup_mode,
                    backup_path=str(resolved),
                    error="live DB missing critical tables: " + ", ".join(missing_live_tables),
                )
            live_schema = _schema_fingerprint(live_conn, CRITICAL_BACKUP_TABLES)
        finally:
            live_conn.close()
        if backup_schema != live_schema:
            return _backup_error_summary(
                backup_mode=backup_mode,
                backup_path=str(resolved),
                error="existing backup schema fingerprint does not match live production DB",
            )
        return _backup_summary_from_path(
            resolved,
            backup_mode=backup_mode,
            backup_created_by_orchestrator=False,
            backup_reused=True,
        )
    except Exception as exc:
        return _backup_error_summary(
            backup_mode=backup_mode,
            backup_path=str(Path(existing_backup_path).resolve()) if existing_backup_path else None,
            error=str(exc),
        )


def _backup_fields(backup_summary: dict[str, object] | None) -> dict[str, object]:
    backup_summary = backup_summary or {}
    return {
        "backup_mode": backup_summary.get("backup_mode"),
        "backup_path": backup_summary.get("backup_path"),
        "backup_created_by_orchestrator": backup_summary.get("backup_created_by_orchestrator"),
        "backup_reused": backup_summary.get("backup_reused"),
        "backup_validation_status": backup_summary.get("backup_validation_status"),
        "backup_size": backup_summary.get("backup_size"),
        "backup_mtime": backup_summary.get("backup_mtime"),
        "backup_sha256": backup_summary.get("backup_sha256"),
        "backup_error": backup_summary.get("backup_error"),
    }


def _read_scheduler_taxonomy(config_path: str | Path | None) -> dict[str, object]:
    if config_path is None:
        return {"scheduler_config_checked": False}
    from rawcandle.scheduler.config import read_scheduler_config

    config = read_scheduler_config(str(config_path))
    return {
        "scheduler_config_checked": True,
        "datacenter_taxonomy_version": config.datacenter_taxonomy_version,
        "datacenter_taxonomy_csv": config.datacenter_taxonomy_csv,
        "ec_source_layer_taxonomy_version": config.ec_source_layer_taxonomy_version,
        "ec_source_layer_taxonomy_csv": config.ec_source_layer_taxonomy_csv,
    }


def _validate_preconditions(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    deployment_id: int,
    date_from: str,
    date_to: str,
    backup_dir: str,
    evidence_output_root: str,
    repo_root: str | Path,
    expected_active_taxonomy_version: str | None,
    scheduler_config_path: str | None,
) -> dict[str, object]:
    errors: list[str] = []
    try:
        backup_path = _resolve_temp_path(backup_dir, repo_root=repo_root)
        evidence_path = _resolve_temp_path(evidence_output_root, repo_root=repo_root)
    except ValueError as exc:
        errors.append(str(exc))
        backup_path = Path(backup_dir).resolve()
        evidence_path = Path(evidence_output_root).resolve()

    if ecosystem_code != "DATACENTER":
        errors.append("taxonomy full rebuild is restricted to ecosystem DATACENTER")
    if not Path(taxonomy_csv_path).exists():
        errors.append("taxonomy CSV does not exist")
    if not Path(watchlist_path).exists():
        errors.append("watchlist does not exist")
    try:
        requested_start = _parse_iso_date(date_from, "date_from")
        requested_end = _parse_iso_date(date_to, "date_to")
        if requested_start > requested_end:
            errors.append("date_from must be less than or equal to date_to")
    except ValueError as exc:
        errors.append(str(exc))

    scheduler_state = _read_scheduler_taxonomy(scheduler_config_path)
    if scheduler_state.get("datacenter_taxonomy_version") == taxonomy_version_code:
        errors.append("scheduler datacenter taxonomy is already switched to proposed taxonomy")
    if scheduler_state.get("ec_source_layer_taxonomy_version") == taxonomy_version_code:
        errors.append("scheduler EC taxonomy is already switched to proposed taxonomy")

    deployment: dict[str, object] | None = None
    taxonomy: dict[str, object] | None = None
    active: dict[str, object] | None = None
    taxonomy_source_sha256 = None
    if Path(taxonomy_csv_path).exists():
        taxonomy_source_sha256 = _file_sha256(taxonomy_csv_path)
    try:
        conn = _connect_readonly(db_path)
        try:
            deployment = _fetch_deployment(
                conn,
                deployment_id=deployment_id,
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
            )
            taxonomy = _fetch_taxonomy(
                conn,
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
            )
            active = _fetch_active_taxonomy(conn, ecosystem_code=ecosystem_code)
        finally:
            conn.close()
    except Exception as exc:
        errors.append(f"database precondition inspection failed: {exc}")

    if deployment is None:
        errors.append("deployment row not found")
    else:
        if int(deployment.get("rebuild_required") or 0) != 1:
            errors.append("deployment rebuild_required is not true")
        if str(deployment.get("activation_status")) == "ACTIVE":
            errors.append("deployment is already active")
        if str(deployment.get("rebuild_start_date")) > date_from:
            errors.append("requested range starts before deployment rebuild_start_date")
        source_sha = str(deployment.get("source_sha256") or "")
        if taxonomy_source_sha256 is not None and source_sha and source_sha != taxonomy_source_sha256:
            errors.append("deployment source hash does not match taxonomy CSV")

    if taxonomy is None:
        errors.append("proposed taxonomy metadata not found")
        taxonomy_version_id = None
    else:
        taxonomy_version_id = int(taxonomy["taxonomy_version_id"])
        if int(taxonomy.get("is_active") or 0) == 1:
            errors.append("proposed taxonomy is already active")
        if taxonomy_source_sha256 is not None and str(taxonomy.get("source_hash") or "") != taxonomy_source_sha256:
            errors.append("loaded taxonomy hash does not match taxonomy CSV")

    if active is None:
        errors.append("active taxonomy not found")
    elif str(active.get("taxonomy_version_code")) == taxonomy_version_code:
        errors.append("proposed taxonomy is already current active taxonomy")
    elif expected_active_taxonomy_version and str(active.get("taxonomy_version_code")) != expected_active_taxonomy_version:
        errors.append("active taxonomy version does not match expected current taxonomy")

    return {
        "precondition_status": "OK" if not errors else "BLOCKED",
        "blocking_errors": sorted(set(errors)),
        "deployment": deployment,
        "taxonomy": taxonomy,
        "active_taxonomy": active,
        "taxonomy_version_id": taxonomy_version_id,
        "taxonomy_source_sha256": taxonomy_source_sha256,
        "backup_dir": str(backup_path),
        "evidence_output_root": str(evidence_path),
        "scheduler_state": scheduler_state,
    }


def plan_ec_taxonomy_full_rebuild(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    deployment_id: int,
    date_from: str,
    date_to: str,
    backup_dir: str,
    evidence_output_root: str,
    confirm_db: str,
    confirm_ecosystem: str,
    confirm_taxonomy_version: str,
    confirm_deployment_id: int,
    confirm_date_from: str,
    confirm_date_to: str,
    expected_active_taxonomy_version: str | None = None,
    scheduler_config_path: str | None = None,
    repo_root: str | Path = ".",
) -> dict[str, object]:
    gate_errors: list[str] = []
    if confirm_db != db_path:
        gate_errors.append("--confirm-db must exactly match --db")
    if confirm_ecosystem != ecosystem_code:
        gate_errors.append("--confirm-ecosystem must exactly match --ecosystem")
    if confirm_taxonomy_version != taxonomy_version_code:
        gate_errors.append("--confirm-taxonomy-version must exactly match --taxonomy-version")
    if int(confirm_deployment_id) != int(deployment_id):
        gate_errors.append("--confirm-deployment-id must exactly match --deployment-id")
    if confirm_date_from != date_from:
        gate_errors.append("--confirm-date-from must exactly match --date-from")
    if confirm_date_to != date_to:
        gate_errors.append("--confirm-date-to must exactly match --date-to")

    try:
        chunks = build_ec_taxonomy_rebuild_chunks(date_from=date_from, date_to=date_to)
    except ValueError as exc:
        chunks = []
        gate_errors.append(str(exc))

    preconditions = _validate_preconditions(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        taxonomy_csv_path=taxonomy_csv_path,
        watchlist_path=watchlist_path,
        deployment_id=deployment_id,
        date_from=date_from,
        date_to=date_to,
        backup_dir=backup_dir,
        evidence_output_root=evidence_output_root,
        repo_root=repo_root,
        expected_active_taxonomy_version=expected_active_taxonomy_version,
        scheduler_config_path=scheduler_config_path,
    )
    gate_errors.extend(str(error) for error in preconditions["blocking_errors"])

    chunk_payload = _canonical_chunk_payload(chunks)
    chunk_plan_hash = _json_sha256(
        {
            "rebuild_mode": REBUILD_MODE,
            "date_from": date_from,
            "date_to": date_to,
            "max_range_days": MAX_RANGE_DAYS,
            "chunks": chunk_payload,
        }
    )
    return {
        "status": "READY_TAXONOMY_FULL_REBUILD_PLAN" if not gate_errors else "BLOCKED_TAXONOMY_FULL_REBUILD_PLAN",
        "rebuild_mode": REBUILD_MODE,
        "requested_start": date_from,
        "requested_end": date_to,
        "chunk_count": len(chunks),
        "chunks": [
            {
                **item,
                "deployment_id": deployment_id,
                "taxonomy_version": taxonomy_version_code,
                "taxonomy_version_id": preconditions.get("taxonomy_version_id"),
            }
            for item in chunk_payload
        ],
        "chunk_plan_hash": chunk_plan_hash,
        "deployment_id": deployment_id,
        "taxonomy_version": taxonomy_version_code,
        "taxonomy_version_id": preconditions.get("taxonomy_version_id"),
        "taxonomy_source_sha256": preconditions.get("taxonomy_source_sha256"),
        "preconditions": preconditions,
        "blocking_errors": sorted(set(gate_errors)),
    }


def _backup_filename(db_path: str, *, ecosystem_code: str, taxonomy_version_code: str, date_from: str, date_to: str) -> str:
    db_base = Path(db_path).stem
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        f"{db_base}__ec_taxonomy_full_rebuild__{ecosystem_code}__"
        f"{taxonomy_version_code}__{date_from.replace('-', '')}_{date_to.replace('-', '')}__{timestamp}.sqlite"
    )


def _create_sqlite_backup(
    *,
    db_path: str,
    backup_dir: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    date_from: str,
    date_to: str,
) -> dict[str, object]:
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    backup_path = Path(backup_dir) / _backup_filename(
        db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        date_from=date_from,
        date_to=date_to,
    )
    source = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(backup_path))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return _backup_summary_from_path(
        backup_path,
        backup_mode=BACKUP_MODE_ORCHESTRATOR_CREATED,
        backup_created_by_orchestrator=True,
        backup_reused=False,
    )


def _progress_path(evidence_output_root: str | Path) -> Path:
    return Path(evidence_output_root) / PROGRESS_FILENAME


def _write_progress(path: Path, progress: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(progress, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _read_progress(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _mark_deployment_ec_status(
    *,
    db_path: str,
    deployment_id: int,
    status: str,
    error: str | None = None,
    mismatch_count: int | None = None,
    required_signal_date: str | None = None,
) -> None:
    conn = _connect_readwrite(db_path)
    try:
        columns = _table_columns(conn, "ec_taxonomy_change_deployment")
        assignments = [
            "ec_rebuild_status = ?",
            "updated_at_utc = CURRENT_TIMESTAMP",
        ]
        params: list[object] = [status]
        if "last_error" in columns:
            assignments.append("last_error = ?")
            params.append(error)
        if mismatch_count is not None and "mismatch_count" in columns:
            assignments.append("mismatch_count = ?")
            params.append(mismatch_count)
        if required_signal_date is not None and "required_signal_date" in columns:
            assignments.append("required_signal_date = ?")
            params.append(required_signal_date)
        params.append(deployment_id)
        with conn:
            conn.execute(
                f"UPDATE ec_taxonomy_change_deployment SET {', '.join(assignments)} WHERE taxonomy_change_id = ?",
                tuple(params),
            )
    finally:
        conn.close()


def _verify_completed_chunk(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    deployment_id: int,
    chunk: RebuildChunk,
) -> dict[str, object]:
    plan = plan_ec_source_layer_backfill(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        date_from=chunk.chunk_start,
        date_to=chunk.chunk_end,
        taxonomy_csv_path=taxonomy_csv_path,
        watchlist_path=watchlist_path,
        allow_replace_existing=True,
        taxonomy_rebuild=True,
        deployment_id=deployment_id,
    )
    if str(plan.get("status")) not in {"READY_TAXONOMY_REBUILD_PLAN", "SKIP_ALL_DATES_ALREADY_LOADED"}:
        return {"status": "FAILED", "error": f"planner status {plan.get('status')} is not verifiable", "planner_summary": plan}
    source_dates = [
        str(row.get("date"))
        for row in plan.get("source_date_availability", {}).get("per_date", [])
        if isinstance(row, dict) and row.get("aligned")
    ]
    if not source_dates:
        return {"status": "OK", "verified_dates": []}
    conn = _connect_readonly(db_path)
    try:
        taxonomy = _fetch_taxonomy(conn, ecosystem_code=ecosystem_code, taxonomy_version_code=taxonomy_version_code)
        if taxonomy is None:
            return {"status": "FAILED", "error": "taxonomy metadata not found"}
        taxonomy_version_id = int(taxonomy["taxonomy_version_id"])
        ecosystem_id = int(taxonomy["ecosystem_id"])
        missing: dict[str, list[str]] = {}
        for table_name in (
            "ec_ticker_signal_daily",
            "ec_group_signal_daily",
            "ec_group_synthetic_ohlc_daily",
            "ec_group_index_daily",
        ):
            columns = _table_columns(conn, table_name)
            predicates = ["signal_date = ?", "taxonomy_version_id = ?"]
            params_prefix: list[object] = []
            if "ecosystem_id" in columns:
                predicates.append("ecosystem_id = ?")
            for signal_date in source_dates:
                params = [signal_date, taxonomy_version_id]
                if "ecosystem_id" in columns:
                    params.append(ecosystem_id)
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE {' AND '.join(predicates)}",
                    tuple(params_prefix + params),
                ).fetchone()[0]
                if int(count) == 0:
                    missing.setdefault(table_name, []).append(signal_date)
        if missing:
            return {"status": "FAILED", "missing_loaded_dates": missing, "verified_dates": source_dates}
        return {"status": "OK", "verified_dates": source_dates}
    finally:
        conn.close()


def _validate_whole_range(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    date_from: str,
    date_to: str,
    chunks: list[dict[str, object]],
) -> dict[str, object]:
    errors: list[str] = []
    total_mismatch_count = sum(int(chunk.get("total_mismatch_count") or 0) for chunk in chunks)
    if total_mismatch_count != 0:
        errors.append("total mismatch count is not zero")
    for chunk in chunks:
        coverage = str(chunk.get("coverage_status") or "OK")
        parity = str(chunk.get("parity_status") or "OK")
        if coverage not in {"OK", "OK_WITH_WARNINGS"}:
            errors.append(f"chunk {chunk.get('chunk_index')} coverage status is {coverage}")
        if parity not in {"OK", "OK_WITH_WARNINGS"}:
            errors.append(f"chunk {chunk.get('chunk_index')} parity status is {parity}")

    conn = _connect_readonly(db_path)
    try:
        taxonomy = _fetch_taxonomy(conn, ecosystem_code=ecosystem_code, taxonomy_version_code=taxonomy_version_code)
        if taxonomy is None:
            errors.append("taxonomy metadata not found")
            stale_summary = {"stale_validation_status": "NOT_RUN"}
        else:
            taxonomy_summary = summarize_taxonomy_csv(taxonomy_csv_path, taxonomy_version_code)
            if str(taxonomy.get("source_hash") or "") != taxonomy_summary.source_sha256:
                errors.append("loaded taxonomy hash does not match taxonomy CSV")
            taxonomy_rows = taxonomy_summary.rows
            stale_summary = validate_rebuild_stale_rows(
                conn,
                ecosystem_id=int(taxonomy["ecosystem_id"]),
                taxonomy_version_id=int(taxonomy["taxonomy_version_id"]),
                taxonomy_version_code=taxonomy_version_code,
                date_from=date_from,
                date_to=date_to,
                taxonomy_rows=taxonomy_rows,
            )
            if stale_summary.get("stale_validation_status") != "OK":
                errors.append("stale rows block whole-range validation")
    finally:
        conn.close()

    return {
        "whole_range_validation_status": "OK" if not errors else "FAILED",
        "coverage_status": "OK" if not any("coverage" in error for error in errors) else "FAILED",
        "parity_status": "OK" if total_mismatch_count == 0 and not any("parity" in error for error in errors) else "FAILED",
        "total_mismatch_count": total_mismatch_count,
        "stale_row_validation": stale_summary,
        "blocking_errors": sorted(set(errors)),
    }


def _assert_resume_matches(
    progress: dict[str, object],
    plan: dict[str, object],
    *,
    existing_backup_path: str | None,
    confirm_existing_backup_path: str | None,
) -> list[str]:
    errors: list[str] = []
    for field in ("deployment_id", "taxonomy_version", "requested_start", "requested_end", "chunk_plan_hash", "taxonomy_source_sha256"):
        if progress.get(field) != plan.get(field):
            errors.append(f"resume state {field} does not match requested plan")
    backup_summary = progress.get("backup_summary")
    if not isinstance(backup_summary, dict):
        errors.append("resume state backup_summary is missing")
        return errors
    backup_path = str(backup_summary.get("backup_path") or "")
    backup_sha = str(backup_summary.get("backup_sha256") or "")
    backup_mode = str(backup_summary.get("backup_mode") or "")
    if backup_mode == BACKUP_MODE_EXISTING:
        if existing_backup_path is None:
            errors.append("resume of existing-backup run requires --existing-backup-path")
        elif Path(existing_backup_path).resolve() != Path(backup_path).resolve():
            errors.append("resume existing backup path does not match original backup path")
        if confirm_existing_backup_path is None:
            errors.append("resume of existing-backup run requires --confirm-existing-backup-path")
        elif Path(confirm_existing_backup_path).resolve() != Path(backup_path).resolve():
            errors.append("resume existing backup confirmation path does not match original backup path")
    if not backup_path:
        errors.append("resume state backup_path is missing")
    elif not Path(backup_path).exists():
        errors.append("resume backup path does not exist")
    elif _file_sha256(backup_path) != backup_sha:
        errors.append("resume backup SHA-256 does not match original backup")
    return errors


def run_ec_taxonomy_full_rebuild(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    deployment_id: int,
    date_from: str,
    date_to: str,
    backup_dir: str,
    evidence_output_root: str,
    confirm_db: str,
    confirm_ecosystem: str,
    confirm_taxonomy_version: str,
    confirm_deployment_id: int,
    confirm_date_from: str,
    confirm_date_to: str,
    existing_backup_path: str | None = None,
    confirm_existing_backup_path: str | None = None,
    expected_active_taxonomy_version: str | None = None,
    scheduler_config_path: str | None = None,
    resume: bool = False,
    repo_root: str | Path = ".",
    backfill_runner: Callable[..., dict[str, object]] = run_ec_source_layer_backfill,
) -> dict[str, object]:
    orchestrator_started_at_utc = datetime.now(timezone.utc)
    plan = plan_ec_taxonomy_full_rebuild(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        taxonomy_csv_path=taxonomy_csv_path,
        watchlist_path=watchlist_path,
        deployment_id=deployment_id,
        date_from=date_from,
        date_to=date_to,
        backup_dir=backup_dir,
        evidence_output_root=evidence_output_root,
        confirm_db=confirm_db,
        confirm_ecosystem=confirm_ecosystem,
        confirm_taxonomy_version=confirm_taxonomy_version,
        confirm_deployment_id=confirm_deployment_id,
        confirm_date_from=confirm_date_from,
        confirm_date_to=confirm_date_to,
        expected_active_taxonomy_version=expected_active_taxonomy_version,
        scheduler_config_path=scheduler_config_path,
        repo_root=repo_root,
    )
    if plan["status"] != "READY_TAXONOMY_FULL_REBUILD_PLAN":
        return {
            "overall_status": "BLOCKED_BEFORE_WRITES",
            "retry_required": False,
            "watermark_finalization_performed": False,
            "plan": plan,
            "blocking_errors": plan["blocking_errors"],
            **_backup_fields(None),
        }

    evidence_root = Path(str(plan["preconditions"]["evidence_output_root"]))
    progress_file = _progress_path(evidence_root)
    previous_progress = _read_progress(progress_file)
    if previous_progress is not None and not resume:
        return {
            "overall_status": "BLOCKED_BEFORE_WRITES",
            "retry_required": False,
            "watermark_finalization_performed": False,
            "plan": plan,
            "blocking_errors": ["progress file already exists; use resume to continue guarded rebuild"],
            **_backup_fields(None),
        }
    completed_chunks: list[dict[str, object]] = []
    backup_summary: dict[str, object]
    if previous_progress is not None:
        resume_errors = _assert_resume_matches(
            previous_progress,
            plan,
            existing_backup_path=existing_backup_path,
            confirm_existing_backup_path=confirm_existing_backup_path,
        )
        if resume_errors:
            return {
                "overall_status": "BLOCKED_BEFORE_WRITES",
                "retry_required": False,
                "watermark_finalization_performed": False,
                "plan": plan,
                "blocking_errors": resume_errors,
                "backup_summary": previous_progress.get("backup_summary"),
                **_backup_fields(previous_progress.get("backup_summary") if isinstance(previous_progress.get("backup_summary"), dict) else None),
            }
        backup_summary = dict(previous_progress.get("backup_summary") or {})
        for completed in previous_progress.get("completed_chunks", []):
            chunk = RebuildChunk(
                chunk_index=int(completed["chunk_index"]),
                chunk_start=str(completed["chunk_start"]),
                chunk_end=str(completed["chunk_end"]),
                chunk_span_days=int(completed["chunk_span_days"]),
            )
            verified = _verify_completed_chunk(
                db_path=db_path,
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
                taxonomy_csv_path=taxonomy_csv_path,
                watchlist_path=watchlist_path,
                deployment_id=deployment_id,
                chunk=chunk,
            )
            if verified["status"] != "OK":
                return {
                    "overall_status": "BLOCKED_BEFORE_WRITES",
                    "retry_required": True,
                    "watermark_finalization_performed": False,
                    "plan": plan,
                    "blocking_errors": [f"completed chunk {chunk.chunk_index} failed resume verification"],
                    "resume_verification": verified,
                    "backup_summary": backup_summary,
                    **_backup_fields(backup_summary),
                }
            completed_chunks.append({**completed, "resume_verification": verified, "skipped_by_resume": True})
    else:
        if existing_backup_path is not None:
            if confirm_existing_backup_path is None:
                backup_summary = _backup_error_summary(
                    backup_mode=BACKUP_MODE_EXISTING,
                    backup_path=str(Path(existing_backup_path).resolve()),
                    error="--confirm-existing-backup-path is required with --existing-backup-path",
                )
            else:
                backup_summary = validate_existing_backup(
                    existing_backup_path=existing_backup_path,
                    confirm_existing_backup_path=confirm_existing_backup_path,
                    db_path=db_path,
                    repo_root=repo_root,
                    orchestrator_started_at_utc=orchestrator_started_at_utc,
                )
            if backup_summary["backup_validation_status"] != "OK":
                return {
                    "overall_status": "BLOCKED_BEFORE_WRITES",
                    "retry_required": False,
                    "watermark_finalization_performed": False,
                    "backup_summary": backup_summary,
                    "plan": plan,
                    "blocking_errors": [str(backup_summary["backup_error"])],
                    **_backup_fields(backup_summary),
                }
        else:
            backup_summary = _create_sqlite_backup(
                db_path=db_path,
                backup_dir=str(plan["preconditions"]["backup_dir"]),
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
                date_from=date_from,
                date_to=date_to,
            )
        _mark_deployment_ec_status(
            db_path=db_path,
            deployment_id=deployment_id,
            status="IN_PROGRESS",
            required_signal_date=date_to,
        )

    progress = {
        "rebuild_mode": REBUILD_MODE,
        "overall_status": "IN_PROGRESS",
        "deployment_id": deployment_id,
        "taxonomy_version": taxonomy_version_code,
        "taxonomy_version_id": plan.get("taxonomy_version_id"),
        "taxonomy_source_sha256": plan.get("taxonomy_source_sha256"),
        "requested_start": date_from,
        "requested_end": date_to,
        "chunk_plan_hash": plan.get("chunk_plan_hash"),
        "chunks": plan.get("chunks"),
        "backup_summary": backup_summary,
        "completed_chunks": completed_chunks,
        "failed_chunk": None,
        "whole_range_validation_status": "NOT_RUN",
        "watermark_finalization_status": "NOT_RUN",
        "updated_at_utc": _utc_now(),
    }
    _write_progress(progress_file, progress)

    completed_indices = {int(chunk["chunk_index"]) for chunk in completed_chunks}
    for chunk_dict in plan["chunks"]:
        chunk_index = int(chunk_dict["chunk_index"])
        if chunk_index in completed_indices:
            continue
        started_at = _utc_now()
        try:
            chunk_summary = backfill_runner(
                db_path=db_path,
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
                date_from=str(chunk_dict["chunk_start"]),
                date_to=str(chunk_dict["chunk_end"]),
                taxonomy_csv_path=taxonomy_csv_path,
                watchlist_path=watchlist_path,
                backup_dir=str(plan["preconditions"]["backup_dir"]),
                confirm_db=confirm_db,
                confirm_ecosystem=confirm_ecosystem,
                confirm_taxonomy_version=confirm_taxonomy_version,
                allow_replace_existing=True,
                taxonomy_rebuild=True,
                deployment_id=deployment_id,
                confirm_rebuild_start=str(chunk_dict["chunk_start"]),
                confirm_rebuild_end=str(chunk_dict["chunk_end"]),
                reconcile_watchlist=False,
                create_backup=False,
                existing_backup_path=str(backup_summary.get("backup_path")),
                advance_watermark=False,
            )
        except Exception as exc:
            chunk_summary = {
                "status": "BACKFILL_FAILED",
                "error": str(exc),
                "errors": [str(exc)],
                "total_mismatch_count": 0,
            }
        finished_at = _utc_now()
        chunk_result = {
            **chunk_dict,
            "started_at_utc": started_at,
            "completed_at_utc": finished_at,
            "status": chunk_summary.get("status"),
            "selected_dates": chunk_summary.get("selected_dates", []),
            "completed_dates": chunk_summary.get("completed_dates", []),
            "skipped_dates": chunk_summary.get("skipped_dates", []),
            "coverage_status": "OK"
            if all(
                str(result.get("coverage_status")) in {"OK", "OK_WITH_WARNINGS"}
                for result in chunk_summary.get("per_date_results", [])
                if isinstance(result, dict)
            )
            else "FAILED",
            "parity_status": "OK"
            if all(
                str(result.get("parity_status")) in {"OK", "OK_WITH_WARNINGS"} and int(result.get("total_mismatch_count") or 0) == 0
                for result in chunk_summary.get("per_date_results", [])
                if isinstance(result, dict)
            )
            else "FAILED",
            "total_mismatch_count": int(chunk_summary.get("total_mismatch_count") or 0),
            "error": chunk_summary.get("error"),
            "summary": chunk_summary,
        }
        if (
            str(chunk_summary.get("status")) not in SUCCESS_CHUNK_STATUSES
            or chunk_result["coverage_status"] != "OK"
            or chunk_result["parity_status"] != "OK"
            or int(chunk_result["total_mismatch_count"]) != 0
        ):
            progress.update(
                {
                    "overall_status": "FAILED",
                    "failed_chunk": chunk_result,
                    "failed_chunk_index": chunk_index,
                    "retry_required": True,
                    "watermark_finalization_status": "NOT_RUN",
                    "updated_at_utc": _utc_now(),
                }
            )
            _write_progress(progress_file, progress)
            _mark_deployment_ec_status(
                db_path=db_path,
                deployment_id=deployment_id,
                status="FAILED",
                error=str(chunk_summary.get("error") or f"chunk {chunk_index} failed"),
                mismatch_count=int(chunk_result["total_mismatch_count"]),
                required_signal_date=date_to,
            )
            return {
                "overall_status": "FAILED",
                "failed_chunk_index": chunk_index,
                "retry_required": True,
                "watermark_finalization_performed": False,
                "backup_summary": backup_summary,
                "progress_path": str(progress_file),
                "chunk_results": completed_chunks + [chunk_result],
                "plan": plan,
                **_backup_fields(backup_summary),
            }
        completed_chunks.append(chunk_result)
        progress["completed_chunks"] = completed_chunks
        progress["updated_at_utc"] = _utc_now()
        _write_progress(progress_file, progress)

    whole_range_validation = _validate_whole_range(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        taxonomy_csv_path=taxonomy_csv_path,
        date_from=date_from,
        date_to=date_to,
        chunks=completed_chunks,
    )
    if whole_range_validation["whole_range_validation_status"] != "OK":
        progress.update(
            {
                "overall_status": "FAILED",
                "whole_range_validation_status": "FAILED",
                "whole_range_validation": whole_range_validation,
                "retry_required": True,
                "updated_at_utc": _utc_now(),
            }
        )
        _write_progress(progress_file, progress)
        _mark_deployment_ec_status(
            db_path=db_path,
            deployment_id=deployment_id,
            status="FAILED",
            error="; ".join(whole_range_validation["blocking_errors"]),
            mismatch_count=int(whole_range_validation["total_mismatch_count"]),
            required_signal_date=date_to,
        )
        return {
            "overall_status": "FAILED",
            "retry_required": True,
            "watermark_finalization_performed": False,
            "backup_summary": backup_summary,
            "progress_path": str(progress_file),
            "chunk_results": completed_chunks,
            "whole_range_validation": whole_range_validation,
            "plan": plan,
            **_backup_fields(backup_summary),
        }

    watermark_summary = advance_ec_pipeline_watermarks_after_historical_backfill(
        target_db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        latest_signal_date=date_to,
        taxonomy_rebuild=True,
    )
    evidence_summary = apply_datacenter_taxonomy_rebuild_evidence(
        analysis_db=db_path,
        ecosystem_code=ecosystem_code,
        proposed_taxonomy_version=taxonomy_version_code,
        proposed_taxonomy_csv=taxonomy_csv_path,
        deployment_id=deployment_id,
        required_signal_date=date_to,
        coverage_status="OK",
        parity_status="OK",
        total_mismatch_count=0,
    )
    progress.update(
        {
            "overall_status": "REBUILD_COMPLETED" if evidence_summary.get("ready_to_activate") else "FAILED",
            "whole_range_validation_status": "OK",
            "whole_range_validation": whole_range_validation,
            "watermark_finalization_status": "OK",
            "watermark_summary": watermark_summary,
            "deployment_evidence_summary": evidence_summary,
            "retry_required": not bool(evidence_summary.get("ready_to_activate")),
            "updated_at_utc": _utc_now(),
        }
    )
    _write_progress(progress_file, progress)
    return {
        "overall_status": progress["overall_status"],
        "retry_required": progress["retry_required"],
        "watermark_finalization_performed": True,
        "canonical_watermark_scopes": list(CANONICAL_EC_WATERMARK_SCOPES),
        "backup_summary": backup_summary,
        "progress_path": str(progress_file),
        "chunk_results": completed_chunks,
        "whole_range_validation": whole_range_validation,
        "watermark_summary": watermark_summary,
        "deployment_evidence_summary": evidence_summary,
        "plan": plan,
        **_backup_fields(backup_summary),
    }


def render_plan_text(summary: dict[str, object]) -> str:
    lines = [
        "EC Taxonomy Full Rebuild Plan",
        f"status={summary.get('status')}",
        f"rebuild_mode={summary.get('rebuild_mode')}",
        f"deployment_id={summary.get('deployment_id')}",
        f"taxonomy_version={summary.get('taxonomy_version')}",
        f"taxonomy_version_id={summary.get('taxonomy_version_id')}",
        f"requested_start={summary.get('requested_start')}",
        f"requested_end={summary.get('requested_end')}",
        f"chunk_count={summary.get('chunk_count')}",
        f"chunk_plan_hash={summary.get('chunk_plan_hash')}",
    ]
    for chunk in summary.get("chunks", []):
        if isinstance(chunk, dict):
            lines.append(
                "chunk "
                f"{chunk.get('chunk_index')}: {chunk.get('chunk_start')}..{chunk.get('chunk_end')} "
                f"span={chunk.get('chunk_span_days')}"
            )
    if summary.get("blocking_errors"):
        lines.append("blocking_errors:")
        for error in summary["blocking_errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines)


def render_run_text(summary: dict[str, object]) -> str:
    lines = [
        "EC Taxonomy Full Rebuild",
        f"overall_status={summary.get('overall_status')}",
        f"retry_required={summary.get('retry_required')}",
        f"watermark_finalization_performed={summary.get('watermark_finalization_performed')}",
    ]
    plan = summary.get("plan")
    if isinstance(plan, dict):
        lines.append(f"deployment_id={plan.get('deployment_id')}")
        lines.append(f"taxonomy_version={plan.get('taxonomy_version')}")
        lines.append(f"requested_start={plan.get('requested_start')}")
        lines.append(f"requested_end={plan.get('requested_end')}")
        lines.append(f"chunk_count={plan.get('chunk_count')}")
    backup = summary.get("backup_summary")
    if isinstance(backup, dict):
        lines.append(f"backup_mode={backup.get('backup_mode')}")
        lines.append(f"backup_path={backup.get('backup_path')}")
        lines.append(f"backup_created_by_orchestrator={backup.get('backup_created_by_orchestrator')}")
        lines.append(f"backup_reused={backup.get('backup_reused')}")
        lines.append(f"backup_validation_status={backup.get('backup_validation_status')}")
        lines.append(f"backup_size={backup.get('backup_size')}")
        lines.append(f"backup_mtime={backup.get('backup_mtime')}")
        lines.append(f"backup_sha256={backup.get('backup_sha256')}")
        lines.append(f"backup_error={backup.get('backup_error')}")
    if summary.get("progress_path"):
        lines.append(f"progress_path={summary.get('progress_path')}")
    for chunk in summary.get("chunk_results", []):
        if isinstance(chunk, dict):
            lines.append(
                f"chunk {chunk.get('chunk_index')}: status={chunk.get('status')} "
                f"range={chunk.get('chunk_start')}..{chunk.get('chunk_end')} "
                f"mismatch={chunk.get('total_mismatch_count')}"
            )
    if summary.get("blocking_errors"):
        lines.append("blocking_errors:")
        for error in summary["blocking_errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines)
