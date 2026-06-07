from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dev_tools.ecosystem_dashboard_read_model import (
    EcosystemDashboardRunRef,
    EcosystemDashboardSnapshot,
)
from dev_tools.run_datacenter_dashboard_html import DatacenterDashboardHtmlGenerationResult
from dev_tools.stock_update_scheduler_ui import (
    DEFAULT_DATACENTER_ANALYSIS_DB,
    DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR,
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
    build_datacenter_dashboard_rolling_report_commands,
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
    run_datacenter_dashboard_rolling_reports_ui_command,
    run_datacenter_ui_command,
    populate_datacenter_report_downloads,
    run_datacenter_build_db_html_ui_action,
    save_config_and_sync_systemd_timer,
    scheduler_skip_button_state,
    scheduler_running_state,
    scheduler_skip_next_run_label,
    update_systemd_timer_on_calendar,
)
from rawcandle.scheduler.config import StockUpdateSchedulerConfig, read_scheduler_config, write_scheduler_config
from rawcandle.scheduler.runner import SchedulerAlreadyRunningError


def _build_config_kwargs():
    return {
        "datacenter_dashboard_enabled": True,
        "datacenter_dashboard_db": "/tmp/ecosystem_dashboard.db",
        "datacenter_dashboard_html_output_dir": "/tmp/html",
        "datacenter_dashboard_reports_reference_enabled": False,
        "datacenter_dashboard_reports_reference_db": "/tmp/reports_reference.db",
        "datacenter_dashboard_reports_reference_html_output_dir": "/tmp/reference_html",
        "datacenter_dashboard_source_mode": "reports",
        "datacenter_enrichment_enabled": False,
        "datacenter_enrichment_apply_migrations": False,
        "datacenter_enrichment_taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "datacenter_enrichment_watchlist_file": "/tmp/watchlist.txt",
        "datacenter_enrichment_write_mode": "replace-date",
        "datacenter_dashboard_fallback_to_reports": True,
        "datacenter_dashboard_run_acceptance_report": False,
    }


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


def _tab_descendants(page, tab_index: int):
    tab = page.datacenter_tabs.tabs[tab_index]
    return list(_iter_flet_descendants(tab.content))


def _descendant_text_values(page, *, tab_index: int):
    values = []
    for control in _tab_descendants(page, tab_index):
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


def _dashboard_html_result(
    *,
    output_path: str = "/tmp/datacenter_dashboard.html",
    report_date: str = "newest",
    selection_mode: str = "newest",
    readiness: str = "READY",
    found_reports: int = 4,
    missing_reports: int = 0,
    decision_total: int = 237,
    candidate_pullback_rows: int = 54,
) -> DatacenterDashboardHtmlGenerationResult:
    return DatacenterDashboardHtmlGenerationResult(
        output_path=output_path,
        report_date=report_date,
        selection_mode=selection_mode,
        readiness=readiness,
        found_reports=found_reports,
        missing_reports=missing_reports,
        decision_total=decision_total,
        candidate_pullback_rows=candidate_pullback_rows,
        summary_lines=(
            f"SUMMARY reports_dir={DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR}",
            f"SUMMARY report_date={report_date}",
        ),
    )


def _install_dashboard_launcher_common_mocks(monkeypatch, *, available_dates=None):
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.load_latest_scheduler_summary", lambda log_dir: None)
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.list_scheduler_log_files", lambda log_dir: [])
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.read_scheduler_status", lambda log_dir: None)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"timer_path": "/tmp/timer", "on_calendar": "*-*-* 05:30:00", "installed": True, "status_summary": "ok", "error": None},
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.list_datacenter_report_dates",
        lambda reports_dir, limit=5: list(available_dates or []),
    )


def _dashboard_snapshot(
    *,
    report_date: str = "2026-05-22",
    run_id: str = "ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z",
    ticker: str = "NVDA",
) -> EcosystemDashboardSnapshot:
    return EcosystemDashboardSnapshot(
        run=EcosystemDashboardRunRef(
            ecosystem_code="DATACENTER",
            report_date=report_date,
            run_id=run_id,
            mode="replace-date",
            status="READY",
            source_report_count=4,
            created_at_utc="2026-05-25T10:00:00Z",
        ),
        source_reports=[{"horizon": "daily"} for _ in range(4)],
        action_summary=[{"action": "WATCH"} for _ in range(2)],
        market_map=[{"name": "Datacenter"} for _ in range(3)],
        watchlist=[{"ticker": ticker}],
        tickers=[{"ticker": ticker}, {"ticker": "CRDO"}],
        decision_trace=[{"ticker": ticker, "trace_index": 0} for _ in range(5)],
    )


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
        tmp_path / "ec_source_layer_usa_20260516T0255Z.txt",
        tmp_path / "stock_update_omxs_20260516T0300Z.txt",
        tmp_path / "ignore_me.txt",
    ]
    for path in files:
        path.write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "stock_update_omxs_20260516T0300Z.txt",
        "ec_source_layer_usa_20260516T0255Z.txt",
        "datacenter_pipeline_usa_20260516T0250Z.txt",
        "stock_update_omxh_20260516T0200Z.log",
        "stock_update_scheduler_summary_20260516T010000Z.json",
    ]
    assert entries[0]["path"].endswith("stock_update_omxs_20260516T0300Z.txt")
    assert entries[0]["text_openable"] is True
    assert entries[1]["text_openable"] is True
    assert entries[2]["text_openable"] is True
    assert entries[3]["text_openable"] is True
    assert entries[4]["text_openable"] is False


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
        **_build_config_kwargs(),
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
        **_build_config_kwargs(),
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
            **_build_config_kwargs(),
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
        **_build_config_kwargs(),
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
    _install_dashboard_launcher_common_mocks(monkeypatch, available_dates=["2026-05-25"])

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


