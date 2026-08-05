from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from analysis.datacenter_indices.swing_pipeline_orchestrator import run_datacenter_swing_pipeline
from analysis.datacenter_indices.taxonomy import DatacenterTaxonomyRow, load_datacenter_taxonomy_csv
from rawcandle.ec_taxonomy_full_rebuild_orchestrator import run_ec_taxonomy_full_rebuild
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
from rawcandle.scheduler.runner import read_scheduler_status, _resolve_datacenter_post_step_config


REBUILD_MODE_FULL = "FULL_REBUILD"
REBUILD_MODE_DELTA = "DELTA_REBUILD"
REBUILD_MODE_AUTO = "AUTO"
CHANGE_EXECUTION_FULL_REBUILD = "FULL_REBUILD"
CHANGE_EXECUTION_DELTA_REBUILD = "DELTA_REBUILD"
CHANGE_EXECUTION_REPORT_STATUS_ONLY = "REPORT_STATUS_ONLY"
TAXONOMY_FIELD_DEPENDENCIES = {
    "taxonomy_version": "IDENTITY",
    "ticker": "IDENTITY",
    "layer": "IDENTITY",
    "subindustry": "IDENTITY",
    "is_primary": "COMPUTATIONAL",
    "role_weight": "COMPUTATIONAL",
    "report_group_status": "REPORTING_ONLY",
    "notes": "DOCUMENTATION_ONLY",
}
REPORT_STATUS_ONLY_ALLOWED_CHANGED_FIELDS = {
    "taxonomy_version",
    "report_group_status",
    "notes",
}
SUPPORTED_REBUILD_MODES = {REBUILD_MODE_FULL, REBUILD_MODE_DELTA}
REBUILD_MODE_ALIASES = {
    "auto": REBUILD_MODE_AUTO,
    "AUTO": REBUILD_MODE_AUTO,
    "full": REBUILD_MODE_FULL,
    "FULL": REBUILD_MODE_FULL,
    "FULL_REBUILD": REBUILD_MODE_FULL,
    "delta": REBUILD_MODE_DELTA,
    "DELTA": REBUILD_MODE_DELTA,
    "DELTA_REBUILD": REBUILD_MODE_DELTA,
}
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


