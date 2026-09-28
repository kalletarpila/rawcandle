from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import dev_tools.forecast_scheduler_page as forecast_page
import rawcandle.forecasts.ui_service as ui_service
from rawcandle.cli import forecasts as forecast_cli
from rawcandle.forecasts.hardening import ForecastDailyAlreadyRunningError
from rawcandle.forecasts.scheduler import FORECAST_DAILY_COMMAND
from rawcandle.forecasts.scheduler_config import (
    ForecastSchedulerConfig,
    consume_forecast_skip_next_run,
    read_forecast_scheduler_config,
    set_forecast_skip_next_run,
    validate_forecast_run_time,
    validate_forecast_scheduler_config,
    validate_forecast_timezone,
    write_forecast_scheduler_config,
)


def _config(tmp_path: Path, **updates) -> ForecastSchedulerConfig:
    values = {
        "forecasts_db_path": str(tmp_path / "forecasts.db"),
        "fundamentals_db_path": str(tmp_path / "fundamentals.db"),
        "log_dir": str(tmp_path / "logs"),
        "timezone": "Europe/Helsinki",
        "run_time": "14:00",
        "skip_next_run": False,
    }
    values.update(updates)
    return ForecastSchedulerConfig(**values)


def test_forecast_config_round_trip_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "forecast.json"
    config = _config(tmp_path)
    write_forecast_scheduler_config(path, config)

    assert read_forecast_scheduler_config(path) == config
    assert json.loads(path.read_text())["run_time"] == "14:00"


@pytest.mark.parametrize("value", ["2:00", "24:00", "14:60", "noon"])
def test_forecast_run_time_validation(value: str) -> None:
    with pytest.raises(ValueError, match="run_time"):
        validate_forecast_run_time(value)


def test_forecast_timezone_validation() -> None:
    assert validate_forecast_timezone("Europe/Helsinki") == "Europe/Helsinki"
    with pytest.raises(ValueError, match="unknown timezone"):
        validate_forecast_timezone("Mars/Olympus")


def test_forecast_skip_is_persistent_one_shot(tmp_path: Path) -> None:
    path = tmp_path / "forecast.json"
    write_forecast_scheduler_config(path, _config(tmp_path))

    set_forecast_skip_next_run(path, skip=True)
    assert read_forecast_scheduler_config(path).skip_next_run is True
    assert consume_forecast_skip_next_run(path) is True
    assert read_forecast_scheduler_config(path).skip_next_run is False
    assert consume_forecast_skip_next_run(path) is False


def test_scheduler_gate_cli_consumes_skip_once(tmp_path: Path) -> None:
    path = tmp_path / "forecast.json"
    write_forecast_scheduler_config(path, _config(tmp_path, skip_next_run=True))

    assert forecast_cli.main(["scheduler-allow-run", "--config", str(path)]) == 1
    assert forecast_cli.main(["scheduler-allow-run", "--config", str(path)]) == 0


