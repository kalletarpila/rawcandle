from rawcandle.reporting_v3_markdown import render_rolling2_markdown_report
from rawcandle.reporting_v3_query import Rolling2ReportQueryData, Rolling30ReportHeader


def _sample_query_data(*, with_empty_events: bool = False) -> Rolling2ReportQueryData:
    return Rolling2ReportQueryData(
        report_header=Rolling30ReportHeader(
            run_id="run-2",
            ecosystem_code="DATACENTER",
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            signal_date="2026-05-30",
            window_code="rolling2",
        ),
        window_summary={
            "requested_end_date": "2026-05-30",
            "window_start_date": "2026-05-29",
            "window_end_date": "2026-05-30",
            "valid_signal_dates_count": 2,
            "valid_signal_dates_included": ["2026-05-29", "2026-05-30"],
            "incomplete_window": False,
        },
        ecosystem_window_change={
            "rows": [
                {
                    "entity_type": "LAYER",
                    "entity_code": "INFRA",
                    "entity_name": "Infrastructure",
                    "metric_name": "trend_breadth",
                    "first_date": "2026-05-29",
                    "first_value": 35.0,
                    "last_date": "2026-05-30",
                    "last_value": 25.0,
                    "change": -10.0,
                },
                {
                    "entity_type": "SUBINDUSTRY",
                    "entity_code": "SEMIS",
                    "entity_name": "Semis",
                    "metric_name": "group_timing_state",
                    "first_date": "2026-05-29",
                    "first_value": "WATCH_PRESSURE",
                    "last_date": "2026-05-30",
                    "last_value": "EMERGENCY_SELL_PRESSURE",
                    "change": "n/a",
                },
            ],
            "rows_available": 120,
            "rows_rendered": 100,
            "is_truncated": True,
            "rows_rendered_by_entity_type": {"LAYER": 50, "SUBINDUSTRY": 50},
        },
        overheat_rotation_risk_progression={
            "risk_count_rows": [
                {"signal_date": "2026-05-29", "entity_type": "LAYER", "risk_level": "LOW", "group_count": 1},
                {"signal_date": "2026-05-30", "entity_type": "SUBINDUSTRY", "risk_level": "HIGH", "group_count": 1},
            ],
            "risk_progression_rows": [
                {
                    "entity_type": "SUBINDUSTRY",
                    "entity_code": "SEMIS",
                    "entity_name": "Semis",
                    "first_date": "2026-05-29",
                    "first_risk_level": "MEDIUM",
                    "last_date": "2026-05-30",
                    "last_risk_level": "HIGH",
                    "risk_change": "WORSENED",
                    "first_timing_state": "WATCH_PRESSURE",
                    "last_timing_state": "EMERGENCY_SELL_PRESSURE",
                }
            ],
            "progression_rows_available": 1,
            "progression_rows_rendered": 1,
            "is_truncated": False,
        },
        watchlist_summary={
            "counts": {
                "active_watchlist_count": 1,
                "in_ecosystem_count": 1,
                "missing_price_data_count": 0,
                "breakout_count": 0,
                "pullback_count": 1,
                "exit_risk_count": 1,
                "high_exit_risk_count": 1,
                "medium_exit_risk_count": 0,
            },
            "rows": [
                {
                    "ticker": "NVDA",
                    "current_watchlist_status": "ACTIVE",
                    "window_watchlist_status": "HIGH_EXIT_RISK",
                    "in_datacenter_ecosystem": True,
                    "primary_layer": "INFRA",
                    "primary_subindustry": "SEMIS",
                    "breakout_days": 0.0,
                    "pullback_days": 1.0,
                    "exit_risk_days": 2.0,
                    "high_exit_risk_days": 2.0,
                    "medium_exit_risk_days": 0.0,
                    "last_subindustry_timing_state": "WATCH_PRESSURE",
                    "last_subindustry_overheat_risk_level": "LOW",
                    "last_layer_timing_state": "WATCH_PRESSURE",
                    "last_layer_overheat_risk_level": "LOW",
                    "last_price_data_status": "OK",
                }
            ],
        },
        quality_summary={
            "rows": [
                {
                    "window_code": "rolling2",
                    "quality_scope": "RUN",
                    "quality_status": "WARN",
                    "scope_entity_type": "ECOSYSTEM",
                    "scope_entity_code": "DATACENTER",
                    "expected_count": 237,
                    "actual_count": 237,
                    "warning_count": 1,
                    "error_count": 0,
                }
            ],
            "coverage_counts": [
                {"entity_type": "ECOSYSTEM", "coverage_status": "OK", "row_count": 1},
                {"entity_type": "TICKER", "coverage_status": "OK", "row_count": 1},
                {"entity_type": "TICKER", "coverage_status": "WATCHLIST_ONLY", "row_count": 1},
            ],
        },
        ecosystem_snapshot={
            "entity_code": "DATACENTER",
            "snapshot_status": "WARN",
            "trend_state": "DOWN",
            "summary_state": "FRAGILE",
            "quality_status": "WARN",
        },
        group_snapshots=[
            {
                "entity_type": "LAYER",
                "entity_code": "INFRA",
                "entity_name": "Infrastructure",
                "timing_state": "WATCH_PRESSURE",
                "trend_state": "DOWN",
                "summary_state": "FRAGILE",
                "freshness_status": "FRESH",
                "quality_status": "OK",
            },
            {
                "entity_type": "SUBINDUSTRY",
                "entity_code": "AI|SEMIS",
                "entity_name": "AI|Semis",
                "timing_state": "EMERGENCY_SELL_PRESSURE",
                "trend_state": "DOWN",
                "summary_state": "HIGH_RISK",
                "freshness_status": "AGING",
                "quality_status": "WARN",
            },
        ],
        ticker_snapshots=[
            {
                "entity_type": "TICKER",
                "entity_code": "CRGY",
                "classification_state": "WRONG_FROM_SNAPSHOT",
            },
            {
                "entity_type": "TICKER",
                "entity_code": "NVDA",
                "classification_state": "WRONG_FROM_SNAPSHOT",
            },
        ],
        rolling2_sell_pressure_classifications=[
            {
                "ticker": "NVDA",
                "classification_state": "EMERGENCY_SELL_PRESSURE",
                "primary_reason": "RISK|STACKED_EXIT_SIGNALS",
                "blocking_reason": "recent_bos_down",
                "risk_reason": "EXIT_RISK_CLUSTER",
                "next_action": "REDUCE_OR_EXIT",
                "decision_status": "OK",
                "priority_score": None,
                "priority_label": None,
                "sort_rank": None,
            }
        ],
        ticker_metrics={
            "NVDA": {
                "ticker": "NVDA",
                "entity_name": "NVIDIA",
                "breakout_days": 0.0,
                "pullback_days": 1.0,
                "exit_risk_days": 2.0,
                "high_exit_risk_days": 2.0,
                "medium_exit_risk_days": 0.0,
                "valid_signal_dates": 2.0,
                "distance_to_ema20_pct": -3.5,
            }
        },
        group_metrics=[
            {
                "entity_type": "LAYER",
                "entity_code": "INFRA",
                "entity_name": "Infrastructure",
                "pct_above_ema20": 40.0,
                "return_5d": -6.0,
                "synthetic_close": 94.0,
                "trend_breadth": 25.0,
                "weakness_breadth": 75.0,
                "valid_signal_dates": 2.0,
                "group_current_status": "WATCH_PRESSURE",
                "group_window_status": "EMERGENCY_SELL_PRESSURE",
                "group_status_change": "WATCH_PRESSURE -> EMERGENCY_SELL_PRESSURE",
                "group_timing_state": "WATCH_PRESSURE",
                "group_timing_reason": "WATCH_PRESSURE:exit_risk_cluster",
                "group_overheat_risk_level": "LOW",
            }
        ],
        watchlist_members=[
            {
                "watchlist_code": "PRIMARY",
                "watchlist_name": "Primary",
                "ticker": "NVDA",
                "entity_name": "NVIDIA",
                "member_role": "CORE",
                "member_status": "ACTIVE",
                "effective_from": "2026-05-30",
                "effective_to": None,
            }
        ],
        structural_events=[] if with_empty_events else [
            {
                "entity_type": "TICKER",
                "entity_code": "NVDA",
                "event_date": "2026-05-30",
                "event_type": "RESET",
                "event_direction": "DOWN",
                "event_status": "ACTIVE",
            }
        ],
        signal_observations=[] if with_empty_events else [
            {
                "entity_code": "NVDA",
                "signal_name": "RESET_FRESHNESS",
                "signal_family": "FRESHNESS",
                "signal_direction": "DOWN",
                "signal_value": "FRESH",
                "observed_date": "2026-05-30",
                "relevance_labels": "CONTEXTUAL",
            }
        ],
        metadata={
            "used_v2_runtime_tables": False,
            "used_generated_reports": False,
            "used_dashboard_output": False,
            "rolling2_classification_source": "eco_classification_decision",
            "rolling2_snapshot_classification_source_used": False,
            "rolling2_event_window_mode": "event_date_range_within_2d_window",
            "ranking_fields_mostly_null": True,
            "coverage_without_classification_tickers": ["CRGY"],
            "signal_names_present": ["RESET_FRESHNESS"],
            "limitations": [
                "generated Markdown/CSV reports were not used as source data",
                "dashboard-rendered output was not used as source data",
                "rolling2 classifications are read from eco_classification_decision",
                "eco_entity_window_snapshot.classification_state is not the primary rolling2 classification source",
                "ranking fields are mostly NULL; deterministic fallback ordering is used",
                "rolling2 signal observations are limited to rolling2-compatible observations; daily candlestick/divergence semantics are not invented",
                "coverage or snapshot rows can exist without rolling2 classification rows, for example CRGY-like cases",
                "rolling2_event_window_mode refers to a 2d event-date range, not 5d or 30d",
                "no V2 report/context tables were used",
            ],
        },
    )


