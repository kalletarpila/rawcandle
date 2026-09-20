"""Durable thin orchestration for existing Fundamentals Admin stages."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import parse_batch_tickers
from rawcandle.fundamentals.admin.contracts import AdminOperationType, fingerprint, utc_now
from rawcandle.fundamentals.admin.ticker_reporting import analysis_reporting_counts, reporting_counts


WORKFLOW_REPORT_NAME = "workflow_report.md"
WORKFLOW_RESULT_NAME = "workflow_result.json"


@dataclass(frozen=True)
class WorkflowOperationAdapter:
    operation_type: AdminOperationType
    label: str
    request_identity: Mapping[str, Any]
    requested_inputs: tuple[str, ...]
    preview_stage: Callable[[Callable[[Mapping[str, Any]], None]], Any]
    test_stage: Callable[[Any, Callable[[Mapping[str, Any]], None]], Any]
    production_stage: Callable[[Any, Any, Callable[[Mapping[str, Any]], None]], Any]
    trigger_source: str = "MANUAL"


def _value(result: Any, name: str, default: Any = None) -> Any:
    return getattr(result, name, default)


def _duration(started: str | None, completed: str | None) -> float | None:
    if not started or not completed:
        return None
    try:
        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(completed.replace("Z", "+00:00"))
        return max(0.0, (end - start).total_seconds())
    except ValueError:
        return None


def _load_result(run_root: Path, run_id: str | None) -> Mapping[str, Any]:
    if not run_id or Path(run_id).name != run_id:
        return {}
    path = run_root / run_id / "result.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, Mapping) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _stage_record(name: str, result: Any, started: str, completed: str) -> dict[str, Any]:
    run_id = _value(result, "run_id")
    return {
        "stage": name,
        "result": _value(result, "outcome") or _value(result, "status") or "UNKNOWN",
        "status": _value(result, "status") or "UNKNOWN",
        "run_id": run_id,
        "duration_seconds": _duration(started, completed),
        "report": str(Path(_value(result, "artifact_dir") or "") / "operation_report.md") if run_id else None,
        "message": _value(result, "message"),
    }


def _refresh_source_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    counts = dict(payload.get("summary_counts") or {})
    discovery = dict((payload.get("refresh_preview") or {}).get("discovery") or {})
    return {
        "discovery_rows": int(
            discovery.get("returned_source_rows")
            or discovery.get("discovery_row_count")
            or discovery.get("row_count")
            or 0
        ),
        "discovered_tickers": int(
            discovery.get("unique_changed_source_tickers")
            or discovery.get("discovered_ticker_count")
            or len(discovery.get("changed_tickers") or [])
        ),
        "effective_changed_known": int(counts.get("effective_changed_known") or 0),
        "unknown_tickers": int(counts.get("NOT_IN_CANONICAL_UNIVERSE") or counts.get("unknown") or 0),
        "review_required": int(counts.get("REVIEW_REQUIRED") or counts.get("review_required") or 0),
        "classification_counts": counts,
    }


def _refresh_publication_outcome(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical = payload.get("canonical_candidate") or {}
    refresh_state = payload.get("refresh_state") or {}
    old_state = payload.get("old_refresh_state") or {}
    return {
        "provider_refreshed_tickers": int((payload.get("provider_candidate") or {}).get("ticker_count") or 0),
        "canonical_impact": dict(canonical.get("impact") or {}),
        "first_public": dict(canonical.get("publication_date_bootstrap") or {}),
        "analysis_status": (payload.get("analysis_candidate") or {}).get("status") or "NOT_RUN",
        "old_watermark": old_state.get("published_watermark"),
        "new_watermark": refresh_state.get("published_source_watermark"),
        "postflight": (payload.get("postflight") or {}).get("status") or ("PASSED" if payload.get("postflight") else "NOT_RUN"),
        "rollback_recovery": (payload.get("rollback") or {}).get("status") or (payload.get("publication_recovery") or {}).get("status") or "NOT_REQUIRED",
    }


def render_workflow_report(result: Mapping[str, Any]) -> str:
    duration = _duration(str(result.get("started_at_utc") or ""), str(result.get("completed_at_utc") or ""))
    duration_text = "Running" if duration is None else f"{duration:.1f} seconds"
    stages = list(result.get("stages") or [])
    batch = result.get("final_batch_outcome") or {}
    refresh = result.get("source_summary") or {}
    publication = result.get("publication_outcome") or {}
    is_refresh = result.get("operation_type") == AdminOperationType.REFRESH_FUNDAMENTALS.value
    lines = [
        f"# {result.get('operation_label', 'Administration')} Full Workflow Report",
        "",
        "## Executive Summary",
        "",
        f"- Trigger: {str(result.get('trigger_source') or 'MANUAL').title()}",
        f"- Overall workflow result: {result.get('outcome', 'RUNNING')}",
        f"- Total duration: {duration_text}",
        f"- Final completed stage: {result.get('final_completed_stage') or 'None'}",
        f"- Production completed: {'Yes' if result.get('production_completed') else 'No'}",
        f"- NO_CHANGE: {'Yes' if result.get('outcome') == 'NO_CHANGE' else 'No'}",
        "",
        "## Stage Results",
        "",
        "| Stage | Result | Duration | Run ID |",
        "| --- | --- | --- | --- |",
    ]
    for stage in stages:
        stage_duration = stage.get("duration_seconds")
        lines.append(
            f"| {stage.get('stage')} | {stage.get('result')} | "
            f"{'Not recorded' if stage_duration is None else f'{float(stage_duration):.1f} sec'} | "
            f"{stage.get('run_id') or 'Not started'} |"
        )
    if result.get("stop_reason"):
        lines.extend([
            "",
            str(result["stop_reason"])
            if result.get("outcome") == "NO_CHANGE"
            else f"Workflow stopped at **{result.get('current_stage')}**: {result['stop_reason']}",
        ])
    if is_refresh:
        lines.extend([
            "", "## Source Outcome", "",
            f"- Discovery rows: {refresh.get('discovery_rows', 0)}",
            f"- Discovered tickers: {refresh.get('discovered_tickers', 0)}",
            f"- Effective changed known tickers: {refresh.get('effective_changed_known', 0)}",
            f"- Unknown tickers: {refresh.get('unknown_tickers', 0)}",
            f"- Review required: {refresh.get('review_required', 0)}",
            f"- Classification counts: `{json.dumps(refresh.get('classification_counts') or {}, sort_keys=True)}`",
            "", "## Final Publication Outcome", "",
            f"- Provider refreshed tickers: {publication.get('provider_refreshed_tickers', 0)}",
            f"- Canonical impact: `{json.dumps(publication.get('canonical_impact') or {}, sort_keys=True)}`",
            f"- First-public work: `{json.dumps(publication.get('first_public') or {}, sort_keys=True)}`",
            f"- V2/RP/RV: {publication.get('analysis_status', 'NOT_RUN')}",
            f"- Watermark: {publication.get('old_watermark') or 'BOOTSTRAP_BASELINE'} -> {publication.get('new_watermark') or 'NOT_PUBLISHED'}",
            f"- Postflight: {publication.get('postflight', 'NOT_RUN')}",
            f"- Rollback/recovery: {publication.get('rollback_recovery', 'NOT_REQUIRED')}",
        ])
    else:
        lines.extend([
            "", "## Final Batch Outcome", "",
            f"- Requested ticker count: {len(result.get('requested_inputs') or [])}",
            f"- Added: {batch.get('added', 0)}",
            f"- Existing tickers included in rebuild: {batch.get('existing_rebuilt', 0)}",
            f"- Review required: {batch.get('review_required', 0)}",
            f"- Expected no-quarterly-history: {batch.get('no_usable_quarterly_history', 0)}",
            f"- Reporting integrity errors: {batch.get('reporting_integrity_errors', 0)}",
        ])
    lines.extend(["", "## Warnings", ""])
    warnings = list(result.get("warnings") or [])
    lines.extend(f"- {warning}" for warning in warnings)
    if not warnings:
        lines.append("- No workflow-level warnings.")
    lines.extend(["", "## Reports", ""])
    for stage in stages:
        if stage.get("report"):
            lines.append(f"- {stage.get('stage')}: `{stage['report']}`")
    return "\n".join(lines).rstrip() + "\n"


def run_operation_workflow(
    adapter: WorkflowOperationAdapter,
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    run_id = stable_run_id(
        adapter.operation_type,
        fingerprint(dict(adapter.request_identity)),
        suffix="full_workflow",
    ) + "_" + secrets.token_hex(4)
    writer = AdminRunWriter(run_id, adapter.operation_type, root=run_root)
    started = utc_now()
    result: dict[str, Any] = {
        "run_id": run_id,
        "artifact_dir": str(writer.run_dir),
        "operation_type": adapter.operation_type.value,
        "operation_label": adapter.label,
        "mode": "FULL_WORKFLOW",
        "trigger_source": adapter.trigger_source,
        "outcome": "RUNNING",
        "workflow_status": "RUNNING",
        "requested_inputs": list(adapter.requested_inputs),
        "current_stage": "Preview",
        "started_at_utc": started,
        "completed_at_utc": None,
        "final_completed_stage": None,
        "production_completed": False,
        "stages": [],
        "warnings": [],
        "stop_reason": None,
    }
    writer.write_json("request.json", {
        "operation_type": adapter.operation_type.value,
        "mode": "FULL_WORKFLOW",
        "trigger_source": adapter.trigger_source,
        "request_identity": dict(adapter.request_identity),
        "requested_inputs": list(adapter.requested_inputs),
    })

    def persist() -> None:
        writer.write_json(WORKFLOW_RESULT_NAME, result)
        writer.write_json("result.json", result)
        writer.write_json("progress_status.json", {
            "run_id": run_id,
            "operation_type": adapter.operation_type.value,
            "current_stage_id": result["current_stage"].upper().replace(" ", "_"),
            "current_stage_number": {"Preview": 1, "Test on copies": 2, "Production update": 3}.get(result["current_stage"], 3),
            "total_declared_stages": 3,
            "stage_state": result["workflow_status"],
            "message": result.get("stop_reason") or f"Full workflow {result['workflow_status'].lower()}.",
            "pid": __import__("os").getpid(),
        })

    def emit(stage: str, number: int, state: str, message: str, child: Mapping[str, Any] | None = None) -> None:
        result["current_stage"] = stage
        event = {
            "run_id": run_id,
            "operation_type": adapter.operation_type.value,
            "current_stage_id": stage.upper().replace(" ", "_"),
            "current_stage_number": number,
            "total_declared_stages": 3,
            "stage_state": state,
            "message": message,
            "child_run_id": (child or {}).get("run_id"),
            "child_stage_id": (child or {}).get("current_stage_id"),
            "timestamp_utc": utc_now(),
        }
        writer.append_jsonl("progress_events.jsonl", event)
        writer.append_heartbeat(event)
        persist()
        if progress_callback:
            progress_callback(event)

    def child_progress(stage: str, number: int) -> Callable[[Mapping[str, Any]], None]:
        def callback(event: Mapping[str, Any]) -> None:
            emit(stage, number, "RUNNING", f"{stage} - {event.get('message', 'working')}", event)
        return callback

    def stop(stage: str, reason: str, *, failed: bool = False) -> None:
        result["workflow_status"] = "FAILED" if failed else "STOPPED"
        result["outcome"] = result["workflow_status"]
        result["current_stage"] = stage
        result["stop_reason"] = reason

    def batch_outcome(payload: Mapping[str, Any]) -> dict[str, int]:
        reports = list(payload.get("ticker_reporting") or [])
        actions = [str(item.get("final_action") or "") for item in reports]
        analysis = analysis_reporting_counts(reports)
        counts = reporting_counts(reports) if reports else {"review_required": 0}
        return {
            "added": actions.count("Added"),
            "existing_rebuilt": actions.count("Existing ticker - analysis rebuilt"),
            "review_required": int(counts.get("review_required") or actions.count("Review required")),
            **analysis,
        }

    persist()
    try:
        emit("Preview", 1, "RUNNING", "Preview - Running")
        stage_started = utc_now()
        preview = adapter.preview_stage(child_progress("Preview", 1))
        stage_completed = utc_now()
        result["stages"].append(_stage_record("Preview", preview, stage_started, stage_completed))
        preview_payload = _load_result(run_root, _value(preview, "run_id"))
        if adapter.operation_type == AdminOperationType.REFRESH_FUNDAMENTALS:
            result["source_summary"] = _refresh_source_summary(preview_payload)
        if _value(preview, "status") == "COMPLETED" and _value(preview, "outcome") == "NO_CHANGE":
            result["workflow_status"] = "COMPLETED"
            result["outcome"] = "NO_CHANGE"
            result["final_completed_stage"] = "Preview"
            result["stop_reason"] = (
                "No relevant Sharadar fundamentals changes were found. No database updates were required."
                if adapter.operation_type == AdminOperationType.REFRESH_FUNDAMENTALS
                else "No ticker additions or analysis rebuilds were required."
            )
            emit("Preview", 1, "COMPLETED", "Preview - No changes")
        elif (
            _value(preview, "status") != "COMPLETED"
            or _value(preview, "outcome") != "COMPLETED"
            or not _value(preview, "preview_payload_path")
            or not _value(preview, "preview_fingerprint")
        ):
            stop("Preview", _value(preview, "message") or "Preview did not authorize Test on copies.")
        else:
            result["preview_payload_path"] = _value(preview, "preview_payload_path")
            result["preview_fingerprint"] = _value(preview, "preview_fingerprint")
            result["final_completed_stage"] = "Preview"
            emit("Preview", 1, "COMPLETED", "Preview - Completed")

        if result["workflow_status"] == "RUNNING":
            emit("Test on copies", 2, "RUNNING", "Test on copies - Running")
            stage_started = utc_now()
            test = adapter.test_stage(preview, child_progress("Test on copies", 2))
            stage_completed = utc_now()
            result["stages"].append(_stage_record("Test on copies", test, stage_started, stage_completed))
            if _value(test, "status") != "COMPLETED" or _value(test, "outcome") != "COMPLETED":
                result["manual_test_retry_available"] = adapter.operation_type == AdminOperationType.ADD_TICKERS
                result["preview_test_rerun_required"] = adapter.operation_type == AdminOperationType.REFRESH_FUNDAMENTALS
                stop("Test on copies", _value(test, "message") or "Test on copies failed.")
            else:
                result["test_run_id"] = _value(test, "run_id")
                result["manual_production_available"] = True
                test_payload = _load_result(run_root, _value(test, "run_id"))
                integrity = analysis_reporting_counts(list(test_payload.get("ticker_reporting") or []))
                result["final_batch_outcome"] = batch_outcome(test_payload)
                result["final_completed_stage"] = "Test on copies"
                emit("Test on copies", 2, "COMPLETED", "Test on copies - Completed")
                if integrity["reporting_integrity_errors"]:
                    stop(
                        "Test on copies",
                        "Full workflow stopped after Test on copies because reporting integrity requires attention. Manual Production review remains available.",
                    )

        if result["workflow_status"] == "RUNNING":
            emit("Production update", 3, "RUNNING", "Production update - Running")
            stage_started = utc_now()
            production = adapter.production_stage(preview, test, child_progress("Production update", 3))
            stage_completed = utc_now()
            result["stages"].append(_stage_record("Production update", production, stage_started, stage_completed))
            production_payload = _load_result(run_root, _value(production, "run_id"))
            if adapter.operation_type == AdminOperationType.REFRESH_FUNDAMENTALS:
                result["publication_outcome"] = _refresh_publication_outcome(production_payload)
            git_state = production_payload.get("git_state") or {}
            if git_state.get("dirty"):
                result["warnings"].append("Warning: Production ran with uncommitted Git worktree changes.")
            if _value(production, "status") == "COMPLETED" and _value(production, "outcome") in {"COMPLETED", "NO_CHANGE"}:
                result["workflow_status"] = "COMPLETED"
                result["outcome"] = "COMPLETED"
                result["production_completed"] = True
                result["final_completed_stage"] = "Production update"
                result["final_batch_outcome"] = batch_outcome(production_payload)
                emit("Production update", 3, "COMPLETED", "Production update - Completed")
            else:
                retry = production_payload.get("retry_authorization") or {}
                result["manual_production_retry_available"] = bool(retry.get("direct_production_retry_available"))
                result["preview_test_rerun_required"] = bool(retry.get("preview_test_rerun_required"))
                if _value(production, "outcome") == "RETRY_REQUIRED":
                    result["workflow_status"] = "STOPPED"
                    result["outcome"] = "RETRY_REQUIRED"
                    result["current_stage"] = "Production update"
                    result["stop_reason"] = _value(production, "message") or "Recovery completed; start a fresh workflow."
                else:
                    stop("Production update", _value(production, "message") or "Production preflight failed.")
    except Exception as exc:
        stop(result["current_stage"], f"Workflow orchestration failed: {type(exc).__name__}: {exc}", failed=True)
    finally:
        result["completed_at_utc"] = utc_now()
        if result["workflow_status"] == "RUNNING":
            stop(result["current_stage"], "Workflow ended without a terminal stage.", failed=True)
        persist()
        report = render_workflow_report(result)
        writer.write_text(WORKFLOW_REPORT_NAME, report)
        writer.write_text("operation_report.md", report)
        writer.write_exit_code(0 if result["outcome"] in {"COMPLETED", "NO_CHANGE"} else 3)
        writer.write_manifest()
    return result


def run_full_workflow(
    raw_inputs: str,
    *,
    market: str,
    run_root: Path = ADMIN_RUN_ROOT,
    preview_stage: Callable[[Callable[[Mapping[str, Any]], None]], Any],
    test_stage: Callable[[Any, Callable[[Mapping[str, Any]], None]], Any],
    production_stage: Callable[[Any, Any, Callable[[Mapping[str, Any]], None]], Any],
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    request = parse_batch_tickers(raw_inputs, market=market)
    adapter = WorkflowOperationAdapter(
        operation_type=AdminOperationType.ADD_TICKERS,
        label="Add Tickers",
        request_identity={"inputs": request.normalized_inputs, "market": request.market},
        requested_inputs=tuple(request.normalized_inputs),
        preview_stage=preview_stage,
        test_stage=test_stage,
        production_stage=production_stage,
    )
    return run_operation_workflow(adapter, run_root=run_root, progress_callback=progress_callback)


def run_refresh_full_workflow(
    *,
    run_root: Path = ADMIN_RUN_ROOT,
    preview_stage: Callable[[Callable[[Mapping[str, Any]], None]], Any],
    test_stage: Callable[[Any, Callable[[Mapping[str, Any]], None]], Any],
    production_stage: Callable[[Any, Any, Callable[[Mapping[str, Any]], None]], Any],
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    adapter = WorkflowOperationAdapter(
        operation_type=AdminOperationType.REFRESH_FUNDAMENTALS,
        label="Refresh Fundamentals",
        request_identity={"operation": AdminOperationType.REFRESH_FUNDAMENTALS.value},
        requested_inputs=(),
        preview_stage=preview_stage,
        test_stage=test_stage,
        production_stage=production_stage,
    )
    return run_operation_workflow(adapter, run_root=run_root, progress_callback=progress_callback)
