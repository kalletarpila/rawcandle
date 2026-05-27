from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dev_tools.ecosystem_dashboard_input_model import EcosystemDashboardInput
from dev_tools.ecosystem_dashboard_reports_adapter import (
    clear_reports_persistence_context,
    peek_reports_persistence_context,
)

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


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_run_id(
    ecosystem_code: str,
    report_date: str,
    generated_at_utc: str,
) -> str:
    timestamp = generated_at_utc.replace("-", "").replace(":", "")
    return f"ECO_DASHBOARD_{ecosystem_code}_{report_date}_{timestamp}"


def persist_ecosystem_dashboard_input(
    dashboard_db: str,
    dashboard_input: EcosystemDashboardInput,
    mode: str,
    run_id: str | None = None,
) -> str:
    normalized_mode = mode.strip()
    if normalized_mode not in {"replace-date", "insert"}:
        raise ValueError(f"unsupported mode: {mode}")

    generated_at_utc = _utc_now_text()
    selected_run_id = run_id or _default_run_id(
        dashboard_input.ecosystem_code,
        dashboard_input.report_date,
        generated_at_utc,
    )
    found_reports = sum(
        1 for report in dashboard_input.source_reports if report.status == "OK"
    )
    missing_reports = len(dashboard_input.source_reports) - found_reports
    reports_dir = ""
    source_paths = [
        report.source_report_path
        for report in dashboard_input.source_reports
        if report.source_report_path
    ]
    if source_paths:
        reports_dir = str(Path(source_paths[0]).parent)
    reports_context = peek_reports_persistence_context(dashboard_input)
    if reports_context is not None:
        reports_dir = reports_context.reports_dir

    conn = connect_dashboard_db(dashboard_db)
    ensure_dashboard_schema(conn)
    try:
        conn.execute("BEGIN")
        if normalized_mode == "replace-date":
            delete_runs_for_ecosystem_date(
                conn,
                ecosystem_code=dashboard_input.ecosystem_code,
                report_date=dashboard_input.report_date,
            )
        else:
            assert_run_id_missing(conn, selected_run_id)

        if reports_context is not None:
            source_report_rows = [
                (
                    selected_run_id,
                    dashboard_input.ecosystem_code,
                    dashboard_input.report_date,
                    report.horizon,
                    "dashboard_report",
                    report.path if report.path and report.path.lower().endswith(".md") else None,
                    report.path if report.path and report.path.lower().endswith(".csv") else None,
                    None,
                    report.status,
                    generated_at_utc,
                )
                for report in reports_context.dashboard_status.reports
            ]
            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_source_reports (
                    run_id,
                    ecosystem_code,
                    report_date,
                    horizon,
                    report_kind,
                    markdown_path,
                    csv_path,
                    modified_at_utc,
                    status,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                source_report_rows,
            )

            conn.execute(
                """
                INSERT INTO ecosystem_dashboard_runs (
                    run_id,
                    ecosystem_code,
                    report_date,
                    taxonomy_version,
                    generated_at_utc,
                    reports_dir,
                    selection_mode,
                    readiness,
                    found_reports,
                    missing_reports,
                    total_parsed_rows,
                    total_parse_warnings,
                    decision_total,
                    market_map_rows,
                    watchlist_rows,
                    ticker_rows,
                    source_reports_count,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    selected_run_id,
                    dashboard_input.ecosystem_code,
                    dashboard_input.report_date,
                    None,
                    generated_at_utc,
                    reports_dir,
                    "report_date",
                    reports_context.dashboard_status.overall_status,
                    found_reports,
                    missing_reports,
                    reports_context.parse_result.total_row_count,
                    reports_context.parse_result.total_warning_count,
                    len(reports_context.decision_result.decisions),
                    len(reports_context.market_map_rows),
                    len(reports_context.watchlist_rows),
                    len(reports_context.ticker_rows),
                    len(source_report_rows),
                    generated_at_utc,
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_action_summary (
                    run_id,
                    ecosystem_code,
                    action,
                    count,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        action,
                        reports_context.decision_result.action_counts.get(action, 0),
                        generated_at_utc,
                    )
                    for action in (
                        "SELL",
                        "REDUCE",
                        "TIGHTEN_STOP",
                        "BLOCKED",
                        "WAIT_PULLBACK",
                        "BUY_NOW",
                        "WATCH",
                        "NEUTRAL",
                    )
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_market_map (
                    run_id,
                    ecosystem_code,
                    report_date,
                    market_level,
                    name,
                    parent_name,
                    layer,
                    subindustry,
                    taxonomy_path,
                    taxonomy_version,
                    current_status,
                    start_status_30d,
                    status_change_30d,
                    status_change_5d,
                    window_status_30d,
                    window_status_5d,
                    window_status_2d,
                    overheat_risk,
                    pct_above_ema20,
                    pct_above_ma10,
                    ema20_breadth_delta_5d,
                    return_5d,
                    return_10d,
                    return_20d,
                    return_60d,
                    dow_trend_state,
                    dow_trend_state_age_td,
                    latest_structure_label,
                    latest_structure_age_td,
                    latest_bos_event_type,
                    latest_bos_age_td,
                    latest_reset_reason,
                    latest_reset_age_td,
                    latest_candle,
                    latest_candle_age_td,
                    latest_divergence,
                    latest_divergence_age_td,
                    latest_chart_pattern,
                    latest_chart_pattern_age_td,
                    source_horizons,
                    source_files,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        dashboard_input.report_date,
                        row.market_level,
                        row.name,
                        (
                            None
                            if row.market_level == "ECOSYSTEM"
                            else (
                                "DC_ECOSYSTEM_TOTAL"
                                if row.market_level == "LAYER"
                                else row.layer
                            )
                        ),
                        row.layer,
                        row.name if row.market_level == "SUBINDUSTRY" else None,
                        (
                            None
                            if row.market_level == "ECOSYSTEM"
                            else (
                                f"DC_ECOSYSTEM_TOTAL > {row.name}"
                                if row.market_level == "LAYER"
                                else f"DC_ECOSYSTEM_TOTAL > {row.layer or '-'} > {row.name}"
                            )
                        ),
                        None,
                        row.current_status,
                        row.start_status_30d,
                        row.status_change_30d,
                        row.status_change_5d,
                        row.window_status_30d,
                        row.window_status_5d,
                        row.window_status_2d,
                        row.overheat_risk,
                        row.pct_above_ema20,
                        row.pct_above_ma10,
                        row.ema20_breadth_delta_5d,
                        row.return_5d,
                        row.return_10d,
                        row.return_20d,
                        row.return_60d,
                        row.dow_trend_state,
                        row.dow_trend_state_age_td,
                        row.latest_structure_label,
                        row.latest_structure_age_td,
                        row.latest_bos_event_type,
                        row.latest_bos_age_td,
                        row.latest_reset_reason,
                        row.latest_reset_age_td,
                        row.latest_candle,
                        row.latest_candle_age_td,
                        row.latest_divergence,
                        row.latest_divergence_age_td,
                        row.latest_chart_pattern,
                        row.latest_chart_pattern_age_td,
                        row.source_horizons,
                        row.source_files,
                        generated_at_utc,
                    )
                    for row in reports_context.market_map_rows
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_watchlist_status (
                    run_id,
                    ecosystem_code,
                    report_date,
                    ticker,
                    action,
                    severity,
                    primary_reason,
                    current_status,
                    start_status_30d,
                    status_change_30d,
                    status_change_5d,
                    window_status_30d,
                    window_status_5d,
                    window_status_2d,
                    ma_break_status,
                    freshness_status,
                    trend_state,
                    trend_state_age_td,
                    latest_structure_label,
                    latest_structure_age_td,
                    latest_bos_event_type,
                    latest_bos_age_td,
                    latest_reset_reason,
                    latest_reset_age_td,
                    latest_candle,
                    latest_candle_age_td,
                    latest_divergence,
                    latest_divergence_age_td,
                    latest_chart_pattern,
                    latest_chart_pattern_age_td,
                    pullback_validity,
                    entry_readiness,
                    candidate_priority,
                    candidate_priority_label,
                    daily_status,
                    rolling_2d_status,
                    rolling_5d_status,
                    rolling_30d_status,
                    horizons_present,
                    source_files,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        dashboard_input.report_date,
                        row.ticker,
                        row.action,
                        row.severity,
                        row.primary_reason,
                        row.current_status,
                        row.start_status_30d,
                        row.status_change_30d,
                        row.status_change_5d,
                        row.window_status_30d,
                        row.window_status_5d,
                        row.window_status_2d,
                        row.ma_break_status,
                        row.freshness_status,
                        row.trend_state,
                        row.trend_state_age_td,
                        row.latest_structure_label,
                        row.latest_structure_age_td,
                        row.latest_bos_event_type,
                        row.latest_bos_age_td,
                        row.latest_reset_reason,
                        row.latest_reset_age_td,
                        row.latest_candle,
                        row.latest_candle_age_td,
                        row.latest_divergence,
                        row.latest_divergence_age_td,
                        row.latest_chart_pattern,
                        row.latest_chart_pattern_age_td,
                        row.pullback_validity,
                        row.entry_readiness,
                        row.candidate_priority,
                        row.candidate_priority_label,
                        row.daily_status,
                        row.rolling_2d_status,
                        row.rolling_5d_status,
                        row.rolling_30d_status,
                        row.horizons_present,
                        row.source_files,
                        generated_at_utc,
                    )
                    for row in reports_context.watchlist_rows
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_ticker_status (
                    run_id,
                    ecosystem_code,
                    report_date,
                    ticker,
                    action,
                    severity,
                    primary_reason,
                    current_status,
                    start_status_30d,
                    status_change_30d,
                    status_change_5d,
                    window_status_30d,
                    window_status_5d,
                    window_status_2d,
                    ma_break_status,
                    freshness_status,
                    trend_state,
                    trend_state_age_td,
                    latest_structure_label,
                    latest_structure_age_td,
                    latest_bos_event_type,
                    latest_bos_age_td,
                    latest_reset_reason,
                    latest_reset_age_td,
                    latest_candle,
                    latest_candle_age_td,
                    latest_divergence,
                    latest_divergence_age_td,
                    latest_chart_pattern,
                    latest_chart_pattern_age_td,
                    pullback_validity,
                    entry_readiness,
                    candidate_priority,
                    candidate_priority_label,
                    daily_status,
                    rolling_2d_status,
                    rolling_5d_status,
                    rolling_30d_status,
                    horizons_present,
                    source_files,
                    is_watchlist,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        dashboard_input.report_date,
                        row.ticker,
                        row.action,
                        row.severity,
                        row.primary_reason,
                        row.current_status,
                        row.start_status_30d,
                        row.status_change_30d,
                        row.status_change_5d,
                        row.window_status_30d,
                        row.window_status_5d,
                        row.window_status_2d,
                        row.ma_break_status,
                        row.freshness_status,
                        row.trend_state,
                        row.trend_state_age_td,
                        row.latest_structure_label,
                        row.latest_structure_age_td,
                        row.latest_bos_event_type,
                        row.latest_bos_age_td,
                        row.latest_reset_reason,
                        row.latest_reset_age_td,
                        row.latest_candle,
                        row.latest_candle_age_td,
                        row.latest_divergence,
                        row.latest_divergence_age_td,
                        row.latest_chart_pattern,
                        row.latest_chart_pattern_age_td,
                        row.pullback_validity,
                        row.entry_readiness,
                        row.candidate_priority,
                        row.candidate_priority_label,
                        row.daily_status,
                        row.rolling_2d_status,
                        row.rolling_5d_status,
                        row.rolling_30d_status,
                        row.horizons_present,
                        row.source_files,
                        row.is_watchlist,
                        generated_at_utc,
                    )
                    for row in reports_context.ticker_rows
                ),
            )

            trace_rows = [
                (decision.ticker, trace_index, trace)
                for decision in reports_context.decision_result.decisions
                for trace_index, trace in enumerate(decision.decision_trace)
            ]
            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_decision_trace (
                    run_id,
                    ecosystem_code,
                    ticker,
                    trace_index,
                    action,
                    matched_rule,
                    matched_token,
                    matched_value,
                    horizon,
                    field,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        ticker,
                        trace_index,
                        trace.action,
                        trace.matched_rule,
                        trace.matched_token,
                        trace.matched_value,
                        trace.horizon,
                        trace.field_name,
                        generated_at_utc,
                    )
                    for ticker, trace_index, trace in trace_rows
                ),
            )
        else:
            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_source_reports (
                    run_id,
                    ecosystem_code,
                    report_date,
                    horizon,
                    report_kind,
                    markdown_path,
                    csv_path,
                    modified_at_utc,
                    status,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        dashboard_input.report_date,
                        report.source_report_type or "",
                        report.source_report_type or "structured_input",
                        report.source_report_path,
                        None,
                        None,
                        report.status or "",
                        generated_at_utc,
                    )
                    for report in dashboard_input.source_reports
                ),
            )

            conn.execute(
                """
                INSERT INTO ecosystem_dashboard_runs (
                    run_id,
                    ecosystem_code,
                    report_date,
                    taxonomy_version,
                    generated_at_utc,
                    reports_dir,
                    selection_mode,
                    readiness,
                    found_reports,
                    missing_reports,
                    total_parsed_rows,
                    total_parse_warnings,
                    decision_total,
                    market_map_rows,
                    watchlist_rows,
                    ticker_rows,
                    source_reports_count,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    selected_run_id,
                    dashboard_input.ecosystem_code,
                    dashboard_input.report_date,
                    None,
                    generated_at_utc,
                    reports_dir,
                    "structured_input",
                    dashboard_input.readiness or "UNKNOWN",
                    found_reports,
                    missing_reports,
                    dashboard_input.total_parsed_rows or 0,
                    dashboard_input.total_parse_warnings or 0,
                    len(dashboard_input.tickers),
                    len(dashboard_input.market_map),
                    len(dashboard_input.watchlist),
                    len(dashboard_input.tickers),
                    len(dashboard_input.source_reports),
                    generated_at_utc,
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_action_summary (
                    run_id,
                    ecosystem_code,
                    action,
                    count,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        row.action_bucket or row.action_label or "",
                        row.ticker_count or 0,
                        generated_at_utc,
                    )
                    for row in dashboard_input.action_summary
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_market_map (
                    run_id,
                    ecosystem_code,
                    report_date,
                    market_level,
                    name,
                    parent_name,
                    layer,
                    subindustry,
                    taxonomy_path,
                    taxonomy_version,
                    current_status,
                    start_status_30d,
                    status_change_30d,
                    status_change_5d,
                    window_status_30d,
                    window_status_5d,
                    window_status_2d,
                    overheat_risk,
                    pct_above_ema20,
                    pct_above_ma10,
                    ema20_breadth_delta_5d,
                    return_5d,
                    return_10d,
                    return_20d,
                    return_60d,
                    dow_trend_state,
                    dow_trend_state_age_td,
                    latest_structure_label,
                    latest_structure_age_td,
                    latest_bos_event_type,
                    latest_bos_age_td,
                    latest_reset_reason,
                    latest_reset_age_td,
                    latest_candle,
                    latest_candle_age_td,
                    latest_divergence,
                    latest_divergence_age_td,
                    latest_chart_pattern,
                    latest_chart_pattern_age_td,
                    source_horizons,
                    source_files,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        dashboard_input.report_date,
                        (
                            row.market_level
                            or (
                                "SUBINDUSTRY"
                                if row.subindustry_name
                                else ("LAYER" if row.layer_name else "ECOSYSTEM")
                            )
                        ),
                        row.name or row.subindustry_name or row.layer_name or "ECOSYSTEM",
                        row.parent_name if row.parent_name is not None else (
                            row.layer_name if row.subindustry_name else None
                        ),
                        row.layer_name,
                        row.subindustry_name,
                        (
                            row.taxonomy_path
                            if row.taxonomy_path is not None
                            else (
                                f"DC_ECOSYSTEM_TOTAL > {row.layer_name} > {row.subindustry_name}"
                                if row.layer_name and row.subindustry_name
                                else (
                                    f"DC_ECOSYSTEM_TOTAL > {row.layer_name}"
                                    if row.layer_name
                                    else None
                                )
                            )
                        ),
                        None,
                        row.dominant_action_bucket,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        row.avg_return_5d,
                        None,
                        row.avg_return_20d,
                        row.avg_return_60d,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "",
                        "",
                        generated_at_utc,
                    )
                    for row in dashboard_input.market_map
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_watchlist_status (
                    run_id,
                    ecosystem_code,
                    report_date,
                    ticker,
                    action,
                    severity,
                    primary_reason,
                    current_status,
                    start_status_30d,
                    status_change_30d,
                    status_change_5d,
                    window_status_30d,
                    window_status_5d,
                    window_status_2d,
                    ma_break_status,
                    freshness_status,
                    trend_state,
                    trend_state_age_td,
                    latest_structure_label,
                    latest_structure_age_td,
                    latest_bos_event_type,
                    latest_bos_age_td,
                    latest_reset_reason,
                    latest_reset_age_td,
                    latest_candle,
                    latest_candle_age_td,
                    latest_divergence,
                    latest_divergence_age_td,
                    latest_chart_pattern,
                    latest_chart_pattern_age_td,
                    pullback_validity,
                    entry_readiness,
                    candidate_priority,
                    candidate_priority_label,
                    daily_status,
                    rolling_2d_status,
                    rolling_5d_status,
                    rolling_30d_status,
                    horizons_present,
                    source_files,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        dashboard_input.report_date,
                        row.ticker,
                        row.action_bucket,
                        row.action_label,
                        row.watchlist_reason,
                        row.data_status,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        row.trend_state,
                        None,
                        row.latest_structure_label,
                        None,
                        row.latest_bos_event_type,
                        None,
                        row.latest_reset_reason,
                        None,
                        None,
                        row.bullish_candle_signal,
                        None,
                        row.bullish_divergence_signal,
                        None,
                        row.hidden_bullish_divergence_signal,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "",
                        0,
                        generated_at_utc,
                    )
                    for row in dashboard_input.watchlist
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_ticker_status (
                    run_id,
                    ecosystem_code,
                    report_date,
                    ticker,
                    action,
                    severity,
                    primary_reason,
                    current_status,
                    start_status_30d,
                    status_change_30d,
                    status_change_5d,
                    window_status_30d,
                    window_status_5d,
                    window_status_2d,
                    ma_break_status,
                    freshness_status,
                    trend_state,
                    trend_state_age_td,
                    latest_structure_label,
                    latest_structure_age_td,
                    latest_bos_event_type,
                    latest_bos_age_td,
                    latest_reset_reason,
                    latest_reset_age_td,
                    latest_candle,
                    latest_candle_age_td,
                    latest_divergence,
                    latest_divergence_age_td,
                    latest_chart_pattern,
                    latest_chart_pattern_age_td,
                    pullback_validity,
                    entry_readiness,
                    candidate_priority,
                    candidate_priority_label,
                    daily_status,
                    rolling_2d_status,
                    rolling_5d_status,
                    rolling_30d_status,
                    horizons_present,
                    source_files,
                    is_watchlist,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        dashboard_input.report_date,
                        row.ticker,
                        row.action_bucket or row.action_label,
                        row.action_label,
                        row.data_status,
                        row.data_status,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        row.latest_bos_freshness or row.latest_reset_freshness,
                        row.trend_state,
                        None,
                        row.latest_structure_label,
                        None,
                        row.latest_bos_event_type,
                        None,
                        row.latest_reset_reason,
                        None,
                        None,
                        row.bullish_candle_signal,
                        None,
                        row.bullish_divergence_signal,
                        None,
                        row.hidden_bullish_divergence_signal,
                        row.pullback_validity,
                        row.entry_readiness,
                        row.candidate_priority,
                        row.candidate_priority_label,
                        None,
                        None,
                        None,
                        None,
                        "",
                        0,
                        0,
                        generated_at_utc,
                    )
                    for row in dashboard_input.tickers
                ),
            )

            insert_many(
                conn,
                """
                INSERT INTO ecosystem_dashboard_decision_trace (
                    run_id,
                    ecosystem_code,
                    ticker,
                    trace_index,
                    action,
                    matched_rule,
                    matched_token,
                    matched_value,
                    horizon,
                    field,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        selected_run_id,
                        dashboard_input.ecosystem_code,
                        row.ticker,
                        row.trace_order,
                        row.decision,
                        row.rule_name,
                        None,
                        row.input_value,
                        row.rule_group,
                        row.reason,
                        generated_at_utc,
                    )
                    for row in dashboard_input.decision_trace
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        clear_reports_persistence_context(dashboard_input)

    return selected_run_id
