import csv
import sqlite3

import pytest

from rawcandle.report_canonical_v3_taxonomy_import import (
    _normalize_entity_code,
    import_datacenter_taxonomy_to_v3,
)


def _write_taxonomy_fixture(csv_path) -> None:
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
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
        writer.writerow(["DC_TAXONOMY_FULL_V2", "NVDA", "AI Inference", "GPU Compute", "CORE", 1, 1.0, ""])
        writer.writerow(["DC_TAXONOMY_FULL_V2", "NVDA", "AI Inference", "Memory Fabric", "EXTENDED", 0, 0.4, ""])
        writer.writerow(["DC_TAXONOMY_FULL_V2", "AMD", "AI Inference", "GPU Compute", "WATCH_ONLY", 0, 0.7, ""])


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_import_datacenter_taxonomy_to_v3_persists_entities_and_relations(tmp_path) -> None:
    db_path = tmp_path / "taxonomy_v3.db"
    csv_path = tmp_path / "taxonomy.csv"
    _write_taxonomy_fixture(csv_path)

    summary = import_datacenter_taxonomy_to_v3(
        db_path=str(db_path),
        taxonomy_source_path=str(csv_path),
    )

    conn = _connect(str(db_path))
    try:
        ecosystem_row = conn.execute(
            """
            SELECT ecosystem_code, ecosystem_name, status
            FROM eco_ecosystem
            """
        ).fetchone()
        assert ecosystem_row == ("DATACENTER", "Datacenter", "ACTIVE")

        taxonomy_row = conn.execute(
            """
            SELECT version_code, is_active, status
            FROM eco_taxonomy_version
            """
        ).fetchone()
        assert taxonomy_row == ("DC_TAXONOMY_FULL_V2", 1, "ACTIVE")

        entity_counts = dict(
            conn.execute(
                """
                SELECT entity_type, COUNT(*)
                FROM eco_entity
                GROUP BY entity_type
                """
            ).fetchall()
        )
        assert entity_counts == {
            "ECOSYSTEM": 1,
            "LAYER": 1,
            "SUBINDUSTRY": 2,
            "TICKER": 2,
        }

        relation_rows = conn.execute(
            """
            SELECT p.entity_type, p.entity_code, c.entity_type, c.entity_code, r.membership_role, r.is_primary
            FROM eco_taxonomy_entity_relation r
            JOIN eco_entity p ON p.entity_id = r.parent_entity_id
            JOIN eco_entity c ON c.entity_id = r.child_entity_id
            ORDER BY p.entity_type, p.entity_code, c.entity_type, c.entity_code
            """
        ).fetchall()
        assert ("ECOSYSTEM", "DATACENTER", "LAYER", "AI_INFERENCE", "CORE", 0) in relation_rows
        assert ("LAYER", "AI_INFERENCE", "SUBINDUSTRY", "GPU_COMPUTE", "CORE", 0) in relation_rows
        assert ("LAYER", "AI_INFERENCE", "SUBINDUSTRY", "MEMORY_FABRIC", "CORE", 0) in relation_rows
        assert ("SUBINDUSTRY", "GPU_COMPUTE", "TICKER", "AMD", "WATCH_ONLY", 0) in relation_rows
        assert ("SUBINDUSTRY", "GPU_COMPUTE", "TICKER", "NVDA", "CORE", 1) in relation_rows
        assert ("SUBINDUSTRY", "MEMORY_FABRIC", "TICKER", "NVDA", "ADJACENT", 0) in relation_rows

        nvda_subindustry_relations = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_taxonomy_entity_relation r
            JOIN eco_entity child ON child.entity_id = r.child_entity_id
            JOIN eco_entity parent ON parent.entity_id = r.parent_entity_id
            WHERE child.entity_type = 'TICKER'
              AND child.entity_code = 'NVDA'
              AND parent.entity_type = 'SUBINDUSTRY'
            """
        ).fetchone()[0]
        assert nvda_subindustry_relations == 2

        assert summary["ecosystems_inserted_or_existing"] == 1
        assert summary["taxonomy_versions_inserted_or_existing"] == 1
        assert summary["ecosystem_entities_inserted_or_existing"] == 1
        assert summary["layer_entities_inserted_or_existing"] == 1
        assert summary["subindustry_entities_inserted_or_existing"] == 2
        assert summary["ticker_entities_inserted_or_existing"] == 2
        assert summary["relations_inserted_or_existing"] == 6
        assert summary["source_rows_read"] == 3
        assert summary["warnings"] == []
    finally:
        conn.close()


def test_import_is_idempotent_and_entity_code_normalization_is_deterministic(tmp_path) -> None:
    db_path = tmp_path / "taxonomy_v3_idempotent.db"
    csv_path = tmp_path / "taxonomy.csv"
    _write_taxonomy_fixture(csv_path)

    first_summary = import_datacenter_taxonomy_to_v3(
        db_path=str(db_path),
        taxonomy_source_path=str(csv_path),
    )
    second_summary = import_datacenter_taxonomy_to_v3(
        db_path=str(db_path),
        taxonomy_source_path=str(csv_path),
    )

    conn = _connect(str(db_path))
    try:
        entity_count = conn.execute("SELECT COUNT(*) FROM eco_entity").fetchone()[0]
        relation_count = conn.execute("SELECT COUNT(*) FROM eco_taxonomy_entity_relation").fetchone()[0]
        assert entity_count == 6
        assert relation_count == 6
        assert first_summary["relations_inserted_or_existing"] == 6
        assert second_summary["relations_inserted_or_existing"] == 6
        assert _normalize_entity_code("AI Inference") == "AI_INFERENCE"
        assert _normalize_entity_code("Memory-Fabric") == "MEMORY_FABRIC"
        assert _normalize_entity_code("  GPU   Compute  ") == "GPU_COMPUTE"
    finally:
        conn.close()


def test_import_requires_source_path_when_no_clear_project_default_exists(tmp_path) -> None:
    db_path = tmp_path / "taxonomy_v3_missing_source.db"

    with pytest.raises(ValueError, match="taxonomy_source_path is required"):
        import_datacenter_taxonomy_to_v3(
            db_path=str(db_path),
            taxonomy_source_path=None,
        )
