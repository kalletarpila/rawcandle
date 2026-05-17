#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_daily_report import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    format_daily_swing_report_summary_lines,
    write_daily_swing_signal_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a read-only datacenter daily swing signal report from persisted analysis tables."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--signal-date", type=str, required=True, help="Exact report date (YYYY-MM-DD)")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to report")
    parser.add_argument("--ohlc-calc-version", type=str, default=DEFAULT_OHLC_CALC_VERSION, help="Synthetic OHLC calc version to report")
    parser.add_argument("--taxonomy-version", type=str, default=None, help="Optional taxonomy_version to scope the report")
    parser.add_argument("--output-md", type=Path, default=None, help="Optional output Markdown path")
    parser.add_argument("--output-csv", type=Path, default=None, help="Optional output CSV path")
    parser.add_argument("--top-n", type=int, default=20, help="Maximum row count for scanner and ranking sections")
    parser.add_argument("--generated-at-utc", type=str, default=None, help="Optional explicit generated_at_utc timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = write_daily_swing_signal_report(
            analysis_db_path=args.analysis_db,
            signal_date=args.signal_date,
            signal_version=args.signal_version,
            ohlc_calc_version=args.ohlc_calc_version,
            taxonomy_version=args.taxonomy_version,
            output_md=args.output_md,
            output_csv=args.output_csv,
            top_n=args.top_n,
            generated_at_utc=args.generated_at_utc,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if args.output_md is None:
        print(result["markdown"], end="")
    for line in format_daily_swing_report_summary_lines(result["summary"]):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
