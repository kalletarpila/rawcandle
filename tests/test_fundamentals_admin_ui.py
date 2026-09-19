from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from dev_tools.fundamentals_admin_page import (
    admin_report_download_url,
    build_fundamentals_admin_page,
)
from dev_tools.stock_update_scheduler_ui import (
    add_fundamentals_admin_download_route,
    add_fundamentals_download_route,
)
from rawcandle.fundamentals.admin.artifacts import sha256_file
from rawcandle.fundamentals.admin.history import AdminRunHistory
from rawcandle.fundamentals.admin.operation_report import (
    OPERATION_REPORT_NAME,
    WORKFLOW_REPORT_NAME,
    build_operation_summary,
    final_status_message,
    render_operation_report,
    resolve_operation_report_download,
    taxonomy_preview_presentation,
    write_operation_report,
)
from rawcandle.fundamentals.admin.production_transaction import render_production_report
from rawcandle.fundamentals.admin.ui_service import (
    AdminOperationCapability,
    AdminUIHistoryEntry,
    AdminUIRunResult,
    FundamentalsAdminUIService,
)


class _Page:
    def __init__(self) -> None:
        self.update_count = 0
        self.launched_urls: list[str] = []
        self.tasks = []
        self.opened_dialogs: list[object] = []

    def update(self) -> None:
        self.update_count += 1

    def launch_url(self, url: str) -> None:
        self.launched_urls.append(url)

    def run_task(self, coro) -> None:
        self.tasks.append(coro)

    def open(self, dialog) -> None:
        self.opened_dialogs.append(dialog)
        dialog.open = True


def _write_run(root: Path, run_id: str = "20260916T120000Z_add_tickers_test") -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "request.json").write_text(
        json.dumps(
            {
                "operation_type": "ADD_TICKERS",
                "requested_inputs": ["NVDA"],
                "token": "secret-value",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "progress_status.json").write_text(
        json.dumps(
            {
                "current_stage_id": "COMPLETED",
                "current_stage_number": 3,
                "total_declared_stages": 3,
                "stage_state": "COMPLETED",
                "message": "Done",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "progress_events.jsonl").write_text(
        json.dumps(
            {
                "current_stage_id": "PREFLIGHT",
                "current_stage_number": 1,
                "total_declared_stages": 3,
                "stage_state": "COMPLETED",
                "message": "Recorded token=secret-value",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "result.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "operation_type": "ADD_TICKERS",
                "outcome": "COMPLETED",
                "mode": "PREVIEW",
                "started_at_utc": "2026-09-16T12:00:00Z",
                "completed_at_utc": "2026-09-16T12:01:00Z",
                "preview_fingerprint": "f" * 64,
                "network_allowed": True,
                "network_used": False,
                "source_resolution": {
                    "NVDA": "existing local provider data",
                    "VRT": "not found",
                },
                "bounded_request_count": 0,
                "summary_counts": {"ELIGIBLE": 1},
                "items": [
                    {"ticker": "NVDA", "status": "ELIGIBLE", "reason": "new ticker"},
                    {"ticker": "VRT", "status": "REJECTED", "reason": "already present"},
                ],
                "changes": {"before": {"ticker_count": 10}, "after": {"ticker_count": 11}},
                "source": {"provider": "fixture", "url": "https://example.invalid/report?token=secret-value"},
                "downstream": {
                    "invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0},
                    "snapshot": {"success": 0, "failure": 0},
                    "write_boundary": {"status": "NOT_CROSSED"},
                },
                "warnings": [{"message": "duplicate request ignored"}],
                "rollback": {"status": "NOT_REQUIRED"},
                "recommended_next_action": "Review the preview.",
                "result_fingerprint": "r" * 64,
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_operation_report_is_written_atomically_manifested_and_redacted(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)

    report = write_operation_report(run_dir.name, root=tmp_path)

    report_path = run_dir / OPERATION_REPORT_NAME
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    text = report_path.read_text(encoding="utf-8")
    assert report.report_path == str(report_path)
    assert report.report_sha256
    assert "Executive Summary" in text
    assert "What Was Checked" in text
    assert "Provider network data was not used" in text
    assert "Changes Found" in text
    assert "NVDA" in text
    assert "already present" in text
    assert "Actions Performed" in text
    assert "Downstream Impact" in text
    assert "Warnings or Blockers" in text
    assert "Final Result" in text
    assert "Technical Appendix" in text
    assert "secret-value" not in text
    assert "https://example.invalid" not in text
    assert any(item["name"] == OPERATION_REPORT_NAME for item in manifest["artifacts"])


def test_operation_report_download_resolver_rejects_escape_symlink_and_wrong_artifact(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    write_operation_report(run_dir.name, root=tmp_path)

    assert resolve_operation_report_download(run_dir.name, root=tmp_path) == (run_dir / OPERATION_REPORT_NAME).resolve()
    with pytest.raises(ValueError):
        resolve_operation_report_download("../bad", root=tmp_path)
    with pytest.raises(ValueError):
        resolve_operation_report_download(run_dir.name, "result.json", root=tmp_path)
    with pytest.raises(FileNotFoundError):
        resolve_operation_report_download("missing", root=tmp_path)

    target = tmp_path / "outside"
    target.mkdir()
    (tmp_path / "link").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        resolve_operation_report_download("link", root=tmp_path)


def test_admin_download_route_serves_exact_operation_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _write_run(tmp_path)
    write_operation_report(run_dir.name, root=tmp_path)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.resolve_operation_report_download",
        lambda run_id, filename: resolve_operation_report_download(run_id, filename, root=tmp_path),
    )
    app = FastAPI()
    add_fundamentals_admin_download_route(app)
    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/fundamentals/admin/reports/{run_id}/{filename:path}"
    )

    response = asyncio.run(route.endpoint(run_dir.name, OPERATION_REPORT_NAME))

    assert Path(response.path).read_bytes() == (run_dir / OPERATION_REPORT_NAME).read_bytes()
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="operation_report.md"'
    with pytest.raises(HTTPException) as error:
        asyncio.run(route.endpoint(run_dir.name, "result.json"))
    assert error.value.status_code == 404


def test_admin_download_route_serves_workflow_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "20260919T120000Z_add_tickers_fixture_full_workflow"
    run_dir.mkdir()
    (run_dir / WORKFLOW_REPORT_NAME).write_text("# Add Tickers Full Workflow Report\n", encoding="utf-8")
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.resolve_operation_report_download",
        lambda run_id, filename: resolve_operation_report_download(run_id, filename, root=tmp_path),
    )
    app = FastAPI()
    add_fundamentals_admin_download_route(app)
    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/fundamentals/admin/reports/{run_id}/{filename:path}"
    )

    response = asyncio.run(route.endpoint(run_dir.name, WORKFLOW_REPORT_NAME))

    assert Path(response.path).read_text(encoding="utf-8").startswith("# Add Tickers Full Workflow Report")
    assert response.headers["content-disposition"] == 'attachment; filename="workflow_report.md"'


def test_admin_download_route_matches_artifact_hash_and_rejects_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run(tmp_path)
    write_operation_report(run_dir.name, root=tmp_path)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.resolve_operation_report_download",
        lambda run_id, filename: resolve_operation_report_download(run_id, filename, root=tmp_path),
    )
    app = FastAPI()
    add_fundamentals_admin_download_route(app)
    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/fundamentals/admin/reports/{run_id}/{filename:path}"
    )

    response = asyncio.run(route.endpoint(run_dir.name, OPERATION_REPORT_NAME))

    report_path = run_dir / OPERATION_REPORT_NAME
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    report_manifest = next(item for item in manifest["artifacts"] if item["name"] == OPERATION_REPORT_NAME)
    assert Path(response.path).read_bytes() == report_path.read_bytes()
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="operation_report.md"'
    assert sha256_file(report_path) == report_manifest["sha256"]
    assert sha256_file(report_path) == __import__("hashlib").sha256(Path(response.path).read_bytes()).hexdigest()
    for run_id, filename in (
        (run_dir.name, "result.json"),
        ("../escape", OPERATION_REPORT_NAME),
        ("%2e%2e%2fescape", OPERATION_REPORT_NAME),
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(route.endpoint(run_id, filename))
        assert error.value.status_code == 404


def test_admin_download_route_ignores_malformed_manifest_and_rejects_symlink_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _write_run(tmp_path)
    write_operation_report(run_dir.name, root=tmp_path)
    (run_dir / "artifact_manifest.json").write_text("{malformed", encoding="utf-8")
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.resolve_operation_report_download",
        lambda run_id, filename: resolve_operation_report_download(run_id, filename, root=tmp_path),
    )
    app = FastAPI()
    add_fundamentals_admin_download_route(app)
    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/fundamentals/admin/reports/{run_id}/{filename:path}"
    )
    assert Path(asyncio.run(route.endpoint(run_dir.name, OPERATION_REPORT_NAME)).path).is_file()

    (run_dir / OPERATION_REPORT_NAME).unlink()
    (run_dir / OPERATION_REPORT_NAME).symlink_to(tmp_path / "outside.md")
    with pytest.raises(HTTPException) as error:
        asyncio.run(route.endpoint(run_dir.name, OPERATION_REPORT_NAME))
    assert error.value.status_code == 404


def test_existing_fundamentals_company_report_download_route_still_serves_exact_bytes(tmp_path: Path) -> None:
    report = tmp_path / "NVDA_2026-09-06.md"
    report.write_text("# NVDA\n", encoding="utf-8")
    app = FastAPI()
    add_fundamentals_download_route(app, report_dir=tmp_path)
    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/fundamentals/reports/{filename:path}"
    )

    response = asyncio.run(route.endpoint("NVDA_2026-09-06.md"))

    assert Path(response.path).read_bytes() == report.read_bytes()
    assert response.headers["content-type"].startswith("text/markdown")
    with pytest.raises(HTTPException) as error:
        asyncio.run(route.endpoint("../secrets.md"))
    assert error.value.status_code == 404


