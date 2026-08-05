from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.datacenter_taxonomy_replacement import (
    DEFAULT_DATACENTER_REBUILD_START_DATE,
    TAXONOMY_REPLACEMENT_COMPONENTS,
    apply_datacenter_taxonomy_dc_rebuild_acceptance,
    apply_datacenter_taxonomy_rebuild_evidence,
    apply_datacenter_taxonomy_activation,
    apply_datacenter_taxonomy_version,
    ensure_taxonomy_replacement_schema,
    plan_datacenter_taxonomy_activation,
    plan_datacenter_taxonomy_change,
    prepare_datacenter_taxonomy_rebuild,
    validate_no_stale_taxonomy_rows,
)
from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_pipeline_watermark_loader import (
    advance_ec_pipeline_watermarks_after_historical_backfill,
)
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration
from rawcandle.scheduler.config import (
    DEFAULT_DATACENTER_TAXONOMY_CSV,
    DEFAULT_DATACENTER_TAXONOMY_VERSION,
    StockUpdateSchedulerConfig,
    scheduler_config_from_dict,
    write_scheduler_config,
    read_scheduler_config,
    validate_scheduler_config,
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


def _write_csv(path: Path, rows: list[list[object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def _base_rows(version: str = "DC_TAXONOMY_FULL_V1") -> list[list[object]]:
    return [
        [version, "AAA", "Compute", "GPU", "CORE", 1, 1.0, ""],
        [version, "BBB", "Power", "UPS", "EXTENDED", 1, 0.8, ""],
        [version, "BBB", "Compute", "GPU", "WATCH_ONLY", 0, 0.2, ""],
    ]


def _db_with_active_v1(tmp_path: Path, current_csv: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "analysis.db"
    apply_ec_sidecar_migration(str(db_path))
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(db_path),
        taxonomy_csv_path=str(current_csv),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )
    return db_path


def _plan(tmp_path: Path, proposed_rows: list[list[object]], proposed_version: str = "DC_TAXONOMY_FULL_V2") -> dict[str, object]:
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows())
    proposed_csv = _write_csv(tmp_path / "proposed.csv", proposed_rows)
    db_path = _db_with_active_v1(tmp_path, current_csv)
    return plan_datacenter_taxonomy_change(
        analysis_db=db_path,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version=proposed_version,
        proposed_taxonomy_csv=proposed_csv,
    )


def test_plan_allows_identical_content_under_new_version(tmp_path) -> None:
    rows = _base_rows("DC_TAXONOMY_FULL_V2")
    summary = _plan(tmp_path, rows)

    assert summary["taxonomy_plan_status"] == "READY_TO_LOAD"
    assert summary["requires_new_taxonomy_version"] is True
    assert summary["requires_full_historical_rebuild"] is True
    assert summary["rebuild_start_date"] == DEFAULT_DATACENTER_REBUILD_START_DATE
    assert summary["affected_ticker_count"] == 0
    assert summary["dc_watermark_reset_required"] is True
    assert summary["ec_watermark_scope"]["lineage_field"] == "taxonomy_version_id"


def test_plan_rejects_reuse_of_active_version_code(tmp_path) -> None:
    summary = _plan(tmp_path, _base_rows("DC_TAXONOMY_FULL_V1"), "DC_TAXONOMY_FULL_V1")

    assert summary["taxonomy_plan_status"] == "BLOCKED"
    assert "proposed version must differ from current active taxonomy version" in summary["blocking_errors"]


def test_plan_rejects_existing_loaded_version_with_different_hash(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows())
    first_v2 = _write_csv(tmp_path / "first_v2.csv", _base_rows("DC_TAXONOMY_FULL_V2"))
    second_v2 = _write_csv(
        tmp_path / "second_v2.csv",
        [[*row[:6], 0.9, row[7]] for row in _base_rows("DC_TAXONOMY_FULL_V2")],
    )
    db_path = _db_with_active_v1(tmp_path, current_csv)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(db_path),
        taxonomy_csv_path=str(first_v2),
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        mark_active=False,
    )

    summary = plan_datacenter_taxonomy_change(
        analysis_db=db_path,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=second_v2,
    )

    assert "proposed version already loaded with a different source hash" in summary["blocking_errors"]


def test_plan_detects_ticker_addition_and_removal(tmp_path) -> None:
    added = _plan(tmp_path, _base_rows("DC_TAXONOMY_FULL_V2") + [["DC_TAXONOMY_FULL_V2", "CCC", "Cloud", "Hyperscaler", "CORE", 1, 1.0, ""]])
    assert added["added_tickers"] == ["CCC"]
    assert added["affected_ticker_count"] == 1

    removed = _plan(tmp_path / "remove", [_base_rows("DC_TAXONOMY_FULL_V2")[0]])
    assert removed["removed_tickers"] == ["BBB"]


def test_plan_detects_primary_secondary_weight_status_and_group_changes(tmp_path) -> None:
    rows = [
        ["DC_TAXONOMY_FULL_V2", "AAA", "Power", "UPS", "CORE", 1, 0.7, ""],
        ["DC_TAXONOMY_FULL_V2", "BBB", "Power", "UPS", "WATCH_ONLY", 1, 0.6, ""],
        ["DC_TAXONOMY_FULL_V2", "BBB", "Networking", "Switching", "EXTENDED", 0, 0.4, ""],
    ]
    summary = _plan(tmp_path, rows)

    assert summary["moved_primary_memberships"][0]["ticker"] == "AAA"
    assert summary["changed_role_weights"]
    assert summary["changed_report_group_statuses"]
    assert summary["added_layers"] == ["Networking"]
    assert summary["added_subindustries"] == ["Switching"]
    assert summary["removed_subindustries"] == ["GPU"]
    assert summary["requires_full_historical_rebuild"] is True


def test_plan_rejects_invalid_hierarchy_duplicate_primary_and_invalid_csv(tmp_path) -> None:
    hierarchy = _plan(
        tmp_path / "hierarchy",
        [
            ["DC_TAXONOMY_FULL_V2", "AAA", "Compute", "Shared", "CORE", 1, 1.0, ""],
            ["DC_TAXONOMY_FULL_V2", "BBB", "Power", "Shared", "CORE", 1, 1.0, ""],
        ],
    )
    assert any("subindustry belongs to multiple layers" in error for error in hierarchy["blocking_errors"])

    duplicate = _plan(
        tmp_path / "duplicate",
        [
            ["DC_TAXONOMY_FULL_V2", "AAA", "Compute", "GPU", "CORE", 1, 1.0, ""],
            ["DC_TAXONOMY_FULL_V2", "AAA", "Power", "UPS", "CORE", 1, 1.0, ""],
        ],
    )
    assert any("duplicate primary membership" in error for error in duplicate["blocking_errors"])

    bad_weight = _plan(
        tmp_path / "bad_weight",
        [["DC_TAXONOMY_FULL_V2", "AAA", "Compute", "GPU", "CORE", 1, -1.0, ""]],
    )
    assert any("role_weight" in error for error in bad_weight["blocking_errors"])


def test_plan_output_is_deterministic(tmp_path) -> None:
    rows = _base_rows("DC_TAXONOMY_FULL_V2") + [["DC_TAXONOMY_FULL_V2", "CCC", "Cloud", "Hyperscaler", "CORE", 1, 1.0, ""]]
    first = _plan(tmp_path / "first", rows)
    second = _plan(tmp_path / "second", rows)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_apply_loads_new_immutable_metadata_not_active_and_records_rebuild_state(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows())
    proposed_csv = _write_csv(tmp_path / "proposed.csv", _base_rows("DC_TAXONOMY_FULL_V2"))
    db_path = _db_with_active_v1(tmp_path, current_csv)

    summary = apply_datacenter_taxonomy_version(
        analysis_db=db_path,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )

    assert summary["taxonomy_apply_status"] == "LOADED_NOT_ACTIVE"
    assert summary["activation_status"] == "NOT_ACTIVE"
    assert summary["rebuild_required"] is True

    conn = sqlite3.connect(db_path)
    try:
        taxonomy = conn.execute(
            """
            SELECT status, is_active, source_hash
            FROM ec_taxonomy_version
            WHERE taxonomy_version_code = 'DC_TAXONOMY_FULL_V2'
            """
        ).fetchone()
        assert taxonomy[0:2] == ("INACTIVE", 0)
        assert taxonomy[2] == summary["source_sha256"]
        deployment = conn.execute(
            """
            SELECT status, rebuild_required, rebuild_start_date, activation_status
            FROM ec_taxonomy_change_deployment
            WHERE proposed_taxonomy_version = 'DC_TAXONOMY_FULL_V2'
            """
        ).fetchone()
        assert deployment == ("LOADED_NOT_ACTIVE", 1, DEFAULT_DATACENTER_REBUILD_START_DATE, "NOT_ACTIVE")
    finally:
        conn.close()


def test_apply_rejects_existing_version_and_rolls_back_on_transaction_failure(tmp_path, monkeypatch) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows())
    proposed_csv = _write_csv(tmp_path / "proposed.csv", _base_rows("DC_TAXONOMY_FULL_V2"))
    db_path = _db_with_active_v1(tmp_path, current_csv)

    apply_datacenter_taxonomy_version(
        analysis_db=db_path,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )
    blocked = apply_datacenter_taxonomy_version(
        analysis_db=db_path,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )
    assert blocked["taxonomy_apply_status"] == "BLOCKED"

    rollback_db = _db_with_active_v1(tmp_path / "rollback", current_csv)
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_replacement._verify_membership_parity",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced parity failure")),
    )
    with pytest.raises(RuntimeError, match="forced parity failure"):
        apply_datacenter_taxonomy_version(
            analysis_db=rollback_db,
            current_taxonomy_version="DC_TAXONOMY_FULL_V1",
            current_taxonomy_csv=current_csv,
            proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
            proposed_taxonomy_csv=proposed_csv,
            confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        )
    conn = sqlite3.connect(rollback_db)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM ec_taxonomy_version WHERE taxonomy_version_code = 'DC_TAXONOMY_FULL_V2'"
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_ec_watermark_lineage_is_recorded_and_scoped_to_ecosystem(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows())
    db_path = _db_with_active_v1(tmp_path, current_csv)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO ec_ecosystem (ecosystem_code, ecosystem_name, status) VALUES ('ENERGY', 'Energy', 'ACTIVE')")
        conn.commit()
    finally:
        conn.close()

    summary = advance_ec_pipeline_watermarks_after_historical_backfill(
        target_db_path=db_path,
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        latest_signal_date="2026-07-31",
    )

    assert summary["taxonomy_lineage_recorded"] is True
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT e.ecosystem_code, COUNT(*), MIN(w.taxonomy_version_id)
            FROM ec_pipeline_watermark w
            JOIN ec_ecosystem e ON e.ecosystem_id = w.ecosystem_id
            GROUP BY e.ecosystem_code
            """
        ).fetchall()
        assert rows == [("DATACENTER", 4, 1)]
    finally:
        conn.close()


def test_dc_rebuild_preparation_is_idempotent_and_does_not_inherit_v1_watermark(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows())
    proposed_csv = _write_csv(tmp_path / "proposed.csv", _base_rows("DC_TAXONOMY_FULL_V2"))
    db_path = _db_with_active_v1(tmp_path, current_csv)
    apply_datacenter_taxonomy_version(
        analysis_db=db_path,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_pipeline_watermark (
                component_name TEXT,
                taxonomy_version TEXT,
                market TEXT,
                signal_version TEXT,
                calc_version TEXT,
                start_date TEXT,
                end_date TEXT,
                row_count INTEGER,
                status TEXT,
                last_successful_run_id TEXT,
                last_successful_at_utc TEXT,
                notes TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO dc_pipeline_watermark VALUES ('TICKER_SWING_BASE', 'DC_TAXONOMY_FULL_V1', 'usa', 'DC_SWING_SIGNAL_V1', '', '2025-08-01', '2026-07-31', 2, 'OK', NULL, NULL, NULL)"
        )
        conn.commit()
        deployment_id = conn.execute(
            "SELECT taxonomy_change_id FROM ec_taxonomy_change_deployment WHERE proposed_taxonomy_version='DC_TAXONOMY_FULL_V2'"
        ).fetchone()[0]
    finally:
        conn.close()

    first = prepare_datacenter_taxonomy_rebuild(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        deployment_id=deployment_id,
        expected_active_taxonomy_version="DC_TAXONOMY_FULL_V1",
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )
    second = prepare_datacenter_taxonomy_rebuild(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        deployment_id=deployment_id,
        expected_active_taxonomy_version="DC_TAXONOMY_FULL_V1",
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )

    assert first["prepare_status"] == "REBUILD_IN_PROGRESS"
    assert second["prepare_status"] == "REBUILD_IN_PROGRESS"
    assert first["previous_dc_watermark_count"] == 1
    assert first["proposed_dc_watermark_count"] == 0


def test_rebuild_evidence_blocks_manual_ok_when_facts_missing(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path, complete=False)
    summary = apply_datacenter_taxonomy_rebuild_evidence(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        deployment_id=1,
        required_signal_date="2026-07-31",
        coverage_status="OK",
        parity_status="OK",
        total_mismatch_count=0,
    )

    assert summary["status_update"] == "FAILED"
    assert summary["ready_to_activate"] is False
    assert "DC fact head incomplete for dc_ticker_swing_signal_daily" in summary["evidence"]["blocking_errors"]


def test_successful_rebuild_evidence_moves_deployment_ready_to_activate(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path, complete=True)
    cleanup_evidence = {
        "deployment_id": 1,
        "ecosystem_code": "DATACENTER",
        "target_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "target_taxonomy_version_id": 2,
        "date_from": "2025-08-01",
        "date_to": "2026-07-31",
        "status": "NO_CHANGE",
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE ec_taxonomy_change_deployment
            SET rebuild_evidence_json = ?,
                rebuild_evidence_sha256 = ?
            WHERE taxonomy_change_id = 1
            """,
            (json.dumps(cleanup_evidence, sort_keys=True), "cleanup-sha"),
        )
        conn.commit()
    summary = apply_datacenter_taxonomy_rebuild_evidence(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        deployment_id=1,
        required_signal_date="2026-07-31",
    )

    assert summary["status_update"] == "READY_TO_ACTIVATE"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT status, dc_rebuild_status, ec_rebuild_status, coverage_status,
                   parity_status, validation_evidence_sha256
            FROM ec_taxonomy_change_deployment
            WHERE taxonomy_change_id = 1
            """
        ).fetchone()
        assert row[:5] == ("READY_TO_ACTIVATE", "OK", "OK", "OK", "OK")
        assert row[5]
    finally:
        conn.close()


def _dc_acceptance_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    db_path, csv_path = _activation_db(tmp_path, complete=True)
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows("DC_TAXONOMY_FULL_V1"))
    config_path = tmp_path / "scheduler_config.json"
    write_scheduler_config(
        str(config_path),
        StockUpdateSchedulerConfig(
            enabled_markets=["usa"],
            osakedata_db_path=str(tmp_path / "osakedata.db"),
            analysis_db_path=str(db_path),
            log_dir=str(tmp_path / "logs"),
            datacenter_taxonomy_version="DC_TAXONOMY_FULL_V1",
            datacenter_taxonomy_csv=str(current_csv),
            ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ),
    )
    evidence_dir = tmp_path / "evidence"
    report_dir = evidence_dir / "dc_reports"
    log_dir = evidence_dir / "logs"
    report_dir.mkdir(parents=True)
    log_dir.mkdir(parents=True)
    for prefix in (
        "datacenter_daily",
        "datacenter_rolling_30",
        "datacenter_rolling_5",
        "datacenter_rolling_2",
    ):
        for suffix in ("md", "csv"):
            (report_dir / f"{prefix}_2026-07-31_1200_full.{suffix}").write_text(
                f"{prefix}-{suffix}",
                encoding="utf-8",
            )
    stage_names = [
        "Datacenter base index",
        "Ticker swing base snapshots",
        "Group swing base metrics",
        "Synthetic OHLC base",
        "Relative OHLC20",
        "Group structure / BOS / RESET",
        "Group timing states",
        "Group overheat risk",
        "Ticker scanners",
        "Pipeline audit",
        "Automatic technical relevance",
        "Daily report",
        "Rolling 30 report",
        "Rolling 5 report",
        "Rolling 2 report",
        "Windows report copy",
    ]
    (log_dir / "datacenter_v2_full_rebuild.stdout").write_text(
        "\n".join(f"=== Stage {index}/16: {name} ===" for index, name in enumerate(stage_names, start=1)),
        encoding="utf-8",
    )
    (log_dir / "datacenter_v2_full_rebuild.stderr").write_text(
        "ERROR [Errno 30] Read-only file system: '/mnt/d/swing_reports/report.md'\n",
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_pipeline_watermark (
                component_name TEXT,
                taxonomy_version TEXT,
                market TEXT,
                signal_version TEXT,
                calc_version TEXT,
                start_date TEXT,
                end_date TEXT,
                row_count INTEGER,
                status TEXT,
                last_successful_run_id TEXT,
                last_successful_at_utc TEXT,
                notes TEXT
            )
            """
        )
        conn.execute(
            """
            UPDATE ec_taxonomy_change_deployment
            SET status='REBUILD_IN_PROGRESS',
                dc_rebuild_status='IN_PROGRESS',
                ec_rebuild_status='NOT_STARTED',
                coverage_status='NOT_STARTED',
                parity_status='NOT_STARTED',
                activation_status='NOT_ACTIVE'
            WHERE taxonomy_change_id=1
            """
        )
        for component in TAXONOMY_REPLACEMENT_COMPONENTS:
            conn.execute(
                """
                INSERT INTO dc_pipeline_watermark (
                    component_name, taxonomy_version, market, signal_version, calc_version,
                    start_date, end_date, row_count, status, last_successful_run_id,
                    last_successful_at_utc, notes
                ) VALUES (?, 'DC_TAXONOMY_FULL_V2', '', 'DC_SWING_SIGNAL_V1', '',
                          '2025-08-01', '2026-07-31', NULL, 'OK', NULL,
                          '2026-08-03T10:40:00Z', NULL)
                """,
                (component,),
            )
        conn.commit()
    return db_path, csv_path, evidence_dir, config_path


