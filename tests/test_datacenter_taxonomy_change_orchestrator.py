from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    CHANGE_EXECUTION_REPORT_STATUS_ONLY,
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
    prepare_taxonomy_change,
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
    assert explicit_delta["change_execution_class"] == REBUILD_MODE_DELTA
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
        lambda **_kwargs: {"safe_to_apply": True, "cleanup_plan_status": "READY_TO_APPLY"},
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
        lambda **_kwargs: {"safe_to_apply": True, "cleanup_plan_status": "READY_TO_APPLY"},
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
            "INSERT INTO dc_group_index_daily VALUES ('2026-07-31','DC_TAXONOMY_FULL_V1','layer','Power',10.0)"
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
        proposed_group_count = conn.execute(
            "SELECT COUNT(*) FROM dc_group_swing_signal_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert proposed_ticker_count == 2
    assert proposed_group_count == 1


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
