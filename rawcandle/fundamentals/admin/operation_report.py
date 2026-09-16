from __future__ import annotations

import json
import stat
from dataclasses import dataclass
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
    counts = result.get("summary_counts") if isinstance(result.get("summary_counts"), Mapping) else {}
    downstream = result.get("downstream") if isinstance(result.get("downstream"), Mapping) else {}
    rollback = result.get("rollback") if isinstance(result.get("rollback"), Mapping) else {}
    rows = [
        f"Operation: {result.get('operation_type', 'UNKNOWN')}",
        f"Mode: {result.get('mode', 'UNKNOWN')}",
        f"Outcome: {result.get('outcome', 'UNKNOWN')}",
    ]
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
        else:
            rows.append("Downstream: recorded")
    if rollback:
        rows.append(f"Rollback: {rollback.get('status', 'RECORDED')}")
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
            rendered = json.dumps(item, sort_keys=True, default=str)
        else:
            rendered = str(item)
        lines.append(f"- {str(key).replace('_', ' ').title()}: `{rendered}`")


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
    _append_mapping(lines, "Request", request or {})
    _append_mapping(lines, "Summary Counts", result.get("summary_counts") if isinstance(result.get("summary_counts"), Mapping) else {})
    _append_mapping(lines, "Downstream", result.get("downstream") if isinstance(result.get("downstream"), Mapping) else {})
    _append_mapping(lines, "Rollback", result.get("rollback") if isinstance(result.get("rollback"), Mapping) else {})
    if events:
        lines.extend(["", "## Progress Events", ""])
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
    lines.extend(
        [
            "",
            "## Technical Appendix",
            "",
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