def _apply_dc_acceptance(
    db_path: Path,
    csv_path: Path,
    evidence_dir: Path,
    config_path: Path,
    **overrides: object,
) -> dict[str, object]:
    params = {
        "analysis_db": db_path,
        "ecosystem_code": "DATACENTER",
        "proposed_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "proposed_taxonomy_csv": csv_path,
        "deployment_id": 1,
        "required_start_date": "2025-08-01",
        "required_signal_date": "2026-07-31",
        "evidence_dir": evidence_dir,
        "scheduler_config": config_path,
        "expected_scheduler_taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "expected_ticker_rows": 1,
        "expected_group_rows": 1,
        "expected_synthetic_rows": 1,
        "expected_index_rows": 1,
        "windows_copy_status": "FAILED_OPTIONAL",
        "windows_copy_required": False,
    }
    params.update(overrides)
    return apply_datacenter_taxonomy_dc_rebuild_acceptance(**params)


def test_dc_rebuild_acceptance_records_optional_copy_failure_without_ready_to_activate(tmp_path) -> None:
    db_path, csv_path, evidence_dir, config_path = _dc_acceptance_fixture(tmp_path)

    summary = _apply_dc_acceptance(db_path, csv_path, evidence_dir, config_path)

    assert summary["status_update"] == "VALIDATION_REQUIRED"
    assert summary["dc_rebuild_accepted"] is True
    evidence = summary["evidence"]
    assert evidence["dc_rebuild_acceptance_status"] == "ACCEPTED"
    assert evidence["dc_rebuild_windows_copy_status"] == "FAILED_OPTIONAL"
    assert evidence["dc_rebuild_windows_copy_required"] is False
    assert evidence["dc_rebuild_accepted_with_noncanonical_warning"] is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status, dc_rebuild_status, ec_rebuild_status, coverage_status,
                   parity_status, activation_status, validation_evidence_sha256
            FROM ec_taxonomy_change_deployment
            WHERE taxonomy_change_id = 1
            """
        ).fetchone()
        assert row[:6] == (
            "VALIDATION_REQUIRED",
            "OK",
            "NOT_STARTED",
            "NOT_STARTED",
            "NOT_STARTED",
            "NOT_ACTIVE",
        )
        assert row[6]
        versions = conn.execute(
            "SELECT taxonomy_version_code, is_active FROM ec_taxonomy_version ORDER BY taxonomy_version_code"
        ).fetchall()
        assert versions == [("DC_TAXONOMY_FULL_V1", 1), ("DC_TAXONOMY_FULL_V2", 0)]


def test_dc_rebuild_acceptance_refuses_missing_canonical_head(tmp_path) -> None:
    db_path, csv_path, evidence_dir, config_path = _dc_acceptance_fixture(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM dc_ticker_swing_signal_daily")
        conn.commit()

    summary = _apply_dc_acceptance(db_path, csv_path, evidence_dir, config_path)

    assert summary["status_update"] == "BLOCKED"
    assert "DC fact coverage incomplete for dc_ticker_swing_signal_daily" in summary["evidence"]["blocking_errors"]


def test_dc_rebuild_acceptance_refuses_missing_watermark(tmp_path) -> None:
    db_path, csv_path, evidence_dir, config_path = _dc_acceptance_fixture(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM dc_pipeline_watermark WHERE component_name='TICKER_SWING_BASE'")
        conn.commit()

    summary = _apply_dc_acceptance(db_path, csv_path, evidence_dir, config_path)

    assert summary["status_update"] == "BLOCKED"
    assert "required DC watermark coverage is incomplete" in summary["evidence"]["blocking_errors"]


def test_dc_rebuild_acceptance_refuses_failed_stage15(tmp_path) -> None:
    db_path, csv_path, evidence_dir, config_path = _dc_acceptance_fixture(tmp_path)
    stdout_path = evidence_dir / "logs" / "datacenter_v2_full_rebuild.stdout"
    stdout_path.write_text(stdout_path.read_text(encoding="utf-8").replace("=== Stage 15/16: Rolling 2 report ===", ""), encoding="utf-8")

    summary = _apply_dc_acceptance(db_path, csv_path, evidence_dir, config_path)

    assert summary["status_update"] == "BLOCKED"
    assert "Stage 1-15 success and optional copy-only failure evidence is incomplete" in summary["evidence"]["blocking_errors"]


def test_dc_rebuild_acceptance_refuses_missing_report_artifact(tmp_path) -> None:
    db_path, csv_path, evidence_dir, config_path = _dc_acceptance_fixture(tmp_path)
    next((evidence_dir / "dc_reports").glob("datacenter_rolling_5_*.csv")).unlink()

    summary = _apply_dc_acceptance(db_path, csv_path, evidence_dir, config_path)

    assert summary["status_update"] == "BLOCKED"
    assert "required generated report artifacts are missing" in summary["evidence"]["blocking_errors"]


def test_dc_rebuild_acceptance_refuses_required_copy_failure(tmp_path) -> None:
    db_path, csv_path, evidence_dir, config_path = _dc_acceptance_fixture(tmp_path)

    summary = _apply_dc_acceptance(
        db_path,
        csv_path,
        evidence_dir,
        config_path,
        windows_copy_required=True,
    )

    assert summary["status_update"] == "BLOCKED"
    assert "Windows report copy was required" in summary["evidence"]["blocking_errors"]


def test_dc_rebuild_acceptance_is_idempotent(tmp_path) -> None:
    db_path, csv_path, evidence_dir, config_path = _dc_acceptance_fixture(tmp_path)

    first = _apply_dc_acceptance(db_path, csv_path, evidence_dir, config_path)
    second = _apply_dc_acceptance(db_path, csv_path, evidence_dir, config_path)

    assert first["status_update"] == "VALIDATION_REQUIRED"
    assert second["status_update"] == "VALIDATION_REQUIRED"


def _activation_db(tmp_path: Path, *, complete: bool = True, wrong_lineage: bool = False) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "activation.db"
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
        conn.execute("CREATE TABLE ec_pipeline_watermark (ecosystem_id INTEGER, pipeline_name TEXT, source_table TEXT, latest_signal_date TEXT, status TEXT, taxonomy_version_id INTEGER)")
        ensure_taxonomy_replacement_schema(conn)
        conn.execute("INSERT INTO ec_ecosystem VALUES (1, 'DATACENTER', 'Datacenter', 'ACTIVE')")
        csv_path = _write_csv(tmp_path / "proposed.csv", _base_rows("DC_TAXONOMY_FULL_V2"))
        import hashlib

        source_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        conn.execute("INSERT INTO ec_taxonomy_version VALUES (1, 1, 'DC_TAXONOMY_FULL_V1', '', '', 'ACTIVE', 1, '2026-01-01', NULL)")
        conn.execute("INSERT INTO ec_taxonomy_version VALUES (2, 1, 'DC_TAXONOMY_FULL_V2', ?, ?, 'INACTIVE', 0, NULL, NULL)", (source_hash, str(csv_path)))
        for table, date_col in [
            ("dc_ticker_swing_signal_daily", "signal_date"),
            ("dc_group_swing_signal_daily", "signal_date"),
            ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
            ("dc_group_index_daily", "index_date"),
        ]:
            conn.execute(f"CREATE TABLE {table} ({date_col} TEXT, taxonomy_version TEXT)")
            if complete:
                conn.execute(f"INSERT INTO {table} VALUES ('2026-07-31', 'DC_TAXONOMY_FULL_V2')")
        for table in [
            "ec_ticker_signal_daily",
            "ec_group_signal_daily",
            "ec_group_synthetic_ohlc_daily",
            "ec_group_index_daily",
        ]:
            conn.execute(f"CREATE TABLE {table} (signal_date TEXT, taxonomy_version_id INTEGER)")
            if complete:
                conn.execute(f"INSERT INTO {table} VALUES ('2026-07-31', 2)")
        conn.execute(
            """
            INSERT INTO ec_taxonomy_change_deployment (
                ecosystem_code, previous_taxonomy_version, proposed_taxonomy_version,
                source_reference, source_sha256, change_summary, added_ticker_count,
                removed_ticker_count, membership_change_count, group_change_count,
                status, rebuild_required, rebuild_start_date, dc_rebuild_status,
                ec_rebuild_status, coverage_status, parity_status, activation_status
            ) VALUES ('DATACENTER', 'DC_TAXONOMY_FULL_V1', 'DC_TAXONOMY_FULL_V2',
                      ?, ?, '{}', 0, 0, 0, 0, 'READY_TO_ACTIVATE', 1,
                      '2025-08-01', ?, ?, ?, ?, 'NOT_ACTIVE')
            """,
            (
                str(csv_path),
                source_hash,
                "OK" if complete else "NOT_STARTED",
                "OK" if complete else "NOT_STARTED",
                "OK" if complete else "NOT_STARTED",
                "OK" if complete else "NOT_STARTED",
            ),
        )
        lineage = 1 if wrong_lineage else 2
        conn.executemany(
            "INSERT INTO ec_pipeline_watermark VALUES (1, ?, ?, '2026-07-31', 'OK', ?)",
            [
                ('TICKER_SWING_BASE', 'dc_ticker_swing_signal_daily', lineage),
                ('GROUP_SWING_BASE', 'dc_group_swing_signal_daily', lineage),
                ('SYNTHETIC_OHLC_BASE', 'dc_group_synthetic_ohlc_daily', lineage),
                ('GROUP_INDEX', 'dc_group_index_daily', lineage),
            ],
        )
        conn.commit()
        return db_path, csv_path
    finally:
        conn.close()


def _write_activation_scheduler_config(
    tmp_path: Path,
    *,
    config_path: Path,
    current_csv: Path,
    datacenter_version: str = "DC_TAXONOMY_FULL_V1",
    ec_version: str = "DC_TAXONOMY_FULL_V1",
    datacenter_csv: Path | None = None,
    ec_csv: Path | None = None,
) -> None:
    watchlist_path = tmp_path / "watchlist.txt"
    watchlist_path.write_text("AAA\n", encoding="utf-8")
    write_scheduler_config(
        str(config_path),
        StockUpdateSchedulerConfig(
            enabled_markets=["usa"],
            osakedata_db_path="/tmp/osakedata.db",
            analysis_db_path="/tmp/analysis.db",
            log_dir="/tmp/logs",
            datacenter_taxonomy_csv=str(datacenter_csv or current_csv),
            datacenter_taxonomy_version=datacenter_version,
            ec_source_layer_enabled=True,
            ec_source_layer_ecosystem="DATACENTER",
            ec_source_layer_taxonomy_csv=str(ec_csv or current_csv),
            ec_source_layer_taxonomy_version=ec_version,
            ec_source_layer_watchlist=str(watchlist_path),
            ec_source_layer_backup_dir=str(tmp_path),
        ),
    )


def test_activation_refuses_incomplete_rebuild_and_wrong_watermark_lineage(tmp_path) -> None:
    incomplete_db, csv_path = _activation_db(tmp_path / "incomplete", complete=False)
    incomplete = plan_datacenter_taxonomy_activation(
        analysis_db=incomplete_db,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
    )
    assert incomplete["activation_plan_status"] == "BLOCKED"
    assert "full DC rebuild is incomplete" in incomplete["blocking_errors"]

    lineage_db, lineage_csv = _activation_db(tmp_path / "lineage", wrong_lineage=True)
    lineage = plan_datacenter_taxonomy_activation(
        analysis_db=lineage_db,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=lineage_csv,
        required_signal_date="2026-07-31",
    )
    assert "EC watermark lineage does not belong to proposed taxonomy" in lineage["blocking_errors"]


def test_activation_accepts_complete_isolated_evidence(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path, complete=True)

    summary = plan_datacenter_taxonomy_activation(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
        expected_scheduler_taxonomy_version="DC_TAXONOMY_FULL_V2",
        expected_scheduler_taxonomy_csv=csv_path,
    )

    assert summary["activation_plan_status"] == "READY_TO_ACTIVATE"
    assert summary["safe_to_activate"] is True


def test_activation_plan_accepts_current_v1_scheduler_and_builds_v2_transition(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path / "db", complete=True)
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows("DC_TAXONOMY_FULL_V1"))
    config_path = tmp_path / "scheduler_config.json"
    _write_activation_scheduler_config(
        tmp_path,
        config_path=config_path,
        current_csv=current_csv,
    )

    summary = plan_datacenter_taxonomy_activation(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        deployment_id=1,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
        scheduler_config_path=config_path,
    )
    loaded = read_scheduler_config(str(config_path))

    assert summary["activation_plan_status"] == "READY_TO_ACTIVATE"
    assert summary["safe_to_activate"] is True
    assert summary["blocking_errors"] == []
    assert summary["current_db_taxonomy_status"] == "EXPECTED_CURRENT"
    assert summary["current_scheduler_taxonomy_status"] == "EXPECTED_CURRENT_V1"
    assert summary["current_scheduler_datacenter_version"] == "DC_TAXONOMY_FULL_V1"
    assert summary["current_scheduler_ec_version"] == "DC_TAXONOMY_FULL_V1"
    assert summary["current_scheduler_config_safe_to_transition"] is True
    assert summary["proposed_scheduler_taxonomy_status"] == "VALID"
    assert summary["proposed_scheduler_config_safe"] is True
    assert summary["config_transition_required"] is True
    assert summary["scheduler_changed_keys"] == [
        "datacenter_taxonomy_csv",
        "datacenter_taxonomy_version",
        "ec_source_layer_taxonomy_csv",
        "ec_source_layer_taxonomy_version",
    ]
    assert summary["scheduler_unexpected_changed_keys"] == []
    assert loaded.datacenter_taxonomy_version == "DC_TAXONOMY_FULL_V1"
    assert loaded.ec_source_layer_taxonomy_version == "DC_TAXONOMY_FULL_V1"


def test_activation_plan_blocks_scheduler_mismatch_and_partial_transition(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path / "db", complete=True)
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows("DC_TAXONOMY_FULL_V1"))
    config_path = tmp_path / "scheduler_config.json"
    _write_activation_scheduler_config(
        tmp_path,
        config_path=config_path,
        current_csv=current_csv,
        datacenter_version="DC_TAXONOMY_FULL_V1",
        ec_version="DC_TAXONOMY_FULL_V2",
        ec_csv=csv_path,
    )

    summary = plan_datacenter_taxonomy_activation(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
        scheduler_config_path=config_path,
    )

    assert summary["activation_plan_status"] == "BLOCKED"
    assert "scheduler Datacenter and EC taxonomy versions disagree" in summary["blocking_errors"]
    assert "scheduler taxonomy configuration is partially transitioned or mixed" in summary["blocking_errors"]


def test_activation_plan_blocks_db_config_mixed_states(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path / "db", complete=True)
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows("DC_TAXONOMY_FULL_V1"))
    config_path = tmp_path / "scheduler_config.json"
    _write_activation_scheduler_config(
        tmp_path,
        config_path=config_path,
        current_csv=current_csv,
        datacenter_version="DC_TAXONOMY_FULL_V2",
        ec_version="DC_TAXONOMY_FULL_V2",
        datacenter_csv=csv_path,
        ec_csv=csv_path,
    )

    summary = plan_datacenter_taxonomy_activation(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
        scheduler_config_path=config_path,
    )

    assert summary["activation_plan_status"] == "BLOCKED"
    assert (
        "mixed state blocks activation: DB current taxonomy with scheduler proposed taxonomy"
        in summary["blocking_errors"]
    )


def test_activation_apply_marks_new_taxonomy_active_after_complete_evidence(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path, complete=True)

    summary = apply_datacenter_taxonomy_activation(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
        confirm_activate_taxonomy_version="DC_TAXONOMY_FULL_V2",
        expected_scheduler_taxonomy_version="DC_TAXONOMY_FULL_V2",
        expected_scheduler_taxonomy_csv=csv_path,
    )

    assert summary["activation_apply_status"] == "ACTIVE"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT taxonomy_version_code, status, is_active
            FROM ec_taxonomy_version
            ORDER BY taxonomy_version_code
            """
        ).fetchall()
        assert rows == [
            ("DC_TAXONOMY_FULL_V1", "INACTIVE", 0),
            ("DC_TAXONOMY_FULL_V2", "ACTIVE", 1),
        ]
        deployment = conn.execute(
            """
            SELECT status, activation_status
            FROM ec_taxonomy_change_deployment
            WHERE proposed_taxonomy_version = 'DC_TAXONOMY_FULL_V2'
            """
        ).fetchone()
        assert deployment == ("ACTIVE", "ACTIVE")
    finally:
        conn.close()


