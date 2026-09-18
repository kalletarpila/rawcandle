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


def _short(value: Any, *, limit: int = 900) -> str:
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(value, sort_keys=True, default=str)
    else:
        rendered = str(value)
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


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
    rows = [
        f"Operation: {result.get('operation_type', 'UNKNOWN')}",
        f"Mode: {result.get('mode', 'UNKNOWN')}",
        f"Outcome: {result.get('outcome', 'UNKNOWN')}",
    ]
    if duration is not None:
        rows.append(f"Duration: {duration:.0f}s")
    if result.get("preview_fingerprint"):
        rows.append(f"Preview fingerprint: {result['preview_fingerprint']}")
    if counts:
        rows.append(
            "Counts: "
            + ", ".join(f"{str(key).replace('_', ' ')}={counts[key]}" for key in sorted(counts))
        )
    if progress:
        rows.append(
            "Progress: "
            f"{progress.get('current_stage_id') or progress.get('stage', 'UNKNOWN')} "
            f"{progress.get('stage_state') or ''}".strip()
        )
    if downstream:
        invocation_counts = downstream.get("invocation_counts")
        if isinstance(invocation_counts, Mapping):
            rows.append(
                "Downstream invocations: "
                + ", ".join(f"{key}={invocation_counts[key]}" for key in sorted(invocation_counts))
            )
        elif result.get("mode") in {"CURRENT_STATE_AUDIT", "CANDIDATE_PREVIEW", "PROTECTED_PRODUCTION_PREVIEW"}:
            rows.append("Potential downstream work was evaluated. No calculations were run during Preview.")
        else:
            rows.append("Downstream: recorded")
    if rollback:
        rows.append(f"Rollback: {rollback.get('status', 'RECORDED')}")
    if warnings:
        rows.append(f"Warning: {_short(redact(warnings[0]), limit=160)}")
    if blockers:
        rows.append(f"Blocker: {_short(redact(blockers[0]), limit=160)}")
    if result.get("recommended_next_action"):
        rows.append(f"Next action: {result['recommended_next_action']}")
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


def _append_mapping(lines: list[str], title: str, value: Mapping[str, Any]) -> None:
    if not value:
        return
    safe_value = redact(value)
    lines.extend(["", f"## {title}", ""])
    for key in sorted(safe_value):
        item = safe_value[key]
        if isinstance(item, (dict, list, tuple)):
            rendered = _short(item)
        else:
            rendered = _short(item)
        lines.append(f"- {str(key).replace('_', ' ').title()}: `{rendered}`")


def _append_items(lines: list[str], title: str, values: list[Any], *, limit: int = 25) -> None:
    if not values:
        return
    lines.extend(["", f"## {title}", ""])
    for index, item in enumerate(values[:limit], start=1):
        safe_item = redact(item)
        if isinstance(safe_item, Mapping):
            label = (
                safe_item.get("ticker")
                or safe_item.get("item_key")
                or safe_item.get("symbol")
                or f"item {index}"
            )
            status = safe_item.get("status") or safe_item.get("decision") or safe_item.get("outcome") or "recorded"
            reason = safe_item.get("reason") or safe_item.get("message") or safe_item.get("explanation") or ""
            lines.append(f"- {label}: {status}" + (f" - {reason}" if reason else ""))
        else:
            lines.append(f"- {_short(safe_item, limit=300)}")
    if len(values) > limit:
        lines.append(f"- {len(values) - limit} additional items retained in artifacts.")


def _append_named_section(lines: list[str], title: str, value: Any) -> None:
    if isinstance(value, Mapping):
        _append_mapping(lines, title, value)
    elif isinstance(value, (list, tuple)):
        _append_items(lines, title, list(value))


