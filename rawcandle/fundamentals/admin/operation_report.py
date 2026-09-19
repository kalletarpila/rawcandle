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
        return "Preview completed." if outcome in {"COMPLETED", "NO_CHANGE"} else "Preview failed."
    return f"{stage}: {operation_result(result)}."


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
    if artifact_name != OPERATION_REPORT_NAME:
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
    counts = _mapping(result.get("summary_counts"))
    downstream = _mapping(result.get("downstream"))
    rollback = _mapping(result.get("rollback"))
    warnings = _sequence(result.get("warnings"))
    blockers = _sequence(result.get("blockers"))
    duration = _duration_seconds(result.get("started_at_utc"), result.get("completed_at_utc"))
    stage = operation_stage(result.get("mode"))
    rows = [final_status_message(result)]
    if duration is not None:
        minutes, seconds = divmod(round(duration), 60)
        rows.append(f"Completed in {minutes} min {seconds} sec")
    if counts:
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
    section(lines, "What Was Checked", checked)

    if taxonomy and taxonomy["business_outcome"] == "NO_CHANGE":
        changes = ["No additions or removals.", "No role or tier changes.", "No primary-membership changes."]
    elif taxonomy:
        changes = [f"{taxonomy['changes']} proposed changes found."]
    elif result.get("outcome") == "NO_CHANGE":
        changes = ["No changes were needed."]
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
                    line = f"{ticker}: {status_label}"
                    if clean_reason and "/" not in clean_reason and "\\" not in clean_reason:
                        line += f" - {clean_reason}"
                changes.append(line.rstrip(".") + ".")
        if not changes:
            changes = ["See the per-item run evidence for detailed changes."]
    section(lines, "Changes Found", changes)

    if preview_only:
        actions = ["Preview checked the current state and recorded its findings.", "No database writes were performed.", "Next step: run Test on copies."]
    elif mode == "COPY_ONLY_APPLY":
        actions = ["The proposed change was tested on isolated database copies.", "No production database writes were performed.", "Next step: Production update is available after this successful test."]
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
        elif preview_only:
            impact = ["Potential downstream work was evaluated. No calculations were run during Preview."]
        else:
            impact = ["Downstream details are retained in the run evidence."]
    section(lines, "Downstream Impact", impact)

    warnings = _sequence(result.get("warnings"))
    blockers = _sequence(result.get("blockers"))
    if taxonomy and not blockers and taxonomy["blockers"]:
        blockers = [f"{taxonomy['blockers']} review blockers were recorded."]
    notices = []
    for label, values in (("Warning", warnings), ("Blocker", blockers)):
        for value in values[:10]:
            detail = str(value.get("reason") or value.get("message") or value.get("status") or label) if isinstance(value, Mapping) else str(value)
            if "/" in detail or "\\" in detail or "{" in detail:
                detail = "Details are available in the retained run evidence."
            notices.append(f"{label}: {detail}.")
    section(lines, "Warnings or Blockers", notices or ["No warnings or blockers were found."])

    if taxonomy and taxonomy["business_outcome"] == "NO_CHANGE":
        final = ["No changes. No further action is required."]
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
    section(lines, "Technical Appendix", appendix)
    return redact_text("\n".join(lines).rstrip() + "\n")


def write_operation_report(run_id: str, *, root: Path = ADMIN_RUN_ROOT) -> OperationReportSummary:
    run_dir = _safe_run_dir(run_id, root)
    result = _load_json(run_dir / "result.json") or {}
    request = _load_json(run_dir / "request.json")
    progress = _load_json(run_dir / "progress_status.json") or _load_json(run_dir / "status.json")
    if result.get("mode") in {"PRODUCTION_APPLY", "TRANSACTION_REHEARSAL"} and "write_set" in result:
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
