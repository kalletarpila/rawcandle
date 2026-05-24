from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    DatacenterReportStatus,
)
from dev_tools.stock_update_scheduler_ui import (
    DEFAULT_DATACENTER_ANALYSIS_DB,
    DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT,
    DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT,
    DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT,
    DEFAULT_DATACENTER_INDEX_BASE_DATE,
    DEFAULT_DATACENTER_MARKET,
    DEFAULT_DATACENTER_OUTPUT_DIR,
    DEFAULT_DATACENTER_PRICE_DB,
    DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE,
    DEFAULT_DATACENTER_SIGNAL_DATE,
    DEFAULT_DATACENTER_START_DATE,
    DEFAULT_DATACENTER_TAXONOMY_CSV,
    DEFAULT_DATACENTER_TAXONOMY_VERSION,
    DEFAULT_DATACENTER_WATCHLIST_FILE,
    SCHEDULER_UI_PORT,
    apply_cancel_skip_next_run_to_config,
    apply_skip_next_run_to_config,
    build_datacenter_audit_command,
    build_text_log_browser_url,
    build_datacenter_daily_report_command,
    build_datacenter_pipeline_command,
    build_datacenter_pipeline_plan_command,
    build_datacenter_rolling_report_command,
    build_datacenter_watermark_command,
    find_datacenter_generated_reports,
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
    run_app,
    run_datacenter_ui_command,
    populate_datacenter_report_downloads,
    save_config_and_sync_systemd_timer,
    scheduler_skip_button_state,
    scheduler_running_state,
    scheduler_skip_next_run_label,
    update_systemd_timer_on_calendar,
)
from rawcandle.scheduler.config import StockUpdateSchedulerConfig, read_scheduler_config, write_scheduler_config
from rawcandle.scheduler.runner import SchedulerAlreadyRunningError


class _FakePage:
    def __init__(self):
        self.controls = []
        self.title = ""
        self.scroll = None
        self.launched_urls = []
        self.tasks = []

    def add(self, control):
        self.controls.append(control)

    def update(self):
        pass

    def launch_url(self, url):
        self.launched_urls.append(url)
        return None

    def run_task(self, task):
        self.tasks.append(task)


def _iter_flet_descendants(control):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _iter_flet_descendants(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _iter_flet_descendants(child)
    tabs = getattr(control, "tabs", None)
    if tabs:
        for tab in tabs:
            yield from _iter_flet_descendants(tab)


def _dashboard_tab_descendants(page):
    dashboard_tab = page.datacenter_tabs.tabs[2]
    return list(_iter_flet_descendants(dashboard_tab.content))


def _descendant_text_values(page):
    values = []
    for control in _dashboard_tab_descendants(page):
        value = getattr(control, "value", None)
        if isinstance(value, str):
            values.append(value)
        text = getattr(control, "text", None)
        if isinstance(text, str):
            values.append(text)
        label = getattr(control, "label", None)
        if isinstance(label, str):
            values.append(label)
    return values


def _descendant_text_values_for_control(control):
    values = []
    for descendant in _iter_flet_descendants(control):
        value = getattr(descendant, "value", None)
        if isinstance(value, str):
            values.append(value)
        text = getattr(descendant, "text", None)
        if isinstance(text, str):
            values.append(text)
        label = getattr(descendant, "label", None)
        if isinstance(label, str):
            values.append(label)
    return values


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
        tmp_path / "stock_update_omxh_20260516T0200Z.log",
        tmp_path / "datacenter_pipeline_usa_20260516T0250Z.txt",
        tmp_path / "stock_update_omxs_20260516T0300Z.txt",
        tmp_path / "ignore_me.txt",
    ]
    for path in files:
        path.write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "stock_update_omxs_20260516T0300Z.txt",
        "datacenter_pipeline_usa_20260516T0250Z.txt",
        "stock_update_omxh_20260516T0200Z.log",
        "stock_update_scheduler_summary_20260516T010000Z.json",
    ]
    assert entries[0]["path"].endswith("stock_update_omxs_20260516T0300Z.txt")
    assert entries[0]["text_openable"] is True
    assert entries[1]["text_openable"] is True
    assert entries[2]["text_openable"] is True
    assert entries[3]["text_openable"] is False


def test_list_scheduler_log_files_ignores_unrelated_files(tmp_path):
    (tmp_path / "stock_update_scheduler_summary_20260516T010000Z.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "stock_update_omxh_20260516T0200Z.txt").write_text(
        "x", encoding="utf-8"
    )
    (tmp_path / "datacenter_pipeline_usa_20260516T0250Z.txt").write_text(
        "x", encoding="utf-8"
    )
    (tmp_path / "something_else.log").write_text("x", encoding="utf-8")
    (tmp_path / "stock_update_foo_20260516T0300Z.txt").write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "datacenter_pipeline_usa_20260516T0250Z.txt",
        "stock_update_omxh_20260516T0200Z.txt",
        "stock_update_scheduler_summary_20260516T010000Z.json",
    ]


