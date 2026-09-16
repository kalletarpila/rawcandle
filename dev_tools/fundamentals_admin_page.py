from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import flet as ft

from rawcandle.fundamentals.admin.operation_report import OPERATION_REPORT_NAME
from rawcandle.fundamentals.admin.ui_service import (
    AdminUIRunResult,
    FundamentalsAdminUIService,
)


LOGGER = logging.getLogger(__name__)
FUNDAMENTALS_ADMIN_ROUTE = "/fundamentals/admin"
FUNDAMENTALS_ADMIN_DOWNLOAD_ROUTE = "/fundamentals/admin/reports"


@dataclass(frozen=True)
class FundamentalsAdminPageControls:
    content: Any
    operation_dropdown: Any
    tickers_field: Any
    market_field: Any
    taxonomy_domain_dropdown: Any
    candidate_path_field: Any
    candidate_version_field: Any
    network_allowed_checkbox: Any
    production_preview_checkbox: Any
    preview_button: Any
    copy_apply_button: Any
    production_apply_button: Any
    preview_payload_field: Any
    preview_fingerprint_field: Any
    production_confirmation_field: Any
    status_field: Any
    summary_column: Any
    progress_field: Any
    history_column: Any


def admin_report_download_url(run_id: str) -> str:
    safe_run_id = quote(str(run_id), safe="")
    safe_name = quote(OPERATION_REPORT_NAME, safe="")
    return f"{FUNDAMENTALS_ADMIN_DOWNLOAD_ROUTE}/{safe_run_id}/{safe_name}"


def _launch_browser_url(page: Any, url: str) -> None:
    result = page.launch_url(url)
    if inspect.isawaitable(result):
        async def _await_launch() -> None:
            await result

        page.run_task(_await_launch)


def _result_text(result: AdminUIRunResult) -> str:
    parts = [f"Status: {result.status}", result.message]
    if result.run_id:
        parts.append(f"Run: {result.run_id}")
    if result.outcome:
        parts.append(f"Outcome: {result.outcome}")
    if result.preview_fingerprint:
        parts.append(f"Preview fingerprint: {result.preview_fingerprint}")
    if result.report_sha256:
        parts.append(f"Operation report sha256: {result.report_sha256}")
    return "\n".join(parts)