def test_activation_updates_scheduler_config_and_creates_backup(tmp_path) -> None:
    db_path, csv_path = _activation_db(tmp_path / "db", complete=True)
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows("DC_TAXONOMY_FULL_V1"))
    config_path = tmp_path / "scheduler_config.json"
    write_scheduler_config(
        str(config_path),
        StockUpdateSchedulerConfig(
            enabled_markets=["usa"],
            osakedata_db_path="/tmp/osakedata.db",
            analysis_db_path="/tmp/analysis.db",
            log_dir="/tmp/logs",
            datacenter_taxonomy_csv=str(current_csv),
            datacenter_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_enabled=True,
            ec_source_layer_ecosystem="DATACENTER",
            ec_source_layer_taxonomy_csv=str(current_csv),
            ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_watchlist=str(tmp_path / "watchlist.txt"),
            ec_source_layer_backup_dir=str(tmp_path),
        ),
    )
    (tmp_path / "watchlist.txt").write_text("AAA\n", encoding="utf-8")

    summary = apply_datacenter_taxonomy_activation(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
        confirm_activate_taxonomy_version="DC_TAXONOMY_FULL_V2",
        expected_scheduler_taxonomy_version="DC_TAXONOMY_FULL_V2",
        expected_scheduler_taxonomy_csv=csv_path,
        scheduler_config_path=config_path,
        expected_current_scheduler_taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_current_scheduler_taxonomy_csv=current_csv,
        target_scheduler_taxonomy_csv=csv_path,
        config_backup_dir=tmp_path / "backups",
    )

    loaded = read_scheduler_config(str(config_path))
    assert summary["activation_apply_status"] == "ACTIVE"
    assert summary["config_activation"]["config_update_status"] == "OK"
    assert Path(summary["config_activation"]["config_backup_path"]).exists()
    assert loaded.datacenter_taxonomy_version == "DC_TAXONOMY_FULL_V2"
    assert loaded.ec_source_layer_taxonomy_version == "DC_TAXONOMY_FULL_V2"


