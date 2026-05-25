from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionBatchResult,
    DatacenterDecisionTrace,
    DatacenterTickerDecision,
)
from dev_tools.run_datacenter_dashboard_html import (
    DatacenterDashboardMarketMapRecord,
    DatacenterDashboardTickerRecord,
    DatacenterDashboardWatchlistRecord,
)
from dev_tools.run_ecosystem_dashboard_build import main


def _write_report(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _row_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _table_exists(db_path: Path, table: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table,),
        ).fetchone()
    return row is not None


def _make_reports_dir(tmp_path: Path, *, date_text: str = "2026-05-22") -> Path:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / f"datacenter_daily_{date_text}_0000_full.csv",
        "ticker;status;reason\nNVDA;SELL;close_below_ema20\n",
    )
    return reports_dir


def _stub_decision_result() -> DatacenterDecisionBatchResult:
    decisions = [
        DatacenterTickerDecision(
            ticker="NVDA",
            action="SELL",
            severity="CRITICAL",
            primary_reason="close_below_ema20",
            reasons=["close_below_ema20"],
            blocking_reasons=[],
            horizons_present=["daily", "rolling 30d"],
            horizon_statuses={"daily": "BREAKOUT_READY", "rolling 30d": "WATCH"},
            distance_to_ema20=None,
            high_exit_risk_days_count=None,
            trend_state="UP",
            latest_structure_label="HH",
            latest_bos_event_type="BOS_UP",
            latest_reset_reason=None,
            latest_bullish_signal_age_td=3,
            latest_bearish_signal_age_td=1,
            pullback_validity="NO_PULLBACK",
            pullback_reason="not a pullback",
            entry_readiness="NOT_READY",
            entry_readiness_reason="risk",
            candidate_priority=5,
            candidate_priority_label="P5_NOT_READY",
            candidate_priority_reason="risk",
            source_files=["daily.csv", "rolling30.csv"],
            decision_trace=[
                DatacenterDecisionTrace(
                    ticker="NVDA",
                    action="SELL",
                    matched_rule="SELL_HARD_TOKEN",
                    horizon="daily",
                    field_name="reason",
                    matched_token="close_below_ema20",
                    matched_value="close_below_ema20",
                    source_file="daily.csv",
                    section="Watchlist Summary",
                    row_kind="watchlist",
                )
            ],
        ),
        DatacenterTickerDecision(
            ticker="AMD",
            action="WATCH",
            severity="LOW",
            primary_reason="trend_ok",
            reasons=["trend_ok"],
            blocking_reasons=[],
            horizons_present=["rolling 30d"],
            horizon_statuses={"rolling 30d": "BUY_ZONE"},
            distance_to_ema20=None,
            high_exit_risk_days_count=None,
            trend_state="UP",
            latest_structure_label="HL",
            latest_bos_event_type="BOS_UP",
            latest_reset_reason=None,
            latest_bullish_signal_age_td=2,
            latest_bearish_signal_age_td=None,
            pullback_validity="VALID_PULLBACK",
            pullback_reason="pullback",
            entry_readiness="READY_TO_WATCH",
            entry_readiness_reason="ok",
            candidate_priority=1,
            candidate_priority_label="P1_READY_TO_WATCH",
            candidate_priority_reason="ok",
            source_files=["rolling30.csv"],
            decision_trace=[],
        ),
    ]
    return DatacenterDecisionBatchResult(
        decisions=decisions,
        action_counts={
            "SELL": 1,
            "REDUCE": 0,
            "TIGHTEN_STOP": 0,
            "BLOCKED": 0,
            "WAIT_PULLBACK": 0,
            "BUY_NOW": 0,
            "WATCH": 1,
            "NEUTRAL": 0,
        },
        pullback_counts={},
        pullback_action_counts={},
        entry_readiness_counts={},
        candidate_priority_counts={},
        warning_count=0,
        warnings=[],
    )


