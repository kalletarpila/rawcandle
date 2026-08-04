from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from analysis.datacenter_indices.taxonomy import DatacenterTaxonomyRow, load_datacenter_taxonomy_csv
from rawcandle.datacenter_taxonomy_replacement import (
    CANONICAL_DC_FACT_TABLES,
    CANONICAL_EC_FACT_TABLES,
    CANONICAL_EC_WATERMARK_SCOPES,
    DATACENTER_ECOSYSTEM_CODE,
    DEFAULT_DATACENTER_REBUILD_START_DATE,
    apply_datacenter_taxonomy_activation,
    apply_datacenter_taxonomy_rebuild_evidence,
    apply_datacenter_taxonomy_version,
    apply_ec_taxonomy_replacement_cleanup,
    finalize_ec_taxonomy_rebuild_validation,
    plan_datacenter_taxonomy_activation as _plan_activation,
    plan_datacenter_taxonomy_change,
    plan_ec_taxonomy_replacement_cleanup,
    prepare_datacenter_taxonomy_rebuild,
    summarize_taxonomy_csv,
)
from rawcandle.scheduler.config import read_scheduler_config, validate_scheduler_config, write_scheduler_config


REBUILD_MODE_FULL = "FULL_REBUILD"
REBUILD_MODE_DELTA = "DELTA_REBUILD"
SUPPORTED_REBUILD_MODES = {REBUILD_MODE_FULL}
SCHEDULER_TAXONOMY_KEYS = {
    "datacenter_taxonomy_csv",
    "datacenter_taxonomy_version",
    "ec_source_layer_taxonomy_csv",
    "ec_source_layer_taxonomy_version",
}
PHASE_SEQUENCE = (
    "DRAFT",
    "PLANNED",
    "REBUILDING",
    "VALIDATING",
    "READY_TO_ACTIVATE",
    "ACTIVATING",
    "ACTIVE",
)
FAILURE_STATES = {
    "BLOCKED",
    "REBUILD_FAILED",
    "VALIDATION_FAILED",
    "ACTIVATION_FAILED",
    "ROLLED_BACK",
}


