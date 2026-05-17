#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    DEFAULT_CALC_VERSION,
    DEFAULT_RELATIVE_BASE_WINDOW,
    format_group_relative_ohlc_summary_lines,
    format_group_synthetic_ohlc_summary_lines,
    persist_datacenter_group_relative_ohlc,
    persist_datacenter_group_synthetic_ohlc,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist deterministic datacenter group synthetic OHLC rows into dc_group_synthetic_ohlc_daily."
    )
    parser.add_argument("--price-db", type=Path, required=True, help="Path to OHLCV SQLite database")
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-csv", type=Path, required=True, help="Path to datacenter taxonomy CSV")
    parser.add_argument("--start-date", type=str, required=True, help="Range start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="Range end date (YYYY-MM-DD)")
    parser.add_argument("--market", type=str, default=None, help="Optional market value to filter from osakedata")
    parser.add_argument("--calc-version", type=str, default=DEFAULT_CALC_VERSION, help="Synthetic OHLC calc version")
    parser.add_argument("--run-id", type=str, default=None, help="Optional explicit run identifier")
    parser.add_argument("--created-at-utc", type=str, default=None, help="Optional explicit created_at_utc timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    parser.add_argument("--write-mode", type=str, required=True, help="Write mode: insert-missing, upsert, replace-range, update-existing, replace-relative-range")
    parser.add_argument("--relative-only", action="store_true", help="Update only rolling relative OHLC fields on existing synthetic OHLC rows")
    parser.add_argument("--relative-base-window", type=int, default=DEFAULT_RELATIVE_BASE_WINDOW, help="Rolling base SMA window for relative OHLC updates")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.relative_only:
            summary = persist_datacenter_group_relative_ohlc(
                analysis_db_path=args.analysis_db,
                price_db_path=args.price_db,
                taxonomy_csv_path=args.taxonomy_csv,
                start_date=args.start_date,
                end_date=args.end_date,
                market=args.market,
                calc_version=args.calc_version,
                run_id=args.run_id,
                created_at_utc=args.created_at_utc,
                relative_base_window=args.relative_base_window,
                write_mode=args.write_mode,
            )
            lines = format_group_relative_ohlc_summary_lines(summary)
        else:
            summary = persist_datacenter_group_synthetic_ohlc(
                analysis_db_path=args.analysis_db,
                price_db_path=args.price_db,
                taxonomy_csv_path=args.taxonomy_csv,
                start_date=args.start_date,
                end_date=args.end_date,
                market=args.market,
                calc_version=args.calc_version,
                run_id=args.run_id,
                created_at_utc=args.created_at_utc,
                write_mode=args.write_mode,
            )
            lines = format_group_synthetic_ohlc_summary_lines(summary)
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
