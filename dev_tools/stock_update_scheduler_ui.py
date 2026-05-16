from __future__ import annotations

import argparse
import inspect
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import flet as ft

from rawcandle.scheduler.config import (
    StockUpdateSchedulerConfig,
    read_scheduler_config,
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
    r"^stock_update_(omxh|omxs|usa)_(\d{8}T\d{6}Z)\.(txt|log)$"
)
_STATUS_OK_COLOR = "#43A047"
_STATUS_WARNING_COLOR = "#EF6C00"
_STATUS_ERROR_COLOR = "#E53935"
SCHEDULER_UI_PORT = 8555


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


def list_scheduler_log_files(log_dir: str, limit: int = 20) -> List[Dict[str, Any]]:
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
                "type": entry_type,
                "text_openable": entry_type == "market_log",
            }
        )

    entries.sort(key=lambda item: item["timestamp"], reverse=True)
    return entries[:limit]


def build_text_log_browser_url(path: str) -> str:
    return f"/{quote(Path(path).name)}"


def launch_browser_url(page: ft.Page, url: str) -> None:
    result = page.launch_url(url)
    if inspect.isawaitable(result):
        async def _await_launch() -> None:
            await result

        page.run_task(_await_launch)


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
    logs_column = ft.Column(spacing=8)

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
            write_scheduler_config(config_path, config)
            _set_status(status_field, f"Config saved: {config_path}", _STATUS_OK_COLOR)
            update_ui_from_config(config)
            refresh_logs_view(config.log_dir)
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

    initial_config = _load_config_or_raise(config_path)
    update_ui_from_config(initial_config)
    refresh_logs_view(initial_config.log_dir)
    skip_next_run_button.on_click = on_skip_next_run
    cancel_skip_next_run_button.on_click = on_cancel_skip_next_run

    page.add(
        ft.Column(
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
                ft.Text("Recent scheduler logs", size=18, weight=ft.FontWeight.BOLD),
                logs_column,
            ],
            spacing=12,
            expand=True,
        )
    )
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