@dataclass
class TaxonomyChangeServices:
    set_scheduler_guard: Callable[..., dict[str, object]] | None = None
    verify_active_writer: Callable[..., dict[str, object]] | None = None
    ensure_backup: Callable[..., dict[str, object]] | None = None
    run_dc_rebuild: Callable[..., dict[str, object]] | None = None
    run_ec_rebuild: Callable[..., dict[str, object]] | None = None


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_readwrite(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def _active_taxonomy(conn: sqlite3.Connection, *, ecosystem_code: str) -> dict[str, object] | None:
    if "ec_taxonomy_version" not in _table_names(conn):
        return None
    row = conn.execute(
        """
        SELECT tv.*
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


def _loaded_taxonomy(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> dict[str, object] | None:
    if "ec_taxonomy_version" not in _table_names(conn):
        return None
    row = conn.execute(
        """
        SELECT tv.*
        FROM ec_taxonomy_version tv
        JOIN ec_ecosystem e ON e.ecosystem_id = tv.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    return dict(row) if row is not None else None


def _deployment_for_source(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_source_hash: str,
) -> dict[str, object] | None:
    if "ec_taxonomy_change_deployment" not in _table_names(conn):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM ec_taxonomy_change_deployment
        WHERE ecosystem_code = ?
          AND proposed_taxonomy_version = ?
          AND source_sha256 = ?
        ORDER BY taxonomy_change_id DESC
        LIMIT 1
        """,
        (ecosystem_code, proposed_taxonomy_version, proposed_source_hash),
    ).fetchone()
    return dict(row) if row is not None else None


def _deployment_by_id(conn: sqlite3.Connection, *, deployment_id: int) -> dict[str, object] | None:
    if "ec_taxonomy_change_deployment" not in _table_names(conn):
        return None
    row = conn.execute(
        "SELECT * FROM ec_taxonomy_change_deployment WHERE taxonomy_change_id = ?",
        (deployment_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _taxonomy_version_from_csv(path: str | Path) -> str:
    rows = load_datacenter_taxonomy_csv(path)
    versions = sorted({row.taxonomy_version for row in rows})
    if len(versions) != 1:
        raise ValueError("proposed taxonomy CSV must contain exactly one taxonomy_version")
    return versions[0]


def _membership_key(row: DatacenterTaxonomyRow) -> tuple[str, str, str]:
    return (row.ticker, row.layer, row.subindustry)


def build_taxonomy_diff(
    *,
    current_taxonomy_csv: str | Path,
    current_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    proposed_taxonomy_version: str,
) -> dict[str, object]:
    current_rows = load_datacenter_taxonomy_csv(
        current_taxonomy_csv,
        expected_taxonomy_version=current_taxonomy_version,
    )
    proposed_rows = load_datacenter_taxonomy_csv(
        proposed_taxonomy_csv,
        expected_taxonomy_version=proposed_taxonomy_version,
    )
    current_tickers = {row.ticker for row in current_rows}
    proposed_tickers = {row.ticker for row in proposed_rows}
    current_layers = {row.layer for row in current_rows}
    proposed_layers = {row.layer for row in proposed_rows}
    current_subindustries = {row.subindustry for row in current_rows}
    proposed_subindustries = {row.subindustry for row in proposed_rows}
    current_by_key = {_membership_key(row): row for row in current_rows}
    proposed_by_key = {_membership_key(row): row for row in proposed_rows}
    current_primary = {row.ticker: _membership_key(row) for row in current_rows if row.is_primary}
    proposed_primary = {row.ticker: _membership_key(row) for row in proposed_rows if row.is_primary}

    added_keys = sorted(set(proposed_by_key) - set(current_by_key))
    removed_keys = sorted(set(current_by_key) - set(proposed_by_key))
    primary_changes = []
    for ticker in sorted(set(current_primary) & set(proposed_primary)):
        if current_primary[ticker] != proposed_primary[ticker]:
            primary_changes.append(
                {
                    "ticker": ticker,
                    "from": list(current_primary[ticker]),
                    "to": list(proposed_primary[ticker]),
                }
            )
    secondary_additions = [
        {"ticker": key[0], "layer": key[1], "subindustry": key[2]}
        for key in added_keys
        if not proposed_by_key[key].is_primary
    ]
    secondary_additions.extend(
        {"ticker": key[0], "layer": key[1], "subindustry": key[2]}
        for key in sorted(set(current_by_key) & set(proposed_by_key))
        if current_by_key[key].is_primary and not proposed_by_key[key].is_primary
    )
    secondary_removals = [
        {"ticker": key[0], "layer": key[1], "subindustry": key[2]}
        for key in removed_keys
        if not current_by_key[key].is_primary
    ]
    secondary_removals.extend(
        {"ticker": key[0], "layer": key[1], "subindustry": key[2]}
        for key in sorted(set(current_by_key) & set(proposed_by_key))
        if not current_by_key[key].is_primary and proposed_by_key[key].is_primary
    )
    scope_flag_changes = []
    for key in sorted(set(current_by_key) & set(proposed_by_key)):
        current = current_by_key[key]
        proposed = proposed_by_key[key]
        if current.report_group_status != proposed.report_group_status:
            scope_flag_changes.append(
                {
                    "ticker": key[0],
                    "layer": key[1],
                    "subindustry": key[2],
                    "from": current.report_group_status,
                    "to": proposed.report_group_status,
                }
            )

    added_layers = sorted(proposed_layers - current_layers)
    removed_layers = sorted(current_layers - proposed_layers)
    added_subindustries = sorted(proposed_subindustries - current_subindustries)
    removed_subindustries = sorted(current_subindustries - proposed_subindustries)
    structural_change_detected = bool(
        added_layers or removed_layers or added_subindustries or removed_subindustries
    )

    affected_tickers = set(proposed_tickers ^ current_tickers)
    affected_tickers.update(item["ticker"] for item in primary_changes)
    affected_tickers.update(item["ticker"] for item in secondary_additions)
    affected_tickers.update(item["ticker"] for item in secondary_removals)
    affected_tickers.update(item["ticker"] for item in scope_flag_changes)
    affected_groups = set(added_layers) | set(removed_layers) | set(added_subindustries) | set(removed_subindustries)
    for item in secondary_additions + secondary_removals + scope_flag_changes:
        affected_groups.add(str(item["layer"]))
        affected_groups.add(str(item["subindustry"]))
    for item in primary_changes:
        affected_groups.update(str(value) for value in item["from"][1:])
        affected_groups.update(str(value) for value in item["to"][1:])

    return {
        "added_tickers": sorted(proposed_tickers - current_tickers),
        "removed_tickers": sorted(current_tickers - proposed_tickers),
        "unchanged_tickers": sorted(current_tickers & proposed_tickers),
        "primary_membership_changes": primary_changes,
        "secondary_membership_additions": secondary_additions,
        "secondary_membership_removals": secondary_removals,
        "scope_flag_changes": scope_flag_changes,
        "affected_tickers": sorted(affected_tickers),
        "affected_groups": sorted(affected_groups),
        "added_layers": added_layers,
        "removed_layers": removed_layers,
        "added_subindustries": added_subindustries,
        "removed_subindustries": removed_subindustries,
        "renamed_layers": [],
        "renamed_subindustries": [],
        "structural_change_detected": structural_change_detected,
        "structural_change_blocking_errors": (
            ["taxonomy structural changes require an explicit structural replacement workflow"]
            if structural_change_detected
            else []
        ),
    }


def _expected_counts(proposed_taxonomy_csv: str | Path, proposed_taxonomy_version: str) -> dict[str, int]:
    summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    group_count = summary.layer_count + summary.subindustry_count + 1
    return {
        "ticker_rows": summary.ticker_count,
        "group_rows": group_count,
        "synthetic_ohlc_rows": group_count,
        "index_rows": group_count,
        "taxonomy_rows": summary.row_count,
        "membership_rows": summary.membership_count,
    }


def build_taxonomy_change_plan(
    *,
    deployment_id: int | None,
    ecosystem_code: str,
    current_taxonomy_version: str,
    current_taxonomy_csv: str | Path,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    date_from: str,
    date_to: str,
    rebuild_mode: str = REBUILD_MODE_FULL,
    backup_policy: str = "ONE_FULL_BACKUP_PER_DEPLOYMENT",
) -> dict[str, object]:
    current_summary = summarize_taxonomy_csv(current_taxonomy_csv, current_taxonomy_version)
    proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    diff = build_taxonomy_diff(
        current_taxonomy_csv=current_taxonomy_csv,
        current_taxonomy_version=current_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
    )
    blocking_errors = list(diff["structural_change_blocking_errors"])
    if rebuild_mode not in {REBUILD_MODE_FULL, REBUILD_MODE_DELTA}:
        blocking_errors.append(f"unsupported rebuild mode: {rebuild_mode}")
    elif rebuild_mode not in SUPPORTED_REBUILD_MODES:
        blocking_errors.append(f"rebuild mode is not supported yet: {rebuild_mode}")
    plan_payload = {
        "deployment_id": deployment_id,
        "ecosystem_code": ecosystem_code,
        "current_taxonomy_version": current_taxonomy_version,
        "current_source_sha256": current_summary.source_sha256,
        "current_source_reference": str(current_taxonomy_csv),
        "proposed_taxonomy_version": proposed_taxonomy_version,
        "proposed_source_sha256": proposed_summary.source_sha256,
        "proposed_source_reference": str(proposed_taxonomy_csv),
        "rebuild_mode": rebuild_mode,
        "date_from": date_from,
        "date_to": date_to,
        "taxonomy_diff": diff,
        "expected_counts": _expected_counts(proposed_taxonomy_csv, proposed_taxonomy_version),
        "backup_policy": backup_policy,
        "phase_sequence": list(PHASE_SEQUENCE),
        "full_rebuild_supported": True,
        "delta_rebuild_supported": False,
    }
    plan_payload["plan_hash"] = _json_hash(plan_payload)
    plan_payload["plan_status"] = "READY" if not blocking_errors else "BLOCKED"
    plan_payload["blocking_errors"] = sorted(set(blocking_errors))
    return plan_payload


def _scheduler_matches_current(
    *,
    scheduler_config_path: str | Path | None,
    current_taxonomy_version: str,
) -> tuple[bool, list[str], dict[str, object]]:
    if scheduler_config_path is None:
        return True, [], {"scheduler_config_checked": False}
    try:
        config = read_scheduler_config(str(scheduler_config_path))
        validate_scheduler_config(config)
    except Exception as exc:
        return False, [f"scheduler config invalid: {exc}"], {"scheduler_config_checked": True}
    errors = []
    if config.datacenter_taxonomy_version != current_taxonomy_version:
        errors.append("scheduler Datacenter taxonomy does not match current active taxonomy")
    if config.ec_source_layer_taxonomy_version != current_taxonomy_version:
        errors.append("scheduler EC taxonomy does not match current active taxonomy")
    summary = {
        "scheduler_config_checked": True,
        "datacenter_taxonomy_version": config.datacenter_taxonomy_version,
        "ec_source_layer_taxonomy_version": config.ec_source_layer_taxonomy_version,
    }
    return not errors, errors, summary


def prepare_taxonomy_change(
    *,
    analysis_db: str | Path,
    proposed_taxonomy_csv: str | Path,
    ecosystem_code: str = DATACENTER_ECOSYSTEM_CODE,
    date_from: str = DEFAULT_DATACENTER_REBUILD_START_DATE,
    date_to: str,
    scheduler_config_path: str | Path | None = None,
    watchlist_path: str | Path | None = None,
    evidence_root: str | Path = "temp",
    rebuild_mode: str = REBUILD_MODE_FULL,
    create_deployment: bool = True,
) -> dict[str, object]:
    blocking_errors: list[str] = []
    proposed_taxonomy_version = _taxonomy_version_from_csv(proposed_taxonomy_csv)
    conn = _connect_readonly(analysis_db)
    try:
        active = _active_taxonomy(conn, ecosystem_code=ecosystem_code)
        if active is None:
            return {
                "prepare_status": "BLOCKED",
                "blocking_errors": ["active taxonomy is missing"],
            }
        current_taxonomy_version = str(active["taxonomy_version_code"])
        current_taxonomy_csv = str(active["source_reference"])
        if proposed_taxonomy_version == current_taxonomy_version:
            blocking_errors.append("proposed taxonomy version must differ from active taxonomy")
        if not Path(current_taxonomy_csv).is_file():
            blocking_errors.append("active taxonomy source reference is not readable")
        proposed_hash = _sha256(proposed_taxonomy_csv)
        existing_deployment = _deployment_for_source(
            conn,
            ecosystem_code=ecosystem_code,
            proposed_taxonomy_version=proposed_taxonomy_version,
            proposed_source_hash=proposed_hash,
        )
    finally:
        conn.close()

    scheduler_ok, scheduler_errors, scheduler_summary = _scheduler_matches_current(
        scheduler_config_path=scheduler_config_path,
        current_taxonomy_version=current_taxonomy_version,
    )
    if not scheduler_ok:
        blocking_errors.extend(scheduler_errors)
    if watchlist_path is not None and not Path(watchlist_path).is_file():
        blocking_errors.append("watchlist path is not readable")
    if not Path(evidence_root).exists():
        Path(evidence_root).mkdir(parents=True, exist_ok=True)

    plan = build_taxonomy_change_plan(
        deployment_id=(
            int(existing_deployment["taxonomy_change_id"])
            if existing_deployment is not None
            else None
        ),
        ecosystem_code=ecosystem_code,
        current_taxonomy_version=current_taxonomy_version,
        current_taxonomy_csv=current_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        date_from=date_from,
        date_to=date_to,
        rebuild_mode=rebuild_mode,
    )
    blocking_errors.extend(plan["blocking_errors"])
    if blocking_errors or not create_deployment:
        return {
            "prepare_status": "BLOCKED" if blocking_errors else "PLAN_READY",
            "deployment_id": plan["deployment_id"],
            "normalized_orchestration_status": "BLOCKED" if blocking_errors else "PLANNED",
            "plan": plan,
            "scheduler": scheduler_summary,
            "blocking_errors": sorted(set(blocking_errors)),
        }

    if existing_deployment is None:
        apply_summary = apply_datacenter_taxonomy_version(
            analysis_db=analysis_db,
            current_taxonomy_version=current_taxonomy_version,
            current_taxonomy_csv=current_taxonomy_csv,
            proposed_taxonomy_version=proposed_taxonomy_version,
            proposed_taxonomy_csv=proposed_taxonomy_csv,
            confirm_proposed_taxonomy_version=proposed_taxonomy_version,
            ecosystem_code=ecosystem_code,
            invocation_source="DATACENTER_TAXONOMY_CHANGE_ORCHESTRATOR_V1",
            rebuild_start_date=date_from,
        )
        if apply_summary.get("taxonomy_apply_status") == "BLOCKED":
            return {
                "prepare_status": "BLOCKED",
                "normalized_orchestration_status": "BLOCKED",
                "plan": plan,
                "blocking_errors": apply_summary.get("blocking_errors", []),
            }
        conn = _connect_readonly(analysis_db)
        try:
            existing_deployment = _deployment_for_source(
                conn,
                ecosystem_code=ecosystem_code,
                proposed_taxonomy_version=proposed_taxonomy_version,
                proposed_source_hash=proposed_hash,
            )
        finally:
            conn.close()
    else:
        apply_summary = {"taxonomy_apply_status": "NO_CHANGE", "deployment_reused": True}

    deployment_id = int(existing_deployment["taxonomy_change_id"])
    plan = build_taxonomy_change_plan(
        deployment_id=deployment_id,
        ecosystem_code=ecosystem_code,
        current_taxonomy_version=current_taxonomy_version,
        current_taxonomy_csv=current_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        date_from=date_from,
        date_to=date_to,
        rebuild_mode=rebuild_mode,
    )
    return {
        "prepare_status": "READY_TO_REBUILD",
        "normalized_orchestration_status": "PLANNED",
        "deployment_id": deployment_id,
        "deployment_reused": bool(apply_summary.get("deployment_reused", False)),
        "plan_hash": plan["plan_hash"],
        "plan": plan,
        "scheduler": scheduler_summary,
        "blocking_errors": [],
    }


def _verify_confirmation(
    *,
    plan: dict[str, object],
    confirm_deployment_id: int,
    confirm_proposed_taxonomy_version: str,
    confirm_proposed_source_hash: str,
    confirm_date_from: str,
    confirm_date_to: str,
    confirm_rebuild_mode: str,
    confirm_plan_hash: str,
) -> list[str]:
    checks = {
        "deployment_id": int(plan["deployment_id"]) == confirm_deployment_id,
        "proposed_taxonomy_version": plan["proposed_taxonomy_version"] == confirm_proposed_taxonomy_version,
        "proposed_source_sha256": plan["proposed_source_sha256"] == confirm_proposed_source_hash,
        "date_from": plan["date_from"] == confirm_date_from,
        "date_to": plan["date_to"] == confirm_date_to,
        "rebuild_mode": plan["rebuild_mode"] == confirm_rebuild_mode,
        "plan_hash": plan["plan_hash"] == confirm_plan_hash,
    }
    return [f"confirmation mismatch: {key}" for key, ok in checks.items() if not ok]


def _phase_result(status: str, **values: object) -> dict[str, object]:
    return {"status": status, **values}


def inspect_taxonomy_change(
    *,
    analysis_db: str | Path,
    deployment_id: int,
    scheduler_config_path: str | Path | None = None,
) -> dict[str, object]:
    conn = _connect_readonly(analysis_db)
    try:
        deployment = _deployment_by_id(conn, deployment_id=deployment_id)
        if deployment is None:
            return {
                "inspect_status": "NOT_FOUND",
                "normalized_orchestration_status": "BLOCKED",
                "blocking_errors": ["deployment not found"],
            }
        active = _active_taxonomy(conn, ecosystem_code=str(deployment["ecosystem_code"]))
        proposed = _loaded_taxonomy(
            conn,
            ecosystem_code=str(deployment["ecosystem_code"]),
            taxonomy_version_code=str(deployment["proposed_taxonomy_version"]),
        )
        dc_heads = {}
        for table, date_col in CANONICAL_DC_FACT_TABLES:
            if table in _table_names(conn):
                row = conn.execute(
                    f"SELECT COUNT(*) AS rows, MAX({date_col}) AS head FROM {table} WHERE taxonomy_version = ?",
                    (deployment["proposed_taxonomy_version"],),
                ).fetchone()
                dc_heads[table] = dict(row)
        ec_heads = {}
        taxonomy_version_id = int(proposed["taxonomy_version_id"]) if proposed is not None else None
        if taxonomy_version_id is not None:
            for table in CANONICAL_EC_FACT_TABLES:
                if table in _table_names(conn):
                    row = conn.execute(
                        f"SELECT COUNT(*) AS rows, MAX(signal_date) AS head FROM {table} WHERE taxonomy_version_id = ?",
                        (taxonomy_version_id,),
                    ).fetchone()
                    ec_heads[table] = dict(row)
        watermark_rows = []
        if "ec_pipeline_watermark" in _table_names(conn):
            watermark_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT ecosystem_id, pipeline_name, source_table, taxonomy_version_id,
                           latest_signal_date, status
                    FROM ec_pipeline_watermark
                    ORDER BY pipeline_name, source_table, taxonomy_version_id
                    """
                )
            ]
    finally:
        conn.close()

    status = _normalize_deployment_status(deployment)
    safe_next_action = _safe_next_action(status)
    scheduler = {}
    if scheduler_config_path is not None:
        config = read_scheduler_config(str(scheduler_config_path))
        scheduler = {
            "datacenter_taxonomy_version": config.datacenter_taxonomy_version,
            "ec_source_layer_taxonomy_version": config.ec_source_layer_taxonomy_version,
        }
    return {
        "inspect_status": "OK",
        "deployment_id": deployment_id,
        "deployment": deployment,
        "normalized_orchestration_status": status,
        "active_taxonomy": active,
        "proposed_taxonomy": proposed,
        "rebuild_mode": REBUILD_MODE_FULL,
        "date_range": {
            "date_from": deployment.get("rebuild_start_date"),
            "date_to": _max_head(ec_heads),
        },
        "backup_state": _backup_state(deployment),
        "per_phase_status": _phase_statuses(deployment),
        "fact_heads": {"dc": dc_heads, "ec": ec_heads},
        "watermark_state": {
            "canonical_scopes": list(CANONICAL_EC_WATERMARK_SCOPES),
            "rows": watermark_rows,
        },
        "activation_readiness": {
            "status": deployment.get("status"),
            "activation_status": deployment.get("activation_status"),
            "coverage_status": deployment.get("coverage_status"),
            "parity_status": deployment.get("parity_status"),
        },
        "scheduler": scheduler,
        "safe_next_action": safe_next_action,
        "blocking_errors": [],
    }


