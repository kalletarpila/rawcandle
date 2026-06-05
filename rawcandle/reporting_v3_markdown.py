from __future__ import annotations

from collections import Counter
from typing import Any


def render_rolling30_markdown_report(query_data: Any) -> str:
    return _render_window_markdown_report(query_data=query_data, window_label="rolling30")


def render_rolling5_markdown_report(query_data: Any) -> str:
    return _render_window_markdown_report(query_data=query_data, window_label="rolling5")


def render_rolling2_markdown_report(query_data: Any) -> str:
    return _render_window_markdown_report(query_data=query_data, window_label="rolling2")


def _render_window_markdown_report(query_data: Any, window_label: str) -> str:
    report_header = _get_field(query_data, "report_header")
    quality_summary = _get_field(query_data, "quality_summary") or {}
    ecosystem_snapshot = _get_field(query_data, "ecosystem_snapshot")
    group_snapshots = list(_get_field(query_data, "group_snapshots") or [])
    watchlist_members = list(_get_field(query_data, "watchlist_members") or [])
    ticker_metrics = _normalize_ticker_metrics(_get_field(query_data, "ticker_metrics") or {})
    group_metrics = list(_get_field(query_data, "group_metrics") or [])
    structural_events = list(_get_field(query_data, "structural_events") or [])
    signal_observations = list(_get_field(query_data, "signal_observations") or [])
    metadata = _get_field(query_data, "metadata") or {}
    rolling2_sell_pressure_classifications = list(_get_field(query_data, "rolling2_sell_pressure_classifications") or [])
    rolling30_buy_classifications = list(_get_field(query_data, "rolling30_buy_classifications") or [])
    rolling30_exit_classifications = list(_get_field(query_data, "rolling30_exit_classifications") or [])
    rolling5_pullback_classifications = list(_get_field(query_data, "rolling5_pullback_classifications") or [])
    classification_source_key = f"{window_label}_classification_source"
    snapshot_source_key = f"{window_label}_snapshot_classification_source_used"
    event_window_mode_key = f"{window_label}_event_window_mode"

    lines = [
        f"# Datacenter {window_label} report prototype",
        "",
        "## Metadata",
        f"- ecosystem_code: {_value(_get_field(report_header, 'ecosystem_code'))}",
        f"- taxonomy_version_code: {_value(_get_field(report_header, 'taxonomy_version_code'))}",
        f"- signal_date: {_value(_get_field(report_header, 'signal_date'))}",
        f"- run_id: {_value(_get_field(report_header, 'run_id'))}",
        f"- window_code: {_value(_get_field(report_header, 'window_code'))}",
        "",
        "## Quality and coverage",
    ]
    lines.extend(_render_quality_and_coverage(quality_summary))
    lines.extend(
        [
            "## Ecosystem snapshot",
            *_render_table_or_none(
                headers=["entity_code", "snapshot_status", "trend_state", "summary_state", "quality_status"],
                rows=[
                    [
                        _get_field(ecosystem_snapshot, "entity_code"),
                        _get_field(ecosystem_snapshot, "snapshot_status"),
                        _get_field(ecosystem_snapshot, "trend_state"),
                        _get_field(ecosystem_snapshot, "summary_state"),
                        _get_field(ecosystem_snapshot, "quality_status"),
                    ]
                ]
                if ecosystem_snapshot
                else [],
                empty_message="No ecosystem snapshot rows.",
            ),
            "## Group overview",
            *_render_table_or_none(
                headers=[
                    "entity_type",
                    "entity_code",
                    "entity_name",
                    "timing_state",
                    "trend_state",
                    "summary_state",
                    "freshness_status",
                    "quality_status",
                ],
                rows=[
                    [
                        row.get("entity_type"),
                        row.get("entity_code"),
                        row.get("entity_name"),
                        row.get("timing_state"),
                        row.get("trend_state"),
                        row.get("summary_state"),
                        row.get("freshness_status"),
                        row.get("quality_status"),
                    ]
                    for row in group_snapshots
                ],
                empty_message="No group snapshot rows.",
            ),
        ]
    )
    if window_label == "rolling30":
        lines.extend(
            [
                "## Rolling30 buy classifications",
                f"- row_count: {len(rolling30_buy_classifications)}",
            ]
        )
        lines.extend(_render_state_counts(rolling30_buy_classifications))
        lines.extend(
            _render_table_or_none(
                headers=["ticker", "classification_state", "primary_reason", "blocking_reason", "decision_status"],
                rows=[
                    [
                        row.get("ticker"),
                        row.get("classification_state"),
                        row.get("primary_reason"),
                        row.get("blocking_reason"),
                        row.get("decision_status"),
                    ]
                    for row in rolling30_buy_classifications
                ],
                empty_message="No rolling30 buy classification rows.",
            )
        )
        lines.extend(
            [
                "## Rolling30 exit classifications",
                f"- row_count: {len(rolling30_exit_classifications)}",
            ]
        )
        lines.extend(_render_state_counts(rolling30_exit_classifications))
        lines.extend(
            _render_table_or_none(
                headers=["ticker", "classification_state", "primary_reason", "risk_reason", "decision_status"],
                rows=[
                    [
                        row.get("ticker"),
                        row.get("classification_state"),
                        row.get("primary_reason"),
                        row.get("risk_reason"),
                        row.get("decision_status"),
                    ]
                    for row in rolling30_exit_classifications
                ],
                empty_message="No rolling30 exit classification rows.",
            )
        )
    elif window_label == "rolling5":
        lines.extend(
            [
                "## Rolling5 pullback classifications",
                f"- row_count: {len(rolling5_pullback_classifications)}",
            ]
        )
        lines.extend(_render_state_counts(rolling5_pullback_classifications))
        lines.extend(
            _render_table_or_none(
                headers=[
                    "ticker",
                    "classification_state",
                    "primary_reason",
                    "blocking_reason",
                    "next_action",
                    "decision_status",
                ],
                rows=[
                    [
                        row.get("ticker"),
                        row.get("classification_state"),
                        row.get("primary_reason"),
                        row.get("blocking_reason"),
                        row.get("next_action"),
                        row.get("decision_status"),
                    ]
                    for row in rolling5_pullback_classifications
                ],
                empty_message="No rolling5 pullback classification rows.",
            )
        )
    else:
        lines.extend(
            [
                "## Rolling2 sell pressure classifications",
                f"- row_count: {len(rolling2_sell_pressure_classifications)}",
            ]
        )
        lines.extend(_render_state_counts(rolling2_sell_pressure_classifications))
        lines.extend(
            _render_table_or_none(
                headers=[
                    "ticker",
                    "classification_state",
                    "primary_reason",
                    "risk_reason",
                    "next_action",
                    "decision_status",
                ],
                rows=[
                    [
                        row.get("ticker"),
                        row.get("classification_state"),
                        row.get("primary_reason"),
                        row.get("risk_reason"),
                        row.get("next_action"),
                        row.get("decision_status"),
                    ]
                    for row in rolling2_sell_pressure_classifications
                ],
                empty_message="No rolling2 sell pressure classification rows.",
            )
        )
    lines.extend(
        [
            "## Watchlist",
            *_render_table_or_none(
                headers=[
                    "watchlist_code",
                    "watchlist_name",
                    "ticker",
                    "entity_name",
                    "member_role",
                    "member_status",
                    "effective_from",
                    "effective_to",
                ],
                rows=[
                    [
                        row.get("watchlist_code"),
                        row.get("watchlist_name"),
                        row.get("ticker"),
                        row.get("entity_name"),
                        row.get("member_role"),
                        row.get("member_status"),
                        row.get("effective_from"),
                        row.get("effective_to"),
                    ]
                    for row in watchlist_members
                ],
                empty_message="No watchlist rows.",
            ),
            "## Ticker metrics",
            *_render_table_or_none(
                headers=[
                    "ticker",
                    "entity_name",
                    "breakout_days",
                    "pullback_days",
                    "exit_risk_days",
                    "high_exit_risk_days",
                    "medium_exit_risk_days",
                    "valid_signal_dates",
                    "distance_to_ema20_pct",
                ],
                rows=[
                    [
                        row.get("ticker"),
                        row.get("entity_name"),
                        row.get("breakout_days"),
                        row.get("pullback_days"),
                        row.get("exit_risk_days"),
                        row.get("high_exit_risk_days"),
                        row.get("medium_exit_risk_days"),
                        row.get("valid_signal_dates"),
                        row.get("distance_to_ema20_pct"),
                    ]
                    for row in ticker_metrics
                ],
                empty_message="No ticker metric rows.",
            ),
            "## Group metrics",
            *_render_table_or_none(
                headers=[
                    "entity_type",
                    "entity_code",
                    "entity_name",
                    "pct_above_ema20",
                    "return_5d",
                    "synthetic_close",
                    "trend_breadth",
                    "weakness_breadth",
                    "valid_signal_dates",
                    "group_current_status",
                    "group_window_status",
                    "group_status_change",
                    "group_timing_state",
                    "group_timing_reason",
                    "group_overheat_risk_level",
                ],
                rows=[
                    [
                        row.get("entity_type"),
                        row.get("entity_code"),
                        row.get("entity_name"),
                        row.get("pct_above_ema20"),
                        row.get("return_5d"),
                        row.get("synthetic_close"),
                        row.get("trend_breadth"),
                        row.get("weakness_breadth"),
                        row.get("valid_signal_dates"),
                        row.get("group_current_status"),
                        row.get("group_window_status"),
                        row.get("group_status_change"),
                        row.get("group_timing_state"),
                        row.get("group_timing_reason"),
                        row.get("group_overheat_risk_level"),
                    ]
                    for row in group_metrics
                ],
                empty_message="No group metric rows.",
            ),
            "## Events and signals",
        ]
    )
    lines.extend(_render_events_and_signals(structural_events, signal_observations, window_label=window_label))
    lines.extend(
        [
            "## Metadata and limitations",
            f"- used_v2_runtime_tables: {_value(metadata.get('used_v2_runtime_tables'))}",
            f"- used_generated_reports: {_value(metadata.get('used_generated_reports'))}",
            f"- used_dashboard_output: {_value(metadata.get('used_dashboard_output'))}",
            f"- {classification_source_key}: {_value(metadata.get(classification_source_key))}",
            f"- {snapshot_source_key}: {_value(metadata.get(snapshot_source_key))}",
            f"- {event_window_mode_key}: {_value(metadata.get(event_window_mode_key))}",
            f"- ranking_fields_mostly_null: {_value(metadata.get('ranking_fields_mostly_null'))}",
            "",
        ]
    )
    limitations = list(metadata.get("limitations") or [])
    if limitations:
        lines.extend(f"- {_escape(str(item))}" for item in limitations)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def _render_quality_and_coverage(quality_summary: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.extend(
        _render_table_or_none(
            headers=[
                "window_code",
                "quality_scope",
                "quality_status",
                "scope_entity_type",
                "scope_entity_code",
                "expected_count",
                "actual_count",
                "warning_count",
                "error_count",
            ],
            rows=[
                [
                    row.get("window_code"),
                    row.get("quality_scope"),
                    row.get("quality_status"),
                    row.get("scope_entity_type"),
                    row.get("scope_entity_code"),
                    row.get("expected_count"),
                    row.get("actual_count"),
                    row.get("warning_count"),
                    row.get("error_count"),
                ]
                for row in list(quality_summary.get("rows") or [])
            ],
            empty_message="No quality summary rows.",
        )
    )
    lines.extend(
        _render_table_or_none(
            headers=["entity_type", "coverage_status", "row_count"],
            rows=[
                [row.get("entity_type"), row.get("coverage_status"), row.get("row_count")]
                for row in list(quality_summary.get("coverage_counts") or [])
            ],
            empty_message="No coverage summary rows.",
        )
    )
    return lines


def _render_state_counts(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- state_counts: none", ""]
    counts = Counter(str(row.get("classification_state") or "") for row in rows)
    lines = ["### Classification state counts"]
    for state_name in sorted(counts):
        lines.append(f"- {_escape(state_name)}: {counts[state_name]}")
    lines.append("")
    return lines


def _render_events_and_signals(
    structural_events: list[dict[str, Any]],
    signal_observations: list[dict[str, Any]],
    window_label: str,
) -> list[str]:
    lines = [
        "### Structural events",
        *_render_table_or_none(
            headers=["entity_type", "entity_code", "event_date", "event_type", "event_direction", "event_status"],
            rows=[
                [
                    row.get("entity_type"),
                    row.get("entity_code"),
                    row.get("event_date"),
                    row.get("event_type"),
                    row.get("event_direction"),
                    row.get("event_status"),
                ]
                for row in structural_events
            ],
            empty_message="No structural event rows.",
        ),
        "### Signal observations",
    ]
    if signal_observations:
        signal_names = sorted({str(row.get("signal_name") or "") for row in signal_observations})
        lines.append(
            f"- {window_label}-compatible signal observations only: "
            + _escape(", ".join(name for name in signal_names if name))
        )
        lines.append("")
    else:
        lines.append(f"- {window_label}-compatible signal observations only: none")
        lines.append("")
    lines.extend(
        _render_table_or_none(
            headers=[
                "entity_code",
                "signal_name",
                "signal_family",
                "signal_direction",
                "signal_value",
                "observed_date",
                "relevance_labels",
            ],
            rows=[
                [
                    row.get("entity_code"),
                    row.get("signal_name"),
                    row.get("signal_family"),
                    row.get("signal_direction"),
                    row.get("signal_value"),
                    row.get("observed_date"),
                    row.get("relevance_labels"),
                ]
                for row in signal_observations
            ],
            empty_message="No signal observation rows.",
        )
    )
    return lines


def _render_table_or_none(headers: list[str], rows: list[list[Any]], empty_message: str) -> list[str]:
    if not rows:
        return [f"- {empty_message}", ""]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_value(value) for value in row) + " |")
    lines.append("")
    return lines


def _normalize_ticker_metrics(ticker_metrics: Any) -> list[dict[str, Any]]:
    if isinstance(ticker_metrics, dict):
        rows = [dict(value) for _, value in sorted(ticker_metrics.items())]
    else:
        rows = [dict(value) for value in list(ticker_metrics or [])]
    rows.sort(key=lambda row: str(row.get("ticker") or ""))
    return rows


def _get_field(obj: Any, field_name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


def _value(value: Any) -> str:
    if value is None:
        return ""
    return _escape(str(value))


def _escape(value: str) -> str:
    return value.replace("|", "\\|")
