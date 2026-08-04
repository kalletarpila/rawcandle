from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

from rawcandle.datacenter_taxonomy_replacement import (
    apply_ec_taxonomy_replacement_cleanup,
    ensure_taxonomy_replacement_schema,
    finalize_ec_taxonomy_rebuild_validation,
    plan_ec_taxonomy_replacement_cleanup,
)


HEADER = [
    "taxonomy_version",
    "ticker",
    "layer",
    "subindustry",
    "report_group_status",
    "is_primary",
    "role_weight",
    "notes",
]


CANONICAL = (
    "ec_ticker_signal_daily",
    "ec_group_signal_daily",
    "ec_group_synthetic_ohlc_daily",
    "ec_group_index_daily",
)


def _write_taxonomy(path: Path) -> str:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerow(["DC_TAXONOMY_FULL_V2", "AAA", "Compute", "GPU", "CORE", 1, 1.0, ""])
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _db(tmp_path: Path) -> tuple[Path, Path]:
    taxonomy_csv = tmp_path / "taxonomy_v2.csv"
    source_hash = _write_taxonomy(taxonomy_csv)
    db_path = tmp_path / "analysis.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE ec_ecosystem (ecosystem_id INTEGER PRIMARY KEY, ecosystem_code TEXT, ecosystem_name TEXT, status TEXT)")
        conn.execute(
            """
            CREATE TABLE ec_taxonomy_version (
                taxonomy_version_id INTEGER PRIMARY KEY,
                ecosystem_id INTEGER,
                taxonomy_version_code TEXT,
                source_hash TEXT,
                source_reference TEXT,
                status TEXT,
                is_active INTEGER,
                active_from TEXT,
                active_to TEXT
            )
            """
        )
        conn.execute("CREATE TABLE ec_entity (entity_id INTEGER PRIMARY KEY, ecosystem_id INTEGER, entity_type TEXT, entity_code TEXT, ticker TEXT, status TEXT)")
        conn.execute("CREATE TABLE ec_membership (membership_id INTEGER PRIMARY KEY, ecosystem_id INTEGER, taxonomy_version_id INTEGER, parent_entity_id INTEGER, child_entity_id INTEGER, membership_type TEXT, status TEXT, is_primary INTEGER)")
        conn.execute("CREATE TABLE ec_pipeline_watermark (ecosystem_id INTEGER, pipeline_name TEXT, source_table TEXT, latest_signal_date TEXT, latest_run_id TEXT, status TEXT, created_at_utc TEXT, updated_at_utc TEXT, taxonomy_version_id INTEGER)")
        for table in CANONICAL:
            version_column = "signal_version"
            if table == "ec_group_synthetic_ohlc_daily":
                version_column = "ohlc_calc_version"
            elif table == "ec_group_index_daily":
                version_column = "calc_version"
            conn.execute(
                f"""
                CREATE TABLE {table} (
                    ecosystem_id INTEGER,
                    taxonomy_version_id INTEGER,
                    signal_date TEXT,
                    entity_id INTEGER,
                    {version_column} TEXT
                )
                """
            )
        ensure_taxonomy_replacement_schema(conn)
        conn.execute("INSERT INTO ec_ecosystem VALUES (1, 'DATACENTER', 'Datacenter', 'ACTIVE')")
        conn.execute("INSERT INTO ec_ecosystem VALUES (2, 'ENERGY', 'Energy', 'ACTIVE')")
        conn.execute("INSERT INTO ec_taxonomy_version VALUES (1, 1, 'DC_TAXONOMY_FULL_V1', 'v1hash', 'v1.csv', 'ACTIVE', 1, '2025-01-01', NULL)")
        conn.execute("INSERT INTO ec_taxonomy_version VALUES (2, 1, 'DC_TAXONOMY_FULL_V2', ?, 'v2.csv', 'INACTIVE', 0, NULL, NULL)", (source_hash,))
        conn.execute("INSERT INTO ec_entity VALUES (10, 1, 'GROUP_L1', 'COMPUTE', NULL, 'ACTIVE')")
        conn.execute("INSERT INTO ec_entity VALUES (11, 1, 'GROUP_L2', 'GPU', NULL, 'ACTIVE')")
        conn.execute("INSERT INTO ec_entity VALUES (100, 1, 'TICKER', 'AAA', 'AAA', 'ACTIVE')")
        conn.execute("INSERT INTO ec_membership VALUES (1, 1, 2, 11, 100, 'TICKER_TO_GROUP', 'ACTIVE', 1)")
        conn.execute(
            """
            INSERT INTO ec_taxonomy_change_deployment (
                taxonomy_change_id, ecosystem_code, previous_taxonomy_version,
                proposed_taxonomy_version, source_reference, source_sha256,
                change_summary, added_ticker_count, removed_ticker_count,
                membership_change_count, group_change_count, status,
                rebuild_required, rebuild_start_date, dc_rebuild_status,
                ec_rebuild_status, coverage_status, parity_status,
                activation_status, last_error
            ) VALUES (7, 'DATACENTER', 'DC_TAXONOMY_FULL_V1',
                      'DC_TAXONOMY_FULL_V2', 'v2.csv', ?, '{}',
                      0, 0, 0, 0, 'VALIDATION_REQUIRED', 1,
                      '2025-08-01', 'OK', 'FAILED', 'NOT_STARTED',
                      'NOT_STARTED', 'NOT_ACTIVE',
                      'stale rows block whole-range validation')
            """,
            (source_hash,),
        )
        _insert_fact_rows(conn)
        conn.commit()
    finally:
        conn.close()
    return db_path, taxonomy_csv