def _max_head(heads: dict[str, dict[str, object]]) -> str | None:
    values = [str(row["head"]) for row in heads.values() if row.get("head") is not None]
    return max(values) if values else None


def _backup_state(deployment: dict[str, object]) -> dict[str, object]:
    evidence = deployment.get("rebuild_evidence_json")
    if not evidence:
        return {"backup_status": "UNKNOWN"}
    try:
        payload = json.loads(str(evidence))
    except json.JSONDecodeError:
        return {"backup_status": "UNPARSEABLE"}
    return {
        "backup_status": payload.get("backup_validation_status", "UNKNOWN"),
        "backup_path": payload.get("backup_path"),
    }


def _phase_statuses(deployment: dict[str, object]) -> dict[str, object]:
    return {
        "metadata": deployment.get("status"),
        "dc_rebuild": deployment.get("dc_rebuild_status"),
        "ec_rebuild": deployment.get("ec_rebuild_status"),
        "coverage": deployment.get("coverage_status"),
        "parity": deployment.get("parity_status"),
        "activation": deployment.get("activation_status"),
    }


def _normalize_deployment_status(deployment: dict[str, object]) -> str:
    if deployment.get("activation_status") == "ACTIVE" or deployment.get("status") == "ACTIVE":
        return "ACTIVE"
    if deployment.get("status") == "READY_TO_ACTIVATE":
        return "READY_TO_ACTIVATE"
    if deployment.get("ec_rebuild_status") == "FAILED":
        return "REBUILD_FAILED"
    if deployment.get("dc_rebuild_status") == "FAILED":
        return "REBUILD_FAILED"
    if deployment.get("coverage_status") == "FAILED" or deployment.get("parity_status") == "FAILED":
        return "VALIDATION_FAILED"
    if deployment.get("status") == "REBUILD_IN_PROGRESS":
        return "REBUILDING"
    if deployment.get("status") == "LOADED_NOT_ACTIVE":
        return "PLANNED"
    if deployment.get("status") in FAILURE_STATES:
        return str(deployment["status"])
    return "DRAFT"


