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

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionBatchResult,
    DatacenterTickerDecision,
    build_datacenter_ticker_decisions,
)
from dev_tools.datacenter_dashboard_inspector import (
    DatacenterTickerInspectorView,
    build_datacenter_ticker_inspector_view,
)
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardBatchParseResult,
    DatacenterDashboardRow,
    parse_datacenter_dashboard_file,
    parse_datacenter_dashboard_reports,
)
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    discover_datacenter_dashboard_status,
    list_datacenter_report_dates,
)
from dev_tools.run_datacenter_dashboard_html import (
    generate_datacenter_dashboard_html_file,
    resolve_dashboard_html_output_path,
)
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
_DATACENTER_LOG_FILENAME_RE = re.compile(
    r"^datacenter_pipeline_([a-z0-9_]+)_(\d{8}T\d{4,6}Z)(?:_(\d+))?\.(txt|log)$"
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
DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR = "/home/kalle/projects/rawcandle/temp"
_DATACENTER_DASHBOARD_REPORT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
        technical_relevance_enabled=config.technical_relevance_enabled,
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
        technical_relevance_enabled=config.technical_relevance_enabled,
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
        datacenter_log_match = _DATACENTER_LOG_FILENAME_RE.match(path.name)
        if summary_match:
            timestamp = summary_match.group(1)
            entry_type = "summary_json"
            suffix = "0"
        elif log_match:
            timestamp = log_match.group(2)
            suffix = log_match.group(3) or "0"
            entry_type = "market_log"
        elif datacenter_log_match:
            timestamp = datacenter_log_match.group(2)
            suffix = datacenter_log_match.group(3) or "0"
            entry_type = "datacenter_log"
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
                "sort_key": f"{timestamp}_{suffix}",
                "type": entry_type,
                "text_openable": entry_type in {"market_log", "datacenter_log"},
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


def _is_wsl_environment() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"microsoft|wsl", proc_version, flags=re.IGNORECASE))


