from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    LEGACY_EQUAL_CALC_VERSION,
    WEIGHTED_CALC_VERSION,
    persist_datacenter_group_relative_ohlc,
    persist_datacenter_group_structure,
    persist_datacenter_group_synthetic_ohlc,
)
from rawcandle.datacenter_weighting_v2_migration import (
    project_v2_to_ec_range,
    run_v2_production_parity_rehearsal,
)
from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_group_synthetic_ohlc_daily_loader import (
    load_ec_group_synthetic_ohlc_daily_from_dc,
)
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration


TAXONOMY_VERSION = "DC_TAXONOMY_TEST_V1"
START_DATE = "2024-01-02"
END_DATE = "2024-02-05"


def _fixture_databases(tmp_path: Path) -> tuple[Path, Path, Path]:
    taxonomy = tmp_path / "taxonomy.csv"
    taxonomy.write_text(
        "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
        f"{TAXONOMY_VERSION},AAA,Power,UPS,CORE,1,1.0,\n"
        f"{TAXONOMY_VERSION},BBB,Networking,Switches,CORE,1,1.0,\n"
        f"{TAXONOMY_VERSION},BBB,Power,UPS,EXTENDED,0,1.0,\n"
        f"{TAXONOMY_VERSION},CCC,Power,UPS,WATCH_ONLY,1,1.0,\n",
        encoding="utf-8",
    )
    prices = tmp_path / "prices.db"
    analysis = tmp_path / "analysis.db"
    with sqlite3.connect(prices) as connection:
        connection.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT, pvm TEXT, open REAL, high REAL, low REAL,
                close REAL, volume INTEGER, market TEXT
            )
            """
        )
        rows = []
        for offset in range(36):
            current = date(2024, 1, 1) + timedelta(days=offset)
            for ticker, multiplier, volume in (
                ("AAA", 1.0, 100),
                ("BBB", 2.0, 200),
                ("CCC", 4.0, 300),
            ):
                close = 100.0 + multiplier * offset
                rows.append(
                    (
                        ticker,
                        current.isoformat(),
                        close - 0.5,
                        close + 1.0,
                        close - 1.0,
                        close,
                        volume + offset,
                        "usa",
                    )
                )
        connection.executemany("INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    DatabaseManager(str(analysis)).close()
    apply_ec_sidecar_migration(str(analysis))
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(analysis),
        taxonomy_csv_path=str(taxonomy),
        taxonomy_version_code=TAXONOMY_VERSION,
    )
    persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis,
        price_db_path=prices,
        taxonomy_csv_path=taxonomy,
        start_date=START_DATE,
        end_date=END_DATE,
        market="usa",
        calc_version=LEGACY_EQUAL_CALC_VERSION,
        run_id="fixture-v1",
        created_at_utc="2026-09-27T00:00:00Z",
        write_mode="replace-range",
        min_eligible_count=1,
    )
    persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis,
        price_db_path=prices,
        taxonomy_csv_path=taxonomy,
        start_date=START_DATE,
        end_date=END_DATE,
        market="usa",
        calc_version=LEGACY_EQUAL_CALC_VERSION,
        run_id="fixture-v1",
        created_at_utc="2026-09-27T00:00:00Z",
        write_mode="replace-relative-range",
    )
    persist_datacenter_group_structure(
        analysis_db_path=analysis,
        start_date=START_DATE,
        end_date=END_DATE,
        calc_version=LEGACY_EQUAL_CALC_VERSION,
        run_id="fixture-v1",
        created_at_utc="2026-09-27T00:00:00Z",
        write_mode="replace-structure-range",
    )
    for offset in range(1, 36):
        signal_date = (date(2024, 1, 1) + timedelta(days=offset)).isoformat()
        load_ec_group_synthetic_ohlc_daily_from_dc(
            source_db_path=str(analysis),
            target_db_path=str(analysis),
            ecosystem_code="DATACENTER",
            taxonomy_version_code=TAXONOMY_VERSION,
            signal_date=signal_date,
            ohlc_calc_version=LEGACY_EQUAL_CALC_VERSION,
            replace_existing=True,
        )
    return analysis, prices, taxonomy


def _scope_rows(db_path: Path, table: str, version_field: str, version: str) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            f"SELECT * FROM {table} WHERE {version_field}=? ORDER BY 1, 2, 3, 4",
            (version,),
        ).fetchall()


def test_v2_rehearsal_isolates_versions_and_proves_projection(tmp_path, monkeypatch) -> None:
    analysis, prices, taxonomy = _fixture_databases(tmp_path)
    source_v1 = _scope_rows(
        analysis, "dc_group_synthetic_ohlc_daily", "calc_version", LEGACY_EQUAL_CALC_VERSION
    )
    source_ec_v1 = _scope_rows(
        analysis, "ec_group_synthetic_ohlc_daily", "ohlc_calc_version", LEGACY_EQUAL_CALC_VERSION
    )
    output_root = tmp_path / "rehearsal"
    monkeypatch.setattr(
        "rawcandle.datacenter_weighting_v2_migration.DEFAULT_OUTPUT_ROOT", output_root
    )

    summary = run_v2_production_parity_rehearsal(
        source_analysis_db=analysis,
        price_db=prices,
        taxonomy_csv=taxonomy,
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        ecosystem_code="DATACENTER",
        output_dir=output_root / "success",
        requested_end_date=END_DATE,
        validated_chain_start_date=START_DATE,
    )

    assert summary["status"] == "OK", summary.get("error")
    assert summary["source_database_unchanged"] is True
    assert summary["v1_dc_unchanged"] is True
    assert summary["v1_ec_unchanged"] is True
    assert summary["v2_rebuild_idempotent"] is True
    assert summary["chain_start_date"] == START_DATE
    assert summary["dc_scope"]["maximum_date"] == END_DATE
    assert summary["dc_ec_v2_parity_mismatch_count"] == 0
    assert summary["v1_report_row_count"] == summary["v2_report_row_count"]
    assert _scope_rows(
        analysis, "dc_group_synthetic_ohlc_daily", "calc_version", LEGACY_EQUAL_CALC_VERSION
    ) == source_v1
    assert _scope_rows(
        analysis, "ec_group_synthetic_ohlc_daily", "ohlc_calc_version", LEGACY_EQUAL_CALC_VERSION
    ) == source_ec_v1

    candidate = Path(summary["candidate_db"])
    v1_rows = _scope_rows(
        candidate, "dc_group_synthetic_ohlc_daily", "calc_version", LEGACY_EQUAL_CALC_VERSION
    )
    v2_rows = _scope_rows(
        candidate, "dc_group_synthetic_ohlc_daily", "calc_version", WEIGHTED_CALC_VERSION
    )
    assert v1_rows and len(v1_rows) == len(v2_rows)
    assert any(v1 != v2 for v1, v2 in zip(v1_rows, v2_rows))
    with sqlite3.connect(candidate) as connection:
        watermarks = dict(
            connection.execute(
                """
                SELECT component_name, row_count
                FROM dc_pipeline_watermark
                WHERE taxonomy_version=? AND calc_version=?
                """,
                (TAXONOMY_VERSION, WEIGHTED_CALC_VERSION),
            ).fetchall()
        )
    assert watermarks["SYNTHETIC_OHLC_BASE"] == len(v2_rows)
    assert watermarks["SYNTHETIC_OHLC_RELATIVE"] == len(v2_rows)
    assert watermarks["SYNTHETIC_OHLC_STRUCTURE"] > 0

    repeat_projection = project_v2_to_ec_range(
        source_db=candidate,
        target_db=candidate,
        ecosystem_code="DATACENTER",
        taxonomy_version=TAXONOMY_VERSION,
        start_date=START_DATE,
        end_date=END_DATE,
    )
    assert repeat_projection["status"] == "OK"
    assert repeat_projection["parity_mismatch_count"] == 0


def test_failed_v2_candidate_keeps_source_and_candidate_v1(tmp_path, monkeypatch) -> None:
    analysis, prices, taxonomy = _fixture_databases(tmp_path)
    source_v1 = _scope_rows(
        analysis, "dc_group_synthetic_ohlc_daily", "calc_version", LEGACY_EQUAL_CALC_VERSION
    )
    output_root = tmp_path / "rehearsal"
    monkeypatch.setattr(
        "rawcandle.datacenter_weighting_v2_migration.DEFAULT_OUTPUT_ROOT", output_root
    )

    summary = run_v2_production_parity_rehearsal(
        source_analysis_db=analysis,
        price_db=prices,
        taxonomy_csv=taxonomy,
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        ecosystem_code="DATACENTER",
        output_dir=output_root / "failure",
        requested_end_date=END_DATE,
        validated_chain_start_date=START_DATE,
        fail_after_stage="base",
    )

    assert summary["status"] == "FAILED"
    assert summary["v1_dc_unchanged"] is True
    assert summary["source_database_unchanged"] is True
    assert "Injected rehearsal failure after base" in summary["error"]
    assert _scope_rows(
        analysis, "dc_group_synthetic_ohlc_daily", "calc_version", LEGACY_EQUAL_CALC_VERSION
    ) == source_v1
    assert _scope_rows(
        Path(summary["candidate_db"]),
        "dc_group_synthetic_ohlc_daily",
        "calc_version",
        LEGACY_EQUAL_CALC_VERSION,
    ) == source_v1