def test_run_app_loads_datacenter_dashboard_scheduler_fields(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler_datacenter_fields.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh", "usa"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
                "datacenter_dashboard_enabled": True,
                "datacenter_enrichment_enabled": True,
                "datacenter_enrichment_apply_migrations": False,
                "datacenter_dashboard_fallback_to_reports": True,
                "datacenter_dashboard_run_acceptance_report": True,
                "datacenter_dashboard_reports_reference_enabled": True,
                "datacenter_dashboard_source_mode": "enrichment",
                "datacenter_enrichment_taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "datacenter_enrichment_watchlist_file": "/tmp/watchlist.txt",
                "datacenter_enrichment_write_mode": "replace-date",
                "datacenter_dashboard_db": "/tmp/ecosystem_dashboard.db",
                "datacenter_dashboard_html_output_dir": "/tmp/html",
                "datacenter_dashboard_reports_reference_db": "/tmp/reports_reference.db",
                "datacenter_dashboard_reports_reference_html_output_dir": "/tmp/reference_html",
            }
        ),
        encoding="utf-8",
    )
    _install_dashboard_launcher_common_mocks(monkeypatch, available_dates=["2026-05-25"])

    page = _FakePage()
    run_app(page, str(config_path))

    assert page.datacenter_dashboard_enabled_checkbox.value is True
    assert page.datacenter_enrichment_enabled_checkbox.value is True
    assert page.datacenter_enrichment_apply_migrations_checkbox.value is False
    assert page.datacenter_dashboard_fallback_to_reports_checkbox.value is True
    assert page.datacenter_dashboard_run_acceptance_report_checkbox.value is True
    assert page.datacenter_dashboard_reports_reference_enabled_checkbox.value is True
    assert page.datacenter_dashboard_source_mode_dropdown.value == "enrichment"
    assert page.datacenter_enrichment_taxonomy_version_config_field.value == "DC_TAXONOMY_FULL_V1"
    assert page.datacenter_enrichment_watchlist_file_config_field.value == "/tmp/watchlist.txt"
    assert page.datacenter_enrichment_write_mode_field.value == "replace-date"
    assert page.datacenter_dashboard_db_config_field.value == "/tmp/ecosystem_dashboard.db"
    assert page.datacenter_dashboard_html_output_dir_config_field.value == "/tmp/html"
    assert page.datacenter_dashboard_reports_reference_db_field.value == "/tmp/reports_reference.db"
    assert (
        page.datacenter_dashboard_reports_reference_html_output_dir_field.value
        == "/tmp/reference_html"
    )