def test_build_text_log_browser_url_quotes_filename(tmp_path):
    log_path = tmp_path / "stock_update_omxh 20260516T0200Z.txt"

    browser_url = build_text_log_browser_url(str(log_path))

    assert browser_url == "/stock_update_omxh%2020260516T0200Z.txt"


def test_list_scheduler_log_files_accepts_legacy_second_precision_name(tmp_path):
    (tmp_path / "stock_update_omxh_20260516T020000Z.txt").write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "stock_update_omxh_20260516T020000Z.txt",
    ]


def test_list_scheduler_log_files_sorts_same_minute_suffix_after_base(tmp_path):
    (tmp_path / "stock_update_omxh_20260516T0200Z.txt").write_text("a", encoding="utf-8")
    (tmp_path / "stock_update_omxh_20260516T0200Z_2.txt").write_text("b", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "stock_update_omxh_20260516T0200Z_2.txt",
        "stock_update_omxh_20260516T0200Z.txt",
    ]


def test_list_scheduler_log_files_defaults_to_10_newest_entries(tmp_path):
    for minute in range(12):
        path = tmp_path / f"stock_update_omxh_20260516T{minute:02d}00Z.txt"
        path.write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert len(entries) == 10
    assert entries[0]["filename"] == "stock_update_omxh_20260516T1100Z.txt"
    assert entries[-1]["filename"] == "stock_update_omxh_20260516T0200Z.txt"


def test_run_app_shows_datacenter_status_in_summary_and_datacenter_log_in_recent_logs(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler_config.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh", "omxs", "usa"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary",
        lambda log_dir: {
            "overall_status": "OK",
            "enabled_markets": ["omxh", "omxs", "usa"],
            "summary_json_path": "/tmp/logs/summary.json",
            "datacenter_pipeline_status": "OK",
            "datacenter_pipeline_market": "usa",
            "datacenter_pipeline_audit_validation_status": "WARN",
            "datacenter_pipeline_log_path": "/tmp/logs/datacenter_pipeline_usa_20260521T0822Z.txt",
            "market_results": [],
        },
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.list_scheduler_log_files",
        lambda log_dir: [
            {
                "filename": "datacenter_pipeline_usa_20260521T0822Z.txt",
                "path": "/tmp/logs/datacenter_pipeline_usa_20260521T0822Z.txt",
                "size_bytes": 123,
                "modified_at": "1",
                "timestamp": "20260521T0822Z",
                "sort_key": "20260521T0822Z_0",
                "type": "datacenter_log",
                "text_openable": True,
            }
        ],
    )
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.read_scheduler_status", lambda log_dir: None)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"timer_path": "/tmp/timer", "on_calendar": "*-*-* 05:30:00", "installed": True, "status_summary": "ok", "error": None},
    )

    page = _FakePage()
    run_app(page, str(config_path))

    assert "datacenter_pipeline.status=OK" in page.summary_field.value
    assert "datacenter_pipeline.audit_validation_status=WARN" in page.summary_field.value
    assert (
        "datacenter_pipeline.log_path=/tmp/logs/datacenter_pipeline_usa_20260521T0822Z.txt"
        in page.summary_field.value
    )
    card = page.logs_column.controls[0]
    log_row = card.content.content.controls[0]
    assert "datacenter_pipeline_usa_20260521T0822Z.txt" in log_row.controls[0].value


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
        technical_relevance_enabled=True,
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
    assert saved.technical_relevance_enabled is True
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
        technical_relevance_enabled=True,
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
    assert saved.technical_relevance_enabled is True
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
        technical_relevance_enabled=True,
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
    assert saved.technical_relevance_enabled is True
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
        technical_relevance_enabled=True,
    )

    assert config.enabled_markets == ["omxh", "omxs"]
    assert config.technical_relevance_enabled is True


def test_build_config_from_ui_values_does_not_include_usa_unless_selected():
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", " omxs "],
        technical_relevance_enabled=False,
    )

    assert config.enabled_markets == ["omxh", "omxs"]
    assert "usa" not in config.enabled_markets
    assert config.technical_relevance_enabled is False


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
    loaded = read_scheduler_config(str(path))

    assert loaded == config


def test_run_app_loads_technical_relevance_enabled_true_into_checkbox(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler_true.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "technical_relevance_enabled": True,
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary", lambda log_dir: None)
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.list_scheduler_log_files", lambda log_dir: [])
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.read_scheduler_status", lambda log_dir: None)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"timer_path": "/tmp/timer", "on_calendar": "*-*-* 05:30:00", "installed": True, "status_summary": "ok", "error": None},
    )

    page = _FakePage()
    run_app(page, str(config_path))

    assert page.technical_relevance_checkbox.value is True


