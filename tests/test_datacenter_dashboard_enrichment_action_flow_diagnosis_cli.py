from __future__ import annotations

import json
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
from dev_tools.run_datacenter_dashboard_enrichment_action_flow_diagnosis import main


def _dashboard_input(
    *,
    report_date: str = "2026-05-22",
    ticker_rows: list[dict[str, object]],
    action_summary_rows: list[tuple[str | None, int]] | None = None,
) -> EcosystemDashboardInput:
    summary_rows = action_summary_rows or []
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path="/tmp/report.md",
                source_report_type="daily",
                source_report_date=report_date,
                loaded_row_count=len(ticker_rows),
                status="OK",
            )
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket=action,
                action_label=action,
                ticker_count=count,
                weight_sum=None,
                notes=None,
            )
            for action, count in summary_rows
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=0,
                subindustry_order=0,
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                ticker_count=len(ticker_rows),
                watchlist_count=sum(1 for row in ticker_rows if row.get("is_watchlist")),
                avg_return_5d=0.1,
                avg_return_20d=0.2,
                avg_return_60d=0.3,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=None,
            )
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker=str(row["ticker"]),
                company_name=None,
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                action_bucket=row.get("action"),
                action_label=row.get("action"),
                watchlist_reason=None,
                last_close=10.0,
                return_5d=1.0,
                return_20d=2.0,
                return_60d=3.0,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason=None,
                bullish_candle_signal=None,
                bullish_divergence_signal=None,
                hidden_bullish_divergence_signal=None,
                data_status="READY",
            )
            for row in ticker_rows
            if row.get("is_watchlist")
        ],
        tickers=[
            EcosystemDashboardTickerStatusInput(
                ticker=str(row["ticker"]),
                company_name=None,
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                last_close=10.0,
                return_5d=1.0,
                return_20d=2.0,
                return_60d=3.0,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_bos_freshness="FRESH",
                latest_reset_reason=None,
                latest_reset_freshness=None,
                bullish_candle_signal=None,
                bullish_divergence_signal=None,
                hidden_bullish_divergence_signal=None,
                action_bucket=row.get("action"),
                action_label=row.get("action"),
                data_status="READY",
            )
            for row in ticker_rows
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker=str(row["ticker"]),
                trace_order=0,
                rule_group="daily",
                rule_name="RULE",
                input_value="signal",
                decision=row.get("action"),
                reason="reason",
            )
            for row in ticker_rows
        ],
        readiness="READY",
        total_parsed_rows=len(ticker_rows),
        total_parse_warnings=0,
    )


def _persist(db_path: Path, dashboard_input: EcosystemDashboardInput, *, run_id: str) -> str:
    return persist_ecosystem_dashboard_input(
        dashboard_db=str(db_path),
        dashboard_input=dashboard_input,
        mode="insert",
        run_id=run_id,
    )


def _create_analysis_copy(path: Path, rows: list[dict[str, object]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT,
                severity TEXT,
                primary_reason TEXT,
                pullback_validity TEXT,
                entry_readiness TEXT,
                candidate_priority INTEGER,
                is_watchlist INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        for row in rows:
            columns = sorted(row)
            conn.execute(
                f"""
                INSERT INTO dc_dashboard_ticker_enrichment_daily ({", ".join(columns)})
                VALUES ({", ".join("?" for _ in columns)})
                """,
                tuple(row[column] for column in columns),
            )


def _write_enrichment_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_cli(
    capsys,
    *,
    enrichment_dashboard_db: Path,
    enrichment_run_id: str,
    analysis_db_copy: Path,
    enrichment_json: Path | None = None,
    tickers: str | None = None,
):
    argv = [
        "--enrichment-dashboard-db",
        str(enrichment_dashboard_db),
        "--enrichment-run-id",
        enrichment_run_id,
        "--analysis-db-copy",
        str(analysis_db_copy),
        "--ecosystem-code",
        "DATACENTER",
        "--report-date",
        "2026-05-22",
    ]
    if enrichment_json is not None:
        argv.extend(["--enrichment-json", str(enrichment_json)])
    if tickers is not None:
        argv.extend(["--tickers", tickers])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_actions_present_in_analysis_but_missing_in_dashboard_is_likely(tmp_path, capsys):
    dashboard_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    run_id = _persist(
        dashboard_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": None}],
            action_summary_rows=[],
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "action": "SELL",
                "severity": "HIGH",
                "primary_reason": "risk_exit",
                "pullback_validity": "NO_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority": 9,
                "is_watchlist": 0,
            }
        ],
    )

    exit_code, output, error = _run_cli(
        capsys,
        enrichment_dashboard_db=dashboard_db,
        enrichment_run_id=run_id,
        analysis_db_copy=analysis_db,
        tickers="AAA",
    )

    assert exit_code == 0
    assert error == ""
    assert (
        "mapping_gap_hypothesis;ACTIONS_PRESENT_IN_ANALYSIS_BUT_MISSING_IN_DASHBOARD;LIKELY;"
        in output
    )