def test_run_app_save_config_persists_datacenter_dashboard_scheduler_fields(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler_save_datacenter_fields.json"
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

    page = _FakePage()
    run_app(page, str(config_path))
    page.datacenter_enrichment_enabled_checkbox.value = True
    page.datacenter_dashboard_source_mode_dropdown.value = "enrichment"
    page.datacenter_dashboard_fallback_to_reports_checkbox.value = True
    page.datacenter_dashboard_run_acceptance_report_checkbox.value = True
    page.datacenter_dashboard_reports_reference_enabled_checkbox.value = True
    page.datacenter_enrichment_apply_migrations_checkbox.value = False
    page.datacenter_dashboard_reports_reference_db_field.value = "/tmp/reports_reference.db"
    page.datacenter_dashboard_reports_reference_html_output_dir_field.value = "/tmp/reference_html"
    page.datacenter_dashboard_db_config_field.value = "/tmp/ecosystem_dashboard.db"
    page.datacenter_dashboard_html_output_dir_config_field.value = "/tmp/html"
    page.datacenter_enrichment_taxonomy_version_config_field.value = "DC_TAXONOMY_FULL_V1"
    page.datacenter_enrichment_watchlist_file_config_field.value = "/tmp/watchlist.txt"
    page.datacenter_enrichment_write_mode_field.value = "replace-date"
    page.save_config_button.on_click(None)

    saved = read_scheduler_config(str(config_path))
    assert saved.datacenter_enrichment_enabled is True
    assert saved.datacenter_dashboard_source_mode == "enrichment"
    assert saved.datacenter_dashboard_fallback_to_reports is True
    assert saved.datacenter_dashboard_run_acceptance_report is True
    assert saved.datacenter_dashboard_reports_reference_enabled is True
    assert saved.datacenter_enrichment_apply_migrations is False
    assert saved.datacenter_dashboard_reports_reference_db == "/tmp/reports_reference.db"
    assert (
        saved.datacenter_dashboard_reports_reference_html_output_dir
        == "/tmp/reference_html"
    )
    assert saved.datacenter_dashboard_db == "/tmp/ecosystem_dashboard.db"
    assert saved.datacenter_dashboard_html_output_dir == "/tmp/html"
    assert saved.datacenter_enrichment_taxonomy_version == "DC_TAXONOMY_FULL_V1"
    assert saved.datacenter_enrichment_watchlist_file == "/tmp/watchlist.txt"
    assert saved.datacenter_enrichment_write_mode == "replace-date"


def test_run_app_backward_compatible_missing_reports_reference_fields_saves_defaults(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler_backward_compatible.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["omxh"],
                "log_dir": str(tmp_path / "logs"),
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "datacenter_dashboard_enabled": True,
                "datacenter_dashboard_db": "/tmp/ecosystem_dashboard.db",
                "datacenter_dashboard_html_output_dir": "/tmp/html",
                "datacenter_dashboard_source_mode": "reports",
                "datacenter_enrichment_enabled": False,
                "datacenter_enrichment_apply_migrations": False,
                "datacenter_enrichment_taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "datacenter_enrichment_watchlist_file": "/tmp/watchlist.txt",
                "datacenter_enrichment_write_mode": "replace-date",
                "datacenter_dashboard_fallback_to_reports": True,
                "datacenter_dashboard_run_acceptance_report": False,
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

    page = _FakePage()
    run_app(page, str(config_path))

    assert page.datacenter_dashboard_reports_reference_enabled_checkbox.value is False
    assert page.datacenter_dashboard_reports_reference_db_field.value
    assert page.datacenter_dashboard_reports_reference_html_output_dir_field.value == "/tmp/html"

    page.save_config_button.on_click(None)
    saved = read_scheduler_config(str(config_path))
    assert saved.datacenter_dashboard_reports_reference_enabled is False
    assert saved.datacenter_dashboard_reports_reference_db
    assert saved.datacenter_dashboard_reports_reference_html_output_dir == "/tmp/html"


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


def test_scheduler_ui_startup_accepts_port_override(tmp_path, monkeypatch):
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

    code = main(["--config", str(config_path), "--port", "8566"])

    assert code == 0
    assert captured["port"] == 8566
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

    dashboard_rolling_commands = build_datacenter_dashboard_rolling_report_commands(
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        signal_date="2026-05-15",
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
        watchlist_file=DEFAULT_DATACENTER_WATCHLIST_FILE,
        output_dir=DEFAULT_DATACENTER_OUTPUT_DIR,
        time_tag="0925",
    )
    assert [spec["window_size"] for spec in dashboard_rolling_commands] == ["2", "5", "30"]
    assert dashboard_rolling_commands[0]["command"][dashboard_rolling_commands[0]["command"].index("--output-md") + 1].endswith(
        "datacenter_rolling_2_2026-05-15_0925_full.md"
    )
    assert dashboard_rolling_commands[1]["command"][dashboard_rolling_commands[1]["command"].index("--output-md") + 1].endswith(
        "datacenter_rolling_5_2026-05-15_0925_full.md"
    )
    assert dashboard_rolling_commands[2]["command"][dashboard_rolling_commands[2]["command"].index("--output-md") + 1].endswith(
        "datacenter_rolling_30_2026-05-15_0925_full.md"
    )
    assert dashboard_rolling_commands[0]["command"][dashboard_rolling_commands[0]["command"].index("--output-csv") + 1].endswith(
        "datacenter_rolling_2_2026-05-15_0925_full.csv"
    )
    assert "datacenter_rolling_2026-05-15_0925_20d_full.md" not in dashboard_rolling_commands[0]["command"][-2]

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


def test_run_datacenter_dashboard_rolling_reports_ui_command_runs_three_horizons_and_logs_summary(
    monkeypatch, tmp_path
):
    class _ImmediateThread:
        def __init__(self, *, target, daemon):
            self._target = target

        def start(self):
            self._target()

    completed_calls = []

    def _fake_run(command, **kwargs):
        completed_calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.threading.Thread", _ImmediateThread)
    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.subprocess.run", _fake_run)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.populate_datacenter_report_downloads",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.build_datacenter_dashboard_rolling_report_commands",
        lambda **kwargs: build_datacenter_dashboard_rolling_report_commands(
            **kwargs,
            time_tag="0925",
        ),
    )

    page = _FakePage()
    log_field = Mock()
    log_field.value = ""
    status_field = Mock()
    status_field.value = ""
    status_field.border_color = None
    reports_column = Mock()
    reports_column.controls = []

    run_datacenter_dashboard_rolling_reports_ui_command(
        page=page,
        log_field=log_field,
        status_field=status_field,
        analysis_db=DEFAULT_DATACENTER_ANALYSIS_DB,
        signal_date="2026-05-15",
        taxonomy_version=DEFAULT_DATACENTER_TAXONOMY_VERSION,
        watchlist_file=DEFAULT_DATACENTER_WATCHLIST_FILE,
        output_dir=str(tmp_path),
        reports_column=reports_column,
        assets_root=tmp_path / "assets",
    )

    assert len(completed_calls) == 3
    assert [command[command.index("--window-size") + 1] for command in completed_calls] == ["2", "5", "30"]
    assert any("=== Datacenter: Generate Dashboard Rolling Reports ===" in line for line in log_field.value.splitlines())
    assert "=== Datacenter: Generate Rolling 2d Report ===" in log_field.value
    assert "=== Datacenter: Generate Rolling 5d Report ===" in log_field.value
    assert "=== Datacenter: Generate Rolling 30d Report ===" in log_field.value
    assert "SUMMARY dashboard_rolling_reports.attempted=3" in log_field.value
    assert "SUMMARY dashboard_rolling_reports.succeeded=3" in log_field.value
    assert "SUMMARY dashboard_rolling_reports.failed=0" in log_field.value
    assert f"SUMMARY dashboard_rolling_reports.output_dir={tmp_path}" in log_field.value
    assert "SUMMARY dashboard_rolling_reports.end_date=2026-05-15" in log_field.value
    assert "SUMMARY dashboard_rolling_2.status=OK" in log_field.value
    assert "SUMMARY dashboard_rolling_5.status=OK" in log_field.value
    assert "SUMMARY dashboard_rolling_30.status=OK" in log_field.value


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
    _install_dashboard_launcher_common_mocks(
        monkeypatch,
        available_dates=["2026-05-25", "2026-05-24", "2026-05-23", "2026-05-22", "2026-05-21"],
    )
    dashboard_rolling_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_datacenter_ui_command",
        lambda **kwargs: captured.append(kwargs),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: type(
            "Inspection",
            (),
            {
                "enabled": 1,
                "ecosystem_code": "DATACENTER",
                "dashboard_db": "/tmp/ecosystem_dashboard.db",
                "reports_dir": "/tmp/swing_reports",
                "html_output_dir": "/tmp/html",
                "expected_report_date": "2026-05-22",
                "expected_html_output_path": "/tmp/html/datacenter_dashboard_2026-05-22.html",
                "mode": "replace-date",
                "render_html": 1,
                "usa_enabled": 0,
                "datacenter_pipeline_enabled": 1,
                "skip_next_run": 0,
                "date_status": "OK",
                "status": "OK",
            },
        )(),
    )
    build_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_datacenter_build_db_html_ui_action",
        lambda **kwargs: build_calls.append(kwargs),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_datacenter_dashboard_rolling_reports_ui_command",
        lambda **kwargs: dashboard_rolling_calls.append(kwargs),
    )

    page = _FakePage()
    run_app(page, str(config_path))
    _ = capsys.readouterr().out

    assert [tab.text for tab in page.datacenter_tabs.tabs] == [
        "Scheduler",
        "Datacenter",
        "Datacenter Dashboard",
    ]
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
    datacenter_text_labels = _descendant_text_values(page, tab_index=1)
    assert "Daily Datacenter flow:\nstock update -> .md reports -> ecosystem_dashboard.db -> DB-backed HTML" in datacenter_text_labels
    assert "Refresh Status" in datacenter_text_labels
    assert "Show Datacenter Plan" in datacenter_text_labels
    assert "Run Full Chain" in datacenter_text_labels
    assert "Build DB + HTML for Date" in datacenter_text_labels
    assert "Show Watermarks" in datacenter_text_labels
    assert "Advanced / Debug" in datacenter_text_labels
    assert "Dry Run Pipeline" in datacenter_text_labels
    assert "Run Audit" in datacenter_text_labels
    assert "Generate Daily Report" in datacenter_text_labels
    assert "Generate Rolling Report" in datacenter_text_labels
    assert "Generate Dashboard Rolling Reports" in datacenter_text_labels
    assert page.datacenter_report_date_field.value == "2026-05-22"
    dashboard_text_labels = _descendant_text_values(page, tab_index=2)
    assert "Datacenter Dashboard" in dashboard_text_labels
    assert "Dashboard flow:\necosystem_dashboard.db -> DB-backed HTML" in dashboard_text_labels
    assert "Report date" in dashboard_text_labels
    assert "Dashboard DB" in dashboard_text_labels
    assert "HTML output dir" in dashboard_text_labels
    assert "Expected HTML output" in dashboard_text_labels
    assert "Snapshot status" in dashboard_text_labels
    assert "HTML file status" in dashboard_text_labels
    assert "Last action status" in dashboard_text_labels
    assert "Refresh Dashboard Status" in dashboard_text_labels
    assert "Inspect DB Snapshot" in dashboard_text_labels
    assert "Render HTML from Existing DB Snapshot" in dashboard_text_labels
    assert "Open HTML File" in dashboard_text_labels
    assert "Build DB + HTML for Date" not in dashboard_text_labels
    assert page.datacenter_dashboard_db_field.value == "/tmp/ecosystem_dashboard.db"
    assert page.datacenter_dashboard_html_output_dir_field.value == "/tmp/html"
    assert page.datacenter_dashboard_report_date_field.value == "2026-05-22"
    assert (
        page.datacenter_dashboard_expected_html_output_field.value
        == "/tmp/html/datacenter_dashboard_2026-05-22.html"
    )

    page.datacenter_signal_date_field.value = "2026-05-15"
    page.datacenter_start_date_field.value = "2026-01-01"
    page.datacenter_dry_run_button.on_click(None)
    dry_run = captured[-1]
    assert dry_run["title"] == "Dry Run Pipeline"
    assert "--dry-run" in dry_run["command"]
    assert dry_run["command"][dry_run["command"].index("--weekly-window-size") + 1] == "20"
    assert dry_run["command"][dry_run["command"].index("--watchlist-file") + 1] == DEFAULT_DATACENTER_WATCHLIST_FILE

    page.datacenter_run_full_chain_button.on_click(None)
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

    page.datacenter_dashboard_rolling_reports_button.on_click(None)
    assert dashboard_rolling_calls
    assert dashboard_rolling_calls[-1]["signal_date"] == "2026-05-15"
    assert dashboard_rolling_calls[-1]["output_dir"] == DEFAULT_DATACENTER_OUTPUT_DIR

    page.datacenter_signal_date_field.value = "2026-05-16"
    page.datacenter_watchlist_file_field.value = "/tmp/custom_watchlist.txt"
    page.datacenter_plan_button.on_click(None)
    assert "Show Datacenter Plan status=OK" in page.datacenter_status_field.value
    assert "expected_report_date=2026-05-22" in page.datacenter_status_field.value

    page.datacenter_report_date_field.value = "2026-05-20"
    page.datacenter_build_db_html_button.on_click(None)
    assert build_calls
    assert build_calls[-1]["report_date"] == "2026-05-20"
    assert build_calls[-1]["dashboard_db"] == "/tmp/ecosystem_dashboard.db"
    assert build_calls[-1]["reports_dir"] == "/tmp/swing_reports"
    assert build_calls[-1]["html_output_path"] == "/tmp/html/datacenter_dashboard_2026-05-20.html"

    page.datacenter_watermarks_button.on_click(None)
    watermark = captured[-1]
    assert watermark["title"] == "Show Watermarks"
    assert "run_datacenter_pipeline_watermark.py" in watermark["command"]

    page.datacenter_daily_report_button.on_click(None)
    daily_override = captured[-1]
    assert daily_override["command"][daily_override["command"].index("--watchlist-file") + 1] == "/tmp/custom_watchlist.txt"