def _stub_market_map_rows() -> list[DatacenterDashboardMarketMapRecord]:
    return [
        DatacenterDashboardMarketMapRecord(
            market_level="ECOSYSTEM",
            name="DC_ECOSYSTEM_TOTAL",
            layer=None,
            current_status="BUY_ZONE",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BUY_ZONE",
            status_change_5d="PULLBACK -> BUY_ZONE",
            window_status_30d="BUY_ZONE",
            window_status_5d="PULLBACK",
            window_status_2d="NEUTRAL",
            overheat_risk="LOW",
            pct_above_ema20=62.5,
            pct_above_ma10=58.0,
            ema20_breadth_delta_5d=4.0,
            return_5d=0.12,
            return_10d=0.18,
            return_20d=0.25,
            return_60d=0.44,
            dow_trend_state="UP",
            dow_trend_state_age_td=8,
            latest_structure_label="HH",
            latest_structure_age_td=3,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=2,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle=None,
            latest_candle_age_td=None,
            latest_divergence=None,
            latest_divergence_age_td=None,
            latest_chart_pattern="BASE_BREAKOUT",
            latest_chart_pattern_age_td=5,
            source_horizons="daily, rolling 30d",
            source_files="daily.md, rolling30.md",
        ),
        DatacenterDashboardMarketMapRecord(
            market_level="SUBINDUSTRY",
            name="Semiconductors",
            layer="Technology",
            current_status="BUY_ZONE",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BUY_ZONE",
            status_change_5d=None,
            window_status_30d="BUY_ZONE",
            window_status_5d=None,
            window_status_2d=None,
            overheat_risk="LOW",
            pct_above_ema20=70.0,
            pct_above_ma10=65.0,
            ema20_breadth_delta_5d=5.0,
            return_5d=0.2,
            return_10d=0.3,
            return_20d=0.4,
            return_60d=0.8,
            dow_trend_state="UP",
            dow_trend_state_age_td=6,
            latest_structure_label="HL",
            latest_structure_age_td=2,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=1,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle=None,
            latest_candle_age_td=None,
            latest_divergence=None,
            latest_divergence_age_td=None,
            latest_chart_pattern="PULLBACK",
            latest_chart_pattern_age_td=2,
            source_horizons="rolling 30d",
            source_files="rolling30.md",
        ),
    ]


def _stub_watchlist_rows() -> list[DatacenterDashboardWatchlistRecord]:
    return [
        DatacenterDashboardWatchlistRecord(
            ticker="NVDA",
            action="SELL",
            severity="CRITICAL",
            primary_reason="close_below_ema20",
            current_status="BREAKOUT_READY",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BREAKOUT_READY",
            status_change_5d="PULLBACK_WINDOW -> BREAKOUT_READY",
            window_status_30d="WATCH",
            window_status_5d="PULLBACK_WINDOW",
            window_status_2d="BREAKOUT_READY",
            ma_break_status="EMA20_WARNING",
            freshness_status="FRESH_BULLISH_SIGNAL",
            trend_state="UP",
            trend_state_age_td=12,
            latest_structure_label="HH",
            latest_structure_age_td=3,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=2,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle="Hammer",
            latest_candle_age_td=4,
            latest_divergence="Bearish Divergence",
            latest_divergence_age_td=2,
            latest_chart_pattern="BASE_BREAKOUT",
            latest_chart_pattern_age_td=5,
            pullback_validity="NO_PULLBACK",
            entry_readiness="NOT_READY",
            candidate_priority=5,
            candidate_priority_label="P5_NOT_READY",
            daily_status="BREAKOUT_READY",
            rolling_2d_status=None,
            rolling_5d_status=None,
            rolling_30d_status="WATCH",
            horizons_present="daily, rolling 30d",
            source_files=2,
        )
    ]