def _utc_operation_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_production_taxonomy_change_services(
    *,
    scheduler_config_path: str | Path,
    evidence_root: str | Path = "temp",
    resume: bool = False,
    dc_pipeline_runner: Callable[..., dict[str, object]] = run_datacenter_swing_pipeline,
    ec_rebuild_runner: Callable[..., dict[str, object]] = run_ec_taxonomy_full_rebuild,
) -> TaxonomyChangeServices:
    config_path = str(scheduler_config_path)
    previous_skip_next_run: list[bool | None] = [None]
    backup_summary: dict[str, object] = {}

    def _set_scheduler_guard(*, enabled: bool) -> dict[str, object]:
        config = read_scheduler_config(config_path)
        if previous_skip_next_run[0] is None:
            previous_skip_next_run[0] = bool(config.skip_next_run)
        config.skip_next_run = True if enabled else bool(previous_skip_next_run[0])
        write_scheduler_config(config_path, config)
        return {
            "status": "OK",
            "guard_enabled": enabled,
            "skip_next_run": config.skip_next_run,
            "restored_previous_value": (not enabled),
        }

    def _verify_active_writer(**_kwargs: object) -> dict[str, object]:
        config = read_scheduler_config(config_path)
        status = read_scheduler_status(config.log_dir)
        if status and bool(status.get("is_running")):
            return {
                "status": "ACTIVE_WRITER",
                "scheduler_status": status,
            }
        return {
            "status": "NO_ACTIVE_WRITER",
            "scheduler_status": status,
        }

    def _ensure_backup(*, deployment_id: int, **_kwargs: object) -> dict[str, object]:
        if backup_summary:
            return {"status": "OK", "backup_reused": True, **backup_summary}
        config = read_scheduler_config(config_path)
        backup_dir = Path(config.ec_source_layer_backup_dir or evidence_root) / "taxonomy_change_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        source_db = Path(config.analysis_db_path)
        backup_path = backup_dir / (
            f"analysis_taxonomy_change_{deployment_id}_{_utc_operation_timestamp()}.sqlite"
        )
        src = sqlite3.connect(str(source_db))
        try:
            dst = sqlite3.connect(str(backup_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        backup_summary.update(
            {
                "backup_path": str(backup_path),
                "backup_sha256": _sha256(backup_path),
                "backup_mode": "SQLITE_BACKUP",
            }
        )
        return {"status": "OK", "backup_reused": False, **backup_summary}

    def _run_dc_rebuild(*, plan: dict[str, object], **_kwargs: object) -> dict[str, object]:
        if plan.get("change_execution_class") == CHANGE_EXECUTION_REPORT_STATUS_ONLY:
            return {
                "status": "OK",
                "dc_rebuild_skipped": True,
                "skip_reason": CHANGE_EXECUTION_REPORT_STATUS_ONLY,
                **_no_computation_evidence(),
            }
        config = read_scheduler_config(config_path)
        resolved = _resolve_datacenter_post_step_config("usa", config)
        if resolved is None:
            return {"status": "FAILED", "error": "Datacenter post-step config is unavailable"}
        expected = dict(plan.get("expected_counts") or {})
        result = dc_pipeline_runner(
            price_db=Path(config.osakedata_db_path),
            analysis_db=Path(config.analysis_db_path),
            taxonomy_csv=Path(str(plan["proposed_source_reference"])),
            taxonomy_version=str(plan["proposed_taxonomy_version"]),
            market=resolved.market,
            signal_date=str(plan["date_to"]),
            start_date=str(plan["date_from"]),
            index_base_date=resolved.index_base_date,
            output_dir=Path(resolved.output_dir),
            expected_ticker_count=int(expected.get("ticker_rows") or resolved.expected_ticker_count),
            expected_group_count=int(expected.get("group_rows") or resolved.expected_group_count),
            expected_synthetic_ohlc_count=int(
                expected.get("synthetic_ohlc_rows") or resolved.expected_synthetic_ohlc_count
            ),
            watchlist_file=Path(config.ec_source_layer_watchlist or resolved.watchlist_file),
            skip_reports=True,
            windows_report_copy_enabled=False,
            no_technical_relevance=True,
            stage2_incremental=False,
        )
        summary = dict(result.get("summary") or {})
        status = "OK" if summary.get("pipeline_status") == "OK" else "FAILED"
        return {
            "status": status,
            "pipeline_status": summary.get("pipeline_status"),
            "audit_validation_status": summary.get("audit_validation_status"),
            "summary": summary,
        }

    def _run_ec_rebuild(*, plan: dict[str, object], **_kwargs: object) -> dict[str, object]:
        config = read_scheduler_config(config_path)
        existing_backup_path = str(backup_summary.get("backup_path") or "")
        result = ec_rebuild_runner(
            db_path=config.analysis_db_path,
            ecosystem_code=str(plan["ecosystem_code"]),
            taxonomy_version_code=str(plan["proposed_taxonomy_version"]),
            taxonomy_csv_path=str(plan["proposed_source_reference"]),
            watchlist_path=str(config.ec_source_layer_watchlist or ""),
            deployment_id=int(plan["deployment_id"]),
            date_from=str(plan["date_from"]),
            date_to=str(plan["date_to"]),
            backup_dir=str(config.ec_source_layer_backup_dir or Path(evidence_root) / "backups"),
            evidence_output_root=str(Path(evidence_root) / "ec_taxonomy_full_rebuild"),
            confirm_db=config.analysis_db_path,
            confirm_ecosystem=str(plan["ecosystem_code"]),
            confirm_taxonomy_version=str(plan["proposed_taxonomy_version"]),
            confirm_deployment_id=int(plan["deployment_id"]),
            confirm_date_from=str(plan["date_from"]),
            confirm_date_to=str(plan["date_to"]),
            existing_backup_path=existing_backup_path or None,
            confirm_existing_backup_path=existing_backup_path or None,
            expected_active_taxonomy_version=str(plan["current_taxonomy_version"]),
            scheduler_config_path=config_path,
            resume=resume,
            finalize_after_rebuild=False,
            require_cleanup_evidence_for_whole_range=True,
        )
        return {
            "status": "OK"
            if result.get("overall_status") in {"REBUILD_COMPLETED", "FACTS_CONSTRUCTED"}
            else "FAILED",
            "overall_status": result.get("overall_status"),
            "retry_required": result.get("retry_required"),
            "watermark_finalization_performed": result.get("watermark_finalization_performed"),
            "summary": result,
        }

    return TaxonomyChangeServices(
        set_scheduler_guard=_set_scheduler_guard,
        verify_active_writer=_verify_active_writer,
        ensure_backup=_ensure_backup,
        run_dc_rebuild=_run_dc_rebuild,
        run_ec_rebuild=_run_ec_rebuild,
    )


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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    if table_name not in _table_names(conn):
        return []
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


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


def _group_keys(row: DatacenterTaxonomyRow) -> tuple[str, str]:
    return (f"layer:{row.layer}", f"subindustry:{row.subindustry}")


def _primary_by_ticker(rows: list[DatacenterTaxonomyRow]) -> dict[str, DatacenterTaxonomyRow]:
    return {row.ticker: row for row in rows if row.is_primary}


def _secondary_groups_by_ticker(rows: list[DatacenterTaxonomyRow]) -> dict[str, list[str]]:
    result: dict[str, set[str]] = {}
    for row in rows:
        if not row.is_primary:
            result.setdefault(row.ticker, set()).update(_group_keys(row))
    return {ticker: sorted(groups) for ticker, groups in sorted(result.items())}


def _all_groups(rows: list[DatacenterTaxonomyRow]) -> set[str]:
    groups: set[str] = set()
    for row in rows:
        groups.update(_group_keys(row))
    groups.add("ecosystem:DATACENTER")
    return groups


def _normalize_rebuild_mode(value: str) -> str:
    try:
        return REBUILD_MODE_ALIASES[value]
    except KeyError as exc:
        raise ValueError(f"unsupported rebuild mode: {value}") from exc


def _range_payload(date_from: str, date_to: str) -> dict[str, str]:
    return {"date_from": date_from, "date_to": date_to}


def _compute_delta_safety(diff: dict[str, object]) -> dict[str, object]:
    reasons = list(diff["structural_change_blocking_errors"])
    if diff.get("renamed_layers"):
        reasons.append("renamed layers require full structural rebuild")
    if diff.get("renamed_subindustries"):
        reasons.append("renamed subindustries require full structural rebuild")
    return {
        "delta_safe": not reasons,
        "delta_blocking_reasons": sorted(set(str(reason) for reason in reasons)),
        "recommended_rebuild_mode": REBUILD_MODE_DELTA if not reasons else REBUILD_MODE_FULL,
    }


def _raw_taxonomy_rows_by_membership_key(
    taxonomy_csv: str | Path,
) -> tuple[list[str], dict[tuple[str, str, str, str], dict[str, str]]]:
    with Path(taxonomy_csv).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows: dict[tuple[str, str, str, str], dict[str, str]] = {}
        for raw in reader:
            key = (
                str(raw.get("ticker") or "").strip().upper(),
                str(raw.get("layer") or "").strip(),
                str(raw.get("subindustry") or "").strip(),
                str(raw.get("is_primary") or "").strip(),
            )
            rows[key] = {field: str(raw.get(field) or "").strip() for field in fieldnames}
    return fieldnames, rows


def classify_report_status_only_change(
    *,
    current_taxonomy_csv: str | Path,
    current_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    proposed_taxonomy_version: str,
    diff: dict[str, object] | None = None,
) -> dict[str, object]:
    """Classify whether a taxonomy diff is safe for metadata-only execution."""
    diff = diff or build_taxonomy_diff(
        current_taxonomy_csv=current_taxonomy_csv,
        current_taxonomy_version=current_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
    )
    current_fields, current_rows = _raw_taxonomy_rows_by_membership_key(current_taxonomy_csv)
    proposed_fields, proposed_rows = _raw_taxonomy_rows_by_membership_key(proposed_taxonomy_csv)
    blocking: list[str] = []
    if current_fields != proposed_fields:
        blocking.append("taxonomy schema changed")
    unknown_fields = sorted((set(current_fields) | set(proposed_fields)) - set(TAXONOMY_FIELD_DEPENDENCIES))
    if unknown_fields:
        blocking.append("unknown taxonomy columns present: " + ", ".join(unknown_fields))
    added_keys = sorted(set(proposed_rows) - set(current_rows))
    removed_keys = sorted(set(current_rows) - set(proposed_rows))
    if added_keys:
        blocking.append("membership rows added")
    if removed_keys:
        blocking.append("membership rows removed")
    structural_checks = {
        "added_tickers": "tickers added",
        "removed_tickers": "tickers removed",
        "added_layers": "layers added",
        "removed_layers": "layers removed",
        "renamed_layers": "layers renamed",
        "added_subindustries": "subindustries added",
        "removed_subindustries": "subindustries removed",
        "renamed_subindustries": "subindustries renamed",
        "primary_membership_changes": "primary memberships changed",
        "secondary_membership_additions": "secondary memberships added",
        "secondary_membership_removals": "secondary memberships removed",
    }
    for key, reason in structural_checks.items():
        if diff.get(key):
            blocking.append(reason)

    changed_fields: set[str] = set()
    changed_rows: list[dict[str, object]] = []
    for key in sorted(set(current_rows) & set(proposed_rows)):
        current = current_rows[key]
        proposed = proposed_rows[key]
        row_fields = sorted(
            field
            for field in set(current) | set(proposed)
            if str(current.get(field) or "") != str(proposed.get(field) or "")
        )
        if row_fields:
            changed_fields.update(row_fields)
            changed_rows.append(
                {
                    "ticker": key[0],
                    "layer": key[1],
                    "subindustry": key[2],
                    "is_primary": key[3],
                    "changed_fields": row_fields,
                }
            )
    disallowed_changed = sorted(changed_fields - REPORT_STATUS_ONLY_ALLOWED_CHANGED_FIELDS)
    if disallowed_changed:
        blocking.append("computational or unknown fields changed: " + ", ".join(disallowed_changed))
    changed_unknown = sorted(changed_fields - set(TAXONOMY_FIELD_DEPENDENCIES))
    if changed_unknown:
        blocking.append("unknown changed fields: " + ", ".join(changed_unknown))
    changed_computational = sorted(
        field
        for field in changed_fields
        if TAXONOMY_FIELD_DEPENDENCIES.get(field) in {"COMPUTATIONAL", "UNKNOWN"}
    )
    if changed_computational:
        blocking.append("computational fields changed: " + ", ".join(changed_computational))

    safe = not blocking
    return {
        "change_execution_class": (
            CHANGE_EXECUTION_REPORT_STATUS_ONLY if safe else CHANGE_EXECUTION_DELTA_REBUILD
        ),
        "report_status_only_safe": safe,
        "report_status_only_blocking_reasons": sorted(set(blocking)),
        "report_status_only_changed_row_count": len(changed_rows),
        "report_status_only_changed_ticker_count": len({str(row["ticker"]) for row in changed_rows}),
        "report_status_only_changed_fields": sorted(changed_fields),
        "report_status_only_changed_rows": changed_rows,
        "taxonomy_field_dependencies": dict(TAXONOMY_FIELD_DEPENDENCIES),
    }


def _ticker_classifications(
    *,
    current_rows: list[DatacenterTaxonomyRow],
    proposed_rows: list[DatacenterTaxonomyRow],
    diff: dict[str, object],
) -> list[dict[str, object]]:
    current_primary = _primary_by_ticker(current_rows)
    proposed_primary = _primary_by_ticker(proposed_rows)
    current_secondary = _secondary_groups_by_ticker(current_rows)
    proposed_secondary = _secondary_groups_by_ticker(proposed_rows)
    added = set(diff["added_tickers"])
    removed = set(diff["removed_tickers"])
    primary_changed = {str(item["ticker"]) for item in diff["primary_membership_changes"]}
    secondary_added = {str(item["ticker"]) for item in diff["secondary_membership_additions"]}
    secondary_removed = {str(item["ticker"]) for item in diff["secondary_membership_removals"]}
    scope_changed = {str(item["ticker"]) for item in diff["scope_flag_changes"]}
    affected_groups_by_ticker: dict[str, set[str]] = {}
    for ticker in added:
        row = proposed_primary.get(ticker)
        if row is not None:
            affected_groups_by_ticker.setdefault(ticker, set()).update(_group_keys(row))
    for ticker in removed:
        row = current_primary.get(ticker)
        if row is not None:
            affected_groups_by_ticker.setdefault(ticker, set()).update(_group_keys(row))
    for item in diff["primary_membership_changes"]:
        ticker = str(item["ticker"])
        for key in (current_primary.get(ticker), proposed_primary.get(ticker)):
            if key is not None:
                affected_groups_by_ticker.setdefault(ticker, set()).update(_group_keys(key))
    for item in list(diff["secondary_membership_additions"]) + list(diff["secondary_membership_removals"]):
        ticker = str(item["ticker"])
        affected_groups_by_ticker.setdefault(ticker, set()).update(
            (f"layer:{item['layer']}", f"subindustry:{item['subindustry']}")
        )

    classifications: list[dict[str, object]] = []
    for ticker in sorted(set(current_primary) | set(proposed_primary) | added | removed):
        change_types: list[str] = []
        if ticker in added:
            change_types.append("ADDED_TICKER")
        if ticker in removed:
            change_types.append("REMOVED_TICKER")
        if ticker in primary_changed:
            change_types.append("PRIMARY_MEMBERSHIP_CHANGED")
        if ticker in secondary_added:
            change_types.append("SECONDARY_MEMBERSHIP_ADDED")
        if ticker in secondary_removed:
            change_types.append("SECONDARY_MEMBERSHIP_REMOVED")
        if ticker in scope_changed:
            change_types.append("SCOPE_FLAG_CHANGED")
        if not change_types:
            change_types.append("UNCHANGED")
        old_primary = current_primary.get(ticker)
        new_primary = proposed_primary.get(ticker)
        if ticker in added:
            action = "REBUILD_NEW_TICKER"
        elif ticker in removed:
            action = "OMIT_REMOVED_TICKER"
        else:
            action = "COPY_UNCHANGED_TICKER_HISTORY"
        classifications.append(
            {
                "ticker": ticker,
                "change_types": change_types,
                "old_scope_flag": old_primary.report_group_status if old_primary else None,
                "new_scope_flag": new_primary.report_group_status if new_primary else None,
                "old_primary_group": (
                    {"layer": old_primary.layer, "subindustry": old_primary.subindustry}
                    if old_primary
                    else None
                ),
                "new_primary_group": (
                    {"layer": new_primary.layer, "subindustry": new_primary.subindustry}
                    if new_primary
                    else None
                ),
                "old_secondary_groups": current_secondary.get(ticker, []),
                "new_secondary_groups": proposed_secondary.get(ticker, []),
                "affected_groups": sorted(affected_groups_by_ticker.get(ticker, set())),
                "ticker_history_action": action,
            }
        )
    return classifications


def _build_delta_scope(
    *,
    current_rows: list[DatacenterTaxonomyRow],
    proposed_rows: list[DatacenterTaxonomyRow],
    diff: dict[str, object],
) -> dict[str, object]:
    current_groups = _all_groups(current_rows)
    proposed_groups = _all_groups(proposed_rows)
    affected_groups: set[str] = set()
    added = set(diff["added_tickers"])
    removed = set(diff["removed_tickers"])
    current_primary = _primary_by_ticker(current_rows)
    proposed_primary = _primary_by_ticker(proposed_rows)
    for ticker in added:
        row = proposed_primary.get(ticker)
        if row is not None:
            affected_groups.update(_group_keys(row))
    for ticker in removed:
        row = current_primary.get(ticker)
        if row is not None:
            affected_groups.update(_group_keys(row))
    for item in diff["primary_membership_changes"]:
        ticker = str(item["ticker"])
        for row in (current_primary.get(ticker), proposed_primary.get(ticker)):
            if row is not None:
                affected_groups.update(_group_keys(row))
    for item in list(diff["secondary_membership_additions"]) + list(diff["secondary_membership_removals"]):
        affected_groups.update((f"layer:{item['layer']}", f"subindustry:{item['subindustry']}"))
    if added or removed or diff["primary_membership_changes"] or diff["secondary_membership_additions"] or diff["secondary_membership_removals"]:
        affected_groups.add("ecosystem:DATACENTER")
    affected_tickers = set(diff["affected_tickers"])
    return {
        "ticker_classifications": _ticker_classifications(
            current_rows=current_rows,
            proposed_rows=proposed_rows,
            diff=diff,
        ),
        "affected_tickers": sorted(affected_tickers),
        "unaffected_tickers": sorted(set(diff["unchanged_tickers"]) - affected_tickers),
        "affected_groups": sorted(affected_groups),
        "unaffected_groups": sorted((current_groups | proposed_groups) - affected_groups),
        "added_tickers": diff["added_tickers"],
        "removed_tickers": diff["removed_tickers"],
        "membership_changed_tickers": sorted(
            {
                str(item["ticker"])
                for item in list(diff["primary_membership_changes"])
                + list(diff["secondary_membership_additions"])
                + list(diff["secondary_membership_removals"])
            }
        ),
        "scope_flag_changed_tickers": sorted({str(item["ticker"]) for item in diff["scope_flag_changes"]}),
    }


def _build_dependency_map(delta_scope: dict[str, object]) -> dict[str, object]:
    affected_groups = list(delta_scope["affected_groups"])
    affected_tickers = list(delta_scope["affected_tickers"])
    return {
        "dc_ticker_swing_signal_daily": {
            "component": "TICKER_SWING_BASE",
            "classification": "REBUILD_AFFECTED_TICKERS",
            "copy_scope": "unchanged and membership-only ticker technical rows may be carried forward with target taxonomy metadata",
            "evidence_status": "CONFIRMED_FROM_CODE",
            "affected_tickers": affected_tickers,
        },
        "dc_group_swing_signal_daily": {
            "component": "GROUP_SWING_BASE",
            "classification": "REBUILD_AFFECTED_GROUPS",
            "evidence_status": "CONFIRMED_FROM_CODE",
            "affected_groups": affected_groups,
        },
        "dc_group_synthetic_ohlc_daily": {
            "component": "SYNTHETIC_OHLC_BASE",
            "classification": "REBUILD_AFFECTED_GROUPS",
            "evidence_status": "CONFIRMED_FROM_CODE",
            "affected_groups": affected_groups,
        },
        "dc_group_index_daily": {
            "component": "GROUP_INDEX",
            "classification": "REBUILD_AFFECTED_GROUPS",
            "evidence_status": "CONFIRMED_FROM_CODE",
            "affected_groups": affected_groups,
        },
        "derived_group_components_stage5_to_stage9": {
            "classification": "REBUILD_AFFECTED_GROUPS",
            "evidence_status": "INFERRED_FROM_FLOW",
            "affected_groups": affected_groups,
        },
        "technical_relevance_and_reports": {
            "classification": "REBUILD_FULL_DATE",
            "evidence_status": "INFERRED_FROM_FLOW",
            "reason": "artifact/report context depends on canonical proposed-version outputs",
        },
        "ec_canonical_tables": {
            "classification": "REBUILD_FROM_COMPLETE_PROPOSED_DC_STATE",
            "evidence_status": "CONFIRMED_FROM_CODE",
            "target_tables": list(CANONICAL_EC_FACT_TABLES),
        },
        "coverage_parity_watermarks": {
            "classification": "REVALIDATE_ONLY",
            "evidence_status": "CONFIRMED_FROM_CODE",
        },
    }


def _build_work_estimate(
    *,
    current_rows: list[DatacenterTaxonomyRow],
    proposed_rows: list[DatacenterTaxonomyRow],
    delta_scope: dict[str, object],
    date_from: str,
    date_to: str,
) -> dict[str, object]:
    total_tickers = len({row.ticker for row in proposed_rows})
    total_groups = len(_all_groups(proposed_rows))
    affected_ticker_count = len(delta_scope["affected_tickers"])
    affected_group_count = len(delta_scope["affected_groups"])
    copied_ticker_count = max(0, total_tickers - len(delta_scope["added_tickers"]))
    copied_group_count = max(0, total_groups - affected_group_count)
    estimated_full = max(1, total_tickers + total_groups)
    estimated_rebuild = len(delta_scope["added_tickers"]) + affected_group_count
    estimated_copy = copied_ticker_count + copied_group_count
    return {
        "total_tickers": total_tickers,
        "affected_ticker_count": affected_ticker_count,
        "copied_ticker_count": copied_ticker_count,
        "rebuilt_ticker_count": len(delta_scope["added_tickers"]),
        "total_groups": total_groups,
        "affected_group_count": affected_group_count,
        "copied_group_count": copied_group_count,
        "rebuild_date_count": {"date_from": date_from, "date_to": date_to},
        "estimated_copy_row_count": estimated_copy,
        "estimated_rebuild_row_count": estimated_rebuild,
        "estimated_full_rebuild_row_count": estimated_full,
        "estimated_work_reduction_pct": round(max(0.0, 100.0 * (1.0 - (estimated_rebuild / estimated_full))), 2),
        "estimate_basis": "relative component scope, not wall-clock runtime",
    }


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
    for key in added_keys + removed_keys:
        affected_groups.add(str(key[1]))
        affected_groups.add(str(key[2]))
    for item in secondary_additions + secondary_removals:
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
    requested_rebuild_mode = _normalize_rebuild_mode(rebuild_mode)
    current_summary = summarize_taxonomy_csv(current_taxonomy_csv, current_taxonomy_version)
    proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    diff = build_taxonomy_diff(
        current_taxonomy_csv=current_taxonomy_csv,
        current_taxonomy_version=current_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
    )
    delta_safety = _compute_delta_safety(diff)
    report_status_classification = classify_report_status_only_change(
        current_taxonomy_csv=current_taxonomy_csv,
        current_taxonomy_version=current_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
        diff=diff,
    )
    selected_rebuild_mode = (
        delta_safety["recommended_rebuild_mode"]
        if requested_rebuild_mode == REBUILD_MODE_AUTO
        else requested_rebuild_mode
    )
    change_execution_class = (
        CHANGE_EXECUTION_REPORT_STATUS_ONLY
        if (
            requested_rebuild_mode == REBUILD_MODE_AUTO
            and report_status_classification["report_status_only_safe"]
        )
        else selected_rebuild_mode
    )
    blocking_errors: list[str] = []
    if selected_rebuild_mode == REBUILD_MODE_DELTA and not delta_safety["delta_safe"]:
        blocking_errors.extend(str(reason) for reason in delta_safety["delta_blocking_reasons"])
    elif selected_rebuild_mode not in SUPPORTED_REBUILD_MODES:
        blocking_errors.append(f"unsupported rebuild mode: {selected_rebuild_mode}")
    delta_scope = _build_delta_scope(
        current_rows=list(current_summary.rows),
        proposed_rows=list(proposed_summary.rows),
        diff=diff,
    )
    dependency_map = _build_dependency_map(delta_scope)
    work_estimate = _build_work_estimate(
        current_rows=list(current_summary.rows),
        proposed_rows=list(proposed_summary.rows),
        delta_scope=delta_scope,
        date_from=date_from,
        date_to=date_to,
    )
    date_ranges = {
        "ticker_history_range": _range_payload(date_from, date_to),
        "group_history_range": _range_payload(date_from, date_to),
        "downstream_history_range": _range_payload(date_from, date_to),
        "validation_range": _range_payload(date_from, date_to),
    }
    plan_payload = {
        "deployment_id": deployment_id,
        "ecosystem_code": ecosystem_code,
        "current_taxonomy_version": current_taxonomy_version,
        "current_source_sha256": current_summary.source_sha256,
        "current_source_reference": str(current_taxonomy_csv),
        "proposed_taxonomy_version": proposed_taxonomy_version,
        "proposed_source_sha256": proposed_summary.source_sha256,
        "proposed_source_reference": str(proposed_taxonomy_csv),
        "requested_rebuild_mode": requested_rebuild_mode,
        "recommended_rebuild_mode": delta_safety["recommended_rebuild_mode"],
        "selected_rebuild_mode": selected_rebuild_mode,
        "rebuild_mode": selected_rebuild_mode,
        "change_execution_class": change_execution_class,
        "report_status_only_safe": report_status_classification["report_status_only_safe"],
        "report_status_only_changed_row_count": report_status_classification[
            "report_status_only_changed_row_count"
        ],
        "report_status_only_changed_ticker_count": report_status_classification[
            "report_status_only_changed_ticker_count"
        ],
        "report_status_only_changed_fields": report_status_classification[
            "report_status_only_changed_fields"
        ],
        "report_status_only_blocking_reasons": report_status_classification[
            "report_status_only_blocking_reasons"
        ],
        "taxonomy_field_dependencies": report_status_classification["taxonomy_field_dependencies"],
        "computational_rebuild_required": change_execution_class != CHANGE_EXECUTION_REPORT_STATUS_ONLY,
        "datacenter_pipeline_required": change_execution_class != CHANGE_EXECUTION_REPORT_STATUS_ONLY,
        "stage2_required": change_execution_class != CHANGE_EXECUTION_REPORT_STATUS_ONLY,
        "date_from": date_from,
        "date_to": date_to,
        "taxonomy_diff": diff,
        "delta_safe": delta_safety["delta_safe"],
        "delta_blocking_reasons": delta_safety["delta_blocking_reasons"],
        "delta_scope_summary": delta_scope,
        "full_rebuild_scope_summary": {
            "ticker_count": proposed_summary.ticker_count,
            "layer_count": proposed_summary.layer_count,
            "subindustry_count": proposed_summary.subindustry_count,
            "date_range": _range_payload(date_from, date_to),
        },
        "date_ranges": date_ranges,
        "dependency_map": dependency_map,
        "estimated_delta_work": work_estimate,
        "estimated_full_work": {
            "total_tickers": proposed_summary.ticker_count,
            "total_groups": proposed_summary.layer_count + proposed_summary.subindustry_count + 1,
            "date_range": _range_payload(date_from, date_to),
        },
        "expected_counts": _expected_counts(proposed_taxonomy_csv, proposed_taxonomy_version),
        "backup_policy": backup_policy,
        "phase_sequence": list(PHASE_SEQUENCE),
        "full_rebuild_supported": True,
        "delta_rebuild_supported": True,
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
    resume: bool = False,
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
    normalized_confirm_rebuild_mode = _normalize_rebuild_mode(confirm_rebuild_mode)
    plan = build_taxonomy_change_plan(
        deployment_id=deployment_id,
        ecosystem_code=str(deployment["ecosystem_code"]),
        current_taxonomy_version=current_version,
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        date_from=str(deployment["rebuild_start_date"]),
        date_to=date_to,
        rebuild_mode=normalized_confirm_rebuild_mode,
    )
    if normalized_confirm_rebuild_mode in SUPPORTED_REBUILD_MODES and plan.get("plan_hash") != confirm_plan_hash:
        auto_plan = build_taxonomy_change_plan(
            deployment_id=deployment_id,
            ecosystem_code=str(deployment["ecosystem_code"]),
            current_taxonomy_version=current_version,
            current_taxonomy_csv=current_csv,
            proposed_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            proposed_taxonomy_csv=proposed_taxonomy_csv,
            date_from=str(deployment["rebuild_start_date"]),
            date_to=date_to,
            rebuild_mode=REBUILD_MODE_AUTO,
        )
        if (
            auto_plan.get("selected_rebuild_mode") == normalized_confirm_rebuild_mode
            and auto_plan.get("plan_hash") == confirm_plan_hash
        ):
            plan = auto_plan
    confirmation_errors = _verify_confirmation(
        plan=plan,
        confirm_deployment_id=confirm_deployment_id,
        confirm_proposed_taxonomy_version=confirm_proposed_taxonomy_version,
        confirm_proposed_source_hash=confirm_proposed_source_hash,
        confirm_date_from=confirm_date_from,
        confirm_date_to=confirm_date_to,
        confirm_rebuild_mode=normalized_confirm_rebuild_mode,
        confirm_plan_hash=confirm_plan_hash,
    )
    change_execution_class = str(plan.get("change_execution_class") or plan.get("selected_rebuild_mode"))
    report_status_only = change_execution_class == CHANGE_EXECUTION_REPORT_STATUS_ONLY
    if confirmation_errors or plan["blocking_errors"]:
        return _failure(
            failed_phase="PLANNED",
            failure_code="CONFIRMATION_FAILED",
            failure_message="; ".join(confirmation_errors + list(plan["blocking_errors"])),
            completed_phases=[],
            resume_from_phase="PLANNED",
            scheduler_guard_restored=True,
        )
    if report_status_only and not plan.get("report_status_only_safe"):
        return _failure(
            failed_phase="PLANNED",
            failure_code="REPORT_STATUS_ONLY_BLOCKED",
            failure_message="; ".join(str(reason) for reason in plan.get("report_status_only_blocking_reasons", [])),
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
        if plan["selected_rebuild_mode"] == REBUILD_MODE_DELTA:
            ticker_allowlist = _dc_ticker_allowlist(plan)
            group_allowlist = _dc_group_allowlist(plan)
            existing_dc_validation = (
                validate_dc_carry_forward_key_universe(
                    analysis_db=analysis_db,
                    plan=plan,
                    ticker_allowlist=ticker_allowlist,
                    group_allowlist=group_allowlist,
                )
                if resume
                else {"validation_status": "NOT_CHECKED"}
            )
            if existing_dc_validation["validation_status"] == "OK":
                carry_forward = {
                    "carry_forward_status": "OK",
                    "resume_skip": True,
                    "dc_key_universe_validation": existing_dc_validation,
                    "table_results": [],
                    "copied_ticker_count": 0,
                    "copied_group_count": 0,
                }
            else:
                carry_forward = copy_delta_carry_forward(analysis_db=analysis_db, plan=plan)
            if carry_forward.get("carry_forward_status") != "OK":
                return _failure(
                    "DC_FACTS_CARRIED_FORWARD",
                    "DELTA_CARRY_FORWARD",
                    str(carry_forward),
                    completed,
                    "DC_FACTS_CARRIED_FORWARD",
                    True,
                )
            completed.append("DELTA_CARRY_FORWARD")
            if report_status_only:
                _mark_dc_facts_validated_for_rso(
                    analysis_db=analysis_db,
                    deployment_id=deployment_id,
                    evidence={
                        "phase": "DC_FACTS_VALIDATED",
                        "change_execution_class": CHANGE_EXECUTION_REPORT_STATUS_ONLY,
                        "carry_forward": carry_forward,
                    },
                )
                completed.append("DC_FACTS_VALIDATED")
        if report_status_only:
            dc_rebuild = {
                "status": "OK",
                "dc_rebuild_skipped": True,
                "skip_reason": CHANGE_EXECUTION_REPORT_STATUS_ONLY,
                **_no_computation_evidence(),
            }
            completed.append("DC_REBUILD_SKIPPED_REPORT_STATUS_ONLY")
        else:
            dc_rebuild = _call_phase(services.run_dc_rebuild, "dc_rebuild", plan=plan)
            completed.append("DC_REBUILD")
            _mark_dc_facts_validated_for_rso(
                analysis_db=analysis_db,
                deployment_id=deployment_id,
                evidence={
                    "phase": "DC_FACTS_VALIDATED",
                    "change_execution_class": change_execution_class,
                    "dc_rebuild": dc_rebuild,
                },
            )
            completed.append("DC_FACTS_VALIDATED")
        ec_rebuild = _call_phase(services.run_ec_rebuild, "ec_rebuild", plan=plan)
        completed.append("EC_FACTS_CONSTRUCTED")
        if str(ec_rebuild.get("overall_status")) in {"FACTS_CONSTRUCTED", "REBUILD_COMPLETED"}:
            completed.append("COVERAGE_PARITY_VALIDATED")
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
        if not cleanup.get("safe_to_apply"):
            return _failure(
                "OLD_EC_CLEANED",
                "CLEANUP_BLOCKED",
                str(cleanup),
                completed,
                "OLD_EC_CLEANED",
                True,
            )
        cleanup_apply = apply_ec_taxonomy_replacement_cleanup(
            db=analysis_db,
            ecosystem=str(deployment["ecosystem_code"]),
            target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            deployment_id=deployment_id,
            date_from=str(deployment["rebuild_start_date"]),
            date_to=date_to,
            confirm_db=analysis_db,
            confirm_ecosystem=str(deployment["ecosystem_code"]),
            confirm_target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            confirm_deployment_id=deployment_id,
            confirm_date_from=str(deployment["rebuild_start_date"]),
            confirm_date_to=date_to,
            confirm_delete_candidate_hash=str(cleanup["delete_candidate_hash"]),
            scheduler_config=scheduler_config_path,
            expected_scheduler_taxonomy_version=current_version,
            invocation_source="UNIFIED_TAXONOMY_CHANGE_REBUILD",
        )
        if cleanup_apply.get("cleanup_apply_status") not in {"APPLIED", "NO_CHANGE"}:
            return _failure(
                "OLD_EC_CLEANED",
                "CLEANUP_FAILED",
                str(cleanup_apply),
                completed,
                "OLD_EC_CLEANED",
                True,
            )
        completed.append("OLD_EC_CLEANED")
        validation = finalize_ec_taxonomy_rebuild_validation(
            db=analysis_db,
            ecosystem=str(deployment["ecosystem_code"]),
            target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            taxonomy_csv=proposed_taxonomy_csv,
            deployment_id=deployment_id,
            date_from=str(deployment["rebuild_start_date"]),
            date_to=date_to,
            finalize_watermarks=True,
            update_deployment_evidence=True,
        )
        completed.append("WHOLE_RANGE_VALIDATED" if validation.get("finalization_status") == "OK" else "VALIDATION_BLOCKED")
        if validation.get("finalization_status") != "OK":
            return _failure(
                "WHOLE_RANGE_VALIDATED",
                "VALIDATION_BLOCKED",
                str(validation),
                completed,
                "WHOLE_RANGE_VALIDATED",
                True,
            )
        completed.append("WATERMARKS_FINALIZED")
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
            "change_execution_class": change_execution_class,
            "report_status_only_execution": report_status_only,
            "dc_rebuild": dc_rebuild,
            **(_no_computation_evidence() if report_status_only else {}),
            "completed_phases": completed,
            "activation_plan": activation_plan,
            "cleanup_plan": cleanup,
            "cleanup_apply": cleanup_apply,
            "validation": validation,
        }
    except Exception as exc:
        return _failure(
            failed_phase="REBUILDING",
            failure_code="PHASE_FAILED",
            failure_message=str(exc),
            completed_phases=completed,
            resume_from_phase="REBUILDING",
            scheduler_guard_restored=True,
        )
    finally:
        if services.set_scheduler_guard is not None:
            services.set_scheduler_guard(enabled=False)


def resume_taxonomy_rebuild(
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
    if services is None and scheduler_config_path is not None:
        services = build_production_taxonomy_change_services(
            scheduler_config_path=scheduler_config_path,
            evidence_root=evidence_root,
            resume=True,
        )
    summary = execute_taxonomy_rebuild(
        analysis_db=analysis_db,
        deployment_id=deployment_id,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        date_to=date_to,
        scheduler_config_path=scheduler_config_path,
        watchlist_path=watchlist_path,
        evidence_root=evidence_root,
        confirm_deployment_id=confirm_deployment_id,
        confirm_proposed_taxonomy_version=confirm_proposed_taxonomy_version,
        confirm_proposed_source_hash=confirm_proposed_source_hash,
        confirm_date_from=confirm_date_from,
        confirm_date_to=confirm_date_to,
        confirm_rebuild_mode=confirm_rebuild_mode,
        confirm_plan_hash=confirm_plan_hash,
        services=services,
        resume=True,
    )
    return {"resume_attempted": True, **summary}


def validate_and_finalize_taxonomy_rebuild(
    *,
    analysis_db: str | Path,
    deployment_id: int,
    proposed_taxonomy_csv: str | Path,
    date_to: str,
    scheduler_config_path: str | Path | None = None,
) -> dict[str, object]:
    inspection = inspect_taxonomy_change(
        analysis_db=analysis_db,
        deployment_id=deployment_id,
        scheduler_config_path=scheduler_config_path,
    )
    deployment = inspection["deployment"]
    current_version = str(deployment["previous_taxonomy_version"])
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
    cleanup_apply: dict[str, object] = {"cleanup_apply_status": "NOT_RUN"}
    if cleanup.get("safe_to_apply"):
        cleanup_apply = apply_ec_taxonomy_replacement_cleanup(
            db=analysis_db,
            ecosystem=str(deployment["ecosystem_code"]),
            target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            deployment_id=deployment_id,
            date_from=str(deployment["rebuild_start_date"]),
            date_to=date_to,
            confirm_db=analysis_db,
            confirm_ecosystem=str(deployment["ecosystem_code"]),
            confirm_target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
            confirm_deployment_id=deployment_id,
            confirm_date_from=str(deployment["rebuild_start_date"]),
            confirm_date_to=date_to,
            confirm_delete_candidate_hash=str(cleanup["delete_candidate_hash"]),
            scheduler_config=scheduler_config_path,
            expected_scheduler_taxonomy_version=current_version,
            invocation_source="UNIFIED_TAXONOMY_CHANGE_VALIDATE_FINALIZE",
        )
    validation = finalize_ec_taxonomy_rebuild_validation(
        db=analysis_db,
        ecosystem=str(deployment["ecosystem_code"]),
        target_taxonomy_version=str(deployment["proposed_taxonomy_version"]),
        taxonomy_csv=proposed_taxonomy_csv,
        deployment_id=deployment_id,
        date_from=str(deployment["rebuild_start_date"]),
        date_to=date_to,
        finalize_watermarks=True,
        update_deployment_evidence=True,
    )
    return {
        "finalize_status": (
            "READY_TO_ACTIVATE"
            if validation.get("finalization_status") == "OK"
            else "VALIDATION_FAILED"
        ),
        "cleanup_plan": cleanup,
        "cleanup_apply": cleanup_apply,
        "validation": validation,
        "activation_executed": False,
    }


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


def _no_computation_evidence() -> dict[str, object]:
    return {
        "datacenter_pipeline_called": False,
        "stage2_planner_called": False,
        "stage2_called": False,
        "ticker_calculation_called": False,
        "group_calculation_called": False,
        "synthetic_ohlc_calculation_called": False,
        "group_index_calculation_called": False,
        "downstream_calculation_called": False,
        "report_generation_called": False,
        "external_fetch_called": False,
    }


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
        "failed_component": None,
        "failed_ticker_or_group": None,
        "target_partial_state": "UNKNOWN",
        "full_fallback_available": True,
        "full_fallback_requires_new_plan": True,
        "current_taxonomy_remains_active": True,
        "scheduler_guard_restored": scheduler_guard_restored,
    }


def _sql_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"unsafe SQL identifier: {name}")
    return f'"{name}"'


def _pk_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_sql_identifier(table_name)})").fetchall()
    ordered = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0)
    return [name for _pos, name in ordered]


