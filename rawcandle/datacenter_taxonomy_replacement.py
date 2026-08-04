from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from analysis.datacenter_indices.taxonomy import (
    DatacenterTaxonomyRow,
    load_datacenter_taxonomy_csv,
)
from rawcandle.scheduler.config import read_scheduler_config
from rawcandle.ec_datacenter_taxonomy_loader import (
    _build_taxonomy_name,
    _compute_source_hash,
    _ensure_alias,
    _ensure_ecosystem_row,
    _ensure_entity,
    _ensure_taxonomy_version_absent,
    _insert_membership,
    _insert_taxonomy_version,
    _normalize_group_entity_code,
    _normalize_ticker_code,
    _require_ec_sidecar_tables,
)


DEFAULT_DATACENTER_TAXONOMY_CSV = "data/datacenter_ecosystem_taxonomy_full_v1.csv"
DEFAULT_DATACENTER_TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"
DEFAULT_DATACENTER_REBUILD_START_DATE = "2025-08-01"
DATACENTER_ECOSYSTEM_CODE = "DATACENTER"
TAXONOMY_REPLACEMENT_COMPONENTS = (
    "TICKER_SWING_BASE",
    "GROUP_SWING_BASE",
    "GROUP_TIMING",
    "GROUP_OVERHEAT",
    "TICKER_SCANNER",
    "SYNTHETIC_OHLC_BASE",
    "SYNTHETIC_OHLC_RELATIVE",
    "SYNTHETIC_OHLC_STRUCTURE",
    "GROUP_INDEX",
    "PIPELINE_AUDIT",
    "DAILY_REPORT",
    "ROLLING_REPORT_2",
    "ROLLING_REPORT_5",
    "ROLLING_REPORT_30",
)
CANONICAL_DC_FACT_TABLES = (
    ("dc_ticker_swing_signal_daily", "signal_date"),
    ("dc_group_swing_signal_daily", "signal_date"),
    ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
    ("dc_group_index_daily", "index_date"),
)
CANONICAL_EC_FACT_TABLES = (
    "ec_ticker_signal_daily",
    "ec_group_signal_daily",
    "ec_group_synthetic_ohlc_daily",
    "ec_group_index_daily",
)
CANONICAL_EC_FACT_DATE_COLUMNS = {
    "ec_ticker_signal_daily": "signal_date",
    "ec_group_signal_daily": "signal_date",
    "ec_group_synthetic_ohlc_daily": "signal_date",
    "ec_group_index_daily": "signal_date",
}
CANONICAL_EC_WATERMARK_SCOPES = (
    ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily"),
    ("GROUP_SWING_BASE", "dc_group_swing_signal_daily"),
    ("SYNTHETIC_OHLC_BASE", "dc_group_synthetic_ohlc_daily"),
    ("GROUP_INDEX", "dc_group_index_daily"),
)
DC_REBUILD_REPORT_FILES = (
    "datacenter_daily_{date}_*_full.md",
    "datacenter_daily_{date}_*_full.csv",
    "datacenter_rolling_30_{date}_*_full.md",
    "datacenter_rolling_30_{date}_*_full.csv",
    "datacenter_rolling_5_{date}_*_full.md",
    "datacenter_rolling_5_{date}_*_full.csv",
    "datacenter_rolling_2_{date}_*_full.md",
    "datacenter_rolling_2_{date}_*_full.csv",
)
DEPLOYMENT_READY_STATUSES = {
    "LOADED_NOT_ACTIVE",
    "REBUILD_IN_PROGRESS",
    "VALIDATION_REQUIRED",
    "READY_TO_ACTIVATE",
}
_ENTITY_CODE_RE = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True)
class TaxonomySummary:
    path: str
    source_sha256: str
    row_count: int
    ticker_count: int
    layer_count: int
    subindustry_count: int
    membership_count: int
    primary_membership_count: int
    secondary_membership_count: int
    rows: tuple[DatacenterTaxonomyRow, ...]


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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SCHEDULER_TAXONOMY_KEYS = (
    "datacenter_taxonomy_csv",
    "datacenter_taxonomy_version",
    "ec_source_layer_taxonomy_csv",
    "ec_source_layer_taxonomy_version",
)


def _scheduler_taxonomy_transition_plan(
    *,
    scheduler_config_path: str | Path | None,
    current_taxonomy_version: str | None,
    current_taxonomy_csv: str | Path | None,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    loaded_current_source_hash: str | None,
    loaded_proposed_source_hash: str | None,
) -> tuple[dict[str, object], list[str]]:
    summary: dict[str, object] = {
        "current_scheduler_taxonomy_status": "NOT_CHECKED",
        "current_scheduler_datacenter_version": None,
        "current_scheduler_ec_version": None,
        "current_scheduler_config_safe_to_transition": False,
        "proposed_scheduler_taxonomy_status": "NOT_CHECKED",
        "proposed_scheduler_config_safe": False,
        "proposed_scheduler_config": None,
        "config_transition_required": False,
        "scheduler_changed_keys": [],
        "scheduler_unexpected_changed_keys": [],
    }
    blocking_errors: list[str] = []
    if scheduler_config_path is None:
        return summary, blocking_errors

    from rawcandle.scheduler.config import validate_scheduler_config

    try:
        current_config = read_scheduler_config(str(scheduler_config_path))
        validate_scheduler_config(current_config)
    except Exception as exc:
        blocking_errors.append(f"scheduler config invalid: {exc}")
        summary["current_scheduler_taxonomy_status"] = "BLOCKED"
        summary["proposed_scheduler_taxonomy_status"] = "BLOCKED"
        return summary, blocking_errors

    dc_version = current_config.datacenter_taxonomy_version
    ec_version = current_config.ec_source_layer_taxonomy_version
    dc_csv = current_config.datacenter_taxonomy_csv
    ec_csv = current_config.ec_source_layer_taxonomy_csv
    summary["current_scheduler_datacenter_version"] = dc_version
    summary["current_scheduler_ec_version"] = ec_version

    if dc_version != ec_version:
        blocking_errors.append("scheduler Datacenter and EC taxonomy versions disagree")
    if not dc_csv or not Path(dc_csv).is_file():
        blocking_errors.append("scheduler Datacenter taxonomy CSV is absent or unreadable")
    if not ec_csv or not Path(ec_csv).is_file():
        blocking_errors.append("scheduler EC taxonomy CSV is absent or unreadable")

    current_hash: str | None = None
    if current_taxonomy_version and dc_version == ec_version == current_taxonomy_version:
        summary["current_scheduler_taxonomy_status"] = "EXPECTED_CURRENT_V1"
        summary["current_scheduler_config_safe_to_transition"] = True
    elif dc_version == ec_version == proposed_taxonomy_version:
        summary["current_scheduler_taxonomy_status"] = "ALREADY_PROPOSED"
    elif current_taxonomy_version and dc_version not in {current_taxonomy_version, proposed_taxonomy_version}:
        summary["current_scheduler_taxonomy_status"] = "BLOCKED_UNEXPECTED_TAXONOMY"
        blocking_errors.append("scheduler configuration points to an unexpected taxonomy")
    else:
        summary["current_scheduler_taxonomy_status"] = "BLOCKED_MIXED_TAXONOMY"
        blocking_errors.append("scheduler taxonomy configuration is partially transitioned or mixed")

    if dc_csv and ec_csv and _sha256(dc_csv) != _sha256(ec_csv):
        blocking_errors.append("scheduler Datacenter and EC taxonomy CSV sources disagree")
    current_status = str(summary["current_scheduler_taxonomy_status"])
    if current_status == "EXPECTED_CURRENT_V1" and current_taxonomy_csv is not None and dc_csv and ec_csv:
        try:
            expected_current_hash = _sha256(current_taxonomy_csv)
            current_hash = _sha256(dc_csv)
            if current_hash != expected_current_hash or _sha256(ec_csv) != expected_current_hash:
                blocking_errors.append("scheduler current taxonomy CSV does not match expected current source")
        except Exception as exc:
            blocking_errors.append(f"current taxonomy source invalid: {exc}")
    if current_status == "EXPECTED_CURRENT_V1" and current_taxonomy_version and dc_csv:
        try:
            current_summary = summarize_taxonomy_csv(dc_csv, current_taxonomy_version)
            current_hash = current_summary.source_sha256
        except Exception as exc:
            blocking_errors.append(f"scheduler current Datacenter taxonomy CSV version mismatch: {exc}")
    if current_status == "EXPECTED_CURRENT_V1" and current_taxonomy_version and ec_csv:
        try:
            summarize_taxonomy_csv(ec_csv, current_taxonomy_version)
        except Exception as exc:
            blocking_errors.append(f"scheduler current EC taxonomy CSV version mismatch: {exc}")
    if current_status == "EXPECTED_CURRENT_V1" and loaded_current_source_hash and current_hash and current_hash != loaded_current_source_hash:
        blocking_errors.append("current source hash differs from loaded taxonomy metadata")

    try:
        proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
        if loaded_proposed_source_hash and proposed_summary.source_sha256 != loaded_proposed_source_hash:
            blocking_errors.append("V2 source hash mismatch")
    except Exception as exc:
        blocking_errors.append(f"proposed scheduler taxonomy invalid: {exc}")
        summary["proposed_scheduler_taxonomy_status"] = "BLOCKED"
        return summary, blocking_errors

    target_csv = str(proposed_taxonomy_csv)
    proposed_config = replace(
        current_config,
        datacenter_taxonomy_csv=target_csv,
        datacenter_taxonomy_version=proposed_taxonomy_version,
        ec_source_layer_taxonomy_csv=target_csv,
        ec_source_layer_taxonomy_version=proposed_taxonomy_version,
    )
    try:
        validate_scheduler_config(proposed_config)
    except Exception as exc:
        blocking_errors.append(f"proposed scheduler config invalid: {exc}")
        summary["proposed_scheduler_taxonomy_status"] = "BLOCKED"
        return summary, blocking_errors

    changed_keys = sorted(
        key
        for key in current_config.__dict__
        if getattr(current_config, key) != getattr(proposed_config, key)
    )
    expected_changed = set(SCHEDULER_TAXONOMY_KEYS)
    unexpected_changed = sorted(set(changed_keys) - expected_changed)
    missing_changed = sorted(expected_changed - set(changed_keys))
    summary["scheduler_changed_keys"] = changed_keys
    summary["scheduler_unexpected_changed_keys"] = unexpected_changed
    summary["config_transition_required"] = bool(changed_keys)
    summary["proposed_scheduler_config"] = {
        "datacenter_taxonomy_csv": proposed_config.datacenter_taxonomy_csv,
        "datacenter_taxonomy_version": proposed_config.datacenter_taxonomy_version,
        "ec_source_layer_taxonomy_csv": proposed_config.ec_source_layer_taxonomy_csv,
        "ec_source_layer_taxonomy_version": proposed_config.ec_source_layer_taxonomy_version,
    }
    summary["proposed_scheduler_taxonomy_status"] = "VALID"
    summary["proposed_scheduler_config_safe"] = not unexpected_changed and (
        not changed_keys or not missing_changed
    )

    if unexpected_changed:
        blocking_errors.append(
            "unexpected scheduler config changed keys: " + ", ".join(unexpected_changed)
        )
    if changed_keys and missing_changed:
        blocking_errors.append(
            "scheduler taxonomy transition does not change exactly four taxonomy keys"
        )
    return summary, blocking_errors


def _normalize_group_entity_code(name: str) -> str:
    code = _ENTITY_CODE_RE.sub("_", name.strip().upper()).strip("_")
    return code or "UNKNOWN"


def _membership_key(row: DatacenterTaxonomyRow) -> tuple[str, str, str]:
    return (row.ticker, row.layer, row.subindustry)


