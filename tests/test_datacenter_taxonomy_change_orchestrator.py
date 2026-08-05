from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    CHANGE_EXECUTION_REPORT_STATUS_ONLY,
    DC_REPAIR_SCOPE_ECOSYSTEM_AGGREGATE_ONLY,
    EC_RESUME_ACTION_REBUILD_EC_FACTS,
    EC_RESUME_ACTION_REVALIDATE_EXISTING_FACTS,
    REBUILD_MODE_AUTO,
    REBUILD_MODE_DELTA,
    REBUILD_MODE_FULL,
    TaxonomyChangeServices,
    build_production_taxonomy_change_services,
    build_taxonomy_change_plan,
    build_taxonomy_diff,
    classify_report_status_only_change,
    copy_delta_carry_forward,
    execute_taxonomy_rebuild,
    inspect_taxonomy_change,
    apply_dc_ecosystem_aggregate_repair,
    plan_ec_resume_action,
    plan_dc_ecosystem_aggregate_repair,
    plan_report_status_only_resume_reconciliation,
    prepare_taxonomy_change,
    revalidate_existing_ec_facts,
)
from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration
from rawcandle.scheduler.runner import write_scheduler_status
from rawcandle.scheduler.config import StockUpdateSchedulerConfig, write_scheduler_config


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


def _rows(version: str) -> list[list[object]]:
    return [
        [version, "AAA", "Compute", "GPU", "CORE", 1, 1.0, ""],
        [version, "BBB", "Power", "UPS", "EXTENDED", 1, 0.8, ""],
        [version, "BBB", "Compute", "GPU", "WATCH_ONLY", 0, 0.2, ""],
    ]


def _report_status_only_rows(version: str) -> list[list[object]]:
    rows = _rows(version)
    rows[1][4] = "CORE"
    rows[1][7] = "report status update"
    return rows


def _db(tmp_path: Path, current_csv: Path) -> Path:
    db_path = tmp_path / "analysis.db"
    apply_ec_sidecar_migration(str(db_path))
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=db_path,
        taxonomy_csv_path=current_csv,
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        mark_active=True,
    )
    return db_path


def _config(tmp_path: Path, current_csv: Path) -> Path:
    watchlist = tmp_path / "watchlist.txt"
    watchlist.write_text("AAA\n", encoding="utf-8")
    config_path = tmp_path / "scheduler_config.json"
    write_scheduler_config(
        str(config_path),
        StockUpdateSchedulerConfig(
            enabled_markets=["usa"],
            osakedata_db_path=str(tmp_path / "prices.db"),
            analysis_db_path=str(tmp_path / "analysis.db"),
            log_dir=str(tmp_path / "logs"),
            datacenter_taxonomy_csv=str(current_csv),
            datacenter_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_enabled=True,
            ec_source_layer_taxonomy_csv=str(current_csv),
            ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_watchlist=str(watchlist),
            ec_source_layer_backup_dir=str(tmp_path / "backups"),
        ),
    )
    return config_path