def _proposed_primary_metadata(proposed_taxonomy_csv: str | Path, proposed_taxonomy_version: str) -> dict[str, dict[str, str]]:
    rows = load_datacenter_taxonomy_csv(
        proposed_taxonomy_csv,
        expected_taxonomy_version=proposed_taxonomy_version,
    )
    return {
        row.ticker: {"primary_layer": row.layer, "primary_subindustry": row.subindustry}
        for row in rows
        if row.is_primary
    }


def _split_group_identity(value: str) -> tuple[str, str] | None:
    if ":" not in value:
        return None
    group_type, group_name = value.split(":", 1)
    if group_type not in {"layer", "subindustry", "ecosystem"}:
        return None
    return group_type, group_name


def _rows_hash(rows: list[dict[str, object]]) -> str:
    return _json_hash(rows)


DC_GROUP_ECOSYSTEM_AGGREGATE_KEY = "ecosystem:DC_ECOSYSTEM_TOTAL"


def _dc_ticker_allowlist(plan: dict[str, object]) -> list[str]:
    delta_scope = dict(plan["delta_scope_summary"])
    return sorted(
        set(delta_scope.get("unaffected_tickers", []))
        | (
            set(delta_scope.get("membership_changed_tickers", []))
            - set(delta_scope.get("added_tickers", []))
            - set(delta_scope.get("removed_tickers", []))
        )
        | (
            set(delta_scope.get("scope_flag_changed_tickers", []))
            - set(delta_scope.get("added_tickers", []))
            - set(delta_scope.get("removed_tickers", []))
        )
    )


