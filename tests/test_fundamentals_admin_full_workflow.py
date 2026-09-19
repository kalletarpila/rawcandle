from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin.full_workflow import run_full_workflow
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


def _stage_result(
    run_root: Path,
    run_id: str,
    *,
    mode: str,
    outcome: str = "COMPLETED",
    ticker_reporting: list[dict] | None = None,
    extra: dict | None = None,
) -> SimpleNamespace:
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True)
    payload = {
        "run_id": run_id,
        "operation_type": "ADD_TICKERS",
        "mode": mode,
        "outcome": outcome,
        "ticker_reporting": ticker_reporting or [],
        **(extra or {}),
    }
    (run_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_dir / "operation_report.md").write_text(f"# {mode}\n", encoding="utf-8")
    return SimpleNamespace(
        status="COMPLETED" if outcome in {"COMPLETED", "NO_CHANGE"} else "FAILED",
        outcome=outcome,
        run_id=run_id,
        artifact_dir=str(run_dir),
        preview_payload_path=str(run_dir / "preview_payload.json") if mode == "PREVIEW" else None,
        preview_fingerprint="preview-fp",
        message=f"{mode} {outcome}",
    )


def _report(ticker: str, *, availability: str | None = None, integrity: str = "READY", action: str = "Added") -> dict:
    analysis = {
        "integrity_status": integrity,
        "score": {"status": "FULL"},
        "lifecycle": {"status": "READY"},
        "valuation": {"status": "VALUATION_FULL"},
        "rp_v2": {"total_results": 1},
        "rv": {"status": "VALUATION_FULL"},
    }
    if availability:
        analysis["analysis_availability"] = availability
        analysis["integrity_status"] = "EXPECTED_NO_ANALYSIS"
        analysis["rp_v2"] = {"total_results": 0}
    return {
        "ticker": ticker,
        "eligibility": {"status": "ELIGIBLE"},
        "after": {"analysis": analysis},
        "final_action": action,
        "before": {"canonical_identity": False},
        "acquisition": {},
        "taxonomy": {},
    }


def test_full_workflow_happy_path_keeps_three_stage_reports_and_workflow_artifacts(tmp_path: Path) -> None:
    calls = []

    def preview(callback):
        calls.append("preview")
        callback({"run_id": "preview-run", "message": "resolving"})
        return _stage_result(tmp_path, "preview-run", mode="PREVIEW")

    def test(preview_result, callback):
        calls.append("test")
        assert preview_result.run_id == "preview-run"
        callback({"run_id": "test-run", "message": "rebuilding"})
        return _stage_result(tmp_path, "test-run", mode="COPY_ONLY_APPLY", ticker_reporting=[_report("NEW", action="Tested successfully")])

    def production(preview_result, test_result, callback):
        calls.append("production")
        assert test_result.run_id == "test-run"
        callback({"run_id": "production-run", "message": "publishing"})
        return _stage_result(tmp_path, "production-run", mode="PRODUCTION_APPLY", ticker_reporting=[_report("NEW")])

    result = run_full_workflow(
        "NEW", market="usa", run_root=tmp_path,
        preview_stage=preview, test_stage=test, production_stage=production,
    )

    assert calls == ["preview", "test", "production"]
    assert result["outcome"] == "COMPLETED"
    assert result["production_completed"] is True
    assert [stage["run_id"] for stage in result["stages"]] == ["preview-run", "test-run", "production-run"]
    assert all((tmp_path / run_id / "operation_report.md").is_file() for run_id in ("preview-run", "test-run", "production-run"))
    workflow_dir = Path(result["artifact_dir"])
    assert (workflow_dir / "workflow_report.md").is_file()
    assert (workflow_dir / "workflow_result.json").is_file()
    assert "| Production update | COMPLETED |" in (workflow_dir / "workflow_report.md").read_text()
    service = FundamentalsAdminUIService(run_root=tmp_path, operation_lock_path=tmp_path / "history.lock")
    workflow_entry = next(entry for entry in service.history_entries(include_technical=False) if entry.run_id == result["run_id"])
    assert workflow_entry.stage == "Full workflow"
    assert workflow_entry.report_filename == "workflow_report.md"


def test_full_workflow_stops_after_test_failure_and_preserves_preview_report(tmp_path: Path) -> None:
    production_calls = []
    result = run_full_workflow(
        "FAIL", market="usa", run_root=tmp_path,
        preview_stage=lambda callback: _stage_result(tmp_path, "preview-run", mode="PREVIEW"),
        test_stage=lambda preview, callback: _stage_result(tmp_path, "test-run", mode="COPY_ONLY_APPLY", outcome="FAILED"),
        production_stage=lambda *args: production_calls.append(args),
    )

    assert result["outcome"] == "STOPPED"
    assert result["current_stage"] == "Test on copies"
    assert result["manual_test_retry_available"] is True
    assert production_calls == []
    assert (tmp_path / "preview-run" / "operation_report.md").is_file()
    assert (tmp_path / "test-run" / "operation_report.md").is_file()


