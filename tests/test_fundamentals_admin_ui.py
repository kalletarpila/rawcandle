from __future__ import annotations

import asyncio
import json
from pathlib import Path

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
    resolve_operation_report_download,
    write_operation_report,
)
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
    assert "Provider Network" in text
    assert "Network Allowed" in text
    assert "existing local provider data" in text
    assert "Per-Item Results" in text
    assert "NVDA" in text
    assert "already present" in text
    assert "Progress Timeline" in text
    assert "Work Performed And Downstream" in text
    assert "Backup And Rollback" in text
    assert "Next Required Action" in text
    assert "secret-value" not in text
    assert "[REDACTED]" in text
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


def test_admin_page_exposes_three_operations_and_downloads_exact_report() -> None:
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
            self.apply_calls.append({"operation_type": operation_type, **kwargs})
            return AdminUIRunResult(
                status="COMPLETED",
                message="Apply completed.",
                run_id="run3",
                outcome="COMPLETED",
                mode="COPY_ONLY_APPLY",
                report_filename=OPERATION_REPORT_NAME,
                report_sha256="b" * 64,
                summary_rows=("Operation: ADD_TICKERS", "Outcome: COMPLETED"),
            )

    page = _Page()
    service = Service()
    controls = build_fundamentals_admin_page(page=page, service=service)

    assert [option.key for option in controls.operation_dropdown.options] == [
        "ADD_TICKERS",
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
    controls.preview_button.on_click(None)

    assert service.calls[0]["operation_type"] == "ADD_TICKERS"
    assert service.calls[0]["network_allowed"] is True
    assert "Preview completed." in controls.status_field.value
    assert controls.preview_payload_field.value == "/tmp/payload.json"
    assert controls.summary_column.controls[0].value == "Operation: ADD_TICKERS"
    assert "PREFLIGHT" in controls.progress_field.value
    assert controls.preview_section.visible is True
    assert controls.progress_section.visible is True
    assert controls.final_section.visible is True
    assert controls.report_button.visible is True
    assert controls.copy_apply_button.disabled is False
    assert controls.production_apply_button.disabled is False
    assert controls.copy_apply_button.visible is True
    controls.copy_apply_button.on_click(None)
    assert service.apply_calls[0]["preview_payload_path"] == "/tmp/payload.json"
    assert service.apply_calls[0]["preview_fingerprint"] == "f" * 64
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
    assert controls.taxonomy_domain_dropdown.visible is True
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

        def production_apply(self, operation_type, **kwargs):
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
    assert page.opened_dialogs
    page.opened_dialogs[-1].actions[1].on_click(None)
    assert service.production_calls[0]["confirmation"] == "CONFIRM_PRODUCTION_BATCH_ADD_TICKERS"
    assert service.production_calls[0]["preview_payload_path"] == "/tmp/payload.json"
    assert service.production_calls[0]["preview_fingerprint"] == "f" * 64


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


def test_history_selection_displays_progress_and_unavailable_report_state(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path, "20260916T130000Z_sector_no_change")
    (run_dir / OPERATION_REPORT_NAME).unlink(missing_ok=True)

    class Service(FundamentalsAdminUIService):
        def __init__(self) -> None:
            super().__init__(run_root=tmp_path)

    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=Service())

    controls.history_column.controls[0].controls[-2].on_click(None)

    assert "20260916T130000Z_sector_no_change" in controls.history_detail_field.value
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
