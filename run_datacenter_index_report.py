#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.reporting import (
    format_report_summary_lines,
    write_datacenter_index_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export deterministic datacenter ecosystem index reports from dc_group_index_daily."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to report")
    parser.add_argument("--as-of-date", type=str, required=True, help="Exact report date (YYYY-MM-DD)")
    parser.add_argument("--output-md", type=Path, required=True, help="Output Markdown report path")
    parser.add_argument("--output-csv", type=Path, required=True, help="Output CSV report path")
    parser.add_argument("--top-n", type=int, default=10, help="Top/bottom section row count")
    parser.add_argument("--include-ticker-performance", action="store_true", help="Include ticker-level performance sections")
    parser.add_argument("--ohlcv-db", type=Path, default=None, help="Path to OHLCV SQLite database for optional ticker performance")
    parser.add_argument("--taxonomy-csv", type=Path, default=None, help="Path to taxonomy CSV for optional ticker performance")
    parser.add_argument("--market", type=str, default=None, help="Optional market filter for optional ticker performance")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = write_datacenter_index_report(
            analysis_db_path=args.analysis_db,
            taxonomy_version=args.taxonomy_version,
            as_of_date=args.as_of_date,
            output_md=args.output_md,
            output_csv=args.output_csv,
            top_n=args.top_n,
            include_ticker_performance=args.include_ticker_performance,
            ohlcv_db_path=args.ohlcv_db,
            taxonomy_csv=args.taxonomy_csv,
            market=args.market,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in format_report_summary_lines(summary):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
