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
from dev_tools.run_datacenter_dashboard_high_exit_risk_days_source_audit import main


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
                rule_group=row.get("rule_group", "rolling 30d"),
                rule_name=row.get("rule_name", "TIGHTEN_STOP"),
                input_value=row.get("input_value", "high_exit_risk_days_count>=1"),
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
                high_exit_risk_days_count INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                exit_reason TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT
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
        "--window-days",
        "30",
        "--max-examples",
        "100",
    ]
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_window_count_detection_marks_current_day_derivation_too_weak(tmp_path, capsys):
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
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "NEUTRAL", "rule_name": "RULE", "input_value": "signal"}]
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
                "high_exit_risk_days_count": 0,
            }
        ],
        source_rows=[
            {
                "signal_date": "2026-05-20",
                "ticker": "AAA",
                "exit_risk_signal": 1,
                "exit_risk_severity": "HIGH",
                "exit_reason": "RISK",
                "latest_bos_event_type": "BOS_DOWN",
                "latest_reset_reason": "DOUBLE_BOS_DOWN",
            },
            {
                "signal_date": "2026-05-22",
                "ticker": "AAA",
                "exit_risk_signal": 0,
                "exit_risk_severity": "",
                "exit_reason": "",
                "latest_bos_event_type": "",
                "latest_reset_reason": "",
            },
        ],
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
    assert "derived_exit_counts;AAA;TIGHTEN_STOP;NEUTRAL;1;0;1;1;1;0;0;2" in output
    assert "hypothesis_summary;CURRENT_DAY_DERIVATION_TOO_WEAK;LIKELY;" in output


def test_no_source_match_hypothesis_can_be_likely(tmp_path, capsys):
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
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "NEUTRAL", "rule_name": "RULE", "input_value": "signal"}]
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
                "high_exit_risk_days_count": 0,
            }
        ],
        source_rows=[
            {
                "signal_date": "2026-05-22",
                "ticker": "AAA",
                "exit_risk_signal": 0,
                "exit_risk_severity": "",
                "exit_reason": "",
                "latest_bos_event_type": "",
                "latest_reset_reason": "",
            }
        ],
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
    assert "hypothesis_summary;NO_ANALYSIS_SOURCE_FOR_REPORTS_HIGH_EXIT;LIKELY;" in output
    assert "SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.no_analysis_source_match=1" in output


def test_latest_day_high_exit_present_is_counted(tmp_path, capsys):
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
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "NEUTRAL", "rule_name": "RULE", "input_value": "signal"}]
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
                "high_exit_risk_days_count": 0,
            }
        ],
        source_rows=[
            {
                "signal_date": "2026-05-22",
                "ticker": "AAA",
                "exit_risk_signal": 1,
                "exit_risk_severity": "HIGH",
                "exit_reason": "RISK",
                "latest_bos_event_type": "BOS_DOWN",
                "latest_reset_reason": "DOUBLE_BOS_DOWN",
            }
        ],
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
    assert "derived_exit_counts;AAA;TIGHTEN_STOP;NEUTRAL;1;0;1;1;1;1;1;1" in output
    assert "SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.latest_day_high_exit_present=1" in output


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
    _create_analysis_db(
        analysis_db,
        enrichment_rows=[
            {
                "signal_date": "2026-05-22",
                "taxonomy_version": "DC_TAXONOMY_FULL_V1",
                "ticker": "AAA",
                "high_exit_risk_days_count": 0,
            }
        ],
        source_rows=[
            {
                "signal_date": "2026-05-22",
                "ticker": "AAA",
                "exit_risk_signal": 1,
                "exit_risk_severity": "HIGH",
                "exit_reason": "RISK",
                "latest_bos_event_type": "BOS_DOWN",
                "latest_reset_reason": "DOUBLE_BOS_DOWN",
            }
        ],
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
    assert "SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.status=OK" in output

    with sqlite3.connect(analysis_db) as conn:
        after_enrichment = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
        after_source = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily"
        ).fetchone()[0]

    assert before_enrichment == after_enrichment
    assert before_source == after_source
