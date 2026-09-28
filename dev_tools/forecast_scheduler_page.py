from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import flet as ft

from rawcandle.forecasts.scheduler_config import (
    DEFAULT_FORECAST_SCHEDULER_CONFIG,
    ForecastSchedulerConfig,
    read_forecast_scheduler_config,
    validate_forecast_scheduler_config,
)
from rawcandle.forecasts.ui_service import (
    FORECAST_LOG_DOWNLOAD_ROUTE,
    forecast_skip_label,
    list_forecast_logs,
    read_forecast_latest_summary,
    read_forecast_timer_status,
    save_forecast_config_and_sync_timer,
    set_forecast_skip,
    start_forecast_run_now,
)


FORECAST_ROUTE = "/forecast"


@dataclass
class ForecastSchedulerControls:
    content: Any
    activate: Callable[[], None]
    forecasts_db_field: Any
    fundamentals_db_field: Any
    log_dir_field: Any
    timezone_field: Any
    run_time_field: Any
    save_button: Any
    reload_button: Any
    run_now_button: Any
    skip_button: Any
    cancel_skip_button: Any
    refresh_logs_button: Any
    status_field: Any
    summary_field: Any
    timer_status_field: Any
    running_status_text: Any
    skip_status_text: Any
    logs_column: Any


def _summary_text(summary: dict[str, Any]) -> str:
    acquisition = summary.get("acquisition", {})
    lines = [
        f"overall_status={summary.get('overall_status', '')}",
        f"run_id={summary.get('run_id', '')}",
        f"started_at={summary.get('started_at', '')}",
        f"completed_at={summary.get('completed_at', '')}",
        f"elapsed_seconds={summary.get('elapsed_seconds', '')}",
        f"universe_version={summary.get('universe_version', '')}",
        f"symbols_selected={summary.get('symbols_selected', 0)}",
        f"requests_attempted={summary.get('requests_attempted', 0)}",
        f"progress={summary.get('persisted_fetches', 0)}/{summary.get('expected_fetches', 0)}",
    ]
    for status in (
        "SUCCESS_CHANGED", "SUCCESS_UNCHANGED", "VALID_NO_DATA",
        "PROVIDER_SYMBOL_UNAVAILABLE", "TRANSIENT_FAILURE", "RATE_LIMITED",
        "MALFORMED_OR_SCHEMA_MISMATCH",
    ):
        lines.append(f"{status}={int(acquisition.get(status, 0))}")
    lines.extend([
        f"identity_resolved={summary.get('identity_resolved', 0)}",
        f"identity_ambiguous={summary.get('identity_ambiguous', 0)}",
        f"identity_unresolved={summary.get('identity_unresolved', 0)}",
        f"fiscal_linked={summary.get('fiscal_linked', 0)}",
        f"fiscal_ambiguous={summary.get('fiscal_ambiguous', 0)}",
        f"fiscal_unresolved={summary.get('fiscal_unresolved', 0)}",
        f"retries={summary.get('retries', 0)}",
        f"unknown_schema_drift={summary.get('unknown_schema_drift', 0)}",
        f"rate_limits={summary.get('rate_limits', 0)}",
        f"quick_check={summary.get('quick_check', '')}",
        f"schema_version={summary.get('schema_version', '')}",
        f"db_size_bytes={summary.get('db_size_bytes', 0)}",
        f"snapshot_count={summary.get('snapshot_count', 0)}",
        f"raw_evidence_bytes={summary.get('raw_evidence_bytes', 0)}",
    ])
    return "\n".join(lines)


def _timer_text(timer: dict[str, Any]) -> str:
    return "\n".join(
        f"{key}={timer.get(key, '')}"
        for key in (
            "installed", "enabled", "active", "status_summary",
            "service_status", "on_calendar", "timezone", "timer_path",
            "service_path", "next_run_local", "timeout_seconds", "command", "error",
        )
    )


