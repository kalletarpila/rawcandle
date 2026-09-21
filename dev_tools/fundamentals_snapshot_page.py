from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import flet as ft

from dev_tools.deferred_ui import DeferredLoadController
from rawcandle.fundamentals.snapshot.ui_service import (
    FundamentalsBatchResult,
    FundamentalsSnapshotUIService,
    FundamentalsUIResult,
    validate_report_filename,
)


LOGGER = logging.getLogger(__name__)
FUNDAMENTALS_ROUTE = "/fundamentals"
FUNDAMENTALS_DOWNLOAD_ROUTE = "/fundamentals/reports"


@dataclass(frozen=True)
class FundamentalsPageControls:
    content: Any
    ticker_field: Any
    report_date_field: Any
    overwrite_checkbox: Any
    generate_button: Any
    status_field: Any
    batch_results_column: Any
    recent_reports_column: Any
    reports_refresh_button: Any
    reports_show_more_button: Any
    activate: Any
    reports_loader: Any


def application_date(timezone_name: str) -> str:
    return datetime.now(ZoneInfo(timezone_name)).date().isoformat()


def result_display_status(result: FundamentalsUIResult) -> str:
    return result.publication_status or result.status


def report_download_url(filename: str) -> str:
    _ticker, _report_date, validated = validate_report_filename(filename)
    return f"{FUNDAMENTALS_DOWNLOAD_ROUTE}/{quote(validated, safe='')}"


def _launch_browser_url(page: Any, url: str) -> None:
    result = page.launch_url(url)
    if inspect.isawaitable(result):
        async def _await_launch() -> None:
            await result

        page.run_task(_await_launch)


def _batch_summary_text(batch: FundamentalsBatchResult) -> str:
    summary = batch.summary
    return (
        f"Status: {batch.status}\n{batch.message}\n"
        f"Requested: {summary.requested} | Created: {summary.created} | "
        f"Overwritten: {summary.overwritten} | Unchanged: {summary.unchanged} | "
        f"Not generated: {summary.not_generated}"
    )