def _build_windows_dashboard_path(output_path: str) -> str | None:
    if shutil.which("wslpath") is None:
        return None
    completed = subprocess.run(
        ["wslpath", "-w", output_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    windows_path = (completed.stdout or "").strip()
    return windows_path or None


def _build_dashboard_file_url(output_path: str, windows_path: str | None) -> str:
    if windows_path:
        return f"file:{windows_path.replace(chr(92), '/')}"
    return Path(output_path).resolve().as_uri()


def open_datacenter_dashboard_html(output_path: str) -> dict[str, str | list[str]]:
    windows_path = _build_windows_dashboard_path(output_path)
    file_url = _build_dashboard_file_url(output_path, windows_path)
    attempts: list[tuple[str, list[str]]] = []
    if _is_wsl_environment():
        if windows_path:
            attempts.extend(
                [
                    ("cmd.exe", ["cmd.exe", "/C", "start", "", windows_path]),
                    (
                        "powershell.exe",
                        ["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{windows_path}'"],
                    ),
                    ("firefox.exe", ["firefox.exe", windows_path]),
                    ("explorer.exe", ["explorer.exe", windows_path]),
                ]
            )
        attempts.extend(
            [
                ("firefox", ["firefox", output_path]),
                ("xdg-open", ["xdg-open", output_path]),
            ]
        )
    else:
        attempts.extend(
            [
                ("firefox", ["firefox", output_path]),
                ("xdg-open", ["xdg-open", output_path]),
            ]
        )

    for opener_name, command in attempts:
        if shutil.which(command[0]) is None:
            continue
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode == 0:
            return {
                "open_status": "OK",
                "opener": opener_name,
                "html_output": output_path,
                "html_output_windows": windows_path or "unavailable",
                "html_file_url": file_url,
                "manual_lines": [],
            }

    manual_lines = [
        "Open manually in Firefox:",
        "1. Copy this path:",
        windows_path or output_path,
        "2. Paste it into Firefox address bar.",
        f"Linux path: {output_path}",
        f"Windows path: {windows_path or 'unavailable'}",
    ]
    return {
        "open_status": "FAILED",
        "opener": "none",
        "html_output": output_path,
        "html_output_windows": windows_path or "unavailable",
        "html_file_url": file_url,
        "manual_lines": manual_lines,
    }


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


def _dashboard_status_color(status: str) -> str:
    if status == "READY" or status == "OK":
        return _STATUS_OK_COLOR
    if status == "PARTIAL":
        return _STATUS_WARNING_COLOR
    return _STATUS_ERROR_COLOR


def populate_datacenter_dashboard_summary(
    *,
    dashboard_status: DatacenterDashboardStatus,
    parse_result: DatacenterDashboardBatchParseResult,
    decision_result: DatacenterDecisionBatchResult,
    overall_status_field: ft.TextField,
    parse_summary_field: ft.TextField,
    decision_summary_field: ft.TextField,
    readiness_text: ft.Text,
    reports_status_text: ft.Text,
    decisions_status_text: ft.Text,
    candidate_status_text: ft.Text,
    reports_column: ft.Column,
) -> None:
    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    missing_reports = sum(1 for report in dashboard_status.reports if report.status != "OK")
    overall_status_field.value = dashboard_status.overall_status
    overall_status_field.border_color = _dashboard_status_color(
        dashboard_status.overall_status
    )
    readiness_text.value = f"Readiness: {dashboard_status.overall_status}"
    reports_status_text.value = (
        f"Reports: found={found_reports} missing={missing_reports}"
    )
    decisions_status_text.value = (
        f"Decisions: total={len(decision_result.decisions)}"
    )
    candidate_count = decision_result.pullback_counts.get("VALID_PULLBACK", 0) + decision_result.pullback_counts.get("EARLY_PULLBACK", 0)
    candidate_status_text.value = f"Candidate Pullbacks: {candidate_count}"
    parse_summary_field.value = (
        f"readiness={dashboard_status.overall_status}\n"
        f"found_reports={found_reports}\n"
        f"missing_reports={missing_reports}\n"
        f"total_parsed_rows={parse_result.total_row_count}\n"
        f"total_parse_warnings={parse_result.total_warning_count}"
    )
    decision_summary_field.value = "\n".join(
        [
            f"decision_total={len(decision_result.decisions)}",
            f"SELL={decision_result.action_counts.get('SELL', 0)}",
            f"REDUCE={decision_result.action_counts.get('REDUCE', 0)}",
            f"TIGHTEN_STOP={decision_result.action_counts.get('TIGHTEN_STOP', 0)}",
            f"BUY_NOW={decision_result.action_counts.get('BUY_NOW', 0)}",
            f"WAIT_PULLBACK={decision_result.action_counts.get('WAIT_PULLBACK', 0)}",
            f"BLOCKED={decision_result.action_counts.get('BLOCKED', 0)}",
            f"WATCH={decision_result.action_counts.get('WATCH', 0)}",
            f"NEUTRAL={decision_result.action_counts.get('NEUTRAL', 0)}",
            f"VALID_PULLBACK={decision_result.pullback_counts.get('VALID_PULLBACK', 0)}",
            f"EARLY_PULLBACK={decision_result.pullback_counts.get('EARLY_PULLBACK', 0)}",
            "STRUCTURE_BLOCKED_PULLBACK="
            f"{decision_result.pullback_counts.get('STRUCTURE_BLOCKED_PULLBACK', 0)}",
            "BREAKDOWN_NOT_PULLBACK="
            f"{decision_result.pullback_counts.get('BREAKDOWN_NOT_PULLBACK', 0)}",
            f"NO_PULLBACK={decision_result.pullback_counts.get('NO_PULLBACK', 0)}",
            "INSUFFICIENT_DATA="
            f"{decision_result.pullback_counts.get('INSUFFICIENT_DATA', 0)}",
            "entry_readiness.READY_TO_WATCH="
            f"{decision_result.entry_readiness_counts.get('READY_TO_WATCH', 0)}",
            "entry_readiness.NEEDS_STOP_STABILIZATION="
            f"{decision_result.entry_readiness_counts.get('NEEDS_STOP_STABILIZATION', 0)}",
            "entry_readiness.NEEDS_RISK_CLEARANCE="
            f"{decision_result.entry_readiness_counts.get('NEEDS_RISK_CLEARANCE', 0)}",
            "entry_readiness.EARLY_MONITOR="
            f"{decision_result.entry_readiness_counts.get('EARLY_MONITOR', 0)}",
            "entry_readiness.NOT_READY="
            f"{decision_result.entry_readiness_counts.get('NOT_READY', 0)}",
            "candidate_priority.P1_READY_TO_WATCH="
            f"{decision_result.candidate_priority_counts.get('P1_READY_TO_WATCH', 0)}",
            "candidate_priority.P2_STOP_STABILIZATION="
            f"{decision_result.candidate_priority_counts.get('P2_STOP_STABILIZATION', 0)}",
            "candidate_priority.P3_RISK_CLEARANCE="
            f"{decision_result.candidate_priority_counts.get('P3_RISK_CLEARANCE', 0)}",
            "candidate_priority.P4_EARLY_MONITOR="
            f"{decision_result.candidate_priority_counts.get('P4_EARLY_MONITOR', 0)}",
            "candidate_priority.P5_NOT_READY="
            f"{decision_result.candidate_priority_counts.get('P5_NOT_READY', 0)}",
        ]
    )
    reports_column.controls.clear()
    parse_by_horizon = {
        report.horizon: report for report in parse_result.reports
    }
    for report in dashboard_status.reports:
        parse_summary = parse_by_horizon.get(report.horizon)
        reports_column.controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            f"{report.horizon}: {report.status}",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(f"path: {report.path or 'NONE'}", size=11),
                        ft.Text(
                            f"modified_at: {report.modified_at or 'NONE'}",
                            size=11,
                            color="gray",
                        ),
                        ft.Text(
                            f"parsed_rows: {parse_summary.row_count if parse_summary else 0}",
                            size=11,
                        ),
                        ft.Text(
                            f"warnings: {parse_summary.warning_count if parse_summary else 0}",
                            size=11,
                        ),
                    ],
                    spacing=2,
                ),
                border=ft.border.all(1, "#DADCE0"),
                border_radius=8,
                padding=10,
            )
        )


