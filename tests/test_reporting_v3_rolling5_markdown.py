from rawcandle.reporting_v3_markdown import render_rolling5_markdown_report
from rawcandle.reporting_v3_query import Rolling30ReportHeader, Rolling5ReportQueryData


def _sample_query_data(*, with_empty_events: bool = False) -> Rolling5ReportQueryData:
    return Rolling5ReportQueryData(
        report_header=Rolling30ReportHeader(
            run_id="run-5",
            ecosystem_code="DATACENTER",
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            signal_date="2026-05-30",
            window_code="rolling5",
        ),
        window_summary={
            "requested_end_date": "2026-05-30",
            "window_start_date": "2026-05-26",
            "window_end_date": "2026-05-30",
            "valid_signal_dates_count": 3,
            "valid_signal_dates_included": ["2026-05-26", "2026-05-29", "2026-05-30"],
            "incomplete_window": True,
        },
        ecosystem_window_change={
            "rows": [
                {
                    "entity_type": "LAYER",
                    "entity_code": "INFRA",
                    "entity_name": "Infrastructure",
                    "metric_name": "return_5d",
                    "first_date": "2026-05-26",
                    "first_value": -2.0,
                    "last_date": "2026-05-30",
                    "last_value": 1.0,
                    "change": 3.0,
                },
                {
                    "entity_type": "SUBINDUSTRY",
                    "entity_code": "SEMIS",
                    "entity_name": "Semis",
                    "metric_name": "group_overheat_risk_level",
                    "first_date": "2026-05-26",
                    "first_value": "MEDIUM",
                    "last_date": "2026-05-30",
                    "last_value": "LOW",
                    "change": "n/a",
                },
            ],
            "rows_available": 2,
            "rows_rendered": 2,
            "is_truncated": False,
        },
        watchlist_summary={
            "counts": {
                "active_watchlist_count": 1,
                "in_ecosystem_count": 1,
                "missing_price_data_count": 0,
                "breakout_count": 1,
                "pullback_count": 1,
                "exit_risk_count": 1,
                "high_exit_risk_count": 0,
                "medium_exit_risk_count": 1,
            },
            "rows": [
                {
                    "ticker": "NVDA",
                    "current_watchlist_status": "ACTIVE",
                    "window_watchlist_status": "EXIT_RISK",
                    "in_datacenter_ecosystem": True,
                    "primary_layer": "INFRA",
                    "primary_subindustry": "SEMIS",
                    "breakout_days": 1.0,
                    "pullback_days": 3.0,
                    "exit_risk_days": 2.0,
                    "high_exit_risk_days": 0.0,
                    "medium_exit_risk_days": 2.0,
                    "last_subindustry_timing_state": "PULLBACK",
                    "last_subindustry_overheat_risk_level": "LOW",
                    "last_layer_timing_state": "PULLBACK",
                    "last_layer_overheat_risk_level": "LOW",
                    "last_price_data_status": "OK",
                }
            ],
        },
        quality_summary={
            "rows": [
                {
                    "window_code": "rolling5",
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
                "timing_state": "PULLBACK_READY",
                "trend_state": "UP",
                "summary_state": "STRONG",
                "freshness_status": "FRESH",
                "quality_status": "OK",
            },
            {
                "entity_type": "SUBINDUSTRY",
                "entity_code": "AI|SEMIS",
                "entity_name": "AI|Semis",
                "timing_state": "BREAKDOWN_RISK",
                "trend_state": "DOWN",
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
        rolling5_pullback_classifications=[
            {
                "ticker": "NVDA",
                "classification_state": "PULLBACK_CANDIDATE",
                "primary_reason": "PULLBACK|ABOVE_EMA20",
                "blocking_reason": "needs_confirmation",
                "next_action": "monitor_reclaim",
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
                "breakout_days": 1.0,
                "pullback_days": 3.0,
                "exit_risk_days": 2.0,
                "high_exit_risk_days": 0.0,
                "medium_exit_risk_days": 2.0,
                "valid_signal_dates": 5.0,
                "distance_to_ema20_pct": -1.5,
            }
        },
        group_metrics=[
            {
                "entity_type": "LAYER",
                "entity_code": "INFRA",
                "entity_name": "Infrastructure",
                "pct_above_ema20": 62.5,
                "return_5d": -1.0,
                "synthetic_close": 101.0,
                "trend_breadth": 70.0,
                "weakness_breadth": 30.0,
                "valid_signal_dates": 5.0,
                "group_current_status": "PULLBACK",
                "group_window_status": "BREAKDOWN_RISK",
                "group_status_change": "BUY_ZONE -> PULLBACK",
                "group_timing_state": "PULLBACK",
                "group_timing_reason": "PULLBACK:ema20_test",
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
                "event_direction": "UP",
                "event_status": "ACTIVE",
            }
        ],
        signal_observations=[] if with_empty_events else [
            {
                "entity_code": "NVDA",
                "signal_name": "RESET_FRESHNESS",
                "signal_family": "FRESHNESS",
                "signal_direction": "UP",
                "signal_value": "FRESH",
                "observed_date": "2026-05-30",
                "relevance_labels": "CONTEXTUAL",
            }
        ],
        metadata={
            "used_v2_runtime_tables": False,
            "used_generated_reports": False,
            "used_dashboard_output": False,
            "rolling5_classification_source": "eco_classification_decision",
            "rolling5_snapshot_classification_source_used": False,
            "rolling5_event_window_mode": "event_date_range_within_5d_window",
            "ranking_fields_mostly_null": True,
            "coverage_without_classification_tickers": ["CRGY"],
            "signal_names_present": ["RESET_FRESHNESS"],
            "limitations": [
                "generated Markdown/CSV reports were not used as source data",
                "dashboard-rendered output was not used as source data",
                "rolling5 classifications are read from eco_classification_decision",
                "eco_entity_window_snapshot.classification_state is not the primary rolling5 classification source",
                "ranking fields are mostly NULL; deterministic fallback ordering is used",
                "rolling5 signal observations are limited to rolling5-compatible observations; daily candlestick/divergence semantics are not invented",
                "coverage or snapshot rows can exist without rolling5 classification rows, for example CRGY-like cases",
                "rolling5_event_window_mode refers to a 5d event-date range, not 30d",
                "no V2 report/context tables were used",
            ],
        },
    )


def test_renderer_returns_deterministic_rolling5_markdown_from_query_data_only() -> None:
    query_data = _sample_query_data()

    markdown = render_rolling5_markdown_report(query_data)

    assert isinstance(markdown, str)
    assert "# Datacenter Rolling Swing Report" in markdown
    assert "## 1. Title and run metadata" in markdown
    assert "## 2. Window summary" in markdown
    assert "requested_end_date" in markdown
    assert "valid_signal_dates_included" in markdown
    assert "2026-05-26, 2026-05-29, 2026-05-30" in markdown
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
    assert "return_5d" in markdown
    assert "group_overheat_risk_level" in markdown
    assert "No ecosystem window change rows available from current V3 query data." not in markdown
    assert "## 4. Ecosystem window change\nNot available from current V3 query data in DB-V3-70." not in markdown
    assert "## 5. Overheat / rotation risk progression" in markdown
    assert "## 6. Subindustry timing persistence" in markdown
    assert "## 7. Subindustry improvement / deterioration" in markdown
    assert "Not available from current V3 query data in DB-V3-70." in markdown
    assert "## 8. Repeated breakout tickers" in markdown
    assert "## 9. Repeated pullback tickers" in markdown
    assert "## 10. Repeated exit-risk tickers" in markdown
    assert "## Rolling 5 Pullback Alerts" in markdown
    assert "## 15. Data quality over the window" in markdown
    assert "## 16. Missing / incomplete inputs summary" in markdown
    assert "## V3 metadata / limitations appendix" in markdown
    assert "## Metadata" not in markdown
    assert "## Quality and coverage" not in markdown
    assert "## Ecosystem snapshot" not in markdown
    assert "## Group overview" not in markdown
    assert "run-5" in markdown
    assert "WATCHLIST_ONLY" in markdown
    assert "rolling5_classification_source: eco_classification_decision" in markdown
    assert "rolling5_snapshot_classification_source_used: False" in markdown
    assert "rolling5_event_window_mode: event_date_range_within_5d_window" in markdown
    assert "generated Markdown/CSV reports were not used as source data" in markdown
    assert "eco_entity_window_snapshot.classification_state is not the primary rolling5 classification source" in markdown
    assert "ranking_fields_mostly_null: True" in markdown
    assert "No such table" not in markdown
    assert "PULLBACK\\|ABOVE_EMA20" in markdown
    assert "AI\\|SEMIS" in markdown
    assert markdown.index("## Watchlist Summary") < markdown.index("## Rolling 5 Pullback Alerts")
    assert markdown.index("## V3 metadata / limitations appendix") > markdown.index("## 16. Missing / incomplete inputs summary")


def test_renderer_handles_empty_rolling5_events_and_signals_gracefully() -> None:
    query_data = _sample_query_data(with_empty_events=True)

    markdown = render_rolling5_markdown_report(query_data)

    assert "- No structural event rows." in markdown
    assert "- rolling5-compatible signal observations only: none" in markdown
    assert "- No signal observation rows." in markdown
