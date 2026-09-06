from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft

from rawcandle.fundamentals.snapshot.ui_service import (
    FundamentalsSnapshotUIService,
    FundamentalsUIResult,
)


LOGGER = logging.getLogger(__name__)
FUNDAMENTALS_ROUTE = "/fundamentals"


@dataclass(frozen=True)
class FundamentalsPageControls:
    content: Any
    ticker_field: Any
    report_date_field: Any
    overwrite_checkbox: Any
    generate_button: Any
    status_field: Any
    recent_reports_column: Any


def application_date(timezone_name: str) -> str:
    return datetime.now(ZoneInfo(timezone_name)).date().isoformat()


def _result_text(result: FundamentalsUIResult) -> str:
    lines = [f"Status: {result.status}", result.message]
    for label, value in (
        ("Ticker", result.ticker),
        ("Report date", result.report_date),
        ("Filename", result.filename),
        ("Path", result.output_path),
        ("Publication", result.publication_status),
    ):
        if value:
            lines.append(f"{label}: {value}")
    if result.report_content_fingerprint:
        lines.append(
            "Fingerprint: " + result.report_content_fingerprint[:16] + "..."
        )
    return "\n".join(lines)


def build_fundamentals_page(
    *,
    page: Any,
    timezone_name: str,
    service: FundamentalsSnapshotUIService | None = None,
) -> FundamentalsPageControls:
    report_service = service or FundamentalsSnapshotUIService()
    ticker_field = ft.TextField(
        label="Ticker",
        max_length=32,
        width=260,
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
        min_lines=4,
        max_lines=9,
    )
    recent_reports_column = ft.Column(spacing=6)

    def refresh_recent_reports() -> None:
        reports = report_service.recent_reports(limit=10)
        recent_reports_column.controls = [
            ft.Row(
                [
                    ft.Text(report.ticker, width=90),
                    ft.Text(report.report_date, width=120),
                    ft.Text(report.filename, expand=True),
                    ft.Text(report.modified_at_utc, width=230),
                ]
            )
            for report in reports
        ] or [ft.Text("No generated company reports found.")]

    def on_generate(_event: Any) -> None:
        if generate_button.disabled:
            return
        generate_button.disabled = True
        if hasattr(page, "update"):
            page.update()
        try:
            result = report_service.generate(
                ticker_input=ticker_field.value,
                report_date_input=report_date_field.value,
                overwrite=bool(overwrite_checkbox.value),
            )
            if result.ticker:
                ticker_field.value = result.ticker
            status_field.value = _result_text(result)
            if result.status in {"GENERATED", "NO_CHANGE"}:
                refresh_recent_reports()
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
            ft.Text("Recent reports", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(
                [
                    ft.Text("Ticker", width=90, weight=ft.FontWeight.BOLD),
                    ft.Text("Report date", width=120, weight=ft.FontWeight.BOLD),
                    ft.Text("Filename", expand=True, weight=ft.FontWeight.BOLD),
                    ft.Text("Modified (UTC)", width=230, weight=ft.FontWeight.BOLD),
                ]
            ),
            recent_reports_column,
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
        recent_reports_column=recent_reports_column,
    )