def test_run_app_adds_datacenter_dashboard_launcher_tab_without_rendered_dashboard_sections(
    tmp_path, monkeypatch
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
    _install_dashboard_launcher_common_mocks(monkeypatch, available_dates=["2026-05-25"])

    page = _FakePage()
    run_app(page, str(config_path))

    assert [tab.text for tab in page.datacenter_tabs.tabs] == [
        "Scheduler",
        "Datacenter",
        "Datacenter Dashboard",
    ]
    dashboard_text = _descendant_text_values(page, tab_index=2)
    all_text = _descendant_text_values_for_control(page.datacenter_tabs)
    assert "Datacenter Dashboard" in dashboard_text
    assert "Refresh Dashboard Status" in dashboard_text
    assert "Inspect DB Snapshot" in dashboard_text
    assert "Render HTML from Existing DB Snapshot" in dashboard_text
    assert "Open HTML File" in dashboard_text
    assert "Report date" in dashboard_text
    assert "Dashboard DB" in dashboard_text
    assert "Command Center" not in dashboard_text
    assert "Candidate Pullbacks" not in dashboard_text
    assert "Ticker Inspector / Details" not in dashboard_text
    assert "REAL RENDER CHECK: DATACENTER DASHBOARD V3" not in all_text
    assert "dashboard_ui_visible_v1" not in all_text
    assert "dashboard_real_render_v3=1" not in all_text


def test_datacenter_build_db_html_for_date_invalid_or_empty_date_shows_error_and_does_not_run(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["usa"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    _install_dashboard_launcher_common_mocks(monkeypatch, available_dates=["2026-05-25"])
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: type(
            "Inspection",
            (),
            {
                "enabled": 1,
                "ecosystem_code": "DATACENTER",
                "dashboard_db": "/tmp/ecosystem_dashboard.db",
                "reports_dir": "/tmp/swing_reports",
                "html_output_dir": "/tmp/html",
                "expected_report_date": "2026-05-22",
                "expected_html_output_path": "/tmp/html/datacenter_dashboard_2026-05-22.html",
                "mode": "replace-date",
                "render_html": 1,
                "usa_enabled": 1,
                "datacenter_pipeline_enabled": 1,
                "skip_next_run": 0,
                "date_status": "OK",
                "status": "OK",
            },
        )(),
    )
    calls = []
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_datacenter_build_db_html_ui_action",
        lambda **kwargs: calls.append(kwargs),
    )

    page = _FakePage()
    run_app(page, str(config_path))

    page.datacenter_report_date_field.value = ""
    page.datacenter_build_db_html_button.on_click(None)
    assert "report_date is required" in page.datacenter_status_field.value
    assert calls == []

    page.datacenter_report_date_field.value = "2026/05/22"
    page.datacenter_build_db_html_button.on_click(None)
    assert "invalid report_date" in page.datacenter_status_field.value
    assert calls == []


def test_datacenter_refresh_status_and_plan_do_not_call_heavy_paths(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler.json"
    config_path.write_text(
        json.dumps(
            {
                "analysis_db_path": "/tmp/analysis.db",
                "enabled_markets": ["usa"],
                "log_dir": "/tmp/logs",
                "osakedata_db_path": "/tmp/osakedata.db",
                "run_time": "05:30",
                "timezone": "Europe/Helsinki",
            }
        ),
        encoding="utf-8",
    )
    _install_dashboard_launcher_common_mocks(monkeypatch, available_dates=["2026-05-25"])
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: type(
            "Inspection",
            (),
            {
                "enabled": 1,
                "ecosystem_code": "DATACENTER",
                "dashboard_db": "/tmp/ecosystem_dashboard.db",
                "reports_dir": "/tmp/swing_reports",
                "html_output_dir": "/tmp/html",
                "expected_report_date": "2026-05-22",
                "expected_html_output_path": "/tmp/html/datacenter_dashboard_2026-05-22.html",
                "mode": "replace-date",
                "render_html": 1,
                "usa_enabled": 1,
                "datacenter_pipeline_enabled": 1,
                "skip_next_run": 0,
                "date_status": "OK",
                "status": "OK",
            },
        )(),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_scheduler_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run_scheduler_config should not be called")
        ),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_datacenter_ui_command",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("run_datacenter_ui_command should not be called")
        ),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.run_datacenter_build_db_html_ui_action",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("build action should not be called")
        ),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_ecosystem_dashboard_build",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("dashboard build should not be called")
        ),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_datacenter_dashboard_html_file",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("html render should not be called")
        ),
    )

    page = _FakePage()
    run_app(page, str(config_path))

    page.datacenter_refresh_status_button.on_click(None)
    assert "Refresh Status status=OK" in page.datacenter_status_field.value

    page.datacenter_plan_button.on_click(None)
    assert "Show Datacenter Plan status=OK" in page.datacenter_status_field.value


