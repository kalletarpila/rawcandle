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
from dev_tools.run_datacenter_dashboard_final_action_residual_diagnosis import (
    REDUCE_TO_TIGHTEN_STOP,
    SELL_TO_REDUCE,
    main,
)


def _dashboard_input(
    *,
    report_date: str = "2026-05-22",
    ticker_rows: list[dict[str, object]],
    trace_rows: list[dict[str, object]] | None = None,
) -> EcosystemDashboardInput:
    action_counts: dict[str, int] = {}
    for row in ticker_rows:
        action = str(row.get("action") or "").strip()
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
    traces = trace_rows or []
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
                rule_group=row.get("rule_group", "daily"),
                rule_name=row.get("rule_name", "RULE"),
                input_value=row.get("input_value", "signal"),
                decision=row.get("action"),
                reason=row.get("reason", "reason"),
            )
            for index, row in enumerate(traces)
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


def _create_analysis_db(
    path: Path,
    *,
    enrichment_rows: list[dict[str, object]],
    source_rows: list[dict[str, object]],
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                ma_break_status TEXT,
                window_status_2d TEXT,
                high_exit_risk_days_count INTEGER,
                return_10d REAL,
                distance_to_ema20_pct REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                return_10d REAL,
                distance_to_ema20_pct REAL
            )
            """
        )
        for row in enrichment_rows:
            columns = sorted(row)
            conn.execute(
                f"""
                INSERT INTO dc_dashboard_ticker_enrichment_daily ({", ".join(columns)})
                VALUES ({", ".join("?" for _ in columns)})
                """,
                tuple(row[column] for column in columns),
            )
        for row in source_rows:
            columns = sorted(row)
            conn.execute(
                f"""
                INSERT INTO dc_ticker_swing_signal_daily ({", ".join(columns)})
                VALUES ({", ".join("?" for _ in columns)})
                """,
                tuple(row[column] for column in columns),
            )


def _run_cli(
    capsys,
    *,
    analysis_db: Path,
    reports_db: Path,
    reports_run_id: str,
    enrichment_db: Path,
    enrichment_run_id: str,
):
    argv = [
        "--analysis-db",
        str(analysis_db),
        "--reports-dashboard-db",
        str(reports_db),
        "--reports-run-id",
        reports_run_id,
        "--enrichment-dashboard-db",
        str(enrichment_db),
        "--enrichment-run-id",
        enrichment_run_id,
        "--ecosystem-code",
        "DATACENTER",
        "--report-date",
        "2026-05-22",
        "--max-examples",
        "100",
    ]
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _build_fixture(tmp_path: Path):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL"},
                {"ticker": "BBB", "action": "REDUCE"},
                {"ticker": "CCC", "action": "TIGHTEN_STOP"},
                {"ticker": "DDD", "action": "TIGHTEN_STOP"},
            ],
            trace_rows=[
                {
                    "ticker": "AAA",
                    "action": "SELL",
                    "rule_name": "SELL_SMA50_CONFIRMED_BREAK",
                    "input_value": "SMA50_CONFIRMED_BREAK",
                    "reason": "ma_break_status",
                    "rule_group": "daily",
                },
                {
                    "ticker": "BBB",
                    "action": "REDUCE",
                    "rule_name": "REDUCE_SIGNAL",
                    "input_value": "HIGH_EXIT_RISK",
                    "reason": "exit_risk",
                    "rule_group": "daily",
                },
                {
                    "ticker": "CCC",
                    "action": "TIGHTEN_STOP",
                    "rule_name": "TIGHTEN_STOP",
                    "input_value": "high_exit_risk_days_count>=1",
                    "reason": "high_exit",
                    "rule_group": "rolling 30d",
                },
                {
                    "ticker": "DDD",
                    "action": "TIGHTEN_STOP",
                    "rule_name": "TIGHTEN_STOP",
                    "input_value": "high_exit_risk_days_count>=1",
                    "reason": "high_exit",
                    "rule_group": "rolling 30d",
                },
            ],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "REDUCE"},
                {"ticker": "BBB", "action": "TIGHTEN_STOP"},
                {"ticker": "CCC", "action": "TIGHTEN_STOP"},
                {"ticker": "DDD", "action": "TIGHTEN_STOP"},
            ],
            trace_rows=[
                {
                    "ticker": "AAA",
                    "action": "REDUCE",
                    "rule_name": "REDUCE_SIGNAL",
                    "input_value": "WATCH_PRESSURE",
                    "reason": "rolling_2d_status",
                    "rule_group": "rolling 2d",
                },
                {
                    "ticker": "BBB",
                    "action": "TIGHTEN_STOP",
                    "rule_name": "TIGHTEN_STOP",
                    "input_value": "high_exit_risk_days_count>=1",
                    "reason": "high_exit",
                    "rule_group": "rolling 30d",
                },
            ],
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_db(
        analysis_db,
        enrichment_rows=[
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "ma_break_status": "OK",
                "window_status_2d": "",
                "high_exit_risk_days_count": 0,
                "return_10d": -0.02,
                "distance_to_ema20_pct": 0.01,
            },
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "BBB",
                "ma_break_status": "OK",
                "window_status_2d": "",
                "high_exit_risk_days_count": 5,
                "return_10d": 0.01,
                "distance_to_ema20_pct": 0.02,
            },
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "CCC",
                "ma_break_status": "OK",
                "window_status_2d": "",
                "high_exit_risk_days_count": 3,
                "return_10d": 0.01,
                "distance_to_ema20_pct": 0.02,
            },
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "DDD",
                "ma_break_status": "OK",
                "window_status_2d": "",
                "high_exit_risk_days_count": 2,
                "return_10d": 0.01,
                "distance_to_ema20_pct": 0.02,
            },
        ],
        source_rows=[
            {
                "signal_date": "2026-05-21",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "BBB",
                "exit_risk_signal": 0,
                "exit_risk_severity": "MEDIUM",
                "return_10d": 0.0,
                "distance_to_ema20_pct": 0.0,
            },
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "BBB",
                "exit_risk_signal": 0,
                "exit_risk_severity": "",
                "return_10d": 0.0,
                "distance_to_ema20_pct": 0.0,
            },
            {
                "signal_date": "2026-05-20",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "CCC",
                "exit_risk_signal": 1,
                "exit_risk_severity": "HIGH",
                "return_10d": 0.0,
                "distance_to_ema20_pct": 0.0,
            },
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "CCC",
                "exit_risk_signal": 0,
                "exit_risk_severity": "",
                "return_10d": 0.0,
                "distance_to_ema20_pct": 0.0,
            },
            {
                "signal_date": "2026-05-20",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "DDD",
                "exit_risk_signal": 0,
                "exit_risk_severity": "HIGH",
                "return_10d": 0.0,
                "distance_to_ema20_pct": 0.0,
            },
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "DDD",
                "exit_risk_signal": 0,
                "exit_risk_severity": "",
                "return_10d": 0.0,
                "distance_to_ema20_pct": 0.0,
            },
        ],
    )
    return analysis_db, reports_db, reports_run_id, enrichment_db, enrichment_run_id


def test_counts_and_ma_break_gap_hypothesis(tmp_path, capsys):
    analysis_db, reports_db, reports_run_id, enrichment_db, enrichment_run_id = _build_fixture(
        tmp_path
    )

    exit_code, output, error = _run_cli(
        capsys,
        analysis_db=analysis_db,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert error == ""
    assert f"residual_gap_counts;{SELL_TO_REDUCE};1" in output
    assert f"residual_gap_counts;{REDUCE_TO_TIGHTEN_STOP};1" in output
    assert (
        "hypothesis_summary;SELL_TO_REDUCE_REQUIRES_TRUE_MA_BREAK_SOURCE;LIKELY;"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.sell_to_reduce_ma_break_gap=1"
        in output
    )


def test_reduce_to_tighten_medium_count_hypothesis(tmp_path, capsys):
    analysis_db, reports_db, reports_run_id, enrichment_db, enrichment_run_id = _build_fixture(
        tmp_path
    )

    exit_code, output, error = _run_cli(
        capsys,
        analysis_db=analysis_db,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert error == ""
    assert (
        "hypothesis_summary;REDUCE_TO_TIGHTEN_CAUSED_BY_MEDIUM_COUNT;LIKELY;"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.reduce_to_tighten_medium_only=1"
        in output
    )


def test_high_only_count_would_match_reports_better_is_deterministic(tmp_path, capsys):
    analysis_db, reports_db, reports_run_id, enrichment_db, enrichment_run_id = _build_fixture(
        tmp_path
    )

    exit_code, output, error = _run_cli(
        capsys,
        analysis_db=analysis_db,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert error == ""
    assert (
        "hypothesis_summary;HIGH_ONLY_COUNT_WOULD_MATCH_REPORTS_BETTER;LIKELY;"
        in output
    )


def test_read_only_behavior(tmp_path, capsys):
    analysis_db, reports_db, reports_run_id, enrichment_db, enrichment_run_id = _build_fixture(
        tmp_path
    )
    with sqlite3.connect(analysis_db) as conn:
        before_enrichment = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
        before_source = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily"
        ).fetchone()[0]

    exit_code, output, error = _run_cli(
        capsys,
        analysis_db=analysis_db,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.status=OK" in output
    with sqlite3.connect(analysis_db) as conn:
        after_enrichment = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
        after_source = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily"
        ).fetchone()[0]
    assert before_enrichment == after_enrichment
    assert before_source == after_source
