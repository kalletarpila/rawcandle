from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from dev_tools.stock_update_scheduler_ui import (
    SCHEDULER_UI_PORT,
    apply_cancel_skip_next_run_to_config,
    apply_skip_next_run_to_config,
    build_text_log_browser_url,
    format_systemd_on_calendar,
    format_run_now_error_message,
    build_cancel_skip_next_run_config,
    build_skip_next_run_config,
    build_config_from_ui_values,
    get_systemd_user_timer_path,
    launch_browser_url,
    list_scheduler_log_files,
    load_latest_scheduler_summary,
    main,
    read_systemd_timer_on_calendar,
    read_systemd_user_timer_status,
    save_config_and_sync_systemd_timer,
    scheduler_skip_button_state,
    scheduler_running_state,
    scheduler_skip_next_run_label,
    update_systemd_timer_on_calendar,
)
from rawcandle.scheduler.config import StockUpdateSchedulerConfig, read_scheduler_config, write_scheduler_config
from rawcandle.scheduler.runner import SchedulerAlreadyRunningError


def test_load_latest_scheduler_summary_picks_newest_by_filename_timestamp(tmp_path):
    older = tmp_path / "stock_update_scheduler_summary_20260516T010000Z.json"
    newer = tmp_path / "stock_update_scheduler_summary_20260516T020000Z.json"
    unrelated = tmp_path / "not_a_summary.json"

    older.write_text(json.dumps({"overall_status": "OK", "marker": "older"}), encoding="utf-8")
    newer.write_text(json.dumps({"overall_status": "OK", "marker": "newer"}), encoding="utf-8")
    unrelated.write_text(json.dumps({"marker": "ignore"}), encoding="utf-8")

    summary = load_latest_scheduler_summary(str(tmp_path))

    assert summary == {"overall_status": "OK", "marker": "newer"}


def test_load_latest_scheduler_summary_returns_none_when_no_summary_exists(tmp_path):
    assert load_latest_scheduler_summary(str(tmp_path)) is None


def test_list_scheduler_log_files_returns_recent_logs_newest_first(tmp_path):
    files = [
        tmp_path / "stock_update_scheduler_summary_20260516T010000Z.json",
        tmp_path / "stock_update_omxh_20260516T020000Z.log",
        tmp_path / "stock_update_omxs_20260516T030000Z.txt",
        tmp_path / "ignore_me.txt",
    ]
    for path in files:
        path.write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "stock_update_omxs_20260516T030000Z.txt",
        "stock_update_omxh_20260516T020000Z.log",
        "stock_update_scheduler_summary_20260516T010000Z.json",
    ]
    assert entries[0]["path"].endswith("stock_update_omxs_20260516T030000Z.txt")
    assert entries[0]["text_openable"] is True
    assert entries[1]["text_openable"] is True
    assert entries[2]["text_openable"] is False


def test_list_scheduler_log_files_ignores_unrelated_files(tmp_path):
    (tmp_path / "stock_update_scheduler_summary_20260516T010000Z.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "stock_update_omxh_20260516T020000Z.txt").write_text(
        "x", encoding="utf-8"
    )
    (tmp_path / "something_else.log").write_text("x", encoding="utf-8")
    (tmp_path / "stock_update_foo_20260516T030000Z.txt").write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "stock_update_omxh_20260516T020000Z.txt",
        "stock_update_scheduler_summary_20260516T010000Z.json",
    ]


def test_build_text_log_browser_url_quotes_filename(tmp_path):
    log_path = tmp_path / "stock_update_omxh 20260516T020000Z.txt"

    browser_url = build_text_log_browser_url(str(log_path))

    assert browser_url == "/stock_update_omxh%2020260516T020000Z.txt"


def test_format_systemd_on_calendar_formats_validated_time():
    assert format_systemd_on_calendar("05:30") == "*-*-* 05:30:00"
    assert format_systemd_on_calendar("06:30") == "*-*-* 06:30:00"


def test_format_systemd_on_calendar_validates_input():
    with pytest.raises(ValueError):
        format_systemd_on_calendar("6:30")


