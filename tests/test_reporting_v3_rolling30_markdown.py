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
    assert "# Datacenter rolling30 report prototype" in markdown
    assert "## Metadata" in markdown
    assert "## Quality and coverage" in markdown
    assert "## Ecosystem snapshot" in markdown
    assert "## Group overview" in markdown
    assert "## Rolling30 buy classifications" in markdown
    assert "## Rolling30 exit classifications" in markdown
    assert "## Watchlist" in markdown
    assert "## Ticker metrics" in markdown
    assert "## Group metrics" in markdown
    assert "## Events and signals" in markdown
    assert "## Metadata and limitations" in markdown
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


def test_renderer_handles_empty_events_and_signals_gracefully() -> None:
    query_data = _sample_query_data(with_empty_events=True)

    markdown = render_rolling30_markdown_report(query_data)

    assert "- No structural event rows." in markdown
    assert "- rolling30-compatible signal observations only: none" in markdown
    assert "- No signal observation rows." in markdown