def _dc_group_allowlist(plan: dict[str, object]) -> list[str]:
    delta_scope = dict(plan["delta_scope_summary"])
    groups = set(str(value) for value in delta_scope.get("unaffected_groups", []))
    if plan.get("change_execution_class") == CHANGE_EXECUTION_REPORT_STATUS_ONLY:
        groups.add(DC_GROUP_ECOSYSTEM_AGGREGATE_KEY)
    return sorted(groups)


def _dc_key_contract(
    table_name: str,
    *,
    available_columns: set[str],
    date_column: str,
) -> tuple[str, ...]:
    candidates = {
        "dc_ticker_swing_signal_daily": ("ticker", "signal_version"),
        "dc_group_swing_signal_daily": ("group_type", "group_name", "signal_version"),
        "dc_group_synthetic_ohlc_daily": ("group_type", "group_name", "calc_version"),
        "dc_group_index_daily": ("group_type", "group_name"),
    }[table_name]
    return (date_column, *(column for column in candidates if column in available_columns))


def _dc_key_class(table_name: str, row: dict[str, object], allowed_keys: set[str]) -> str:
    if table_name == "dc_ticker_swing_signal_daily":
        return "ordinary" if str(row.get("ticker") or "") in allowed_keys else "unexpected"
    group_key = f"{row.get('group_type')}:{row.get('group_name')}"
    if group_key == DC_GROUP_ECOSYSTEM_AGGREGATE_KEY and group_key in allowed_keys:
        return "ecosystem_aggregate"
    if group_key in allowed_keys:
        return "ordinary"
    return "unexpected"


