from __future__ import annotations

import argparse
import inspect
import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import flet as ft

from rawcandle.scheduler.config import (
    StockUpdateSchedulerConfig,
    read_scheduler_config,
    validate_run_time,
    validate_scheduler_config,
    write_scheduler_config,
)
from rawcandle.scheduler.runner import (
    SchedulerAlreadyRunningError,
    read_scheduler_status,
    run_scheduler_config,
)


SCHEDULER_UI_PORT = 8555
DEFAULT_DATACENTER_PRICE_DB = "data/osakedata.db"
DEFAULT_DATACENTER_ANALYSIS_DB = "data/analysis.db"
DEFAULT_DATACENTER_TAXONOMY_CSV = "data/datacenter_ecosystem_taxonomy_full_v1.csv"
DEFAULT_DATACENTER_TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"
DEFAULT_DATACENTER_MARKET = "usa"
DEFAULT_DATACENTER_INDEX_BASE_DATE = "2020-01-01"
DEFAULT_DATACENTER_OUTPUT_DIR = "/home/kalle/projects/rawcandle/swing_reports"
DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT = "236"
DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT = "54"
DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT = "53"
DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE = "20"
DEFAULT_DATACENTER_WATCHLIST_FILE = "/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt"
DEFAULT_DATACENTER_SIGNAL_DATE = (date.today() - timedelta(days=1)).isoformat()
DEFAULT_DATACENTER_START_DATE = "2025-08-01"
_SUMMARY_FILENAME_RE = r"stock_update_scheduler_summary_"
_TIMER_PATH = Path.home() / ".config/systemd/user/rawcandle-stock-update-scheduler.timer"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone stock update scheduler control panel."
    )
    parser.add_argument("--config", default="scheduler_config.json")
    parser.add_argument("--port", type=int, default=SCHEDULER_UI_PORT)
    return parser


def build_config_from_ui_values(
    *,
    osakedata_db_path: str,
    analysis_db_path: str,
    log_dir: str,
    timezone: str,
    run_time: str,
    selected_markets: List[str],
    technical_relevance_enabled: bool,
) -> StockUpdateSchedulerConfig:
    config = StockUpdateSchedulerConfig(
        enabled_markets=selected_markets,
        run_time=run_time,
        osakedata_db_path=osakedata_db_path,
        analysis_db_path=analysis_db_path,
        log_dir=log_dir,
        timezone=timezone,
        technical_relevance_enabled=technical_relevance_enabled,
    )
    return validate_scheduler_config(config)


def load_latest_scheduler_summary(log_dir: str) -> Optional[Dict[str, Any]]:
    directory = Path(log_dir)
    if not directory.exists():
        return None
    candidates = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.name.startswith(_SUMMARY_FILENAME_RE)
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def list_scheduler_log_files(log_dir: str, limit: int = 10) -> list[Path]:
    directory = Path(log_dir)
    if not directory.exists():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".txt", ".log"}
        ),
        key=lambda path: path.name,
        reverse=True,
    )[:limit]


def build_text_log_browser_url(path: str) -> str:
    return f"/{quote(Path(path).name)}"


def read_text_log_file(path: str, max_chars: int = 200_000) -> str:
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    if len(content) <= max_chars:
        return content
    return f"[truncated to last {max_chars} chars]\n{content[-max_chars:]}"


def launch_browser_url(page: Any, url: str) -> None:
    result = page.launch_url(url)
    if inspect.isawaitable(result):
        async def _await_launch() -> None:
            await result

        page.run_task(_await_launch)


def format_run_now_error_message(exc: Exception) -> str:
    if isinstance(exc, SchedulerAlreadyRunningError):
        return "Run now blocked: scheduler run is already active."
    return f"Run now failed: {exc}"


def get_systemd_user_timer_path() -> Path:
    return _TIMER_PATH


def format_systemd_on_calendar(*, run_time: str) -> str:
    validate_run_time(run_time)
    return f"*-*-* {run_time}:00"


def read_systemd_timer_on_calendar(timer_path: Path) -> Optional[str]:
    if not timer_path.exists():
        return None
    for line in timer_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OnCalendar="):
            return line.split("=", 1)[1]
    return None