def _prepared(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(tmp_path / "proposed.csv", _rows("DC_TAXONOMY_FULL_V2"))
    db_path = _db(tmp_path, current_csv)
    config_path = _config(tmp_path, current_csv)
    summary = prepare_taxonomy_change(
        analysis_db=db_path,
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        watchlist_path=tmp_path / "watchlist.txt",
        evidence_root=tmp_path / "evidence",
    )
    return db_path, config_path, proposed_csv, summary


def test_taxonomy_diff_detects_added_removed_and_unchanged_tickers(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed = _rows("DC_TAXONOMY_FULL_V2")
    proposed.pop(1)
    proposed.append(["DC_TAXONOMY_FULL_V2", "CCC", "Compute", "GPU", "CORE", 1, 1.0, ""])
    proposed_csv = _write_csv(tmp_path / "proposed.csv", proposed)

    diff = build_taxonomy_diff(
        current_taxonomy_csv=current_csv,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        proposed_taxonomy_csv=proposed_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )

    assert diff["added_tickers"] == ["CCC"]
    assert diff["removed_tickers"] == []
    assert diff["unchanged_tickers"] == ["AAA", "BBB"]
    assert diff["secondary_membership_removals"] == []


def test_taxonomy_diff_detects_primary_secondary_and_scope_changes(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed = [
        ["DC_TAXONOMY_FULL_V2", "AAA", "Power", "UPS", "CORE", 1, 1.0, ""],
        ["DC_TAXONOMY_FULL_V2", "BBB", "Power", "UPS", "CORE", 1, 0.8, ""],
        ["DC_TAXONOMY_FULL_V2", "BBB", "Compute", "GPU", "WATCH_ONLY", 0, 0.2, ""],
        ["DC_TAXONOMY_FULL_V2", "AAA", "Compute", "GPU", "WATCH_ONLY", 0, 0.1, ""],
    ]
    proposed_csv = _write_csv(tmp_path / "proposed.csv", proposed)

    diff = build_taxonomy_diff(
        current_taxonomy_csv=current_csv,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        proposed_taxonomy_csv=proposed_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )

    assert diff["primary_membership_changes"][0]["ticker"] == "AAA"
    assert diff["secondary_membership_additions"] == [
        {"ticker": "AAA", "layer": "Compute", "subindustry": "GPU"}
    ]
    assert diff["scope_flag_changes"] == [
        {
            "ticker": "AAA",
            "layer": "Compute",
            "subindustry": "GPU",
            "from": "CORE",
            "to": "WATCH_ONLY",
        },
        {
            "ticker": "BBB",
            "layer": "Power",
            "subindustry": "UPS",
            "from": "EXTENDED",
            "to": "CORE",
        }
    ]


def test_taxonomy_diff_blocks_structural_changes(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed = _rows("DC_TAXONOMY_FULL_V2")
    proposed[0][2] = "NewLayer"
    proposed_csv = _write_csv(tmp_path / "proposed.csv", proposed)

    diff = build_taxonomy_diff(
        current_taxonomy_csv=current_csv,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        proposed_taxonomy_csv=proposed_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
    )

    assert diff["structural_change_detected"] is True
    assert diff["added_layers"] == ["NewLayer"]
    assert diff["structural_change_blocking_errors"]


def test_report_status_only_classifier_allows_only_reporting_and_notes(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )

    classification = classify_report_status_only_change(
        current_taxonomy_csv=current_csv,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        proposed_taxonomy_csv=proposed_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
    )

    assert classification["change_execution_class"] == CHANGE_EXECUTION_REPORT_STATUS_ONLY
    assert classification["report_status_only_safe"] is True
    assert classification["report_status_only_changed_fields"] == [
        "notes",
        "report_group_status",
        "taxonomy_version",
    ]
    assert classification["report_status_only_changed_row_count"] == 3
    assert classification["report_status_only_changed_ticker_count"] == 2
    assert classification["report_status_only_blocking_reasons"] == []


def test_report_status_only_classifier_blocks_computational_and_unknown_fields(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed = _rows("DC_TAXONOMY_FULL_V2_1")
    proposed[0][6] = 0.9
    proposed_csv = _write_csv(tmp_path / "proposed.csv", proposed)

    classification = classify_report_status_only_change(
        current_taxonomy_csv=current_csv,
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        proposed_taxonomy_csv=proposed_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
    )

    assert classification["report_status_only_safe"] is False
    assert classification["change_execution_class"] == REBUILD_MODE_DELTA
    assert "computational fields changed: role_weight" in classification["report_status_only_blocking_reasons"]


def test_plan_hash_is_deterministic_and_changes_with_inputs(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(tmp_path / "proposed.csv", _rows("DC_TAXONOMY_FULL_V2"))
    kwargs = {
        "deployment_id": 12,
        "ecosystem_code": "DATACENTER",
        "current_taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "current_taxonomy_csv": current_csv,
        "proposed_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "proposed_taxonomy_csv": proposed_csv,
        "date_from": "2025-08-01",
        "date_to": "2026-07-31",
        "rebuild_mode": REBUILD_MODE_FULL,
    }

    first = build_taxonomy_change_plan(**kwargs)
    second = build_taxonomy_change_plan(**kwargs)
    changed = build_taxonomy_change_plan(**{**kwargs, "date_to": "2026-08-31"})

    assert first["plan_hash"] == second["plan_hash"]
    assert first["plan_hash"] != changed["plan_hash"]


def test_auto_plan_selects_report_status_only_for_safe_metadata_change(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )

    auto = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2025-08-01",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_AUTO,
    )
    explicit_delta = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2025-08-01",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_DELTA,
    )

    assert auto["selected_rebuild_mode"] == REBUILD_MODE_DELTA
    assert auto["change_execution_class"] == CHANGE_EXECUTION_REPORT_STATUS_ONLY
    assert auto["report_status_only_safe"] is True
    assert auto["computational_rebuild_required"] is False
    assert auto["datacenter_pipeline_required"] is False
    assert auto["stage2_required"] is False
    assert explicit_delta["change_execution_class"] == CHANGE_EXECUTION_REPORT_STATUS_ONLY
    assert auto["plan_hash"] != explicit_delta["plan_hash"]


def test_delta_rebuild_is_supported_for_safe_monthly_change(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(tmp_path / "proposed.csv", _rows("DC_TAXONOMY_FULL_V2"))

    plan = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2025-08-01",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_DELTA,
    )

    assert plan["plan_status"] == "READY"
    assert plan["selected_rebuild_mode"] == REBUILD_MODE_DELTA
    assert plan["delta_rebuild_supported"] is True
    assert plan["delta_safe"] is True
    assert plan["blocking_errors"] == []


def test_auto_selects_delta_for_safe_change_and_full_for_structural_change(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(tmp_path / "proposed.csv", _rows("DC_TAXONOMY_FULL_V2"))
    safe = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2025-08-01",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_AUTO,
    )
    assert safe["selected_rebuild_mode"] == REBUILD_MODE_DELTA

    structural_rows = _rows("DC_TAXONOMY_FULL_V3")
    structural_rows[0][2] = "NewLayer"
    structural_csv = _write_csv(tmp_path / "structural.csv", structural_rows)
    structural = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V3",
        proposed_taxonomy_csv=structural_csv,
        date_from="2025-08-01",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_AUTO,
    )
    assert structural["selected_rebuild_mode"] == REBUILD_MODE_FULL
    assert structural["delta_safe"] is False
    assert structural["plan_status"] == "READY"


def test_explicit_delta_blocks_when_structural_change_is_unsafe(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed = _rows("DC_TAXONOMY_FULL_V2")
    proposed[0][3] = "NewSubindustry"
    proposed_csv = _write_csv(tmp_path / "proposed.csv", proposed)

    plan = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2025-08-01",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_DELTA,
    )

    assert plan["plan_status"] == "BLOCKED"
    assert plan["selected_rebuild_mode"] == REBUILD_MODE_DELTA
    assert plan["delta_safe"] is False


def test_prepare_creates_and_reuses_one_deployment(tmp_path) -> None:
    db_path, config_path, proposed_csv, first = _prepared(tmp_path)

    second = prepare_taxonomy_change(
        analysis_db=db_path,
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        watchlist_path=tmp_path / "watchlist.txt",
        evidence_root=tmp_path / "evidence",
    )

    assert first["prepare_status"] == "READY_TO_REBUILD"
    assert second["prepare_status"] == "READY_TO_REBUILD"
    assert second["deployment_id"] == first["deployment_id"]
    assert second["deployment_reused"] is True


def test_inspect_is_read_only_and_reports_safe_next_action(tmp_path) -> None:
    db_path, config_path, _proposed_csv, prepared = _prepared(tmp_path)

    summary = inspect_taxonomy_change(
        analysis_db=db_path,
        deployment_id=prepared["deployment_id"],
        scheduler_config_path=config_path,
    )

    assert summary["inspect_status"] == "OK"
    assert summary["normalized_orchestration_status"] == "PLANNED"
    assert summary["safe_next_action"] == "execute_rebuild"
    assert summary["per_phase_status"]["activation"] == "NOT_ACTIVE"


def test_run_blocks_without_injected_services_and_preserves_resume_fields(tmp_path) -> None:
    db_path, config_path, proposed_csv, prepared = _prepared(tmp_path)
    plan = prepared["plan"]

    summary = execute_taxonomy_rebuild(
        analysis_db=db_path,
        deployment_id=prepared["deployment_id"],
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        confirm_deployment_id=prepared["deployment_id"],
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_proposed_source_hash=plan["proposed_source_sha256"],
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_rebuild_mode=REBUILD_MODE_FULL,
        confirm_plan_hash=plan["plan_hash"],
    )

    assert summary["run_status"] == "FAILED"
    assert summary["failure_code"] == "EXECUTION_SERVICES_NOT_CONFIGURED"
    assert summary["current_taxonomy_remains_active"] is True
    assert summary["scheduler_guard_restored"] is True


def test_run_confirmation_mismatch_blocks_changed_plan(tmp_path) -> None:
    db_path, config_path, proposed_csv, prepared = _prepared(tmp_path)
    plan = prepared["plan"]

    summary = execute_taxonomy_rebuild(
        analysis_db=db_path,
        deployment_id=prepared["deployment_id"],
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        confirm_deployment_id=prepared["deployment_id"],
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_proposed_source_hash=plan["proposed_source_sha256"],
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-08-31",
        confirm_rebuild_mode=REBUILD_MODE_FULL,
        confirm_plan_hash=plan["plan_hash"],
    )

    assert summary["failure_code"] == "CONFIRMATION_FAILED"
    assert "confirmation mismatch: date_to" in summary["failure_message"]


def test_run_calls_injected_rebuild_services_in_order(tmp_path, monkeypatch) -> None:
    db_path, config_path, proposed_csv, prepared = _prepared(tmp_path)
    plan = prepared["plan"]
    calls: list[str] = []

    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.plan_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"safe_to_apply": True, "cleanup_plan_status": "READY_TO_APPLY", "delete_candidate_hash": "hash"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.apply_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"cleanup_apply_status": "NO_CHANGE"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.finalize_ec_taxonomy_rebuild_validation",
        lambda **_kwargs: {"finalization_status": "OK"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator._plan_activation",
        lambda **_kwargs: {"safe_to_activate": True, "activation_plan_status": "READY_TO_ACTIVATE"},
    )
    services = TaxonomyChangeServices(
        set_scheduler_guard=lambda **kwargs: calls.append(f"guard:{kwargs['enabled']}") or {"status": "OK"},
        verify_active_writer=lambda **_kwargs: calls.append("writer") or {"status": "NO_ACTIVE_WRITER"},
        ensure_backup=lambda **_kwargs: calls.append("backup") or {"status": "OK"},
        run_dc_rebuild=lambda **_kwargs: calls.append("dc") or {"status": "OK"},
        run_ec_rebuild=lambda **_kwargs: calls.append("ec") or {"status": "OK"},
    )

    summary = execute_taxonomy_rebuild(
        analysis_db=db_path,
        deployment_id=prepared["deployment_id"],
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        confirm_deployment_id=prepared["deployment_id"],
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_proposed_source_hash=plan["proposed_source_sha256"],
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_rebuild_mode=REBUILD_MODE_FULL,
        confirm_plan_hash=plan["plan_hash"],
        services=services,
    )

    assert summary["run_status"] == "READY_TO_ACTIVATE"
    assert summary["activation_executed"] is False
    assert calls == ["guard:True", "writer", "backup", "dc", "ec", "guard:False"]
    assert summary["completed_phases"].index("OLD_EC_CLEANED") < summary["completed_phases"].index("WHOLE_RANGE_VALIDATED")


def test_report_status_only_execution_skips_datacenter_rebuild(tmp_path, monkeypatch) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )
    db_path = _db(tmp_path, current_csv)
    config_path = _config(tmp_path, current_csv)
    prepared = prepare_taxonomy_change(
        analysis_db=db_path,
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        watchlist_path=tmp_path / "watchlist.txt",
        evidence_root=tmp_path / "evidence",
        rebuild_mode=REBUILD_MODE_AUTO,
    )
    plan = prepared["plan"]
    calls: list[str] = []

    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.plan_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"safe_to_apply": True, "cleanup_plan_status": "READY_TO_APPLY", "delete_candidate_hash": "hash"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.apply_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"cleanup_apply_status": "APPLIED"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.finalize_ec_taxonomy_rebuild_validation",
        lambda **_kwargs: {"finalization_status": "OK"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator._plan_activation",
        lambda **_kwargs: {"safe_to_activate": True, "activation_plan_status": "READY_TO_ACTIVATE"},
    )

    def fail_dc(**_kwargs):
        raise AssertionError("Datacenter rebuild must not run for REPORT_STATUS_ONLY")

    services = TaxonomyChangeServices(
        set_scheduler_guard=lambda **kwargs: calls.append(f"guard:{kwargs['enabled']}") or {"status": "OK"},
        verify_active_writer=lambda **_kwargs: calls.append("writer") or {"status": "NO_ACTIVE_WRITER"},
        ensure_backup=lambda **_kwargs: calls.append("backup") or {"status": "OK"},
        run_dc_rebuild=fail_dc,
        run_ec_rebuild=lambda **_kwargs: calls.append("ec") or {"status": "OK"},
    )

    summary = execute_taxonomy_rebuild(
        analysis_db=db_path,
        deployment_id=prepared["deployment_id"],
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        confirm_deployment_id=prepared["deployment_id"],
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        confirm_proposed_source_hash=plan["proposed_source_sha256"],
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_rebuild_mode=REBUILD_MODE_DELTA,
        confirm_plan_hash=plan["plan_hash"],
        services=services,
    )

    assert summary["run_status"] == "READY_TO_ACTIVATE"
    assert summary["change_execution_class"] == CHANGE_EXECUTION_REPORT_STATUS_ONLY
    assert summary["report_status_only_execution"] is True
    assert summary["dc_rebuild"]["dc_rebuild_skipped"] is True
    assert summary["datacenter_pipeline_called"] is False
    assert summary["stage2_called"] is False
    assert summary["external_fetch_called"] is False
    assert calls == ["guard:True", "writer", "backup", "ec", "guard:False"]
    assert "DC_REBUILD_SKIPPED_REPORT_STATUS_ONLY" in summary["completed_phases"]
    assert summary["completed_phases"].index("OLD_EC_CLEANED") < summary["completed_phases"].index("WHOLE_RANGE_VALIDATED")


def test_report_status_only_cleanup_failure_prevents_whole_range_validation(tmp_path, monkeypatch) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )
    db_path = _db(tmp_path, current_csv)
    config_path = _config(tmp_path, current_csv)
    prepared = prepare_taxonomy_change(
        analysis_db=db_path,
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        watchlist_path=tmp_path / "watchlist.txt",
        evidence_root=tmp_path / "evidence",
        rebuild_mode=REBUILD_MODE_AUTO,
    )
    plan = prepared["plan"]
    finalized = False

    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.plan_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"safe_to_apply": True, "cleanup_plan_status": "READY_TO_APPLY", "delete_candidate_hash": "hash"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.apply_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"cleanup_apply_status": "BLOCKED", "blocking_errors": ["simulated cleanup failure"]},
    )

    def fail_finalization(**_kwargs):
        nonlocal finalized
        finalized = True
        raise AssertionError("whole-range validation must not run after cleanup failure")

    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.finalize_ec_taxonomy_rebuild_validation",
        fail_finalization,
    )
    services = TaxonomyChangeServices(
        set_scheduler_guard=lambda **_kwargs: {"status": "OK"},
        verify_active_writer=lambda **_kwargs: {"status": "NO_ACTIVE_WRITER"},
        ensure_backup=lambda **_kwargs: {"status": "OK"},
        run_dc_rebuild=lambda **_kwargs: {"status": "OK"},
        run_ec_rebuild=lambda **_kwargs: {"status": "OK", "overall_status": "FACTS_CONSTRUCTED"},
    )

    summary = execute_taxonomy_rebuild(
        analysis_db=db_path,
        deployment_id=prepared["deployment_id"],
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        confirm_deployment_id=prepared["deployment_id"],
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        confirm_proposed_source_hash=plan["proposed_source_sha256"],
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_rebuild_mode=REBUILD_MODE_DELTA,
        confirm_plan_hash=plan["plan_hash"],
        services=services,
    )

    assert summary["run_status"] == "FAILED"
    assert summary["failed_phase"] == "OLD_EC_CLEANED"
    assert summary["resume_from_phase"] == "OLD_EC_CLEANED"
    assert finalized is False


