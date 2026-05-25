from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import re
import sqlite3

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionBatchResult,
    DatacenterDecisionTrace,
    DatacenterTickerDecision,
)
from dev_tools.datacenter_dashboard_inspector import DatacenterTickerInspectorView
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardBatchParseResult,
    DatacenterDashboardReportParseSummary,
    DatacenterDashboardRow,
)
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    DatacenterReportStatus,
)
from dev_tools.ecosystem_dashboard_persistence import (
    connect_dashboard_db,
    ensure_dashboard_schema,
)
from dev_tools.run_datacenter_dashboard_html import (
    _format_value_with_age,
    _status_class_from_text,
    build_parser,
    generate_datacenter_dashboard_html_file,
    generate_dashboard_html,
    main,
)

_MARKET_MAP_HEADER_SNIPPETS = (
    "<th>Market level</th>",
    "<th>Name</th>",
    "<th>Layer</th>",
    "<th>Current status</th>",
    "<th>Start status 30d</th>",
    "<th>Status change 30d</th>",
    "<th>Status change 5d</th>",
    "<th>Window status 30d</th>",
    "<th>Window status 5d</th>",
    "<th>Window status 2d</th>",
    "<th>Overheat risk</th>",
    "<th>% above EMA20</th>",
    "<th>% above MA10</th>",
    "<th>EMA20 breadth delta 5d</th>",
    "<th>Return 5d</th>",
    "<th>Return 10d</th>",
    "<th>Return 20d</th>",
    "<th>Return 60d</th>",
    "<th>Dow trend state</th>",
    "<th>Latest structure</th>",
    "<th>Latest BOS</th>",
    "<th>Latest reset</th>",
    "<th>Latest relevant pattern</th>",
    "<th>Source horizons</th>",
    "<th>Source files</th>",
)