def test_run_app_loads_technical_relevance_enabled_false_when_false_or_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary", lambda log_dir: None)
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.list_scheduler_log_files", lambda log_dir: [])
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.read_scheduler_status", lambda log_dir: None)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"timer_path": "/tmp/timer", "on_calendar": "*-*-* 05:30:00", "installed": True, "status_summary": "ok", "error": None},
    )

    false_path = tmp_path / "scheduler_false.json"
    false_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "technical_relevance_enabled": False,
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    missing_path = tmp_path / "scheduler_missing.json"
    missing_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )

    false_page = _FakePage()
    run_app(false_page, str(false_path))
    assert false_page.technical_relevance_checkbox.value is False

    missing_page = _FakePage()
    run_app(missing_page, str(missing_path))
    assert missing_page.technical_relevance_checkbox.value is False


def test_run_app_save_config_persists_technical_relevance_checkbox_state(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler_save.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": str(tmp_path / "logs"),
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "technical_relevance_enabled": False,
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary", lambda log_dir: None)
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.list_scheduler_log_files", lambda log_dir: [])
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.read_scheduler_status", lambda log_dir: None)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"timer_path": "/tmp/timer", "on_calendar": "*-*-* 05:30:00", "installed": False, "status_summary": "missing", "error": None},
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: tmp_path / "missing.timer",
    )

    checked_page = _FakePage()
    run_app(checked_page, str(config_path))
    checked_page.technical_relevance_checkbox.value = True
    checked_page.save_config_button.on_click(None)
    saved_checked = read_scheduler_config(str(config_path))
    assert saved_checked.technical_relevance_enabled is True

    unchecked_page = _FakePage()
    run_app(unchecked_page, str(config_path))
    unchecked_page.technical_relevance_checkbox.value = False
    unchecked_page.save_config_button.on_click(None)
    saved_unchecked = read_scheduler_config(str(config_path))
    assert saved_unchecked.technical_relevance_enabled is False


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


def test_datacenter_command_builders_use_expected_defaults_and_shapes():
    pipeline_command = build_datacenter_pipeline_command(
        price_db=DEFAULT_DATACENTER_PRICE_DB,
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        taxonomy_csv=DEFAULT_DATACENTER_TAXONOMY_CSV,
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
        market=DEFAULT_DATACENTER_MARKET,
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date=DEFAULT_DATACENTER_INDEX_BASE_DATE,
        output_dir=DEFAULT_DATACENTER_OUTPUT_DIR,
        expected_ticker_count=DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT,
        expected_group_count=DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT,
        expected_synthetic_ohlc_count=DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT,
        rolling_window_size=DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE,
        watchlist_file=DEFAULT_DATACENTER_WATCHLIST_FILE,
        dry_run=True,
    )
    assert pipeline_command[:2] == ["python3", "run_datacenter_swing_pipeline.py"]
    assert "--dry-run" in pipeline_command
    assert pipeline_command[pipeline_command.index("--weekly-window-size") + 1] == "20"
    assert pipeline_command[pipeline_command.index("--watchlist-file") + 1] == DEFAULT_DATACENTER_WATCHLIST_FILE

    audit_command = build_datacenter_audit_command(
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        signal_date="2026-05-15",
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
        expected_ticker_count=DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT,
        expected_group_count=DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT,
        expected_synthetic_ohlc_count=DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT,
        rolling_window_size=DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE,
    )
    assert audit_command[:2] == ["python3", "run_datacenter_swing_pipeline_audit.py"]
    assert audit_command[audit_command.index("--weekly-window-size") + 1] == "20"

    daily_command = build_datacenter_daily_report_command(
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        signal_date="2026-05-15",
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
        watchlist_file=DEFAULT_DATACENTER_WATCHLIST_FILE,
        output_dir=DEFAULT_DATACENTER_OUTPUT_DIR,
    )
    assert "run_datacenter_daily_signal_report.py" in daily_command
    assert daily_command[daily_command.index("--output-md") + 1].endswith("datacenter_daily_2026-05-15_full.md")

    rolling_command = build_datacenter_rolling_report_command(
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        signal_date="2026-05-15",
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
        rolling_window_size="20",
        watchlist_file=DEFAULT_DATACENTER_WATCHLIST_FILE,
        output_dir=DEFAULT_DATACENTER_OUTPUT_DIR,
    )
    assert "run_datacenter_weekly_swing_report.py" in rolling_command
    assert rolling_command[rolling_command.index("--window-size") + 1] == "20"
    assert rolling_command[rolling_command.index("--output-md") + 1].endswith("datacenter_rolling_2026-05-15_20d_full.md")

    plan_command = build_datacenter_pipeline_plan_command(
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
        market=DEFAULT_DATACENTER_MARKET,
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date=DEFAULT_DATACENTER_INDEX_BASE_DATE,
    )
    assert plan_command[:2] == ["python3", "run_datacenter_swing_pipeline_plan.py"]

    watermark_command = build_datacenter_watermark_command(
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
    )
    assert watermark_command[:2] == ["python3", "run_datacenter_pipeline_watermark.py"]


