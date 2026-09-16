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
    operation_guidance_field: Any
    history_detail_field: Any
    show_technical_history_checkbox: Any
    preview_section: Any
    progress_section: Any
    final_section: Any
    report_button: Any


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
    parts = [result.message]
    if result.run_id:
        parts.append(f"Run: {result.run_id}")
    if result.outcome:
        parts.append(f"Outcome: {result.outcome}")
    if result.preview_fingerprint:
        parts.append(f"Preview fingerprint: {result.preview_fingerprint}")
    if result.report_sha256:
        parts.append(f"Operation report sha256: {result.report_sha256}")
    return "\n".join(parts)


def _material_preview_signature(
    *,
    operation_type: str,
    raw_inputs: str,
    market: str,
    taxonomy_domain: str,
    candidate_path: str,
    candidate_version: str,
    production_mode: bool,
    network_allowed: bool,
) -> tuple[object, ...]:
    operation = operation_type.strip().upper()
    return (
        operation,
        raw_inputs.strip() if operation == "ADD_TICKERS" else "",
        market.strip().lower(),
        taxonomy_domain.strip().lower() if operation == "CHECK_UPDATE_TAXONOMY" else "",
        candidate_path.strip() if operation == "CHECK_UPDATE_TAXONOMY" else "",
        candidate_version.strip() if operation == "CHECK_UPDATE_TAXONOMY" else "",
        bool(production_mode) if operation == "CHECK_UPDATE_TAXONOMY" else False,
        True if operation == "ADD_TICKERS" else bool(network_allowed),
    )


def _short_fingerprint(value: str | None) -> str:
    if not value:
        return "not recorded"
    return value if len(value) <= 16 else value[:12] + "..."