def test_activation_rolls_back_db_if_config_write_fails(tmp_path, monkeypatch) -> None:
    db_path, csv_path = _activation_db(tmp_path / "db", complete=True)
    current_csv = _write_csv(tmp_path / "current.csv", _base_rows("DC_TAXONOMY_FULL_V1"))
    config_path = tmp_path / "scheduler_config.json"
    watchlist_path = tmp_path / "watchlist.txt"
    watchlist_path.write_text("AAA\n", encoding="utf-8")
    write_scheduler_config(
        str(config_path),
        StockUpdateSchedulerConfig(
            enabled_markets=["usa"],
            osakedata_db_path="/tmp/osakedata.db",
            analysis_db_path="/tmp/analysis.db",
            log_dir="/tmp/logs",
            datacenter_taxonomy_csv=str(current_csv),
            datacenter_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_enabled=True,
            ec_source_layer_ecosystem="DATACENTER",
            ec_source_layer_taxonomy_csv=str(current_csv),
            ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_watchlist=str(watchlist_path),
            ec_source_layer_backup_dir=str(tmp_path),
        ),
    )

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("config write failed")

    monkeypatch.setattr("rawcandle.scheduler.config.write_scheduler_config", fail_write)
    summary = apply_datacenter_taxonomy_activation(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=csv_path,
        required_signal_date="2026-07-31",
        confirm_activate_taxonomy_version="DC_TAXONOMY_FULL_V2",
        expected_scheduler_taxonomy_version="DC_TAXONOMY_FULL_V2",
        expected_scheduler_taxonomy_csv=csv_path,
        scheduler_config_path=config_path,
        expected_current_scheduler_taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_current_scheduler_taxonomy_csv=current_csv,
        target_scheduler_taxonomy_csv=csv_path,
        config_backup_dir=tmp_path / "backups",
    )

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT taxonomy_version_code, status, is_active FROM ec_taxonomy_version ORDER BY taxonomy_version_code"
        ).fetchall()
        deployment = conn.execute(
            "SELECT status, activation_status FROM ec_taxonomy_change_deployment WHERE taxonomy_change_id = 1"
        ).fetchone()
    finally:
        conn.close()
    loaded = read_scheduler_config(str(config_path))
    assert summary["activation_apply_status"] == "FAILED"
    assert summary["activation_rollback_attempted"] is True
    assert summary["activation_rollback_status"] == "CONFIG_RESTORED_DB_ROLLED_BACK"
    assert summary["activation_error"] == "config write failed"
    assert rows == [
        ("DC_TAXONOMY_FULL_V1", "ACTIVE", 1),
        ("DC_TAXONOMY_FULL_V2", "INACTIVE", 0),
    ]
    assert deployment == ("READY_TO_ACTIVATE", "NOT_ACTIVE")
    assert loaded.datacenter_taxonomy_version == "DC_TAXONOMY_FULL_V1"