def test_datacenter_report_downloads_are_discoverable_and_launchable(tmp_path):
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    daily_csv = output_dir / "datacenter_daily_2026-05-15_1200_full.csv"
    daily_md = output_dir / "datacenter_daily_2026-05-15_1200_full.md"
    rolling_csv = output_dir / "datacenter_rolling_2026-05-15_20d_1200_full.csv"
    for report_path in (daily_csv, daily_md, rolling_csv):
        report_path.write_text("report", encoding="utf-8")

    report_paths = find_datacenter_generated_reports(
        output_dir=str(output_dir),
        signal_date="2026-05-15",
        rolling_window_size="20",
        include_daily=True,
        include_rolling=True,
    )

    assert daily_csv in report_paths
    assert daily_md in report_paths
    assert rolling_csv in report_paths

    page = _FakePage()
    reports_column = Mock()
    reports_column.controls = []
    status_field = Mock()
    status_field.value = ""
    status_field.border_color = None
    assets_root = tmp_path / "assets"

    populate_datacenter_report_downloads(
        page=page,
        reports_column=reports_column,
        status_field=status_field,
        assets_root=assets_root,
        report_paths=[daily_csv],
    )

    assert reports_column.controls[0].controls[0].value == "Generated reports"
    reports_column.controls[1].controls[2].on_click(None)
    assert page.launched_urls == ["/datacenter_downloads/datacenter_daily_2026-05-15_1200_full.csv"]
    assert (assets_root / "datacenter_downloads" / "datacenter_daily_2026-05-15_1200_full.csv").exists()


def test_datacenter_command_log_prepends_newest_entries(monkeypatch, tmp_path):
    class _ImmediateThread:
        def __init__(self, *, target, daemon):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.threading.Thread", _ImmediateThread)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout="stdout line\nsecond line\n",
            stderr="stderr line\n",
        ),
    )

    page = _FakePage()
    log_field = Mock()
    log_field.value = "older entry"
    status_field = Mock()
    status_field.value = ""
    status_field.border_color = None

    run_datacenter_ui_command(
        page=page,
        title="Dry Run Pipeline",
        command=["python3", "run_datacenter_swing_pipeline.py", "--dry-run"],
        log_field=log_field,
        status_field=status_field,
        output_dir=str(tmp_path),
    )

    expected_lines = [
        "=== Datacenter: Dry Run Pipeline completed ===",
        "stdout line",
        "second line",
        "stderr line",
        "COMMAND python3 run_datacenter_swing_pipeline.py --dry-run",
        "=== Datacenter: Dry Run Pipeline ===",
        "older entry",
    ]
    assert log_field.value.splitlines() == expected_lines


