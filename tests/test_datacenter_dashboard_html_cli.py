from __future__ import annotations

from pathlib import Path

import pytest
import re

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
                raw_fields={"watchlist_status": "BREAKOUT_READY"},
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
                raw_fields={},
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
                    "current_watchlist_status": "PULLBACK_MONITOR",
                    "window_watchlist_status": "PULLBACK_WINDOW",
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
                raw_fields={},
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
                source_files=[str(tmp_path / "daily.csv"), str(tmp_path / "rolling30.csv")],
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
                action: 0 for action in (
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


def _install_pipeline_mocks(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "daily.csv").write_text(
        """## 3. Dashboard
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
| LAYER | Compute |  |  | WATCH | NORMAL | WATCH |  | 2.3 | 4.1 | 9.2 |  | UP | HL | fresh | BOS_UP | fresh |  |  |  |  |  |  |  | OK |
| SUBINDUSTRY | Compute | AI Accelerators |  | BUY_ZONE | HIGH | WATCH |  | 2.7 | 5.0 | 10.8 |  | UP | HH | fresh | BOS_UP | fresh |  |  |  |  |  |  |  | OK |
""",
        encoding="utf-8",
    )
    rolling_fixture = """## 4. Ecosystem window change
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
| layer | Compute | BOS_UP | 2026-05-22 | 1 | fresh |  |  |  |  | HH | 3 | fresh | TRENDING_UP | WATCH | WATCH |
| subindustry | AI Accelerators | BOS_UP | 2026-05-22 | 1 | fresh |  |  |  |  | HH | 3 | fresh | TRENDING_UP | BUY_ZONE | HIGH |

## 7. Group Window Status Change
| group_type | group_name | first_timing_state | last_timing_state |
| --- | --- | --- | --- |
| layer | Compute | NEUTRAL | WATCH |
| subindustry | AI Accelerators | NEUTRAL | BUY_ZONE |

## Datacenter Taxonomy Listing
| row_type | layer | subindustry | ticker | current_status | start_status | status_change | window_status | subindustry_context_risk | layer_context_risk | last_close | breakout_days | pullback_days | exit_risk_days | high_exit_risk_days | medium_exit_risk_days | last_exit_risk_severity | last_exit_reason | last_trend_state | last_trend_state_age_td | last_latest_structure_label | last_latest_structure_age_trading_days | last_latest_structure_freshness | last_latest_bos_event_type | last_latest_bos_age_trading_days | last_latest_bos_freshness | last_latest_reset_reason | last_latest_reset_age_trading_days | last_latest_reset_freshness | last_price_data_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER | Compute |  |  | WATCH | NEUTRAL | NEUTRAL -> WATCH | ADD_ON_PULLBACK | NORMAL | WATCH |  | 0 | 2 | 0 | 0 | 0 |  |  | UP | 2 | HH | 3 | fresh | BOS_UP | 1 | fresh |  |  |  | OK |
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
        lambda path, horizon: type("ParseResult", (), {"rows": _fake_rows(path, horizon)})(),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.build_datacenter_ticker_decisions",
        lambda rows: decision_result,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.build_datacenter_ticker_inspector_view",
        lambda decision, rows: inspector_views[decision.ticker],
    )


def test_build_parser_requires_reports_dir():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_generate_dashboard_html_is_deterministic_and_escapes_values(tmp_path, monkeypatch):
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
    assert html_one.index('id="market-map-ecosystem"') < html_one.index('id="watchlist-status"')
    assert html_one.index('id="market-map-layers-subindustries"') > html_one.index('id="market-map-ecosystem"')
    hierarchy_section = html_one[
        html_one.index('id="market-map-layers-subindustries"'):html_one.index('id="watchlist-status"')
    ]
    summary_match = re.search(r"<summary>(.*?)</summary>", hierarchy_section, re.DOTALL)
    assert summary_match is not None
    summary_html = summary_match.group(1)
    assert "<details" in hierarchy_section
    assert "<summary>" in hierarchy_section
    assert 'class="market-layer-detail risk-medium"' in hierarchy_section
    assert "Current: WATCH" in summary_html
    assert "Window 30d: ADD_ON_PULLBACK" in summary_html
    assert "Window 5d: ADD_ON_PULLBACK" in summary_html
    assert "Window 2d: ADD_ON_PULLBACK" in summary_html
    assert "Overheat: WATCH" in summary_html
    assert "30d: NEUTRAL -&gt; WATCH" not in summary_html
    assert "Layer summary" in hierarchy_section
    assert "Subindustries" in hierarchy_section
    assert "<td>LAYER</td><td>Compute</td><td>Compute</td>" in hierarchy_section
    assert "<td>SUBINDUSTRY</td><td>AI Accelerators</td><td>Compute</td>" in hierarchy_section
    assert 'class="status-positive">ADD_ON_PULLBACK</td>' in hierarchy_section
    assert html_one.index('id="watchlist-status"') > html_one.index('id="summary"')
    assert html_one.index('id="watchlist-status"') < html_one.index('id="candidate-pullbacks"')
    assert html_one.index('id="candidate-pullbacks"') < html_one.index('id="command-center"')


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
    assert any(line == "SUMMARY selection_mode=report_date" for line in result.summary_lines)


def test_html_cli_generates_default_output_and_prints_summaries(tmp_path, monkeypatch, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"])

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
    assert "Filters apply to Market Map, Watchlist Status, Candidate Pullbacks, Command Center and Inspector rows." in html
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


def test_html_cli_accepts_report_date_and_uses_date_specific_default_output(tmp_path, monkeypatch, capsys):
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


def test_html_cli_invalid_report_date_format_exits_non_zero(tmp_path, monkeypatch, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(["--reports-dir", str(reports_dir), "--report-date", "2026/05/22"])

    assert exit_code == 2
    assert "invalid report_date format" in capsys.readouterr().out


def test_html_cli_report_date_no_matching_reports_exits_non_zero(tmp_path, monkeypatch, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.discover_datacenter_dashboard_status",
        lambda reports_dir, report_date=None: _fake_dashboard_status(tmp_path).__class__(
            overall_status="MISSING",
            reports=[
                report.__class__(horizon=report.horizon, status="MISSING", path=None, modified_at=None)
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
            {"rows": [row for row in _fake_rows(path, horizon) if row.section != "Watchlist Summary"]},
        )(),
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"])

    assert exit_code == 0
    html = (reports_dir / "datacenter_dashboard.html").read_text(encoding="utf-8")
    assert "No watchlist rows found in the selected reports." in html


def test_html_cli_renders_empty_market_map_state(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)
    for name in ("daily.csv", "rolling2.csv", "rolling5.csv", "rolling30.csv"):
        (reports_dir / name).write_text("", encoding="utf-8")

    exit_code = main(["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"])

    assert exit_code == 0
    html = (reports_dir / "datacenter_dashboard.html").read_text(encoding="utf-8")
    assert "No market map rows found in the selected reports." in html


def test_html_cli_market_map_missing_optional_fields_render_as_dash(tmp_path, monkeypatch):
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

    exit_code = main(["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"])

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
