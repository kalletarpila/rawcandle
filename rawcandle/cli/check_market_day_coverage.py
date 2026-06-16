from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

CLASSIFICATION_NO_REFERENCE_DATES = "NO_REFERENCE_DATES"
CLASSIFICATION_MARKET_CLOSED_OR_NO_NORMAL_COVERAGE = (
    "MARKET_CLOSED_OR_NO_NORMAL_COVERAGE"
)
CLASSIFICATION_NORMAL_COVERAGE = "NORMAL_COVERAGE"
CLASSIFICATION_PARTIAL_SMALL_GAP = "PARTIAL_SMALL_GAP"
CLASSIFICATION_DAY_LEVEL_GAP = "DAY_LEVEL_GAP"

GAP_POSITION_INTERIOR = "INTERIOR_GAP"
GAP_POSITION_LATEST_OR_RIGHT_EDGE = "LATEST_OR_RIGHT_EDGE_GAP"
GAP_POSITION_LEFT_EDGE_OR_OLD_START = "LEFT_EDGE_OR_OLD_START_GAP"
GAP_POSITION_NO_REFERENCE = "NO_REFERENCE"

DOWNSREAM_RECOMPUTE_MODE_LATEST = "LATEST_DAY_RECOMPUTE_OK"
DOWNSREAM_RECOMPUTE_MODE_FORWARD = "FROM_RECOVERED_DATE_FORWARD_REQUIRED"
DOWNSREAM_RECOMPUTE_MODE_REPORT_ONLY = "REPORT_ONLY_NO_SAFE_RECOMPUTE_MODE"

NORMAL_COVERAGE_THRESHOLD = 0.98
DAY_LEVEL_GAP_THRESHOLD = 0.90
SMALL_GAP_MAX_MISSING = 25
REQUIRED_COLUMNS = {
    "osake",
    "pvm",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "market",
}


@dataclass(frozen=True)
class CoverageReport:
    db_path: str
    market: str
    target_date: str
    previous_reference_date: Optional[str]
    previous_reference_tickers_count: int
    next_reference_date: Optional[str]
    next_reference_tickers_count: int
    expected_tickers_count: int
    present_tickers_count: int
    missing_tickers_count: int
    coverage_ratio: float
    classification: str
    gap_position: str
    downstream_recompute_mode: str
    missing_tickers: list[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only market day coverage checker for osakedata."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--missing-limit", type=int, default=100)
    parser.add_argument("--reference-window-days", type=int, default=10)
    parser.add_argument("--min-reference-count", type=int, default=1000)
    return parser


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)


def _validate_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"Missing db: {db_path}")
    if not path.is_file():
        raise ValueError(f"db is not a file: {db_path}")
    return path


def _load_reference_date(
    conn: sqlite3.Connection,
    *,
    market: str,
    target_date: str,
    reference_window_days: int,
    min_reference_count: int,
    direction: str,
) -> Optional[str]:
    if direction == "previous":
        date_predicate = "pvm < ? AND pvm >= date(?, ?)"
        order_clause = "ORDER BY pvm DESC"
        date_modifier = f"-{reference_window_days} days"
    else:
        date_predicate = "pvm > ? AND pvm <= date(?, ?)"
        order_clause = "ORDER BY pvm ASC"
        date_modifier = f"+{reference_window_days} days"

    row = conn.execute(
        f"""
        WITH daily AS (
            SELECT pvm, COUNT(DISTINCT osake) AS ticker_count
            FROM osakedata
            WHERE lower(market) = lower(?)
            GROUP BY pvm
        )
        SELECT pvm
        FROM daily
        WHERE {date_predicate}
          AND ticker_count >= ?
        {order_clause}
        LIMIT 1
        """,
        (market, target_date, target_date, date_modifier, min_reference_count),
    ).fetchone()
    return None if row is None else str(row[0])


