from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

SELL_TO_REDUCE = "SELL_TO_REDUCE"
REDUCE_TO_TIGHTEN_STOP = "REDUCE_TO_TIGHTEN_STOP"
WINDOW_ROWS = 30
TRACE_SUMMARY_LIMIT = 3


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
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
    selected: list[str] = []
    seen: set[str] = set()
    for token in raw.replace(",", " ").split():
        ticker = token.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            selected.append(ticker)
    return selected


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


def _gap_group(reports_action: object, enrichment_action: object) -> str | None:
    reports = _normalized_action(reports_action)
    enrichment = _normalized_action(enrichment_action)
    if reports == "SELL" and enrichment == "REDUCE":
        return SELL_TO_REDUCE
    if reports == "REDUCE" and enrichment == "TIGHTEN_STOP":
        return REDUCE_TO_TIGHTEN_STOP
    return None


def _load_enrichment_rows(
    analysis_db: str,
    report_date: str,
) -> dict[str, dict[str, object]]:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, "dc_dashboard_ticker_enrichment_daily")
        rows = conn.execute(
            """
            SELECT *
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = ?
            ORDER BY ticker ASC, taxonomy_version ASC
            """,
            (report_date,),
        ).fetchall()
        by_ticker: dict[str, dict[str, object]] = {}
        for row in rows:
            ticker = _cell(row["ticker"]).upper()
            if ticker and ticker not in by_ticker:
                by_ticker[ticker] = {key: row[key] for key in row.keys()}
        return by_ticker


def _load_source_history(
    analysis_db: str,
    report_date: str,
    tickers: list[str],
    enrichment_rows: dict[str, dict[str, object]],
    window_rows: int,
) -> dict[str, list[dict[str, object]]]:
    if not tickers:
        return {}
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, "dc_ticker_swing_signal_daily")
        source_columns = _table_columns(conn, "dc_ticker_swing_signal_daily")
        has_taxonomy = "taxonomy_version" in source_columns
        placeholders = ", ".join("?" for _ in tickers)
        rows = conn.execute(
            f"""
            SELECT *
            FROM dc_ticker_swing_signal_daily
            WHERE ticker IN ({placeholders})
              AND signal_date <= ?
            ORDER BY ticker ASC, signal_date DESC
            """,
            (*tickers, report_date),
        ).fetchall()
        grouped_desc: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            ticker = _cell(row["ticker"]).upper()
            if not ticker:
                continue
            if has_taxonomy:
                expected_taxonomy = _cell(enrichment_rows.get(ticker, {}).get("taxonomy_version"))
                row_taxonomy = _cell(row["taxonomy_version"])
                if expected_taxonomy and row_taxonomy and row_taxonomy != expected_taxonomy:
                    continue
            if len(grouped_desc[ticker]) >= window_rows:
                continue
            grouped_desc[ticker].append({key: row[key] for key in row.keys()})
        return {
            ticker: list(reversed(ticker_rows))
            for ticker, ticker_rows in grouped_desc.items()
        }


def _safe_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None


def _trace_value(trace: dict[str, object], *fields: str) -> str:
    for field in fields:
        text = _cell(trace.get(field))
        if text:
            return text
    return ""


