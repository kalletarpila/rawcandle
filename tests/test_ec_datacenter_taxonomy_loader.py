import csv
import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_datacenter_taxonomy_loader import (
    _build_taxonomy_name,
    _normalize_group_entity_code,
    load_datacenter_taxonomy_to_ec_sidecar,
)
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_csv(path: Path, rows: list[list[object]], header: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            header
            or [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        writer.writerows(rows)


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def test_loader_persists_expected_ec_sidecar_rows_and_summary(tmp_path) -> None:
    db_path = tmp_path / "ec_loader.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""],
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "Accelerators", "EXTENDED", 0, 0.4, "adjacent"],
            ["DC_TAXONOMY_FULL_V1", "AMD", "Compute silicon", "GPUs", "WATCH_ONLY", 1, 0.7, ""],
        ],
    )

    summary = load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(db_path),
        taxonomy_csv_path=str(csv_path),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )

    conn = _connect(str(db_path))
    try:
        assert conn.execute(
            """
            SELECT ecosystem_code, ecosystem_name, status
            FROM ec_ecosystem
            """
        ).fetchone() == ("DATACENTER", "Datacenter", "ACTIVE")
        assert conn.execute(
            """
            SELECT taxonomy_version_code, taxonomy_name, source_type, source_reference, status, is_active
            FROM ec_taxonomy_version
            """
        ).fetchone() == (
            "DC_TAXONOMY_FULL_V1",
            "Datacenter taxonomy full v1",
            "CSV",
            str(csv_path),
            "ACTIVE",
            1,
        )

        entity_counts = dict(
            conn.execute(
                """
                SELECT entity_type, COUNT(*)
                FROM ec_entity
                GROUP BY entity_type
                """
            ).fetchall()
        )
        assert entity_counts == {
            "ECOSYSTEM": 1,
            "GROUP_L1": 1,
            "GROUP_L2": 2,
            "TICKER": 2,
        }

        alias_row = conn.execute(
            """
            SELECT alias_type, alias_value, source_system
            FROM ec_entity_alias
            """
        ).fetchone()
        assert alias_row == ("DC_GROUP_NAME", "DC_ECOSYSTEM_TOTAL", "dc_group_facts")

        membership_rows = conn.execute(
            """
            SELECT parent.entity_type, parent.entity_name, child.entity_type, child.entity_name,
                   m.membership_role, m.is_primary, m.role_weight, m.source_note
            FROM ec_membership m
            JOIN ec_entity parent ON parent.entity_id = m.parent_entity_id
            JOIN ec_entity child ON child.entity_id = m.child_entity_id
            ORDER BY parent.entity_type, parent.entity_name, child.entity_type, child.entity_name
            """
        ).fetchall()
        assert ("ECOSYSTEM", "Datacenter", "GROUP_L1", "Compute silicon", None, 1, 1.0, None) in membership_rows
        assert ("GROUP_L1", "Compute silicon", "GROUP_L2", "Accelerators", None, 1, 1.0, None) in membership_rows
        assert ("GROUP_L1", "Compute silicon", "GROUP_L2", "GPUs", None, 1, 1.0, None) in membership_rows
        assert ("GROUP_L2", "Accelerators", "TICKER", "NVDA", "EXTENDED", 0, 0.4, "adjacent") in membership_rows
        assert ("GROUP_L2", "GPUs", "TICKER", "AMD", "WATCH_ONLY", 1, 0.7, None) in membership_rows
        assert ("GROUP_L2", "GPUs", "TICKER", "NVDA", "CORE", 1, 1.0, None) in membership_rows

        assert summary == {
            "status": "OK",
            "ecosystem_code": "DATACENTER",
            "taxonomy_version_code": "DC_TAXONOMY_FULL_V1",
            "taxonomy_rows": 3,
            "layer_count": 1,
            "subindustry_count": 2,
            "ticker_count": 2,
            "membership_count": 6,
            "primary_membership_count": 2,
            "multi_membership_ticker_count": 1,
            "alias_count": 1,
            "warnings": [],
        }
    finally:
        conn.close()


