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
from dev_tools.stock_update_scheduler_ui import add_fundamentals_admin_download_route
from rawcandle.fundamentals.admin.operation_report import (
    OPERATION_REPORT_NAME,
    resolve_operation_report_download,
    write_operation_report,
)
from rawcandle.fundamentals.admin.ui_service import (
    AdminUIHistoryEntry,
    AdminUIRunResult,
    FundamentalsAdminUIService,
)


class _Page:
    def __init__(self) -> None:
        self.update_count = 0
        self.launched_urls: list[str] = []
        self.tasks = []

    def update(self) -> None:
        self.update_count += 1

    def launch_url(self, url: str) -> None:
        self.launched_urls.append(url)

    def run_task(self, coro) -> None:
        self.tasks.append(coro)


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
                "summary_counts": {"ELIGIBLE": 1},
                "downstream": {"package": "NOT_RUN_IN_PREVIEW"},
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

        def history_entries(self, *, limit):
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

    page = _Page()
    service = Service()
    controls = build_fundamentals_admin_page(page=page, service=service)

    assert [option.key for option in controls.operation_dropdown.options] == [
        "ADD_TICKERS",
        "CHECK_UPDATE_SECTOR_INDUSTRY",
        "CHECK_UPDATE_TAXONOMY",
    ]
    controls.tickers_field.value = "NVDA"
    controls.preview_button.on_click(None)

    assert service.calls[0]["operation_type"] == "ADD_TICKERS"
    assert "Status: COMPLETED" in controls.status_field.value
    assert controls.preview_payload_field.value == "/tmp/payload.json"
    assert controls.summary_column.controls[0].value == "Operation: ADD_TICKERS"
    assert "PREFLIGHT" in controls.progress_field.value
    controls.history_column.controls[0].controls[-1].on_click(None)
    assert page.launched_urls == [admin_report_download_url("run1")]
    assert controls.preview_button.disabled is False