def _primary_membership(rows: Iterable[DatacenterTaxonomyRow]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for row in rows:
        if row.is_primary == 1:
            result[row.ticker] = (row.layer, row.subindustry)
    return result


def _role_weight_map(rows: Iterable[DatacenterTaxonomyRow]) -> dict[tuple[str, str, str], float]:
    return {_membership_key(row): row.role_weight for row in rows}


def _status_map(rows: Iterable[DatacenterTaxonomyRow]) -> dict[tuple[str, str, str], str]:
    return {_membership_key(row): row.report_group_status for row in rows}


def _validate_taxonomy_hierarchy(rows: tuple[DatacenterTaxonomyRow, ...]) -> list[str]:
    errors: list[str] = []
    primary_counts: dict[str, int] = {}
    subindustry_to_layers: dict[str, set[str]] = {}
    layer_codes: dict[str, str] = {}
    subindustry_codes: dict[str, str] = {}

    for row in rows:
        primary_counts[row.ticker] = primary_counts.get(row.ticker, 0) + int(row.is_primary == 1)
        subindustry_to_layers.setdefault(row.subindustry, set()).add(row.layer)
        layer_code = _normalize_group_entity_code(row.layer)
        if layer_code in layer_codes and layer_codes[layer_code] != row.layer:
            errors.append(
                "ambiguous layer entity code "
                f"{layer_code!r}: {layer_codes[layer_code]!r} vs {row.layer!r}"
            )
        layer_codes[layer_code] = row.layer
        subindustry_code = _normalize_group_entity_code(row.subindustry)
        if subindustry_code in subindustry_codes and subindustry_codes[subindustry_code] != row.subindustry:
            errors.append(
                "ambiguous subindustry entity code "
                f"{subindustry_code!r}: {subindustry_codes[subindustry_code]!r} vs {row.subindustry!r}"
            )
        subindustry_codes[subindustry_code] = row.subindustry

    missing_primary = sorted(ticker for ticker, count in primary_counts.items() if count == 0)
    duplicate_primary = sorted(ticker for ticker, count in primary_counts.items() if count > 1)
    if missing_primary:
        errors.append("missing primary membership for tickers: " + ", ".join(missing_primary))
    if duplicate_primary:
        errors.append("duplicate primary membership for tickers: " + ", ".join(duplicate_primary))

    invalid_subindustry_parents = {
        subindustry: sorted(layers)
        for subindustry, layers in subindustry_to_layers.items()
        if len(layers) > 1
    }
    if invalid_subindustry_parents:
        formatted = "; ".join(
            f"{subindustry}: {', '.join(layers)}"
            for subindustry, layers in sorted(invalid_subindustry_parents.items())
        )
        errors.append("invalid hierarchy: subindustry belongs to multiple layers: " + formatted)
    return sorted(set(errors))


def summarize_taxonomy_csv(
    taxonomy_csv: str | Path,
    taxonomy_version: str,
) -> TaxonomySummary:
    rows = tuple(load_datacenter_taxonomy_csv(taxonomy_csv, expected_taxonomy_version=taxonomy_version))
    return TaxonomySummary(
        path=str(taxonomy_csv),
        source_sha256=_sha256(taxonomy_csv),
        row_count=len(rows),
        ticker_count=len({row.ticker for row in rows}),
        layer_count=len({row.layer for row in rows}),
        subindustry_count=len({row.subindustry for row in rows}),
        membership_count=len(rows),
        primary_membership_count=sum(1 for row in rows if row.is_primary == 1),
        secondary_membership_count=sum(1 for row in rows if row.is_primary == 0),
        rows=rows,
    )


def _fetch_loaded_taxonomy(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> dict[str, object] | None:
    if "ec_taxonomy_version" not in _table_names(conn) or "ec_ecosystem" not in _table_names(conn):
        return None
    row = conn.execute(
        """
        SELECT tv.taxonomy_version_id, tv.taxonomy_version_code, tv.source_hash,
               tv.source_reference, tv.status, tv.is_active
        FROM ec_taxonomy_version tv
        JOIN ec_ecosystem e ON e.ecosystem_id = tv.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    return dict(row) if row is not None else None


def _fetch_active_taxonomy(conn: sqlite3.Connection, *, ecosystem_code: str) -> dict[str, object] | None:
    if "ec_taxonomy_version" not in _table_names(conn) or "ec_ecosystem" not in _table_names(conn):
        return None
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


def _fetch_deployment_by_id(
    conn: sqlite3.Connection,
    *,
    deployment_id: int,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
) -> dict[str, object] | None:
    if "ec_taxonomy_change_deployment" not in _table_names(conn):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM ec_taxonomy_change_deployment
        WHERE taxonomy_change_id = ?
          AND ecosystem_code = ?
          AND proposed_taxonomy_version = ?
        """,
        (deployment_id, ecosystem_code, proposed_taxonomy_version),
    ).fetchone()
    return dict(row) if row is not None else None


def _dc_watermark_evidence(conn: sqlite3.Connection, *, taxonomy_version: str) -> list[dict[str, object]]:
    if "dc_pipeline_watermark" not in _table_names(conn):
        return []
    rows = conn.execute(
        """
        SELECT component_name, taxonomy_version, market, signal_version, calc_version,
               start_date, end_date, row_count, status, last_successful_run_id,
               last_successful_at_utc, notes
        FROM dc_pipeline_watermark
        WHERE taxonomy_version = ?
        ORDER BY component_name, market, signal_version, calc_version
        """,
        (taxonomy_version,),
    ).fetchall()
    return [dict(row) for row in rows]


def _dc_fact_heads(conn: sqlite3.Connection, *, taxonomy_version: str) -> dict[str, str | None]:
    heads: dict[str, str | None] = {}
    for table_name, date_column in CANONICAL_DC_FACT_TABLES:
        if table_name not in _table_names(conn):
            heads[table_name] = None
            continue
        row = conn.execute(
            f"SELECT MAX({date_column}) FROM {table_name} WHERE taxonomy_version = ?",
            (taxonomy_version,),
        ).fetchone()
        heads[table_name] = None if row is None or row[0] is None else str(row[0])
    return heads


def _ec_fact_heads(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
) -> dict[str, str | None]:
    heads: dict[str, str | None] = {}
    for table_name in CANONICAL_EC_FACT_TABLES:
        if table_name not in _table_names(conn):
            heads[table_name] = None
            continue
        columns = _table_columns(conn, table_name)
        predicates = ["taxonomy_version_id = ?"]
        params: list[object] = [taxonomy_version_id]
        if "ecosystem_id" in columns:
            predicates.append("ecosystem_id = ?")
            params.append(ecosystem_id)
        row = conn.execute(
            f"SELECT MAX(signal_date) FROM {table_name} WHERE {' AND '.join(predicates)}",
            tuple(params),
        ).fetchone()
        heads[table_name] = None if row is None or row[0] is None else str(row[0])
    return heads


def _ec_watermark_lineage_evidence(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
) -> list[dict[str, object]]:
    if "ec_pipeline_watermark" not in _table_names(conn):
        return []
    columns = _table_columns(conn, "ec_pipeline_watermark")
    lineage_select = "taxonomy_version_id" if "taxonomy_version_id" in columns else "NULL AS taxonomy_version_id"
    rows = conn.execute(
        f"""
        SELECT pipeline_name, source_table, latest_signal_date, status, {lineage_select}
        FROM ec_pipeline_watermark
        WHERE ecosystem_id = ?
        ORDER BY pipeline_name, source_table
        """,
        (ecosystem_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_active_taxonomy(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
) -> dict[str, object] | None:
    if "ec_taxonomy_version" not in _table_names(conn) or "ec_ecosystem" not in _table_names(conn):
        return None
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


def _diff_taxonomies(current: TaxonomySummary, proposed: TaxonomySummary) -> dict[str, object]:
    current_tickers = {row.ticker for row in current.rows}
    proposed_tickers = {row.ticker for row in proposed.rows}
    current_memberships = {_membership_key(row) for row in current.rows}
    proposed_memberships = {_membership_key(row) for row in proposed.rows}
    current_primary = _primary_membership(current.rows)
    proposed_primary = _primary_membership(proposed.rows)
    common_memberships = current_memberships & proposed_memberships
    current_weights = _role_weight_map(current.rows)
    proposed_weights = _role_weight_map(proposed.rows)
    current_statuses = _status_map(current.rows)
    proposed_statuses = _status_map(proposed.rows)

    moved_primary = [
        {
            "ticker": ticker,
            "from": {
                "layer": current_primary[ticker][0],
                "subindustry": current_primary[ticker][1],
            },
            "to": {
                "layer": proposed_primary[ticker][0],
                "subindustry": proposed_primary[ticker][1],
            },
        }
        for ticker in sorted(set(current_primary) & set(proposed_primary))
        if current_primary[ticker] != proposed_primary[ticker]
    ]
    changed_weights = [
        {
            "ticker": ticker,
            "layer": layer,
            "subindustry": subindustry,
            "from": current_weights[(ticker, layer, subindustry)],
            "to": proposed_weights[(ticker, layer, subindustry)],
        }
        for ticker, layer, subindustry in sorted(common_memberships)
        if current_weights[(ticker, layer, subindustry)] != proposed_weights[(ticker, layer, subindustry)]
    ]
    changed_statuses = [
        {
            "ticker": ticker,
            "layer": layer,
            "subindustry": subindustry,
            "from": current_statuses[(ticker, layer, subindustry)],
            "to": proposed_statuses[(ticker, layer, subindustry)],
        }
        for ticker, layer, subindustry in sorted(common_memberships)
        if current_statuses[(ticker, layer, subindustry)] != proposed_statuses[(ticker, layer, subindustry)]
    ]
    added_memberships = [
        {"ticker": ticker, "layer": layer, "subindustry": subindustry}
        for ticker, layer, subindustry in sorted(proposed_memberships - current_memberships)
    ]
    removed_memberships = [
        {"ticker": ticker, "layer": layer, "subindustry": subindustry}
        for ticker, layer, subindustry in sorted(current_memberships - proposed_memberships)
    ]
    affected_tickers = set(proposed_tickers ^ current_tickers)
    affected_tickers.update(item["ticker"] for item in moved_primary)
    affected_tickers.update(item["ticker"] for item in changed_weights)
    affected_tickers.update(item["ticker"] for item in changed_statuses)
    affected_tickers.update(item["ticker"] for item in added_memberships)
    affected_tickers.update(item["ticker"] for item in removed_memberships)

    current_layers = {row.layer for row in current.rows}
    proposed_layers = {row.layer for row in proposed.rows}
    current_subindustries = {row.subindustry for row in current.rows}
    proposed_subindustries = {row.subindustry for row in proposed.rows}
    affected_groups = (current_layers ^ proposed_layers) | (current_subindustries ^ proposed_subindustries)
    affected_groups.update(item["layer"] for item in added_memberships)
    affected_groups.update(item["layer"] for item in removed_memberships)
    affected_groups.update(item["subindustry"] for item in added_memberships)
    affected_groups.update(item["subindustry"] for item in removed_memberships)

    return {
        "added_tickers": sorted(proposed_tickers - current_tickers),
        "removed_tickers": sorted(current_tickers - proposed_tickers),
        "added_memberships": added_memberships,
        "removed_memberships": removed_memberships,
        "moved_primary_memberships": moved_primary,
        "changed_role_weights": changed_weights,
        "changed_report_group_statuses": changed_statuses,
        "added_layers": sorted(proposed_layers - current_layers),
        "removed_layers": sorted(current_layers - proposed_layers),
        "added_subindustries": sorted(proposed_subindustries - current_subindustries),
        "removed_subindustries": sorted(current_subindustries - proposed_subindustries),
        "affected_ticker_count": len(affected_tickers),
        "affected_group_count": len(affected_groups),
        "primary_membership_change_count": len(moved_primary),
        "secondary_membership_change_count": (
            len(added_memberships) + len(removed_memberships) + len(changed_weights) + len(changed_statuses)
        ),
    }


def plan_datacenter_taxonomy_change(
    *,
    analysis_db: str | Path,
    current_taxonomy_version: str,
    current_taxonomy_csv: str | Path,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    ecosystem_code: str = DATACENTER_ECOSYSTEM_CODE,
    rebuild_start_date: str = DEFAULT_DATACENTER_REBUILD_START_DATE,
) -> dict[str, object]:
    blocking_errors: list[str] = []
    warnings: list[str] = []
    current_summary: TaxonomySummary | None = None
    proposed_summary: TaxonomySummary | None = None

    try:
        current_summary = summarize_taxonomy_csv(current_taxonomy_csv, current_taxonomy_version)
    except Exception as exc:
        blocking_errors.append(f"current taxonomy invalid: {exc}")
    try:
        proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    except Exception as exc:
        blocking_errors.append(f"proposed taxonomy invalid: {exc}")

    if proposed_taxonomy_version == current_taxonomy_version:
        blocking_errors.append("proposed version must differ from current active taxonomy version")

    conn = _connect_readonly(analysis_db)
    try:
        active_taxonomy = _fetch_active_taxonomy(conn, ecosystem_code=ecosystem_code)
        loaded_proposed = _fetch_loaded_taxonomy(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=proposed_taxonomy_version,
        )
        if active_taxonomy and active_taxonomy.get("taxonomy_version_code") != current_taxonomy_version:
            warnings.append(
                "current_taxonomy_version does not match loaded active taxonomy: "
                f"{active_taxonomy.get('taxonomy_version_code')}"
            )
        if proposed_summary is not None and loaded_proposed is not None:
            loaded_hash = str(loaded_proposed.get("source_hash") or "")
            if loaded_hash and loaded_hash != proposed_summary.source_sha256:
                blocking_errors.append("proposed version already loaded with a different source hash")
            else:
                blocking_errors.append("proposed version is already loaded")
    finally:
        conn.close()

    if current_summary is not None:
        blocking_errors.extend(_validate_taxonomy_hierarchy(current_summary.rows))
    if proposed_summary is not None:
        blocking_errors.extend(_validate_taxonomy_hierarchy(proposed_summary.rows))

    diff = (
        _diff_taxonomies(current_summary, proposed_summary)
        if current_summary is not None and proposed_summary is not None
        else {
            "added_tickers": [],
            "removed_tickers": [],
            "added_memberships": [],
            "removed_memberships": [],
            "moved_primary_memberships": [],
            "changed_role_weights": [],
            "changed_report_group_statuses": [],
            "added_layers": [],
            "removed_layers": [],
            "added_subindustries": [],
            "removed_subindustries": [],
            "affected_ticker_count": 0,
            "affected_group_count": 0,
            "primary_membership_change_count": 0,
            "secondary_membership_change_count": 0,
        }
    )
    safe_to_load = not blocking_errors
    return {
        "taxonomy_plan_status": "READY_TO_LOAD" if safe_to_load else "BLOCKED",
        "ecosystem_code": ecosystem_code,
        "current_taxonomy_version": current_taxonomy_version,
        "proposed_taxonomy_version": proposed_taxonomy_version,
        "current_source_sha256": current_summary.source_sha256 if current_summary else None,
        "proposed_source_sha256": proposed_summary.source_sha256 if proposed_summary else None,
        "current_row_count": current_summary.row_count if current_summary else None,
        "proposed_row_count": proposed_summary.row_count if proposed_summary else None,
        "current_ticker_count": current_summary.ticker_count if current_summary else None,
        "proposed_ticker_count": proposed_summary.ticker_count if proposed_summary else None,
        "current_layer_count": current_summary.layer_count if current_summary else None,
        "proposed_layer_count": proposed_summary.layer_count if proposed_summary else None,
        "current_subindustry_count": current_summary.subindustry_count if current_summary else None,
        "proposed_subindustry_count": proposed_summary.subindustry_count if proposed_summary else None,
        **diff,
        "requires_new_taxonomy_version": True,
        "requires_full_historical_rebuild": True,
        "rebuild_start_date": rebuild_start_date,
        "safe_to_load": safe_to_load,
        "safe_to_replace_active_taxonomy": False,
        "dc_watermark_reset_required": True,
        "dc_watermark_affected_components": list(TAXONOMY_REPLACEMENT_COMPONENTS),
        "dc_watermark_previous_version": current_taxonomy_version,
        "dc_watermark_new_version": proposed_taxonomy_version,
        "dc_watermark_rebuild_start_date": rebuild_start_date,
        "ec_watermark_reset_required": True,
        "ec_watermark_scope": {
            "ecosystem_code": ecosystem_code,
            "identity": ["ecosystem_id", "pipeline_name", "source_table"],
            "lineage_field": "taxonomy_version_id",
        },
        "blocking_errors": sorted(set(blocking_errors)),
        "warnings": warnings,
    }


def ensure_taxonomy_replacement_schema(conn: sqlite3.Connection) -> None:
    if "ec_pipeline_watermark" in _table_names(conn) and "taxonomy_version_id" not in _table_columns(conn, "ec_pipeline_watermark"):
        conn.execute("ALTER TABLE ec_pipeline_watermark ADD COLUMN taxonomy_version_id INTEGER NULL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ec_taxonomy_change_deployment (
            taxonomy_change_id INTEGER PRIMARY KEY,
            ecosystem_code TEXT NOT NULL,
            previous_taxonomy_version TEXT NOT NULL,
            proposed_taxonomy_version TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            change_summary TEXT NOT NULL,
            added_ticker_count INTEGER NOT NULL,
            removed_ticker_count INTEGER NOT NULL,
            membership_change_count INTEGER NOT NULL,
            group_change_count INTEGER NOT NULL,
            loaded_at_utc TEXT NULL,
            status TEXT NOT NULL,
            rebuild_required INTEGER NOT NULL CHECK (rebuild_required IN (0, 1)),
            rebuild_start_date TEXT NOT NULL,
            dc_rebuild_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            ec_rebuild_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            coverage_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            parity_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
            activation_status TEXT NOT NULL DEFAULT 'NOT_ACTIVE',
            activated_at_utc TEXT NULL,
            invocation_source TEXT NULL,
            created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at_utc TEXT NULL,
            UNIQUE (ecosystem_code, proposed_taxonomy_version)
        )
        """
    )
    deployment_columns = _table_columns(conn, "ec_taxonomy_change_deployment")
    optional_columns = {
        "prepared_at_utc": "TEXT NULL",
        "validation_completed_at_utc": "TEXT NULL",
        "rebuild_evidence_json": "TEXT NULL",
        "rebuild_evidence_sha256": "TEXT NULL",
        "validation_evidence_json": "TEXT NULL",
        "validation_evidence_sha256": "TEXT NULL",
        "last_error": "TEXT NULL",
    }
    for column_name, column_sql in optional_columns.items():
        if column_name not in deployment_columns:
            conn.execute(
                f"ALTER TABLE ec_taxonomy_change_deployment ADD COLUMN {column_name} {column_sql}"
            )


def _fetch_taxonomy_version_id(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> int:
    row = conn.execute(
        """
        SELECT tv.taxonomy_version_id
        FROM ec_taxonomy_version tv
        JOIN ec_ecosystem e ON e.ecosystem_id = tv.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    if row is None:
        raise ValueError(f"taxonomy version is not loaded: {taxonomy_version_code}")
    return int(row[0])


def _verify_membership_parity(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
    rows: tuple[DatacenterTaxonomyRow, ...],
) -> None:
    db_rows = conn.execute(
        """
        SELECT child.entity_code AS ticker, parent_l1.entity_name AS layer,
               parent_l2.entity_name AS subindustry, m.membership_role,
               m.is_primary, m.role_weight
        FROM ec_membership m
        JOIN ec_entity child ON child.entity_id = m.child_entity_id
        JOIN ec_entity parent_l2 ON parent_l2.entity_id = m.parent_entity_id
        JOIN ec_membership parent_m ON parent_m.taxonomy_version_id = m.taxonomy_version_id
                                   AND parent_m.child_entity_id = parent_l2.entity_id
        JOIN ec_entity parent_l1 ON parent_l1.entity_id = parent_m.parent_entity_id
        WHERE m.taxonomy_version_id = ?
          AND child.entity_type = 'TICKER'
          AND parent_l2.entity_type = 'GROUP_L2'
          AND parent_l1.entity_type = 'GROUP_L1'
          AND m.status = 'ACTIVE'
        ORDER BY child.entity_code, parent_l1.entity_name, parent_l2.entity_name
        """,
        (taxonomy_version_id,),
    ).fetchall()
    expected = sorted(
        (
            row.ticker,
            row.layer,
            row.subindustry,
            row.report_group_status,
            row.is_primary,
            float(row.role_weight),
        )
        for row in rows
    )
    actual = sorted(
        (
            str(row["ticker"]),
            str(row["layer"]),
            str(row["subindustry"]),
            str(row["membership_role"]),
            int(row["is_primary"]),
            float(row["role_weight"]),
        )
        for row in db_rows
    )
    if actual != expected:
        raise ValueError("loaded taxonomy membership parity mismatch")


def _load_taxonomy_metadata_in_transaction(
    conn: sqlite3.Connection,
    *,
    taxonomy_csv_path: str | Path,
    taxonomy_version_code: str,
    ecosystem_code: str,
    ecosystem_name: str = "Datacenter",
    mark_active: bool = False,
) -> dict[str, object]:
    source_rows = tuple(load_datacenter_taxonomy_csv(taxonomy_csv_path, taxonomy_version_code))
    _require_ec_sidecar_tables(conn)
    warnings: list[str] = []
    ecosystem_id = _ensure_ecosystem_row(
        conn,
        ecosystem_code=ecosystem_code,
        ecosystem_name=ecosystem_name,
        warnings=warnings,
    )
    _ensure_taxonomy_version_absent(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_code=taxonomy_version_code,
    )
    csv_path = Path(taxonomy_csv_path)
    taxonomy_version_id = _insert_taxonomy_version(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_code=taxonomy_version_code,
        taxonomy_name=_build_taxonomy_name(taxonomy_version_code),
        source_reference=str(csv_path),
        source_hash=_compute_source_hash(csv_path),
        mark_active=mark_active,
    )
    ecosystem_entity_id = _ensure_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="ECOSYSTEM",
        entity_code=ecosystem_code,
        entity_name=ecosystem_name,
    )
    alias_count = _ensure_alias(
        conn,
        ecosystem_id=ecosystem_id,
        entity_id=ecosystem_entity_id,
        alias_type="DC_GROUP_NAME",
        alias_value="DC_ECOSYSTEM_TOTAL",
        source_system="dc_group_facts",
    )

    layer_names = sorted({row.layer for row in source_rows})
    subindustry_names = sorted({row.subindustry for row in source_rows})
    ticker_codes = sorted({row.ticker for row in source_rows})
    layer_entity_ids = {
        layer_name: _ensure_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="GROUP_L1",
            entity_code=_normalize_group_entity_code(layer_name),
            entity_name=layer_name,
        )
        for layer_name in layer_names
    }
    subindustry_entity_ids = {
        subindustry_name: _ensure_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="GROUP_L2",
            entity_code=_normalize_group_entity_code(subindustry_name),
            entity_name=subindustry_name,
        )
        for subindustry_name in subindustry_names
    }
    ticker_entity_ids = {
        ticker_code: _ensure_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="TICKER",
            entity_code=_normalize_ticker_code(ticker_code),
            entity_name=ticker_code,
            ticker=ticker_code,
        )
        for ticker_code in ticker_codes
    }

    membership_count = 0
    seen_ecosystem_layer: set[tuple[int, int]] = set()
    seen_layer_subindustry: set[tuple[int, int]] = set()
    for row in source_rows:
        layer_entity_id = layer_entity_ids[row.layer]
        subindustry_entity_id = subindustry_entity_ids[row.subindustry]
        ticker_entity_id = ticker_entity_ids[row.ticker]
        ecosystem_layer_key = (ecosystem_entity_id, layer_entity_id)
        if ecosystem_layer_key not in seen_ecosystem_layer:
            membership_count += _insert_membership(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                parent_entity_id=ecosystem_entity_id,
                child_entity_id=layer_entity_id,
                membership_role=None,
                is_primary=1,
                role_weight=1.0,
                source_note=None,
            )
            seen_ecosystem_layer.add(ecosystem_layer_key)
        layer_subindustry_key = (layer_entity_id, subindustry_entity_id)
        if layer_subindustry_key not in seen_layer_subindustry:
            membership_count += _insert_membership(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                parent_entity_id=layer_entity_id,
                child_entity_id=subindustry_entity_id,
                membership_role=None,
                is_primary=1,
                role_weight=1.0,
                source_note=None,
            )
            seen_layer_subindustry.add(layer_subindustry_key)
        membership_count += _insert_membership(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            parent_entity_id=subindustry_entity_id,
            child_entity_id=ticker_entity_id,
            membership_role=row.report_group_status,
            is_primary=row.is_primary,
            role_weight=row.role_weight,
            source_note=row.notes,
        )

    return {
        "status": "OK",
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_id": taxonomy_version_id,
        "taxonomy_version_code": taxonomy_version_code,
        "taxonomy_rows": len(source_rows),
        "layer_count": len(layer_names),
        "subindustry_count": len(subindustry_names),
        "ticker_count": len(ticker_codes),
        "membership_count": membership_count,
        "primary_membership_count": sum(1 for row in source_rows if row.is_primary == 1),
        "multi_membership_ticker_count": sum(
            1
            for ticker_code in ticker_codes
            if sum(1 for row in source_rows if row.ticker == ticker_code) > 1
        ),
        "alias_count": alias_count,
        "activation_status": "ACTIVE" if mark_active else "NOT_ACTIVE",
        "warnings": warnings,
    }


