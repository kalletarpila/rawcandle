from __future__ import annotations

from collections import Counter
from typing import Any


def render_rolling30_markdown_report(query_data: Any) -> str:
    return _render_window_markdown_report(query_data=query_data, window_label="rolling30")


def render_rolling5_markdown_report(query_data: Any) -> str:
    return _render_window_markdown_report(query_data=query_data, window_label="rolling5")


def render_rolling2_markdown_report(query_data: Any) -> str:
    return _render_window_markdown_report(query_data=query_data, window_label="rolling2")


def render_daily_markdown_report(query_data: Any) -> str:
    return _render_window_markdown_report(query_data=query_data, window_label="daily")


def _render_window_markdown_report(query_data: Any, window_label: str) -> str:
    report_header = _get_field(query_data, "report_header")
    window_summary = _get_field(query_data, "window_summary") or {}
    watchlist_summary = _get_field(query_data, "watchlist_summary") or {}
    quality_summary = _get_field(query_data, "quality_summary") or {}
    ecosystem_snapshot = _get_field(query_data, "ecosystem_snapshot")
    group_snapshots = list(_get_field(query_data, "group_snapshots") or [])
    watchlist_members = list(_get_field(query_data, "watchlist_members") or [])
    ticker_metrics = _normalize_ticker_metrics(_get_field(query_data, "ticker_metrics") or {})
    group_metrics = list(_get_field(query_data, "group_metrics") or [])
    structural_events = list(_get_field(query_data, "structural_events") or [])
    signal_observations = list(_get_field(query_data, "signal_observations") or [])
    metadata = _get_field(query_data, "metadata") or {}
    daily_trigger_classifications = list(_get_field(query_data, "daily_trigger_classifications") or [])
    rolling2_sell_pressure_classifications = list(_get_field(query_data, "rolling2_sell_pressure_classifications") or [])
    rolling30_buy_classifications = list(_get_field(query_data, "rolling30_buy_classifications") or [])
    rolling30_exit_classifications = list(_get_field(query_data, "rolling30_exit_classifications") or [])
    rolling5_pullback_classifications = list(_get_field(query_data, "rolling5_pullback_classifications") or [])
    classification_source_key = f"{window_label}_classification_source"
    snapshot_source_key = f"{window_label}_snapshot_classification_source_used"
    event_window_mode_key = f"{window_label}_event_window_mode"
    if window_label != "daily":
        return _render_rolling_legacy_shell(
            report_header=report_header,
            window_summary=window_summary,
            watchlist_summary=watchlist_summary,
            quality_summary=quality_summary,
            ecosystem_snapshot=ecosystem_snapshot,
            group_snapshots=group_snapshots,
            watchlist_members=watchlist_members,
            ticker_metrics=ticker_metrics,
            group_metrics=group_metrics,
            structural_events=structural_events,
            signal_observations=signal_observations,
            metadata=metadata,
            rolling2_sell_pressure_classifications=rolling2_sell_pressure_classifications,
            rolling30_buy_classifications=rolling30_buy_classifications,
            rolling30_exit_classifications=rolling30_exit_classifications,
            rolling5_pullback_classifications=rolling5_pullback_classifications,
            classification_source_key=classification_source_key,
            snapshot_source_key=snapshot_source_key,
            event_window_mode_key=event_window_mode_key,
            window_label=window_label,
        )

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
    elif window_label == "rolling2":
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
    else:
        lines.extend(
            [
                "## Daily trigger classifications",
                f"- row_count: {len(daily_trigger_classifications)}",
            ]
        )
        lines.extend(_render_state_counts(daily_trigger_classifications))
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
                    for row in daily_trigger_classifications
                ],
                empty_message="No daily trigger classification rows.",
            )
        )
    ticker_metric_headers = (
        [
            "ticker",
            "entity_name",
            "distance_to_ema10_pct",
            "distance_to_ema20_pct",
            "return_5d",
            "return_10d",
            "return_20d",
            "return_60d",
            "latest_bos_age_trading_days",
            "latest_reset_age_trading_days",
            "latest_structure_age_trading_days",
            "freshness_latest_bos_age_trading_days",
            "freshness_latest_bos_class",
            "freshness_latest_reset_age_trading_days",
            "freshness_latest_reset_class",
            "freshness_latest_structure_age_trading_days",
            "freshness_latest_structure_class",
        ]
        if window_label == "daily"
        else [
            "ticker",
            "entity_name",
            "breakout_days",
            "pullback_days",
            "exit_risk_days",
            "high_exit_risk_days",
            "medium_exit_risk_days",
            "valid_signal_dates",
            "distance_to_ema20_pct",
        ]
    )
    ticker_metric_rows = (
        [
            [
                row.get("ticker"),
                row.get("entity_name"),
                row.get("distance_to_ema10_pct"),
                row.get("distance_to_ema20_pct"),
                row.get("return_5d"),
                row.get("return_10d"),
                row.get("return_20d"),
                row.get("return_60d"),
                row.get("latest_bos_age_trading_days"),
                row.get("latest_reset_age_trading_days"),
                row.get("latest_structure_age_trading_days"),
                row.get("freshness_latest_bos_age_trading_days"),
                row.get("freshness_latest_bos_class"),
                row.get("freshness_latest_reset_age_trading_days"),
                row.get("freshness_latest_reset_class"),
                row.get("freshness_latest_structure_age_trading_days"),
                row.get("freshness_latest_structure_class"),
            ]
            for row in ticker_metrics
        ]
        if window_label == "daily"
        else [
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
        ]
    )
    group_metric_headers = (
        [
            "entity_type",
            "entity_code",
            "entity_name",
            "pct_above_ema20",
            "return_5d",
            "synthetic_close",
            "trend_breadth",
            "weakness_breadth",
            "group_current_status",
            "group_timing_state",
            "group_timing_reason",
            "group_overheat_risk_level",
            "freshness_latest_bos_age_trading_days",
            "freshness_latest_bos_class",
            "freshness_latest_reset_age_trading_days",
            "freshness_latest_reset_class",
            "freshness_latest_structure_age_trading_days",
            "freshness_latest_structure_class",
        ]
        if window_label == "daily"
        else [
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
        ]
    )
    group_metric_rows = (
        [
            [
                row.get("entity_type"),
                row.get("entity_code"),
                row.get("entity_name"),
                row.get("pct_above_ema20"),
                row.get("return_5d"),
                row.get("synthetic_close"),
                row.get("trend_breadth"),
                row.get("weakness_breadth"),
                row.get("group_current_status"),
                row.get("group_timing_state"),
                row.get("group_timing_reason"),
                row.get("group_overheat_risk_level"),
                row.get("freshness_latest_bos_age_trading_days"),
                row.get("freshness_latest_bos_class"),
                row.get("freshness_latest_reset_age_trading_days"),
                row.get("freshness_latest_reset_class"),
                row.get("freshness_latest_structure_age_trading_days"),
                row.get("freshness_latest_structure_class"),
            ]
            for row in group_metrics
        ]
        if window_label == "daily"
        else [
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
        ]
    )
    lines.extend(
        [
            "## Watchlist Summary",
            "## Ticker metrics",
            *_render_table_or_none(
                headers=ticker_metric_headers,
                rows=ticker_metric_rows,
                empty_message="No ticker metric rows.",
            ),
            "## Group metrics",
            *_render_table_or_none(
                headers=group_metric_headers,
                rows=group_metric_rows,
                empty_message="No group metric rows.",
            ),
            "## Events and signals",
        ]
    )
    if window_label == "daily" and watchlist_summary:
        watchlist_index = lines.index("## Watchlist Summary")
        lines[watchlist_index:watchlist_index + 1] = [
            "## Watchlist Summary",
            *_render_table_or_none(
                headers=["field", "value"],
                rows=[
                    ["active_watchlist_count", watchlist_summary.get("counts", {}).get("active_watchlist_count")],
                    ["in_ecosystem_count", watchlist_summary.get("counts", {}).get("in_ecosystem_count")],
                    ["missing_price_data_count", watchlist_summary.get("counts", {}).get("missing_price_data_count")],
                    ["breakout_count", watchlist_summary.get("counts", {}).get("breakout_count")],
                    ["pullback_count", watchlist_summary.get("counts", {}).get("pullback_count")],
                    ["exit_risk_count", watchlist_summary.get("counts", {}).get("exit_risk_count")],
                    ["high_exit_risk_count", watchlist_summary.get("counts", {}).get("high_exit_risk_count")],
                    ["medium_exit_risk_count", watchlist_summary.get("counts", {}).get("medium_exit_risk_count")],
                ],
                empty_message="No active watchlist rows available from current V3 query data.",
            ),
            *_render_table_or_none(
                headers=[
                    "ticker",
                    "watchlist_status",
                    "in_datacenter_ecosystem",
                    "primary_layer",
                    "primary_subindustry",
                    "close",
                    "return_5d",
                    "return_10d",
                    "return_20d",
                    "distance_to_ema20_pct",
                    "ticker_trend_state",
                    "breakout_signal",
                    "pullback_signal",
                    "exit_risk_signal",
                    "exit_risk_severity",
                    "exit_reason",
                    "subindustry_timing_state",
                    "subindustry_overheat_risk_level",
                    "layer_timing_state",
                    "layer_overheat_risk_level",
                    "price_data_status",
                ],
                rows=[
                    [
                        row.get("ticker"),
                        row.get("watchlist_status"),
                        row.get("in_datacenter_ecosystem"),
                        row.get("primary_layer"),
                        row.get("primary_subindustry"),
                        row.get("close"),
                        row.get("return_5d"),
                        row.get("return_10d"),
                        row.get("return_20d"),
                        row.get("distance_to_ema20_pct"),
                        row.get("ticker_trend_state"),
                        row.get("breakout_signal"),
                        row.get("pullback_signal"),
                        row.get("exit_risk_signal"),
                        row.get("exit_risk_severity"),
                        row.get("exit_reason"),
                        row.get("subindustry_timing_state"),
                        row.get("subindustry_overheat_risk_level"),
                        row.get("layer_timing_state"),
                        row.get("layer_overheat_risk_level"),
                        row.get("price_data_status"),
                    ]
                    for row in watchlist_summary.get("rows", [])
                ],
                empty_message="No active watchlist rows available from current V3 query data.",
            ),
        ]
    else:
        watchlist_index = lines.index("## Watchlist Summary")
        lines[watchlist_index:watchlist_index + 1] = [
            "## Watchlist Summary",
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
        ]
    lines.extend(_render_events_and_signals(structural_events, signal_observations, window_label=window_label))
    if window_label == "daily":
        lines.extend(
            [
                "## Accepted special cases",
                f"- CRGY is intentionally materialized as INSUFFICIENT_DATA in daily_trigger.",
                f"- NXPI reflects accepted current lower-level source-truth SELL_TRIGGER semantics.",
                "",
            ]
        )
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