def _semantic_payload(
    row: dict[str, object],
    *,
    columns: set[str],
    table_name: str,
) -> tuple[tuple[str, object], ...]:
    ignored = {"taxonomy_version", "created_at_utc", "updated_at_utc", "loaded_at_utc"}
    if table_name == "dc_ticker_swing_signal_daily":
        ignored.update({"primary_layer", "primary_subindustry"})
    return tuple(
        (column, row.get(column))
        for column in sorted(columns)
        if column not in ignored
    )


def _validate_carry_forward_table(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_column: str,
    current_taxonomy_version: str,
    proposed_taxonomy_version: str,
    date_from: str,
    date_to: str,
    allowed_keys: set[str],
) -> dict[str, object]:
    if table_name not in _table_names(conn):
        return {
            "table": table_name,
            "validation_status": "SKIPPED_TABLE_MISSING",
            "missing_target_ordinary_keys": 0,
            "missing_target_ecosystem_aggregate_keys": 0,
            "extra_target_keys": 0,
            "duplicate_keys": 0,
            "semantic_mismatch_count": 0,
            "unexpected_source_keys": [],
            "unexpected_target_keys": [],
            "mismatches": [],
        }
    columns = _table_columns(conn, table_name)
    key_columns = _dc_key_contract(table_name, available_columns=columns, date_column=date_column)
    select_sql = (
        f"SELECT {', '.join(_sql_identifier(column) for column in columns)} "
        f"FROM {_sql_identifier(table_name)} "
        f"WHERE taxonomy_version = ? AND {_sql_identifier(date_column)} BETWEEN ? AND ? "
        f"ORDER BY {', '.join(_sql_identifier(column) for column in key_columns)}"
    )
    source_rows = [
        dict(row)
        for row in conn.execute(select_sql, (current_taxonomy_version, date_from, date_to)).fetchall()
    ]
    target_rows = [
        dict(row)
        for row in conn.execute(select_sql, (proposed_taxonomy_version, date_from, date_to)).fetchall()
    ]

    def keyed(rows: list[dict[str, object]]) -> tuple[dict[tuple[object, ...], dict[str, object]], dict[str, int], list[dict[str, object]]]:
        result: dict[tuple[object, ...], dict[str, object]] = {}
        duplicate_counts: dict[str, int] = {}
        unexpected: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        for row in rows:
            key = tuple(row.get(column) for column in key_columns)
            key_class = _dc_key_class(table_name, row, allowed_keys)
            if key_class == "unexpected":
                unexpected.append({"key": list(key), "row_class": key_class})
                continue
            if key in seen:
                duplicate_counts[str(list(key))] = duplicate_counts.get(str(list(key)), 1) + 1
            seen.add(key)
            result[key] = row
        return result, duplicate_counts, unexpected

    source_by_key, source_duplicates, unexpected_source = keyed(source_rows)
    target_by_key, target_duplicates, unexpected_target = keyed(target_rows)
    missing_keys = sorted(set(source_by_key) - set(target_by_key))
    extra_keys = sorted(set(target_by_key) - set(source_by_key))
    semantic_mismatches = []
    for key in sorted(set(source_by_key) & set(target_by_key)):
        if _semantic_payload(source_by_key[key], columns=columns, table_name=table_name) != _semantic_payload(
            target_by_key[key],
            columns=columns,
            table_name=table_name,
        ):
            semantic_mismatches.append({"key": list(key), "table": table_name})
    missing_ordinary = [
        key
        for key in missing_keys
        if _dc_key_class(table_name, source_by_key[key], allowed_keys) == "ordinary"
    ]
    missing_ecosystem = [
        key
        for key in missing_keys
        if _dc_key_class(table_name, source_by_key[key], allowed_keys) == "ecosystem_aggregate"
    ]
    duplicate_total = sum(source_duplicates.values()) + sum(target_duplicates.values())
    ok = (
        not missing_ordinary
        and not missing_ecosystem
        and not extra_keys
        and duplicate_total == 0
        and not semantic_mismatches
        and not unexpected_target
    )
    return {
        "table": table_name,
        "validation_status": "OK" if ok else "BLOCKED",
        "key_columns": list(key_columns),
        "ordinary_key_count": sum(
            1 for row in source_by_key.values() if _dc_key_class(table_name, row, allowed_keys) == "ordinary"
        ),
        "ecosystem_aggregate_key_count": sum(
            1
            for row in source_by_key.values()
            if _dc_key_class(table_name, row, allowed_keys) == "ecosystem_aggregate"
        ),
        "missing_target_ordinary_keys": len(missing_ordinary),
        "missing_target_ecosystem_aggregate_keys": len(missing_ecosystem),
        "extra_target_keys": len(extra_keys) + len(unexpected_target),
        "duplicate_keys": duplicate_total,
        "semantic_mismatch_count": len(semantic_mismatches),
        "unexpected_source_keys": unexpected_source,
        "unexpected_target_keys": unexpected_target + [{"key": list(key), "row_class": "extra"} for key in extra_keys],
        "mismatches": semantic_mismatches[:20],
    }