def apply_datacenter_taxonomy_version(
    *,
    analysis_db: str | Path,
    current_taxonomy_version: str,
    current_taxonomy_csv: str | Path,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    confirm_proposed_taxonomy_version: str,
    ecosystem_code: str = DATACENTER_ECOSYSTEM_CODE,
    invocation_source: str = "CLI",
    rebuild_start_date: str = DEFAULT_DATACENTER_REBUILD_START_DATE,
) -> dict[str, object]:
    if confirm_proposed_taxonomy_version != proposed_taxonomy_version:
        raise ValueError("confirm_proposed_taxonomy_version must match proposed_taxonomy_version")

    plan = plan_datacenter_taxonomy_change(
        analysis_db=analysis_db,
        current_taxonomy_version=current_taxonomy_version,
        current_taxonomy_csv=current_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        ecosystem_code=ecosystem_code,
        rebuild_start_date=rebuild_start_date,
    )
    if not plan["safe_to_load"]:
        return {
            "taxonomy_apply_status": "BLOCKED",
            "blocking_errors": plan["blocking_errors"],
            "plan": plan,
        }

    proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    conn = _connect_readwrite(analysis_db)
    try:
        with conn:
            ensure_taxonomy_replacement_schema(conn)
            load_summary = _load_taxonomy_metadata_in_transaction(
                conn,
                taxonomy_csv_path=proposed_taxonomy_csv,
                taxonomy_version_code=proposed_taxonomy_version,
                ecosystem_code=ecosystem_code,
                mark_active=False,
            )
            taxonomy_version_id = _fetch_taxonomy_version_id(
                conn,
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=proposed_taxonomy_version,
            )
            _verify_membership_parity(
                conn,
                taxonomy_version_id=taxonomy_version_id,
                rows=proposed_summary.rows,
            )
            change_summary = json.dumps(
                {
                    "added_tickers": plan["added_tickers"],
                    "removed_tickers": plan["removed_tickers"],
                    "added_layers": plan["added_layers"],
                    "removed_layers": plan["removed_layers"],
                    "added_subindustries": plan["added_subindustries"],
                    "removed_subindustries": plan["removed_subindustries"],
                },
                sort_keys=True,
            )
            membership_change_count = (
                len(plan["added_memberships"])
                + len(plan["removed_memberships"])
                + len(plan["moved_primary_memberships"])
                + len(plan["changed_role_weights"])
                + len(plan["changed_report_group_statuses"])
            )
            conn.execute(
                """
                INSERT INTO ec_taxonomy_change_deployment (
                    ecosystem_code,
                    previous_taxonomy_version,
                    proposed_taxonomy_version,
                    source_reference,
                    source_sha256,
                    change_summary,
                    added_ticker_count,
                    removed_ticker_count,
                    membership_change_count,
                    group_change_count,
                    loaded_at_utc,
                    status,
                    rebuild_required,
                    rebuild_start_date,
                    invocation_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                """,
                (
                    ecosystem_code,
                    current_taxonomy_version,
                    proposed_taxonomy_version,
                    str(proposed_taxonomy_csv),
                    proposed_summary.source_sha256,
                    change_summary,
                    len(plan["added_tickers"]),
                    len(plan["removed_tickers"]),
                    membership_change_count,
                    int(plan["affected_group_count"]),
                    "LOADED_NOT_ACTIVE",
                    1,
                    rebuild_start_date,
                    invocation_source,
                ),
            )

        return {
            "taxonomy_apply_status": "LOADED_NOT_ACTIVE",
            "taxonomy_version_id": taxonomy_version_id,
            "taxonomy_version_code": proposed_taxonomy_version,
            "source_reference": str(proposed_taxonomy_csv),
            "source_sha256": proposed_summary.source_sha256,
            "row_count": proposed_summary.row_count,
            "ticker_count": proposed_summary.ticker_count,
            "layer_count": proposed_summary.layer_count,
            "subindustry_count": proposed_summary.subindustry_count,
            "membership_count": proposed_summary.membership_count,
            "primary_membership_count": proposed_summary.primary_membership_count,
            "secondary_membership_count": proposed_summary.secondary_membership_count,
            "rebuild_required": True,
            "rebuild_start_date": rebuild_start_date,
            "activation_status": "NOT_ACTIVE",
            "load_summary": load_summary,
        }
    finally:
        conn.close()


def prepare_datacenter_taxonomy_rebuild(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    deployment_id: int,
    expected_active_taxonomy_version: str,
    confirm_proposed_taxonomy_version: str,
) -> dict[str, object]:
    if confirm_proposed_taxonomy_version != proposed_taxonomy_version:
        return {
            "prepare_status": "BLOCKED",
            "blocking_errors": ["confirm_proposed_taxonomy_version must match proposed_taxonomy_version"],
        }
    proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    blocking_errors: list[str] = []
    conn = _connect_readwrite(analysis_db)
    try:
        with conn:
            ensure_taxonomy_replacement_schema(conn)
            deployment = _fetch_deployment_by_id(
                conn,
                deployment_id=deployment_id,
                ecosystem_code=ecosystem_code,
                proposed_taxonomy_version=proposed_taxonomy_version,
            )
            loaded = _fetch_loaded_taxonomy(
                conn,
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=proposed_taxonomy_version,
            )
            active = _fetch_active_taxonomy(conn, ecosystem_code=ecosystem_code)
            if deployment is None:
                blocking_errors.append("taxonomy deployment row not found")
            elif str(deployment.get("status")) not in {
                "LOADED_NOT_ACTIVE",
                "REBUILD_IN_PROGRESS",
                "VALIDATION_REQUIRED",
                "FAILED",
            }:
                blocking_errors.append("deployment status is not preparable")
            if loaded is None:
                blocking_errors.append("proposed taxonomy metadata is not loaded")
            elif str(loaded.get("source_hash") or "") != proposed_summary.source_sha256:
                blocking_errors.append("loaded taxonomy hash does not match proposed source")
            if active is None:
                blocking_errors.append("active taxonomy is missing")
            elif str(active.get("taxonomy_version_code")) != expected_active_taxonomy_version:
                blocking_errors.append("active taxonomy version does not match expected current taxonomy")
            elif str(active.get("taxonomy_version_code")) == proposed_taxonomy_version:
                blocking_errors.append("proposed taxonomy is already active")
            if blocking_errors:
                return {
                    "prepare_status": "BLOCKED",
                    "deployment_id": deployment_id,
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": proposed_taxonomy_version,
                    "blocking_errors": sorted(set(blocking_errors)),
                }

            assert deployment is not None
            previous_taxonomy_version = str(deployment["previous_taxonomy_version"])
            evidence = {
                "prepared_at_utc": _utc_now(),
                "deployment_id": deployment_id,
                "ecosystem_code": ecosystem_code,
                "previous_taxonomy_version": previous_taxonomy_version,
                "proposed_taxonomy_version": proposed_taxonomy_version,
                "source_sha256": proposed_summary.source_sha256,
                "rebuild_start_date": deployment["rebuild_start_date"],
                "affected_components": list(TAXONOMY_REPLACEMENT_COMPONENTS),
                "previous_dc_watermarks": _dc_watermark_evidence(
                    conn,
                    taxonomy_version=previous_taxonomy_version,
                ),
                "proposed_dc_watermarks": _dc_watermark_evidence(
                    conn,
                    taxonomy_version=proposed_taxonomy_version,
                ),
            }
            evidence_json = json.dumps(evidence, sort_keys=True, default=str)
            evidence_sha = _json_sha256(evidence)
            conn.execute(
                """
                UPDATE ec_taxonomy_change_deployment
                SET status = 'REBUILD_IN_PROGRESS',
                    dc_rebuild_status = CASE
                        WHEN dc_rebuild_status = 'OK' THEN dc_rebuild_status
                        ELSE 'IN_PROGRESS'
                    END,
                    updated_at_utc = CURRENT_TIMESTAMP,
                    prepared_at_utc = COALESCE(prepared_at_utc, CURRENT_TIMESTAMP),
                    rebuild_evidence_json = ?,
                    rebuild_evidence_sha256 = ?,
                    last_error = NULL
                WHERE taxonomy_change_id = ?
                """,
                (evidence_json, evidence_sha, deployment_id),
            )
        return {
            "prepare_status": "REBUILD_IN_PROGRESS",
            "deployment_id": deployment_id,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": proposed_taxonomy_version,
            "taxonomy_source_sha256": proposed_summary.source_sha256,
            "rebuild_start_date": evidence["rebuild_start_date"],
            "affected_components": list(TAXONOMY_REPLACEMENT_COMPONENTS),
            "previous_dc_watermark_count": len(evidence["previous_dc_watermarks"]),
            "proposed_dc_watermark_count": len(evidence["proposed_dc_watermarks"]),
            "rebuild_evidence_sha256": evidence_sha,
            "blocking_errors": [],
        }
    finally:
        conn.close()


