from __future__ import annotations

import argparse
import sqlite3
from datetime import date

from rawcandle.technical_signal_relevance_persistence import query_relevance_records


VALID_RELEVANCE_CLASSES = {"RELEVANT", "WEAK_CONTEXT", "NOISE"}
SECTION_NAME = "technical_signal_relevance_export"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export persisted technical signal relevance rows."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--ticker", nargs="+")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--relevance-class")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--include-rule-trace", action="store_true")
    return parser


def _parse_tickers(raw_ticker_values: list[str] | None) -> list[str] | None:
    if raw_ticker_values is None:
        return None
    joined_value = " ".join(str(value) for value in raw_ticker_values)
    return [segment.strip() for segment in joined_value.split(",") if segment.strip()]


def _validate_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _validate_args(args: argparse.Namespace, tickers: list[str] | None) -> tuple[str | None, str | None]:
    normalized_start_date = None
    normalized_end_date = None
    if args.start_date is not None:
        normalized_start_date = _validate_iso_date(args.start_date, "start_date")
    if args.end_date is not None:
        normalized_end_date = _validate_iso_date(args.end_date, "end_date")
    if normalized_start_date is not None and normalized_end_date is not None:
        if normalized_start_date > normalized_end_date:
            raise ValueError("start_date must be less than or equal to end_date")
    if args.relevance_class is not None and args.relevance_class not in VALID_RELEVANCE_CLASSES:
        raise ValueError("relevance_class must be one of RELEVANT, WEAK_CONTEXT, NOISE")
    if args.limit <= 0:
        raise ValueError("limit must be positive")
    if tickers is not None and not tickers:
        raise ValueError("ticker list must be non-empty")
    return normalized_start_date, normalized_end_date


def _format_cell(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def _print_rows(rows: list[dict[str, object]], include_rule_trace: bool) -> None:
    print(f"section;{SECTION_NAME}")
    header = [
        "section",
        "run_id",
        "ticker",
        "timeframe",
        "signal_date",
        "signal_confirmed_as_of_date",
        "signal_name",
        "signal_source_id",
        "relevance_class",
        "relevance_reason",
        "dow_trend_state",
        "dow_context_state",
        "latest_bos_direction",
        "bars_since_latest_bos",
        "bars_since_latest_reset",
        "near_latest_pivot",
        "near_active_bos_level",
        "is_trend_aligned",
        "is_counter_trend",
    ]
    if include_rule_trace:
        header.append("rule_trace")
    print(";".join(header))

    for row in rows:
        output = [
            SECTION_NAME,
            _format_cell(row.get("run_id")),
            _format_cell(row.get("ticker")),
            _format_cell(row.get("timeframe")),
            _format_cell(row.get("signal_date")),
            _format_cell(row.get("signal_confirmed_as_of_date")),
            _format_cell(row.get("signal_name")),
            _format_cell(row.get("signal_source_id")),
            _format_cell(row.get("relevance_class")),
            _format_cell(row.get("relevance_reason")),
            _format_cell(row.get("dow_trend_state")),
            _format_cell(row.get("dow_context_state")),
            _format_cell(row.get("latest_bos_direction")),
            _format_cell(row.get("bars_since_latest_bos")),
            _format_cell(row.get("bars_since_latest_reset")),
            _format_cell(row.get("near_latest_pivot")),
            _format_cell(row.get("near_active_bos_level")),
            _format_cell(row.get("is_trend_aligned")),
            _format_cell(row.get("is_counter_trend")),
        ]
        if include_rule_trace:
            output.append(_format_cell(row.get("rule_trace")))
        print(";".join(output))


def _print_summary(
    *,
    rows_returned: int,
    run_id_filter: str | None,
    ticker_count_filter: int | None,
    timeframe_filter: str,
    start_date_filter: str | None,
    end_date_filter: str | None,
    relevance_class_filter: str | None,
    limit: int,
    status: str,
) -> None:
    print(f"SUMMARY technical_signal_relevance_export.rows_returned={rows_returned}")
    print(
        "SUMMARY technical_signal_relevance_export.run_id_filter="
        f"{run_id_filter if run_id_filter is not None else 'ALL'}"
    )
    print(
        "SUMMARY technical_signal_relevance_export.ticker_count_filter="
        f"{ticker_count_filter if ticker_count_filter is not None else 'ALL'}"
    )
    print(f"SUMMARY technical_signal_relevance_export.timeframe_filter={timeframe_filter}")
    print(
        "SUMMARY technical_signal_relevance_export.start_date_filter="
        f"{start_date_filter if start_date_filter is not None else 'NONE'}"
    )
    print(
        "SUMMARY technical_signal_relevance_export.end_date_filter="
        f"{end_date_filter if end_date_filter is not None else 'NONE'}"
    )
    print(
        "SUMMARY technical_signal_relevance_export.relevance_class_filter="
        f"{relevance_class_filter if relevance_class_filter is not None else 'ALL'}"
    )
    print(f"SUMMARY technical_signal_relevance_export.limit={limit}")
    print(f"SUMMARY technical_signal_relevance_export.status={status}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tickers = _parse_tickers(args.ticker)
    conn: sqlite3.Connection | None = None

    try:
        normalized_start_date, normalized_end_date = _validate_args(args, tickers)
        conn = sqlite3.connect(args.analysis_db)
        conn.row_factory = sqlite3.Row
        rows = query_relevance_records(
            conn,
            run_id=args.run_id,
            tickers=tickers,
            timeframe=args.timeframe,
            start_date=normalized_start_date,
            end_date=normalized_end_date,
            relevance_class=args.relevance_class,
            limit=args.limit,
        )
        _print_rows(rows, args.include_rule_trace)
        _print_summary(
            rows_returned=len(rows),
            run_id_filter=args.run_id,
            ticker_count_filter=None if tickers is None else len(set(tickers)),
            timeframe_filter=args.timeframe,
            start_date_filter=normalized_start_date,
            end_date_filter=normalized_end_date,
            relevance_class_filter=args.relevance_class,
            limit=args.limit,
            status="OK",
        )
        conn.close()
        return 0
    except (ValueError, sqlite3.Error):
        _print_summary(
            rows_returned=0,
            run_id_filter=args.run_id,
            ticker_count_filter=None if tickers is None else len(set(tickers)),
            timeframe_filter=args.timeframe,
            start_date_filter=args.start_date,
            end_date_filter=args.end_date,
            relevance_class_filter=args.relevance_class,
            limit=args.limit,
            status="FAILED",
        )
        if conn is not None:
            conn.close()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
