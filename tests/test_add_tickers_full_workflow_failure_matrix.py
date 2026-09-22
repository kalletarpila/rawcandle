from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin import batch_add_tickers
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.test_fundamentals_admin_batch_add_tickers import _archive_row, _generic_paths


@pytest.mark.parametrize(
    ("provider_status", "http_status", "payload", "rows", "reason", "retryable"),
    (
        ("TRANSIENT_FAILURE", 500, None, [], "NETWORK_TRANSIENT_FAILURE", True),
        ("AUTH_FAILED", 401, None, [], "NETWORK_PERMANENT_FAILURE", False),
        ("SUCCESS", 200, [], [], "NO_USABLE_QUARTERLY_HISTORY", False),
        ("SUCCESS", 200, {"unexpected": []}, [], "RESPONSE_SCHEMA_INVALID", False),
        (
            "SUCCESS", 200, None,
            [{key: value for key, value in _archive_row("NEWC").items() if key != "fiscalperiod"}],
            "INCOMPLETE_FISCAL_IDENTITY", False,
        ),
    ),
)
def test_real_preview_acquisition_failure_stops_full_workflow_before_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_status: str,
    http_status: int,
    payload: object,
    rows: list[dict[str, str]],
    reason: str,
    retryable: bool,
) -> None:
    paths = _generic_paths(tmp_path / "databases")
    monkeypatch.setattr(batch_add_tickers, "DEFAULT_ARCHIVE", tmp_path / "missing.zip")

    class Client:
        request_count = 0

        def fundamentals(self, **_kwargs: object) -> SimpleNamespace:
            self.request_count += 1
            return SimpleNamespace(
                ok=provider_status == "SUCCESS",
                status=provider_status,
                auth_status="AUTH_OK" if provider_status == "SUCCESS" else "REQUEST_FAILED",
                http_status=http_status,
                endpoint="fundamentals",
                url="fixture://sharadar/NEWC",
                records=[dict(row) for row in rows],
                payload=payload if payload is not None else [dict(row) for row in rows],
                error="fixture provider failure" if provider_status != "SUCCESS" else "",
            )

    monkeypatch.setattr(batch_add_tickers, "SharadarClient", Client)
    stages: list[str] = []

    def preview(raw_inputs: str, **kwargs: object) -> dict[str, object]:
        return batch_add_tickers.run_preview(
            raw_inputs,
            source_paths=paths,
            run_root=Path(str(kwargs["run_root"])),
            temp_root=tmp_path / "temp",
            network_allowed=True,
            market="usa",
            progress_callback=kwargs.get("progress_callback"),  # type: ignore[arg-type]
        )

    service = FundamentalsAdminUIService(
        run_root=tmp_path / "runs",
        add_preview=preview,
        add_apply=lambda **_kwargs: stages.append("test"),  # type: ignore[arg-type]
        add_production_apply=lambda **_kwargs: stages.append("production"),  # type: ignore[arg-type]
        operation_lock_path=tmp_path / "ui.lock",
        recover_publication_on_startup=False,
    )
    workflow = service.full_workflow(operation_type="ADD_TICKERS", raw_inputs="NEWC")

    assert workflow.outcome == "STOPPED"
    assert stages == []
    durable = json.loads(Path(workflow.artifact_dir, "workflow_result.json").read_text(encoding="utf-8"))
    assert durable["final_completed_stage"] == "Preview"
    problem = durable["terminal_summary"]["problem_items"][0]
    assert problem["ticker"] == "NEWC"
    assert reason in problem["issue_codes"]
    preview_run = durable["stages"][0]["run_id"]
    preview_result = service.history_result_summary(preview_run)
    assert preview_result
    child = service._load_json_file(service.run_root / preview_run / "result.json")
    assert child is not None
    acquisition = child["ticker_reporting"][0]["acquisition"]
    assert acquisition["status"] == (
        "SUCCESS_NO_USABLE_QUARTERLY_HISTORY"
        if reason == "NO_USABLE_QUARTERLY_HISTORY" else reason
    )
    assert bool(acquisition.get("retryable")) is retryable
    assert acquisition["authoritative"] is (reason == "NO_USABLE_QUARTERLY_HISTORY")