def _insert_fact_rows(conn: sqlite3.Connection) -> None:
    table_versions = {
        "ec_ticker_signal_daily": "signal_version",
        "ec_group_signal_daily": "signal_version",
        "ec_group_synthetic_ohlc_daily": "ohlc_calc_version",
        "ec_group_index_daily": "calc_version",
    }
    for table, version_column in table_versions.items():
        entity_id = 100 if table == "ec_ticker_signal_daily" else 11
        conn.execute(f"INSERT INTO {table} (ecosystem_id, taxonomy_version_id, signal_date, entity_id, {version_column}) VALUES (1, 1, '2026-07-30', ?, 'v1')", (entity_id,))
        conn.execute(f"INSERT INTO {table} (ecosystem_id, taxonomy_version_id, signal_date, entity_id, {version_column}) VALUES (1, 1, '2026-07-31', ?, 'v1')", (entity_id,))
        conn.execute(f"INSERT INTO {table} (ecosystem_id, taxonomy_version_id, signal_date, entity_id, {version_column}) VALUES (1, 2, '2025-08-01', ?, 'v2')", (entity_id,))
        conn.execute(f"INSERT INTO {table} (ecosystem_id, taxonomy_version_id, signal_date, entity_id, {version_column}) VALUES (1, 2, '2026-07-31', ?, 'v2')", (entity_id,))
        conn.execute(f"INSERT INTO {table} (ecosystem_id, taxonomy_version_id, signal_date, entity_id, {version_column}) VALUES (1, 1, '2026-08-01', ?, 'v1')", (entity_id,))
        conn.execute(f"INSERT INTO {table} (ecosystem_id, taxonomy_version_id, signal_date, entity_id, {version_column}) VALUES (2, 1, '2026-07-31', ?, 'v1')", (entity_id,))


def _counts(conn: sqlite3.Connection, table: str) -> tuple[int, int, int, int]:
    return (
        conn.execute(f"SELECT COUNT(*) FROM {table} WHERE ecosystem_id=1 AND taxonomy_version_id=1 AND signal_date BETWEEN '2025-08-01' AND '2026-07-31'").fetchone()[0],
        conn.execute(f"SELECT COUNT(*) FROM {table} WHERE ecosystem_id=1 AND taxonomy_version_id=2").fetchone()[0],
        conn.execute(f"SELECT COUNT(*) FROM {table} WHERE ecosystem_id=1 AND signal_date='2026-08-01'").fetchone()[0],
        conn.execute(f"SELECT COUNT(*) FROM {table} WHERE ecosystem_id=2").fetchone()[0],
    )


def test_cleanup_plan_finds_only_old_datacenter_rows_and_hash_is_deterministic(tmp_path: Path) -> None:
    db_path, _ = _db(tmp_path)

    first = plan_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
    )
    second = plan_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
    )

    assert first["cleanup_plan_status"] == "READY_TO_APPLY"
    assert first["delete_candidate_hash"] == second["delete_candidate_hash"]
    assert [table["delete_candidate_count"] for table in first["tables"]] == [2, 2, 2, 2]
    assert all(table["target_v2_row_count"] == 2 for table in first["tables"])
    assert all(table["old_version_taxonomy_ids"] == [1] for table in first["tables"])
    assert all(table["unexpected_other_ecosystem_rows"] == 0 for table in first["tables"])


