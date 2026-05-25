from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

SQLITE_BUSY_TIMEOUT_MS = 30_000
SQLITE_CONNECT_TIMEOUT_SECONDS = 30.0


def connect_dashboard_db(db_path: str) -> sqlite3.Connection:
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        timeout=SQLITE_CONNECT_TIMEOUT_SECONDS,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def ensure_dashboard_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ecosystem_dashboard_runs (
            run_id TEXT PRIMARY KEY,
            ecosystem_code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            taxonomy_version TEXT,
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
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_runs_ecosystem_date
        ON ecosystem_dashboard_runs (ecosystem_code, report_date)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_runs_ecosystem_created
        ON ecosystem_dashboard_runs (ecosystem_code, created_at_utc)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ecosystem_dashboard_source_reports (
            run_id TEXT NOT NULL,
            ecosystem_code TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_source_reports_ecosystem_date
        ON ecosystem_dashboard_source_reports (ecosystem_code, report_date)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_source_reports_run_id
        ON ecosystem_dashboard_source_reports (run_id)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ecosystem_dashboard_action_summary (
            run_id TEXT NOT NULL,
            ecosystem_code TEXT NOT NULL,
            action TEXT NOT NULL,
            count INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, action)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_action_summary_ecosystem_action
        ON ecosystem_dashboard_action_summary (ecosystem_code, action)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_action_summary_run_id
        ON ecosystem_dashboard_action_summary (run_id)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ecosystem_dashboard_market_map (
            run_id TEXT NOT NULL,
            ecosystem_code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            market_level TEXT NOT NULL,
            name TEXT NOT NULL,
            parent_name TEXT,
            layer TEXT,
            subindustry TEXT,
            taxonomy_path TEXT,
            taxonomy_version TEXT,
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
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_market_map_ecosystem_date_level
        ON ecosystem_dashboard_market_map (ecosystem_code, report_date, market_level)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_market_map_run_id_level
        ON ecosystem_dashboard_market_map (run_id, market_level)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ecosystem_dashboard_watchlist_status (
            run_id TEXT NOT NULL,
            ecosystem_code TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_watchlist_status_ecosystem_date_ticker
        ON ecosystem_dashboard_watchlist_status (ecosystem_code, report_date, ticker)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_watchlist_status_run_id_action
        ON ecosystem_dashboard_watchlist_status (run_id, action)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_watchlist_status_run_id_candidate_priority
        ON ecosystem_dashboard_watchlist_status (run_id, candidate_priority)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ecosystem_dashboard_ticker_status (
            run_id TEXT NOT NULL,
            ecosystem_code TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_ticker_status_ecosystem_date_ticker
        ON ecosystem_dashboard_ticker_status (ecosystem_code, report_date, ticker)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_ticker_status_run_id_action
        ON ecosystem_dashboard_ticker_status (run_id, action)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_ticker_status_run_id_is_watchlist
        ON ecosystem_dashboard_ticker_status (run_id, is_watchlist)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ecosystem_dashboard_decision_trace (
            run_id TEXT NOT NULL,
            ecosystem_code TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_decision_trace_ecosystem_run_ticker
        ON ecosystem_dashboard_decision_trace (ecosystem_code, run_id, ticker)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ecosystem_dashboard_decision_trace_ecosystem_run_rule
        ON ecosystem_dashboard_decision_trace (ecosystem_code, run_id, matched_rule)
        """
    )
    conn.commit()


def delete_runs_for_ecosystem_date(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    report_date: str,
) -> None:
    child_tables = (
        "ecosystem_dashboard_source_reports",
        "ecosystem_dashboard_action_summary",
        "ecosystem_dashboard_market_map",
        "ecosystem_dashboard_watchlist_status",
        "ecosystem_dashboard_ticker_status",
        "ecosystem_dashboard_decision_trace",
    )
    for table in child_tables:
        conn.execute(
            f"""
            DELETE FROM {table}
            WHERE run_id IN (
                SELECT run_id
                FROM ecosystem_dashboard_runs
                WHERE ecosystem_code = ? AND report_date = ?
            )
            """,
            (ecosystem_code, report_date),
        )
    conn.execute(
        """
        DELETE FROM ecosystem_dashboard_runs
        WHERE ecosystem_code = ? AND report_date = ?
        """,
        (ecosystem_code, report_date),
    )


def assert_run_id_missing(conn: sqlite3.Connection, run_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM ecosystem_dashboard_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is not None:
        raise ValueError(f"run_id already exists: {run_id}")


def insert_many(
    conn: sqlite3.Connection,
    sql: str,
    rows: Iterable[tuple[object, ...]],
) -> None:
    materialized_rows = list(rows)
    if not materialized_rows:
        return
    conn.executemany(sql, materialized_rows)
