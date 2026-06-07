import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_group_index_daily_loader import load_ec_group_index_daily_from_dc
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_taxonomy_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
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
        writer.writerow(["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""])
        writer.writerow(["DC_TAXONOMY_FULL_V1", "AVGO", "Networking", "Switch silicon", "CORE", 1, 1.0, ""])


def _create_source_db(path: Path, rows: list[dict[str, object]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_group_index_daily (
                index_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                member_count INTEGER NULL,
                eligible_count INTEGER NULL,
                ma50_eligible_count INTEGER NULL,
                ma200_eligible_count INTEGER NULL,
                daily_return_equal REAL NULL,
                median_return REAL NULL,
                pct_positive REAL NULL,
                index_level_equal REAL NULL,
                return_20d REAL NULL,
                return_60d REAL NULL,
                return_120d REAL NULL,
                pct_above_ma50 REAL NULL,
                pct_above_ma200 REAL NULL,
                volatility_20d REAL NULL,
                volatility_60d REAL NULL,
                relative_strength_spy_60d REAL NULL,
                relative_strength_qqq_60d REAL NULL,
                data_quality_status TEXT NULL,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (index_date, taxonomy_version, group_type, group_name)
            )
            """
        )
        columns = list(rows[0].keys()) if rows else []
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO dc_group_index_daily ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _source_row(
    *,
    group_type: str,
    group_name: str,
    index_date: str = "2026-06-05",
    calc_version: str = "DC_INDEX_CALC_V1",
    run_id: str = "DC_INDEX_DC_TAXONOMY_FULL_V1_BASE20200101_20200101_20260605",
) -> dict[str, object]:
    return {
        "index_date": index_date,
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "group_type": group_type,
        "group_name": group_name,
        "member_count": 11,
        "eligible_count": 10,
        "ma50_eligible_count": 10,
        "ma200_eligible_count": 9,
        "daily_return_equal": 0.0134,
        "median_return": 0.0091,
        "pct_positive": 0.7273,
        "index_level_equal": 124.55,
        "return_20d": 0.082,
        "return_60d": 0.194,
        "return_120d": 0.331,
        "pct_above_ma50": 0.8,
        "pct_above_ma200": 0.6,
        "volatility_20d": 0.021,
        "volatility_60d": 0.028,
        "relative_strength_spy_60d": 0.143,
        "relative_strength_qqq_60d": 0.067,
        "data_quality_status": "OK",
        "calc_version": calc_version,
        "run_id": run_id,
        "created_at_utc": "2026-06-07T04:12:00Z",
    }


def _setup_target_db(tmp_path) -> tuple[Path, Path]:
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    target_db = tmp_path / "target.db"
    taxonomy_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(target_db))
    _write_taxonomy_csv(taxonomy_path)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(target_db),
        taxonomy_csv_path=str(taxonomy_path),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )
    return target_db, taxonomy_path


def test_loader_persists_group_index_rows_lineage_and_signal_run(tmp_path) -> None:
    source_db = tmp_path / "source.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(
        source_db,
        [
            _source_row(group_type="layer", group_name="Compute silicon"),
            _source_row(group_type="subindustry", group_name="GPUs"),
            _source_row(group_type="ecosystem", group_name="DC_ECOSYSTEM_TOTAL"),
        ],
    )

    summary = load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    conn = _connect(str(target_db))
    try:
        rows = conn.execute(
            """
            SELECT entity_type, signal_date, calc_version, member_count, eligible_count, index_value, return_1d,
                   return_20d, relative_strength_20d, relative_strength_spy_60d,
                   relative_strength_qqq_60d, data_quality_status, source_table,
                   source_pk_json, source_row_hash, source_run_id
            FROM ec_group_index_daily
            ORDER BY entity_type, entity_id
            """
        ).fetchall()
        assert rows[0][:12] == (
            "ECOSYSTEM",
            "2026-06-05",
            "DC_INDEX_CALC_V1",
            11,
            10,
            124.55,
            0.0134,
            0.082,
            None,
            0.143,
            0.067,
            "OK",
        )
        assert rows[1][:12] == (
            "GROUP_L1",
            "2026-06-05",
            "DC_INDEX_CALC_V1",
            11,
            10,
            124.55,
            0.0134,
            0.082,
            None,
            0.143,
            0.067,
            "OK",
        )
        assert rows[2][:12] == (
            "GROUP_L2",
            "2026-06-05",
            "DC_INDEX_CALC_V1",
            11,
            10,
            124.55,
            0.0134,
            0.082,
            None,
            0.143,
            0.067,
            "OK",
        )
        assert all(row[12] == "dc_group_index_daily" for row in rows)
        source_pk = json.loads(rows[0][13])
        assert source_pk == {
            "calc_version": "DC_INDEX_CALC_V1",
            "group_name": "DC_ECOSYSTEM_TOTAL",
            "group_type": "ecosystem",
            "index_date": "2026-06-05",
            "run_id": "DC_INDEX_DC_TAXONOMY_FULL_V1_BASE20200101_20200101_20260605",
            "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        }
        assert len(rows[0][14]) == 64
        assert rows[0][15] == "DC_INDEX_DC_TAXONOMY_FULL_V1_BASE20200101_20200101_20260605"

        signal_run = conn.execute(
            """
            SELECT run_type, signal_version, ohlc_calc_version, source_mode, status, started_at_utc, finished_at_utc
            FROM ec_signal_run
            WHERE run_id = 'DC_INDEX_DC_TAXONOMY_FULL_V1_BASE20200101_20200101_20260605'
            """
        ).fetchone()
        assert signal_run == (
            "GROUP_INDEX",
            None,
            None,
            "DC_BACKFILL",
            "OK",
            "2026-06-07T04:12:00Z",
            "2026-06-07T04:12:00Z",
        )

        assert summary == {
            "status": "OK_WITH_WARNINGS",
            "ecosystem_code": "DATACENTER",
            "taxonomy_version_code": "DC_TAXONOMY_FULL_V1",
            "signal_date": "2026-06-05",
            "calc_version": "DC_INDEX_CALC_V1",
            "source_table": "dc_group_index_daily",
            "source_row_count": 3,
            "loaded_row_count": 3,
            "failed_row_count": 0,
            "unmapped_source_columns": [],
            "unmapped_target_columns": [
                "return_5d",
                "return_10d",
                "trend_breadth",
                "weakness_breadth",
                "relative_strength_20d",
            ],
            "missing_group_entities": [],
            "missing_group_aliases": [],
            "multiple_group_matches": [],
            "source_run_ids": ["DC_INDEX_DC_TAXONOMY_FULL_V1_BASE20200101_20200101_20260605"],
            "created_signal_run_count": 1,
            "reused_signal_run_count": 0,
            "group_count_by_type": {
                "ecosystem": 1,
                "layer": 1,
                "subindustry": 1,
            },
            "warnings": [
                "Target columns left NULL because current dc source has no values: return_5d, return_10d, trend_breadth, weakness_breadth, relative_strength_20d"
            ],
        }
    finally:
        conn.close()


def test_loader_fails_when_layer_entity_is_missing(tmp_path) -> None:
    source_db = tmp_path / "source_missing_layer.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Missing layer")])

    summary = load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    assert summary["status"] == "FAILED"
    assert summary["missing_group_entities"] == ["layer:Missing layer"]
    assert summary["failed_row_count"] == 1


def test_loader_fails_when_subindustry_entity_is_missing(tmp_path) -> None:
    source_db = tmp_path / "source_missing_subindustry.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row(group_type="subindustry", group_name="GPUs")])

    with _connect(str(target_db)) as conn:
        conn.execute("DELETE FROM ec_membership WHERE parent_entity_id IN (SELECT entity_id FROM ec_entity WHERE entity_type='GROUP_L2' AND entity_code='GPUS')")
        conn.execute("DELETE FROM ec_membership WHERE child_entity_id IN (SELECT entity_id FROM ec_entity WHERE entity_type='GROUP_L2' AND entity_code='GPUS')")
        conn.execute("DELETE FROM ec_entity WHERE entity_type='GROUP_L2' AND entity_code='GPUS'")
        conn.commit()

    summary = load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    assert summary["status"] == "FAILED"
    assert summary["missing_group_entities"] == ["subindustry:GPUs"]
    assert summary["failed_row_count"] == 1


def test_loader_fails_when_ecosystem_alias_is_missing(tmp_path) -> None:
    source_db = tmp_path / "source_missing_alias.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row(group_type="ecosystem", group_name="DC_ECOSYSTEM_TOTAL")])

    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            DELETE FROM ec_entity_alias
            WHERE alias_type = 'DC_GROUP_NAME'
              AND alias_value = 'DC_ECOSYSTEM_TOTAL'
              AND source_system = 'dc_group_facts'
            """
        )
        conn.commit()

    summary = load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    assert summary["status"] == "FAILED"
    assert summary["missing_group_aliases"] == ["DC_ECOSYSTEM_TOTAL"]
    assert summary["failed_row_count"] == 1


def test_loader_duplicate_scope_requires_replace_existing_and_replace_is_scoped(tmp_path) -> None:
    source_db = tmp_path / "source_replace.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Compute silicon")])

    first_summary = load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )
    assert first_summary["loaded_row_count"] == 1

    with pytest.raises(ValueError, match="Target group index fact rows already exist"):
        load_ec_group_index_daily_from_dc(
            source_db_path=str(source_db),
            target_db_path=str(target_db),
            replace_existing=False,
        )

    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            INSERT INTO ec_signal_run (
                run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, source_mode, status, started_at_utc
            ) VALUES ('legacy-index-run', 1, 1, '2026-06-04', 'GROUP_INDEX', 'TEST', 'OK', '2026-06-07T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO ec_group_index_daily (
                ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, calc_version,
                source_table, source_pk_json, source_row_hash, source_run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "2026-06-04",
                1,
                "ECOSYSTEM",
                "DC_INDEX_CALC_V1",
                "dc_group_index_daily",
                '{"index_date":"2026-06-04","group_name":"legacy"}',
                "legacy-hash",
                "legacy-index-run",
                "2026-06-07T00:00:00Z",
            ),
        )
        conn.commit()

    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Compute silicon", calc_version="DC_INDEX_CALC_V1")])
    summary = load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
        replace_existing=True,
    )

    with _connect(str(target_db)) as conn:
        rows = conn.execute(
            """
            SELECT signal_date, entity_type, index_value
            FROM ec_group_index_daily
            ORDER BY signal_date, entity_type
            """
        ).fetchall()
        assert rows == [
            ("2026-06-04", "ECOSYSTEM", None),
            ("2026-06-05", "GROUP_L1", 124.55),
        ]
    assert summary["loaded_row_count"] == 1
    assert summary["reused_signal_run_count"] == 1
    assert summary["created_signal_run_count"] == 0


def test_loader_source_row_hash_is_deterministic(tmp_path) -> None:
    source_db = tmp_path / "source_hash.db"
    target_db_a, _ = _setup_target_db(tmp_path / "a")
    target_db_b, _ = _setup_target_db(tmp_path / "b")
    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Compute silicon")])

    load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db_a),
    )
    load_ec_group_index_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db_b),
    )

    with _connect(str(target_db_a)) as conn_a, _connect(str(target_db_b)) as conn_b:
        hash_a = conn_a.execute("SELECT source_row_hash FROM ec_group_index_daily").fetchone()[0]
        hash_b = conn_b.execute("SELECT source_row_hash FROM ec_group_index_daily").fetchone()[0]
        assert hash_a == hash_b
