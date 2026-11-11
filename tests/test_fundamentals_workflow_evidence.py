"""Control state bounds, exact child references, and interruption acceptance."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin.artifacts import AdminRunWriter
from rawcandle.fundamentals.admin.contracts import AdminOperationType
from rawcandle.fundamentals.admin.full_workflow import run_refresh_full_workflow
from rawcandle.fundamentals.admin.refresh_operational_decision import (
    refresh_operational_decision,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.admin import workflow_evidence as evidence

FP = "exact-preview-binding"


def child(root, run_id, mode, *, outcome="COMPLETED", held=(), blob="", **extra):
    writer = AdminRunWriter(run_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=root)
    held = [
        {
            "ticker": t,
            "review_type": "FROZEN_HISTORICAL_PROVIDER_CONFLICT",
            "reason_codes": ["FROZEN_HISTORICAL_PROVIDER_CONFLICT"],
            "scope": "TICKER_LOCAL_REVIEW",
            "change": {"provider_history": blob},
        }
        for t in held
    ]
    decision = refresh_operational_decision(
        safe_effective_changes=1,
        held_items=held,
        global_blockers=[],
        future_test_authorized=outcome == "COMPLETED",
        test_reason_code="SAFE_CHANGES_TEST_AUTHORIZED",
    )
    payload = {
        "run_id": run_id,
        "operation_type": "REFRESH_FUNDAMENTALS",
        "mode": mode,
        "outcome": outcome,
        "preview_fingerprint": FP,
        "completed_at_utc": "2026-11-11T12:00:00Z",
        "summary_counts": {
            "effective_changed_known": 1,
            "safe_changes": 1,
            "held_for_review": len(held),
            "global_blockers": 0,
        },
        "operational_decision": decision,
        "refresh_preview": {
            "future_test_authorized": outcome == "COMPLETED",
            "review_partition": {"held": held},
            "ticker_changes": [],
        },
        **extra,
    }
    writer.write_json(
        "request.json", {"operation_type": "REFRESH_FUNDAMENTALS", "mode": mode}
    )
    writer.write_json("result.json", payload)
    if mode == "PREVIEW":
        writer.write_json(
            "refresh_preview.json",
            {
                "refresh_set_fingerprint": FP,
                "future_test_authorized": outcome == "COMPLETED",
            },
        )
    writer.write_text("operation_report.md", "# Native child details\n")
    writer.write_json("status.json", {"run_id": run_id, "stage": "COMPLETED"})
    writer.write_manifest()
    return SimpleNamespace(
        run_id=run_id,
        artifact_dir=str(writer.run_dir),
        mode=mode,
        status="COMPLETED",
        outcome=outcome,
        message=outcome,
        preview_fingerprint=FP,
        preview_payload_path=(
            str(writer.run_dir / "refresh_preview.json") if mode == "PREVIEW" else None
        ),
    )


def workflow(root, *, held=(), blob="", on_progress=None, test=None, preview=None):
    return run_refresh_full_workflow(
        run_root=root,
        preview_stage=preview
        or (lambda cb: child(root, "preview", "PREVIEW", held=held, blob=blob)),
        test_stage=test
        or (lambda p, cb: child(root, "test", "COPY_ONLY_APPLY", held=held)),
        production_stage=lambda p, t, cb: child(
            root,
            "production",
            "PRODUCTION_APPLY",
            held=held,
            provider_candidate={"ticker_count": 1},
            postflight={"status": "PASSED"},
        ),
        progress_callback=on_progress,
    )


def test_compact_control_keeps_exact_counts_and_child_authority(tmp_path):
    result = workflow(tmp_path, held=[f"H{i}" for i in range(100)], blob="X" * 8192)
    assert result["outcome"] == "COMPLETED"
    assert result["operational_decision"]["held_item_count"] == 100
    assert len(result["operational_decision"]["held_items"]) <= evidence.MAX_ITEMS
    assert result["terminal_summary"]["affected_item_count"] == 100
    parent = Path(result["artifact_dir"])
    assert (parent / "result.json").stat().st_size < 128 * 1024
    assert "provider_history" not in (parent / "result.json").read_text()
    for stage in result["stages"]:
        ref = stage["evidence_reference"]
        assert evidence.verify_reference(
            tmp_path, ref, kind="RESULT", run_id=stage["run_id"]
        ).is_file()
    assert result["preview_fingerprint"] == FP
    assert result["stages"][0]["preview_reference"]["semantic_fingerprint"] == FP
    assert (
        json.loads((tmp_path / "preview" / "result.json").read_text())[
            "operational_decision"
        ]["held_items"][0]["change"]["provider_history"]
        == "X" * 8192
    )


def test_repeated_real_parent_progress_never_reads_child_artifacts(
    tmp_path, monkeypatch
):
    in_progress = False
    reads = []
    original = Path.open

    def opened(path, *args, **kwargs):
        if in_progress and path.parent.name in ("preview", "test", "production"):
            reads.append(str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)

    def test(p, cb):
        nonlocal in_progress
        for i in range(100):
            in_progress = True
            cb({"run_id": "test", "current_stage_id": "WORK", "message": f"event {i}"})
            in_progress = False
        return child(tmp_path, "test", "COPY_ONLY_APPLY")

    result = workflow(tmp_path, held=["HELD"], blob="X" * 65536, test=test)
    assert result["outcome"] == "COMPLETED" and reads == []
    directory = Path(result["artifact_dir"])
    events = [
        json.loads(x)
        for x in (directory / "progress_events.jsonl").read_text().splitlines()
    ]
    assert [x["sequence"] for x in events] == list(range(1, len(events) + 1))
    assert (directory / "progress_status.json").stat().st_size < 2048
    assert (directory / "workflow_result.json").stat().st_size < 32768


@pytest.mark.parametrize(
    "defect",
    [
        "missing_result",
        "changed_result",
        "missing_preview",
        "changed_preview",
        "changed_summary",
        "missing_manifest",
        "missing_summary",
        "missing_status",
        "wrong_status_id",
        "wrong_mode",
        "incomplete",
        "wrong_fingerprint",
        "wrong_preview_type",
    ],
)
def test_artifact_defects_fail_closed_before_test(tmp_path, defect):
    called = []

    def preview(cb):
        value = child(tmp_path, "preview", "PREVIEW")
        folder = tmp_path / "preview"
        if defect == "missing_result":
            (folder / "result.json").unlink()
        if defect == "changed_result":
            with (folder / "result.json").open("a") as f:
                f.write(" ")
        if defect == "changed_summary":
            with (folder / evidence.SUMMARY).open("a") as f:
                f.write(" ")
        if defect == "missing_manifest":
            (folder / "artifact_manifest.json").unlink()
        if defect == "missing_summary":
            (folder / evidence.SUMMARY).unlink()
        if defect == "missing_status":
            (folder / "status.json").unlink()
        if defect == "wrong_status_id":
            (folder / "status.json").write_text(
                '{"run_id":"other","stage":"COMPLETED"}'
            )
        if defect == "wrong_mode":
            value.mode = "COPY_ONLY_APPLY"
            raw = json.loads((folder / "result.json").read_text())
            raw["mode"] = "COPY_ONLY_APPLY"
            writer = AdminRunWriter(
                "preview", AdminOperationType.REFRESH_FUNDAMENTALS, root=tmp_path
            )
            writer.write_json("result.json", raw)
            writer.write_manifest()
        if defect == "incomplete":
            (folder / "status.json").write_text('{"stage":"RUNNING"}')
        if defect == "wrong_fingerprint":
            value.preview_fingerprint = "different-binding"
        if defect == "wrong_preview_type":
            value.preview_payload_path = str(folder / "result.json")
        return value

    def progress(event):
        if (
            event["current_stage_id"] == "PREVIEW"
            and event["stage_state"] == "COMPLETED"
        ):
            path = tmp_path / "preview" / "refresh_preview.json"
            if defect == "missing_preview":
                path.unlink()
            if defect == "changed_preview":
                with path.open("a") as f:
                    f.write(" ")

    result = workflow(
        tmp_path,
        preview=preview,
        on_progress=progress,
        test=lambda *_: called.append("TEST"),
    )
    assert result["outcome"] == "FAILED" and called == []
    assert result["production_completed"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "other"},
        {"kind": "REPORT"},
        {"relative_path": "../outside.json"},
        {"format": "UNKNOWN"},
    ],
)
def test_reference_identity_and_type_cannot_be_reinterpreted(tmp_path, change):
    child(tmp_path, "preview", "PREVIEW")
    ref = evidence.reference(
        tmp_path, "preview", "PREVIEW", operation="REFRESH_FUNDAMENTALS"
    )
    with pytest.raises(ValueError):
        evidence.verify_reference(
            tmp_path, {**ref, **change}, kind="PREVIEW", run_id="preview"
        )


def test_review_required_remains_controlled_stop(tmp_path):
    result = workflow(
        tmp_path,
        preview=lambda cb: child(
            tmp_path, "preview", "PREVIEW", outcome="REVIEW_REQUIRED"
        ),
    )
    assert result["outcome"] == "STOPPED" and not result["production_completed"]
    assert len(result["stages"]) == 1


def test_child_report_remains_available_by_exact_reference(tmp_path):
    result = workflow(tmp_path)
    report = Path(result["artifact_dir"], "workflow_report.md").read_text()
    assert "Native child details" in report
    service = FundamentalsAdminUIService(
        run_root=tmp_path, recover_publication_on_startup=False
    )
    assert (
        service.resolve_named_report_download("production", "operation_report.md")
        == tmp_path / "production" / "operation_report.md"
    )


def test_atomic_control_interruption_never_exposes_partial_completion(
    tmp_path, monkeypatch
):
    import rawcandle.io_atomic as atomic

    original = atomic.os.replace
    armed = False

    class PowerLoss(BaseException):
        pass

    def replace(src, dst):
        if armed and Path(dst).name == "workflow_result.json":
            raise PowerLoss()
        return original(src, dst)

    monkeypatch.setattr(atomic.os, "replace", replace)

    def test(p, cb):
        nonlocal armed
        armed = True
        cb({"run_id": "test", "message": "not durable"})
        pytest.fail("interrupted callback must not return")

    with pytest.raises(PowerLoss):
        workflow(tmp_path, test=test)
    parent = next(x for x in tmp_path.iterdir() if "_full_workflow_" in x.name)
    data = json.loads((parent / "workflow_result.json").read_text())
    assert (
        data["workflow_status"] == "RUNNING" and data["production_completed"] is False
    )
    assert [x["stage"] for x in data["stages"]] == ["Preview"]
    assert not list(parent.glob(".*.tmp"))


def test_legacy_large_inline_parent_projection_does_not_decode_evidence(
    tmp_path, monkeypatch
):
    path = tmp_path / "legacy.json"
    with path.open("w") as f:
        f.write(
            '{\n  "run_id": "legacy",\n  "mode": "FULL_WORKFLOW",\n  "operational_decision": {\n    "held_item_count": 999,\n    "held_items": [\n      {"history": "'
        )
        for _ in range(64):
            f.write("X" * 65536)
        f.write(
            '"}\n    ]\n  },\n  "outcome": "STOPPED",\n  "stages": [\n    {\n      "stage": "Preview",\n      "run_id": "child"\n    }\n  ]\n}\n'
        )
    original = Path.read_text

    def no_giant_read(p, *a, **kw):
        assert p != path, "normal legacy view decoded complete evidence"
        return original(p, *a, **kw)

    monkeypatch.setattr(Path, "read_text", no_giant_read)
    result = evidence.read_metadata(path)
    assert (
        result["outcome"] == "STOPPED"
        and result["operational_decision"]["held_item_count"] == 999
    )
    assert result["stages"][0]["run_id"] == "child"
    assert "held_items" not in result["operational_decision"]


def test_keyboard_interrupt_records_stopped_without_fabricated_test_result(tmp_path):
    def interrupt(*args):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        workflow(tmp_path, test=interrupt)
    parent = next(x for x in tmp_path.iterdir() if "_full_workflow_" in x.name)
    result = json.loads((parent / "workflow_result.json").read_text())
    assert (
        result["outcome"] == "STOPPED"
        and result["terminal_summary"]["stop_kind"] == "INTERRUPTED"
    )
    assert result["interrupted"] is True and not result["production_completed"]
    assert [x["stage"] for x in result["stages"]] == ["Preview"]


def test_symlink_or_caller_path_cannot_supply_child_evidence(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "result.json").write_text("{}")
    (tmp_path / "child").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        evidence.reference(tmp_path, "child", "RESULT")
    with pytest.raises(ValueError):
        evidence.reference(tmp_path, "../outside", "RESULT")


def test_exact_child_counts_survive_large_review_sample(tmp_path):
    result = workflow(
        tmp_path,
        preview=lambda cb: child(
            tmp_path,
            "preview",
            "PREVIEW",
            outcome="REVIEW_REQUIRED",
            held=[f"H{i}" for i in range(75)],
        ),
    )
    assert result["outcome"] == "STOPPED"
    assert result["terminal_summary"]["affected_item_count"] == 75
    assert result["terminal_summary"]["review_required_count"] == 75
    assert len(result["terminal_summary"]["problem_items"]) <= evidence.MAX_ITEMS


@pytest.mark.parametrize("defect", ["missing", "tampered"])
def test_native_generation_workflow_rejects_preview_artifact_before_test(
    tmp_path, monkeypatch, defect
):
    from tests import (
        test_fundamentals_admin_refresh_full_workflow_production_parity as native,
    )
    from rawcandle.fundamentals.admin.publication_journal import sha256_file

    fixture = native._fixture(tmp_path, monkeypatch)
    native._migrate_refresh_fixture_to_generation_layout(fixture, monkeypatch)
    before = {r: sha256_file(p) for r, p in fixture.paths.as_dict().items()}

    def progress(event):
        if (
            event["current_stage_id"] == "PREVIEW"
            and event["stage_state"] == "COMPLETED"
        ):
            path = next(fixture.run_root.glob("*/refresh_preview.json"))
            if defect == "missing":
                path.unlink()
            else:
                with path.open("a") as f:
                    f.write(" ")

    result = native._service(fixture, actual_production=True).full_workflow(
        operation_type="REFRESH_FUNDAMENTALS", raw_inputs="", progress_callback=progress
    )
    workflow = native._workflow_payload(result)
    assert result.outcome == "FAILED" and not workflow["production_completed"]
    assert len(workflow["stages"]) == 1 and not list(fixture.run_root.glob("*_test"))
    assert {r: sha256_file(p) for r, p in fixture.paths.as_dict().items()} == before
    assert not fixture.journal_path.exists()


def test_native_generation_workflow_atomic_interruption_retains_completed_child(
    tmp_path, monkeypatch
):
    from tests import (
        test_fundamentals_admin_refresh_full_workflow_production_parity as native,
    )
    from rawcandle.fundamentals.admin.publication_journal import sha256_file
    import rawcandle.io_atomic as atomic

    fixture = native._fixture(tmp_path, monkeypatch)
    native._migrate_refresh_fixture_to_generation_layout(fixture, monkeypatch)
    before = {r: sha256_file(p) for r, p in fixture.paths.as_dict().items()}
    service = native._service(fixture, actual_production=True)
    original_preview = service._refresh_preview
    armed = False
    replace = atomic.os.replace

    class PowerLoss(BaseException):
        pass

    def preview(**kwargs):
        nonlocal armed
        result = original_preview(**kwargs)
        armed = True
        return result

    def interrupted(src, dst):
        if armed and Path(dst).name == "workflow_result.json":
            raise PowerLoss()
        return replace(src, dst)

    service._refresh_preview = preview
    monkeypatch.setattr(atomic.os, "replace", interrupted)
    with pytest.raises(PowerLoss):
        service.full_workflow(operation_type="REFRESH_FUNDAMENTALS", raw_inputs="")
    parent = next(fixture.run_root.glob("*full_workflow*"))
    latest = json.loads((parent / "workflow_result.json").read_text())
    assert latest["workflow_status"] == "RUNNING" and not latest["production_completed"]
    assert len(list(fixture.run_root.glob("*/refresh_preview.json"))) == 1
    assert (
        not list(fixture.run_root.glob("*_test")) and not fixture.journal_path.exists()
    )
    assert {r: sha256_file(p) for r, p in fixture.paths.as_dict().items()} == before


@pytest.mark.parametrize("count", [0, 1, 75])
def test_compact_safe_noop_preserves_native_pb_full_scope_gate(tmp_path, count):
    from rawcandle.fundamentals.admin.pb_ownership_future import (
        financial_result_allows_ownership_reconciliation as eligible,
    )

    held = [
        {
            "ticker": f"H{i}",
            "scope": "TICKER_LOCAL_REVIEW",
            "review_type": "FROZEN_HISTORICAL_PROVIDER_CONFLICT",
        }
        for i in range(count)
    ]
    decision = refresh_operational_decision(
        safe_effective_changes=0,
        held_items=held,
        global_blockers=[],
        future_test_authorized=False,
        test_reason_code="NO_SAFE_CHANGES_TO_PUBLISH",
    )
    result = workflow(
        tmp_path,
        preview=lambda cb: child(
            tmp_path,
            "preview",
            "PREVIEW",
            outcome="REVIEW_REQUIRED",
            held=[x["ticker"] for x in held],
            operational_decision=decision,
            summary_counts={
                "effective_changed_known": 0,
                "safe_changes": 0,
                "held_for_review": count,
                "global_blockers": 0,
            },
        ),
    )
    assert result["outcome"] == "STOPPED"
    hydrated = evidence.ownership_eligibility_view(result, tmp_path)
    assert eligible(hydrated) is True
    assert len(hydrated["operational_decision"]["held_items"]) == count
    scope_path = tmp_path / "preview" / "workflow_noop_scope.json"
    with scope_path.open("a") as f:
        f.write(" ")
    assert eligible(evidence.ownership_eligibility_view(result, tmp_path)) is False


def test_long_review_text_keeps_exact_stop_classification_and_totals(tmp_path):
    reports = [
        {
            "ticker": f"R{i}",
            "eligibility": {"status": "REVIEW_REQUIRED", "user_reasons": ["X" * 10000]},
            "after": {"analysis": {"integrity_status": "REPORTING_INTEGRITY_ERROR"}},
            "final_action": "Review required",
        }
        for i in range(100)
    ]
    result = workflow(
        tmp_path,
        preview=lambda cb: child(
            tmp_path,
            "preview",
            "PREVIEW",
            outcome="REVIEW_REQUIRED",
            ticker_reporting=reports,
        ),
    )
    assert result["outcome"] == "STOPPED"
    terminal = result["terminal_summary"]
    assert terminal["affected_item_count"] == terminal["review_required_count"] == 100
    assert terminal["reporting_integrity_error_count"] == 100
    assert all(
        x["review_required"] and x["reporting_integrity_error"]
        for x in terminal["problem_items"]
    )
    assert (
        "Showing 24 of 100"
        in Path(result["artifact_dir"], "workflow_report.md").read_text()
    )


def test_history_uses_exact_requested_count_beyond_parent_display_sample(tmp_path):
    from rawcandle.fundamentals.admin.full_workflow import run_full_workflow
    from tests.test_fundamentals_admin_full_workflow import _stage_result

    result = run_full_workflow(
        ",".join(f"T{i}" for i in range(30)),
        market="usa",
        run_root=tmp_path,
        preview_stage=lambda cb: _stage_result(tmp_path, "preview", mode="PREVIEW"),
        test_stage=lambda p, cb: _stage_result(
            tmp_path, "test", mode="COPY_ONLY_APPLY"
        ),
        production_stage=lambda p, t, cb: _stage_result(
            tmp_path, "production", mode="PRODUCTION_APPLY"
        ),
    )
    assert result["outcome"] == "COMPLETED"
    assert (
        len(result["requested_inputs"]) == evidence.MAX_ITEMS
        and result["requested_input_count"] == 30
    )
    service = FundamentalsAdminUIService(
        run_root=tmp_path, recover_publication_on_startup=False
    )
    row = next(x for x in service.history_entries() if x.run_id == result["run_id"])
    assert row.primary_count == 30 and row.count_label == "30 items"