def update_systemd_timer_on_calendar(timer_path: Path, *, run_time: str) -> None:
    if not timer_path.exists():
        raise FileNotFoundError(timer_path)
    lines = timer_path.read_text(encoding="utf-8").splitlines()
    replacement = f"OnCalendar={format_systemd_on_calendar(run_time=run_time)}"
    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.startswith("OnCalendar="):
            updated.append(replacement)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        raise ValueError("OnCalendar line not found")
    timer_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def read_systemd_user_timer_status() -> dict[str, Any]:
    timer_path = get_systemd_user_timer_path()
    on_calendar = read_systemd_timer_on_calendar(timer_path)
    installed = timer_path.exists()
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", "rawcandle-stock-update-scheduler.timer"],
            check=False,
            capture_output=True,
            text=True,
        )
        status_summary = proc.stdout.strip() or proc.stderr.strip() or "unknown"
        error = None
    except Exception as exc:  # pragma: no cover - defensive UI helper
        status_summary = "unknown"
        error = str(exc)
    return {
        "timer_path": str(timer_path),
        "on_calendar": on_calendar,
        "installed": installed,
        "status_summary": status_summary if installed else "missing",
        "error": error,
    }


def save_config_and_sync_systemd_timer(
    *,
    config_path: str,
    config: StockUpdateSchedulerConfig,
) -> dict[str, Any]:
    write_scheduler_config(config_path, config)
    timer_path = get_systemd_user_timer_path()
    if not timer_path.exists():
        return {
            "status": "WARNING",
            "message": "Config saved; systemd timer file missing.",
            "timer_path": str(timer_path),
        }
    update_systemd_timer_on_calendar(timer_path, run_time=config.run_time)
    proc = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {
            "status": "WARNING",
            "message": f"Config saved; systemd daemon-reload failed: {proc.stderr.strip()}",
            "timer_path": str(timer_path),
        }
    return {"status": "OK", "message": "Config saved.", "timer_path": str(timer_path)}


def build_skip_next_run_config(config: StockUpdateSchedulerConfig) -> StockUpdateSchedulerConfig:
    config.skip_next_run = True
    return validate_scheduler_config(config)


def build_cancel_skip_next_run_config(config: StockUpdateSchedulerConfig) -> StockUpdateSchedulerConfig:
    config.skip_next_run = False
    return validate_scheduler_config(config)


def scheduler_running_state(status: Optional[dict[str, Any]]) -> dict[str, Any]:
    is_running = bool(status and status.get("is_running"))
    return {"is_running": is_running}


def scheduler_skip_button_state(
    *, is_running: bool, skip_next_run: bool
) -> dict[str, bool]:
    return {
        "skip_disabled": is_running or skip_next_run,
        "cancel_disabled": is_running or not skip_next_run,
    }


def scheduler_skip_next_run_label(config: StockUpdateSchedulerConfig) -> str:
    return "Next scheduled run: SKIP" if config.skip_next_run else "Next scheduled run: RUN"


def apply_skip_next_run_to_config(config_path: str) -> StockUpdateSchedulerConfig:
    config = read_scheduler_config(config_path)
    status = read_scheduler_status(config.log_dir)
    if scheduler_running_state(status)["is_running"]:
        return config
    config = build_skip_next_run_config(config)
    write_scheduler_config(config_path, config)
    return config


def apply_cancel_skip_next_run_to_config(config_path: str) -> StockUpdateSchedulerConfig:
    config = read_scheduler_config(config_path)
    status = read_scheduler_status(config.log_dir)
    if scheduler_running_state(status)["is_running"]:
        return config
    config = build_cancel_skip_next_run_config(config)
    write_scheduler_config(config_path, config)
    return config


