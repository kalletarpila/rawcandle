from __future__ import annotations

import sqlite3


def apply_datacenter_dashboard_migration(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_dashboard_runs (
            run_id TEXT PRIMARY KEY,
            report_date TEXT NOT NULL,
            generated_at_utc TEXT NOT NULL,
            reports_dir TEXT NOT NULL,
            selection_mode TEXT NOT NULL,
            readiness TEXT NOT NULL,
            found_reports INTEGER NOT NULL,
            missing_reports INTEGER NOT NULL,
            total_parsed_rows INTEGER NOT NULL DEFAULT 0,
            total_parse_warnings INTEGER NOT NULL DEFAULT 0,
            decision_total INTEGER NOT NULL DEFAULT 0,
            market_map_rows INTEGER NOT NULL DEFAULT 0,
            watchlist_rows INTEGER NOT NULL DEFAULT 0,
            ticker_rows INTEGER NOT NULL DEFAULT 0,
            source_reports_count INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_runs_report_date
        ON dc_dashboard_runs (report_date)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_runs_created_at_utc
        ON dc_dashboard_runs (created_at_utc)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_dashboard_source_reports (
            run_id TEXT NOT NULL,
            report_date TEXT NOT NULL,
            horizon TEXT NOT NULL,
            report_kind TEXT NOT NULL,
            markdown_path TEXT,
            csv_path TEXT,
            modified_at_utc TEXT,
            status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, horizon, report_kind)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_source_reports_report_date
        ON dc_dashboard_source_reports (report_date)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_source_reports_run_id
        ON dc_dashboard_source_reports (run_id)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_dashboard_action_summary (
            run_id TEXT NOT NULL,
            action TEXT NOT NULL,
            count INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, action)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_dashboard_market_map (
            run_id TEXT NOT NULL,
            report_date TEXT NOT NULL,
            market_level TEXT NOT NULL,
            name TEXT NOT NULL,
            layer TEXT,
            current_status TEXT,
            start_status_30d TEXT,
            status_change_30d TEXT,
            status_change_5d TEXT,
            window_status_30d TEXT,
            window_status_5d TEXT,
            window_status_2d TEXT,
            overheat_risk TEXT,
            pct_above_ema20 REAL,
            pct_above_ma10 REAL,
            ema20_breadth_delta_5d REAL,
            return_5d REAL,
            return_10d REAL,
            return_20d REAL,
            return_60d REAL,
            dow_trend_state TEXT,
            dow_trend_state_age_td INTEGER,
            latest_structure_label TEXT,
            latest_structure_age_td INTEGER,
            latest_bos_event_type TEXT,
            latest_bos_age_td INTEGER,
            latest_reset_reason TEXT,
            latest_reset_age_td INTEGER,
            latest_candle TEXT,
            latest_candle_age_td INTEGER,
            latest_divergence TEXT,
            latest_divergence_age_td INTEGER,
            latest_chart_pattern TEXT,
            latest_chart_pattern_age_td INTEGER,
            source_horizons TEXT,
            source_files TEXT,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, market_level, name)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_market_map_report_date_level
        ON dc_dashboard_market_map (report_date, market_level)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_market_map_run_id_level
        ON dc_dashboard_market_map (run_id, market_level)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_dashboard_watchlist_status (
            run_id TEXT NOT NULL,
            report_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT,
            severity TEXT,
            primary_reason TEXT,
            current_status TEXT,
            start_status_30d TEXT,
            status_change_30d TEXT,
            status_change_5d TEXT,
            window_status_30d TEXT,
            window_status_5d TEXT,
            window_status_2d TEXT,
            ma_break_status TEXT,
            freshness_status TEXT,
            trend_state TEXT,
            trend_state_age_td INTEGER,
            latest_structure_label TEXT,
            latest_structure_age_td INTEGER,
            latest_bos_event_type TEXT,
            latest_bos_age_td INTEGER,
            latest_reset_reason TEXT,
            latest_reset_age_td INTEGER,
            latest_candle TEXT,
            latest_candle_age_td INTEGER,
            latest_divergence TEXT,
            latest_divergence_age_td INTEGER,
            latest_chart_pattern TEXT,
            latest_chart_pattern_age_td INTEGER,
            pullback_validity TEXT,
            entry_readiness TEXT,
            candidate_priority INTEGER,
            candidate_priority_label TEXT,
            daily_status TEXT,
            rolling_2d_status TEXT,
            rolling_5d_status TEXT,
            rolling_30d_status TEXT,
            horizons_present TEXT,
            source_files INTEGER,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, ticker)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_watchlist_status_report_date_ticker
        ON dc_dashboard_watchlist_status (report_date, ticker)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_watchlist_status_run_id_action
        ON dc_dashboard_watchlist_status (run_id, action)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_watchlist_status_run_id_candidate_priority
        ON dc_dashboard_watchlist_status (run_id, candidate_priority)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_dashboard_ticker_status (
            run_id TEXT NOT NULL,
            report_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT,
            severity TEXT,
            primary_reason TEXT,
            current_status TEXT,
            start_status_30d TEXT,
            status_change_30d TEXT,
            status_change_5d TEXT,
            window_status_30d TEXT,
            window_status_5d TEXT,
            window_status_2d TEXT,
            ma_break_status TEXT,
            freshness_status TEXT,
            trend_state TEXT,
            trend_state_age_td INTEGER,
            latest_structure_label TEXT,
            latest_structure_age_td INTEGER,
            latest_bos_event_type TEXT,
            latest_bos_age_td INTEGER,
            latest_reset_reason TEXT,
            latest_reset_age_td INTEGER,
            latest_candle TEXT,
            latest_candle_age_td INTEGER,
            latest_divergence TEXT,
            latest_divergence_age_td INTEGER,
            latest_chart_pattern TEXT,
            latest_chart_pattern_age_td INTEGER,
            pullback_validity TEXT,
            entry_readiness TEXT,
            candidate_priority INTEGER,
            candidate_priority_label TEXT,
            daily_status TEXT,
            rolling_2d_status TEXT,
            rolling_5d_status TEXT,
            rolling_30d_status TEXT,
            horizons_present TEXT,
            source_files INTEGER,
            is_watchlist INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, ticker)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_ticker_status_report_date_ticker
        ON dc_dashboard_ticker_status (report_date, ticker)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_ticker_status_run_id_action
        ON dc_dashboard_ticker_status (run_id, action)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_ticker_status_run_id_is_watchlist
        ON dc_dashboard_ticker_status (run_id, is_watchlist)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dc_dashboard_decision_trace (
            run_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            trace_index INTEGER NOT NULL,
            action TEXT,
            matched_rule TEXT,
            matched_token TEXT,
            matched_value TEXT,
            horizon TEXT,
            field TEXT,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, ticker, trace_index)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_decision_trace_run_id_ticker
        ON dc_dashboard_decision_trace (run_id, ticker)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dc_dashboard_decision_trace_run_id_matched_rule
        ON dc_dashboard_decision_trace (run_id, matched_rule)
        """
    )
