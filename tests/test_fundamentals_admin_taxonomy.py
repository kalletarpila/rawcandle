from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.fundamentals.admin.taxonomy import TaxonomyPaths, run_apply, run_preview, validate_taxonomy_domain


def _write_csv(path: Path, version: str, role: str = "CORE") -> Path:
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                f"{version},AAA,Compute,Servers,{role},1,1.0,",
                f"{version},BBB,Power,UPS,CORE,1,1.0,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _create_dc_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ecosystem_membership (
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            layer TEXT NOT NULL,
            subindustry TEXT NOT NULL,
            report_group_status TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            role_weight REAL NOT NULL DEFAULT 1.0,
            notes TEXT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (taxonomy_version, ticker, layer, subindustry)
        )
        """
    )


def _create_ec_schema(conn: sqlite3.Connection) -> None:
    migration = Path("rawcandle/sqlite/migrations/019_create_ec_sidecar_schema.sql").read_text(encoding="utf-8")
    conn.executescript(migration)


def _db(tmp_path: Path) -> Path:
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        _create_dc_schema(conn)
        _create_ec_schema(conn)
        conn.executemany(
            """
            INSERT INTO dc_ecosystem_membership (
                taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes,created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("DC_TAXONOMY_V1", "AAA", "Compute", "Servers", "CORE", 1, 1.0, None, "2026-01-01T00:00:00Z"),
                ("DC_TAXONOMY_V1", "BBB", "Power", "UPS", "CORE", 1, 1.0, None, "2026-01-01T00:00:00Z"),
            ],
        )
    load_datacenter_taxonomy_to_ec_sidecar(db_path, _write_csv(tmp_path / "ec_v1.csv", "EC_TAXONOMY_V1"), "EC_TAXONOMY_V1", mark_active=True)
    return db_path


def _paths(db_path: Path) -> TaxonomyPaths:
    return TaxonomyPaths(provider_db=db_path, canonical_db=db_path, analysis_db=db_path, market_db=db_path, taxonomy_db=db_path)


def test_validate_taxonomy_domain_rejects_unknown_domain() -> None:
    assert validate_taxonomy_domain("dc_ecosystem") == "dc_ecosystem"
    with pytest.raises(ValueError, match="PHASE13G4_UNKNOWN_TAXONOMY_DOMAIN"):
        validate_taxonomy_domain("merged_taxonomy")


def test_preview_fingerprints_are_domain_specific(tmp_path: Path) -> None:
    paths = _paths(_db(tmp_path))
    run_root = tmp_path / "runs"

    dc = run_preview(taxonomy_domain="dc_ecosystem", source_paths=paths, run_root=run_root)
    ec = run_preview(taxonomy_domain="ec_taxonomy", source_paths=paths, run_root=run_root)

    dc_preview = json.loads((Path(dc["artifact_dir"]) / "preview.json").read_text(encoding="utf-8"))
    ec_preview = json.loads((Path(ec["artifact_dir"]) / "preview.json").read_text(encoding="utf-8"))
    assert dc_preview["taxonomy_domain"] == "dc_ecosystem"
    assert ec_preview["taxonomy_domain"] == "ec_taxonomy"
    assert dc_preview["preview_fingerprint"] != ec_preview["preview_fingerprint"]
    assert "ec_taxonomy_version" in dc_preview["active_taxonomy"]["schema"]["tables"]
    assert dc_preview["active_taxonomy"]["version"]["is_current_primary_production_taxonomy"] is True
    assert ec_preview["active_taxonomy"]["schema"]["update_contract_status"] == "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY"
    assert ec_preview["active_taxonomy"]["version"]["is_current_primary_production_taxonomy"] is False


