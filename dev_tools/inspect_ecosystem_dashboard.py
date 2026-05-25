from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_html import _REPORT_DATE_RE

REQUIRED_TABLES = (
    "ecosystem_dashboard_runs",
    "ecosystem_dashboard_source_reports",
    "ecosystem_dashboard_action_summary",
    "ecosystem_dashboard_market_map",
    "ecosystem_dashboard_watchlist_status",
    "ecosystem_dashboard_ticker_status",
    "ecosystem_dashboard_decision_trace",
)
ACTION_ORDER = (
    "SELL",
    "REDUCE",
    "TIGHTEN_STOP",
    "BLOCKED",
    "WAIT_PULLBACK",
    "BUY_NOW",
    "WATCH",
    "NEUTRAL",
)
MARKET_LEVEL_ORDER = (
    "ECOSYSTEM",
    "LAYER",
    "SUBINDUSTRY",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect ecosystem dashboard snapshots from a read-only SQLite DB."
    )
    parser.add_argument("--dashboard-db", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date")
    parser.add_argument("--run-id")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--show-runs", action="store_true")
    parser.add_argument("--show-action-summary", action="store_true")
    parser.add_argument("--show-market-map", action="store_true")
    parser.add_argument("--show-watchlist", action="store_true")
    parser.add_argument("--show-tickers", action="store_true")
    parser.add_argument("--show-trace", action="store_true")
    parser.add_argument("--ticker")
    parser.add_argument("--market-level")
    parser.add_argument("--action")
    parser.add_argument("--format", choices=("text", "csv"), default="text")
    return parser


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _validate_report_date(report_date: str | None) -> str | None:
    if report_date is None:
        return None
    normalized = report_date.strip()
    if not _REPORT_DATE_RE.match(normalized):
        raise ValueError(f"invalid report_date format: {normalized}")
    return normalized


def _validate_market_level(market_level: str | None) -> str | None:
    if market_level is None:
        return None
    return market_level.strip().upper()


def _validate_limit(limit: int) -> int:
    if limit < 0:
        raise ValueError(f"invalid limit: {limit}")
    return limit


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _require_tables(conn: sqlite3.Connection) -> None:
    missing = [table for table in REQUIRED_TABLES if not _table_exists(conn, table)]
    if missing:
        raise RuntimeError(f"required tables missing: {', '.join(missing)}")


def _action_sort_key(action: str) -> tuple[int, str]:
    normalized = _normalize_text(action).upper()
    if normalized in ACTION_ORDER:
        return (ACTION_ORDER.index(normalized), normalized)
    return (len(ACTION_ORDER), normalized)


def _market_level_sort_key(level: str) -> tuple[int, str]:
    normalized = _normalize_text(level).upper()
    if normalized in MARKET_LEVEL_ORDER:
        return (MARKET_LEVEL_ORDER.index(normalized), normalized)
    return (len(MARKET_LEVEL_ORDER), normalized)


def _load_matching_runs(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    report_date: str | None,
    run_id: str | None,
) -> list[sqlite3.Row]:
    sql = """
        SELECT
            run_id,
            ecosystem_code,
            report_date,
            created_at_utc,
            readiness,
            decision_total,
            market_map_rows,
            watchlist_rows,
            ticker_rows,
            source_reports_count
        FROM ecosystem_dashboard_runs
        WHERE ecosystem_code = ?
    """
    params: list[object] = [ecosystem_code]
    if report_date is not None:
        sql += " AND report_date = ?"
        params.append(report_date)
    if run_id is not None:
        sql += " AND run_id = ?"
        params.append(run_id)
    sql += " ORDER BY report_date DESC, created_at_utc DESC, run_id ASC"
    return list(conn.execute(sql, params).fetchall())


def _select_run(
    matching_runs: list[sqlite3.Row],
    *,
    explicit_run_id: str | None,
    latest: bool,
    detail_requested: bool,
) -> sqlite3.Row | None:
    if explicit_run_id is not None:
        if not matching_runs:
            raise RuntimeError(f"run_id not found: {explicit_run_id}")
        return matching_runs[0]
    if latest:
        if not matching_runs:
            return None
        return sorted(
            matching_runs,
            key=lambda row: (
                _normalize_text(row["created_at_utc"]),
                _normalize_text(row["run_id"]),
            ),
            reverse=True,
        )[0]
    if len(matching_runs) == 1:
        return matching_runs[0]
    if detail_requested and len(matching_runs) > 1:
        raise RuntimeError(
            "multiple runs match; use --run-id or --latest for detail views"
        )
    return None


def _count_for_run(conn: sqlite3.Connection, table: str, run_id: str) -> int:
    row = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _summary_lines(
    *,
    dashboard_db: str,
    ecosystem_code: str,
    report_date: str | None,
    run_id: str | None,
    matching_runs: list[sqlite3.Row],
    selected_run: sqlite3.Row | None,
    decision_total: int,
    market_map_rows: int,
    watchlist_rows: int,
    ticker_rows: int,
    trace_rows: int,
) -> list[str]:
    lines = [
        "SUMMARY ecosystem_dashboard_inspect.status=OK",
        f"SUMMARY ecosystem_dashboard_inspect.dashboard_db={dashboard_db}",
        f"SUMMARY ecosystem_dashboard_inspect.ecosystem_code={ecosystem_code}",
        f"SUMMARY ecosystem_dashboard_inspect.report_date={report_date or 'ALL'}",
        f"SUMMARY ecosystem_dashboard_inspect.run_id={run_id or 'NONE'}",
        f"SUMMARY ecosystem_dashboard_inspect.runs_found={len(matching_runs)}",
        f"SUMMARY ecosystem_dashboard_inspect.selected_run_id={_normalize_text(selected_run['run_id']) if selected_run is not None else 'NONE'}",
        f"SUMMARY ecosystem_dashboard_inspect.selected_report_date={_normalize_text(selected_run['report_date']) if selected_run is not None else 'NONE'}",
        f"SUMMARY ecosystem_dashboard_inspect.readiness={_normalize_text(selected_run['readiness']) if selected_run is not None else 'NONE'}",
        f"SUMMARY ecosystem_dashboard_inspect.decision_total={decision_total}",
        f"SUMMARY ecosystem_dashboard_inspect.market_map_rows={market_map_rows}",
        f"SUMMARY ecosystem_dashboard_inspect.watchlist_rows={watchlist_rows}",
        f"SUMMARY ecosystem_dashboard_inspect.ticker_rows={ticker_rows}",
        f"SUMMARY ecosystem_dashboard_inspect.trace_rows={trace_rows}",
    ]
    compatibility_lines = [
        f"SUMMARY ecosystem_code={ecosystem_code}",
        f"SUMMARY selected_report_date={_normalize_text(selected_run['report_date']) if selected_run is not None else ''}",
        f"SUMMARY selected_run_id={_normalize_text(selected_run['run_id']) if selected_run is not None else ''}",
        "SUMMARY status=OK",
    ]
    for line in compatibility_lines:
        if line not in lines:
            lines.append(line)
    return lines


def _print_section(header: str, rows: list[list[object]]) -> None:
    print(header)
    for row in rows:
        print(";".join(_normalize_text(value) for value in row))


def _load_action_summary(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    limit: int,
) -> list[list[object]]:
    rows = list(
        conn.execute(
            """
            SELECT action, count
            FROM ecosystem_dashboard_action_summary
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
    )
    rows = sorted(
        rows,
        key=lambda row: _action_sort_key(row["action"]),
    )
    return [[row["action"], row["count"]] for row in rows[:limit]]


def _load_market_map(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    market_level: str | None,
    limit: int,
) -> list[list[object]]:
    sql = """
        SELECT
            market_level,
            name,
            layer,
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
            source_files
        FROM ecosystem_dashboard_market_map
        WHERE run_id = ?
    """
    params: list[object] = [run_id]
    if market_level is not None:
        sql += " AND market_level = ?"
        params.append(market_level)
    rows = list(conn.execute(sql, params).fetchall())
    rows = sorted(
        rows,
        key=lambda row: (
            _market_level_sort_key(row["market_level"]),
            1 if not _normalize_text(row["layer"]) else 0,
            _normalize_text(row["layer"]),
            _normalize_text(row["name"]),
        ),
    )
    return [
        [
            row["market_level"],
            row["name"],
            row["layer"],
            row["current_status"],
            row["start_status_30d"],
            row["status_change_30d"],
            row["status_change_5d"],
            row["window_status_30d"],
            row["window_status_5d"],
            row["window_status_2d"],
            row["overheat_risk"],
            row["pct_above_ema20"],
            row["pct_above_ma10"],
            row["ema20_breadth_delta_5d"],
            row["return_5d"],
            row["return_10d"],
            row["return_20d"],
            row["return_60d"],
            row["dow_trend_state"],
            row["dow_trend_state_age_td"],
            row["latest_structure_label"],
            row["latest_structure_age_td"],
            row["latest_bos_event_type"],
            row["latest_bos_age_td"],
            row["latest_reset_reason"],
            row["latest_reset_age_td"],
            row["latest_candle"],
            row["latest_candle_age_td"],
            row["latest_divergence"],
            row["latest_divergence_age_td"],
            row["latest_chart_pattern"],
            row["latest_chart_pattern_age_td"],
            row["source_horizons"],
            row["source_files"],
        ]
        for row in rows[:limit]
    ]


def _load_watchlist(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str | None,
    action: str | None,
    limit: int,
) -> list[list[object]]:
    sql = """
        SELECT
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
            source_files
        FROM ecosystem_dashboard_watchlist_status
        WHERE run_id = ?
    """
    params: list[object] = [run_id]
    if ticker is not None:
        sql += " AND UPPER(ticker) = ?"
        params.append(ticker.upper())
    if action is not None:
        sql += " AND UPPER(action) = ?"
        params.append(action.upper())
    rows = list(conn.execute(sql, params).fetchall())
    rows = sorted(
        rows,
        key=lambda row: (
            _action_sort_key(row["action"]),
            _normalize_text(row["ticker"]),
        ),
    )
    return [
        [
            row["ticker"],
            row["action"],
            row["severity"],
            row["primary_reason"],
            row["current_status"],
            row["start_status_30d"],
            row["status_change_30d"],
            row["status_change_5d"],
            row["window_status_30d"],
            row["window_status_5d"],
            row["window_status_2d"],
            row["ma_break_status"],
            row["freshness_status"],
            row["trend_state"],
            row["trend_state_age_td"],
            row["latest_structure_label"],
            row["latest_structure_age_td"],
            row["latest_bos_event_type"],
            row["latest_bos_age_td"],
            row["latest_reset_reason"],
            row["latest_reset_age_td"],
            row["latest_candle"],
            row["latest_candle_age_td"],
            row["latest_divergence"],
            row["latest_divergence_age_td"],
            row["latest_chart_pattern"],
            row["latest_chart_pattern_age_td"],
            row["pullback_validity"],
            row["entry_readiness"],
            row["candidate_priority"],
            row["candidate_priority_label"],
            row["daily_status"],
            row["rolling_2d_status"],
            row["rolling_5d_status"],
            row["rolling_30d_status"],
            row["horizons_present"],
            row["source_files"],
        ]
        for row in rows[:limit]
    ]


def _load_tickers(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str | None,
    action: str | None,
    limit: int,
) -> list[list[object]]:
    sql = """
        SELECT
            ticker,
            is_watchlist,
            action,
            severity,
            primary_reason,
            current_status,
            ma_break_status,
            freshness_status,
            pullback_validity,
            entry_readiness,
            candidate_priority,
            candidate_priority_label,
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
            daily_status,
            rolling_2d_status,
            rolling_5d_status,
            rolling_30d_status,
            horizons_present
        FROM ecosystem_dashboard_ticker_status
        WHERE run_id = ?
    """
    params: list[object] = [run_id]
    if ticker is not None:
        sql += " AND UPPER(ticker) = ?"
        params.append(ticker.upper())
    if action is not None:
        sql += " AND UPPER(action) = ?"
        params.append(action.upper())
    rows = list(conn.execute(sql, params).fetchall())
    rows = sorted(
        rows,
        key=lambda row: (
            _action_sort_key(row["action"]),
            1 if row["candidate_priority"] is None else 0,
            row["candidate_priority"] if row["candidate_priority"] is not None else 0,
            _normalize_text(row["ticker"]),
        ),
    )
    return [
        [
            row["ticker"],
            row["is_watchlist"],
            row["action"],
            row["severity"],
            row["primary_reason"],
            row["current_status"],
            row["ma_break_status"],
            row["freshness_status"],
            row["pullback_validity"],
            row["entry_readiness"],
            row["candidate_priority"],
            row["candidate_priority_label"],
            row["trend_state"],
            row["trend_state_age_td"],
            row["latest_structure_label"],
            row["latest_structure_age_td"],
            row["latest_bos_event_type"],
            row["latest_bos_age_td"],
            row["latest_reset_reason"],
            row["latest_reset_age_td"],
            row["latest_candle"],
            row["latest_candle_age_td"],
            row["latest_divergence"],
            row["latest_divergence_age_td"],
            row["latest_chart_pattern"],
            row["latest_chart_pattern_age_td"],
            row["daily_status"],
            row["rolling_2d_status"],
            row["rolling_5d_status"],
            row["rolling_30d_status"],
            row["horizons_present"],
        ]
        for row in rows[:limit]
    ]


def _load_trace(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str | None,
    limit: int,
) -> list[list[object]]:
    sql = """
        SELECT
            ticker,
            trace_index,
            action,
            matched_rule,
            matched_token,
            matched_value,
            horizon,
            field
        FROM ecosystem_dashboard_decision_trace
        WHERE run_id = ?
    """
    params: list[object] = [run_id]
    if ticker is not None:
        sql += " AND UPPER(ticker) = ?"
        params.append(ticker.upper())
    rows = list(conn.execute(sql, params).fetchall())
    rows = sorted(
        rows,
        key=lambda row: (_normalize_text(row["ticker"]), int(row["trace_index"])),
    )
    return [
        [
            row["ticker"],
            row["trace_index"],
            row["action"],
            row["matched_rule"],
            row["matched_token"],
            row["matched_value"],
            row["horizon"],
            row["field"],
        ]
        for row in rows[:limit]
    ]


def _detail_requested(args: argparse.Namespace) -> bool:
    return any(
        (
            args.show_action_summary,
            args.show_market_map,
            args.show_watchlist,
            args.show_tickers,
            args.show_trace,
        )
    )


def inspect_dashboard(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report_date = _validate_report_date(args.report_date)
        market_level = _validate_market_level(args.market_level)
        limit = _validate_limit(args.limit)
        dashboard_db_path = Path(args.dashboard_db)
        if not dashboard_db_path.exists():
            raise FileNotFoundError(f"dashboard_db not found: {args.dashboard_db}")

        conn = _connect_read_only(str(dashboard_db_path))
        conn.row_factory = sqlite3.Row
        try:
            _require_tables(conn)
            matching_runs = _load_matching_runs(
                conn,
                ecosystem_code=args.ecosystem_code,
                report_date=report_date,
                run_id=args.run_id,
            )
            if args.run_id is not None and not matching_runs:
                raise RuntimeError(f"run_id not found: {args.run_id}")
            if not matching_runs:
                raise RuntimeError(
                    f"no runs found for ecosystem_code={args.ecosystem_code}"
                    + (f" report_date={report_date}" if report_date else "")
                )

            selected_run = _select_run(
                matching_runs,
                explicit_run_id=args.run_id,
                latest=args.latest,
                detail_requested=_detail_requested(args),
            )
            if selected_run is not None:
                decision_total = int(selected_run["decision_total"])
                market_map_rows = _count_for_run(
                    conn, "ecosystem_dashboard_market_map", selected_run["run_id"]
                )
                watchlist_rows = _count_for_run(
                    conn, "ecosystem_dashboard_watchlist_status", selected_run["run_id"]
                )
                ticker_rows = _count_for_run(
                    conn, "ecosystem_dashboard_ticker_status", selected_run["run_id"]
                )
                trace_rows = _count_for_run(
                    conn, "ecosystem_dashboard_decision_trace", selected_run["run_id"]
                )
            else:
                decision_total = 0
                market_map_rows = 0
                watchlist_rows = 0
                ticker_rows = 0
                trace_rows = 0

            for line in _summary_lines(
                dashboard_db=args.dashboard_db,
                ecosystem_code=args.ecosystem_code,
                report_date=report_date,
                run_id=args.run_id,
                matching_runs=matching_runs,
                selected_run=selected_run,
                decision_total=decision_total,
                market_map_rows=market_map_rows,
                watchlist_rows=watchlist_rows,
                ticker_rows=ticker_rows,
                trace_rows=trace_rows,
            ):
                print(line)

            if args.show_runs:
                _print_section(
                    "section;runs\nrun_id;ecosystem_code;report_date;created_at_utc;readiness;decision_total;market_map_rows;watchlist_rows;ticker_rows;source_reports_count",
                    [
                        [
                            row["run_id"],
                            row["ecosystem_code"],
                            row["report_date"],
                            row["created_at_utc"],
                            row["readiness"],
                            row["decision_total"],
                            row["market_map_rows"],
                            row["watchlist_rows"],
                            row["ticker_rows"],
                            row["source_reports_count"],
                        ]
                        for row in matching_runs[:limit]
                    ],
                )

            if selected_run is None:
                return 0

            selected_run_id = _normalize_text(selected_run["run_id"])
            if args.show_action_summary:
                _print_section(
                    "section;action_summary\naction;count",
                    _load_action_summary(conn, run_id=selected_run_id, limit=limit),
                )
            if args.show_market_map:
                _print_section(
                    "section;market_map\nmarket_level;name;layer;current_status;start_status_30d;status_change_30d;status_change_5d;window_status_30d;window_status_5d;window_status_2d;overheat_risk;pct_above_ema20;pct_above_ma10;ema20_breadth_delta_5d;return_5d;return_10d;return_20d;return_60d;dow_trend_state;dow_trend_state_age_td;latest_structure_label;latest_structure_age_td;latest_bos_event_type;latest_bos_age_td;latest_reset_reason;latest_reset_age_td;latest_candle;latest_candle_age_td;latest_divergence;latest_divergence_age_td;latest_chart_pattern;latest_chart_pattern_age_td;source_horizons;source_files",
                    _load_market_map(
                        conn,
                        run_id=selected_run_id,
                        market_level=market_level,
                        limit=limit,
                    ),
                )
            if args.show_watchlist:
                _print_section(
                    "section;watchlist\nticker;action;severity;primary_reason;current_status;start_status_30d;status_change_30d;status_change_5d;window_status_30d;window_status_5d;window_status_2d;ma_break_status;freshness_status;trend_state;trend_state_age_td;latest_structure_label;latest_structure_age_td;latest_bos_event_type;latest_bos_age_td;latest_reset_reason;latest_reset_age_td;latest_candle;latest_candle_age_td;latest_divergence;latest_divergence_age_td;latest_chart_pattern;latest_chart_pattern_age_td;pullback_validity;entry_readiness;candidate_priority;candidate_priority_label;daily_status;rolling_2d_status;rolling_5d_status;rolling_30d_status;horizons_present;source_files",
                    _load_watchlist(
                        conn,
                        run_id=selected_run_id,
                        ticker=args.ticker,
                        action=args.action,
                        limit=limit,
                    ),
                )
            if args.show_tickers:
                _print_section(
                    "section;tickers\nticker;is_watchlist;action;severity;primary_reason;current_status;ma_break_status;freshness_status;pullback_validity;entry_readiness;candidate_priority;candidate_priority_label;trend_state;trend_state_age_td;latest_structure_label;latest_structure_age_td;latest_bos_event_type;latest_bos_age_td;latest_reset_reason;latest_reset_age_td;latest_candle;latest_candle_age_td;latest_divergence;latest_divergence_age_td;latest_chart_pattern;latest_chart_pattern_age_td;daily_status;rolling_2d_status;rolling_5d_status;rolling_30d_status;horizons_present",
                    _load_tickers(
                        conn,
                        run_id=selected_run_id,
                        ticker=args.ticker,
                        action=args.action,
                        limit=limit,
                    ),
                )
            if args.show_trace:
                _print_section(
                    "section;decision_trace\nticker;trace_index;action;matched_rule;matched_token;matched_value;horizon;field",
                    _load_trace(
                        conn,
                        run_id=selected_run_id,
                        ticker=args.ticker,
                        limit=limit,
                    ),
                )
        finally:
            conn.close()
    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print("SUMMARY ecosystem_dashboard_inspect.status=FAILED")
        print(f"ERROR: {exc}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return inspect_dashboard(argv)


if __name__ == "__main__":
    raise SystemExit(main())
