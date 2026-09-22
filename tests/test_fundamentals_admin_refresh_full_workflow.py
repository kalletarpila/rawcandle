from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin.full_workflow import run_refresh_full_workflow
from rawcandle.fundamentals.admin.refresh_scheduler import run_scheduler_refresh_discovery
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.scheduler.config import StockUpdateSchedulerConfig, scheduler_config_from_dict
from rawcandle.scheduler.runner import ScheduledStockUpdateRunResult, _write_summary_json


def _stage(
    root: Path,
    run_id: str,
    *,
    mode: str,
    outcome: str = "COMPLETED",
    extra: dict | None = None,
) -> SimpleNamespace:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    payload = {
        "run_id": run_id,
        "operation_type": "REFRESH_FUNDAMENTALS",
        "mode": mode,
        "outcome": outcome,
        "trigger_source": "MANUAL",
        "summary_counts": {"effective_changed_known": 1, "HISTORICAL_REVISION": 1},
        **(extra or {}),
    }
    (run_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_dir / "operation_report.md").write_text(f"# {mode}\n", encoding="utf-8")
    return SimpleNamespace(
        status="COMPLETED" if outcome in {"COMPLETED", "NO_CHANGE", "REVIEW_REQUIRED"} else (
            "RETRY_REQUIRED" if outcome == "RETRY_REQUIRED" else "FAILED"
        ),
        outcome=outcome,
        run_id=run_id,
        artifact_dir=str(run_dir),
        preview_payload_path=str(run_dir / "refresh_preview.json") if mode == "PREVIEW" else None,
        preview_fingerprint="refresh-fingerprint",
        message=f"{mode} {outcome}",
    )


def test_refresh_full_workflow_no_change_stops_after_preview(tmp_path: Path) -> None:
    calls: list[str] = []

    def preview(_callback):
        calls.append("preview")
        return _stage(
            tmp_path, "preview-run", mode="PREVIEW", outcome="NO_CHANGE",
            extra={"summary_counts": {"effective_changed_known": 0}},
        )

    result = run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=preview,
        test_stage=lambda *_args: calls.append("test"),
        production_stage=lambda *_args: calls.append("production"),
    )
    assert calls == ["preview"]
    assert result["outcome"] == "NO_CHANGE"
    assert result["production_completed"] is False
    assert len(result["stages"]) == 1
    assert "No relevant Sharadar fundamentals changes" in result["stop_reason"]
    workflow_dir = Path(result["artifact_dir"])
    assert (workflow_dir / "workflow_report.md").is_file()
    assert (workflow_dir / "workflow_result.json").is_file()
    assert list(tmp_path.rglob("*_candidate.db")) == []
    assert list(tmp_path.rglob("*.backup.db")) == []
    assert list(tmp_path.rglob("*journal*.json")) == []


def test_refresh_full_workflow_happy_path_retains_child_reports(tmp_path: Path) -> None:
    result = run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=lambda _callback: _stage(
            tmp_path, "preview-run", mode="PREVIEW",
            extra={"refresh_preview": {"discovery": {"returned_source_rows": 2, "unique_changed_source_tickers": 1}}},
        ),
        test_stage=lambda _preview, _callback: _stage(tmp_path, "test-run", mode="COPY_ONLY_APPLY"),
        production_stage=lambda _preview, _test, _callback: _stage(
            tmp_path, "production-run", mode="PRODUCTION_APPLY",
            extra={
                "provider_candidate": {"ticker_count": 1},
                "canonical_candidate": {
                    "impact": {"changed_quarters": 1},
                    "publication_date_bootstrap": {"preservation_map_applied": 1},
                },
                "analysis_candidate": {"status": "READY"},
                "old_refresh_state": {"published_watermark": "2026-09-01"},
                "refresh_state": {"published_source_watermark": "2026-09-20"},
                "postflight": {"status": "PASSED"},
                "rollback": {"status": "NOT_REQUIRED"},
                "journal": {"state": "COMPLETED"},
            },
        ),
    )
    assert result["outcome"] == "COMPLETED"
    assert result["production_completed"] is True
    assert [item["run_id"] for item in result["stages"]] == ["preview-run", "test-run", "production-run"]
    assert all((tmp_path / run / "operation_report.md").is_file() for run in ("preview-run", "test-run", "production-run"))
    assert result["publication_outcome"]["new_watermark"] == "2026-09-20"
    report = (Path(result["artifact_dir"]) / "workflow_report.md").read_text(encoding="utf-8")
    assert "# Refresh Fundamentals Full Workflow Report" in report
    assert "| Production update | COMPLETED |" in report
    assert "V2/RP/RV: READY" in report