def test_production_taxonomy_services_guard_backup_and_rebuild_runners(tmp_path) -> None:
    db_path, config_path, _proposed_csv, prepared = _prepared(tmp_path)
    config_before = StockUpdateSchedulerConfig(
        enabled_markets=["usa"],
        osakedata_db_path=str(tmp_path / "prices.db"),
        analysis_db_path=str(db_path),
        log_dir=str(tmp_path / "logs"),
        datacenter_taxonomy_csv=str(tmp_path / "current.csv"),
        datacenter_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=str(tmp_path / "current.csv"),
        ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_watchlist=str(tmp_path / "watchlist.txt"),
        ec_source_layer_backup_dir=str(tmp_path / "backups"),
        skip_next_run=False,
    )
    write_scheduler_config(str(config_path), config_before)
    dc_calls: list[dict[str, object]] = []
    ec_calls: list[dict[str, object]] = []

    def fake_dc_runner(**kwargs):
        dc_calls.append(kwargs)
        return {"summary": {"pipeline_status": "OK", "audit_validation_status": "OK"}}

    def fake_ec_runner(**kwargs):
        ec_calls.append(kwargs)
        return {
            "overall_status": "REBUILD_COMPLETED",
            "retry_required": False,
            "watermark_finalization_performed": True,
        }

    services = build_production_taxonomy_change_services(
        scheduler_config_path=config_path,
        evidence_root=tmp_path / "repo" / "temp" / "taxonomy",
        dc_pipeline_runner=fake_dc_runner,
        ec_rebuild_runner=fake_ec_runner,
    )
    assert services.set_scheduler_guard is not None
    assert services.verify_active_writer is not None
    assert services.ensure_backup is not None
    assert services.run_dc_rebuild is not None
    assert services.run_ec_rebuild is not None

    assert services.set_scheduler_guard(enabled=True)["skip_next_run"] is True
    assert services.verify_active_writer()["status"] == "NO_ACTIVE_WRITER"
    backup = services.ensure_backup(deployment_id=prepared["deployment_id"])
    assert backup["status"] == "OK"
    assert Path(str(backup["backup_path"])).exists()
    dc = services.run_dc_rebuild(plan=prepared["plan"])
    ec = services.run_ec_rebuild(plan=prepared["plan"])
    assert dc["status"] == "OK"
    assert ec["status"] == "OK"
    assert dc_calls[0]["skip_reports"] is True
    assert dc_calls[0]["windows_report_copy_enabled"] is False
    assert dc_calls[0]["stage2_incremental"] is False
    assert ec_calls[0]["existing_backup_path"] == backup["backup_path"]
    assert services.set_scheduler_guard(enabled=False)["skip_next_run"] is False


