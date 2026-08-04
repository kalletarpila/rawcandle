from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
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
    taxonomy_activation_action_state,
    taxonomy_activation_confirmation_key,
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
from rawcandle.datacenter_taxonomy_replacement import ensure_taxonomy_replacement_schema
from rawcandle.scheduler.config import (
    StockUpdateSchedulerConfig,
    read_scheduler_config,
    write_scheduler_config,
)
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

_TAXONOMY_HEADER = [
    "taxonomy_version",
    "ticker",
    "layer",
    "subindustry",
    "report_group_status",
    "is_primary",
    "role_weight",
    "notes",
]


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


def _write_taxonomy_csv(path: Path, version: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        [version, "AAA", "Compute", "GPU", "CORE", 1, 1.0, ""],
        [version, "BBB", "Power", "UPS", "EXTENDED", 1, 0.8, ""],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_TAXONOMY_HEADER)
        writer.writerows(rows)
    return path


def _write_taxonomy_ui_config(path: Path, *, db_path: Path, current_csv: Path) -> None:
    watchlist = path.parent / "watchlist_test.txt"
    watchlist.write_text("AAA\n", encoding="utf-8")
    write_scheduler_config(
        str(path),
        StockUpdateSchedulerConfig(
            enabled_markets=["usa"],
            osakedata_db_path=str(path.parent / "osakedata_test.sqlite"),
            analysis_db_path=str(db_path),
            log_dir=str(path.parent / "logs"),
            run_time="05:30",
            timezone="Europe/Helsinki",
            datacenter_taxonomy_csv=str(current_csv),
            datacenter_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_enabled=True,
            ec_source_layer_ecosystem="DATACENTER",
            ec_source_layer_taxonomy_csv=str(current_csv),
            ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
            ec_source_layer_watchlist=str(watchlist),
            ec_source_layer_backup_dir=str(path.parent / "backups"),
        ),
    )