def test_refresh_full_workflow_preview_blocker_never_invokes_test(tmp_path: Path) -> None:
    calls: list[str] = []
    result = run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=lambda _callback: _stage(
            tmp_path, "preview-run", mode="PREVIEW", outcome="REVIEW_REQUIRED",
        ),
        test_stage=lambda *_args: calls.append("test"),
        production_stage=lambda *_args: calls.append("production"),
    )
    assert result["outcome"] == "STOPPED"
    assert result["current_stage"] == "Preview"
    assert calls == []
    assert result["terminal_summary"]["authoritative_stage"] == "Preview"
    assert result["terminal_summary"]["source"] == "STRUCTURED_CHILD_RESULT"
    report = (Path(result["artifact_dir"]) / "workflow_report.md").read_text(encoding="utf-8")
    assert "## Failure / Review Summary" in report
    assert "Classification: TECHNICAL_FAILURE" in report


@pytest.mark.parametrize(
    ("test_outcome", "production_outcome", "expected"),
    [
        ("FAILED", None, "STOPPED"),
        ("COMPLETED", "FAILED", "STOPPED"),
        ("COMPLETED", "RETRY_REQUIRED", "RETRY_REQUIRED"),
    ],
)
def test_refresh_full_workflow_stops_without_automatic_retry(
    tmp_path: Path, test_outcome: str, production_outcome: str | None, expected: str,
) -> None:
    production_calls: list[str] = []

    def production(_preview, _test, _callback):
        production_calls.append("production")
        return _stage(
            tmp_path, "production-run", mode="PRODUCTION_APPLY",
            outcome=str(production_outcome),
            extra={
                "retry_authorization": {
                    "direct_production_retry_available": False,
                    "preview_test_rerun_required": True,
                }
            },
        )

    result = run_refresh_full_workflow(
        run_root=tmp_path,
        preview_stage=lambda _callback: _stage(tmp_path, "preview-run", mode="PREVIEW"),
        test_stage=lambda _preview, _callback: _stage(
            tmp_path, "test-run", mode="COPY_ONLY_APPLY", outcome=test_outcome,
        ),
        production_stage=production,
    )
    assert result["outcome"] == expected
    assert production_calls == ([] if test_outcome == "FAILED" else ["production"])
    assert len(production_calls) <= 1


