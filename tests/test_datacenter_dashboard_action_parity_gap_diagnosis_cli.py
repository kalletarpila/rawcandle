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
)
from dev_tools.ecosystem_dashboard_persistence import persist_ecosystem_dashboard_input
from dev_tools.run_datacenter_dashboard_action_parity_gap_diagnosis import main


def _dashboard_input(
    *,
    report_date: str = "2026-05-22",
    ticker_rows: list[dict[str, object]],
) -> EcosystemDashboardInput:
    action_counts: dict[str, int] = {}
    for row in ticker_rows:
        action = str(row.get("action") or "").strip()
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
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
            for action, count in sorted(action_counts.items())
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=0,
                subindustry_order=0,
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                ticker_count=len(ticker_rows),
                watchlist_count=0,
                avg_return_5d=0.1,
                avg_return_20d=0.2,
                avg_return_60d=0.3,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=next(iter(action_counts), None),
            )
        ],
        watchlist=[],
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
                reason=row.get("primary_reason"),
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
                primary_reason TEXT,
                current_status TEXT,
                daily_status TEXT,
                ma_break_status TEXT,
                freshness_status TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                exit_risk_severity TEXT,
                high_exit_risk_days_count INTEGER,
                rolling_2d_status TEXT,
                rolling_5d_status TEXT,
                rolling_30d_status TEXT,
                pullback_validity TEXT,
                entry_readiness TEXT,
                candidate_priority INTEGER
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


def _run_cli(
    capsys,
    *,
    reports_db: Path,
    reports_run_id: str,
    enrichment_db: Path,
    enrichment_run_id: str,
    analysis_db_copy: Path,
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
        "50",
    ]
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_confusion_matrix_contains_expected_rows(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL"},
                {"ticker": "BBB", "action": "REDUCE"},
            ]
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "NEUTRAL"},
                {"ticker": "BBB", "action": "REDUCE"},
            ]
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {"signal_date": "2026-05-22", "taxonomy_version": "DC_TAXONOMY_FULL_V1", "ticker": "AAA"},
            {"signal_date": "2026-05-22", "taxonomy_version": "DC_TAXONOMY_FULL_V1", "ticker": "BBB"},
        ],
    )

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "action_confusion_matrix;SELL;NEUTRAL;1" in output
    assert "action_confusion_matrix;REDUCE;REDUCE;1" in output


def test_major_gap_examples_include_analysis_fields(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "SELL", "primary_reason": "risk"}]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "NEUTRAL"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "daily_status": "HIGH_EXIT_RISK",
                "current_status": "HIGH_EXIT_RISK",
                "latest_bos_event_type": "BOS_DOWN",
                "exit_risk_severity": "HIGH",
            }
        ],
    )

    _, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert "major_gap_examples;AAA;SELL;NEUTRAL;" in output
    assert "HIGH_EXIT_RISK" in output
    assert "BOS_DOWN" in output


def test_missing_signal_summary_counts_missing_rolling_2d_for_sell_neutral_gap(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "SELL"}]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "NEUTRAL"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {"signal_date": "2026-05-22", "taxonomy_version": "DC_TAXONOMY_FULL_V1", "ticker": "AAA"}
        ],
    )

    _, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert (
        "missing_signal_summary;REPORTS_SELL_ENRICHMENT_NEUTRAL;rolling_2d_status;1;1;100.0000"
        in output
    )


def test_missing_rolling_2d_hypothesis_is_likely(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL"},
                {"ticker": "BBB", "action": "SELL"},
            ]
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "NEUTRAL"},
                {"ticker": "BBB", "action": "REDUCE"},
            ]
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {"signal_date": "2026-05-22", "taxonomy_version": "DC_TAXONOMY_FULL_V1", "ticker": "AAA"},
            {"signal_date": "2026-05-22", "taxonomy_version": "DC_TAXONOMY_FULL_V1", "ticker": "BBB"},
        ],
    )

    _, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert (
        "hypothesis_summary;MISSING_ROLLING_2D_SIGNALS_CAUSES_SELL_GAP;LIKELY;"
        in output
    )


def test_missing_high_exit_risk_days_hypothesis_is_likely(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "TIGHTEN_STOP"}]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "REDUCE"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "daily_status": "HIGH_EXIT_RISK",
            }
        ],
    )

    _, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert (
        "hypothesis_summary;MISSING_HIGH_EXIT_RISK_DAYS_CAUSES_TIGHTEN_STOP_GAP;LIKELY;"
        in output
    )


def test_crgy_reports_only_is_excluded_from_gap_analysis(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL"},
                {"ticker": "CRGY", "action": "SELL"},
            ]
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "NEUTRAL"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [{"signal_date": "2026-05-22", "taxonomy_version": "DC_TAXONOMY_FULL_V1", "ticker": "AAA"}],
    )

    _, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert "major_gap_examples;CRGY;" not in output
    assert "SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.common_tickers=1" in output


def test_read_only_behavior_leaves_input_row_counts_unchanged(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "SELL"}]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "NEUTRAL"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        [{"signal_date": "2026-05-22", "taxonomy_version": "DC_TAXONOMY_FULL_V1", "ticker": "AAA"}],
    )
    with sqlite3.connect(analysis_db) as conn:
        before = conn.execute("SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily").fetchone()[0]

    exit_code, _, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    with sqlite3.connect(analysis_db) as conn:
        after = conn.execute("SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily").fetchone()[0]
    assert exit_code == 0
    assert before == after
