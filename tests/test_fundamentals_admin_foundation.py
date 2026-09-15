from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.artifacts import AdminRunWriter
from rawcandle.fundamentals.admin.contracts import (
    AdminFinalResult,
    AdminItemDecision,
    AdminOperationType,
    AdminPreview,
    AdminStatus,
    RunStage,
    build_batch_request,
    fingerprint,
    validate_transition,
)
from rawcandle.fundamentals.admin.history import AdminRunHistory
from rawcandle.fundamentals.admin.orchestrator import AdminOrchestrator
from rawcandle.fundamentals.admin.redaction import REDACTED, redact
from rawcandle.fundamentals.admin.reporting import render_markdown_report


def _decision(value: str, status: AdminStatus = AdminStatus.ELIGIBLE) -> AdminItemDecision:
    return AdminItemDecision(
        item_key=value,
        requested_value=value,
        normalized_value=value,
        status=status,
        reason="Synthetic decision for tests.",
        market="usa",
        source_category="synthetic",
    )


def _preview() -> AdminPreview:
    request = build_batch_request(AdminOperationType.ADD_TICKERS, " nvda, nvda msft ")
    return AdminPreview(
        operation_type=AdminOperationType.ADD_TICKERS,
        request=request,
        decisions=(_decision("NVDA"), _decision("MSFT", AdminStatus.ALREADY_PRESENT)),
        source_state={"dependency": "stable"},
        proposed_changes=({"ticker": "NVDA", "action": "ADD"},),
    )


def test_request_normalization_deduplicates_and_rejects() -> None:
    request = build_batch_request(AdminOperationType.ADD_TICKERS, " nvda, msft\nnvda bad/value ", market="USA")

    assert request.requested_inputs == ("nvda", "msft", "nvda", "bad/value")
    assert request.normalized_inputs == ("NVDA", "MSFT")
    assert request.market == "usa"
    assert request.rejected_inputs[0]["requested_value"] == "bad/value"


def test_preview_fingerprint_stable_and_sensitive() -> None:
    first = _preview().as_dict()
    second = _preview().as_dict()
    changed = AdminPreview(
        operation_type=_preview().operation_type,
        request=_preview().request,
        decisions=(_decision("NVDA", AdminStatus.REVIEW_REQUIRED),),
        source_state={"dependency": "stable"},
        proposed_changes=({"ticker": "NVDA", "action": "REVIEW"},),
    ).as_dict()

    assert first["preview_fingerprint"] == second["preview_fingerprint"]
    assert first["preview_fingerprint"] != changed["preview_fingerprint"]
    assert fingerprint({**first, "run_id": "local"}) == fingerprint(first)


def test_lifecycle_transition_validation() -> None:
    validate_transition(None, RunStage.REQUEST_CREATED)
    validate_transition(RunStage.REQUEST_CREATED, RunStage.PREVIEW_STARTED)
    validate_transition(RunStage.PREVIEW_STARTED, RunStage.PREVIEW_READY)
    validate_transition(RunStage.PREVIEW_READY, RunStage.COMPLETED)
    validate_transition(RunStage.WRITE_BOUNDARY_NOT_CROSSED, RunStage.COMPLETED)

    with pytest.raises(ValueError):
        validate_transition(RunStage.COMPLETED, RunStage.PREVIEW_STARTED)
    with pytest.raises(ValueError):
        validate_transition(RunStage.ROLLBACK_STARTED, RunStage.ROLLBACK_COMPLETE, write_boundary_crossed=False)


def test_atomic_status_survives_failed_replacement(monkeypatch, tmp_path) -> None:
    writer = AdminRunWriter("run1", AdminOperationType.ADD_TICKERS, root=tmp_path)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="created")
    status_path = writer.run_dir / "status.json"
    before = status_path.read_text(encoding="utf-8")

    def fail_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("rawcandle.io_atomic.os.replace", fail_replace)
    with pytest.raises(OSError):
        writer.write_json("status.json", {"stage": "BROKEN"})

    assert status_path.read_text(encoding="utf-8") == before


