from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from analysis.datacenter_indices.taxonomy import load_datacenter_taxonomy_csv

from .report_canonical_v3_migration import apply_report_canonical_v3_migration


_STATUS_TO_MEMBERSHIP_ROLE = {
    "CORE": "CORE",
    "EXTENDED": "ADJACENT",
    "WATCH_ONLY": "WATCH_ONLY",
    "TOO_SMALL": "OPTIONAL",
}


def _normalize_entity_code(name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", name.strip().upper()).strip("_")
    if not normalized:
        raise ValueError("Entity code normalization produced an empty code")
    return normalized


def _get_required_source_path(taxonomy_source_path: str | None) -> str:
    if taxonomy_source_path is None:
        raise ValueError(
            "taxonomy_source_path is required because no clear project default taxonomy CSV path is defined"
        )
    return taxonomy_source_path


def _fetch_id(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> int | None:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return int(row[0])


def _ensure_ecosystem(conn: sqlite3.Connection) -> tuple[int, int]:
    existing_id = _fetch_id(
        conn,
        "SELECT ecosystem_id FROM eco_ecosystem WHERE ecosystem_code = ?",
        ("DATACENTER",),
    )
    if existing_id is not None:
        return existing_id, 1
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code,
            ecosystem_name,
            description,
            status
        ) VALUES (?, ?, ?, ?)
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    return int(cursor.lastrowid), 1


def _ensure_taxonomy_version(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    version_code: str,
) -> tuple[int, int]:
    existing_id = _fetch_id(
        conn,
        """
        SELECT taxonomy_version_id
        FROM eco_taxonomy_version
        WHERE ecosystem_id = ? AND version_code = ?
        """,
        (ecosystem_id, version_code),
    )
    if existing_id is not None:
        return existing_id, 1
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id,
            version_code,
            version_label,
            source_type,
            source_reference,
            effective_from,
            effective_to,
            is_active,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            version_code,
            version_code,
            "CSV",
            None,
            None,
            None,
            1,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid), 1


def _ensure_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
    entity_name: str,
    ticker: str | None = None,
) -> tuple[int, int]:
    existing_id = _fetch_id(
        conn,
        """
        SELECT entity_id
        FROM eco_entity
        WHERE ecosystem_id = ? AND entity_type = ? AND entity_code = ?
        """,
        (ecosystem_id, entity_type, entity_code),
    )
    if existing_id is not None:
        return existing_id, 0
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            exchange,
            market,
            currency,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            None,
            None,
            None,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid), 1


