#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.stock_dow_structure import (
    DEFAULT_ANALYSIS_DB_PATH,
    DEFAULT_OSAKEDATA_DB_PATH,
    DEFAULT_PIVOT_RADIUS,
    DEFAULT_RECALC_TAIL_TRADING_DAYS,
    format_summary_lines,
    run_stock_dow_structure,
)


def parse_recalc_from_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid --recalc-from-date: {value}"
        ) from exc
    return parsed.date().isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate stock-level Dow structure events into analysis.db."
    )
    parser.add_argument(
        "--analysis-db",
        type=Path,
        default=DEFAULT_ANALYSIS_DB_PATH,
        help="Path to analysis.db (default: data/analysis.db)",
    )
    parser.add_argument(
        "--osakedata-db",
        type=Path,
        default=DEFAULT_OSAKEDATA_DB_PATH,
        help="Path to osakedata.db (default: data/osakedata.db)",
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Single ticker to calculate",
    )
    parser.add_argument(
        "--market",
        type=str,
        default=None,
        help="Calculate all tickers for this market when --ticker is not provided",
    )
    parser.add_argument(
        "--pivot-radius",
        type=int,
        default=DEFAULT_PIVOT_RADIUS,
        help="Pivot radius for confirmation windows (default: 3)",
    )
    parser.add_argument(
        "--recalc-tail-trading-days",
        type=int,
        default=DEFAULT_RECALC_TAIL_TRADING_DAYS,
        help="Incremental recalculation tail in trading days (default: 30)",
    )
    parser.add_argument(
        "--recalc-from-date",
        type=parse_recalc_from_date,
        default=None,
        help="Force recalculation from this confirmed_as_of_date boundary (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="upsert",
        help="Write mode (only 'upsert' is supported in V1)",
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Force full recalculation for each processed ticker",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write event rows, print SUMMARY only",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    summary = run_stock_dow_structure(
        analysis_db_path=args.analysis_db,
        osakedata_db_path=args.osakedata_db,
        ticker=args.ticker,
        market=args.market,
        pivot_radius=args.pivot_radius,
        recalc_tail_trading_days=args.recalc_tail_trading_days,
        recalc_from_date=args.recalc_from_date,
        mode=args.mode,
        force_full=args.force_full,
        dry_run=args.dry_run,
    )
    for line in format_summary_lines(summary):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
