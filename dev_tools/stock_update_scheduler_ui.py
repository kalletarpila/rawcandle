from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import shutil
import subprocess
import threading
import zipfile
from datetime import date, datetime, timedelta
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


_SUMMARY_FILENAME_RE = re.compile(
    r"^stock_update_scheduler_summary_(\d{8}T\d{6}Z)\.json$"
)
_MARKET_LOG_FILENAME_RE = re.compile(
    r"^stock_update_(omxh|omxs|usa)_(\d{8}T\d{4,6}Z)(?:_(\d+))?\.(txt|log)$"
)
_STATUS_OK_COLOR = "#43A047"
_STATUS_WARNING_COLOR = "#EF6C00"
_STATUS_ERROR_COLOR = "#E53935"
SCHEDULER_UI_PORT = 8555
REPO_ROOT = Path(__file__).resolve().parent.parent
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
DEFAULT_DATACENTER_WATCHLIST_FILE = "/home/kalle/projects/rawcandle/swing_reports/datacenter_watchlist.txt"
DEFAULT_DATACENTER_SIGNAL_DATE = (date.today() - timedelta(days=1)).isoformat()
DEFAULT_DATACENTER_START_DATE = "2025-08-01"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone stock update scheduler control panel."
    )
    parser.add_argument("--config", required=True)
    return parser


def build_config_from_ui_values(
    *,
    osakedata_db_path: str,
    analysis_db_path: str,
    log_dir: str,
    timezone: str,
    run_time: str,
    selected_markets: List[str],
) -> StockUpdateSchedulerConfig:
    config = StockUpdateSchedulerConfig(
        enabled_markets=selected_markets,
        run_time=run_time,
        osakedata_db_path=osakedata_db_path,
        analysis_db_path=analysis_db_path,
        log_dir=log_dir,
        timezone=timezone,
    )
    return validate_scheduler_config(config)


def build_skip_next_run_config(
    config: StockUpdateSchedulerConfig,
) -> StockUpdateSchedulerConfig:
    updated_config = StockUpdateSchedulerConfig(
        enabled_markets=list(config.enabled_markets),
        run_time=config.run_time,
        osakedata_db_path=config.osakedata_db_path,
        analysis_db_path=config.analysis_db_path,
        log_dir=config.log_dir,
        timezone=config.timezone,
        skip_next_run=True,
    )
    return validate_scheduler_config(updated_config)


def build_cancel_skip_next_run_config(
    config: StockUpdateSchedulerConfig,
) -> StockUpdateSchedulerConfig:
    updated_config = StockUpdateSchedulerConfig(
        enabled_markets=list(config.enabled_markets),
        run_time=config.run_time,
        osakedata_db_path=config.osakedata_db_path,
        analysis_db_path=config.analysis_db_path,
        log_dir=config.log_dir,
        timezone=config.timezone,
        skip_next_run=False,
    )
    return validate_scheduler_config(updated_config)