def build_datacenter_pipeline_command(
    *,
    price_db: str,
    analysis_db: str,
    taxonomy_csv: str,
    taxonomy_version: str,
    market: str,
    signal_date: str,
    start_date: str,
    index_base_date: str,
    output_dir: str,
    expected_ticker_count: str,
    expected_group_count: str,
    expected_synthetic_ohlc_count: str,
    rolling_window_size: str,
    watchlist_file: str,
    dry_run: bool,
) -> List[str]:
    command = [
        "python3",
        "run_datacenter_swing_pipeline.py",
        "--price-db",
        price_db,
        "--analysis-db",
        analysis_db,
        "--taxonomy-csv",
        taxonomy_csv,
        "--taxonomy-version",
        taxonomy_version,
        "--market",
        market,
        "--signal-date",
        signal_date,
        "--start-date",
        start_date,
        "--index-base-date",
        index_base_date,
        "--output-dir",
        output_dir,
        "--expected-ticker-count",
        expected_ticker_count,
        "--expected-group-count",
        expected_group_count,
        "--expected-synthetic-ohlc-count",
        expected_synthetic_ohlc_count,
        "--weekly-window-size",
        rolling_window_size,
        "--watchlist-file",
        watchlist_file,
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def build_datacenter_pipeline_plan_command(**kwargs: str) -> List[str]:
    return build_datacenter_pipeline_command(dry_run=True, **kwargs)


def build_datacenter_audit_command(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    expected_ticker_count: str,
    expected_group_count: str,
    expected_synthetic_ohlc_count: str,
    rolling_window_size: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_swing_pipeline_audit.py",
        "--analysis-db",
        analysis_db,
        "--signal-date",
        signal_date,
        "--taxonomy-version",
        taxonomy_version,
        "--expected-ticker-count",
        expected_ticker_count,
        "--expected-group-count",
        expected_group_count,
        "--expected-synthetic-ohlc-count",
        expected_synthetic_ohlc_count,
        "--weekly-window-size",
        rolling_window_size,
    ]


def build_datacenter_daily_report_command(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    watchlist_file: str,
    output_dir: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_daily_report.py",
        "--analysis-db",
        analysis_db,
        "--signal-date",
        signal_date,
        "--taxonomy-version",
        taxonomy_version,
        "--watchlist-file",
        watchlist_file,
        "--output-dir",
        output_dir,
    ]


def build_datacenter_rolling_report_command(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    rolling_window_size: str,
    watchlist_file: str,
    output_dir: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_rolling_swing_report.py",
        "--analysis-db",
        analysis_db,
        "--signal-date",
        signal_date,
        "--taxonomy-version",
        taxonomy_version,
        "--rolling-window-size",
        rolling_window_size,
        "--watchlist-file",
        watchlist_file,
        "--output-dir",
        output_dir,
    ]


def build_datacenter_watermark_command(*, analysis_db: str) -> List[str]:
    return ["python3", "run_datacenter_pipeline_watermark.py", "--analysis-db", analysis_db]


def find_datacenter_generated_reports(output_dir: str) -> list[Path]:
    directory = Path(output_dir)
    if not directory.exists():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".md", ".csv"}
        ),
        key=lambda path: path.name,
        reverse=True,
    )


def populate_datacenter_report_downloads(
    *, reports_column: Any, output_dir: str, assets_root: Path | None = None
) -> None:
    reports_column.controls = [
        ft.Text(str(path)) for path in find_datacenter_generated_reports(output_dir)
    ]


def run_datacenter_ui_command(
    *,
    page: Any,
    title: str,
    command: List[str],
    log_field: Any,
    status_field: Any,
    output_dir: str | None = None,
    reports_column: Any | None = None,
    assets_root: Path | None = None,
    **_kwargs: Any,
) -> None:
    log_field.value = " ".join(command)
    status_field.value = f"{title} planned."
    if output_dir and reports_column is not None:
        populate_datacenter_report_downloads(
            reports_column=reports_column,
            output_dir=output_dir,
            assets_root=assets_root,
        )
    if hasattr(page, "update"):
        page.update()


def _load_config_or_raise(config_path: str) -> StockUpdateSchedulerConfig:
    return read_scheduler_config(config_path)


