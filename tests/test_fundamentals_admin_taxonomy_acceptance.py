from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.fundamentals.admin.taxonomy import TaxonomyPaths
from rawcandle.fundamentals.admin.taxonomy_acceptance import run_dc_ecosystem_copy_acceptance


def _write_csv(path: Path, version: str) -> Path:
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                f"{version},AAA,Compute,Servers,CORE,1,1.0,",
                f"{version},BBB,Power,UPS,CORE,1,1.0,",
                f"{version},NVDA,Compute,Accelerators,CORE,1,1.0,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _create_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(Path("rawcandle/sqlite/migrations/019_create_ec_sidecar_schema.sql").read_text(encoding="utf-8"))
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
    load_datacenter_taxonomy_to_ec_sidecar(db_path, _write_csv(tmp_path / "dc_v1.csv", "DC_TAXONOMY_FULL_V2_1"), "DC_TAXONOMY_FULL_V2_1", mark_active=True)
    return db_path


def _paths(db_path: Path) -> TaxonomyPaths:
    return TaxonomyPaths(provider_db=db_path, canonical_db=db_path, analysis_db=db_path, market_db=db_path, taxonomy_db=db_path)


def test_dc_acceptance_verifies_copy_apply_replay_and_rollback(tmp_path: Path) -> None:
    result = run_dc_ecosystem_copy_acceptance(
        source_paths=_paths(_create_db(tmp_path)),
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "tmp",
        run_full_downstream=False,
        scheduler_evidence={"timer_initial": "inactive", "service_initial": "inactive"},
    )

    assert result["candidate"]["status"] == "TEST_ONLY_NOT_FOR_PRODUCTION"
    assert result["apply"]["taxonomy_apply"]["outcome"] == "APPLIED"
    assert result["apply"]["changed"] is True
    assert result["apply"]["ec_unchanged"] is True
    assert result["repeat_no_change"]["outcome"] == "NO_CHANGE"
    assert result["repeat_no_change"]["new_version_rows"] == 0
    assert result["repeat_no_change"]["membership_writes"] == 0
    assert result["replay"]["status"] == "MATCH"
    assert result["rollback"]["partial_state_existed"] is True
    assert result["rollback"]["restored_matches_baseline"] is True
    assert result["production_immutability"]["active_dc_taxonomy_unchanged"] is True
    assert result["cleanup"]["reclaimed_bytes"] > 0


def test_dc_acceptance_keeps_source_database_unchanged(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    run_dc_ecosystem_copy_acceptance(
        source_paths=_paths(db_path),
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "tmp",
        run_full_downstream=False,
    )

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT taxonomy_version_code,status,is_active FROM ec_taxonomy_version ORDER BY taxonomy_version_id").fetchall()
    assert rows == [("DC_TAXONOMY_FULL_V2_1", "ACTIVE", 1)]