def validate_datacenter_taxonomy_rebuild_evidence(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    deployment_id: int,
    required_signal_date: str,
    coverage_status: str = "OK",
    parity_status: str = "OK",
    total_mismatch_count: int = 0,
) -> dict[str, object]:
    proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    blocking_errors: list[str] = []
    conn = _connect_readonly(analysis_db)
    try:
        deployment = _fetch_deployment_by_id(
            conn,
            deployment_id=deployment_id,
            ecosystem_code=ecosystem_code,
            proposed_taxonomy_version=proposed_taxonomy_version,
        )
        loaded = _fetch_loaded_taxonomy(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=proposed_taxonomy_version,
        )
        if deployment is None:
            blocking_errors.append("taxonomy deployment row not found")
        elif str(deployment.get("activation_status")) == "ACTIVE":
            blocking_errors.append("deployment already active")
        if loaded is None:
            blocking_errors.append("proposed taxonomy metadata is not loaded")
            taxonomy_version_id = None
            ecosystem_id = None
        else:
            taxonomy_version_id = int(loaded["taxonomy_version_id"])
            if str(loaded.get("source_hash") or "") != proposed_summary.source_sha256:
                blocking_errors.append("loaded taxonomy hash does not match proposed source")
            eco_row = conn.execute(
                "SELECT ecosystem_id FROM ec_ecosystem WHERE ecosystem_code = ?",
                (ecosystem_code,),
            ).fetchone()
            ecosystem_id = int(eco_row[0]) if eco_row is not None else None
        if coverage_status != "OK":
            blocking_errors.append("coverage is not accepted")
        if parity_status != "OK" or int(total_mismatch_count) != 0:
            blocking_errors.append("parity is not accepted")

        dc_heads = _dc_fact_heads(conn, taxonomy_version=proposed_taxonomy_version)
        for table_name, head in dc_heads.items():
            if head is None or head < required_signal_date:
                blocking_errors.append(f"DC fact head incomplete for {table_name}")

        ec_heads: dict[str, str | None] = {}
        watermark_rows: list[dict[str, object]] = []
        stale_summary = {
            "stale_validation_status": "NOT_RUN",
            "stale_dc_rows": {},
            "stale_ec_rows": {},
        }
        if taxonomy_version_id is not None and ecosystem_id is not None:
            ec_heads = _ec_fact_heads(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
            )
            for table_name, head in ec_heads.items():
                if head is None or head < required_signal_date:
                    blocking_errors.append(f"EC fact head incomplete for {table_name}")
            watermark_rows = _ec_watermark_lineage_evidence(conn, ecosystem_id=ecosystem_id)
            watermark_by_scope = {
                (str(row["pipeline_name"]), str(row["source_table"])): row
                for row in watermark_rows
            }
            for scope in CANONICAL_EC_WATERMARK_SCOPES:
                row = watermark_by_scope.get(scope)
                if row is None:
                    blocking_errors.append(f"missing EC canonical watermark scope: {scope[0]}")
                    continue
                if row.get("taxonomy_version_id") != taxonomy_version_id:
                    blocking_errors.append("EC watermark lineage does not belong to proposed taxonomy")
                latest = row.get("latest_signal_date")
                if latest is None or str(latest) < required_signal_date:
                    blocking_errors.append(f"EC watermark head incomplete for {scope[0]}")
                if str(row.get("status")) != "OK":
                    blocking_errors.append(f"EC watermark status is not OK for {scope[0]}")
            stale_summary = validate_rebuild_stale_rows(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                taxonomy_version_code=proposed_taxonomy_version,
                date_from=str(deployment["rebuild_start_date"]) if deployment is not None else "0000-00-00",
                date_to=required_signal_date,
                taxonomy_rows=proposed_summary.rows,
            )
            if stale_summary["stale_validation_status"] != "OK":
                blocking_errors.append("stale rows block readiness")
    finally:
        conn.close()

    ready = not blocking_errors
    return {
        "evidence_status": "READY_TO_ACTIVATE" if ready else "BLOCKED",
        "deployment_id": deployment_id,
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": proposed_taxonomy_version,
        "taxonomy_version_id": taxonomy_version_id,
        "required_signal_date": required_signal_date,
        "coverage_status": coverage_status,
        "parity_status": parity_status,
        "total_mismatch_count": int(total_mismatch_count),
        "dc_fact_heads": dc_heads,
        "ec_fact_heads": ec_heads,
        "ec_watermark_lineage": watermark_rows,
        "stale_row_validation": stale_summary,
        "blocking_errors": sorted(set(blocking_errors)),
        "evidence_sha256": _json_sha256(
            {
                "required_signal_date": required_signal_date,
                "coverage_status": coverage_status,
                "parity_status": parity_status,
                "total_mismatch_count": int(total_mismatch_count),
                "dc_fact_heads": dc_heads,
                "ec_fact_heads": ec_heads,
                "ec_watermark_lineage": watermark_rows,
                "stale_row_validation": stale_summary,
            }
        ),
    }


def _dc_duplicate_key_counts(conn: sqlite3.Connection, *, taxonomy_version: str) -> dict[str, int]:
    duplicate_counts: dict[str, int] = {}
    key_candidates = {
        "dc_ticker_swing_signal_daily": ("signal_date", "taxonomy_version", "ticker", "signal_version"),
        "dc_group_swing_signal_daily": (
            "signal_date",
            "taxonomy_version",
            "group_type",
            "group_name",
            "signal_version",
        ),
        "dc_group_synthetic_ohlc_daily": (
            "ohlc_date",
            "taxonomy_version",
            "group_type",
            "group_name",
            "calc_version",
        ),
        "dc_group_index_daily": ("index_date", "taxonomy_version", "group_type", "group_name"),
    }
    fallback_date_columns = {
        "dc_ticker_swing_signal_daily": "signal_date",
        "dc_group_swing_signal_daily": "signal_date",
        "dc_group_synthetic_ohlc_daily": "ohlc_date",
        "dc_group_index_daily": "index_date",
    }
    for table_name, candidate_columns in key_candidates.items():
        if table_name not in _table_names(conn):
            duplicate_counts[table_name] = 0
            continue
        columns = _table_columns(conn, table_name)
        key_columns = (
            candidate_columns
            if set(candidate_columns).issubset(columns)
            else (fallback_date_columns[table_name], "taxonomy_version")
        )
        key_sql = ", ".join(key_columns)
        row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT {key_sql}, COUNT(*) AS row_count
                FROM {table_name}
                WHERE taxonomy_version = ?
                GROUP BY {key_sql}
                HAVING row_count > 1
            )
            """,
            (taxonomy_version,),
        ).fetchone()
        duplicate_counts[table_name] = int(row[0]) if row is not None else 0
    return duplicate_counts


def _dc_fact_coverage(
    conn: sqlite3.Connection,
    *,
    taxonomy_version: str,
    required_signal_date: str,
    expected_ticker_rows: int,
    expected_group_rows: int,
    expected_synthetic_rows: int,
    expected_index_rows: int,
) -> dict[str, dict[str, object]]:
    expected_final_rows = {
        "dc_ticker_swing_signal_daily": expected_ticker_rows,
        "dc_group_swing_signal_daily": expected_group_rows,
        "dc_group_synthetic_ohlc_daily": expected_synthetic_rows,
        "dc_group_index_daily": expected_index_rows,
    }
    coverage: dict[str, dict[str, object]] = {}
    for table_name, date_column in CANONICAL_DC_FACT_TABLES:
        if table_name not in _table_names(conn):
            coverage[table_name] = {
                "status": "MISSING_TABLE",
                "total_rows": 0,
                "distinct_dates": 0,
                "min_date": None,
                "max_date": None,
                "final_date_rows": 0,
                "expected_final_date_rows": expected_final_rows[table_name],
                "taxonomy_version_count": 0,
            }
            continue
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS total_rows,
                   COUNT(DISTINCT {date_column}) AS distinct_dates,
                   MIN({date_column}) AS min_date,
                   MAX({date_column}) AS max_date,
                   SUM(CASE WHEN {date_column} = ? THEN 1 ELSE 0 END) AS final_date_rows,
                   COUNT(DISTINCT taxonomy_version) AS taxonomy_version_count
            FROM {table_name}
            WHERE taxonomy_version = ?
            """,
            (required_signal_date, taxonomy_version),
        ).fetchone()
        final_rows = int(row["final_date_rows"] or 0)
        max_date = None if row["max_date"] is None else str(row["max_date"])
        coverage[table_name] = {
            "status": "OK"
            if max_date == required_signal_date and final_rows == expected_final_rows[table_name]
            else "BLOCKED",
            "total_rows": int(row["total_rows"] or 0),
            "distinct_dates": int(row["distinct_dates"] or 0),
            "min_date": row["min_date"],
            "max_date": max_date,
            "final_date_rows": final_rows,
            "expected_final_date_rows": expected_final_rows[table_name],
            "taxonomy_version_count": int(row["taxonomy_version_count"] or 0),
        }
    return coverage


def _dc_required_watermark_status(
    conn: sqlite3.Connection,
    *,
    taxonomy_version: str,
    required_signal_date: str,
) -> dict[str, object]:
    rows = _dc_watermark_evidence(conn, taxonomy_version=taxonomy_version)
    by_component = {str(row["component_name"]): row for row in rows}
    missing: list[str] = []
    incomplete: list[str] = []
    failed: list[str] = []
    for component in TAXONOMY_REPLACEMENT_COMPONENTS:
        row = by_component.get(component)
        if row is None:
            missing.append(component)
            continue
        if str(row.get("status")) != "OK":
            failed.append(component)
        end_date = row.get("end_date")
        if end_date is None or str(end_date) < required_signal_date:
            incomplete.append(component)
    return {
        "status": "OK" if not missing and not incomplete and not failed else "BLOCKED",
        "rows": rows,
        "required_components": list(TAXONOMY_REPLACEMENT_COMPONENTS),
        "missing_components": missing,
        "incomplete_components": incomplete,
        "failed_components": failed,
    }


