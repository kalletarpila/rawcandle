from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    REBUILD_MODE_DELTA,
    REBUILD_MODE_FULL,
    TaxonomyChangeServices,
    build_taxonomy_change_plan,
    build_taxonomy_diff,
    execute_taxonomy_rebuild,
    inspect_taxonomy_change,
    prepare_taxonomy_change,
)
from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration
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


def test_delta_rebuild_is_explicitly_unsupported(tmp_path) -> None:
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

    assert plan["plan_status"] == "BLOCKED"
    assert "rebuild mode is not supported yet: DELTA_REBUILD" in plan["blocking_errors"]


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
