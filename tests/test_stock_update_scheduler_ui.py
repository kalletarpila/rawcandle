from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from dev_tools.stock_update_scheduler_ui import (
    SCHEDULER_UI_PORT,
    apply_cancel_skip_next_run_to_config,
    apply_skip_next_run_to_config,
    build_cancel_skip_next_run_config,
    build_config_from_ui_values,
    build_datacenter_audit_command,
    build_datacenter_pipeline_command,
    build_datacenter_pipeline_plan_command,
    build_datacenter_watermark_command,
    build_skip_next_run_config,
    build_text_log_browser_url,
    find_datacenter_generated_reports,
    format_run_now_error_message,
    format_systemd_on_calendar,
    launch_browser_url,
    list_scheduler_log_files,
    load_latest_scheduler_summary,
    main,
    read_systemd_timer_on_calendar,
    read_systemd_user_timer_status,
    run_app,
    run_datacenter_ui_command,
    save_config_and_sync_systemd_timer,
    scheduler_running_state,
    scheduler_skip_button_state,
    scheduler_skip_next_run_label,
    update_systemd_timer_on_calendar,
)
from rawcandle.scheduler.config import read_scheduler_config, write_scheduler_config
from rawcandle.scheduler.runner import SchedulerAlreadyRunningError


class _FakePage:
    def __init__(self):
        self.controls = []
        self.title = ""
        self.scroll = None
        self.launched_urls = []
        self.tasks = []
        self.update_count = 0

    def add(self, control):
        self.controls.append(control)

    def update(self):
        self.update_count += 1

    def launch_url(self, url):
        self.launched_urls.append(url)

    def run_task(self, coro):
        self.tasks.append(coro)


def _write_config(path: Path, *, skip_next_run: bool = False) -> None:
    path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": str(path.parent / "logs"),
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "skip_next_run": skip_next_run,
                "technical_relevance_enabled": False,
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )


def test_load_latest_scheduler_summary_picks_newest_by_filename_timestamp(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "stock_update_scheduler_summary_20260616T080000Z.json").write_text(
        json.dumps({"status": "old"}),
        encoding="utf-8",
    )
    (log_dir / "stock_update_scheduler_summary_20260617T080000Z.json").write_text(
        json.dumps({"status": "new"}),
        encoding="utf-8",
    )

    assert load_latest_scheduler_summary(str(log_dir)) == {"status": "new"}


def test_list_scheduler_log_files_returns_recent_text_logs(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for name in ["b.txt", "a.txt", "ignore.json"]:
        (log_dir / name).write_text("x", encoding="utf-8")

    assert [path.name for path in list_scheduler_log_files(str(log_dir))] == [
        "b.txt",
        "a.txt",
    ]


def test_build_text_log_browser_url_quotes_path(tmp_path):
    path = tmp_path / "log file.txt"
    assert "%20" in build_text_log_browser_url(str(path))


def test_launch_browser_url_handles_sync_page_method():
    page = _FakePage()

    asyncio.run(launch_browser_url(page, "https://example.test"))

    assert page.launched_urls == ["https://example.test"]


def test_format_run_now_error_message_for_lock_conflict_is_concise():
    assert (
        format_run_now_error_message(SchedulerAlreadyRunningError("already running"))
        == "Run now blocked: scheduler run is already active."
    )


def test_systemd_timer_helpers_update_oncalendar(tmp_path):
    timer = tmp_path / "timer"
    timer.write_text("[Timer]\nOnCalendar=*-*-* 04:00:00\n", encoding="utf-8")

    update_systemd_timer_on_calendar(timer, run_time="05:30")

    assert read_systemd_timer_on_calendar(timer) == "*-*-* 05:30:00"
    assert format_systemd_on_calendar(run_time="05:30") == "*-*-* 05:30:00"


def test_read_systemd_user_timer_status_reports_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: tmp_path / "missing.timer",
    )

    status = read_systemd_user_timer_status()

    assert status["installed"] is False
    assert status["status_summary"] == "missing"


def test_save_config_and_sync_systemd_timer_reports_missing_timer(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    timer_path = tmp_path / "missing.timer"
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH"],
        technical_relevance_enabled=True,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: timer_path,
    )

    result = save_config_and_sync_systemd_timer(
        config_path=str(config_path),
        config=config,
    )

    assert result["status"] == "WARNING"
    assert read_scheduler_config(str(config_path)).technical_relevance_enabled is True


def test_build_config_from_ui_values_normalizes_markets():
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", " omxs "],
        technical_relevance_enabled=True,
    )

    assert config.enabled_markets == ["omxh", "omxs"]
    assert config.technical_relevance_enabled is True


def test_build_config_from_ui_values_invalid_run_time_raises_value_error():
    with pytest.raises(ValueError):
        build_config_from_ui_values(
            osakedata_db_path="/tmp/osakedata.db",
            analysis_db_path="/tmp/analysis.db",
            log_dir="/tmp/logs",
            timezone="Europe/Helsinki",
            run_time="5:30",
            selected_markets=["OMXH"],
            technical_relevance_enabled=False,
        )