def populate_datacenter_dashboard_command_center(
    *,
    decision_result: DatacenterDecisionBatchResult,
    command_center_column: ft.Column,
) -> None:
    command_center_column.controls.clear()
    grouped_actions = [
        ("Critical exits", ("SELL", "REDUCE", "TIGHTEN_STOP")),
        ("Buy candidates", ("BUY_NOW", "WATCH", "WAIT_PULLBACK")),
        ("Blocked / neutral", ("BLOCKED", "NEUTRAL")),
    ]

    decisions_by_action: dict[str, list[Any]] = {}
    for action_name in ("SELL", "REDUCE", "TIGHTEN_STOP", "BUY_NOW", "WATCH", "WAIT_PULLBACK", "BLOCKED", "NEUTRAL"):
        decisions_by_action[action_name] = [
            decision for decision in decision_result.decisions if decision.action == action_name
        ]

    if not decision_result.decisions:
        command_center_column.controls.append(ft.Text("No decisions available."))
        return

    for group_title, actions in grouped_actions:
        group_rows = [
            decision
            for action_name in actions
            for decision in decisions_by_action[action_name]
        ]
        if not group_rows:
            continue
        command_center_column.controls.append(
            ft.Text(group_title, size=18, weight=ft.FontWeight.BOLD)
        )
        for decision in group_rows:
            command_center_column.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                f"{decision.ticker} | {decision.action} | {decision.severity}",
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                f"primary_reason: {decision.primary_reason or 'NONE'}",
                                size=11,
                            ),
                            ft.Text(
                                "distance_to_ema20="
                                f"{decision.distance_to_ema20 if decision.distance_to_ema20 is not None else 'NONE'}"
                                " | high_exit_risk_days_count="
                                f"{decision.high_exit_risk_days_count if decision.high_exit_risk_days_count is not None else 'NONE'}",
                                size=11,
                            ),
                            ft.Text(
                                "trend_state="
                                f"{decision.trend_state or 'NONE'}"
                                " | latest_structure_label="
                                f"{decision.latest_structure_label or 'NONE'}"
                                " | latest_bos_event_type="
                                f"{decision.latest_bos_event_type or 'NONE'}",
                                size=11,
                            ),
                            ft.Text(
                                f"latest_reset_reason: {decision.latest_reset_reason or 'NONE'}",
                                size=11,
                            ),
                            ft.Text(
                                "horizons_present: "
                                f"{', '.join(decision.horizons_present) if decision.horizons_present else 'NONE'}",
                                size=11,
                            ),
                            ft.Text(
                                f"source_files: {len(decision.source_files)}",
                                size=11,
                                color="gray",
                            ),
                        ],
                        spacing=2,
                    ),
                    border=ft.border.all(1, "#DADCE0"),
                    border_radius=8,
                    padding=10,
                )
            )


def _dashboard_context_rows_for_ticker(
    rows: list[DatacenterDashboardRow],
    ticker: str,
) -> list[DatacenterDashboardRow]:
    horizon_order = {
        "daily": 0,
        "rolling 2d": 1,
        "rolling 5d": 2,
        "rolling 30d": 3,
    }
    return sorted(
        [row for row in rows if row.ticker == ticker],
        key=lambda row: (
            horizon_order.get(row.horizon, 99),
            row.source_file,
            row.section or "",
            row.raw_status or "",
            row.raw_action or "",
        ),
    )


def _dashboard_first_non_empty_context_value(
    rows: list[DatacenterDashboardRow],
    field_name: str,
) -> str | int | float | None:
    for row in rows:
        value = getattr(row, field_name, None)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def populate_datacenter_dashboard_candidate_pullbacks(
    *,
    decision_result: DatacenterDecisionBatchResult,
    parsed_rows: list[DatacenterDashboardRow],
    candidate_pullbacks_column: ft.Column,
) -> None:
    candidate_pullbacks_column.controls.clear()
    candidate_decisions = [
        decision
        for decision in decision_result.decisions
        if decision.pullback_validity in {"VALID_PULLBACK", "EARLY_PULLBACK"}
    ]
    candidate_decisions.sort(
        key=lambda decision: (
            decision.candidate_priority or 9,
            0 if decision.pullback_validity == "VALID_PULLBACK" else 1,
            (
                "READY_TO_WATCH",
                "NEEDS_STOP_STABILIZATION",
                "NEEDS_RISK_CLEARANCE",
                "EARLY_MONITOR",
                "NOT_READY",
                "INSUFFICIENT_DATA",
            ).index(decision.entry_readiness or "INSUFFICIENT_DATA"),
            ("WATCH", "NEUTRAL", "TIGHTEN_STOP", "REDUCE", "SELL", "BLOCKED", "WAIT_PULLBACK", "BUY_NOW").index(decision.action),
            decision.latest_bullish_signal_age_td
            if decision.latest_bullish_signal_age_td is not None
            else 999999,
            decision.ticker,
        )
    )
    if not candidate_decisions:
        candidate_pullbacks_column.controls.append(ft.Text("No candidate pullbacks available."))
        return
    for decision in candidate_decisions:
        context_rows = _dashboard_context_rows_for_ticker(parsed_rows, decision.ticker)
        candidate_pullbacks_column.controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            f"{decision.ticker} | {decision.candidate_priority_label or 'P9_NOT_CANDIDATE'} | {decision.entry_readiness or 'NONE'} | {decision.action}",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"primary_reason: {decision.primary_reason or 'NONE'}",
                            size=11,
                        ),
                        ft.Text(
                            f"entry_readiness_reason: {decision.entry_readiness_reason or 'NONE'}",
                            size=11,
                        ),
                        ft.Text(
                            "ma_break_status="
                            f"{_dashboard_first_non_empty_context_value(context_rows, 'ma_break_status') or 'NONE'}"
                            " | freshness_status="
                            f"{_dashboard_first_non_empty_context_value(context_rows, 'freshness_status') or 'NONE'}",
                            size=11,
                        ),
                    ],
                    spacing=2,
                ),
                border=ft.border.all(1, "#DADCE0"),
                border_radius=8,
                padding=10,
            )
        )