def _dc_report_artifacts(evidence_dir: str | Path, *, required_signal_date: str) -> dict[str, object]:
    report_dir = Path(evidence_dir) / "dc_reports"
    artifacts: list[dict[str, object]] = []
    missing_patterns: list[str] = []
    for pattern_template in DC_REBUILD_REPORT_FILES:
        pattern = pattern_template.format(date=required_signal_date)
        matches = sorted(report_dir.glob(pattern))
        if len(matches) != 1:
            missing_patterns.append(pattern)
            continue
        path = matches[0]
        artifacts.append(
            {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "status": "OK" if len(artifacts) == len(DC_REBUILD_REPORT_FILES) and not missing_patterns else "BLOCKED",
        "report_dir": str(report_dir),
        "artifacts": artifacts,
        "missing_patterns": missing_patterns,
    }


def _dc_stage_evidence(
    evidence_dir: str | Path,
    *,
    windows_copy_status: str,
    windows_copy_required: bool,
) -> dict[str, object]:
    log_dir = Path(evidence_dir) / "logs"
    stdout_path = log_dir / "datacenter_v2_full_rebuild.stdout"
    stderr_path = log_dir / "datacenter_v2_full_rebuild.stderr"
    stdout = stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
    stage_headings = [line.strip() for line in stdout.splitlines() if line.startswith("=== Stage ")]
    required_stage_names = [
        "Datacenter base index",
        "Ticker swing base snapshots",
        "Group swing base metrics",
        "Synthetic OHLC base",
        "Relative OHLC20",
        "Group structure / BOS / RESET",
        "Group timing states",
        "Group overheat risk",
        "Ticker scanners",
        "Pipeline audit",
        "Automatic technical relevance",
        "Daily report",
        "Rolling 30 report",
        "Rolling 5 report",
        "Rolling 2 report",
    ]
    missing_stages = [
        stage_name
        for stage_name in required_stage_names
        if not any(stage_name in heading for heading in stage_headings)
    ]
    windows_copy_failure_is_expected = (
        windows_copy_status == "FAILED_OPTIONAL"
        and not windows_copy_required
        and "Read-only file system" in stderr
        and "swing_reports" in stderr
    )
    return {
        "status": "OK" if not missing_stages and windows_copy_failure_is_expected else "BLOCKED",
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stage_headings": stage_headings,
        "missing_required_stages": missing_stages,
        "windows_copy_failure_is_expected": windows_copy_failure_is_expected,
        "windows_copy_error": stderr.strip(),
    }


def validate_datacenter_taxonomy_dc_rebuild_acceptance(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    deployment_id: int,
    required_start_date: str,
    required_signal_date: str,
    evidence_dir: str | Path,
    scheduler_config: str | Path,
    expected_scheduler_taxonomy_version: str,
    expected_ticker_rows: int,
    expected_group_rows: int,
    expected_synthetic_rows: int,
    expected_index_rows: int,
    windows_copy_status: str,
    windows_copy_required: bool,
) -> dict[str, object]:
    proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    blocking_errors: list[str] = []
    scheduler = read_scheduler_config(str(scheduler_config))
    if scheduler.datacenter_taxonomy_version != expected_scheduler_taxonomy_version:
        blocking_errors.append("scheduler Datacenter taxonomy version is not expected V1")
    if scheduler.ec_source_layer_taxonomy_version != expected_scheduler_taxonomy_version:
        blocking_errors.append("scheduler EC taxonomy version is not expected V1")

    conn = _connect_readonly(analysis_db)
    try:
        deployment = _fetch_deployment_by_id(
            conn,
            deployment_id=deployment_id,
            ecosystem_code=ecosystem_code,
            proposed_taxonomy_version=proposed_taxonomy_version,
        )
        loaded = _fetch_loaded_taxonomy(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=proposed_taxonomy_version,
        )
        active = _fetch_active_taxonomy(conn, ecosystem_code=ecosystem_code)
        if deployment is None:
            blocking_errors.append("taxonomy deployment row not found")
        else:
            if str(deployment.get("rebuild_start_date")) != required_start_date:
                blocking_errors.append("deployment rebuild_start_date does not match required range")
            if str(deployment.get("activation_status")) == "ACTIVE":
                blocking_errors.append("deployment already active")
            if str(deployment.get("ec_rebuild_status")) != "NOT_STARTED":
                blocking_errors.append("EC rebuild status is not NOT_STARTED")
            if str(deployment.get("coverage_status")) != "NOT_STARTED":
                blocking_errors.append("coverage status is not NOT_STARTED")
            if str(deployment.get("parity_status")) != "NOT_STARTED":
                blocking_errors.append("parity status is not NOT_STARTED")
        taxonomy_version_id = None
        if loaded is None:
            blocking_errors.append("proposed taxonomy metadata is not loaded")
        else:
            taxonomy_version_id = int(loaded["taxonomy_version_id"])
            if int(loaded.get("is_active") or 0) != 0:
                blocking_errors.append("proposed taxonomy is already active")
            if str(loaded.get("source_hash") or "") != proposed_summary.source_sha256:
                blocking_errors.append("loaded taxonomy hash does not match proposed source")
        if active is None:
            blocking_errors.append("active taxonomy is missing")
        elif str(active.get("taxonomy_version_code")) == proposed_taxonomy_version:
            blocking_errors.append("proposed taxonomy is active unexpectedly")
        eco_row = conn.execute(
            "SELECT ecosystem_id FROM ec_ecosystem WHERE ecosystem_code = ?",
            (ecosystem_code,),
        ).fetchone()
        ecosystem_id = int(eco_row[0]) if eco_row is not None else 0

        fact_coverage = _dc_fact_coverage(
            conn,
            taxonomy_version=proposed_taxonomy_version,
            required_signal_date=required_signal_date,
            expected_ticker_rows=expected_ticker_rows,
            expected_group_rows=expected_group_rows,
            expected_synthetic_rows=expected_synthetic_rows,
            expected_index_rows=expected_index_rows,
        )
        for table_name, coverage in fact_coverage.items():
            if coverage["status"] != "OK":
                blocking_errors.append(f"DC fact coverage incomplete for {table_name}")
            if int(coverage["taxonomy_version_count"]) > 1:
                blocking_errors.append(f"taxonomy version impurity detected for {table_name}")

        duplicate_counts = _dc_duplicate_key_counts(conn, taxonomy_version=proposed_taxonomy_version)
        for table_name, duplicate_count in duplicate_counts.items():
            if duplicate_count:
                blocking_errors.append(f"duplicate DC keys detected for {table_name}")

        dc_watermarks = _dc_required_watermark_status(
            conn,
            taxonomy_version=proposed_taxonomy_version,
            required_signal_date=required_signal_date,
        )
        if dc_watermarks["status"] != "OK":
            blocking_errors.append("required DC watermark coverage is incomplete")

        stale_summary = {
            "stale_validation_status": "NOT_RUN",
            "stale_dc_rows": {},
            "stale_ec_rows": {},
        }
        if taxonomy_version_id is not None:
            stale_summary = validate_rebuild_stale_rows(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                taxonomy_version_code=proposed_taxonomy_version,
                date_from=required_start_date,
                date_to=required_signal_date,
                taxonomy_rows=proposed_summary.rows,
            )
            stale_dc_rows = stale_summary.get("stale_dc_rows", {})
            if any(int(value) for value in stale_dc_rows.values()):
                blocking_errors.append("stale V1 rows exist under V2 DC scope")
            else:
                stale_summary = {
                    **stale_summary,
                    "stale_validation_status": "OK_DC_SCOPE",
                    "ec_stale_rows_ignored_for_dc_only_acceptance": True,
                }
    finally:
        conn.close()

    report_artifacts = _dc_report_artifacts(evidence_dir, required_signal_date=required_signal_date)
    if report_artifacts["status"] != "OK":
        blocking_errors.append("required generated report artifacts are missing")
    stage_evidence = _dc_stage_evidence(
        evidence_dir,
        windows_copy_status=windows_copy_status,
        windows_copy_required=windows_copy_required,
    )
    if stage_evidence["status"] != "OK":
        blocking_errors.append("Stage 1-15 success and optional copy-only failure evidence is incomplete")
    if windows_copy_required:
        blocking_errors.append("Windows report copy was required")
    if windows_copy_status != "FAILED_OPTIONAL":
        blocking_errors.append("Windows report copy status is not accepted as FAILED_OPTIONAL")

    accepted = not blocking_errors
    evidence_payload = {
        "dc_rebuild_acceptance_status": "ACCEPTED" if accepted else "BLOCKED",
        "dc_rebuild_canonical_status": "OK" if not any("DC fact" in e for e in blocking_errors) else "BLOCKED",
        "dc_rebuild_report_generation_status": report_artifacts["status"],
        "dc_rebuild_windows_copy_status": windows_copy_status,
        "dc_rebuild_windows_copy_required": windows_copy_required,
        "dc_rebuild_windows_copy_error": stage_evidence["windows_copy_error"],
        "dc_rebuild_accepted_with_noncanonical_warning": bool(accepted and windows_copy_status == "FAILED_OPTIONAL"),
        "dc_rebuild_evidence_path": str(evidence_dir),
        "deployment_id": deployment_id,
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": proposed_taxonomy_version,
        "required_start_date": required_start_date,
        "required_signal_date": required_signal_date,
        "fact_coverage": fact_coverage,
        "duplicate_key_counts": duplicate_counts,
        "dc_watermark_status": dc_watermarks,
        "stale_row_validation": stale_summary,
        "report_artifacts": report_artifacts,
        "stage_evidence": stage_evidence,
        "blocking_errors": sorted(set(blocking_errors)),
    }
    evidence_sha = _json_sha256(evidence_payload)
    evidence_payload["dc_rebuild_evidence_sha256"] = evidence_sha
    return evidence_payload


def apply_datacenter_taxonomy_dc_rebuild_acceptance(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    deployment_id: int,
    required_start_date: str,
    required_signal_date: str,
    evidence_dir: str | Path,
    scheduler_config: str | Path,
    expected_scheduler_taxonomy_version: str,
    expected_ticker_rows: int,
    expected_group_rows: int,
    expected_synthetic_rows: int,
    expected_index_rows: int,
    windows_copy_status: str,
    windows_copy_required: bool,
) -> dict[str, object]:
    evidence = validate_datacenter_taxonomy_dc_rebuild_acceptance(
        analysis_db=analysis_db,
        ecosystem_code=ecosystem_code,
        proposed_taxonomy_version=proposed_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        deployment_id=deployment_id,
        required_start_date=required_start_date,
        required_signal_date=required_signal_date,
        evidence_dir=evidence_dir,
        scheduler_config=scheduler_config,
        expected_scheduler_taxonomy_version=expected_scheduler_taxonomy_version,
        expected_ticker_rows=expected_ticker_rows,
        expected_group_rows=expected_group_rows,
        expected_synthetic_rows=expected_synthetic_rows,
        expected_index_rows=expected_index_rows,
        windows_copy_status=windows_copy_status,
        windows_copy_required=windows_copy_required,
    )
    conn = _connect_readwrite(analysis_db)
    try:
        with conn:
            ensure_taxonomy_replacement_schema(conn)
            if evidence["dc_rebuild_acceptance_status"] != "ACCEPTED":
                return {
                    "status_update": "BLOCKED",
                    "deployment_id": deployment_id,
                    "dc_rebuild_accepted": False,
                    "evidence": evidence,
                }
            conn.execute(
                """
                UPDATE ec_taxonomy_change_deployment
                SET status = 'VALIDATION_REQUIRED',
                    dc_rebuild_status = 'OK',
                    validation_evidence_json = ?,
                    validation_evidence_sha256 = ?,
                    last_error = ?,
                    updated_at_utc = CURRENT_TIMESTAMP
                WHERE taxonomy_change_id = ?
                """,
                (
                    json.dumps(evidence, sort_keys=True, default=str),
                    evidence["dc_rebuild_evidence_sha256"],
                    "DC rebuild accepted with noncanonical optional Windows report-copy failure",
                    deployment_id,
                ),
            )
        return {
            "status_update": "VALIDATION_REQUIRED",
            "deployment_id": deployment_id,
            "dc_rebuild_accepted": True,
            "evidence": evidence,
        }
    finally:
        conn.close()


def apply_datacenter_taxonomy_rebuild_evidence(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    deployment_id: int,
    required_signal_date: str,
    coverage_status: str = "OK",
    parity_status: str = "OK",
    total_mismatch_count: int = 0,
) -> dict[str, object]:
    evidence = validate_datacenter_taxonomy_rebuild_evidence(
        analysis_db=analysis_db,
        ecosystem_code=ecosystem_code,
        proposed_taxonomy_version=proposed_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        deployment_id=deployment_id,
        required_signal_date=required_signal_date,
        coverage_status=coverage_status,
        parity_status=parity_status,
        total_mismatch_count=total_mismatch_count,
    )
    conn = _connect_readwrite(analysis_db)
    try:
        with conn:
            ensure_taxonomy_replacement_schema(conn)
            if evidence["evidence_status"] != "READY_TO_ACTIVATE":
                conn.execute(
                    """
                    UPDATE ec_taxonomy_change_deployment
                    SET status = 'FAILED',
                        last_error = ?,
                        validation_evidence_json = ?,
                        validation_evidence_sha256 = ?,
                        updated_at_utc = CURRENT_TIMESTAMP
                    WHERE taxonomy_change_id = ?
                    """,
                    (
                        "; ".join(evidence["blocking_errors"]),
                        json.dumps(evidence, sort_keys=True, default=str),
                        evidence["evidence_sha256"],
                        deployment_id,
                    ),
                )
                return {
                    "status_update": "FAILED",
                    "deployment_id": deployment_id,
                    "ready_to_activate": False,
                    "evidence": evidence,
                }
            conn.execute(
                """
                UPDATE ec_taxonomy_change_deployment
                SET status = 'READY_TO_ACTIVATE',
                    dc_rebuild_status = 'OK',
                    ec_rebuild_status = 'OK',
                    coverage_status = 'OK',
                    parity_status = 'OK',
                    validation_completed_at_utc = CURRENT_TIMESTAMP,
                    validation_evidence_json = ?,
                    validation_evidence_sha256 = ?,
                    last_error = NULL,
                    updated_at_utc = CURRENT_TIMESTAMP
                WHERE taxonomy_change_id = ?
                """,
                (
                    json.dumps(evidence, sort_keys=True, default=str),
                    evidence["evidence_sha256"],
                    deployment_id,
                ),
            )
        return {
            "status_update": "READY_TO_ACTIVATE",
            "deployment_id": deployment_id,
            "ready_to_activate": True,
            "evidence": evidence,
        }
    finally:
        conn.close()


def _resolve_ecosystem_id_for_code(conn: sqlite3.Connection, ecosystem_code: str) -> int | None:
    if "ec_ecosystem" not in _table_names(conn):
        return None
    row = conn.execute(
        "SELECT ecosystem_id FROM ec_ecosystem WHERE ecosystem_code = ?",
        (ecosystem_code,),
    ).fetchone()
    return int(row[0]) if row is not None else None


def _row_fingerprint_expr(conn: sqlite3.Connection, table_name: str) -> tuple[str, ...]:
    preferred = (
        "ecosystem_id",
        "taxonomy_version_id",
        "signal_date",
        "entity_id",
        "signal_version",
        "ohlc_calc_version",
        "calc_version",
    )
    columns = _table_columns(conn, table_name)
    return tuple(column for column in preferred if column in columns)


def _fact_scope_hash(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    where_sql: str,
    params: tuple[object, ...],
) -> str:
    columns = _row_fingerprint_expr(conn, table_name)
    if not columns:
        columns = ("rowid",)
    select_list = ", ".join(columns)
    rows = conn.execute(
        f"SELECT {select_list} FROM {table_name} WHERE {where_sql} ORDER BY {select_list}",
        params,
    ).fetchall()
    payload = {
        "table_name": table_name,
        "columns": columns,
        "rows": [tuple(row[column] for column in columns) for row in rows],
    }
    return _json_sha256(payload)


def _cleanup_table_plan(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    ecosystem_id: int,
    target_taxonomy_version_id: int,
    date_from: str,
    date_to: str,
) -> dict[str, object]:
    blocking_errors: list[str] = []
    warnings: list[str] = []
    if table_name not in _table_names(conn):
        return {
            "table_name": table_name,
            "target_v2_row_count": 0,
            "old_version_row_count": 0,
            "old_version_taxonomy_ids": [],
            "old_version_min_date": None,
            "old_version_max_date": None,
            "delete_candidate_count": 0,
            "delete_candidate_key_hash": _json_sha256({"table_name": table_name, "rows": []}),
            "unexpected_target_rows": 0,
            "unexpected_other_ecosystem_rows": 0,
            "safe_to_apply": False,
            "blocking_errors": [f"missing canonical EC fact table: {table_name}"],
            "warnings": warnings,
        }
    required_columns = {"ecosystem_id", "taxonomy_version_id", CANONICAL_EC_FACT_DATE_COLUMNS[table_name]}
    missing = sorted(required_columns - _table_columns(conn, table_name))
    if missing:
        return {
            "table_name": table_name,
            "target_v2_row_count": 0,
            "old_version_row_count": 0,
            "old_version_taxonomy_ids": [],
            "old_version_min_date": None,
            "old_version_max_date": None,
            "delete_candidate_count": 0,
            "delete_candidate_key_hash": _json_sha256({"table_name": table_name, "rows": []}),
            "unexpected_target_rows": 0,
            "unexpected_other_ecosystem_rows": 0,
            "safe_to_apply": False,
            "blocking_errors": [f"{table_name} missing required cleanup columns: {missing}"],
            "warnings": warnings,
        }
    date_column = CANONICAL_EC_FACT_DATE_COLUMNS[table_name]
    target_row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE ecosystem_id = ?
          AND taxonomy_version_id = ?
          AND {date_column} >= ?
          AND {date_column} <= ?
        """,
        (ecosystem_id, target_taxonomy_version_id, date_from, date_to),
    ).fetchone()
    old_row = conn.execute(
        f"""
        SELECT COUNT(*), MIN({date_column}), MAX({date_column})
        FROM {table_name}
        WHERE ecosystem_id = ?
          AND taxonomy_version_id <> ?
          AND {date_column} >= ?
          AND {date_column} <= ?
        """,
        (ecosystem_id, target_taxonomy_version_id, date_from, date_to),
    ).fetchone()
    old_ids = [
        int(row[0])
        for row in conn.execute(
            f"""
            SELECT DISTINCT taxonomy_version_id
            FROM {table_name}
            WHERE ecosystem_id = ?
              AND taxonomy_version_id <> ?
              AND {date_column} >= ?
              AND {date_column} <= ?
            ORDER BY taxonomy_version_id
            """,
            (ecosystem_id, target_taxonomy_version_id, date_from, date_to),
        ).fetchall()
        if row[0] is not None
    ]
    candidate_hash = _fact_scope_hash(
        conn,
        table_name=table_name,
        where_sql=(
            f"ecosystem_id = ? AND taxonomy_version_id <> ? "
            f"AND {date_column} >= ? AND {date_column} <= ?"
        ),
        params=(ecosystem_id, target_taxonomy_version_id, date_from, date_to),
    )
    unexpected_target = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE ecosystem_id = ?
          AND taxonomy_version_id = ?
          AND ({date_column} < ? OR {date_column} > ?)
        """,
        (ecosystem_id, target_taxonomy_version_id, date_from, date_to),
    ).fetchone()[0]
    return {
        "table_name": table_name,
        "target_v2_row_count": int(target_row[0]),
        "old_version_row_count": int(old_row[0]),
        "old_version_taxonomy_ids": old_ids,
        "old_version_min_date": old_row[1],
        "old_version_max_date": old_row[2],
        "delete_candidate_count": int(old_row[0]),
        "delete_candidate_key_hash": candidate_hash,
        "unexpected_target_rows": int(unexpected_target),
        "unexpected_other_ecosystem_rows": 0,
        "safe_to_apply": not blocking_errors,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
    }


def plan_ec_taxonomy_replacement_cleanup(
    *,
    db: str | Path,
    ecosystem: str,
    target_taxonomy_version: str,
    deployment_id: int,
    date_from: str,
    date_to: str,
    scheduler_config: str | Path | None = None,
    expected_scheduler_taxonomy_version: str | None = None,
) -> dict[str, object]:
    blocking_errors: list[str] = []
    conn = _connect_readonly(db)
    try:
        ecosystem_id = _resolve_ecosystem_id_for_code(conn, ecosystem)
        if ecosystem_id is None:
            blocking_errors.append(f"ecosystem not found: {ecosystem}")
            taxonomy = None
        else:
            taxonomy = _fetch_loaded_taxonomy(
                conn,
                ecosystem_code=ecosystem,
                taxonomy_version_code=target_taxonomy_version,
            )
        if taxonomy is None:
            blocking_errors.append("target taxonomy metadata is not loaded")
            target_taxonomy_version_id = None
        else:
            target_taxonomy_version_id = int(taxonomy["taxonomy_version_id"])
            if int(taxonomy.get("is_active") or 0) != 0:
                blocking_errors.append("target taxonomy is already active")
        active = _fetch_active_taxonomy(conn, ecosystem_code=ecosystem)
        if active is None:
            blocking_errors.append("active taxonomy is missing")
        elif str(active.get("taxonomy_version_code")) == target_taxonomy_version:
            blocking_errors.append("target taxonomy is active unexpectedly")
        deployment = _fetch_deployment_by_id(
            conn,
            deployment_id=deployment_id,
            ecosystem_code=ecosystem,
            proposed_taxonomy_version=target_taxonomy_version,
        )
        if deployment is None:
            blocking_errors.append("taxonomy deployment row not found")
        else:
            if str(deployment.get("dc_rebuild_status")) != "OK":
                blocking_errors.append("DC rebuild status is not OK")
            if str(deployment.get("activation_status")) == "ACTIVE":
                blocking_errors.append("deployment already active")

        table_plans: list[dict[str, object]] = []
        if ecosystem_id is not None and target_taxonomy_version_id is not None:
            for table_name in CANONICAL_EC_FACT_TABLES:
                table_plan = _cleanup_table_plan(
                    conn,
                    table_name=table_name,
                    ecosystem_id=ecosystem_id,
                    target_taxonomy_version_id=target_taxonomy_version_id,
                    date_from=date_from,
                    date_to=date_to,
                )
                table_plans.append(table_plan)
                blocking_errors.extend(str(error) for error in table_plan["blocking_errors"])
        else:
            table_plans = []
    finally:
        conn.close()

    if scheduler_config is not None and expected_scheduler_taxonomy_version is not None:
        scheduler = read_scheduler_config(str(scheduler_config))
        if scheduler.datacenter_taxonomy_version != expected_scheduler_taxonomy_version:
            blocking_errors.append("scheduler Datacenter taxonomy version is not expected active version")
        if scheduler.ec_source_layer_taxonomy_version != expected_scheduler_taxonomy_version:
            blocking_errors.append("scheduler EC taxonomy version is not expected active version")

    plan_payload = {
        "ecosystem_code": ecosystem,
        "ecosystem_id": ecosystem_id,
        "target_taxonomy_version": target_taxonomy_version,
        "target_taxonomy_version_id": target_taxonomy_version_id,
        "deployment_id": deployment_id,
        "date_from": date_from,
        "date_to": date_to,
        "tables": table_plans,
    }
    cleanup_plan_hash = _json_sha256(plan_payload)
    delete_candidate_hash = _json_sha256(
        {
            "cleanup_plan_hash": cleanup_plan_hash,
            "tables": [
                {
                    "table_name": table["table_name"],
                    "delete_candidate_count": table["delete_candidate_count"],
                    "delete_candidate_key_hash": table["delete_candidate_key_hash"],
                }
                for table in table_plans
            ],
        }
    )
    return {
        "cleanup_plan_status": "READY_TO_APPLY" if not blocking_errors else "BLOCKED",
        "safe_to_apply": not blocking_errors,
        "cleanup_plan_hash": cleanup_plan_hash,
        "delete_candidate_hash": delete_candidate_hash,
        "blocking_errors": sorted(set(blocking_errors)),
        **plan_payload,
    }


