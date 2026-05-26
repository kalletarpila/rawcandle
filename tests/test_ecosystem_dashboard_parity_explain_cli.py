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
from dev_tools.run_ecosystem_dashboard_parity_explain import main


def _base_dashboard_input(
    *,
    report_date: str = "2026-05-22",
    watchlist_tickers: list[str] | None = None,
    ticker_symbols: list[str] | None = None,
    ticker_action: str = "WATCH",
    ticker_status: str = "READY",
    extra_market_map: list[EcosystemDashboardMarketMapInput] | None = None,
    decision_trace_tickers: list[str] | None = None,
) -> EcosystemDashboardInput:
    selected_watchlist = watchlist_tickers or ["AAA"]
    selected_tickers = ticker_symbols or list(selected_watchlist)
    trace_tickers = decision_trace_tickers or list(selected_watchlist)
    watchlist = [
        EcosystemDashboardWatchlistInput(
            ticker=ticker,
            company_name=f"{ticker} Corp",
            layer_name="Infrastructure",
            subindustry_name="AI Accelerators",
            action_bucket=ticker_action,
            action_label=ticker_action,
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
            data_status=ticker_status,
        )
        for ticker in selected_watchlist
    ]
    tickers = [
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
            action_bucket=ticker_action,
            action_label=ticker_action,
            data_status=ticker_status,
        )
        for ticker in selected_tickers
    ]
    decision_trace = [
        EcosystemDashboardDecisionTraceInput(
            ticker=ticker,
            trace_order=0,
            rule_group="daily",
            rule_name="WATCH_RULE",
            input_value="signal",
            decision=ticker_action,
            reason="momentum",
        )
        for ticker in trace_tickers
    ]
    market_map = [
        EcosystemDashboardMarketMapInput(
            layer_order=0,
            subindustry_order=0,
            layer_name="Infrastructure",
            subindustry_name="AI Accelerators",
            ticker_count=len(selected_tickers),
            watchlist_count=len(selected_watchlist),
            avg_return_5d=0.1,
            avg_return_20d=0.2,
            avg_return_60d=0.3,
            avg_trend_score=None,
            avg_action_score=None,
            dominant_action_bucket=ticker_action,
        )
    ]
    if extra_market_map:
        market_map.extend(extra_market_map)
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path="/tmp/reports/datacenter_daily_2026-05-22.md",
                source_report_type="daily",
                source_report_date=report_date,
                loaded_row_count=len(selected_tickers),
                status="OK",
            )
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket=ticker_action,
                action_label=ticker_action,
                ticker_count=len(selected_tickers),
                weight_sum=None,
                notes=None,
            )
        ],
        market_map=market_map,
        watchlist=watchlist,
        tickers=tickers,
        decision_trace=decision_trace,
        readiness="READY",
        total_parsed_rows=len(selected_tickers),
        total_parse_warnings=0,
    )


def _persist(
    db_path: Path,
    dashboard_input: EcosystemDashboardInput,
    *,
    run_id: str,
) -> str:
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
    max_examples: int = 50,
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
        "--max-examples",
        str(max_examples),
    ]
    if report_date is not None:
        argv.extend(["--report-date", report_date])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _section_data_lines(output: str, section_name: str) -> list[str]:
    lines = output.splitlines()
    marker = f"section;{section_name}"
    header_prefix = f"{section_name};"
    start = lines.index(marker)
    collected: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("section;"):
            break
        if line.startswith(header_prefix) and line != line.split(";")[0] + ";" + ";".join(line.split(";")[1:]):
            collected.append(line)
    if collected:
        return collected[1:]
    return []


def test_parity_explain_exact_match_reports_zero_only_counts(tmp_path, capsys):
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
    assert "SUMMARY ecosystem_dashboard_parity_explain.ticker_only_left=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_explain.ticker_only_right=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_explain.market_map_only_left=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_explain.market_map_only_right=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_explain.decision_trace_only_left=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_explain.decision_trace_only_right=0" in output
    assert "hypothesis_summary;WATCHLIST_PARITY_OK;LIKELY;left_watchlist=1;right_watchlist=1;watchlist_key_diff=0" in output
    assert "SUMMARY ecosystem_dashboard_parity_explain.status=OK" in output