def _render_rolling_legacy_shell(
    *,
    report_header: Any,
    window_summary: dict[str, Any],
    watchlist_summary: dict[str, Any],
    quality_summary: dict[str, Any],
    ecosystem_snapshot: Any,
    group_snapshots: list[dict[str, Any]],
    watchlist_members: list[dict[str, Any]],
    ticker_metrics: list[dict[str, Any]],
    group_metrics: list[dict[str, Any]],
    structural_events: list[dict[str, Any]],
    signal_observations: list[dict[str, Any]],
    metadata: dict[str, Any],
    rolling2_sell_pressure_classifications: list[dict[str, Any]],
    rolling30_buy_classifications: list[dict[str, Any]],
    rolling30_exit_classifications: list[dict[str, Any]],
    rolling5_pullback_classifications: list[dict[str, Any]],
    classification_source_key: str,
    snapshot_source_key: str,
    event_window_mode_key: str,
    window_label: str,
) -> str:
    ticker_metric_rows = [
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
    ]
    group_metric_rows = [
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
    ]
    lines = [
        "# Datacenter Rolling Swing Report",
        "",
        "## 1. Title and run metadata",
        f"- ecosystem_code: {_value(_get_field(report_header, 'ecosystem_code'))}",
        f"- taxonomy_version_code: {_value(_get_field(report_header, 'taxonomy_version_code'))}",
        f"- signal_date: {_value(_get_field(report_header, 'signal_date'))}",
        f"- run_id: {_value(_get_field(report_header, 'run_id'))}",
        f"- window_code: {_value(_get_field(report_header, 'window_code'))}",
        "",
        "## 2. Window summary",
    ]
    lines.extend(
        _render_table_or_none(
            headers=["field", "value"],
            rows=[
                ["requested_end_date", window_summary.get("requested_end_date")],
                ["window_start_date", window_summary.get("window_start_date")],
                ["window_end_date", window_summary.get("window_end_date")],
                ["valid_signal_dates_count", window_summary.get("valid_signal_dates_count")],
                [
                    "valid_signal_dates_included",
                    ", ".join(window_summary.get("valid_signal_dates_included") or []),
                ],
                ["incomplete_window", window_summary.get("incomplete_window")],
            ],
            empty_message="Not available from current V3 query data in DB-V3-70.",
        )
    )
    lines.extend(
        [
            "",
            "## Watchlist Summary",
        ]
    )
    if watchlist_summary:
        lines.extend(
            _render_table_or_none(
                headers=["field", "value"],
                rows=[
                    ["active_watchlist_count", watchlist_summary.get("counts", {}).get("active_watchlist_count")],
                    ["in_ecosystem_count", watchlist_summary.get("counts", {}).get("in_ecosystem_count")],
                    ["missing_price_data_count", watchlist_summary.get("counts", {}).get("missing_price_data_count")],
                    ["breakout_count", watchlist_summary.get("counts", {}).get("breakout_count")],
                    ["pullback_count", watchlist_summary.get("counts", {}).get("pullback_count")],
                    ["exit_risk_count", watchlist_summary.get("counts", {}).get("exit_risk_count")],
                    ["high_exit_risk_count", watchlist_summary.get("counts", {}).get("high_exit_risk_count")],
                    ["medium_exit_risk_count", watchlist_summary.get("counts", {}).get("medium_exit_risk_count")],
                ],
                empty_message="No active watchlist rows available from current V3 query data.",
            )
        )
        lines.extend(
            _render_table_or_none(
                headers=[
                    "ticker",
                    "current_watchlist_status",
                    "window_watchlist_status",
                    "in_datacenter_ecosystem",
                    "primary_layer",
                    "primary_subindustry",
                    "breakout_days",
                    "pullback_days",
                    "exit_risk_days",
                    "high_exit_risk_days",
                    "medium_exit_risk_days",
                    "last_subindustry_timing_state",
                    "last_subindustry_overheat_risk_level",
                    "last_layer_timing_state",
                    "last_layer_overheat_risk_level",
                    "last_price_data_status",
                ],
                rows=[
                    [
                        row.get("ticker"),
                        row.get("current_watchlist_status"),
                        row.get("window_watchlist_status"),
                        row.get("in_datacenter_ecosystem"),
                        row.get("primary_layer"),
                        row.get("primary_subindustry"),
                        row.get("breakout_days"),
                        row.get("pullback_days"),
                        row.get("exit_risk_days"),
                        row.get("high_exit_risk_days"),
                        row.get("medium_exit_risk_days"),
                        row.get("last_subindustry_timing_state"),
                        row.get("last_subindustry_overheat_risk_level"),
                        row.get("last_layer_timing_state"),
                        row.get("last_layer_overheat_risk_level"),
                        row.get("last_price_data_status"),
                    ]
                    for row in watchlist_summary.get("rows", [])
                ],
                empty_message="No active watchlist rows available from current V3 query data.",
            )
        )
    else:
        lines.append("No active watchlist rows available from current V3 query data.")
    lines.extend(
        [
            "## 4. Ecosystem window change",
            "Not available from current V3 query data in DB-V3-70.",
            "",
            "## 5. Overheat / rotation risk progression",
        ]
    )
    if group_metric_rows:
        lines.extend(
            _render_table_or_none(
                headers=[
                    "entity_type",
                    "entity_code",
                    "entity_name",
                    "pct_above_ema20",
                    "return_5d",
                    "trend_breadth",
                    "weakness_breadth",
                    "group_current_status",
                    "group_window_status",
                    "group_status_change",
                    "group_timing_state",
                    "group_overheat_risk_level",
                ],
                rows=[
                    [
                        row.get("entity_type"),
                        row.get("entity_code"),
                        row.get("entity_name"),
                        row.get("pct_above_ema20"),
                        row.get("return_5d"),
                        row.get("trend_breadth"),
                        row.get("weakness_breadth"),
                        row.get("group_current_status"),
                        row.get("group_window_status"),
                        row.get("group_status_change"),
                        row.get("group_timing_state"),
                        row.get("group_overheat_risk_level"),
                    ]
                    for row in group_metrics
                ],
                empty_message="Not available from current V3 query data in DB-V3-70.",
            )
        )
        lines.append("- Historical progression across dates is not available from current V3 query data in DB-V3-70.")
    else:
        lines.append("Not available from current V3 query data in DB-V3-70.")
    lines.extend(
        [
            "## 6. Subindustry timing persistence",
            "Not available from current V3 query data in DB-V3-70.",
            "",
            "## 7. Subindustry improvement / deterioration",
            "Not available from current V3 query data in DB-V3-70.",
            "",
            "## 8. Repeated breakout tickers",
        ]
    )
    lines.extend(
        _render_repeated_ticker_section(
            ticker_metrics=ticker_metrics,
            metric_name="breakout_days",
            headers=[
                "ticker",
                "entity_name",
                "breakout_days",
                "pullback_days",
                "exit_risk_days",
                "valid_signal_dates",
                "distance_to_ema20_pct",
            ],
            section_key="breakout_days",
        )
    )
    lines.append("## 9. Repeated pullback tickers")
    lines.extend(
        _render_repeated_ticker_section(
            ticker_metrics=ticker_metrics,
            metric_name="pullback_days",
            headers=[
                "ticker",
                "entity_name",
                "pullback_days",
                "breakout_days",
                "exit_risk_days",
                "valid_signal_dates",
                "distance_to_ema20_pct",
            ],
            section_key="pullback_days",
        )
    )
    lines.append("## 10. Repeated exit-risk tickers")
    lines.extend(
        _render_repeated_ticker_section(
            ticker_metrics=ticker_metrics,
            metric_name="exit_risk_days",
            headers=[
                "ticker",
                "entity_name",
                "exit_risk_days",
                "high_exit_risk_days",
                "medium_exit_risk_days",
                "pullback_days",
                "distance_to_ema20_pct",
            ],
            section_key="exit_risk_days",
        )
    )
    lines.extend(
        _render_rolling_classification_sections(
            window_label=window_label,
            rolling2_sell_pressure_classifications=rolling2_sell_pressure_classifications,
            rolling30_buy_classifications=rolling30_buy_classifications,
            rolling30_exit_classifications=rolling30_exit_classifications,
            rolling5_pullback_classifications=rolling5_pullback_classifications,
        )
    )
    lines.extend(
        [
            "## 15. Data quality over the window",
        ]
    )
    lines.extend(_render_quality_and_coverage(quality_summary))
    lines.extend(
        [
            "## 16. Missing / incomplete inputs summary",
            "- Current V3 query data provides combined quality and coverage summaries; a separate legacy missing-input read-model is not available in DB-V3-70.",
            "",
            "## V3 metadata / limitations appendix",
            f"- {classification_source_key}: {_value(metadata.get(classification_source_key))}",
            f"- {snapshot_source_key}: {_value(metadata.get(snapshot_source_key))}",
            f"- {event_window_mode_key}: {_value(metadata.get(event_window_mode_key))}",
            f"- ranking_fields_mostly_null: {_value(metadata.get('ranking_fields_mostly_null'))}",
            "",
        ]
    )
    lines.extend(
        _render_table_or_none(
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
        )
    )
    lines.extend(
        _render_table_or_none(
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
        )
    )
    lines.extend(
        _render_table_or_none(
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
            rows=ticker_metric_rows,
            empty_message="No ticker metric rows.",
        )
    )
    lines.extend(
        _render_table_or_none(
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
            rows=group_metric_rows,
            empty_message="No group metric rows.",
        )
    )
    lines.extend(_render_events_and_signals(structural_events, signal_observations, window_label=window_label))
    limitations = list(metadata.get("limitations") or [])
    if limitations:
        lines.extend(f"- {_escape(str(item))}" for item in limitations)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def _render_repeated_ticker_section(
    *,
    ticker_metrics: list[dict[str, Any]],
    metric_name: str,
    headers: list[str],
    section_key: str,
) -> list[str]:
    filtered_rows = []
    for row in ticker_metrics:
        value = row.get(metric_name)
        if value is not None and value != 0:
            if section_key == "breakout_days":
                filtered_rows.append(
                    [
                        row.get("ticker"),
                        row.get("entity_name"),
                        row.get("breakout_days"),
                        row.get("pullback_days"),
                        row.get("exit_risk_days"),
                        row.get("valid_signal_dates"),
                        row.get("distance_to_ema20_pct"),
                    ]
                )
            elif section_key == "pullback_days":
                filtered_rows.append(
                    [
                        row.get("ticker"),
                        row.get("entity_name"),
                        row.get("pullback_days"),
                        row.get("breakout_days"),
                        row.get("exit_risk_days"),
                        row.get("valid_signal_dates"),
                        row.get("distance_to_ema20_pct"),
                    ]
                )
            else:
                filtered_rows.append(
                    [
                        row.get("ticker"),
                        row.get("entity_name"),
                        row.get("exit_risk_days"),
                        row.get("high_exit_risk_days"),
                        row.get("medium_exit_risk_days"),
                        row.get("pullback_days"),
                        row.get("distance_to_ema20_pct"),
                    ]
                )
    if not filtered_rows:
        return ["Not available from current V3 query data in DB-V3-70.", ""]
    lines = _render_table_or_none(headers=headers, rows=filtered_rows, empty_message="Not available from current V3 query data in DB-V3-70.")
    lines.append("")
    return lines


