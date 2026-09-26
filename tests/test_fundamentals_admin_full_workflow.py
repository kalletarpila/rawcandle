from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin.full_workflow import (
    run_full_workflow,
    run_remove_tickers_full_workflow,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


def _stage_result(
    run_root: Path,
    run_id: str,
    *,
    mode: str,
    outcome: str = "COMPLETED",
    status: str | None = None,
    ticker_reporting: list[dict] | None = None,
    extra: dict | None = None,
    operation_type: str = "ADD_TICKERS",
    report_content: str | None = None,
) -> SimpleNamespace:
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True)
    payload = {
        "run_id": run_id,
        "operation_type": operation_type,
        "mode": mode,
        "outcome": outcome,
        "ticker_reporting": ticker_reporting or [],
        **(extra or {}),
    }
    (run_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_dir / "operation_report.md").write_text(
        report_content if report_content is not None else f"# {mode}\n", encoding="utf-8",
    )
    return SimpleNamespace(
        status=status or ("COMPLETED" if outcome in {"COMPLETED", "NO_CHANGE"} else "FAILED"),
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


def _review_report(ticker: str, *codes: str) -> dict:
    report = _report(ticker, integrity="REPORTING_INTEGRITY_ERROR", action="Review required")
    report["eligibility"] = {
        "status": "REVIEW_REQUIRED",
        "reason": ",".join(codes),
        "reason_codes": list(codes),
        "user_reasons": [code.replace("_", " ").title() for code in codes],
    }
    report["after"]["analysis"]["integrity_reason"] = "Canonical ticker was not found in the after-state identity database"
    return report


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
    assert result["appendix_source"]["stage"] == "Production update"
    assert result["appendix_source"]["run_id"] == "production-run"
    assert [stage["run_id"] for stage in result["stages"]] == ["preview-run", "test-run", "production-run"]
    assert all((tmp_path / run_id / "operation_report.md").is_file() for run_id in ("preview-run", "test-run", "production-run"))
    workflow_dir = Path(result["artifact_dir"])
    assert (workflow_dir / "workflow_report.md").is_file()
    assert (workflow_dir / "workflow_result.json").is_file()
    assert "| Production update | COMPLETED |" in (workflow_dir / "workflow_report.md").read_text()
    report = (workflow_dir / "workflow_report.md").read_text(encoding="utf-8")
    assert "## Failure / Review Summary" not in report
    assert "Published/added: 1" in report
    assert "Production executed: Yes" in report
    assert "## Appendix: Authoritative Child Operation Report" in report
    assert "# PRODUCTION_APPLY" in report
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
    assert result["terminal_summary"]["stop_kind"] == "TECHNICAL_FAILURE"
    report = (Path(result["artifact_dir"]) / "workflow_report.md").read_text(encoding="utf-8")
    assert "Classification: TECHNICAL_FAILURE" in report
    assert "Production entered: No" in report


def test_real_workflow_review_stop_propagates_structured_test_facts_without_markdown_scraping(
    tmp_path: Path,
) -> None:
    production_calls: list[str] = []
    reports = [
        _report("ONE", action="Tested successfully - new ticker"),
        _report("TWO", action="Tested successfully - new ticker"),
        _report("THREE", action="Tested successfully - new ticker"),
        _review_report("DRK", "PROVIDER_METADATA_MISSING", "INCOMPATIBLE_EXCHANGE"),
        _review_report("KRSA", "PROVIDER_METADATA_MISSING", "INCOMPATIBLE_EXCHANGE"),
    ]
    result = run_full_workflow(
        "ONE TWO THREE DRK KRSA", market="usa", run_root=tmp_path,
        preview_stage=lambda callback: _stage_result(tmp_path, "preview-run", mode="PREVIEW"),
        test_stage=lambda preview, callback: _stage_result(
            tmp_path, "test-run", mode="COPY_ONLY_APPLY",
            outcome="PARTIALLY_COMPLETED", status="COMPLETED", ticker_reporting=reports,
            extra={"recommended_next_action": "Review identity evidence before rerunning the batch."},
        ),
        production_stage=lambda *args: production_calls.append("production"),
    )

    assert result["outcome"] == "STOPPED"
    assert result["final_completed_stage"] == "Test on copies"
    assert production_calls == []
    assert result["final_batch_outcome"] == {
        "requested": 5, "new": 5, "eligible": 3, "already_present": 0,
        "tested_successfully": 3, "test_completed": 5,
        "review_required": 2, "rejected": 0,
        "published_added": 0, "added": 0, "existing_rebuilt": 0,
        "no_usable_quarterly_history": 0, "reporting_integrity_errors": 2,
    }
    terminal = result["terminal_summary"]
    assert terminal["source"] == "STRUCTURED_CHILD_RESULT"
    assert terminal["authoritative_stage"] == "Test on copies"
    assert result["authoritative_item_evidence"]["stage"] == "Test on copies"
    assert result["appendix_source"]["stage"] == "Test on copies"
    assert terminal["production_entered"] is False
    assert terminal["production_database_writes"] == 0
    assert [item["ticker"] for item in terminal["problem_items"]] == ["DRK", "KRSA"]
    report = (Path(result["artifact_dir"]) / "workflow_report.md").read_text(encoding="utf-8")
    for expected in (
        "## Failure / Review Summary", "Classification: REVIEW_REQUIRED",
        "Workflow stopped after Test on copies because 2 tickers require review",
        "### DRK - REVIEW_REQUIRED", "### KRSA - REVIEW_REQUIRED",
        "Provider Metadata Missing", "Incompatible Exchange",
        "Test completed for: 5", "Tested successfully: 3", "Review required: 2", "Rejected: 0",
        "Reporting integrity errors: 2", "Published/added: 0", "Production executed: No",
    ):
        assert expected in report
    assert "# COPY_ONLY_APPLY" in report
    ui_result = FundamentalsAdminUIService(
        run_root=tmp_path, operation_lock_path=tmp_path / "ui.lock",
    )._finalize(result, default_message="Full workflow completed.")
    assert ui_result.status == "FAILED"
    assert "2 tickers require review" in ui_result.message
    assert "Requested: 5; eligible: 3; tested successfully: 3; review required: 2; rejected: 0." in ui_result.summary_rows
    assert "Affected tickers: DRK, KRSA." in ui_result.summary_rows
    assert "Production ran: No." in ui_result.summary_rows


def test_preview_review_stop_uses_preview_as_authoritative_terminal_stage(tmp_path: Path) -> None:
    calls: list[str] = []
    result = run_full_workflow(
        "DRK", market="usa", run_root=tmp_path,
        preview_stage=lambda callback: _stage_result(
            tmp_path, "preview-run", mode="PREVIEW", outcome="REVIEW_REQUIRED",
            status="FAILED", ticker_reporting=[_review_report("DRK", "PROVIDER_METADATA_MISSING")],
        ),
        test_stage=lambda *args: calls.append("test"),
        production_stage=lambda *args: calls.append("production"),
    )
    assert calls == []
    assert result["terminal_summary"]["authoritative_stage"] == "Preview"
    assert result["authoritative_item_evidence"]["stage"] == "Preview"
    assert result["appendix_source"]["stage"] == "Preview"
    assert result["terminal_summary"]["problem_items"][0]["ticker"] == "DRK"


def test_completed_preview_with_structured_review_stops_before_test_and_production(tmp_path: Path) -> None:
    calls: list[str] = []
    reports = [
        _report("PSQL", action="Eligible to add"),
        _review_report("KRSA", "NETWORK_TRANSIENT_FAILURE"),
        _review_report("QVCG", "NETWORK_TRANSIENT_FAILURE"),
    ]
    for report in reports:
        report["after"] = {"stage": "PREVIEW", "analysis": "Not calculated during Preview"}
    result = run_full_workflow(
        "KRSA PSQL QVCG", market="usa", run_root=tmp_path,
        preview_stage=lambda callback: _stage_result(
            tmp_path, "preview-run", mode="PREVIEW", ticker_reporting=reports,
            extra={
                "applyability": {
                    "copy_apply_authorized": False,
                    "eligible_count": 1,
                    "review_required_count": 2,
                    "rejected_count": 0,
                }
            },
        ),
        test_stage=lambda *args: calls.append("test"),
        production_stage=lambda *args: calls.append("production"),
    )

    assert calls == []
    assert result["outcome"] == "STOPPED"
    assert result["final_completed_stage"] == "Preview"
    assert result["terminal_summary"]["stop_kind"] == "REVIEW_REQUIRED"
    assert result["terminal_summary"]["failure_stage"] == "Preview"
    assert [item["ticker"] for item in result["terminal_summary"]["problem_items"]] == ["KRSA", "QVCG"]
    assert result["final_batch_outcome"]["requested"] == 3
    assert result["final_batch_outcome"]["eligible"] == 1
    assert result["final_batch_outcome"]["review_required"] == 2


def test_test_technical_failure_retains_latest_preview_ticker_evidence(tmp_path: Path) -> None:
    preview_reports = [_report(ticker, action="Eligible to add") for ticker in ("KRSA", "PSQL", "QVCG")]
    for report in preview_reports:
        report["after"] = {"stage": "PREVIEW", "analysis": "Not calculated during Preview"}
    result = run_full_workflow(
        "KRSA PSQL QVCG", market="usa", run_root=tmp_path,
        preview_stage=lambda callback: _stage_result(
            tmp_path, "preview-run", mode="PREVIEW", ticker_reporting=preview_reports,
            extra={"applyability": {"copy_apply_authorized": True, "blocking_items": []}},
        ),
        test_stage=lambda preview, callback: _stage_result(
            tmp_path, "test-run", mode="COPY_ONLY_APPLY", outcome="FAILED",
            extra={"user_failure_reason": "Candidate validation failed before ticker results were materialized."},
        ),
        production_stage=lambda *args: pytest.fail("Production must not run"),
    )

    terminal = result["terminal_summary"]
    assert terminal["stop_kind"] == "TECHNICAL_FAILURE"
    assert terminal["failure_stage"] == "Test on copies"
    assert terminal["authoritative_stage"] == "Preview"
    assert terminal["source"] == "STRUCTURED_LATEST_MATERIAL_RESULT"
    assert terminal["batch_outcome"]["requested"] == 3
    assert terminal["batch_outcome"]["eligible"] == 3
    report = (Path(result["artifact_dir"]) / "workflow_report.md").read_text(encoding="utf-8")
    assert "Technical failure/stop stage: Test on copies" in report
    assert "Authoritative item evidence: Preview" in report


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
    assert result["terminal_summary"]["authoritative_stage"] == "Production update"
    assert result["terminal_summary"]["production_entered"] is True
    assert "production lock" in result["terminal_summary"]["headline"]
    report = (Path(result["artifact_dir"]) / "workflow_report.md").read_text(encoding="utf-8")
    assert "Classification: TECHNICAL_FAILURE" in report
    assert "Production entered: Yes" in report


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

def test_structured_details_survive_missing_authoritative_child_report(tmp_path: Path) -> None:
    def preview(_callback):
        child = _stage_result(
            tmp_path, "preview-run", mode="PREVIEW", outcome="REVIEW_REQUIRED",
            status="FAILED",
            ticker_reporting=[_review_report("DRK", "PROVIDER_METADATA_MISSING")],
        )
        Path(child.artifact_dir, "operation_report.md").unlink()
        return child

    result = run_full_workflow(
        "DRK", market="usa", run_root=tmp_path,
        preview_stage=preview,
        test_stage=lambda *_args: pytest.fail("Test must not run"),
        production_stage=lambda *_args: pytest.fail("Production must not run"),
    )

    report = Path(result["artifact_dir"], "workflow_report.md").read_text(encoding="utf-8")
    assert "## Authoritative Child Details" in report
    assert "### DRK - REVIEW_REQUIRED" in report
    assert "Provider Metadata Missing" in report
    assert "## Appendix: Authoritative Child Operation Report" in report
    assert "could not be read: FileNotFoundError" in report


def test_recursive_child_appendix_is_not_duplicated(tmp_path: Path) -> None:
    nested = (
        "# Preview child\n\n"
        "Child evidence before appendix.\n\n"
        "## Appendix: Authoritative Child Operation Report\n\n"
        "recursive content must not survive\n"
    )
    result = run_full_workflow(
        "DRK", market="usa", run_root=tmp_path,
        preview_stage=lambda _callback: _stage_result(
            tmp_path, "preview-run", mode="PREVIEW", outcome="REVIEW_REQUIRED",
            status="FAILED",
            ticker_reporting=[_review_report("DRK", "PROVIDER_METADATA_MISSING")],
            report_content=nested,
        ),
        test_stage=lambda *_args: pytest.fail("Test must not run"),
        production_stage=lambda *_args: pytest.fail("Production must not run"),
    )

    report = Path(result["artifact_dir"], "workflow_report.md").read_text(encoding="utf-8")
    assert report.count("## Appendix: Authoritative Child Operation Report") == 1
    assert "Child evidence before appendix." in report
    assert "Nested workflow appendix omitted" in report
    assert "recursive content must not survive" not in report


def test_remove_tickers_review_stop_promotes_structured_item_details(tmp_path: Path) -> None:
    removal_item = {
        "requested_ticker": "OLD",
        "company_id": 7,
        "security_id": 11,
        "classification": "AMBIGUOUS_IDENTITY_REVIEW_REQUIRED",
        "removal_eligible": False,
        "blocking_or_review_reasons": ["HISTORICAL_ALIAS_MUST_NOT_REMOVE_CURRENT_SUCCESSOR"],
        "canonical": {"expected_current_universe_rows_affected": 0},
        "expected_derived_rebuild_impact": "NONE",
    }
    result = run_remove_tickers_full_workflow(
        "OLD", run_root=tmp_path,
        preview_stage=lambda _callback: _stage_result(
            tmp_path, "preview-run", mode="PREVIEW", outcome="REVIEW_REQUIRED",
            status="FAILED", operation_type="REMOVE_TICKERS",
            extra={
                "removal_plan": [removal_item],
                "recommended_next_action": "Resolve the current successor identity before removal.",
            },
            report_content="# Remove Tickers Preview\n\nAuthoritative removal evidence.\n",
        ),
        test_stage=lambda *_args: pytest.fail("Test must not run"),
        production_stage=lambda *_args: pytest.fail("Production must not run"),
    )

    report = Path(result["artifact_dir"], "workflow_report.md").read_text(encoding="utf-8")
    assert result["authoritative_item_evidence"]["stage"] == "Preview"
    assert "### OLD - AMBIGUOUS_IDENTITY_REVIEW_REQUIRED" in report
    assert "Historical Alias Must Not Remove Current Successor" in report
    assert '"company_id": 7' in report
    assert "Authoritative removal evidence." in report