def test_admin_ui_service_runs_preview_through_backend_boundary_and_finalizes_report(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_preview(raw_inputs, *, run_root, market, network_allowed, progress_callback):
        calls.append(
            {
                "raw_inputs": raw_inputs,
                "run_root": run_root,
                "market": market,
                "network_allowed": network_allowed,
            }
        )
        run_dir = _write_run(run_root)
        payload = run_dir / "phase13d_preview_payload.json"
        payload.write_text("{}", encoding="utf-8")
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        result["artifact_dir"] = str(run_dir)
        result["phase13d_preview_payload_path"] = str(payload)
        return result

    service = FundamentalsAdminUIService(run_root=tmp_path, add_preview=fake_preview)

    result = service.preview(
        "ADD_TICKERS",
        raw_inputs="nvda",
        market="usa",
        network_allowed=False,
    )

    assert calls == [{"raw_inputs": "nvda", "run_root": tmp_path.resolve(), "market": "usa", "network_allowed": False}]
    assert result.status == "COMPLETED"
    assert result.preview_payload_path.endswith("phase13d_preview_payload.json")
    assert result.report_filename == OPERATION_REPORT_NAME
    assert (tmp_path / result.run_id / OPERATION_REPORT_NAME).is_file()
    assert service.history_entries(limit=1)[0].report_available is True


def test_admin_page_exposes_four_operations_and_downloads_exact_report() -> None:
    class Service:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.apply_calls: list[dict[str, object]] = []

        def history_entries(self, *, limit, include_technical=False):
            return [
                AdminUIHistoryEntry(
                    run_id="run1",
                    operation_type="ADD_TICKERS",
                    outcome="COMPLETED",
                    status="completed",
                    mode="PREVIEW",
                    completed_at_utc="2026-09-16T12:01:00Z",
                    report_available=True,
                )
            ]

        def progress(self, run_id):
            return AdminRunHistory(Path("/tmp/does-not-exist")).progress(run_id)

        def preview(self, operation_type, **kwargs):
            self.calls.append({"operation_type": operation_type, **kwargs})
            kwargs["progress_callback"](
                {
                    "current_stage_number": 1,
                    "total_declared_stages": 2,
                    "current_stage_id": "PREFLIGHT",
                    "stage_state": "RUNNING",
                    "message": "Working",
                }
            )
            return AdminUIRunResult(
                status="COMPLETED",
                message="Preview completed.",
                run_id="run2",
                outcome="COMPLETED",
                mode="PREVIEW",
                preview_fingerprint="f" * 64,
                preview_payload_path="/tmp/payload.json",
                report_filename=OPERATION_REPORT_NAME,
                report_sha256="a" * 64,
                summary_rows=("Operation: ADD_TICKERS", "Outcome: COMPLETED"),
            )

        def copy_apply(self, operation_type, **kwargs):
            assert controls.preview_button.disabled is True
            assert controls.copy_apply_button.disabled is True
            assert controls.production_apply_button.disabled is True
            assert controls.full_workflow_button.disabled is True
            self.apply_calls.append({"operation_type": operation_type, **kwargs})
            return AdminUIRunResult(
                status="COMPLETED",
                message="Apply completed.",
                run_id="run3",
                outcome="COMPLETED",
                mode="COPY_ONLY_APPLY",
                preview_fingerprint="f" * 64,
                report_filename=OPERATION_REPORT_NAME,
                report_sha256="b" * 64,
                summary_rows=("Operation: ADD_TICKERS", "Outcome: COMPLETED"),
            )

    page = _Page()
    service = Service()
    controls = build_fundamentals_admin_page(page=page, service=service)

    assert [option.key for option in controls.operation_dropdown.options] == [
        "ADD_TICKERS",
        "REFRESH_FUNDAMENTALS",
        "CHECK_UPDATE_SECTOR_INDUSTRY",
        "CHECK_UPDATE_TAXONOMY",
    ]
    assert controls.network_allowed_checkbox.visible is False
    assert controls.preview_payload_field.visible is False
    assert controls.preview_payload_field.read_only is True
    assert controls.preview_fingerprint_field.visible is False
    assert controls.preview_fingerprint_field.read_only is True
    assert controls.production_confirmation_field.visible is False
    assert controls.production_confirmation_field.read_only is True
    assert controls.taxonomy_domain_dropdown.visible is False
    assert controls.candidate_path_field.visible is False
    controls.tickers_field.value = "NVDA"
    controls.tickers_field.on_change(None)
    assert controls.full_workflow_button.disabled is False
    controls.preview_button.on_click(None)

    assert service.calls[0]["operation_type"] == "ADD_TICKERS"
    assert service.calls[0]["network_allowed"] is True
    assert "Preview completed." in controls.status_field.value
    assert controls.preview_payload_field.value == "/tmp/payload.json"
    assert controls.summary_column.controls[0].value == "Operation: ADD_TICKERS"
    assert "PREFLIGHT" in controls.progress_field.value
    assert controls.preview_section.visible is True
    assert controls.progress_section.visible is True
    assert controls.final_section.visible is False
    assert controls.report_button.visible is True
    assert controls.copy_apply_button.disabled is False
    assert controls.production_apply_button.disabled is True
    assert controls.copy_apply_button.visible is True
    assert controls.full_workflow_button.disabled is True
    controls.copy_apply_button.on_click(None)
    assert service.apply_calls[0]["preview_payload_path"] == "/tmp/payload.json"
    assert service.apply_calls[0]["preview_fingerprint"] == "f" * 64
    assert controls.copy_apply_button.visible is True
    assert controls.copy_apply_button.disabled is True
    assert controls.production_apply_button.disabled is False
    controls.tickers_field.value = "MSFT"
    controls.tickers_field.on_change(None)
    assert controls.copy_apply_button.disabled is True
    assert controls.production_apply_button.disabled is True
    assert "preview is no longer current" in controls.status_field.value
    controls.history_column.controls[0].controls[-1].on_click(None)
    assert page.launched_urls == [admin_report_download_url("run1")]
    assert controls.preview_button.disabled is False


def test_admin_page_conditional_fields_switch_by_operation() -> None:
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=FundamentalsAdminUIService())

    assert controls.tickers_field.visible is True
    assert controls.taxonomy_domain_dropdown.visible is False
    assert controls.candidate_path_field.visible is False
    assert controls.network_allowed_checkbox.visible is False

    controls.operation_dropdown.value = "CHECK_UPDATE_SECTOR_INDUSTRY"
    controls.operation_dropdown.on_change(None)
    assert controls.tickers_field.visible is False
    assert controls.market_field.visible is True
    assert controls.taxonomy_domain_dropdown.visible is False
    assert controls.candidate_path_field.visible is False
    assert "ticker_meta" in controls.operation_guidance_field.value

    controls.operation_dropdown.value = "CHECK_UPDATE_TAXONOMY"
    controls.operation_dropdown.on_change(None)
    assert controls.tickers_field.visible is False
    assert controls.market_field.visible is False
    assert controls.taxonomy_domain_dropdown.visible is False
    assert controls.candidate_path_field.visible is False
    assert "dc_ecosystem" in controls.operation_guidance_field.value