def validate_dc_carry_forward_key_universe(
    *,
    analysis_db: str | Path,
    plan: dict[str, object],
    ticker_allowlist: list[str],
    group_allowlist: list[str],
) -> dict[str, object]:
    conn = _connect_readonly(analysis_db)
    try:
        table_results = [
            _validate_carry_forward_table(
                conn,
                table_name="dc_ticker_swing_signal_daily",
                date_column="signal_date",
                current_taxonomy_version=str(plan["current_taxonomy_version"]),
                proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                date_from=str(plan["date_from"]),
                date_to=str(plan["date_to"]),
                allowed_keys=set(ticker_allowlist),
            ),
            _validate_carry_forward_table(
                conn,
                table_name="dc_group_swing_signal_daily",
                date_column="signal_date",
                current_taxonomy_version=str(plan["current_taxonomy_version"]),
                proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                date_from=str(plan["date_from"]),
                date_to=str(plan["date_to"]),
                allowed_keys=set(group_allowlist),
            ),
            _validate_carry_forward_table(
                conn,
                table_name="dc_group_synthetic_ohlc_daily",
                date_column="ohlc_date",
                current_taxonomy_version=str(plan["current_taxonomy_version"]),
                proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                date_from=str(plan["date_from"]),
                date_to=str(plan["date_to"]),
                allowed_keys=set(group_allowlist),
            ),
            _validate_carry_forward_table(
                conn,
                table_name="dc_group_index_daily",
                date_column="index_date",
                current_taxonomy_version=str(plan["current_taxonomy_version"]),
                proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                date_from=str(plan["date_from"]),
                date_to=str(plan["date_to"]),
                allowed_keys=set(group_allowlist),
            ),
        ]
    finally:
        conn.close()
    return {
        "validation_status": "OK" if all(row["validation_status"] in {"OK", "SKIPPED_TABLE_MISSING"} for row in table_results) else "BLOCKED",
        "tables": table_results,
        "missing_target_ordinary_keys": sum(int(row["missing_target_ordinary_keys"]) for row in table_results),
        "missing_target_ecosystem_aggregate_keys": sum(
            int(row["missing_target_ecosystem_aggregate_keys"]) for row in table_results
        ),
        "extra_target_keys": sum(int(row["extra_target_keys"]) for row in table_results),
        "duplicate_keys": sum(int(row["duplicate_keys"]) for row in table_results),
        "semantic_mismatch_count": sum(int(row["semantic_mismatch_count"]) for row in table_results),
    }