def test_scheduler_defaults_and_validates_configured_taxonomy(tmp_path) -> None:
    default_config = scheduler_config_from_dict(
        {
            "enabled_markets": ["omxh"],
            "run_time": "05:30",
            "osakedata_db_path": "/tmp/osakedata.db",
            "analysis_db_path": "/tmp/analysis.db",
            "log_dir": "/tmp/logs",
        }
    )
    assert default_config.datacenter_taxonomy_csv == DEFAULT_DATACENTER_TAXONOMY_CSV
    assert default_config.datacenter_taxonomy_version == DEFAULT_DATACENTER_TAXONOMY_VERSION

    proposed_csv = _write_csv(tmp_path / "proposed.csv", _base_rows("DC_TAXONOMY_FULL_V2"))
    valid = validate_scheduler_config(
        StockUpdateSchedulerConfig(
            enabled_markets=["usa"],
            osakedata_db_path="/tmp/osakedata.db",
            analysis_db_path="/tmp/analysis.db",
            log_dir="/tmp/logs",
            datacenter_taxonomy_csv=str(proposed_csv),
            datacenter_taxonomy_version="DC_TAXONOMY_FULL_V2",
        )
    )
    assert valid.datacenter_taxonomy_version == "DC_TAXONOMY_FULL_V2"

    with pytest.raises(ValueError, match="does not match expected"):
        validate_scheduler_config(
            StockUpdateSchedulerConfig(
                enabled_markets=["usa"],
                osakedata_db_path="/tmp/osakedata.db",
                analysis_db_path="/tmp/analysis.db",
                log_dir="/tmp/logs",
                datacenter_taxonomy_csv=str(proposed_csv),
                datacenter_taxonomy_version="DC_TAXONOMY_FULL_V3",
            )
        )