def populate_datacenter_dashboard_inspector(
    *,
    inspector_view: DatacenterTickerInspectorView | None,
    inspector_ticker_dropdown: ft.Dropdown,
    decision_result: DatacenterDecisionBatchResult,
    selected_ticker: str | None,
    action_field: ft.TextField,
    conflict_detected_field: ft.TextField,
    pullback_validity_field: ft.TextField,
    pullback_reason_field: ft.TextField,
    supporting_signals_field: ft.TextField,
    conflicting_signals_field: ft.TextField,
    override_explanation_field: ft.TextField,
) -> None:
    inspector_ticker_dropdown.options = [
        ft.dropdown.Option(decision.ticker) for decision in decision_result.decisions
    ]
    if decision_result.decisions:
        inspector_ticker_dropdown.value = selected_ticker or decision_result.decisions[0].ticker
    else:
        inspector_ticker_dropdown.value = None

    if inspector_view is None:
        action_field.value = "NONE"
        conflict_detected_field.value = "False"
        pullback_validity_field.value = "NONE"
        pullback_reason_field.value = "NONE"
        supporting_signals_field.value = "NONE"
        conflicting_signals_field.value = "NONE"
        override_explanation_field.value = "NONE"
        return

    action_field.value = (
        f"{inspector_view.ticker} | {inspector_view.action} | {inspector_view.severity}"
    )
    conflict_detected_field.value = str(inspector_view.conflict_detected)
    pullback_validity_field.value = inspector_view.pullback_validity or "NONE"
    pullback_reason_field.value = inspector_view.pullback_reason or "NONE"
    supporting_signals_field.value = (
        ", ".join(inspector_view.supporting_signals)
        if inspector_view.supporting_signals
        else "NONE"
    )
    conflicting_signals_field.value = (
        ", ".join(inspector_view.conflicting_signals)
        if inspector_view.conflicting_signals
        else "NONE"
    )
    override_explanation_field.value = inspector_view.override_explanation or "NONE"


