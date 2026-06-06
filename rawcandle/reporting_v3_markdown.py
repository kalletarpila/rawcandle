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
    ecosystem_window_change = _get_field(query_data, "ecosystem_window_change") or {}
    overheat_rotation_risk_progression = _get_field(query_data, "overheat_rotation_risk_progression") or {}
    subindustry_timing_persistence = _get_field(query_data, "subindustry_timing_persistence") or {}
    subindustry_improvement_deterioration = _get_field(query_data, "subindustry_improvement_deterioration") or {}
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
    ticker_scanners = _get_field(query_data, "ticker_scanners") or {}
    synthetic_ohlc_structure_summary = _get_field(query_data, "synthetic_ohlc_structure_summary") or {}
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
            ecosystem_window_change=ecosystem_window_change,
            overheat_rotation_risk_progression=overheat_rotation_risk_progression,
            subindustry_timing_persistence=subindustry_timing_persistence,
            subindustry_improvement_deterioration=subindustry_improvement_deterioration,
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
    return _render_daily_legacy_shell(
        report_header=report_header,
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
        ticker_scanners=ticker_scanners,
        synthetic_ohlc_structure_summary=synthetic_ohlc_structure_summary,
        daily_trigger_classifications=daily_trigger_classifications,
        classification_source_key=classification_source_key,
        snapshot_source_key=snapshot_source_key,
        event_window_mode_key=event_window_mode_key,
    )