def build_fundamentals_admin_page(
    *,
    page: Any,
    service: FundamentalsAdminUIService | None = None,
) -> FundamentalsAdminPageControls:
    admin_service = service or FundamentalsAdminUIService()
    capabilities = {
        item.operation_type: item
        for item in getattr(admin_service, "capabilities", lambda: ())()
    }

    def capability_for_current_operation() -> Any:
        return capabilities.get(operation_dropdown.value or "ADD_TICKERS")

    operation_dropdown = ft.Dropdown(
        label="Operation",
        width=360,
        options=[
            ft.dropdown.Option("ADD_TICKERS", "Add Tickers"),
            ft.dropdown.Option("CHECK_UPDATE_SECTOR_INDUSTRY", "Sector and Industry"),
            ft.dropdown.Option("CHECK_UPDATE_TAXONOMY", "Taxonomy"),
        ],
        value="ADD_TICKERS",
    )
    tickers_field = ft.TextField(
        label="Tickers / scope",
        hint_text="NVDA, VRT or empty for full scan",
        multiline=True,
        min_lines=1,
        max_lines=3,
        width=520,
        capitalization=ft.TextCapitalization.CHARACTERS,
        autocorrect=False,
    )
    market_field = ft.TextField(label="Market", value="usa", width=120)
    taxonomy_domain_dropdown = ft.Dropdown(
        label="Taxonomy",
        width=220,
        options=[
            ft.dropdown.Option("dc_ecosystem", "dc_ecosystem"),
            ft.dropdown.Option("ec_taxonomy", "ec_taxonomy"),
        ],
        value="dc_ecosystem",
    )
    candidate_path_field = ft.TextField(label="Candidate CSV", width=520)
    candidate_version_field = ft.TextField(label="Candidate version", width=260)
    network_allowed_checkbox = ft.Checkbox(label="Allow provider network for preview", value=False)
    production_preview_checkbox = ft.Checkbox(label="Protected production preview", value=False)
    preview_payload_field = ft.TextField(label="Preview payload path", width=620)
    preview_fingerprint_field = ft.TextField(label="Preview fingerprint", width=620)
    production_confirmation_field = ft.TextField(
        label="Production confirmation token",
        password=True,
        can_reveal_password=True,
        width=620,
    )
    status_field = ft.TextField(
        label="Result",
        value="No administration run started in this session.",
        read_only=True,
        multiline=True,
        min_lines=5,
        max_lines=8,
    )
    progress_field = ft.TextField(
        label="Progress",
        value="No active run selected.",
        read_only=True,
        multiline=True,
        min_lines=3,
        max_lines=6,
    )
    summary_column = ft.Column(spacing=4)
    history_column = ft.Column(spacing=6)

    def download_button(run_id: str, *, enabled: bool = True) -> Any:
        if not enabled:
            return ft.Container(width=48)
        return ft.IconButton(
            icon=ft.Icons.DOWNLOAD,
            tooltip="Download operation report",
            on_click=lambda _event: _launch_browser_url(page, admin_report_download_url(run_id)),
        )

    def update_summary(result: AdminUIRunResult) -> None:
        summary_column.controls = [ft.Text(row) for row in result.summary_rows] or [
            ft.Text("No summary rows recorded.")
        ]

    def refresh_history() -> None:
        rows = []
        for item in admin_service.history_entries(limit=12):
            rows.append(
                ft.Row(
                    [
                        ft.Text(item.run_id, width=340),
                        ft.Text(item.operation_type, width=230),
                        ft.Text(item.mode, width=150),
                        ft.Text(item.outcome, width=140),
                        ft.Text(item.status, width=140),
                        download_button(item.run_id, enabled=item.report_available),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        history_column.controls = rows or [ft.Text("No administration runs found.")]

    def progress_callback(event: Any) -> None:
        progress_field.value = (
            f"[{event.get('current_stage_number', '?')}/{event.get('total_declared_stages', '?')}] "
            f"{event.get('current_stage_id', 'UNKNOWN')} - {event.get('stage_state', 'UNKNOWN')}\n"
            f"{event.get('message', '')}"
        )
        if hasattr(page, "update"):
            page.update()

    def apply_result(result: AdminUIRunResult) -> None:
        status_field.value = _result_text(result)
        if result.preview_payload_path:
            preview_payload_field.value = result.preview_payload_path
        if result.preview_fingerprint:
            preview_fingerprint_field.value = result.preview_fingerprint
        update_summary(result)
        refresh_history()

    def apply_capabilities() -> None:
        capability = capability_for_current_operation()
        preview_button.disabled = bool(capability and not capability.preview_enabled)
        copy_apply_button.disabled = bool(capability and not capability.copy_apply_enabled)
        production_apply_button.disabled = bool(capability and not capability.production_apply_enabled)

    def run_guarded(button: Any, fn: Any) -> None:
        if button.disabled:
            return
        button.disabled = True
        if hasattr(page, "update"):
            page.update()
        try:
            apply_result(fn())
        except Exception:
            LOGGER.exception("Fundamentals administration UI run failed")
            status_field.value = "Status: FAILED\nAdministration run failed. See the application log for details."
        finally:
            apply_capabilities()
            if hasattr(page, "update"):
                page.update()

    def on_preview(_event: Any) -> None:
        run_guarded(
            preview_button,
            lambda: admin_service.preview(
                operation_dropdown.value or "ADD_TICKERS",
                raw_inputs=tickers_field.value or "",
                market=market_field.value or "usa",
                taxonomy_domain=taxonomy_domain_dropdown.value or "dc_ecosystem",
                candidate_path=candidate_path_field.value or None,
                candidate_version=candidate_version_field.value or None,
                production_mode=bool(production_preview_checkbox.value),
                network_allowed=bool(network_allowed_checkbox.value),
                progress_callback=progress_callback,
            ),
        )

    def on_copy_apply(_event: Any) -> None:
        run_guarded(
            copy_apply_button,
            lambda: admin_service.copy_apply(
                operation_dropdown.value or "ADD_TICKERS",
                preview_payload_path=preview_payload_field.value or "",
                preview_fingerprint=preview_fingerprint_field.value or "",
                taxonomy_domain=taxonomy_domain_dropdown.value or "dc_ecosystem",
                progress_callback=progress_callback,
            ),
        )

    def on_production_apply(_event: Any) -> None:
        run_guarded(
            production_apply_button,
            lambda: admin_service.production_apply(
                operation_dropdown.value or "ADD_TICKERS",
                preview_payload_path=preview_payload_field.value or "",
                preview_fingerprint=preview_fingerprint_field.value or "",
                confirmation=production_confirmation_field.value or "",
                progress_callback=progress_callback,
            ),
        )

    preview_button = ft.ElevatedButton("Preview", icon=ft.Icons.PREVIEW, on_click=on_preview)
    copy_apply_button = ft.OutlinedButton("Copy apply", icon=ft.Icons.CHECKLIST, on_click=on_copy_apply)
    production_apply_button = ft.OutlinedButton("Production apply", icon=ft.Icons.LOCK, on_click=on_production_apply)
    operation_dropdown.on_change = lambda _event: (apply_capabilities(), page.update() if hasattr(page, "update") else None)
    apply_capabilities()
    refresh_history()

    content = ft.Column(
        [
            ft.Text("Fundamentals Administration", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([operation_dropdown, market_field, taxonomy_domain_dropdown], wrap=True, spacing=12),
            tickers_field,
            ft.Row([candidate_path_field, candidate_version_field], wrap=True, spacing=12),
            ft.Row([network_allowed_checkbox, production_preview_checkbox], wrap=True, spacing=12),
            ft.Row([preview_button, copy_apply_button, production_apply_button], spacing=12),
            preview_payload_field,
            preview_fingerprint_field,
            production_confirmation_field,
            status_field,
            ft.Text("Summary", size=18, weight=ft.FontWeight.BOLD),
            summary_column,
            progress_field,
            ft.Divider(),
            ft.Text("Run history", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(
                [
                    ft.Text("Run", width=340, weight=ft.FontWeight.BOLD),
                    ft.Text("Operation", width=230, weight=ft.FontWeight.BOLD),
                    ft.Text("Mode", width=150, weight=ft.FontWeight.BOLD),
                    ft.Text("Outcome", width=140, weight=ft.FontWeight.BOLD),
                    ft.Text("Status", width=140, weight=ft.FontWeight.BOLD),
                    ft.Container(width=48),
                ]
            ),
            history_column,
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
    return FundamentalsAdminPageControls(
        content=content,
        operation_dropdown=operation_dropdown,
        tickers_field=tickers_field,
        market_field=market_field,
        taxonomy_domain_dropdown=taxonomy_domain_dropdown,
        candidate_path_field=candidate_path_field,
        candidate_version_field=candidate_version_field,
        network_allowed_checkbox=network_allowed_checkbox,
        production_preview_checkbox=production_preview_checkbox,
        preview_button=preview_button,
        copy_apply_button=copy_apply_button,
        production_apply_button=production_apply_button,
        preview_payload_field=preview_payload_field,
        preview_fingerprint_field=preview_fingerprint_field,
        production_confirmation_field=production_confirmation_field,
        status_field=status_field,
        summary_column=summary_column,
        progress_field=progress_field,
        history_column=history_column,
    )
