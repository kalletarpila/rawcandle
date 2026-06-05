from rawcandle.reporting_v3_markdown import render_rolling30_markdown_report
from rawcandle.reporting_v3_query import Rolling30ReportHeader, Rolling30ReportQueryData


def _sample_query_data(*, with_empty_events: bool = False) -> Rolling30ReportQueryData:
    return Rolling30ReportQueryData(
        report_header=Rolling30ReportHeader(
            run_id="run-30",
            ecosystem_code="DATACENTER",
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            signal_date="2026-05-30",
            window_code="rolling30",
        ),
        window_summary={
            "requested_end_date": "2026-05-30",
            "window_start_date": "2026-05-01",
            "window_end_date": "2026-05-30",
            "valid_signal_dates_count": 4,
            "valid_signal_dates_included": ["2026-05-01", "2026-05-14", "2026-05-28", "2026-05-30"],
            "incomplete_window": True,
        },
        ecosystem_window_change={
            "rows": [
                {
                    "entity_type": "LAYER",
                    "entity_code": "INFRA",
                    "entity_name": "Infrastructure",
                    "metric_name": "pct_above_ema20",
                    "first_date": "2026-05-01",
                    "first_value": 52.0,
                    "last_date": "2026-05-30",
                    "last_value": 62.5,
                    "change": 10.5,
                },
                {
                    "entity_type": "SUBINDUSTRY",
                    "entity_code": "SEMIS",
                    "entity_name": "Semis",
                    "metric_name": "group_timing_state",
                    "first_date": "2026-05-01",
                    "first_value": "BUY_ZONE",
                    "last_date": "2026-05-30",
                    "last_value": "WATCH_ZONE",
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
                {"signal_date": "2026-05-01", "entity_type": "LAYER", "risk_level": "MEDIUM", "group_count": 2},
                {"signal_date": "2026-05-30", "entity_type": "SUBINDUSTRY", "risk_level": "HIGH", "group_count": 1},
            ],
            "risk_progression_rows": [
                {
                    "entity_type": "SUBINDUSTRY",
                    "entity_code": "SEMIS",
                    "entity_name": "Semis",
                    "first_date": "2026-05-01",
                    "first_risk_level": "MEDIUM",
                    "last_date": "2026-05-30",
                    "last_risk_level": "HIGH",
                    "risk_change": "WORSENED",
                    "first_timing_state": "BUY_ZONE",
                    "last_timing_state": "EXIT_ZONE",
                }
            ],
            "progression_rows_available": 1,
            "progression_rows_rendered": 1,
            "is_truncated": False,
        },
        subindustry_timing_persistence={
            "rows": [
                {
                    "entity_type": "SUBINDUSTRY",
                    "entity_code": "SEMIS",
                    "entity_name": "Semis",
                    "selected_dates_count": 4,
                    "observed_timing_dates_count": 3,
                    "buy_zone_days": 1,
                    "add_on_pullback_days": 0,
                    "trim_watch_days": 1,
                    "exit_zone_days": 1,
                    "neutral_days": 0,
                    "other_timing_days": 0,
                    "first_date": "2026-05-01",
                    "first_timing_state": "BUY_ZONE",
                    "last_date": "2026-05-30",
                    "last_timing_state": "EXIT_ZONE",
                    "last_overheat_risk_level": "HIGH",
                }
            ],
            "rows_available": 1,
            "rows_rendered": 1,
            "is_truncated": False,
            "selected_dates_count": 4,
        },
        watchlist_summary={
            "counts": {
                "active_watchlist_count": 1,
                "in_ecosystem_count": 1,
                "missing_price_data_count": 0,
                "breakout_count": 1,
                "pullback_count": 1,
                "exit_risk_count": 1,
                "high_exit_risk_count": 1,
                "medium_exit_risk_count": 1,
            },
            "rows": [
                {
                    "ticker": "NVDA",
                    "current_watchlist_status": "ACTIVE",
                    "window_watchlist_status": "HIGH_EXIT_RISK",
                    "in_datacenter_ecosystem": True,
                    "primary_layer": "INFRA",
                    "primary_subindustry": "SEMIS",
                    "breakout_days": 3.0,
                    "pullback_days": 2.0,
                    "exit_risk_days": 4.0,
                    "high_exit_risk_days": 2.0,
                    "medium_exit_risk_days": 2.0,
                    "last_subindustry_timing_state": "BUY_ZONE",
                    "last_subindustry_overheat_risk_level": "LOW",
                    "last_layer_timing_state": "BUY_ZONE",
                    "last_layer_overheat_risk_level": "LOW",
                    "last_price_data_status": "OK",
                }
            ],
        },
        quality_summary={
            "rows": [
                {
                    "window_code": "rolling30",
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
            "snapshot_status": "OK",
            "trend_state": "UP",
            "summary_state": "HEALTHY",
            "quality_status": "WARN",
        },
        group_snapshots=[
            {
                "entity_type": "LAYER",
                "entity_code": "INFRA",
                "entity_name": "Infrastructure",
                "timing_state": "BUY_ZONE",
                "trend_state": "UP",
                "summary_state": "STRONG",
                "freshness_status": "FRESH",
                "quality_status": "OK",
            },
            {
                "entity_type": "SUBINDUSTRY",
                "entity_code": "AI|SEMIS",
                "entity_name": "AI|Semis",
                "timing_state": "TRIM_WATCH",
                "trend_state": "UP",
                "summary_state": "MIXED",
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
        rolling30_buy_classifications=[
            {
                "ticker": "NVDA",
                "classification_state": "WATCH_ZONE",
                "primary_reason": "MIXED|OR_UNCONFIRMED_STRUCTURE",
                "blocking_reason": "recent_bos_down",
                "decision_status": "OK",
                "priority_score": None,
                "priority_label": None,
                "sort_rank": None,
            }
        ],
        rolling30_exit_classifications=[
            {
                "ticker": "NVDA",
                "classification_state": "EXIT_ZONE",
                "primary_reason": "ELEVATED_EXIT_RISK",
                "risk_reason": "CURRENT_HIGH_EXIT_RISK",
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
                "breakout_days": 3.0,
                "pullback_days": 2.0,
                "exit_risk_days": 4.0,
                "high_exit_risk_days": 2.0,
                "medium_exit_risk_days": 2.0,
                "valid_signal_dates": 30.0,
                "distance_to_ema20_pct": 1.5,
            }
        },
        group_metrics=[
            {
                "entity_type": "LAYER",
                "entity_code": "INFRA",
                "entity_name": "Infrastructure",
                "pct_above_ema20": 62.5,
                "return_5d": 4.0,
                "synthetic_close": 101.0,
                "trend_breadth": 70.0,
                "weakness_breadth": 30.0,
                "valid_signal_dates": 30.0,
                "group_current_status": "BUY_ZONE",
                "group_window_status": "EXIT_ZONE",
                "group_status_change": "BUY_ZONE -> EXIT_ZONE",
                "group_timing_state": "BUY_ZONE",
                "group_timing_reason": "BUY_ZONE:return_5d_pos",
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
                "event_type": "BOS",
                "event_direction": "DOWN",
                "event_status": "ACTIVE",
            }
        ],
        signal_observations=[] if with_empty_events else [
            {
                "entity_code": "NVDA",
                "signal_name": "BOS_FRESHNESS",
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
            "rolling30_classification_source": "eco_classification_decision",
            "rolling30_snapshot_classification_source_used": False,
            "ranking_fields_mostly_null": True,
            "coverage_without_classification_tickers": ["CRGY"],
            "signal_names_present": ["BOS_FRESHNESS"],
            "limitations": [
                "generated Markdown/CSV reports were not used as source data",
                "dashboard-rendered output was not used as source data",
                "rolling30 classifications are read from eco_classification_decision",
                "eco_entity_window_snapshot.classification_state is not used as the rolling30 classification source",
                "ranking fields are mostly NULL; deterministic fallback ordering is used",
                "rolling30 signal observations are limited to rolling30-compatible observations; daily candlestick/divergence semantics are not invented",
                "coverage or snapshot rows can exist without rolling30 classification rows, for example CRGY-like cases",
                "no V2 report/context tables were used",
            ],
        },
    )


def test_renderer_returns_deterministic_markdown_from_query_data_only() -> None:
    query_data = _sample_query_data()

    markdown = render_rolling30_markdown_report(query_data)

    assert isinstance(markdown, str)
    assert "# Datacenter Rolling Swing Report" in markdown
    assert "## 1. Title and run metadata" in markdown
    assert "## 2. Window summary" in markdown
    assert "requested_end_date" in markdown
    assert "window_start_date" in markdown
    assert "window_end_date" in markdown
    assert "valid_signal_dates_count" in markdown
    assert "valid_signal_dates_included" in markdown
    assert "2026-05-01, 2026-05-14, 2026-05-28, 2026-05-30" in markdown
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
    assert "INFRA" in markdown
    assert "pct_above_ema20" in markdown
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
    assert "subindustry | dates | buy_zone_days | add_on_pullback_days | trim_watch_days | exit_zone_days | neutral_days | other_days | first_state | last_state | last_overheat" in markdown
    assert "SEMIS" in markdown
    assert "3/4" in markdown
    assert "## 6. Subindustry timing persistence\nNot available from current V3 query data in DB-V3-70." not in markdown
    assert "## 7. Subindustry improvement / deterioration" in markdown
    assert "Not available from current V3 query data in DB-V3-70." in markdown
    assert "## 8. Repeated breakout tickers" in markdown
    assert "## 9. Repeated pullback tickers" in markdown
    assert "## 10. Repeated exit-risk tickers" in markdown
    assert "## Rolling 30 Buy Filter" in markdown
    assert "## Rolling 30 Exit Prefilter" in markdown
    assert "## 15. Data quality over the window" in markdown
    assert "## 16. Missing / incomplete inputs summary" in markdown
    assert "## V3 metadata / limitations appendix" in markdown
    assert "## Metadata" not in markdown
    assert "## Quality and coverage" not in markdown
    assert "## Ecosystem snapshot" not in markdown
    assert "## Group overview" not in markdown
    assert "run-30" in markdown
    assert "WATCHLIST_ONLY" in markdown
    assert "rolling30_classification_source: eco_classification_decision" in markdown
    assert "rolling30_snapshot_classification_source_used: False" in markdown
    assert "generated Markdown/CSV reports were not used as source data" in markdown
    assert "eco_entity_window_snapshot.classification_state is not used as the rolling30 classification source" in markdown
    assert "ranking_fields_mostly_null: True" in markdown
    assert "No such table" not in markdown
    assert "MIXED\\|OR_UNCONFIRMED_STRUCTURE" in markdown
    assert "AI\\|SEMIS" in markdown
    assert markdown.index("## Watchlist Summary") < markdown.index("## Rolling 30 Buy Filter")
    assert markdown.index("## Rolling 30 Exit Prefilter") < markdown.index("## 15. Data quality over the window")
    assert markdown.index("## V3 metadata / limitations appendix") > markdown.index("## 16. Missing / incomplete inputs summary")


def test_renderer_handles_empty_events_and_signals_gracefully() -> None:
    query_data = _sample_query_data(with_empty_events=True)

    markdown = render_rolling30_markdown_report(query_data)

    assert "- No structural event rows." in markdown
    assert "- rolling30-compatible signal observations only: none" in markdown
    assert "- No signal observation rows." in markdown
