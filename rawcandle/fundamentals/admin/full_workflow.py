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
from rawcandle.fundamentals.admin.ticker_reporting import (
    analysis_reporting_counts,
    human_reasons,
    reporting_counts,
)


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


def _stage_record(
    name: str, result: Any, started: str, completed: str,
    *, child_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _value(result, "run_id")
    return {
        "stage": name,
        "result": _value(result, "outcome") or _value(result, "status") or "UNKNOWN",
        "status": _value(result, "status") or "UNKNOWN",
        "run_id": run_id,
        "duration_seconds": _duration(started, completed),
        "report": str(Path(_value(result, "artifact_dir") or "") / "operation_report.md") if run_id else None,
        "message": _value(result, "message"),
        "child_summary": dict(child_summary or {}),
    }


def _problem_items(reports: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for report in reports:
        eligibility = report.get("eligibility") or {}
        analysis = (report.get("after") or {}).get("analysis") or {}
        status = str(eligibility.get("status") or "").upper()
        integrity = (
            analysis.get("integrity_status") == "REPORTING_INTEGRITY_ERROR"
            if isinstance(analysis, Mapping) else False
        )
        if status not in {"REVIEW_REQUIRED", "REJECTED"} and not integrity:
            continue
        reasons = list(eligibility.get("user_reasons") or human_reasons(eligibility.get("reason")))
        integrity_reason = str(analysis.get("integrity_reason") or "").strip() if integrity else ""
        if integrity_reason and integrity_reason not in reasons:
            reasons.append(integrity_reason)
        issue_codes = list(eligibility.get("reason_codes") or [])
        if integrity and "REPORTING_INTEGRITY_ERROR" not in issue_codes:
            issue_codes.append("REPORTING_INTEGRITY_ERROR")
        final_status = (
            status if status in {"REVIEW_REQUIRED", "REJECTED"}
            else "REVIEW_REQUIRED" if integrity else status or "UNKNOWN"
        )
        problems.append({
            "ticker": str(report.get("ticker") or "UNKNOWN"),
            "final_status": final_status,
            "issue_class": "REPORTING_INTEGRITY_ERROR" if integrity else final_status,
            "issue_codes": issue_codes,
            "reasons": reasons or ["No structured reason was recorded."],
            "reporting_integrity_error": integrity,
            "review_required": final_status == "REVIEW_REQUIRED",
        })
    return problems


def _batch_outcome(payload: Mapping[str, Any], *, production_published: bool = False) -> dict[str, int]:
    reports = [item for item in (payload.get("ticker_reporting") or []) if isinstance(item, Mapping)]
    actions = [str(item.get("final_action") or "") for item in reports]
    analysis = analysis_reporting_counts(reports)
    counts = reporting_counts(reports) if reports else {
        "requested": 0, "new": 0, "already_present": 0,
        "review_required": 0, "rejected": 0,
    }
    tested = sum(
        action.startswith("Tested successfully") or action.startswith("Existing ticker - V2")
        for action in actions
    )
    report_stages = {str((item.get("after") or {}).get("stage") or "") for item in reports}
    test_actions = sum(
        action.startswith("Tested successfully")
        or action.startswith("Existing ticker - V2")
        or action in {"Review required", "Rejected"}
        for action in actions
    )
    published = actions.count("Added") if production_published else 0
    return {
        "requested": int(counts.get("requested") or 0),
        "new": int(counts.get("new") or 0),
        "already_present": int(counts.get("already_present") or 0),
        "tested_successfully": tested,
        "test_completed": len(reports) if report_stages == {"COPY_ONLY_APPLY"} or test_actions == len(reports) else 0,
        "review_required": int(counts.get("review_required") or actions.count("Review required")),
        "rejected": int(counts.get("rejected") or actions.count("Rejected")),
        "published_added": published,
        "added": published,
        "existing_rebuilt": actions.count("Existing ticker - analysis rebuilt") if production_published else 0,
        **analysis,
    }


def _child_reason(payload: Mapping[str, Any], child: Any, fallback: str) -> str:
    for value in (
        payload.get("user_failure_reason"), payload.get("outcome_message"),
        payload.get("message"), _value(child, "message"), payload.get("error"),
    ):
        if str(value or "").strip():
            return str(value).strip().rstrip(".") + "."
    errors = payload.get("errors") or []
    if errors:
        first = errors[0]
        if isinstance(first, Mapping):
            value = first.get("message") or first.get("error") or first.get("code")
        else:
            value = first
        if str(value or "").strip():
            return str(value).strip().rstrip(".") + "."
    return fallback


def _production_write_count(payload: Mapping[str, Any], *, completed: bool) -> int:
    activity = payload.get("publication_activity") or {}
    replacements = activity.get("live_replacements") if isinstance(activity, Mapping) else None
    if isinstance(replacements, list):
        return len(replacements)
    value = payload.get("production_writes")
    if isinstance(value, int):
        return value
    if payload.get("write_boundary_crossed"):
        return 1
    return 1 if completed else 0


def _terminal_summary(
    *, stage: str, child: Any, payload: Mapping[str, Any],
    workflow_outcome: str, requested_count: int, production_entered: bool,
    production_completed: bool, fallback_reason: str,
) -> dict[str, Any]:
    reports = [item for item in (payload.get("ticker_reporting") or []) if isinstance(item, Mapping)]
    problems = _problem_items(reports)
    review_count = sum(item["review_required"] for item in problems)
    integrity_count = sum(item["reporting_integrity_error"] for item in problems)
    child_outcome = str(_value(child, "outcome") or payload.get("outcome") or "UNKNOWN")
    controlled_review = (
        bool(problems)
        and stage != "Production update"
        and child_outcome in {"COMPLETED", "PARTIALLY_COMPLETED", "REVIEW_REQUIRED"}
    )
    if controlled_review and workflow_outcome != "COMPLETED":
        stop_kind = "REVIEW_REQUIRED"
        noun = "ticker" if len(problems) == 1 else "tickers"
        verb = "requires" if len(problems) == 1 else "require"
        integrity_note = "; reporting integrity requires attention" if integrity_count else ""
        headline = (
            f"Workflow stopped after {stage} because {len(problems)} {noun} {verb} review"
            f"{integrity_note}."
        )
        next_action = str(payload.get("recommended_next_action") or "Review the listed tickers and rerun the intended batch after resolving their issues.")
    elif workflow_outcome == "COMPLETED":
        stop_kind = "CLEAN_COMPLETION"
        headline = "Full workflow completed successfully."
        next_action = "No corrective operator action is required."
    else:
        stop_kind = "TECHNICAL_FAILURE"
        headline = _child_reason(payload, child, fallback_reason)
        next_action = str(payload.get("recommended_next_action") or "Review the stage error and rerun only after correcting its cause.")
    batch = _batch_outcome(payload, production_published=production_completed)
    if not batch["requested"]:
        batch["requested"] = requested_count
    return {
        "authoritative_stage": stage,
        "child_run_id": _value(child, "run_id"),
        "child_status": _value(child, "status") or payload.get("status") or "UNKNOWN",
        "child_outcome": child_outcome,
        "workflow_outcome": workflow_outcome,
        "stop_kind": stop_kind,
        "headline": headline,
        "reason": headline,
        "affected_item_count": len(problems),
        "review_required_count": review_count,
        "reporting_integrity_error_count": integrity_count,
        "problem_items": problems,
        "batch_outcome": batch,
        "production_entered": production_entered,
        "production_completed": production_completed,
        "production_database_writes": _production_write_count(payload, completed=production_completed),
        "recommended_next_action": next_action,
        "source": "STRUCTURED_CHILD_RESULT",
    }


def workflow_ui_summary(result: Mapping[str, Any]) -> tuple[str, ...]:
    terminal = result.get("terminal_summary") or {}
    batch = result.get("final_batch_outcome") or terminal.get("batch_outcome") or {}
    stage_label = "Completed stage" if result.get("outcome") in {"COMPLETED", "NO_CHANGE"} else "Stopped stage"
    rows = [
        f"Workflow: {str(result.get('outcome') or 'UNKNOWN').replace('_', ' ').title()}.",
        f"{stage_label}: {terminal.get('authoritative_stage') or result.get('current_stage') or 'Not recorded'}.",
        str(terminal.get("headline") or result.get("stop_reason") or "No terminal reason was recorded."),
    ]
    if batch:
        rows.append(
            f"Tested successfully: {batch.get('tested_successfully', 0)}; "
            f"review required: {batch.get('review_required', 0)}; rejected: {batch.get('rejected', 0)}."
        )
    problems = terminal.get("problem_items") or []
    if problems:
        rows.append("Affected tickers: " + ", ".join(str(item.get("ticker")) for item in problems) + ".")
    rows.append(f"Production ran: {'Yes' if terminal.get('production_entered') else 'No'}.")
    return tuple(rows)


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
    terminal = result.get("terminal_summary") or {}
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
    ]
    if result.get("outcome") not in {"COMPLETED", "NO_CHANGE"}:
        lines.extend([
            "", "## Failure / Review Summary", "",
            f"- Terminal workflow result: {result.get('outcome', 'UNKNOWN')}",
            f"- Workflow stopped at: {terminal.get('authoritative_stage') or result.get('current_stage') or 'Unknown'}",
            f"- Classification: {terminal.get('stop_kind', 'TECHNICAL_FAILURE')}",
            f"- Production entered: {'Yes' if terminal.get('production_entered') else 'No'}",
            f"- Production database writes: {terminal.get('production_database_writes', 0)}",
            f"- Reason: {terminal.get('headline') or result.get('stop_reason') or 'Not recorded'}",
            f"- Affected tickers/items: {terminal.get('affected_item_count', 0)}",
        ])
        for item in terminal.get("problem_items") or []:
            lines.extend([
                "",
                f"### {item.get('ticker', 'UNKNOWN')} - {item.get('final_status', 'UNKNOWN')}",
                "",
                f"- Error/review classification: {item.get('issue_class', 'UNKNOWN')}",
                f"- Issue codes: {', '.join(item.get('issue_codes') or []) or 'Not recorded'}",
            ])
            lines.extend(f"- {reason}" for reason in item.get("reasons") or [])
        lines.extend([
            "",
            f"- Recommended operator action: {terminal.get('recommended_next_action') or 'Review the terminal stage evidence before retrying.'}",
        ])
    lines.extend([
        "", "## Stage Results", "",
        "| Stage | Result | Duration | Run ID |",
        "| --- | --- | --- | --- |",
    ])
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
            f"- Requested ticker count: {batch.get('requested', len(result.get('requested_inputs') or []))}",
            f"- New tickers: {batch.get('new', 0)}",
            f"- Already present: {batch.get('already_present', 0)}",
            f"- Test completed for: {batch.get('test_completed', 0)}",
            f"- Tested successfully: {batch.get('tested_successfully', 0)}",
            f"- Published/added: {batch.get('published_added', 0)}",
            f"- Existing tickers included in rebuild: {batch.get('existing_rebuilt', 0)}",
            f"- Review required: {batch.get('review_required', 0)}",
            f"- Rejected: {batch.get('rejected', 0)}",
            f"- Expected no-quarterly-history: {batch.get('no_usable_quarterly_history', 0)}",
            f"- Reporting integrity errors: {batch.get('reporting_integrity_errors', 0)}",
            f"- Production executed: {'Yes' if terminal.get('production_entered') or any(stage.get('stage') == 'Production update' for stage in stages) else 'No'}",
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

    persist()
    try:
        emit("Preview", 1, "RUNNING", "Preview - Running")
        stage_started = utc_now()
        preview = adapter.preview_stage(child_progress("Preview", 1))
        stage_completed = utc_now()
        preview_payload = _load_result(run_root, _value(preview, "run_id"))
        preview_record = _stage_record("Preview", preview, stage_started, stage_completed)
        result["stages"].append(preview_record)
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
            terminal = _terminal_summary(
                stage="Preview", child=preview, payload=preview_payload,
                workflow_outcome=result["outcome"], requested_count=len(adapter.requested_inputs),
                production_entered=False, production_completed=False,
                fallback_reason="Preview did not authorize Test on copies.",
            )
            result["terminal_summary"] = terminal
            result["stop_reason"] = terminal["headline"]
            if adapter.operation_type == AdminOperationType.ADD_TICKERS:
                result["final_batch_outcome"] = terminal["batch_outcome"]
            preview_record["child_summary"] = terminal
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
            test_payload = _load_result(run_root, _value(test, "run_id"))
            test_record = _stage_record("Test on copies", test, stage_started, stage_completed)
            result["stages"].append(test_record)
            test_batch = _batch_outcome(test_payload)
            test_problems = _problem_items([
                item for item in (test_payload.get("ticker_reporting") or []) if isinstance(item, Mapping)
            ])
            if adapter.operation_type == AdminOperationType.ADD_TICKERS:
                result["test_batch_outcome"] = test_batch
                result["final_batch_outcome"] = test_batch
            if _value(test, "status") != "COMPLETED" or _value(test, "outcome") != "COMPLETED":
                result["manual_test_retry_available"] = adapter.operation_type == AdminOperationType.ADD_TICKERS
                result["preview_test_rerun_required"] = adapter.operation_type == AdminOperationType.REFRESH_FUNDAMENTALS
                stop("Test on copies", _value(test, "message") or "Test on copies failed.")
                terminal = _terminal_summary(
                    stage="Test on copies", child=test, payload=test_payload,
                    workflow_outcome=result["outcome"], requested_count=len(adapter.requested_inputs),
                    production_entered=False, production_completed=False,
                    fallback_reason="Test on copies failed.",
                )
                result["terminal_summary"] = terminal
                result["stop_reason"] = terminal["headline"]
                test_record["child_summary"] = terminal
                if _value(test, "status") == "COMPLETED" or test_problems:
                    result["final_completed_stage"] = "Test on copies"
            else:
                result["test_run_id"] = _value(test, "run_id")
                result["manual_production_available"] = True
                integrity = analysis_reporting_counts(list(test_payload.get("ticker_reporting") or []))
                result["final_completed_stage"] = "Test on copies"
                emit("Test on copies", 2, "COMPLETED", "Test on copies - Completed")
                if integrity["reporting_integrity_errors"]:
                    stop(
                        "Test on copies",
                        "Full workflow stopped after Test on copies because reporting integrity requires attention. Manual Production review remains available.",
                    )
                    terminal = _terminal_summary(
                        stage="Test on copies", child=test, payload=test_payload,
                        workflow_outcome=result["outcome"], requested_count=len(adapter.requested_inputs),
                        production_entered=False, production_completed=False,
                        fallback_reason="Test on copies completed, but reporting integrity requires attention.",
                    )
                    result["terminal_summary"] = terminal
                    result["stop_reason"] = terminal["headline"]
                    test_record["child_summary"] = terminal

        if result["workflow_status"] == "RUNNING":
            emit("Production update", 3, "RUNNING", "Production update - Running")
            stage_started = utc_now()
            production = adapter.production_stage(preview, test, child_progress("Production update", 3))
            stage_completed = utc_now()
            production_payload = _load_result(run_root, _value(production, "run_id"))
            production_record = _stage_record("Production update", production, stage_started, stage_completed)
            result["stages"].append(production_record)
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
                production_batch = _batch_outcome(production_payload, production_published=True)
                if adapter.operation_type == AdminOperationType.ADD_TICKERS:
                    result["final_batch_outcome"] = {
                        **(result.get("test_batch_outcome") or {}),
                        **production_batch,
                        "tested_successfully": (result.get("test_batch_outcome") or {}).get(
                            "tested_successfully", production_batch["tested_successfully"]
                        ),
                        "test_completed": (result.get("test_batch_outcome") or {}).get(
                            "test_completed", production_batch["test_completed"]
                        ),
                    }
                result["terminal_summary"] = _terminal_summary(
                    stage="Production update", child=production, payload=production_payload,
                    workflow_outcome="COMPLETED", requested_count=len(adapter.requested_inputs),
                    production_entered=True, production_completed=True,
                    fallback_reason="Production update completed successfully.",
                )
                production_record["child_summary"] = result["terminal_summary"]
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
                terminal = _terminal_summary(
                    stage="Production update", child=production, payload=production_payload,
                    workflow_outcome=result["outcome"], requested_count=len(adapter.requested_inputs),
                    production_entered=True, production_completed=False,
                    fallback_reason="Production update failed or stopped.",
                )
                result["terminal_summary"] = terminal
                result["stop_reason"] = terminal["headline"]
                production_record["child_summary"] = terminal
    except Exception as exc:
        stop(result["current_stage"], f"Workflow orchestration failed: {type(exc).__name__}: {exc}", failed=True)
        result["terminal_summary"] = _terminal_summary(
            stage=result["current_stage"], child=None,
            payload={"error": result["stop_reason"]}, workflow_outcome=result["outcome"],
            requested_count=len(adapter.requested_inputs),
            production_entered=any(stage["stage"] == "Production update" for stage in result["stages"]),
            production_completed=False, fallback_reason=result["stop_reason"],
        )
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
