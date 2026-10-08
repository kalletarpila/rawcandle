from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from dev_tools.stock_update_scheduler_ui import build_config_from_ui_values
from rawcandle.cli.configure_fundamentals_refresh_scheduler import (
    FULL_WORKFLOW_CONFIRMATION,
    configure_mode,
)
from rawcandle.fundamentals.admin.production_transaction import production_lock
from rawcandle.fundamentals.admin.refresh_scheduler import (
    run_scheduler_refresh_discovery,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.scheduler.config import read_scheduler_config, write_scheduler_config


def test_full_workflow_mode_requires_explicit_persistent_config_confirmation(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "scheduler.json"
    write_scheduler_config(
        str(config_path),
        replace(read_scheduler_config("scheduler_config.json"), fundamentals_refresh_mode="PREVIEW_ONLY"),
    )
    original = read_scheduler_config(str(config_path))
    assert original.fundamentals_refresh_mode == "PREVIEW_ONLY"

    with pytest.raises(PermissionError, match="CONFIRMATION_REQUIRED"):
        configure_mode(config_path=str(config_path), mode="FULL_WORKFLOW")
    assert read_scheduler_config(str(config_path)).fundamentals_refresh_mode == "PREVIEW_ONLY"

    updated = configure_mode(
        config_path=str(config_path),
        mode="FULL_WORKFLOW",
        confirmation=FULL_WORKFLOW_CONFIRMATION,
    )
    assert updated["configured_mode"] == "FULL_WORKFLOW"
    assert read_scheduler_config(str(config_path)).fundamentals_refresh_mode == "FULL_WORKFLOW"

    configure_mode(config_path=str(config_path), mode="PREVIEW_ONLY")
    assert read_scheduler_config(str(config_path)).fundamentals_refresh_mode == "PREVIEW_ONLY"


def test_ui_config_builder_requires_confirmation_for_full_workflow() -> None:
    config = replace(read_scheduler_config("scheduler_config.json"), fundamentals_refresh_mode="PREVIEW_ONLY")
    kwargs = {
        "osakedata_db_path": config.osakedata_db_path,
        "analysis_db_path": config.analysis_db_path,
        "log_dir": config.log_dir,
        "timezone": config.timezone,
        "run_time": config.run_time,
        "selected_markets": config.enabled_markets,
        "technical_relevance_enabled": config.technical_relevance_enabled,
        "fundamentals_refresh_mode": "FULL_WORKFLOW",
        "base_config": config,
    }
    with pytest.raises(PermissionError, match="CONFIRMATION_REQUIRED"):
        build_config_from_ui_values(**kwargs)

    updated = build_config_from_ui_values(
        **kwargs,
        fundamentals_refresh_mode_confirmation=FULL_WORKFLOW_CONFIRMATION,
    )
    assert updated.fundamentals_refresh_mode == "FULL_WORKFLOW"


def test_scheduler_full_workflow_reports_each_gate_without_creating_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "scheduler-full-workflow"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    payload = {
        "run_id": run_id,
        "outcome": "COMPLETED",
        "production_completed": True,
        "started_at_utc": "2026-10-02T01:00:00Z",
        "source_summary": {
            "discovered_tickers": 4,
            "effective_changed_known": 3,
            "held_for_review": 1,
            "global_blockers": 0,
            "classification_counts": {
                "effective_changed_known": 3,
                "held_for_review": 1,
            },
        },
        "review_partition": {"held": [{"ticker": "HELD"}]},
        "publication_outcome": {
            "old_watermark": "2026-09-01",
            "new_watermark": "2026-10-01",
        },
        "stages": [
            {"stage": "Preview", "result": "COMPLETED", "run_id": "preview"},
            {"stage": "Test on copies", "result": "COMPLETED", "run_id": "test"},
            {"stage": "Production update", "result": "COMPLETED", "run_id": "production"},
        ],
    }
    (run_dir / "workflow_result.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_scheduler.safety_status",
        lambda: {"status": "CLEAR", "production_writes_blocked": False},
    )
    monkeypatch.setattr(
        FundamentalsAdminUIService,
        "resolve_refresh_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("scheduler must not create operator approvals")
        ),
    )
    calls: list[dict[str, object]] = []

    def workflow_backend(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            run_id=run_id,
            outcome="COMPLETED",
            status="COMPLETED",
            message="Full workflow completed.",
        )

    result = run_scheduler_refresh_discovery(
        run_root=tmp_path,
        operation_lock_path=tmp_path / "operation.lock",
        scheduler_mode="FULL_WORKFLOW",
        full_workflow_backend=workflow_backend,
    )

    assert calls == [{
        "operation_type": "REFRESH_FUNDAMENTALS",
        "raw_inputs": "",
        "trigger_source": "SCHEDULER",
        "scheduler_log_dir": None,
        "scheduler_managed_locks": True,
    }]
    assert result["configured_mode"] == "FULL_WORKFLOW"
    assert result["preview_result"] == "COMPLETED"
    assert result["test_invoked"] is True
    assert result["production_invoked"] is True
    assert result["production_run_id"] == "production"
    assert result["held_review_tickers"] == ["HELD"]
    assert result["global_blockers"] == 0
    assert result["final_outcome"] == "COMPLETED"


def test_full_workflow_scheduler_lock_is_admin_first_and_reentrant(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "admin.lock"
    log_dir = str(tmp_path / "scheduler")

    with production_lock(lock_path=lock_path, scheduler_log_dir=log_dir) as outer:
        with production_lock(
            lock_path=lock_path,
            scheduler_log_dir=log_dir,
            allow_reentrant=True,
        ) as inner:
            assert inner == outer


def test_invalid_scheduler_mode_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MODE_INVALID"):
        run_scheduler_refresh_discovery(
            run_root=tmp_path, scheduler_mode="AUTO_APPROVE",
        )