def _safe_next_action(status: str) -> str:
    return {
        "DRAFT": "prepare",
        "PLANNED": "execute_rebuild",
        "REBUILDING": "inspect_or_resume",
        "REBUILD_FAILED": "resume_from_failed_phase",
        "VALIDATION_FAILED": "validation_only_recovery",
        "READY_TO_ACTIVATE": "inspect_activation_plan",
        "ACTIVE": "no_change",
    }.get(status, "inspect")


def execute_taxonomy_rebuild(
    *,
    analysis_db: str | Path,
    deployment_id: int,
    proposed_taxonomy_csv: str | Path,
    date_to: str,
    scheduler_config_path: str | Path | None = None,
    watchlist_path: str | Path | None = None,
    evidence_root: str | Path = "temp",
    confirm_deployment_id: int,
    confirm_proposed_taxonomy_version: str,
    confirm_proposed_source_hash: str,
    confirm_date_from: str,
    confirm_date_to: str,
    confirm_rebuild_mode: str,
    confirm_plan_hash: str,
    services: TaxonomyChangeServices | None = None,
) -> dict[str, object]:
    services = services or TaxonomyChangeServices()
    inspection = inspect_taxonomy_change(
        analysis_db=analysis_db,
        deployment_id=deployment_id,
        scheduler_config_path=scheduler_config_path,
    )
    status = inspection["normalized_orchestration_status"]
    if status == "ACTIVE":
        return {"run_status": "ALREADY_ACTIVE", "activation_executed": False, "inspection": inspection}
    if status == "READY_TO_ACTIVATE":
        return {"run_status": "NO_CHANGE_READY_TO_ACTIVATE", "activation_executed": False, "inspection": inspection}

    deployment = inspection["deployment"]
    current_version = str(deployment["previous_taxonomy_version"])
    current_csv = _current_source_from_db(analysis_db, ecosystem_code=str(deployment["ecosystem_code"]), taxonomy_version=current_version)
    plan = build_taxonomy_change_plan(
        deployment_id=deployment_id,
        ecosystem_code=str(deployment["ecosystem_code"]),
        current_taxonomy_version=current_version,
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        date_from=str(deployment["rebuild_start_date"]),
        date_to=date_to,
        rebuild_mode=confirm_rebuild_mode,
    )
    confirmation_errors = _verify_confirmation(
        plan=plan,
        confirm_deployment_id=confirm_deployment_id,
        confirm_proposed_taxonomy_version=confirm_proposed_taxonomy_version,
        confirm_proposed_source_hash=confirm_proposed_source_hash,
        confirm_date_from=confirm_date_from,
        confirm_date_to=confirm_date_to,
        confirm_rebuild_mode=confirm_rebuild_mode,
        confirm_plan_hash=confirm_plan_hash,
    )
    if confirmation_errors or plan["blocking_errors"]:
        return _failure(
            failed_phase="PLANNED",
            failure_code="CONFIRMATION_FAILED",
            failure_message="; ".join(confirmation_errors + list(plan["blocking_errors"])),
            completed_phases=[],
            resume_from_phase="PLANNED",
            scheduler_guard_restored=True,
        )

    if _missing_services(services):
        return _failure(
            failed_phase="REBUILDING",
            failure_code="EXECUTION_SERVICES_NOT_CONFIGURED",
            failure_message="unified rebuild execution requires injected production services",
            completed_phases=["PLANNED"],
            resume_from_phase=_resume_from_status(status),
            scheduler_guard_restored=True,
        )

    completed: list[str] = ["PLANNED"]
    try:
        _call_phase(services.set_scheduler_guard, "scheduler_guard", enabled=True)
        writer = _call_phase(services.verify_active_writer, "active_writer_check")
        if writer.get("status") not in {"OK", "NO_ACTIVE_WRITER"}:
            return _failure("REBUILDING", "ACTIVE_WRITER", str(writer), completed, "REBUILDING", True)
        _call_phase(services.ensure_backup, "backup", deployment_id=deployment_id)
        completed.append("BACKUP")
        _call_phase(services.run_dc_rebuild, "dc_rebuild", plan=plan)
        completed.append("DC_REBUILD")
        _call_phase(services.run_ec_rebuild, "ec_rebuild", plan=plan)
        completed.append("EC_REBUILD")
        cleanup = plan_ec_taxonomy_replacement_cleanup(
            db=analysis_db,
            ecosystem=str(deployment["ecosystem_code"]),
            target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            deployment_id=deployment_id,
            date_from=str(deployment["rebuild_start_date"]),
            date_to=date_to,
            scheduler_config=scheduler_config_path,
            expected_scheduler_taxonomy_version=current_version,
        )
        completed.append("CLEANUP_PLANNED" if cleanup.get("safe_to_apply") else "CLEANUP_BLOCKED")
        validation = finalize_ec_taxonomy_rebuild_validation(
            db=analysis_db,
            ecosystem=str(deployment["ecosystem_code"]),
            target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            taxonomy_csv=proposed_taxonomy_csv,
            deployment_id=deployment_id,
            date_from=str(deployment["rebuild_start_date"]),
            date_to=date_to,
            finalize_watermarks=False,
            update_deployment_evidence=False,
        )
        completed.append("VALIDATED" if validation.get("finalization_status") == "OK" else "VALIDATION_BLOCKED")
        activation_plan = _plan_activation(
            analysis_db=analysis_db,
            ecosystem_code=str(deployment["ecosystem_code"]),
            deployment_id=deployment_id,
            current_taxonomy_version=current_version,
            current_taxonomy_csv=current_csv,
            proposed_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            proposed_taxonomy_csv=proposed_taxonomy_csv,
            required_signal_date=date_to,
            scheduler_config_path=scheduler_config_path,
        )
        return {
            "run_status": "READY_TO_ACTIVATE" if activation_plan.get("safe_to_activate") else "VALIDATION_FAILED",
            "activation_executed": False,
            "completed_phases": completed,
            "activation_plan": activation_plan,
            "cleanup_plan": cleanup,
            "validation": validation,
        }
    finally:
        if services.set_scheduler_guard is not None:
            services.set_scheduler_guard(enabled=False)