def test_production_services_skip_dc_runner_for_report_status_only_plan(tmp_path) -> None:
    db_path, config_path, _proposed_csv, _prepared_summary = _prepared(tmp_path)
    dc_calls: list[dict[str, object]] = []

    def fake_dc_runner(**kwargs):
        dc_calls.append(kwargs)
        return {"summary": {"pipeline_status": "OK"}}

    services = build_production_taxonomy_change_services(
        scheduler_config_path=config_path,
        evidence_root=tmp_path / "repo" / "temp" / "taxonomy",
        dc_pipeline_runner=fake_dc_runner,
    )
    assert services.run_dc_rebuild is not None
    skipped = services.run_dc_rebuild(
        plan={
            "change_execution_class": CHANGE_EXECUTION_REPORT_STATUS_ONLY,
            "deployment_id": 1,
            "proposed_source_reference": str(tmp_path / "proposed.csv"),
            "proposed_taxonomy_version": "DC_TAXONOMY_FULL_V2_1",
            "date_to": "2026-07-31",
            "date_from": "2025-08-01",
            "expected_counts": {},
        }
    )

    assert db_path.exists()
    assert skipped["status"] == "OK"
    assert skipped["dc_rebuild_skipped"] is True
    assert skipped["datacenter_pipeline_called"] is False
    assert skipped["stage2_called"] is False
    assert dc_calls == []


def test_production_taxonomy_services_block_active_scheduler_writer(tmp_path) -> None:
    _db_path, config_path, _proposed_csv, _prepared_summary = _prepared(tmp_path)
    write_scheduler_status(
        log_dir=str(tmp_path / "logs"),
        is_running=True,
        started_at_utc="2026-08-01T00:00:00Z",
        finished_at_utc=None,
        current_market="usa",
        last_status="RUNNING",
        summary_json_path=None,
        error=None,
    )
    services = build_production_taxonomy_change_services(
        scheduler_config_path=config_path,
        evidence_root=tmp_path / "repo" / "temp" / "taxonomy",
    )

    assert services.verify_active_writer is not None
    assert services.verify_active_writer()["status"] == "ACTIVE_WRITER"


def test_resume_production_services_reuse_existing_taxonomy_change_backup(tmp_path) -> None:
    db_path, config_path, _proposed_csv, prepared = _prepared(tmp_path)
    backup_dir = tmp_path / "backups" / "taxonomy_change_backups"
    backup_dir.mkdir(parents=True)
    existing_backup = backup_dir / (
        f"analysis_taxonomy_change_{prepared['deployment_id']}_20260805T000000Z.sqlite"
    )
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(existing_backup)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    services = build_production_taxonomy_change_services(
        scheduler_config_path=config_path,
        evidence_root=tmp_path / "repo" / "temp" / "taxonomy",
        resume=True,
    )

    backup = services.ensure_backup(deployment_id=prepared["deployment_id"])

    assert backup["status"] == "OK"
    assert backup["backup_reused"] is True
    assert backup["backup_path"] == str(existing_backup)
    assert backup["backup_mode"] == "EXISTING_SQLITE_BACKUP"
    assert backup["backup_validation_status"] == "OK"