def _ec_fact_table_hashes(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    date_from: str,
    date_to: str,
) -> dict[str, str]:
    return {
        table_name: _fact_scope_hash(
            conn,
            table_name=table_name,
            where_sql=(
                f"ecosystem_id = ? AND taxonomy_version_id = ? "
                f"AND {CANONICAL_EC_FACT_DATE_COLUMNS[table_name]} >= ? "
                f"AND {CANONICAL_EC_FACT_DATE_COLUMNS[table_name]} <= ?"
            ),
            params=(ecosystem_id, taxonomy_version_id, date_from, date_to),
        )
        for table_name in CANONICAL_EC_FACT_TABLES
    }


def _validate_v2_fact_state(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    required_signal_date: str,
    date_from: str,
    date_to: str,
) -> tuple[dict[str, object], list[str]]:
    blocking_errors: list[str] = []
    heads = _ec_fact_heads(conn, ecosystem_id=ecosystem_id, taxonomy_version_id=taxonomy_version_id)
    for table_name, head in heads.items():
        if head is None or head < required_signal_date:
            blocking_errors.append(f"V2 EC fact head incomplete for {table_name}")
    outside_range: dict[str, int] = {}
    duplicate_counts: dict[str, int] = {}
    for table_name in CANONICAL_EC_FACT_TABLES:
        date_column = CANONICAL_EC_FACT_DATE_COLUMNS[table_name]
        outside = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {table_name}
            WHERE ecosystem_id = ?
              AND taxonomy_version_id = ?
              AND ({date_column} < ? OR {date_column} > ?)
            """,
            (ecosystem_id, taxonomy_version_id, date_from, date_to),
        ).fetchone()[0]
        outside_range[table_name] = int(outside)
        if outside:
            blocking_errors.append(f"V2 rows outside rebuild range for {table_name}")
        columns = _row_fingerprint_expr(conn, table_name)
        key_columns = [column for column in columns if column not in {"ecosystem_id", "taxonomy_version_id"}]
        if key_columns:
            group_by = ", ".join(key_columns)
            duplicate = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT {group_by}, COUNT(*) AS c
                    FROM {table_name}
                    WHERE ecosystem_id = ?
                      AND taxonomy_version_id = ?
                    GROUP BY {group_by}
                    HAVING c > 1
                )
                """,
                (ecosystem_id, taxonomy_version_id),
            ).fetchone()[0]
        else:
            duplicate = 0
        duplicate_counts[table_name] = int(duplicate)
        if duplicate:
            blocking_errors.append(f"V2 duplicate keys for {table_name}")
    return {
        "status": "OK" if not blocking_errors else "FAILED",
        "ec_fact_heads": heads,
        "outside_range_counts": outside_range,
        "duplicate_key_counts": duplicate_counts,
    }, blocking_errors


def apply_ec_taxonomy_replacement_cleanup(
    *,
    db: str | Path,
    ecosystem: str,
    target_taxonomy_version: str,
    deployment_id: int,
    date_from: str,
    date_to: str,
    confirm_db: str | Path,
    confirm_ecosystem: str,
    confirm_target_taxonomy_version: str,
    confirm_deployment_id: int,
    confirm_date_from: str,
    confirm_date_to: str,
    confirm_delete_candidate_hash: str,
    scheduler_config: str | Path | None = None,
    expected_scheduler_taxonomy_version: str | None = None,
    invocation_source: str = "APPLY_EC_TAXONOMY_REPLACEMENT_CLEANUP",
) -> dict[str, object]:
    blocking_errors: list[str] = []
    if Path(db) != Path(confirm_db):
        blocking_errors.append("confirm-db does not match db")
    if ecosystem != confirm_ecosystem:
        blocking_errors.append("confirm-ecosystem does not match ecosystem")
    if target_taxonomy_version != confirm_target_taxonomy_version:
        blocking_errors.append("confirm-target-taxonomy-version does not match target")
    if deployment_id != confirm_deployment_id:
        blocking_errors.append("confirm-deployment-id does not match deployment")
    if date_from != confirm_date_from or date_to != confirm_date_to:
        blocking_errors.append("confirmed date range does not match requested range")

    plan = plan_ec_taxonomy_replacement_cleanup(
        db=db,
        ecosystem=ecosystem,
        target_taxonomy_version=target_taxonomy_version,
        deployment_id=deployment_id,
        date_from=date_from,
        date_to=date_to,
        scheduler_config=scheduler_config,
        expected_scheduler_taxonomy_version=expected_scheduler_taxonomy_version,
    )
    if not plan["safe_to_apply"]:
        blocking_errors.extend(str(error) for error in plan["blocking_errors"])
    if plan["delete_candidate_hash"] != confirm_delete_candidate_hash:
        blocking_errors.append("delete candidate hash mismatch")

    conn = _connect_readonly(db)
    try:
        ecosystem_id = plan.get("ecosystem_id")
        taxonomy_version_id = plan.get("target_taxonomy_version_id")
        deployment = _fetch_deployment_by_id(
            conn,
            deployment_id=deployment_id,
            ecosystem_code=ecosystem,
            proposed_taxonomy_version=target_taxonomy_version,
        )
        if deployment is None:
            blocking_errors.append("taxonomy deployment row not found")
        elif str(deployment.get("dc_rebuild_status")) != "OK":
            blocking_errors.append("DC rebuild status is not OK")
        if ecosystem_id is not None and taxonomy_version_id is not None:
            fact_state, fact_errors = _validate_v2_fact_state(
                conn,
                ecosystem_id=int(ecosystem_id),
                taxonomy_version_id=int(taxonomy_version_id),
                required_signal_date=date_to,
                date_from=date_from,
                date_to=date_to,
            )
            blocking_errors.extend(fact_errors)
            pre_hashes = _ec_fact_table_hashes(
                conn,
                ecosystem_id=int(ecosystem_id),
                taxonomy_version_id=int(taxonomy_version_id),
                date_from=date_from,
                date_to=date_to,
            )
        else:
            fact_state = {"status": "FAILED"}
            pre_hashes = {}
    finally:
        conn.close()

    if blocking_errors:
        return {
            "cleanup_apply_status": "BLOCKED",
            "cleanup_applied": False,
            "blocking_errors": sorted(set(blocking_errors)),
            "plan": plan,
            "fact_state": fact_state,
        }

    started_at = _utc_now()
    deleted_counts: dict[str, int] = {}
    conn = _connect_readwrite(db)
    try:
        with conn:
            for table in plan["tables"]:
                table_name = str(table["table_name"])
                date_column = CANONICAL_EC_FACT_DATE_COLUMNS[table_name]
                cursor = conn.execute(
                    f"""
                    DELETE FROM {table_name}
                    WHERE ecosystem_id = ?
                      AND taxonomy_version_id <> ?
                      AND {date_column} >= ?
                      AND {date_column} <= ?
                    """,
                    (int(plan["ecosystem_id"]), int(plan["target_taxonomy_version_id"]), date_from, date_to),
                )
                deleted_counts[table_name] = int(cursor.rowcount or 0)
            post_hashes = _ec_fact_table_hashes(
                conn,
                ecosystem_id=int(plan["ecosystem_id"]),
                taxonomy_version_id=int(plan["target_taxonomy_version_id"]),
                date_from=date_from,
                date_to=date_to,
            )
            if post_hashes != pre_hashes:
                raise RuntimeError("V2 fact hashes changed during cleanup")
            evidence = {
                "deployment_id": deployment_id,
                "ecosystem_code": ecosystem,
                "target_taxonomy_version": target_taxonomy_version,
                "target_taxonomy_version_id": plan["target_taxonomy_version_id"],
                "date_from": date_from,
                "date_to": date_to,
                "cleanup_plan_hash": plan["cleanup_plan_hash"],
                "delete_candidate_hash": plan["delete_candidate_hash"],
                "started_at_utc": started_at,
                "completed_at_utc": _utc_now(),
                "status": "NO_CHANGE" if not any(deleted_counts.values()) else "APPLIED",
                "per_table_candidate_counts": {
                    str(table["table_name"]): int(table["delete_candidate_count"])
                    for table in plan["tables"]
                },
                "per_table_deleted_counts": deleted_counts,
                "old_taxonomy_ids": sorted(
                    {
                        int(taxonomy_id)
                        for table in plan["tables"]
                        for taxonomy_id in table["old_version_taxonomy_ids"]
                    }
                ),
                "pre_cleanup_fact_hashes": pre_hashes,
                "post_cleanup_fact_hashes": post_hashes,
                "invocation_source": invocation_source,
                "error": None,
            }
            if "ec_taxonomy_change_deployment" in _table_names(conn):
                conn.execute(
                    """
                    UPDATE ec_taxonomy_change_deployment
                    SET rebuild_evidence_json = ?,
                        rebuild_evidence_sha256 = ?,
                        updated_at_utc = CURRENT_TIMESTAMP
                    WHERE taxonomy_change_id = ?
                    """,
                    (
                        json.dumps(evidence, sort_keys=True, default=str),
                        _json_sha256(evidence),
                        deployment_id,
                    ),
                )
    finally:
        conn.close()

    return {
        "cleanup_apply_status": evidence["status"],
        "cleanup_applied": any(deleted_counts.values()),
        "deployment_id": deployment_id,
        "deleted_counts": deleted_counts,
        "evidence": evidence,
        "plan": plan,
    }


def validate_ec_taxonomy_rebuild_existing_facts(
    *,
    db: str | Path,
    ecosystem: str,
    target_taxonomy_version: str,
    taxonomy_csv: str | Path,
    deployment_id: int,
    date_from: str,
    date_to: str,
    coverage_status: str = "OK",
    parity_status: str = "OK",
    total_mismatch_count: int = 0,
) -> dict[str, object]:
    taxonomy_summary = summarize_taxonomy_csv(taxonomy_csv, target_taxonomy_version)
    blocking_errors: list[str] = []
    conn = _connect_readonly(db)
    try:
        ecosystem_id = _resolve_ecosystem_id_for_code(conn, ecosystem)
        loaded = _fetch_loaded_taxonomy(
            conn,
            ecosystem_code=ecosystem,
            taxonomy_version_code=target_taxonomy_version,
        )
        deployment = _fetch_deployment_by_id(
            conn,
            deployment_id=deployment_id,
            ecosystem_code=ecosystem,
            proposed_taxonomy_version=target_taxonomy_version,
        )
        if ecosystem_id is None:
            blocking_errors.append(f"ecosystem not found: {ecosystem}")
            taxonomy_version_id = None
        elif loaded is None:
            blocking_errors.append("target taxonomy metadata is not loaded")
            taxonomy_version_id = None
        else:
            taxonomy_version_id = int(loaded["taxonomy_version_id"])
            if str(loaded.get("source_hash") or "") != taxonomy_summary.source_sha256:
                blocking_errors.append("loaded taxonomy hash does not match source CSV")
        if deployment is None:
            blocking_errors.append("taxonomy deployment row not found")
        if coverage_status not in {"OK", "OK_WITH_WARNINGS"}:
            blocking_errors.append("coverage is not accepted")
        if parity_status not in {"OK", "OK_WITH_WARNINGS"} or int(total_mismatch_count) != 0:
            blocking_errors.append("parity is not accepted")
        if ecosystem_id is not None and taxonomy_version_id is not None:
            fact_state, fact_errors = _validate_v2_fact_state(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                required_signal_date=date_to,
                date_from=date_from,
                date_to=date_to,
            )
            blocking_errors.extend(fact_errors)
            stale_summary = validate_rebuild_stale_rows(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                taxonomy_version_code=target_taxonomy_version,
                date_from=date_from,
                date_to=date_to,
                taxonomy_rows=taxonomy_summary.rows,
            )
            if stale_summary["stale_validation_status"] != "OK":
                blocking_errors.append("stale rows block validation-only recovery")
        else:
            fact_state = {"status": "FAILED"}
            stale_summary = {"stale_validation_status": "NOT_RUN", "stale_dc_rows": {}, "stale_ec_rows": {}}
    finally:
        conn.close()
    return {
        "validation_mode": "EXISTING_REBUILT_FACTS",
        "validation_status": "OK" if not blocking_errors else "BLOCKED",
        "whole_range_validation_status": "OK" if not blocking_errors else "FAILED",
        "coverage_status": coverage_status,
        "parity_status": parity_status,
        "total_mismatch_count": int(total_mismatch_count),
        "stale_row_validation": stale_summary,
        "stale_row_count": sum(int(value) for value in (stale_summary.get("stale_ec_rows") or {}).values()),
        "fact_state": fact_state,
        "loaders_rerun": False,
        "chunks_rerun": False,
        "blocking_errors": sorted(set(blocking_errors)),
    }


def finalize_ec_taxonomy_rebuild_validation(
    *,
    db: str | Path,
    ecosystem: str,
    target_taxonomy_version: str,
    taxonomy_csv: str | Path,
    deployment_id: int,
    date_from: str,
    date_to: str,
    coverage_status: str = "OK",
    parity_status: str = "OK",
    total_mismatch_count: int = 0,
    finalize_watermarks: bool = False,
    update_deployment_evidence: bool = False,
) -> dict[str, object]:
    validation = validate_ec_taxonomy_rebuild_existing_facts(
        db=db,
        ecosystem=ecosystem,
        target_taxonomy_version=target_taxonomy_version,
        taxonomy_csv=taxonomy_csv,
        deployment_id=deployment_id,
        date_from=date_from,
        date_to=date_to,
        coverage_status=coverage_status,
        parity_status=parity_status,
        total_mismatch_count=total_mismatch_count,
    )
    if validation["validation_status"] != "OK":
        return {
            "finalization_status": "BLOCKED",
            "watermark_finalization_performed": False,
            "deployment_evidence_updated": False,
            "validation": validation,
        }
    watermark_summary = {"status": "NOT_REQUESTED"}
    if finalize_watermarks:
        from rawcandle.ec_pipeline_watermark_loader import (
            advance_ec_pipeline_watermarks_after_historical_backfill,
        )

        watermark_summary = advance_ec_pipeline_watermarks_after_historical_backfill(
            target_db_path=str(db),
            ecosystem_code=ecosystem,
            taxonomy_version_code=target_taxonomy_version,
            latest_signal_date=date_to,
            taxonomy_rebuild=True,
        )
    evidence_summary = {"status_update": "NOT_REQUESTED"}
    if update_deployment_evidence:
        evidence_summary = apply_datacenter_taxonomy_rebuild_evidence(
            analysis_db=db,
            ecosystem_code=ecosystem,
            proposed_taxonomy_version=target_taxonomy_version,
            proposed_taxonomy_csv=taxonomy_csv,
            deployment_id=deployment_id,
            required_signal_date=date_to,
            coverage_status="OK" if coverage_status == "OK_WITH_WARNINGS" else coverage_status,
            parity_status="OK" if parity_status == "OK_WITH_WARNINGS" else parity_status,
            total_mismatch_count=total_mismatch_count,
        )
    return {
        "finalization_status": "OK",
        "watermark_finalization_performed": bool(finalize_watermarks),
        "deployment_evidence_updated": bool(update_deployment_evidence),
        "validation": validation,
        "watermark_summary": watermark_summary,
        "evidence_summary": evidence_summary,
        "retry_policy": "NO_REBUILD_RETRY_NEEDED_VALIDATION_ONLY_AFTER_FIX",
    }