def _current_source_from_db(
    analysis_db: str | Path,
    *,
    ecosystem_code: str,
    taxonomy_version: str,
) -> str:
    conn = _connect_readonly(analysis_db)
    try:
        loaded = _loaded_taxonomy(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version,
        )
        if loaded is None:
            raise ValueError("current taxonomy metadata is missing")
        return str(loaded["source_reference"])
    finally:
        conn.close()


def _missing_services(services: TaxonomyChangeServices) -> bool:
    return any(
        service is None
        for service in (
            services.set_scheduler_guard,
            services.verify_active_writer,
            services.ensure_backup,
            services.run_dc_rebuild,
            services.run_ec_rebuild,
        )
    )


def _call_phase(func: Callable[..., dict[str, object]] | None, phase: str, **kwargs: object) -> dict[str, object]:
    if func is None:
        raise RuntimeError(f"phase service is not configured: {phase}")
    result = func(**kwargs)
    if result.get("status") not in {"OK", "NO_ACTIVE_WRITER", "NO_CHANGE"}:
        raise RuntimeError(f"phase failed: {phase}: {result}")
    return result


def _resume_from_status(status: str) -> str:
    return {
        "PLANNED": "REBUILDING",
        "REBUILD_FAILED": "REBUILDING",
        "VALIDATION_FAILED": "VALIDATING",
    }.get(status, "PLANNED")