def test_datacenter_command_builders_use_expected_entrypoints():
    command = build_datacenter_pipeline_command(
        price_db="/tmp/price.db",
        analysis_db="/tmp/analysis.db",
        taxonomy_csv="/tmp/taxonomy.csv",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-22",
        start_date="2025-08-01",
        index_base_date="2020-01-01",
        output_dir="/tmp/reports",
        expected_ticker_count="236",
        expected_group_count="54",
        expected_synthetic_ohlc_count="53",
        rolling_window_size="20",
        watchlist_file="/tmp/watchlist.txt",
        dry_run=False,
    )

    assert command[:2] == ["python3", "run_datacenter_swing_pipeline.py"]
    assert "--export-dashboard-input-json" not in command
    assert build_datacenter_pipeline_plan_command(
        price_db="/tmp/price.db",
        analysis_db="/tmp/analysis.db",
        taxonomy_csv="/tmp/taxonomy.csv",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-22",
        start_date="2025-08-01",
        index_base_date="2020-01-01",
        output_dir="/tmp/reports",
        expected_ticker_count="236",
        expected_group_count="54",
        expected_synthetic_ohlc_count="53",
        rolling_window_size="20",
        watchlist_file="/tmp/watchlist.txt",
    )[-1] == "--dry-run"
    assert build_datacenter_audit_command(
        analysis_db="/tmp/analysis.db",
        signal_date="2026-05-22",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        expected_ticker_count="236",
        expected_group_count="54",
        expected_synthetic_ohlc_count="53",
        rolling_window_size="20",
    )[:2] == ["python3", "run_datacenter_swing_pipeline_audit.py"]
    assert build_datacenter_watermark_command(analysis_db="/tmp/analysis.db") == [
        "python3",
        "run_datacenter_pipeline_watermark.py",
        "--analysis-db",
        "/tmp/analysis.db",
    ]


def test_find_datacenter_generated_reports_lists_markdown_and_csv(tmp_path):
    (tmp_path / "report.md").write_text("x", encoding="utf-8")
    (tmp_path / "report.csv").write_text("x", encoding="utf-8")
    (tmp_path / "ignore.html").write_text("x", encoding="utf-8")

    assert {path.suffix for path in find_datacenter_generated_reports(str(tmp_path))} == {
        ".md",
        ".csv",
    }


def test_run_datacenter_ui_command_updates_fields(tmp_path):
    page = _FakePage()
    log_field = Mock(value="")
    status_field = Mock(value="")
    reports_column = Mock(controls=[])

    run_datacenter_ui_command(
        page=page,
        title="Plan",
        command=["python3", "run.py"],
        log_field=log_field,
        status_field=status_field,
        output_dir=str(tmp_path),
        reports_column=reports_column,
    )

    assert log_field.value == "python3 run.py"
    assert status_field.value == "Plan planned."
    assert page.update_count == 1


def test_run_app_exposes_scheduler_and_datacenter_controls(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"installed": False, "status_summary": "missing"},
    )

    page = _FakePage()
    run_app(page, str(config_path))

    assert page.title == "RawCandle stock update scheduler"
    assert page.technical_relevance_checkbox.value is False
    assert page.datacenter_plan_button is not None
    assert not hasattr(page, "datacenter_dashboard_content")


def test_run_app_save_config_persists_technical_relevance(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"installed": False, "status_summary": "missing"},
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: tmp_path / "missing.timer",
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.technical_relevance_checkbox.value = True
    page.save_config_button.on_click(None)

    assert read_scheduler_config(str(config_path)).technical_relevance_enabled is True


def test_scheduler_ui_port_constant_is_fixed():
    assert SCHEDULER_UI_PORT == 8555


def test_scheduler_ui_startup_passes_fixed_port_to_ft_app(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    app_mock = Mock()
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.ft.app", app_mock)

    main(["--config", str(config_path)])

    assert app_mock.call_args.kwargs["port"] == 8555


def test_skip_next_run_helpers_roundtrip(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: {"is_running": False},
    )

    skipped = apply_skip_next_run_to_config(str(config_path))
    cancelled = apply_cancel_skip_next_run_to_config(str(config_path))

    assert skipped.skip_next_run is True
    assert cancelled.skip_next_run is False
    assert scheduler_skip_next_run_label(skipped) == "Next scheduled run: SKIP"


def test_skip_next_run_builders_and_button_state(tmp_path):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    config = read_scheduler_config(str(config_path))

    assert build_skip_next_run_config(config).skip_next_run is True
    assert build_cancel_skip_next_run_config(config).skip_next_run is False
    assert scheduler_running_state({"is_running": True}) == {"is_running": True}
    assert scheduler_skip_button_state(is_running=False, skip_next_run=False) == {
        "skip_disabled": False,
        "cancel_disabled": True,
    }


def test_config_write_read_roundtrip_through_existing_config_module(tmp_path):
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", "OMXS"],
        technical_relevance_enabled=True,
    )
    path = tmp_path / "scheduler.json"

    write_scheduler_config(str(path), config)

    assert read_scheduler_config(str(path)) == config
