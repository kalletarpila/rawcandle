from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, sha256_file
from rawcandle.fundamentals.admin.contracts import fingerprint
from rawcandle.fundamentals.admin.redaction import redact, redact_text
from rawcandle.io_atomic import write_text_atomic


OPERATION_REPORT_NAME = "operation_report.md"
WORKFLOW_REPORT_NAME = "workflow_report.md"

STAGE_LABELS = {
    "PREVIEW": "Preview",
    "CURRENT_STATE_AUDIT": "Preview",
    "CANDIDATE_PREVIEW": "Preview",
    "PROTECTED_PRODUCTION_PREVIEW": "Preview",
    "ACTIVE_TAXONOMY_PREVIEW": "Preview",
    "READ_ONLY_AUDIT": "Preview",
    "COPY_ONLY_APPLY": "Test on copies",
    "PRODUCTION_APPLY": "Production update",
    "PRODUCTION_NO_CHANGE_APPLY": "Production update",
    "PROTECTED_PRODUCTION_NO_CHANGE_VERIFY": "Production update",
    "TRANSACTION_REHEARSAL": "Production update",
    "FULL_WORKFLOW": "Full workflow",
}


@dataclass(frozen=True)
class OperationReportSummary:
    run_id: str
    operation_type: str
    outcome: str
    mode: str
    summary_rows: tuple[str, ...]
    report_path: str | None
    report_sha256: str | None