def test_actions_missing_already_in_analysis_is_likely(tmp_path, capsys):
    dashboard_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    run_id = _persist(
        dashboard_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": None}], action_summary_rows=[]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "action": None,
                "severity": None,
                "primary_reason": None,
                "pullback_validity": None,
                "entry_readiness": None,
                "candidate_priority": None,
                "is_watchlist": 0,
            }
        ],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        enrichment_dashboard_db=dashboard_db,
        enrichment_run_id=run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    assert "mapping_gap_hypothesis;ACTIONS_MISSING_ALREADY_IN_ANALYSIS;LIKELY;" in output


def test_action_summary_empty_action_row_is_likely(tmp_path, capsys):
    dashboard_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    run_id = _persist(
        dashboard_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": None}],
            action_summary_rows=[(None, 1)],
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "action": None,
                "severity": None,
                "primary_reason": None,
                "pullback_validity": None,
                "entry_readiness": None,
                "candidate_priority": None,
                "is_watchlist": 0,
            }
        ],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        enrichment_dashboard_db=dashboard_db,
        enrichment_run_id=run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    assert "mapping_gap_hypothesis;ACTION_SUMMARY_EMPTY_ACTION_ROW;LIKELY;" in output


def test_watchlist_present_in_analysis_is_likely_and_example_row_shows_flow(tmp_path, capsys):
    dashboard_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    run_id = _persist(
        dashboard_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": None, "is_watchlist": 0}],
            action_summary_rows=[],
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "action": "SELL",
                "severity": "HIGH",
                "primary_reason": "risk_exit",
                "pullback_validity": "NO_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority": 9,
                "is_watchlist": 1,
            }
        ],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        enrichment_dashboard_db=dashboard_db,
        enrichment_run_id=run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    assert "mapping_gap_hypothesis;WATCHLIST_PRESENT_IN_ANALYSIS;LIKELY;" in output
    assert "ticker_action_flow_examples;AAA;SELL;HIGH;risk_exit;NO_PULLBACK;NOT_READY;9;1" in output


def test_export_mapping_gap_likely_when_json_actions_missing_too(tmp_path, capsys):
    dashboard_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    enrichment_json = tmp_path / "enrichment.json"
    run_id = _persist(
        dashboard_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": None}], action_summary_rows=[]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "action": "SELL",
                "severity": "HIGH",
                "primary_reason": "risk_exit",
                "pullback_validity": "NO_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority": 9,
                "is_watchlist": 0,
            }
        ],
    )
    _write_enrichment_json(
        enrichment_json,
        {
            "tickers": [{"ticker": "AAA", "action_label": None}],
            "action_summary": [{"action_label": None, "ticker_count": 1}],
        },
    )

    exit_code, output, _ = _run_cli(
        capsys,
        enrichment_dashboard_db=dashboard_db,
        enrichment_run_id=run_id,
        analysis_db_copy=analysis_db,
        enrichment_json=enrichment_json,
    )

    assert exit_code == 0
    assert "mapping_gap_hypothesis;EXPORT_MAPPING_GAP_LIKELY;LIKELY;" in output


def test_read_only_behavior_keeps_row_counts_unchanged(tmp_path, capsys):
    dashboard_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    run_id = _persist(
        dashboard_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": None}], action_summary_rows=[]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "action": "SELL",
                "severity": "HIGH",
                "primary_reason": "risk_exit",
                "pullback_validity": "NO_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority": 9,
                "is_watchlist": 0,
            }
        ],
    )
    with sqlite3.connect(analysis_db) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]

    exit_code, _, _ = _run_cli(
        capsys,
        enrichment_dashboard_db=dashboard_db,
        enrichment_run_id=run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    with sqlite3.connect(analysis_db) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
    assert before == after
