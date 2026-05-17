#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_ticker_persistence import (
    DEFAULT_MAX_VALID_PRICE_ROWS,
    DEFAULT_SIGNAL_VERSION,
    format_ticker_swing_summary_lines,
    persist_datacenter_ticker_swing_snapshots,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist deterministic datacenter ticker swing base snapshots into dc_ticker_swing_signal_daily."
    )
    parser.add_argument("--price-db", type=Path, required=True, help="Path to OHLCV SQLite database")
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-csv", type=Path, required=True, help="Path to datacenter taxonomy CSV")
    parser.add_argument("--as-of-date", type=str, required=True, help="Exact signal date (YYYY-MM-DD)")
    parser.add_argument("--market", type=str, default=None, help="Optional market value to filter from osakedata")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to persist")
    parser.add_argument("--run-id", type=str, default=None, help="Optional explicit run identifier")
    parser.add_argument("--created-at-utc", type=str, default=None, help="Optional explicit created_at_utc timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    parser.add_argument("--write-mode", type=str, required=True, help="Write mode: insert-missing, upsert, replace-date")
    parser.add_argument("--max-valid-price-rows", type=int, default=DEFAULT_MAX_VALID_PRICE_ROWS, help="Maximum valid OHLCV rows to load per ticker")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = persist_datacenter_ticker_swing_snapshots(
            analysis_db_path=args.analysis_db,
            price_db_path=args.price_db,
            taxonomy_csv_path=args.taxonomy_csv,
            as_of_date=args.as_of_date,
            market=args.market,
            signal_version=args.signal_version,
            run_id=args.run_id,
            created_at_utc=args.created_at_utc,
            write_mode=args.write_mode,
            max_valid_price_rows=args.max_valid_price_rows,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in format_ticker_swing_summary_lines(summary):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
