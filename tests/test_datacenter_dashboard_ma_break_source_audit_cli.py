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
from dev_tools.run_datacenter_dashboard_ma_break_source_audit import main


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
                rule_group=row.get("rule_group", "rolling 2d"),
                rule_name=row.get("rule_name", "RULE"),
                input_value=row.get("matched_value", "signal"),
                decision=row.get("action"),
                reason=row.get("field_name", "reason"),
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
    source_rows: list[dict[str, object]],
    enrichment_rows: list[dict[str, object]],
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                ma_break_status TEXT,
                distance_to_ema20_pct REAL,
                close_below_ema20 INTEGER,
                return_10d REAL,
                return_10d_lt_minus_8pct INTEGER,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                ma_break_status TEXT,
                distance_to_ema20_pct REAL,
                close_below_ema20 INTEGER,
                return_10d REAL,
                return_10d_lt_minus_8pct INTEGER,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT
            )
            """
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
        for row in enrichment_rows:
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
        "50",
    ]
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_reports_trace_ma_break_detection(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "SELL"}],
            trace_rows=[
                {
                    "ticker": "AAA",
                    "action": "SELL",
                    "rule_name": "SELL_SMA50_CONFIRMED_BREAK",
                    "matched_value": "SMA50_CONFIRMED_BREAK",
                    "field_name": "ma_break_status",
                }
            ],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "REDUCE"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_db(
        analysis_db,
        source_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "ma_break_status": "SMA50_CONFIRMED_BREAK"}],
        enrichment_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "ma_break_status": None}],
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
    assert "reports_trace_matches;AAA;SELL_SMA50_CONFIRMED_BREAK;" in output
    assert "hypothesis_summary;REPORTS_SELL_USES_MA_BREAK;LIKELY;" in output


def test_hard_sell_token_detection(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "SELL"}],
            trace_rows=[
                {
                    "ticker": "AAA",
                    "action": "SELL",
                    "rule_name": "SELL_HARD_TOKEN",
                    "matched_value": "return_10d_lt_minus_8pct",
                    "field_name": "raw_fields.primary_reason",
                }
            ],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "REDUCE"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_db(
        analysis_db,
        source_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "return_10d_lt_minus_8pct": 1}],
        enrichment_rows=[{"signal_date": "2026-05-22", "ticker": "AAA"}],
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
    assert "hypothesis_summary;REPORTS_SELL_USES_HARD_SELL_TOKEN;LIKELY;" in output


def test_analysis_source_has_ma_break_status(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "SELL"}],
            trace_rows=[{"ticker": "AAA", "action": "SELL", "rule_name": "SELL_SMA50_CONFIRMED_BREAK", "matched_value": "SMA50_CONFIRMED_BREAK"}],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "REDUCE"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_db(
        analysis_db,
        source_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "ma_break_status": "SMA50_CONFIRMED_BREAK"}],
        enrichment_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "ma_break_status": None}],
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
    assert "ma_break_candidate_sources;dc_ticker_swing_signal_daily.ma_break_status;1;1;" in output
    assert "hypothesis_summary;ANALYSIS_HAS_MA_BREAK_SOURCE;LIKELY;" in output


def test_needs_new_ma_break_enrichment_when_reports_use_ma_break_but_source_lacks_it(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "SELL"}],
            trace_rows=[
                {
                    "ticker": "AAA",
                    "action": "SELL",
                    "rule_name": "SELL_SMA50_CONFIRMED_BREAK",
                    "matched_value": "SMA50_CONFIRMED_BREAK",
                    "field_name": "ma_break_status",
                }
            ],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "REDUCE"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_db(
        analysis_db,
        source_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "return_10d": -9.0}],
        enrichment_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "ma_break_status": None}],
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
    assert "hypothesis_summary;NEEDS_NEW_MA_BREAK_ENRICHMENT;LIKELY;" in output
    assert "SUMMARY datacenter_dashboard_ma_break_source_audit.needs_new_ma_break_enrichment=1" in output


def test_read_only_behavior(tmp_path, capsys):
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
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "REDUCE"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_db(
        analysis_db,
        source_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "ma_break_status": None}],
        enrichment_rows=[{"signal_date": "2026-05-22", "ticker": "AAA", "ma_break_status": None}],
    )

    with sqlite3.connect(analysis_db) as conn:
        before_source = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
        before_enrichment = conn.execute("SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily").fetchone()[0]

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
    assert "SUMMARY datacenter_dashboard_ma_break_source_audit.status=OK" in output

    with sqlite3.connect(analysis_db) as conn:
        after_source = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
        after_enrichment = conn.execute("SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily").fetchone()[0]

    assert before_source == after_source
    assert before_enrichment == after_enrichment