def test_run_app_exposes_datacenter_tab_defaults_and_button_wiring(
    tmp_path, monkeypatch, capsys
):
    config_path = tmp_path / "scheduler.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    captured: list[dict[str, object]] = []
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary", lambda log_dir: None)
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.list_scheduler_log_files", lambda log_dir: [])
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.read_scheduler_status", lambda log_dir: None)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.discover_datacenter_dashboard_status",
        lambda reports_dir: DatacenterDashboardStatus(
            overall_status="MISSING",
            reports=[
                DatacenterReportStatus(
                    horizon=horizon,
                    status="MISSING",
                    path=None,
                    modified_at=None,
                )
                for horizon in ("rolling 30d", "rolling 5d", "rolling 2d", "daily")
            ],
        ),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"timer_path": "/tmp/timer", "on_calendar": "*-*-* 05:30:00", "installed": True, "status_summary": "ok", "error": None},
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_datacenter_ui_command",
        lambda **kwargs: captured.append(kwargs),
    )

    page = _FakePage()
    run_app(page, str(config_path))
    captured_stdout = capsys.readouterr().out

    assert page.datacenter_tabs.tabs[1].text == "Datacenter"
    assert page.datacenter_tabs.tabs[2].text == "Datacenter Dashboard"
    assert page.datacenter_price_db_field.value == DEFAULT_DATACENTER_PRICE_DB
    assert page.datacenter_analysis_db_field.value == DEFAULT_DATACENTER_ANALYSIS_DB
    assert page.datacenter_taxonomy_csv_field.value == DEFAULT_DATACENTER_TAXONOMY_CSV
    assert page.datacenter_taxonomy_version_field.value == DEFAULT_DATACENTER_TAXONOMY_VERSION
    assert page.datacenter_market_field.value == DEFAULT_DATACENTER_MARKET
    assert page.datacenter_signal_date_field.value == DEFAULT_DATACENTER_SIGNAL_DATE
    assert page.datacenter_start_date_field.value == DEFAULT_DATACENTER_START_DATE
    assert page.datacenter_index_base_date_field.value == DEFAULT_DATACENTER_INDEX_BASE_DATE
    assert page.datacenter_output_dir_field.value == DEFAULT_DATACENTER_OUTPUT_DIR
    assert page.datacenter_expected_ticker_count_field.value == DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT
    assert page.datacenter_expected_group_count_field.value == DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT
    assert page.datacenter_expected_synthetic_ohlc_count_field.value == DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT
    assert page.datacenter_rolling_window_size_field.value == DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE
    assert page.datacenter_watchlist_file_field.value == DEFAULT_DATACENTER_WATCHLIST_FILE
    assert page.datacenter_dashboard_reports_dir_field.value == DEFAULT_DATACENTER_OUTPUT_DIR
    assert page.datacenter_dashboard_overall_status_field.value == "NOT_REFRESHED"
    assert "readiness=NOT_REFRESHED" in page.datacenter_dashboard_parse_summary_field.value
    assert "found_reports=0" in page.datacenter_dashboard_parse_summary_field.value
    assert "missing_reports=0" in page.datacenter_dashboard_parse_summary_field.value
    assert "total_parsed_rows=0" in page.datacenter_dashboard_parse_summary_field.value
    assert "total_parse_warnings=0" in page.datacenter_dashboard_parse_summary_field.value
    assert "decision_total=0" in page.datacenter_dashboard_decision_summary_field.value
    assert "SELL=0" in page.datacenter_dashboard_decision_summary_field.value
    assert "VALID_PULLBACK=0" in page.datacenter_dashboard_decision_summary_field.value
    assert "NO_PULLBACK=0" in page.datacenter_dashboard_decision_summary_field.value
    assert "entry_readiness.READY_TO_WATCH=0" in page.datacenter_dashboard_decision_summary_field.value
    assert "candidate_priority.P1_READY_TO_WATCH=0" in page.datacenter_dashboard_decision_summary_field.value
    assert page.datacenter_dashboard_refresh_button.text == "Refresh Dashboard"
    assert page.datacenter_dashboard_reports_dir_field.label == "dashboard_reports_dir"
    assert page.datacenter_dashboard_build_marker_text.value == (
        "Dashboard UI build: dashboard_ui_visible_v1"
    )
    assert page.datacenter_dashboard_scroll_content.expand is True
    assert page.datacenter_dashboard_scroll_content.auto_scroll is False
    assert page.datacenter_dashboard_content.padding.left == 8
    assert page.datacenter_dashboard_content.padding.top == 6
    assert page.datacenter_dashboard_readiness_text.value == "Readiness: NOT_REFRESHED"
    assert page.datacenter_dashboard_reports_status_text.value == "Reports: No reports loaded."
    assert (
        page.datacenter_dashboard_decisions_status_text.value
        == "Decisions: No decisions available."
    )
    assert (
        page.datacenter_dashboard_candidate_status_text.value
        == "Candidate Pullbacks: No candidate pullbacks available."
    )
    assert page.datacenter_dashboard_reports_column.controls[0].value == "No reports loaded."
    assert page.datacenter_dashboard_command_center_column.controls[0].value == "No decisions available."
    assert page.datacenter_dashboard_conflict_detected_field.value == "False"
    assert page.datacenter_dashboard_pullback_validity_field.value == "NONE"
    assert page.datacenter_dashboard_pullback_reason_field.value == "NONE"
    assert page.datacenter_dashboard_supporting_signals_field.value == "NONE"
    assert page.datacenter_dashboard_conflicting_signals_field.value == "NONE"
    assert page.datacenter_dashboard_override_explanation_field.value == "NONE"
    datacenter_text_labels = [
        control.value
        for control in page.datacenter_content.controls
        if hasattr(control, "value")
    ]
    assert "Datacenter Dashboard" not in datacenter_text_labels
    dashboard_text_labels = _descendant_text_values(page)
    header_text_labels = _descendant_text_values_for_control(
        page.datacenter_dashboard_header
    )
    scroll_text_labels = _descendant_text_values_for_control(
        page.datacenter_dashboard_scroll_content
    )
    assert "Datacenter Dashboard" in dashboard_text_labels
    assert "Dashboard UI build: dashboard_ui_visible_v1" in dashboard_text_labels
    assert "Reports directory" in dashboard_text_labels
    assert "Refresh Dashboard" in dashboard_text_labels
    assert "Readiness: NOT_REFRESHED" in dashboard_text_labels
    assert "Reports: No reports loaded." in dashboard_text_labels
    assert "Decisions: No decisions available." in dashboard_text_labels
    assert "Candidate Pullbacks: No candidate pullbacks available." in dashboard_text_labels
    assert "Command Center" in dashboard_text_labels
    assert "Candidate Pullbacks" in dashboard_text_labels
    assert "Inspector" in dashboard_text_labels
    assert "Dashboard UI build: dashboard_ui_visible_v1" in header_text_labels
    assert "Reports directory" in header_text_labels
    assert "Refresh Dashboard" in header_text_labels
    assert "Readiness: NOT_REFRESHED" in header_text_labels
    assert "Dashboard Summary" not in header_text_labels
    assert "Dashboard Summary" in scroll_text_labels
    assert "Reports" in scroll_text_labels
    assert "Command Center" in scroll_text_labels
    assert "Candidate Pullbacks" in scroll_text_labels
    assert "Inspector" in scroll_text_labels
    assert "Reports directory" not in scroll_text_labels
    assert len(page.datacenter_dashboard_scroll_content.controls) == 5
    assert hasattr(page.datacenter_dashboard_content, "content")
    assert len(_dashboard_tab_descendants(page)) > 20
    assert "DEBUG dashboard_ui_build=dashboard_ui_visible_v1" in captured_stdout
    assert "DEBUG dashboard_parent=" in captured_stdout
    assert "DEBUG dashboard_children_count=" in captured_stdout

    page.datacenter_signal_date_field.value = "2026-05-15"
    page.datacenter_start_date_field.value = "2026-01-01"
    page.datacenter_dry_run_button.on_click(None)
    dry_run = captured[-1]
    assert dry_run["title"] == "Dry Run Pipeline"
    assert "--dry-run" in dry_run["command"]
    assert dry_run["command"][dry_run["command"].index("--weekly-window-size") + 1] == "20"
    assert dry_run["command"][dry_run["command"].index("--watchlist-file") + 1] == DEFAULT_DATACENTER_WATCHLIST_FILE

    page.datacenter_run_pipeline_button.on_click(None)
    full_run = captured[-1]
    assert full_run["title"] == "Run Full Pipeline"
    assert "--dry-run" not in full_run["command"]

    page.datacenter_audit_button.on_click(None)
    audit = captured[-1]
    assert audit["title"] == "Run Audit"
    assert "run_datacenter_swing_pipeline_audit.py" in audit["command"]

    page.datacenter_daily_report_button.on_click(None)
    daily = captured[-1]
    assert daily["title"] == "Generate Daily Report"
    assert daily["command"][daily["command"].index("--output-md") + 1].endswith("datacenter_daily_2026-05-15_full.md")

    page.datacenter_rolling_report_button.on_click(None)
    rolling = captured[-1]
    assert rolling["title"] == "Generate Rolling Report"
    assert rolling["command"][rolling["command"].index("--window-size") + 1] == "20"
    assert rolling["command"][rolling["command"].index("--output-md") + 1].endswith("datacenter_rolling_2026-05-15_20d_full.md")

    page.datacenter_signal_date_field.value = "2026-05-16"
    page.datacenter_watchlist_file_field.value = "/tmp/custom_watchlist.txt"
    page.datacenter_plan_button.on_click(None)
    plan = captured[-1]
    assert plan["title"] == "Show Pipeline Plan"
    assert plan["command"][plan["command"].index("--signal-date") + 1] == "2026-05-16"

    page.datacenter_watermarks_button.on_click(None)
    watermark = captured[-1]
    assert watermark["title"] == "Show Watermarks"
    assert "run_datacenter_pipeline_watermark.py" in watermark["command"]

    page.datacenter_daily_report_button.on_click(None)
    daily_override = captured[-1]
    assert daily_override["command"][daily_override["command"].index("--watchlist-file") + 1] == "/tmp/custom_watchlist.txt"