def test_production_confirmation_uses_internal_token_and_waits_for_confirm() -> None:
    class Service:
        def __init__(self) -> None:
            self.production_calls: list[dict[str, object]] = []

        def history_entries(self, *, limit, include_technical=False):
            return []

        def progress(self, run_id):
            raise FileNotFoundError

        def preview(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED",
                message="Preview completed.",
                run_id="run2",
                outcome="COMPLETED",
                mode="PREVIEW",
                preview_fingerprint="f" * 64,
                preview_payload_path="/tmp/payload.json",
                report_filename=OPERATION_REPORT_NAME,
                report_sha256="a" * 64,
                summary_rows=("Operation: ADD_TICKERS", "Outcome: COMPLETED"),
            )

        def copy_apply(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED", message="Test completed.", run_id="copy-run",
                outcome="COMPLETED", mode="COPY_ONLY_APPLY", preview_fingerprint="f" * 64,
            )

        def production_apply(self, operation_type, **kwargs):
            assert controls.preview_button.disabled is True
            assert controls.copy_apply_button.disabled is True
            assert controls.production_apply_button.disabled is True
            self.production_calls.append({"operation_type": operation_type, **kwargs})
            return AdminUIRunResult(
                status="COMPLETED",
                message="Production completed.",
                run_id="run3",
                outcome="COMPLETED",
                mode="PRODUCTION",
                report_filename=OPERATION_REPORT_NAME,
                report_sha256="b" * 64,
                summary_rows=("Operation: ADD_TICKERS", "Outcome: COMPLETED"),
            )

    page = _Page()
    service = Service()
    controls = build_fundamentals_admin_page(page=page, service=service)
    controls.tickers_field.value = "NVDA"
    controls.tickers_field.on_change(None)
    controls.preview_button.on_click(None)

    controls.production_apply_button.on_click(None)

    assert service.production_calls == []
    assert page.opened_dialogs == []
    controls.copy_apply_button.on_click(None)
    controls.production_apply_button.on_click(None)
    assert page.opened_dialogs
    page.opened_dialogs[-1].actions[1].on_click(None)
    assert service.production_calls[0]["confirmation"] == "CONFIRM_PRODUCTION_BATCH_ADD_TICKERS"
    assert service.production_calls[0]["preview_payload_path"] == "/tmp/payload.json"
    assert service.production_calls[0]["preview_fingerprint"] == "f" * 64
    assert service.production_calls[0]["test_run_id"] == "copy-run"