def test_read_systemd_timer_on_calendar_returns_value_when_line_exists(tmp_path):
    timer_path = tmp_path / "stock-update-scheduler.timer"
    timer_path.write_text("[Timer]\nOnCalendar=*-*-* 06:30:00\n", encoding="utf-8")

    assert read_systemd_timer_on_calendar(timer_path) == "*-*-* 06:30:00"


def test_read_systemd_timer_on_calendar_returns_none_when_missing(tmp_path):
    assert read_systemd_timer_on_calendar(tmp_path / "missing.timer") is None


def test_update_systemd_timer_on_calendar_replaces_only_oncalendar_line(tmp_path):
    timer_path = tmp_path / "stock-update-scheduler.timer"
    timer_path.write_text(
        "[Unit]\nDescription=Test\n[Timer]\nOnCalendar=*-*-* 05:30:00\nPersistent=true\n",
        encoding="utf-8",
    )

    update_systemd_timer_on_calendar(timer_path=timer_path, run_time="06:30")

    assert (
        timer_path.read_text(encoding="utf-8")
        == "[Unit]\nDescription=Test\n[Timer]\nOnCalendar=*-*-* 06:30:00\nPersistent=true\n"
    )


def test_update_systemd_timer_on_calendar_raises_when_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        update_systemd_timer_on_calendar(
            timer_path=tmp_path / "missing.timer",
            run_time="06:30",
        )


def test_update_systemd_timer_on_calendar_raises_when_oncalendar_missing(tmp_path):
    timer_path = tmp_path / "stock-update-scheduler.timer"
    timer_path.write_text("[Timer]\nPersistent=true\n", encoding="utf-8")

    with pytest.raises(ValueError):
        update_systemd_timer_on_calendar(timer_path=timer_path, run_time="06:30")


def test_read_systemd_user_timer_status_returns_missing_status_when_timer_missing(
    tmp_path, monkeypatch
):
    timer_path = tmp_path / "stock-update-scheduler.timer"
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: timer_path,
    )

    status = read_systemd_user_timer_status()

    assert status["installed"] is False
    assert status["timer_path"] == str(timer_path)
    assert status["on_calendar"] is None
    assert status["error"] is None


def test_read_systemd_user_timer_status_returns_stable_mocked_status(tmp_path, monkeypatch):
    timer_path = tmp_path / "stock-update-scheduler.timer"
    timer_path.write_text("[Timer]\nOnCalendar=*-*-* 06:30:00\n", encoding="utf-8")
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: timer_path,
    )

    def fake_run(command, capture_output, text, check):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Trigger: Mon 2026-05-18 06:30:00 EEST\n",
            stderr="",
        )

    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.subprocess.run", fake_run)

    status = read_systemd_user_timer_status()

    assert status["installed"] is True
    assert status["on_calendar"] == "*-*-* 06:30:00"
    assert "Trigger:" in status["status_summary"]
    assert status["error"] is None


def test_save_config_and_sync_systemd_timer_reports_success(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    timer_path = tmp_path / "stock-update-scheduler.timer"
    timer_path.write_text("[Timer]\nOnCalendar=*-*-* 05:30:00\n", encoding="utf-8")
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="06:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: timer_path,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.reload_systemd_user_timer",
        lambda: None,
    )

    result = save_config_and_sync_systemd_timer(
        config_path=str(config_path),
        config=config,
    )

    saved = read_scheduler_config(str(config_path))
    assert saved.run_time == "06:30"
    assert read_systemd_timer_on_calendar(timer_path) == "*-*-* 06:30:00"
    assert result == {
        "config_saved": True,
        "timer_file_found": True,
        "timer_updated": True,
        "systemd_reloaded": True,
        "status": "OK",
        "message": "Config saved and systemd timer updated to 06:30.",
    }


def test_save_config_and_sync_systemd_timer_reports_missing_timer_warning(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler.json"
    timer_path = tmp_path / "missing.timer"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="06:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: timer_path,
    )
    reloaded_called = {"value": False}
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.reload_systemd_user_timer",
        lambda: reloaded_called.__setitem__("value", True),
    )

    result = save_config_and_sync_systemd_timer(
        config_path=str(config_path),
        config=config,
    )

    saved = read_scheduler_config(str(config_path))
    assert saved.run_time == "06:30"
    assert reloaded_called["value"] is False
    assert result["status"] == "WARNING"
    assert result["timer_file_found"] is False