def test_run_datacenter_build_db_html_ui_action_success_updates_status(
    monkeypatch, tmp_path
):
    class _ImmediateThread:
        def __init__(self, *, target, daemon):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.threading.Thread", _ImmediateThread)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_ecosystem_dashboard_build",
        lambda **kwargs: ("ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z", []),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_datacenter_dashboard_html_file",
        lambda **kwargs: _dashboard_html_result(output_path=kwargs["output"]),
    )

    page = _FakePage()
    log_field = Mock()
    log_field.value = ""
    status_field = Mock()
    status_field.value = ""
    status_field.border_color = None

    run_datacenter_build_db_html_ui_action(
        page=page,
        status_field=status_field,
        log_field=log_field,
        report_date="2026-05-22",
        dashboard_db="/tmp/ecosystem_dashboard.db",
        reports_dir="/tmp/swing_reports",
        html_output_path="/tmp/html/datacenter_dashboard_2026-05-22.html",
    )

    assert "status=OK" in status_field.value
    assert "report_date=2026-05-22" in status_field.value
    assert "dashboard_db=/tmp/ecosystem_dashboard.db" in status_field.value
    assert "html_output_path=/tmp/html/datacenter_dashboard_2026-05-22.html" in status_field.value
    assert "run_id=ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z" in status_field.value


