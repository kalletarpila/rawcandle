from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardDecisionTraceInput,
    EcosystemDashboardInput,
    EcosystemDashboardMarketMapInput,
    EcosystemDashboardSourceReportInput,
    EcosystemDashboardTickerStatusInput,
    EcosystemDashboardWatchlistInput,
)
from dev_tools.ecosystem_dashboard_persistence import persist_ecosystem_dashboard_input
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot


def _table_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _minimal_dashboard_input(*, report_date: str = "2026-05-22") -> EcosystemDashboardInput:
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path="/tmp/datacenter_daily_2026-05-22.csv",
                source_report_type="daily",
                source_report_date=report_date,
                loaded_row_count=12,
                status="OK",
            )
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket="WATCH",
                action_label="Watch Candidate",
                ticker_count=1,
                weight_sum=1.5,
                notes=None,
            )
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=1,
                subindustry_order=2,
                layer_name="Infrastructure",
                subindustry_name="Optical",
                ticker_count=4,
                watchlist_count=1,
                avg_return_5d=1.25,
                avg_return_20d=4.5,
                avg_return_60d=12.0,
                avg_trend_score=0.8,
                avg_action_score=0.6,
                dominant_action_bucket="WATCH",
            )
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker="NVDA",
                company_name="NVIDIA",
                layer_name="Infrastructure",
                subindustry_name="Optical",
                action_bucket="WATCH",
                action_label="Watch Candidate",
                watchlist_reason="momentum",
                last_close=100.5,
                return_5d=1.2,
                return_20d=4.5,
                return_60d=12.0,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason=None,
                bullish_candle_signal=1,
                bullish_divergence_signal=None,
                hidden_bullish_divergence_signal=None,
                data_status="READY",
            )
        ],
        tickers=[
            EcosystemDashboardTickerStatusInput(
                ticker="NVDA",
                company_name="NVIDIA",
                layer_name="Infrastructure",
                subindustry_name="Optical",
                last_close=100.5,
                return_5d=1.2,
                return_20d=4.5,
                return_60d=12.0,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_bos_freshness="FRESH",
                latest_reset_reason=None,
                latest_reset_freshness=None,
                bullish_candle_signal=1,
                bullish_divergence_signal=None,
                hidden_bullish_divergence_signal=None,
                action_bucket="WATCH",
                action_label="Watch Candidate",
                data_status="READY",
            )
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker="NVDA",
                trace_order=0,
                rule_group="daily",
                rule_name="WATCH_MOMENTUM",
                input_value="1.2",
                decision="WATCH",
                reason="momentum",
            )
        ],
        readiness="READY",
        total_parsed_rows=12,
        total_parse_warnings=0,
    )


def test_input_dataclasses_can_represent_minimal_complete_dashboard_input():
    dashboard_input = _minimal_dashboard_input()

    assert dashboard_input.ecosystem_code == "DATACENTER"
    assert dashboard_input.report_date == "2026-05-22"
    assert dashboard_input.source_reports[0].source_report_type == "daily"
    assert dashboard_input.action_summary[0].action_bucket == "WATCH"
    assert dashboard_input.watchlist[0].ticker == "NVDA"
    assert dashboard_input.tickers[0].last_close == 100.5
    assert dashboard_input.decision_trace[0].trace_order == 0


def test_persist_ecosystem_dashboard_input_writes_rows_and_round_trips_via_read_model(tmp_path):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    dashboard_input = _minimal_dashboard_input()

    run_id = persist_ecosystem_dashboard_input(
        str(dashboard_db),
        dashboard_input,
        mode="insert",
        run_id="RUN_INPUT_A",
    )

    assert run_id == "RUN_INPUT_A"
    assert _table_count(dashboard_db, "ecosystem_dashboard_runs") == 1
    assert _table_count(dashboard_db, "ecosystem_dashboard_source_reports") == 1
    assert _table_count(dashboard_db, "ecosystem_dashboard_action_summary") == 1
    assert _table_count(dashboard_db, "ecosystem_dashboard_market_map") == 1
    assert _table_count(dashboard_db, "ecosystem_dashboard_watchlist_status") == 1
    assert _table_count(dashboard_db, "ecosystem_dashboard_ticker_status") == 1
    assert _table_count(dashboard_db, "ecosystem_dashboard_decision_trace") == 1

    snapshot = load_dashboard_snapshot(
        str(dashboard_db),
        "DATACENTER",
        run_id="RUN_INPUT_A",
    )

    assert snapshot.run.run_id == "RUN_INPUT_A"
    assert snapshot.run.ecosystem_code == "DATACENTER"
    assert snapshot.run.report_date == "2026-05-22"
    assert snapshot.action_summary[0]["action"] == "WATCH"
    assert snapshot.action_summary[0]["count"] == 1
    assert snapshot.watchlist[0]["ticker"] == "NVDA"
    assert snapshot.watchlist[0]["action"] == "WATCH"
    assert snapshot.watchlist[0]["severity"] == "Watch Candidate"
    assert snapshot.watchlist[0]["primary_reason"] == "momentum"
    assert snapshot.tickers[0]["ticker"] == "NVDA"
    assert snapshot.tickers[0]["action"] == "WATCH"
    assert snapshot.tickers[0]["severity"] == "Watch Candidate"
    assert snapshot.market_map[0]["return_20d"] == 4.5
    assert snapshot.market_map[0]["return_60d"] == 12.0
    assert snapshot.tickers[0]["latest_reset_reason"] is None
    assert snapshot.decision_trace[0]["matched_rule"] == "WATCH_MOMENTUM"
    assert snapshot.decision_trace[0]["matched_token"] is None
    assert snapshot.decision_trace[0]["matched_value"] == "1.2"
    assert snapshot.decision_trace[0]["horizon"] == "daily"


def test_persist_ecosystem_dashboard_input_replace_date_excludes_old_rows_from_selected_run(tmp_path):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"

    persist_ecosystem_dashboard_input(
        str(dashboard_db),
        _minimal_dashboard_input(report_date="2026-05-22"),
        mode="insert",
        run_id="RUN_OLD",
    )
    persist_ecosystem_dashboard_input(
        str(dashboard_db),
        _minimal_dashboard_input(report_date="2026-05-22"),
        mode="replace-date",
        run_id="RUN_NEW",
    )

    snapshot = load_dashboard_snapshot(
        str(dashboard_db),
        "DATACENTER",
        report_date="2026-05-22",
    )

    assert snapshot.run.run_id == "RUN_NEW"
    with sqlite3.connect(dashboard_db) as conn:
        old_rows = conn.execute(
            "SELECT COUNT(*) FROM ecosystem_dashboard_runs WHERE run_id = 'RUN_OLD'"
        ).fetchone()[0]
    assert old_rows == 0