def test_cross_domain_preview_is_rejected_before_apply(tmp_path: Path) -> None:
    paths = _paths(_db(tmp_path))
    candidate = _write_csv(tmp_path / "dc_v2.csv", "DC_TAXONOMY_V2", role="EXTENDED")
    preview = run_preview(taxonomy_domain="dc_ecosystem", candidate_path=candidate, candidate_version="DC_TAXONOMY_V2", source_paths=paths, run_root=tmp_path / "runs")

    with pytest.raises(ValueError, match="PHASE13G4_CROSS_DOMAIN_PREVIEW_REJECTED"):
        run_apply(
            taxonomy_domain="ec_taxonomy",
            preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=str(preview["preview_fingerprint"]),
            source_paths=paths,
            run_root=tmp_path / "runs",
            temp_root=tmp_path / "tmp",
            confirm_apply=True,
        )


def test_dc_copy_apply_does_not_mutate_ec_or_source(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    paths = _paths(db_path)
    candidate = _write_csv(tmp_path / "dc_v2.csv", "DC_TAXONOMY_V2", role="EXTENDED")
    preview = run_preview(taxonomy_domain="dc_ecosystem", candidate_path=candidate, candidate_version="DC_TAXONOMY_V2", source_paths=paths, run_root=tmp_path / "runs")

    result = run_apply(
        taxonomy_domain="dc_ecosystem",
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=str(preview["preview_fingerprint"]),
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "tmp",
        confirm_apply=True,
    )

    assert result["outcome"] == "COMPLETED"
    assert result["downstream"]["isolation"]["cross_domain_mutation"] is False
    assert result["downstream"]["non_selected_domain_before_fingerprint"] == result["downstream"]["non_selected_domain_after_fingerprint"]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT taxonomy_version_code FROM ec_taxonomy_version WHERE is_active=1").fetchone()[0] == "EC_TAXONOMY_V1"
        assert conn.execute("SELECT COUNT(*) FROM ec_taxonomy_version WHERE taxonomy_version_code='DC_TAXONOMY_V2'").fetchone()[0] == 0


def test_ec_copy_apply_reports_update_contract_not_ready(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    paths = _paths(db_path)
    candidate = _write_csv(tmp_path / "ec_v2.csv", "EC_TAXONOMY_V2", role="EXTENDED")
    preview = run_preview(taxonomy_domain="ec_taxonomy", candidate_path=candidate, candidate_version="EC_TAXONOMY_V2", source_paths=paths, run_root=tmp_path / "runs")

    preview_json = json.loads((Path(preview["artifact_dir"]) / "preview.json").read_text(encoding="utf-8"))
    assert preview_json["dependency_reasoning"]["update_contract_status"] == "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY"
    assert preview_json["expected_writable_database_set"] == []
    with pytest.raises(RuntimeError, match="EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY"):
        run_apply(
            taxonomy_domain="ec_taxonomy",
            preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=str(preview["preview_fingerprint"]),
            source_paths=paths,
            run_root=tmp_path / "runs",
            temp_root=tmp_path / "tmp",
            confirm_apply=True,
        )
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM dc_ecosystem_membership WHERE taxonomy_version='EC_TAXONOMY_V2'").fetchone()[0] == 0
        assert conn.execute("SELECT taxonomy_version_code FROM ec_taxonomy_version WHERE is_active=1").fetchone()[0] == "EC_TAXONOMY_V1"


def test_copy_apply_rollback_injection_records_restored_copy(tmp_path: Path) -> None:
    paths = _paths(_db(tmp_path))
    candidate = _write_csv(tmp_path / "dc_v2.csv", "DC_TAXONOMY_V2", role="EXTENDED")
    preview = run_preview(taxonomy_domain="dc_ecosystem", candidate_path=candidate, candidate_version="DC_TAXONOMY_V2", source_paths=paths, run_root=tmp_path / "runs")

    result = run_apply(
        taxonomy_domain="dc_ecosystem",
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=str(preview["preview_fingerprint"]),
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "tmp",
        confirm_apply=True,
        inject_failure_after_write=True,
    )

    assert result["outcome"] == "ROLLED_BACK"
    assert result["rollback"]["status"] == "RESTORED_COPY_SET"