def _create_carry_forward_fact_tables(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                primary_layer TEXT NOT NULL,
                primary_subindustry TEXT NOT NULL,
                close REAL,
                signal_version TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, ticker, signal_version)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                member_count INTEGER,
                signal_version TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, group_type, group_name, signal_version)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_synthetic_ohlc_daily (
                ohlc_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                close REAL,
                calc_version TEXT NOT NULL,
                PRIMARY KEY (ohlc_date, taxonomy_version, group_type, group_name, calc_version)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_index_daily (
                index_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                close REAL,
                PRIMARY KEY (index_date, taxonomy_version, group_type, group_name)
            )
            """
        )
        conn.execute(
            "INSERT INTO dc_ticker_swing_signal_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','AAA','Compute','GPU',100.0,'v1')"
        )
        conn.execute(
            "INSERT INTO dc_ticker_swing_signal_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','BBB','Power','UPS',50.0,'v1')"
        )
        for table, date_col, version_col in [
            ("dc_group_swing_signal_daily", "signal_date", "signal_version"),
            ("dc_group_synthetic_ohlc_daily", "ohlc_date", "calc_version"),
        ]:
            conn.execute(
                f"INSERT INTO {table} VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','layer','Power',2,'v1')"
            )
        conn.execute(
            "INSERT INTO dc_group_swing_signal_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','ecosystem','DC_ECOSYSTEM_TOTAL',2,'v1')"
        )
        conn.execute(
            "INSERT INTO dc_group_swing_signal_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','sentinel','BAD_SENTINEL',2,'v1')"
        )
        conn.execute(
            "INSERT INTO dc_group_index_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','layer','Power',10.0)"
        )
        conn.execute(
            "INSERT INTO dc_group_index_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','ecosystem','DC_ECOSYSTEM_TOTAL',10.0)"
        )
        conn.execute(
            "INSERT INTO dc_group_index_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','sentinel','BAD_SENTINEL',10.0)"
        )
        conn.commit()
    finally:
        conn.close()


def test_delta_carry_forward_copies_safe_rows_and_is_idempotent(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed = _rows("DC_TAXONOMY_FULL_V2")
    proposed[0][2] = "Power"
    proposed[0][3] = "UPS"
    proposed_csv = _write_csv(tmp_path / "proposed.csv", proposed)
    db_path = tmp_path / "facts.db"
    _create_carry_forward_fact_tables(db_path)
    plan = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2026-07-31",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_DELTA,
    )

    first = copy_delta_carry_forward(analysis_db=db_path, plan=plan)
    second = copy_delta_carry_forward(analysis_db=db_path, plan=plan)

    assert first["carry_forward_status"] == "OK"
    assert second["carry_forward_status"] == "OK"
    conn = sqlite3.connect(db_path)
    try:
        active_count = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V1'"
        ).fetchone()[0]
        proposed_rows = conn.execute(
            """
            SELECT ticker, primary_layer, primary_subindustry
            FROM dc_ticker_swing_signal_daily
            WHERE taxonomy_version='DC_TAXONOMY_FULL_V2'
            ORDER BY ticker
            """
        ).fetchall()
    finally:
        conn.close()
    assert active_count == 2
    assert proposed_rows == [("AAA", "Power", "UPS"), ("BBB", "Power", "UPS")]


def test_report_status_only_carry_forward_copies_complete_dc_slice(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )
    db_path = tmp_path / "facts.db"
    _create_carry_forward_fact_tables(db_path)
    plan = build_taxonomy_change_plan(
        deployment_id=None,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2026-07-31",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_AUTO,
    )

    result = copy_delta_carry_forward(analysis_db=db_path, plan=plan)

    assert plan["change_execution_class"] == CHANGE_EXECUTION_REPORT_STATUS_ONLY
    assert result["carry_forward_status"] == "OK"
    conn = sqlite3.connect(db_path)
    try:
        proposed_ticker_count = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'"
        ).fetchone()[0]
        proposed_group_rows = conn.execute(
            "SELECT COUNT(*) FROM dc_group_swing_signal_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'"
        ).fetchone()[0]
        proposed_index_rows = conn.execute(
            "SELECT group_type, group_name FROM dc_group_index_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1' ORDER BY group_type, group_name"
        ).fetchall()
    finally:
        conn.close()
    assert proposed_ticker_count == 2
    assert proposed_group_rows == 2
    assert proposed_index_rows == [("ecosystem", "DC_ECOSYSTEM_TOTAL"), ("layer", "Power")]


def test_report_status_only_aggregate_repair_copies_only_ecosystem_rows(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )
    db_path = tmp_path / "facts.db"
    _create_carry_forward_fact_tables(db_path)
    plan = build_taxonomy_change_plan(
        deployment_id=2,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2026-07-31",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_AUTO,
    )

    repair_plan = plan_dc_ecosystem_aggregate_repair(analysis_db=db_path, plan=plan)
    applied = apply_dc_ecosystem_aggregate_repair(
        analysis_db=db_path,
        plan=plan,
        confirm_dc_repair_scope=DC_REPAIR_SCOPE_ECOSYSTEM_AGGREGATE_ONLY,
        confirm_repair_candidate_hash=str(repair_plan["repair_candidate_hash"]),
    )
    second = apply_dc_ecosystem_aggregate_repair(
        analysis_db=db_path,
        plan=plan,
        confirm_dc_repair_scope=DC_REPAIR_SCOPE_ECOSYSTEM_AGGREGATE_ONLY,
        confirm_repair_candidate_hash=str(applied["post_repair_plan"]["repair_candidate_hash"]),
    )

    assert repair_plan["dc_repair_scope"] == DC_REPAIR_SCOPE_ECOSYSTEM_AGGREGATE_ONLY
    assert repair_plan["repair_candidate_count"] == 2
    assert repair_plan["ordinary_dc_recopy_required"] is False
    assert applied["dc_repair_apply_status"] == "APPLIED"
    assert second["dc_repair_apply_status"] == "NO_CHANGE"
    conn = sqlite3.connect(db_path)
    try:
        proposed_ticker_count = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'"
        ).fetchone()[0]
        proposed_synthetic_count = conn.execute(
            "SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'"
        ).fetchone()[0]
        proposed_group_rows = conn.execute(
            """
            SELECT group_type, group_name
            FROM dc_group_swing_signal_daily
            WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'
            ORDER BY group_type, group_name
            """
        ).fetchall()
        proposed_index_rows = conn.execute(
            """
            SELECT group_type, group_name
            FROM dc_group_index_daily
            WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'
            ORDER BY group_type, group_name
            """
        ).fetchall()
    finally:
        conn.close()
    assert proposed_ticker_count == 0
    assert proposed_synthetic_count == 0
    assert proposed_group_rows == [("ecosystem", "DC_ECOSYSTEM_TOTAL")]
    assert proposed_index_rows == [("ecosystem", "DC_ECOSYSTEM_TOTAL")]


def test_report_status_only_aggregate_repair_rolls_back_partial_failure(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )
    db_path = tmp_path / "facts.db"
    _create_carry_forward_fact_tables(db_path)
    plan = build_taxonomy_change_plan(
        deployment_id=2,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2026-07-31",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_AUTO,
    )
    repair_plan = plan_dc_ecosystem_aggregate_repair(analysis_db=db_path, plan=plan)

    failed = apply_dc_ecosystem_aggregate_repair(
        analysis_db=db_path,
        plan=plan,
        confirm_dc_repair_scope=DC_REPAIR_SCOPE_ECOSYSTEM_AGGREGATE_ONLY,
        confirm_repair_candidate_hash=str(repair_plan["repair_candidate_hash"]),
        inject_failure_after_table="dc_group_swing_signal_daily",
    )

    assert failed["dc_repair_apply_status"] == "FAILED"
    conn = sqlite3.connect(db_path)
    try:
        proposed_group_count = conn.execute(
            "SELECT COUNT(*) FROM dc_group_swing_signal_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'"
        ).fetchone()[0]
        proposed_index_count = conn.execute(
            "SELECT COUNT(*) FROM dc_group_index_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert proposed_group_count == 0
    assert proposed_index_count == 0


def test_report_status_only_reconciliation_requires_aggregate_only_amendment(tmp_path) -> None:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )
    db_path = tmp_path / "facts.db"
    _create_carry_forward_fact_tables(db_path)
    plan = build_taxonomy_change_plan(
        deployment_id=2,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2026-07-31",
        date_to="2026-07-31",
        rebuild_mode=REBUILD_MODE_AUTO,
    )

    reconciliation = plan_report_status_only_resume_reconciliation(
        analysis_db=db_path,
        plan=plan,
        original_plan_hash="old-plan-hash",
        current_plan_hash=str(plan["plan_hash"]),
        existing_backup_path=str(tmp_path / "backup.sqlite"),
        existing_backup_sha256="backup-sha",
    )

    assert reconciliation["plan_reconciliation_status"] == "SAFE_AMENDMENT_READY"
    assert reconciliation["original_plan_preserved"] is True
    assert reconciliation["repair_scope_narrower_or_equal"] is True
    assert reconciliation["safe_to_resume_after_amendment"] is True
    assert reconciliation["dc_repair_plan"]["dc_repair_scope"] == DC_REPAIR_SCOPE_ECOSYSTEM_AGGREGATE_ONLY
    assert reconciliation["dc_repair_plan"]["repair_candidate_count"] == 2


def _create_ec_revalidation_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    current_csv = _write_csv(tmp_path / "current.csv", _rows("DC_TAXONOMY_FULL_V1"))
    proposed_csv = _write_csv(
        tmp_path / "proposed.csv",
        _report_status_only_rows("DC_TAXONOMY_FULL_V2_1"),
    )
    db_path = tmp_path / "ec_revalidation.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE ec_ecosystem (
                ecosystem_id INTEGER PRIMARY KEY,
                ecosystem_code TEXT NOT NULL
            );
            CREATE TABLE ec_taxonomy_version (
                taxonomy_version_id INTEGER PRIMARY KEY,
                ecosystem_id INTEGER NOT NULL,
                taxonomy_version_code TEXT NOT NULL,
                source_hash TEXT,
                source_reference TEXT,
                status TEXT,
                is_active INTEGER
            );
            CREATE TABLE ec_taxonomy_change_deployment (
                taxonomy_change_id INTEGER PRIMARY KEY,
                ecosystem_code TEXT NOT NULL,
                previous_taxonomy_version TEXT NOT NULL,
                proposed_taxonomy_version TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                change_summary TEXT NOT NULL,
                added_ticker_count INTEGER NOT NULL,
                removed_ticker_count INTEGER NOT NULL,
                membership_change_count INTEGER NOT NULL,
                group_change_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                rebuild_required INTEGER NOT NULL,
                rebuild_start_date TEXT NOT NULL,
                dc_rebuild_status TEXT DEFAULT 'NOT_STARTED',
                ec_rebuild_status TEXT DEFAULT 'NOT_STARTED',
                coverage_status TEXT DEFAULT 'NOT_STARTED',
                parity_status TEXT DEFAULT 'NOT_STARTED',
                activation_status TEXT DEFAULT 'NOT_ACTIVE',
                rebuild_evidence_json TEXT,
                rebuild_evidence_sha256 TEXT,
                validation_evidence_json TEXT,
                validation_evidence_sha256 TEXT,
                last_error TEXT,
                updated_at_utc TEXT
            );
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT,
                taxonomy_version TEXT,
                ticker TEXT,
                signal_version TEXT
            );
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT,
                taxonomy_version TEXT,
                group_type TEXT,
                group_name TEXT,
                signal_version TEXT
            );
            CREATE TABLE dc_group_synthetic_ohlc_daily (
                ohlc_date TEXT,
                taxonomy_version TEXT,
                group_type TEXT,
                group_name TEXT,
                calc_version TEXT
            );
            CREATE TABLE dc_group_index_daily (
                index_date TEXT,
                taxonomy_version TEXT,
                group_type TEXT,
                group_name TEXT
            );
            CREATE TABLE ec_ticker_signal_daily (
                ecosystem_id INTEGER,
                taxonomy_version_id INTEGER,
                signal_date TEXT,
                ticker_id INTEGER,
                signal_version TEXT
            );
            CREATE TABLE ec_group_signal_daily (
                ecosystem_id INTEGER,
                taxonomy_version_id INTEGER,
                signal_date TEXT,
                group_type TEXT,
                group_name TEXT,
                signal_version TEXT
            );
            CREATE TABLE ec_group_synthetic_ohlc_daily (
                ecosystem_id INTEGER,
                taxonomy_version_id INTEGER,
                signal_date TEXT,
                group_type TEXT,
                group_name TEXT,
                calc_version TEXT
            );
            CREATE TABLE ec_group_index_daily (
                ecosystem_id INTEGER,
                taxonomy_version_id INTEGER,
                signal_date TEXT,
                group_type TEXT,
                group_name TEXT
            );
            """
        )
        conn.execute("INSERT INTO ec_ecosystem VALUES (1, 'DATACENTER')")
        conn.execute(
            "INSERT INTO ec_taxonomy_version VALUES (1,1,'DC_TAXONOMY_FULL_V1',?,?, 'ACTIVE', 1)",
            (hashlib.sha256(current_csv.read_bytes()).hexdigest(), str(current_csv)),
        )
        conn.execute(
            "INSERT INTO ec_taxonomy_version VALUES (2,1,'DC_TAXONOMY_FULL_V2_1',?,?, 'INACTIVE', 0)",
            (hashlib.sha256(proposed_csv.read_bytes()).hexdigest(), str(proposed_csv)),
        )
        conn.execute(
            """
            INSERT INTO ec_taxonomy_change_deployment (
                taxonomy_change_id, ecosystem_code, previous_taxonomy_version,
                proposed_taxonomy_version, source_reference, source_sha256,
                change_summary, added_ticker_count, removed_ticker_count,
                membership_change_count, group_change_count, status,
                rebuild_required, rebuild_start_date
            ) VALUES (2,'DATACENTER','DC_TAXONOMY_FULL_V1','DC_TAXONOMY_FULL_V2_1',?,?, '{}',0,0,0,0,'LOADED_NOT_ACTIVE',1,'2026-07-31')
            """,
            (str(proposed_csv), hashlib.sha256(proposed_csv.read_bytes()).hexdigest()),
        )
        for date_value in ["2026-07-31", "2026-08-03"]:
            conn.execute("INSERT INTO dc_group_swing_signal_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', 'ecosystem', 'DC_ECOSYSTEM_TOTAL', 'v1')", (date_value,))
            conn.execute("INSERT INTO dc_group_index_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', 'ecosystem', 'DC_ECOSYSTEM_TOTAL')", (date_value,))
            conn.execute("INSERT INTO dc_ticker_swing_signal_daily VALUES (?, 'DC_TAXONOMY_FULL_V2_1', 'AAA', 'v1')", (date_value,))
            conn.execute("INSERT INTO dc_group_swing_signal_daily VALUES (?, 'DC_TAXONOMY_FULL_V2_1', 'ecosystem', 'DC_ECOSYSTEM_TOTAL', 'v1')", (date_value,))
            conn.execute("INSERT INTO dc_group_synthetic_ohlc_daily VALUES (?, 'DC_TAXONOMY_FULL_V2_1', 'ecosystem', 'DC_ECOSYSTEM_TOTAL', 'v1')", (date_value,))
            conn.execute("INSERT INTO dc_group_index_daily VALUES (?, 'DC_TAXONOMY_FULL_V2_1', 'ecosystem', 'DC_ECOSYSTEM_TOTAL')", (date_value,))
            conn.execute("INSERT INTO ec_ticker_signal_daily VALUES (1,2,?,1,'v1')", (date_value,))
            conn.execute("INSERT INTO ec_group_signal_daily VALUES (1,2,?,'ecosystem','DC_ECOSYSTEM_TOTAL','v1')", (date_value,))
            conn.execute("INSERT INTO ec_group_synthetic_ohlc_daily VALUES (1,2,?,'ecosystem','DC_ECOSYSTEM_TOTAL','v1')", (date_value,))
            conn.execute("INSERT INTO ec_group_index_daily VALUES (1,2,?,'ecosystem','DC_ECOSYSTEM_TOTAL')", (date_value,))
        conn.commit()
    finally:
        conn.close()
    plan = build_taxonomy_change_plan(
        deployment_id=2,
        ecosystem_code="DATACENTER",
        current_taxonomy_version="DC_TAXONOMY_FULL_V1",
        current_taxonomy_csv=current_csv,
        proposed_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        proposed_taxonomy_csv=proposed_csv,
        date_from="2026-07-31",
        date_to="2026-08-03",
        rebuild_mode=REBUILD_MODE_DELTA,
    )
    return db_path, proposed_csv, plan