def _ensure_relation(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
    ecosystem_id: int,
    parent_entity_id: int,
    child_entity_id: int,
    membership_role: str,
    is_primary: int,
    weight: float | None,
) -> int:
    existing_id = _fetch_id(
        conn,
        """
        SELECT relation_id
        FROM eco_taxonomy_entity_relation
        WHERE taxonomy_version_id = ?
          AND parent_entity_id = ?
          AND child_entity_id = ?
          AND relation_type = ?
        """,
        (taxonomy_version_id, parent_entity_id, child_entity_id, "CONTAINS"),
    )
    if existing_id is not None:
        return 0
    conn.execute(
        """
        INSERT INTO eco_taxonomy_entity_relation (
            taxonomy_version_id,
            ecosystem_id,
            parent_entity_id,
            child_entity_id,
            relation_type,
            membership_role,
            weight,
            is_primary,
            sort_order,
            effective_from,
            effective_to,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            taxonomy_version_id,
            ecosystem_id,
            parent_entity_id,
            child_entity_id,
            "CONTAINS",
            membership_role,
            weight,
            is_primary,
            None,
            None,
            None,
            "ACTIVE",
        ),
    )
    return 1


def import_datacenter_taxonomy_to_v3(
    db_path: str,
    taxonomy_source_path: str | None = None,
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    dry_run: bool = False,
) -> dict:
    source_path = _get_required_source_path(taxonomy_source_path)
    source_rows = load_datacenter_taxonomy_csv(source_path)
    source_versions = sorted({row.taxonomy_version for row in source_rows})
    if not source_versions:
        raise ValueError("Taxonomy source did not contain any rows")
    if len(source_versions) > 1:
        raise ValueError(
            f"Taxonomy source must contain exactly one taxonomy_version, got {source_versions}"
        )
    effective_taxonomy_version_code = source_versions[0] or taxonomy_version_code

    if not dry_run:
        apply_report_canonical_v3_migration(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    warnings: list[str] = []
    summary = {
        "ecosystems_inserted_or_existing": 0,
        "taxonomy_versions_inserted_or_existing": 0,
        "ecosystem_entities_inserted_or_existing": 0,
        "layer_entities_inserted_or_existing": 0,
        "subindustry_entities_inserted_or_existing": 0,
        "ticker_entities_inserted_or_existing": 0,
        "relations_inserted_or_existing": 0,
        "source_rows_read": len(source_rows),
        "warnings": warnings,
    }

    try:
        ecosystem_id, ecosystem_count = _ensure_ecosystem(conn)
        summary["ecosystems_inserted_or_existing"] = ecosystem_count

        taxonomy_version_id, taxonomy_count = _ensure_taxonomy_version(
            conn,
            ecosystem_id=ecosystem_id,
            version_code=effective_taxonomy_version_code,
        )
        summary["taxonomy_versions_inserted_or_existing"] = taxonomy_count

        ecosystem_entity_id, ecosystem_entity_inserted = _ensure_entity(
            conn,
            ecosystem_id=ecosystem_id,
            entity_type="ECOSYSTEM",
            entity_code="DATACENTER",
            entity_name="Datacenter",
        )
        summary["ecosystem_entities_inserted_or_existing"] = ecosystem_entity_inserted or 1

        layer_ids: dict[str, int] = {}
        subindustry_ids: dict[str, int] = {}
        ticker_ids: dict[str, int] = {}

        for row in source_rows:
            layer_code = _normalize_entity_code(row.layer)
            if layer_code not in layer_ids:
                layer_id, inserted = _ensure_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    entity_type="LAYER",
                    entity_code=layer_code,
                    entity_name=row.layer,
                )
                layer_ids[layer_code] = layer_id
                summary["layer_entities_inserted_or_existing"] += inserted or 1

                summary["relations_inserted_or_existing"] += _ensure_relation(
                    conn,
                    taxonomy_version_id=taxonomy_version_id,
                    ecosystem_id=ecosystem_id,
                    parent_entity_id=ecosystem_entity_id,
                    child_entity_id=layer_id,
                    membership_role="CORE",
                    is_primary=0,
                    weight=None,
                ) or 1

            subindustry_code = _normalize_entity_code(row.subindustry)
            if subindustry_code not in subindustry_ids:
                subindustry_id, inserted = _ensure_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    entity_type="SUBINDUSTRY",
                    entity_code=subindustry_code,
                    entity_name=row.subindustry,
                )
                subindustry_ids[subindustry_code] = subindustry_id
                summary["subindustry_entities_inserted_or_existing"] += inserted or 1

                summary["relations_inserted_or_existing"] += _ensure_relation(
                    conn,
                    taxonomy_version_id=taxonomy_version_id,
                    ecosystem_id=ecosystem_id,
                    parent_entity_id=layer_ids[layer_code],
                    child_entity_id=subindustry_id,
                    membership_role="CORE",
                    is_primary=0,
                    weight=None,
                ) or 1

            ticker_code = row.ticker
            if ticker_code not in ticker_ids:
                ticker_id, inserted = _ensure_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    entity_type="TICKER",
                    entity_code=ticker_code,
                    entity_name=row.ticker,
                    ticker=row.ticker,
                )
                ticker_ids[ticker_code] = ticker_id
                summary["ticker_entities_inserted_or_existing"] += inserted or 1

            membership_role = _STATUS_TO_MEMBERSHIP_ROLE[row.report_group_status]
            summary["relations_inserted_or_existing"] += _ensure_relation(
                conn,
                taxonomy_version_id=taxonomy_version_id,
                ecosystem_id=ecosystem_id,
                parent_entity_id=subindustry_ids[subindustry_code],
                child_entity_id=ticker_ids[ticker_code],
                membership_role=membership_role,
                is_primary=row.is_primary,
                weight=row.role_weight,
            ) or 1

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return summary
    finally:
        conn.close()