def test_run_datacenter_build_db_html_ui_action_failure_updates_status(
    monkeypatch
):
    class _ImmediateThread:
        def __init__(self, *, target, daemon):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("dev_tools.stock_update_scheduler_ui.threading.Thread", _ImmediateThread)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_ecosystem_dashboard_build",
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing reports")),
    )

    page = _FakePage()
    log_field = Mock()
    log_field.value = ""
    status_field = Mock()
    status_field.value = ""
    status_field.border_color = None

    run_datacenter_build_db_html_ui_action(
        page=page,
        status_field=status_field,
        log_field=log_field,
        report_date="2026-05-22",
        dashboard_db="/tmp/ecosystem_dashboard.db",
        reports_dir="/tmp/swing_reports",
        html_output_path="/tmp/html/datacenter_dashboard_2026-05-22.html",
    )

    assert "status=FAILED" in status_field.value
    assert "failure_stage=source_reports" in status_field.value
    assert "missing reports" in status_field.value


def test_datacenter_dashboard_viewer_invalid_or_empty_report_date_shows_error_and_does_not_run(
    tmp_path, monkeypatch
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
    _install_dashboard_launcher_common_mocks(monkeypatch)
    read_calls: list[dict[str, object]] = []
    render_calls: list[dict[str, object]] = []
    open_calls: list[str] = []
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.load_dashboard_snapshot",
        lambda **kwargs: read_calls.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_datacenter_dashboard_html_file",
        lambda **kwargs: render_calls.append(kwargs),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.open_datacenter_dashboard_html",
        lambda path: open_calls.append(path),
    )

    page = _FakePage()
    run_app(page, str(config_path))

    page.datacenter_dashboard_report_date_field.value = ""
    page.datacenter_dashboard_refresh_button.on_click(None)
    assert "dashboard_status.status=FAILED" in page.datacenter_dashboard_status_field.value
    assert "reason=report_date is required" in page.datacenter_dashboard_status_field.value

    page.datacenter_dashboard_report_date_field.value = "2026/05/22"
    page.datacenter_dashboard_inspect_button.on_click(None)
    assert "dashboard_inspect.status=FAILED" in page.datacenter_dashboard_status_field.value
    assert "invalid report date, expected YYYY-MM-DD" in page.datacenter_dashboard_status_field.value

    page.datacenter_dashboard_render_button.on_click(None)
    assert "dashboard_html.status=FAILED" in page.datacenter_dashboard_status_field.value

    page.datacenter_dashboard_open_button.on_click(None)
    assert "dashboard_open.status=FAILED" in page.datacenter_dashboard_status_field.value

    assert read_calls == []
    assert render_calls == []
    assert open_calls == []