def test_run_app_datacenter_dashboard_refresh_reads_report_directory(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "datacenter_daily_2026-05-22_0000_full.md").write_text(
        "ticker;status\nNVDA;BUY_WATCH\n", encoding="utf-8"
    )
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary",
        lambda log_dir: None,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.list_scheduler_log_files",
        lambda log_dir: [],
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: None,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {
            "timer_path": "/tmp/timer",
            "on_calendar": "*-*-* 05:30:00",
            "installed": True,
            "status_summary": "ok",
            "error": None,
        },
    )

    page = _FakePage()
    run_app(page, str(config_path))
    header_id_before = id(page.datacenter_dashboard_header)
    build_marker_id_before = id(page.datacenter_dashboard_build_marker_text)
    page.datacenter_dashboard_reports_dir_field.value = str(reports_dir)
    page.datacenter_dashboard_refresh_button.on_click(None)

    assert page.datacenter_dashboard_overall_status_field.value == "PARTIAL"
    assert page.datacenter_dashboard_readiness_text.value == "Readiness: PARTIAL"
    assert page.datacenter_dashboard_reports_status_text.value == "Reports: found=1 missing=3"
    assert page.datacenter_dashboard_decisions_status_text.value == "Decisions: total=1"
    assert page.datacenter_dashboard_candidate_status_text.value == "Candidate Pullbacks: 0"
    assert id(page.datacenter_dashboard_header) == header_id_before
    assert id(page.datacenter_dashboard_build_marker_text) == build_marker_id_before
    assert "readiness=PARTIAL" in page.datacenter_dashboard_parse_summary_field.value
    assert "found_reports=1" in page.datacenter_dashboard_parse_summary_field.value
    assert "missing_reports=3" in page.datacenter_dashboard_parse_summary_field.value
    assert "total_parsed_rows=1" in page.datacenter_dashboard_parse_summary_field.value
    assert "total_parse_warnings=0" in page.datacenter_dashboard_parse_summary_field.value
    assert "decision_total=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "NEUTRAL=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "NO_PULLBACK=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "entry_readiness.NOT_READY=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "candidate_priority.P5_NOT_READY=1" in page.datacenter_dashboard_decision_summary_field.value
    assert (
        page.datacenter_dashboard_candidate_pullbacks_column.controls[0].value
        == "No candidate pullbacks available."
    )
    assert page.datacenter_dashboard_inspector_action_field.value == "NVDA | NEUTRAL | INFO"
    assert page.datacenter_dashboard_conflict_detected_field.value == "False"
    assert page.datacenter_dashboard_pullback_validity_field.value == "NO_PULLBACK"
    assert page.datacenter_dashboard_pullback_reason_field.value == "NO_PULLBACK_CONTEXT"
    first_card = page.datacenter_dashboard_reports_column.controls[0]
    assert "rolling 30d: MISSING" in first_card.content.controls[0].value
    assert "parsed_rows: 0" in first_card.content.controls[3].value
    daily_card = page.datacenter_dashboard_reports_column.controls[3]
    assert "daily: OK" in daily_card.content.controls[0].value
    assert "parsed_rows: 1" in daily_card.content.controls[3].value
    assert "warnings: 0" in daily_card.content.controls[4].value
    dashboard_text_labels = _descendant_text_values(page)
    scroll_text_labels = _descendant_text_values_for_control(
        page.datacenter_dashboard_scroll_content
    )
    assert "Readiness: PARTIAL" in dashboard_text_labels
    assert "Reports: found=1 missing=3" in dashboard_text_labels
    assert "Decisions: total=1" in dashboard_text_labels
    assert "Candidate Pullbacks: 0" in dashboard_text_labels
    assert "Dashboard Summary" in scroll_text_labels
    assert "Reports" in scroll_text_labels
    assert "Command Center" in scroll_text_labels
    assert "Candidate Pullbacks" in scroll_text_labels
    assert "Inspector" in scroll_text_labels