def test_integrity_error_stops_automatic_production_but_zero_arq_does_not(tmp_path: Path) -> None:
    integrity_production_calls = []
    integrity = run_full_workflow(
        "BROKEN", market="usa", run_root=tmp_path / "integrity",
        preview_stage=lambda callback: _stage_result(tmp_path / "integrity", "preview-run", mode="PREVIEW"),
        test_stage=lambda preview, callback: _stage_result(
            tmp_path / "integrity", "test-run", mode="COPY_ONLY_APPLY",
            ticker_reporting=[_report("BROKEN", integrity="REPORTING_INTEGRITY_ERROR")],
        ),
        production_stage=lambda *args: integrity_production_calls.append(args),
    )
    assert integrity["outcome"] == "STOPPED"
    assert integrity["manual_production_available"] is True
    assert "reporting integrity requires attention" in integrity["stop_reason"]
    assert integrity_production_calls == []

    zero_production_calls = []

    def zero_production(preview, test, callback):
        zero_production_calls.append("production")
        return _stage_result(
            tmp_path / "zero", "production-run", mode="PRODUCTION_APPLY",
            ticker_reporting=[_report("ZERO", availability="NO_USABLE_QUARTERLY_HISTORY")],
        )

    zero = run_full_workflow(
        "ZERO", market="usa", run_root=tmp_path / "zero",
        preview_stage=lambda callback: _stage_result(tmp_path / "zero", "preview-run", mode="PREVIEW"),
        test_stage=lambda preview, callback: _stage_result(
            tmp_path / "zero", "test-run", mode="COPY_ONLY_APPLY",
            ticker_reporting=[_report("ZERO", availability="NO_USABLE_QUARTERLY_HISTORY")],
        ),
        production_stage=zero_production,
    )
    assert zero["outcome"] == "COMPLETED"
    assert zero["final_batch_outcome"]["no_usable_quarterly_history"] == 1
    assert zero_production_calls == ["production"]


def test_retryable_production_failure_stops_without_loop_and_exposes_manual_retry(tmp_path: Path) -> None:
    def failed_production(preview, test, callback):
        return _stage_result(
            tmp_path, "production-run", mode="PRODUCTION_APPLY", outcome="FAILED",
            extra={
                "retry_authorization": {
                    "direct_production_retry_available": True,
                    "preview_test_rerun_required": False,
                },
                "user_failure_reason": "Another Administration operation currently holds the production lock.",
            },
        )

    result = run_full_workflow(
        "RETRY", market="usa", run_root=tmp_path,
        preview_stage=lambda callback: _stage_result(tmp_path, "preview-run", mode="PREVIEW"),
        test_stage=lambda preview, callback: _stage_result(tmp_path, "test-run", mode="COPY_ONLY_APPLY"),
        production_stage=failed_production,
    )

    assert result["outcome"] == "STOPPED"
    assert result["manual_production_retry_available"] is True
    assert len(result["stages"]) == 3


def test_dirty_git_warning_does_not_change_completed_workflow_outcome(tmp_path: Path) -> None:
    result = run_full_workflow(
        "DIRTY", market="usa", run_root=tmp_path,
        preview_stage=lambda callback: _stage_result(tmp_path, "preview-run", mode="PREVIEW"),
        test_stage=lambda preview, callback: _stage_result(tmp_path, "test-run", mode="COPY_ONLY_APPLY"),
        production_stage=lambda preview, test, callback: _stage_result(
            tmp_path, "production-run", mode="PRODUCTION_APPLY",
            extra={"git_state": {"head": "abc123", "dirty": True}},
        ),
    )

    assert result["outcome"] == "COMPLETED"
    assert result["warnings"] == ["Warning: Production ran with uncommitted Git worktree changes."]


def test_shared_operation_lock_rejects_conflicting_manual_stage(tmp_path: Path) -> None:
    service = FundamentalsAdminUIService(
        run_root=tmp_path / "runs",
        operation_lock_path=tmp_path / "operation.lock",
        add_preview=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not start")),
    )

    with service._operation_lock():
        with pytest.raises(RuntimeError, match="ADMIN_OPERATION_ALREADY_RUNNING"):
            service.preview("ADD_TICKERS", raw_inputs="NVDA")
