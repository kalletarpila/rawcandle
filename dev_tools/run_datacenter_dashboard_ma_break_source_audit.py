from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

TRACE_KEYWORDS = (
    "ma_break",
    "sma50",
    "ema20",
    "sell_signal_detected",
    "return_10d_lt_minus_8pct",
    "close_below_ema20",
    "sell",
)
MA_BREAK_TRACE_KEYWORDS = ("ma_break", "sma50", "ema20")
HARD_SELL_TRACE_KEYWORDS = ("return_10d_lt_minus_8pct", "close_below_ema20", "sell")
SOURCE_FIELDS = (
    "ma_break_status",
    "price_vs_ema20",
    "distance_to_ema20_pct",
    "close_below_ema20",
    "return_10d",
    "return_10d_lt_minus_8pct",
    "exit_risk_signal",
    "exit_risk_severity",
    "latest_bos_event_type",
    "latest_reset_reason",
)
CANDIDATE_SOURCES = (
    ("dc_ticker_swing_signal_daily", "ma_break_status"),
    ("dc_ticker_swing_signal_daily", "distance_to_ema20_pct"),
    ("dc_ticker_swing_signal_daily", "close_below_ema20"),
    ("dc_ticker_swing_signal_daily", "return_10d"),
    ("dc_ticker_swing_signal_daily", "return_10d_lt_minus_8pct"),
    ("dc_dashboard_ticker_enrichment_daily", "ma_break_status"),
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace(";", ",").strip()


def _print_section(name: str) -> None:
    print(f"section;{name}")


def _print_row(prefix: str, *columns: object) -> None:
    print(";".join([prefix, *(_cell(column) for column in columns)]))


def _normalized_action(value: object) -> str:
    return _cell(value).upper()


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    tickers: list[str] = []
    seen: set[str] = set()
    for token in raw.replace(",", " ").split():
        ticker = token.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def _connect_analysis_read_only(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise ValueError(f"analysis_db not found: {path}")
    conn = _connect_read_only(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _require_table(conn: sqlite3.Connection, table_name: str) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"required table missing: {table_name}")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


def _load_analysis_rows(
    analysis_db: str,
    report_date: str,
    tickers: list[str],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], set[str], set[str]]:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, "dc_ticker_swing_signal_daily")
        source_columns = _table_columns(conn, "dc_ticker_swing_signal_daily")
        enrichment_columns: set[str] = set()
        if _table_exists(conn, "dc_dashboard_ticker_enrichment_daily"):
            enrichment_columns = _table_columns(conn, "dc_dashboard_ticker_enrichment_daily")
        if not tickers:
            return {}, {}, source_columns, enrichment_columns
        placeholders = ", ".join("?" for _ in tickers)
        source_select = ", ".join(
            f"{field} AS {field}" if field in source_columns else f"NULL AS {field}"
            for field in ("ticker", *SOURCE_FIELDS)
        )
        source_rows = conn.execute(
            f"""
            SELECT {source_select}
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date = ?
              AND ticker IN ({placeholders})
            ORDER BY ticker ASC
            """,
            (report_date, *tickers),
        ).fetchall()
        source_by_ticker = {
            _cell(row["ticker"]).upper(): {key: row[key] for key in row.keys()}
            for row in source_rows
            if _cell(row["ticker"])
        }
        enrichment_by_ticker: dict[str, dict[str, object]] = {}
        if enrichment_columns:
            enrichment_select = ", ".join(
                f"{field} AS {field}" if field in enrichment_columns else f"NULL AS {field}"
                for field in ("ticker", *SOURCE_FIELDS)
            )
            enrichment_rows = conn.execute(
                f"""
                SELECT {enrichment_select}
                FROM dc_dashboard_ticker_enrichment_daily
                WHERE signal_date = ?
                  AND ticker IN ({placeholders})
                ORDER BY ticker ASC
                """,
                (report_date, *tickers),
            ).fetchall()
            enrichment_by_ticker = {
                _cell(row["ticker"]).upper(): {key: row[key] for key in row.keys()}
                for row in enrichment_rows
                if _cell(row["ticker"])
            }
        return source_by_ticker, enrichment_by_ticker, source_columns, enrichment_columns


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _select_tickers(
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[str]:
    common = sorted(set(reports_by_ticker) & set(enrichment_by_ticker))
    if explicit_tickers:
        return [ticker for ticker in explicit_tickers if ticker in common and ticker != "CRGY"]
    return [
        ticker
        for ticker in common
        if ticker != "CRGY"
        and _normalized_action(reports_by_ticker[ticker].get("action")) == "SELL"
        and _normalized_action(enrichment_by_ticker[ticker].get("action")) == "REDUCE"
    ][:max_examples]


def _trace_value(trace: dict[str, object], *fields: str) -> str:
    for field in fields:
        text = _cell(trace.get(field))
        if text:
            return text
    return ""


def _is_non_empty(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _matches_trace_keywords(trace: dict[str, object]) -> bool:
    haystack = " ".join(
        [
            _trace_value(trace, "matched_rule", "rule_name"),
            _trace_value(trace, "matched_token", "matched_value", "input_value"),
            _trace_value(trace, "field", "field_name", "matched_field"),
        ]
    ).lower()
    return any(keyword in haystack for keyword in TRACE_KEYWORDS)


def _matches_ma_break_trace(trace: dict[str, object]) -> bool:
    haystack = " ".join(
        [
            _trace_value(trace, "matched_rule", "rule_name"),
            _trace_value(trace, "matched_token", "matched_value", "input_value"),
            _trace_value(trace, "field", "field_name", "matched_field"),
        ]
    ).lower()
    return any(keyword in haystack for keyword in MA_BREAK_TRACE_KEYWORDS)


def _matches_hard_sell_trace(trace: dict[str, object]) -> bool:
    haystack = " ".join(
        [
            _trace_value(trace, "matched_rule", "rule_name"),
            _trace_value(trace, "matched_token", "matched_value", "input_value"),
            _trace_value(trace, "field", "field_name", "matched_field"),
        ]
    ).lower()
    return any(keyword in haystack for keyword in HARD_SELL_TRACE_KEYWORDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit MA-break and hard-sell source availability for SELL->REDUCE gaps."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        reports_snapshot = load_dashboard_snapshot(
            dashboard_db=args.reports_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.reports_run_id,
        )
        enrichment_snapshot = load_dashboard_snapshot(
            dashboard_db=args.enrichment_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.enrichment_run_id,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _ticker_map(reports_snapshot.tickers)
    enrichment_by_ticker = _ticker_map(enrichment_snapshot.tickers)
    selected_tickers = _select_tickers(
        reports_by_ticker,
        enrichment_by_ticker,
        _parse_tickers(args.tickers),
        args.max_examples,
    )

    try:
        source_by_ticker, enrichment_analysis_by_ticker, source_columns, enrichment_columns = _load_analysis_rows(
            args.analysis_db,
            args.report_date,
            selected_tickers,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_trace_rows = [
        trace
        for trace in reports_snapshot.decision_trace
        if _cell(trace.get("ticker")).upper() in set(selected_tickers)
        and _matches_trace_keywords(trace)
    ]
    reports_trace_ma_break_matches = sum(1 for trace in reports_trace_rows if _matches_ma_break_trace(trace))
    reports_trace_hard_sell_matches = sum(1 for trace in reports_trace_rows if _matches_hard_sell_trace(trace))

    _print_section("run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
    _print_row("run_summary", "reports", args.reports_dashboard_db, args.reports_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "enrichment", args.enrichment_dashboard_db, args.enrichment_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "analysis", args.analysis_db, "", args.report_date, "analysis_db")

    _print_section("selected_tickers")
    _print_row(
        "selected_tickers",
        "ticker",
        "reports_action",
        "enrichment_action",
        "reports_primary_reason",
        "enrichment_primary_reason",
    )
    for ticker in selected_tickers:
        _print_row(
            "selected_tickers",
            ticker,
            reports_by_ticker.get(ticker, {}).get("action"),
            enrichment_by_ticker.get(ticker, {}).get("action"),
            reports_by_ticker.get(ticker, {}).get("primary_reason"),
            enrichment_by_ticker.get(ticker, {}).get("primary_reason"),
        )

    _print_section("reports_trace_matches")
    _print_row(
        "reports_trace_matches",
        "ticker",
        "matched_rule",
        "matched_token",
        "matched_value",
        "matched_field",
        "matched_horizon",
    )
    for trace in reports_trace_rows:
        _print_row(
            "reports_trace_matches",
            trace.get("ticker"),
            _trace_value(trace, "matched_rule", "rule_name"),
            _trace_value(trace, "matched_token"),
            _trace_value(trace, "matched_value", "input_value"),
            _trace_value(trace, "field", "field_name", "matched_field"),
            _trace_value(trace, "horizon", "rule_group", "matched_horizon"),
        )

    _print_section("source_field_presence")
    _print_row("source_field_presence", "ticker", "field_name", "source_value", "enrichment_value")
    for ticker in selected_tickers:
        source_row = source_by_ticker.get(ticker, {})
        enrichment_row = enrichment_analysis_by_ticker.get(ticker, {})
        for field_name in SOURCE_FIELDS:
            _print_row(
                "source_field_presence",
                ticker,
                field_name,
                source_row.get(field_name),
                enrichment_row.get(field_name),
            )

    _print_section("ma_break_candidate_sources")
    _print_row("ma_break_candidate_sources", "candidate_source", "exists", "non_empty_count", "details")
    analysis_ma_break_source_exists = 0
    direct_source_ma_break_non_empty = 0
    for table_name, field_name in CANDIDATE_SOURCES:
        columns = source_columns if table_name == "dc_ticker_swing_signal_daily" else enrichment_columns
        rows_by_ticker = source_by_ticker if table_name == "dc_ticker_swing_signal_daily" else enrichment_analysis_by_ticker
        exists = field_name in columns
        non_empty_count = sum(
            1
            for ticker in selected_tickers
            if _is_non_empty(rows_by_ticker.get(ticker, {}).get(field_name))
        )
        if non_empty_count > 0:
            analysis_ma_break_source_exists = 1
        if table_name == "dc_ticker_swing_signal_daily" and field_name == "ma_break_status":
            direct_source_ma_break_non_empty = non_empty_count
        _print_row(
            "ma_break_candidate_sources",
            f"{table_name}.{field_name}",
            1 if exists else 0,
            non_empty_count,
            f"selected_tickers={len(selected_tickers)}",
        )

    reports_sell_uses_ma_break = reports_trace_ma_break_matches > 0
    reports_sell_uses_hard_sell = reports_trace_hard_sell_matches > 0
    analysis_has_ma_break_source = analysis_ma_break_source_exists == 1
    needs_new_ma_break_enrichment = (
        (reports_sell_uses_ma_break or reports_sell_uses_hard_sell)
        and direct_source_ma_break_non_empty == 0
    )

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "REPORTS_SELL_USES_MA_BREAK",
        "LIKELY" if reports_sell_uses_ma_break else "UNLIKELY",
        f"reports_trace_ma_break_matches={reports_trace_ma_break_matches}",
    )
    _print_row(
        "hypothesis_summary",
        "REPORTS_SELL_USES_HARD_SELL_TOKEN",
        "LIKELY" if reports_sell_uses_hard_sell else "UNLIKELY",
        f"reports_trace_hard_sell_matches={reports_trace_hard_sell_matches}",
    )
    _print_row(
        "hypothesis_summary",
        "ANALYSIS_HAS_MA_BREAK_SOURCE",
        "LIKELY" if analysis_has_ma_break_source else "UNLIKELY",
        f"analysis_ma_break_source_exists={analysis_ma_break_source_exists}",
    )
    _print_row(
        "hypothesis_summary",
        "NEEDS_NEW_MA_BREAK_ENRICHMENT",
        "LIKELY" if needs_new_ma_break_enrichment else "UNLIKELY",
        f"reports_trace_ma_break_matches={reports_trace_ma_break_matches},reports_trace_hard_sell_matches={reports_trace_hard_sell_matches},direct_source_ma_break_non_empty={direct_source_ma_break_non_empty}",
    )

    _print_section("summary")
    _print_row("SUMMARY datacenter_dashboard_ma_break_source_audit.status=OK")
    _print_row(f"SUMMARY datacenter_dashboard_ma_break_source_audit.report_date={args.report_date}")
    _print_row(f"SUMMARY datacenter_dashboard_ma_break_source_audit.selected_tickers={len(selected_tickers)}")
    _print_row(f"SUMMARY datacenter_dashboard_ma_break_source_audit.reports_trace_ma_break_matches={reports_trace_ma_break_matches}")
    _print_row(f"SUMMARY datacenter_dashboard_ma_break_source_audit.reports_trace_hard_sell_matches={reports_trace_hard_sell_matches}")
    _print_row(f"SUMMARY datacenter_dashboard_ma_break_source_audit.analysis_ma_break_source_exists={analysis_ma_break_source_exists}")
    _print_row(f"SUMMARY datacenter_dashboard_ma_break_source_audit.needs_new_ma_break_enrichment={1 if needs_new_ma_break_enrichment else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
