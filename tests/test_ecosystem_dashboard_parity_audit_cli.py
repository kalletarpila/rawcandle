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
from dev_tools.run_ecosystem_dashboard_parity_audit import main


def _base_dashboard_input(
    *,
    report_date: str = "2026-05-22",
    watchlist_ticker: str = "AAA",
    ticker_symbols: list[str] | None = None,
    watchlist_action: str = "WATCH",
    ticker_action: str = "WATCH",
) -> EcosystemDashboardInput:
    symbols = ticker_symbols or [watchlist_ticker]
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path="/tmp/reports/datacenter_daily_2026-05-22.md",
                source_report_type="daily",
                source_report_date=report_date,
                loaded_row_count=1,
                status="OK",
            )
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket=watchlist_action,
                action_label=watchlist_action,
                ticker_count=len(symbols),
                weight_sum=None,
                notes=None,
            )
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=0,
                subindustry_order=0,
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                ticker_count=len(symbols),
                watchlist_count=1,
                avg_return_5d=0.1,
                avg_return_20d=0.2,
                avg_return_60d=0.3,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=watchlist_action,
            )
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker=watchlist_ticker,
                company_name="Alpha",
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                action_bucket=watchlist_action,
                action_label=watchlist_action,
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
        ],
        tickers=[
            EcosystemDashboardTickerStatusInput(
                ticker=symbol,
                company_name=f"{symbol} Corp",
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
                action_bucket=ticker_action,
                action_label=ticker_action,
                data_status="READY",
            )
            for symbol in symbols
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker=watchlist_ticker,
                trace_order=0,
                rule_group="daily",
                rule_name="WATCH_RULE",
                input_value="signal",
                decision=watchlist_action,
                reason="momentum",
            )
        ],
        readiness="READY",
        total_parsed_rows=len(symbols),
        total_parse_warnings=0,
    )


def _persist(db_path: Path, dashboard_input: EcosystemDashboardInput, *, run_id: str) -> str:
    return persist_ecosystem_dashboard_input(
        dashboard_db=str(db_path),
        dashboard_input=dashboard_input,
        mode="insert",
        run_id=run_id,
    )


def _run_cli(
    capsys,
    *,
    left_db: Path,
    left_run_id: str,
    right_db: Path,
    right_run_id: str,
    report_date: str | None = None,
    left_label: str = "reports",
    right_label: str = "structured",
):
    argv = [
        "--left-dashboard-db",
        str(left_db),
        "--left-run-id",
        left_run_id,
        "--right-dashboard-db",
        str(right_db),
        "--right-run-id",
        right_run_id,
        "--ecosystem-code",
        "DATACENTER",
        "--left-label",
        left_label,
        "--right-label",
        right_label,
    ]
    if report_date is not None:
        argv.extend(["--report-date", report_date])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _data_lines(output: str, prefix: str) -> list[str]:
    return [
        line
        for line in output.splitlines()
        if line.startswith(prefix) and not line.endswith(prefix.split(";")[0])
    ]


def test_parity_audit_exact_match_reports_all_match(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(left_db, _base_dashboard_input(), run_id="LEFT_RUN")
    right_run_id = _persist(right_db, _base_dashboard_input(), run_id="RIGHT_RUN")

    exit_code, output, error = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
        report_date="2026-05-22",
    )

    assert exit_code == 0
    assert error == ""
    assert "section;run_summary" in output
    assert "section;section_counts" in output
    assert "section;key_differences" in output
    assert "section;field_differences" in output
    assert "section;summary" in output
    assert "section_counts;tickers;1;1;0;MATCH" in output
    assert "SUMMARY ecosystem_dashboard_parity_audit.key_differences=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_audit.field_differences=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_audit.status=OK" in output


