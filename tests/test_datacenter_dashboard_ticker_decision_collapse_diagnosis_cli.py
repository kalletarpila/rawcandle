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
from dev_tools.run_datacenter_dashboard_ticker_decision_collapse_diagnosis import main


def _dashboard_input(
    *,
    report_date: str = "2026-05-22",
    ticker_actions: dict[str, str],
    watchlist_tickers: list[str] | None = None,
) -> EcosystemDashboardInput:
    watchlist = watchlist_tickers or []
    action_counts: dict[str, int] = {}
    for action in ticker_actions.values():
        action_counts[action] = action_counts.get(action, 0) + 1
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path="/tmp/report.md",
                source_report_type="daily",
                source_report_date=report_date,
                loaded_row_count=len(ticker_actions),
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
            for action, count in sorted(action_counts.items())
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=0,
                subindustry_order=0,
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                ticker_count=len(ticker_actions),
                watchlist_count=len(watchlist),
                avg_return_5d=0.1,
                avg_return_20d=0.2,
                avg_return_60d=0.3,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=next(iter(action_counts)) if action_counts else None,
            )
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker=ticker,
                company_name=f"{ticker} Corp",
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                action_bucket=ticker_actions.get(ticker),
                action_label=ticker_actions.get(ticker),
                watchlist_reason="momentum",
                last_close=10.0,
                return_5d=1.0,
                return_20d=2.0,
                return_60d=3.0,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason=None,
                bullish_candle_signal=1,
                bullish_divergence_signal=0,
                hidden_bullish_divergence_signal=0,
                data_status="READY",
            )
            for ticker in watchlist
        ],
        tickers=[
            EcosystemDashboardTickerStatusInput(
                ticker=ticker,
                company_name=f"{ticker} Corp",
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
                bullish_candle_signal=1,
                bullish_divergence_signal=0,
                hidden_bullish_divergence_signal=0,
                action_bucket=action,
                action_label=action,
                data_status="READY",
            )
            for ticker, action in ticker_actions.items()
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker=ticker,
                trace_order=0,
                rule_group="daily",
                rule_name="RULE",
                input_value="signal",
                decision=action,
                reason="momentum",
            )
            for ticker, action in ticker_actions.items()
        ],
        readiness="READY",
        total_parsed_rows=len(ticker_actions),
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
                current_status TEXT,
                pullback_validity TEXT,
                entry_readiness TEXT,
                candidate_priority INTEGER,
                candidate_priority_label TEXT,
                horizons_present TEXT,
                trend_state TEXT,
                latest_structure_label TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                ma_break_status TEXT,
                freshness_status TEXT,
                daily_status TEXT,
                rolling_2d_status TEXT,
                rolling_5d_status TEXT,
                rolling_30d_status TEXT,
                high_exit_risk_days_count INTEGER,
                blocking_reasons TEXT
            )
            """
        )
        for row in rows:
            columns = sorted(row)
            placeholders = ", ".join("?" for _ in columns)
            conn.execute(
                f"""
                INSERT INTO dc_dashboard_ticker_enrichment_daily (
                    {", ".join(columns)}
                ) VALUES ({placeholders})
                """,
                tuple(row[column] for column in columns),
            )


def _run_cli(
    capsys,
    *,
    reports_db: Path,
    reports_run_id: str,
    enrichment_db: Path,
    enrichment_run_id: str,
    analysis_db_copy: Path,
    tickers: str | None = None,
    max_examples: int = 25,
):
    argv = [
        "--reports-dashboard-db",
        str(reports_db),
        "--reports-run-id",
        reports_run_id,
        "--enrichment-dashboard-db",
        str(enrichment_db),
        "--enrichment-run-id",
        enrichment_run_id,
        "--analysis-db-copy",
        str(analysis_db_copy),
        "--ecosystem-code",
        "DATACENTER",
        "--report-date",
        "2026-05-22",
        "--max-examples",
        str(max_examples),
    ]
    if tickers is not None:
        argv.extend(["--tickers", tickers])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_basic_diagnosis_outputs_selected_ticker_and_adapter_rows(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_actions={"AAA": "SELL"}),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_actions={"AAA": "NEUTRAL"}),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "current_status": "NEUTRAL",
                "trend_state": "UP",
                "latest_structure_label": "HH",
                "latest_bos_event_type": "BOS_UP",
            }
        ],
    )

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
        tickers="AAA",
    )

    assert exit_code == 0
    assert error == ""
    assert "selected_tickers;AAA;EXPLICIT_REQUEST;SELL;NEUTRAL" in output
    assert "adapter_input_rows;AAA;1;daily;" in output
    assert "adapter_decision_output;AAA;NEUTRAL;" in output
    assert "SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.status=OK" in output


def test_auto_selection_selects_non_neutral_reports_vs_neutral_enrichment_and_excludes_crgy(
    tmp_path, capsys
):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_actions={
                "AAA": "SELL",
                "BBB": "REDUCE",
                "CCC": "TIGHTEN_STOP",
                "CRGY": "SELL",
            }
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_actions={
                "AAA": "NEUTRAL",
                "BBB": "NEUTRAL",
                "CCC": "NEUTRAL",
                "CRGY": "NEUTRAL",
            }
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": ticker,
                "current_status": "NEUTRAL",
            }
            for ticker in ("AAA", "BBB", "CCC", "CRGY")
        ],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    assert "selected_tickers;AAA;REPORTS_SELL_ENRICHMENT_NEUTRAL;SELL;NEUTRAL" in output
    assert "selected_tickers;BBB;REPORTS_REDUCE_ENRICHMENT_NEUTRAL;REDUCE;NEUTRAL" in output
    assert (
        "selected_tickers;CCC;REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL;TIGHTEN_STOP;NEUTRAL"
        in output
    )
    assert "selected_tickers;CRGY;" not in output


def test_missing_rolling_horizon_diagnosis_is_likely(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_actions={"AAA": "SELL"}),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_actions={"AAA": "NEUTRAL"}),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "current_status": "NEUTRAL",
            }
        ],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
        tickers="AAA",
    )

    assert exit_code == 0
    assert "missing_signal_diagnosis;AAA;NO_ROLLING_HORIZON_INPUTS;LIKELY;" in output


def test_weak_raw_status_mapping_diagnosis_is_likely(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_actions={"AAA": "SELL"}),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_actions={"AAA": "NEUTRAL"}),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "current_status": "NEUTRAL",
            }
        ],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
        tickers="AAA",
    )

    assert exit_code == 0
    assert "missing_signal_diagnosis;AAA;NO_RAW_ACTION_OR_STATUS_TOKENS;LIKELY;" in output


def test_adapter_neutral_hypothesis_is_likely(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_actions={"AAA": "SELL"}),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_actions={"AAA": "NEUTRAL"}),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "current_status": "NEUTRAL",
            }
        ],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
        tickers="AAA",
    )

    assert exit_code == 0
    assert "hypothesis_summary;ADAPTER_DECISION_MATCHES_ENRICHMENT_NEUTRAL;LIKELY;" in output


def test_missing_db_or_run_id_fails_clearly(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_actions={"AAA": "SELL"}),
        run_id="REPORTS_RUN",
    )
    _persist(
        enrichment_db,
        _dashboard_input(ticker_actions={"AAA": "NEUTRAL"}),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "current_status": "NEUTRAL",
            }
        ],
    )

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id="MISSING_RUN",
        analysis_db_copy=analysis_db,
        tickers="AAA",
    )

    assert exit_code == 1
    assert output == ""
    assert "ERROR:" in error
    assert "status=OK" not in error


def test_read_only_behavior_keeps_analysis_row_count_unchanged(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_actions={"AAA": "SELL"}),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_actions={"AAA": "NEUTRAL"}),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "current_status": "NEUTRAL",
            }
        ],
    )
    with sqlite3.connect(analysis_db) as conn:
        before_count = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]

    exit_code, _, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
        tickers="AAA",
    )

    assert exit_code == 0
    with sqlite3.connect(analysis_db) as conn:
        after_count = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
    assert after_count == before_count