def build_fundamentals_page(
    *,
    page: Any,
    timezone_name: str,
    service: FundamentalsSnapshotUIService | None = None,
    defer_initial_load: bool = False,
) -> FundamentalsPageControls:
    report_service = service or FundamentalsSnapshotUIService()
    ticker_field = ft.TextField(
        label="Tickers - separate multiple tickers with commas or spaces",
        hint_text="NVDA, VRT CRMD",
        max_length=512,
        width=520,
        multiline=True,
        min_lines=1,
        max_lines=3,
        capitalization=ft.TextCapitalization.CHARACTERS,
        autocorrect=False,
    )
    report_date_field = ft.TextField(
        label="Report date",
        value=application_date(timezone_name),
        hint_text="YYYY-MM-DD",
        width=220,
    )
    overwrite_checkbox = ft.Checkbox(
        label="Replace an existing different report",
        value=False,
    )
    status_field = ft.TextField(
        label="Result",
        value="No report generated in this session.",
        read_only=True,
        multiline=True,
        min_lines=3,
        max_lines=5,
    )
    batch_results_column = ft.Column(spacing=6)
    recent_reports_column = ft.Column(spacing=6)
    recent_reports: list[Any] | None = None
    recent_reports_limit = 8

    def download_button(filename: str) -> Any:
        return ft.IconButton(
            icon=ft.Icons.DOWNLOAD,
            tooltip=f"Download {filename}",
            on_click=lambda _event: _launch_browser_url(
                page, report_download_url(filename)
            ),
        )

    def result_row(result: FundamentalsUIResult) -> Any:
        controls = [
            ft.Text(result.ticker or "-", width=90),
            ft.Text(result_display_status(result), width=150),
            ft.Text(result.filename or "-", expand=True),
            ft.Text(result.message, expand=True),
        ]
        downloadable = result.filename and result_display_status(result) in {
            "CREATED",
            "OVERWRITTEN",
            "NO_CHANGE",
            "OVERWRITE_REQUIRED",
        }
        controls.append(download_button(result.filename) if downloadable else ft.Container(width=48))
        return ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def load_recent_reports() -> list[Any]:
        nonlocal recent_reports
        if recent_reports is None:
            requested = 1_000_000 if defer_initial_load else 10
            recent_reports = list(report_service.recent_reports(limit=requested))
        return recent_reports[:recent_reports_limit]

    def apply_recent_reports(reports: list[Any]) -> None:
        recent_reports_column.controls = [
            ft.Row(
                [
                    ft.Text(report.ticker, width=90),
                    ft.Text(report.report_date, width=120),
                    ft.Text(report.filename, expand=True),
                    ft.Text(report.modified_at_utc, width=230),
                    download_button(report.filename),
                ]
            )
            for report in reports
        ] or [ft.Text("No generated company reports found.")]
        reports_show_more_button.visible = bool(
            recent_reports is not None and recent_reports_limit < len(recent_reports)
        )
        reports_show_more_button.disabled = False

    def reports_failed(_exc: Exception) -> None:
        recent_reports_column.controls = [ft.Text("Recent reports could not be loaded.")]
        reports_show_more_button.visible = False
        reports_show_more_button.disabled = False

    def reports_loading() -> None:
        recent_reports_column.controls = [ft.Text("Loading recent reports...")]
        reports_show_more_button.disabled = True

    reports_loader = DeferredLoadController(
        page=page,
        load=load_recent_reports,
        apply=apply_recent_reports,
        loading=reports_loading,
        failed=reports_failed,
    )

    def refresh_recent_reports(*, force: bool = False) -> None:
        nonlocal recent_reports, recent_reports_limit
        if force:
            recent_reports = None
            recent_reports_limit = 8
            reports_loader.invalidate()
        if defer_initial_load:
            reports_loader.start(force=force)
        else:
            try:
                apply_recent_reports(load_recent_reports())
            except Exception as exc:
                reports_failed(exc)

    def show_more_reports(_event: Any) -> None:
        nonlocal recent_reports_limit
        recent_reports_limit += 8
        if defer_initial_load and recent_reports is not None:
            apply_recent_reports(recent_reports[:recent_reports_limit])
            page.update()
        elif defer_initial_load:
            reports_loader.start()
        else:
            refresh_recent_reports()

    reports_show_more_button = ft.TextButton(
        "Show more",
        icon=ft.Icons.EXPAND_MORE,
        on_click=show_more_reports,
        visible=False,
    )
    reports_refresh_button = ft.IconButton(
        icon=ft.Icons.REFRESH,
        tooltip="Refresh recent reports",
        on_click=lambda _event: refresh_recent_reports(force=True),
    )

    def on_generate(_event: Any) -> None:
        if generate_button.disabled:
            return
        generate_button.disabled = True
        if hasattr(page, "update"):
            page.update()
        try:
            batch = report_service.generate_batch(
                ticker_input=ticker_field.value,
                report_date_input=report_date_field.value,
                overwrite=bool(overwrite_checkbox.value),
            )
            status_field.value = _batch_summary_text(batch)
            batch_results_column.controls = [result_row(result) for result in batch.results]
            if any(
                result_display_status(result) in {"CREATED", "OVERWRITTEN", "NO_CHANGE"}
                for result in batch.results
            ):
                refresh_recent_reports(force=True)
        except Exception:
            LOGGER.exception("Unexpected Fundamentals UI generation failure")
            status_field.value = (
                "Status: FAILED\nReport generation failed. "
                "See the application log for details."
            )
        finally:
            generate_button.disabled = False
            if hasattr(page, "update"):
                page.update()

    generate_button = ft.ElevatedButton(
        "Generate report",
        icon=ft.Icons.DESCRIPTION,
        on_click=on_generate,
    )
    ticker_field.on_submit = on_generate
    if not defer_initial_load:
        refresh_recent_reports()

    content = ft.Column(
        [
            ft.Text("Fundamentals", size=24, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Generate the latest currently revised company fundamentals "
                "snapshot as a Markdown report."
            ),
            ft.Row([ticker_field, report_date_field], wrap=True, spacing=12),
            overwrite_checkbox,
            generate_button,
            status_field,
            ft.Divider(),
            ft.Text("Batch results", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(
                [
                    ft.Text("Ticker", width=90, weight=ft.FontWeight.BOLD),
                    ft.Text("Status", width=150, weight=ft.FontWeight.BOLD),
                    ft.Text("Filename", expand=True, weight=ft.FontWeight.BOLD),
                    ft.Text("Message", expand=True, weight=ft.FontWeight.BOLD),
                    ft.Container(width=48),
                ]
            ),
            batch_results_column,
            ft.Divider(),
            ft.Row(
                [
                    ft.Text("Recent reports", size=18, weight=ft.FontWeight.BOLD),
                    reports_refresh_button,
                ]
            ),
            ft.Row(
                [
                    ft.Text("Ticker", width=90, weight=ft.FontWeight.BOLD),
                    ft.Text("Report date", width=120, weight=ft.FontWeight.BOLD),
                    ft.Text("Filename", expand=True, weight=ft.FontWeight.BOLD),
                    ft.Text("Modified (UTC)", width=230, weight=ft.FontWeight.BOLD),
                    ft.Container(width=48),
                ]
            ),
            recent_reports_column,
            reports_show_more_button,
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
    return FundamentalsPageControls(
        content=content,
        ticker_field=ticker_field,
        report_date_field=report_date_field,
        overwrite_checkbox=overwrite_checkbox,
        generate_button=generate_button,
        status_field=status_field,
        batch_results_column=batch_results_column,
        recent_reports_column=recent_reports_column,
        reports_refresh_button=reports_refresh_button,
        reports_show_more_button=reports_show_more_button,
        activate=lambda: reports_loader.start(),
        reports_loader=reports_loader,
    )