def _stub_ticker_rows() -> list[DatacenterDashboardTickerRecord]:
    return [
        DatacenterDashboardTickerRecord(
            ticker="AMD",
            action="WATCH",
            severity="LOW",
            primary_reason="trend_ok",
            current_status="BUY_ZONE",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BUY_ZONE",
            status_change_5d=None,
            window_status_30d="BUY_ZONE",
            window_status_5d=None,
            window_status_2d=None,
            ma_break_status="OK",
            freshness_status="FRESH_BULLISH_SIGNAL",
            trend_state="UP",
            trend_state_age_td=7,
            latest_structure_label="HL",
            latest_structure_age_td=2,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=1,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle=None,
            latest_candle_age_td=None,
            latest_divergence=None,
            latest_divergence_age_td=None,
            latest_chart_pattern="PULLBACK",
            latest_chart_pattern_age_td=2,
            pullback_validity="VALID_PULLBACK",
            entry_readiness="READY_TO_WATCH",
            candidate_priority=1,
            candidate_priority_label="P1_READY_TO_WATCH",
            daily_status=None,
            rolling_2d_status=None,
            rolling_5d_status=None,
            rolling_30d_status="BUY_ZONE",
            horizons_present="rolling 30d",
            source_files=1,
            is_watchlist=0,
        ),
        DatacenterDashboardTickerRecord(
            ticker="NVDA",
            action="SELL",
            severity="CRITICAL",
            primary_reason="close_below_ema20",
            current_status="BREAKOUT_READY",
            start_status_30d="WATCH",
            status_change_30d="WATCH -> BREAKOUT_READY",
            status_change_5d="PULLBACK_WINDOW -> BREAKOUT_READY",
            window_status_30d="WATCH",
            window_status_5d="PULLBACK_WINDOW",
            window_status_2d="BREAKOUT_READY",
            ma_break_status="EMA20_WARNING",
            freshness_status="FRESH_BULLISH_SIGNAL",
            trend_state="UP",
            trend_state_age_td=12,
            latest_structure_label="HH",
            latest_structure_age_td=3,
            latest_bos_event_type="BOS_UP",
            latest_bos_age_td=2,
            latest_reset_reason=None,
            latest_reset_age_td=None,
            latest_candle="Hammer",
            latest_candle_age_td=4,
            latest_divergence="Bearish Divergence",
            latest_divergence_age_td=2,
            latest_chart_pattern="BASE_BREAKOUT",
            latest_chart_pattern_age_td=5,
            pullback_validity="NO_PULLBACK",
            entry_readiness="NOT_READY",
            candidate_priority=5,
            candidate_priority_label="P5_NOT_READY",
            daily_status="BREAKOUT_READY",
            rolling_2d_status=None,
            rolling_5d_status=None,
            rolling_30d_status="WATCH",
            horizons_present="daily, rolling 30d",
            source_files=2,
            is_watchlist=1,
        ),
    ]


def _patch_models(monkeypatch) -> None:
    monkeypatch.setattr(
        "dev_tools.run_ecosystem_dashboard_build.build_datacenter_ticker_decisions",
        lambda rows: _stub_decision_result(),
    )
    monkeypatch.setattr(
        "dev_tools.run_ecosystem_dashboard_build.build_dashboard_market_map_model",
        lambda status: _stub_market_map_rows(),
    )
    monkeypatch.setattr(
        "dev_tools.run_ecosystem_dashboard_build.build_dashboard_watchlist_model",
        lambda rows, decisions: _stub_watchlist_rows(),
    )
    monkeypatch.setattr(
        "dev_tools.run_ecosystem_dashboard_build.build_dashboard_ticker_model",
        lambda rows, decisions: _stub_ticker_rows(),
    )


def test_cli_creates_tables_and_does_not_require_analysis_db(tmp_path, monkeypatch, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    _patch_models(monkeypatch)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
        ]
    )

    assert exit_code == 0
    assert _table_exists(dashboard_db, "ecosystem_dashboard_runs")
    assert _table_exists(dashboard_db, "ecosystem_dashboard_source_reports")
    assert _table_exists(dashboard_db, "ecosystem_dashboard_action_summary")
    assert _table_exists(dashboard_db, "ecosystem_dashboard_market_map")
    assert _table_exists(dashboard_db, "ecosystem_dashboard_watchlist_status")
    assert _table_exists(dashboard_db, "ecosystem_dashboard_ticker_status")
    assert _table_exists(dashboard_db, "ecosystem_dashboard_decision_trace")
    assert not _table_exists(dashboard_db, "dc_dashboard_runs")
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=OK" in output
    assert "SUMMARY ecosystem_dashboard_build.input_mode=reports" in output