def _ok_parity(**_kwargs):
    return {"status": "OK", "total_mismatch_count": 0, "warnings": []}


def test_complete_target_ec_facts_select_read_only_revalidation(tmp_path) -> None:
    db_path, proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)

    result = plan_ec_resume_action(
        analysis_db=db_path,
        plan=plan,
        deployment_id=2,
        parity_audit=_ok_parity,
    )

    assert result["ec_resume_action"] == EC_RESUME_ACTION_REVALIDATE_EXISTING_FACTS
    assert result["ec_rebuild_required"] is False
    assert result["ec_loaders_required"] is False
    assert result["ec_chunks_required"] is False
    assert result["ec_revalidation_required"] is True
    assert proposed_csv.exists()


def test_missing_target_ec_row_does_not_select_read_only_revalidation(tmp_path) -> None:
    db_path, _proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM ec_group_index_daily WHERE signal_date='2026-08-03'")
        conn.commit()
    finally:
        conn.close()

    result = plan_ec_resume_action(analysis_db=db_path, plan=plan, deployment_id=2, parity_audit=_ok_parity)

    assert result["ec_resume_action"] == EC_RESUME_ACTION_REBUILD_EC_FACTS
    assert result["ec_revalidation"]["safe_to_continue_to_cleanup"] is False