def test_canonical_replacement_validation_rejects_stale_rows(tmp_path) -> None:
    db_path = tmp_path / "stale.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE ec_ecosystem (ecosystem_id INTEGER PRIMARY KEY, ecosystem_code TEXT)")
        conn.execute("CREATE TABLE ec_taxonomy_version (taxonomy_version_id INTEGER PRIMARY KEY, ecosystem_id INTEGER, taxonomy_version_code TEXT, source_hash TEXT, source_reference TEXT, status TEXT, is_active INTEGER)")
        conn.execute("INSERT INTO ec_ecosystem VALUES (1, 'DATACENTER')")
        conn.execute("INSERT INTO ec_taxonomy_version VALUES (1, 1, 'DC_TAXONOMY_FULL_V2', '', '', 'ACTIVE', 1)")
        for table, date_col in [
            ("dc_ticker_swing_signal_daily", "signal_date"),
            ("dc_group_swing_signal_daily", "signal_date"),
            ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
            ("dc_group_index_daily", "index_date"),
        ]:
            conn.execute(f"CREATE TABLE {table} ({date_col} TEXT, taxonomy_version TEXT)")
        conn.execute("INSERT INTO dc_ticker_swing_signal_daily VALUES ('2026-07-31', 'DC_TAXONOMY_FULL_V1')")
        conn.commit()
    finally:
        conn.close()

    summary = validate_no_stale_taxonomy_rows(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        active_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )

    assert summary["canonical_replacement_validation_status"] == "BLOCKED_STALE_ROWS"
    assert summary["stale_dc_rows"] == {"dc_ticker_swing_signal_daily": 1}