def _create_ready_taxonomy_activation_db(tmp_path: Path, proposed_csv: Path) -> Path:
    db_path = tmp_path / "analysis_test.sqlite"
    source_hash = hashlib.sha256(proposed_csv.read_bytes()).hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE ec_ecosystem (ecosystem_id INTEGER PRIMARY KEY, ecosystem_code TEXT, ecosystem_name TEXT, status TEXT)"
        )
        conn.execute(
            """
            CREATE TABLE ec_taxonomy_version (
                taxonomy_version_id INTEGER PRIMARY KEY,
                ecosystem_id INTEGER,
                taxonomy_version_code TEXT,
                source_hash TEXT,
                source_reference TEXT,
                status TEXT,
                is_active INTEGER,
                active_from TEXT,
                active_to TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ec_pipeline_watermark (
                ecosystem_id INTEGER,
                pipeline_name TEXT,
                source_table TEXT,
                latest_signal_date TEXT,
                status TEXT,
                taxonomy_version_id INTEGER
            )
            """
        )
        ensure_taxonomy_replacement_schema(conn)
        conn.execute("INSERT INTO ec_ecosystem VALUES (1, 'DATACENTER', 'Datacenter', 'ACTIVE')")
        conn.execute(
            "INSERT INTO ec_taxonomy_version VALUES (1, 1, 'DC_TAXONOMY_FULL_V1', '', '', 'ACTIVE', 1, '2026-01-01', NULL)"
        )
        conn.execute(
            "INSERT INTO ec_taxonomy_version VALUES (2, 1, 'DC_TAXONOMY_FULL_V2', ?, ?, 'INACTIVE', 0, NULL, NULL)",
            (source_hash, str(proposed_csv)),
        )
        for table, date_col in [
            ("dc_ticker_swing_signal_daily", "signal_date"),
            ("dc_group_swing_signal_daily", "signal_date"),
            ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
            ("dc_group_index_daily", "index_date"),
        ]:
            conn.execute(f"CREATE TABLE {table} ({date_col} TEXT, taxonomy_version TEXT)")
            conn.execute(f"INSERT INTO {table} VALUES ('2026-07-31', 'DC_TAXONOMY_FULL_V2')")
        for table in [
            "ec_ticker_signal_daily",
            "ec_group_signal_daily",
            "ec_group_synthetic_ohlc_daily",
            "ec_group_index_daily",
        ]:
            conn.execute(f"CREATE TABLE {table} (signal_date TEXT, taxonomy_version_id INTEGER)")
            conn.execute(f"INSERT INTO {table} VALUES ('2026-07-31', 2)")
        conn.execute(
            """
            INSERT INTO ec_taxonomy_change_deployment (
                ecosystem_code, previous_taxonomy_version, proposed_taxonomy_version,
                source_reference, source_sha256, change_summary, added_ticker_count,
                removed_ticker_count, membership_change_count, group_change_count,
                status, rebuild_required, rebuild_start_date, dc_rebuild_status,
                ec_rebuild_status, coverage_status, parity_status, activation_status
            ) VALUES ('DATACENTER', 'DC_TAXONOMY_FULL_V1', 'DC_TAXONOMY_FULL_V2',
                      ?, ?, '{}', 1, 0, 0, 0, 'READY_TO_ACTIVATE', 1,
                      '2025-08-01', 'OK', 'OK', 'OK', 'OK', 'NOT_ACTIVE')
            """,
            (str(proposed_csv), source_hash),
        )
        conn.executemany(
            "INSERT INTO ec_pipeline_watermark VALUES (1, ?, ?, '2026-07-31', 'OK', 2)",
            [
                ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily"),
                ("GROUP_SWING_BASE", "dc_group_swing_signal_daily"),
                ("SYNTHETIC_OHLC_BASE", "dc_group_synthetic_ohlc_daily"),
                ("GROUP_INDEX", "dc_group_index_daily"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


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


def test_build_config_from_ui_values_preserves_hidden_existing_settings():
    base_config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "usa"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        technical_relevance_enabled=True,
        datacenter_stage2_incremental_enabled=True,
        datacenter_stage2_overlap_trading_days=5,
        ec_source_layer_enabled=True,
        ec_source_layer_ecosystem="DATACENTER",
        ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_taxonomy_csv="/tmp/taxonomy.csv",
        ec_source_layer_watchlist="/tmp/watchlist.txt",
        ec_source_layer_backup_dir="/tmp/backups",
        ec_source_layer_mode="refresh_latest",
    )

    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata-next.db",
        analysis_db_path="/tmp/analysis-next.db",
        log_dir="/tmp/logs-next",
        timezone="Europe/Helsinki",
        run_time="06:15",
        selected_markets=["USA"],
        technical_relevance_enabled=False,
        base_config=base_config,
    )

    assert config.osakedata_db_path == "/tmp/osakedata-next.db"
    assert config.analysis_db_path == "/tmp/analysis-next.db"
    assert config.enabled_markets == ["usa"]
    assert config.run_time == "06:15"
    assert config.datacenter_stage2_incremental_enabled is True
    assert config.datacenter_stage2_overlap_trading_days == 5
    assert config.ec_source_layer_enabled is True
    assert config.ec_source_layer_mode == "refresh_latest"
    assert config.ec_source_layer_taxonomy_csv == base_config.ec_source_layer_taxonomy_csv
    assert config.ec_source_layer_watchlist == base_config.ec_source_layer_watchlist


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


def test_run_app_exposes_scheduler_and_taxonomy_controls_without_old_datacenter_tab(tmp_path, monkeypatch):
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
    tabs = page.controls[0].tabs
    assert [tab.text for tab in tabs] == ["Scheduler", "Taxonomy"]
    assert page.taxonomy_prepare_button is not None
    assert not hasattr(page, "datacenter_plan_button")
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


def test_taxonomy_activation_button_requires_ready_guard_and_current_confirmation():
    ready_plan = {
        "deployment_id": 1,
        "current_taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "proposed_taxonomy_version": "DC_TAXONOMY_FULL_V2",
        "proposed_source_sha256": "abc",
        "required_signal_date": "2026-07-31",
        "current_db_taxonomy_status": "EXPECTED_CURRENT",
        "current_scheduler_taxonomy_status": "EXPECTED_CURRENT_V1",
        "proposed_scheduler_taxonomy_status": "VALID",
        "scheduler_changed_keys": [
            "datacenter_taxonomy_csv",
            "datacenter_taxonomy_version",
            "ec_source_layer_taxonomy_csv",
            "ec_source_layer_taxonomy_version",
        ],
        "blocking_errors": [],
        "safe_to_activate": True,
    }
    changed_plan = {**ready_plan, "required_signal_date": "2026-08-03"}
    changed_csv_plan = {**ready_plan, "proposed_source_sha256": "def"}

    assert taxonomy_activation_confirmation_key(ready_plan) != taxonomy_activation_confirmation_key(changed_plan)
    assert taxonomy_activation_confirmation_key(ready_plan) != taxonomy_activation_confirmation_key(changed_csv_plan)
    assert taxonomy_activation_action_state(
        orchestration_status="READY_TO_ACTIVATE",
        activation_plan_status="READY_TO_ACTIVATE",
        safe_to_activate=True,
        confirmation_valid=True,
        blocking_errors=[],
    ) == {"activate_disabled": False}
    assert taxonomy_activation_action_state(
        orchestration_status="READY_TO_ACTIVATE",
        activation_plan_status="BLOCKED",
        safe_to_activate=False,
        confirmation_valid=True,
        blocking_errors=["coverage is not accepted"],
    ) == {"activate_disabled": True}


def test_taxonomy_ui_activation_uses_guarded_backend_and_is_idempotent(tmp_path, monkeypatch):
    current_csv = _write_taxonomy_csv(tmp_path / "active_taxonomy_v1.csv", "DC_TAXONOMY_FULL_V1")
    proposed_csv = _write_taxonomy_csv(tmp_path / "proposed_taxonomy_v2.csv", "DC_TAXONOMY_FULL_V2")
    db_path = _create_ready_taxonomy_activation_db(tmp_path, proposed_csv)
    config_path = tmp_path / "scheduler_config_test.json"
    _write_taxonomy_ui_config(config_path, db_path=db_path, current_csv=current_csv)
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui._TAXONOMY_EVIDENCE_ROOT",
        str(tmp_path / "temp" / "datacenter_taxonomy_ui_e2e_dry_run" / "evidence"),
    )
    monkeypatch.setattr(
        "dev_tools.stock_update_scheduler_ui.read_systemd_user_timer_status",
        lambda: {
            "installed": False,
            "status_summary": "missing",
            "on_calendar": None,
            "timer_path": "x",
            "error": None,
        },
    )

    page = _FakePage()
    run_app(page, str(config_path))
    page.analysis_db_field.value = str(db_path)
    page.taxonomy_proposed_csv_field.value = str(proposed_csv)
    page.taxonomy_deployment_id_field.value = "1"
    page.taxonomy_confirmation_state["summary"] = {
        "deployment_id": 1,
        "plan": {
            "current_taxonomy_version": "DC_TAXONOMY_FULL_V1",
            "current_source_reference": str(current_csv),
            "proposed_taxonomy_version": "DC_TAXONOMY_FULL_V2",
            "proposed_source_sha256": hashlib.sha256(proposed_csv.read_bytes()).hexdigest(),
            "date_from": "2025-08-01",
            "date_to": "2026-07-31",
            "selected_rebuild_mode": "DELTA_REBUILD",
            "plan_hash": "fixture-plan",
        },
    }

    page.taxonomy_refresh_button.on_click(None)
    assert page.taxonomy_plan_activation_button.disabled is False

    page.taxonomy_plan_activation_button.on_click(None)
    assert page.taxonomy_activate_button.disabled is True
    original_proposed_csv = proposed_csv.read_bytes()
    proposed_csv.write_bytes(original_proposed_csv + b"\n")
    page.taxonomy_confirm_activation_button.on_click(None)
    assert page.taxonomy_activate_button.disabled is True
    proposed_csv.write_bytes(original_proposed_csv)
    page.taxonomy_plan_activation_button.on_click(None)
    page.taxonomy_confirm_activation_button.on_click(None)
    assert page.taxonomy_activate_button.disabled is False

    page.taxonomy_activate_button.on_click(None)
    loaded = read_scheduler_config(str(config_path))
    assert loaded.datacenter_taxonomy_version == "DC_TAXONOMY_FULL_V2"
    assert loaded.ec_source_layer_taxonomy_version == "DC_TAXONOMY_FULL_V2"
    assert "activation_apply_status" in page.taxonomy_status_field.value
    assert "ACTIVE" in page.taxonomy_status_field.value

    conn = sqlite3.connect(db_path)
    try:
        active = conn.execute(
            "SELECT taxonomy_version_code FROM ec_taxonomy_version WHERE is_active = 1"
        ).fetchone()[0]
        activation_status = conn.execute(
            "SELECT status, activation_status FROM ec_taxonomy_change_deployment WHERE taxonomy_change_id = 1"
        ).fetchone()
    finally:
        conn.close()
    assert active == "DC_TAXONOMY_FULL_V2"
    assert activation_status == ("ACTIVE", "ACTIVE")

    page.taxonomy_plan_activation_button.on_click(None)
    assert '"activation_plan_status": "ALREADY_ACTIVE"' in page.taxonomy_status_field.value
    page.taxonomy_confirm_activation_button.on_click(None)
    assert page.taxonomy_activate_button.disabled is True