def test_save_config_and_sync_systemd_timer_reports_reload_warning(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    timer_path = tmp_path / "stock-update-scheduler.timer"
    timer_path.write_text("[Timer]\nOnCalendar=*-*-* 05:30:00\n", encoding="utf-8")
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="06:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: timer_path,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.reload_systemd_user_timer",
        lambda: (_ for _ in ()).throw(RuntimeError("reload failed")),
    )

    result = save_config_and_sync_systemd_timer(
        config_path=str(config_path),
        config=config,
    )

    saved = read_scheduler_config(str(config_path))
    assert saved.run_time == "06:30"
    assert read_systemd_timer_on_calendar(timer_path) == "*-*-* 06:30:00"
    assert result["status"] == "WARNING"
    assert "reload failed" in result["message"]


def test_launch_browser_url_awaits_launch_when_needed():
    async def _fake_launch_result():
        return None

    def _run_task(handler, *args, **kwargs):
        asyncio.run(handler(*args, **kwargs))
        return Mock()

    page = Mock()
    page.launch_url = Mock(return_value=_fake_launch_result())
    page.run_task = Mock(side_effect=_run_task)

    launch_browser_url(page, "/stock_update_omxh_20260516T020000Z.txt")

    page.launch_url.assert_called_once_with(
        "/stock_update_omxh_20260516T020000Z.txt"
    )
    page.run_task.assert_called_once()


def test_format_run_now_error_message_for_lock_conflict_is_concise():
    message = format_run_now_error_message(
        SchedulerAlreadyRunningError("already running")
    )

    assert message == "Run now blocked: scheduler run is already active."


def test_build_config_from_ui_values_normalizes_markets():
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", " omxs "],
    )

    assert config.enabled_markets == ["omxh", "omxs"]


def test_build_config_from_ui_values_does_not_include_usa_unless_selected():
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", " omxs "],
    )

    assert config.enabled_markets == ["omxh", "omxs"]
    assert "usa" not in config.enabled_markets


def test_build_config_from_ui_values_invalid_run_time_raises_value_error():
    with pytest.raises(ValueError):
        build_config_from_ui_values(
            osakedata_db_path="/tmp/osakedata.db",
            analysis_db_path="/tmp/analysis.db",
            log_dir="/tmp/logs",
            timezone="Europe/Helsinki",
            run_time="5:30",
            selected_markets=["OMXH"],
        )


def test_config_write_read_roundtrip_through_existing_config_module(tmp_path):
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", "OMXS"],
    )
    path = tmp_path / "scheduler.json"

    write_scheduler_config(str(path), config)
    loaded = read_scheduler_config(str(path))

    assert loaded == config


def test_scheduler_ui_port_constant_is_fixed():
    assert SCHEDULER_UI_PORT == 8555


def test_scheduler_ui_startup_passes_fixed_port_to_ft_app(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh", "omxs"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )

    captured = {}

    def fake_app(*, target, view, port, assets_dir):
        captured["target"] = target
        captured["view"] = view
        captured["port"] = port
        captured["assets_dir"] = assets_dir

    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.ft.app", fake_app)

    code = main(["--config", str(config_path)])

    assert code == 0
    assert captured["port"] == SCHEDULER_UI_PORT
    assert captured["assets_dir"] == "/tmp/logs"


def test_build_skip_next_run_config_sets_true_without_changing_other_fields():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=False,
    )

    updated = build_skip_next_run_config(config)

    assert updated.skip_next_run is True
    assert updated.enabled_markets == config.enabled_markets
    assert updated.run_time == config.run_time
    assert updated.osakedata_db_path == config.osakedata_db_path
    assert updated.analysis_db_path == config.analysis_db_path
    assert updated.log_dir == config.log_dir
    assert updated.timezone == config.timezone


def test_build_cancel_skip_next_run_config_sets_false_without_changing_other_fields():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=True,
    )

    updated = build_cancel_skip_next_run_config(config)

    assert updated.skip_next_run is False
    assert updated.enabled_markets == config.enabled_markets
    assert updated.run_time == config.run_time
    assert updated.osakedata_db_path == config.osakedata_db_path
    assert updated.analysis_db_path == config.analysis_db_path
    assert updated.log_dir == config.log_dir
    assert updated.timezone == config.timezone