def test_datacenter_dashboard_viewer_refresh_status_updates_paths_and_existence(
    tmp_path, monkeypatch
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
    _install_dashboard_launcher_common_mocks(monkeypatch)
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    html_path = html_dir / "datacenter_dashboard_2026-05-22.html"
    html_path.write_text("ok", encoding="utf-8")
    dashboard_db.write_text("db", encoding="utf-8")
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: SimpleNamespace(
            enabled=1,
            ecosystem_code="DATACENTER",
            dashboard_db=str(dashboard_db),
            reports_dir="/tmp/swing_reports",
            html_output_dir=str(html_dir),
            expected_report_date="2026-05-22",
            expected_html_output_path=str(html_path),
            mode="replace-date",
            render_html=1,
            usa_enabled=1,
            datacenter_pipeline_enabled=1,
            skip_next_run=0,
            date_status="OK",
            status="OK",
        ),
    )
    resolve_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "dev_tools.ecosystem_dashboard_read_model.resolve_dashboard_run",
        lambda **kwargs: resolve_calls.append(kwargs)
        or EcosystemDashboardRunRef(
            ecosystem_code="DATACENTER",
            report_date="2026-05-22",
            run_id="RUN123",
            mode="replace-date",
            status="READY",
            source_report_count=4,
            created_at_utc="2026-05-25T10:00:00Z",
        ),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_ecosystem_dashboard_build",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("build should not be called")),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_datacenter_dashboard_html_file",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("render should not be called")),
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.datacenter_dashboard_refresh_button.on_click(None)

    assert resolve_calls
    assert page.datacenter_dashboard_db_field.value == str(dashboard_db)
    assert page.datacenter_dashboard_expected_html_output_field.value == str(html_path)
    assert page.datacenter_dashboard_snapshot_status_field.value == "FOUND"
    assert page.datacenter_dashboard_html_file_status_field.value == "FOUND"
    assert page.datacenter_dashboard_run_id_field.value == "RUN123"
    status = page.datacenter_dashboard_status_field.value
    assert "dashboard_status.report_date=2026-05-22" in status
    assert f"dashboard_status.dashboard_db={dashboard_db}" in status
    assert f"dashboard_status.html_output_path={html_path}" in status
    assert "dashboard_status.snapshot_exists=1" in status
    assert "dashboard_status.html_exists=1" in status
    assert "dashboard_status.status=OK" in status


def test_datacenter_dashboard_viewer_inspect_snapshot_uses_read_model_and_shows_counts(
    tmp_path, monkeypatch
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
    _install_dashboard_launcher_common_mocks(monkeypatch)
    snapshot = _dashboard_snapshot()
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: SimpleNamespace(
            enabled=1,
            ecosystem_code="DATACENTER",
            dashboard_db="/tmp/ecosystem_dashboard.db",
            reports_dir="/tmp/swing_reports",
            html_output_dir="/tmp/html",
            expected_report_date="2026-05-22",
            expected_html_output_path="/tmp/html/datacenter_dashboard_2026-05-22.html",
            mode="replace-date",
            render_html=1,
            usa_enabled=1,
            datacenter_pipeline_enabled=1,
            skip_next_run=0,
            date_status="OK",
            status="OK",
        ),
    )
    monkeypatch.setattr(
        "dev_tools.ecosystem_dashboard_read_model.resolve_dashboard_run",
        lambda **kwargs: snapshot.run,
    )
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        "dev_tools.ecosystem_dashboard_read_model.load_dashboard_snapshot",
        lambda **kwargs: captured.append(kwargs) or snapshot,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_datacenter_dashboard_html_file",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("render should not be called")),
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.datacenter_dashboard_report_date_field.value = "2026-05-22"
    page.datacenter_dashboard_inspect_button.on_click(None)

    assert captured
    assert captured[-1]["run_id"] == snapshot.run.run_id
    status = page.datacenter_dashboard_status_field.value
    assert "dashboard_inspect.status=OK" in status
    assert "report_date=2026-05-22" in status
    assert f"run_id={snapshot.run.run_id}" in status
    assert "source_reports=4" in status
    assert "action_summary=2" in status
    assert "market_map=3" in status
    assert "watchlist=1" in status
    assert "tickers=2" in status
    assert "decision_trace=5" in status


