#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.persistence import (
    format_datacenter_summary_lines,
    run_datacenter_indices,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate and persist datacenter ecosystem group indices into analysis.db."
    )
    parser.add_argument("--ohlcv-db", type=Path, required=True, help="Path to OHLCV SQLite database")
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-csv", type=Path, required=True, help="Path to datacenter taxonomy CSV")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to calculate")
    parser.add_argument("--market", type=str, default=None, help="Optional market value to filter from osakedata")
    parser.add_argument("--index-base-date", type=str, default="2020-01-01", help="Index base date for anchoring index_level_equal (YYYY-MM-DD)")
    parser.add_argument("--start-date", type=str, required=True, help="Write range start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="Write range end date (YYYY-MM-DD)")
    parser.add_argument("--write-mode", type=str, required=True, help="Write mode (only replace-range is supported)")
    parser.add_argument("--spy-ticker", type=str, default="SPY", help="Benchmark ticker for SPY relative strength")
    parser.add_argument("--qqq-ticker", type=str, default="QQQ", help="Benchmark ticker for QQQ relative strength")
    parser.add_argument("--run-id", type=str, default=None, help="Optional explicit run identifier")
    parser.add_argument("--created-at-utc", type=str, default=None, help="Optional explicit created_at_utc timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_datacenter_indices(
            ohlcv_db_path=args.ohlcv_db,
            analysis_db_path=args.analysis_db,
            taxonomy_csv=args.taxonomy_csv,
            taxonomy_version=args.taxonomy_version,
            market=args.market,
            index_base_date=args.index_base_date,
            start_date=args.start_date,
            end_date=args.end_date,
            write_mode=args.write_mode,
            spy_ticker=args.spy_ticker,
            qqq_ticker=args.qqq_ticker,
            run_id=args.run_id,
            created_at_utc=args.created_at_utc,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in format_datacenter_summary_lines(summary):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