def build_forecast_scheduler_page(
    page: Any,
    *,
    config_path: str | Path = DEFAULT_FORECAST_SCHEDULER_CONFIG,
    defer_initial_load: bool = False,
) -> ForecastSchedulerControls:
    current = read_forecast_scheduler_config(config_path)
    forecasts_db_field = ft.TextField(
        label="forecasts_db_path", value=current.forecasts_db_path
    )
    fundamentals_db_field = ft.TextField(
        label="fundamentals_db_path", value=current.fundamentals_db_path
    )
    log_dir_field = ft.TextField(label="log_dir", value=current.log_dir)
    timezone_field = ft.TextField(label="timezone", value=current.timezone)
    run_time_field = ft.TextField(label="run_time", value=current.run_time)
    status_field = ft.TextField(label="Status", read_only=True, multiline=True)
    summary_field = ft.TextField(
        label="Latest summary", read_only=True, multiline=True
    )
    timer_status_field = ft.TextField(
        label="Forecast Timer status", read_only=True, multiline=True
    )
    running_status_text = ft.Text("Scheduler status: UNKNOWN")
    skip_status_text = ft.Text(forecast_skip_label(current))
    logs_column = ft.Column(spacing=8)

    def config_from_fields() -> ForecastSchedulerConfig:
        saved = read_forecast_scheduler_config(config_path)
        return validate_forecast_scheduler_config(ForecastSchedulerConfig(
            forecasts_db_path=str(forecasts_db_field.value or ""),
            fundamentals_db_path=str(fundamentals_db_field.value or ""),
            log_dir=str(log_dir_field.value or ""),
            timezone=str(timezone_field.value or ""),
            run_time=str(run_time_field.value or ""),
            skip_next_run=saved.skip_next_run,
        ))

    def apply_config(config: ForecastSchedulerConfig) -> None:
        forecasts_db_field.value = config.forecasts_db_path
        fundamentals_db_field.value = config.fundamentals_db_path
        log_dir_field.value = config.log_dir
        timezone_field.value = config.timezone
        run_time_field.value = config.run_time
        skip_status_text.value = forecast_skip_label(config)
        skip_button.disabled = config.skip_next_run
        cancel_skip_button.disabled = not config.skip_next_run

    def log_url(filename: str, *, download: bool) -> str:
        return (
            f"{FORECAST_LOG_DOWNLOAD_ROUTE}/{quote(filename)}"
            f"?download={'true' if download else 'false'}"
        )

    def refresh() -> None:
        config = read_forecast_scheduler_config(config_path)
        summary = read_forecast_latest_summary(config)
        timer = read_forecast_timer_status()
        summary_field.value = _summary_text(summary)
        timer_status_field.value = _timer_text(timer)
        workflow_running = summary.get("overall_status") == "RUNNING"
        running_status_text.value = (
            "Scheduler status: running" if workflow_running
            else "Scheduler status: not running"
        )
        skip_status_text.value = forecast_skip_label(config)
        skip_button.disabled = config.skip_next_run
        cancel_skip_button.disabled = not config.skip_next_run
        logs_column.controls = []
        logs = list_forecast_logs(config.log_dir)
        if not logs:
            logs_column.controls.append(ft.Text("No forecast log files found."))
        for item in logs:
            logs_column.controls.append(ft.Row([
                ft.Text(
                    f"{item['filename']} [{item['type']}] "
                    f"(size={item['size_bytes']}, modified_at={item['modified_at']})",
                    expand=True,
                ),
                ft.TextButton(
                    "Open", on_click=lambda _e, name=item["filename"]:
                    page.launch_url(log_url(name, download=False)),
                ),
                ft.TextButton(
                    "Download", on_click=lambda _e, name=item["filename"]:
                    page.launch_url(log_url(name, download=True)),
                ),
            ]))
        if hasattr(page, "update"):
            page.update()

    def on_save(_event: Any) -> None:
        try:
            config = config_from_fields()
            result = save_forecast_config_and_sync_timer(
                config_path=config_path, config=config
            )
            apply_config(config)
            status_field.value = str(result["message"])
            refresh()
        except Exception as exc:
            status_field.value = f"Save config failed: {exc}"
            if hasattr(page, "update"):
                page.update()

    def on_reload(_event: Any) -> None:
        try:
            apply_config(read_forecast_scheduler_config(config_path))
            status_field.value = "Forecast config reloaded."
            refresh()
        except Exception as exc:
            status_field.value = f"Reload config failed: {exc}"
            if hasattr(page, "update"):
                page.update()

    def on_run_now(_event: Any) -> None:
        try:
            result = start_forecast_run_now(read_forecast_scheduler_config(config_path))
            status_field.value = (
                "Run now blocked: forecast run is already active."
                if result["status"] == "OVERLAP_ACTIVE"
                else f"Run now started. log={result['log_path']}"
            )
            refresh()
        except Exception as exc:
            status_field.value = f"Run now failed: {exc}"
            if hasattr(page, "update"):
                page.update()

    def on_skip(_event: Any) -> None:
        apply_config(set_forecast_skip(config_path, skip=True))
        status_field.value = "Next scheduled forecast run will be skipped."
        if hasattr(page, "update"):
            page.update()

    def on_cancel_skip(_event: Any) -> None:
        apply_config(set_forecast_skip(config_path, skip=False))
        status_field.value = "Forecast skip cancelled; next scheduled run will run."
        if hasattr(page, "update"):
            page.update()

    save_button = ft.ElevatedButton("Save config", on_click=on_save)
    reload_button = ft.ElevatedButton("Reload config", on_click=on_reload)
    run_now_button = ft.ElevatedButton("Run now", on_click=on_run_now)
    skip_button = ft.ElevatedButton("Skip next run", on_click=on_skip)
    cancel_skip_button = ft.ElevatedButton("Cancel skip", on_click=on_cancel_skip)
    refresh_logs_button = ft.ElevatedButton("Refresh logs", on_click=lambda _e: refresh())
    apply_config(current)

    content = ft.Column(
        [
            ft.Text("CONFIGURATION", weight=ft.FontWeight.BOLD),
            forecasts_db_field,
            fundamentals_db_field,
            log_dir_field,
            timezone_field,
            run_time_field,
            ft.Text("Universe: Full bounded operational universe"),
            ft.Row([save_button, reload_button]),
            ft.Row([run_now_button, skip_button, cancel_skip_button, refresh_logs_button]),
            running_status_text,
            skip_status_text,
            status_field,
            summary_field,
            timer_status_field,
            ft.Text("Logs", weight=ft.FontWeight.BOLD),
            logs_column,
        ],
        spacing=10,
    )
    controls = ForecastSchedulerControls(
        content=content, activate=refresh,
        forecasts_db_field=forecasts_db_field,
        fundamentals_db_field=fundamentals_db_field,
        log_dir_field=log_dir_field,
        timezone_field=timezone_field,
        run_time_field=run_time_field,
        save_button=save_button,
        reload_button=reload_button,
        run_now_button=run_now_button,
        skip_button=skip_button,
        cancel_skip_button=cancel_skip_button,
        refresh_logs_button=refresh_logs_button,
        status_field=status_field,
        summary_field=summary_field,
        timer_status_field=timer_status_field,
        running_status_text=running_status_text,
        skip_status_text=skip_status_text,
        logs_column=logs_column,
    )
    if not defer_initial_load:
        refresh()
    return controls