def test_apply_visibility_follows_backend_capability() -> None:
    class Service:
        def capabilities(self):
            return (
                AdminOperationCapability("ADD_TICKERS", True, False, False),
            )

        def history_entries(self, *, limit, include_technical=False):
            return []

        def preview(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED",
                message="Preview completed.",
                run_id="run2",
                outcome="COMPLETED",
                mode="PREVIEW",
                preview_fingerprint="f" * 64,
                preview_payload_path="/tmp/payload.json",
                report_filename=OPERATION_REPORT_NAME,
                report_sha256="a" * 64,
                summary_rows=("Operation: ADD_TICKERS", "Outcome: COMPLETED"),
            )

    controls = build_fundamentals_admin_page(page=_Page(), service=Service())
    controls.tickers_field.value = "NVDA"
    controls.tickers_field.on_change(None)
    controls.preview_button.on_click(None)

    assert controls.copy_apply_button.visible is False
    assert controls.production_apply_button.visible is False


def test_refresh_fundamentals_is_input_free_preview_and_test_only() -> None:
    class Service:
        def capabilities(self):
            return (AdminOperationCapability("REFRESH_FUNDAMENTALS", True, True, False),)

        def history_entries(self, *, limit, include_technical=False):
            return []

    controls = build_fundamentals_admin_page(page=_Page(), service=Service())
    controls.operation_dropdown.value = "REFRESH_FUNDAMENTALS"
    controls.operation_dropdown.on_change(None)

    assert controls.tickers_field.visible is False
    assert controls.preview_button.disabled is False
    assert controls.copy_apply_button.visible is False
    assert controls.production_apply_button.visible is False
    assert controls.full_workflow_button.visible is False
    assert "read-only" in controls.operation_guidance_field.value


@pytest.mark.parametrize(
    ("outcome", "test_visible"),
    [("COMPLETED", True), ("NO_CHANGE", False), ("REVIEW_REQUIRED", False)],
)
def test_refresh_test_action_requires_authorized_changing_preview(outcome: str, test_visible: bool) -> None:
    class Service:
        def capabilities(self):
            return (AdminOperationCapability("REFRESH_FUNDAMENTALS", True, True, False),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def preview(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED", message="Preview completed.", run_id="refresh-preview",
                outcome=outcome, mode="PREVIEW", preview_fingerprint="f" * 64,
                preview_payload_path="/tmp/refresh-preview.json",
            )

    controls = build_fundamentals_admin_page(page=_Page(), service=Service())
    controls.operation_dropdown.value = "REFRESH_FUNDAMENTALS"
    controls.operation_dropdown.on_change(None)
    controls.preview_button.on_click(None)
    assert controls.copy_apply_button.visible is test_visible
    assert controls.production_apply_button.visible is False
    assert controls.full_workflow_button.visible is False


def _taxonomy_preview_result(*, outcome="COMPLETED", counts=None, blockers=None, candidate=None, mode="CURRENT_STATE_AUDIT"):
    return {
        "run_id": "taxonomy_fixture",
        "operation_type": "CHECK_UPDATE_TAXONOMY",
        "mode": mode,
        "outcome": outcome,
        "taxonomy_domain": "dc_ecosystem",
        "started_at_utc": "2026-09-18T08:10:31Z",
        "completed_at_utc": "2026-09-18T08:14:45Z",
        "preview_fingerprint": "f" * 64,
        "summary_counts": counts if counts is not None else {"UNCHANGED": 350, "automatic_apply_eligible": 0, "blocked": 0},
        "downstream": {
            "active_taxonomy": {"domain": "dc_ecosystem", "version": {"taxonomy_version_code": "DC_TAXONOMY_FULL_V2_1"}, "counts": {"rows": 350, "tickers": 257}},
            "candidate": candidate,
            "dependency_reasoning": {"package_invocations": 0, "relative_position_invocations": 0},
        },
        "blockers": blockers or [],
    }


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({}, "NO_CHANGE"),
        ({"summary_counts": {"MEMBERSHIP_ADDED": 1, "automatic_apply_eligible": 0, "blocked": 0}}, "REVIEW_REQUIRED"),
        ({"summary_counts": {"MEMBERSHIP_ADDED": 1, "automatic_apply_eligible": 1, "blocked": 0}}, "CHANGES_AVAILABLE"),
        ({"blockers": [{"status": "UNRESOLVED_IDENTITY"}]}, "BLOCKED"),
        ({"outcome": "FAILED"}, "FAILED"),
    ],
)
def test_taxonomy_business_outcome_uses_structured_evidence(updates, expected) -> None:
    result = _taxonomy_preview_result()
    result.update(updates)
    assert taxonomy_preview_presentation(result)["business_outcome"] == expected


def test_taxonomy_no_change_summary_report_and_retained_run() -> None:
    retained = Path(__file__).resolve().parents[1] / "fundamental_reports/admin_runs/20260918T081031Z_check_update_taxonomy_dcb015ad6e99_dc_ecosystem_preview/result.json"
    result = json.loads(retained.read_text(encoding="utf-8")) if retained.exists() else _taxonomy_preview_result()
    info = taxonomy_preview_presentation(result)
    assert info["business_outcome"] == "NO_CHANGE"
    assert info["memberships"] == 350
    assert info["tickers"] == 257
    summary = build_operation_summary(result)
    report = render_operation_report(run_id=result["run_id"], result=result)
    assert summary[0] == "Taxonomy is up to date"
    assert "No changes" in summary
    assert "350 memberships checked." in summary
    assert "257 tickers checked." in summary
    assert "No production writes. No update is required." in summary
    assert "Potential downstream work was evaluated. No calculations were run during Preview." in summary
    assert "0 additions and 0 removals." in report
    assert "0 role or tier changes and 0 primary-membership changes." in report
    assert "0 review blockers." in report
    assert "Preview fingerprint:" in report
    assert result["preview_fingerprint"] not in "\n".join(summary)