def test_heartbeat_records_are_parseable_and_concurrent_read_safe(tmp_path) -> None:
    writer = AdminRunWriter("run1", AdminOperationType.ADD_TICKERS, root=tmp_path)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="created")
    writer.append_heartbeat({"stage": "SYNTHETIC", "counter": 1})

    rows = [json.loads(line) for line in (writer.run_dir / "heartbeat.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["stage"] == RunStage.REQUEST_CREATED.value
    assert rows[-1]["counter"] == 1


def test_markdown_report_contains_plain_language_sections() -> None:
    result = AdminFinalResult(
        run_id="run1",
        operation_type=AdminOperationType.ADD_TICKERS,
        outcome=AdminStatus.PARTIALLY_COMPLETED,
        mode="APPLY",
        started_at_utc="2026-09-15T00:00:00Z",
        completed_at_utc="2026-09-15T00:01:00Z",
        preview_fingerprint="abc",
        request=_preview().request.as_dict(),
        item_results=(_decision("NVDA", AdminStatus.APPLIED), _decision("MSFT", AdminStatus.REVIEW_REQUIRED)),
        summary_counts={"applied": 1, "review_required": 1},
        rollback={"status": "NOT_REQUIRED"},
        downstream={"package": "NOT_RUN", "relative_position": "NOT_RUN", "relative_valuation": "NOT_RUN"},
        recommended_next_action="Review the unresolved item before applying it.",
    ).as_dict()

    report = render_markdown_report(result)

    assert "Accepted Changes" in report
    assert "Review Required" in report
    assert "Rollback" in report
    assert "Review the unresolved item" in report


def test_csv_and_json_contracts_are_stable(tmp_path) -> None:
    writer = AdminRunWriter("run1", AdminOperationType.ADD_TICKERS, root=tmp_path)
    path = writer.write_items_csv([_decision("NVDA").as_dict()])
    header = path.read_text(encoding="utf-8").splitlines()[0]

    assert header == "requested_value,normalized_value,item_key,market,company_name,status,reason,old_value,new_value,source_category,warning,applied_action"
    assert json.loads(writer.write_json("preview.json", _preview().as_dict()).read_text(encoding="utf-8"))["operation_type"] == "ADD_TICKERS"


def test_secret_redaction_from_all_artifacts(tmp_path) -> None:
    secret = "sentinel-secret-123"
    writer = AdminRunWriter("run1", AdminOperationType.ADD_TICKERS, root=tmp_path, configured_secrets=(secret,))
    writer.write_json("request.json", {"api_key": secret, "url": f"https://example.test?api_key={secret}", "safe_fingerprint": "abc123"})
    writer.write_text("report.md", f"authorization: Bearer {secret}\n")
    try:
        raise RuntimeError(f"failure included {secret}")
    except RuntimeError as exc:
        writer.write_error(exc)
    writer.write_manifest()

    for path in writer.run_dir.iterdir():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert secret not in text
    assert json.loads((writer.run_dir / "request.json").read_text(encoding="utf-8"))["safe_fingerprint"] == "abc123"
    assert REDACTED in (writer.run_dir / "error.json").read_text(encoding="utf-8")
    assert redact({"password": "x"})["password"] == REDACTED


def test_history_reader_lists_orders_and_rejects_escape(tmp_path) -> None:
    first = AdminRunWriter("20260101T000000Z_add_tickers_a", AdminOperationType.ADD_TICKERS, root=tmp_path)
    first.checkpoint(RunStage.REQUEST_CREATED, message="created")
    first.write_json("result.json", {"run_id": first.run_id, "operation_type": "ADD_TICKERS", "outcome": "COMPLETED"})
    second = AdminRunWriter("20260102T000000Z_add_tickers_b", AdminOperationType.ADD_TICKERS, root=tmp_path)
    second.checkpoint(RunStage.REQUEST_CREATED, message="created")

    history = AdminRunHistory(tmp_path, stale_seconds=0)
    rows = history.list_runs()

    assert [row.run_id for row in rows] == [second.run_id, first.run_id]
    assert rows[0].outcome == "INTERRUPTED"
    with pytest.raises(ValueError):
        history.artifact_path(first.run_id, "../result.json")


def test_history_reader_rejects_symlink_escape(tmp_path) -> None:
    target = tmp_path / "outside"
    target.mkdir()
    (tmp_path / "evil").symlink_to(target, target_is_directory=True)
    history = AdminRunHistory(tmp_path)

    with pytest.raises(ValueError):
        history.summarize("evil")


def test_corrupt_incomplete_artifact_set(tmp_path) -> None:
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "status.json").write_text("{not-json", encoding="utf-8")

    entry = AdminRunHistory(tmp_path, stale_seconds=0).summarize("run1")

    assert entry.status == "corrupt_or_incomplete"


def test_synthetic_orchestration_success_and_failure(tmp_path) -> None:
    def factory(run_id, operation_type):
        return AdminRunWriter(run_id, operation_type, root=tmp_path)

    orchestrator = AdminOrchestrator(writer_factory=factory)
    preview = _preview()
    preview_result = orchestrator.run_preview(preview.request, lambda request: preview)

    assert preview_result.result["outcome"] == "COMPLETED"
    assert Path(preview_result.artifact_dir, "report.md").exists()

    def apply_ok(preview_obj, writer):
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="synthetic write", write_boundary_crossed=True)
        return AdminFinalResult(
            run_id=writer.run_id,
            operation_type=preview_obj.operation_type,
            outcome=AdminStatus.COMPLETED,
            mode="APPLY",
            started_at_utc="2026-09-15T00:00:00Z",
            completed_at_utc="2026-09-15T00:01:00Z",
            preview_fingerprint=preview_obj.as_dict()["preview_fingerprint"],
            request=preview_obj.request.as_dict(),
            item_results=preview_obj.decisions,
        )

    apply_result = orchestrator.run_apply(preview, confirmed_preview_fingerprint=preview.as_dict()["preview_fingerprint"], apply_handler=apply_ok)
    assert apply_result.result["outcome"] == "COMPLETED"

    def apply_fail(preview_obj, writer):
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="synthetic write", write_boundary_crossed=True)
        raise RuntimeError("synthetic failure")

    failed = orchestrator.run_apply(
        preview,
        confirmed_preview_fingerprint=preview.as_dict()["preview_fingerprint"],
        apply_handler=apply_fail,
        rollback_handler=lambda exc, writer: {"status": "ROLLED_BACK", "message": "synthetic rollback complete"},
    )
    assert failed.result["outcome"] == "ROLLED_BACK"


def test_apply_preview_fingerprint_mismatch_rejected(tmp_path) -> None:
    orchestrator = AdminOrchestrator(writer_factory=lambda run_id, operation_type: AdminRunWriter(run_id, operation_type, root=tmp_path))

    with pytest.raises(ValueError):
        orchestrator.run_apply(_preview(), confirmed_preview_fingerprint="wrong", apply_handler=lambda preview, writer: None)  # type: ignore[arg-type]