def _render_rolling_legacy_shell(
    *,
    report_header: Any,
    window_summary: dict[str, Any],
    ecosystem_window_change: dict[str, Any],
    overheat_rotation_risk_progression: dict[str, Any],
    subindustry_timing_persistence: dict[str, Any],
    subindustry_improvement_deterioration: dict[str, Any],
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
        ]
    )
    lines.extend(
        _render_table_or_none(
            headers=["entity_type", "entity", "metric", "first_date", "first_value", "last_date", "last_value", "change"],
            rows=[
                [
                    row.get("entity_type"),
                    row.get("entity_code"),
                    row.get("metric_name"),
                    row.get("first_date"),
                    row.get("first_value"),
                    row.get("last_date"),
                    row.get("last_value"),
                    row.get("change"),
                ]
                for row in list(ecosystem_window_change.get("rows") or [])
            ],
            empty_message="No ecosystem window change rows available from current V3 query data.",
        )
    )
    if ecosystem_window_change.get("is_truncated"):
        lines.append(
            f"Showing {ecosystem_window_change.get('rows_rendered')} of {ecosystem_window_change.get('rows_available')} ecosystem window change rows using stratified LAYER/SUBINDUSTRY selection."
        )
        rendered_counts = ecosystem_window_change.get("rows_rendered_by_entity_type") or {}
        if rendered_counts:
            count_parts = []
            for entity_type in ("LAYER", "SUBINDUSTRY", "ECOSYSTEM"):
                if entity_type in rendered_counts:
                    count_parts.append(f"{entity_type}={rendered_counts[entity_type]}")
            if count_parts:
                lines.append(f"Rendered rows by entity type: {', '.join(count_parts)}.")
        lines.append("")
    lines.extend(
        [
            "## 5. Overheat / rotation risk progression",
        ]
    )
    lines.extend(
        _render_table_or_none(
            headers=["signal_date", "entity_type", "risk_level", "group_count"],
            rows=[
                [
                    row.get("signal_date"),
                    row.get("entity_type"),
                    row.get("risk_level"),
                    row.get("group_count"),
                ]
                for row in list(overheat_rotation_risk_progression.get("risk_count_rows") or [])
            ],
            empty_message="No overheat / rotation risk count rows available from current V3 query data.",
        )
    )
    lines.extend(
        _render_table_or_none(
            headers=[
                "entity_type",
                "entity",
                "first_date",
                "first_risk",
                "last_date",
                "last_risk",
                "change",
                "first_timing",
                "last_timing",
            ],
            rows=[
                [
                    row.get("entity_type"),
                    row.get("entity_code"),
                    row.get("first_date"),
                    row.get("first_risk_level"),
                    row.get("last_date"),
                    row.get("last_risk_level"),
                    row.get("risk_change"),
                    row.get("first_timing_state"),
                    row.get("last_timing_state"),
                ]
                for row in list(overheat_rotation_risk_progression.get("risk_progression_rows") or [])
            ],
            empty_message="No non-low or worsened overheat / rotation risk progression rows available from current V3 query data.",
        )
    )
    if overheat_rotation_risk_progression.get("is_truncated"):
        lines.append(
            f"Showing {overheat_rotation_risk_progression.get('progression_rows_rendered')} of {overheat_rotation_risk_progression.get('progression_rows_available')} overheat / rotation risk progression rows."
        )
        lines.append("")
    lines.extend(
        [
            "## 6. Subindustry timing persistence",
        ]
    )
    lines.extend(
        _render_table_or_none(
            headers=[
                "subindustry",
                "dates",
                "buy_zone_days",
                "add_on_pullback_days",
                "trim_watch_days",
                "exit_zone_days",
                "neutral_days",
                "other_days",
                "first_state",
                "last_state",
                "last_overheat",
            ],
            rows=[
                [
                    row.get("entity_code"),
                    f"{row.get('observed_timing_dates_count')}/{row.get('selected_dates_count')}",
                    row.get("buy_zone_days"),
                    row.get("add_on_pullback_days"),
                    row.get("trim_watch_days"),
                    row.get("exit_zone_days"),
                    row.get("neutral_days"),
                    row.get("other_timing_days"),
                    row.get("first_timing_state"),
                    row.get("last_timing_state"),
                    row.get("last_overheat_risk_level"),
                ]
                for row in list(subindustry_timing_persistence.get("rows") or [])
            ],
            empty_message="No subindustry timing persistence rows available from current V3 query data.",
        )
    )
    if subindustry_timing_persistence.get("is_truncated"):
        lines.extend(
            [
                f"Showing {subindustry_timing_persistence.get('rows_rendered')} of {subindustry_timing_persistence.get('rows_available')} subindustry timing persistence rows.",
                "",
            ]
        )
    else:
        lines.append("")
    lines.extend(
        [
            "## 7. Subindustry improvement / deterioration",
        ]
    )
    lines.extend(
        _render_table_or_none(
            headers=["subindustry", "metric", "first_date", "first_value", "last_date", "last_value", "change", "change_pct", "direction"],
            rows=[
                [
                    row.get("entity_code"),
                    row.get("metric_name"),
                    row.get("first_date"),
                    row.get("first_value"),
                    row.get("last_date"),
                    row.get("last_value"),
                    row.get("change"),
                    row.get("change_pct"),
                    row.get("direction"),
                ]
                for row in list(subindustry_improvement_deterioration.get("rows") or [])
            ],
            empty_message="No subindustry improvement / deterioration rows available from current V3 query data.",
        )
    )
    if subindustry_improvement_deterioration.get("is_truncated"):
        rendered_by_direction = subindustry_improvement_deterioration.get("rows_rendered_by_direction") or {}
        lines.extend(
            [
                f"Showing {subindustry_improvement_deterioration.get('rows_rendered')} of {subindustry_improvement_deterioration.get('rows_available')} subindustry improvement / deterioration rows using direction-aware selection.",
            ]
        )
        if rendered_by_direction:
            lines.extend(
                [
                    "Rendered rows by direction: "
                    f"DETERIORATED={rendered_by_direction.get('DETERIORATED', 0)}, "
                    f"IMPROVED={rendered_by_direction.get('IMPROVED', 0)}, "
                    f"UNCHANGED={rendered_by_direction.get('UNCHANGED', 0)}, "
                    f"n/a={rendered_by_direction.get('n/a', 0)}.",
                    "",
                ]
            )
        else:
            lines.append("")
    else:
        lines.append("")
    lines.extend(
        [
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


def _render_daily_legacy_shell(
    *,
    report_header: Any,
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
    ticker_scanners: dict[str, Any],
    synthetic_ohlc_structure_summary: dict[str, Any],
    daily_trigger_classifications: list[dict[str, Any]],
    classification_source_key: str,
    snapshot_source_key: str,
    event_window_mode_key: str,
) -> str:
    timing_rows = _daily_timing_rows(group_metrics=group_metrics, group_snapshots=group_snapshots)
    lines = [
        "# Datacenter Daily Swing Signal Report",
        "",
        "## 1. Title and run metadata",
        f"- ecosystem_code: {_value(_get_field(report_header, 'ecosystem_code'))}",
        f"- taxonomy_version_code: {_value(_get_field(report_header, 'taxonomy_version_code'))}",
        f"- signal_date: {_value(_get_field(report_header, 'signal_date'))}",
        f"- run_id: {_value(_get_field(report_header, 'run_id'))}",
        f"- window_code: {_value(_get_field(report_header, 'window_code'))}",
        "",
        "## Watchlist Summary",
    ]
    lines.extend(_render_daily_watchlist_summary(watchlist_summary, watchlist_members))
    lines.extend(
        [
            "## 3. Dashboard",
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
            empty_message="Not available from current V3 query data in DB-V3-73b.",
        )
    )
    lines.append("- Full legacy dashboard aggregation is not available from current V3 query data in DB-V3-73b.")
    lines.append("")
    lines.append("## 4. Rotation Risk / Overheat Index")
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
                    row.get("group_timing_state"),
                    row.get("group_overheat_risk_level"),
                ]
                for row in group_metrics
            ],
            empty_message="Not available from current V3 query data in DB-V3-73b.",
        )
    )
    lines.extend(["## 5. Subindustry Timing States"])
    lines.extend(
        _render_table_or_none(
            headers=[
                "entity_code",
                "entity_name",
                "timing_state",
                "trend_state",
                "summary_state",
                "freshness_status",
                "quality_status",
            ],
            rows=timing_rows,
            empty_message="Not available from current V3 query data in DB-V3-73b.",
        )
    )
    lines.extend(["## 6. Buy-Zone Subindustries"])
    lines.extend(
        _render_filtered_daily_subindustry_rows(
            timing_rows=timing_rows,
            allowed_states={"BUY_ZONE"},
        )
    )
    lines.extend(["## 7. Add-On Pullback Subindustries"])
    lines.extend(
        _render_filtered_daily_subindustry_rows(
            timing_rows=timing_rows,
            allowed_states={"ADD_ON_PULLBACK", "PULLBACK_CANDIDATE"},
        )
    )
    lines.extend(["## 8. Trim/Watch Subindustries"])
    lines.extend(
        _render_filtered_daily_subindustry_rows(
            timing_rows=timing_rows,
            allowed_states={"TRIM_WATCH", "WATCH_ZONE", "EXIT_WATCH"},
        )
    )
    lines.extend(["## 9. Exit-Zone Subindustries"])
    lines.extend(
        _render_filtered_daily_subindustry_rows(
            timing_rows=timing_rows,
            allowed_states={"EXIT_ZONE"},
        )
    )
    lines.extend(
        [
            "## 10. Synthetic OHLC Structure Summary",
        ]
    )
    lines.extend(
        _render_daily_synthetic_ohlc_structure_summary(
            summary=synthetic_ohlc_structure_summary,
        )
    )
    lines.extend(
        [
            "## 11. Group Structure Breaks / Resets",
        ]
    )
    lines.extend(
        _render_table_or_none(
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
                if row.get("entity_type") in {"ECOSYSTEM", "LAYER", "SUBINDUSTRY"}
            ],
            empty_message="Not available from current V3 query data in DB-V3-73b.",
        )
    )
    lines.extend(
        [
            "## 12. Breakout Ticker Scanner",
        ]
    )
    lines.extend(
        _render_daily_ticker_scanner_section(
            rows=list(ticker_scanners.get("breakout_rows") or []),
            rows_available=ticker_scanners.get("breakout_rows_available"),
            is_truncated=bool(ticker_scanners.get("is_breakout_truncated")),
            scanner_label="breakout",
        )
    )
    lines.extend(
        [
            "## 13. Pullback Ticker Scanner",
        ]
    )
    lines.extend(
        _render_daily_ticker_scanner_section(
            rows=list(ticker_scanners.get("pullback_rows") or []),
            rows_available=ticker_scanners.get("pullback_rows_available"),
            is_truncated=bool(ticker_scanners.get("is_pullback_truncated")),
            scanner_label="pullback",
        )
    )
    lines.extend(
        [
            "## 14. Exit-Risk Ticker Scanner",
        ]
    )
    lines.extend(
        _render_daily_ticker_scanner_section(
            rows=list(ticker_scanners.get("exit_risk_rows") or []),
            rows_available=ticker_scanners.get("exit_risk_rows_available"),
            is_truncated=bool(ticker_scanners.get("is_exit_risk_truncated")),
            scanner_label="exit-risk",
        )
    )
    lines.extend(
        [
            "## 15. Daily Triggers",
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
    lines.extend(
        [
            "## 16. Swing MA Break Status",
        ]
    )
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
                if str(row.get("signal_family") or "") == "MA_STATUS" or "MA_" in str(row.get("signal_name") or "")
            ],
            empty_message="Not available from current V3 query data in DB-V3-73b.",
        )
    )
    lines.extend(
        [
            "## 17. Swing Signal Freshness",
        ]
    )
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
                if str(row.get("signal_family") or "") == "FRESHNESS"
            ],
            empty_message="Not available from current V3 query data in DB-V3-73b.",
        )
    )
    lines.extend(
        [
            "## 18. Data Quality",
        ]
    )
    lines.extend(_render_quality_and_coverage(quality_summary))
    lines.extend(
        [
            "## 19. Missing / Incomplete Inputs Summary",
            "- Current V3 query data provides combined quality and coverage summaries; a separate legacy missing-input read-model is not available in DB-V3-73b.",
            "",
            "## 20. Technical Relevance Context",
        ]
    )
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
                if row.get("relevance_labels")
            ],
            empty_message="Not available from current V3 query data in DB-V3-73b.",
        )
    )
    lines.extend(
        [
            "## V3 metadata / limitations appendix",
            f"- used_v2_runtime_tables: {_value(metadata.get('used_v2_runtime_tables'))}",
            f"- used_generated_reports: {_value(metadata.get('used_generated_reports'))}",
            f"- used_dashboard_output: {_value(metadata.get('used_dashboard_output'))}",
            f"- {classification_source_key}: {_value(metadata.get(classification_source_key))}",
            f"- {snapshot_source_key}: {_value(metadata.get(snapshot_source_key))}",
            f"- {event_window_mode_key}: {_value(metadata.get(event_window_mode_key))}",
            f"- ranking_fields_mostly_null: {_value(metadata.get('ranking_fields_mostly_null'))}",
            "- CRGY is intentionally materialized as INSUFFICIENT_DATA in daily_trigger.",
            "- NXPI reflects accepted current lower-level source-truth SELL_TRIGGER semantics.",
            "",
        ]
    )
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