def run_app(page: Any, config_path: str = "scheduler_config.json") -> None:
    config = _load_config_or_raise(config_path)
    page.title = "RawCandle stock update scheduler"
    page.scroll = ft.ScrollMode.AUTO

    osakedata_db_field = ft.TextField(label="osakedata_db_path", value=config.osakedata_db_path)
    analysis_db_field = ft.TextField(label="analysis_db_path", value=config.analysis_db_path)
    log_dir_field = ft.TextField(label="log_dir", value=config.log_dir)
    timezone_field = ft.TextField(label="timezone", value=config.timezone)
    run_time_field = ft.TextField(label="run_time", value=config.run_time)
    omxh_checkbox = ft.Checkbox(label="OMXH", value="omxh" in config.enabled_markets)
    omxs_checkbox = ft.Checkbox(label="OMXS", value="omxs" in config.enabled_markets)
    usa_checkbox = ft.Checkbox(label="USA", value="usa" in config.enabled_markets)
    technical_relevance_checkbox = ft.Checkbox(
        label="Run technical relevance after stock updates",
        value=config.technical_relevance_enabled,
    )
    status_field = ft.TextField(label="Status", read_only=True, multiline=True)
    summary_field = ft.TextField(label="Latest summary", read_only=True, multiline=True)
    timer_status_field = ft.TextField(label="Timer status", read_only=True, multiline=True)
    selected_log_field = ft.TextField(label="Selected log", read_only=True, multiline=True)
    skip_next_run_text = ft.Text(scheduler_skip_next_run_label(config))
    running_status_text = ft.Text("Scheduler running: UNKNOWN")
    logs_column = ft.Column(spacing=8)

    def selected_markets_from_ui() -> list[str]:
        markets: list[str] = []
        if omxh_checkbox.value:
            markets.append("omxh")
        if omxs_checkbox.value:
            markets.append("omxs")
        if usa_checkbox.value:
            markets.append("usa")
        return markets

    def _market_row_text(market_result: dict[str, Any]) -> str:
        return (
            f"market={market_result.get('market', '')} "
            f"status={market_result.get('summary_status', '')} "
            f"log={market_result.get('log_path', '')}"
        )

    def refresh_timer_status() -> None:
        timer_status = read_systemd_user_timer_status()
        timer_status_field.value = "\n".join(
            [
                f"installed={timer_status.get('installed', False)}",
                f"status_summary={timer_status.get('status_summary', '')}",
                f"on_calendar={timer_status.get('on_calendar', '')}",
                f"timer_path={timer_status.get('timer_path', '')}",
                f"error={timer_status.get('error', '')}",
            ]
        )

    def refresh_running_state(log_dir: str) -> None:
        status = read_scheduler_status(log_dir)
        state = scheduler_running_state(status)
        running_status_text.value = (
            "Scheduler status: running"
            if state["is_running"]
            else "Scheduler status: not running"
        )
        current_config = _load_config_or_raise(config_path)
        button_state = scheduler_skip_button_state(
            is_running=state["is_running"],
            skip_next_run=current_config.skip_next_run,
        )
        skip_next_run_button.disabled = button_state["skip_disabled"]
        cancel_skip_next_run_button.disabled = button_state["cancel_disabled"]
        refresh_timer_status()

    def load_log_into_view(path: Path) -> None:
        try:
            selected_log_field.value = read_text_log_file(str(path))
            status_field.value = f"Loaded log: {path.name}"
        except Exception as exc:
            selected_log_field.value = ""
            status_field.value = f"Load log failed: {exc}"

    def open_log_in_browser(path: Path) -> None:
        launch_browser_url(page, build_text_log_browser_url(str(path)))
        status_field.value = f"Opened log: {path.name}"

    def refresh_logs_view(log_dir: str) -> None:
        log_paths = list_scheduler_log_files(log_dir)
        latest = load_latest_scheduler_summary(log_dir)
        if latest is None:
            summary_field.value = "No scheduler summary JSON found."
        else:
            lines = [
                f"overall_status={latest.get('overall_status', '')}",
                "enabled_markets=" + ",".join(latest.get("enabled_markets", [])),
                f"summary_json_path={latest.get('summary_json_path', '')}",
                "technical_relevance_status="
                f"{latest.get('technical_relevance_status', '')}",
                "ec_source_layer_status="
                f"{latest.get('ec_source_layer_status', '')}",
            ]
            for market_result in latest.get("market_results", []):
                lines.append(_market_row_text(market_result))
            summary_field.value = "\n".join(lines)

        logs_column.controls = []
        if not log_paths:
            logs_column.controls.append(ft.Text("No text log files found."))
            selected_log_field.value = ""
        else:
            for path in log_paths:
                stat_result = path.stat()
                logs_column.controls.append(
                    ft.Row(
                        [
                            ft.Text(
                                f"{path.name} (size={stat_result.st_size}, modified_at={int(stat_result.st_mtime)})",
                                expand=True,
                            ),
                            ft.TextButton(
                                "Preview",
                                on_click=lambda _e, path=path: load_log_into_view(path),
                            ),
                            ft.TextButton(
                                "Open",
                                on_click=lambda _e, path=path: open_log_in_browser(path),
                            ),
                        ]
                    )
                )
        refresh_running_state(log_dir)

    def update_ui_from_config(next_config: StockUpdateSchedulerConfig) -> None:
        osakedata_db_field.value = next_config.osakedata_db_path
        analysis_db_field.value = next_config.analysis_db_path
        log_dir_field.value = next_config.log_dir
        timezone_field.value = next_config.timezone
        run_time_field.value = next_config.run_time
        enabled = set(next_config.enabled_markets)
        omxh_checkbox.value = "omxh" in enabled
        omxs_checkbox.value = "omxs" in enabled
        usa_checkbox.value = "usa" in enabled
        technical_relevance_checkbox.value = next_config.technical_relevance_enabled
        skip_next_run_text.value = scheduler_skip_next_run_label(next_config)

    def on_save_config(_e: Any) -> None:
        try:
            next_config = build_config_from_ui_values(
                osakedata_db_path=osakedata_db_field.value,
                analysis_db_path=analysis_db_field.value,
                log_dir=log_dir_field.value,
                timezone=timezone_field.value,
                run_time=run_time_field.value,
                selected_markets=selected_markets_from_ui(),
                technical_relevance_enabled=bool(technical_relevance_checkbox.value),
            )
            result = save_config_and_sync_systemd_timer(
                config_path=config_path,
                config=next_config,
            )
            update_ui_from_config(next_config)
            refresh_logs_view(next_config.log_dir)
            status_field.value = result["message"]
        except Exception as exc:
            status_field.value = f"Save config failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_reload_config(_e: Any) -> None:
        try:
            next_config = _load_config_or_raise(config_path)
            update_ui_from_config(next_config)
            refresh_logs_view(next_config.log_dir)
            status_field.value = "Config reloaded."
        except Exception as exc:
            status_field.value = f"Reload config failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_run_now(_e: Any) -> None:
        try:
            run_scheduler_config(config_path=config_path)
            status_field.value = "Run now completed."
        except Exception as exc:
            status_field.value = format_run_now_error_message(exc)
        if hasattr(page, "update"):
            page.update()

    def on_skip_next_run(_e: Any) -> None:
        next_config = apply_skip_next_run_to_config(config_path)
        update_ui_from_config(next_config)
        refresh_running_state(next_config.log_dir)
        if hasattr(page, "update"):
            page.update()

    def on_cancel_skip_next_run(_e: Any) -> None:
        next_config = apply_cancel_skip_next_run_to_config(config_path)
        update_ui_from_config(next_config)
        refresh_running_state(next_config.log_dir)
        if hasattr(page, "update"):
            page.update()

    def on_refresh_logs(_e: Any) -> None:
        refresh_logs_view(log_dir_field.value)
        if hasattr(page, "update"):
            page.update()

    save_config_button = ft.ElevatedButton("Save config", on_click=on_save_config)
    reload_config_button = ft.ElevatedButton("Reload config", on_click=on_reload_config)
    run_now_button = ft.ElevatedButton("Run now", on_click=on_run_now)
    skip_next_run_button = ft.ElevatedButton("Skip next run", on_click=on_skip_next_run)
    cancel_skip_next_run_button = ft.ElevatedButton(
        "Cancel skip", on_click=on_cancel_skip_next_run
    )
    refresh_logs_button = ft.ElevatedButton("Refresh logs", on_click=on_refresh_logs)

    datacenter_price_db_field = ft.TextField(label="price_db", value=DEFAULT_DATACENTER_PRICE_DB)
    datacenter_analysis_db_field = ft.TextField(label="analysis_db", value=DEFAULT_DATACENTER_ANALYSIS_DB)
    datacenter_taxonomy_csv_field = ft.TextField(label="taxonomy_csv", value=DEFAULT_DATACENTER_TAXONOMY_CSV)
    datacenter_taxonomy_version_field = ft.TextField(label="taxonomy_version", value=DEFAULT_DATACENTER_TAXONOMY_VERSION)
    datacenter_market_field = ft.TextField(label="market", value=DEFAULT_DATACENTER_MARKET)
    datacenter_signal_date_field = ft.TextField(label="signal_date", value=DEFAULT_DATACENTER_SIGNAL_DATE)
    datacenter_start_date_field = ft.TextField(label="start_date", value=DEFAULT_DATACENTER_START_DATE)
    datacenter_index_base_date_field = ft.TextField(label="index_base_date", value=DEFAULT_DATACENTER_INDEX_BASE_DATE)
    datacenter_output_dir_field = ft.TextField(label="output_dir", value=DEFAULT_DATACENTER_OUTPUT_DIR)
    datacenter_expected_ticker_count_field = ft.TextField(label="expected_ticker_count", value=DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT)
    datacenter_expected_group_count_field = ft.TextField(label="expected_group_count", value=DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT)
    datacenter_expected_synthetic_ohlc_count_field = ft.TextField(label="expected_synthetic_ohlc_count", value=DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT)
    datacenter_rolling_window_size_field = ft.TextField(label="rolling_window_size", value=DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE)
    datacenter_watchlist_file_field = ft.TextField(label="watchlist_file", value=DEFAULT_DATACENTER_WATCHLIST_FILE)
    datacenter_status_field = ft.TextField(label="Datacenter status", read_only=True)
    datacenter_log_field = ft.TextField(label="Datacenter command", read_only=True)
    datacenter_reports_column = ft.Column(spacing=8)

    def _pipeline_command(*, dry_run: bool) -> list[str]:
        return build_datacenter_pipeline_command(
            price_db=datacenter_price_db_field.value,
            analysis_db=datacenter_analysis_db_field.value,
            taxonomy_csv=datacenter_taxonomy_csv_field.value,
            taxonomy_version=datacenter_taxonomy_version_field.value,
            market=datacenter_market_field.value,
            signal_date=datacenter_signal_date_field.value,
            start_date=datacenter_start_date_field.value,
            index_base_date=datacenter_index_base_date_field.value,
            output_dir=datacenter_output_dir_field.value,
            expected_ticker_count=datacenter_expected_ticker_count_field.value,
            expected_group_count=datacenter_expected_group_count_field.value,
            expected_synthetic_ohlc_count=datacenter_expected_synthetic_ohlc_count_field.value,
            rolling_window_size=datacenter_rolling_window_size_field.value,
            watchlist_file=datacenter_watchlist_file_field.value,
            dry_run=dry_run,
        )

    datacenter_plan_button = ft.ElevatedButton(
        "Plan Datacenter",
        on_click=lambda e: run_datacenter_ui_command(
            page=page,
            title="Plan Datacenter",
            command=_pipeline_command(dry_run=True),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
            output_dir=datacenter_output_dir_field.value,
            reports_column=datacenter_reports_column,
        ),
    )
    datacenter_run_full_chain_button = ft.ElevatedButton(
        "Run Datacenter Pipeline",
        on_click=lambda e: run_datacenter_ui_command(
            page=page,
            title="Run Datacenter Pipeline",
            command=_pipeline_command(dry_run=False),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
            output_dir=datacenter_output_dir_field.value,
            reports_column=datacenter_reports_column,
        ),
    )
    datacenter_audit_button = ft.ElevatedButton(
        "Run Audit",
        on_click=lambda e: run_datacenter_ui_command(
            page=page,
            title="Run Audit",
            command=build_datacenter_audit_command(
                analysis_db=datacenter_analysis_db_field.value,
                signal_date=datacenter_signal_date_field.value,
                taxonomy_version=datacenter_taxonomy_version_field.value,
                expected_ticker_count=datacenter_expected_ticker_count_field.value,
                expected_group_count=datacenter_expected_group_count_field.value,
                expected_synthetic_ohlc_count=datacenter_expected_synthetic_ohlc_count_field.value,
                rolling_window_size=datacenter_rolling_window_size_field.value,
            ),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
        ),
    )
    datacenter_watermarks_button = ft.ElevatedButton(
        "Watermarks",
        on_click=lambda e: run_datacenter_ui_command(
            page=page,
            title="Watermarks",
            command=build_datacenter_watermark_command(
                analysis_db=datacenter_analysis_db_field.value
            ),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
        ),
    )

    scheduler_content = ft.Column(
        [
            osakedata_db_field,
            analysis_db_field,
            log_dir_field,
            timezone_field,
            run_time_field,
            ft.Row([omxh_checkbox, omxs_checkbox, usa_checkbox]),
            technical_relevance_checkbox,
            skip_next_run_text,
            running_status_text,
            ft.Row(
                [
                    save_config_button,
                    reload_config_button,
                    run_now_button,
                    skip_next_run_button,
                    cancel_skip_next_run_button,
                    refresh_logs_button,
                ]
            ),
            status_field,
            summary_field,
            timer_status_field,
            selected_log_field,
            logs_column,
        ],
        spacing=12,
        expand=True,
    )
    datacenter_content = ft.Column(
        [
            datacenter_price_db_field,
            datacenter_analysis_db_field,
            datacenter_taxonomy_csv_field,
            datacenter_taxonomy_version_field,
            ft.Row([datacenter_market_field, datacenter_signal_date_field]),
            ft.Row([datacenter_start_date_field, datacenter_index_base_date_field]),
            datacenter_output_dir_field,
            ft.Row(
                [
                    datacenter_expected_ticker_count_field,
                    datacenter_expected_group_count_field,
                    datacenter_expected_synthetic_ohlc_count_field,
                    datacenter_rolling_window_size_field,
                ]
            ),
            datacenter_watchlist_file_field,
            ft.Row(
                [
                    datacenter_plan_button,
                    datacenter_run_full_chain_button,
                    datacenter_audit_button,
                    datacenter_watermarks_button,
                ]
            ),
            datacenter_status_field,
            datacenter_reports_column,
            datacenter_log_field,
        ],
        spacing=12,
        expand=True,
    )

    refresh_logs_view(config.log_dir)

    page.osakedata_db_field = osakedata_db_field
    page.analysis_db_field = analysis_db_field
    page.log_dir_field = log_dir_field
    page.timezone_field = timezone_field
    page.run_time_field = run_time_field
    page.omxh_checkbox = omxh_checkbox
    page.omxs_checkbox = omxs_checkbox
    page.usa_checkbox = usa_checkbox
    page.technical_relevance_checkbox = technical_relevance_checkbox
    page.save_config_button = save_config_button
    page.reload_config_button = reload_config_button
    page.run_now_button = run_now_button
    page.skip_next_run_button = skip_next_run_button
    page.cancel_skip_next_run_button = cancel_skip_next_run_button
    page.refresh_logs_button = refresh_logs_button
    page.status_field = status_field
    page.summary_field = summary_field
    page.timer_status_field = timer_status_field
    page.running_status_text = running_status_text
    page.selected_log_field = selected_log_field
    page.logs_column = logs_column
    page.datacenter_price_db_field = datacenter_price_db_field
    page.datacenter_analysis_db_field = datacenter_analysis_db_field
    page.datacenter_taxonomy_csv_field = datacenter_taxonomy_csv_field
    page.datacenter_taxonomy_version_field = datacenter_taxonomy_version_field
    page.datacenter_market_field = datacenter_market_field
    page.datacenter_signal_date_field = datacenter_signal_date_field
    page.datacenter_start_date_field = datacenter_start_date_field
    page.datacenter_index_base_date_field = datacenter_index_base_date_field
    page.datacenter_output_dir_field = datacenter_output_dir_field
    page.datacenter_expected_ticker_count_field = datacenter_expected_ticker_count_field
    page.datacenter_expected_group_count_field = datacenter_expected_group_count_field
    page.datacenter_expected_synthetic_ohlc_count_field = datacenter_expected_synthetic_ohlc_count_field
    page.datacenter_rolling_window_size_field = datacenter_rolling_window_size_field
    page.datacenter_watchlist_file_field = datacenter_watchlist_file_field
    page.datacenter_plan_button = datacenter_plan_button
    page.datacenter_run_full_chain_button = datacenter_run_full_chain_button
    page.datacenter_audit_button = datacenter_audit_button
    page.datacenter_watermarks_button = datacenter_watermarks_button
    page.datacenter_status_field = datacenter_status_field
    page.datacenter_log_field = datacenter_log_field
    page.datacenter_reports_column = datacenter_reports_column
    page.scheduler_content = scheduler_content
    page.datacenter_content = datacenter_content

    page.add(
        ft.Tabs(
            tabs=[
                ft.Tab(text="Scheduler", content=scheduler_content),
                ft.Tab(text="Datacenter", content=datacenter_content),
            ],
            expand=True,
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    initial_config = read_scheduler_config(args.config)

    def _app(page: Any) -> None:
        run_app(page, args.config)

    ft.app(
        target=_app,
        port=args.port,
        view=ft.AppView.WEB_BROWSER,
        assets_dir=initial_config.log_dir,
    )


if __name__ == "__main__":
    main()