def test_parity_audit_detects_count_differences(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(ticker_symbols=["AAA"]),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(ticker_symbols=["AAA", "BBB"]),
        run_id="RIGHT_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 0
    assert "section_counts;tickers;1;2;1;DIFF" in output
    assert "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=" in output
    assert "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=0" not in output


def test_parity_audit_detects_key_differences(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(watchlist_ticker="AAA", ticker_symbols=["AAA"]),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(watchlist_ticker="BBB", ticker_symbols=["BBB"]),
        run_id="RIGHT_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 0
    assert "key_differences;watchlist;ONLY_LEFT;AAA" in output
    assert "key_differences;watchlist;ONLY_RIGHT;BBB" in output
    assert "key_differences;tickers;ONLY_LEFT;AAA" in output
    assert "key_differences;tickers;ONLY_RIGHT;BBB" in output


def test_parity_audit_detects_field_differences_for_common_ticker(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(watchlist_action="BUY_NOW", ticker_action="BUY_NOW"),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(watchlist_action="WATCH", ticker_action="WATCH"),
        run_id="RIGHT_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 0
    assert "field_differences;watchlist;AAA;action;BUY_NOW;WATCH" in output
    assert "field_differences;tickers;AAA;action;BUY_NOW;WATCH" in output


def test_parity_audit_report_date_safety_check_fails_on_mismatch(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(left_db, _base_dashboard_input(report_date="2026-05-22"), run_id="LEFT_RUN")
    right_run_id = _persist(right_db, _base_dashboard_input(report_date="2026-05-21"), run_id="RIGHT_RUN")

    exit_code, output, error = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
        report_date="2026-05-22",
    )

    assert exit_code == 1
    assert output == ""
    assert "report_date mismatch" in error
    assert "status=OK" not in error


def test_parity_audit_missing_db_fails_clearly(tmp_path, capsys):
    right_db = tmp_path / "right.db"
    right_run_id = _persist(right_db, _base_dashboard_input(), run_id="RIGHT_RUN")

    exit_code, output, error = _run_cli(
        capsys,
        left_db=tmp_path / "missing.db",
        left_run_id="LEFT_RUN",
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 1
    assert output == ""
    assert "dashboard_db not found" in error


def test_parity_audit_missing_run_id_fails_clearly(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    _persist(left_db, _base_dashboard_input(), run_id="LEFT_RUN")
    right_run_id = _persist(right_db, _base_dashboard_input(), run_id="RIGHT_RUN")

    exit_code, output, error = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id="DOES_NOT_EXIST",
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 1
    assert output == ""
    assert "run_id not found" in error


def test_parity_audit_key_differences_are_deterministically_ordered(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(watchlist_ticker="ZZZ", ticker_symbols=["ZZZ", "MMM"]),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(watchlist_ticker="AAA", ticker_symbols=["AAA", "NNN"]),
        run_id="RIGHT_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 0
    key_lines = [
        line
        for line in output.splitlines()
        if line.startswith("key_differences;") and line != "key_differences;section_name;diff_type;key"
    ]
    assert key_lines == [
        "key_differences;watchlist;ONLY_LEFT;ZZZ",
        "key_differences;watchlist;ONLY_RIGHT;AAA",
        "key_differences;tickers;ONLY_LEFT;MMM",
        "key_differences;tickers;ONLY_LEFT;ZZZ",
        "key_differences;tickers;ONLY_RIGHT;AAA",
        "key_differences;tickers;ONLY_RIGHT;NNN",
        "key_differences;decision_trace;ONLY_LEFT;ZZZ|0|WATCH_RULE",
        "key_differences;decision_trace;ONLY_RIGHT;AAA|0|WATCH_RULE",
    ]


def test_parity_audit_does_not_mutate_or_render_anything(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(left_db, _base_dashboard_input(), run_id="LEFT_RUN")
    right_run_id = _persist(right_db, _base_dashboard_input(), run_id="RIGHT_RUN")
    before_files = sorted(path.name for path in tmp_path.iterdir())

    def _counts(db_path: Path) -> dict[str, int]:
        with sqlite3.connect(db_path) as conn:
            return {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in [
                    "ecosystem_dashboard_runs",
                    "ecosystem_dashboard_source_reports",
                    "ecosystem_dashboard_action_summary",
                    "ecosystem_dashboard_market_map",
                    "ecosystem_dashboard_watchlist_status",
                    "ecosystem_dashboard_ticker_status",
                    "ecosystem_dashboard_decision_trace",
                ]
            }

    left_counts_before = _counts(left_db)
    right_counts_before = _counts(right_db)

    exit_code, output, error = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 0
    assert error == ""
    assert left_counts_before == _counts(left_db)
    assert right_counts_before == _counts(right_db)
    assert before_files == sorted(path.name for path in tmp_path.iterdir())
    assert not list(tmp_path.glob("*.html"))
    assert "SUMMARY ecosystem_dashboard_parity_audit.status=OK" in output