def _load_json(path: Path) -> Mapping[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _duration_seconds(started: Any, completed: Any) -> float | None:
    if not started or not completed:
        return None
    try:
        start = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
        return max(0.0, (end - start).total_seconds())
    except Exception:
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def operation_stage(mode: Any) -> str:
    return STAGE_LABELS.get(str(mode or ""), "Recorded run")


def operation_result(result: Mapping[str, Any]) -> str:
    outcome = str(result.get("outcome") or "RECORDED").upper()
    if outcome in {"COMPLETED", "APPLIED", "READY_TO_APPLY"}:
        return "Completed"
    if outcome == "NO_CHANGE":
        return "No changes"
    if outcome in {"FAILED_ROLLED_BACK", "ROLLED_BACK"}:
        return "Rolled back"
    if outcome == "CRITICAL_ROLLBACK_FAILED":
        return "Critical rollback failure"
    if outcome in {"FAILED", "ERROR", "INTERRUPTED"}:
        return "Failed"
    return outcome.replace("_", " ").title()


def final_status_message(result: Mapping[str, Any]) -> str:
    stage = operation_stage(result.get("mode"))
    outcome = str(result.get("outcome") or "").upper()
    if stage == "Production update":
        if outcome in {"COMPLETED", "NO_CHANGE"}:
            return "Production update completed successfully."
        if outcome in {"FAILED_ROLLED_BACK", "ROLLED_BACK"}:
            return "Production update failed. All production database changes were rolled back successfully."
        if outcome == "CRITICAL_ROLLBACK_FAILED":
            return "CRITICAL: Production update failed and rollback did not complete. Immediate operator review is required."
        return "Production update failed before any production database changes were made."
    if stage == "Test on copies":
        return "Test on copies completed successfully." if outcome == "COMPLETED" else "Test on copies failed."
    if stage == "Preview":
        if outcome in {"COMPLETED", "NO_CHANGE"}:
            return "Preview completed."
        if result.get("user_error"):
            return f"{str(result['user_error']).rstrip('.')}. No database changes were made."
        failed_stage = str(result.get("failed_stage") or "").replace("_", " ").lower()
        location = f" during {failed_stage}" if failed_stage else ""
        return f"Preview failed{location}. No database changes were made."
    return f"{stage}: {operation_result(result)}."


def production_failure_reason(result: Mapping[str, Any]) -> str | None:
    explicit = str(result.get("user_failure_reason") or "").strip()
    if explicit:
        return explicit
    error = str(result.get("error") or "")
    translations = (
        ("ADMIN_PRODUCTION_UPDATE_ALREADY_RUNNING", "Another Administration operation currently holds the production lock."),
        ("SCHEDULER_ALREADY_RUNNING", "The scheduler currently holds the database update lock."),
        ("ADMIN_INSUFFICIENT_DISK", "There is not enough free disk space for backup, rebuild, and rollback."),
        ("STALE", "The authoritative source state changed after the tested Preview."),
        ("MISMATCH", "The saved Preview or Test evidence no longer matches the production request."),
        ("CHANGED_DURING", "An authoritative source database changed during production preflight."),
        ("MATCHING_SUCCESSFUL_TEST_REQUIRED", "The matching successful Test on copies evidence is missing or invalid."),
    )
    for code, message in translations:
        if code in error:
            return message
    return None


def taxonomy_preview_presentation(result: Mapping[str, Any]) -> dict[str, Any] | None:
    if result.get("operation_type") != "CHECK_UPDATE_TAXONOMY" or result.get("mode") not in {
        "CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "PROTECTED_PRODUCTION_PREVIEW",
    }:
        return None
    downstream = _mapping(result.get("downstream"))
    protected = _mapping(downstream.get("production_preview"))
    counts = _mapping(result.get("summary_counts")) or _mapping(downstream.get("change_counts")) or _mapping(protected.get("change_counts"))
    active = _mapping(downstream.get("active_taxonomy")) or _mapping(protected.get("active_taxonomy")) or _mapping(result.get("active_taxonomy"))
    active_counts = _mapping(active.get("counts"))
    blockers = _sequence(result.get("blockers")) or _sequence(downstream.get("blockers")) or _sequence(protected.get("blockers"))
    proposed = _sequence(result.get("proposed_changes")) or _sequence(downstream.get("proposed_changes")) or _sequence(protected.get("proposed_changes"))
    change_keys = ("MEMBERSHIP_ADDED", "MEMBERSHIP_REMOVED", "MEMBERSHIP_CHANGED", "ROLE_TIER_CHANGED", "PRIMARY_DESIGNATION_CHANGED")
    alias_keys = ("additions", "removals", "role_or_tier_changes", "primary_changes")
    try:
        changes = max(sum(int(counts.get(key, 0)) for key in change_keys), sum(int(counts.get(key, 0)) for key in alias_keys), int(counts.get("semantic_changes", 0)), len(proposed))
        eligible = int(counts.get("automatic_apply_eligible", 0))
        blocked = max(int(counts.get("blocked", 0)), int(counts.get("blockers", 0)), int(counts.get("unresolved_identities", 0)), len(blockers))
        unexpected = any(int(value) != 0 for key, value in counts.items() if key not in {*change_keys, *alias_keys, "semantic_changes", "UNCHANGED", "automatic_apply_eligible", "blocked", "blockers", "unresolved_identities"})
    except (TypeError, ValueError):
        return None
    execution_ok = str(result.get("outcome")) not in {"FAILED", "ERROR", "INTERRUPTED", "ROLLED_BACK"} and not result.get("errors")
    no_change = bool(result.get("outcome") in {"COMPLETED", "NO_CHANGE"} and execution_ok and counts and active_counts and not changes and not eligible and not blocked and not unexpected)
    if not execution_ok:
        business = "FAILED"
    elif blocked:
        business = "BLOCKED"
    elif changes and eligible == 0:
        business = "REVIEW_REQUIRED"
    elif changes:
        business = "CHANGES_AVAILABLE"
    elif no_change:
        business = "NO_CHANGE"
    else:
        business = "REVIEW_REQUIRED"
    invocations = _mapping(downstream.get("invocation_counts"))
    if invocations and all(isinstance(value, int) and value == 0 for value in invocations.values()):
        downstream_text = "No downstream calculations were required or run."
    elif invocations:
        downstream_text = "Downstream calculations ran: " + ", ".join(f"{key} {value}" for key, value in sorted(invocations.items())) + "."
    elif str(result.get("mode", "")).endswith("PREVIEW") or result.get("mode") == "CURRENT_STATE_AUDIT":
        downstream_text = "Potential downstream work was evaluated. No calculations were run during Preview."
    else:
        downstream_text = "Downstream calculation status is unavailable."
    domain = str(result.get("taxonomy_domain") or active.get("domain") or "unknown")
    version = _mapping(active.get("version"))
    return {
        "business_outcome": business,
        "domain": domain,
        "version": version.get("taxonomy_version_code") or result.get("active_version"),
        "memberships": active_counts.get("rows"),
        "tickers": active_counts.get("tickers"),
        "counts": counts,
        "blockers": blocked,
        "changes": changes,
        "eligible": eligible,
        "candidate": _mapping(downstream.get("candidate")) or _mapping(protected.get("candidate")) or _mapping(result.get("candidate")),
        "downstream_text": downstream_text,
    }


def _taxonomy_no_change_rows(info: Mapping[str, Any], result: Mapping[str, Any]) -> tuple[str, ...]:
    rows = ["Taxonomy is up to date", "No changes", f"Taxonomy: {info['domain']}"]
    if info.get("version"):
        rows.append(f"Active version: {info['version']}")
    if info.get("tickers") is not None:
        rows.append(f"{info['tickers']} tickers checked.")
    if info.get("memberships") is not None:
        rows.append(f"{info['memberships']} memberships checked.")
    rows.extend((
        "0 additions and 0 removals.",
        "0 role or tier changes and 0 primary-membership changes.",
        "0 review blockers.",
        "No production writes. No update is required.",
        info["downstream_text"],
    ))
    duration = _duration_seconds(result.get("started_at_utc"), result.get("completed_at_utc"))
    if duration is not None:
        minutes, seconds = divmod(round(duration), 60)
        rows.append(f"Completed in {minutes} min {seconds} sec")
    return tuple(rows)


def _taxonomy_preview_rows(info: Mapping[str, Any], result: Mapping[str, Any]) -> tuple[str, ...]:
    if info["business_outcome"] == "NO_CHANGE":
        return _taxonomy_no_change_rows(info, result)
    label = {
        "CHANGES_AVAILABLE": "Changes available",
        "REVIEW_REQUIRED": "Review required",
        "BLOCKED": "Update blocked",
        "FAILED": "Preview failed",
    }[info["business_outcome"]]
    rows = [f"Taxonomy: {info['domain']}", label]
    if info.get("version"):
        rows.append(f"Active version: {info['version']}")
    if info.get("memberships") is not None:
        rows.append(f"{info['memberships']} memberships checked.")
    rows.extend((f"{info['changes']} proposed changes.", f"{info['blockers']} review blockers.", info["downstream_text"]))
    duration = _duration_seconds(result.get("started_at_utc"), result.get("completed_at_utc"))
    if duration is not None:
        minutes, seconds = divmod(round(duration), 60)
        rows.append(f"Completed in {minutes} min {seconds} sec")
    return tuple(rows)


def _safe_run_dir(run_id: str, root: Path = ADMIN_RUN_ROOT) -> Path:
    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        raise ValueError("invalid run_id")
    base = root.resolve()
    raw = base / run_id
    if raw.is_symlink():
        raise ValueError("run path symlink is not allowed")
    resolved = raw.resolve()
    if base != resolved and base not in resolved.parents:
        raise ValueError("run path escapes admin root")
    if not resolved.is_dir():
        raise FileNotFoundError("admin run not found")
    return resolved


def resolve_operation_report_download(
    run_id: str,
    artifact_name: str = OPERATION_REPORT_NAME,
    *,
    root: Path = ADMIN_RUN_ROOT,
) -> Path:
    if artifact_name not in {OPERATION_REPORT_NAME, WORKFLOW_REPORT_NAME}:
        raise ValueError("invalid operation report artifact")
    run_dir = _safe_run_dir(run_id, root)
    path = (run_dir / artifact_name).resolve()
    if path.parent != run_dir:
        raise ValueError("operation report path escapes run directory")
    try:
        file_stat = path.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise FileNotFoundError("operation report not found") from exc
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise FileNotFoundError("operation report not found")
    return path


def build_operation_summary(result: Mapping[str, Any], progress: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    taxonomy = taxonomy_preview_presentation(result)
    if taxonomy:
        return _taxonomy_preview_rows(taxonomy, result)
    if result.get("operation_type") == "REFRESH_FUNDAMENTALS":
        counts = _mapping(result.get("summary_counts"))
        if result.get("mode") == "COPY_ONLY_APPLY":
            downstream = _mapping(result.get("downstream"))
            provider = _mapping(downstream.get("provider"))
            canonical = _mapping(downstream.get("canonical"))
            bootstrap = _mapping(canonical.get("publication_date_bootstrap"))
            analysis = _mapping(downstream.get("analysis"))
            return (
                final_status_message(result),
                f"Changed known tickers tested: {counts.get('effective_changed_known', 0)}.",
                f"Complete ARQ/MRQ replacement completed for {provider.get('ticker_count', 0)} tickers.",
                f"First-public preservation map: {bootstrap.get('preservation_map_applied', 0)}/{bootstrap.get('preservation_map_applicable_existing_quarters', 0)} existing quarters.",
                f"Full V2, RP V2 and RV rebuild: {analysis.get('status', 'not completed')}.",
                "Production writes: 0. Production update is not yet enabled for Refresh Fundamentals.",
            )
        discovery = _mapping(_mapping(result.get("refresh_preview")).get("discovery"))
        date_state = _mapping(_mapping(result.get("refresh_preview")).get("publication_date_state"))
        return (
            final_status_message(result),
            f"Sharadar discovery: {discovery.get('returned_source_rows', 0)} rows across {discovery.get('unique_changed_source_tickers', 0)} tickers.",
            f"Known tickers with effective changes: {counts.get('effective_changed_known', 0)}.",
            f"New quarter: {counts.get('NEW_QUARTER', 0)}; historical revision: {counts.get('HISTORICAL_REVISION', 0)}; both: {counts.get('NEW_QUARTER_AND_REVISION', 0)}.",
            f"Source removal: {counts.get('SOURCE_REMOVAL', 0)}; no effective change: {counts.get('NO_EFFECTIVE_CHANGE', 0)}.",
            f"Source-window retention: {counts.get('newly_aged_out_source_rows', 0)} newly aged-out rows "
            f"({counts.get('retained_arq', 0)} ARQ, {counts.get('retained_mrq', 0)} MRQ); "
            f"{counts.get('already_retained_carry_forward', 0)} already retained; "
            f"{counts.get('true_source_removals', 0)} true removals; "
            f"{counts.get('ambiguous_removals', 0)} ambiguous.",
            f"Fiscal identity revisions: {counts.get('fiscal_identity_revisions', 0)}; "
            f"requiring review: {counts.get('fiscal_identity_revisions_requiring_review', 0)}.",
            f"Not in canonical universe: {counts.get('NOT_IN_CANONICAL_UNIVERSE', 0)}; review required: {counts.get('REVIEW_REQUIRED', 0)}.",
            f"First-public dates: {date_state.get('established_first_public_dates', 0)} established; "
            f"historical bootstrap eligible: {date_state.get('historical_bootstrap_eligible', 0)}; "
            f"repair required: {date_state.get('repair_required', 0)}.",
        )
    counts = _mapping(result.get("summary_counts"))
    downstream = _mapping(result.get("downstream"))
    rollback = _mapping(result.get("rollback"))
    warnings = _sequence(result.get("warnings"))
    blockers = _sequence(result.get("blockers"))
    stage = operation_stage(result.get("mode"))
    rows = [final_status_message(result)]
    if stage == "Production update" and str(result.get("outcome") or "").upper() in {"FAILED", "ERROR"}:
        reason = production_failure_reason(result)
        if reason:
            rows.append(reason)
        retry = _mapping(result.get("retry_authorization"))
        if retry.get("direct_production_retry_available"):
            rows.append("The successful Preview and Test remain valid; Production update may be retried directly.")
        elif retry:
            rows.append("Preview and Test must be rerun before another Production update.")
    ticker_reporting = _sequence(result.get("ticker_reporting"))
    if result.get("operation_type") == "ADD_TICKERS" and ticker_reporting:
        from rawcandle.fundamentals.admin.ticker_reporting import summary_rows

        rows.extend(summary_rows(ticker_reporting))
    elif counts:
        for key in ("requested", "eligible", "applied", "accepted", "changed", "already_present", "failed"):
            if key in counts:
                rows.append(f"{str(key).replace('_', ' ').title()}: {counts[key]}.")
    if downstream:
        active_taxonomy = _mapping(downstream.get("active_taxonomy"))
        if active_taxonomy:
            version = active_taxonomy.get("version")
            if isinstance(version, Mapping):
                version = version.get("taxonomy_version_code") or version.get("version")
            rows.append("Active taxonomy: " + str(version or active_taxonomy.get("domain", "unknown")) + ".")
        invocation_counts = downstream.get("invocation_counts")
        if isinstance(invocation_counts, Mapping):
            if stage != "Preview" and any(invocation_counts.values()):
                rows.append("Full V2 analysis, RP V2 and RV completed successfully.")
        elif result.get("mode") in {"CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "PROTECTED_PRODUCTION_PREVIEW"}:
            rows.append("Potential downstream work was evaluated. No calculations were run during Preview.")
    if rollback:
        if rollback.get("status") == "ROLLED_BACK":
            rows.append("The operation was rolled back.")
    if warnings:
        rows.append(f"{len(warnings)} warning(s) recorded.")
    if blockers:
        rows.append(f"{len(blockers)} blocker(s) recorded.")
    return tuple(rows[:12])


def _progress_events(run_dir: Path, *, limit: int = 8) -> list[Mapping[str, Any]]:
    path = run_dir / "progress_events.jsonl"
    if not path.is_file() or path.is_symlink():
        return []
    events: list[Mapping[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                parsed = json.loads(line)
                if isinstance(parsed, Mapping):
                    events.append(parsed)
    except Exception:
        return []
    return events[-limit:]


def render_operation_report(
    *,
    run_id: str,
    result: Mapping[str, Any],
    request: Mapping[str, Any] | None = None,
    progress: Mapping[str, Any] | None = None,
    events: list[Mapping[str, Any]] | None = None,
) -> str:
    result = redact(result)
    request = redact(request or {})
    summary_rows = build_operation_summary(result, progress)
    taxonomy = taxonomy_preview_presentation(result)
    operation = {
        "ADD_TICKERS": "Add Tickers",
        "REFRESH_FUNDAMENTALS": "Refresh Fundamentals",
        "CHECK_UPDATE_SECTOR_INDUSTRY": "Sector and Industry",
        "CHECK_UPDATE_TAXONOMY": "Taxonomy",
    }.get(str(result.get("operation_type")), "Administration")
    mode = str(result.get("mode") or "")
    preview_only = mode in {"PREVIEW", "CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "PROTECTED_PRODUCTION_PREVIEW", "READ_ONLY_AUDIT"}
    counts = _mapping(result.get("summary_counts"))
    downstream = _mapping(result.get("downstream"))
    request_data = request or _mapping(result.get("request"))
    inputs = _sequence(request_data.get("normalized_inputs")) or _sequence(request_data.get("requested_inputs"))

    def section(lines: list[str], title: str, rows: list[str] | tuple[str, ...]) -> None:
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- {row}" for row in rows if row)

    duration = _duration_seconds(result.get("started_at_utc"), result.get("completed_at_utc"))
    duration_text = "Not reached"
    if duration is not None:
        minutes, seconds = divmod(round(duration), 60)
        duration_text = f"{minutes} min {seconds} sec"
    executive = [
        f"Operation: {operation}",
        f"Stage: {operation_stage(mode)}",
        f"Result: {operation_result(result)}",
        f"Duration: {duration_text}",
        *summary_rows,
    ]
    lines = ["# Fundamentals Administration Operation Report"]
    section(lines, "Executive Summary", executive)
    if result.get("operation_type") == "ADD_TICKERS" and result.get("ticker_reporting"):
        from rawcandle.fundamentals.admin.ticker_reporting import render_ticker_sections

        lines.extend(["", render_ticker_sections(_sequence(result.get("ticker_reporting"))).rstrip()])

    checked = [f"Operation: {operation}."]
    if taxonomy:
        checked.append(f"Taxonomy domain: {taxonomy['domain']}.")
        if taxonomy.get("version"):
            checked.append(f"Active version: {taxonomy['version']}.")
        if taxonomy.get("tickers") is not None:
            checked.append(f"{taxonomy['tickers']} tickers checked.")
        if taxonomy.get("memberships") is not None:
            checked.append(f"{taxonomy['memberships']} memberships checked.")
    elif inputs:
        checked.append("Requested tickers: " + ", ".join(str(value) for value in inputs[:25]) + (" and more." if len(inputs) > 25 else "."))
    elif operation == "Sector and Industry":
        checked.append("The active operational universe was checked.")
    if result.get("network_used") is True:
        checked.append("Provider network data was used.")
    elif result.get("network_allowed") is not None:
        checked.append("Provider network data was not used.")
    failed = str(result.get("outcome") or "").upper() in {
        "FAILED", "ERROR", "INTERRUPTED", "ROLLED_BACK", "FAILED_ROLLED_BACK", "CRITICAL_ROLLBACK_FAILED",
    }
    section(lines, "What Was Checked", checked)
    if failed and inputs:
        section(lines, "Requested Inputs", [str(value) for value in inputs])
    if failed:
        errors = _sequence(result.get("errors"))
        first_error = errors[0] if errors and isinstance(errors[0], Mapping) else {}
        failure_rows = [final_status_message(result)]
        if operation_stage(mode) == "Production update":
            failure_rows.append("Production update did not modify production databases." if not result.get("write_boundary_crossed") else "See rollback evidence for database restoration status.")
            reason = production_failure_reason(result)
            if reason:
                failure_rows.append(reason)
            retry = _mapping(result.get("retry_authorization"))
            if retry.get("direct_production_retry_available"):
                failure_rows.append("Direct Production retry remains available; Preview and Test do not need to be rerun.")
            elif retry:
                failure_rows.append("Direct Production retry is unavailable; rerun Preview and Test.")
        if first_error.get("message"):
            failure_rows.append(str(first_error["message"]))
        section(lines, "Failure", failure_rows)
        section(
            lines,
            "Database Safety",
            ["No database writes were performed." if preview_only or result.get("database_safety") == "NO_DATABASE_WRITES" else "See rollback and write-boundary evidence below."],
        )
        completed_events = [
            event for event in (events or [])
            if str(event.get("stage_state")) == "COMPLETED"
        ]
        section(
            lines,
            "Completed Work",
            [
                f"{str(event.get('current_stage_id') or 'Stage').replace('_', ' ').title()}: {event.get('message') or 'Completed.'}"
                for event in completed_events
            ] or ["No stage completed before the failure."],
        )

    ticker_reporting = _sequence(result.get("ticker_reporting"))
    if taxonomy and taxonomy["business_outcome"] == "NO_CHANGE":
        changes = ["No additions or removals.", "No role or tier changes.", "No primary-membership changes."]
    elif taxonomy:
        changes = [f"{taxonomy['changes']} proposed changes found."]
    elif result.get("outcome") == "NO_CHANGE":
        changes = ["No changes were needed."]
    elif result.get("operation_type") == "ADD_TICKERS" and ticker_reporting:
        from rawcandle.fundamentals.admin.ticker_reporting import human_reasons

        changes = []
        for item in ticker_reporting:
            action = str(item.get("final_action") or "Not available")
            reasons = (item.get("eligibility") or {}).get("user_reasons") or human_reasons((item.get("eligibility") or {}).get("reason"))
            detail = "; ".join(str(reason) for reason in reasons) if action in {"Review required", "Rejected"} else ""
            changes.append(f"{item.get('ticker')}: {action}" + (f" - {detail}" if detail else "") + ".")
    else:
        changes = [f"{key.replace('_', ' ').title()}: {counts[key]}." for key in ("requested", "accepted", "changed", "already_present", "failed") if key in counts]
        for item in (_sequence(result.get("items")) or _sequence(result.get("item_results")))[:25]:
            if not isinstance(item, Mapping):
                continue
            ticker = item.get("ticker") or item.get("item_key")
            status = item.get("status") or item.get("decision")
            reason = item.get("reason")
            if ticker and status:
                status_label = str(status).replace("_", " ").title()
                clean_reason = str(reason or "").strip().rstrip(".")
                if mode == "COPY_ONLY_APPLY" and str(status).upper() == "APPLIED":
                    line = f"{ticker}: Successfully tested on copies"
                else:
                    if clean_reason.lower().startswith(status_label.lower() + " from"):
                        clean_reason = clean_reason[len(status_label):].strip()
                        if clean_reason.lower().startswith("from "):
                            clean_reason = clean_reason[5:]
                    line = f"{ticker}: {status_label}"
                    if clean_reason and "/" not in clean_reason and "\\" not in clean_reason:
                        line += f" - {clean_reason}"
                changes.append(line.rstrip(".") + ".")
        if not changes:
            changes = ["See the per-item run evidence for detailed changes."]
    section(lines, "Changes Found", changes)

    if preview_only and failed:
        actions = ["Preview stopped at the recorded failure stage.", "No database writes were performed."]
    elif preview_only:
        review_count = sum(
            str((item.get("eligibility") or {}).get("status") or "").upper() == "REVIEW_REQUIRED"
            for item in ticker_reporting
        )
        next_step = "Next step: resolve review items if needed, then run Test on copies." if review_count else "Next step: run Test on copies."
        actions = ["Preview checked the current state and recorded its findings.", "No database writes were performed.", next_step]
    elif mode == "COPY_ONLY_APPLY":
        from rawcandle.fundamentals.admin.ticker_reporting import analysis_reporting_counts

        analysis_counts = analysis_reporting_counts(ticker_reporting)
        if failed:
            next_step = "Next step: resolve the Test on copies failure before Production update."
        elif analysis_counts["reporting_integrity_errors"]:
            next_step = "Reporting integrity requires attention. Manual Production update remains backend-authorized by the successful Test, but automatic workflow progression is stopped."
        else:
            next_step = "Next step: Production update is available."
        actions = ["The proposed change was tested on isolated database copies.", "No production database writes were performed.", next_step]
    elif result.get("outcome") == "NO_CHANGE":
        actions = ["No production change was required."]
    else:
        actions = ["The protected operation ran. Review the final result for its outcome."]
    section(lines, "Actions Performed", actions)

    if taxonomy:
        impact = [taxonomy["downstream_text"]]
    else:
        invocations = _mapping(downstream.get("invocation_counts"))
        if invocations and all(isinstance(value, int) and value == 0 for value in invocations.values()):
            impact = ["No downstream calculations were required or run."]
        elif invocations:
            impact = [f"{str(key).replace('_', ' ').title()}: {value} run(s)." for key, value in sorted(invocations.items())]
        elif preview_only and failed:
            impact = ["No downstream calculations were run."]
        elif preview_only:
            impact = ["Potential downstream work was evaluated. No calculations were run during Preview."]
        else:
            impact = ["Downstream details are retained in the run evidence."]
    section(lines, "Downstream Impact", impact)

    if result.get("operation_type") == "ADD_TICKERS" and ticker_reporting:
        from rawcandle.fundamentals.admin.ticker_reporting import no_quarterly_history_tickers

        no_history = no_quarterly_history_tickers(ticker_reporting)
        if no_history:
            section(
                lines,
                "Analytical Limitations",
                [
                    f"{len(no_history)} ticker{'s' if len(no_history) != 1 else ''} {'have' if len(no_history) != 1 else 'has'} provider data but no usable quarterly ARQ history: {', '.join(no_history)}.",
                    "These tickers may be added successfully even though V2 analysis is not currently available.",
                ],
            )

    warnings = _sequence(result.get("warnings"))
    blockers = _sequence(result.get("blockers"))
    if taxonomy and not blockers and taxonomy["blockers"]:
        blockers = [f"{taxonomy['blockers']} review blockers were recorded."]
    notices = []
    review_reasons = {
        str((item.get("eligibility") or {}).get("reason") or "")
        for item in ticker_reporting
        if str((item.get("eligibility") or {}).get("status") or "").upper() == "REVIEW_REQUIRED"
    }
    for label, values in (("Warning", warnings), ("Blocker", blockers)):
        for value in values[:10]:
            detail = str(value.get("reason") or value.get("message") or value.get("status") or label) if isinstance(value, Mapping) else str(value)
            if result.get("operation_type") == "ADD_TICKERS" and detail in review_reasons:
                continue
            if result.get("operation_type") == "ADD_TICKERS":
                from rawcandle.fundamentals.admin.ticker_reporting import human_reasons

                translated = human_reasons(detail)
                detail = "; ".join(translated) if translated else detail
            if "/" in detail or "\\" in detail or "{" in detail:
                detail = "Details are available in the retained run evidence."
            notices.append(f"{label}: {detail}.")
    review_count = sum(
        str((item.get("eligibility") or {}).get("status") or "").upper() == "REVIEW_REQUIRED"
        for item in ticker_reporting
    )
    if review_count:
        notices.append("No operation-level blockers were found.")
        notices.append(f"{review_count} ticker{'s' if review_count != 1 else ''} require{'s' if review_count == 1 else ''} review.")
    if result.get("operation_type") == "ADD_TICKERS" and ticker_reporting:
        from rawcandle.fundamentals.admin.ticker_reporting import analysis_reporting_counts

        integrity_errors = analysis_reporting_counts(ticker_reporting)["reporting_integrity_errors"]
        if integrity_errors:
            notices.append(
                f"Warning: {integrity_errors} reporting integrity error{'s' if integrity_errors != 1 else ''} "
                f"{'require' if integrity_errors != 1 else 'requires'} attention."
            )
    section(lines, "Warnings or Blockers", notices or ["No warnings or blockers were found."])

    if taxonomy and taxonomy["business_outcome"] == "NO_CHANGE":
        final = ["No changes. No further action is required."]
    elif result.get("operation_type") == "ADD_TICKERS" and preview_only and ticker_reporting:
        from rawcandle.fundamentals.admin.ticker_reporting import reporting_counts

        ticker_counts = reporting_counts(ticker_reporting)
        eligible_noun = "ticker is" if ticker_counts["eligible"] == 1 else "tickers are"
        present_noun = "is" if ticker_counts["already_present"] == 1 else "are"
        review_verb = "requires" if ticker_counts["review_required"] == 1 else "require"
        next_step = "Next step: resolve review items if needed, then run Test on copies." if ticker_counts["review_required"] else "Next step: run Test on copies."
        final = [
            "Preview completed.",
            f"{ticker_counts['eligible']} {eligible_noun} eligible to add, {ticker_counts['already_present']} {present_noun} already present, and {ticker_counts['review_required']} {review_verb} review.",
            "No database writes were performed.",
            next_step,
        ]
    else:
        outcome = str(result.get("outcome") or "Recorded").replace("_", " ").title()
        final = [f"Result: {outcome}."]
        recommendation = None if mode in {"PREVIEW", "COPY_ONLY_APPLY"} else result.get("recommended_next_action")
        if isinstance(recommendation, str) and recommendation and "/" not in recommendation and "\\" not in recommendation:
            final.append(recommendation)
    section(lines, "Final Result", final)

    appendix = [f"Run ID: `{run_id}`"]
    for label, key in (("Started UTC", "started_at_utc"), ("Completed UTC", "completed_at_utc"), ("Preview fingerprint", "preview_fingerprint"), ("Result fingerprint", "result_fingerprint")):
        if result.get(key):
            appendix.append(f"{label}: `{result[key]}`")
    appendix.append(f"Report content fingerprint: `{fingerprint({'result': result, 'request': request_data, 'events': events or []})}`")
    if counts:
        appendix.append("Structured counts: " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)))
    active_taxonomy = _mapping(downstream.get("active_taxonomy"))
    if active_taxonomy.get("semantic_fingerprint"):
        appendix.append(f"Active taxonomy semantic fingerprint: `{active_taxonomy['semantic_fingerprint']}`")
    artifacts = _mapping(result.get("artifacts"))
    if artifacts:
        appendix.append("Artifact files: " + ", ".join(sorted({Path(str(value)).name for value in artifacts.values() if isinstance(value, str)})))
    if result.get("failed_stage"):
        appendix.append(f"Failure stage: `{result['failed_stage']}`")
    errors = _sequence(result.get("errors"))
    if errors and isinstance(errors[0], Mapping):
        if errors[0].get("type"):
            appendix.append(f"Exception class: `{errors[0]['type']}`")
        if errors[0].get("message"):
            appendix.append(f"Technical error: `{errors[0]['message']}`")
    elif result.get("error"):
        appendix.append(f"Technical error: `{result['error']}`")
    if result.get("artifact_dir"):
        appendix.append(f"Artifact directory: `{result['artifact_dir']}`")
    section(lines, "Technical Appendix", appendix)
    return redact_text("\n".join(lines).rstrip() + "\n")


def write_operation_report(run_id: str, *, root: Path = ADMIN_RUN_ROOT) -> OperationReportSummary:
    run_dir = _safe_run_dir(run_id, root)
    result = _load_json(run_dir / "result.json") or {}
    request = _load_json(run_dir / "request.json")
    progress = _load_json(run_dir / "progress_status.json") or _load_json(run_dir / "status.json")
    if result.get("operation_type") == "REFRESH_FUNDAMENTALS" and result.get("mode") in {"PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"}:
        from rawcandle.fundamentals.admin.refresh_production import render_report

        report = render_report(result)
    elif result.get("operation_type") == "REFRESH_FUNDAMENTALS" and result.get("mode") == "COPY_ONLY_APPLY":
        from rawcandle.fundamentals.admin.refresh_copy_runtime import _render_report

        report = _render_report(result)
    elif result.get("operation_type") == "REFRESH_FUNDAMENTALS" and result.get("refresh_preview"):
        from rawcandle.fundamentals.admin.refresh_fundamentals import _render_refresh_report

        report = _render_refresh_report(result)
    elif result.get("mode") in {"PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"} and "write_set" in result:
        from rawcandle.fundamentals.admin.production_transaction import render_production_report
        report = render_production_report(result)
    else:
        report = render_operation_report(
            run_id=run_id,
            result=result,
            request=request,
            progress=progress,
            events=_progress_events(run_dir),
        )
    report_path = run_dir / OPERATION_REPORT_NAME
    write_text_atomic(report_path, report)
    manifest = {
        "run_id": run_id,
        "artifacts": [
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(run_dir.iterdir())
            if path.is_file() and not path.is_symlink() and path.name != "artifact_manifest.json"
        ],
    }
    write_text_atomic(
        run_dir / "artifact_manifest.json",
        json.dumps(redact(manifest), indent=2, sort_keys=True, allow_nan=False, default=str) + "\n",
    )
    return OperationReportSummary(
        run_id=run_id,
        operation_type=str(result.get("operation_type", "UNKNOWN")),
        outcome=str(result.get("outcome", "UNKNOWN")),
        mode=str(result.get("mode", "UNKNOWN")),
        summary_rows=build_operation_summary(result, progress),
        report_path=str(report_path),
        report_sha256=sha256_file(report_path),
    )
