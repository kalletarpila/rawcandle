from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.ecosystem_dashboard_persistence import (
    connect_dashboard_db,
    ensure_dashboard_schema,
)
from dev_tools.inspect_ecosystem_dashboard import main


def _seed_dashboard_db(db_path: Path) -> None:
    conn = connect_dashboard_db(str(db_path))
    try:
        ensure_dashboard_schema(conn)
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
                "RUN_A_OLD",
                "DATACENTER",
                "2026-05-22",
                None,
                "2026-05-25T10:00:00Z",
                "/tmp/reports",
                "report_date",
                "PARTIAL",
                3,
                1,
                100,
                2,
                4,
                3,
                2,
                4,
                4,
                "2026-05-25T10:00:00Z",
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
                "RUN_A_NEW",
                "DATACENTER",
                "2026-05-22",
                None,
                "2026-05-25T11:00:00Z",
                "/tmp/reports",
                "report_date",
                "READY",
                4,
                0,
                200,
                1,
                6,
                4,
                3,
                5,
                4,
                "2026-05-25T11:00:00Z",
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
                "RUN_B",
                "DATACENTER",
                "2026-05-21",
                None,
                "2026-05-24T11:00:00Z",
                "/tmp/reports",
                "report_date",
                "READY",
                4,
                0,
                210,
                0,
                7,
                2,
                1,
                7,
                4,
                "2026-05-24T11:00:00Z",
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
                "RUN_OTHER",
                "OTHER",
                "2026-05-22",
                None,
                "2026-05-25T12:00:00Z",
                "/tmp/reports",
                "report_date",
                "READY",
                1,
                0,
                10,
                0,
                1,
                1,
                0,
                1,
                1,
                "2026-05-25T12:00:00Z",
            ),
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_action_summary (
                run_id, ecosystem_code, action, count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("RUN_A_NEW", "DATACENTER", "WATCH", 2, "2026-05-25T11:00:00Z"),
                ("RUN_A_NEW", "DATACENTER", "SELL", 1, "2026-05-25T11:00:00Z"),
                ("RUN_A_NEW", "DATACENTER", "BLOCKED", 1, "2026-05-25T11:00:00Z"),
                ("RUN_A_NEW", "DATACENTER", "CUSTOM", 3, "2026-05-25T11:00:00Z"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_market_map (
                run_id, ecosystem_code, report_date, market_level, name, parent_name, layer, subindustry,
                taxonomy_path, taxonomy_version, current_status, start_status_30d, status_change_30d,
                status_change_5d, window_status_30d, window_status_5d, window_status_2d, overheat_risk,
                pct_above_ema20, pct_above_ma10, ema20_breadth_delta_5d, return_5d, return_10d, return_20d,
                return_60d, dow_trend_state, dow_trend_state_age_td, latest_structure_label, latest_structure_age_td,
                latest_bos_event_type, latest_bos_age_td, latest_reset_reason, latest_reset_age_td, latest_candle,
                latest_candle_age_td, latest_divergence, latest_divergence_age_td, latest_chart_pattern,
                latest_chart_pattern_age_td, source_horizons, source_files, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "SUBINDUSTRY", "Semis", "Tech", "Tech", "Semis",
                    "DC > Tech > Semis", None, "BUY_ZONE", "WATCH", "WATCH -> BUY_ZONE", "", "BUY_ZONE", "", "",
                    "LOW", 70.0, 65.0, 4.0, 0.2, 0.3, 0.4, 0.5, "UP", 6, "HL", 2, "BOS_UP", 1, "", None, "", None,
                    "", None, "PULLBACK", 2, "rolling 30d", "rolling30.md", "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "ECOSYSTEM", "DC_ECOSYSTEM_TOTAL", "", "", "",
                    "", None, "BUY_ZONE", "WATCH", "WATCH -> BUY_ZONE", "", "BUY_ZONE", "", "", "LOW",
                    60.0, 55.0, 3.0, 0.1, 0.2, 0.3, 0.4, "UP", 8, "HH", 3, "BOS_UP", 2, "", None, "", None, "", None,
                    "BASE_BREAKOUT", 5, "daily, rolling 30d", "daily.md, rolling30.md", "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "LAYER", "Tech", "DC_ECOSYSTEM_TOTAL", "Tech", "",
                    "DC > Tech", None, "BUY_ZONE", "WATCH", "WATCH -> BUY_ZONE", "", "BUY_ZONE", "", "", "LOW",
                    65.0, 60.0, 3.5, 0.15, 0.25, 0.35, 0.45, "UP", 7, "HH", 3, "BOS_UP", 2, "", None, "", None, "", None,
                    "BASE_BREAKOUT", 5, "daily, rolling 30d", "daily.md, rolling30.md", "2026-05-25T11:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_watchlist_status (
                run_id, ecosystem_code, report_date, ticker, action, severity, primary_reason, current_status,
                start_status_30d, status_change_30d, status_change_5d, window_status_30d, window_status_5d,
                window_status_2d, ma_break_status, freshness_status, trend_state, trend_state_age_td,
                latest_structure_label, latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td, latest_divergence,
                latest_divergence_age_td, latest_chart_pattern, latest_chart_pattern_age_td, pullback_validity,
                entry_readiness, candidate_priority, candidate_priority_label, daily_status, rolling_2d_status,
                rolling_5d_status, rolling_30d_status, horizons_present, source_files, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "NVDA", "SELL", "CRITICAL", "close_below_ema20",
                    "BREAKOUT_READY", "WATCH", "WATCH -> BREAKOUT_READY", "PULLBACK -> BREAKOUT_READY", "WATCH",
                    "PULLBACK", "BREAKOUT_READY", "EMA20_WARNING", "FRESH", "UP", 12, "HH", 3, "BOS_UP", 2, "", None,
                    "Hammer", 4, "Bearish Divergence", 2, "BASE_BREAKOUT", 5, "NO_PULLBACK", "NOT_READY", 5,
                    "P5_NOT_READY", "BREAKOUT_READY", "", "", "WATCH", "daily, rolling 30d", 2, "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "AMD", "WATCH", "LOW", "trend_ok",
                    "BUY_ZONE", "WATCH", "WATCH -> BUY_ZONE", "", "BUY_ZONE", "", "", "OK", "FRESH", "UP", 7, "HL", 2,
                    "BOS_UP", 1, "", None, "", None, "", None, "PULLBACK", 2, "VALID_PULLBACK", "READY_TO_WATCH", 1,
                    "P1_READY_TO_WATCH", "", "", "", "BUY_ZONE", "rolling 30d", 1, "2026-05-25T11:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_ticker_status (
                run_id, ecosystem_code, report_date, ticker, action, severity, primary_reason, current_status,
                start_status_30d, status_change_30d, status_change_5d, window_status_30d, window_status_5d,
                window_status_2d, ma_break_status, freshness_status, trend_state, trend_state_age_td,
                latest_structure_label, latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td, latest_divergence,
                latest_divergence_age_td, latest_chart_pattern, latest_chart_pattern_age_td, pullback_validity,
                entry_readiness, candidate_priority, candidate_priority_label, daily_status, rolling_2d_status,
                rolling_5d_status, rolling_30d_status, horizons_present, source_files, is_watchlist, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "MSFT", "BLOCKED", "HIGH", "risk", "", "", "", "", "", "",
                    "", "OK", "FRESH", "UP", 4, "HL", 1, "BOS_UP", 1, "", None, "", None, "", None, "BASE", 1,
                    "EARLY_PULLBACK", "EARLY_MONITOR", None, "", "", "", "", "BUY_ZONE", "rolling 30d", 1, 0,
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "AMD", "WATCH", "LOW", "trend_ok", "BUY_ZONE", "WATCH",
                    "WATCH -> BUY_ZONE", "", "BUY_ZONE", "", "", "OK", "FRESH", "UP", 7, "HL", 2, "BOS_UP", 1, "", None,
                    "", None, "", None, "PULLBACK", 2, "VALID_PULLBACK", "READY_TO_WATCH", 1, "P1_READY_TO_WATCH", "", "",
                    "", "BUY_ZONE", "rolling 30d", 1, 0, "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_A_NEW", "DATACENTER", "2026-05-22", "NVDA", "SELL", "CRITICAL", "close_below_ema20",
                    "BREAKOUT_READY", "WATCH", "WATCH -> BREAKOUT_READY", "PULLBACK -> BREAKOUT_READY", "WATCH",
                    "PULLBACK", "BREAKOUT_READY", "EMA20_WARNING", "FRESH", "UP", 12, "HH", 3, "BOS_UP", 2, "", None,
                    "Hammer", 4, "Bearish Divergence", 2, "BASE_BREAKOUT", 5, "NO_PULLBACK", "NOT_READY", 5,
                    "P5_NOT_READY", "BREAKOUT_READY", "", "", "WATCH", "daily, rolling 30d", 2, 1, "2026-05-25T11:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_decision_trace (
                run_id, ecosystem_code, ticker, trace_index, action, matched_rule,
                matched_token, matched_value, horizon, field, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("RUN_A_NEW", "DATACENTER", "NVDA", 1, "SELL", "SELL_SECOND", "x", "y", "daily", "reason", "2026-05-25T11:00:00Z"),
                ("RUN_A_NEW", "DATACENTER", "NVDA", 0, "SELL", "SELL_FIRST", "close_below_ema20", "close_below_ema20", "daily", "reason", "2026-05-25T11:00:00Z"),
                ("RUN_A_NEW", "DATACENTER", "AMD", 0, "WATCH", "WATCH_RULE", "pullback", "pullback", "rolling 30d", "status", "2026-05-25T11:00:00Z"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_missing_dashboard_db_fails(tmp_path, capsys):
    missing_db = tmp_path / "missing.db"
    exit_code = main(
        [
            "--dashboard-db",
            str(missing_db),
            "--ecosystem-code",
            "DATACENTER",
        ]
    )
    assert exit_code == 1
    assert capsys.readouterr().out.strip().splitlines() == [
        "SUMMARY ecosystem_dashboard_inspect.status=FAILED",
        f"ERROR: dashboard_db not found: {missing_db}",
    ]
    assert not missing_db.exists()


def test_missing_tables_fail(tmp_path, capsys):
    db_path = tmp_path / "blank.db"
    sqlite3.connect(db_path).close()
    exit_code = main(
        [
            "--dashboard-db",
            str(db_path),
            "--ecosystem-code",
            "DATACENTER",
        ]
    )
    assert exit_code == 1
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_inspect.status=FAILED" in output
    assert "required tables missing:" in output


def test_invalid_report_date_fails(tmp_path, capsys):
    db_path = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(db_path)
    exit_code = main(
        [
            "--dashboard-db",
            str(db_path),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "20260522",
        ]
    )
    assert exit_code == 1
    assert "ERROR: invalid report_date format: 20260522" in capsys.readouterr().out


def test_no_runs_for_ecosystem_fail(tmp_path, capsys):
    db_path = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(db_path)
    exit_code = main(
        [
            "--dashboard-db",
            str(db_path),
            "--ecosystem-code",
            "MISSING",
        ]
    )
    assert exit_code == 1
    assert "ERROR: no runs found for ecosystem_code=MISSING" in capsys.readouterr().out


def test_ambiguous_detail_requires_run_id_or_latest(tmp_path, capsys):
    db_path = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(db_path)
    exit_code = main(
        [
            "--dashboard-db",
            str(db_path),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--show-watchlist",
        ]
    )
    assert exit_code == 1
    assert (
        "ERROR: multiple runs match; use --run-id or --latest for detail views"
        in capsys.readouterr().out
    )


def test_show_runs_prints_sorted_runs_and_summary(tmp_path, capsys):
    db_path = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(db_path)
    exit_code = main(
        [
            "--dashboard-db",
            str(db_path),
            "--ecosystem-code",
            "DATACENTER",
            "--show-runs",
            "--limit",
            "5",
        ]
    )
    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[:14] == [
        "SUMMARY ecosystem_dashboard_inspect.status=OK",
        f"SUMMARY ecosystem_dashboard_inspect.dashboard_db={db_path}",
        "SUMMARY ecosystem_dashboard_inspect.ecosystem_code=DATACENTER",
        "SUMMARY ecosystem_dashboard_inspect.report_date=ALL",
        "SUMMARY ecosystem_dashboard_inspect.run_id=NONE",
        "SUMMARY ecosystem_dashboard_inspect.runs_found=3",
        "SUMMARY ecosystem_dashboard_inspect.selected_run_id=NONE",
        "SUMMARY ecosystem_dashboard_inspect.selected_report_date=NONE",
        "SUMMARY ecosystem_dashboard_inspect.readiness=NONE",
        "SUMMARY ecosystem_dashboard_inspect.decision_total=0",
        "SUMMARY ecosystem_dashboard_inspect.market_map_rows=0",
        "SUMMARY ecosystem_dashboard_inspect.watchlist_rows=0",
        "SUMMARY ecosystem_dashboard_inspect.ticker_rows=0",
        "SUMMARY ecosystem_dashboard_inspect.trace_rows=0",
    ]
    assert lines[14:] == [
        "section;runs",
        "run_id;ecosystem_code;report_date;created_at_utc;readiness;decision_total;market_map_rows;watchlist_rows;ticker_rows;source_reports_count",
        "RUN_A_NEW;DATACENTER;2026-05-22;2026-05-25T11:00:00Z;READY;6;4;3;5;4",
        "RUN_A_OLD;DATACENTER;2026-05-22;2026-05-25T10:00:00Z;PARTIAL;4;3;2;4;4",
        "RUN_B;DATACENTER;2026-05-21;2026-05-24T11:00:00Z;READY;7;2;1;7;4",
    ]


def test_latest_detail_sections_apply_filters_and_limits(tmp_path, capsys):
    db_path = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(db_path)
    exit_code = main(
        [
            "--dashboard-db",
            str(db_path),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--latest",
            "--show-action-summary",
            "--show-market-map",
            "--show-watchlist",
            "--show-tickers",
            "--show-trace",
            "--ticker",
            "nvda",
            "--market-level",
            "subindustry",
            "--action",
            "sell",
            "--limit",
            "5",
        ]
    )
    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY ecosystem_dashboard_inspect.selected_run_id=RUN_A_NEW" in lines
    assert "SUMMARY ecosystem_dashboard_inspect.selected_report_date=2026-05-22" in lines
    assert "SUMMARY ecosystem_dashboard_inspect.readiness=READY" in lines
    assert "SUMMARY ecosystem_dashboard_inspect.decision_total=6" in lines
    assert "section;action_summary" in lines
    action_idx = lines.index("section;action_summary")
    assert lines[action_idx + 1 : action_idx + 6] == [
        "action;count",
        "SELL;1",
        "BLOCKED;1",
        "WATCH;2",
        "CUSTOM;3",
    ]
    market_idx = lines.index("section;market_map")
    assert lines[market_idx + 1] == "market_level;name;layer;current_status;start_status_30d;status_change_30d;status_change_5d;window_status_30d;window_status_5d;window_status_2d;overheat_risk;pct_above_ema20;pct_above_ma10;ema20_breadth_delta_5d;return_5d;return_10d;return_20d;return_60d;dow_trend_state;dow_trend_state_age_td;latest_structure_label;latest_structure_age_td;latest_bos_event_type;latest_bos_age_td;latest_reset_reason;latest_reset_age_td;latest_candle;latest_candle_age_td;latest_divergence;latest_divergence_age_td;latest_chart_pattern;latest_chart_pattern_age_td;source_horizons;source_files"
    assert lines[market_idx + 2] == "SUBINDUSTRY;Semis;Tech;BUY_ZONE;WATCH;WATCH -> BUY_ZONE;;BUY_ZONE;;;LOW;70.0;65.0;4.0;0.2;0.3;0.4;0.5;UP;6;HL;2;BOS_UP;1;;;;;;;PULLBACK;2;rolling 30d;rolling30.md"
    watch_idx = lines.index("section;watchlist")
    assert lines[watch_idx + 2] == "NVDA;SELL;CRITICAL;close_below_ema20;BREAKOUT_READY;WATCH;WATCH -> BREAKOUT_READY;PULLBACK -> BREAKOUT_READY;WATCH;PULLBACK;BREAKOUT_READY;EMA20_WARNING;FRESH;UP;12;HH;3;BOS_UP;2;;;Hammer;4;Bearish Divergence;2;BASE_BREAKOUT;5;NO_PULLBACK;NOT_READY;5;P5_NOT_READY;BREAKOUT_READY;;;WATCH;daily, rolling 30d;2"
    tickers_idx = lines.index("section;tickers")
    assert lines[tickers_idx + 2] == "NVDA;1;SELL;CRITICAL;close_below_ema20;BREAKOUT_READY;EMA20_WARNING;FRESH;NO_PULLBACK;NOT_READY;5;P5_NOT_READY;UP;12;HH;3;BOS_UP;2;;;Hammer;4;Bearish Divergence;2;BASE_BREAKOUT;5;BREAKOUT_READY;;;WATCH;daily, rolling 30d"
    trace_idx = lines.index("section;decision_trace")
    assert lines[trace_idx + 2 : trace_idx + 4] == [
        "NVDA;0;SELL;SELL_FIRST;close_below_ema20;close_below_ema20;daily;reason",
        "NVDA;1;SELL;SELL_SECOND;x;y;daily;reason",
    ]


def test_zero_row_requested_section_still_prints_marker_and_header(tmp_path, capsys):
    db_path = tmp_path / "ecosystem_dashboard.db"
    _seed_dashboard_db(db_path)
    exit_code = main(
        [
            "--dashboard-db",
            str(db_path),
            "--ecosystem-code",
            "DATACENTER",
            "--run-id",
            "RUN_A_NEW",
            "--show-watchlist",
            "--ticker",
            "TSLA",
        ]
    )
    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-2:] == [
        "section;watchlist",
        "ticker;action;severity;primary_reason;current_status;start_status_30d;status_change_30d;status_change_5d;window_status_30d;window_status_5d;window_status_2d;ma_break_status;freshness_status;trend_state;trend_state_age_td;latest_structure_label;latest_structure_age_td;latest_bos_event_type;latest_bos_age_td;latest_reset_reason;latest_reset_age_td;latest_candle;latest_candle_age_td;latest_divergence;latest_divergence_age_td;latest_chart_pattern;latest_chart_pattern_age_td;pullback_validity;entry_readiness;candidate_priority;candidate_priority_label;daily_status;rolling_2d_status;rolling_5d_status;rolling_30d_status;horizons_present;source_files",
    ]
