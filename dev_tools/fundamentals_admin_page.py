from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import flet as ft

from dev_tools.deferred_ui import DeferredLoadController, LoadState
from rawcandle.fundamentals.admin.operation_report import OPERATION_REPORT_NAME, WORKFLOW_REPORT_NAME
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
    full_workflow_button: Any
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
    technical_details_column: Any
    progress_summary: Any
    progress_details: Any
    history_show_more_button: Any
    cleanup_status_field: Any
    cleanup_button: Any
    activate: Any
    history_loader: Any


def admin_report_download_url(run_id: str, filename: str = OPERATION_REPORT_NAME) -> str:
    safe_run_id = quote(str(run_id), safe="")
    safe_name = quote(filename, safe="")
    return f"{FUNDAMENTALS_ADMIN_DOWNLOAD_ROUTE}/{safe_run_id}/{safe_name}"


def _launch_browser_url(page: Any, url: str) -> None:
    result = page.launch_url(url)
    if inspect.isawaitable(result):
        async def _await_launch() -> None:
            await result

        page.run_task(_await_launch)


def _result_text(result: AdminUIRunResult) -> str:
    return result.message


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
        raw_inputs.strip() if operation in {"ADD_TICKERS", "REMOVE_TICKERS", "RESOLVE_TICKER_IDENTITY"} else "",
        market.strip().lower(),
        taxonomy_domain.strip().lower() if operation == "CHECK_UPDATE_TAXONOMY" else "",
        "",
        "",
        bool(production_mode) if operation == "CHECK_UPDATE_TAXONOMY" else False,
        True if operation == "ADD_TICKERS" else bool(network_allowed),
    )


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
    defer_initial_load: bool = False,
) -> FundamentalsAdminPageControls:
    owns_service = service is None
    admin_service = service or FundamentalsAdminUIService(
        recover_publication_on_startup=not defer_initial_load
    )
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
            ft.dropdown.Option("REMOVE_TICKERS", "Remove Tickers"),
            ft.dropdown.Option("REFRESH_FUNDAMENTALS", "Refresh Fundamentals"),
            ft.dropdown.Option("CHECK_UPDATE_SECTOR_INDUSTRY", "Sector and Industry"),
            ft.dropdown.Option("CHECK_UPDATE_TAXONOMY", "Taxonomy"),
            ft.dropdown.Option("SYNCHRONIZE_PROVIDER_CIK", "Synchronize provider CIK"),
            ft.dropdown.Option("RESOLVE_TICKER_IDENTITY", "Resolve ticker identity"),
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
        ],
        value="dc_ecosystem",
    )
    candidate_path_field = ft.TextField(label="Candidate CSV", width=520, visible=False)
    candidate_version_field = ft.TextField(label="Candidate version", width=260, visible=False)
    network_allowed_checkbox = ft.Checkbox(label="Allow provider network for preview", value=True, visible=False)
    production_preview_checkbox = ft.Checkbox(label="Protected production preview", value=False, visible=False)
    operation_guidance_field = ft.Text(
        "Enter up to 25 tickers. Provider network access is enabled automatically when local data is insufficient."
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
    try:
        publication_safety = admin_service.publication_safety_status()
    except (AttributeError, OSError, RuntimeError):
        publication_safety = {"status": "UNKNOWN", "production_writes_blocked": False}
    publication_safety_field = ft.Text(
        (
            "Production safety block: RawCandle could not restore a complete verified Fundamentals generation. "
            "Production-writing operations are disabled until recovery is resolved."
            if publication_safety.get("production_writes_blocked")
            else ""
        ),
        visible=bool(publication_safety.get("production_writes_blocked")),
    )
    pending_refresh = None
    if not defer_initial_load:
        try:
            pending_refresh = admin_service.pending_refresh_status()
        except (AttributeError, OSError, RuntimeError):
            pending_refresh = None
    pending_refresh_field = ft.Text(
        (
            "Pending Sharadar fundamentals changes detected: "
            f"{pending_refresh.get('effective_changed_known', 0)} known tickers; "
            f"last scheduler Preview {pending_refresh.get('detected_at_utc') or 'time unavailable'}."
            if pending_refresh else ""
        ),
        visible=bool(pending_refresh),
    )
    progress_field = ft.ListView(
        height=230,
        spacing=4,
        padding=8,
        auto_scroll=True,
        visible=False,
    )
    progress_field.value = ""
    history_detail_field = ft.TextField(
        label="Selected run",
        value="Select a run from history to inspect its durable progress and report availability.",
        read_only=True,
        multiline=True,
        min_lines=4,
        max_lines=7,
    )
    cleanup_status_field = ft.Text("", visible=False)
    cleanup_button = ft.ElevatedButton(
        "Accept run and cleanup backups",
        icon=ft.Icons.DELETE_SWEEP,
        visible=False,
        disabled=True,
    )
    summary_column = ft.Column(spacing=4)
    history_column = ft.Column(spacing=6)
    show_technical_history_checkbox = ft.Checkbox(label="Show technical and legacy runs", value=False)
    technical_details_column = ft.Column(spacing=4)
    preview_title = ft.Text("Preview result", size=18, weight=ft.FontWeight.BOLD)
    preview_section = ft.Column(
        [preview_title, summary_column],
        spacing=6,
        visible=False,
    )
    progress_summary = ft.Text("", visible=False)
    progress_details = ft.ExpansionPanelList(controls=[ft.ExpansionPanel(
        header=ft.ListTile(title=ft.Text("Progress details")),
        content=progress_field,
        expanded=False,
    )], visible=False)
    progress_section = ft.Column(
        [ft.Text("Progress", size=18, weight=ft.FontWeight.BOLD), progress_summary, progress_details],
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
    current_test_run_id: str | None = None
    current_report_run_id: str | None = None
    selected_history_run_id: str | None = None
    history_cursor: Any = None
    history_limit = 8
    operation_running = False
    last_progress_count: tuple[object, object] | None = None
    progress_lines: list[str] = []
    progress_follow_latest = True

    def render_progress(*, replace: list[str] | None = None, append: str | None = None) -> None:
        nonlocal progress_lines
        if replace is not None:
            progress_lines = list(replace)
        if append:
            progress_lines.append(append)
        progress_lines = progress_lines[-200:]
        progress_field.value = "\n".join(progress_lines)
        progress_field.controls = [ft.Text(line, selectable=True) for line in progress_lines]
        progress_field.auto_scroll = progress_follow_latest

    def on_progress_scroll(event: Any) -> None:
        nonlocal progress_follow_latest
        pixels = float(getattr(event, "pixels", 0) or 0)
        maximum = float(getattr(event, "max_scroll_extent", 0) or 0)
        progress_follow_latest = maximum - pixels <= 24
        progress_field.auto_scroll = progress_follow_latest

    progress_field.on_scroll = on_progress_scroll

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
                "Sector/Industry source, and this can be run without adding a ticker. Test on copies is shown "
                "only when the backend reports an authorized correctable candidate."
            )
        if operation == "CHECK_UPDATE_TAXONOMY":
            return "Rebuilds Fundamentals from the active dc_ecosystem version in data/analysis.db."
        if operation == "REFRESH_FUNDAMENTALS":
            return (
                "Checks Sharadar for new quarterly results and historical revisions. Preview is read-only; "
                "Test on copies performs complete source replacement and a fresh V2 rebuild. Production update publishes a verified journaled generation."
            )
        if operation == "SYNCHRONIZE_PROVIDER_CIK":
            return (
                "Synchronizes an available Sharadar provider CIK into the mapped canonical company. "
                "Provider CIK absence is allowed and conflicts require review."
            )
        if operation == "RESOLVE_TICKER_IDENTITY":
            return "Inspect company, security, ticker and provider continuity for up to 25 tickers. This operation is read-only."
        if operation == "REMOVE_TICKERS":
            return (
                "Plan removal of up to 25 current securities from the active Fundamentals universe. "
                "Preview preserves permanent identity and history; Test on copies validates the removal and full rebuild. "
                "Production is not available yet."
            )
        return (
            "Enter 1 to 25 tickers. Commas, spaces, newlines and duplicates are accepted. "
            "Provider network access is enabled automatically when local data is insufficient."
        )

    def update_operation_visibility() -> None:
        operation = (operation_dropdown.value or "ADD_TICKERS").strip().upper()
        is_add = operation == "ADD_TICKERS"
        is_remove = operation == "REMOVE_TICKERS"
        is_refresh = operation == "REFRESH_FUNDAMENTALS"
        is_sector = operation == "CHECK_UPDATE_SECTOR_INDUSTRY"
        is_taxonomy = operation == "CHECK_UPDATE_TAXONOMY"
        is_cik_sync = operation == "SYNCHRONIZE_PROVIDER_CIK"
        is_identity = operation == "RESOLVE_TICKER_IDENTITY"
        tickers_field.visible = is_add or is_remove or is_identity
        market_field.visible = is_add or is_sector
        taxonomy_domain_dropdown.visible = False
        candidate_path_field.visible = False
        candidate_version_field.visible = False
        network_allowed_checkbox.visible = False
        production_preview_checkbox.visible = False
        preview_payload_field.visible = False
        preview_fingerprint_field.visible = False
        production_confirmation_field.visible = False
        operation_guidance_field.value = operation_guidance()
        if is_sector:
            tickers_field.value = ""
        if is_refresh or is_cik_sync:
            tickers_field.value = ""

    def can_preview() -> bool:
        operation = (operation_dropdown.value or "ADD_TICKERS").strip().upper()
        if operation in {"ADD_TICKERS", "REMOVE_TICKERS", "RESOLVE_TICKER_IDENTITY"}:
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

    def render_history(entries: Any) -> None:
        rows = []
        for item in entries:
            run_id = item.run_id
            title = _plain_status(item.outcome)
            when = item.completed_at_utc or ("In progress" if item.status == "running" else "Time unavailable")
            category = getattr(item, "category", "Administration run")
            primary = getattr(item, "primary_count", None)
            count_text = getattr(item, "count_label", None) or (f"{primary} items" if primary is not None else "")
            operation_label = {
                "ADD_TICKERS": "Add Tickers",
                "REMOVE_TICKERS": "Remove Tickers",
                "REFRESH_FUNDAMENTALS": "Refresh Fundamentals",
                "CHECK_UPDATE_SECTOR_INDUSTRY": "Sector and Industry",
                "CHECK_UPDATE_TAXONOMY": "Taxonomy",
                "SYNCHRONIZE_PROVIDER_CIK": "Synchronize provider CIK",
                "RESOLVE_TICKER_IDENTITY": "Resolve ticker identity",
            }.get(item.operation_type, item.operation_type.replace("_", " ").title())
            if getattr(item, "trigger_source", "MANUAL") == "SCHEDULER":
                operation_label += " [Scheduler]"
            weight = ft.FontWeight.BOLD if run_id == selected_history_run_id else ft.FontWeight.NORMAL
            rows.append(
                ft.Row(
                    [
                        ft.Text(when, width=185, weight=weight),
                        ft.Text(operation_label, width=190, weight=weight),
                        ft.Text(item.stage, width=155, weight=weight),
                        ft.Text(title, width=135, weight=weight),
                        ft.Text(count_text, width=125, weight=weight),
                        ft.Text(category, width=170, tooltip=f"run_id={item.run_id}; mode={item.mode}"),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip="Remove from run history",
                            on_click=lambda _event, selected_run_id=run_id: open_history_delete_confirmation(
                                selected_run_id
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.INFO,
                            tooltip="View details",
                            on_click=lambda _event, selected_run_id=run_id: select_history_run(selected_run_id),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DOWNLOAD,
                            tooltip="Download workflow report" if item.report_filename == WORKFLOW_REPORT_NAME else "Download operation report",
                            disabled=not item.report_available,
                            on_click=lambda _event, selected_run_id=run_id, filename=item.report_filename: _launch_browser_url(
                                page, admin_report_download_url(selected_run_id, filename)
                            ),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        history_column.controls = rows or [ft.Text("No administration runs found.")]
        history_show_more_button.visible = bool(
            history_cursor is not None and not getattr(history_cursor, "exhausted", True)
        )

    def load_history() -> dict[str, Any]:
        nonlocal history_cursor
        safety_initializer = getattr(admin_service, "initialize_publication_safety", None)
        safety = safety_initializer() if owns_service and callable(safety_initializer) else None
        include_technical = bool(show_technical_history_checkbox.value)
        if history_cursor is None or history_cursor.include_technical != include_technical:
            cursor_factory = getattr(admin_service, "history_cursor", None)
            if callable(cursor_factory):
                history_cursor = cursor_factory(include_technical=include_technical)
            else:
                class _CompatibilityCursor:
                    exhausted = True
                    projections: dict[Any, Any] = {}

                    def __init__(self) -> None:
                        self.include_technical = include_technical
                        self.entries: list[Any] = []

                    def fill(self, limit: int) -> list[Any]:
                        self.entries = list(admin_service.history_entries(
                            limit=limit,
                            include_technical=self.include_technical,
                        ))
                        return self.entries

                history_cursor = _CompatibilityCursor()
        entries = history_cursor.fill(history_limit)
        pending_reader = getattr(admin_service, "pending_refresh_status", None)
        pending = pending_reader(
            projection_cache=getattr(history_cursor, "projections", None),
        ) if callable(pending_reader) else None
        return {"entries": entries, "pending": pending, "publication_safety": safety}

    def apply_history(payload: dict[str, Any]) -> None:
        nonlocal publication_safety
        loaded_safety = payload.get("publication_safety")
        if loaded_safety is not None:
            publication_safety = loaded_safety
            blocked = bool(publication_safety.get("production_writes_blocked"))
            publication_safety_field.value = (
                "Production safety block: RawCandle could not restore a complete verified "
                "Fundamentals generation. Production-writing operations are disabled until "
                "recovery is resolved."
                if blocked else ""
            )
            publication_safety_field.visible = blocked
            apply_capabilities()
        pending = payload.get("pending")
        if pending and pending.get("status") == "ERROR":
            pending_refresh_field.value = str(pending.get("error") or "Refresh history is unavailable.")
            pending_refresh_field.visible = True
        elif pending:
            pending_refresh_field.value = (
                "Pending Sharadar fundamentals changes detected: "
                f"{pending.get('effective_changed_known', 0)} known tickers; "
                f"last scheduler Preview {pending.get('detected_at_utc') or 'time unavailable'}."
            )
            pending_refresh_field.visible = True
        else:
            pending_refresh_field.value = ""
            pending_refresh_field.visible = False
        render_history(payload.get("entries") or [])
        history_show_more_button.disabled = False

    def history_failed(_exc: Exception) -> None:
        history_column.controls = [ft.Text("Administration history could not be loaded.")]
        history_show_more_button.visible = False
        history_show_more_button.disabled = False

    def history_loading() -> None:
        history_column.controls = [ft.Text("Loading administration history...")]
        history_show_more_button.disabled = True

    history_loader = DeferredLoadController(
        page=page,
        load=load_history,
        apply=apply_history,
        loading=history_loading,
        failed=history_failed,
    )

    def refresh_history(*, force: bool = False) -> None:
        nonlocal history_cursor, history_limit
        if force:
            history_cursor = None
            history_limit = 8
            history_loader.invalidate()
        if defer_initial_load:
            history_loader.start(force=force)
            return
        try:
            apply_history(load_history())
        except Exception:
            LOGGER.exception("Administration history refresh failed")
            history_failed(RuntimeError("history load failed"))

    def show_more_history(_event: Any) -> None:
        nonlocal history_limit
        history_limit += 8
        if defer_initial_load:
            history_loader.start(force=True)
        else:
            refresh_history()

    history_show_more_button = ft.TextButton(
        "Show more",
        icon=ft.Icons.EXPAND_MORE,
        on_click=show_more_history,
        visible=False,
    )

    def apply_cleanup_eligibility(run_id: str) -> dict[str, Any]:
        reader = getattr(admin_service, "cleanup_eligibility", None)
        if not callable(reader):
            cleanup_button.visible = False
            cleanup_status_field.visible = False
            return {}
        state = dict(reader(run_id))
        eligible = bool(state.get("eligible"))
        cleanup_button.visible = eligible
        cleanup_button.disabled = not eligible
        cleanup_status_field.value = (
            "Deletes only this accepted run's verified rollback backups. Production data is not changed."
            if eligible
            else str(state.get("reason") or "Backup cleanup is not available for this run.")
        )
        cleanup_status_field.visible = True
        return state

    def select_history_run(run_id: str) -> None:
        nonlocal selected_history_run_id
        try:
            projection_cache = getattr(history_cursor, "projections", None)
            progress_reader = admin_service.progress
            progress = (
                progress_reader(run_id, projection_cache=projection_cache)
                if "projection_cache" in inspect.signature(progress_reader).parameters
                else progress_reader(run_id)
            )
            summary_reader = getattr(admin_service, "history_result_summary", None)
            summary = (
                summary_reader(run_id, projection_cache=projection_cache)
                if callable(summary_reader)
                and "projection_cache" in inspect.signature(summary_reader).parameters
                else summary_reader(run_id) if callable(summary_reader) else ()
            )
            report_text = "available" if OPERATION_REPORT_NAME in progress.artifacts else "not yet available"
            heartbeat = (
                f"{progress.heartbeat_age_seconds:.0f}s ago"
                if progress.heartbeat_age_seconds is not None
                else "not recorded"
            )
            history_detail_field.value = (
                ("\n".join(summary) + "\n" if summary else "")
                +
                f"Run: {progress.run_id}\n"
                f"Operation: {progress.operation_type}\n"
                f"Status: {progress.status}; outcome: {progress.terminal_outcome or 'not terminal'}\n"
                f"Stage: {progress.current_stage} "
                f"({progress.current_stage_number or '?'}/{progress.total_declared_stages or '?'})\n"
                f"Completed stages: {progress.completed_stages}; heartbeat: {heartbeat}\n"
                f"Operation report: {report_text}"
            )
            selected_history_run_id = run_id
            apply_cleanup_eligibility(run_id)
            render_progress(replace=[
                "Still working." if progress.status == "running" else "Selected run progress loaded.",
                f"{progress.current_stage} ({progress.current_stage_number or '?'}/{progress.total_declared_stages or '?'})",
            ])
        except Exception:
            history_detail_field.value = f"Run: {run_id}\nStatus: unavailable or incomplete."
            cleanup_button.visible = False
            cleanup_status_field.value = "Backup cleanup eligibility is unavailable."
            cleanup_status_field.visible = True
        if history_cursor is not None:
            render_history(history_cursor.entries[:history_limit])
        if hasattr(page, "update"):
            page.update()

    def confirm_history_delete(run_id: str) -> None:
        nonlocal selected_history_run_id, current_report_run_id
        try:
            admin_service.remove_history_entry(run_id)
        except Exception as exc:
            LOGGER.exception("Administration history removal failed")
            history_detail_field.value = f"Run: {run_id}\nCould not remove from history: {exc}"
            close_dialog()
            if hasattr(page, "update"):
                page.update()
            return
        if selected_history_run_id == run_id:
            selected_history_run_id = None
            history_detail_field.value = (
                f"Run {run_id} was removed from this history list. "
                "Its report files remain available as audit evidence."
            )
        if current_report_run_id == run_id:
            current_report_run_id = None
            report_button.visible = False
        close_dialog()
        refresh_history(force=True)
        if hasattr(page, "update"):
            page.update()

    def open_history_delete_confirmation(run_id: str) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Remove run from history?"),
            content=ft.Text(
                f"Run: {run_id}\n\n"
                "This removes the row from Run history. The report files remain on disk as audit evidence."
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _event: close_dialog()),
                ft.ElevatedButton(
                    "Remove",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda _event: confirm_history_delete(run_id),
                ),
            ],
        )
        setattr(page, "dialog", dialog)
        if hasattr(page, "open"):
            page.open(dialog)
        else:
            dialog.open = True
        if hasattr(page, "update"):
            page.update()

    def confirm_backup_cleanup(run_id: str) -> None:
        close_dialog()
        cleanup_button.disabled = True
        cleanup_status_field.value = "Verifying this run's rollback backups..."
        cleanup_status_field.visible = True
        if hasattr(page, "update"):
            page.update()
        try:
            result = admin_service.accept_run_and_cleanup_backups(run_id)
            status = str(result.get("status") or result.get("cleanup_outcome") or "COMPLETED")
            if status == "ALREADY_CLEANED":
                cleanup_status_field.value = "Accepted / backups cleaned"
            else:
                freed = int(result.get("bytes_freed") or 0)
                cleanup_status_field.value = f"Accepted / backups cleaned ({freed / (1024 ** 3):.3f} GiB freed)"
            cleanup_button.visible = False
            select_history_run(run_id)
        except Exception as exc:
            LOGGER.exception("Administration backup cleanup failed")
            cleanup_status_field.value = f"Backup cleanup stopped: {exc}"
            cleanup_button.visible = False
            cleanup_button.disabled = True
        if hasattr(page, "update"):
            page.update()

    def open_backup_cleanup_confirmation(_event: Any) -> None:
        run_id = selected_history_run_id
        if not run_id:
            return
        state = apply_cleanup_eligibility(run_id)
        if not state.get("eligible"):
            if hasattr(page, "update"):
                page.update()
            return
        count = int(state.get("backup_count") or 0)
        gib = int(state.get("bytes_freed") or 0) / (1024 ** 3)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Accept Production run and cleanup backups?"),
            content=ft.Text(
                f"Run: {run_id}\n\n"
                f"This removes {count} verified rollback backup file(s), approximately {gib:.3f} GiB.\n"
                "Live Production databases will not be modified."
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _event: close_dialog()),
                ft.ElevatedButton(
                    "Accept and cleanup",
                    icon=ft.Icons.DELETE_SWEEP,
                    on_click=lambda _event: confirm_backup_cleanup(run_id),
                ),
            ],
        )
        setattr(page, "dialog", dialog)
        if hasattr(page, "open"):
            page.open(dialog)
        else:
            dialog.open = True
        if hasattr(page, "update"):
            page.update()

    cleanup_button.on_click = open_backup_cleanup_confirmation

    def progress_callback(event: Any) -> None:
        nonlocal last_progress_count
        progress_section.visible = True
        progress_field.visible = True
        progress_details.visible = True
        progress_details.controls[0].expanded = True
        progress_summary.visible = False
        last_progress_count = (event.get("current_stage_number", "?"), event.get("total_declared_stages", "?"))
        progress_line = (
            f"[{event.get('current_stage_number', '?')}/{event.get('total_declared_stages', '?')}] "
            f"{event.get('current_stage_id', 'UNKNOWN')} - {event.get('stage_state', 'UNKNOWN')}: "
            f"{event.get('message', '')}"
        )
        render_progress(append=progress_line)
        if hasattr(page, "update"):
            page.update()

    def apply_result(result: AdminUIRunResult) -> None:
        nonlocal current_preview_signature, current_preview_result, current_preview_payload_path
        nonlocal current_preview_fingerprint, current_test_run_id, current_report_run_id, selected_history_run_id
        is_preview = result.mode in {"PREVIEW", "CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "PROTECTED_PRODUCTION_PREVIEW", "ACTIVE_TAXONOMY_PREVIEW"}
        is_workflow = result.mode == "FULL_WORKFLOW"
        status_field.value = _result_text(result)
        final_section.visible = not is_preview or result.status == "FAILED"
        status_field.visible = not is_preview or result.status == "FAILED"
        if result.preview_payload_path:
            current_preview_payload_path = result.preview_payload_path
            preview_payload_field.value = result.preview_payload_path
        if result.preview_fingerprint:
            current_preview_fingerprint = result.preview_fingerprint
            preview_fingerprint_field.value = result.preview_fingerprint
        if is_preview and result.preview_payload_path and result.preview_fingerprint:
            current_preview_signature = current_signature()
            current_preview_result = result
            current_test_run_id = None
        elif result.mode == "COPY_ONLY_APPLY" and result.status == "COMPLETED" and result.outcome == "COMPLETED" and result.preview_fingerprint == current_preview_fingerprint:
            current_test_run_id = result.run_id
        elif is_workflow and result.direct_production_retry_available and result.preview_payload_path and result.preview_fingerprint:
            current_preview_signature = current_signature()
            current_preview_result = AdminUIRunResult(
                status="COMPLETED",
                message="Preview completed.",
                outcome="COMPLETED",
                mode="PREVIEW",
                preview_payload_path=result.preview_payload_path,
                preview_fingerprint=result.preview_fingerprint,
            )
            current_test_run_id = result.test_run_id
        elif is_workflow and result.direct_test_retry_available and result.preview_payload_path and result.preview_fingerprint:
            current_preview_signature = current_signature()
            current_preview_result = AdminUIRunResult(
                status="COMPLETED",
                message="Preview completed.",
                outcome="COMPLETED",
                mode="PREVIEW",
                preview_payload_path=result.preview_payload_path,
                preview_fingerprint=result.preview_fingerprint,
            )
            current_test_run_id = None
        elif result.mode == "PRODUCTION_APPLY" and result.status == "FAILED" and result.direct_production_retry_available:
            current_test_run_id = result.test_run_id or current_test_run_id
        elif not is_preview:
            current_test_run_id = None
            current_preview_signature = None
            current_preview_result = None
            current_preview_payload_path = None
            current_preview_fingerprint = None
            preview_payload_field.value = ""
            preview_fingerprint_field.value = ""
        if (
            result.mode in {"PRODUCTION_APPLY", "FULL_WORKFLOW"}
            and result.status == "COMPLETED"
            and (operation_dropdown.value or "").strip().upper() == "ADD_TICKERS"
        ):
            tickers_field.value = ""
        if result.run_id:
            current_report_run_id = result.run_id
            selected_history_run_id = result.run_id
            report_button.on_click = lambda _event, run_id=result.run_id: _launch_browser_url(
                page,
                admin_report_download_url(run_id, result.report_filename or OPERATION_REPORT_NAME),
            )
            report_button.visible = bool(result.report_filename)
        update_summary(result)
        preview_section.visible = is_preview
        if result.preview_domain and is_preview:
            preview_title.value = {
                "NO_CHANGE": "Taxonomy is up to date",
                "CHANGES_AVAILABLE": "Taxonomy changes available",
                "REVIEW_REQUIRED": "Taxonomy needs review",
                "BLOCKED": "Taxonomy update blocked",
                "FAILED": "Taxonomy preview failed",
            }.get(result.business_outcome, "Taxonomy preview result")
        else:
            preview_title.value = "Preview result" if is_preview else "Result"
        if result.business_outcome == "NO_CHANGE" and result.preview_domain:
            summary_column.controls = [ft.Text("No changes"), *[ft.Text(row) for row in result.summary_rows if row not in {"Taxonomy is up to date", "No changes"}]]
        elif is_preview and result.outcome == "NO_CHANGE":
            preview_title.value = "No changes"
            summary_column.controls = [ft.Text("No update is required.")]
        if progress_section.visible:
            if result.status == "FAILED":
                progress_summary.value = "Operation failed"
            elif last_progress_count:
                progress_summary.value = f"{last_progress_count[0]} of {last_progress_count[1]} stages completed"
            else:
                progress_summary.value = "Preview completed" if is_preview else "Operation completed"
            progress_summary.visible = True
            progress_details.visible = True
            progress_details.controls[0].expanded = True
        refresh_history(force=True)
        technical_details_column.controls = [
            ft.Text(f"Run id: {result.run_id or 'not recorded'}"),
            ft.Text(f"Operation: {(operation_dropdown.value or '').strip()}"),
            ft.Text(f"Execution status: {result.status}; backend outcome: {result.outcome or 'not recorded'}"),
            ft.Text(f"Mode: {result.mode or 'not recorded'}"),
            ft.Text(f"Failure stage: {result.failure_stage or 'not recorded'}"),
            ft.Text(f"Exception type: {result.exception_type or 'not recorded'}"),
            ft.Text(f"Technical error: {result.technical_error or 'not recorded'}"),
            ft.Text(f"Preview fingerprint: {result.preview_fingerprint or 'not recorded'}"),
            ft.Text(f"Artifact directory: {result.artifact_dir or 'not recorded'}"),
            ft.Text(f"Report sha256: {result.report_sha256 or 'not recorded'}"),
        ]

    def apply_capabilities() -> None:
        capability = capability_for_current_operation()
        production_safety_blocked = bool(publication_safety.get("production_writes_blocked"))
        update_operation_visibility()
        preview_button.disabled = bool(operation_running or (capability and not capability.preview_enabled) or not can_preview())
        preview_ready = has_current_preview()
        taxonomy = (operation_dropdown.value or "") == "CHECK_UPDATE_TAXONOMY"
        copy_authorized = bool(getattr(capability, "copy_apply_enabled", False if taxonomy else True))
        production_authorized = bool(getattr(capability, "production_apply_enabled", False if taxonomy else True))
        taxonomy_preview_ok = bool(current_preview_result and current_preview_result.status == "COMPLETED" and current_preview_result.mode == "ACTIVE_TAXONOMY_PREVIEW" and taxonomy_domain_dropdown.value == "dc_ecosystem")
        operation = (operation_dropdown.value or "").strip().upper()
        generic_preview_ok = bool(
            current_preview_result
            and current_preview_result.status == "COMPLETED"
            and (
                current_preview_result.outcome == "COMPLETED"
                if operation == "REFRESH_FUNDAMENTALS"
                else current_preview_result.outcome != "NO_CHANGE"
            )
        )
        if operation == "REMOVE_TICKERS":
            generic_preview_ok = bool(
                generic_preview_ok
                and current_preview_result
                and current_preview_result.copy_actionable is True
            )
        copy_available = bool(preview_ready and ((generic_preview_ok and not taxonomy) or (taxonomy and taxonomy_preview_ok and current_preview_result.copy_actionable is True)))
        copy_ready = bool(copy_available and not current_test_run_id)
        production_ready = bool(current_test_run_id and preview_ready and ((generic_preview_ok and not taxonomy) or (taxonomy and taxonomy_preview_ok and current_preview_result.production_actionable is True)))
        copy_apply_button.visible = bool(copy_authorized and copy_available)
        copy_apply_button.disabled = bool(operation_running or not copy_authorized or not copy_ready)
        production_apply_button.visible = bool(production_authorized and production_ready)
        production_apply_button.disabled = bool(operation_running or production_safety_blocked or not production_authorized or not production_ready)
        full_workflow_button.visible = (operation_dropdown.value or "").strip().upper() in {
            "ADD_TICKERS", "REFRESH_FUNDAMENTALS",
        }
        full_workflow_button.disabled = bool(
            operation_running
            or production_safety_blocked
            or not can_preview()
            or current_preview_signature is not None
        )

    def invalidate_preview(_event: Any | None = None) -> None:
        nonlocal current_preview_signature, current_preview_result, current_preview_payload_path
        nonlocal current_preview_fingerprint, current_test_run_id, current_report_run_id
        if current_preview_signature is not None and current_preview_signature != current_signature():
            current_preview_signature = None
            current_preview_result = None
            current_preview_payload_path = None
            current_preview_fingerprint = None
            current_test_run_id = None
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
        nonlocal operation_running, last_progress_count, progress_follow_latest
        if button.disabled:
            return
        if button is not preview_button:
            last_progress_count = None
        operation_running = True
        button.disabled = True
        preview_button.disabled = True
        copy_apply_button.disabled = True
        production_apply_button.disabled = True
        full_workflow_button.disabled = True
        progress_section.visible = True
        progress_field.visible = True
        progress_follow_latest = True
        render_progress(replace=["Starting..."])
        progress_summary.visible = False
        progress_details.visible = True
        progress_details.controls[0].expanded = True
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
        nonlocal current_preview_signature, current_preview_result, current_preview_payload_path, current_preview_fingerprint, current_test_run_id, last_progress_count
        current_preview_signature = None
        current_preview_result = None
        current_preview_payload_path = None
        current_preview_fingerprint = None
        current_test_run_id = None
        preview_payload_field.value = ""
        preview_fingerprint_field.value = ""
        last_progress_count = None
        run_guarded(
            preview_button,
            lambda: admin_service.preview(
                operation_dropdown.value or "ADD_TICKERS",
                raw_inputs=tickers_field.value or "",
                market=market_field.value or "usa",
                taxonomy_domain=taxonomy_domain_dropdown.value or "dc_ecosystem",
                candidate_path=None,
                candidate_version=None,
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
        if operation == "REMOVE_TICKERS":
            return "CONFIRM_PRODUCTION_REMOVE_TICKERS"
        if operation == "REFRESH_FUNDAMENTALS":
            return "CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS"
        if operation == "CHECK_UPDATE_SECTOR_INDUSTRY":
            return "CONFIRM_PRODUCTION_SECTOR_INDUSTRY"
        if operation == "CHECK_UPDATE_TAXONOMY":
            return "CONFIRM_PRODUCTION_TAXONOMY"
        if operation == "SYNCHRONIZE_PROVIDER_CIK":
            return "CONFIRM_PRODUCTION_PROVIDER_CIK_SYNC"
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
                test_run_id=current_test_run_id or "",
                progress_callback=progress_callback,
            ),
        )

    def on_production_apply(_event: Any) -> None:
        if production_apply_button.disabled:
            return
        open_production_confirmation(_event)

    def on_full_workflow(_event: Any) -> None:
        nonlocal current_preview_signature, current_preview_result, current_preview_payload_path
        nonlocal current_preview_fingerprint, current_test_run_id, last_progress_count
        current_preview_signature = None
        current_preview_result = None
        current_preview_payload_path = None
        current_preview_fingerprint = None
        current_test_run_id = None
        preview_payload_field.value = ""
        preview_fingerprint_field.value = ""
        last_progress_count = None
        run_guarded(
            full_workflow_button,
            lambda: admin_service.full_workflow(
                operation_type=operation_dropdown.value or "ADD_TICKERS",
                raw_inputs=tickers_field.value or "",
                market=market_field.value or "usa",
                progress_callback=progress_callback,
            ),
        )

    preview_button = ft.ElevatedButton("Preview", icon=ft.Icons.PREVIEW, on_click=on_preview)
    copy_apply_button = ft.OutlinedButton("Test on copies", icon=ft.Icons.CHECKLIST, on_click=on_copy_apply, visible=False)
    production_apply_button = ft.ElevatedButton("Production update", icon=ft.Icons.LOCK, on_click=on_production_apply, visible=False)
    full_workflow_button = ft.ElevatedButton("Run full workflow", icon=ft.Icons.PLAY_ARROW, on_click=on_full_workflow)
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
        refresh_history(force=True),
        page.update() if hasattr(page, "update") else None,
    )
    apply_capabilities()
    if not defer_initial_load:
        refresh_history()

    content = ft.Column(
        [
            ft.Text("Fundamentals Administration", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Administration operation", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([operation_dropdown, market_field, taxonomy_domain_dropdown], wrap=True, spacing=12),
            operation_guidance_field,
            publication_safety_field,
            pending_refresh_field,
            ft.Text("Preview checks proposed changes. Test on copies runs them in isolated databases. Production update writes an approved change under the existing safeguards."),
            tickers_field,
            ft.Row([candidate_path_field, candidate_version_field], wrap=True, spacing=12),
            ft.Row([full_workflow_button, preview_button, copy_apply_button, production_apply_button], spacing=12, wrap=True),
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
                    ft.Text("Operation", width=190, weight=ft.FontWeight.BOLD),
                    ft.Text("Stage", width=155, weight=ft.FontWeight.BOLD),
                    ft.Text("Result", width=135, weight=ft.FontWeight.BOLD),
                    ft.Text("Count", width=125, weight=ft.FontWeight.BOLD),
                    ft.Text("Category", width=170, weight=ft.FontWeight.BOLD),
                    ft.Container(width=48),
                    ft.Container(width=48),
                    ft.Container(width=48),
                ]
            ),
            history_column,
            history_show_more_button,
            history_detail_field,
            cleanup_status_field,
            cleanup_button,
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
    def activate() -> None:
        nonlocal publication_safety
        if (
            owns_service
            and defer_initial_load
            and history_loader.state not in {LoadState.LOADING, LoadState.LOADED}
        ):
            publication_safety = {
                "status": "CHECKING",
                "production_writes_blocked": True,
            }
            publication_safety_field.value = "Checking production publication safety..."
            publication_safety_field.visible = True
            apply_capabilities()
        history_loader.start()

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
        full_workflow_button=full_workflow_button,
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
        technical_details_column=technical_details_column,
        progress_summary=progress_summary,
        progress_details=progress_details,
        history_show_more_button=history_show_more_button,
        cleanup_status_field=cleanup_status_field,
        cleanup_button=cleanup_button,
        activate=activate,
        history_loader=history_loader,
    )
