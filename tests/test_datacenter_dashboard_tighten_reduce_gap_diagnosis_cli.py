from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardDecisionTraceInput,
    EcosystemDashboardInput,
    EcosystemDashboardMarketMapInput,
    EcosystemDashboardSourceReportInput,
    EcosystemDashboardTickerStatusInput,
)
from dev_tools.ecosystem_dashboard_persistence import persist_ecosystem_dashboard_input
from dev_tools.run_datacenter_dashboard_tighten_reduce_gap_diagnosis import main


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
                trace_order=index,
                rule_group="daily",
                rule_name=row.get("rule_name", "RULE"),
                input_value=row.get("matched_token", "signal"),
                decision=row.get("action"),
                reason=row.get("primary_reason", "reason"),
            )
            for row in ticker_rows
            for index in range(1)
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
                current_status TEXT,
                daily_status TEXT,
                rolling_2d_status TEXT,
                rolling_5d_status TEXT,
                rolling_30d_status TEXT,
                high_exit_risk_days_count INTEGER,
                ma_break_status TEXT,
                freshness_status TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                pullback_validity TEXT,
                entry_readiness TEXT,
                candidate_priority INTEGER,
                candidate_priority_label TEXT,
                horizons_present TEXT
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


def test_gap_group_counts_are_reported(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "TIGHTEN_STOP"},
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
    assert "gap_group_counts;REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL;1" in output
    assert "gap_group_counts;REPORTS_SELL_ENRICHMENT_REDUCE;1" in output


def test_field_comparison_and_adapter_rows_include_high_exit_risk_days_count(tmp_path, capsys):
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
                "rolling_2d_status": "WATCH_PRESSURE",
                "high_exit_risk_days_count": 1,
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

    assert "field_comparison;AAA;high_exit_risk_days_count;" in output
    assert "adapter_row_inputs;AAA;2;rolling 2d" in output or "adapter_row_inputs;AAA;1;rolling 2d" in output
    assert ";1;" in output


def test_high_exit_count_visible_to_adapter_hypothesis_is_likely(tmp_path, capsys):
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
                "rolling_2d_status": "WATCH_PRESSURE",
                "high_exit_risk_days_count": 1,
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

    assert "hypothesis_summary;HIGH_EXIT_COUNT_VISIBLE_TO_ADAPTER;LIKELY;" in output


def test_persisted_vs_adapter_difference_hypothesis_works(tmp_path, monkeypatch, capsys):
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
                "rolling_2d_status": "WATCH_PRESSURE",
                "high_exit_risk_days_count": 1,
            }
        ],
    )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_tighten_reduce_gap_diagnosis.build_decisions_from_ticker_enrichment_rows",
        lambda rows: SimpleNamespace(
            decisions=[
                SimpleNamespace(
                    ticker="AAA",
                    action="TIGHTEN_STOP",
                    primary_reason="HIGH_EXIT_RISK_DAYS_PRESENT",
                    pullback_validity=None,
                    entry_readiness=None,
                    candidate_priority=None,
                    horizons_present=["rolling 2d"],
                    decision_trace=[],
                )
            ]
        ),
    )

    _, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert "hypothesis_summary;PERSISTED_ENRICHMENT_ACTION_DIFFERS_FROM_ADAPTER;LIKELY;" in output


def test_read_only_behavior_keeps_row_counts_unchanged(tmp_path, capsys):
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
                "high_exit_risk_days_count": 1,
            }
        ],
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