def test_scheduler_preview_no_change_and_pending_never_run_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden_calls: list[str] = []
    for method_name in ("copy_apply", "production_apply", "full_workflow"):
        monkeypatch.setattr(
            FundamentalsAdminUIService,
            method_name,
            lambda _self, *_args, _name=method_name, **_kwargs: forbidden_calls.append(_name),
        )
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_scheduler.safety_status",
        lambda: {"status": "CLEAR", "production_writes_blocked": False},
    )

    def backend(*, run_root, trigger_source, **_kwargs):
        assert trigger_source == "SCHEDULER"
        return vars(_stage(
            run_root, "20260920T010000Z_refresh_fundamentals_nochange", mode="PREVIEW", outcome="NO_CHANGE",
            extra={
                "trigger_source": trigger_source,
                "summary_counts": {"effective_changed_known": 0},
                "refresh_preview": {
                    "state": {"published_watermark": "2026-09-01"},
                    "discovery": {"unique_changed_source_tickers": 0},
                },
            },
        )) | {
            "operation_type": "REFRESH_FUNDAMENTALS", "mode": "PREVIEW",
            "outcome": "NO_CHANGE", "trigger_source": trigger_source,
            "summary_counts": {"effective_changed_known": 0},
        }

    no_change = run_scheduler_refresh_discovery(
        run_root=tmp_path, operation_lock_path=tmp_path / "operation.lock",
        preview_backend=backend,
    )
    assert no_change["outcome"] == "NO_CHANGE"
    assert no_change["test_invoked"] is False
    assert no_change["production_invoked"] is False
    assert no_change["full_workflow_invoked"] is False
    assert no_change["unattended_production_available"] is False
    assert no_change["scheduler_summary_result"] == "NO_CHANGE"
    assert no_change["published_baseline"] == "2026-09-01"
    assert no_change["message"] == "Refresh Fundamentals: No relevant Sharadar changes since the last published refresh."

    def pending_backend(*, run_root, trigger_source, **_kwargs):
        stage = _stage(
            run_root, "20260920T020000Z_refresh_fundamentals_pending", mode="PREVIEW",
            extra={
                "trigger_source": trigger_source,
                "summary_counts": {"effective_changed_known": 3, "NEW_QUARTER": 1},
                "refresh_preview": {
                    "state": {"published_watermark": "2026-09-01"},
                    "discovery": {"unique_changed_source_tickers": 4},
                },
            },
        )
        return vars(stage) | {
            "operation_type": "REFRESH_FUNDAMENTALS", "mode": "PREVIEW",
            "outcome": "COMPLETED", "trigger_source": trigger_source,
            "summary_counts": {"effective_changed_known": 3, "NEW_QUARTER": 1},
        }

    pending = run_scheduler_refresh_discovery(
        run_root=tmp_path, operation_lock_path=tmp_path / "operation.lock",
        preview_backend=pending_backend,
    )
    assert pending["outcome"] == "PENDING_CHANGES"
    assert pending["scheduler_summary_result"] == "CHANGES_FOUND"
    assert pending["discovered_source_ticker_count"] == 4
    assert pending["summary_counts"]["effective_changed_known"] == 3
    assert pending["pending_changes"] is True
    assert pending["review_required"] is False
    assert forbidden_calls == []
    status = FundamentalsAdminUIService(
        run_root=tmp_path, operation_lock_path=tmp_path / "history.lock",
    ).pending_refresh_status()
    assert status is not None
    assert status["effective_changed_known"] == 3
    assert status["production_authorized"] is False


def test_scheduler_discovery_respects_publication_safety_and_shared_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_scheduler.safety_status",
        lambda: {"status": "RECOVERY_FAILED", "production_writes_blocked": True},
    )
    blocked = run_scheduler_refresh_discovery(
        run_root=tmp_path, operation_lock_path=tmp_path / "operation.lock",
        preview_backend=lambda **_kwargs: calls.append("preview"),
    )
    assert blocked["outcome"] == "BLOCKED"
    assert calls == []

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_scheduler.safety_status",
        lambda: {"status": "CLEAR", "production_writes_blocked": False},
    )
    service = FundamentalsAdminUIService(
        run_root=tmp_path, operation_lock_path=tmp_path / "operation.lock",
    )
    with service._operation_lock():
        blocked_by_lock = run_scheduler_refresh_discovery(
                run_root=tmp_path, operation_lock_path=tmp_path / "operation.lock",
                preview_backend=lambda **_kwargs: calls.append("preview"),
            )
    assert blocked_by_lock["scheduler_summary_result"] == "FAILED"
    assert blocked_by_lock["technical_failure"].endswith("ADMIN_OPERATION_ALREADY_RUNNING")
    assert blocked_by_lock["test_invoked"] is False
    assert blocked_by_lock["production_invoked"] is False
    assert blocked_by_lock["full_workflow_invoked"] is False