def _failure(
    failed_phase: str,
    failure_code: str,
    failure_message: str,
    completed_phases: list[str],
    resume_from_phase: str,
    scheduler_guard_restored: bool,
) -> dict[str, object]:
    return {
        "run_status": "FAILED",
        "failed_phase": failed_phase,
        "failure_code": failure_code,
        "failure_message": failure_message,
        "completed_phases": completed_phases,
        "resume_from_phase": resume_from_phase,
        "retry_safe": True,
        "restore_required": False,
        "cleanup_required": failed_phase in {"VALIDATING"},
        "current_taxonomy_remains_active": True,
        "scheduler_guard_restored": scheduler_guard_restored,
    }


def plan_taxonomy_activation(**kwargs: object) -> dict[str, object]:
    return _plan_activation(**kwargs)


def activate_taxonomy_change(**kwargs: object) -> dict[str, object]:
    return apply_datacenter_taxonomy_activation(**kwargs)


def build_prepare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a unified Datacenter taxonomy change deployment")
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ecosystem", default=DATACENTER_ECOSYSTEM_CODE)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--date-from", default=DEFAULT_DATACENTER_REBUILD_START_DATE)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--scheduler-config")
    parser.add_argument("--watchlist")
    parser.add_argument("--evidence-root", default="temp")
    parser.add_argument("--rebuild-mode", default=REBUILD_MODE_FULL)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def build_inspect_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect a Datacenter taxonomy change deployment")
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--deployment-id", required=True, type=int)
    parser.add_argument("--scheduler-config")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the unified Datacenter taxonomy change rebuild workflow")
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--deployment-id", required=True, type=int)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--scheduler-config")
    parser.add_argument("--watchlist")
    parser.add_argument("--evidence-root", default="temp")
    parser.add_argument("--confirm-deployment-id", required=True, type=int)
    parser.add_argument("--confirm-proposed-taxonomy-version", required=True)
    parser.add_argument("--confirm-proposed-source-hash", required=True)
    parser.add_argument("--confirm-date-from", required=True)
    parser.add_argument("--confirm-date-to", required=True)
    parser.add_argument("--confirm-rebuild-mode", required=True)
    parser.add_argument("--confirm-plan-hash", required=True)
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def print_json(summary: dict[str, object]) -> None:
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
