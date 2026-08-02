from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from analysis.datacenter_indices.taxonomy import (
    DATACENTER_TAXONOMY_REQUIRED_COLUMNS,
    DatacenterTaxonomyRow,
    load_datacenter_taxonomy_csv,
)


REQUIRED_EC_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_entity_alias",
    "ec_membership",
)


def _normalize_group_entity_code(name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", name.strip().upper())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError("Group entity code normalization produced an empty code")
    return normalized


def _normalize_ticker_code(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("Ticker entity code normalization produced an empty code")
    return normalized


def _validate_target_taxonomy_version_code(taxonomy_version_code: str) -> str:
    normalized = taxonomy_version_code.strip()
    if not normalized:
        raise ValueError("taxonomy_version_code must not be empty")
    return normalized


def _require_ec_sidecar_tables(conn: sqlite3.Connection) -> None:
    existing = {
        str(row[0])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name GLOB 'ec_*'
            """
        ).fetchall()
    }
    missing = [table_name for table_name in REQUIRED_EC_TABLES if table_name not in existing]
    if missing:
        raise ValueError(f"Missing required ec_ sidecar tables: {missing}")


def _read_source_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _compute_source_hash(path: Path) -> str:
    return hashlib.sha256(_read_source_bytes(path)).hexdigest()


def _build_taxonomy_name(taxonomy_version_code: str) -> str:
    remainder = taxonomy_version_code
    if remainder.startswith("DC_"):
        remainder = remainder[3:]
    if remainder.startswith("TAXONOMY_"):
        remainder = remainder[len("TAXONOMY_") :]
    return f"Datacenter taxonomy {remainder.lower().replace('_', ' ')}"


def _fetch_existing_id(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> int | None:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return int(row[0])


def _ensure_ecosystem_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    ecosystem_name: str,
    warnings: list[str],
) -> int:
    row = conn.execute(
        """
        SELECT ecosystem_id, ecosystem_name
        FROM ec_ecosystem
        WHERE ecosystem_code = ?
        """,
        (ecosystem_code,),
    ).fetchone()
    if row is not None:
        ecosystem_id = int(row[0])
        existing_name = str(row[1])
        if existing_name != ecosystem_name:
            warnings.append(
                "existing ecosystem_name differs from requested name: "
                f"{existing_name!r} vs {ecosystem_name!r}"
            )
        return ecosystem_id

    cursor = conn.execute(
        """
        INSERT INTO ec_ecosystem (
            ecosystem_code,
            ecosystem_name,
            status
        ) VALUES (?, ?, ?)
        """,
        (ecosystem_code, ecosystem_name, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _ensure_taxonomy_version_absent(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_code: str,
) -> None:
    existing_id = _fetch_existing_id(
        conn,
        """
        SELECT taxonomy_version_id
        FROM ec_taxonomy_version
        WHERE ecosystem_id = ? AND taxonomy_version_code = ?
        """,
        (ecosystem_id, taxonomy_version_code),
    )
    if existing_id is not None:
        raise ValueError(
            "Target taxonomy version already exists for ecosystem "
            f"{ecosystem_id} and taxonomy_version_code {taxonomy_version_code!r}"
        )


def _insert_taxonomy_version(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_code: str,
    taxonomy_name: str,
    source_reference: str,
    source_hash: str,
    mark_active: bool = True,
) -> int:
    status = "ACTIVE" if mark_active else "INACTIVE"
    is_active = 1 if mark_active else 0
    cursor = conn.execute(
        """
        INSERT INTO ec_taxonomy_version (
            ecosystem_id,
            taxonomy_version_code,
            taxonomy_name,
            source_type,
            source_reference,
            source_hash,
            status,
            is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            taxonomy_version_code,
            taxonomy_name,
            "CSV",
            source_reference,
            source_hash,
            status,
            is_active,
        ),
    )
    return int(cursor.lastrowid)


def _ensure_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
    entity_name: str | None,
    ticker: str | None = None,
) -> int:
    existing_id = _fetch_existing_id(
        conn,
        """
        SELECT entity_id
        FROM ec_entity
        WHERE ecosystem_id = ? AND entity_type = ? AND entity_code = ?
        """,
        (ecosystem_id, entity_type, entity_code),
    )
    if existing_id is not None:
        return existing_id

    cursor = conn.execute(
        """
        INSERT INTO ec_entity (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, entity_type, entity_code, entity_name, ticker, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _ensure_alias(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_id: int,
    alias_type: str,
    alias_value: str,
    source_system: str | None,
) -> int:
    existing_id = _fetch_existing_id(
        conn,
        """
        SELECT entity_alias_id
        FROM ec_entity_alias
        WHERE ecosystem_id = ?
          AND alias_type = ?
          AND alias_value = ?
          AND source_system IS ?
        """,
        (ecosystem_id, alias_type, alias_value, source_system),
    )
    if existing_id is not None:
        return 0

    conn.execute(
        """
        INSERT INTO ec_entity_alias (
            ecosystem_id,
            entity_id,
            alias_type,
            alias_value,
            source_system,
            status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, entity_id, alias_type, alias_value, source_system, "ACTIVE"),
    )
    return 1


def _insert_membership(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    parent_entity_id: int,
    child_entity_id: int,
    membership_role: str | None,
    is_primary: int,
    role_weight: float | None,
    source_note: str | None,
) -> int:
    conn.execute(
        """
        INSERT INTO ec_membership (
            ecosystem_id,
            taxonomy_version_id,
            parent_entity_id,
            child_entity_id,
            membership_type,
            membership_role,
            is_primary,
            role_weight,
            status,
            source_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            taxonomy_version_id,
            parent_entity_id,
            child_entity_id,
            "CONTAINS",
            membership_role,
            is_primary,
            role_weight,
            "ACTIVE",
            source_note,
        ),
    )
    return 1


def _validate_source_versions(
    rows: list[DatacenterTaxonomyRow],
    taxonomy_version_code: str,
) -> None:
    source_versions = sorted({row.taxonomy_version for row in rows})
    if source_versions != [taxonomy_version_code]:
        raise ValueError(
            "Taxonomy source taxonomy_version values do not match requested "
            f"taxonomy_version_code: source={source_versions}, requested={taxonomy_version_code!r}"
        )


def _validate_primary_memberships(rows: list[DatacenterTaxonomyRow]) -> tuple[int, int]:
    primary_counts: dict[str, int] = {}
    membership_counts: dict[str, int] = {}
    for row in rows:
        membership_counts[row.ticker] = membership_counts.get(row.ticker, 0) + 1
        primary_counts[row.ticker] = primary_counts.get(row.ticker, 0) + row.is_primary

    invalid = sorted(ticker for ticker, count in primary_counts.items() if count != 1)
    if invalid:
        raise ValueError(
            "Each ticker must have exactly one primary taxonomy membership; "
            f"invalid tickers: {invalid}"
        )

    primary_membership_count = sum(primary_counts.values())
    multi_membership_ticker_count = sum(1 for count in membership_counts.values() if count > 1)
    return primary_membership_count, multi_membership_ticker_count


def _load_source_rows(
    taxonomy_csv_path: Path,
    taxonomy_version_code: str,
) -> list[DatacenterTaxonomyRow]:
    rows = load_datacenter_taxonomy_csv(taxonomy_csv_path)
    _validate_source_versions(rows, taxonomy_version_code)
    return rows


def load_datacenter_taxonomy_to_ec_sidecar(
    db_path: str | Path,
    taxonomy_csv_path: str | Path,
    taxonomy_version_code: str,
    ecosystem_code: str = "DATACENTER",
    ecosystem_name: str = "Datacenter",
    replace_existing: bool = False,
    mark_active: bool = True,
) -> dict[str, object]:
    normalized_taxonomy_version_code = _validate_target_taxonomy_version_code(taxonomy_version_code)
    if replace_existing:
        raise NotImplementedError(
            "replace_existing=True is not implemented for EC-LOAD-01; "
            "use replace_existing=False"
        )

    csv_path = Path(taxonomy_csv_path)
    source_rows = _load_source_rows(csv_path, normalized_taxonomy_version_code)
    primary_membership_count, multi_membership_ticker_count = _validate_primary_memberships(source_rows)

    layer_names = sorted({row.layer for row in source_rows})
    subindustry_names = sorted({row.subindustry for row in source_rows})
    ticker_codes = sorted({row.ticker for row in source_rows})
    source_hash = _compute_source_hash(csv_path)
    warnings: list[str] = []

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _require_ec_sidecar_tables(conn)
        with conn:
            ecosystem_id = _ensure_ecosystem_row(
                conn,
                ecosystem_code=ecosystem_code,
                ecosystem_name=ecosystem_name,
                warnings=warnings,
            )
            _ensure_taxonomy_version_absent(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_code=normalized_taxonomy_version_code,
            )
            taxonomy_version_id = _insert_taxonomy_version(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_code=normalized_taxonomy_version_code,
                taxonomy_name=_build_taxonomy_name(normalized_taxonomy_version_code),
                source_reference=str(csv_path),
                source_hash=source_hash,
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

            layer_entity_ids: dict[str, int] = {}
            for layer_name in layer_names:
                layer_entity_ids[layer_name] = _ensure_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    entity_type="GROUP_L1",
                    entity_code=_normalize_group_entity_code(layer_name),
                    entity_name=layer_name,
                )

            subindustry_entity_ids: dict[str, int] = {}
            for subindustry_name in subindustry_names:
                subindustry_entity_ids[subindustry_name] = _ensure_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    entity_type="GROUP_L2",
                    entity_code=_normalize_group_entity_code(subindustry_name),
                    entity_name=subindustry_name,
                )

            ticker_entity_ids: dict[str, int] = {}
            for ticker_code in ticker_codes:
                ticker_entity_ids[ticker_code] = _ensure_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    entity_type="TICKER",
                    entity_code=_normalize_ticker_code(ticker_code),
                    entity_name=ticker_code,
                    ticker=ticker_code,
                )

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

        summary = {
            "status": "OK",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": normalized_taxonomy_version_code,
            "taxonomy_rows": len(source_rows),
            "layer_count": len(layer_names),
            "subindustry_count": len(subindustry_names),
            "ticker_count": len(ticker_codes),
            "membership_count": membership_count,
            "primary_membership_count": primary_membership_count,
            "multi_membership_ticker_count": multi_membership_ticker_count,
            "alias_count": alias_count,
            "warnings": warnings,
            "activation_status": "ACTIVE" if mark_active else "NOT_ACTIVE",
        }
        return summary
    finally:
        conn.close()
