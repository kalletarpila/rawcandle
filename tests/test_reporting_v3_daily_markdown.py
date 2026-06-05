from rawcandle.reporting_v3_markdown import render_daily_markdown_report
from rawcandle.reporting_v3_query import DailyReportQueryData, Rolling30ReportHeader


def _sample_query_data(*, with_empty_events: bool = False) -> DailyReportQueryData:
    return DailyReportQueryData(
        report_header=Rolling30ReportHeader(
            run_id="run-daily",
            ecosystem_code="DATACENTER",
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            signal_date="2026-05-30",
            window_code="daily",
        ),
        watchlist_summary={
            "counts": {
                "active_watchlist_count": 2,
                "in_ecosystem_count": 2,
                "missing_price_data_count": 0,
                "breakout_count": 1,
                "pullback_count": 0,
                "exit_risk_count": 1,
                "high_exit_risk_count": 1,
                "medium_exit_risk_count": 0,
            },
            "rows": [
                {
                    "ticker": "NXPI",
                    "watchlist_status": "HIGH_EXIT_RISK",
                    "in_datacenter_ecosystem": True,
                    "primary_layer": "INFRA",
                    "primary_subindustry": "SEMIS",
                    "close": None,
                    "return_5d": 1.0,
                    "return_10d": 2.0,
                    "return_20d": 3.0,
                    "distance_to_ema20_pct": -0.5,
                    "ticker_trend_state": "DOWN",
                    "breakout_signal": False,
                    "pullback_signal": None,
                    "exit_risk_signal": True,
                    "exit_risk_severity": "HIGH",
                    "exit_reason": "BEARISH_DAILY_SIGNAL",
                    "subindustry_timing_state": None,
                    "subindustry_overheat_risk_level": None,
                    "layer_timing_state": "BUY_ZONE",
                    "layer_overheat_risk_level": "LOW",
                    "price_data_status": "OK",
                },
                {
                    "ticker": "NVDA",
                    "watchlist_status": "BREAKOUT",
                    "in_datacenter_ecosystem": True,
                    "primary_layer": "INFRA",
                    "primary_subindustry": "SEMIS",
                    "close": None,
                    "return_5d": 4.0,
                    "return_10d": 6.0,
                    "return_20d": 8.0,
                    "distance_to_ema20_pct": 1.5,
                    "ticker_trend_state": "UP",
                    "breakout_signal": True,
                    "pullback_signal": None,
                    "exit_risk_signal": False,
                    "exit_risk_severity": None,
                    "exit_reason": None,
                    "subindustry_timing_state": None,
                    "subindustry_overheat_risk_level": None,
                    "layer_timing_state": "BUY_ZONE",
                    "layer_overheat_risk_level": "LOW",
                    "price_data_status": "OK",
                },
            ],
        },
        quality_summary={
            "rows": [
                {
                    "window_code": "daily",
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
                {"entity_type": "TICKER", "coverage_status": "OK", "row_count": 2},
                {"entity_type": "TICKER", "coverage_status": "WATCHLIST_ONLY", "row_count": 1},
            ],
        },
        ecosystem_snapshot={
            "entity_code": "DATACENTER",
            "snapshot_status": "WARN",
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
                "timing_state": "EXIT_WATCH",
                "trend_state": "DOWN",
                "summary_state": "MIXED",
                "freshness_status": "AGING",
                "quality_status": "WARN",
            },
        ],
        ticker_snapshots=[
            {"entity_type": "TICKER", "entity_code": "CRGY", "classification_state": "WRONG_FROM_SNAPSHOT"},
            {"entity_type": "TICKER", "entity_code": "NVDA", "classification_state": "WRONG_FROM_SNAPSHOT"},
            {"entity_type": "TICKER", "entity_code": "NXPI", "classification_state": "WRONG_FROM_SNAPSHOT"},
        ],
        daily_trigger_classifications=[
            {
                "ticker": "NVDA",
                "classification_state": "BUY_WATCH",
                "primary_reason": "BULLISH|SETUP",
                "blocking_reason": None,
                "risk_reason": None,
                "next_action": "MONITOR_FOR_DAILY_CONFIRMATION",
                "decision_status": "OK",
                "priority_score": None,
                "priority_label": None,
                "sort_rank": None,
            },
            {
                "ticker": "NXPI",
                "classification_state": "SELL_TRIGGER",
                "primary_reason": "DAILY_SELL_TRIGGER",
                "blocking_reason": "BEARISH_DAILY_SIGNAL",
                "risk_reason": None,
                "next_action": "REVIEW_SELL_OR_TIGHTEN_STOP",
                "decision_status": "OK",
                "priority_score": None,
                "priority_label": None,
                "sort_rank": None,
            },
            {
                "ticker": "CRGY",
                "classification_state": "INSUFFICIENT_DATA",
                "primary_reason": "MISSING_PRICE_CONTEXT",
                "blocking_reason": None,
                "risk_reason": None,
                "next_action": "WAIT_FOR_DATA",
                "decision_status": "OK",
                "priority_score": None,
                "priority_label": None,
                "sort_rank": None,
            },
        ],
        ticker_metrics={
            "NVDA": {
                "ticker": "NVDA",
                "entity_name": "NVIDIA",
                "distance_to_ema10_pct": 1.0,
                "distance_to_ema20_pct": 1.5,
                "return_5d": 4.0,
                "return_10d": 6.0,
                "return_20d": 8.0,
                "return_60d": 15.0,
                "latest_bos_age_trading_days": 2.0,
                "latest_reset_age_trading_days": 4.0,
                "latest_structure_age_trading_days": 6.0,
                "freshness_latest_bos_age_trading_days": 1.0,
                "freshness_latest_bos_class": "FRESH",
                "freshness_latest_reset_age_trading_days": 3.0,
                "freshness_latest_reset_class": "AGING",
                "freshness_latest_structure_age_trading_days": 5.0,
                "freshness_latest_structure_class": "STALE",
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
                "group_current_status": "BUY_ZONE",
                "group_timing_state": "BUY_ZONE",
                "group_timing_reason": "BUY_ZONE:return_5d_pos",
                "group_overheat_risk_level": "LOW",
                "freshness_latest_bos_age_trading_days": 1.0,
                "freshness_latest_bos_class": "FRESH",
                "freshness_latest_reset_age_trading_days": 2.0,
                "freshness_latest_reset_class": "AGING",
                "freshness_latest_structure_age_trading_days": 3.0,
                "freshness_latest_structure_class": "STALE",
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
                "entity_code": "NXPI",
                "event_date": "2026-05-30",
                "event_type": "STRUCTURE_CHANGE",
                "event_direction": "DOWN",
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
            },
            {
                "entity_code": "NXPI",
                "signal_name": "REVERSAL_MEDIUM",
                "signal_family": "REVERSAL_MEDIUM",
                "signal_direction": "DOWN",
                "signal_value": "BEARISH",
                "observed_date": "2026-05-30",
                "relevance_labels": "CONTEXTUAL",
            },
        ],
        metadata={
            "used_v2_runtime_tables": False,
            "used_generated_reports": False,
            "used_dashboard_output": False,
            "daily_classification_source": "eco_classification_decision",
            "daily_snapshot_classification_source_used": False,
            "daily_event_window_mode": "event_date_range_signal_day_only",
            "ranking_fields_mostly_null": True,
            "limitations": [
                "generated Markdown/CSV reports were not used as source data",
                "dashboard-rendered output was not used as source data",
                "daily classifications are read from eco_classification_decision",
                "eco_entity_window_snapshot.classification_state is not the primary daily classification source",
                "ranking fields are mostly NULL; deterministic fallback ordering is used",
                "daily signal observations come from eco_signal_observation and optional eco_signal_relevance",
                "CRGY is intentionally materialized as INSUFFICIENT_DATA in daily_trigger",
                "NXPI reflects accepted current lower-level source-truth SELL_TRIGGER semantics",
                "daily signal observations may include actual daily-observed technical signals; no signals are invented",
                "no V2 report/context tables were used",
            ],
        },
    )