def _validate_schema(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(osakedata)").fetchall()
    if not rows:
        raise ValueError("Missing table: osakedata")
    columns = {str(row[1]) for row in rows}
    missing_columns = sorted(REQUIRED_COLUMNS - columns)
    if missing_columns:
        raise ValueError(
            "osakedata is missing required columns: "
            + ", ".join(missing_columns)
        )


def _load_tickers_for_date(
    conn: sqlite3.Connection,
    *,
    market: str,
    target_date: str,
) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT osake
        FROM osakedata
        WHERE lower(market) = lower(?)
          AND pvm = ?
        ORDER BY osake
        """,
        (market, target_date),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _classify_coverage(
    *,
    previous_reference_date: Optional[str],
    next_reference_date: Optional[str],
    present_tickers_count: int,
    expected_tickers_count: int,
    missing_tickers_count: int,
    coverage_ratio: float,
    min_reference_count: int,
) -> str:
    if previous_reference_date is None and next_reference_date is None:
        if present_tickers_count <= 0:
            return CLASSIFICATION_MARKET_CLOSED_OR_NO_NORMAL_COVERAGE
        return CLASSIFICATION_NO_REFERENCE_DATES
    if expected_tickers_count <= 0:
        return CLASSIFICATION_NO_REFERENCE_DATES
    if coverage_ratio >= NORMAL_COVERAGE_THRESHOLD:
        return CLASSIFICATION_NORMAL_COVERAGE
    if coverage_ratio < DAY_LEVEL_GAP_THRESHOLD and missing_tickers_count > 0:
        return CLASSIFICATION_DAY_LEVEL_GAP
    if missing_tickers_count <= SMALL_GAP_MAX_MISSING:
        return CLASSIFICATION_PARTIAL_SMALL_GAP
    return CLASSIFICATION_DAY_LEVEL_GAP


def _determine_gap_position(
    *,
    previous_reference_date: Optional[str],
    next_reference_date: Optional[str],
) -> str:
    if previous_reference_date is not None and next_reference_date is not None:
        return GAP_POSITION_INTERIOR
    if previous_reference_date is not None:
        return GAP_POSITION_LATEST_OR_RIGHT_EDGE
    if next_reference_date is not None:
        return GAP_POSITION_LEFT_EDGE_OR_OLD_START
    return GAP_POSITION_NO_REFERENCE


def _determine_downstream_recompute_mode(gap_position: str) -> str:
    if gap_position == GAP_POSITION_LATEST_OR_RIGHT_EDGE:
        return DOWNSREAM_RECOMPUTE_MODE_LATEST
    if gap_position in (GAP_POSITION_INTERIOR, GAP_POSITION_LEFT_EDGE_OR_OLD_START):
        return DOWNSREAM_RECOMPUTE_MODE_FORWARD
    return DOWNSREAM_RECOMPUTE_MODE_REPORT_ONLY


def build_coverage_report(
    *,
    db_path: str,
    market: str,
    target_date: str,
    reference_window_days: int,
    min_reference_count: int,
) -> CoverageReport:
    _validate_db_path(db_path)
    with _connect_read_only(db_path) as conn:
        _validate_schema(conn)
        previous_reference_date = _load_reference_date(
            conn,
            market=market,
            target_date=target_date,
            reference_window_days=reference_window_days,
            min_reference_count=min_reference_count,
            direction="previous",
        )
        next_reference_date = _load_reference_date(
            conn,
            market=market,
            target_date=target_date,
            reference_window_days=reference_window_days,
            min_reference_count=min_reference_count,
            direction="next",
        )

        previous_reference_tickers = (
            _load_tickers_for_date(
                conn,
                market=market,
                target_date=previous_reference_date,
            )
            if previous_reference_date is not None
            else set()
        )
        next_reference_tickers = (
            _load_tickers_for_date(
                conn,
                market=market,
                target_date=next_reference_date,
            )
            if next_reference_date is not None
            else set()
        )
        present_tickers = _load_tickers_for_date(
            conn,
            market=market,
            target_date=target_date,
        )

    if previous_reference_tickers and next_reference_tickers:
        expected_tickers = previous_reference_tickers | next_reference_tickers
    elif previous_reference_tickers:
        expected_tickers = previous_reference_tickers
    else:
        expected_tickers = next_reference_tickers
    missing_tickers = sorted(expected_tickers - present_tickers)
    expected_tickers_count = len(expected_tickers)
    present_tickers_count = len(present_tickers)
    missing_tickers_count = len(missing_tickers)
    coverage_ratio = (
        present_tickers_count / expected_tickers_count
        if expected_tickers_count > 0
        else 0.0
    )
    classification = _classify_coverage(
        previous_reference_date=previous_reference_date,
        next_reference_date=next_reference_date,
        present_tickers_count=present_tickers_count,
        expected_tickers_count=expected_tickers_count,
        missing_tickers_count=missing_tickers_count,
        coverage_ratio=coverage_ratio,
        min_reference_count=min_reference_count,
    )
    gap_position = _determine_gap_position(
        previous_reference_date=previous_reference_date,
        next_reference_date=next_reference_date,
    )
    downstream_recompute_mode = _determine_downstream_recompute_mode(gap_position)

    return CoverageReport(
        db_path=str(Path(db_path).resolve()),
        market=market,
        target_date=target_date,
        previous_reference_date=previous_reference_date,
        previous_reference_tickers_count=len(previous_reference_tickers),
        next_reference_date=next_reference_date,
        next_reference_tickers_count=len(next_reference_tickers),
        expected_tickers_count=expected_tickers_count,
        present_tickers_count=present_tickers_count,
        missing_tickers_count=missing_tickers_count,
        coverage_ratio=coverage_ratio,
        classification=classification,
        gap_position=gap_position,
        downstream_recompute_mode=downstream_recompute_mode,
        missing_tickers=missing_tickers,
    )


def _print_text_report(report: CoverageReport, missing_limit: int) -> None:
    print("MARKET_DAY_COVERAGE")
    print(f"db: {report.db_path}")
    print(f"market: {report.market}")
    print(f"target_date: {report.target_date}")
    print()
    print(f"previous_reference_date: {report.previous_reference_date or 'NONE'}")
    print(
        f"previous_reference_tickers: {report.previous_reference_tickers_count}"
    )
    print(f"next_reference_date: {report.next_reference_date or 'NONE'}")
    print(f"next_reference_tickers: {report.next_reference_tickers_count}")
    print()
    print(f"expected_tickers: {report.expected_tickers_count}")
    print(f"present_tickers: {report.present_tickers_count}")
    print(f"missing_tickers: {report.missing_tickers_count}")
    print(f"coverage_ratio: {report.coverage_ratio:.4f}")
    print(f"classification: {report.classification}")
    print(f"gap_position: {report.gap_position}")
    print(
        f"downstream_recompute_mode: {report.downstream_recompute_mode}"
    )
    print()
    print("missing_examples:")
    for ticker in report.missing_tickers[: max(0, missing_limit)]:
        print(ticker)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_coverage_report(
            db_path=args.db,
            market=args.market,
            target_date=args.date,
            reference_window_days=args.reference_window_days,
            min_reference_count=args.min_reference_count,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.format == "json":
        print(json.dumps(asdict(report), ensure_ascii=True, sort_keys=True))
    else:
        _print_text_report(report, args.missing_limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
