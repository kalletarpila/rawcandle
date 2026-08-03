import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_group_signal_daily_loader import load_ec_group_signal_daily_from_dc
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_taxonomy_csv(path: Path, *, version: str = "DC_TAXONOMY_FULL_V1") -> None:
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
        writer.writerow([version, "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""])
        writer.writerow([version, "AVGO", "Networking", "Switch silicon", "CORE", 1, 1.0, ""])


def _create_source_db(path: Path, rows: list[dict[str, object]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                member_count INTEGER NULL,
                eligible_count INTEGER NULL,
                return_5d REAL NULL,
                return_10d REAL NULL,
                return_20d REAL NULL,
                return_60d REAL NULL,
                pct_above_ma10 REAL NULL,
                pct_above_ema20 REAL NULL,
                pct_above_rising_ema20 REAL NULL,
                ma10_breadth_delta_5d REAL NULL,
                ema20_breadth_delta_5d REAL NULL,
                trend_breadth REAL NULL,
                weakness_breadth REAL NULL,
                overheat_risk_level TEXT NULL,
                timing_state TEXT NULL,
                timing_reason TEXT NULL,
                data_quality_status TEXT NULL,
                signal_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, group_type, group_name, signal_version)
            )
            """
        )
        columns = list(rows[0].keys()) if rows else []
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO dc_group_swing_signal_daily ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _source_row(
    *,
    group_type: str,
    group_name: str,
    signal_date: str = "2026-06-05",
    signal_version: str = "DC_SWING_SIGNAL_V1",
    run_id: str = "DC_GROUP_SWING_20260605_DC_SWING_SIGNAL_V1",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
) -> dict[str, object]:
    return {
        "signal_date": signal_date,
        "taxonomy_version": taxonomy_version,
        "group_type": group_type,
        "group_name": group_name,
        "member_count": 10,
        "eligible_count": 9,
        "return_5d": 0.05,
        "return_10d": 0.10,
        "return_20d": 0.20,
        "return_60d": 0.30,
        "pct_above_ma10": 40.0,
        "pct_above_ema20": 50.0,
        "pct_above_rising_ema20": 45.0,
        "ma10_breadth_delta_5d": -5.0,
        "ema20_breadth_delta_5d": -2.0,
        "trend_breadth": 60.0,
        "weakness_breadth": 40.0,
        "overheat_risk_level": "LOW",
        "timing_state": "SETUP",
        "timing_reason": "setup-window",
        "data_quality_status": "OK",
        "signal_version": signal_version,
        "run_id": run_id,
        "created_at_utc": "2026-06-07T03:48:03Z",
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


def _setup_target_db_with_versions(tmp_path, versions: tuple[str, ...]) -> Path:
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    target_db = tmp_path / "target.db"
    apply_ec_sidecar_migration(str(target_db))
    for version in versions:
        taxonomy_path = tmp_path / f"{version}.csv"
        _write_taxonomy_csv(taxonomy_path, version=version)
        load_datacenter_taxonomy_to_ec_sidecar(
            db_path=str(target_db),
            taxonomy_csv_path=str(taxonomy_path),
            taxonomy_version_code=version,
        )
    return target_db


def test_loader_persists_group_fact_rows_lineage_alias_and_signal_run(tmp_path) -> None:
    source_db = tmp_path / "source.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(
        source_db,
        [
            _source_row(group_type="ecosystem", group_name="DC_ECOSYSTEM_TOTAL"),
            _source_row(group_type="layer", group_name="Compute silicon"),
            _source_row(group_type="subindustry", group_name="GPUs"),
        ],
    )

    summary = load_ec_group_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    conn = _connect(str(target_db))
    try:
        rows = conn.execute(
            """
            SELECT entity_type, signal_date, signal_version, member_count, pct_above_rising_ema20,
                   timing_state, data_quality_status, source_table, source_pk_json, source_row_hash, source_run_id
            FROM ec_group_signal_daily
            ORDER BY entity_type, entity_id
            """
        ).fetchall()
        assert rows[0][:7] == ("ECOSYSTEM", "2026-06-05", "DC_SWING_SIGNAL_V1", 10, 45.0, "SETUP", "OK")
        assert rows[1][:7] == ("GROUP_L1", "2026-06-05", "DC_SWING_SIGNAL_V1", 10, 45.0, "SETUP", "OK")
        assert rows[2][:7] == ("GROUP_L2", "2026-06-05", "DC_SWING_SIGNAL_V1", 10, 45.0, "SETUP", "OK")
        assert all(row[7] == "dc_group_swing_signal_daily" for row in rows)
        source_pk = json.loads(rows[0][8])
        assert source_pk == {
            "group_name": "DC_ECOSYSTEM_TOTAL",
            "group_type": "ecosystem",
            "run_id": "DC_GROUP_SWING_20260605_DC_SWING_SIGNAL_V1",
            "signal_date": "2026-06-05",
            "signal_version": "DC_SWING_SIGNAL_V1",
            "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        }
        assert len(rows[0][9]) == 64
        assert rows[0][10] == "DC_GROUP_SWING_20260605_DC_SWING_SIGNAL_V1"

        signal_run = conn.execute(
            """
            SELECT run_type, signal_version, source_mode, status, started_at_utc, finished_at_utc
            FROM ec_signal_run
            WHERE run_id = 'DC_GROUP_SWING_20260605_DC_SWING_SIGNAL_V1'
            """
        ).fetchone()
        assert signal_run == (
            "GROUP_SIGNAL",
            "DC_SWING_SIGNAL_V1",
            "DC_BACKFILL",
            "OK",
            "2026-06-07T03:48:03Z",
            "2026-06-07T03:48:03Z",
        )

        assert summary["status"] == "OK_WITH_WARNINGS"
        assert summary["loader_status"] == "OK_WITH_WARNINGS"
        assert summary["loader_error_code"] == "NONE"
        assert summary["ecosystem_code"] == "DATACENTER"
        assert summary["taxonomy_version_code"] == "DC_TAXONOMY_FULL_V1"
        assert summary["requested_taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
        assert summary["source_taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
        assert summary["source_taxonomy_match"] is True
        assert summary["signal_date"] == "2026-06-05"
        assert summary["signal_version"] == "DC_SWING_SIGNAL_V1"
        assert summary["source_table"] == "dc_group_swing_signal_daily"
        assert summary["source_row_count"] == 3
        assert summary["source_distinct_group_count"] == 3
        assert summary["duplicate_source_group_count"] == 0
        assert summary["unexpected_taxonomy_version_count"] == 0
        assert summary["unexpected_signal_version_count"] == 0
        assert summary["null_required_source_key_count"] == 0
        assert summary["loaded_row_count"] == 3
        assert summary["failed_row_count"] == 0
        assert summary["mapped_row_count"] == 3
        assert summary["distinct_target_key_count"] == 3
        assert summary["duplicate_target_key_count"] == 0
        assert summary["null_target_key_count"] == 0
        assert summary["unresolved_group_count"] == 0
        assert summary["unresolved_groups"] == []
        assert summary["multiple_source_to_same_target_count"] == 0
        assert summary["unmapped_source_columns"] == []
        assert summary["unmapped_target_columns"] == [
            "valid_price_count",
            "return_1d",
            "return_120d",
            "pct_above_sma50",
            "pct_above_sma200",
        ]
        assert summary["missing_group_entities"] == []
        assert summary["missing_group_aliases"] == []
        assert summary["multiple_group_matches"] == []
        assert summary["source_run_ids"] == ["DC_GROUP_SWING_20260605_DC_SWING_SIGNAL_V1"]
        assert summary["created_signal_run_count"] == 1
        assert summary["reused_signal_run_count"] == 0
        assert summary["group_count_by_type"] == {"ecosystem": 1, "layer": 1, "subindustry": 1}
        assert summary["group_type_counts"] == {"ecosystem": 1, "layer": 1, "subindustry": 1}
        assert summary["data_quality_status_counts"] == {"OK": 3}
        assert summary["warnings"] == [
            "Target columns left NULL because current dc source has no values: valid_price_count, return_1d, return_120d, pct_above_sma50, pct_above_sma200"
        ]
    finally:
        conn.close()


def test_loader_fails_when_layer_entity_is_missing(tmp_path) -> None:
    source_db = tmp_path / "source_missing_layer.db"
    target_db, _ = _setup_target_db(tmp_path)
    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Missing layer")])

    summary = load_ec_group_signal_daily_from_dc(
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

    summary = load_ec_group_signal_daily_from_dc(
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

    summary = load_ec_group_signal_daily_from_dc(
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

    first_summary = load_ec_group_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )
    assert first_summary["loaded_row_count"] == 1

    with pytest.raises(ValueError, match="Target group fact rows already exist"):
        load_ec_group_signal_daily_from_dc(
            source_db_path=str(source_db),
            target_db_path=str(target_db),
            replace_existing=False,
        )

    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            INSERT INTO ec_signal_run (
                run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, signal_version,
                source_mode, status, started_at_utc
            ) VALUES ('legacy-group-run', 1, 1, '2026-06-04', 'GROUP_SIGNAL', 'DC_SWING_SIGNAL_V1', 'TEST', 'OK', '2026-06-07T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO ec_group_signal_daily (
                ecosystem_id, taxonomy_version_id, signal_date, entity_id, entity_type, signal_version,
                source_table, source_pk_json, source_row_hash, source_run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "2026-06-04",
                1,
                "ECOSYSTEM",
                "DC_SWING_SIGNAL_V1",
                "dc_group_swing_signal_daily",
                '{"signal_date":"2026-06-04","group_name":"legacy"}',
                "legacy-hash",
                "legacy-group-run",
                "2026-06-07T00:00:00Z",
            ),
        )
        conn.commit()

    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Compute silicon")])
    summary = load_ec_group_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
        replace_existing=True,
    )

    with _connect(str(target_db)) as conn:
        rows = conn.execute(
            """
            SELECT signal_date, entity_type, member_count
            FROM ec_group_signal_daily
            ORDER BY signal_date, entity_type
            """
        ).fetchall()
        assert rows == [
            ("2026-06-04", "ECOSYSTEM", None),
            ("2026-06-05", "GROUP_L1", 10),
        ]
    assert summary["loaded_row_count"] == 1
    assert summary["reused_signal_run_count"] == 1
    assert summary["created_signal_run_count"] == 0


def test_loader_source_row_hash_is_deterministic(tmp_path) -> None:
    source_db = tmp_path / "source_hash.db"
    target_db_a, _ = _setup_target_db(tmp_path / "a")
    target_db_b, _ = _setup_target_db(tmp_path / "b")
    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Compute silicon")])

    load_ec_group_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db_a),
    )
    load_ec_group_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db_b),
    )

    with _connect(str(target_db_a)) as conn_a, _connect(str(target_db_b)) as conn_b:
        hash_a = conn_a.execute("SELECT source_row_hash FROM ec_group_signal_daily").fetchone()[0]
        hash_b = conn_b.execute("SELECT source_row_hash FROM ec_group_signal_daily").fetchone()[0]
        assert hash_a == hash_b


def test_loader_selects_only_requested_taxonomy_when_v1_and_v2_share_date_and_signal(tmp_path) -> None:
    source_db = tmp_path / "source_mixed_taxonomy.db"
    target_db = _setup_target_db_with_versions(tmp_path, ("DC_TAXONOMY_FULL_V1", "DC_TAXONOMY_FULL_V2"))
    source_rows = []
    for taxonomy_version, marker in (
        ("DC_TAXONOMY_FULL_V1", 10),
        ("DC_TAXONOMY_FULL_V2", 20),
    ):
        source_rows.extend(
            [
                {
                    **_source_row(
                        group_type="ecosystem",
                        group_name="DC_ECOSYSTEM_TOTAL",
                        signal_date="2025-08-01",
                        taxonomy_version=taxonomy_version,
                        run_id=f"{taxonomy_version}_GROUP_RUN",
                    ),
                    "member_count": marker,
                },
                {
                    **_source_row(
                        group_type="layer",
                        group_name="Compute silicon",
                        signal_date="2025-08-01",
                        taxonomy_version=taxonomy_version,
                        run_id=f"{taxonomy_version}_GROUP_RUN",
                    ),
                    "member_count": marker,
                },
                {
                    **_source_row(
                        group_type="subindustry",
                        group_name="GPUs",
                        signal_date="2025-08-01",
                        taxonomy_version=taxonomy_version,
                        run_id=f"{taxonomy_version}_GROUP_RUN",
                    ),
                    "member_count": marker,
                },
            ]
        )
    _create_source_db(source_db, source_rows)

    summary = load_ec_group_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        signal_date="2025-08-01",
    )

    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["requested_taxonomy_version"] == "DC_TAXONOMY_FULL_V2"
    assert summary["source_taxonomy_version"] == "DC_TAXONOMY_FULL_V2"
    assert summary["source_taxonomy_match"] is True
    assert summary["source_row_count"] == 3
    assert summary["source_distinct_group_count"] == 3
    assert summary["duplicate_target_key_count"] == 0
    assert summary["mapped_row_count"] == 3
    with _connect(str(target_db)) as conn:
        rows = conn.execute(
            """
            SELECT taxonomy_version_id, member_count, source_run_id
            FROM ec_group_signal_daily
            ORDER BY entity_type, entity_id
            """
        ).fetchall()
    assert rows == [
        (2, 20, "DC_TAXONOMY_FULL_V2_GROUP_RUN"),
        (2, 20, "DC_TAXONOMY_FULL_V2_GROUP_RUN"),
        (2, 20, "DC_TAXONOMY_FULL_V2_GROUP_RUN"),
    ]


def test_loader_ordinary_v1_path_selects_only_v1(tmp_path) -> None:
    source_db = tmp_path / "source_mixed_v1.db"
    target_db = _setup_target_db_with_versions(tmp_path, ("DC_TAXONOMY_FULL_V1", "DC_TAXONOMY_FULL_V2"))
    _create_source_db(
        source_db,
        [
            {
                **_source_row(
                    group_type="layer",
                    group_name="Compute silicon",
                    taxonomy_version="DC_TAXONOMY_FULL_V1",
                    run_id="V1_GROUP_RUN",
                ),
                "member_count": 11,
            },
            {
                **_source_row(
                    group_type="layer",
                    group_name="Compute silicon",
                    taxonomy_version="DC_TAXONOMY_FULL_V2",
                    run_id="V2_GROUP_RUN",
                ),
                "member_count": 22,
            },
        ],
    )

    summary = load_ec_group_signal_daily_from_dc(source_db_path=str(source_db), target_db_path=str(target_db))

    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["requested_taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    assert summary["source_taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    with _connect(str(target_db)) as conn:
        row = conn.execute("SELECT taxonomy_version_id, member_count, source_run_id FROM ec_group_signal_daily").fetchone()
    assert row == (1, 11, "V1_GROUP_RUN")


def test_loader_returns_structured_failure_when_requested_taxonomy_has_no_source_rows(tmp_path) -> None:
    source_db = tmp_path / "source_no_v2.db"
    target_db = _setup_target_db_with_versions(tmp_path, ("DC_TAXONOMY_FULL_V1", "DC_TAXONOMY_FULL_V2"))
    _create_source_db(source_db, [_source_row(group_type="layer", group_name="Compute silicon")])

    summary = load_ec_group_signal_daily_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        signal_date="2026-06-05",
    )

    assert summary["status"] == "FAILED"
    assert summary["loader_status"] == "FAILED"
    assert summary["loader_error_code"] == "SOURCE_SCOPE_UNAVAILABLE"
    assert summary["requested_taxonomy_version"] == "DC_TAXONOMY_FULL_V2"
    assert summary["source_row_count"] == 0
    assert summary["loaded_row_count"] == 0
    assert "DC_TAXONOMY_FULL_V2" in summary["loader_error"]


def test_loader_blocks_ambiguous_signal_version_within_requested_taxonomy(tmp_path) -> None:
    source_db = tmp_path / "source_ambiguous_signal.db"
    target_db = _setup_target_db_with_versions(tmp_path, ("DC_TAXONOMY_FULL_V1",))
    _create_source_db(
        source_db,
        [
            _source_row(group_type="layer", group_name="Compute silicon", signal_version="A", run_id="RUN_A"),
            _source_row(group_type="layer", group_name="Compute silicon", signal_version="B", run_id="RUN_B"),
        ],
    )

    summary = load_ec_group_signal_daily_from_dc(source_db_path=str(source_db), target_db_path=str(target_db))

    assert summary["status"] == "FAILED"
    assert summary["loader_error_code"] == "SOURCE_SIGNAL_VERSION_AMBIGUOUS"
    assert "Multiple signal_version values" in summary["loader_error"]


def test_loader_blocks_duplicate_source_group_keys_before_insert(tmp_path) -> None:
    source_db = tmp_path / "source_duplicate_groups.db"
    target_db = _setup_target_db_with_versions(tmp_path, ("DC_TAXONOMY_FULL_V1",))
    row = _source_row(group_type="layer", group_name="Compute silicon")
    duplicate = {**row, "member_count": 99}
    _create_source_db_without_source_pk(source_db, [row, duplicate])

    summary = load_ec_group_signal_daily_from_dc(source_db_path=str(source_db), target_db_path=str(target_db))

    assert summary["status"] == "FAILED"
    assert summary["loader_error_code"] == "SOURCE_SCOPE_INVALID"
    assert summary["duplicate_source_group_count"] == 1
    assert summary["loaded_row_count"] == 0
    with _connect(str(target_db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ec_group_signal_daily").fetchone()[0] == 0


def test_loader_blocks_multiple_source_rows_mapping_to_same_entity_before_insert(tmp_path) -> None:
    source_db = tmp_path / "source_mapping_collision.db"
    target_db = _setup_target_db_with_versions(tmp_path, ("DC_TAXONOMY_FULL_V1",))
    _create_source_db(
        source_db,
        [
            _source_row(group_type="layer", group_name="Compute silicon"),
            _source_row(group_type="layer", group_name="COMPUTE_SILICON", run_id="RUN_ALIAS"),
        ],
    )

    summary = load_ec_group_signal_daily_from_dc(source_db_path=str(source_db), target_db_path=str(target_db))

    assert summary["status"] == "FAILED"
    assert summary["loader_error_code"] == "TARGET_KEY_INVALID"
    assert summary["mapped_row_count"] == 2
    assert summary["distinct_target_key_count"] == 1
    assert summary["duplicate_target_key_count"] == 1
    assert summary["multiple_source_to_same_target_count"] == 1
    with _connect(str(target_db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ec_group_signal_daily").fetchone()[0] == 0


def test_loader_rolls_back_group_transaction_on_sql_insert_failure(tmp_path, monkeypatch) -> None:
    source_db = tmp_path / "source_insert_failure.db"
    target_db = _setup_target_db_with_versions(tmp_path, ("DC_TAXONOMY_FULL_V1",))
    _create_source_db(
        source_db,
        [
            _source_row(group_type="layer", group_name="Compute silicon"),
            _source_row(group_type="subindustry", group_name="GPUs"),
        ],
    )
    from rawcandle import ec_group_signal_daily_loader as loader

    original_insert = loader._insert_target_row
    calls = {"count": 0}

    def fail_second_insert(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise sqlite3.IntegrityError("injected group insert failure")
        return original_insert(*args, **kwargs)

    monkeypatch.setattr(loader, "_insert_target_row", fail_second_insert)

    summary = load_ec_group_signal_daily_from_dc(source_db_path=str(source_db), target_db_path=str(target_db))

    assert summary["status"] == "FAILED"
    assert summary["loader_error_code"] == "SQL_INSERT_FAILED"
    assert "injected group insert failure" in summary["loader_error"]
    with _connect(str(target_db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ec_group_signal_daily").fetchone()[0] == 0


def _create_source_db_without_source_pk(path: Path, rows: list[dict[str, object]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                member_count INTEGER NULL,
                eligible_count INTEGER NULL,
                return_5d REAL NULL,
                return_10d REAL NULL,
                return_20d REAL NULL,
                return_60d REAL NULL,
                pct_above_ma10 REAL NULL,
                pct_above_ema20 REAL NULL,
                pct_above_rising_ema20 REAL NULL,
                ma10_breadth_delta_5d REAL NULL,
                ema20_breadth_delta_5d REAL NULL,
                trend_breadth REAL NULL,
                weakness_breadth REAL NULL,
                overheat_risk_level TEXT NULL,
                timing_state TEXT NULL,
                timing_reason TEXT NULL,
                data_quality_status TEXT NULL,
                signal_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            )
            """
        )
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO dc_group_swing_signal_daily ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()