def _render_rolling_classification_sections(
    *,
    window_label: str,
    rolling2_sell_pressure_classifications: list[dict[str, Any]],
    rolling30_buy_classifications: list[dict[str, Any]],
    rolling30_exit_classifications: list[dict[str, Any]],
    rolling5_pullback_classifications: list[dict[str, Any]],
) -> list[str]:
    if window_label == "rolling30":
        lines = [
            "## Rolling 30 Buy Filter",
            f"- row_count: {len(rolling30_buy_classifications)}",
        ]
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
                "## Rolling 30 Exit Prefilter",
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
        return lines
    if window_label == "rolling5":
        lines = [
            "## Rolling 5 Pullback Alerts",
            f"- row_count: {len(rolling5_pullback_classifications)}",
        ]
        lines.extend(_render_state_counts(rolling5_pullback_classifications))
        lines.extend(
            _render_table_or_none(
                headers=["ticker", "classification_state", "primary_reason", "blocking_reason", "next_action", "decision_status"],
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
        return lines
    lines = [
        "## Rolling 2 Sell Pressure",
        f"- row_count: {len(rolling2_sell_pressure_classifications)}",
    ]
    lines.extend(_render_state_counts(rolling2_sell_pressure_classifications))
    lines.extend(
        _render_table_or_none(
            headers=["ticker", "classification_state", "primary_reason", "risk_reason", "next_action", "decision_status"],
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
    return lines


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