def test_duplicate_target_ec_row_blocks_revalidation(tmp_path) -> None:
    db_path, _proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO ec_group_index_daily VALUES (1,2,'2026-08-03','ecosystem','DC_ECOSYSTEM_TOTAL')")
        conn.commit()
    finally:
        conn.close()

    result = revalidate_existing_ec_facts(
        analysis_db=db_path,
        ecosystem_code="DATACENTER",
        target_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        taxonomy_csv=plan["proposed_source_reference"],
        deployment_id=2,
        date_from="2026-07-31",
        date_to="2026-08-03",
        parity_audit=_ok_parity,
    )

    assert result["duplicate_status"] == "BLOCKED"
    assert result["safe_to_continue_to_cleanup"] is False


def test_taxonomy_hash_mismatch_blocks_ec_revalidation(tmp_path) -> None:
    db_path, _proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE ec_taxonomy_version SET source_hash='stale' WHERE taxonomy_version_code='DC_TAXONOMY_FULL_V2_1'")
        conn.commit()
    finally:
        conn.close()

    result = plan_ec_resume_action(analysis_db=db_path, plan=plan, deployment_id=2, parity_audit=_ok_parity)

    assert result["ec_resume_action"] == EC_RESUME_ACTION_REBUILD_EC_FACTS
    assert result["ec_revalidation"]["taxonomy_purity_status"] == "BLOCKED"


def test_parity_mismatch_blocks_continuation(tmp_path) -> None:
    db_path, _proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)

    def bad_parity(**_kwargs):
        return {"status": "FAILED", "total_mismatch_count": 1, "warnings": []}

    result = plan_ec_resume_action(analysis_db=db_path, plan=plan, deployment_id=2, parity_audit=bad_parity)

    assert result["ec_resume_action"] == EC_RESUME_ACTION_REBUILD_EC_FACTS
    assert result["ec_revalidation"]["total_mismatch_count"] == 1


