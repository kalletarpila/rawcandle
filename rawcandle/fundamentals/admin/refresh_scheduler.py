"""Scheduler trigger for Preview-only or explicitly enabled full Refresh."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.publication_journal import safety_status
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.scheduler.config import SUPPORTED_FUNDAMENTALS_REFRESH_MODES


def _load_payload(run_root: Path, run_id: str | None) -> dict[str, Any]:
    if not run_id or Path(run_id).name != run_id:
        return {}
    for filename in ("workflow_result.json", "result.json"):
        try:
            value = json.loads((run_root / run_id / filename).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def _full_workflow_summary(
    *, response: Any, payload: dict[str, Any], run_root: Path,
) -> dict[str, Any]:
    stages = list(payload.get("stages") or [])
    stage_names = [str(item.get("stage")) for item in stages]
    production_stage = next(
        (item for item in stages if item.get("stage") == "Production update"), {}
    )
    source = dict(payload.get("source_summary") or {})
    terminal = dict(payload.get("terminal_summary") or {})
    review_partition = dict(payload.get("review_partition") or {})
    held_items = list(review_partition.get("held") or [])
    if not held_items:
        held_items = [
            item for item in (terminal.get("problem_items") or [])
            if item.get("review_scope") == "TICKER_LOCAL_REVIEW"
        ]
    held_tickers = sorted({
        str(item.get("ticker")) for item in held_items if item.get("ticker")
    })
    global_blockers = int(source.get("global_blockers") or 0)
    workflow_outcome = str(payload.get("outcome") or response.outcome or "FAILED")
    production_ran = "Production update" in stage_names
    test_ran = "Test on copies" in stage_names
    production_completed = bool(payload.get("production_completed"))
    failed = workflow_outcome == "FAILED" or str(response.status) == "FAILED"
    review_required = bool(held_tickers or global_blockers)
    summary_result = (
        "FAILED" if failed
        else "REVIEW_REQUIRED" if review_required and not production_completed
        else "NO_CHANGE" if workflow_outcome == "NO_CHANGE"
        else "COMPLETED" if production_completed
        else "STOPPED"
    )
    reason = (
        "Production completed."
        if production_completed
        else str(terminal.get("headline") or payload.get("stop_reason") or response.message)
    )
    return {
        "operation_type": "REFRESH_FUNDAMENTALS",
        "mode": "SCHEDULER_FULL_WORKFLOW",
        "configured_mode": "FULL_WORKFLOW",
        "trigger_source": "SCHEDULER",
        "outcome": workflow_outcome,
        "final_outcome": workflow_outcome,
        "scheduler_summary_result": summary_result,
        "status": response.status,
        "run_id": response.run_id,
        "report": str(run_root / str(response.run_id) / "workflow_report.md"),
        "preview_result": next(
            (item.get("result") for item in stages if item.get("stage") == "Preview"),
            "NOT_RUN",
        ),
        "summary_counts": dict(source.get("classification_counts") or {}),
        "held_review_tickers": held_tickers,
        "global_blockers": global_blockers,
        "test_invoked": test_ran,
        "production_invoked": production_ran,
        "production_run_id": production_stage.get("run_id"),
        "production_decision_reason": reason,
        "full_workflow_invoked": True,
        "unattended_production_available": True,
        "pending_changes": bool(source.get("effective_changed_known")) and not production_completed,
        "review_required": review_required,
        "technical_failure": reason if failed else None,
        "preview_timestamp_utc": payload.get("started_at_utc"),
        "published_watermark": (payload.get("publication_outcome") or {}).get("new_watermark"),
        "published_baseline": (
            (payload.get("publication_outcome") or {}).get("new_watermark")
            or (payload.get("publication_outcome") or {}).get("old_watermark")
            or "BOOTSTRAP_BASELINE"
        ),
        "discovered_source_ticker_count": int(source.get("discovered_tickers") or 0),
        "message": reason,
    }


def run_scheduler_refresh_discovery(
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    operation_lock_path: Path | None = None,
    preview_backend: Callable[..., dict[str, Any]] | None = None,
    scheduler_mode: str = "PREVIEW_ONLY",
    scheduler_log_dir: str | None = None,
    full_workflow_backend: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run configured Refresh mode without creating operator approvals."""
    if scheduler_mode not in SUPPORTED_FUNDAMENTALS_REFRESH_MODES:
        raise ValueError("FUNDAMENTALS_REFRESH_SCHEDULER_MODE_INVALID")
    safety = safety_status()
    if safety.get("production_writes_blocked"):
        return {
            "operation_type": "REFRESH_FUNDAMENTALS",
            "mode": "SCHEDULER_DISCOVERY",
            "configured_mode": scheduler_mode,
            "trigger_source": "SCHEDULER",
            "outcome": "BLOCKED",
            "scheduler_summary_result": "FAILED",
            "status": "BLOCKED",
            "preview_timestamp_utc": None,
            "published_watermark": None,
            "published_baseline": "RECOVERY_REQUIRED",
            "discovered_source_ticker_count": 0,
            "publication_safety": safety,
            "pending_changes": False,
            "review_required": False,
            "technical_failure": "PUBLICATION_RECOVERY_REQUIRED",
            "preview_result": "BLOCKED",
            "held_review_tickers": [],
            "global_blockers": 1,
            "test_invoked": False,
            "production_invoked": False,
            "production_run_id": None,
            "production_decision_reason": "Publication recovery is required.",
            "full_workflow_invoked": False,
            "unattended_production_available": False,
            "message": "Refresh discovery deferred because Fundamentals publication recovery requires attention.",
        }
    kwargs: dict[str, Any] = {
        "run_root": run_root,
        "operation_lock_path": operation_lock_path,
        "recover_publication_on_startup": False,
    }
    if preview_backend is not None:
        kwargs["refresh_preview"] = preview_backend
    service = FundamentalsAdminUIService(**kwargs)
    if scheduler_mode == "FULL_WORKFLOW":
        try:
            response = (
                full_workflow_backend(
                    operation_type="REFRESH_FUNDAMENTALS",
                    raw_inputs="",
                    trigger_source="SCHEDULER",
                    scheduler_log_dir=scheduler_log_dir,
                    scheduler_managed_locks=True,
                )
                if full_workflow_backend is not None
                else service.full_workflow(
                    operation_type="REFRESH_FUNDAMENTALS",
                    raw_inputs="",
                    trigger_source="SCHEDULER",
                    scheduler_log_dir=scheduler_log_dir,
                    scheduler_managed_locks=True,
                )
            )
        except Exception as exc:
            return {
                "operation_type": "REFRESH_FUNDAMENTALS",
                "mode": "SCHEDULER_FULL_WORKFLOW",
                "configured_mode": scheduler_mode,
                "trigger_source": "SCHEDULER",
                "outcome": "FAILED",
                "final_outcome": "FAILED",
                "scheduler_summary_result": "FAILED",
                "status": "FAILED",
                "run_id": None,
                "report": None,
                "preview_result": "FAILED",
                "summary_counts": {},
                "held_review_tickers": [],
                "global_blockers": 0,
                "test_invoked": False,
                "production_invoked": False,
                "production_run_id": None,
                "production_decision_reason": f"{type(exc).__name__}: {exc}",
                "full_workflow_invoked": True,
                "unattended_production_available": True,
                "pending_changes": False,
                "review_required": False,
                "technical_failure": f"{type(exc).__name__}: {exc}",
                "message": f"Refresh Full Workflow failed: {type(exc).__name__}.",
            }
        payload = _load_payload(run_root, response.run_id)
        return _full_workflow_summary(
            response=response, payload=payload, run_root=run_root,
        )
    try:
        response = service.preview("REFRESH_FUNDAMENTALS", trigger_source="SCHEDULER")
    except Exception as exc:
        return {
            "operation_type": "REFRESH_FUNDAMENTALS",
            "mode": "SCHEDULER_DISCOVERY",
            "configured_mode": scheduler_mode,
            "trigger_source": "SCHEDULER",
            "outcome": "FAILED",
            "scheduler_summary_result": "FAILED",
            "status": "FAILED",
            "preview_timestamp_utc": None,
            "published_watermark": None,
            "published_baseline": "UNKNOWN",
            "discovered_source_ticker_count": 0,
            "run_id": None,
            "report": None,
            "summary_counts": {"failed": 1},
            "pending_changes": False,
            "review_required": False,
            "technical_failure": f"{type(exc).__name__}: {exc}",
            "preview_result": "FAILED",
            "held_review_tickers": [],
            "global_blockers": 0,
            "test_invoked": False,
            "production_invoked": False,
            "production_run_id": None,
            "production_decision_reason": "Preview failed before Test could run.",
            "full_workflow_invoked": False,
            "unattended_production_available": False,
            "message": (
                "Refresh Fundamentals Preview failed technically before completion: "
                f"{type(exc).__name__}."
            ),
        }
    payload = _load_payload(run_root, response.run_id)
    counts = dict(payload.get("summary_counts") or {})
    preview = dict(payload.get("refresh_preview") or {})
    state = dict(preview.get("state") or {})
    discovery = dict(preview.get("discovery") or {})
    known = int(counts.get("effective_changed_known") or 0)
    review_count = int(counts.get("REVIEW_REQUIRED") or 0)
    review_required = response.outcome == "REVIEW_REQUIRED" or review_count > 0
    pending = response.status == "COMPLETED" and response.outcome == "COMPLETED"
    pending_changes = known > 0
    result_name = (
        "REVIEW_REQUIRED" if review_required
        else "CHANGES_FOUND" if pending
        else "NO_CHANGE" if response.outcome == "NO_CHANGE"
        else "FAILED"
    )
    errors = payload.get("errors") or []
    first_error = errors[0] if errors and isinstance(errors[0], dict) else {}
    technical_failure = (
        f"{first_error.get('type')}: {first_error.get('message')}"
        if result_name == "FAILED" and first_error else None
    )
    new_quarter = int(counts.get("NEW_QUARTER") or 0)
    revision = int(counts.get("HISTORICAL_REVISION") or 0)
    combined = int(counts.get("NEW_QUARTER_AND_REVISION") or 0)
    held = int(counts.get("held_for_review") or 0)
    return {
        "operation_type": "REFRESH_FUNDAMENTALS",
        "mode": "SCHEDULER_DISCOVERY",
        "configured_mode": scheduler_mode,
        "trigger_source": "SCHEDULER",
        "outcome": "PENDING_CHANGES" if pending else response.outcome,
        "scheduler_summary_result": result_name,
        "status": response.status,
        "preview_timestamp_utc": payload.get("completed_at_utc"),
        "published_watermark": state.get("published_watermark"),
        "published_baseline": state.get("published_watermark") or "BOOTSTRAP_BASELINE",
        "discovered_source_ticker_count": int(
            discovery.get("unique_changed_source_tickers")
            or discovery.get("discovered_ticker_count")
            or len(discovery.get("changed_tickers") or [])
        ),
        "run_id": response.run_id,
        "report": str(run_root / response.run_id / "operation_report.md") if response.run_id else None,
        "summary_counts": counts,
        "pending_changes": pending_changes,
        "review_required": review_required,
        "technical_failure": technical_failure,
        "preview_result": result_name,
        "held_review_tickers": sorted({
            str(item.get("ticker"))
            for item in ((preview.get("review_partition") or {}).get("held") or [])
            if item.get("ticker")
        }),
        "global_blockers": int(counts.get("global_blockers") or 0),
        "test_invoked": False,
        "production_invoked": False,
        "production_run_id": None,
        "production_decision_reason": "Configured mode is PREVIEW_ONLY.",
        "full_workflow_invoked": False,
        "unattended_production_available": False,
        "message": (
            f"Refresh Fundamentals: {known} known tickers have pending changes: "
            f"{new_quarter} new quarters, {revision} revisions, "
            f"{combined} new-quarter + revision. Scheduler PREVIEW_ONLY completed; "
            "Test/Production intentionally not requested."
            + (f" {held} ticker(s) held in the review queue." if held else "")
            if pending
            else f"Refresh Fundamentals: {review_count} ticker(s) require review. Manual review pending."
            if review_required
            else "Refresh Fundamentals: No relevant Sharadar changes since the last published refresh."
            if response.outcome == "NO_CHANGE"
            else response.message
        ),
    }
