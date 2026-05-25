from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dev_tools.ecosystem_dashboard_persistence import (
    connect_dashboard_db,
    ensure_dashboard_schema,
)
from dev_tools.ecosystem_dashboard_read_model import (
    EcosystemDashboardRunRef,
    EcosystemDashboardSnapshot,
    load_dashboard_snapshot,
    resolve_dashboard_run,
)


def _seed_dashboard_db(db_path: Path) -> None:
    conn = connect_dashboard_db(str(db_path))
    try:
        ensure_dashboard_schema(conn)
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_runs (
                run_id, ecosystem_code, report_date, taxonomy_version, generated_at_utc,
                reports_dir, selection_mode, readiness, found_reports, missing_reports,
                total_parsed_rows, total_parse_warnings, decision_total, market_map_rows,
                watchlist_rows, ticker_rows, source_reports_count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_OLD",
                    "DATACENTER",
                    "2026-05-22",
                    None,
                    "2026-05-25T10:00:00Z",
                    "/tmp/reports",
                    "report_date",
                    "PARTIAL",
                    2,
                    1,
                    10,
                    1,
                    2,
                    3,
                    2,
                    2,
                    2,
                    "2026-05-25T10:00:00Z",
                ),
                (
                    "RUN_NEW_B",
                    "DATACENTER",
                    "2026-05-22",
                    None,
                    "2026-05-25T11:00:00Z",
                    "/tmp/reports",
                    "report_date",
                    "READY",
                    4,
                    0,
                    20,
                    0,
                    4,
                    4,
                    3,
                    3,
                    2,
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_A",
                    "DATACENTER",
                    "2026-05-22",
                    None,
                    "2026-05-25T11:00:00Z",
                    "/tmp/reports",
                    "report_date",
                    "READY",
                    4,
                    0,
                    20,
                    0,
                    4,
                    4,
                    3,
                    3,
                    2,
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_OTHER_DATE",
                    "DATACENTER",
                    "2026-05-21",
                    None,
                    "2026-05-24T11:00:00Z",
                    "/tmp/reports",
                    "report_date",
                    "READY",
                    1,
                    0,
                    5,
                    0,
                    1,
                    1,
                    1,
                    1,
                    1,
                    "2026-05-24T11:00:00Z",
                ),
                (
                    "RUN_OTHER_ECOSYSTEM",
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
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_source_reports (
                run_id, ecosystem_code, report_date, horizon, report_kind, markdown_path,
                csv_path, modified_at_utc, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_NEW_B",
                    "DATACENTER",
                    "2026-05-22",
                    "rolling_30d",
                    "full",
                    "/b/report.md",
                    "/b/report.csv",
                    "2026-05-25T11:00:00Z",
                    "FOUND",
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B",
                    "DATACENTER",
                    "2026-05-22",
                    "daily",
                    "full",
                    "/a/report.md",
                    "/a/report.csv",
                    "2026-05-25T11:00:00Z",
                    "FOUND",
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_OLD",
                    "DATACENTER",
                    "2026-05-22",
                    "daily",
                    "full",
                    "/z/old.md",
                    "/z/old.csv",
                    "2026-05-25T10:00:00Z",
                    "FOUND",
                    "2026-05-25T10:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_action_summary (
                run_id, ecosystem_code, action, count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("RUN_NEW_B", "DATACENTER", "WATCH", 5, "2026-05-25T11:00:00Z"),
                ("RUN_NEW_B", "DATACENTER", "SELL", 2, "2026-05-25T11:00:00Z"),
                ("RUN_NEW_B", "DATACENTER", "CUSTOM", 1, "2026-05-25T11:00:00Z"),
                ("RUN_OLD", "DATACENTER", "SELL", 9, "2026-05-25T10:00:00Z"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_market_map (
                run_id, ecosystem_code, report_date, market_level, name, parent_name, layer,
                subindustry, taxonomy_path, taxonomy_version, current_status, start_status_30d,
                status_change_30d, status_change_5d, window_status_30d, window_status_5d,
                window_status_2d, overheat_risk, pct_above_ema20, pct_above_ma10,
                ema20_breadth_delta_5d, return_5d, return_10d, return_20d, return_60d,
                dow_trend_state, dow_trend_state_age_td, latest_structure_label,
                latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td,
                latest_divergence, latest_divergence_age_td, latest_chart_pattern,
                latest_chart_pattern_age_td, source_horizons, source_files, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "SUBINDUSTRY", "Cloud", "Technology",
                    "Technology", "Cloud", "Technology > Cloud", None, "BUY_ZONE", "WATCH",
                    "WATCH -> BUY_ZONE", None, "BUY_ZONE", None, None, "LOW", 62.5, 58.0, 4.0,
                    0.12, 0.18, 0.25, 0.44, "UP", 8, "HH", 3, "BOS_UP", 2, None, None, None,
                    None, None, None, "BASE_BREAKOUT", 5, "daily,rolling_30d", "daily.md", "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "ECOSYSTEM", "All", None,
                    None, None, None, None, "WATCH", None, None, None, None, None, None, None,
                    50.0, 45.0, -1.0, 0.05, 0.10, 0.15, 0.20, "UP", 5, "HL", None, "BOS_UP", 1,
                    None, None, None, None, None, None, "PULLBACK", 2, "daily", "all.md", "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "LAYER", "Software", "Technology",
                    "Technology", None, "Technology", None, "BUY_ZONE", "WATCH",
                    "WATCH -> BUY_ZONE", None, "BUY_ZONE", None, None, "LOW", 70.0, 65.0, 5.0,
                    0.20, 0.30, 0.40, 0.80, "UP", 6, "HL", 2, "BOS_UP", 1, None, None, None,
                    None, None, None, "PULLBACK", 1, "rolling_30d", "layer.md", "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_OLD", "DATACENTER", "2026-05-22", "ECOSYSTEM", "Old", None,
                    None, None, None, None, "SELL", None, None, None, None, None, None, None,
                    1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, "DOWN", 1, "LL", 1, "BOS_DOWN", 1, None,
                    None, None, None, None, None, "OLD", 1, "old", "old.md", "2026-05-25T10:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_watchlist_status (
                run_id, ecosystem_code, report_date, ticker, action, severity, primary_reason,
                current_status, start_status_30d, status_change_30d, status_change_5d,
                window_status_30d, window_status_5d, window_status_2d, ma_break_status,
                freshness_status, trend_state, trend_state_age_td, latest_structure_label,
                latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td,
                latest_divergence, latest_divergence_age_td, latest_chart_pattern,
                latest_chart_pattern_age_td, pullback_validity, entry_readiness,
                candidate_priority, candidate_priority_label, daily_status, rolling_2d_status,
                rolling_5d_status, rolling_30d_status, horizons_present, source_files,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "MSFT", "WATCH", "LOW", "trend_ok",
                    "BUY_ZONE", "WATCH", "WATCH -> BUY_ZONE", None, "BUY_ZONE", None, None,
                    "OK", "FRESH", "UP", 7, "HL", 2, "BOS_UP", 1, None, None, None, None, None,
                    None, "PULLBACK", 2, "VALID_PULLBACK", "READY_TO_WATCH", 1,
                    "P1_READY_TO_WATCH", None, None, None, "BUY_ZONE", "rolling_30d", 1,
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "NVDA", "SELL", "CRITICAL",
                    "close_below_ema20", "BREAKOUT_READY", "WATCH", "WATCH -> BREAKOUT_READY",
                    "PULLBACK -> BREAKOUT_READY", "WATCH", "PULLBACK", "BREAKOUT_READY",
                    "EMA20_WARNING", "FRESH", "UP", 12, "HH", 3, "BOS_UP", 2, None, None,
                    "Hammer", 4, "Bearish Divergence", 2, "BASE_BREAKOUT", 5, "NO_PULLBACK",
                    "NOT_READY", 5, "P5_NOT_READY", "BREAKOUT_READY", None, None, "WATCH",
                    "daily,rolling_30d", 2, "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "ABCD", "CUSTOM", "MEDIUM", "other",
                    None, None, None, None, None, None, None, None, None, "UP", None, None,
                    None, None, None, None, None, None, None, None, None, None, None, None,
                    None, None, None, None, None, None, None, None, 0, "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_OLD", "DATACENTER", "2026-05-22", "OLD", "SELL", "HIGH", "old",
                    None, None, None, None, None, None, None, None, None, "DOWN", 1, None, None,
                    None, None, None, None, None, None, None, None, None, None, None, None, None,
                    None, None, None, None, None, None, 1, "2026-05-25T10:00:00Z",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_ticker_status (
                run_id, ecosystem_code, report_date, ticker, action, severity, primary_reason,
                current_status, start_status_30d, status_change_30d, status_change_5d,
                window_status_30d, window_status_5d, window_status_2d, ma_break_status,
                freshness_status, trend_state, trend_state_age_td, latest_structure_label,
                latest_structure_age_td, latest_bos_event_type, latest_bos_age_td,
                latest_reset_reason, latest_reset_age_td, latest_candle, latest_candle_age_td,
                latest_divergence, latest_divergence_age_td, latest_chart_pattern,
                latest_chart_pattern_age_td, pullback_validity, entry_readiness,
                candidate_priority, candidate_priority_label, daily_status, rolling_2d_status,
                rolling_5d_status, rolling_30d_status, horizons_present, source_files,
                is_watchlist, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "ZZZ", "WATCH", "LOW", "watch",
                    None, None, None, None, None, None, None, None, None, "UP", 1, None, None,
                    None, None, None, None, None, None, None, None, None, None, None, None,
                    2, "P2", None, None, None, None, "daily", 1, 0, "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "AAA", "SELL", "HIGH", "risk",
                    None, None, None, None, None, None, None, None, None, "DOWN", 2, None, None,
                    None, None, None, None, None, None, None, None, None, None, None, None,
                    1, "P1", None, None, None, None, "rolling_30d", 2, 1, "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "2026-05-22", "MMM", None, None, None,
                    None, None, None, None, None, None, None, None, None, "UP", None, None, None,
                    None, None, None, None, None, None, None, None, None, None, None, None,
                    None, None, None, None, None, None, None, 0, 0, "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_OLD", "DATACENTER", "2026-05-22", "OLD", "SELL", "HIGH", "old",
                    None, None, None, None, None, None, None, None, None, "DOWN", 1, None, None,
                    None, None, None, None, None, None, None, None, None, None, None, None,
                    9, "P9", None, None, None, None, "daily", 1, 0, "2026-05-25T10:00:00Z",
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
                (
                    "RUN_NEW_B", "DATACENTER", "NVDA", 1, "SELL", "SELL_SECOND", "x", "y",
                    "daily", "reason", "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "NVDA", 0, "SELL", "SELL_FIRST",
                    "close_below_ema20", "close_below_ema20", "daily", "reason",
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_NEW_B", "DATACENTER", "AAA", 0, "SELL", "SELL_AAA", "risk", "risk",
                    "rolling_30d", "status", "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_OLD", "DATACENTER", "OLD", 0, "SELL", "OLD_RULE", "old", "old",
                    "daily", "reason", "2026-05-25T10:00:00Z",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_resolve_dashboard_run_by_explicit_run_id(tmp_path):
    db_path = tmp_path / "dashboard.db"
    _seed_dashboard_db(db_path)

    run = resolve_dashboard_run(str(db_path), "DATACENTER", run_id="RUN_NEW_B")

    assert run == EcosystemDashboardRunRef(
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
        run_id="RUN_NEW_B",
        mode="report_date",
        status="READY",
        source_report_count=2,
        created_at_utc="2026-05-25T11:00:00Z",
    )


def test_resolve_dashboard_run_by_report_date_selects_latest_deterministically(tmp_path):
    db_path = tmp_path / "dashboard.db"
    _seed_dashboard_db(db_path)

    run = resolve_dashboard_run(str(db_path), "DATACENTER", report_date="2026-05-22")

    assert run.run_id == "RUN_NEW_B"


def test_resolve_dashboard_run_mismatching_run_id_and_report_date_fails(tmp_path):
    db_path = tmp_path / "dashboard.db"
    _seed_dashboard_db(db_path)

    with pytest.raises(ValueError, match="run_id/report_date mismatch"):
        resolve_dashboard_run(
            str(db_path),
            "DATACENTER",
            report_date="2026-05-21",
            run_id="RUN_NEW_B",
        )


def test_missing_db_fails_and_does_not_create_file(tmp_path):
    db_path = tmp_path / "missing.db"

    with pytest.raises(ValueError, match="dashboard_db not found"):
        resolve_dashboard_run(str(db_path), "DATACENTER", report_date="2026-05-22")

    assert not db_path.exists()


def test_load_dashboard_snapshot_returns_selected_run_only_with_deterministic_ordering(tmp_path):
    db_path = tmp_path / "dashboard.db"
    _seed_dashboard_db(db_path)

    snapshot = load_dashboard_snapshot(
        str(db_path),
        "DATACENTER",
        report_date="2026-05-22",
    )

    assert isinstance(snapshot, EcosystemDashboardSnapshot)
    assert isinstance(snapshot.run, EcosystemDashboardRunRef)
    assert snapshot.run.run_id == "RUN_NEW_B"

    assert [row["markdown_path"] for row in snapshot.source_reports] == [
        "/a/report.md",
        "/b/report.md",
    ]
    assert [row["action"] for row in snapshot.action_summary] == [
        "SELL",
        "WATCH",
        "CUSTOM",
    ]
    assert [row["market_level"] for row in snapshot.market_map] == [
        "ECOSYSTEM",
        "LAYER",
        "SUBINDUSTRY",
    ]
    assert [row["ticker"] for row in snapshot.watchlist] == [
        "NVDA",
        "MSFT",
        "ABCD",
    ]
    assert [row["ticker"] for row in snapshot.tickers] == [
        "AAA",
        "MMM",
        "ZZZ",
    ]
    assert [(row["ticker"], row["trace_index"]) for row in snapshot.decision_trace] == [
        ("AAA", 0),
        ("NVDA", 0),
        ("NVDA", 1),
    ]

    assert "OLD" not in {row["ticker"] for row in snapshot.tickers}
    assert snapshot.market_map[0]["pct_above_ema20"] == 50.0
    assert isinstance(snapshot.market_map[0]["pct_above_ema20"], float)
    assert snapshot.market_map[0]["latest_structure_age_td"] is None
    assert snapshot.watchlist[2]["current_status"] is None


def test_load_dashboard_snapshot_does_not_depend_on_analysis_db_or_source_files(tmp_path):
    db_path = tmp_path / "dashboard.db"
    _seed_dashboard_db(db_path)

    snapshot = load_dashboard_snapshot(
        str(db_path),
        "DATACENTER",
        run_id="RUN_NEW_B",
    )

    assert snapshot.run.run_id == "RUN_NEW_B"
    assert len(snapshot.source_reports) == 2
    assert len(snapshot.action_summary) == 3
    assert len(snapshot.market_map) == 3
    assert len(snapshot.watchlist) == 3
    assert len(snapshot.tickers) == 3
    assert len(snapshot.decision_trace) == 3