def test_cleanup_apply_deletes_exact_scope_and_is_idempotent(tmp_path: Path) -> None:
    db_path, _ = _db(tmp_path)
    plan = plan_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
    )

    summary = apply_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
        confirm_db=db_path,
        confirm_ecosystem="DATACENTER",
        confirm_target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_deployment_id=7,
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_delete_candidate_hash=str(plan["delete_candidate_hash"]),
    )

    assert summary["cleanup_apply_status"] == "APPLIED"
    assert set(summary["deleted_counts"].values()) == {2}
    with sqlite3.connect(db_path) as conn:
        for table in CANONICAL:
            assert _counts(conn, table) == (0, 2, 1, 1)

    second_plan = plan_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
    )
    second = apply_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
        confirm_db=db_path,
        confirm_ecosystem="DATACENTER",
        confirm_target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_deployment_id=7,
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_delete_candidate_hash=str(second_plan["delete_candidate_hash"]),
    )
    assert second["cleanup_apply_status"] == "NO_CHANGE"


def test_cleanup_apply_blocks_hash_mismatch_and_active_v2(tmp_path: Path) -> None:
    db_path, _ = _db(tmp_path)
    blocked = apply_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
        confirm_db=db_path,
        confirm_ecosystem="DATACENTER",
        confirm_target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_deployment_id=7,
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_delete_candidate_hash="wrong",
    )
    assert blocked["cleanup_apply_status"] == "BLOCKED"
    assert "delete candidate hash mismatch" in blocked["blocking_errors"]

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE ec_taxonomy_version SET is_active=1, status='ACTIVE' WHERE taxonomy_version_id=2")
        conn.commit()
    active = plan_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
    )
    assert active["cleanup_plan_status"] == "BLOCKED"
    assert "target taxonomy is already active" in active["blocking_errors"]


def test_validation_only_blocks_until_cleanup_and_then_can_finalize_watermark_lineage(tmp_path: Path) -> None:
    db_path, taxonomy_csv = _db(tmp_path)
    for pipeline_name, source_table in (
        ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily"),
        ("GROUP_SWING_BASE", "dc_group_swing_signal_daily"),
        ("SYNTHETIC_OHLC_BASE", "dc_group_synthetic_ohlc_daily"),
        ("GROUP_INDEX", "dc_group_index_daily"),
        ("DAILY_REPORT", "UNKNOWN:DAILY_REPORT"),
    ):
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO ec_pipeline_watermark VALUES (1, ?, ?, '2026-07-31', NULL, 'OK', '2026-07-31T00:00:00Z', '2026-07-31T00:00:00Z', 1)",
                (pipeline_name, source_table),
            )
            conn.commit()

    blocked = finalize_ec_taxonomy_rebuild_validation(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        taxonomy_csv=taxonomy_csv,
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
        finalize_watermarks=False,
    )
    assert blocked["finalization_status"] == "BLOCKED"
    assert blocked["validation"]["loaders_rerun"] is False
    assert blocked["validation"]["chunks_rerun"] is False

    plan = plan_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
    )
    apply_ec_taxonomy_replacement_cleanup(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
        confirm_db=db_path,
        confirm_ecosystem="DATACENTER",
        confirm_target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_deployment_id=7,
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_delete_candidate_hash=str(plan["delete_candidate_hash"]),
    )

    ok = finalize_ec_taxonomy_rebuild_validation(
        db=db_path,
        ecosystem="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2",
        taxonomy_csv=taxonomy_csv,
        deployment_id=7,
        date_from="2025-08-01",
        date_to="2026-07-31",
        coverage_status="OK_WITH_WARNINGS",
        parity_status="OK_WITH_WARNINGS",
        total_mismatch_count=0,
        finalize_watermarks=True,
    )
    assert ok["finalization_status"] == "OK"
    assert ok["watermark_summary"]["watermark_rows_updated"] == 4
    assert ok["validation"]["whole_range_validation_status"] == "OK"
    with sqlite3.connect(db_path) as conn:
        canonical = conn.execute(
            "SELECT DISTINCT taxonomy_version_id FROM ec_pipeline_watermark WHERE source_table <> 'UNKNOWN:DAILY_REPORT'"
        ).fetchall()
        daily = conn.execute(
            "SELECT taxonomy_version_id FROM ec_pipeline_watermark WHERE source_table = 'UNKNOWN:DAILY_REPORT'"
        ).fetchone()
    assert canonical == [(2,)]
    assert daily == (1,)