def test_scheduler_running_state_disables_skip_button_when_running():
    state = scheduler_running_state(
        {"is_running": True, "current_market": "omxh", "last_status": "RUNNING"}
    )

    assert state["is_running"] is True
    assert state["skip_button_disabled"] is True
    assert state["current_market"] == "omxh"


def test_scheduler_running_state_missing_status_means_not_running():
    state = scheduler_running_state(None)

    assert state["is_running"] is False
    assert state["skip_button_disabled"] is False
    assert state["current_market"] is None


def test_apply_skip_next_run_to_config_does_not_modify_config_when_running(
    tmp_path, monkeypatch
):
    path = tmp_path / "scheduler.json"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir=str(tmp_path / "logs"),
        timezone="Europe/Helsinki",
        skip_next_run=False,
    )
    write_scheduler_config(str(path), config)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: {"is_running": True, "current_market": "omxh"},
    )

    with pytest.raises(ValueError):
        apply_skip_next_run_to_config(str(path))

    reloaded = read_scheduler_config(str(path))
    assert reloaded.skip_next_run is False


def test_apply_skip_next_run_to_config_sets_flag_true(tmp_path, monkeypatch):
    path = tmp_path / "scheduler.json"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir=str(tmp_path / "logs"),
        timezone="Europe/Helsinki",
        skip_next_run=False,
    )
    write_scheduler_config(str(path), config)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: None,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_scheduler_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run scheduler")),
    )

    updated = apply_skip_next_run_to_config(str(path))
    reloaded = read_scheduler_config(str(path))

    assert updated.skip_next_run is True
    assert reloaded.skip_next_run is True


def test_apply_cancel_skip_next_run_to_config_sets_flag_false(tmp_path, monkeypatch):
    path = tmp_path / "scheduler.json"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir=str(tmp_path / "logs"),
        timezone="Europe/Helsinki",
        skip_next_run=True,
    )
    write_scheduler_config(str(path), config)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: None,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_scheduler_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run scheduler")),
    )

    updated = apply_cancel_skip_next_run_to_config(str(path))
    reloaded = read_scheduler_config(str(path))

    assert updated.skip_next_run is False
    assert reloaded.skip_next_run is False
    assert reloaded.enabled_markets == ["omxh", "omxs"]


def test_apply_cancel_skip_next_run_to_config_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "scheduler.json"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir=str(tmp_path / "logs"),
        timezone="Europe/Helsinki",
        skip_next_run=False,
    )
    write_scheduler_config(str(path), config)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: None,
    )

    updated = apply_cancel_skip_next_run_to_config(str(path))
    reloaded = read_scheduler_config(str(path))

    assert updated.skip_next_run is False
    assert reloaded.skip_next_run is False
    assert reloaded.enabled_markets == ["omxh", "omxs"]


def test_skip_next_run_display_state_comes_from_config():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=True,
    )

    assert scheduler_skip_next_run_label(config) == "Skip next run: true"


def test_scheduler_skip_button_state_not_running_skip_false():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=False,
    )

    state = scheduler_skip_button_state(config=config, status=None)

    assert state == {"skip_enabled": True, "cancel_enabled": False}


def test_scheduler_skip_button_state_not_running_skip_true():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=True,
    )

    state = scheduler_skip_button_state(config=config, status=None)

    assert state == {"skip_enabled": False, "cancel_enabled": True}


def test_scheduler_skip_button_state_running_disables_both():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=True,
    )

    state = scheduler_skip_button_state(
        config=config,
        status={"is_running": True, "current_market": "omxh"},
    )

    assert state == {"skip_enabled": False, "cancel_enabled": False}


def test_apply_cancel_skip_next_run_to_config_does_not_modify_config_when_running(
    tmp_path, monkeypatch
):
    path = tmp_path / "scheduler.json"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir=str(tmp_path / "logs"),
        timezone="Europe/Helsinki",
        skip_next_run=True,
    )
    write_scheduler_config(str(path), config)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: {"is_running": True, "current_market": "omxh"},
    )

    with pytest.raises(ValueError):
        apply_cancel_skip_next_run_to_config(str(path))

    reloaded = read_scheduler_config(str(path))
    assert reloaded.skip_next_run is True
