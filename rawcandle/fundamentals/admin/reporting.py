from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


def _line(value: Any) -> str:
    return "" if value is None else str(value)


def render_markdown_report(result: Mapping[str, Any]) -> str:
    lines: list[str] = []
    operation = _line(result.get("operation_type"))
    outcome = _line(result.get("outcome"))
    lines.append(f"# Fundamentals Administration Run {result.get('run_id', '')}")
    lines.append("")
    lines.append(f"Outcome: **{outcome}**")
    if result.get("outcome_message"):
        lines.append("")
        lines.append(_line(result["outcome_message"]))
    lines.append("")
    lines.append("## Run")
    lines.append("")
    lines.append(f"- Operation: `{operation}`")
    lines.append(f"- Mode: `{result.get('mode', 'UNKNOWN')}`")
    lines.append(f"- Started: `{result.get('started_at_utc', '')}`")
    lines.append(f"- Completed: `{result.get('completed_at_utc', '')}`")
    if result.get("preview_fingerprint"):
        lines.append(f"- Preview fingerprint: `{result['preview_fingerprint']}`")
    request = result.get("request") if isinstance(result.get("request"), Mapping) else {}
    requested = request.get("requested_inputs") or request.get("requested") or []
    if requested:
        lines.append("")
        lines.append("## Requested Inputs")
        lines.append("")
        for item in requested:
            lines.append(f"- {_line(item)}")
    counts = result.get("summary_counts") if isinstance(result.get("summary_counts"), Mapping) else {}
    if counts:
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        for key in sorted(counts):
            lines.append(f"- {key.replace('_', ' ').title()}: `{counts[key]}`")
    items = result.get("item_results") if isinstance(result.get("item_results"), Sequence) else []
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        if isinstance(item, Mapping):
            grouped[str(item.get("status", "UNKNOWN"))].append(item)
    sections = [
        ("APPLIED", "Accepted Changes"),
        ("NO_CHANGE", "Unchanged Items"),
        ("REJECTED", "Rejected Items"),
        ("REVIEW_REQUIRED", "Review Required"),
        ("FAILED", "Failed Items"),
    ]
    for status, title in sections:
        rows = grouped.get(status, [])
        if not rows:
            continue
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Item | Reason | Source | Old | New |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    _line(value).replace("|", "\\|")
                    for value in (
                        row.get("normalized_value") or row.get("item_key"),
                        row.get("reason") or row.get("status_message"),
                        row.get("source_category"),
                        row.get("old_value"),
                        row.get("new_value"),
                    )
                )
                + " |"
            )
    downstream = result.get("downstream") if isinstance(result.get("downstream"), Mapping) else {}
    if downstream:
        lines.append("")
        lines.append("## Downstream Outcomes")
        lines.append("")
        for key in ("provider", "canonical", "ttm", "package", "relative_position", "relative_valuation"):
            if key in downstream:
                lines.append(f"- {key.replace('_', ' ').title()}: `{downstream[key]}`")
    rollback = result.get("rollback") if isinstance(result.get("rollback"), Mapping) else {}
    lines.append("")
    lines.append("## Rollback")
    lines.append("")
    if rollback:
        lines.append(f"- Status: `{rollback.get('status', 'UNKNOWN')}`")
        if rollback.get("message"):
            lines.append(f"- Note: {_line(rollback.get('message'))}")
    else:
        lines.append("- Status: `NOT_REQUIRED_OR_NOT_RECORDED`")
    lines.append("")
    lines.append("## Final Outcome")
    lines.append("")
    lines.append(_line(result.get("recommended_next_action") or "Review the summary and keep this report with the run artifacts."))
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), Mapping) else {}
    lines.append("")
    lines.append("## Technical Appendix")
    lines.append("")
    if result.get("result_fingerprint"):
        lines.append(f"- Result fingerprint: `{result['result_fingerprint']}`")
    for key, value in sorted(artifacts.items()):
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines).rstrip() + "\n"
