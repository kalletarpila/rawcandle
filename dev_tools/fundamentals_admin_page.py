from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import flet as ft

from dev_tools.deferred_ui import DeferredLoadController, LoadState
from rawcandle.fundamentals.admin.operation_report import OPERATION_REPORT_NAME, WORKFLOW_REPORT_NAME
from rawcandle.fundamentals.admin.review_presentation import (
    provider_review, ownership_review, review_groups, classification_label,
)
from rawcandle.fundamentals.admin.operational_presentation import (
    NORMAL, REVIEW, DEEP_REVIEW, review_route, boundary_route, normal_summary,
)
from rawcandle.fundamentals.admin.recent_history import recent_history_visible, terminal_history_date, RECENT_HISTORY_NOTE
from rawcandle.fundamentals.admin.review_evidence_presentation import provider_card_fields, evidence_summary, decision_label, historical_classification
from rawcandle.fundamentals.admin.run_presentation import source_scan, ACTION_REQUIRED
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
    history_refresh_button: Any
    cleanup_status_field: Any
    cleanup_button: Any
    review_queue_column: Any
    review_queue_status_field: Any
    review_queue_detail_field: Any
    review_queue_include_resolved_checkbox: Any
    review_queue_refresh_button: Any
    review_queue_blocked_actions: Any
    pb_ownership_column: Any
    pb_ownership_status_field: Any
    activate: Any
    history_loader: Any
    operational_summary_field: Any
    normal_workflow_button: Any
    review_section: Any
    deep_review_section: Any
    deep_review_column: Any
    ownership_history_column: Any
    provider_history_column: Any
    accounting_history_column: Any
    selected_review_evidence: Any
    technical_details_section: Any


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
        '\n'.join(source_scan({})['rows']),visible=True,
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
    review_queue_column = ft.Column(spacing=6)
    pb_ownership_column = ft.Column(spacing=6)
    pb_ownership_status_field = ft.Text('Not loaded.')
    operational_summary_field = ft.Text('Fundamentals: status not loaded. Refresh operational status before deciding whether action is required.')
    deep_review_column = ft.Column(spacing=8)
    ownership_history_column = ft.Column(spacing=8)
    provider_history_column = ft.Column(spacing=8)
    accounting_history_column = ft.Column(spacing=8)
    latest_workflow_history = ft.Text('',visible=False)
    selected_review_evidence = ft.ExpansionPanelList(controls=[],visible=False)
    selected_review_summary = ft.Text('')
    selected_review_raw = ft.Text('',selectable=True)
    selected_review_ticker = None
    operational_state = dict(loaded=False, providers=[], owners=[], boundaries=[], settings={}, last=None, error='')
    review_queue_status_field = ft.Text("Not loaded.")
    review_queue_detail_field = ft.TextField(
        label="Selected review item",
        value="Select an item to inspect its persisted evidence.",
        read_only=True,
        multiline=True,
        min_lines=5,
        max_lines=12,
    )
    review_queue_include_resolved_checkbox = ft.Checkbox(label="Include resolved provider history", value=False)
    review_queue_blocked_actions = ft.Row(
        [
            ft.OutlinedButton("Confirm true source removal", icon=ft.Icons.BLOCK, disabled=True),
        ],
        spacing=12,
        wrap=True,
        visible=False,
    )
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
    cleanup_eligibility_cache: dict[str, dict[str, Any]] = {}
    operation_running = False
    running_full_workflow = False
    last_progress_count: tuple[object, object] | None = None
    progress_lines: list[str] = []
    progress_follow_latest = True

    def update_operational_summary() -> None:
        provider_views = [provider_review(item) for item in operational_state['providers']]
        owner_views = operational_state['owners']
        routes = [(view, review_route(view, policy=policy)) for view, policy in owner_views]
        routes += [(view, review_route(view)) for view in provider_views]
        review_count = sum(view.needs_action and route.mode == REVIEW for view, route in routes)
        deep_count = sum(not view.history_or_terminal and route.mode == DEEP_REVIEW for view, route in routes) + len(operational_state['boundaries'])
        review_count += operational_state.get('unregistered_manual',0)
        deep_count += operational_state.get('unregistered_deep',0)
        operational_summary_field.value = '\n'.join(normal_summary(
            loaded=operational_state['loaded'],review_count=review_count,deep_count=deep_count,
            safety=publication_safety,settings=operational_state['settings'],
            last_workflow=operational_state['last'],running=operation_running,error=operational_state['error'],
            pending_reviews=sum(not view.needs_action and not view.history_or_terminal for view in provider_views)))
        deep_review_column.controls = [*operational_state.get('owner_controls', []),
            *operational_state.get('boundary_controls', [])]
        for diagnostic_item in operational_state.get('unregistered_deep_items', []):
            deep_review_column.controls.append(evidence_panel('Current deep source diagnostic','diagnostic',diagnostic_item))
        if publication_safety.get('production_writes_blocked'):
            deep_review_column.controls.append(evidence_panel('Publication / recovery evidence','safety',publication_safety))
        last = operational_state['last'] or {}
        if last.get('mode')==DEEP_REVIEW:
            deep_review_column.controls.append(ft.Text('\n'.join(last.get('rows') or ('Inspect workflow evidence.',))))
        if not deep_review_column.controls:
            deep_review_column.controls = [ft.Text('No deep review action required')]
        latest_workflow_history.value = ('Latest Full Workflow: '+str(last.get('human_summary') or (last.get('rows') or ['Not recorded'])[0])
            + (f" · P/B auto-continuation {last['ownership_status']} · published {last.get('ownership_published','not recorded')}" if last.get('ownership_status') else '')
            + f' · {review_count} current reviews'
            + (' · Action required — see Deep Review / Details' if last.get('mode')==DEEP_REVIEW else '')) if last else ''
        latest_workflow_history.visible = bool(latest_workflow_history.value)

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
        if result.operational_summary and result.operational_summary.get('kind')=='preview':
            summary_column.controls = [ft.Text(row) for row in result.operational_summary['rows']]
            return
        summary_column.controls = [ft.Text(row) for row in result.summary_rows] or [
            ft.Text("No summary rows recorded.")
        ]

    def cleanup_eligibility_state(run_id: str, *, force: bool = False) -> dict[str, Any]:
        if not force and run_id in cleanup_eligibility_cache:
            return cleanup_eligibility_cache[run_id]
        reader = getattr(admin_service, "cleanup_eligibility", None)
        if not callable(reader):
            state = {
                "eligible": False,
                "status": "NOT_SUPPORTED",
                "reason": "Backup cleanup is not available for this run.",
            }
        else:
            try:
                state = dict(reader(run_id, projection_cache=getattr(history_cursor, "projections", None))
                             if not force and "projection_cache" in inspect.signature(reader).parameters else reader(run_id))
            except Exception as exc:
                LOGGER.exception("Administration backup cleanup eligibility failed")
                state = {
                    "eligible": False,
                    "status": "NOT_ELIGIBLE",
                    "reason": str(exc) or "Backup cleanup eligibility is unavailable.",
                }
        cleanup_eligibility_cache[run_id] = state
        return state

    def render_history(entries: Any) -> None:
        rows = []
        for item in entries:
            run_id = item.run_id
            title = _plain_status(item.outcome)
            meaning = getattr(item,'operational_meaning',None)
            if meaning:
                title += '\n'+meaning['meaning']+'\n'+('ACTION REQUIRED · ' if meaning['category']==ACTION_REQUIRED else '')+'Action: '+meaning['action']
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
            row_controls = [
                ft.Text(when, width=185, weight=weight),
                ft.Text(operation_label, width=190, weight=weight),
                ft.Text(item.stage, width=155, weight=weight),
                ft.Text(title, width=280, weight=weight,tooltip='Backend outcome: '+item.outcome),
                ft.Text(count_text, width=125, weight=weight),
                ft.Text(category, width=170, tooltip=f"run_id={item.run_id}; mode={item.mode}" + (
                    f"; workflow_parent={item.workflow_parent_run_id}; scheduler_provenance="
                    + ("inherited" if item.provenance_inherited else "stored")
                    if getattr(item, "workflow_parent_run_id", None) else ""
                )),
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
            ]
            if ((item.stage == "Production update" and item.outcome == "COMPLETED")
                    or (item.mode == "FULL_WORKFLOW" and item.operation_type == "REFRESH_FUNDAMENTALS")):
                cleanup_state = cleanup_eligibility_state(run_id)
                if cleanup_state.get("eligible"):
                    row_controls.append(
                        ft.IconButton(
                            icon=ft.Icons.DELETE_SWEEP,
                            tooltip="Accept run and cleanup backups",
                            on_click=lambda _event, selected_run_id=run_id: (
                                open_backup_cleanup_confirmation(_event, selected_run_id)
                            ),
                        )
                    )
                elif cleanup_state.get("status") == "ALREADY_CLEANED":
                    row_controls.append(
                        ft.IconButton(
                            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                            tooltip="Backups cleaned",
                            disabled=True,
                        )
                    )
            rows.append(
                ft.Row(
                    row_controls,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        history_column.controls = rows or [ft.Text("No administration runs found.")]
        history_show_more_button.visible = bool(
            history_cursor is not None and not getattr(history_cursor, "exhausted", True)
        )

    def review_item_details(item: dict[str, Any]) -> str:
        reasons = item.get("reason_explanations") or item.get("reason_codes") or []
        fiscal = []
        for identity in item.get("fiscal_identities") or []:
            if isinstance(identity, dict):
                old = identity.get("old_fiscal_identity") or identity
                current = identity.get("current_fiscal_identity") or identity
                source = identity.get("source_identity") or {}
                proof = identity.get("arq_companion_identity_proof") or {}
                fiscal.append(
                    f"{identity.get('dimension') or source.get('dimension') or '?'} "
                    f"{old.get('fiscal_year', '?')} {old.get('fiscal_quarter', '?')} -> "
                    f"{current.get('fiscal_year', '?')} {current.get('fiscal_quarter', '?')} "
                    f"({source.get('reportperiod') or source.get('date') or '?'}, "
                    f"financial payload changed: {identity.get('financial_payload_changed', '?')}, "
                    f"ARQ companion: {proof.get('status') or '?'})"
                )
            else:
                fiscal.append(str(identity))
        source_keys = []
        for source in item.get("affected_source_keys") or []:
            if isinstance(source, dict):
                source_keys.append(
                    " / ".join(
                        str(source.get(key) or "?")
                        for key in ("ticker", "dimension", "date", "reportperiod")
                    )
                )
            else:
                source_keys.append(str(source))
        resolution = item.get("resolution_evidence") or {}
        consumed_run = item.get("approval_consumed_run_id")
        consumed_suffix = f" ({consumed_run})" if consumed_run else ""
        return "\n".join(
            [
                f"Ticker: {item.get('ticker', 'UNKNOWN')}",
                f"Status: {item.get('operator_status_label') or item.get('status', 'UNKNOWN')}",
                f"Scope: {item.get('review_scope', 'TICKER_LOCAL_REVIEW')}",
                f"Classification: {item.get('classification', 'UNKNOWN')}",
                f"Technical reason codes: {', '.join(str(value) for value in item.get('reason_codes') or [])}",
                f"Next action: {provider_review(item).next_action}",
                provider_review(item).blocked_action_reason,
                f"Summary: {item.get('human_summary', 'No additional explanation is available.')}",
                f"Reasons: {'; '.join(str(value) for value in reasons) or 'None recorded'}",
                f"Affected fiscal identities ({len(fiscal)}): {', '.join(fiscal) or 'None recorded'}",
                "Affected source keys "
                f"({len(source_keys)}): {', '.join(source_keys) or 'None recorded'}",
                f"First seen: {item.get('first_seen_at_utc') or 'not recorded'} "
                f"({item.get('first_seen_run_id') or 'run not recorded'})",
                f"Last seen: {item.get('last_seen_at_utc') or 'not recorded'} "
                f"({item.get('last_seen_run_id') or 'run not recorded'})",
                f"Published binding: {item.get('last_published_binding') or 'not recorded'}",
                f"Evidence fingerprint: {item.get('source_evidence_fingerprint') or 'not recorded'}",
                f"Operator action: {item.get('operator_action') or 'none'}",
                f"Approval timestamp: {item.get('approval_timestamp_utc') or 'not approved'}",
                f"Approved source rows: {item.get('approved_source_count') or 0}",
                "Approval evidence fingerprint: "
                f"{item.get('approval_evidence_fingerprint') or 'not approved'}",
                "Approval consumed: "
                f"{'yes' if item.get('approval_consumed') else 'no'}"
                f"{consumed_suffix}",
                f"Operator evidence: {item.get('approval_operator_evidence') or 'none'}",
                f"Resolution evidence: {resolution or 'none'}",
            ]
        )

    def select_review_item(item: dict[str, Any]) -> None:
        nonlocal selected_review_ticker
        selected_review_ticker = str(item.get('ticker') or 'Unknown')
        review_queue_detail_field.value = review_item_details(item)
        selected_review_summary.value = '\n'.join(evidence_summary('provider',item))
        selected_review_raw.value = json.dumps(item,indent=2,sort_keys=True,default=str)
        selected_review_evidence.controls[0].header.title.value = 'Evidence for '+selected_review_ticker
        selected_review_evidence.visible = True
        selected_review_evidence.controls[0].expanded = True
        if hasattr(page, "update"):
            page.update()

    def apply_review_action(
        ticker: str,
        action: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        try:
            admin_service.resolve_refresh_review(
                ticker,
                action,
                evidence=evidence or {"source": "FUNDAMENTALS_ADMIN_UI"},
            )
            refresh_review_queue()
        except Exception:
            LOGGER.exception("Refresh review queue action failed")
            review_queue_status_field.value = f"Could not apply {action} to {ticker}."
            if hasattr(page, "update"):
                page.update()

    def open_retained_history_confirmation(item: dict[str, Any]) -> None:
        if not item.get("accept_retained_history_eligible"):
            review_queue_status_field.value = str(
                item.get("accept_retained_history_reason")
                or "Retained-history approval is not eligible."
            )
            if hasattr(page, "update"):
                page.update()
            return
        ticker = str(item.get("ticker") or "UNKNOWN")
        comment = ft.TextField(
            label="Operator comment (optional)",
            max_length=240,
            multiline=True,
            min_lines=1,
            max_lines=3,
        )

        def confirm(_event: Any) -> None:
            close_dialog()
            apply_review_action(
                ticker,
                "ACCEPT_RETAINED_HISTORY",
                evidence={
                    "source": "FUNDAMENTALS_ADMIN_UI",
                    "comment": str(comment.value or "").strip(),
                },
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Accept retained history?"),
            content=ft.Column(
                [
                    ft.Text(
                        f"Ticker: {ticker}\n"
                        f"Affected source rows: {item.get('affected_source_count') or 0}\n"
                        f"Classification: {item.get('classification') or 'UNKNOWN'}\n"
                        "\n"
                        "Preserve these exact previously published historical observations "
                        "if the next Preview sees the same missing-source evidence."
                    ),
                    comment,
                    evidence_panel('Exact retained-history evidence','provider',item),
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _event: close_dialog()),
                ft.ElevatedButton(
                    "Accept retained history",
                    icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                    on_click=confirm,
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

    def open_fiscal_revision_confirmation(item: dict[str, Any]) -> None:
        if not item.get("accept_fiscal_revision_eligible"):
            review_queue_status_field.value = str(
                item.get("accept_fiscal_revision_reason")
                or "Fiscal-revision approval is not eligible."
            )
            if hasattr(page, "update"):
                page.update()
            return
        ticker = str(item.get("ticker") or "UNKNOWN")
        events = item.get("fiscal_revision_events") or []
        event_lines = []
        for event in events:
            old = event.get("old_fiscal_identity") or {}
            current = event.get("current_fiscal_identity") or {}
            source = event.get("source_identity") or {}
            proof = event.get("arq_companion_identity_proof") or {}
            event_lines.append(
                f"{event.get('dimension') or '?'} {source.get('reportperiod') or source.get('date') or '?'}: "
                f"{old.get('fiscal_year', '?')} {old.get('fiscal_quarter', '?')} -> "
                f"{current.get('fiscal_year', '?')} {current.get('fiscal_quarter', '?')}; "
                f"financial payload changed: {event.get('financial_payload_changed', '?')}; "
                f"ARQ companion: {proof.get('status') or '?'}"
            )
        comment = ft.TextField(label="Operator comment (optional)", max_length=240, multiline=True, min_lines=1, max_lines=3)

        def confirm(_event: Any) -> None:
            close_dialog()
            apply_review_action(
                ticker,
                "ACCEPT_FISCAL_IDENTITY_REVISION",
                evidence={"source": "FUNDAMENTALS_ADMIN_UI", "comment": str(comment.value or "").strip()},
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Accept fiscal revision?"),
            content=ft.Column([
                ft.Text(
                    f"Ticker: {ticker}\nFiscal revision events: {len(events)}\n"
                    f"Review reason: {item.get('classification') or 'UNKNOWN'}\n"
                    + "\n".join(event_lines)
                    + "\n\nThis does not modify Production immediately. The next Refresh will re-fetch "
                    "and revalidate source evidence. Publication occurs only through normal "
                    "Preview -> Test -> Production. Any evidence drift invalidates this approval."
                ),
                comment,
            ], tight=True),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _event: close_dialog()),
                ft.ElevatedButton("Accept fiscal revision", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, on_click=confirm),
            ],
        )
        setattr(page, "dialog", dialog)
        if hasattr(page, "open"):
            page.open(dialog)
        else:
            dialog.open = True
        if hasattr(page, "update"):
            page.update()

    def open_true_removal_confirmation(item: dict[str, Any]) -> None:
        if not item.get("confirm_true_removal_eligible"):
            review_queue_status_field.value = str(
                item.get("confirm_true_removal_reason")
                or "True source removal confirmation is not eligible."
            )
            if hasattr(page, "update"):
                page.update()
            return
        ticker = str(item.get("ticker") or "UNKNOWN")
        source_keys = item.get("true_removal_source_keys") or []
        provider_evidence = item.get("true_removal_provider_evidence") or []
        key_lines = [
            " / ".join(
                str(key.get(field) or "?")
                for field in ("ticker", "dimension", "date", "reportperiod")
            )
            for key in source_keys if isinstance(key, dict)
        ]
        fiscal_lines = [
            f"{value.get('fiscal_year', '?')} {value.get('fiscal_quarter', '?')}"
            for value in item.get("fiscal_identities") or []
            if isinstance(value, dict)
        ]
        evidence_lines = [
            f"{(value.get('source_identity') or {}).get('dimension', '?')}: "
            f"status={(value.get('provider_absence_proof') or {}).get('source_response_status', '?')}, "
            f"absent={(value.get('provider_absence_proof') or {}).get('absent_from_complete_source', '?')}, "
            f"rows={(value.get('provider_absence_proof') or {}).get('complete_source_row_count', '?')}"
            for value in provider_evidence if isinstance(value, dict)
        ]
        comment = ft.TextField(
            label="Operator comment (optional)", max_length=240,
            multiline=True, min_lines=1, max_lines=3,
        )

        def confirm(_event: Any) -> None:
            close_dialog()
            apply_review_action(
                ticker,
                "CONFIRM_TRUE_SOURCE_REMOVAL",
                evidence={
                    "source": "FUNDAMENTALS_ADMIN_UI",
                    "comment": str(comment.value or "").strip(),
                },
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm true source removal?"),
            content=ft.Column([
                ft.Text(
                    f"Ticker: {ticker}\n"
                    f"Exact source keys ({len(key_lines)}): {', '.join(key_lines)}\n"
                    f"Affected fiscal quarters: {', '.join(fiscal_lines) or 'none'}\n"
                    "Changes financial history: "
                    f"{'YES' if item.get('true_removal_changes_financial_history') else 'NO'}\n"
                    f"Complete-provider absence evidence: {'; '.join(evidence_lines)}\n\n"
                    "Successful future Production may delete these exact accepted "
                    "source observations from the published provider generation. "
                    "Preview, Test, and Production will revalidate the evidence; "
                    "any drift invalidates this confirmation."
                ),
                comment,
            ], tight=True),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _event: close_dialog()),
                ft.ElevatedButton(
                    "Confirm removal", icon=ft.Icons.DELETE_OUTLINE,
                    on_click=confirm,
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

    def review_history(title: str, controls: list[Any], *, show_count: bool = True, recent_only: bool = False) -> Any:
        return ft.ExpansionPanelList(controls=[ft.ExpansionPanel(
            header=ft.ListTile(title=ft.Text(f"{title}{' — visible recent cases' if recent_only else ''} ({len(controls)})" if show_count else title),
                               subtitle=ft.Text(RECENT_HISTORY_NOTE) if recent_only else None),
            content=ft.Column(controls, spacing=8), expanded=False,
        )])

    def evidence_panel(title: str, kind: str, item: dict[str,Any], *, raw=None, view=None) -> Any:
        return review_history(title,[ft.Text('\n'.join(evidence_summary(kind,item,view=view))),
            review_history('Raw technical evidence / JSON',[ft.Text(json.dumps(item if raw is None else raw,indent=2,sort_keys=True,default=str),selectable=True)],show_count=False)],show_count=False)

    def render_review_queue(items: list[dict[str, Any]]) -> None:
        nonlocal selected_review_ticker
        rows, historical_rows = [], []
        current, historical = review_groups(items, provider_review)
        historical = [(item,view) for item,view in historical if recent_history_visible(item,kind='provider')]
        for item, view in [*current, *historical]:
            ticker = str(item.get("ticker") or "UNKNOWN")
            status_lines = [str(
                item.get("operator_status_label") or view.display_status
            )]
            if item.get("operator_action"):
                status_lines.append(str(item["operator_action"]))
            if item.get("reevaluation_pending") and not item.get(
                "approval_pending_publication"
            ):
                status_lines.append("Reevaluation pending")
            (historical_rows if view.history_or_terminal else rows).append(
                ft.Row(
                    [
                        ft.Text(ticker, width=65, weight=ft.FontWeight.BOLD),
                        ft.Text("\n".join(status_lines), width=125),
                        ft.Text(
                            ('Historical: ' if view.history_or_terminal else '') + classification_label(view.classification),
                            width=170,
                            tooltip=None,
                        ),
                        ft.Column([ft.Text(line) for line in provider_card_fields(item,view)],width=500,spacing=2),
                        ft.Text(
                            str(item.get('first_seen_at_utc') or 'not recorded'),
                            width=145,
                            tooltip=str(item.get('first_seen_run_id') or 'run not recorded'),
                            visible=False,
                        ),
                        ft.Text(
                            str(item.get('last_seen_at_utc') or 'not recorded'),
                            width=145,
                            tooltip=str(item.get('last_seen_run_id') or 'run not recorded'),
                            visible=False,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.INFO,
                            tooltip="View persisted review evidence",
                            on_click=lambda _event, selected=dict(item): select_review_item(selected),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.HOURGLASS_EMPTY,
                            tooltip="Wait for Providers",
                            disabled='WAIT_FOR_PROVIDER' not in view.allowed_actions,
                            visible='WAIT_FOR_PROVIDER' in view.allowed_actions,
                            on_click=lambda _event, selected=ticker: apply_review_action(
                                selected, "WAIT_FOR_PROVIDER"
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            tooltip="Retry reevaluation",
                            disabled='RETRY_REEVALUATION' not in view.allowed_actions,
                            visible='RETRY_REEVALUATION' in view.allowed_actions,
                            on_click=lambda _event, selected=ticker: apply_review_action(
                                selected, "RETRY_REEVALUATION"
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                            tooltip=(
                                "Accept exact retained-history evidence"
                                if item.get("accept_retained_history_eligible")
                                else str(
                                    item.get("accept_retained_history_reason")
                                    or "Retained-history approval unavailable"
                                )
                            ),
                            disabled=not bool(
                                item.get("accept_retained_history_eligible")
                            ),
                            visible='ACCEPT_RETAINED_HISTORY' in view.allowed_actions,
                            on_click=lambda _event, selected=dict(item): (
                                open_retained_history_confirmation(selected)
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.RULE,
                            tooltip=(
                                "Accept fiscal revision"
                                if item.get("accept_fiscal_revision_eligible")
                                else str(item.get("accept_fiscal_revision_reason") or "Fiscal-revision approval unavailable")
                            ),
                            disabled=not bool(item.get("accept_fiscal_revision_eligible")),
                            visible='ACCEPT_FISCAL_IDENTITY_REVISION' in view.allowed_actions,
                            on_click=lambda _event, selected=dict(item): open_fiscal_revision_confirmation(selected),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip=(
                                "Confirm exact true source removal"
                                if item.get("confirm_true_removal_eligible")
                                else str(item.get("confirm_true_removal_reason") or "True source removal confirmation unavailable")
                            ),
                            disabled=not bool(item.get("confirm_true_removal_eligible")),
                            visible='CONFIRM_TRUE_SOURCE_REMOVAL' in view.allowed_actions,
                            on_click=lambda _event, selected=dict(item): open_true_removal_confirmation(selected),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,wrap=True,spacing=8,run_spacing=8,
                )
            )
        provider_history_column.controls = [review_history('Resolved / provider history',historical_rows,recent_only=True)] if historical_rows else []
        provider_history_column.visible = bool(historical_rows)
        if selected_review_ticker and not any(item.get('ticker')==selected_review_ticker for item,_ in [*current,*historical]):
            selected_review_ticker = None
            selected_review_evidence.visible = False
        elif selected_review_ticker:
            select_review_item(next(dict(item) for item,_ in [*current,*historical] if item.get('ticker')==selected_review_ticker))
        review_queue_column.controls = rows or [ft.Text("No action required.")]

    def open_pb_ownership_review(item: dict[str, Any], *, hold: bool = False) -> None:
        try:
            effect = None if hold else admin_service.preview_pb_ownership_review(
                item['case_id'], candidate_hash=item['candidate_hash'])
        except Exception as exc:
            pb_ownership_status_field.value = f'Review preview stopped: {exc}'
            if hasattr(page, 'update'):
                page.update()
            return
        operator = ft.TextField(label='Operator name (optional)', value='')
        note = ft.TextField(label='Hold reason' if hold else 'Quarterly basis review note (optional)', value='', multiline=True)
        confirmed = ft.Checkbox(label='I confirm this exact quarterly observation and the displayed ownership interpretation.', value=False)
        text = f"{item['ticker']} · {item['new']['fiscal_year']}-{item['new']['fiscal_quarter']}"
        if effect:
            hypothetical = effect.get('hypothetical_current') or {}
            text += (f"\nPrior reviewed Current P/B reference: {effect.get('prior_current_reference', {}).get('reason')} (as of {effect.get('prior_reference_as_of')})\n"
                     f"Held Current P/B: {effect['held_current']['reason']}\n"
                     f"Hypothetical approved P/B: {hypothetical.get('value')} ({hypothetical.get('reason')})\n"
                     f"New shares: {item['new']['sharesbas']} · Price: {hypothetical.get('price')}\n"
                     f"New parent equity: {item['new']['parent_equity_usd']}\n"
                     'Approval prepares evidence and an inactive candidate. Controlled publication is still required.')

        def confirm(_event: Any) -> None:
            try:
                if hold:
                    admin_service.hold_pb_ownership_review(item['case_id'], candidate_hash=item['candidate_hash'], note=str(note.value or ''))
                    pb_ownership_status_field.value = 'Quarterly ownership review kept on hold.'
                else:
                    if confirmed.value is not True:
                        raise ValueError('Explicit confirmation required')
                    result = admin_service.approve_pb_ownership_review(item['case_id'], candidate_hash=item['candidate_hash'],
                        operator=str(operator.value or ''), note=str(note.value or ''), confirmed=True)
                    pb_ownership_status_field.value = f"Approved pending controlled publication. Candidate: {result['candidate_canonical']}"
                close_dialog()
                load_pb_ownership_reviews()
            except Exception as exc:
                pb_ownership_status_field.value = f'Quarterly ownership action stopped: {exc}'
            if hasattr(page, 'update'):
                page.update()

        button = ft.ElevatedButton('Keep on hold' if hold else 'Approve quarterly ownership continuation', on_click=confirm, disabled=True)

        def enable(_event: Any) -> None:
            button.disabled = not (str(note.value or '').strip() if hold else confirmed.value is True)
            if hasattr(page, 'update'):
                page.update()
        operator.on_change = note.on_change = confirmed.on_change = enable
        dialog = ft.AlertDialog(modal=True, title=ft.Text('Keep quarterly ownership on hold?' if hold else 'Approve quarterly ownership continuation?'),
            content=ft.Column([ft.Text(text), *([] if hold else [operator, confirmed]), note,
                evidence_panel('Exact observation evidence','ownership',item)], tight=True),
            actions=[ft.TextButton('Cancel', on_click=lambda _event: close_dialog()), button])
        setattr(page, 'dialog', dialog)
        if hasattr(page, 'open'):
            page.open(dialog)
        else:
            dialog.open = True
        if hasattr(page, 'update'):
            page.update()

    def open_pb_ownership_publication(item: dict[str, Any]) -> None:
        try:
            preview = admin_service.preview_pb_ownership_publication([item['case_id']])
        except Exception as exc:
            pb_ownership_status_field.value = f'Ownership publication preview stopped: {exc}'
            if hasattr(page, 'update'):
                page.update()
            return
        comparisons = preview['comparisons']
        lines = [f"Selected approved cases: {len(preview['selection'])}"]
        for result in comparisons:
            a,b = result['before'],result['candidate']
            lines.append(f"{result['ticker']}: Current P/B {a['value']} ({a['reason']}) → {b['value']} ({b['reason']})")
        lines.append('Production publication: APPROVED → PUBLISHED after successful postflight. This is a separate decision from ownership approval.')
        operator = ft.TextField(label='Publishing operator', value='')
        confirmation = ft.Checkbox(label='I explicitly confirm Production publication of this selected approved ownership review.', value=False)

        def publish(_event: Any) -> None:
            try:
                if confirmation.value is not True or not str(operator.value or '').strip():
                    raise ValueError('Explicit Production confirmation and operator required')
                result = admin_service.publish_pb_ownership_reviews(preview['preview_id'],preview_hash=preview['preview_hash'],
                    operator=str(operator.value),confirmed=True)
                pb_ownership_status_field.value = f"Ownership publication: {result['outcome']} · {result['generation_id']}"
                close_dialog()
                load_pb_ownership_reviews()
            except Exception as exc:
                pb_ownership_status_field.value = f'Ownership publication stopped: {exc}'
            if hasattr(page, 'update'):
                page.update()
        button = ft.ElevatedButton('Publish approved P/B ownership reviews', disabled=True, on_click=publish)
        def enable(_event: Any) -> None:
            button.disabled = not (confirmation.value is True and str(operator.value or '').strip())
            if hasattr(page, 'update'):
                page.update()
        operator.on_change = confirmation.on_change = enable
        dialog = ft.AlertDialog(modal=True,title=ft.Text('Confirm Production ownership publication'),
            content=ft.Column([ft.Text('\n'.join(lines)),operator,confirmation,
                evidence_panel('Publication evidence','publication',preview)],tight=True,scroll=ft.ScrollMode.AUTO),
            actions=[ft.TextButton('Cancel',on_click=lambda _e:close_dialog()),button])
        setattr(page,'dialog',dialog)
        if hasattr(page,'open'):
            page.open(dialog)
        else:
            dialog.open=True
        if hasattr(page,'update'):
            page.update()

    def load_pb_ownership_reviews() -> None:
        reader = getattr(admin_service, 'list_pb_ownership_reviews', None)
        if not callable(reader):
            return
        try:
            # History is read-only and always available under a collapsed group.
            items = reader(include_resolved=True)
            diagnostics=getattr(admin_service,'pb_ownership_auto_diagnostics',None)
            policy_items={};diagnostic=None
            if callable(diagnostics):
                diagnostic=diagnostics()
                policy_items={v['case']['case_id']:v for v in diagnostic['items']}
            enabled = diagnostic['enabled'] if diagnostic else None
            current, historical = review_groups(items, lambda item: ownership_review(item, policy_items.get(item['case_id']), policy_enabled=enabled))
            historical = [(item,view) for item,view in historical if recent_history_visible(item,kind='ownership')]
            operational_state['owners'] = [(view,policy_items.get(item['case_id'])) for item,view in current]
            if diagnostic:
                operational_state['settings']['ownership_enabled'] = diagnostic['enabled']
            rows, history_rows, deep_rows = [], [], []
            for raw, view in [*current, *historical]:
                item=dict(raw);auto_policy=policy_items.get(item['case_id'])
                approval=item.get('approval') or {}
                decision=approval.get('decision_type') or (approval.get('record') or {}).get('approval_mode')
                description=(f"{item['ticker']} · Status: {view.display_status}\n"
                    f"{'Historical classification' if view.history_or_terminal else 'Classification'}: {classification_label(view.classification)}\nReason: {view.reason}\n"
                    f"Action required: {'YES / REVIEW' if view.needs_action else 'No'}\nNext action: {view.next_action}")
                if decision:description += '\nDecision: '+str(decision)
                if view.next_action_explanation:description += '\n'+view.next_action_explanation
                if view.blocked_action_reason:description += '\n'+view.blocked_action_reason
                if auto_policy and auto_policy.get('warnings'):
                    description += '\nWarnings: '+'; '.join(str(w).replace('_',' ').capitalize() for w in auto_policy['warnings'])
                actions=[]
                if 'APPROVE_OWNERSHIP' in view.allowed_actions:
                    actions.append(ft.ElevatedButton('Approve quarterly ownership continuation', on_click=lambda _e,case=item:open_pb_ownership_review(case)))
                if 'KEEP_ON_HOLD' in view.allowed_actions:
                    actions.append(ft.TextButton('Keep on hold',on_click=lambda _e,case=item:open_pb_ownership_review(case,hold=True)))
                if 'PREVIEW_PUBLICATION' in view.allowed_actions:
                    actions.append(ft.ElevatedButton('Publish approved P/B ownership reviews',on_click=lambda _e,case=item:open_pb_ownership_publication(case)))
                evidence={'stored_review':item}
                if auto_policy:evidence['current_policy']={k:v for k,v in auto_policy.items() if k not in ('case','ticker')}
                details=evidence_panel('Evidence / technical details','ownership',item,raw=evidence,view=view)
                card=ft.Column([ft.Text(description), *([ft.Row(actions,wrap=True)] if actions else []), details])
                if view.history_or_terminal:
                    day=terminal_history_date(item,kind='ownership')
                    label=decision_label(item) if item['status']=='PUBLISHED' else historical_classification(view.classification)
                    card=ft.Column([ft.Text(f"{item['ticker']} · {item['status']} · {label} · {day or 'Date not established'}"),details],spacing=2)
                (history_rows if view.history_or_terminal else deep_rows if review_route(view,policy=auto_policy).mode==DEEP_REVIEW else rows).append(card)
            operational_state['owner_controls'] = deep_rows
            attention=sum(view.needs_action for _,view in current)
            if attention:
                headline=f'Needs your attention ({attention})'
            elif current:
                headline=f'No manual action required now · {len(current)} current review(s) awaiting normal workflow'
            else:
                headline='No action required' if diagnostic else 'No current ownership queue items; policy diagnostics unavailable'
            if diagnostic:
                diagnostic_count=sum(diagnostic[k] for k in ('auto_continue','manual_review','deep_review'))
                queued_ids={item['case_id'] for item in items}
                missing_policy=[p for p in diagnostic['items'] if p['case']['case_id'] not in queued_ids]
                operational_state['unregistered_manual'] = sum(p['partition']=='MANUAL_REVIEW' for p in missing_policy)
                operational_state['unregistered_deep'] = sum(p['partition']=='DEEP_REVIEW/BLOCKED' for p in missing_policy)
                operational_state['unregistered_deep_items'] = [p for p in missing_policy if p['partition']=='DEEP_REVIEW/BLOCKED']
                missing_count=len(missing_policy) or (diagnostic_count if not current else 0)
                if missing_count:
                    if current:
                        headline += f'\n{missing_count} additional current source case(s) have no matching persisted queue row; inspect diagnostics'
                    elif enabled is True and missing_policy and all(p['partition']=='AUTO_CONTINUE' for p in missing_policy):
                        headline=f'No manual action required now · {missing_count} source case(s) awaiting normal workflow reconciliation'
                    else:
                        headline=f'Needs attention: {missing_count} source policy case(s); inspect current diagnostics and reload reviews'
                    rows.append(ft.Text('Current source diagnostics have no matching persisted queue rows. No approval controls are enabled for these unregistered diagnostic cases.'))
                    rows.append(review_history('Current policy diagnostics', [evidence_panel('Policy diagnostic','diagnostic',p) for p in (missing_policy or diagnostic['items'])]))
                headline += (f"\nAutomatic continuation {'enabled' if diagnostic['enabled'] else 'disabled'} · {diagnostic['policy_version']}"
                             f"\nautomatic {diagnostic['auto_continue']} / manual {diagnostic['manual_review']} / deep {diagnostic['deep_review']}")
            ownership_history_column.controls = [review_history('Ownership history / audit',history_rows,recent_only=True)] if history_rows else []
            ownership_history_column.visible = bool(history_rows)
            if deep_rows:headline += f'\nDeep Review: {len(deep_rows)} current ownership case(s); see Deep Review / evidence'
            pb_ownership_column.controls=rows
            pb_ownership_status_field.value=headline
        except Exception as exc:
            pb_ownership_status_field.value = f'Quarterly ownership queue could not be loaded: {exc}'
            operational_state['error'] = 'Ownership status unavailable; inspect Details and refresh status.'
        finally:
            update_operational_summary()

    def refresh_review_queue(_event: Any | None = None) -> None:
        operational_state['error'] = ''
        review_queue_refresh_button.disabled = True
        review_queue_status_field.value = "Loading review queue..."
        if hasattr(page, "update"):
            page.update()
        try:
            reader = getattr(admin_service, "list_refresh_review_queue", None)
            if callable(reader):
                payload = dict(reader(active_only=not bool(review_queue_include_resolved_checkbox.value)))
            else:
                legacy_reader = getattr(admin_service, "refresh_review_queue")
                items = legacy_reader(include_resolved=bool(review_queue_include_resolved_checkbox.value))
                payload = {"status": "READY" if items else "EMPTY", "items": items}
            status = str(payload.get("status") or "ERROR")
            items = [dict(item) for item in payload.get("items") or []]
            operational_state['providers'] = items
            operational_state['loaded'] = status in ('READY','EMPTY')
            render_review_queue(items)
            boundary_reader = getattr(admin_service, "list_accounting_boundary_reviews", None)
            boundary_items = boundary_reader() if callable(boundary_reader) else []
            active_boundary = [item for item in boundary_items if boundary_route(item).mode==DEEP_REVIEW]
            completed_boundary = [item for item in boundary_items if boundary_route(item).mode!=DEEP_REVIEW]
            operational_state['boundaries'] = active_boundary
            operational_state['boundary_controls'] = [ft.Column([ft.Text('Accounting-boundary review — '+str(item.get('status'))),
                evidence_panel('Accounting-boundary evidence','boundary',item)]) for item in active_boundary]
            accounting_history_column.controls = [review_history('Accounting-boundary history / audit',
                [evidence_panel(str(item.get('status'))+' · accounting-boundary evidence','boundary',item) for item in completed_boundary])] if completed_boundary else []
            accounting_history_column.visible = bool(completed_boundary)
            empty_message = (
                "No Refresh review items are currently quarantined."
                if not review_queue_include_resolved_checkbox.value
                else "No Refresh review items have been recorded."
            )
            if active_boundary:
                status = "READY"
            if status == "EMPTY":
                review_queue_column.controls = [ft.Text(empty_message)]
            views=[provider_review(item) for item in items]
            attention=sum(view.needs_action for view in views)
            current_count=sum(not view.history_or_terminal for view in views)
            ready_message=(f'Needs your attention ({attention})' if attention else
                           f'No action required now · {current_count} waiting/pending review(s)' if current_count else 'No action required')
            if active_boundary:ready_message += f' · {len(active_boundary)} accounting-boundary review(s), see Deep Review'
            status_message = {
                "NOT_INITIALIZED": "Review queue has not been initialized.",
                "EMPTY": empty_message,
                "READY": ready_message,
            }.get(status, str(payload.get("error") or "Review queue could not be loaded."))
            review_queue_status_field.value = status_message
            if status in {"NOT_INITIALIZED", "ERROR"}:
                review_queue_column.controls = [ft.Text(status_message)]
                operational_state['error'] = status_message
        except Exception:
            LOGGER.exception("Refresh review queue load failed")
            review_queue_column.controls = []
            review_queue_status_field.value = "Review queue could not be loaded."
            operational_state['loaded'] = False
            operational_state['error'] = 'Review queue could not be loaded.'
        finally:
            load_pb_ownership_reviews()
            update_operational_summary()
            review_queue_refresh_button.disabled = False
            if hasattr(page, "update"):
                page.update()

    review_queue_refresh_button = ft.IconButton(
        icon=ft.Icons.REFRESH,
        tooltip="Load or refresh review queue",
        on_click=refresh_review_queue,
    )
    review_queue_include_resolved_checkbox.on_change = refresh_review_queue

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
        last = next((item for item in entries if item.mode == 'FULL_WORKFLOW' and item.operation_type == 'REFRESH_FUNDAMENTALS'), None)
        last_summary = None
        reader = getattr(admin_service, 'history_operational_summary', None)
        if last and callable(reader):
            try:
                last_summary = reader(last.run_id,projection_cache=getattr(history_cursor,'projections',None))
            except (OSError,ValueError,RuntimeError):
                last_summary = dict(mode=DEEP_REVIEW,rows=('Full Workflow result unavailable; inspect retained history.',))
        if last and last_summary is None:
            last_summary = dict(mode=NORMAL if last.outcome in ('COMPLETED','NO_CHANGE') else REVIEW,
                                rows=(f'Financial workflow: {last.outcome}',),running=last.status=='running')
        if last and last.status == 'running':
            last_summary = dict(mode=NORMAL,rows=('Full Workflow: running',),running=True)
        return {"entries": entries, "pending": pending, "publication_safety": safety, 'last_workflow':last_summary}

    def apply_history(payload: dict[str, Any]) -> None:
        nonlocal publication_safety
        operational_state['last'] = payload.get('last_workflow')
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
            scan = next((getattr(item,'source_scan',None) for item in payload.get('entries') or []
                         if item.operation_type=='REFRESH_FUNDAMENTALS' and item.mode in ('PREVIEW','FULL_WORKFLOW')),None)
            pending_refresh_field.value = '\n'.join((scan or source_scan({}))['rows'])
            pending_refresh_field.visible = True
        else:
            scan = next((getattr(item,'source_scan',None) for item in payload.get('entries') or []
                         if item.operation_type=='REFRESH_FUNDAMENTALS' and item.mode in ('PREVIEW','FULL_WORKFLOW')),None)
            pending_refresh_field.value = '\n'.join((scan or source_scan({}))['rows'])
            pending_refresh_field.visible = True
        render_history(payload.get("entries") or [])
        history_show_more_button.disabled = False
        history_refresh_button.disabled = False
        settings_reader = getattr(admin_service, 'operational_settings', None)
        if callable(settings_reader):
            settings_error = ''
            try:
                operational_state['settings'] = dict(settings_reader())
            except (OSError,ValueError,RuntimeError):
                settings_error = 'Operational settings unavailable.'
            refresh_review_queue()
            if settings_error:
                operational_state['error'] = settings_error
                update_operational_summary()
        else:
            update_operational_summary()

    def history_failed(_exc: Exception) -> None:
        history_column.controls = [ft.Text("Administration history could not be loaded.")]
        history_show_more_button.visible = False
        history_show_more_button.disabled = False
        history_refresh_button.disabled = False
        operational_state['error'] = 'Administration history could not be loaded; refresh status before deciding whether action is required.'
        update_operational_summary()

    def history_loading() -> None:
        history_column.controls = [ft.Text("Loading administration history...")]
        history_show_more_button.disabled = True
        history_refresh_button.disabled = True

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
            cleanup_eligibility_cache.clear()
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
        if history_show_more_button.disabled or (history_cursor is not None and history_cursor.exhausted):
            return
        history_limit += 8
        if defer_initial_load:
            history_loader.start(force=True)
        else:
            refresh_history()
            if hasattr(page,'update'):
                page.update()

    history_show_more_button = ft.TextButton(
        "Show more",
        icon=ft.Icons.EXPAND_MORE,
        on_click=show_more_history,
        visible=False,
    )

    def on_history_refresh(_event: Any) -> None:
        refresh_history(force=True)
        if hasattr(page, "update"):
            page.update()

    history_refresh_button = ft.IconButton(
        icon=ft.Icons.REFRESH,
        tooltip="Refresh run history",
        on_click=on_history_refresh,
    )

    def apply_cleanup_eligibility(run_id: str, *, force: bool = False) -> dict[str, Any]:
        state = cleanup_eligibility_state(run_id, force=force)
        eligible = bool(state.get("eligible"))
        cleanup_button.visible = eligible
        cleanup_button.disabled = not eligible
        cleanup_status_field.value = (
            "Deletes only this accepted run's verified rollback backups. Production data is not changed."
            if eligible
            else str(state.get("reason") or "Backup cleanup is not available for this run.")
        )
        cleanup_status_field.visible = True
        if state.get("workflow_parent_run_id"):
            child = state.get("cleanup_target_run_id")
            cleanup_status_field.value = (
                f"Cleanup target: Production child\nProduction child run: {child or 'unavailable'}\n"
                f"Cleanup status: {state.get('status', 'NOT_ELIGIBLE')}\n"
                f"Rollback backups {'deleted' if state.get('status') == 'ALREADY_CLEANED' else 'retained'}: "
                f"{state.get('backup_count', 0) if eligible or state.get('status') == 'ALREADY_CLEANED' else 'not verified'}\n"
                f"Acceptance required: {'YES' if eligible else 'NO' if state.get('status') == 'ALREADY_CLEANED' else 'unavailable'}\n"
                + str(state.get("reason") or "")
                + (f"\nChild cleanup evidence: {child}/backup_cleanup.json" if state.get("status") == "ALREADY_CLEANED" else "")
            )
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

    def confirm_backup_cleanup(run_id: str, *, workflow_parent_run_id: str | None = None,
                               expected_eligibility: dict[str, Any] | None = None) -> None:
        close_dialog()
        cleanup_button.disabled = True
        cleanup_status_field.value = "Verifying this run's rollback backups..."
        cleanup_status_field.visible = True
        if hasattr(page, "update"):
            page.update()
        try:
            result = (admin_service.accept_run_and_cleanup_backups(
                run_id, workflow_parent_run_id=workflow_parent_run_id, expected_eligibility=expected_eligibility,
            ) if workflow_parent_run_id else admin_service.accept_run_and_cleanup_backups(run_id))
            status = str(result.get("status") or result.get("cleanup_outcome") or "COMPLETED")
            if status == "ALREADY_CLEANED":
                cleanup_status_field.value = "Accepted / backups cleaned"
            else:
                freed = int(result.get("bytes_freed") or 0)
                cleanup_status_field.value = f"Accepted / backups cleaned ({freed / (1024 ** 3):.3f} GiB freed)"
            # Parent and technical child are views of the same child-owned state.
            cleanup_eligibility_cache.clear()
            cleanup_eligibility_cache[run_id] = {
                "run_id": run_id,
                "status": "ALREADY_CLEANED",
                "eligible": False,
                "reason": "Accepted / backups cleaned",
                "backup_count": len(result.get("files_deleted") or []),
                "bytes_freed": int(result.get("bytes_freed") or 0),
            }
            cleanup_button.visible = False
            if selected_history_run_id == run_id:
                cleanup_status_field.visible = True
            if history_cursor is not None:
                render_history(history_cursor.entries[:history_limit])
            if selected_history_run_id and (
                selected_history_run_id == workflow_parent_run_id
                or cleanup_eligibility_cache.get(selected_history_run_id, {}).get("cleanup_target_run_id") == run_id
            ):
                apply_cleanup_eligibility(selected_history_run_id, force=True)
        except Exception as exc:
            LOGGER.exception("Administration backup cleanup failed")
            cleanup_status_field.value = f"Backup cleanup stopped: {exc}"
            cleanup_status_field.visible = True
            cleanup_button.visible = False
            cleanup_button.disabled = True
        if hasattr(page, "update"):
            page.update()

    def open_backup_cleanup_confirmation(_event: Any, selected_run_id: str | None = None) -> None:
        run_id = selected_run_id or selected_history_run_id
        if not run_id:
            return
        state = apply_cleanup_eligibility(run_id, force=True)
        if not state.get("eligible"):
            if hasattr(page, "update"):
                page.update()
            return
        count = int(state.get("backup_count") or 0)
        gib = int(state.get("bytes_freed") or 0) / (1024 ** 3)
        parent_id = state.get("workflow_parent_run_id")
        child_id = state.get("cleanup_target_run_id") if parent_id else run_id
        identity = (f"Full workflow: {parent_id}\nCleanup target: Production child {child_id}\n" if parent_id else f"Run: {run_id}\n")
        evidence = ""
        if parent_id:
            evidence = (f"Eligibility: {state.get('status')}\nExact bytes: {state.get('bytes_freed', 0)}\n"
                        + "\n".join(str(path) for path in state.get("backup_files", [])) + "\n")
            if state.get("terminal_receipt"):
                evidence += "Terminal receipt: " + json.dumps(state["terminal_receipt"], sort_keys=True) + "\n"
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Accept Production run and cleanup backups?"),
            content=ft.Text(
                identity + evidence + "\n"
                f"This removes {count} verified rollback backup file(s), approximately {gib:.3f} GiB.\n"
                "Live Production databases will not be modified."
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _event: close_dialog()),
                ft.ElevatedButton(
                    "Accept and cleanup",
                    icon=ft.Icons.DELETE_SWEEP,
                    on_click=lambda _event: confirm_backup_cleanup(
                        child_id, workflow_parent_run_id=parent_id, expected_eligibility=state,
                    ) if parent_id else confirm_backup_cleanup(run_id),
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
        progress_details.controls[0].expanded = not running_full_workflow
        progress_summary.visible = running_full_workflow
        if running_full_workflow:
            progress_summary.value = f"Full Workflow running · {event.get('current_stage_id','Stage in progress')}"
        last_progress_count = (event.get("current_stage_number", "?"), event.get("total_declared_stages", "?"))
        progress_line = (
            f"[{event.get('current_stage_number', '?')}/{event.get('total_declared_stages', '?')}] "
            f"{event.get('current_stage_id', 'UNKNOWN')} - {event.get('stage_state', 'UNKNOWN')}: "
            f"{event.get('message', '')}"
        )
        render_progress(append=progress_line)
        update_operational_summary()
        if hasattr(page, "update"):
            page.update()

    def apply_result(result: AdminUIRunResult) -> None:
        nonlocal current_preview_signature, current_preview_result, current_preview_payload_path
        nonlocal current_preview_fingerprint, current_test_run_id, current_report_run_id, selected_history_run_id
        is_preview = result.mode in {"PREVIEW", "CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "PROTECTED_PRODUCTION_PREVIEW", "ACTIVE_TAXONOMY_PREVIEW"}
        is_workflow = result.mode == "FULL_WORKFLOW"
        status_field.value = '\n'.join(result.operational_summary['rows']) if result.operational_summary else _result_text(result)
        status_field.max_lines = 12 if is_workflow else 5
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
        elif is_preview and result.outcome == "NO_CHANGE" and not result.operational_summary:
            preview_title.value = "No changes"
            summary_column.controls = [ft.Text("No update is required.")]
        if progress_section.visible:
            if is_workflow and result.operational_summary:
                progress_summary.value = f"Full Workflow finished · financial {result.operational_summary['financial_outcome']} · see result"
            elif result.status == "FAILED":
                progress_summary.value = "Operation failed"
            elif last_progress_count:
                completed_count = (
                    last_progress_count[1]
                    if result.status == "COMPLETED"
                    else last_progress_count[0]
                )
                progress_summary.value = f"{completed_count} of {last_progress_count[1]} stages completed"
            else:
                progress_summary.value = "Preview completed" if is_preview else "Operation completed"
            progress_summary.visible = True
            progress_details.visible = True
            progress_details.controls[0].expanded = not is_workflow
        refresh_history(force=True)
        if is_preview and result.operational_summary and result.operational_summary.get('source_scan'):
            pending_refresh_field.value = '\n'.join(result.operational_summary['source_scan']['rows'])
            pending_refresh_field.visible = True
        if is_workflow and result.operational_summary:
            operational_state['last'] = result.operational_summary
        update_operational_summary()
        technical_details_column.controls = [
            ft.Text('Recorded result: '+result.message),
            *[ft.Text(row) for row in result.summary_rows],
            ft.Text(f"Run id: {result.run_id or 'not recorded'}"),
            ft.Text(f"Operation: {(operation_dropdown.value or '').strip()}"),
            ft.Text(f"Execution status: {result.status}; backend outcome: {result.outcome or 'not recorded'}"),
            ft.Text(f"Mode: {result.mode or 'not recorded'}"),
            ft.Text(f"Failure stage: {result.failure_stage or 'not recorded'}"),
            ft.Text(f"Exception type: {result.exception_type or 'not recorded'}"),
            ft.Text(f"Technical error: {result.technical_error or 'not recorded'}"),
            ft.Text(f"Preview fingerprint: {result.preview_fingerprint or 'not recorded'}"),
            ft.Text(f"Preview payload: {result.preview_payload_path or 'not recorded'}"),
            ft.Text(f"Artifact directory: {result.artifact_dir or 'not recorded'}"),
            ft.Text(f"Report sha256: {result.report_sha256 or 'not recorded'}"),
        ]
        if result.operational_decision:
            decision=result.operational_decision
            technical_details_column.controls.extend([
                ft.Text(f"Decision code: {decision.get('decision_code','not recorded')}\nTest reason: {(decision.get('test_gate') or {}).get('reason_code','not recorded')}\nProduction authorization: {(decision.get('production_gate') or {}).get('state','not recorded')}"),
                review_history('Raw operational decision / JSON',[ft.Text(json.dumps(decision,indent=2,sort_keys=True),selectable=True)],show_count=False)])
        technical_details_section.visible = bool(technical_details_column.controls)
        technical_details_section.controls[0].expanded = False

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
            "ADD_TICKERS", "REMOVE_TICKERS", "REFRESH_FUNDAMENTALS",
        }
        full_workflow_button.disabled = bool(
            operation_running
            or production_safety_blocked
            or not can_preview()
            or current_preview_signature is not None
        )
        normal_capability = capabilities.get('REFRESH_FUNDAMENTALS')
        normal_workflow_button.disabled = bool(operation_running or publication_safety.get('production_writes_blocked') or
            (normal_capability and not normal_capability.production_apply_enabled))

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
        update_operational_summary()
        button.disabled = True
        preview_button.disabled = True
        copy_apply_button.disabled = True
        production_apply_button.disabled = True
        full_workflow_button.disabled = True
        normal_workflow_button.disabled = True
        progress_section.visible = True
        progress_field.visible = True
        progress_follow_latest = True
        render_progress(replace=["Starting..."])
        progress_summary.visible = False
        progress_details.visible = True
        progress_details.controls[0].expanded = not running_full_workflow
        if hasattr(page, "update"):
            page.update()
        try:
            apply_result(fn())
        except Exception:
            LOGGER.exception("Fundamentals administration UI run failed")
            operational_state['last'] = dict(mode=DEEP_REVIEW,rows=('Administration run failed; inspect the recorded error and workflow evidence.',))
            final_section.visible = True
            status_field.visible = True
            status_field.value = "Administration run failed. See the operation log or report for details."
        finally:
            operation_running = False
            update_operational_summary()
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
        nonlocal running_full_workflow
        current_preview_signature = None
        current_preview_result = None
        current_preview_payload_path = None
        current_preview_fingerprint = None
        current_test_run_id = None
        preview_payload_field.value = ""
        preview_fingerprint_field.value = ""
        last_progress_count = None
        running_full_workflow = True
        try:
            run_guarded(
                full_workflow_button,
                lambda: admin_service.full_workflow(
                    operation_type=operation_dropdown.value or "ADD_TICKERS",
                    raw_inputs=tickers_field.value or "",
                    market=market_field.value or "usa",
                    progress_callback=progress_callback,
                ),
            )
        finally:
            running_full_workflow = False

    preview_button = ft.ElevatedButton("Preview", icon=ft.Icons.PREVIEW, on_click=on_preview)
    copy_apply_button = ft.OutlinedButton("Test on copies", icon=ft.Icons.CHECKLIST, on_click=on_copy_apply, visible=False)
    production_apply_button = ft.ElevatedButton("Production update", icon=ft.Icons.LOCK, on_click=on_production_apply, visible=False)
    full_workflow_button = ft.ElevatedButton("Run full workflow", icon=ft.Icons.PLAY_ARROW, on_click=on_full_workflow)
    def run_normal_workflow(_event: Any) -> None:
        if normal_workflow_button.disabled:
            return
        operation_dropdown.value = 'REFRESH_FUNDAMENTALS'
        invalidate_preview()
        on_full_workflow(_event)
    normal_workflow_button = ft.ElevatedButton('Refresh Fundamentals — Full Workflow',icon=ft.Icons.PLAY_ARROW,on_click=run_normal_workflow)
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

    selected_review_evidence.controls = review_history('Selected review evidence',[selected_review_summary,
        review_history('Raw technical evidence / JSON',[review_queue_detail_field,selected_review_raw],show_count=False)],show_count=False).controls
    review_section = review_history('Review — current exceptions', [
        ft.Row([ft.Text('Provider history / source removal',size=18),review_queue_refresh_button,review_queue_include_resolved_checkbox],wrap=True),
        review_queue_status_field,review_queue_column,
        selected_review_evidence,
        review_queue_blocked_actions,
        ft.Text('Quarterly P/B ownership reviews',size=18),pb_ownership_status_field,pb_ownership_column,
    ],show_count=False)
    deep_review_section = review_history('Deep Review — exceptional evidence',[deep_review_column],show_count=False)
    def open_review(_event: Any) -> None:
        refresh_review_queue()
        review_section.controls[0].expanded = True
        if hasattr(page,'update'):page.update()
    def open_deep(_event: Any) -> None:
        refresh_review_queue()
        deep_review_section.controls[0].expanded = True
        if hasattr(page,'update'):page.update()
    advanced_section = review_history('Advanced — administration tools and workflow stages', [
            ft.Text("Administration operation", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([operation_dropdown, market_field, taxonomy_domain_dropdown], wrap=True, spacing=12),
            operation_guidance_field,
            ft.Text("Full Workflow runs Preview, Test on copies and safe publication under the existing safeguards. Individual stages remain available for exceptions."),
            tickers_field,
            ft.Row([candidate_path_field, candidate_version_field], wrap=True, spacing=12),
            ft.Row([full_workflow_button, preview_button, copy_apply_button, production_apply_button], spacing=12, wrap=True),
            ],show_count=False)
    run_history_section = review_history('Run history and cleanup evidence', [
            ft.Row([
                ft.Text("Run history", size=18, weight=ft.FontWeight.BOLD),
                history_refresh_button,
            ]),
            show_technical_history_checkbox,
            ft.Row(
                [
                    ft.Text("Time", width=185, weight=ft.FontWeight.BOLD),
                    ft.Text("Operation", width=190, weight=ft.FontWeight.BOLD),
                    ft.Text("Stage", width=155, weight=ft.FontWeight.BOLD),
                    ft.Text("Result / operational meaning", width=280, weight=ft.FontWeight.BOLD),
                    ft.Text("Count", width=125, weight=ft.FontWeight.BOLD),
                    ft.Text("Category", width=170, weight=ft.FontWeight.BOLD),
                    ft.Container(width=48),
                    ft.Container(width=48),
                    ft.Container(width=48),
                    ft.Container(width=48),
                ]
            ),
            latest_workflow_history,
            ownership_history_column,
            accounting_history_column,
            provider_history_column,
            history_column,
            history_show_more_button,
            history_detail_field,
            cleanup_status_field,
            cleanup_button,
            ],show_count=False)
    technical_details_section = review_history('Technical details',[
        preview_payload_field,preview_fingerprint_field,production_confirmation_field,technical_details_column],show_count=False)
    technical_details_section.visible = False
    content = ft.Column([
        ft.Text('Fundamentals Administration',size=24,weight=ft.FontWeight.BOLD),
        operational_summary_field,
        ft.Row([normal_workflow_button,
            ft.TextButton('Review current exceptions',on_click=open_review),
            ft.TextButton('Deep Review / evidence',on_click=open_deep),
            ft.TextButton('Refresh operational status',on_click=refresh_review_queue)],wrap=True),
        publication_safety_field,pending_refresh_field,
        preview_section,progress_section,final_section,report_button,
        run_history_section,review_section,deep_review_section,advanced_section,technical_details_section,
    ],spacing=12,expand=True,scroll=ft.ScrollMode.AUTO)
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
        history_refresh_button=history_refresh_button,
        cleanup_status_field=cleanup_status_field,
        cleanup_button=cleanup_button,
        review_queue_column=review_queue_column,
        review_queue_status_field=review_queue_status_field,
        review_queue_detail_field=review_queue_detail_field,
        review_queue_include_resolved_checkbox=review_queue_include_resolved_checkbox,
        review_queue_refresh_button=review_queue_refresh_button,
        review_queue_blocked_actions=review_queue_blocked_actions,
        pb_ownership_column=pb_ownership_column,
        pb_ownership_status_field=pb_ownership_status_field,
        activate=activate,
        history_loader=history_loader,
        operational_summary_field=operational_summary_field,
        normal_workflow_button=normal_workflow_button,
        review_section=review_section,
        deep_review_section=deep_review_section,
        deep_review_column=deep_review_column,
        ownership_history_column=ownership_history_column,
        provider_history_column=provider_history_column,
        accounting_history_column=accounting_history_column,
        selected_review_evidence=selected_review_evidence,
        technical_details_section=technical_details_section,
    )