def _mark_dc_facts_validated_for_rso(
    *,
    analysis_db: str | Path,
    deployment_id: int,
    evidence: dict[str, object],
) -> None:
    conn = _connect_readwrite(analysis_db)
    try:
        with conn:
            if "ec_taxonomy_change_deployment" not in _table_names(conn):
                return
            conn.execute(
                """
                UPDATE ec_taxonomy_change_deployment
                SET status = 'VALIDATION_REQUIRED',
                    dc_rebuild_status = 'OK',
                    validation_evidence_json = ?,
                    validation_evidence_sha256 = ?,
                    last_error = NULL,
                    updated_at_utc = CURRENT_TIMESTAMP
                WHERE taxonomy_change_id = ?
                """,
                (json.dumps(evidence, sort_keys=True, default=str), _json_hash(evidence), deployment_id),
            )
    finally:
        conn.close()


def _copy_rows_to_taxonomy(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_column: str,
    current_taxonomy_version: str,
    proposed_taxonomy_version: str,
    date_from: str,
    date_to: str,
    ticker_allowlist: list[str] | None = None,
    group_allowlist: list[str] | None = None,
    proposed_primary_meta: dict[str, dict[str, str]] | None = None,
) -> dict[str, object]:
    if table_name not in _table_names(conn):
        return {"table": table_name, "status": "SKIPPED_TABLE_MISSING", "copied_row_count": 0}
    columns = _table_columns(conn, table_name)
    required = {"taxonomy_version", date_column}
    if not required.issubset(columns):
        return {
            "table": table_name,
            "status": "SKIPPED_UNSUPPORTED_SCHEMA",
            "missing_columns": sorted(required - set(columns)),
            "copied_row_count": 0,
        }
    clauses = ["taxonomy_version = ?", f"{_sql_identifier(date_column)} BETWEEN ? AND ?"]
    params: list[object] = [current_taxonomy_version, date_from, date_to]
    if ticker_allowlist is not None:
        if "ticker" not in columns:
            return {"table": table_name, "status": "SKIPPED_TICKER_COLUMN_MISSING", "copied_row_count": 0}
        if not ticker_allowlist:
            return {"table": table_name, "status": "OK", "copied_row_count": 0, "source_row_count": 0}
        placeholders = ", ".join("?" for _ in ticker_allowlist)
        clauses.append(f"ticker IN ({placeholders})")
        params.extend(ticker_allowlist)
        target_delete_clause = f"taxonomy_version = ? AND {_sql_identifier(date_column)} BETWEEN ? AND ? AND ticker IN ({placeholders})"
        target_delete_params: list[object] = [proposed_taxonomy_version, date_from, date_to, *ticker_allowlist]
    elif group_allowlist is not None:
        if not {"group_type", "group_name"}.issubset(columns):
            return {"table": table_name, "status": "SKIPPED_GROUP_COLUMNS_MISSING", "copied_row_count": 0}
        group_pairs = [pair for value in group_allowlist if (pair := _split_group_identity(value)) is not None]
        if not group_pairs:
            return {"table": table_name, "status": "OK", "copied_row_count": 0, "source_row_count": 0}
        group_clauses = []
        for group_type, group_name in group_pairs:
            group_clauses.append("(group_type = ? AND group_name = ?)")
            params.extend([group_type, group_name])
        clauses.append("(" + " OR ".join(group_clauses) + ")")
        target_delete_clause = (
            f"taxonomy_version = ? AND {_sql_identifier(date_column)} BETWEEN ? AND ? AND ("
            + " OR ".join(group_clauses)
            + ")"
        )
        target_delete_params = [proposed_taxonomy_version, date_from, date_to]
        for group_type, group_name in group_pairs:
            target_delete_params.extend([group_type, group_name])
    else:
        raise ValueError("ticker_allowlist or group_allowlist is required")

    select_sql = (
        f"SELECT {', '.join(_sql_identifier(column) for column in columns)} "
        f"FROM {_sql_identifier(table_name)} WHERE {' AND '.join(clauses)} "
        f"ORDER BY {', '.join(_sql_identifier(column) for column in columns)}"
    )
    source_rows = [dict(row) for row in conn.execute(select_sql, params).fetchall()]
    pk_columns = _pk_columns(conn, table_name)
    if pk_columns:
        projected_keys = []
        for row in source_rows:
            target = dict(row)
            target["taxonomy_version"] = proposed_taxonomy_version
            projected_keys.append(tuple(target[column] for column in pk_columns))
        if len(projected_keys) != len(set(projected_keys)):
            return {
                "table": table_name,
                "status": "BLOCKED_DUPLICATE_PROJECTED_TARGET_KEYS",
                "copied_row_count": 0,
                "source_row_count": len(source_rows),
            }

    delete_sql = f"DELETE FROM {_sql_identifier(table_name)} WHERE {target_delete_clause}"
    deleted_count = conn.execute(delete_sql, target_delete_params).rowcount
    insert_sql = (
        f"INSERT INTO {_sql_identifier(table_name)} ({', '.join(_sql_identifier(column) for column in columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})"
    )
    target_rows: list[dict[str, object]] = []
    for row in source_rows:
        target = dict(row)
        target["taxonomy_version"] = proposed_taxonomy_version
        ticker = str(target.get("ticker") or "")
        if proposed_primary_meta is not None and ticker in proposed_primary_meta:
            if "primary_layer" in target:
                target["primary_layer"] = proposed_primary_meta[ticker]["primary_layer"]
            if "primary_subindustry" in target:
                target["primary_subindustry"] = proposed_primary_meta[ticker]["primary_subindustry"]
        conn.execute(insert_sql, [target[column] for column in columns])
        target_rows.append(target)
    return {
        "table": table_name,
        "status": "OK",
        "source_taxonomy_version": current_taxonomy_version,
        "target_taxonomy_version": proposed_taxonomy_version,
        "date_from": date_from,
        "date_to": date_to,
        "deleted_target_row_count": deleted_count,
        "source_row_count": len(source_rows),
        "copied_row_count": len(target_rows),
        "target_rows_hash": _rows_hash(target_rows),
        "primary_taxonomy_metadata_rewritten": proposed_primary_meta is not None,
    }