def populate_datacenter_dashboard_not_refreshed(
    *,
    overall_status_field: ft.TextField,
    parse_summary_field: ft.TextField,
    decision_summary_field: ft.TextField,
    readiness_text: ft.Text,
    reports_status_text: ft.Text,
    decisions_status_text: ft.Text,
    candidate_status_text: ft.Text,
    reports_column: ft.Column,
    command_center_column: ft.Column,
    candidate_pullbacks_column: ft.Column,
    inspector_ticker_dropdown: ft.Dropdown,
    action_field: ft.TextField,
    conflict_detected_field: ft.TextField,
    pullback_validity_field: ft.TextField,
    pullback_reason_field: ft.TextField,
    supporting_signals_field: ft.TextField,
    conflicting_signals_field: ft.TextField,
    override_explanation_field: ft.TextField,
) -> None:
    overall_status_field.value = "NOT_REFRESHED"
    overall_status_field.border_color = _STATUS_WARNING_COLOR
    readiness_text.value = "Readiness: NOT_REFRESHED"
    reports_status_text.value = "Reports: No reports loaded."
    decisions_status_text.value = "Decisions: No decisions available."
    candidate_status_text.value = "Candidate Pullbacks: No candidate pullbacks available."
    parse_summary_field.value = (
        "readiness=NOT_REFRESHED\n"
        "found_reports=0\n"
        "missing_reports=0\n"
        "total_parsed_rows=0\n"
        "total_parse_warnings=0"
    )
    decision_summary_field.value = "\n".join(
        [
            "decision_total=0",
            "SELL=0",
            "REDUCE=0",
            "TIGHTEN_STOP=0",
            "BUY_NOW=0",
            "WAIT_PULLBACK=0",
            "BLOCKED=0",
            "WATCH=0",
            "NEUTRAL=0",
            "VALID_PULLBACK=0",
            "EARLY_PULLBACK=0",
            "STRUCTURE_BLOCKED_PULLBACK=0",
            "BREAKDOWN_NOT_PULLBACK=0",
            "NO_PULLBACK=0",
            "INSUFFICIENT_DATA=0",
            "entry_readiness.READY_TO_WATCH=0",
            "entry_readiness.NEEDS_STOP_STABILIZATION=0",
            "entry_readiness.NEEDS_RISK_CLEARANCE=0",
            "entry_readiness.EARLY_MONITOR=0",
            "entry_readiness.NOT_READY=0",
            "candidate_priority.P1_READY_TO_WATCH=0",
            "candidate_priority.P2_STOP_STABILIZATION=0",
            "candidate_priority.P3_RISK_CLEARANCE=0",
            "candidate_priority.P4_EARLY_MONITOR=0",
            "candidate_priority.P5_NOT_READY=0",
        ]
    )
    reports_column.controls.clear()
    reports_column.controls.append(ft.Text("No reports loaded."))
    command_center_column.controls.clear()
    command_center_column.controls.append(ft.Text("No decisions available."))
    candidate_pullbacks_column.controls.clear()
    candidate_pullbacks_column.controls.append(ft.Text("No candidate pullbacks available."))
    inspector_ticker_dropdown.options = []
    inspector_ticker_dropdown.value = None
    action_field.value = "NONE"
    conflict_detected_field.value = "False"
    pullback_validity_field.value = "NONE"
    pullback_reason_field.value = "NONE"
    supporting_signals_field.value = "NONE"
    conflicting_signals_field.value = "NONE"
    override_explanation_field.value = "NONE"


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
    technical_relevance_checkbox = ft.Checkbox(
        label="Run technical relevance after stock updates",
        value=False,
        tooltip=(
            "Runs technical_signal_relevance after daily "
            "OHLCV/candle/divergence/Dow updates. Default off."
        ),
    )
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
    datacenter_dashboard_reports_dir_field = ft.TextField(
        label="dashboard_reports_dir",
        value=DEFAULT_DATACENTER_OUTPUT_DIR,
        expand=True,
    )
    datacenter_dashboard_real_render_marker_text = ft.Text(
        "REAL RENDER CHECK: DATACENTER DASHBOARD V3",
        size=28,
        weight=ft.FontWeight.BOLD,
        color="#0B57D0",
    )
    datacenter_dashboard_real_render_diag_text = ft.Text(
        "dashboard_real_render_v3=1"
    )
    datacenter_dashboard_tab_constructed_text = ft.Text(
        "dashboard_tab_constructed=1"
    )
    datacenter_dashboard_backend_available_text = ft.Text(
        "dashboard_backend_available=1"
    )
    datacenter_dashboard_build_marker_text = ft.Text(
        "Dashboard UI build: dashboard_ui_visible_v1",
        size=12,
        color="gray",
    )
    datacenter_dashboard_readiness_text = ft.Text("Readiness: NOT_REFRESHED")
    datacenter_dashboard_reports_status_text = ft.Text("Reports: No reports loaded.")
    datacenter_dashboard_decisions_status_text = ft.Text("Decisions: No decisions available.")
    datacenter_dashboard_candidate_status_text = ft.Text(
        "Candidate Pullbacks: No candidate pullbacks available."
    )
    datacenter_dashboard_overall_status_field = ft.TextField(
        label="dashboard_overall_status",
        value="NOT_REFRESHED",
        read_only=True,
        width=220,
        border_color=_STATUS_WARNING_COLOR,
    )
    datacenter_dashboard_parse_summary_field = ft.TextField(
        label="dashboard_readiness_summary",
        value=(
            "readiness=NOT_REFRESHED\n"
            "found_reports=0\n"
            "missing_reports=0\n"
            "total_parsed_rows=0\n"
            "total_parse_warnings=0"
        ),
        read_only=True,
        multiline=True,
        min_lines=5,
        max_lines=5,
        width=260,
    )
    datacenter_dashboard_decision_summary_field = ft.TextField(
        label="dashboard_decision_summary",
        value=(
            "decision_total=0\n"
            "SELL=0\n"
            "REDUCE=0\n"
            "TIGHTEN_STOP=0\n"
            "BUY_NOW=0\n"
            "WAIT_PULLBACK=0\n"
            "BLOCKED=0\n"
            "WATCH=0\n"
            "NEUTRAL=0\n"
            "VALID_PULLBACK=0\n"
            "EARLY_PULLBACK=0\n"
            "STRUCTURE_BLOCKED_PULLBACK=0\n"
            "BREAKDOWN_NOT_PULLBACK=0\n"
            "NO_PULLBACK=0\n"
            "INSUFFICIENT_DATA=0\n"
            "entry_readiness.READY_TO_WATCH=0\n"
            "entry_readiness.NEEDS_STOP_STABILIZATION=0\n"
            "entry_readiness.NEEDS_RISK_CLEARANCE=0\n"
            "entry_readiness.EARLY_MONITOR=0\n"
            "candidate_priority.P1_READY_TO_WATCH=0\n"
            "candidate_priority.P2_STOP_STABILIZATION=0\n"
            "candidate_priority.P3_RISK_CLEARANCE=0\n"
            "candidate_priority.P4_EARLY_MONITOR=0"
        ),
        read_only=True,
        multiline=True,
        min_lines=8,
        max_lines=16,
        width=300,
    )
    datacenter_dashboard_candidate_pullbacks_column = ft.Column(spacing=8)
    datacenter_dashboard_inspector_ticker_dropdown = ft.Dropdown(
        label="inspector_ticker",
        options=[],
        width=220,
    )
    datacenter_dashboard_inspector_action_field = ft.TextField(
        label="inspector_action",
        value="NONE",
        read_only=True,
        multiline=True,
        min_lines=1,
        max_lines=2,
        expand=True,
    )
    datacenter_dashboard_conflict_detected_field = ft.TextField(
        label="conflict_detected",
        value="False",
        read_only=True,
        width=180,
    )
    datacenter_dashboard_pullback_validity_field = ft.TextField(
        label="pullback_validity",
        value="NONE",
        read_only=True,
        width=240,
    )
    datacenter_dashboard_pullback_reason_field = ft.TextField(
        label="pullback_reason",
        value="NONE",
        read_only=True,
        multiline=True,
        min_lines=1,
        max_lines=2,
        expand=True,
    )
    datacenter_dashboard_supporting_signals_field = ft.TextField(
        label="supporting_signals",
        value="NONE",
        read_only=True,
        multiline=True,
        min_lines=2,
        max_lines=4,
        expand=True,
    )
    datacenter_dashboard_conflicting_signals_field = ft.TextField(
        label="conflicting_signals",
        value="NONE",
        read_only=True,
        multiline=True,
        min_lines=2,
        max_lines=4,
        expand=True,
    )
    datacenter_dashboard_override_explanation_field = ft.TextField(
        label="override_explanation",
        value="NONE",
        read_only=True,
        multiline=True,
        min_lines=2,
        max_lines=3,
        expand=True,
    )
    datacenter_dashboard_command_center_column = ft.Column(spacing=8)
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
    datacenter_dashboard_reports_column = ft.Column(spacing=8)
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
        technical_relevance_checkbox.value = config.technical_relevance_enabled

    def refresh_datacenter_dashboard_view() -> dict[str, int]:
        dashboard_status = discover_datacenter_dashboard_status(
            datacenter_dashboard_reports_dir_field.value
        )
        parse_result = parse_datacenter_dashboard_reports(dashboard_status.reports)
        parsed_rows: list[DatacenterDashboardRow] = []
        for report in dashboard_status.reports:
            if not report.path:
                continue
            parsed_rows.extend(
                parse_datacenter_dashboard_file(
                    path=report.path,
                    horizon=report.horizon,
                ).rows
            )
        decision_result = build_datacenter_ticker_decisions(parsed_rows)
        populate_datacenter_dashboard_summary(
            dashboard_status=dashboard_status,
            parse_result=parse_result,
            decision_result=decision_result,
            overall_status_field=datacenter_dashboard_overall_status_field,
            parse_summary_field=datacenter_dashboard_parse_summary_field,
            decision_summary_field=datacenter_dashboard_decision_summary_field,
            readiness_text=datacenter_dashboard_readiness_text,
            reports_status_text=datacenter_dashboard_reports_status_text,
            decisions_status_text=datacenter_dashboard_decisions_status_text,
            candidate_status_text=datacenter_dashboard_candidate_status_text,
            reports_column=datacenter_dashboard_reports_column,
        )
        populate_datacenter_dashboard_command_center(
            decision_result=decision_result,
            command_center_column=datacenter_dashboard_command_center_column,
        )
        populate_datacenter_dashboard_candidate_pullbacks(
            decision_result=decision_result,
            parsed_rows=parsed_rows,
            candidate_pullbacks_column=datacenter_dashboard_candidate_pullbacks_column,
        )
        decisions_by_ticker = {
            decision.ticker: decision for decision in decision_result.decisions
        }
        selected_ticker = datacenter_dashboard_inspector_ticker_dropdown.value
        if (
            decision_result.decisions
            and (not selected_ticker or selected_ticker not in decisions_by_ticker)
        ):
            selected_ticker = decision_result.decisions[0].ticker
        selected_decision = (
            decisions_by_ticker.get(selected_ticker) if selected_ticker else None
        )
        inspector_view = (
            build_datacenter_ticker_inspector_view(
                decision=selected_decision,
                rows=parsed_rows,
            )
            if selected_decision is not None
            else None
        )
        populate_datacenter_dashboard_inspector(
            inspector_view=inspector_view,
            inspector_ticker_dropdown=datacenter_dashboard_inspector_ticker_dropdown,
            decision_result=decision_result,
            selected_ticker=selected_ticker,
            action_field=datacenter_dashboard_inspector_action_field,
            conflict_detected_field=datacenter_dashboard_conflict_detected_field,
            pullback_validity_field=datacenter_dashboard_pullback_validity_field,
            pullback_reason_field=datacenter_dashboard_pullback_reason_field,
            supporting_signals_field=datacenter_dashboard_supporting_signals_field,
            conflicting_signals_field=datacenter_dashboard_conflicting_signals_field,
            override_explanation_field=datacenter_dashboard_override_explanation_field,
        )
        page.update()
        found_reports = sum(
            1 for report in dashboard_status.reports if report.status == "OK"
        )
        return {
            "found_reports": found_reports,
            "decision_total": len(decision_result.decisions),
        }

    def refresh_datacenter_dashboard_inspector_for_selected_ticker() -> None:
        dashboard_status = discover_datacenter_dashboard_status(
            datacenter_dashboard_reports_dir_field.value
        )
        parsed_rows: list[DatacenterDashboardRow] = []
        for report in dashboard_status.reports:
            if not report.path:
                continue
            parsed_rows.extend(
                parse_datacenter_dashboard_file(
                    path=report.path,
                    horizon=report.horizon,
                ).rows
            )
        decision_result = build_datacenter_ticker_decisions(parsed_rows)
        selected_ticker = datacenter_dashboard_inspector_ticker_dropdown.value
        decisions_by_ticker = {
            decision.ticker: decision for decision in decision_result.decisions
        }
        if (
            decision_result.decisions
            and (not selected_ticker or selected_ticker not in decisions_by_ticker)
        ):
            selected_ticker = decision_result.decisions[0].ticker
        selected_decision = next(
            (
                decision
                for decision in decision_result.decisions
                if decision.ticker == selected_ticker
            ),
            None,
        )
        inspector_view = (
            build_datacenter_ticker_inspector_view(
                decision=selected_decision,
                rows=parsed_rows,
            )
            if selected_decision is not None
            else None
        )
        populate_datacenter_dashboard_inspector(
            inspector_view=inspector_view,
            inspector_ticker_dropdown=datacenter_dashboard_inspector_ticker_dropdown,
            decision_result=decision_result,
            selected_ticker=selected_ticker,
            action_field=datacenter_dashboard_inspector_action_field,
            conflict_detected_field=datacenter_dashboard_conflict_detected_field,
            pullback_validity_field=datacenter_dashboard_pullback_validity_field,
            pullback_reason_field=datacenter_dashboard_pullback_reason_field,
            supporting_signals_field=datacenter_dashboard_supporting_signals_field,
            conflicting_signals_field=datacenter_dashboard_conflicting_signals_field,
            override_explanation_field=datacenter_dashboard_override_explanation_field,
        )
        page.update()

    def on_datacenter_dashboard_refresh(_e) -> None:
        print("DEBUG dashboard_refresh_clicked=1")
        print(
            f"DEBUG dashboard_reports_dir={datacenter_dashboard_reports_dir_field.value}"
        )
        refresh_result = refresh_datacenter_dashboard_view()
        print("DEBUG dashboard_refresh_completed=1")
        print(f"DEBUG dashboard_found_reports={refresh_result['found_reports']}")
        print(f"DEBUG dashboard_decision_total={refresh_result['decision_total']}")

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
                "datacenter_pipeline.status="
                f"{latest_summary.get('datacenter_pipeline_status', '')}",
                "datacenter_pipeline.market="
                f"{latest_summary.get('datacenter_pipeline_market', '')}",
                "datacenter_pipeline.audit_validation_status="
                f"{latest_summary.get('datacenter_pipeline_audit_validation_status', '')}",
                "datacenter_pipeline.log_path="
                f"{latest_summary.get('datacenter_pipeline_log_path', '')}",
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
                technical_relevance_enabled=bool(technical_relevance_checkbox.value),
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

    save_config_button = ft.ElevatedButton("Save config", on_click=on_save_config)
    reload_config_button = ft.ElevatedButton("Reload config", on_click=on_reload_config)
    run_now_button = ft.ElevatedButton("Run now", on_click=on_run_now)
    refresh_logs_button = ft.ElevatedButton("Refresh logs", on_click=on_refresh_logs)

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

    datacenter_dashboard_reports_dir_field = ft.TextField(
        label="Reports directory",
        value=DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR,
    )
    datacenter_dashboard_report_date_field = ft.TextField(
        label="Report date",
        hint_text="YYYY-MM-DD",
    )
    datacenter_dashboard_available_dates_text = ft.Text(
        "",
        size=13,
        color="#4b5563",
    )
    datacenter_dashboard_output_field = ft.TextField(
        label="Output path (optional)",
    )
    datacenter_dashboard_status_field = ft.TextField(
        label="Status",
        value="",
        multiline=True,
        min_lines=10,
        max_lines=16,
        read_only=True,
    )
    datacenter_dashboard_generate_button = ft.ElevatedButton("Generate HTML Dashboard")
    datacenter_dashboard_open_button = ft.ElevatedButton(
        "Open Last Generated Dashboard",
        disabled=True,
    )

    def _dashboard_effective_output_path() -> str:
        report_date_value = datacenter_dashboard_report_date_field.value.strip() or None
        output_value = datacenter_dashboard_output_field.value.strip() or None
        return str(
            resolve_dashboard_html_output_path(
                reports_dir=datacenter_dashboard_reports_dir_field.value.strip() or DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR,
                output=output_value,
                report_date=report_date_value,
            )
        )

    def _refresh_datacenter_dashboard_available_dates(*, preserve_user_value: bool) -> None:
        reports_dir_value = datacenter_dashboard_reports_dir_field.value.strip() or DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR
        available_dates = list_datacenter_report_dates(reports_dir_value, limit=5)
        current_value = datacenter_dashboard_report_date_field.value.strip()
        previous_auto_value = getattr(page, "datacenter_dashboard_auto_report_date", "")
        newest_date = available_dates[0] if available_dates else ""
        if newest_date and (
            not current_value
            or (preserve_user_value and current_value == previous_auto_value)
            or not preserve_user_value
        ):
            datacenter_dashboard_report_date_field.value = newest_date
            current_value = newest_date
        elif not available_dates and not preserve_user_value:
            datacenter_dashboard_report_date_field.value = ""
            current_value = ""
        page.datacenter_dashboard_auto_report_date = newest_date
        if available_dates:
            datacenter_dashboard_available_dates_text.value = (
                "Available report dates (latest 5): " + ", ".join(available_dates)
            )
        else:
            datacenter_dashboard_available_dates_text.value = "Available report dates (latest 5): none found"

    def on_datacenter_dashboard_reports_dir_change(e) -> None:
        _refresh_datacenter_dashboard_available_dates(preserve_user_value=True)
        datacenter_dashboard_status_field.value = "\n".join(
            [
                f"reports_dir={datacenter_dashboard_reports_dir_field.value.strip() or DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR}",
                f"report_date={datacenter_dashboard_report_date_field.value.strip() or 'newest'}",
                f"output={_dashboard_effective_output_path()}",
                "readiness=MISSING",
                "found_reports=0",
                "missing_reports=0",
                "decision_total=0",
                "candidate_pullback_rows=0",
                "generate_status=SKIPPED",
                "open_status=SKIPPED",
            ]
        )
        page.update()

    def _set_datacenter_dashboard_status(lines: list[str]) -> None:
        datacenter_dashboard_status_field.value = "\n".join(lines)
        page.update()

    def _show_dashboard_missing_report_error(report_date_value: str, reports_dir_value: str) -> None:
        _set_datacenter_dashboard_status(
            [
                f"ERROR no datacenter reports found for report_date={report_date_value} in {reports_dir_value}. Run the reports from the Datacenter tab first.",
                f"reports_dir={reports_dir_value}",
                f"report_date={report_date_value}",
                f"output={_dashboard_effective_output_path()}",
                "generate_status=FAILED",
                "open_status=SKIPPED",
                "Expected filename examples:",
                f"datacenter_daily_{report_date_value}_*.md",
                f"datacenter_rolling_2_{report_date_value}_*.md",
                f"datacenter_rolling_5_{report_date_value}_*.md",
                f"datacenter_rolling_30_{report_date_value}_*.md",
            ]
        )

    def on_datacenter_dashboard_generate(e) -> None:
        reports_dir_value = datacenter_dashboard_reports_dir_field.value.strip() or DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR
        report_date_value = datacenter_dashboard_report_date_field.value.strip()
        output_value = datacenter_dashboard_output_field.value.strip() or None
        if report_date_value and not _DATACENTER_DASHBOARD_REPORT_DATE_RE.match(report_date_value):
            _set_datacenter_dashboard_status(
                [
                    "ERROR invalid report date, expected YYYY-MM-DD",
                    f"reports_dir={reports_dir_value}",
                    f"report_date={report_date_value}",
                    f"output={_dashboard_effective_output_path()}",
                    "generate_status=FAILED",
                    "open_status=SKIPPED",
                ]
            )
            return

        try:
            result = generate_datacenter_dashboard_html_file(
                reports_dir=reports_dir_value,
                output=output_value,
                report_date=report_date_value or None,
            )
        except FileNotFoundError:
            if report_date_value:
                _show_dashboard_missing_report_error(report_date_value, reports_dir_value)
                return
            _set_datacenter_dashboard_status(
                [
                    "ERROR no datacenter reports found for newest mode in the selected reports directory.",
                    f"reports_dir={reports_dir_value}",
                    "report_date=newest",
                    f"output={_dashboard_effective_output_path()}",
                    "generate_status=FAILED",
                    "open_status=SKIPPED",
                ]
            )
            return
        except ValueError as exc:
            _set_datacenter_dashboard_status(
                [
                    f"ERROR {exc}",
                    f"reports_dir={reports_dir_value}",
                    f"report_date={report_date_value or 'newest'}",
                    f"output={_dashboard_effective_output_path()}",
                    "generate_status=FAILED",
                    "open_status=SKIPPED",
                ]
            )
            return
        except Exception as exc:
            _set_datacenter_dashboard_status(
                [
                    f"ERROR {exc}",
                    f"reports_dir={reports_dir_value}",
                    f"report_date={report_date_value or 'newest'}",
                    f"output={_dashboard_effective_output_path()}",
                    "generate_status=FAILED",
                    "open_status=SKIPPED",
                ]
            )
            return

        open_result = open_datacenter_dashboard_html(result.output_path)
        page.datacenter_dashboard_last_output_path = result.output_path
        datacenter_dashboard_output_field.value = result.output_path
        datacenter_dashboard_open_button.disabled = False
        status_lines = [
            f"reports_dir={reports_dir_value}",
            f"report_date={result.report_date}",
            f"output={result.output_path}",
            f"readiness={result.readiness}",
            f"found_reports={result.found_reports}",
            f"missing_reports={result.missing_reports}",
            f"decision_total={result.decision_total}",
            f"candidate_pullback_rows={result.candidate_pullback_rows}",
            "generate_status=OK",
            f"open_status={open_result['open_status']}",
            f"opener={open_result['opener']}",
            f"html_output_windows={open_result['html_output_windows']}",
            f"html_file_url={open_result['html_file_url']}",
        ]
        if result.readiness == "PARTIAL" and report_date_value:
            status_lines.append(f"WARNING partial reports found for report_date={report_date_value}")
        manual_lines = open_result.get("manual_lines") or []
        _set_datacenter_dashboard_status(status_lines + list(manual_lines))

    def on_datacenter_dashboard_open_last(e) -> None:
        last_output_path = getattr(page, "datacenter_dashboard_last_output_path", None)
        if not last_output_path:
            _set_datacenter_dashboard_status(
                [
                    "ERROR no generated dashboard available yet.",
                    "generate_status=FAILED",
                    "open_status=SKIPPED",
                ]
            )
            return
        open_result = open_datacenter_dashboard_html(last_output_path)
        status_lines = [
            f"reports_dir={datacenter_dashboard_reports_dir_field.value.strip() or DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR}",
            f"report_date={datacenter_dashboard_report_date_field.value.strip() or 'newest'}",
            f"output={last_output_path}",
            "generate_status=OK",
            f"open_status={open_result['open_status']}",
            f"opener={open_result['opener']}",
            f"html_output_windows={open_result['html_output_windows']}",
            f"html_file_url={open_result['html_file_url']}",
        ]
        _set_datacenter_dashboard_status(status_lines + list(open_result.get("manual_lines") or []))

    datacenter_dashboard_generate_button.on_click = on_datacenter_dashboard_generate
    datacenter_dashboard_open_button.on_click = on_datacenter_dashboard_open_last
    datacenter_dashboard_reports_dir_field.on_change = on_datacenter_dashboard_reports_dir_change
    datacenter_dashboard_content = ft.Column(
        controls=[
            ft.Text("Datacenter Dashboard", size=24, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Generate and open the static HTML dashboard from existing datacenter reports."
            ),
            ft.Text(
                "If reports for the selected date are missing, run the datacenter reports first from the Datacenter tab."
            ),
            datacenter_dashboard_reports_dir_field,
            datacenter_dashboard_available_dates_text,
            datacenter_dashboard_report_date_field,
            datacenter_dashboard_output_field,
            ft.Row(
                [
                    datacenter_dashboard_generate_button,
                    datacenter_dashboard_open_button,
                ],
                wrap=True,
            ),
            ft.Text("Status", size=16, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=datacenter_dashboard_status_field,
                bgcolor="#f5f5f5",
                border=ft.border.all(1, "#d0d0d0"),
                border_radius=4,
                padding=8,
                height=260,
            ),
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    page.datacenter_dashboard_last_output_path = None
    page.datacenter_dashboard_auto_report_date = ""
    _refresh_datacenter_dashboard_available_dates(preserve_user_value=False)
    datacenter_dashboard_status_field.value = "\n".join(
        [
            f"reports_dir={DEFAULT_DATACENTER_DASHBOARD_REPORTS_DIR}",
            f"report_date={datacenter_dashboard_report_date_field.value.strip() or 'newest'}",
            f"output={_dashboard_effective_output_path()}",
            "readiness=MISSING",
            "found_reports=0",
            "missing_reports=0",
            "decision_total=0",
            "candidate_pullback_rows=0",
            "generate_status=SKIPPED",
            "open_status=SKIPPED",
        ]
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
    page.summary_field = summary_field
    page.logs_column = logs_column
    page.technical_relevance_checkbox = technical_relevance_checkbox
    page.save_config_button = save_config_button
    page.reload_config_button = reload_config_button
    page.datacenter_content = datacenter_content
    page.datacenter_dashboard_reports_dir_field = datacenter_dashboard_reports_dir_field
    page.datacenter_dashboard_report_date_field = datacenter_dashboard_report_date_field
    page.datacenter_dashboard_available_dates_text = datacenter_dashboard_available_dates_text
    page.datacenter_dashboard_output_field = datacenter_dashboard_output_field
    page.datacenter_dashboard_status_field = datacenter_dashboard_status_field
    page.datacenter_dashboard_generate_button = datacenter_dashboard_generate_button
    page.datacenter_dashboard_open_button = datacenter_dashboard_open_button
    page.datacenter_dashboard_content = datacenter_dashboard_content

    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(text="Scheduler", content=scheduler_content),
            ft.Tab(text="Datacenter", content=datacenter_content),
            ft.Tab(text="Datacenter Dashboard", content=datacenter_dashboard_content),
        ],
        expand=1,
    )
    page.datacenter_tabs = tabs
    page.add(tabs)
    page.update()


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config
    port = args.port
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Missing scheduler config: {config_path}")
    initial_config = read_scheduler_config(config_path)

    app_view = ft.WEB_BROWSER if hasattr(ft, "WEB_BROWSER") else ft.AppView.WEB_BROWSER
    ft.app(
        target=lambda page: run_app(page, config_path),
        view=app_view,
        port=port,
        assets_dir=initial_config.log_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