def scheduler_running_state(status: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not status or not status.get("is_running"):
        return {"is_running": False, "current_market": None, "skip_button_disabled": False}
    return {
        "is_running": True,
        "current_market": status.get("current_market"),
        "skip_button_disabled": True,
    }


def scheduler_skip_next_run_label(config: StockUpdateSchedulerConfig) -> str:
    return f"Skip next run: {'true' if config.skip_next_run else 'false'}"


def scheduler_skip_button_state(
    *,
    config: StockUpdateSchedulerConfig,
    status: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    running_state = scheduler_running_state(status)
    if running_state["is_running"]:
        return {"skip_enabled": False, "cancel_enabled": False}
    if config.skip_next_run:
        return {"skip_enabled": False, "cancel_enabled": True}
    return {"skip_enabled": True, "cancel_enabled": False}


def apply_skip_next_run_to_config(config_path: str) -> StockUpdateSchedulerConfig:
    current_config = read_scheduler_config(config_path)
    running_state = scheduler_running_state(read_scheduler_status(current_config.log_dir))
    if running_state["is_running"]:
        raise ValueError("Scheduler run is currently active.")
    updated_config = build_skip_next_run_config(current_config)
    write_scheduler_config(config_path, updated_config)
    return updated_config


def apply_cancel_skip_next_run_to_config(config_path: str) -> StockUpdateSchedulerConfig:
    current_config = read_scheduler_config(config_path)
    running_state = scheduler_running_state(read_scheduler_status(current_config.log_dir))
    if running_state["is_running"]:
        raise ValueError("Scheduler run is currently active.")
    updated_config = build_cancel_skip_next_run_config(current_config)
    write_scheduler_config(config_path, updated_config)
    return updated_config


def load_latest_scheduler_summary(log_dir: str) -> Optional[Dict[str, Any]]:
    log_dir_path = Path(log_dir)
    if not log_dir_path.exists() or not log_dir_path.is_dir():
        return None

    matching_files = sorted(
        (
            path
            for path in log_dir_path.iterdir()
            if path.is_file() and _SUMMARY_FILENAME_RE.match(path.name)
        ),
        key=lambda path: _SUMMARY_FILENAME_RE.match(path.name).group(1),  # type: ignore[union-attr]
        reverse=True,
    )
    if not matching_files:
        return None

    with matching_files[0].open("r", encoding="utf-8") as summary_file:
        return json.load(summary_file)


def list_scheduler_log_files(log_dir: str, limit: int = 10) -> List[Dict[str, Any]]:
    log_dir_path = Path(log_dir)
    if not log_dir_path.exists() or not log_dir_path.is_dir():
        return []

    entries: List[Dict[str, Any]] = []
    for path in log_dir_path.iterdir():
        if not path.is_file():
            continue
        summary_match = _SUMMARY_FILENAME_RE.match(path.name)
        log_match = _MARKET_LOG_FILENAME_RE.match(path.name)
        if summary_match:
            timestamp = summary_match.group(1)
            entry_type = "summary_json"
        elif log_match:
            timestamp = log_match.group(2)
            suffix = log_match.group(3) or "0"
            entry_type = "market_log"
        else:
            continue

        stat_result = path.stat()
        entries.append(
            {
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat_result.st_size,
                "modified_at": str(int(stat_result.st_mtime)),
                "timestamp": timestamp,
                "sort_key": f"{timestamp}_{suffix}" if log_match else timestamp,
                "type": entry_type,
                "text_openable": entry_type == "market_log",
            }
        )

    entries.sort(key=lambda item: item["sort_key"], reverse=True)
    return entries[:limit]


def build_text_log_browser_url(path: str) -> str:
    return f"/{quote(Path(path).name)}"


def get_systemd_user_timer_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "stock-update-scheduler.timer"


def format_systemd_on_calendar(run_time: str) -> str:
    validated_run_time = validate_run_time(run_time)
    return f"*-*-* {validated_run_time}:00"


def read_systemd_timer_on_calendar(timer_path: Path) -> Optional[str]:
    if not timer_path.exists():
        return None
    for line in timer_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OnCalendar="):
            return line.split("=", 1)[1]
    return None


def update_systemd_timer_on_calendar(
    *,
    timer_path: Path,
    run_time: str,
) -> None:
    if not timer_path.exists():
        raise FileNotFoundError(f"Missing systemd timer file: {timer_path}")
    on_calendar = format_systemd_on_calendar(run_time)
    lines = timer_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    updated_lines: List[str] = []
    for line in lines:
        if not replaced and line.startswith("OnCalendar="):
            updated_lines.append(f"OnCalendar={on_calendar}")
            replaced = True
        else:
            updated_lines.append(line)
    if not replaced:
        raise ValueError(f"OnCalendar line not found in timer file: {timer_path}")
    timer_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def reload_systemd_user_timer() -> None:
    commands = [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "restart", "stock-update-scheduler.timer"],
    ]
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            error_text = (completed.stderr or completed.stdout).strip() or "unknown error"
            raise RuntimeError(error_text)


def read_systemd_user_timer_status() -> Dict[str, Any]:
    timer_path = get_systemd_user_timer_path()
    on_calendar = read_systemd_timer_on_calendar(timer_path)
    if not timer_path.exists():
        return {
            "installed": False,
            "timer_path": str(timer_path),
            "on_calendar": None,
            "status_summary": "timer file missing",
            "error": None,
        }

    try:
        completed = subprocess.run(
            ["systemctl", "--user", "status", "stock-update-scheduler.timer"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return {
            "installed": True,
            "timer_path": str(timer_path),
            "on_calendar": on_calendar,
            "status_summary": "status read failed",
            "error": str(exc),
        }

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).strip()
    trigger_line = next(
        (line.strip() for line in stdout.splitlines() if line.strip().startswith("Trigger:")),
        None,
    )
    if completed.returncode == 0:
        status_summary = trigger_line or "timer loaded"
        return {
            "installed": True,
            "timer_path": str(timer_path),
            "on_calendar": on_calendar,
            "status_summary": status_summary,
            "error": None,
        }

    lowered = combined.lower()
    installed = "not-found" not in lowered and "could not be found" not in lowered
    return {
        "installed": installed,
        "timer_path": str(timer_path),
        "on_calendar": on_calendar,
        "status_summary": trigger_line or "status read failed",
        "error": combined or "systemctl status failed",
    }


def save_config_and_sync_systemd_timer(
    *,
    config_path: str,
    config: StockUpdateSchedulerConfig,
) -> Dict[str, Any]:
    result = {
        "config_saved": False,
        "timer_file_found": False,
        "timer_updated": False,
        "systemd_reloaded": False,
        "status": "FAILED",
        "message": "",
    }
    try:
        write_scheduler_config(config_path, config)
    except Exception as exc:
        result["message"] = f"Save failed: {exc}"
        return result

    result["config_saved"] = True
    timer_path = get_systemd_user_timer_path()
    if not timer_path.exists():
        result["status"] = "WARNING"
        result["message"] = "Config saved, but systemd timer file was not found."
        return result

    result["timer_file_found"] = True
    try:
        update_systemd_timer_on_calendar(timer_path=timer_path, run_time=config.run_time)
        result["timer_updated"] = True
    except Exception as exc:
        result["status"] = "WARNING"
        result["message"] = f"Config saved, but timer file update failed: {exc}"
        return result

    try:
        reload_systemd_user_timer()
        result["systemd_reloaded"] = True
        result["status"] = "OK"
        result["message"] = (
            f"Config saved and systemd timer updated to {config.run_time}."
        )
        return result
    except Exception as exc:
        result["status"] = "WARNING"
        result["message"] = (
            f"Config saved, timer file updated, but systemd reload failed: {exc}"
        )
        return result


def launch_browser_url(page: ft.Page, url: str) -> None:
    result = page.launch_url(url)
    if inspect.isawaitable(result):
        async def _await_launch() -> None:
            await result

        page.run_task(_await_launch)


def _datacenter_downloads_dir(assets_root: Path) -> Path:
    return assets_root / "datacenter_downloads"


def _stage_datacenter_download_asset(file_path: Path, assets_root: Path) -> Path:
    downloads_dir = _datacenter_downloads_dir(assets_root)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    staged_path = downloads_dir / file_path.name
    shutil.copy2(file_path, staged_path)
    return staged_path


def _datacenter_asset_url(assets_root: Path, staged_path: Path) -> str:
    relative_path = staged_path.relative_to(assets_root)
    return "/" + "/".join(quote(part) for part in relative_path.parts)


def _find_latest_matching_file(output_dir_path: Path, patterns: List[str]) -> Optional[Path]:
    candidates: List[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for candidate in output_dir_path.glob(pattern):
            if candidate.is_file() and candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)
    if not candidates:
        return None
    candidates.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return candidates[0]


def find_datacenter_generated_reports(
    *,
    output_dir: str,
    signal_date: str,
    rolling_window_size: str,
    include_daily: bool,
    include_rolling: bool,
) -> List[Path]:
    output_dir_path = Path(output_dir.strip())
    if not output_dir_path.exists() or not output_dir_path.is_dir():
        return []

    report_paths: List[Path] = []
    if include_daily:
        for suffix in ("md", "csv"):
            report_path = _find_latest_matching_file(
                output_dir_path,
                [
                    f"datacenter_daily_{signal_date.strip()}_*_full.{suffix}",
                    f"datacenter_daily_{signal_date.strip()}_full.{suffix}",
                ],
            )
            if report_path is not None:
                report_paths.append(report_path)

    if include_rolling:
        for suffix in ("md", "csv"):
            report_path = _find_latest_matching_file(
                output_dir_path,
                [
                    f"datacenter_rolling_{signal_date.strip()}_{rolling_window_size.strip()}d_*_full.{suffix}",
                    f"datacenter_rolling_{signal_date.strip()}_{rolling_window_size.strip()}d_full.{suffix}",
                ],
            )
            if report_path is not None:
                report_paths.append(report_path)

    return report_paths


def populate_datacenter_report_downloads(
    *,
    page: ft.Page,
    reports_column: ft.Column,
    status_field: ft.TextField,
    assets_root: Path,
    report_paths: List[Path],
) -> None:
    reports_column.controls.clear()
    if not report_paths:
        reports_column.controls.append(ft.Text("No generated reports available."))
        return

    def _download_single(file_path: Path) -> None:
        try:
            staged_path = _stage_datacenter_download_asset(file_path, assets_root)
            launch_browser_url(page, _datacenter_asset_url(assets_root, staged_path))
            _set_status(status_field, f"Downloading report: {file_path.name}", _STATUS_OK_COLOR)
        except Exception as exc:
            _set_status(status_field, f"Report download failed: {exc}", _STATUS_ERROR_COLOR)
        page.update()

    def _download_all(_e) -> None:
        try:
            downloads_dir = _datacenter_downloads_dir(assets_root)
            downloads_dir.mkdir(parents=True, exist_ok=True)
            archive_name = f"datacenter_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            archive_path = downloads_dir / archive_name
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for report_path in report_paths:
                    archive.write(report_path, arcname=report_path.name)
            launch_browser_url(page, _datacenter_asset_url(assets_root, archive_path))
            _set_status(status_field, f"Downloading report bundle: {archive_name}", _STATUS_OK_COLOR)
        except Exception as exc:
            _set_status(status_field, f"Report bundle download failed: {exc}", _STATUS_ERROR_COLOR)
        page.update()

    reports_column.controls.append(
        ft.Row(
            controls=[
                ft.Text("Generated reports", weight=ft.FontWeight.BOLD, expand=True),
                ft.ElevatedButton("Download All as ZIP", on_click=_download_all),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )
    for report_path in report_paths:
        reports_column.controls.append(
            ft.Row(
                controls=[
                    ft.Text(report_path.name, expand=True),
                    ft.Text(str(report_path), size=11, color="gray"),
                    ft.ElevatedButton(
                        "Download",
                        on_click=lambda _e, selected_report=report_path: _download_single(selected_report),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )


def format_run_now_error_message(exc: Exception) -> str:
    if isinstance(exc, SchedulerAlreadyRunningError):
        return "Run now blocked: scheduler run is already active."
    return f"Run now failed: {exc}"


def _load_config_or_raise(config_path: str) -> StockUpdateSchedulerConfig:
    return read_scheduler_config(config_path)


def _set_status(status_field: ft.TextField, message: str, color: str | None = None) -> None:
    status_field.value = message
    if color is not None:
        status_field.border_color = color


def _market_row_text(market_result: Dict[str, Any]) -> str:
    return (
        f"{market_result.get('market', '')}: "
        f"status={market_result.get('summary_status', '')}, "
        f"exit_code={market_result.get('exit_code', '')}, "
        f"log_path={market_result.get('log_path', '')}"
    )


def _datacenter_append_optional_arg(command: List[str], flag: str, value: str) -> None:
    if value.strip():
        command.extend([flag, value.strip()])


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
        price_db.strip(),
        "--analysis-db",
        analysis_db.strip(),
        "--taxonomy-csv",
        taxonomy_csv.strip(),
        "--taxonomy-version",
        taxonomy_version.strip(),
        "--market",
        market.strip(),
        "--signal-date",
        signal_date.strip(),
        "--start-date",
        start_date.strip(),
        "--index-base-date",
        index_base_date.strip(),
        "--output-dir",
        output_dir.strip(),
        "--weekly-window-size",
        rolling_window_size.strip(),
        "--watchlist-file",
        watchlist_file.strip(),
    ]
    _datacenter_append_optional_arg(command, "--expected-ticker-count", expected_ticker_count)
    _datacenter_append_optional_arg(command, "--expected-group-count", expected_group_count)
    _datacenter_append_optional_arg(command, "--expected-synthetic-ohlc-count", expected_synthetic_ohlc_count)
    if dry_run:
        command.append("--dry-run")
    return command


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
    command = [
        "python3",
        "run_datacenter_swing_pipeline_audit.py",
        "--analysis-db",
        analysis_db.strip(),
        "--signal-date",
        signal_date.strip(),
        "--taxonomy-version",
        taxonomy_version.strip(),
        "--weekly-window-size",
        rolling_window_size.strip(),
    ]
    _datacenter_append_optional_arg(command, "--expected-ticker-count", expected_ticker_count)
    _datacenter_append_optional_arg(command, "--expected-group-count", expected_group_count)
    _datacenter_append_optional_arg(command, "--expected-synthetic-ohlc-count", expected_synthetic_ohlc_count)
    return command


def build_datacenter_daily_report_command(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    watchlist_file: str,
    output_dir: str,
) -> List[str]:
    output_dir_path = Path(output_dir.strip())
    return [
        "python3",
        "run_datacenter_daily_signal_report.py",
        "--analysis-db",
        analysis_db.strip(),
        "--signal-date",
        signal_date.strip(),
        "--taxonomy-version",
        taxonomy_version.strip(),
        "--watchlist-file",
        watchlist_file.strip(),
        "--output-md",
        str(output_dir_path / f"datacenter_daily_{signal_date.strip()}_full.md"),
        "--output-csv",
        str(output_dir_path / f"datacenter_daily_{signal_date.strip()}_full.csv"),
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
    output_dir_path = Path(output_dir.strip())
    return [
        "python3",
        "run_datacenter_weekly_swing_report.py",
        "--analysis-db",
        analysis_db.strip(),
        "--end-date",
        signal_date.strip(),
        "--taxonomy-version",
        taxonomy_version.strip(),
        "--window-size",
        rolling_window_size.strip(),
        "--watchlist-file",
        watchlist_file.strip(),
        "--output-md",
        str(output_dir_path / f"datacenter_rolling_{signal_date.strip()}_{rolling_window_size.strip()}d_full.md"),
        "--output-csv",
        str(output_dir_path / f"datacenter_rolling_{signal_date.strip()}_{rolling_window_size.strip()}d_full.csv"),
    ]


def build_datacenter_pipeline_plan_command(
    *,
    analysis_db: str,
    taxonomy_version: str,
    market: str,
    signal_date: str,
    start_date: str,
    index_base_date: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_swing_pipeline_plan.py",
        "--analysis-db",
        analysis_db.strip(),
        "--taxonomy-version",
        taxonomy_version.strip(),
        "--market",
        market.strip(),
        "--signal-date",
        signal_date.strip(),
        "--start-date",
        start_date.strip(),
        "--index-base-date",
        index_base_date.strip(),
    ]


def build_datacenter_watermark_command(
    *,
    analysis_db: str,
    taxonomy_version: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_pipeline_watermark.py",
        "--analysis-db",
        analysis_db.strip(),
        "--taxonomy-version",
        taxonomy_version.strip(),
    ]


def run_datacenter_ui_command(
    *,
    page: ft.Page,
    title: str,
    command: List[str],
    log_field: ft.TextField,
    status_field: ft.TextField,
    output_dir: str | None = None,
    reports_column: ft.Column | None = None,
    assets_root: Path | None = None,
    signal_date: str | None = None,
    rolling_window_size: str | None = None,
    include_daily_reports: bool = False,
    include_rolling_reports: bool = False,
) -> None:
    def _append_log(message: str) -> None:
        existing = log_field.value or ""
        log_field.value = f"{message}\n{existing}".strip()

    def _worker() -> None:
        try:
            if output_dir and output_dir.strip():
                Path(output_dir.strip()).mkdir(parents=True, exist_ok=True)
            _append_log(f"=== Datacenter: {title} ===")
            _append_log("COMMAND " + " ".join(command))
            page.update()
            env = os.environ.copy()
            env["PYTHONPATH"] = "."
            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            combined = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).strip()
            if combined:
                _append_log(combined)
            if completed.returncode == 0:
                generated_reports: List[Path] = []
                if (
                    reports_column is not None
                    and assets_root is not None
                    and output_dir
                    and signal_date
                    and (include_daily_reports or include_rolling_reports)
                ):
                    generated_reports = find_datacenter_generated_reports(
                        output_dir=output_dir,
                        signal_date=signal_date,
                        rolling_window_size=rolling_window_size or "",
                        include_daily=include_daily_reports,
                        include_rolling=include_rolling_reports,
                    )
                    populate_datacenter_report_downloads(
                        page=page,
                        reports_column=reports_column,
                        status_field=status_field,
                        assets_root=assets_root,
                        report_paths=generated_reports,
                    )
                _append_log(f"=== Datacenter: {title} completed ===")
                if generated_reports:
                    generated_names = ", ".join(report_path.name for report_path in generated_reports)
                    _set_status(
                        status_field,
                        f"{title} completed.\nGenerated reports: {generated_names}",
                        _STATUS_OK_COLOR,
                    )
                else:
                    _set_status(status_field, f"{title} completed.", _STATUS_OK_COLOR)
            else:
                _append_log(f"=== Datacenter: {title} failed (exit {completed.returncode}) ===")
                _set_status(status_field, f"{title} failed with exit code {completed.returncode}.", _STATUS_ERROR_COLOR)
            page.update()
        except Exception as exc:
            _append_log(f"=== Datacenter: {title} failed ({exc}) ===")
            _set_status(status_field, f"{title} failed: {exc}", _STATUS_ERROR_COLOR)
            page.update()

    threading.Thread(target=_worker, daemon=True).start()


def run_app(page: ft.Page, config_path: str) -> None:
    page.title = "Stock Update Scheduler Control Panel"
    page.scroll = ft.ScrollMode.AUTO

    config_path_field = ft.TextField(
        label="Config path",
        value=config_path,
        read_only=True,
        expand=True,
    )
    osakedata_db_field = ft.TextField(label="osakedata_db_path", expand=True)
    analysis_db_field = ft.TextField(label="analysis_db_path", expand=True)
    log_dir_field = ft.TextField(label="log_dir", expand=True)
    timezone_field = ft.TextField(label="timezone", expand=True)
    run_time_field = ft.TextField(label="Run time (HH:MM)", width=200)

    omxh_checkbox = ft.Checkbox(label="OMXH")
    omxs_checkbox = ft.Checkbox(label="OMXS")
    usa_checkbox = ft.Checkbox(label="USA")
    skip_next_run_text = ft.Text("")
    running_status_text = ft.Text("")
    skip_next_run_button = ft.ElevatedButton("Ohita seuraava ajastettu ajo")
    cancel_skip_next_run_button = ft.ElevatedButton("Peru seuraavan ajon ohitus")

    status_field = ft.TextField(
        label="Status",
        value="",
        multiline=True,
        min_lines=3,
        max_lines=6,
        read_only=True,
        expand=True,
    )
    summary_field = ft.TextField(
        label="Latest scheduler summary",
        value="",
        multiline=True,
        min_lines=5,
        max_lines=10,
        read_only=True,
        expand=True,
    )
    timer_status_field = ft.TextField(
        label="Systemd timer status",
        value="",
        multiline=True,
        min_lines=5,
        max_lines=8,
        read_only=True,
        expand=True,
    )
    logs_column = ft.Column(spacing=8)
    datacenter_price_db_field = ft.TextField(label="price_db", value=DEFAULT_DATACENTER_PRICE_DB, expand=True)
    datacenter_analysis_db_field = ft.TextField(label="analysis_db", value=DEFAULT_DATACENTER_ANALYSIS_DB, expand=True)
    datacenter_taxonomy_csv_field = ft.TextField(label="taxonomy_csv", value=DEFAULT_DATACENTER_TAXONOMY_CSV, expand=True)
    datacenter_taxonomy_version_field = ft.TextField(label="taxonomy_version", value=DEFAULT_DATACENTER_TAXONOMY_VERSION, expand=True)
    datacenter_market_field = ft.TextField(label="market", value=DEFAULT_DATACENTER_MARKET, width=180)
    datacenter_signal_date_field = ft.TextField(
        label="signal_date (previous valid trading day)",
        value=DEFAULT_DATACENTER_SIGNAL_DATE,
        width=220,
    )
    datacenter_start_date_field = ft.TextField(
        label="start_date (swing recalculation start)",
        value=DEFAULT_DATACENTER_START_DATE,
        width=220,
    )
    datacenter_index_base_date_field = ft.TextField(label="index_base_date", value=DEFAULT_DATACENTER_INDEX_BASE_DATE, width=220)
    datacenter_output_dir_field = ft.TextField(label="output_dir", value=DEFAULT_DATACENTER_OUTPUT_DIR, expand=True)
    datacenter_expected_ticker_count_field = ft.TextField(label="expected_ticker_count", value=DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT, width=180)
    datacenter_expected_group_count_field = ft.TextField(label="expected_group_count", value=DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT, width=180)
    datacenter_expected_synthetic_ohlc_count_field = ft.TextField(label="expected_synthetic_ohlc_count", value=DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT, width=220)
    datacenter_rolling_window_size_field = ft.TextField(label="rolling_window_size", value=DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE, width=180)
    datacenter_watchlist_file_field = ft.TextField(label="watchlist_file", value=DEFAULT_DATACENTER_WATCHLIST_FILE, expand=True)
    datacenter_status_field = ft.TextField(
        label="Datacenter status",
        value="",
        multiline=True,
        min_lines=2,
        max_lines=4,
        read_only=True,
        expand=True,
    )
    datacenter_log_field = ft.TextField(
        label="Datacenter command log",
        value="",
        multiline=True,
        min_lines=12,
        max_lines=20,
        read_only=True,
        expand=True,
    )
    datacenter_reports_column = ft.Column(spacing=8)

    def selected_markets_from_ui() -> List[str]:
        selected: List[str] = []
        if omxh_checkbox.value:
            selected.append("OMXH")
        if omxs_checkbox.value:
            selected.append(" omxs ")
        if usa_checkbox.value:
            selected.append("USA")
        return selected

    def update_ui_from_config(config: StockUpdateSchedulerConfig) -> None:
        osakedata_db_field.value = config.osakedata_db_path
        analysis_db_field.value = config.analysis_db_path
        log_dir_field.value = config.log_dir
        timezone_field.value = config.timezone
        run_time_field.value = config.run_time
        skip_next_run_text.value = scheduler_skip_next_run_label(config)
        enabled_markets = set(config.enabled_markets)
        omxh_checkbox.value = "omxh" in enabled_markets
        omxs_checkbox.value = "omxs" in enabled_markets
        usa_checkbox.value = "usa" in enabled_markets

    def refresh_timer_status(config: StockUpdateSchedulerConfig) -> None:
        timer_status = read_systemd_user_timer_status()
        lines = [
            f"timer_path={timer_status['timer_path']}",
            f"desired_run_time={config.run_time}",
            f"installed_on_calendar={timer_status['on_calendar'] or ''}",
            f"timer_installed={1 if timer_status['installed'] else 0}",
            f"timer_status={timer_status['status_summary']}",
        ]
        if timer_status["error"]:
            lines.append(f"timer_error={timer_status['error']}")
        timer_status_field.value = "\n".join(lines)

    def refresh_running_state(log_dir: str) -> None:
        status = read_scheduler_status(log_dir)
        state = scheduler_running_state(status)
        if state["is_running"]:
            if state["current_market"]:
                running_status_text.value = (
                    f"Scheduler status: running ({state['current_market']})"
                )
            else:
                running_status_text.value = "Scheduler status: running"
        else:
            running_status_text.value = "Scheduler status: not running"
        current_config = _load_config_or_raise(config_path)
        button_state = scheduler_skip_button_state(config=current_config, status=status)
        skip_next_run_button.disabled = not button_state["skip_enabled"]
        cancel_skip_next_run_button.disabled = not button_state["cancel_enabled"]
        refresh_timer_status(current_config)

    def refresh_logs_view(log_dir: str) -> None:
        latest_summary = load_latest_scheduler_summary(log_dir)
        if latest_summary is None:
            summary_field.value = "No scheduler summary JSON found."
        else:
            lines = [
                f"overall_status={latest_summary.get('overall_status', '')}",
                "enabled_markets="
                + ",".join(latest_summary.get("enabled_markets", [])),
                f"summary_json_path={latest_summary.get('summary_json_path', '')}",
            ]
            for market_result in latest_summary.get("market_results", []):
                lines.append(_market_row_text(market_result))
            summary_field.value = "\n".join(lines)

        logs_column.controls.clear()
        text_log_entries = [
            log_entry
            for log_entry in list_scheduler_log_files(log_dir)
            if log_entry["text_openable"]
        ]
        if not text_log_entries:
            logs_column.controls.append(ft.Text("No text log files found."))
        else:
            log_rows: List[ft.Control] = []
            for log_entry in text_log_entries:
                log_path = log_entry["path"]

                def on_open_text_log(e, *, selected_log_path=log_path) -> None:
                    try:
                        if not Path(selected_log_path).exists():
                            raise FileNotFoundError(selected_log_path)
                        launch_browser_url(page, build_text_log_browser_url(selected_log_path))
                        _set_status(
                            status_field,
                            f"Opened text log: {selected_log_path}",
                            _STATUS_OK_COLOR,
                        )
                    except FileNotFoundError:
                        _set_status(
                            status_field,
                            f"Text log missing: {selected_log_path}",
                            _STATUS_ERROR_COLOR,
                        )
                    except Exception as exc:
                        _set_status(
                            status_field,
                            f"Open text log failed: {exc}",
                            _STATUS_ERROR_COLOR,
                        )
                    page.update()

                log_rows.append(
                    ft.Row(
                        controls=[
                            ft.Text(
                                f"{log_entry['filename']} "
                                f"(size={log_entry['size_bytes']}, modified_at={log_entry['modified_at']})",
                                expand=True,
                            ),
                            ft.ElevatedButton("Avaa .txt", on_click=on_open_text_log),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )

            logs_column.controls.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(controls=log_rows, spacing=8),
                        padding=12,
                    )
                )
            )
        refresh_running_state(log_dir)

    def on_save_config(e) -> None:
        try:
            config = build_config_from_ui_values(
                osakedata_db_path=osakedata_db_field.value,
                analysis_db_path=analysis_db_field.value,
                log_dir=log_dir_field.value,
                timezone=timezone_field.value,
                run_time=run_time_field.value,
                selected_markets=selected_markets_from_ui(),
            )
            save_result = save_config_and_sync_systemd_timer(
                config_path=config_path,
                config=config,
            )
            update_ui_from_config(config)
            refresh_logs_view(config.log_dir)
            status_color = {
                "OK": _STATUS_OK_COLOR,
                "WARNING": _STATUS_WARNING_COLOR,
                "FAILED": _STATUS_ERROR_COLOR,
            }[save_result["status"]]
            _set_status(status_field, save_result["message"], status_color)
        except Exception as exc:
            _set_status(status_field, f"Save failed: {exc}", _STATUS_ERROR_COLOR)
        page.update()

    def on_reload_config(e) -> None:
        try:
            config = _load_config_or_raise(config_path)
            update_ui_from_config(config)
            refresh_logs_view(config.log_dir)
            _set_status(status_field, f"Config reloaded: {config_path}", _STATUS_OK_COLOR)
        except Exception as exc:
            _set_status(status_field, f"Reload failed: {exc}", _STATUS_ERROR_COLOR)
        page.update()

    def on_run_now(e) -> None:
        try:
            result = run_scheduler_config(config_path=config_path)
            config = _load_config_or_raise(config_path)
            update_ui_from_config(config)
            refresh_logs_view(log_dir_field.value)
            _set_status(
                status_field,
                f"Run now completed: {result.overall_status}",
                _STATUS_OK_COLOR if result.overall_status == "OK" else _STATUS_WARNING_COLOR,
            )
        except Exception as exc:
            _set_status(status_field, format_run_now_error_message(exc), _STATUS_ERROR_COLOR)
        page.update()

    def on_skip_next_run(e) -> None:
        try:
            current_config = _load_config_or_raise(config_path)
            running_state = scheduler_running_state(read_scheduler_status(current_config.log_dir))
            if running_state["is_running"]:
                _set_status(
                    status_field,
                    "Skip next run blocked: scheduler run is currently active.",
                    _STATUS_ERROR_COLOR,
                )
                refresh_logs_view(current_config.log_dir)
                page.update()
                return
            updated_config = apply_skip_next_run_to_config(config_path)
            update_ui_from_config(updated_config)
            refresh_logs_view(updated_config.log_dir)
            _set_status(
                status_field,
                "Next scheduled run will be skipped.",
                _STATUS_OK_COLOR,
            )
        except Exception as exc:
            _set_status(status_field, f"Skip next run failed: {exc}", _STATUS_ERROR_COLOR)
        page.update()

    def on_cancel_skip_next_run(e) -> None:
        try:
            current_config = _load_config_or_raise(config_path)
            running_state = scheduler_running_state(read_scheduler_status(current_config.log_dir))
            if running_state["is_running"]:
                _set_status(
                    status_field,
                    "Cancel skip blocked: scheduler run is currently active.",
                    _STATUS_ERROR_COLOR,
                )
                refresh_logs_view(current_config.log_dir)
                page.update()
                return
            updated_config = apply_cancel_skip_next_run_to_config(config_path)
            update_ui_from_config(updated_config)
            refresh_logs_view(updated_config.log_dir)
            _set_status(
                status_field,
                "Next scheduled run will NOT be skipped.",
                _STATUS_OK_COLOR,
            )
        except Exception as exc:
            _set_status(status_field, f"Cancel skip failed: {exc}", _STATUS_ERROR_COLOR)
        page.update()

    def on_refresh_logs(e) -> None:
        try:
            refresh_logs_view(log_dir_field.value)
            _set_status(status_field, "Logs refreshed.", _STATUS_OK_COLOR)
        except Exception as exc:
            _set_status(status_field, f"Refresh logs failed: {exc}", _STATUS_ERROR_COLOR)
        page.update()

    def _datacenter_pipeline_command(*, dry_run: bool) -> List[str]:
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

    def on_datacenter_dry_run(e) -> None:
        run_datacenter_ui_command(
            page=page,
            title="Dry Run Pipeline",
            command=_datacenter_pipeline_command(dry_run=True),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
            output_dir=datacenter_output_dir_field.value,
            reports_column=datacenter_reports_column,
            assets_root=datacenter_assets_root,
        )

    def on_datacenter_run_pipeline(e) -> None:
        run_datacenter_ui_command(
            page=page,
            title="Run Full Pipeline",
            command=_datacenter_pipeline_command(dry_run=False),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
            output_dir=datacenter_output_dir_field.value,
            reports_column=datacenter_reports_column,
            assets_root=datacenter_assets_root,
            signal_date=datacenter_signal_date_field.value,
            rolling_window_size=datacenter_rolling_window_size_field.value,
            include_daily_reports=True,
            include_rolling_reports=True,
        )

    def on_datacenter_run_audit(e) -> None:
        run_datacenter_ui_command(
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
        )

    def on_datacenter_daily_report(e) -> None:
        run_datacenter_ui_command(
            page=page,
            title="Generate Daily Report",
            command=build_datacenter_daily_report_command(
                analysis_db=datacenter_analysis_db_field.value,
                signal_date=datacenter_signal_date_field.value,
                taxonomy_version=datacenter_taxonomy_version_field.value,
                watchlist_file=datacenter_watchlist_file_field.value,
                output_dir=datacenter_output_dir_field.value,
            ),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
            output_dir=datacenter_output_dir_field.value,
            reports_column=datacenter_reports_column,
            assets_root=datacenter_assets_root,
            signal_date=datacenter_signal_date_field.value,
            include_daily_reports=True,
        )

    def on_datacenter_rolling_report(e) -> None:
        run_datacenter_ui_command(
            page=page,
            title="Generate Rolling Report",
            command=build_datacenter_rolling_report_command(
                analysis_db=datacenter_analysis_db_field.value,
                signal_date=datacenter_signal_date_field.value,
                taxonomy_version=datacenter_taxonomy_version_field.value,
                rolling_window_size=datacenter_rolling_window_size_field.value,
                watchlist_file=datacenter_watchlist_file_field.value,
                output_dir=datacenter_output_dir_field.value,
            ),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
            output_dir=datacenter_output_dir_field.value,
            reports_column=datacenter_reports_column,
            assets_root=datacenter_assets_root,
            signal_date=datacenter_signal_date_field.value,
            rolling_window_size=datacenter_rolling_window_size_field.value,
            include_rolling_reports=True,
        )

    def on_datacenter_plan(e) -> None:
        run_datacenter_ui_command(
            page=page,
            title="Show Pipeline Plan",
            command=build_datacenter_pipeline_plan_command(
                analysis_db=datacenter_analysis_db_field.value,
                taxonomy_version=datacenter_taxonomy_version_field.value,
                market=datacenter_market_field.value,
                signal_date=datacenter_signal_date_field.value,
                start_date=datacenter_start_date_field.value,
                index_base_date=datacenter_index_base_date_field.value,
            ),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
        )

    def on_datacenter_watermarks(e) -> None:
        run_datacenter_ui_command(
            page=page,
            title="Show Watermarks",
            command=build_datacenter_watermark_command(
                analysis_db=datacenter_analysis_db_field.value,
                taxonomy_version=datacenter_taxonomy_version_field.value,
            ),
            log_field=datacenter_log_field,
            status_field=datacenter_status_field,
        )

    initial_config = _load_config_or_raise(config_path)
    datacenter_assets_root = Path(initial_config.log_dir)
    update_ui_from_config(initial_config)
    refresh_logs_view(initial_config.log_dir)
    skip_next_run_button.on_click = on_skip_next_run
    cancel_skip_next_run_button.on_click = on_cancel_skip_next_run

    scheduler_content = ft.Column(
        controls=[
            ft.Text("Stock Update Scheduler Control Panel", size=24, weight=ft.FontWeight.BOLD),
            config_path_field,
            osakedata_db_field,
            analysis_db_field,
            log_dir_field,
            timezone_field,
            run_time_field,
            ft.Row([omxh_checkbox, omxs_checkbox, usa_checkbox]),
            skip_next_run_text,
            running_status_text,
            ft.Row(
                [
                    ft.ElevatedButton("Save config", on_click=on_save_config),
                    ft.ElevatedButton("Reload config", on_click=on_reload_config),
                    ft.ElevatedButton("Run now", on_click=on_run_now),
                    skip_next_run_button,
                    cancel_skip_next_run_button,
                    ft.ElevatedButton("Refresh logs", on_click=on_refresh_logs),
                ]
            ),
            status_field,
            summary_field,
            timer_status_field,
            ft.Text("Recent scheduler logs", size=18, weight=ft.FontWeight.BOLD),
            logs_column,
        ],
        spacing=12,
        expand=True,
    )

    datacenter_dry_run_button = ft.ElevatedButton("Dry Run Pipeline", on_click=on_datacenter_dry_run)
    datacenter_run_pipeline_button = ft.ElevatedButton("Run Full Pipeline", on_click=on_datacenter_run_pipeline)
    datacenter_audit_button = ft.ElevatedButton("Run Audit", on_click=on_datacenter_run_audit)
    datacenter_daily_report_button = ft.ElevatedButton("Generate Daily Report", on_click=on_datacenter_daily_report)
    datacenter_rolling_report_button = ft.ElevatedButton("Generate Rolling Report", on_click=on_datacenter_rolling_report)
    datacenter_plan_button = ft.ElevatedButton("Show Pipeline Plan", on_click=on_datacenter_plan)
    datacenter_watermarks_button = ft.ElevatedButton("Show Watermarks", on_click=on_datacenter_watermarks)
    datacenter_buttons = ft.Row(
        [
            datacenter_dry_run_button,
            datacenter_run_pipeline_button,
            datacenter_audit_button,
            datacenter_daily_report_button,
            datacenter_rolling_report_button,
            datacenter_plan_button,
            datacenter_watermarks_button,
        ],
        wrap=True,
    )
    datacenter_content = ft.Column(
        controls=[
            ft.Text("Datacenter", size=24, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Run Audit before interpreting reports. WARN may be acceptable; FAIL means do not interpret reports."
            ),
            datacenter_price_db_field,
            datacenter_analysis_db_field,
            datacenter_taxonomy_csv_field,
            ft.Row([datacenter_taxonomy_version_field, datacenter_market_field]),
            ft.Row([datacenter_signal_date_field, datacenter_start_date_field, datacenter_index_base_date_field]),
            datacenter_output_dir_field,
            ft.Row(
                [
                    datacenter_expected_ticker_count_field,
                    datacenter_expected_group_count_field,
                    datacenter_expected_synthetic_ohlc_count_field,
                    datacenter_rolling_window_size_field,
                ],
                wrap=True,
            ),
            datacenter_watchlist_file_field,
            datacenter_buttons,
            datacenter_status_field,
            datacenter_reports_column,
            datacenter_log_field,
        ],
        spacing=12,
        expand=True,
    )

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
    page.datacenter_status_field = datacenter_status_field
    page.datacenter_reports_column = datacenter_reports_column
    page.datacenter_log_field = datacenter_log_field
    page.datacenter_dry_run_button = datacenter_dry_run_button
    page.datacenter_run_pipeline_button = datacenter_run_pipeline_button
    page.datacenter_audit_button = datacenter_audit_button
    page.datacenter_daily_report_button = datacenter_daily_report_button
    page.datacenter_rolling_report_button = datacenter_rolling_report_button
    page.datacenter_plan_button = datacenter_plan_button
    page.datacenter_watermarks_button = datacenter_watermarks_button

    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(text="Scheduler", content=scheduler_content),
            ft.Tab(text="Datacenter", content=datacenter_content),
        ],
        expand=1,
    )
    page.datacenter_tabs = tabs
    page.add(tabs)
    page.update()


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Missing scheduler config: {config_path}")
    initial_config = read_scheduler_config(config_path)

    app_view = ft.WEB_BROWSER if hasattr(ft, "WEB_BROWSER") else ft.AppView.WEB_BROWSER
    ft.app(
        target=lambda page: run_app(page, config_path),
        view=app_view,
        port=SCHEDULER_UI_PORT,
        assets_dir=initial_config.log_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