def render_operation_report(
    *,
    run_id: str,
    result: Mapping[str, Any],
    request: Mapping[str, Any] | None = None,
    progress: Mapping[str, Any] | None = None,
    events: list[Mapping[str, Any]] | None = None,
) -> str:
    summary_rows = build_operation_summary(result, progress)
    lines = [
        f"# Fundamentals Administration Operation Report",
        "",
        "## Executive Summary",
        "",
    ]
    for row in summary_rows:
        lines.append(f"- {row}")
    lines.extend(
        [
            "",
            "## Run Identity",
            "",
            f"- Run ID: `{run_id}`",
            f"- Started UTC: `{result.get('started_at_utc', '')}`",
            f"- Completed UTC: `{result.get('completed_at_utc', '')}`",
        ]
    )
    duration = _duration_seconds(result.get("started_at_utc"), result.get("completed_at_utc"))
    if duration is not None:
        lines.append(f"- Duration seconds: `{duration:.0f}`")
    _append_mapping(lines, "Request", request or {})
    _append_mapping(lines, "Summary Counts", result.get("summary_counts") if isinstance(result.get("summary_counts"), Mapping) else {})
    provider_network = {
        "network_allowed": result.get("network_allowed", (request or {}).get("network_allowed")),
        "network_used": result.get("network_used"),
        "bounded_request_count": result.get("bounded_request_count") or result.get("provider_request_count"),
        "source_resolution": result.get("source_resolution") or result.get("provider_source_resolution"),
        "provider_failure": result.get("provider_failure"),
    }
    provider_network = {key: value for key, value in provider_network.items() if value is not None}
    _append_mapping(lines, "Provider Network", provider_network)
    _append_items(lines, "Per-Item Results", _sequence(result.get("items")) or _sequence(result.get("item_results")) or _sequence(result.get("results")))
    _append_named_section(lines, "Before And After Changes", result.get("changes") or result.get("change_summary") or result.get("before_after"))
    _append_named_section(lines, "Source And Provenance", result.get("source") or result.get("provenance") or result.get("active_taxonomy"))
    _append_mapping(lines, "Work Performed And Downstream", result.get("downstream") if isinstance(result.get("downstream"), Mapping) else {})
    _append_named_section(lines, "Snapshot Results", result.get("snapshot") or result.get("snapshot_results") or _mapping(result.get("downstream")).get("snapshot"))
    _append_named_section(lines, "Warnings And Blockers", {"warnings": _sequence(result.get("warnings")), "blockers": _sequence(result.get("blockers"))})
    _append_named_section(lines, "Write Boundary", result.get("write_boundary") or _mapping(result.get("downstream")).get("write_boundary") or {"status": result.get("write_boundary_status", "NOT_RECORDED")})
    _append_named_section(lines, "Databases Read And Written", result.get("databases") or result.get("database_roles") or result.get("expected_writable_database_set"))
    _append_mapping(lines, "Backup And Rollback", result.get("rollback") if isinstance(result.get("rollback"), Mapping) else {})
    _append_named_section(lines, "Scheduler Handling", result.get("scheduler") or {"status": result.get("scheduler_status", "NOT_RECORDED")})
    if events:
        lines.extend(["", "## Progress Timeline", ""])
        for event in events:
            safe_event = redact(event)
            lines.append(
                "- "
                f"{safe_event.get('current_stage_number', '?')}/{safe_event.get('total_declared_stages', '?')} "
                f"{safe_event.get('current_stage_id', 'UNKNOWN')} "
                f"{safe_event.get('stage_state', 'UNKNOWN')}: {safe_event.get('message', '')}"
            )
    errors = result.get("errors") if isinstance(result.get("errors"), list) else []
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            if isinstance(error, Mapping):
                lines.append(f"- {error.get('type', 'Error')}: {error.get('message', '')}")
            else:
                lines.append(f"- {_short(redact(error), limit=300)}")
    lines.extend(["", "## Next Required Action", ""])
    lines.append(f"- {result.get('recommended_next_action') or 'Review the outcome and retained artifacts before any further action.'}")
    lines.extend(["", "## Cleanup And Retained Artifacts", ""])
    lines.append("- Durable run artifacts are retained in this run directory.")
    if result.get("artifact_dir"):
        lines.append(f"- Artifact directory: `{result.get('artifact_dir')}`")
    lines.extend(
        [
            "",
            "## Technical Appendix",
            "",
            f"- Preview fingerprint: `{result.get('preview_fingerprint', '')}`",
            f"- Result fingerprint: `{result.get('result_fingerprint', '')}`",
            f"- Report content fingerprint: `{fingerprint({'result': result, 'request': request or {}, 'events': events or []})}`",
        ]
    )
    return redact_text("\n".join(lines).rstrip() + "\n")


def write_operation_report(run_id: str, *, root: Path = ADMIN_RUN_ROOT) -> OperationReportSummary:
    run_dir = _safe_run_dir(run_id, root)
    result = _load_json(run_dir / "result.json") or {}
    request = _load_json(run_dir / "request.json")
    progress = _load_json(run_dir / "progress_status.json") or _load_json(run_dir / "status.json")
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