def _summarize_trace(trace_rows: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for trace in trace_rows[:TRACE_SUMMARY_LIMIT]:
        rule = _trace_value(trace, "matched_rule", "rule_name")
        token = _trace_value(trace, "matched_token", "matched_value", "input_value")
        field_name = _trace_value(trace, "matched_field", "field_name", "field")
        horizon = _trace_value(trace, "horizon", "rule_group")
        parts.append("|".join([rule or "-", token or "-", field_name or "-", horizon or "-"]))
    return " || ".join(parts)


def _ticker_traces(snapshot, ticker: str) -> list[dict[str, object]]:
    return [
        trace
        for trace in snapshot.decision_trace
        if _cell(trace.get("ticker")).upper() == ticker
    ]


def _trace_contains_any(trace_rows: list[dict[str, object]], keywords: tuple[str, ...]) -> bool:
    for trace in trace_rows:
        haystack = " ".join(
            [
                _trace_value(trace, "matched_rule", "rule_name"),
                _trace_value(trace, "matched_token", "matched_value", "input_value"),
                _trace_value(trace, "matched_field", "field_name", "field"),
            ]
        ).lower()
        if any(keyword in haystack for keyword in keywords):
            return True
    return False


def _first_trace_match(trace_rows: list[dict[str, object]], keywords: tuple[str, ...]) -> str:
    for trace in trace_rows:
        values = [
            _trace_value(trace, "matched_rule", "rule_name"),
            _trace_value(trace, "matched_token", "matched_value", "input_value"),
            _trace_value(trace, "matched_field", "field_name", "field"),
        ]
        haystack = " ".join(values).lower()
        if any(keyword in haystack for keyword in keywords):
            return next((value for value in values if value), "")
    return ""


def _derive_counts(source_rows: list[dict[str, object]]) -> dict[str, int]:
    return {
        "high_only": sum(
            1 for row in source_rows if _cell(row.get("exit_risk_severity")).upper() == "HIGH"
        ),
        "medium_or_high": sum(
            1
            for row in source_rows
            if _cell(row.get("exit_risk_severity")).upper() in {"HIGH", "MEDIUM"}
        ),
        "exit_signal": sum(
            1 for row in source_rows if _safe_int(row.get("exit_risk_signal")) == 1
        ),
    }


def _selected_gap_tickers(
    common_tickers: list[str],
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[tuple[str, str]]:
    if explicit_tickers:
        selected = []
        for ticker in explicit_tickers:
            if ticker not in common_tickers or ticker == "CRGY":
                continue
            gap_group = _gap_group(
                reports_by_ticker[ticker].get("action"),
                enrichment_by_ticker[ticker].get("action"),
            )
            if gap_group:
                selected.append((ticker, gap_group))
        return selected
    selected: list[tuple[str, str]] = []
    for gap_group in (SELL_TO_REDUCE, REDUCE_TO_TIGHTEN_STOP):
        matches = [
            (
                ticker,
                gap_group,
            )
            for ticker in common_tickers
            if ticker != "CRGY"
            and _gap_group(
                reports_by_ticker[ticker].get("action"),
                enrichment_by_ticker[ticker].get("action"),
            )
            == gap_group
        ]
        selected.extend(matches[:max_examples])
    return selected[:max_examples]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose final residual action parity gaps between reports and enrichment."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=100)
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
        analysis_by_ticker = _load_enrichment_rows(args.analysis_db, args.report_date)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _ticker_map(reports_snapshot.tickers)
    enrichment_by_ticker = _ticker_map(enrichment_snapshot.tickers)
    common_tickers = sorted(set(reports_by_ticker) & set(enrichment_by_ticker) & set(analysis_by_ticker))
    explicit_tickers = _parse_tickers(args.tickers)
    selected = _selected_gap_tickers(
        common_tickers,
        reports_by_ticker,
        enrichment_by_ticker,
        explicit_tickers,
        args.max_examples,
    )
    selected_tickers = [ticker for ticker, _gap_group_name in selected]
    source_history_by_ticker = _load_source_history(
        args.analysis_db,
        args.report_date,
        selected_tickers + [
            ticker
            for ticker in common_tickers
            if _normalized_action(reports_by_ticker[ticker].get("action")) == "TIGHTEN_STOP"
        ],
        analysis_by_ticker,
        WINDOW_ROWS,
    )

    gap_counts = {
        SELL_TO_REDUCE: sum(
            1
            for ticker in common_tickers
            if _gap_group(
                reports_by_ticker[ticker].get("action"),
                enrichment_by_ticker[ticker].get("action"),
            )
            == SELL_TO_REDUCE
        ),
        REDUCE_TO_TIGHTEN_STOP: sum(
            1
            for ticker in common_tickers
            if _gap_group(
                reports_by_ticker[ticker].get("action"),
                enrichment_by_ticker[ticker].get("action"),
            )
            == REDUCE_TO_TIGHTEN_STOP
        ),
    }

    sell_to_reduce_ma_break_gap = 0
    reduce_to_tighten_medium_only = 0
    reduce_to_tighten_exit_signal_only = 0
    reduce_to_tighten_high_zero = 0
    reports_tighten_common = 0
    reports_tighten_high_only_positive = 0
    sell_ma_break_candidates = 0
    sell_hard_sell_tuning_candidates = 0

    _print_section("run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
    _print_row(
        "run_summary",
        "reports",
        args.reports_dashboard_db,
        args.reports_run_id,
        args.report_date,
        "dashboard_snapshot",
    )
    _print_row(
        "run_summary",
        "enrichment",
        args.enrichment_dashboard_db,
        args.enrichment_run_id,
        args.report_date,
        "dashboard_snapshot",
    )
    _print_row(
        "run_summary",
        "analysis",
        args.analysis_db,
        "",
        args.report_date,
        "analysis_enrichment_and_source",
    )

    _print_section("residual_gap_counts")
    _print_row("residual_gap_counts", "gap_group", "count")
    _print_row("residual_gap_counts", SELL_TO_REDUCE, gap_counts[SELL_TO_REDUCE])
    _print_row("residual_gap_counts", REDUCE_TO_TIGHTEN_STOP, gap_counts[REDUCE_TO_TIGHTEN_STOP])

    _print_section("residual_gap_examples")
    _print_row(
        "residual_gap_examples",
        "ticker",
        "gap_group",
        "reports_action",
        "enrichment_action",
        "reports_primary_reason",
        "enrichment_primary_reason",
        "reports_trace_summary",
        "enrichment_trace_summary",
    )
    for ticker, gap_group in selected:
        reports_row = reports_by_ticker[ticker]
        enrichment_row = enrichment_by_ticker[ticker]
        reports_trace = _ticker_traces(reports_snapshot, ticker)
        enrichment_trace = _ticker_traces(enrichment_snapshot, ticker)
        _print_row(
            "residual_gap_examples",
            ticker,
            gap_group,
            reports_row.get("action"),
            enrichment_row.get("action"),
            reports_row.get("primary_reason"),
            enrichment_row.get("primary_reason"),
            _summarize_trace(reports_trace),
            _summarize_trace(enrichment_trace),
        )

    _print_section("sell_reduce_diagnosis")
    _print_row(
        "sell_reduce_diagnosis",
        "ticker",
        "reports_sell_reason",
        "reports_ma_break_status",
        "enrichment_ma_break_status",
        "reports_hard_sell_token",
        "enrichment_hard_sell_token",
        "analysis_return_10d",
        "analysis_distance_to_ema20_pct",
        "analysis_window_status_2d",
    )
    for ticker, gap_group in selected:
        if gap_group != SELL_TO_REDUCE:
            continue
        reports_trace = _ticker_traces(reports_snapshot, ticker)
        analysis_row = analysis_by_ticker.get(ticker, {})
        reports_ma_break_status = _first_trace_match(
            reports_trace,
            ("sma50_confirmed_break", "ema20_confirmed_break", "sma50_warning", "ema20_warning"),
        )
        reports_hard_sell_token = _first_trace_match(
            reports_trace,
            ("return_10d_lt_minus_8pct", "close_below_ema20", "sell_hard_token"),
        )
        enrichment_hard_sell_token = _cell(analysis_row.get("window_status_2d"))
        enrichment_ma_break_status = _cell(analysis_row.get("ma_break_status"))
        if reports_ma_break_status and enrichment_ma_break_status not in {
            "SMA50_CONFIRMED_BREAK",
            "EMA20_CONFIRMED_BREAK",
        }:
            sell_to_reduce_ma_break_gap += 1
        if reports_hard_sell_token and not any(
            token in enrichment_hard_sell_token
            for token in ("return_10d_lt_minus_8pct", "close_below_ema20")
        ):
            sell_hard_sell_tuning_candidates += 1
        if reports_ma_break_status:
            sell_ma_break_candidates += 1
        _print_row(
            "sell_reduce_diagnosis",
            ticker,
            reports_by_ticker[ticker].get("primary_reason"),
            reports_ma_break_status,
            enrichment_ma_break_status,
            reports_hard_sell_token,
            enrichment_hard_sell_token,
            analysis_row.get("return_10d"),
            analysis_row.get("distance_to_ema20_pct"),
            analysis_row.get("window_status_2d"),
        )

    _print_section("reduce_tighten_diagnosis")
    _print_row(
        "reduce_tighten_diagnosis",
        "ticker",
        "reports_reduce_reason",
        "reports_high_exit_trace",
        "enrichment_high_exit_risk_days_count",
        "derived_high_only_count",
        "derived_medium_or_high_count",
        "derived_exit_signal_count",
        "latest_day_exit_risk_severity",
        "latest_day_exit_risk_signal",
    )
    for ticker in common_tickers:
        if _normalized_action(reports_by_ticker[ticker].get("action")) == "TIGHTEN_STOP":
            reports_tighten_common += 1
            if _derive_counts(source_history_by_ticker.get(ticker, [])).get("high_only", 0) > 0:
                reports_tighten_high_only_positive += 1
    for ticker, gap_group in selected:
        if gap_group != REDUCE_TO_TIGHTEN_STOP:
            continue
        reports_trace = _ticker_traces(reports_snapshot, ticker)
        high_exit_trace = _first_trace_match(reports_trace, ("high_exit_risk_days_count", "tighten_stop"))
        analysis_row = analysis_by_ticker.get(ticker, {})
        source_rows = source_history_by_ticker.get(ticker, [])
        derived = _derive_counts(source_rows)
        latest_day = source_rows[-1] if source_rows else {}
        if derived["medium_or_high"] > 0 and derived["high_only"] == 0:
            reduce_to_tighten_medium_only += 1
        if derived["exit_signal"] > 0 and derived["high_only"] == 0:
            reduce_to_tighten_exit_signal_only += 1
        if derived["high_only"] == 0:
            reduce_to_tighten_high_zero += 1
        _print_row(
            "reduce_tighten_diagnosis",
            ticker,
            reports_by_ticker[ticker].get("primary_reason"),
            high_exit_trace,
            analysis_row.get("high_exit_risk_days_count"),
            derived["high_only"],
            derived["medium_or_high"],
            derived["exit_signal"],
            latest_day.get("exit_risk_severity"),
            latest_day.get("exit_risk_signal"),
        )

    sell_to_reduce_requires_true_ma_break = (
        gap_counts[SELL_TO_REDUCE] > 0 and sell_to_reduce_ma_break_gap >= max(1, gap_counts[SELL_TO_REDUCE] // 2)
    )
    sell_to_reduce_requires_hard_sell_tuning = (
        gap_counts[SELL_TO_REDUCE] > 0
        and sell_hard_sell_tuning_candidates >= max(1, gap_counts[SELL_TO_REDUCE] // 2)
    )
    reduce_to_tighten_caused_by_medium_count = (
        gap_counts[REDUCE_TO_TIGHTEN_STOP] > 0
        and reduce_to_tighten_medium_only >= max(1, gap_counts[REDUCE_TO_TIGHTEN_STOP] // 2)
    )
    reduce_to_tighten_caused_by_exit_signal_count = (
        gap_counts[REDUCE_TO_TIGHTEN_STOP] > 0
        and reduce_to_tighten_exit_signal_only >= max(1, gap_counts[REDUCE_TO_TIGHTEN_STOP] // 2)
    )
    high_only_count_would_match_reports_better = (
        gap_counts[REDUCE_TO_TIGHTEN_STOP] > 0
        and reduce_to_tighten_high_zero >= max(1, gap_counts[REDUCE_TO_TIGHTEN_STOP] // 2)
        and reports_tighten_common > 0
        and reports_tighten_high_only_positive >= max(1, reports_tighten_common // 2)
    )

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "SELL_TO_REDUCE_REQUIRES_TRUE_MA_BREAK_SOURCE",
        "LIKELY" if sell_to_reduce_requires_true_ma_break else "UNLIKELY",
        f"sell_to_reduce={gap_counts[SELL_TO_REDUCE]},ma_break_gap={sell_to_reduce_ma_break_gap}",
    )
    _print_row(
        "hypothesis_summary",
        "SELL_TO_REDUCE_REQUIRES_HARD_SELL_TOKEN_TUNING",
        "LIKELY" if sell_to_reduce_requires_hard_sell_tuning else "UNLIKELY",
        f"sell_to_reduce={gap_counts[SELL_TO_REDUCE]},hard_sell_token_gap={sell_hard_sell_tuning_candidates}",
    )
    _print_row(
        "hypothesis_summary",
        "REDUCE_TO_TIGHTEN_CAUSED_BY_MEDIUM_COUNT",
        "LIKELY" if reduce_to_tighten_caused_by_medium_count else "UNLIKELY",
        f"reduce_to_tighten={gap_counts[REDUCE_TO_TIGHTEN_STOP]},medium_only={reduce_to_tighten_medium_only}",
    )
    _print_row(
        "hypothesis_summary",
        "REDUCE_TO_TIGHTEN_CAUSED_BY_EXIT_SIGNAL_COUNT",
        "LIKELY" if reduce_to_tighten_caused_by_exit_signal_count else "UNLIKELY",
        f"reduce_to_tighten={gap_counts[REDUCE_TO_TIGHTEN_STOP]},exit_signal_only={reduce_to_tighten_exit_signal_only}",
    )
    _print_row(
        "hypothesis_summary",
        "HIGH_ONLY_COUNT_WOULD_MATCH_REPORTS_BETTER",
        "LIKELY" if high_only_count_would_match_reports_better else "UNLIKELY",
        (
            f"reduce_to_tighten_high_zero={reduce_to_tighten_high_zero},"
            f"reports_tighten_high_only_positive={reports_tighten_high_only_positive},"
            f"reports_tighten_common={reports_tighten_common}"
        ),
    )

    _print_section("summary")
    _print_row(
        "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.status=OK",
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_final_action_residual_diagnosis.report_date={args.report_date}",
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_final_action_residual_diagnosis.sell_to_reduce={gap_counts[SELL_TO_REDUCE]}",
    )
    _print_row(
        "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.reduce_to_tighten_stop="
        f"{gap_counts[REDUCE_TO_TIGHTEN_STOP]}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.sell_to_reduce_ma_break_gap="
        f"{sell_to_reduce_ma_break_gap}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.reduce_to_tighten_medium_only="
        f"{reduce_to_tighten_medium_only}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_final_action_residual_diagnosis.reduce_to_tighten_exit_signal_only="
        f"{reduce_to_tighten_exit_signal_only}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
