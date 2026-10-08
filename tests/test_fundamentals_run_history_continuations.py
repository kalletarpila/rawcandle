"""Manual continuation visibility and explicit refresh of a bounded history cursor."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page, admin_report_download_url
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.test_fundamentals_admin_ui import _Page, _write_run


# Compact fixtures retain the actual manual chain's IDs, modes and UTC timestamps.
CHAIN = [
    ("20261008T173613Z_refresh_fundamentals_f8b949dda174", "PREVIEW", "2026-10-08T17:36:13Z", "2026-10-08T17:36:51Z", "Preview"),
    ("20261008T173737Z_refresh_fundamentals_b97b94e0bcf7_test", "COPY_ONLY_APPLY", "2026-10-08T17:37:37Z", "2026-10-08T17:49:30Z", "Test on copies"),
    ("20261008T175341Z_refresh_fundamentals_b97b94e0bcf7_production_aec4c4b9", "PRODUCTION_APPLY", "2026-10-08T17:53:41Z", "2026-10-08T18:04:46Z", "Production update"),
]


def _continuation(root, spec):
    run_id, mode, started, completed, stage = spec
    folder = root / run_id
    folder.mkdir(parents=True)
    request = {"operation_type": "REFRESH_FUNDAMENTALS", "options": {"mode": mode}, "requested_inputs": []}
    result = {
        "run_id": run_id, "operation_type": "REFRESH_FUNDAMENTALS", "mode": mode,
        "outcome": "COMPLETED", "started_at_utc": started, "completed_at_utc": completed,
        "summary_counts": {"effective_changed_known": 17},
    }
    if mode != "PRODUCTION_APPLY":
        result["request"] = request  # Actual Production result has no embedded request.
    (folder / "request.json").write_text(json.dumps(request))
    (folder / "result.json").write_text(json.dumps(result))
    (folder / "operation_report.md").write_text(f"# Refresh Fundamentals {stage}\n")
    return folder


def _service(root):
    return FundamentalsAdminUIService(
        run_root=root, operation_lock_path=root / "admin.lock",
        recover_publication_on_startup=False,
        cleanup_inspect=lambda _run: {"eligible": False, "reason": "No cleanup requested"},
    )


def _drain(page):
    while page.tasks:
        asyncio.run(page.tasks.pop(0)())


def _row_ids(controls):
    return [r.controls[5].tooltip.split(";")[0].removeprefix("run_id=")
            for r in controls.history_column.controls if hasattr(r, "controls")]


def test_manual_continuations_are_normal_distinct_downloadable_runs(tmp_path):
    for spec in CHAIN:
        _continuation(tmp_path, spec)
    # Internal artifacts do not become logical Production rows.
    (tmp_path / "publication-journal.json").write_text("{}")
    generation = tmp_path / ("refresh_" + CHAIN[-1][0])
    generation.mkdir()
    (generation / "manifest.json").write_text("{}")
    technical = tmp_path / "phase_acceptance"
    technical.mkdir()
    (technical / "acceptance_summary.json").write_text("{}")
    legacy = tmp_path / "old_report_layout"
    legacy.mkdir()
    (legacy / "legacy.md").write_text("old report")
    scheduler = _write_run(tmp_path, "20261008T041927Z_refresh_fundamentals_scheduler_full_workflow")
    payload = json.loads((scheduler / "result.json").read_text())
    payload.update(operation_type="REFRESH_FUNDAMENTALS", mode="FULL_WORKFLOW", outcome="STOPPED", trigger_source="SCHEDULER")
    (scheduler / "result.json").write_text(json.dumps(payload))
    (scheduler / "workflow_report.md").write_text("# Scheduler Full Workflow\n")
    service = _service(tmp_path)
    normal = service.history_entries(limit=24)
    all_rows = service.history_entries(limit=24, include_technical=True)
    assert [r.run_id for r in normal] == [s[0] for s in reversed(CHAIN)] + [scheduler.name]
    assert len({r.run_id for r in all_rows}) == len(all_rows)
    assert {r.run_id for r in normal} <= {r.run_id for r in all_rows}
    assert {r.run_id for r in all_rows} - {r.run_id for r in normal} == {generation.name, technical.name, legacy.name}
    for spec, entry in zip(reversed(CHAIN), normal):
        assert (entry.stage, entry.outcome, entry.primary_count, entry.category) == (spec[4], "COMPLETED", 17, "Administration run")
        assert entry.completed_at_utc == spec[3]
        assert entry.count_label == "17 changed tickers"
        assert entry.report_available
        assert service.resolve_named_report_download(entry.run_id, entry.report_filename) == tmp_path / entry.run_id / "operation_report.md"
    assert (normal[-1].stage, normal[-1].trigger_source, normal[-1].outcome) == ("Full workflow", "SCHEDULER", "STOPPED")


@pytest.mark.parametrize("deferred", [False, True])
def test_explicit_history_refresh_discovers_late_test_and_production(tmp_path, deferred, monkeypatch):
    if deferred:
        # Deterministic bridge, as in the existing DeferredLoadController tests.
        async def inline_to_thread(function):
            return function()
        monkeypatch.setattr("dev_tools.deferred_ui.asyncio.to_thread", inline_to_thread)
    _continuation(tmp_path, CHAIN[0])
    service, page = _service(tmp_path), _Page()
    controls = build_fundamentals_admin_page(page=page, service=service, defer_initial_load=deferred)
    if deferred:
        controls.activate()
        _drain(page)
    assert _row_ids(controls) == [CHAIN[0][0]]
    for spec in CHAIN[1:]:
        _continuation(tmp_path, spec)
    # Proves the real source defect: a loaded session retains its candidate snapshot.
    assert [r.run_id for r in service.history_entries()] == [s[0] for s in reversed(CHAIN)]
    if deferred:
        controls.activate()
        assert page.tasks == []  # Loaded route reuse is intentional.
    assert _row_ids(controls) == [CHAIN[0][0]]
    assert controls.show_technical_history_checkbox.value is False
    controls.history_refresh_button.on_click(None)
    _drain(page)
    assert _row_ids(controls) == [s[0] for s in reversed(CHAIN)]
    for row_control, spec in zip(controls.history_column.controls, reversed(CHAIN)):
        assert [c.value for c in row_control.controls[:6]] == [spec[3], "Refresh Fundamentals", spec[4], "Completed", "17 changed tickers", "Administration run"]
        row_control.controls[7].on_click(None)
        assert spec[0] in controls.history_detail_field.value
        assert "Operation report: available" in controls.history_detail_field.value
        row_control.controls[8].on_click(None)
        assert page.launched_urls[-1] == admin_report_download_url(spec[0])
    technical = tmp_path / "acceptance_fixture"
    technical.mkdir()
    (technical / "acceptance_summary.json").write_text("{}")
    controls.show_technical_history_checkbox.value = True
    controls.show_technical_history_checkbox.on_change(None)
    _drain(page)
    assert set(_row_ids(controls)) == {s[0] for s in CHAIN} | {technical.name}
    controls.show_technical_history_checkbox.value = False
    controls.show_technical_history_checkbox.on_change(None)
    _drain(page)
    assert _row_ids(controls) == [s[0] for s in reversed(CHAIN)]


def test_history_refresh_resets_bounded_paging_and_never_deletes_production(tmp_path):
    root = tmp_path / "runs"
    for minute in range(24):
        _write_run(root, f"20261007T12{minute:02d}00Z_add_tickers_old{minute}")
    for spec in CHAIN:
        _continuation(root, spec)
    service, page = _service(root), _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)
    for count in (8, 16, 24):
        assert len(_row_ids(controls)) == count
        assert len(set(_row_ids(controls))) == count
        assert _row_ids(controls) == [r.run_id for r in service.history_entries(limit=count)]
        if count < 24:
            controls.history_show_more_button.on_click(None)
    controls.history_refresh_button.on_click(None)
    assert len(_row_ids(controls)) == 8
    # Hide-only deletion is isolated from generation, backup and journal state.
    protected = [tmp_path / name for name in ("active-generation.db", "rollback-backup.db", "publication-journal.json")]
    for p in protected:
        p.write_bytes(b"retained production state")
    production_dir = root / CHAIN[-1][0]
    original = {p.name: p.read_bytes() for p in production_dir.iterdir()}
    controls.history_column.controls[0].controls[6].on_click(None)
    assert page.dialog.title.value == "Remove run from history?"
    page.dialog.actions[1].on_click(None)
    assert CHAIN[-1][0] not in _row_ids(controls)
    assert {p.name: p.read_bytes() for p in production_dir.iterdir()} == original
    assert all(p.read_bytes() == b"retained production state" for p in protected)
    assert service.resolve_report_download(CHAIN[-1][0]).is_file()
