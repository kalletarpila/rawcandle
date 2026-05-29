from __future__ import annotations

from pathlib import Path

from dev_tools.ecosystem_dashboard_persistence import (
    connect_dashboard_db,
    ensure_dashboard_schema,
)
from dev_tools.run_datacenter_dashboard_markdown import (
    generate_datacenter_dashboard_markdown_file,
)


def _seed_dashboard_db(db_path: Path) -> str:
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
                "RUN_MD",
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
                2,
                1,
                0,
                2,
                1,
                "2026-05-25T11:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO ecosystem_dashboard_action_summary (
                run_id, ecosystem_code, action, count, created_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("RUN_MD", "DATACENTER", "WATCH", 2, "2026-05-25T11:00:00Z"),
        )
        conn.execute(
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
            (
                "RUN_MD",
                "DATACENTER",
                "2026-05-22",
                "SUBINDUSTRY",
                "Cloud|AI",
                "Technology",
                "Technology",
                "Cloud",
                "Technology > Cloud",
                None,
                "BUY_ZONE",
                "WATCH",
                "WATCH -> BUY_ZONE",
                "",
                "BUY_ZONE",
                "",
                "",
                "LOW",
                62.5,
                58.0,
                4.0,
                0.12,
                0.18,
                0.25,
                0.44,
                "UP",
                8,
                "HH",
                3,
                "BOS_UP",
                2,
                "Reset\nComplete",
                1,
                None,
                None,
                None,
                None,
                "BASE_BREAKOUT",
                5,
                "daily,rolling_30d",
                "market|map.md",
                "2026-05-25T11:00:00Z",
            ),
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
                    "RUN_MD",
                    "DATACENTER",
                    "2026-05-22",
                    "MSFT",
                    "WATCH",
                    "LOW",
                    "trend_ok",
                    "BUY_ZONE",
                    "WATCH",
                    "WATCH -> BUY_ZONE",
                    "",
                    "BUY_ZONE",
                    "",
                    "",
                    "OK",
                    "FRESH",
                    "UP",
                    1,
                    "HL",
                    2,
                    "BOS_UP",
                    1,
                    "Reset|Okay",
                    1,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "VALID_PULLBACK",
                    "READY_TO_WATCH",
                    1,
                    "P1_READY_TO_WATCH",
                    "BUY_ZONE",
                    "WATCH",
                    "WATCH",
                    "BUY_ZONE",
                    "daily,rolling_30d",
                    "msft|daily.md",
                    1,
                    "2026-05-25T11:00:00Z",
                ),
                (
                    "RUN_MD",
                    "DATACENTER",
                    "2026-05-22",
                    "NVDA",
                    "SELL",
                    "HIGH",
                    "risk",
                    "BREAKOUT_READY",
                    "WATCH",
                    "WATCH -> BREAKOUT_READY",
                    "PULLBACK -> BREAKOUT_READY",
                    "WATCH",
                    "PULLBACK",
                    "BREAKOUT_READY",
                    "EMA20_WARNING",
                    "FRESH",
                    "UP",
                    2,
                    "HH",
                    3,
                    "BOS_UP",
                    2,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "NO_PULLBACK",
                    "NOT_READY",
                    5,
                    "P5_NOT_READY",
                    "BREAKOUT_READY",
                    "",
                    "",
                    "WATCH",
                    "daily,rolling_30d",
                    "nvda.md",
                    0,
                    "2026-05-25T11:00:00Z",
                ),
            ],
        )
        for trace_index in range(101):
            conn.execute(
                """
                INSERT INTO ecosystem_dashboard_decision_trace (
                    run_id, ecosystem_code, ticker, trace_index, action, matched_rule,
                    matched_token, matched_value, horizon, field, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "RUN_MD",
                    "DATACENTER",
                    "NVDA" if trace_index % 2 else "MSFT",
                    trace_index,
                    "WATCH",
                    f"RULE_{trace_index}",
                    "token|value",
                    "line\nbreak",
                    "daily",
                    "reason",
                    "2026-05-25T11:00:00Z",
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return "RUN_MD"


def test_generate_datacenter_dashboard_markdown_file_renders_db_snapshot(tmp_path):
    dashboard_db = tmp_path / "dashboard.db"
    output_path = tmp_path / "dashboard.md"
    run_id = _seed_dashboard_db(dashboard_db)

    result = generate_datacenter_dashboard_markdown_file(
        dashboard_db=str(dashboard_db),
        output_path=str(output_path),
        run_id=run_id,
    )

    assert result.output_path == str(output_path)
    text = output_path.read_text(encoding="utf-8")
    assert "# Datacenter Dashboard - 2026-05-22" in text
    assert "## Run Summary" in text
    assert "- ecosystem_code: DATACENTER" in text
    assert "## Action Summary" in text
    assert "| action | count |" in text
    assert "## Market Map" in text
    assert "Cloud\\|AI" in text
    assert "Reset Complete" in text
    assert "market\\|map.md" in text
    assert "## Watchlist" in text
    assert "No watchlist rows." in text
    assert "## Tickers" in text
    assert (
        "| ticker | action | pullback validity | entry readiness | candidate priority label |"
        in text
    )
    assert "## Decision Trace" in text
    assert "Decision trace truncated: showing 50 of 101 rows." in text
    assert "token\\|value" in text
    assert "line break" in text