def test_taxonomy_no_change_ui_has_one_summary_and_no_actions() -> None:
    class Service:
        def capabilities(self):
            return (AdminOperationCapability("CHECK_UPDATE_TAXONOMY", True, True, True),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def preview(self, operation_type, **kwargs):
            callback = kwargs["progress_callback"]
            callback({"current_stage_number": 2, "total_declared_stages": 17, "current_stage_id": "LOAD_ACTIVE_TAXONOMY", "stage_state": "RUNNING", "message": "Checking"})
            assert controls.progress_details.controls[0].expanded is True
            callback({"current_stage_number": 17, "total_declared_stages": 17, "current_stage_id": "COMPLETED", "stage_state": "COMPLETED", "message": "Done"})
            result = _taxonomy_preview_result()
            return AdminUIRunResult(
                status="COMPLETED", message="Preview completed.", run_id=result["run_id"],
                outcome="COMPLETED", mode="CURRENT_STATE_AUDIT", preview_domain="dc_ecosystem",
                business_outcome="NO_CHANGE", copy_actionable=False, production_actionable=False,
                preview_payload_path="/tmp/taxonomy_preview_payload.json", preview_fingerprint=result["preview_fingerprint"],
                report_filename=OPERATION_REPORT_NAME, report_sha256="a" * 64,
                summary_rows=build_operation_summary(result),
            )

    controls = build_fundamentals_admin_page(page=_Page(), service=Service())
    controls.operation_dropdown.value = "CHECK_UPDATE_TAXONOMY"
    controls.operation_dropdown.on_change(None)
    controls.preview_button.on_click(None)
    visible_text = "\n".join(control.value for control in controls.summary_column.controls)
    assert controls.preview_section.controls[0].value == "Taxonomy is up to date"
    assert "No changes" in visible_text
    assert "350 memberships checked." in visible_text
    assert "No update is required." in visible_text
    assert "f" * 64 not in visible_text
    assert "a" * 64 not in visible_text
    assert "CHECK_UPDATE_TAXONOMY" not in visible_text
    assert controls.final_section.visible is False
    assert controls.copy_apply_button.visible is False
    assert controls.copy_apply_button.disabled is True
    assert controls.production_apply_button.visible is False
    assert controls.production_apply_button.disabled is True
    assert controls.progress_summary.value == "17 of 17 stages completed"
    assert controls.progress_details.controls[0].expanded is True
    technical = "\n".join(control.value for control in controls.technical_details_column.controls)
    assert "f" * 64 in technical
    assert "a" * 64 in technical
    assert controls.report_button.visible is True


def test_taxonomy_service_action_gates_require_candidate_and_authorized_provenance(tmp_path: Path) -> None:
    service = FundamentalsAdminUIService(run_root=tmp_path)
    changed = _taxonomy_preview_result(
        mode="CANDIDATE_PREVIEW",
        counts={"MEMBERSHIP_ADDED": 1, "automatic_apply_eligible": 1, "blocked": 0},
        candidate={"taxonomy_version": "NEXT"},
    )
    for payload, copy_allowed, production_allowed in (
        (changed, True, False),
        ({**changed, "downstream": {**changed["downstream"], "candidate": None}}, False, False),
        ({**changed, "mode": "PROTECTED_PRODUCTION_PREVIEW", "downstream": {**changed["downstream"], "candidate": {"provenance": "TEST_ONLY_NOT_FOR_PRODUCTION"}}}, False, False),
        ({**changed, "mode": "PROTECTED_PRODUCTION_PREVIEW", "downstream": {**changed["downstream"], "candidate": {"provenance": "CURATED_PRODUCTION_CANDIDATE"}}}, False, False),
        ({**changed, "mode": "ACTIVE_TAXONOMY_PREVIEW"}, True, True),
    ):
        run_dir = tmp_path / payload["run_id"]
        run_dir.mkdir(exist_ok=True)
        (run_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        final = service._finalize(payload, default_message="Preview completed.")
        assert final.copy_actionable is copy_allowed
        assert final.production_actionable is production_allowed


def test_taxonomy_changed_preview_requires_capability_and_fresh_matching_scope() -> None:
    class Service:
        def __init__(self):
            self.copy_enabled = True

        def capabilities(self):
            return (AdminOperationCapability("CHECK_UPDATE_TAXONOMY", True, self.copy_enabled, True),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def preview(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED", message="Preview completed.", run_id="changed",
                outcome="COMPLETED", mode="ACTIVE_TAXONOMY_PREVIEW", business_outcome="CHANGES_AVAILABLE",
                preview_domain="dc_ecosystem", copy_actionable=True, production_actionable=False,
                preview_payload_path="/tmp/taxonomy_candidate.json", preview_fingerprint="f" * 64,
                summary_rows=("Changes available",),
            )

    service = Service()
    controls = build_fundamentals_admin_page(page=_Page(), service=service)
    controls.operation_dropdown.value = "CHECK_UPDATE_TAXONOMY"
    controls.operation_dropdown.on_change(None)
    controls.preview_button.on_click(None)
    assert controls.copy_apply_button.visible is True
    assert controls.production_apply_button.visible is False
    controls.taxonomy_domain_dropdown.value = "ec_taxonomy"
    controls.taxonomy_domain_dropdown.on_change(None)
    assert controls.copy_apply_button.visible is False
    assert controls.copy_apply_button.disabled is True

    service.copy_enabled = False
    controls = build_fundamentals_admin_page(page=_Page(), service=service)
    controls.operation_dropdown.value = "CHECK_UPDATE_TAXONOMY"
    controls.operation_dropdown.on_change(None)
    controls.preview_button.on_click(None)
    assert controls.copy_apply_button.visible is False


def test_history_selection_displays_progress_and_unavailable_report_state(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path, "20260916T130000Z_add_tickers_no_change")
    (run_dir / OPERATION_REPORT_NAME).unlink(missing_ok=True)

    class Service(FundamentalsAdminUIService):
        def __init__(self) -> None:
            super().__init__(run_root=tmp_path)

    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=Service())

    controls.history_column.controls[0].controls[-2].on_click(None)

    assert "20260916T130000Z_add_tickers_no_change" in controls.history_detail_field.value
    assert "Operation report: not yet available" in controls.history_detail_field.value
    assert "Selected run progress loaded" in controls.progress_field.value


def test_history_defaults_to_admin_runs_and_filter_exposes_technical_evidence(tmp_path: Path) -> None:
    _write_run(tmp_path, "20260916T130000Z_add_tickers_admin")
    evidence = tmp_path / "phase13h1_1_acceptance"
    evidence.mkdir()
    (evidence / "acceptance_summary.json").write_text("{}", encoding="utf-8")
    (tmp_path / "empty_broken_run").mkdir()
    service = FundamentalsAdminUIService(run_root=tmp_path)

    default = service.history_entries(limit=10)
    technical = service.history_entries(limit=10, include_technical=True)

    assert [entry.category for entry in default] == ["Administration run"]
    assert any(entry.category == "Acceptance/test evidence" for entry in technical)
    assert any(entry.category == "Invalid or corrupt run" for entry in technical)


def _retained_taxonomy_result() -> dict:
    retained = Path(__file__).resolve().parents[1] / "fundamental_reports/admin_runs/20260918T085757Z_check_update_taxonomy_dcb015ad6e99_dc_ecosystem_preview/result.json"
    result = json.loads(retained.read_text(encoding="utf-8")) if retained.exists() else _taxonomy_preview_result()
    return result


def test_retained_taxonomy_history_is_first_and_technical_evidence_stays_separate(tmp_path: Path) -> None:
    result = _retained_taxonomy_result()
    run_dir = tmp_path / result["run_id"]
    run_dir.mkdir()
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (run_dir / "progress_status.json").write_text(json.dumps({
        "current_stage_id": "COMPLETED", "current_stage_number": 17,
        "total_declared_stages": 17, "stage_state": "COMPLETED",
    }), encoding="utf-8")
    write_operation_report(run_dir.name, root=tmp_path)
    phase = tmp_path / "phase13h1_2_ui_simplification"
    phase.mkdir()
    phase_result = {
        "run_id": phase.name, "operation_type": "ADD_TICKERS", "mode": "UI_SIMPLIFICATION_SYNTHETIC_NO_PRODUCTION_WRITE",
        "outcome": "COMPLETED", "completed_at_utc": "2026-09-19T10:00:00Z",
    }
    (phase / "result.json").write_text(json.dumps(phase_result), encoding="utf-8")
    service = FundamentalsAdminUIService(run_root=tmp_path)
    visible = service.history_entries(limit=12)
    all_entries = service.history_entries(limit=12, include_technical=True)
    assert [entry.run_id for entry in visible] == [result["run_id"]]
    assert visible[0].category == "Administration run"
    assert visible[0].outcome == "NO_CHANGE"
    assert visible[0].completed_at_utc == result["completed_at_utc"]
    assert visible[0].count_label == "350 memberships"
    assert visible[0].report_available is True
    assert all_entries[0].run_id == result["run_id"]
    assert any(entry.run_id == phase.name and entry.category != "Administration run" for entry in all_entries)
    assert "350 memberships checked." in service.history_result_summary(result["run_id"])


def test_malformed_or_symlinked_history_result_is_not_an_admin_run(tmp_path: Path) -> None:
    malformed = _write_run(tmp_path, "20260918T120000Z_add_tickers_malformed")
    (malformed / "result.json").write_text("{invalid", encoding="utf-8")
    linked = _write_run(tmp_path, "20260918T120100Z_add_tickers_linked")
    (linked / "result.json").unlink()
    (linked / "result.json").symlink_to(malformed / "result.json")
    service = FundamentalsAdminUIService(run_root=tmp_path)
    assert service.history_entries() == []
    assert all(item.category == "Invalid or corrupt run" for item in service.history_entries(include_technical=True))
    with pytest.raises(ValueError):
        service.history_result_summary(linked.name)


def test_retained_taxonomy_report_has_human_sections_and_is_deterministic() -> None:
    result = _retained_taxonomy_result()
    report = render_operation_report(run_id=result["run_id"], result=result)
    assert report == render_operation_report(run_id=result["run_id"], result=result)
    main, appendix = report.split("## Technical Appendix", 1)
    for section in (
        "Executive Summary", "What Was Checked", "Changes Found", "Actions Performed",
        "Downstream Impact", "Warnings or Blockers", "Final Result",
    ):
        assert f"## {section}" in main
    for fact in (
        "dc_ecosystem", "DC_TAXONOMY_FULL_V2_1", "257 tickers", "350 memberships",
        "No additions or removals", "No role or tier changes", "No primary-membership changes",
        "No warnings or blockers", "No database writes", "No calculations were run during Preview",
        "No further action is required",
    ):
        assert fact in main
    for clutter in ("/home/kalle/", "None", "[]", "{", "NOT_RECORDED", "COMPLETED RUNNING", result["preview_fingerprint"]):
        assert clutter not in main
    assert result["preview_fingerprint"] in appendix


def test_history_refresh_after_taxonomy_preview_and_action_label(tmp_path: Path) -> None:
    result = _taxonomy_preview_result()
    result["run_id"] = "20260918T120000Z_check_update_taxonomy_fixture_preview"
    result["completed_at_utc"] = "2026-09-18T12:04:00Z"

    def preview(*, taxonomy_domain, candidate_path, candidate_version, run_root, progress_callback):
        run_dir = run_root / result["run_id"]
        run_dir.mkdir()
        payload = run_dir / "taxonomy_preview_payload.json"
        payload.write_text("{}", encoding="utf-8")
        stored = {**result, "preview_payload_path": str(payload), "artifact_dir": str(run_dir)}
        (run_dir / "result.json").write_text(json.dumps(stored), encoding="utf-8")
        (run_dir / "progress_status.json").write_text(json.dumps({
            "operation_type": "CHECK_UPDATE_TAXONOMY", "current_stage_id": "COMPLETED",
            "current_stage_number": 17, "total_declared_stages": 17, "stage_state": "COMPLETED",
        }), encoding="utf-8")
        return stored

    service = FundamentalsAdminUIService(run_root=tmp_path, taxonomy_preview=preview)
    controls = build_fundamentals_admin_page(page=_Page(), service=service)
    assert controls.copy_apply_button.text == "Test on copies"
    assert controls.history_column.controls[0].value == "No administration runs found."
    controls.operation_dropdown.value = "CHECK_UPDATE_TAXONOMY"
    controls.operation_dropdown.on_change(None)
    controls.preview_button.on_click(None)
    row = controls.history_column.controls[0]
    assert row.controls[1].value == "Taxonomy"
    assert row.controls[2].value == "Preview"
    assert row.controls[3].value == "No changes"
    assert row.controls[4].value == "350 memberships"
    assert row.controls[5].value == "Administration run"
    assert controls.copy_apply_button.visible is False
    assert controls.production_apply_button.visible is False
    row.controls[-2].on_click(None)
    assert "Taxonomy is up to date" in controls.history_detail_field.value
    assert "17/17" in controls.history_detail_field.value
    assert "Operation report: available" in controls.history_detail_field.value
    row.controls[-1].on_click(None)
    assert controls.report_button.visible is True


@pytest.mark.parametrize(
    ("outcome", "failed_stage", "expected"),
    [
        ("COMPLETED", None, "Production update completed successfully."),
        ("FAILED", "PREFLIGHT", "Production update failed before any production database changes were made."),
        ("FAILED_ROLLED_BACK", "POSTFLIGHT", "All production database changes were rolled back successfully."),
        ("CRITICAL_ROLLBACK_FAILED", "POSTFLIGHT", "Immediate operator review is required."),
    ],
)
def test_production_final_status_is_derived_from_backend_outcome(outcome, failed_stage, expected) -> None:
    result = {"mode": "PRODUCTION_APPLY", "outcome": outcome, "failed_stage": failed_stage}
    message = final_status_message(result)
    assert expected in message
    if outcome != "COMPLETED":
        assert message != "Production update completed successfully."


def test_progress_details_retain_lines_and_respect_manual_scroll() -> None:
    class Service:
        def capabilities(self):
            return (AdminOperationCapability("ADD_TICKERS", True, True, True),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def preview(self, operation_type, **kwargs):
            callback = kwargs["progress_callback"]
            for number in range(1, 6):
                callback({"current_stage_number": number, "total_declared_stages": 12, "current_stage_id": f"STAGE_{number}", "stage_state": "COMPLETED", "message": f"Line {number}"})
            controls.progress_field.on_scroll(SimpleNamespace(pixels=0, max_scroll_extent=500))
            for number in range(6, 13):
                callback({"current_stage_number": number, "total_declared_stages": 12, "current_stage_id": f"STAGE_{number}", "stage_state": "COMPLETED", "message": f"Line {number}"})
            return AdminUIRunResult(
                status="COMPLETED", message="Preview completed.", run_id="progress-run",
                outcome="COMPLETED", mode="PREVIEW", preview_fingerprint="f" * 64,
                preview_payload_path="/tmp/progress.json", summary_rows=("Preview completed",),
            )

    controls = build_fundamentals_admin_page(page=_Page(), service=Service())
    controls.tickers_field.value = "NVDA"
    controls.tickers_field.on_change(None)
    controls.preview_button.on_click(None)

    assert controls.progress_field.height == 230
    assert len(controls.progress_field.controls) == 13
    assert "STAGE_1" in controls.progress_field.value
    assert "STAGE_12" in controls.progress_field.value
    assert controls.progress_field.auto_scroll is False
    assert controls.progress_summary.value == "12 of 12 stages completed"
    assert controls.progress_details.controls[0].expanded is True


def test_add_tickers_reports_use_stage_and_user_facing_language() -> None:
    preview = {
        "run_id": "preview-run", "operation_type": "ADD_TICKERS", "mode": "PREVIEW",
        "outcome": "COMPLETED", "started_at_utc": "2026-09-19T10:00:00Z",
        "completed_at_utc": "2026-09-19T10:00:05Z", "summary_counts": {"eligible": 1},
        "items": [{"ticker": "TSEM", "status": "ELIGIBLE", "reason": "Eligible from provider identity, price, classification and fundamentals evidence."}],
    }
    copy = {
        **preview, "run_id": "copy-run", "mode": "COPY_ONLY_APPLY",
        "summary_counts": {"applied": 1},
        "items": [{"ticker": "TSEM", "status": "APPLIED", "reason": "Applied on copy-lane."}],
    }
    preview_report = render_operation_report(run_id="preview-run", result=preview)
    copy_report = render_operation_report(run_id="copy-run", result=copy)

    assert "Stage: Preview" in preview_report
    assert "TSEM: Eligible - provider identity" in preview_report
    assert "Eligible - Eligible" not in preview_report
    assert ".." not in preview_report
    assert "Next step: run Test on copies." in preview_report
    assert "Stage: Test on copies" in copy_report
    assert "TSEM: Successfully tested on copies." in copy_report
    assert "copy-lane" not in copy_report
    assert "Next step: Production update is available" in copy_report


def test_failed_preview_is_visible_downloadable_and_has_technical_details(tmp_path: Path) -> None:
    run_id = "20260919T120000Z_add_tickers_failure1234"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    request = {
        "operation_type": "ADD_TICKERS",
        "requested_inputs": ["STM", "TECK", "TEM"],
        "normalized_inputs": ["STM", "TECK", "TEM"],
        "options": {"contract_version": "test"},
    }
    result = {
        "run_id": run_id,
        "artifact_dir": str(run_dir),
        "operation_type": "ADD_TICKERS",
        "mode": "PREVIEW",
        "outcome": "FAILED",
        "failed_stage": "SOURCE_RESOLUTION",
        "started_at_utc": "2026-09-19T12:00:00Z",
        "completed_at_utc": "2026-09-19T12:00:03Z",
        "request": request,
        "summary_counts": {"requested": 3, "failed": 3},
        "database_safety": "NO_DATABASE_WRITES",
        "errors": [{"type": "TimeoutError", "message": "provider timed out"}],
    }
    (run_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (run_dir / "progress_status.json").write_text(json.dumps({
        "operation_type": "ADD_TICKERS", "current_stage_id": "SOURCE_RESOLUTION",
        "current_stage_number": 3, "total_declared_stages": 19, "stage_state": "FAILED",
    }), encoding="utf-8")

    service = FundamentalsAdminUIService(run_root=tmp_path)
    finalized = service._finalize(result, default_message="unused")
    history = service.history_entries(limit=1)

    assert finalized.status == "FAILED"
    assert finalized.message == "Preview failed during source resolution. No database changes were made."
    assert finalized.failure_stage == "SOURCE_RESOLUTION"
    assert finalized.exception_type == "TimeoutError"
    assert finalized.technical_error == "provider timed out"
    assert finalized.report_sha256
    assert service.resolve_report_download(run_id).name == OPERATION_REPORT_NAME
    assert len(history) == 1
    assert (history[0].stage, history[0].outcome, history[0].count_label) == ("Preview", "FAILED", "3 items")


def test_successful_add_tickers_production_clears_batch_and_next_preview_submits_visible_value() -> None:
    class Service:
        def __init__(self) -> None:
            self.preview_inputs: list[str] = []

        def capabilities(self):
            return (AdminOperationCapability("ADD_TICKERS", True, True, True),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def preview(self, operation_type, **kwargs):
            self.preview_inputs.append(kwargs["raw_inputs"])
            sequence = len(self.preview_inputs)
            return AdminUIRunResult(
                status="COMPLETED", message="Preview completed.", run_id=f"preview-{sequence}",
                outcome="COMPLETED", mode="PREVIEW", preview_fingerprint=f"fp-{sequence}",
                preview_payload_path=f"/tmp/preview-{sequence}.json", summary_rows=("Preview completed.",),
            )

        def copy_apply(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED", message="Test on copies completed successfully.", run_id="copy-1",
                outcome="COMPLETED", mode="COPY_ONLY_APPLY", preview_fingerprint="fp-1",
            )

        def production_apply(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED", message="Production update completed successfully.", run_id="prod-1",
                outcome="COMPLETED", mode="PRODUCTION_APPLY",
            )

    service = Service()
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)
    old_batch = " ".join(f"OLD{number}" for number in range(20))
    controls.tickers_field.value = old_batch
    controls.tickers_field.on_change(None)
    controls.preview_button.on_click(None)
    controls.copy_apply_button.on_click(None)
    controls.production_apply_button.on_click(None)
    page.dialog.actions[1].on_click(None)

    assert controls.tickers_field.value == ""
    assert controls.copy_apply_button.disabled is True
    assert controls.production_apply_button.disabled is True
    controls.tickers_field.value = "STM TECK TEM"
    controls.tickers_field.on_change(None)
    controls.preview_button.on_click(None)

    assert service.preview_inputs == [old_batch, "STM TECK TEM"]
    assert "1 to 25 tickers" in controls.operation_guidance_field.value


def test_production_preflight_failure_report_is_plain_and_technical_details_are_secondary() -> None:
    result = {
        "run_id": "production-failure", "operation_type": "ADD_TICKERS", "mode": "PRODUCTION_APPLY",
        "outcome": "FAILED", "failed_stage": "PREFLIGHT",
        "started_at_utc": "2026-09-19T10:00:00Z", "completed_at_utc": "2026-09-19T10:00:03Z",
        "preview_fingerprint": "f" * 64, "error": "PermissionError: INTERNAL_PATH_FAILURE",
    }
    report = render_production_report(result)
    main, appendix = report.split("## Technical Appendix", 1)

    assert "Operation: Add Tickers" in main
    assert "Stage: Production update" in main
    assert "Result: Failed" in main
    assert "Failure phase" not in main
    assert "No production database writes were performed." in main
    assert "No backup was required." in main
    assert "No rollback was required." in main
    assert "Requested change: null" not in report
    assert "Failure phase: `PREFLIGHT`" in appendix
    assert "PermissionError: INTERNAL_PATH_FAILURE" in appendix


def test_retryable_production_failure_keeps_preview_test_and_direct_retry_enabled() -> None:
    class Service:
        def __init__(self) -> None:
            self.production_calls = 0

        def capabilities(self):
            return (AdminOperationCapability("ADD_TICKERS", True, True, True),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def preview(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED", message="Preview completed.", run_id="preview-run",
                outcome="COMPLETED", mode="PREVIEW", preview_fingerprint="preview-fp",
                preview_payload_path="/tmp/preview.json",
            )

        def copy_apply(self, operation_type, **kwargs):
            return AdminUIRunResult(
                status="COMPLETED", message="Test completed.", run_id="test-run",
                outcome="COMPLETED", mode="COPY_ONLY_APPLY", preview_fingerprint="preview-fp",
            )

        def production_apply(self, operation_type, **kwargs):
            self.production_calls += 1
            if self.production_calls == 1:
                return AdminUIRunResult(
                    status="FAILED", message="Production lock is temporarily unavailable.", run_id="prod-failed",
                    outcome="FAILED", mode="PRODUCTION_APPLY", preview_fingerprint="preview-fp",
                    preview_payload_path="/tmp/preview.json", test_run_id="test-run",
                    direct_production_retry_available=True,
                )
            return AdminUIRunResult(
                status="COMPLETED", message="Production update completed successfully.", run_id="prod-ok",
                outcome="COMPLETED", mode="PRODUCTION_APPLY",
            )

    service = Service()
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)
    controls.tickers_field.value = "NVDA"
    controls.tickers_field.on_change(None)
    controls.preview_button.on_click(None)
    controls.copy_apply_button.on_click(None)
    controls.production_apply_button.on_click(None)
    page.dialog.actions[1].on_click(None)

    assert service.production_calls == 1
    assert controls.production_apply_button.visible is True
    assert controls.production_apply_button.disabled is False
    assert controls.copy_apply_button.disabled is True
    assert "temporarily unavailable" in controls.status_field.value

    controls.production_apply_button.on_click(None)
    page.dialog.actions[1].on_click(None)
    assert service.production_calls == 2
    assert controls.tickers_field.value == ""


def test_full_workflow_button_disables_conflicting_actions_and_resets_successful_batch() -> None:
    class Service:
        def capabilities(self):
            return (AdminOperationCapability("ADD_TICKERS", True, True, True),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def full_workflow(self, **kwargs):
            assert controls.preview_button.disabled is True
            assert controls.copy_apply_button.disabled is True
            assert controls.production_apply_button.disabled is True
            assert controls.full_workflow_button.disabled is True
            kwargs["progress_callback"]({
                "current_stage_number": 1, "total_declared_stages": 3,
                "current_stage_id": "PREVIEW", "stage_state": "COMPLETED",
                "message": "Preview - Completed",
            })
            kwargs["progress_callback"]({
                "current_stage_number": 2, "total_declared_stages": 3,
                "current_stage_id": "TEST_ON_COPIES", "stage_state": "COMPLETED",
                "message": "Test on copies - Completed",
            })
            kwargs["progress_callback"]({
                "current_stage_number": 3, "total_declared_stages": 3,
                "current_stage_id": "PRODUCTION_UPDATE", "stage_state": "COMPLETED",
                "message": "Production update - Completed",
            })
            return AdminUIRunResult(
                status="COMPLETED", message="Full workflow completed.", run_id="workflow-run",
                outcome="COMPLETED", mode="FULL_WORKFLOW", report_filename="workflow_report.md",
                workflow_stage_run_ids=("preview-run", "test-run", "production-run"),
            )

    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=Service())
    controls.tickers_field.value = "NVDA"
    controls.tickers_field.on_change(None)

    assert controls.full_workflow_button.disabled is False
    assert controls.copy_apply_button.disabled is True
    assert controls.production_apply_button.disabled is True
    controls.full_workflow_button.on_click(None)

    assert "Preview - Completed" in controls.progress_field.value
    assert "Test on copies - Completed" in controls.progress_field.value
    assert "Production update - Completed" in controls.progress_field.value
    assert controls.tickers_field.value == ""
    assert controls.full_workflow_button.disabled is True


def test_full_workflow_test_failure_preserves_preview_for_manual_test_retry() -> None:
    class Service:
        def capabilities(self):
            return (AdminOperationCapability("ADD_TICKERS", True, True, True),)

        def history_entries(self, *, limit, include_technical=False):
            return []

        def full_workflow(self, **kwargs):
            return AdminUIRunResult(
                status="FAILED", message="Test on copies failed.", run_id="workflow-stopped",
                outcome="STOPPED", mode="FULL_WORKFLOW",
                preview_payload_path="/tmp/preview.json", preview_fingerprint="preview-fp",
                direct_test_retry_available=True,
            )

        def copy_apply(self, operation_type, **kwargs):
            raise AssertionError("state assertion does not invoke Test")

    controls = build_fundamentals_admin_page(page=_Page(), service=Service())
    controls.tickers_field.value = "NVDA"
    controls.tickers_field.on_change(None)
    controls.full_workflow_button.on_click(None)

    assert controls.copy_apply_button.visible is True
    assert controls.copy_apply_button.disabled is False
    assert controls.production_apply_button.disabled is True
    assert controls.full_workflow_button.disabled is True