def test_renderer_returns_deterministic_daily_markdown_from_query_data_only() -> None:
    query_data = _sample_query_data()

    markdown = render_daily_markdown_report(query_data)

    assert isinstance(markdown, str)
    expected_headings = [
        "# Datacenter Daily Swing Signal Report",
        "## 1. Title and run metadata",
        "## Watchlist Summary",
        "## 3. Dashboard",
        "## 4. Rotation Risk / Overheat Index",
        "## 5. Subindustry Timing States",
        "## 6. Buy-Zone Subindustries",
        "## 7. Add-On Pullback Subindustries",
        "## 8. Trim/Watch Subindustries",
        "## 9. Exit-Zone Subindustries",
        "## 10. Synthetic OHLC Structure Summary",
        "## 11. Group Structure Breaks / Resets",
        "## 12. Breakout Ticker Scanner",
        "## 13. Pullback Ticker Scanner",
        "## 14. Exit-Risk Ticker Scanner",
        "## 15. Daily Triggers",
        "## 16. Swing MA Break Status",
        "## 17. Swing Signal Freshness",
        "## 18. Data Quality",
        "## 19. Missing / Incomplete Inputs Summary",
        "## 20. Technical Relevance Context",
        "## V3 metadata / limitations appendix",
    ]
    heading_positions = [markdown.index(heading) for heading in expected_headings]
    assert heading_positions == sorted(heading_positions)
    assert "## Watchlist Summary" in markdown
    assert "active_watchlist_count" in markdown
    assert "watchlist_status" in markdown
    assert "primary_layer" in markdown
    assert "primary_subindustry" in markdown
    assert "distance_to_ema20_pct" in markdown
    assert "breakout_signal" in markdown
    assert "exit_risk_signal" in markdown
    assert "## Metadata" not in markdown
    assert "## Quality and coverage" not in markdown
    assert "## Ecosystem snapshot" not in markdown
    assert "## Group overview" not in markdown
    assert "## Daily trigger classifications" not in markdown
    assert "## Ticker metrics" not in markdown
    assert "## Group metrics" not in markdown
    assert "## Events and signals" not in markdown
    assert "## Accepted special cases" not in markdown
    assert "## Metadata and limitations" not in markdown
    assert "run-daily" in markdown
    assert "WATCHLIST_ONLY" in markdown
    assert "daily_classification_source: eco_classification_decision" in markdown
    assert "daily_snapshot_classification_source_used: False" in markdown
    assert "daily_event_window_mode: event_date_range_signal_day_only" in markdown
    assert "Full legacy dashboard aggregation is not available from current V3 query data in DB-V3-73b." in markdown
    assert "Current V3 query data provides combined quality and coverage summaries; a separate legacy missing-input read-model is not available in DB-V3-73b." in markdown
    assert "Not available from current V3 query data in DB-V3-73b." in markdown
    assert "generated Markdown/CSV reports were not used as source data" in markdown
    assert "eco_entity_window_snapshot.classification_state is not the primary daily classification source" in markdown
    assert "CRGY is intentionally materialized as INSUFFICIENT_DATA in daily_trigger" in markdown
    assert "NXPI reflects accepted current lower-level source-truth SELL_TRIGGER semantics" in markdown
    assert "ranking_fields_mostly_null: True" in markdown
    assert "No such table" not in markdown
    assert "BULLISH\\|SETUP" in markdown
    assert "AI\\|SEMIS" in markdown


def test_renderer_handles_empty_daily_events_and_signals_gracefully() -> None:
    query_data = _sample_query_data(with_empty_events=True)

    markdown = render_daily_markdown_report(query_data)

    assert "## 11. Group Structure Breaks / Resets" in markdown
    assert "## 16. Swing MA Break Status" in markdown
    assert "## 17. Swing Signal Freshness" in markdown
    assert "## 20. Technical Relevance Context" in markdown
    assert markdown.count("Not available from current V3 query data in DB-V3-73b.") >= 4