def test_datacenter_dashboard_viewer_render_existing_snapshot_calls_db_backed_html_render(
    tmp_path, monkeypatch
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
    _install_dashboard_launcher_common_mocks(monkeypatch)
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    snapshot = _dashboard_snapshot(report_date="2026-05-22", run_id="RUN456")
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: SimpleNamespace(
            enabled=1,
            ecosystem_code="DATACENTER",
            dashboard_db="/tmp/ecosystem_dashboard.db",
            reports_dir="/tmp/swing_reports",
            html_output_dir=str(html_dir),
            expected_report_date="2026-05-22",
            expected_html_output_path=str(html_dir / "datacenter_dashboard_2026-05-22.html"),
            mode="replace-date",
            render_html=1,
            usa_enabled=1,
            datacenter_pipeline_enabled=1,
            skip_next_run=0,
            date_status="OK",
            status="OK",
        ),
    )
    monkeypatch.setattr(
        "dev_tools.ecosystem_dashboard_read_model.resolve_dashboard_run",
        lambda **kwargs: snapshot.run,
    )
    monkeypatch.setattr(
        "dev_tools.ecosystem_dashboard_read_model.load_dashboard_snapshot",
        lambda **kwargs: snapshot,
    )
    render_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_datacenter_dashboard_html_file",
        lambda **kwargs: render_calls.append(kwargs)
        or _dashboard_html_result(output_path=kwargs["output"], report_date="2026-05-22"),
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.datacenter_dashboard_report_date_field.value = "2026-05-22"
    page.datacenter_dashboard_render_button.on_click(None)

    assert render_calls
    assert render_calls[-1]["dashboard_db"] == "/tmp/ecosystem_dashboard.db"
    assert render_calls[-1]["ecosystem_code"] == "DATACENTER"
    assert render_calls[-1]["run_id"] == "RUN456"
    assert render_calls[-1]["output"] == str(
        html_dir / "datacenter_dashboard_2026-05-22.html"
    )
    status = page.datacenter_dashboard_status_field.value
    assert "dashboard_html.status=OK" in status
    assert "input_mode=dashboard_db" in status
    assert "report_date=2026-05-22" in status
    assert f"html_output_path={html_dir / 'datacenter_dashboard_2026-05-22.html'}" in status


def test_datacenter_dashboard_viewer_render_existing_snapshot_fails_clearly_when_snapshot_missing(
    tmp_path, monkeypatch
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
    _install_dashboard_launcher_common_mocks(monkeypatch)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: SimpleNamespace(
            enabled=1,
            ecosystem_code="DATACENTER",
            dashboard_db="/tmp/ecosystem_dashboard.db",
            reports_dir="/tmp/swing_reports",
            html_output_dir="/tmp/html",
            expected_report_date="2026-05-22",
            expected_html_output_path="/tmp/html/datacenter_dashboard_2026-05-22.html",
            mode="replace-date",
            render_html=1,
            usa_enabled=1,
            datacenter_pipeline_enabled=1,
            skip_next_run=0,
            date_status="OK",
            status="OK",
        ),
    )
    monkeypatch.setattr(
        "dev_tools.ecosystem_dashboard_read_model.resolve_dashboard_run",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("no dashboard run found")),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.generate_datacenter_dashboard_html_file",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("render should not be called")),
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.datacenter_dashboard_render_button.on_click(None)

    assert "dashboard_html.status=FAILED" in page.datacenter_dashboard_status_field.value
    assert "reason=no dashboard run found" in page.datacenter_dashboard_status_field.value


def test_datacenter_dashboard_viewer_open_html_file_uses_open_helper_and_missing_file_fails(
    tmp_path, monkeypatch
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
    _install_dashboard_launcher_common_mocks(monkeypatch)
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    html_path = html_dir / "datacenter_dashboard_2026-05-22.html"
    html_path.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.inspect_scheduler_dashboard_config",
        lambda **kwargs: SimpleNamespace(
            enabled=1,
            ecosystem_code="DATACENTER",
            dashboard_db="/tmp/ecosystem_dashboard.db",
            reports_dir="/tmp/swing_reports",
            html_output_dir=str(html_dir),
            expected_report_date="2026-05-22",
            expected_html_output_path=str(html_path),
            mode="replace-date",
            render_html=1,
            usa_enabled=1,
            datacenter_pipeline_enabled=1,
            skip_next_run=0,
            date_status="OK",
            status="OK",
        ),
    )
    open_calls: list[str] = []
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.open_datacenter_dashboard_html",
        lambda path: open_calls.append(path)
        or {
            "open_status": "OK",
            "opener": "firefox",
            "html_output": path,
            "html_output_windows": "unavailable",
            "html_file_url": Path(path).resolve().as_uri(),
            "manual_lines": [],
        },
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.datacenter_dashboard_report_date_field.value = "2026-05-22"
    page.datacenter_dashboard_open_button.on_click(None)

    assert open_calls == [str(html_path)]
    assert "dashboard_open.status=OK" in page.datacenter_dashboard_status_field.value
    assert f"html_output_path={html_path}" in page.datacenter_dashboard_status_field.value

    html_path.unlink()
    page.datacenter_dashboard_open_button.on_click(None)
    assert "dashboard_open.status=FAILED" in page.datacenter_dashboard_status_field.value
    assert "reason=html file not found" in page.datacenter_dashboard_status_field.value


def test_run_app_does_not_add_broker_or_order_buttons(
    tmp_path, monkeypatch
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

    all_text = _descendant_text_values_for_control(page.datacenter_tabs)
    assert "Send Order" not in all_text
    assert "Buy" not in [value.strip() for value in all_text]
    assert "Sell" not in [value.strip() for value in all_text]


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