def copy_delta_carry_forward(
    *,
    analysis_db: str | Path,
    plan: dict[str, object],
) -> dict[str, object]:
    """Copy safely reusable active-taxonomy DC facts into the proposed taxonomy.

    This helper is intentionally scoped to DC fact tables with explicit
    taxonomy_version lineage. EC construction remains delegated to the existing
    canonical DC-to-EC loaders after proposed DC state is complete.
    """
    if plan.get("selected_rebuild_mode") != REBUILD_MODE_DELTA and plan.get("rebuild_mode") != REBUILD_MODE_DELTA:
        return {"carry_forward_status": "SKIPPED_NON_DELTA_PLAN", "table_results": []}
    ticker_allowlist = _dc_ticker_allowlist(plan)
    group_allowlist = _dc_group_allowlist(plan)
    proposed_primary_meta = _proposed_primary_metadata(
        str(plan["proposed_source_reference"]),
        str(plan["proposed_taxonomy_version"]),
    )
    conn = _connect_readwrite(analysis_db)
    table_results: list[dict[str, object]] = []
    try:
        try:
            with conn:
                table_results = [
                    _copy_rows_to_taxonomy(
                        conn,
                        table_name="dc_ticker_swing_signal_daily",
                        date_column="signal_date",
                        current_taxonomy_version=str(plan["current_taxonomy_version"]),
                        proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        date_from=str(plan["date_from"]),
                        date_to=str(plan["date_to"]),
                        ticker_allowlist=ticker_allowlist,
                        proposed_primary_meta=proposed_primary_meta,
                    ),
                    _copy_rows_to_taxonomy(
                        conn,
                        table_name="dc_group_swing_signal_daily",
                        date_column="signal_date",
                        current_taxonomy_version=str(plan["current_taxonomy_version"]),
                        proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        date_from=str(plan["date_from"]),
                        date_to=str(plan["date_to"]),
                        group_allowlist=group_allowlist,
                    ),
                    _copy_rows_to_taxonomy(
                        conn,
                        table_name="dc_group_synthetic_ohlc_daily",
                        date_column="ohlc_date",
                        current_taxonomy_version=str(plan["current_taxonomy_version"]),
                        proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        date_from=str(plan["date_from"]),
                        date_to=str(plan["date_to"]),
                        group_allowlist=group_allowlist,
                    ),
                    _copy_rows_to_taxonomy(
                        conn,
                        table_name="dc_group_index_daily",
                        date_column="index_date",
                        current_taxonomy_version=str(plan["current_taxonomy_version"]),
                        proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        date_from=str(plan["date_from"]),
                        date_to=str(plan["date_to"]),
                        group_allowlist=group_allowlist,
                    ),
                ]
                blocked = [row for row in table_results if str(row["status"]).startswith("BLOCKED")]
                if blocked:
                    raise RuntimeError("delta carry-forward blocked")
        except RuntimeError as exc:
            return {
                "carry_forward_status": "BLOCKED",
                "failure_message": str(exc),
                "table_results": table_results,
                "copied_ticker_count": 0,
                "copied_group_count": 0,
            }
        validation = validate_dc_carry_forward_key_universe(
            analysis_db=analysis_db,
            plan=plan,
            ticker_allowlist=ticker_allowlist,
            group_allowlist=group_allowlist,
        )
        if validation["validation_status"] != "OK":
            return {
                "carry_forward_status": "BLOCKED",
                "failure_message": "DC carry-forward key-universe validation failed",
                "table_results": table_results,
                "dc_key_universe_validation": validation,
                "copied_ticker_count": len(ticker_allowlist),
                "copied_group_count": len(group_allowlist),
            }
        return {
            "carry_forward_status": "OK",
            "table_results": table_results,
            "dc_key_universe_validation": validation,
            "copied_ticker_count": len(ticker_allowlist),
            "copied_group_count": len(group_allowlist),
        }
    finally:
        conn.close()


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
    parser.add_argument("--rebuild-mode", default=REBUILD_MODE_FULL, choices=("auto", "full", "delta", REBUILD_MODE_AUTO, REBUILD_MODE_FULL, REBUILD_MODE_DELTA))
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
    parser.add_argument("--confirm-rebuild-mode", required=True, choices=("full", "delta", REBUILD_MODE_FULL, REBUILD_MODE_DELTA))
    parser.add_argument("--confirm-plan-hash", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def print_json(summary: dict[str, object]) -> None:
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
