"""Scheduler trigger for read-only Refresh Fundamentals discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.publication_journal import safety_status
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


def run_scheduler_refresh_discovery(
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    operation_lock_path: Path | None = None,
    preview_backend: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the normal Refresh Preview backend; Test and Production are unavailable here."""
    safety = safety_status()
    if safety.get("production_writes_blocked"):
        return {
            "operation_type": "REFRESH_FUNDAMENTALS",
            "mode": "SCHEDULER_DISCOVERY",
            "trigger_source": "SCHEDULER",
            "outcome": "BLOCKED",
            "scheduler_summary_result": "FAILED",
            "status": "BLOCKED",
            "preview_timestamp_utc": None,
            "published_watermark": None,
            "published_baseline": "RECOVERY_REQUIRED",
            "discovered_source_ticker_count": 0,
            "publication_safety": safety,
            "test_invoked": False,
            "production_invoked": False,
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
    response = service.preview("REFRESH_FUNDAMENTALS", trigger_source="SCHEDULER")
    payload: dict[str, Any] = {}
    if response.run_id:
        result_path = run_root / response.run_id / "result.json"
        try:
            value = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                payload = value
        except (OSError, ValueError, json.JSONDecodeError):
            payload = {}
    counts = dict(payload.get("summary_counts") or {})
    preview = dict(payload.get("refresh_preview") or {})
    state = dict(preview.get("state") or {})
    discovery = dict(preview.get("discovery") or {})
    pending = response.status == "COMPLETED" and response.outcome == "COMPLETED"
    result_name = "CHANGES_FOUND" if pending else "NO_CHANGE" if response.outcome == "NO_CHANGE" else "FAILED"
    known = int(counts.get("effective_changed_known") or 0)
    new_quarter = int(counts.get("NEW_QUARTER") or 0)
    revision = int(counts.get("HISTORICAL_REVISION") or 0)
    combined = int(counts.get("NEW_QUARTER_AND_REVISION") or 0)
    return {
        "operation_type": "REFRESH_FUNDAMENTALS",
        "mode": "SCHEDULER_DISCOVERY",
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
        "pending_changes": pending,
        "test_invoked": False,
        "production_invoked": False,
        "unattended_production_available": False,
        "message": (
            f"Refresh Fundamentals: {known} known tickers have pending changes: "
            f"{new_quarter} new quarters, {revision} revisions, "
            f"{combined} new-quarter + revision. Manual refresh pending."
            if pending
            else "Refresh Fundamentals: No relevant Sharadar changes since the last published refresh."
            if response.outcome == "NO_CHANGE"
            else response.message
        ),
    }
