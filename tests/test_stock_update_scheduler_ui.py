from __future__ import annotations

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
    get_systemd_user_timer_path,
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

_LEGACY_DASHBOARD_CONFIG_KEYS = {
    "datacenter_dashboard_fallback_to_reports": True,
    "datacenter_dashboard_reports_reference_db": (
        "/home/kalle/projects/rawcandle/temp/datacenter_dashboard_reports_reference.db"
    ),
    "datacenter_dashboard_reports_reference_enabled": True,
    "datacenter_dashboard_reports_reference_html_output_dir": (
        "/home/kalle/projects/rawcandle/swing_reports"
    ),
    "datacenter_dashboard_run_acceptance_report": True,
    "datacenter_dashboard_source_mode": "enrichment",
    "datacenter_enrichment_apply_migrations": False,
    "datacenter_enrichment_enabled": True,
    "datacenter_v3_reports_ecosystem": "DATACENTER",
    "datacenter_v3_reports_enabled": False,
    "datacenter_v3_reports_output_dir": "/home/kalle/projects/rawcandle/swing_reports/v3",
    "datacenter_v3_reports_taxonomy_version": "DC_TAXONOMY_FULL_V1",
}


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
                **_LEGACY_DASHBOARD_CONFIG_KEYS,
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
    for name in [
        "stock_update_omxh_20260617T0900Z.txt",
        "datacenter_pipeline_usa_20260617T0901Z.txt",
        "ec_source_layer_usa_20260617T0902Z.txt",
        "ignore.json",
    ]:
        (log_dir / name).write_text("x", encoding="utf-8")

    assert [entry["filename"] for entry in list_scheduler_log_files(str(log_dir))] == [
        "ec_source_layer_usa_20260617T0902Z.txt",
        "datacenter_pipeline_usa_20260617T0901Z.txt",
        "stock_update_omxh_20260617T0900Z.txt",
    ]


def test_list_scheduler_log_files_limits_to_10_newest_known_scheduler_logs(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    names = [
        "stock_update_omxh_20260617T0900Z.txt",
        "stock_update_usa_20260617T0901Z.txt",
        "datacenter_pipeline_usa_20260617T0902Z.txt",
        "ec_source_layer_usa_20260617T0903Z.txt",
        "stock_update_omxs_20260617T0904Z.txt",
        "datacenter_pipeline_usa_20260617T0905Z.txt",
        "ec_source_layer_usa_20260617T0906Z.txt",
        "stock_update_usa_20260617T0907Z.txt",
        "datacenter_pipeline_usa_20260617T0908Z.txt",
        "ec_source_layer_usa_20260617T0909Z.txt",
        "stock_update_omxh_20260617T0910Z.txt",
        "random_notes_20260617T0911Z.txt",
    ]
    for name in names:
        (log_dir / name).write_text(name, encoding="utf-8")

    results = list_scheduler_log_files(str(log_dir))

    assert len(results) == 10
    assert results[0]["filename"] == "stock_update_omxh_20260617T0910Z.txt"
    assert results[-1]["filename"] == "stock_update_usa_20260617T0901Z.txt"
    assert all(
        entry["type"] in {"market_log", "datacenter_log", "ec_source_layer_log"}
        for entry in results
    )


def test_build_text_log_browser_url_quotes_path(tmp_path):
    path = tmp_path / "log file.txt"
    assert build_text_log_browser_url(str(path)) == "/log%20file.txt"


def test_launch_browser_url_handles_sync_page_method():
    page = _FakePage()

    launch_browser_url(page, "https://example.test")

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


def test_get_systemd_user_timer_path_uses_stock_update_scheduler_name():
    assert get_systemd_user_timer_path().name == "stock-update-scheduler.timer"


def test_read_systemd_user_timer_status_checks_stock_update_scheduler_unit(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return Mock(stdout="active\n", stderr="", returncode=0)

    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.get_systemd_user_timer_path",
        lambda: Path("/tmp/stock-update-scheduler.timer"),
    )
    monkeypatch.setattr(
        Path,
        "exists",
        lambda self: str(self) == "/tmp/stock-update-scheduler.timer",
    )
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding="utf-8": "[Timer]\nOnCalendar=*-*-* 05:30:00\n",
    )

    status = read_systemd_user_timer_status()

    assert calls[0] == [
        "systemctl",
        "--user",
        "is-active",
        "stock-update-scheduler.timer",
    ]
    assert status["status_summary"] == "active"


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
    assert page.running_status_text.value == "Scheduler status: not running"


def test_run_app_loads_current_style_local_config_with_legacy_dashboard_keys(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"installed": False, "status_summary": "missing"},
    )

    page = _FakePage()
    run_app(page, str(config_path))

    loaded = read_scheduler_config(str(config_path))
    assert page.title == "RawCandle stock update scheduler"
    assert loaded.datacenter_dashboard_source_mode == "enrichment"
    assert loaded.datacenter_enrichment_enabled is True


def test_run_app_log_open_button_launches_asset_url(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "stock_update_omxh_20260617T0900Z.txt").write_text(
        "hello log\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"installed": False, "status_summary": "missing"},
    )

    page = _FakePage()
    run_app(page, str(config_path))

    assert "size=" in page.logs_column.controls[0].controls[0].value
    page.logs_column.controls[0].controls[1].on_click(None)

    assert page.launched_urls == ["/stock_update_omxh_20260617T0900Z.txt"]


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
    assert app_mock.call_args.kwargs["view"].value == "web_browser"
    assert app_mock.call_args.kwargs["assets_dir"] == str(config_path.parent / "logs")


def test_run_app_without_summary_or_logs_shows_clear_messages(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"installed": False, "status_summary": "missing", "on_calendar": None, "timer_path": "x", "error": None},
    )

    page = _FakePage()
    run_app(page, str(config_path))

    assert page.summary_field.value == "No scheduler summary JSON found."
    assert page.logs_column.controls[0].value == "No text log files found."


def test_run_app_formats_summary_lines_from_latest_summary(tmp_path, monkeypatch):
    config_path = tmp_path / "scheduler.json"
    _write_config(config_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    (log_dir / "stock_update_scheduler_summary_20260617T080000Z.json").write_text(
        json.dumps(
            {
                "overall_status": "OK",
                "enabled_markets": ["omxh", "usa"],
                "summary_json_path": "/tmp/summary.json",
                "technical_relevance_status": "OK",
                "ec_source_layer_status": "SKIPPED",
                "market_results": [
                    {
                        "market": "omxh",
                        "summary_status": "OK",
                        "log_path": "/tmp/omxh.txt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {"installed": False, "status_summary": "missing", "on_calendar": None, "timer_path": "x", "error": None},
    )

    page = _FakePage()
    run_app(page, str(config_path))

    assert "overall_status=OK" in page.summary_field.value
    assert "enabled_markets=omxh,usa" in page.summary_field.value
    assert "market=omxh status=OK log=/tmp/omxh.txt" in page.summary_field.value


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