@pytest.mark.parametrize(
    ("outcome", "counts", "summary_status", "review_required", "technical_failure"),
    [
        ("REVIEW_REQUIRED", {"REVIEW_REQUIRED": 2, "effective_changed_known": 1}, "REVIEW_REQUIRED", True, None),
        ("FAILED", {"failed": 1}, "FAILED", False, "ProviderUnavailable: temporary outage"),
    ],
)
def test_scheduler_preview_preserves_review_and_technical_failure_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    counts: dict[str, int],
    summary_status: str,
    review_required: bool,
    technical_failure: str | None,
) -> None:
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_scheduler.safety_status",
        lambda: {"status": "CLEAR", "production_writes_blocked": False},
    )

    def backend(*, run_root, trigger_source, **_kwargs):
        extra = {
            "trigger_source": trigger_source,
            "summary_counts": counts,
            "refresh_preview": {
                "state": {"published_watermark": "2026-09-01"},
                "discovery": {"unique_changed_source_tickers": 2},
            },
        }
        if technical_failure:
            error_type, message = technical_failure.split(": ", 1)
            extra["errors"] = [{"type": error_type, "message": message}]
        stage = _stage(
            run_root,
            f"20260920T030000Z_refresh_fundamentals_{outcome.lower()}",
            mode="PREVIEW",
            outcome=outcome,
            extra=extra,
        )
        return vars(stage) | {
            "operation_type": "REFRESH_FUNDAMENTALS",
            "mode": "PREVIEW",
            "outcome": outcome,
            **extra,
        }

    result = run_scheduler_refresh_discovery(
        run_root=tmp_path,
        operation_lock_path=tmp_path / "operation.lock",
        preview_backend=backend,
    )

    assert result["scheduler_summary_result"] == summary_status
    assert result["review_required"] is review_required
    assert result["technical_failure"] == technical_failure
    assert result["test_invoked"] is False
    assert result["production_invoked"] is False
    assert result["full_workflow_invoked"] is False


def test_scheduler_config_is_disabled_by_default_and_has_no_production_switch() -> None:
    config = StockUpdateSchedulerConfig()
    assert config.fundamentals_refresh_preview_enabled is False
    with pytest.raises(ValueError, match="Unexpected config keys"):
        scheduler_config_from_dict({
            "enabled_markets": [], "run_time": "05:30",
            "osakedata_db_path": "market.db", "analysis_db_path": "analysis.db",
            "log_dir": "logs", "fundamentals_refresh_production_enabled": True,
        })


def test_refresh_uses_existing_scheduler_summary_json_contract(tmp_path: Path) -> None:
    config = StockUpdateSchedulerConfig(log_dir=str(tmp_path))
    result = ScheduledStockUpdateRunResult(
        started_at_utc="2026-09-20T01:00:00Z",
        finished_at_utc="2026-09-20T01:01:00Z",
        config_path="scheduler.json",
        enabled_markets=[],
        fundamentals_refresh_preview_enabled=True,
        fundamentals_refresh_preview_attempted=1,
        fundamentals_refresh_preview_status="CHANGES_FOUND",
        fundamentals_refresh_preview_timestamp_utc="2026-09-20T01:00:30Z",
        fundamentals_refresh_published_baseline="2026-09-01",
        fundamentals_refresh_pending_changes=True,
        fundamentals_refresh_review_required=False,
        fundamentals_refresh_technical_failure="NONE",
        fundamentals_refresh_discovered_source_ticker_count=25,
        fundamentals_refresh_preview_changed_tickers=23,
        fundamentals_refresh_new_quarter_count=17,
        fundamentals_refresh_historical_revision_count=4,
        fundamentals_refresh_new_quarter_and_revision_count=2,
        fundamentals_refresh_source_removal_count=0,
        fundamentals_refresh_review_required_count=0,
        fundamentals_refresh_unknown_ticker_count=2,
        fundamentals_refresh_preview_run_id="scheduler-preview",
        fundamentals_refresh_preview_report="runs/scheduler-preview/operation_report.md",
        fundamentals_refresh_preview_message=(
            "Refresh Fundamentals: 23 known tickers have pending changes: "
            "17 new quarters, 4 revisions, 2 new-quarter + revision. Manual refresh pending."
        ),
    )
    import datetime

    _write_summary_json(
        config=config,
        run_started_at=datetime.datetime(2026, 9, 20, 1, 0, tzinfo=datetime.timezone.utc),
        result=result,
    )
    summary_files = list(tmp_path.glob("stock_update_scheduler_summary_*.json"))
    assert len(summary_files) == 1
    payload = json.loads(summary_files[0].read_text(encoding="utf-8"))
    assert payload["fundamentals_refresh_preview_status"] == "CHANGES_FOUND"
    assert payload["fundamentals_refresh_published_baseline"] == "2026-09-01"
    assert payload["fundamentals_refresh_preview_changed_tickers"] == 23
    assert payload["fundamentals_refresh_pending_changes"] is True
    assert payload["fundamentals_refresh_review_required"] is False
    assert not list(tmp_path.glob("*fundamentals*summary*.json"))