def test_invalid_report_date_exits_non_zero(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "20260522",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=FAILED" in output
    assert "invalid report_date format" in output


def test_unsupported_ecosystem_code_exits_non_zero(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "FOO",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=FAILED" in output
    assert (
        "ERROR: unsupported ecosystem_code=FOO; currently supported: DATACENTER"
        in output
    )


def test_no_matching_reports_exits_non_zero_and_writes_no_run(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
        ]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=FAILED" in output
    assert not _table_exists(dashboard_db, "ecosystem_dashboard_runs") or _row_count(
        dashboard_db, "ecosystem_dashboard_runs"
    ) == 0


def test_cli_writes_run_and_rows_with_ecosystem_code(tmp_path, monkeypatch, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    _patch_models(monkeypatch)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--run-id",
            "RUN_A",
        ]
    )

    assert exit_code == 0
    assert _row_count(dashboard_db, "ecosystem_dashboard_runs") == 1
    assert _row_count(dashboard_db, "ecosystem_dashboard_source_reports") == 4
    assert _row_count(dashboard_db, "ecosystem_dashboard_action_summary") == 8
    assert _row_count(dashboard_db, "ecosystem_dashboard_market_map") == 2
    assert _row_count(dashboard_db, "ecosystem_dashboard_watchlist_status") == 1
    assert _row_count(dashboard_db, "ecosystem_dashboard_ticker_status") == 2
    assert _row_count(dashboard_db, "ecosystem_dashboard_decision_trace") == 1

    with sqlite3.connect(dashboard_db) as conn:
        run_row = conn.execute(
            """
            SELECT ecosystem_code, report_date, readiness, decision_total
            FROM ecosystem_dashboard_runs
            WHERE run_id = 'RUN_A'
            """
        ).fetchone()
        market_row = conn.execute(
            """
            SELECT ecosystem_code, parent_name, subindustry, taxonomy_path
            FROM ecosystem_dashboard_market_map
            WHERE run_id = 'RUN_A' AND market_level = 'SUBINDUSTRY' AND name = 'Semiconductors'
            """
        ).fetchone()
        watchlist_row = conn.execute(
            """
            SELECT ecosystem_code, latest_structure_label, latest_structure_age_td
            FROM ecosystem_dashboard_watchlist_status
            WHERE run_id = 'RUN_A' AND ticker = 'NVDA'
            """
        ).fetchone()
        ticker_row = conn.execute(
            """
            SELECT ecosystem_code, is_watchlist
            FROM ecosystem_dashboard_ticker_status
            WHERE run_id = 'RUN_A' AND ticker = 'AMD'
            """
        ).fetchone()
        trace_row = conn.execute(
            """
            SELECT ecosystem_code, matched_rule
            FROM ecosystem_dashboard_decision_trace
            WHERE run_id = 'RUN_A' AND ticker = 'NVDA'
            """
        ).fetchone()
    assert run_row == ("DATACENTER", "2026-05-22", "PARTIAL", 2)
    assert market_row == (
        "DATACENTER",
        "Technology",
        "Semiconductors",
        "DC_ECOSYSTEM_TOTAL > Technology > Semiconductors",
    )
    assert watchlist_row == ("DATACENTER", "HH", 3)
    assert ticker_row == ("DATACENTER", 0)
    assert trace_row == ("DATACENTER", "SELL_HARD_TOKEN")

    output_lines = capsys.readouterr().out.strip().splitlines()
    assert output_lines == [
        "SUMMARY ecosystem_dashboard_build.status=OK",
        "SUMMARY ecosystem_dashboard_build.run_id=RUN_A",
        "SUMMARY ecosystem_dashboard_build.ecosystem_code=DATACENTER",
        "SUMMARY ecosystem_dashboard_build.report_date=2026-05-22",
        "SUMMARY ecosystem_dashboard_build.input_mode=reports",
        f"SUMMARY ecosystem_dashboard_build.dashboard_db={dashboard_db}",
        f"SUMMARY ecosystem_dashboard_build.reports_dir={reports_dir}",
        "SUMMARY ecosystem_dashboard_build.readiness=PARTIAL",
        "SUMMARY ecosystem_dashboard_build.source_reports_count=4",
        "SUMMARY ecosystem_dashboard_build.total_parsed_rows=1",
        "SUMMARY ecosystem_dashboard_build.total_parse_warnings=0",
        "SUMMARY ecosystem_dashboard_build.decision_total=2",
        "SUMMARY ecosystem_dashboard_build.market_map_rows=2",
        "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
        "SUMMARY ecosystem_dashboard_build.ticker_rows=2",
        "SUMMARY ecosystem_dashboard_build.trace_rows=1",
        "SUMMARY ecosystem_dashboard_build.mode=replace-date",
    ]


def test_replace_date_deletes_only_matching_ecosystem_and_report_date(tmp_path, monkeypatch):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    _patch_models(monkeypatch)

    assert main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--run-id",
            "RUN_OLD",
        ]
    ) == 0

    with sqlite3.connect(dashboard_db) as conn:
        conn.execute(
            """
            INSERT INTO ecosystem_dashboard_runs (
                run_id, ecosystem_code, report_date, taxonomy_version, generated_at_utc,
                reports_dir, selection_mode, readiness, found_reports, missing_reports,
                total_parsed_rows, total_parse_warnings, decision_total, market_map_rows,
                watchlist_rows, ticker_rows, source_reports_count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "KEEP_OTHER_ECO",
                "OTHER",
                "2026-05-22",
                None,
                "2026-05-25T12:00:00Z",
                "/tmp/reports",
                "report_date",
                "READY",
                1,
                0,
                1,
                0,
                1,
                1,
                1,
                1,
                1,
                "2026-05-25T12:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO ecosystem_dashboard_runs (
                run_id, ecosystem_code, report_date, taxonomy_version, generated_at_utc,
                reports_dir, selection_mode, readiness, found_reports, missing_reports,
                total_parsed_rows, total_parse_warnings, decision_total, market_map_rows,
                watchlist_rows, ticker_rows, source_reports_count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "KEEP_OTHER_DATE",
                "DATACENTER",
                "2026-05-21",
                None,
                "2026-05-25T12:00:00Z",
                "/tmp/reports",
                "report_date",
                "READY",
                1,
                0,
                1,
                0,
                1,
                1,
                1,
                1,
                1,
                "2026-05-25T12:00:00Z",
            ),
        )
        conn.commit()

    assert main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--run-id",
            "RUN_NEW",
            "--mode",
            "replace-date",
        ]
    ) == 0

    with sqlite3.connect(dashboard_db) as conn:
        run_ids = conn.execute(
            "SELECT run_id FROM ecosystem_dashboard_runs ORDER BY run_id"
        ).fetchall()
    assert run_ids == [("KEEP_OTHER_DATE",), ("KEEP_OTHER_ECO",), ("RUN_NEW",)]


def test_insert_fails_on_duplicate_run_id(tmp_path, monkeypatch, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    _patch_models(monkeypatch)

    assert main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--run-id",
            "RUN_SAME",
            "--mode",
            "insert",
        ]
    ) == 0

    second_exit = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--run-id",
            "RUN_SAME",
            "--mode",
            "insert",
        ]
    )

    assert second_exit == 2
    assert _row_count(dashboard_db, "ecosystem_dashboard_runs") == 1
    assert "run_id already exists: RUN_SAME" in capsys.readouterr().out


def test_build_without_render_html_does_not_create_html_output(tmp_path, monkeypatch):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    html_output = tmp_path / "dashboard.html"
    _patch_models(monkeypatch)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--run-id",
            "RUN_NO_RENDER",
        ]
    )

    assert exit_code == 0
    assert not html_output.exists()


def test_build_with_render_html_for_datacenter_builds_and_renders(
    tmp_path, monkeypatch, capsys
):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    html_output = tmp_path / "dashboard.html"
    _patch_models(monkeypatch)

    def fake_render(**kwargs):
        Path(kwargs["output"]).write_text(
            f"run_id={kwargs['run_id']} report_date=2026-05-22 ticker=NVDA",
            encoding="utf-8",
        )
        return object()

    monkeypatch.setattr(
        "dev_tools.run_ecosystem_dashboard_build.generate_datacenter_dashboard_html_file",
        fake_render,
    )

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--run-id",
            "RUN_RENDER",
            "--render-html",
            "--html-output",
            str(html_output),
        ]
    )

    assert exit_code == 0
    assert _row_count(dashboard_db, "ecosystem_dashboard_runs") == 1
    assert html_output.exists()
    html = html_output.read_text(encoding="utf-8")
    assert "2026-05-22" in html
    assert "RUN_RENDER" in html
    assert "NVDA" in html
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.input_mode=reports" in output
    assert "SUMMARY ecosystem_dashboard_build.render_html_requested=1" in output
    assert f"SUMMARY ecosystem_dashboard_build.html_output_path={html_output}" in output
    assert "SUMMARY ecosystem_dashboard_build.html_render_status=OK" in output


def test_render_html_without_html_output_fails_clearly(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--render-html",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=FAILED" in output
    assert "--html-output is required when --render-html is provided" in output


def test_html_output_without_render_html_fails_clearly(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    html_output = tmp_path / "dashboard.html"

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--html-output",
            str(html_output),
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=FAILED" in output
    assert "--html-output requires --render-html" in output


def test_render_html_with_other_ecosystem_fails_clearly(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    html_output = tmp_path / "dashboard.html"

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "OTHER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--render-html",
            "--html-output",
            str(html_output),
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=FAILED" in output
    assert (
        "--render-html is currently supported only for ecosystem_code=DATACENTER; got OTHER"
        in output
    )


def test_cli_accepts_explicit_input_mode_reports(tmp_path, monkeypatch, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)
    _patch_models(monkeypatch)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--input-mode",
            "reports",
        ]
    )

    assert exit_code == 0
    assert "SUMMARY ecosystem_dashboard_build.input_mode=reports" in capsys.readouterr().out


def test_cli_rejects_unsupported_input_mode(tmp_path, capsys):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = _make_reports_dir(tmp_path)

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--ecosystem-code",
            "DATACENTER",
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--input-mode",
            "structured",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.status=FAILED" in output
    assert "unsupported input_mode=structured; currently supported: reports" in output