def test_save_config_updates_forecast_timer_only_and_preserves_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "forecast.json"
    calls = []
    monkeypatch.setattr(ui_service, "_systemctl_value", lambda *args: "enabled")
    monkeypatch.setattr(
        ui_service, "install_scheduler", lambda **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(
        ui_service, "read_forecast_timer_status", lambda: {"active": "active"}
    )
    config = _config(tmp_path, run_time="15:30")

    result = ui_service.save_forecast_config_and_sync_timer(
        config_path=path, config=config
    )

    assert result["enabled_preserved"] is True
    assert read_forecast_scheduler_config(path).run_time == "15:30"
    assert calls[0]["activate"] is False
    assert calls[0]["config"] == config
    assert calls[0]["config_path"] == path


def test_timer_status_uses_installed_units_and_systemd_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer = tmp_path / "rawcandle-forecast-daily.timer"
    service = tmp_path / "rawcandle-forecast-daily.service"
    timer.write_text(
        "[Timer]\nOnCalendar=*-*-* 14:00:00 Europe/Helsinki\n",
        encoding="utf-8",
    )
    service.write_text("[Service]\n", encoding="utf-8")
    monkeypatch.setattr(
        ui_service, "_unit_path",
        lambda name: timer if name.endswith(".timer") else service,
    )

    def value(*arguments: str) -> str:
        if arguments[0] == "is-enabled":
            return "enabled"
        if arguments[0] == "is-active" and arguments[1].endswith(".timer"):
            return "active"
        if arguments[0] == "is-active":
            return "failed"
        return "Mon 2026-09-28 14:00:00 EEST"

    monkeypatch.setattr(ui_service, "_systemctl_value", value)
    status = ui_service.read_forecast_timer_status()

    assert status["installed"] is True
    assert status["enabled"] == "enabled"
    assert status["active"] == "active"
    assert status["service_status"] == "failed"
    assert status["on_calendar"] == "*-*-* 14:00:00 Europe/Helsinki"
    assert status["timezone"] == "Europe/Helsinki"
    assert status["next_run_local"] == "Mon 2026-09-28 14:00:00 EEST"


def test_run_now_uses_fixed_full_universe_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class Process:
        pid = 123

    def popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr(ui_service.subprocess, "Popen", popen)

    result = ui_service.start_forecast_run_now(_config(tmp_path))

    assert result["status"] == "STARTED"
    assert " ".join(captured["command"]) == FORECAST_DAILY_COMMAND
    assert "--max-symbols" not in captured["command"]
    assert captured["start_new_session"] is True


def test_run_now_reports_overlap_without_starting_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Locked:
        def __enter__(self):
            raise ForecastDailyAlreadyRunningError("active")

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(ui_service, "forecast_daily_lock", lambda _path: Locked())
    monkeypatch.setattr(
        ui_service.subprocess, "Popen",
        lambda *_args, **_kwargs: pytest.fail("must not start"),
    )

    result = ui_service.start_forecast_run_now(_config(tmp_path))
    assert result["status"] == "OVERLAP_ACTIVE"


def test_forecast_logs_are_sorted_and_path_safe(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    scheduler_log = log_dir / "forecast_scheduler.log"
    manual_log = log_dir / "forecast_run_20260928T080000Z.log"
    scheduler_log.write_text("scheduler", encoding="utf-8")
    manual_log.write_text("manual", encoding="utf-8")
    (log_dir / "raw_payload.json").write_text("{}", encoding="utf-8")

    assert {item["filename"] for item in ui_service.list_forecast_logs(str(log_dir))} == {
        scheduler_log.name, manual_log.name,
    }
    assert ui_service.resolve_forecast_log(str(log_dir), scheduler_log.name) == scheduler_log
    with pytest.raises(ValueError):
        ui_service.resolve_forecast_log(str(log_dir), "../forecast_scheduler.log")
    with pytest.raises(ValueError):
        ui_service.resolve_forecast_log(str(log_dir), "raw_payload.json")


class _Page:
    def __init__(self) -> None:
        self.urls = []
        self.updates = 0

    def update(self) -> None:
        self.updates += 1

    def launch_url(self, url: str) -> None:
        self.urls.append(url)


def test_forecast_page_renders_partial_separately_from_failed_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "forecast.json"
    write_forecast_scheduler_config(path, _config(tmp_path))
    summary = {
        "overall_status": "PARTIAL", "run_id": "run-1",
        "acquisition": {"MALFORMED_OR_SCHEMA_MISMATCH": 11},
        "persisted_fetches": 7323, "expected_fetches": 7323,
    }
    monkeypatch.setattr(forecast_page, "read_forecast_latest_summary", lambda _c: summary)
    monkeypatch.setattr(
        forecast_page, "read_forecast_timer_status",
        lambda: {"installed": True, "enabled": "enabled", "active": "active",
                 "service_status": "failed", "status_summary": "timer=active; service=failed"},
    )
    monkeypatch.setattr(forecast_page, "list_forecast_logs", lambda _d: [])

    controls = forecast_page.build_forecast_scheduler_page(
        _Page(), config_path=path
    )

    assert "overall_status=PARTIAL" in controls.summary_field.value
    assert "service_status=failed" in controls.timer_status_field.value
    assert "overall_status=FAILED" not in controls.summary_field.value
    assert controls.running_status_text.value == "Scheduler status: not running"


def test_forecast_page_has_expected_controls_and_no_maintenance_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "forecast.json"
    write_forecast_scheduler_config(path, _config(tmp_path))
    monkeypatch.setattr(
        forecast_page, "read_forecast_latest_summary",
        lambda _c: {"overall_status": "SUCCESS", "acquisition": {}},
    )
    monkeypatch.setattr(forecast_page, "read_forecast_timer_status", lambda: {})
    monkeypatch.setattr(forecast_page, "list_forecast_logs", lambda _d: [])

    controls = forecast_page.build_forecast_scheduler_page(_Page(), config_path=path)
    labels = {
        controls.save_button.text, controls.reload_button.text,
        controls.run_now_button.text, controls.skip_button.text,
        controls.cancel_skip_button.text, controls.refresh_logs_button.text,
    }

    assert labels == {
        "Save config", "Reload config", "Run now", "Skip next run",
        "Cancel skip", "Refresh logs",
    }
    rendered = str(controls.content).lower()
    assert "restore" not in rendered
    assert "cleanup" not in rendered
    assert "migration" not in rendered


def test_forecast_page_save_reload_run_and_skip_actions_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "forecast.json"
    write_forecast_scheduler_config(path, _config(tmp_path))
    saved = []
    started = []
    monkeypatch.setattr(
        forecast_page, "read_forecast_latest_summary",
        lambda _c: {"overall_status": "SUCCESS", "acquisition": {}},
    )
    monkeypatch.setattr(forecast_page, "read_forecast_timer_status", lambda: {})
    monkeypatch.setattr(forecast_page, "list_forecast_logs", lambda _d: [])
    monkeypatch.setattr(
        forecast_page, "save_forecast_config_and_sync_timer",
        lambda **kwargs: saved.append(kwargs) or {"message": "saved"},
    )
    monkeypatch.setattr(
        forecast_page, "start_forecast_run_now",
        lambda config: started.append(config) or {
            "status": "STARTED", "log_path": "/tmp/forecast.log",
        },
    )

    controls = forecast_page.build_forecast_scheduler_page(_Page(), config_path=path)
    controls.run_time_field.value = "15:15"
    controls.save_button.on_click(None)
    assert saved[0]["config"].run_time == "15:15"
    assert saved[0]["config_path"] == path

    controls.run_now_button.on_click(None)
    assert started[0].run_time == "14:00"
    controls.skip_button.on_click(None)
    assert read_forecast_scheduler_config(path).skip_next_run is True
    assert controls.cancel_skip_button.disabled is False
    controls.cancel_skip_button.on_click(None)
    assert read_forecast_scheduler_config(path).skip_next_run is False

    controls.run_time_field.value = "broken"
    controls.save_button.on_click(None)
    assert "run_time" in controls.status_field.value
    controls.reload_button.on_click(None)
    assert controls.run_time_field.value == "14:00"


def test_forecast_page_log_open_and_download_use_scoped_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "forecast.json"
    write_forecast_scheduler_config(path, _config(tmp_path))
    monkeypatch.setattr(
        forecast_page, "read_forecast_latest_summary",
        lambda _c: {"overall_status": "SUCCESS", "acquisition": {}},
    )
    monkeypatch.setattr(forecast_page, "read_forecast_timer_status", lambda: {})
    monkeypatch.setattr(
        forecast_page, "list_forecast_logs",
        lambda _d: [{
            "filename": "forecast_scheduler.log", "type": "scheduler",
            "size_bytes": 42, "modified_at": "2026-09-28T08:00:00+00:00",
        }],
    )
    page = _Page()
    controls = forecast_page.build_forecast_scheduler_page(page, config_path=path)

    row = controls.logs_column.controls[0]
    row.controls[1].on_click(None)
    row.controls[2].on_click(None)

    assert page.urls == [
        "/forecast/logs/forecast_scheduler.log?download=false",
        "/forecast/logs/forecast_scheduler.log?download=true",
    ]