def test_parity_explain_detects_broader_right_ticker_universe(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(watchlist_tickers=["AAA"], ticker_symbols=["AAA"]),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(watchlist_tickers=["AAA"], ticker_symbols=["AAA", "BBB"]),
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
    assert "ticker_only_right;BBB;WATCH;READY;UP;HH;BOS_UP;;" in output
    assert "hypothesis_summary;BROADER_TICKER_UNIVERSE_IN_RIGHT;LIKELY;" in output
    assert "right_only_tickers=1" in output


def test_parity_explain_watchlist_parity_is_likely_for_same_watchlist(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(left_db, _base_dashboard_input(watchlist_tickers=["AAA"]), run_id="LEFT_RUN")
    right_run_id = _persist(right_db, _base_dashboard_input(watchlist_tickers=["AAA"]), run_id="RIGHT_RUN")

    exit_code, output, _ = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
    )

    assert exit_code == 0
    assert "hypothesis_summary;WATCHLIST_PARITY_OK;LIKELY;left_watchlist=1;right_watchlist=1;watchlist_key_diff=0" in output


def test_parity_explain_market_map_scope_difference_is_likely(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(left_db, _base_dashboard_input(), run_id="LEFT_RUN")
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(
            extra_market_map=[
                EcosystemDashboardMarketMapInput(
                    layer_order=1,
                    subindustry_order=0,
                    layer_name="Infrastructure",
                    subindustry_name="Optics",
                    ticker_count=1,
                    watchlist_count=0,
                    avg_return_5d=0.2,
                    avg_return_20d=0.3,
                    avg_return_60d=0.4,
                    avg_trend_score=None,
                    avg_action_score=None,
                    dominant_action_bucket="WATCH",
                )
            ]
        ),
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
    assert "market_map_only_right;DC_ECOSYSTEM_TOTAL > Infrastructure > Optics;SUBINDUSTRY;Optics;Infrastructure;Infrastructure;Optics;WATCH;" in output
    assert "hypothesis_summary;MARKET_MAP_SCOPE_DIFF;LIKELY;market_map_only_left=0;market_map_only_right=1" in output


def test_parity_explain_extra_right_decision_trace_from_extra_tickers_is_likely(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(
            ticker_symbols=["AAA"],
            decision_trace_tickers=["AAA"],
        ),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(
            ticker_symbols=["AAA", "BBB"],
            decision_trace_tickers=["AAA", "BBB"],
        ),
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
    assert "decision_trace_only_right_summary;BBB;1;WATCH_RULE;;momentum;daily" in output
    assert "hypothesis_summary;EXTRA_RIGHT_DECISION_TRACE_FROM_EXTRA_TICKERS;LIKELY;right_only_trace_tickers=1;overlap_with_right_only_tickers=1;overlap_ratio=1.0000" in output


def test_parity_explain_common_ticker_field_drift_is_likely(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(ticker_action="BUY_NOW", ticker_status="BUY_ZONE"),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(ticker_action="WATCH", ticker_status="READY"),
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
    assert "ticker_common_field_diff_summary;action;1;AAA;BUY_NOW;WATCH" in output
    assert "ticker_common_field_diff_summary;current_status;1;AAA;BUY_ZONE;READY" in output
    assert "hypothesis_summary;COMMON_TICKER_FIELD_DRIFT;LIKELY;common_ticker_field_differences=" in output


def test_parity_explain_max_examples_limits_printed_rows_but_not_summary_counts(tmp_path, capsys):
    left_db = tmp_path / "left.db"
    right_db = tmp_path / "right.db"
    left_run_id = _persist(
        left_db,
        _base_dashboard_input(ticker_symbols=["AAA"]),
        run_id="LEFT_RUN",
    )
    right_run_id = _persist(
        right_db,
        _base_dashboard_input(ticker_symbols=["AAA", "BBB", "CCC", "DDD"]),
        run_id="RIGHT_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        left_db=left_db,
        left_run_id=left_run_id,
        right_db=right_db,
        right_run_id=right_run_id,
        max_examples=2,
    )

    assert exit_code == 0
    ticker_only_right_lines = [
        line
        for line in output.splitlines()
        if line.startswith("ticker_only_right;")
        and line
        != "ticker_only_right;ticker;action;current_status;trend_state;latest_structure_label;latest_bos_event_type;latest_reset_reason;horizons_present;is_watchlist"
    ]
    assert len(ticker_only_right_lines) == 2
    assert "SUMMARY ecosystem_dashboard_parity_explain.ticker_only_right=3" in output


def test_parity_explain_report_date_mismatch_fails_clearly(tmp_path, capsys):
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


def test_parity_explain_missing_run_id_or_db_fails_clearly(tmp_path, capsys):
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

    left_db = tmp_path / "left.db"
    _persist(left_db, _base_dashboard_input(), run_id="LEFT_RUN")
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


def test_parity_explain_command_is_read_only(tmp_path, capsys):
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
    assert "SUMMARY ecosystem_dashboard_parity_explain.status=OK" in output