def _plain_status(outcome: str | None) -> str:
    normalized = (outcome or "").upper()
    if normalized in {"COMPLETED", "APPLIED", "READY_TO_APPLY"}:
        return "Completed"
    if normalized == "NO_CHANGE":
        return "No changes"
    if normalized in {"PARTIALLY_COMPLETED", "PARTIAL"}:
        return "Partially completed"
    if normalized in {"REVIEW_REQUIRED", "BLOCKED", "REJECTED"}:
        return "Review required"
    if normalized in {"ROLLED_BACK"}:
        return "Rolled back"
    if normalized in {"FAILED", "ERROR"}:
        return "Failed"
    if normalized in {"INTERRUPTED", "CORRUPT_OR_INCOMPLETE"}:
        return "Interrupted"
    return outcome or "Recorded"


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
        label="Tickers",
        hint_text="NVDA, VRT or one ticker per line",
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
    network_allowed_checkbox = ft.Checkbox(label="Allow provider network for preview", value=True, visible=False)
    production_preview_checkbox = ft.Checkbox(label="Protected production preview", value=False, visible=False)
    operation_guidance_field = ft.Text(
        "Provider network access is enabled automatically when local data is insufficient."
    )
    preview_payload_field = ft.TextField(label="Preview payload path", width=620, read_only=True, visible=False)
    preview_fingerprint_field = ft.TextField(label="Preview fingerprint", width=620, read_only=True, visible=False)
    production_confirmation_field = ft.TextField(
        label="Production confirmation token",
        password=True,
        can_reveal_password=True,
        width=620,
        read_only=True,
        visible=False,
    )
    status_field = ft.TextField(
        label="Result summary",
        value="",
        read_only=True,
        multiline=True,
        min_lines=2,
        max_lines=5,
        visible=False,
    )
    progress_field = ft.TextField(
        label="Progress",
        value="",
        read_only=True,
        multiline=True,
        min_lines=2,
        max_lines=5,
        visible=False,
    )
    history_detail_field = ft.TextField(
        label="Selected run",
        value="Select a run from history to inspect its durable progress and report availability.",
        read_only=True,
        multiline=True,
        min_lines=4,
        max_lines=7,
    )
    summary_column = ft.Column(spacing=4)
    history_column = ft.Column(spacing=6)
    show_technical_history_checkbox = ft.Checkbox(label="Show technical and legacy runs", value=False)
    technical_details_column = ft.Column(spacing=4, visible=False)
    preview_section = ft.Column(
        [ft.Text("Preview summary", size=18, weight=ft.FontWeight.BOLD), summary_column],
        spacing=6,
        visible=False,
    )
    progress_section = ft.Column(
        [ft.Text("Progress", size=18, weight=ft.FontWeight.BOLD), progress_field],
        spacing=6,
        visible=False,
    )
    final_section = ft.Column(
        [ft.Text("Final summary", size=18, weight=ft.FontWeight.BOLD), status_field],
        spacing=6,
        visible=False,
    )
    report_button = ft.OutlinedButton(
        "Download full operation report",
        icon=ft.Icons.DOWNLOAD,
        visible=False,
    )
    current_preview_signature: tuple[object, ...] | None = None
    current_preview_result: AdminUIRunResult | None = None
    current_preview_payload_path: str | None = None
    current_preview_fingerprint: str | None = None
    current_report_run_id: str | None = None
    operation_running = False

    def current_signature() -> tuple[object, ...]:
        return _material_preview_signature(
            operation_type=operation_dropdown.value or "ADD_TICKERS",
            raw_inputs=tickers_field.value or "",
            market=market_field.value or "usa",
            taxonomy_domain=taxonomy_domain_dropdown.value or "dc_ecosystem",
            candidate_path=candidate_path_field.value or "",
            candidate_version=candidate_version_field.value or "",
            production_mode=bool(production_preview_checkbox.value),
            network_allowed=True if (operation_dropdown.value or "ADD_TICKERS") == "ADD_TICKERS" else False,
        )

    def has_current_preview() -> bool:
        return (
            current_preview_signature == current_signature()
            and bool((preview_payload_field.value or "").strip())
            and bool((preview_fingerprint_field.value or "").strip())
        )

    def operation_guidance() -> str:
        operation = (operation_dropdown.value or "ADD_TICKERS").strip().upper()
        if operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            return (
                "Checks the full active universe. data/osakedata.db.ticker_meta is the authoritative "
                "Sector/Industry source, and this can be run without adding a ticker. Apply is shown "
                "only when the backend reports an authorized correctable candidate."
            )
        if operation == "CHECK_UPDATE_TAXONOMY":
            domain = taxonomy_domain_dropdown.value or "dc_ecosystem"
            if domain == "ec_taxonomy":
                return (
                    "ec_taxonomy is a separate future domain and remains read-only/not-ready unless "
                    "the backend authorizes a safe workflow."
                )
            return (
                "dc_ecosystem is the current primary Datacenter taxonomy. Fundamentals consumption "
                "does not automatically edit taxonomy source classifications."
            )
        return (
            "Enter one or more tickers. Commas, spaces, newlines and duplicates are accepted. "
            "Provider network access is enabled automatically when local data is insufficient."
        )

    def update_operation_visibility() -> None:
        operation = (operation_dropdown.value or "ADD_TICKERS").strip().upper()
        is_add = operation == "ADD_TICKERS"
        is_sector = operation == "CHECK_UPDATE_SECTOR_INDUSTRY"
        is_taxonomy = operation == "CHECK_UPDATE_TAXONOMY"
        tickers_field.visible = is_add
        market_field.visible = is_add or is_sector
        taxonomy_domain_dropdown.visible = is_taxonomy
        candidate_path_field.visible = is_taxonomy and bool(candidate_path_field.value)
        candidate_version_field.visible = is_taxonomy and bool(candidate_version_field.value)
        network_allowed_checkbox.visible = False
        production_preview_checkbox.visible = False
        preview_payload_field.visible = False
        preview_fingerprint_field.visible = False
        production_confirmation_field.visible = False
        operation_guidance_field.value = operation_guidance()
        if is_sector:
            tickers_field.value = ""

    def can_preview() -> bool:
        operation = (operation_dropdown.value or "ADD_TICKERS").strip().upper()
        if operation == "ADD_TICKERS":
            return bool((tickers_field.value or "").strip())
        if operation == "CHECK_UPDATE_TAXONOMY":
            return bool(taxonomy_domain_dropdown.value)
        return True

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
        for item in admin_service.history_entries(
            limit=12,
            include_technical=bool(show_technical_history_checkbox.value),
        ):
            run_id = item.run_id
            title = _plain_status(item.outcome)
            when = item.completed_at_utc or "not finished"
            category = getattr(item, "category", "Administration run")
            primary = getattr(item, "primary_count", None)
            count_text = f"{primary} items" if primary is not None else ""
            rows.append(
                ft.Row(
                    [
                        ft.Text(when, width=185),
                        ft.Text(item.operation_type.replace("_", " ").title(), width=210),
                        ft.Text(title, width=150),
                        ft.Text(count_text, width=90),
                        ft.Text(category, width=170, tooltip=f"run_id={item.run_id}; mode={item.mode}"),
                        ft.IconButton(
                            icon=ft.Icons.INFO,
                            tooltip="View details",
                            on_click=lambda _event, selected_run_id=run_id: select_history_run(selected_run_id),
                        ),
                        download_button(item.run_id, enabled=item.report_available),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        history_column.controls = rows or [ft.Text("No administration runs found.")]

    def select_history_run(run_id: str) -> None:
        try:
            progress = admin_service.progress(run_id)
            report_text = "available" if OPERATION_REPORT_NAME in progress.artifacts else "not yet available"
            heartbeat = (
                f"{progress.heartbeat_age_seconds:.0f}s ago"
                if progress.heartbeat_age_seconds is not None
                else "not recorded"
            )
            history_detail_field.value = (
                f"Run: {progress.run_id}\n"
                f"Operation: {progress.operation_type}\n"
                f"Status: {progress.status}; outcome: {progress.terminal_outcome or 'not terminal'}\n"
                f"Stage: {progress.current_stage} "
                f"({progress.current_stage_number or '?'}/{progress.total_declared_stages or '?'})\n"
                f"Completed stages: {progress.completed_stages}; heartbeat: {heartbeat}\n"
                f"Operation report: {report_text}"
            )
            progress_field.value = (
                "Still working." if progress.status == "running" else "Selected run progress loaded."
            ) + (
                f"\n{progress.current_stage} "
                f"({progress.current_stage_number or '?'}/{progress.total_declared_stages or '?'})"
            )
        except Exception:
            history_detail_field.value = f"Run: {run_id}\nStatus: unavailable or incomplete."
        if hasattr(page, "update"):
            page.update()

    def progress_callback(event: Any) -> None:
        progress_section.visible = True
        progress_field.visible = True
        progress_field.value = (
            f"[{event.get('current_stage_number', '?')}/{event.get('total_declared_stages', '?')}] "
            f"{event.get('current_stage_id', 'UNKNOWN')} - {event.get('stage_state', 'UNKNOWN')}\n"
            f"{event.get('message', '')}"
        )
        if hasattr(page, "update"):
            page.update()

    def apply_result(result: AdminUIRunResult) -> None:
        nonlocal current_preview_signature, current_preview_result, current_preview_payload_path
        nonlocal current_preview_fingerprint, current_report_run_id
        status_field.value = _result_text(result)
        final_section.visible = True
        status_field.visible = True
        if result.preview_payload_path:
            current_preview_payload_path = result.preview_payload_path
            preview_payload_field.value = result.preview_payload_path
        if result.preview_fingerprint:
            current_preview_fingerprint = result.preview_fingerprint
            preview_fingerprint_field.value = result.preview_fingerprint
        if result.preview_payload_path and result.preview_fingerprint:
            current_preview_signature = current_signature()
            current_preview_result = result
        if result.run_id:
            current_report_run_id = result.run_id
            report_button.on_click = lambda _event, run_id=result.run_id: _launch_browser_url(
                page,
                admin_report_download_url(run_id),
            )
            report_button.visible = bool(result.report_filename)
        update_summary(result)
        preview_section.visible = True
        refresh_history()
        technical_details_column.controls = [
            ft.Text(f"Run id: {result.run_id or 'not recorded'}"),
            ft.Text(f"Preview fingerprint: {_short_fingerprint(result.preview_fingerprint)}"),
            ft.Text(f"Artifact directory: {result.artifact_dir or 'not recorded'}"),
            ft.Text(f"Report sha256: {_short_fingerprint(result.report_sha256)}"),
        ]

    def apply_capabilities() -> None:
        capability = capability_for_current_operation()
        update_operation_visibility()
        preview_button.disabled = bool(operation_running or (capability and not capability.preview_enabled) or not can_preview())
        preview_ready = has_current_preview()
        copy_authorized = bool(getattr(capability, "copy_apply_enabled", True))
        production_authorized = bool(getattr(capability, "production_apply_enabled", True))
        copy_apply_button.visible = bool(copy_authorized and preview_ready)
        copy_apply_button.disabled = bool(operation_running or not preview_ready)
        production_apply_button.visible = bool(production_authorized and preview_ready)
        production_apply_button.disabled = bool(operation_running or not preview_ready)

    def invalidate_preview(_event: Any | None = None) -> None:
        nonlocal current_preview_signature, current_preview_result, current_preview_payload_path
        nonlocal current_preview_fingerprint, current_report_run_id
        if current_preview_signature is not None and current_preview_signature != current_signature():
            current_preview_signature = None
            current_preview_result = None
            current_preview_payload_path = None
            current_preview_fingerprint = None
            current_report_run_id = None
            preview_payload_field.value = ""
            preview_fingerprint_field.value = ""
            status_field.value = (
                "The preview is no longer current. Run Preview again."
            )
            update_summary(AdminUIRunResult(status="PREVIEW_STALE", message="Preview is stale."))
            report_button.visible = False
        apply_capabilities()
        if hasattr(page, "update"):
            page.update()

    def run_guarded(button: Any, fn: Any) -> None:
        nonlocal operation_running
        if button.disabled:
            return
        operation_running = True
        button.disabled = True
        preview_button.disabled = True
        copy_apply_button.disabled = True
        production_apply_button.disabled = True
        progress_section.visible = True
        progress_field.visible = True
        progress_field.value = "Starting..."
        if hasattr(page, "update"):
            page.update()
        try:
            apply_result(fn())
        except Exception:
            LOGGER.exception("Fundamentals administration UI run failed")
            final_section.visible = True
            status_field.visible = True
            status_field.value = "Administration run failed. See the operation log or report for details."
        finally:
            operation_running = False
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
                production_mode=False,
                network_allowed=True if (operation_dropdown.value or "ADD_TICKERS") == "ADD_TICKERS" else False,
                progress_callback=progress_callback,
            ),
        )

    def on_copy_apply(_event: Any) -> None:
        run_guarded(
            copy_apply_button,
            lambda: admin_service.copy_apply(
                operation_dropdown.value or "ADD_TICKERS",
                preview_payload_path=current_preview_payload_path or "",
                preview_fingerprint=current_preview_fingerprint or "",
                taxonomy_domain=taxonomy_domain_dropdown.value or "dc_ecosystem",
                progress_callback=progress_callback,
            ),
        )

    def confirmation_token_for_current_operation() -> str:
        operation = (operation_dropdown.value or "ADD_TICKERS").strip().upper()
        if operation == "ADD_TICKERS":
            return "CONFIRM_PRODUCTION_BATCH_ADD_TICKERS"
        if operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            return "CONFIRM_PRODUCTION_SECTOR_INDUSTRY"
        capability = capability_for_current_operation()
        return str(getattr(capability, "production_confirmation_hint", "") or "")

    def open_production_confirmation(_event: Any) -> None:
        operation = (operation_dropdown.value or "ADD_TICKERS").replace("_", " ").title()
        scope = (tickers_field.value or "Full active universe").strip()
        domain = taxonomy_domain_dropdown.value or "not applicable"
        body = (
            f"Operation: {operation}\n"
            f"Scope: {scope}\n"
            f"Taxonomy domain: {domain}\n"
            "Provider network may be used when Add Tickers local data is insufficient.\n"
            "Package/RP/RV work and backups remain controlled by the backend contract.\n"
            "This may be long-running and production data may change."
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm production update"),
            content=ft.Text(body),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _event: close_dialog()),
                ft.ElevatedButton("Confirm production update", on_click=lambda _event: confirm_production_apply()),
            ],
        )
        setattr(page, "dialog", dialog)
        if hasattr(page, "open"):
            page.open(dialog)
        else:
            dialog.open = True
        if hasattr(page, "update"):
            page.update()

    def close_dialog() -> None:
        dialog = getattr(page, "dialog", None)
        if dialog is not None:
            dialog.open = False
        if hasattr(page, "update"):
            page.update()

    def confirm_production_apply() -> None:
        close_dialog()
        run_guarded(
            production_apply_button,
            lambda: admin_service.production_apply(
                operation_dropdown.value or "ADD_TICKERS",
                preview_payload_path=current_preview_payload_path or "",
                preview_fingerprint=current_preview_fingerprint or "",
                confirmation=confirmation_token_for_current_operation(),
                progress_callback=progress_callback,
            ),
        )

    def on_production_apply(_event: Any) -> None:
        if production_apply_button.disabled:
            return
        open_production_confirmation(_event)

    preview_button = ft.ElevatedButton("Preview", icon=ft.Icons.PREVIEW, on_click=on_preview)
    copy_apply_button = ft.OutlinedButton("Apply", icon=ft.Icons.CHECKLIST, on_click=on_copy_apply, visible=False)
    production_apply_button = ft.OutlinedButton("Production update", icon=ft.Icons.LOCK, on_click=on_production_apply, visible=False)
    for control in (
        operation_dropdown,
        tickers_field,
        market_field,
        taxonomy_domain_dropdown,
        candidate_path_field,
        candidate_version_field,
        network_allowed_checkbox,
        production_preview_checkbox,
    ):
        control.on_change = invalidate_preview
    show_technical_history_checkbox.on_change = lambda _event: (
        refresh_history(),
        page.update() if hasattr(page, "update") else None,
    )
    apply_capabilities()
    refresh_history()

    content = ft.Column(
        [
            ft.Text("Fundamentals Administration", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Administration operation", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([operation_dropdown, market_field, taxonomy_domain_dropdown], wrap=True, spacing=12),
            operation_guidance_field,
            tickers_field,
            ft.Row([candidate_path_field, candidate_version_field], wrap=True, spacing=12),
            ft.Row([preview_button, copy_apply_button, production_apply_button], spacing=12),
            preview_section,
            progress_section,
            final_section,
            report_button,
            ft.ExpansionPanelList(
                controls=[
                    ft.ExpansionPanel(
                        header=ft.ListTile(title=ft.Text("Technical details")),
                        content=ft.Column(
                            [preview_payload_field, preview_fingerprint_field, production_confirmation_field, technical_details_column],
                            spacing=6,
                        ),
                        expanded=False,
                    )
                ]
            ),
            ft.Divider(),
            ft.Text("Run history", size=18, weight=ft.FontWeight.BOLD),
            show_technical_history_checkbox,
            ft.Row(
                [
                    ft.Text("Time", width=185, weight=ft.FontWeight.BOLD),
                    ft.Text("Operation", width=210, weight=ft.FontWeight.BOLD),
                    ft.Text("Result", width=150, weight=ft.FontWeight.BOLD),
                    ft.Text("Count", width=90, weight=ft.FontWeight.BOLD),
                    ft.Text("Category", width=170, weight=ft.FontWeight.BOLD),
                    ft.Container(width=48),
                    ft.Container(width=48),
                ]
            ),
            history_column,
            history_detail_field,
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
        operation_guidance_field=operation_guidance_field,
        history_detail_field=history_detail_field,
        show_technical_history_checkbox=show_technical_history_checkbox,
        preview_section=preview_section,
        progress_section=progress_section,
        final_section=final_section,
        report_button=report_button,
    )