def test_current_plan_hash_is_backend_derived_and_stale_supplied_hash_blocks(tmp_path) -> None:
    db_path, _proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)

    safe = plan_report_status_only_resume_reconciliation(
        analysis_db=db_path,
        plan=plan,
        original_plan_hash="original",
    )
    stale = plan_report_status_only_resume_reconciliation(
        analysis_db=db_path,
        plan=plan,
        original_plan_hash="original",
        current_plan_hash="stale-current-hash",
    )

    assert safe["plan_drift_classification"] == "SAFE_IMPLEMENTATION_RECONCILIATION"
    assert safe["current_recomputed_plan_hash"] == plan["plan_hash"]
    assert safe["current_plan_inputs_hash"]
    assert stale["plan_reconciliation_status"] == "BLOCKED"
    assert stale["plan_drift_classification"] == "UNSUPPORTED_PLAN_DRIFT"
    assert stale["original_plan_hash"] == "original"


def test_source_hash_drift_blocks_report_status_only_reconciliation(tmp_path) -> None:
    db_path, _proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)

    result = plan_report_status_only_resume_reconciliation(
        analysis_db=db_path,
        plan=plan,
        original_plan_hash="original",
        expected_proposed_source_sha256="stale-source-hash",
    )

    assert result["plan_reconciliation_status"] == "BLOCKED"
    assert result["plan_drift_classification"] == "SOURCE_DRIFT"
    assert result["source_inputs_unchanged"] is False


def test_report_status_only_resume_revalidation_dispatch_invokes_no_ec_rebuild(tmp_path, monkeypatch) -> None:
    db_path, _proposed_csv, plan = _create_ec_revalidation_fixture(tmp_path)
    ec_rebuild_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.validate_dc_carry_forward_key_universe",
        lambda **_kwargs: {"validation_status": "OK"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.plan_ec_resume_action",
        lambda **_kwargs: {
            "ec_resume_action": EC_RESUME_ACTION_REVALIDATE_EXISTING_FACTS,
            "ec_rebuild_required": False,
            "ec_loaders_required": False,
            "ec_chunks_required": False,
            "ec_revalidation_required": True,
            "ec_revalidation": {
                "safe_to_continue_to_cleanup": True,
                "total_mismatch_count": 0,
                "ec_revalidation_status": "OK",
            },
        },
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.plan_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"safe_to_apply": True, "delete_candidate_hash": "cleanup-hash"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.apply_ec_taxonomy_replacement_cleanup",
        lambda **_kwargs: {"cleanup_apply_status": "NO_CHANGE"},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator.finalize_ec_taxonomy_rebuild_validation",
        lambda **_kwargs: {"finalization_status": "OK", "total_mismatch_count": 0},
    )
    monkeypatch.setattr(
        "rawcandle.datacenter_taxonomy_change_orchestrator._plan_activation",
        lambda **_kwargs: {"safe_to_activate": True, "activation_plan_status": "READY_TO_ACTIVATE"},
    )

    def forbidden_ec_rebuild(**kwargs):
        ec_rebuild_calls.append(kwargs)
        raise AssertionError("EC rebuild must not be invoked for read-only revalidation")

    services = TaxonomyChangeServices(
        set_scheduler_guard=lambda **_kwargs: {"status": "OK"},
        verify_active_writer=lambda **_kwargs: {"status": "NO_ACTIVE_WRITER"},
        ensure_backup=lambda **_kwargs: {"status": "OK", "backup_reused": True},
        run_dc_rebuild=lambda **_kwargs: {"status": "OK"},
        run_ec_rebuild=forbidden_ec_rebuild,
    )

    summary = execute_taxonomy_rebuild(
        analysis_db=db_path,
        deployment_id=2,
        proposed_taxonomy_csv=str(plan["proposed_source_reference"]),
        date_to=str(plan["date_to"]),
        confirm_deployment_id=2,
        confirm_proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
        confirm_proposed_source_hash=str(plan["proposed_source_sha256"]),
        confirm_date_from=str(plan["date_from"]),
        confirm_date_to=str(plan["date_to"]),
        confirm_rebuild_mode=REBUILD_MODE_DELTA,
        confirm_plan_hash=str(plan["plan_hash"]),
        confirm_dc_repair_scope=DC_REPAIR_SCOPE_ECOSYSTEM_AGGREGATE_ONLY,
        confirm_repair_candidate_hash=str(plan_dc_ecosystem_aggregate_repair(analysis_db=db_path, plan=plan)["repair_candidate_hash"]),
        services=services,
        resume=True,
    )

    assert summary["run_status"] == "READY_TO_ACTIVATE"
    assert "EC_FACTS_REVALIDATED" in summary["completed_phases"]
    assert summary["ec_rebuild"]["run_ec_rebuild_invoked"] is False
    assert summary["ec_rebuild"]["ec_loaders_invoked"] is False
    assert summary["ec_rebuild"]["ec_chunks_invoked"] is False
    assert ec_rebuild_calls == []


def test_ready_to_activate_and_active_are_idempotent(tmp_path) -> None:
    db_path, config_path, proposed_csv, prepared = _prepared(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE ec_taxonomy_change_deployment SET status='READY_TO_ACTIVATE' WHERE taxonomy_change_id=?",
            (prepared["deployment_id"],),
        )
        conn.commit()
    finally:
        conn.close()

    ready = execute_taxonomy_rebuild(
        analysis_db=db_path,
        deployment_id=prepared["deployment_id"],
        proposed_taxonomy_csv=proposed_csv,
        date_to="2026-07-31",
        scheduler_config_path=config_path,
        confirm_deployment_id=prepared["deployment_id"],
        confirm_proposed_taxonomy_version="DC_TAXONOMY_FULL_V2",
        confirm_proposed_source_hash=prepared["plan"]["proposed_source_sha256"],
        confirm_date_from="2025-08-01",
        confirm_date_to="2026-07-31",
        confirm_rebuild_mode=REBUILD_MODE_FULL,
        confirm_plan_hash=prepared["plan"]["plan_hash"],
    )
    assert ready["run_status"] == "NO_CHANGE_READY_TO_ACTIVATE"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE ec_taxonomy_change_deployment SET status='ACTIVE', activation_status='ACTIVE'")
        conn.commit()
    finally:
        conn.close()
    active = inspect_taxonomy_change(analysis_db=db_path, deployment_id=prepared["deployment_id"])
    assert active["normalized_orchestration_status"] == "ACTIVE"
