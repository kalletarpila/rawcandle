#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_ticker_persistence import (
    DEFAULT_SIGNAL_VERSION,
    cleanup_non_trading_ticker_swing_rows,
    format_ticker_cleanup_summary_lines,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Identify and optionally delete old non-trading-date ticker swing snapshot rows."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--price-db", type=Path, required=True, help="Path to OHLCV SQLite database")
    parser.add_argument("--taxonomy-csv", type=Path, required=True, help="Path to datacenter taxonomy CSV")
    parser.add_argument("--start-date", type=str, required=True, help="Range start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="Range end date (YYYY-MM-DD)")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to clean")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to clean")
    parser.add_argument("--market", type=str, required=True, help="Market filter to use when deriving valid price dates")
    parser.add_argument("--apply", action="store_true", help="Actually delete candidate rows")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = cleanup_non_trading_ticker_swing_rows(
            analysis_db_path=args.analysis_db,
            price_db_path=args.price_db,
            taxonomy_csv_path=args.taxonomy_csv,
            start_date=args.start_date,
            end_date=args.end_date,
            taxonomy_version=args.taxonomy_version,
            signal_version=args.signal_version,
            market=args.market,
            apply=args.apply,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in format_ticker_cleanup_summary_lines(summary):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