def test_renderer_returns_deterministic_rolling2_markdown_from_query_data_only() -> None:
    query_data = _sample_query_data()

    markdown = render_rolling2_markdown_report(query_data)

    assert isinstance(markdown, str)
    assert "# Datacenter Rolling Swing Report" in markdown
    assert "## 1. Title and run metadata" in markdown
    assert "## 2. Window summary" in markdown
    assert "requested_end_date" in markdown
    assert "valid_signal_dates_included" in markdown
    assert "2026-05-29, 2026-05-30" in markdown
    assert "Window start/end and valid selected dates: Not available from current V3 query data in DB-V3-70." not in markdown
    assert "## Watchlist Summary" in markdown
    assert "active_watchlist_count" in markdown
    assert "window_watchlist_status" in markdown
    assert "primary_layer" in markdown
    assert "primary_subindustry" in markdown
    assert "last_price_data_status" in markdown
    assert "Full legacy watchlist read-model is not available from current V3 query data in DB-V3-70." not in markdown
    assert "## 4. Ecosystem window change" in markdown
    assert "entity_type | entity | metric | first_date | first_value | last_date | last_value | change" in markdown
    assert "LAYER" in markdown
    assert "SUBINDUSTRY" in markdown
    assert "trend_breadth" in markdown
    assert "group_timing_state" in markdown
    assert "No ecosystem window change rows available from current V3 query data." not in markdown
    assert "## 4. Ecosystem window change\nNot available from current V3 query data in DB-V3-70." not in markdown
    assert "Showing 100 of 120 ecosystem window change rows using stratified LAYER/SUBINDUSTRY selection." in markdown
    assert "Rendered rows by entity type: LAYER=50, SUBINDUSTRY=50." in markdown
    assert "## 5. Overheat / rotation risk progression" in markdown
    assert "signal_date | entity_type | risk_level | group_count" in markdown
    assert "entity_type | entity | first_date | first_risk | last_date | last_risk | change | first_timing | last_timing" in markdown
    assert "WORSENED" in markdown
    assert "No overheat / rotation risk count rows available from current V3 query data." not in markdown
    assert "No non-low or worsened overheat / rotation risk progression rows available from current V3 query data." not in markdown
    assert "## 5. Overheat / rotation risk progression\nNot available from current V3 query data in DB-V3-70." not in markdown
    assert "## 6. Subindustry timing persistence" in markdown
    assert "## 7. Subindustry improvement / deterioration" in markdown
    assert "Not available from current V3 query data in DB-V3-70." in markdown
    assert "## 8. Repeated breakout tickers" in markdown
    assert "## 9. Repeated pullback tickers" in markdown
    assert "## 10. Repeated exit-risk tickers" in markdown
    assert "## Rolling 2 Sell Pressure" in markdown
    assert "## 15. Data quality over the window" in markdown
    assert "## 16. Missing / incomplete inputs summary" in markdown
    assert "## V3 metadata / limitations appendix" in markdown
    assert "## Metadata" not in markdown
    assert "## Quality and coverage" not in markdown
    assert "## Ecosystem snapshot" not in markdown
    assert "## Group overview" not in markdown
    assert "run-2" in markdown
    assert "WATCHLIST_ONLY" in markdown
    assert "rolling2_classification_source: eco_classification_decision" in markdown
    assert "rolling2_snapshot_classification_source_used: False" in markdown
    assert "rolling2_event_window_mode: event_date_range_within_2d_window" in markdown
    assert "generated Markdown/CSV reports were not used as source data" in markdown
    assert "eco_entity_window_snapshot.classification_state is not the primary rolling2 classification source" in markdown
    assert "ranking_fields_mostly_null: True" in markdown
    assert "No such table" not in markdown
    assert "RISK\\|STACKED_EXIT_SIGNALS" in markdown
    assert "AI\\|SEMIS" in markdown
    assert markdown.index("## Watchlist Summary") < markdown.index("## Rolling 2 Sell Pressure")
    assert markdown.index("## V3 metadata / limitations appendix") > markdown.index("## 16. Missing / incomplete inputs summary")


def test_renderer_handles_empty_rolling2_events_and_signals_gracefully() -> None:
    query_data = _sample_query_data(with_empty_events=True)

    markdown = render_rolling2_markdown_report(query_data)

    assert "- No structural event rows." in markdown
    assert "- rolling2-compatible signal observations only: none" in markdown
    assert "- No signal observation rows." in markdown