def _render_daily_watchlist_summary(
    watchlist_summary: dict[str, Any],
    watchlist_members: list[dict[str, Any]],
) -> list[str]:
    if watchlist_summary:
        lines = _render_table_or_none(
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
        lines.extend(
            _render_table_or_none(
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
            )
        )
        return lines
    return _render_table_or_none(
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
    )


def _render_daily_ticker_scanner_section(
    *,
    rows: list[dict[str, Any]],
    rows_available: Any,
    is_truncated: bool,
    scanner_label: str,
) -> list[str]:
    empty_messages = {
        "breakout": "No breakout ticker scanner rows available from current V3 query data.",
        "pullback": "No pullback ticker scanner rows available from current V3 query data.",
        "exit-risk": "No exit-risk ticker scanner rows available from current V3 query data.",
    }
    lines = _render_table_or_none(
        headers=[
            "ticker",
            "layer",
            "subindustry",
            "close",
            "return_5d",
            "return_10d",
            "return_20d",
            "distance_to_ema20_pct",
            "trend_state",
            "signal",
            "strength",
            "exit_severity",
            "exit_reason",
            "subindustry_timing",
            "subindustry_overheat",
            "layer_timing",
            "layer_overheat",
            "price_status",
        ],
        rows=[
            [
                row.get("ticker"),
                row.get("primary_layer"),
                row.get("primary_subindustry"),
                row.get("close"),
                row.get("return_5d"),
                row.get("return_10d"),
                row.get("return_20d"),
                row.get("distance_to_ema20_pct"),
                row.get("ticker_trend_state"),
                row.get("signal_value"),
                row.get("signal_strength"),
                row.get("exit_risk_severity"),
                row.get("exit_reason"),
                row.get("subindustry_timing_state"),
                row.get("subindustry_overheat_risk_level"),
                row.get("layer_timing_state"),
                row.get("layer_overheat_risk_level"),
                row.get("price_data_status"),
            ]
            for row in rows
        ],
        empty_message=empty_messages[scanner_label],
    )
    if is_truncated:
        lines.append(
            f"- Showing {len(rows)} of {_value(rows_available)} {scanner_label} ticker scanner rows."
        )
        lines.append("")
    return lines


def _render_daily_synthetic_ohlc_structure_summary(
    *,
    summary: dict[str, Any],
) -> list[str]:
    rows = list(summary.get("rows") or [])
    lines = _render_table_or_none(
        headers=[
            "entity_type",
            "entity",
            "structure",
            "structure_date",
            "bos_event",
            "bos_date",
            "reset_reason",
            "reset_date",
            "structure_freshness",
            "bos_freshness",
            "reset_freshness",
            "timing_state",
            "overheat",
        ],
        rows=[
            [
                row.get("entity_type"),
                row.get("entity_code"),
                row.get("latest_structure_label"),
                row.get("latest_structure_date"),
                row.get("latest_bos_event_type"),
                row.get("latest_bos_date"),
                row.get("latest_reset_reason"),
                row.get("latest_reset_date"),
                row.get("structure_freshness"),
                row.get("bos_freshness"),
                row.get("reset_freshness"),
                row.get("timing_state"),
                row.get("overheat_risk_level"),
            ]
            for row in rows
        ],
        empty_message="No synthetic OHLC structure summary rows available from current V3 query data.",
    )
    if summary.get("is_truncated"):
        lines.append(
            f"- Showing {len(rows)} of {_value(summary.get('rows_available'))} synthetic OHLC structure summary rows."
        )
        lines.append("")
    return lines


def _daily_timing_rows(
    *,
    group_metrics: list[dict[str, Any]],
    group_snapshots: list[dict[str, Any]],
) -> list[list[Any]]:
    metric_rows_by_code = {
        str(row.get("entity_code") or ""): row
        for row in group_metrics
        if str(row.get("entity_type") or "") == "SUBINDUSTRY"
    }
    rows: list[list[Any]] = []
    seen_codes: set[str] = set()
    for row in group_snapshots:
        if str(row.get("entity_type") or "") != "SUBINDUSTRY":
            continue
        entity_code = str(row.get("entity_code") or "")
        metric_row = metric_rows_by_code.get(entity_code, {})
        rows.append(
            [
                row.get("entity_code"),
                row.get("entity_name"),
                metric_row.get("group_timing_state") or row.get("timing_state"),
                row.get("trend_state"),
                row.get("summary_state"),
                row.get("freshness_status"),
                row.get("quality_status"),
            ]
        )
        seen_codes.add(entity_code)
    for row in group_metrics:
        if str(row.get("entity_type") or "") != "SUBINDUSTRY":
            continue
        entity_code = str(row.get("entity_code") or "")
        if entity_code in seen_codes:
            continue
        rows.append(
            [
                row.get("entity_code"),
                row.get("entity_name"),
                row.get("group_timing_state"),
                None,
                row.get("group_current_status"),
                None,
                None,
            ]
        )
    rows.sort(key=lambda row: (str(row[2] or ""), str(row[0] or "")))
    return rows


def _render_filtered_daily_subindustry_rows(
    *,
    timing_rows: list[list[Any]],
    allowed_states: set[str],
) -> list[str]:
    filtered_rows = [row for row in timing_rows if str(row[2] or "") in allowed_states]
    if not filtered_rows:
        return ["Not available from current V3 query data in DB-V3-73b.", ""]
    return _render_table_or_none(
        headers=[
            "entity_code",
            "entity_name",
            "timing_state",
            "trend_state",
            "summary_state",
            "freshness_status",
            "quality_status",
        ],
        rows=filtered_rows,
        empty_message="Not available from current V3 query data in DB-V3-73b.",
    )


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