def test_run_app_datacenter_dashboard_command_center_shows_grouped_read_only_rows(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler.json"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "datacenter_rolling_30_2026-05-22_0000_full.csv").write_text(
        "\n".join(
            [
                "ticker;status;distance_to_ema20;blocking_reasons",
                "META;BUY_ZONE;16.5;STRUCTURAL_BLOCK",
                "MRVL;LEADER;;",
                "TSM;BUY_ZONE;;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "datacenter_rolling_5_2026-05-22_0000_full.csv").write_text(
        "ticker;status\nTSM;PULLBACK_CANDIDATE\n",
        encoding="utf-8",
    )
    (reports_dir / "datacenter_rolling_2_2026-05-22_0000_full.csv").write_text(
        "ticker;high_exit_risk_days_count;status;latest_bos_event_type;latest_bos_freshness\nLRCX;1;;;\nNVDA;;PULLBACK_CANDIDATE;BOS_DOWN;FRESH\n",
        encoding="utf-8",
    )
    (reports_dir / "datacenter_daily_2026-05-22_0000_full.csv").write_text(
        "\n".join(
            [
                "ticker;status;reason;ma_break_status;freshness_status",
                "NVDA;SELL;close_below_ema20;;",
                "AVGO;WATCH;exit_risk;;",
                "TSM;BULLISH;;OK;FRESH_BULLISH_SIGNAL",
                "INTC;SIDEWAYS;;;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary",
        lambda log_dir: None,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.list_scheduler_log_files",
        lambda log_dir: [],
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_scheduler_status",
        lambda log_dir: None,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {
            "timer_path": "/tmp/timer",
            "on_calendar": "*-*-* 05:30:00",
            "installed": True,
            "status_summary": "ok",
            "error": None,
        },
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.datacenter_dashboard_reports_dir_field.value = str(reports_dir)
    page.datacenter_dashboard_refresh_button.on_click(None)

    assert "decision_total=7" in page.datacenter_dashboard_decision_summary_field.value
    assert page.datacenter_dashboard_readiness_text.value == "Readiness: READY"
    assert page.datacenter_dashboard_reports_status_text.value == "Reports: found=4 missing=0"
    assert page.datacenter_dashboard_decisions_status_text.value == "Decisions: total=7"
    assert page.datacenter_dashboard_candidate_status_text.value == "Candidate Pullbacks: 1"
    assert "SELL=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "REDUCE=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "TIGHTEN_STOP=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "BUY_NOW=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "BLOCKED=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "WATCH=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "NEUTRAL=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "STRUCTURE_BLOCKED_PULLBACK=1" in page.datacenter_dashboard_decision_summary_field.value
    assert "entry_readiness.NOT_READY=6" in page.datacenter_dashboard_decision_summary_field.value
    assert "candidate_priority.P9_READY_TO_WATCH=0" not in page.datacenter_dashboard_decision_summary_field.value
    candidate_titles = [
        control.content.controls[0].value
        for control in page.datacenter_dashboard_candidate_pullbacks_column.controls
        if hasattr(control, "content")
    ]
    assert "TSM | P9_NOT_CANDIDATE | INSUFFICIENT_DATA | BUY_NOW" in candidate_titles
    candidate_readiness_lines = [
        control.content.controls[2].value
        for control in page.datacenter_dashboard_candidate_pullbacks_column.controls
        if hasattr(control, "content")
    ]
    assert "entry_readiness_reason: MISSING_PULLBACK_VALIDITY_OR_ACTION" in candidate_readiness_lines
    labels = [
        control.value
        for control in page.datacenter_dashboard_command_center_column.controls
        if hasattr(control, "value")
    ]
    assert "Critical exits" in labels
    assert "Buy candidates" in labels
    assert "Blocked / neutral" in labels
    row_titles = [
        control.content.controls[0].value
        for control in page.datacenter_dashboard_command_center_column.controls
        if hasattr(control, "content")
    ]
    assert "NVDA | SELL | CRITICAL" in row_titles
    assert "AVGO | REDUCE | HIGH" in row_titles
    assert "LRCX | TIGHTEN_STOP | MEDIUM" in row_titles
    assert "META | BLOCKED | HIGH" in row_titles
    assert "TSM | BUY_NOW | HIGH" in row_titles
    assert "MRVL | WATCH | LOW" in row_titles
    assert "INTC | NEUTRAL | INFO" in row_titles
    page.datacenter_dashboard_inspector_ticker_dropdown.value = "NVDA"
    page.datacenter_dashboard_inspector_ticker_dropdown.on_change(None)
    assert page.datacenter_dashboard_inspector_action_field.value == "NVDA | SELL | CRITICAL"
    assert page.datacenter_dashboard_conflict_detected_field.value == "True"
    assert (
        page.datacenter_dashboard_pullback_validity_field.value
        == "STRUCTURE_BLOCKED_PULLBACK"
    )
    assert (
        page.datacenter_dashboard_pullback_reason_field.value
        == "FRESH_BOS_DOWN_BLOCKS_PULLBACK"
    )
    assert "close_below_ema20" in page.datacenter_dashboard_supporting_signals_field.value
    assert "PULLBACK_CANDIDATE" in page.datacenter_dashboard_conflicting_signals_field.value
    page.datacenter_dashboard_inspector_ticker_dropdown.value = "META"
    page.datacenter_dashboard_inspector_ticker_dropdown.on_change(None)
    assert page.datacenter_dashboard_conflict_detected_field.value == "True"
    assert "STRUCTURAL_BLOCK" in page.datacenter_dashboard_supporting_signals_field.value
    assert "BUY_ZONE" in page.datacenter_dashboard_conflicting_signals_field.value
    assert (
        page.datacenter_dashboard_override_explanation_field.value
        == "Blocking reasons override constructive setup labels."
    )


def test_build_skip_next_run_config_sets_true_without_changing_other_fields():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=False,
        technical_relevance_enabled=True,
    )

    updated = build_skip_next_run_config(config)

    assert updated.skip_next_run is True
    assert updated.enabled_markets == config.enabled_markets
    assert updated.run_time == config.run_time
    assert updated.osakedata_db_path == config.osakedata_db_path
    assert updated.analysis_db_path == config.analysis_db_path
    assert updated.log_dir == config.log_dir
    assert updated.timezone == config.timezone
    assert updated.technical_relevance_enabled is True


def test_build_cancel_skip_next_run_config_sets_false_without_changing_other_fields():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        skip_next_run=True,
        technical_relevance_enabled=True,
    )

    updated = build_cancel_skip_next_run_config(config)

    assert updated.skip_next_run is False
    assert updated.enabled_markets == config.enabled_markets
    assert updated.run_time == config.run_time
    assert updated.osakedata_db_path == config.osakedata_db_path
    assert updated.analysis_db_path == config.analysis_db_path
    assert updated.log_dir == config.log_dir
    assert updated.timezone == config.timezone
    assert updated.technical_relevance_enabled is True


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
