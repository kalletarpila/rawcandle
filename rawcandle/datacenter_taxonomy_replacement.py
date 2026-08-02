from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from analysis.datacenter_indices.taxonomy import (
    DatacenterTaxonomyRow,
    load_datacenter_taxonomy_csv,
)
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


def plan_datacenter_taxonomy_activation(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    required_signal_date: str,
    expected_scheduler_taxonomy_version: str | None = None,
    expected_scheduler_taxonomy_csv: str | Path | None = None,
) -> dict[str, object]:
    blocking_errors: list[str] = []
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
                if str(deployment["dc_rebuild_status"]) != "OK":
                    blocking_errors.append("full DC rebuild is incomplete")
                if str(deployment["ec_rebuild_status"]) != "OK":
                    blocking_errors.append("full EC rebuild is incomplete")
                if str(deployment["coverage_status"]) != "OK":
                    blocking_errors.append("coverage is not accepted")
                if str(deployment["parity_status"]) != "OK":
                    blocking_errors.append("parity is not accepted")
                if str(deployment["activation_status"]) == "ACTIVE":
                    blocking_errors.append("taxonomy is already active")

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
                mismatched = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM ec_pipeline_watermark w
                    JOIN ec_ecosystem e ON e.ecosystem_id = w.ecosystem_id
                    WHERE e.ecosystem_code = ?
                      AND w.taxonomy_version_id IS NOT ?
                    """,
                    (ecosystem_code, taxonomy_version_id),
                ).fetchone()[0]
                if int(mismatched) > 0:
                    blocking_errors.append("EC watermark lineage does not belong to proposed taxonomy")
            else:
                blocking_errors.append("EC watermark taxonomy lineage field is missing")

        if expected_scheduler_taxonomy_version and expected_scheduler_taxonomy_version != proposed_taxonomy_version:
            blocking_errors.append("configured scheduler taxonomy version does not match proposed taxonomy")
        if expected_scheduler_taxonomy_csv and proposed_summary is not None:
            if _sha256(expected_scheduler_taxonomy_csv) != proposed_summary.source_sha256:
                blocking_errors.append("configured scheduler taxonomy CSV does not match proposed taxonomy")
    finally:
        conn.close()

    ready = not blocking_errors
    return {
        "activation_plan_status": "READY_TO_ACTIVATE" if ready else "BLOCKED",
        "ecosystem_code": ecosystem_code,
        "proposed_taxonomy_version": proposed_taxonomy_version,
        "required_signal_date": required_signal_date,
        "safe_to_activate": ready,
        "blocking_errors": sorted(set(blocking_errors)),
    }


def apply_datacenter_taxonomy_activation(
    *,
    analysis_db: str | Path,
    ecosystem_code: str,
    proposed_taxonomy_version: str,
    proposed_taxonomy_csv: str | Path,
    required_signal_date: str,
    confirm_activate_taxonomy_version: str,
    expected_scheduler_taxonomy_version: str | None = None,
    expected_scheduler_taxonomy_csv: str | Path | None = None,
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
        proposed_taxonomy_version=proposed_taxonomy_version,
        proposed_taxonomy_csv=proposed_taxonomy_csv,
        required_signal_date=required_signal_date,
        expected_scheduler_taxonomy_version=expected_scheduler_taxonomy_version,
        expected_scheduler_taxonomy_csv=expected_scheduler_taxonomy_csv,
    )
    if not plan["safe_to_activate"]:
        return {
            "activation_apply_status": "BLOCKED",
            "activation_performed": False,
            "blocking_errors": plan["blocking_errors"],
            "plan": plan,
        }

    conn = _connect_readwrite(analysis_db)
    try:
        with conn:
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

        return {
            "activation_apply_status": "ACTIVE",
            "activation_performed": True,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_id": taxonomy_version_id,
            "taxonomy_version_code": proposed_taxonomy_version,
            "plan": plan,
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
    parser.add_argument("--proposed-taxonomy-version", required=True)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--required-signal-date", required=True)
    parser.add_argument("--expected-scheduler-taxonomy-version")
    parser.add_argument("--expected-scheduler-taxonomy-csv")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def build_apply_activation_parser() -> argparse.ArgumentParser:
    parser = build_activation_plan_parser()
    parser.description = "Guarded Datacenter taxonomy activation boundary"
    parser.add_argument("--confirm-activate-taxonomy-version", required=True)
    return parser