def test_loader_creates_one_ticker_entity_and_multiple_memberships_for_multi_membership_ticker(tmp_path) -> None:
    db_path = tmp_path / "ec_loader_multi.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""],
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Networking", "AI Fabric", "EXTENDED", 0, 0.5, ""],
        ],
    )

    summary = load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(db_path),
        taxonomy_csv_path=str(csv_path),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )

    conn = _connect(str(db_path))
    try:
        ticker_entity_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ec_entity
            WHERE entity_type = 'TICKER' AND entity_code = 'NVDA'
            """
        ).fetchone()[0]
        ticker_membership_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ec_membership m
            JOIN ec_entity child ON child.entity_id = m.child_entity_id
            WHERE child.entity_type = 'TICKER' AND child.entity_code = 'NVDA'
            """
        ).fetchone()[0]
        primary_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ec_membership m
            JOIN ec_entity child ON child.entity_id = m.child_entity_id
            WHERE child.entity_type = 'TICKER' AND child.entity_code = 'NVDA' AND m.is_primary = 1
            """
        ).fetchone()[0]
        assert ticker_entity_count == 1
        assert ticker_membership_count == 2
        assert primary_count == 1
        assert summary["multi_membership_ticker_count"] == 1
    finally:
        conn.close()


def test_loader_rejects_duplicate_load_without_replace_existing(tmp_path) -> None:
    db_path = tmp_path / "ec_loader_duplicate.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""],
        ],
    )

    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(db_path),
        taxonomy_csv_path=str(csv_path),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )

    with pytest.raises(ValueError, match="Target taxonomy version already exists"):
        load_datacenter_taxonomy_to_ec_sidecar(
            db_path=str(db_path),
            taxonomy_csv_path=str(csv_path),
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            replace_existing=False,
        )


def test_loader_rejects_replace_existing_true_for_now(tmp_path) -> None:
    db_path = tmp_path / "ec_loader_replace.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""],
        ],
    )

    with pytest.raises(NotImplementedError, match="replace_existing=True is not implemented"):
        load_datacenter_taxonomy_to_ec_sidecar(
            db_path=str(db_path),
            taxonomy_csv_path=str(csv_path),
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            replace_existing=True,
        )


def test_loader_missing_required_column_fails_and_rolls_back(tmp_path) -> None:
    db_path = tmp_path / "ec_loader_missing_column.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0]],
        header=[
            "taxonomy_version",
            "ticker",
            "layer",
            "subindustry",
            "report_group_status",
            "is_primary",
            "role_weight",
        ],
    )

    with pytest.raises(ValueError, match="Invalid taxonomy CSV columns"):
        load_datacenter_taxonomy_to_ec_sidecar(
            db_path=str(db_path),
            taxonomy_csv_path=str(csv_path),
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        )

    conn = _connect(str(db_path))
    try:
        assert _table_count(conn, "ec_ecosystem") == 0
        assert _table_count(conn, "ec_taxonomy_version") == 0
        assert _table_count(conn, "ec_entity") == 0
        assert _table_count(conn, "ec_entity_alias") == 0
        assert _table_count(conn, "ec_membership") == 0
    finally:
        conn.close()


def test_loader_missing_ticker_layer_or_subindustry_fails_and_rolls_back(tmp_path) -> None:
    db_path = tmp_path / "ec_loader_missing_value.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [
            ["DC_TAXONOMY_FULL_V1", "", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""],
        ],
    )

    with pytest.raises(ValueError, match="ticker must not be empty"):
        load_datacenter_taxonomy_to_ec_sidecar(
            db_path=str(db_path),
            taxonomy_csv_path=str(csv_path),
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        )

    conn = _connect(str(db_path))
    try:
        assert _table_count(conn, "ec_ecosystem") == 0
        assert _table_count(conn, "ec_taxonomy_version") == 0
        assert _table_count(conn, "ec_entity") == 0
        assert _table_count(conn, "ec_entity_alias") == 0
        assert _table_count(conn, "ec_membership") == 0
    finally:
        conn.close()


def test_loader_requires_matching_taxonomy_version_code(tmp_path) -> None:
    db_path = tmp_path / "ec_loader_mismatch.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [
            ["DC_TAXONOMY_FULL_V2", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""],
        ],
    )

    with pytest.raises(ValueError, match="do not match requested taxonomy_version_code"):
        load_datacenter_taxonomy_to_ec_sidecar(
            db_path=str(db_path),
            taxonomy_csv_path=str(csv_path),
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        )


def test_loader_requires_exactly_one_primary_membership_per_ticker(tmp_path) -> None:
    db_path = tmp_path / "ec_loader_primary.db"
    csv_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_csv(
        csv_path,
        [
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 0, 1.0, ""],
            ["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "Accelerators", "EXTENDED", 0, 0.4, ""],
        ],
    )

    with pytest.raises(ValueError, match="exactly one primary taxonomy membership"):
        load_datacenter_taxonomy_to_ec_sidecar(
            db_path=str(db_path),
            taxonomy_csv_path=str(csv_path),
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        )


def test_loader_helpers_are_deterministic() -> None:
    assert _normalize_group_entity_code("  AI cloud / neocloud infrastructure ") == "AI_CLOUD_NEOCLOUD_INFRASTRUCTURE"
    assert _normalize_group_entity_code("Glass / optical materials / specialty glass") == "GLASS_OPTICAL_MATERIALS_SPECIALTY_GLASS"
    assert _build_taxonomy_name("DC_TAXONOMY_FULL_V1") == "Datacenter taxonomy full v1"