def _fake_dashboard_status(tmp_path: Path) -> DatacenterDashboardStatus:
    return DatacenterDashboardStatus(
        overall_status="READY",
        reports=[
            DatacenterReportStatus(
                horizon="rolling 30d",
                status="OK",
                path=str(tmp_path / "rolling30.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="rolling 5d",
                status="OK",
                path=str(tmp_path / "rolling5.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="rolling 2d",
                status="OK",
                path=str(tmp_path / "rolling2.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="daily",
                status="OK",
                path=str(tmp_path / "daily.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
        ],
    )


def _seed_dashboard_db(db_path: Path) -> str:
    conn = connect_dashboard_db(str(db_path))
    try:
        ensure_dashboard_schema(conn)
        run_id = "RUN_DB_HTML"
        conn.execute(
            """
            INSERT INTO ecosystem_dashboard_runs (
                run_id, ecosystem_code, report_date, taxonomy_version, generated_at_utc,
                reports_dir, selection_mode, readiness, found_reports, missing_reports,
                total_parsed_rows, total_parse_warnings, decision_total, market_map_rows,
                watchlist_rows, ticker_rows, source_reports_count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "DATACENTER",
                "2026-05-22",
                None,
                "2026-05-25T11:00:00Z",
                "/tmp/reports",
                "report_date",
                "READY",
                4,
                0,
                20,
                0,
                2,
                2,
                1,
                2,
                2,
                "2026-05-25T11:00:00Z",
            ),
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_source_reports (
                run_id, ecosystem_code, report_date, horizon, report_kind, markdown_path,
                csv_path, modified_at_utc, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id, "DATACENTER", "2026-05-22", "daily", "full",
                    "/tmp/daily.md", "/tmp/daily.csv", "2026-05-25T11:00:00Z",
                    "FOUND", "2026-05-25T11:00:00Z",
                ),
                (
                    run_id, "DATACENTER", "2026-05-22", "rolling_30d", "full",
                    "/tmp/r30.md", "/tmp/r30.csv", "2026-05-25T11:00:00Z",
                    "FOUND", "2026-05-25T11:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_action_summary (
                run_id, ecosystem_code, action, count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (run_id, "DATACENTER", "SELL", 1, "2026-05-25T11:00:00Z"),
                (run_id, "DATACENTER", "WATCH", 1, "2026-05-25T11:00:00Z"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_market_map (
                run_id, ecosystem_code, report_date, market_level, name, parent_name, layer,
                subindustry, taxonomy_path, taxonomy_version, current_status, start_status_30d,
                status_change_30d, status_change_5d, window_status_30d, window_status_5d,
                window_status_2d, overheat_risk, pct_above_ema20, pct_above_ma10,
                ema20_breadth_delta_5d, return_5d, return_10d, return_20d, return_60d,
                dow_trend_state, dow_trend_state_age_td, latest_structure_label,
                latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td,
                latest_divergence, latest_divergence_age_td, latest_chart_pattern,
                latest_chart_pattern_age_td, source_horizons, source_files, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id, "DATACENTER", "2026-05-22", "ECOSYSTEM", "DC_ECOSYSTEM_TOTAL", None,
                    None, None, None, None, "BUY_ZONE", "WATCH", "WATCH -> BUY_ZONE", "",
                    "BUY_ZONE", "", "", "LOW", 62.5, 58.0, 4.0, 0.12, 0.18, 0.25, 0.44,
                    "UP", 8, "HH", 3, "BOS_UP", 2, None, None, None, None, None, None,
                    "BASE_BREAKOUT", 5, "daily, rolling 30d", "daily.md, r30.md", "2026-05-25T11:00:00Z",
                ),
                (
                    run_id, "DATACENTER", "2026-05-22", "LAYER", "Compute", "Technology",
                    "Technology", None, None, None, "WATCH", "NEUTRAL", "NEUTRAL -> WATCH", "",
                    "WATCH", "", "", "LOW", 50.0, 40.0, 1.0, 0.05, 0.08, 0.10, 0.15,
                    "UP", 2, "HL", 1, "BOS_UP", 1, None, None, None, None, None, None,
                    "PULLBACK", 2, "rolling 30d", "r30.md", "2026-05-25T11:00:00Z",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO ecosystem_dashboard_watchlist_status (
                run_id, ecosystem_code, report_date, ticker, action, severity, primary_reason,
                current_status, start_status_30d, status_change_30d, status_change_5d,
                window_status_30d, window_status_5d, window_status_2d, ma_break_status,
                freshness_status, trend_state, trend_state_age_td, latest_structure_label,
                latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td,
                latest_divergence, latest_divergence_age_td, latest_chart_pattern,
                latest_chart_pattern_age_td, pullback_validity, entry_readiness,
                candidate_priority, candidate_priority_label, daily_status, rolling_2d_status,
                rolling_5d_status, rolling_30d_status, horizons_present, source_files,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, "DATACENTER", "2026-05-22", "NVDA", "SELL", "CRITICAL",
                "close_below_ema20", "BREAKOUT_READY", "WATCH", "WATCH -> BREAKOUT_READY",
                "", "WATCH", "", "", "EMA20_WARNING", "FRESH", "UP", 12, "HH", 3,
                "BOS_UP", 2, None, None, "Hammer", 4, "Bearish Divergence", 2,
                "BASE_BREAKOUT", 5, "NO_PULLBACK", "NOT_READY", 5, "P5_NOT_READY",
                "BREAKOUT_READY", None, None, "WATCH", "daily, rolling 30d", 2,
                "2026-05-25T11:00:00Z",
            ),
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_ticker_status (
                run_id, ecosystem_code, report_date, ticker, action, severity, primary_reason,
                current_status, start_status_30d, status_change_30d, status_change_5d,
                window_status_30d, window_status_5d, window_status_2d, ma_break_status,
                freshness_status, trend_state, trend_state_age_td, latest_structure_label,
                latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td,
                latest_divergence, latest_divergence_age_td, latest_chart_pattern,
                latest_chart_pattern_age_td, pullback_validity, entry_readiness,
                candidate_priority, candidate_priority_label, daily_status, rolling_2d_status,
                rolling_5d_status, rolling_30d_status, horizons_present, source_files,
                is_watchlist, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id, "DATACENTER", "2026-05-22", "NVDA", "SELL", "CRITICAL",
                    "close_below_ema20", "BREAKOUT_READY", "WATCH", "WATCH -> BREAKOUT_READY",
                    "", "WATCH", "", "", "EMA20_WARNING", "FRESH", "UP", 12, "HH", 3,
                    "BOS_UP", 2, None, None, "Hammer", 4, "Bearish Divergence", 2,
                    "BASE_BREAKOUT", 5, "NO_PULLBACK", "NOT_READY", 5, "P5_NOT_READY",
                    "BREAKOUT_READY", None, None, "WATCH", "daily, rolling 30d", 2, 1,
                    "2026-05-25T11:00:00Z",
                ),
                (
                    run_id, "DATACENTER", "2026-05-22", "AMD", "WATCH", "LOW", "trend_ok",
                    "BUY_ZONE", "WATCH", "WATCH -> BUY_ZONE", "", "BUY_ZONE", "", "", "OK",
                    "FRESH", "UP", 7, "HL", 2, "BOS_UP", 1, None, None, None, None, None,
                    None, "PULLBACK", 2, "VALID_PULLBACK", "READY_TO_WATCH", 1,
                    "P1_READY_TO_WATCH", None, None, None, "BUY_ZONE", "rolling 30d", 1, 0,
                    "2026-05-25T11:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_decision_trace (
                run_id, ecosystem_code, ticker, trace_index, action, matched_rule,
                matched_token, matched_value, horizon, field, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id, "DATACENTER", "NVDA", 0, "SELL", "SELL_HARD_TOKEN",
                    "close_below_ema20", "close_below_ema20", "daily", "reason",
                    "2026-05-25T11:00:00Z",
                ),
                (
                    run_id, "DATACENTER", "AMD", 0, "WATCH", "WATCH_RULE",
                    "trend_ok", "trend_ok", "rolling 30d", "status",
                    "2026-05-25T11:00:00Z",
                ),
            ],
        )
        conn.commit()
        return run_id
    finally:
        conn.close()


def _fake_parse_batch(tmp_path: Path) -> DatacenterDashboardBatchParseResult:
    return DatacenterDashboardBatchParseResult(
        reports=[
            DatacenterDashboardReportParseSummary(
                horizon="rolling 30d",
                source_file=str(tmp_path / "rolling30.csv"),
                row_count=1,
                warning_count=0,
            ),
            DatacenterDashboardReportParseSummary(
                horizon="rolling 5d",
                source_file=str(tmp_path / "rolling5.csv"),
                row_count=1,
                warning_count=0,
            ),
            DatacenterDashboardReportParseSummary(
                horizon="rolling 2d",
                source_file=str(tmp_path / "rolling2.csv"),
                row_count=1,
                warning_count=0,
            ),
            DatacenterDashboardReportParseSummary(
                horizon="daily",
                source_file=str(tmp_path / "daily.csv"),
                row_count=2,
                warning_count=1,
            ),
        ],
        total_row_count=5,
        total_warning_count=1,
    )


def _fake_rows(path: str, horizon: str) -> list[DatacenterDashboardRow]:
    if horizon == "daily":
        return [
            DatacenterDashboardRow(
                ticker="MS&FT",
                horizon=horizon,
                source_file=path,
                section="Watchlist Summary",
                row_kind="watchlist",
                raw_action=None,
                raw_status=None,
                reason=None,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status="OK",
                ema20_break_confirmed=0,
                sma50_break_confirmed=0,
                close_below_ema20=0,
                close_below_sma50=0,
                consecutive_closes_below_ema20=0,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=0.0,
                sma50_break_pct=0.0,
                freshness_status="FRESH_BULLISH_SIGNAL",
                structure_warning_overrides_bullish_signal=0,
                latest_bullish_signal_age_td=1,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=1,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={
                    "watchlist_status": "BREAKOUT_READY",
                    "trend_state_age_td": "12",
                    "latest_structure_age_td": "3",
                    "start_status_30d": "WATCH",
                    "status_change_30d": "WATCH -> BREAKOUT_READY",
                    "status_change_5d": "PULLBACK_WINDOW -> BREAKOUT_READY",
                },
            ),
            DatacenterDashboardRow(
                ticker="MS&FT",
                horizon=horizon,
                source_file=path,
                section="signals",
                row_kind="row",
                raw_action=None,
                raw_status="BULLISH",
                reason="fresh <entry> & follow-through",
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status="OK",
                ema20_break_confirmed=0,
                sma50_break_confirmed=0,
                close_below_ema20=0,
                close_below_sma50=0,
                consecutive_closes_below_ema20=0,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=0.0,
                sma50_break_pct=0.0,
                freshness_status="FRESH_BULLISH_SIGNAL",
                structure_warning_overrides_bullish_signal=0,
                latest_bullish_signal_age_td=1,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=1,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={
                    "latest_bullish_candle": "Hammer",
                    "bullish_candle_age_td": "4",
                    "latest_bearish_divergence": "Bearish Divergence",
                    "bearish_divergence_age_td": "2",
                    "latest_bullish_relevance_signal_name": "Hammer",
                    "latest_bearish_relevance_signal_name": "Bearish Divergence",
                    "latest_chart_pattern": "BASE_BREAKOUT",
                    "latest_chart_pattern_age_td": "5",
                },
            ),
            DatacenterDashboardRow(
                ticker="NV<DA>",
                horizon=horizon,
                source_file=path,
                section="Watchlist Summary",
                row_kind="watchlist",
                raw_action=None,
                raw_status=None,
                reason=None,
                trend_state="DOWN",
                latest_structure_label="LL",
                latest_bos_event_type="BOS_DOWN",
                latest_reset_reason="DOUBLE_BOS_DOWN",
                distance_to_ema20=None,
                high_exit_risk_days_count=2,
                blocking_reasons=None,
                ma_break_status="EMA20_CONFIRMED_BREAK",
                ema20_break_confirmed=1,
                sma50_break_confirmed=0,
                close_below_ema20=1,
                close_below_sma50=0,
                consecutive_closes_below_ema20=3,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=-0.02,
                sma50_break_pct=0.0,
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
                structure_warning_overrides_bullish_signal=1,
                latest_bullish_signal_age_td=None,
                latest_bearish_signal_age_td=0,
                latest_bos_up_age_td=None,
                latest_bos_down_age_td=1,
                latest_reset_age_td=1,
                raw_fields={"watchlist_status": "EXIT_RISK"},
            ),
            DatacenterDashboardRow(
                ticker="NV<DA>",
                horizon=horizon,
                source_file=path,
                section="signals",
                row_kind="row",
                raw_action=None,
                raw_status="SELL",
                reason="close_below_ema20 & risk",
                trend_state="DOWN",
                latest_structure_label="LL",
                latest_bos_event_type="BOS_DOWN",
                latest_reset_reason="RESET",
                distance_to_ema20=None,
                high_exit_risk_days_count=2,
                blocking_reasons=None,
                ma_break_status="EMA20_CONFIRMED_BREAK",
                ema20_break_confirmed=1,
                sma50_break_confirmed=0,
                close_below_ema20=1,
                close_below_sma50=0,
                consecutive_closes_below_ema20=3,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=-0.02,
                sma50_break_pct=0.0,
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
                structure_warning_overrides_bullish_signal=1,
                latest_bullish_signal_age_td=None,
                latest_bearish_signal_age_td=0,
                latest_bos_up_age_td=None,
                latest_bos_down_age_td=0,
                latest_reset_age_td=0,
                raw_fields={},
            ),
        ]
    if horizon == "rolling 5d":
        return [
            DatacenterDashboardRow(
                ticker="AMD",
                horizon=horizon,
                source_file=path,
                section="Watchlist Summary",
                row_kind="watchlist",
                raw_action=None,
                raw_status=None,
                reason=None,
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="FAILED_BREAKOUT",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status="EMA20_WARNING",
                ema20_break_confirmed=0,
                sma50_break_confirmed=0,
                close_below_ema20=0,
                close_below_sma50=0,
                consecutive_closes_below_ema20=0,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=0.0,
                sma50_break_pct=0.0,
                freshness_status="FRESH_BULLISH_SIGNAL",
                structure_warning_overrides_bullish_signal=0,
                latest_bullish_signal_age_td=3,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=2,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={
                    "current_watchlist_status": "PULLBACK_MONITOR",
                    "window_watchlist_status": "PULLBACK_WINDOW",
                    "first_current_watchlist_status": "NEUTRAL",
                    "status_change_5d": "NEUTRAL -> PULLBACK_MONITOR",
                },
            ),
            DatacenterDashboardRow(
                ticker="AMD",
                horizon=horizon,
                source_file=path,
                section="signals",
                row_kind="row",
                raw_action=None,
                raw_status="PULLBACK_CANDIDATE",
                reason="monitor",
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status="EMA20_WARNING",
                ema20_break_confirmed=0,
                sma50_break_confirmed=0,
                close_below_ema20=0,
                close_below_sma50=0,
                consecutive_closes_below_ema20=0,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=0.0,
                sma50_break_pct=0.0,
                freshness_status="FRESH_BULLISH_SIGNAL",
                structure_warning_overrides_bullish_signal=0,
                latest_bullish_signal_age_td=3,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=2,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={
                    "latest_bearish_candle": "SHOOTING_STAR",
                    "bearish_candle_age_td": "2",
                    "latest_bullish_candle": "HAMMER",
                    "bullish_candle_age_td": "2",
                    "latest_hidden_bullish_divergence": "HIDDEN_BULLISH_DIVERGENCE",
                    "hidden_bullish_divergence_age_td": "1",
                    "latest_bearish_divergence": "BEARISH_DIVERGENCE",
                    "bearish_divergence_age_td": "1",
                    "chart_pattern": "ASCENDING_TRIANGLE",
                    "chart_pattern_age_td": "6",
                },
            ),
        ]
    if horizon == "rolling 30d":
        return [
            DatacenterDashboardRow(
                ticker="MS&FT",
                horizon=horizon,
                source_file=path,
                section="context",
                row_kind="row",
                raw_action=None,
                raw_status="BUY_ZONE",
                reason="leader",
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status=None,
                ema20_break_confirmed=None,
                sma50_break_confirmed=None,
                close_below_ema20=None,
                close_below_sma50=None,
                consecutive_closes_below_ema20=None,
                consecutive_closes_below_sma50=None,
                ema20_break_pct=None,
                sma50_break_pct=None,
                freshness_status=None,
                structure_warning_overrides_bullish_signal=None,
                latest_bullish_signal_age_td=None,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=None,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={},
            ),
        ]
    return []


def _fake_decision_result(tmp_path: Path) -> DatacenterDecisionBatchResult:
    return DatacenterDecisionBatchResult(
        decisions=[
            DatacenterTickerDecision(
                ticker="MS&FT",
                action="WATCH",
                severity="LOW",
                primary_reason="VALID_PULLBACK_WAIT_FOR_ENTRY_CONFIRMATION",
                reasons=[],
                blocking_reasons=[],
                horizons_present=["daily", "rolling 30d"],
                horizon_statuses={"daily": "BULLISH", "rolling 30d": "BUY_ZONE"},
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                latest_bullish_signal_age_td=1,
                latest_bearish_signal_age_td=None,
                pullback_validity="VALID_PULLBACK",
                pullback_reason="FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK",
                entry_readiness="READY_TO_WATCH",
                entry_readiness_reason="VALID_PULLBACK_NO_STRONG_RISK_ACTION",
                candidate_priority=1,
                candidate_priority_label="P1_READY_TO_WATCH",
                candidate_priority_reason="READY_TO_WATCH",
                source_files=[
                    str(tmp_path / "daily.csv"),
                    str(tmp_path / "rolling30.csv"),
                ],
                decision_trace=[
                    DatacenterDecisionTrace(
                        ticker="MS&FT",
                        action="WATCH",
                        matched_rule="WATCH_VALID_PULLBACK",
                        horizon=None,
                        field_name=None,
                        matched_token="VALID_PULLBACK",
                        matched_value="FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK",
                        source_file=None,
                        section=None,
                        row_kind=None,
                    )
                ],
            ),
            DatacenterTickerDecision(
                ticker="AMD",
                action="WATCH",
                severity="LOW",
                primary_reason="EARLY_PULLBACK_MONITOR",
                reasons=[],
                blocking_reasons=[],
                horizons_present=["rolling 5d"],
                horizon_statuses={"rolling 5d": "PULLBACK_CANDIDATE"},
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                latest_bullish_signal_age_td=3,
                latest_bearish_signal_age_td=None,
                pullback_validity="EARLY_PULLBACK",
                pullback_reason="WAIT_FOR_BULLISH_CONFIRMATION",
                entry_readiness="EARLY_MONITOR",
                entry_readiness_reason="WAIT_FOR_BULLISH_CONFIRMATION",
                candidate_priority=4,
                candidate_priority_label="P4_EARLY_MONITOR",
                candidate_priority_reason="EARLY_PULLBACK_WAIT_FOR_CONFIRMATION",
                source_files=[str(tmp_path / "rolling5.csv")],
                decision_trace=[
                    DatacenterDecisionTrace(
                        ticker="AMD",
                        action="WATCH",
                        matched_rule="WATCH_EARLY_PULLBACK",
                        horizon=None,
                        field_name=None,
                        matched_token="EARLY_PULLBACK",
                        matched_value="WAIT_FOR_BULLISH_CONFIRMATION",
                        source_file=None,
                        section=None,
                        row_kind=None,
                    )
                ],
            ),
            DatacenterTickerDecision(
                ticker="NV<DA>",
                action="SELL",
                severity="CRITICAL",
                primary_reason="SELL_SIGNAL_DETECTED",
                reasons=[],
                blocking_reasons=[],
                horizons_present=["daily"],
                horizon_statuses={"daily": "SELL"},
                distance_to_ema20=None,
                high_exit_risk_days_count=2,
                trend_state="DOWN",
                latest_structure_label="LL",
                latest_bos_event_type="BOS_DOWN",
                latest_reset_reason="RESET",
                latest_bullish_signal_age_td=None,
                latest_bearish_signal_age_td=0,
                pullback_validity="STRUCTURE_BLOCKED_PULLBACK",
                pullback_reason="ACUTE_BOS_DOWN_SELL_CONFIRMATION_BLOCKS_PULLBACK",
                entry_readiness="NOT_READY",
                entry_readiness_reason="STRUCTURE_BLOCKED_PULLBACK",
                candidate_priority=5,
                candidate_priority_label="P5_NOT_READY",
                candidate_priority_reason="NOT_READY",
                source_files=[str(tmp_path / "daily.csv")],
                decision_trace=[
                    DatacenterDecisionTrace(
                        ticker="NV<DA>",
                        action="SELL",
                        matched_rule="SELL_EMA20_CONFIRMED_BREAK",
                        horizon="daily",
                        field_name="ma_break_status",
                        matched_token="EMA20_CONFIRMED_BREAK",
                        matched_value="EMA20_CONFIRMED_BREAK",
                        source_file=str(tmp_path / "daily.csv"),
                        section="signals",
                        row_kind="row",
                    )
                ],
            ),
        ],
        action_counts={
            "SELL": 1,
            "REDUCE": 0,
            "TIGHTEN_STOP": 0,
            "BLOCKED": 0,
            "WAIT_PULLBACK": 0,
            "BUY_NOW": 0,
            "WATCH": 2,
            "NEUTRAL": 0,
        },
        pullback_counts={
            "VALID_PULLBACK": 1,
            "EARLY_PULLBACK": 1,
            "STRUCTURE_BLOCKED_PULLBACK": 1,
            "BREAKDOWN_NOT_PULLBACK": 0,
            "NO_PULLBACK": 0,
            "INSUFFICIENT_DATA": 0,
        },
        pullback_action_counts={
            key: {
                action: 0
                for action in (
                    "SELL",
                    "REDUCE",
                    "TIGHTEN_STOP",
                    "BLOCKED",
                    "WAIT_PULLBACK",
                    "BUY_NOW",
                    "WATCH",
                    "NEUTRAL",
                )
            }
            for key in (
                "VALID_PULLBACK",
                "EARLY_PULLBACK",
                "STRUCTURE_BLOCKED_PULLBACK",
                "BREAKDOWN_NOT_PULLBACK",
                "NO_PULLBACK",
                "INSUFFICIENT_DATA",
            )
        },
        entry_readiness_counts={
            "READY_TO_WATCH": 1,
            "NEEDS_STOP_STABILIZATION": 0,
            "NEEDS_RISK_CLEARANCE": 0,
            "EARLY_MONITOR": 1,
            "NOT_READY": 1,
            "INSUFFICIENT_DATA": 0,
        },
        candidate_priority_counts={
            "P1_READY_TO_WATCH": 1,
            "P2_STOP_STABILIZATION": 0,
            "P3_RISK_CLEARANCE": 0,
            "P4_EARLY_MONITOR": 1,
            "P5_NOT_READY": 1,
            "P9_NOT_CANDIDATE": 0,
        },
        warning_count=0,
        warnings=[],
    )


def _fake_decision_result_with_action(
    tmp_path: Path,
    *,
    ticker: str,
    action: str,
    severity: str,
) -> DatacenterDecisionBatchResult:
    base_result = _fake_decision_result(tmp_path)
    decision = next(item for item in base_result.decisions if item.ticker == ticker)
    updated_decision = replace(decision, action=action, severity=severity)
    return DatacenterDecisionBatchResult(
        decisions=[updated_decision],
        action_counts={
            "SELL": 1 if action == "SELL" else 0,
            "REDUCE": 1 if action == "REDUCE" else 0,
            "TIGHTEN_STOP": 1 if action == "TIGHTEN_STOP" else 0,
            "BLOCKED": 1 if action == "BLOCKED" else 0,
            "WAIT_PULLBACK": 1 if action == "WAIT_PULLBACK" else 0,
            "BUY_NOW": 1 if action == "BUY_NOW" else 0,
            "WATCH": 1 if action == "WATCH" else 0,
            "NEUTRAL": 1 if action == "NEUTRAL" else 0,
        },
        pullback_counts=base_result.pullback_counts,
        pullback_action_counts=base_result.pullback_action_counts,
        entry_readiness_counts=base_result.entry_readiness_counts,
        candidate_priority_counts=base_result.candidate_priority_counts,
        warning_count=0,
        warnings=[],
    )


def _fake_inspector_views() -> dict[str, DatacenterTickerInspectorView]:
    return {
        "MS&FT": DatacenterTickerInspectorView(
            ticker="MS&FT",
            action="WATCH",
            severity="LOW",
            primary_reason="VALID_PULLBACK_WAIT_FOR_ENTRY_CONFIRMATION",
            pullback_validity="VALID_PULLBACK",
            pullback_reason="FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK",
            supporting_signals=["BOS_UP", "leader"],
            conflicting_signals=[],
            override_explanation=None,
            conflict_detected=False,
        ),
        "AMD": DatacenterTickerInspectorView(
            ticker="AMD",
            action="WATCH",
            severity="LOW",
            primary_reason="EARLY_PULLBACK_MONITOR",
            pullback_validity="EARLY_PULLBACK",
            pullback_reason="WAIT_FOR_BULLISH_CONFIRMATION",
            supporting_signals=["PULLBACK_CANDIDATE"],
            conflicting_signals=[],
            override_explanation=None,
            conflict_detected=False,
        ),
        "NV<DA>": DatacenterTickerInspectorView(
            ticker="NV<DA>",
            action="SELL",
            severity="CRITICAL",
            primary_reason="SELL_SIGNAL_DETECTED",
            pullback_validity="STRUCTURE_BLOCKED_PULLBACK",
            pullback_reason="ACUTE_BOS_DOWN_SELL_CONFIRMATION_BLOCKS_PULLBACK",
            supporting_signals=["close_below_ema20", "risk & reset"],
            conflicting_signals=["PULLBACK_CANDIDATE"],
            override_explanation="Bearish <structure> overrides bullish.",
            conflict_detected=True,
        ),
    }


def _install_pipeline_mocks(
    monkeypatch,
    tmp_path: Path,
    *,
    layer_current_status: str = "WATCH",
    layer_start_status: str = "NEUTRAL",
    layer_window_status: str = "ADD_ON_PULLBACK",
    layer_overheat_status: str = "WATCH",
) -> None:
    (tmp_path / "daily.csv").write_text(
        f"""## 3. Dashboard
| metric | value |
| --- | --- |
| timing_state | BUY_ZONE |
| ecosystem_overheat_risk_level | NORMAL |
| ecosystem_pct_above_ema20 | 72 |
| ecosystem_pct_above_ma10 | 68 |
| ecosystem_ema20_breadth_delta_5d | 4 |
| ecosystem_return_5d | 2.1 |
| ecosystem_return_10d | 3.8 |
| ecosystem_return_20d | 8.4 |
| ecosystem_return_60d | 21.0 |
| trend_state | TRENDING_UP |
| trend_state_age_td | 2 |
| latest_structure_label | HH |
| latest_structure_age_td | 3 |
| latest_bos_event_type | BOS_UP |
| latest_bos_age_td | 1 |
| latest_reset_reason | RESET_COMPLETE |
| latest_reset_age_td | 1 |
| latest_bullish_divergence | BULL_DIV |
| bullish_divergence_age_td | 4 |
| latest_bearish_candle | SHOOTING_STAR |
| bearish_candle_age_td | 1 |

## 4. Rotation Risk / Overheat Index
| group_type | group_name | overheat_risk_level | pct_above_ema20 | ema20_breadth_delta_5d | return_10d | return_20d |
| --- | --- | --- | --- | --- | --- | --- |
| layer | Compute | WATCH | 75 | 5 | 4.0 | 9.0 |
| subindustry | AI Accelerators | HIGH | 81 | 7 | 5.5 | 11.0 |

## 5. Subindustry Timing States
| group_name | timing_state | pct_above_ema20 | ema20_breadth_delta_5d | return_5d | return_10d | return_20d | return_60d |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI Accelerators | BUY_ZONE | 79 | 6 | 2.4 | 4.8 | 10.2 | 25.0 |

## Datacenter Taxonomy Listing
| row_type | layer | subindustry | ticker | status | subindustry_context_risk | layer_context_risk | close | return_5d | return_10d | return_20d | distance_to_ema20_pct | trend_state | latest_structure_label | latest_structure_freshness | latest_bos_event_type | latest_bos_freshness | latest_reset_reason | latest_reset_freshness | breakout_signal | pullback_signal | exit_risk_signal | exit_risk_severity | exit_reason | price_data_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER | Compute |  |  | {layer_current_status} | NORMAL | {layer_overheat_status} |  | 2.3 | 4.1 | 9.2 |  | UP | HL | fresh | BOS_UP | fresh |  |  |  |  |  |  |  | OK |
| SUBINDUSTRY | Compute | AI Accelerators |  | BUY_ZONE | HIGH | WATCH |  | 2.7 | 5.0 | 10.8 |  | UP | HH | fresh | BOS_UP | fresh |  |  |  |  |  |  |  | OK |
""",
        encoding="utf-8",
    )
    rolling_fixture = f"""## 4. Ecosystem window change
| metric | first_value | last_value | change |
| --- | --- | --- | --- |
| timing_state | WATCH | BUY_ZONE | BUY_ZONE |
| overheat_risk_level | NORMAL | WATCH | WATCH |
| pct_above_ema20 | 66 | 74 | 8 |
| pct_above_ma10 | 62 | 70 | 8 |
| ema20_breadth_delta_5d | 1 | 5 | 4 |
| return_5d | 1.1 | 2.8 | 1.7 |
| return_10d | 2.0 | 4.2 | 2.2 |
| return_20d | 4.4 | 9.1 | 4.7 |
| latest_chart_pattern | ASCENDING_TRIANGLE | ASCENDING_TRIANGLE |  |
| chart_pattern_age_td | 7 | 7 | 0 |

## 6. Group Structure Timing
| group_type | group_name | latest_bos_event_type | latest_bos_event_date | latest_bos_age_trading_days | latest_bos_freshness | latest_reset_reason | latest_reset_event_date | latest_reset_age_trading_days | latest_reset_freshness | latest_structure_label | latest_structure_age_trading_days | latest_structure_freshness | trend_classification | timing_state | overheat_risk_level |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| layer | Compute | BOS_UP | 2026-05-22 | 1 | fresh |  |  |  |  | HH | 3 | fresh | TRENDING_UP | {layer_current_status} | {layer_overheat_status} |
| subindustry | AI Accelerators | BOS_UP | 2026-05-22 | 1 | fresh |  |  |  |  | HH | 3 | fresh | TRENDING_UP | BUY_ZONE | HIGH |

## 7. Group Window Status Change
| group_type | group_name | first_timing_state | last_timing_state |
| --- | --- | --- | --- |
| layer | Compute | {layer_start_status} | {layer_current_status} |
| subindustry | AI Accelerators | NEUTRAL | BUY_ZONE |

## Datacenter Taxonomy Listing
| row_type | layer | subindustry | ticker | current_status | start_status | status_change | window_status | subindustry_context_risk | layer_context_risk | last_close | breakout_days | pullback_days | exit_risk_days | high_exit_risk_days | medium_exit_risk_days | last_exit_risk_severity | last_exit_reason | last_trend_state | last_trend_state_age_td | last_latest_structure_label | last_latest_structure_age_trading_days | last_latest_structure_freshness | last_latest_bos_event_type | last_latest_bos_age_trading_days | last_latest_bos_freshness | last_latest_reset_reason | last_latest_reset_age_trading_days | last_latest_reset_freshness | last_price_data_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER | Compute |  |  | {layer_current_status} | {layer_start_status} | {layer_start_status} -> {layer_current_status} | {layer_window_status} | NORMAL | {layer_overheat_status} |  | 0 | 2 | 0 | 0 | 0 |  |  | UP | 2 | HH | 3 | fresh | BOS_UP | 1 | fresh |  |  |  | OK |
| SUBINDUSTRY | Compute | AI Accelerators |  | BUY_ZONE | NEUTRAL | NEUTRAL -> BUY_ZONE | WATCH | HIGH | WATCH |  | 1 | 1 | 0 | 0 | 0 |  |  | UP | 2 | HH | 3 | fresh | BOS_UP | 1 | fresh |  |  |  | OK |
"""
    for name in ("rolling2.csv", "rolling5.csv", "rolling30.csv"):
        (tmp_path / name).write_text(rolling_fixture, encoding="utf-8")

    decision_result = _fake_decision_result(tmp_path)
    inspector_views = _fake_inspector_views()
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.discover_datacenter_dashboard_status",
        lambda reports_dir, report_date=None: _fake_dashboard_status(tmp_path),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.parse_datacenter_dashboard_reports",
        lambda reports: _fake_parse_batch(tmp_path),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.parse_datacenter_dashboard_file",
        lambda path, horizon: type(
            "ParseResult", (), {"rows": _fake_rows(path, horizon)}
        )(),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.build_datacenter_ticker_decisions",
        lambda rows: decision_result,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.build_datacenter_ticker_inspector_view",
        lambda decision, rows: inspector_views[decision.ticker],
    )


def test_build_parser_accepts_dashboard_db_mode_args():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--dashboard-db",
            "/tmp/dashboard.db",
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
        ]
    )
    assert args.dashboard_db == "/tmp/dashboard.db"
    assert args.reports_dir is None


def test_generate_dashboard_html_is_deterministic_and_escapes_values(
    tmp_path, monkeypatch
):
    _install_pipeline_mocks(monkeypatch, tmp_path)

    html_one, _status_one, _parse_one, _decisions_one = generate_dashboard_html(
        reports_dir=str(tmp_path),
        title="Custom <Dashboard>",
        ticker="MS&FT",
        report_date=None,
        max_command_rows=10,
        max_candidate_rows=10,
        generated_at_utc="2026-05-25T00:00:00+00:00",
    )
    html_two, _status_two, _parse_two, _decisions_two = generate_dashboard_html(
        reports_dir=str(tmp_path),
        title="Custom <Dashboard>",
        ticker="MS&FT",
        report_date=None,
        max_command_rows=10,
        max_candidate_rows=10,
        generated_at_utc="2026-05-25T00:00:00+00:00",
    )

    ecosystem_header = re.search(
        r'<section id="market-map-ecosystem".*?<thead><tr>(.*?)</tr></thead>',
        html_one,
        re.DOTALL,
    )
    assert ecosystem_header is not None
    for snippet in _MARKET_MAP_HEADER_SNIPPETS:
        assert snippet in ecosystem_header.group(1)
    assert 'class="sticky-table market-map-table"' in html_one
    assert "<colgroup>" in html_one
    assert ".market-map-table {" in html_one

    assert html_one == html_two
    assert "Custom &lt;Dashboard&gt;" in html_one
    assert "MS&amp;FT" in html_one
    assert "NV&lt;DA&gt;" in html_one
    assert "Bearish &lt;structure&gt; overrides bullish." in html_one
    assert ".page-header {" in html_one
    assert 'class="page-header"' in html_one
    assert "selected_report_date" in html_one
    assert "selection_mode" in html_one
    assert "newest" in html_one
    assert 'id="summary"' in html_one
    assert 'id="market-map-ecosystem"' in html_one
    assert 'id="market-map-layers-subindustries"' in html_one
    assert 'id="watchlist-status"' in html_one
    assert 'id="candidate-pullbacks"' in html_one
    assert 'id="command-center"' in html_one
    assert 'id="inspector"' in html_one
    assert 'id="source-files"' in html_one
    assert "Ecosystem Summary" in html_one
    assert "Layers and Subindustries" in html_one
    assert "Compute" in html_one
    assert "AI Accelerators" in html_one
    assert "ADD_ON_PULLBACK" in html_one
    assert "Current status" in html_one
    assert "Start status 30d" in html_one
    assert "Status change 30d" in html_one
    assert "Status change 5d" in html_one
    assert "Window status 30d" in html_one
    assert "Window status 5d" in html_one
    assert "Window status 2d" in html_one
    assert "Dow trend state" in html_one
    assert "Latest relevant pattern" in html_one
    assert "Pattern age td" not in html_one
    assert "Latest structure" in html_one
    assert "Latest BOS" in html_one
    assert "Latest reset" in html_one
    assert "Source horizons" in html_one
    assert "Source files" in html_one
    assert 'class="market-layer-detail' in html_one
    assert "WATCH -&gt; BUY_ZONE" in html_one
    assert "NEUTRAL -&gt; WATCH" in html_one
    assert "72.00%" in html_one
    assert "68.00%" in html_one
    assert "4.00%" in html_one
    assert "210.00%" in html_one
    assert "2100.00%" in html_one
    assert "TRENDING_UP (2)" in html_one
    assert "HH (3)" in html_one
    assert "BOS_UP (1)" in html_one
    assert "RESET_COMPLETE (1)" in html_one
    assert "SHOOTING_STAR (1)" in html_one
    assert "daily, rolling 2d, rolling 5d, rolling 30d" in html_one
    assert html_one.count("<td>DC_ECOSYSTEM_TOTAL</td>") == 1
    assert "<td>ECOSYSTEM</td>" in html_one
    assert "<td>-</td>" in html_one
    assert 'data-section="market-map"' in html_one
    assert ".risk-high {" in html_one
    assert ".risk-medium {" in html_one
    assert ".status-positive {" in html_one
    assert ".status-neutral {" in html_one
    assert html_one.index('id="market-map-ecosystem"') > html_one.index('id="summary"')
    assert html_one.index('id="market-map-ecosystem"') < html_one.index(
        'id="watchlist-status"'
    )
    assert html_one.index('id="market-map-layers-subindustries"') > html_one.index(
        'id="market-map-ecosystem"'
    )
    hierarchy_section = html_one[
        html_one.index('id="market-map-layers-subindustries"') : html_one.index(
            'id="watchlist-status"'
        )
    ]
    assert 'class="table-scroll market-map-hierarchy-scroll"' in hierarchy_section
    summary_match = re.search(
        r'<summary class="market-layer-summary ([^"]+)">(.*?)</summary>',
        hierarchy_section,
        re.DOTALL,
    )
    assert summary_match is not None
    summary_classes = summary_match.group(1).split()
    summary_html = summary_match.group(2)
    assert "<details" in hierarchy_section
    assert '<summary class="market-layer-summary risk-medium">' in hierarchy_section
    assert 'class="market-layer-detail risk-medium"' in hierarchy_section
    assert "risk-medium" in summary_classes
    assert 'class="table-scroll"><table class="sticky-table"' not in hierarchy_section
    assert 'class="sticky-table market-map-table"' in hierarchy_section
    assert "Current: WATCH" in summary_html
    assert "Window 30d: ADD_ON_PULLBACK" in summary_html
    assert "Window 5d: ADD_ON_PULLBACK" in summary_html
    assert "Window 2d: ADD_ON_PULLBACK" in summary_html
    assert "Overheat: WATCH" in summary_html
    assert "30d: NEUTRAL -&gt; WATCH" not in summary_html
    assert "Layer summary" not in hierarchy_section
    assert "<h3>Subindustries</h3>" not in hierarchy_section
    assert "<td>LAYER</td><td>Compute</td><td>Compute</td>" in hierarchy_section
    assert (
        "<td>SUBINDUSTRY</td><td>AI Accelerators</td><td>Compute</td>"
        in hierarchy_section
    )
    assert 'class="status-positive">ADD_ON_PULLBACK</td>' in hierarchy_section
    assert hierarchy_section.count("<thead><tr>") == 1
    assert html_one.index('id="watchlist-status"') > html_one.index('id="summary"')
    assert html_one.index('id="watchlist-status"') < html_one.index(
        'id="candidate-pullbacks"'
    )
    assert html_one.index('id="candidate-pullbacks"') < html_one.index(
        'id="command-center"'
    )
    watchlist_section = html_one[
        html_one.index('id="watchlist-status"') : html_one.index(
            'id="candidate-pullbacks"'
        )
    ]
    assert 'class="watchlist-detail ' in watchlist_section
    assert 'class="watchlist-summary ' in watchlist_section
    assert 'data-section="watchlist-status"' in watchlist_section
    assert 'data-filter-row="1"' in watchlist_section
    assert 'data-action="' in watchlist_section
    assert 'data-filter-text="' in watchlist_section
    assert (
        'class="table-scroll"><table class="sticky-table"><thead><tr><th>Ticker</th><th>Action</th>'
        not in watchlist_section
    )
    assert watchlist_section.count('class="watchlist-detail ') == 3

    msft_summary_match = re.search(
        r'<summary class="watchlist-summary ([^"]+)">\s*<span class="watchlist-ticker">MS&amp;FT</span>(.*?)</summary>',
        watchlist_section,
        re.DOTALL,
    )
    assert msft_summary_match is not None
    msft_summary_classes = msft_summary_match.group(1).split()
    msft_summary_html = msft_summary_match.group(2)
    assert "action-watch" in msft_summary_classes
    assert "WATCH" in msft_summary_html
    assert "LOW" in msft_summary_html
    assert "VALID_PULLBACK_WAIT_FOR_ENTRY_CONFIRMATION" in msft_summary_html
    assert "OK" in msft_summary_html
    assert "FRESH_BULLISH_SIGNAL" in msft_summary_html
    assert "Trend UP (12)" in msft_summary_html
    assert "Structure HH (3)" in msft_summary_html
    assert "BOS BOS_UP (1)" in msft_summary_html
    assert "Reset -" in msft_summary_html
    assert "Pattern Bearish Divergence (2)" in msft_summary_html

    assert "HH (3)" in watchlist_section
    assert "BOS_DOWN (1)" in watchlist_section
    assert "DOUBLE_BOS_DOWN (1)" in watchlist_section
    assert "FAILED_BREAKOUT" in watchlist_section
    assert "Hammer (4)" in watchlist_section
    assert "Bearish Divergence (2)" in watchlist_section
    assert "BASE_BREAKOUT (5)" in watchlist_section
    assert "SHOOTING_STAR (2)" in watchlist_section
    assert "BEARISH_DIVERGENCE (1)" in watchlist_section
    assert "ASCENDING_TRIANGLE (6)" in watchlist_section
    assert "FAILED_BREAKOUT (-)" not in watchlist_section
    assert "HH (-)" not in watchlist_section
    assert "BOS_UP (-)" not in watchlist_section
    assert "Pattern -" not in watchlist_section

    for snippet in (
        "<th>Ticker</th>",
        "<th>Action</th>",
        "<th>Severity</th>",
        "<th>Primary reason</th>",
        "<th>Current status</th>",
        "<th>Start status 30d</th>",
        "<th>Status change 30d</th>",
        "<th>Status change 5d</th>",
        "<th>Window status 30d</th>",
        "<th>Window status 5d</th>",
        "<th>Window status 2d</th>",
        "<th>MA break</th>",
        "<th>Freshness</th>",
        "<th>Trend state</th>",
        "<th>Latest structure</th>",
        "<th>Latest BOS</th>",
        "<th>Latest reset</th>",
        "<th>Latest candle</th>",
        "<th>Latest divergence</th>",
        "<th>Latest chart pattern</th>",
        "<th>Pullback validity</th>",
        "<th>Entry readiness</th>",
        "<th>Candidate priority</th>",
        "<th>Daily status</th>",
        "<th>Rolling 2d status</th>",
        "<th>Rolling 5d status</th>",
        "<th>Rolling 30d status</th>",
        "<th>Horizons</th>",
    ):
        assert snippet in watchlist_section

    assert "BREAKOUT_READY" in watchlist_section
    assert "WATCH -&gt; BREAKOUT_READY" in watchlist_section
    assert "PULLBACK_WINDOW -&gt; BREAKOUT_READY" in watchlist_section
    assert "PULLBACK_MONITOR" in watchlist_section
    assert "PULLBACK_WINDOW" in watchlist_section

    amd_details_match = re.search(
        r'<details class="watchlist-detail [^"]+"[^>]*data-filter-text="([^"]+)"[^>]*>\s*<summary class="watchlist-summary [^"]+">\s*<span class="watchlist-ticker">AMD</span>(.*?)</summary>.*?<table class="sticky-table watchlist-detail-table">(.*?)</table>',
        watchlist_section,
        re.DOTALL,
    )
    assert amd_details_match is not None
    amd_filter_text = amd_details_match.group(1).lower()
    amd_detail_html = amd_details_match.group(3)
    assert "SHOOTING_STAR (2)" in amd_detail_html
    assert "BEARISH_DIVERGENCE (1)" in amd_detail_html
    assert "ascending_triangle (6)" in amd_detail_html.lower()
    assert "hammer (2)" not in amd_detail_html.lower()
    assert "hidden_bullish_divergence (1)" not in amd_detail_html.lower()
    assert "shooting_star (2)" in amd_filter_text
    assert "bearish_divergence (1)" in amd_filter_text
    assert "ascending_triangle (6)" in amd_filter_text


@pytest.mark.parametrize(
    ("layer_current_status", "expected_summary_class"),
    [
        ("TRIM_WATCH", "risk-medium"),
        ("EXIT_ZONE", "risk-high"),
        ("BUY_ZONE", "status-positive"),
    ],
)
def test_market_map_layer_summary_uses_current_status_class(
    tmp_path,
    monkeypatch,
    layer_current_status,
    expected_summary_class,
):
    _install_pipeline_mocks(
        monkeypatch,
        tmp_path,
        layer_current_status=layer_current_status,
        layer_window_status=layer_current_status,
        layer_overheat_status=layer_current_status,
    )

    html, _status, _parse, _decisions = generate_dashboard_html(
        reports_dir=str(tmp_path),
        title="Custom <Dashboard>",
        ticker="MS&FT",
        report_date=None,
        max_command_rows=10,
        max_candidate_rows=10,
        generated_at_utc="2026-05-25T00:00:00+00:00",
    )

    hierarchy_section = html[
        html.index('id="market-map-layers-subindustries"') : html.index(
            'id="watchlist-status"'
        )
    ]
    summary_match = re.search(
        r'<summary class="market-layer-summary ([^"]+)">\s*<span class="layer-name">Compute</span>',
        hierarchy_section,
    )
    assert summary_match is not None
    summary_classes = summary_match.group(1).split()

    assert "market-layer-summary" in summary_match.group(0)
    assert expected_summary_class in summary_classes
    assert f'class="market-layer-detail {expected_summary_class}"' in hierarchy_section


@pytest.mark.parametrize(
    ("action", "severity", "expected_summary_class"),
    [
        ("SELL", "CRITICAL", "action-sell"),
        ("REDUCE", "HIGH", "action-reduce"),
        ("TIGHTEN_STOP", "MEDIUM", "action-tighten"),
    ],
)
def test_watchlist_summary_uses_action_based_color_class(
    tmp_path,
    monkeypatch,
    action,
    severity,
    expected_summary_class,
):
    _install_pipeline_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.build_datacenter_ticker_decisions",
        lambda rows: _fake_decision_result_with_action(
            tmp_path,
            ticker="MS&FT",
            action=action,
            severity=severity,
        ),
    )

    html, _status, _parse, _decisions = generate_dashboard_html(
        reports_dir=str(tmp_path),
        title="Custom <Dashboard>",
        ticker="MS&FT",
        report_date=None,
        max_command_rows=10,
        max_candidate_rows=10,
        generated_at_utc="2026-05-25T00:00:00+00:00",
    )

    watchlist_section = html[
        html.index('id="watchlist-status"') : html.index('id="candidate-pullbacks"')
    ]
    summary_match = re.search(
        r'<summary class="watchlist-summary ([^"]+)">\s*<span class="watchlist-ticker">MS&amp;FT</span>',
        watchlist_section,
    )
    assert summary_match is not None
    summary_classes = summary_match.group(1).split()

    assert expected_summary_class in summary_classes
    assert f'class="watchlist-detail {expected_summary_class}"' in watchlist_section


def test_generate_datacenter_dashboard_html_file_returns_output_path_and_summary_values(
    tmp_path, monkeypatch
):
    _install_pipeline_mocks(monkeypatch, tmp_path)

    result = generate_datacenter_dashboard_html_file(
        reports_dir=str(tmp_path),
        report_date="2026-05-22",
    )

    assert result.output_path.endswith("datacenter_dashboard_2026-05-22.html")
    assert Path(result.output_path).exists()
    assert result.report_date == "2026-05-22"
    assert result.selection_mode == "report_date"
    assert result.readiness == "READY"
    assert result.found_reports == 4
    assert result.missing_reports == 0
    assert result.decision_total == 3
    assert result.candidate_pullback_rows == 2
    assert any(
        line == "SUMMARY selection_mode=report_date" for line in result.summary_lines
    )


def test_html_cli_generates_default_output_and_prints_summaries(
    tmp_path, monkeypatch, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"]
    )

    assert exit_code == 0
    output_path = reports_dir / "datacenter_dashboard.html"
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    ecosystem_header = re.search(
        r'<section id="market-map-ecosystem".*?<thead><tr>(.*?)</tr></thead>',
        html,
        re.DOTALL,
    )
    assert ecosystem_header is not None
    for snippet in _MARKET_MAP_HEADER_SNIPPETS:
        assert snippet in ecosystem_header.group(1)
    assert "<h1>Datacenter Dashboard</h1>" in html
    assert 'href="#summary"' in html
    assert 'href="#market-map-ecosystem"' in html
    assert 'href="#market-map-layers-subindustries"' in html
    assert 'href="#watchlist-status"' in html
    assert 'href="#candidate-pullbacks"' in html
    assert 'href="#command-center"' in html
    assert 'href="#inspector"' in html
    assert 'href="#source-files"' in html
    assert "Summary" in html
    assert "Watchlist Status" in html
    assert "Candidate Pullbacks" in html
    assert "Command Center" in html
    assert "Ticker Inspector / Details" in html
    assert "Source Files / Report Status" in html
    assert "Ecosystem Summary" in html
    assert "Layers and Subindustries" in html
    assert "Current status" in html
    assert "Start status 30d" in html
    assert "Status change 30d" in html
    assert "Status change 5d" in html
    assert "Window status 30d" in html
    assert "Window status 5d" in html
    assert "Window status 2d" in html
    assert "Overheat risk" in html
    assert "Dow trend state" in html
    assert "Latest relevant pattern" in html
    assert "Pattern age td" not in html
    assert "Latest structure" in html
    assert "Latest BOS" in html
    assert "Latest reset" in html
    assert "Source horizons" in html
    assert "Source files" in html
    assert html.count('class="table-scroll"') >= 4
    assert "WATCH -&gt; BUY_ZONE" in html
    assert "NEUTRAL -&gt; WATCH" in html
    assert "72.00%" in html
    assert "68.00%" in html
    assert "4.00%" in html
    assert "210.00%" in html
    assert "2100.00%" in html
    assert "SHOOTING_STAR (1)" in html
    assert "TRENDING_UP (2)" in html
    assert "HH (3)" in html
    assert "BOS_UP (1)" in html
    assert "RESET_COMPLETE (1)" in html
    assert "daily, rolling 2d, rolling 5d, rolling 30d" in html
    assert "Report Source" in html
    assert "generated_at_utc" in html
    assert "reports_dir" in html
    assert "selected_report_date" in html
    assert "selection_mode" in html
    assert str(reports_dir / "daily.csv") in html
    assert str(reports_dir / "rolling2.csv") in html
    assert str(reports_dir / "rolling5.csv") in html
    assert str(reports_dir / "rolling30.csv") in html
    assert "Filters" in html
    assert (
        "Filters apply to Market Map, Watchlist Status, Candidate Pullbacks, Command Center and Inspector rows."
        in html
    )
    assert 'id="ticker-filter"' in html
    assert 'id="action-filter"' in html
    assert 'id="pullback-filter"' in html
    assert 'id="entry-readiness-filter"' in html
    assert 'id="candidate-priority-filter"' in html
    assert "function applyFilters()" in html
    assert ".sticky-table thead th" in html
    assert "Visible filtered rows:" in html
    assert "Market Map rows:" in html
    assert "Watchlist rows:" in html
    assert html.index("<h2>Filters</h2>") < html.index('id="candidate-pullbacks"')
    assert "<td>MS&amp;FT</td>" in html

    stdout = capsys.readouterr().out
    assert f"SUMMARY reports_dir={reports_dir}" in stdout
    assert "SUMMARY report_date=newest" in stdout
    assert "SUMMARY selection_mode=newest" in stdout
    assert f"SUMMARY html_output={output_path}" in stdout
    assert "SUMMARY readiness=READY" in stdout
    assert "SUMMARY found_reports=4" in stdout
    assert "SUMMARY missing_reports=0" in stdout
    assert "SUMMARY decision_total=3" in stdout
    assert "SUMMARY candidate_pullback_rows=2" in stdout


def test_market_map_status_class_mapping_covers_requested_status_groups():
    assert _status_class_from_text("TRIM_WATCH") == "risk-medium"
    assert _status_class_from_text("EXIT_ZONE") == "risk-high"
    assert _status_class_from_text("BUY_ZONE") == "status-positive"
    assert _status_class_from_text("NEUTRAL") == "status-neutral"
    assert _status_class_from_text("ELEVATED") == "risk-medium"
    assert _status_class_from_text("INSUFFICIENT_DATA") == "status-missing"


def test_market_map_status_change_prefers_rhs_status_for_coloring():
    assert _status_class_from_text("EXIT_ZONE -> NEUTRAL") == "status-neutral"
    assert _status_class_from_text("NEUTRAL -> BUY_ZONE") == "status-positive"


def test_market_map_value_age_formatting_omits_missing_age_and_missing_value():
    assert _format_value_with_age("HH", "3") == "HH (3)"
    assert _format_value_with_age("HH", "") == "HH"
    assert _format_value_with_age("", "3") == "-"
    assert _format_value_with_age("HH", "-") == "HH"


def test_html_cli_accepts_report_date_and_uses_date_specific_default_output(
    tmp_path, monkeypatch, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(["--reports-dir", str(reports_dir), "--report-date", "2026-05-22"])

    assert exit_code == 0
    output_path = reports_dir / "datacenter_dashboard_2026-05-22.html"
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert "Datacenter Dashboard — 2026-05-22" in html
    assert "2026-05-22" in html
    assert "report_date" in capsys.readouterr().out


def test_html_cli_invalid_report_date_format_exits_non_zero(
    tmp_path, monkeypatch, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(["--reports-dir", str(reports_dir), "--report-date", "2026/05/22"])

    assert exit_code == 2
    assert "invalid report_date format" in capsys.readouterr().out


def test_html_cli_report_date_no_matching_reports_exits_non_zero(
    tmp_path, monkeypatch, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.discover_datacenter_dashboard_status",
        lambda reports_dir, report_date=None: _fake_dashboard_status(
            tmp_path
        ).__class__(
            overall_status="MISSING",
            reports=[
                report.__class__(
                    horizon=report.horizon,
                    status="MISSING",
                    path=None,
                    modified_at=None,
                )
                for report in _fake_dashboard_status(tmp_path).reports
            ],
        ),
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--report-date", "2026-05-22"])

    assert exit_code == 1
    assert "no reports found for report_date=2026-05-22" in capsys.readouterr().out


def test_html_cli_renders_empty_watchlist_state(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.parse_datacenter_dashboard_file",
        lambda path, horizon: type(
            "ParseResult",
            (),
            {
                "rows": [
                    row
                    for row in _fake_rows(path, horizon)
                    if row.section != "Watchlist Summary"
                ]
            },
        )(),
    )

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"]
    )

    assert exit_code == 0
    html = (reports_dir / "datacenter_dashboard.html").read_text(encoding="utf-8")
    assert "No watchlist rows found in the selected reports." in html


def test_html_cli_renders_empty_market_map_state(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)
    for name in ("daily.csv", "rolling2.csv", "rolling5.csv", "rolling30.csv"):
        (reports_dir / name).write_text("", encoding="utf-8")

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"]
    )

    assert exit_code == 0
    html = (reports_dir / "datacenter_dashboard.html").read_text(encoding="utf-8")
    assert "No market map rows found in the selected reports." in html


def test_html_cli_market_map_missing_optional_fields_render_as_dash(
    tmp_path, monkeypatch
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)
    (reports_dir / "daily.csv").write_text(
        """## 3. Dashboard
| metric | value |
| --- | --- |
| timing_state | NEUTRAL |
""",
        encoding="utf-8",
    )
    for name in ("rolling2.csv", "rolling5.csv", "rolling30.csv"):
        (reports_dir / name).write_text("", encoding="utf-8")

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"]
    )

    assert exit_code == 0
    html = (reports_dir / "datacenter_dashboard.html").read_text(encoding="utf-8")
    assert "DC_ECOSYSTEM_TOTAL" in html
    assert "NEUTRAL" in html
    assert "<td>-</td>" in html


def test_html_cli_custom_output_path_works(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    output_path = tmp_path / "custom" / "dashboard.html"
    output_path.parent.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(
        [
            "--reports-dir",
            str(reports_dir),
            "--output",
            str(output_path),
            "--ticker",
            "MS&FT",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert 'class="ticker-detail selected"' in html


def test_html_cli_dashboard_db_mode_renders_html_and_prints_db_summaries(
    tmp_path, capsys
):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    output_path = tmp_path / "dashboard_db_mode.html"
    run_id = _seed_dashboard_db(dashboard_db)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert "2026-05-22" in html
    assert run_id in html
    assert "NVDA" in html
    assert "SELL" in html

    stdout = capsys.readouterr().out
    assert "SUMMARY datacenter_dashboard_html.input_mode=dashboard_db" in stdout
    assert "SUMMARY datacenter_dashboard_html.ecosystem_code=DATACENTER" in stdout
    assert "SUMMARY datacenter_dashboard_html.report_date=2026-05-22" in stdout
    assert f"SUMMARY datacenter_dashboard_html.run_id={run_id}" in stdout
    assert "SUMMARY datacenter_dashboard_html.status=OK" in stdout


def test_html_cli_dashboard_db_mode_requires_run_id_or_report_date(
    tmp_path, capsys
):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(dashboard_db)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
        ]
    )

    assert exit_code == 2
    assert "dashboard-db mode requires --run-id or --report-date" in capsys.readouterr().out


def test_html_cli_dashboard_db_mode_rejects_non_datacenter_ecosystem_code(
    tmp_path, capsys
):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(dashboard_db)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "OTHER",
            "--report-date",
            "2026-05-22",
        ]
    )

    assert exit_code == 2
    assert "unsupported ecosystem_code for this CLI: OTHER" in capsys.readouterr().out