def validate_rebuild_stale_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    taxonomy_version_code: str,
    date_from: str,
    date_to: str,
    taxonomy_rows: tuple[DatacenterTaxonomyRow, ...],
) -> dict[str, object]:
    taxonomy_tickers = {row.ticker for row in taxonomy_rows}
    taxonomy_layers = {row.layer for row in taxonomy_rows}
    taxonomy_subindustries = {row.subindustry for row in taxonomy_rows}
    stale_dc: dict[str, object] = {}
    stale_ec: dict[str, int] = {}

    if (
        "dc_ticker_swing_signal_daily" in _table_names(conn)
        and {"ticker", "taxonomy_version", "signal_date"}.issubset(
            _table_columns(conn, "dc_ticker_swing_signal_daily")
        )
    ):
        rows = conn.execute(
            """
            SELECT DISTINCT ticker
            FROM dc_ticker_swing_signal_daily
            WHERE taxonomy_version = ?
              AND signal_date >= ?
              AND signal_date <= ?
            ORDER BY ticker
            """,
            (taxonomy_version_code, date_from, date_to),
        ).fetchall()
        stale_tickers = sorted({str(row[0]) for row in rows} - taxonomy_tickers)
        if stale_tickers:
            stale_dc["dc_ticker_swing_signal_daily"] = stale_tickers

    group_checks = (
        ("dc_group_swing_signal_daily", "signal_date"),
        ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
        ("dc_group_index_daily", "index_date"),
    )
    allowed_by_group_type = {
        "ecosystem": {"DC_ECOSYSTEM_TOTAL"},
        "layer": taxonomy_layers,
        "subindustry": taxonomy_subindustries,
    }
    for table_name, date_column in group_checks:
        if table_name not in _table_names(conn):
            continue
        if not {"group_type", "group_name", "taxonomy_version", date_column}.issubset(
            _table_columns(conn, table_name)
        ):
            continue
        rows = conn.execute(
            f"""
            SELECT DISTINCT group_type, group_name
            FROM {table_name}
            WHERE taxonomy_version = ?
              AND {date_column} >= ?
              AND {date_column} <= ?
            ORDER BY group_type, group_name
            """,
            (taxonomy_version_code, date_from, date_to),
        ).fetchall()
        invalid = [
            [str(row["group_type"]), str(row["group_name"])]
            for row in rows
            if str(row["group_name"]) not in allowed_by_group_type.get(str(row["group_type"]), set())
        ]
        if invalid:
            stale_dc[table_name] = invalid

    for table_name in CANONICAL_EC_FACT_TABLES:
        if table_name not in _table_names(conn):
            continue
        columns = _table_columns(conn, table_name)
        if "ecosystem_id" not in columns or "taxonomy_version_id" not in columns:
            continue
        row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {table_name}
            WHERE ecosystem_id = ?
              AND taxonomy_version_id <> ?
              AND signal_date >= ?
              AND signal_date <= ?
            """,
            (ecosystem_id, taxonomy_version_id, date_from, date_to),
        ).fetchone()
        count = int(row[0])
        if count:
            stale_ec[table_name] = count

    return {
        "stale_validation_status": "OK" if not stale_dc and not stale_ec else "BLOCKED_STALE_ROWS",
        "stale_dc_rows": stale_dc,
        "stale_ec_rows": stale_ec,
    }


def plan_datacenter_taxonomy_activation(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    required_signal_date: str,
    deployment_id: int | None = None,
    current_taxonomy_version: str | None = None,
    current_taxonomy_csv: str | Path | None = None,
    scheduler_config_path: str | Path | None = None,
    expected_scheduler_taxonomy_version: str | None = None,
    expected_scheduler_taxonomy_csv: str | Path | None = None,
) -> dict[str, object]:
    blocking_errors: list[str] = []
    warnings: list[str] = []
    current_db_taxonomy_status = "UNKNOWN"
    scheduler_summary: dict[str, object] = {
        "current_scheduler_taxonomy_status": "NOT_CHECKED",
        "current_scheduler_datacenter_version": None,
        "current_scheduler_ec_version": None,
        "current_scheduler_config_safe_to_transition": False,
        "proposed_scheduler_taxonomy_status": "NOT_CHECKED",
        "proposed_scheduler_config_safe": False,
        "proposed_scheduler_config": None,
        "config_transition_required": False,
        "scheduler_changed_keys": [],
        "scheduler_unexpected_changed_keys": [],
    }
    proposed_summary: TaxonomySummary | None = None
    try:
        proposed_summary = summarize_taxonomy_csv(proposed_taxonomy_csv, proposed_taxonomy_version)
    except Exception as exc:
        blocking_errors.append(f"proposed taxonomy invalid: {exc}")

    conn = _connect_readonly(analysis_db)
    try:
        loaded = _fetch_loaded_taxonomy(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=proposed_taxonomy_version,
        )
        loaded_current = None
        if loaded is None:
            blocking_errors.append("proposed taxonomy metadata is not loaded")
            taxonomy_version_id = None
        else:
            taxonomy_version_id = int(loaded["taxonomy_version_id"])
            if proposed_summary is not None and str(loaded.get("source_hash") or "") != proposed_summary.source_sha256:
                blocking_errors.append("loaded taxonomy hash does not match proposed source")

        if "ec_taxonomy_change_deployment" not in _table_names(conn):
            blocking_errors.append("taxonomy change deployment state table is missing")
            deployment = None
        else:
            if deployment_id is not None:
                deployment = conn.execute(
                    """
                    SELECT *
                    FROM ec_taxonomy_change_deployment
                    WHERE taxonomy_change_id = ?
                      AND ecosystem_code = ?
                      AND proposed_taxonomy_version = ?
                    """,
                    (deployment_id, ecosystem_code, proposed_taxonomy_version),
                ).fetchone()
            else:
                deployment = conn.execute(
                    """
                    SELECT *
                    FROM ec_taxonomy_change_deployment
                    WHERE ecosystem_code = ?
                      AND proposed_taxonomy_version = ?
                    """,
                    (ecosystem_code, proposed_taxonomy_version),
                ).fetchone()
            if deployment is None:
                blocking_errors.append("taxonomy deployment state is missing")
            else:
                current_taxonomy_version = current_taxonomy_version or str(
                    deployment["previous_taxonomy_version"]
                )
                if str(deployment["dc_rebuild_status"]) != "OK":
                    blocking_errors.append("full DC rebuild is incomplete")
                if str(deployment["ec_rebuild_status"]) != "OK":
                    blocking_errors.append("full EC rebuild is incomplete")
                if str(deployment["coverage_status"]) != "OK":
                    blocking_errors.append("coverage is not accepted")
                if str(deployment["parity_status"]) != "OK":
                    blocking_errors.append("parity is not accepted")

        if current_taxonomy_version:
            loaded_current = _fetch_loaded_taxonomy(
                conn,
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=current_taxonomy_version,
            )
            if loaded_current is None:
                blocking_errors.append("current taxonomy metadata is not loaded")

        active_rows = []
        if "ec_taxonomy_version" in _table_names(conn):
            active_rows = conn.execute(
                """
                SELECT taxonomy_version_code
                FROM ec_taxonomy_version
                WHERE is_active = 1
                ORDER BY taxonomy_version_code
                """
            ).fetchall()
        active_versions = [str(row[0]) for row in active_rows]
        current_db_taxonomy_status = "UNKNOWN"
        if current_taxonomy_version and active_versions == [current_taxonomy_version]:
            current_db_taxonomy_status = "EXPECTED_CURRENT"
        elif active_versions == [proposed_taxonomy_version]:
            current_db_taxonomy_status = "ALREADY_PROPOSED"
        elif active_versions:
            current_db_taxonomy_status = "BLOCKED_MIXED_OR_UNEXPECTED"
            blocking_errors.append("database active taxonomy state is mixed or unexpected")
        else:
            current_db_taxonomy_status = "BLOCKED_NO_ACTIVE_TAXONOMY"
            blocking_errors.append("database has no active taxonomy")

        if taxonomy_version_id is not None:
            for table_name, date_column in CANONICAL_DC_FACT_TABLES:
                if table_name not in _table_names(conn):
                    blocking_errors.append(f"missing DC fact table: {table_name}")
                    continue
                row = conn.execute(
                    f"SELECT MAX({date_column}) FROM {table_name} WHERE taxonomy_version = ?",
                    (proposed_taxonomy_version,),
                ).fetchone()
                if row is None or row[0] is None or str(row[0]) < required_signal_date:
                    blocking_errors.append(f"DC fact head incomplete for {table_name}")
            for table_name in CANONICAL_EC_FACT_TABLES:
                if table_name not in _table_names(conn):
                    blocking_errors.append(f"missing EC fact table: {table_name}")
                    continue
                row = conn.execute(
                    f"SELECT MAX(signal_date) FROM {table_name} WHERE taxonomy_version_id = ?",
                    (taxonomy_version_id,),
                ).fetchone()
                if row is None or row[0] is None or str(row[0]) < required_signal_date:
                    blocking_errors.append(f"EC fact head incomplete for {table_name}")

            if "ec_pipeline_watermark" in _table_names(conn) and "taxonomy_version_id" in _table_columns(conn, "ec_pipeline_watermark"):
                ecosystem_row = conn.execute(
                    "SELECT ecosystem_id FROM ec_ecosystem WHERE ecosystem_code = ?",
                    (ecosystem_code,),
                ).fetchone()
                ecosystem_id = int(ecosystem_row[0]) if ecosystem_row is not None else None
                if ecosystem_id is None:
                    blocking_errors.append(f"ecosystem not found: {ecosystem_code}")
                else:
                    for pipeline_name, source_table in CANONICAL_EC_WATERMARK_SCOPES:
                        row = conn.execute(
                            """
                            SELECT latest_signal_date, status, taxonomy_version_id
                            FROM ec_pipeline_watermark
                            WHERE ecosystem_id = ?
                              AND pipeline_name = ?
                              AND source_table = ?
                            """,
                            (ecosystem_id, pipeline_name, source_table),
                        ).fetchone()
                        if row is None:
                            blocking_errors.append(f"missing EC canonical watermark scope: {pipeline_name}")
                            continue
                        if row["taxonomy_version_id"] != taxonomy_version_id:
                            blocking_errors.append("EC watermark lineage does not belong to proposed taxonomy")
                        if row["latest_signal_date"] is None or str(row["latest_signal_date"]) < required_signal_date:
                            blocking_errors.append(f"EC watermark head incomplete for {pipeline_name}")
                        if str(row["status"]) != "OK":
                            blocking_errors.append(f"EC watermark status is not OK for {pipeline_name}")
            else:
                blocking_errors.append("EC watermark taxonomy lineage field is missing")

        scheduler_current_version = current_taxonomy_version or expected_scheduler_taxonomy_version
        scheduler_current_csv = current_taxonomy_csv or expected_scheduler_taxonomy_csv
        scheduler_summary, scheduler_errors = _scheduler_taxonomy_transition_plan(
            scheduler_config_path=scheduler_config_path,
            current_taxonomy_version=scheduler_current_version,
            current_taxonomy_csv=scheduler_current_csv,
            proposed_taxonomy_version=proposed_taxonomy_version,
            proposed_taxonomy_csv=proposed_taxonomy_csv,
            loaded_current_source_hash=(
                str(loaded_current["source_hash"])
                if loaded_current is not None and loaded_current["source_hash"]
                else None
            ),
            loaded_proposed_source_hash=(
                str(loaded["source_hash"])
                if loaded is not None and loaded["source_hash"]
                else None
            ),
        )
        blocking_errors.extend(scheduler_errors)
        scheduler_status = str(scheduler_summary.get("current_scheduler_taxonomy_status"))
        if current_db_taxonomy_status == "EXPECTED_CURRENT" and scheduler_status == "ALREADY_PROPOSED":
            blocking_errors.append("mixed state blocks activation: DB current taxonomy with scheduler proposed taxonomy")
        if current_db_taxonomy_status == "ALREADY_PROPOSED" and scheduler_status == "EXPECTED_CURRENT_V1":
            blocking_errors.append("mixed state blocks activation: DB proposed taxonomy with scheduler current taxonomy")
    finally:
        conn.close()

    unique_errors = sorted(set(blocking_errors))
    already_active = (
        not unique_errors
        and current_db_taxonomy_status == "ALREADY_PROPOSED"
        and scheduler_summary.get("current_scheduler_taxonomy_status")
        in {"ALREADY_PROPOSED", "NOT_CHECKED"}
    )
    ready = not unique_errors and not already_active
    return {
        "activation_plan_status": (
            "ALREADY_ACTIVE" if already_active else "READY_TO_ACTIVATE" if ready else "BLOCKED"
        ),
        "ecosystem_code": ecosystem_code,
        "deployment_id": deployment_id,
        "current_db_taxonomy_status": current_db_taxonomy_status,
        "current_taxonomy_version": current_taxonomy_version,
        "proposed_taxonomy_version": proposed_taxonomy_version,
        "required_signal_date": required_signal_date,
        "safe_to_activate": ready,
        **scheduler_summary,
        "blocking_errors": unique_errors,
        "warnings": warnings,
    }


def apply_datacenter_taxonomy_activation(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    required_signal_date: str,
    confirm_activate_taxonomy_version: str,
    deployment_id: int | None = None,
    current_taxonomy_version: str | None = None,
    current_taxonomy_csv: str | Path | None = None,
    expected_scheduler_taxonomy_version: str | None = None,
    expected_scheduler_taxonomy_csv: str | Path | None = None,
    scheduler_config_path: str | Path | None = None,
    expected_current_scheduler_taxonomy_version: str | None = None,
    expected_current_scheduler_taxonomy_csv: str | Path | None = None,
    target_scheduler_taxonomy_csv: str | Path | None = None,
    config_backup_dir: str | Path = "temp",
) -> dict[str, object]:
    if confirm_activate_taxonomy_version != proposed_taxonomy_version:
        return {
            "activation_apply_status": "BLOCKED",
            "activation_performed": False,
            "blocking_errors": [
                "confirm_activate_taxonomy_version must match proposed_taxonomy_version"
            ],
        }
    plan = plan_datacenter_taxonomy_activation(
        analysis_db=analysis_db,
        ecosystem_code=ecosystem_code,
        deployment_id=deployment_id,
        current_taxonomy_version=current_taxonomy_version
        or expected_current_scheduler_taxonomy_version,
        current_taxonomy_csv=current_taxonomy_csv or expected_current_scheduler_taxonomy_csv,
        proposed_taxonomy_version=proposed_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        required_signal_date=required_signal_date,
        scheduler_config_path=scheduler_config_path,
        expected_scheduler_taxonomy_version=expected_scheduler_taxonomy_version,
        expected_scheduler_taxonomy_csv=expected_scheduler_taxonomy_csv,
    )
    if plan["activation_plan_status"] == "ALREADY_ACTIVE":
        return {
            "activation_apply_status": "NO_CHANGE",
            "activation_performed": False,
            "activation_db_status": "ALREADY_ACTIVE",
            "activation_config_status": "ALREADY_ACTIVE",
            "activation_consistency_status": "OK",
            "activation_rollback_attempted": False,
            "activation_rollback_status": "NOT_NEEDED",
            "activation_error": None,
            "blocking_errors": [],
            "plan": plan,
        }
    if not plan["safe_to_activate"]:
        return {
            "activation_apply_status": "BLOCKED",
            "activation_performed": False,
            "activation_db_status": "NOT_STARTED",
            "activation_config_status": "NOT_STARTED",
            "activation_consistency_status": "NOT_RUN",
            "activation_rollback_attempted": False,
            "activation_rollback_status": "NOT_NEEDED",
            "activation_error": None,
            "blocking_errors": plan["blocking_errors"],
            "plan": plan,
        }

    config_summary: dict[str, object] = {
        "config_update_requested": scheduler_config_path is not None,
        "config_update_status": "NOT_REQUESTED",
    }
    updated_config = None
    backup_path: Path | None = None
    if scheduler_config_path is not None:
        from rawcandle.scheduler.config import (
            read_scheduler_config,
            validate_scheduler_config,
            write_scheduler_config,
        )

        config_path = Path(scheduler_config_path)
        backup_dir_path = Path(config_backup_dir)
        backup_dir_path.mkdir(parents=True, exist_ok=True)
        current_config = read_scheduler_config(str(config_path))
        target_csv = str(target_scheduler_taxonomy_csv or proposed_taxonomy_csv)
        updated_config = replace(
            current_config,
            datacenter_taxonomy_csv=target_csv,
            datacenter_taxonomy_version=proposed_taxonomy_version,
            ec_source_layer_taxonomy_csv=target_csv,
            ec_source_layer_taxonomy_version=proposed_taxonomy_version,
        )
        validate_scheduler_config(updated_config)
        changed_keys = {
            key
            for key, value in current_config.__dict__.items()
            if getattr(updated_config, key) != value
        }
        expected_changed = {
            "datacenter_taxonomy_csv",
            "datacenter_taxonomy_version",
            "ec_source_layer_taxonomy_csv",
            "ec_source_layer_taxonomy_version",
        }
        unexpected_changed = sorted(changed_keys - expected_changed)
        missing_changed = sorted(expected_changed - changed_keys)
        if unexpected_changed:
            return {
                "activation_apply_status": "BLOCKED",
                "activation_performed": False,
                "activation_db_status": "NOT_STARTED",
                "activation_config_status": "NOT_STARTED",
                "activation_consistency_status": "NOT_RUN",
                "activation_rollback_attempted": False,
                "activation_rollback_status": "NOT_NEEDED",
                "activation_error": None,
                "blocking_errors": ["unexpected scheduler config changed keys: " + ", ".join(unexpected_changed)],
                "plan": plan,
            }
        if missing_changed:
            return {
                "activation_apply_status": "BLOCKED",
                "activation_performed": False,
                "activation_db_status": "NOT_STARTED",
                "activation_config_status": "NOT_STARTED",
                "activation_consistency_status": "NOT_RUN",
                "activation_rollback_attempted": False,
                "activation_rollback_status": "NOT_NEEDED",
                "activation_error": None,
                "blocking_errors": ["scheduler taxonomy transition does not change exactly four taxonomy keys"],
                "plan": plan,
            }
        backup_path = backup_dir_path / (
            f"{config_path.name}.before_taxonomy_activation_{_utc_now().replace(':', '').replace('-', '')}.json"
        )
        shutil.copy2(config_path, backup_path)
        config_summary = {
            "config_update_requested": True,
            "config_update_status": "VALIDATED_PENDING_DB",
            "config_backup_path": str(backup_path),
            "changed_keys": sorted(changed_keys),
            "unexpected_changed_keys": "NONE",
        }

    conn = _connect_readwrite(analysis_db)
    activation_db_status = "NOT_STARTED"
    activation_config_status = config_summary["config_update_status"]
    rollback_attempted = False
    rollback_status = "NOT_NEEDED"
    expected_current_version = current_taxonomy_version or expected_current_scheduler_taxonomy_version
    try:
        try:
            with conn:
                activation_db_status = "IN_PROGRESS"
                loaded = _fetch_loaded_taxonomy(
                    conn,
                    ecosystem_code=ecosystem_code,
                    taxonomy_version_code=proposed_taxonomy_version,
                )
                if loaded is None:
                    raise ValueError("proposed taxonomy metadata disappeared before activation")
                ecosystem_row = conn.execute(
                    "SELECT ecosystem_id FROM ec_ecosystem WHERE ecosystem_code = ?",
                    (ecosystem_code,),
                ).fetchone()
                if ecosystem_row is None:
                    raise ValueError(f"ecosystem not found: {ecosystem_code}")
                ecosystem_id = int(ecosystem_row[0])
                taxonomy_version_id = int(loaded["taxonomy_version_id"])
                conn.execute(
                    """
                    UPDATE ec_taxonomy_version
                    SET status = 'INACTIVE',
                        is_active = 0,
                        active_to = CURRENT_TIMESTAMP
                    WHERE ecosystem_id = ?
                      AND taxonomy_version_id <> ?
                    """,
                    (ecosystem_id, taxonomy_version_id),
                )
                conn.execute(
                    """
                    UPDATE ec_taxonomy_version
                    SET status = 'ACTIVE',
                        is_active = 1,
                        active_from = COALESCE(active_from, CURRENT_TIMESTAMP),
                        active_to = NULL
                    WHERE taxonomy_version_id = ?
                    """,
                    (taxonomy_version_id,),
                )
                conn.execute(
                    """
                    UPDATE ec_taxonomy_change_deployment
                    SET status = 'ACTIVE',
                        activation_status = 'ACTIVE',
                        activated_at_utc = CURRENT_TIMESTAMP,
                        updated_at_utc = CURRENT_TIMESTAMP
                    WHERE ecosystem_code = ?
                      AND proposed_taxonomy_version = ?
                    """,
                    (ecosystem_code, proposed_taxonomy_version),
                )
                activation_db_status = "DB_WRITES_DONE_PENDING_COMMIT"
                if scheduler_config_path is not None and updated_config is not None:
                    try:
                        write_scheduler_config(str(scheduler_config_path), updated_config)
                        from rawcandle.scheduler.config import read_scheduler_config

                        read_scheduler_config(str(scheduler_config_path))
                        config_summary["config_update_status"] = "OK"
                        activation_config_status = "OK"
                    except Exception:
                        rollback_attempted = True
                        if backup_path is not None:
                            shutil.copy2(backup_path, scheduler_config_path)
                            rollback_status = "CONFIG_RESTORED_DB_ROLLED_BACK"
                        else:
                            rollback_status = "DB_ROLLED_BACK"
                        raise
            activation_db_status = "OK"
        except Exception as exc:
            activation_error = str(exc)
            if rollback_status == "NOT_NEEDED":
                rollback_attempted = True
                rollback_status = "DB_ROLLED_BACK"
            return {
                "activation_apply_status": "FAILED",
                "activation_performed": False,
                "activation_db_status": "ROLLED_BACK",
                "activation_config_status": activation_config_status,
                "activation_consistency_status": "NOT_VERIFIED_AFTER_FAILURE",
                "activation_rollback_attempted": rollback_attempted,
                "activation_rollback_status": rollback_status,
                "activation_error": activation_error,
                "config_backup_path": str(backup_path) if backup_path is not None else None,
                "blocking_errors": [activation_error],
                "plan": plan,
                "config_activation": config_summary,
            }

        consistency_plan = plan_datacenter_taxonomy_activation(
            analysis_db=analysis_db,
            ecosystem_code=ecosystem_code,
            deployment_id=deployment_id,
            current_taxonomy_version=expected_current_version,
            current_taxonomy_csv=current_taxonomy_csv
            or expected_current_scheduler_taxonomy_csv,
            proposed_taxonomy_version=proposed_taxonomy_version,
            proposed_taxonomy_csv=proposed_taxonomy_csv,
            required_signal_date=required_signal_date,
            scheduler_config_path=scheduler_config_path,
        )
        if consistency_plan["activation_plan_status"] != "ALREADY_ACTIVE":
            raise RuntimeError("final activation consistency verification failed")

        return {
            "activation_apply_status": "ACTIVE",
            "activation_performed": True,
            "activation_db_status": activation_db_status,
            "activation_config_status": activation_config_status,
            "activation_consistency_status": "OK",
            "activation_rollback_attempted": False,
            "activation_rollback_status": "NOT_NEEDED",
            "activation_error": None,
            "config_backup_path": str(backup_path) if backup_path is not None else None,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_id": taxonomy_version_id,
            "taxonomy_version_code": proposed_taxonomy_version,
            "plan": plan,
            "post_activation_plan": consistency_plan,
            "config_activation": config_summary,
        }
    except Exception as exc:
        if scheduler_config_path is not None and backup_path is not None:
            rollback_attempted = True
            shutil.copy2(backup_path, scheduler_config_path)
            rollback_status = "CONFIG_RESTORED"
        if activation_db_status == "OK" and expected_current_version is not None:
            rollback_attempted = True
            try:
                with conn:
                    ecosystem_row = conn.execute(
                        "SELECT ecosystem_id FROM ec_ecosystem WHERE ecosystem_code = ?",
                        (ecosystem_code,),
                    ).fetchone()
                    if ecosystem_row is None:
                        raise ValueError(f"ecosystem not found: {ecosystem_code}")
                    ecosystem_id = int(ecosystem_row[0])
                    conn.execute(
                        """
                        UPDATE ec_taxonomy_version
                        SET status = 'INACTIVE',
                            is_active = 0,
                            active_to = CURRENT_TIMESTAMP
                        WHERE ecosystem_id = ?
                          AND taxonomy_version_code = ?
                        """,
                        (ecosystem_id, proposed_taxonomy_version),
                    )
                    conn.execute(
                        """
                        UPDATE ec_taxonomy_version
                        SET status = 'ACTIVE',
                            is_active = 1,
                            active_from = COALESCE(active_from, CURRENT_TIMESTAMP),
                            active_to = NULL
                        WHERE ecosystem_id = ?
                          AND taxonomy_version_code = ?
                        """,
                        (ecosystem_id, expected_current_version),
                    )
                    conn.execute(
                        """
                        UPDATE ec_taxonomy_change_deployment
                        SET status = 'READY_TO_ACTIVATE',
                            activation_status = 'NOT_ACTIVE',
                            activated_at_utc = NULL,
                            updated_at_utc = CURRENT_TIMESTAMP
                        WHERE ecosystem_code = ?
                          AND proposed_taxonomy_version = ?
                        """,
                        (ecosystem_code, proposed_taxonomy_version),
                    )
                rollback_status = (
                    "DB_AND_CONFIG_RESTORED"
                    if rollback_status == "CONFIG_RESTORED"
                    else "DB_RESTORED"
                )
                activation_db_status = "ROLLED_BACK"
            except Exception as rollback_exc:
                rollback_status = f"ROLLBACK_FAILED: {rollback_exc}"
        return {
            "activation_apply_status": "FAILED",
            "activation_performed": False,
            "activation_db_status": activation_db_status,
            "activation_config_status": activation_config_status,
            "activation_consistency_status": "FAILED",
            "activation_rollback_attempted": rollback_attempted,
            "activation_rollback_status": rollback_status,
            "activation_error": str(exc),
            "config_backup_path": str(backup_path) if backup_path is not None else None,
            "blocking_errors": [str(exc)],
            "plan": plan,
            "config_activation": config_summary,
        }
    finally:
        conn.close()


def validate_no_stale_taxonomy_rows(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    active_taxonomy_version: str,
) -> dict[str, object]:
    conn = _connect_readonly(analysis_db)
    stale_dc: dict[str, int] = {}
    stale_ec: dict[str, int] = {}
    try:
        for table_name, _date_column in CANONICAL_DC_FACT_TABLES:
            if table_name in _table_names(conn):
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE taxonomy_version <> ?",
                    (active_taxonomy_version,),
                ).fetchone()
                count = int(row[0])
                if count:
                    stale_dc[table_name] = count
        active = _fetch_loaded_taxonomy(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=active_taxonomy_version,
        )
        if active is not None:
            taxonomy_version_id = int(active["taxonomy_version_id"])
            for table_name in CANONICAL_EC_FACT_TABLES:
                if table_name in _table_names(conn):
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM {table_name} WHERE taxonomy_version_id <> ?",
                        (taxonomy_version_id,),
                    ).fetchone()
                    count = int(row[0])
                    if count:
                        stale_ec[table_name] = count
    finally:
        conn.close()
    return {
        "canonical_replacement_validation_status": "OK" if not stale_dc and not stale_ec else "BLOCKED_STALE_ROWS",
        "ecosystem_code": ecosystem_code,
        "active_taxonomy_version": active_taxonomy_version,
        "stale_dc_rows": stale_dc,
        "stale_ec_rows": stale_ec,
    }


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def print_json(summary: dict[str, object]) -> None:
    print(json.dumps(summary, indent=2, sort_keys=True, default=_json_default))


def build_plan_change_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a read-only Datacenter taxonomy replacement")
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--current-taxonomy-version", required=True)
    parser.add_argument("--current-taxonomy-csv", required=True)
    parser.add_argument("--proposed-taxonomy-version", required=True)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--ecosystem", default=DATACENTER_ECOSYSTEM_CODE)
    parser.add_argument("--rebuild-start-date", default=DEFAULT_DATACENTER_REBUILD_START_DATE)
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def build_apply_version_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load immutable Datacenter taxonomy metadata without activation")
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--current-taxonomy-version", required=True)
    parser.add_argument("--current-taxonomy-csv", required=True)
    parser.add_argument("--proposed-taxonomy-version", required=True)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--confirm-proposed-taxonomy-version", required=True)
    parser.add_argument("--ecosystem", default=DATACENTER_ECOSYSTEM_CODE)
    parser.add_argument("--invocation-source", default="CLI")
    parser.add_argument("--rebuild-start-date", default=DEFAULT_DATACENTER_REBUILD_START_DATE)
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def build_activation_plan_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan guarded activation of a rebuilt Datacenter taxonomy")
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ecosystem", default=DATACENTER_ECOSYSTEM_CODE)
    parser.add_argument("--deployment-id", type=int)
    parser.add_argument("--current-taxonomy-version")
    parser.add_argument("--current-taxonomy-csv")
    parser.add_argument("--proposed-taxonomy-version", required=True)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--required-signal-date", required=True)
    parser.add_argument("--scheduler-config")
    parser.add_argument("--expected-scheduler-taxonomy-version")
    parser.add_argument("--expected-scheduler-taxonomy-csv")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def build_apply_activation_parser() -> argparse.ArgumentParser:
    parser = build_activation_plan_parser()
    parser.description = "Guarded Datacenter taxonomy activation boundary"
    parser.add_argument("--confirm-activate-taxonomy-version", required=True)
    parser.add_argument("--expected-current-scheduler-taxonomy-version")
    parser.add_argument("--expected-current-scheduler-taxonomy-csv")
    parser.add_argument("--target-scheduler-taxonomy-csv")
    parser.add_argument("--config-backup-dir", default="temp")
    return parser
