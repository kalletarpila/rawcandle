#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_pipeline_audit import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    DEFAULT_WEEKLY_WINDOW_SIZE,
    format_swing_pipeline_audit_summary_lines,
    load_swing_pipeline_audit,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only datacenter swing pipeline completeness audit for one signal date."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--signal-date", type=str, required=True, help="Selected signal date (YYYY-MM-DD)")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to audit")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to audit")
    parser.add_argument("--ohlc-calc-version", type=str, default=DEFAULT_OHLC_CALC_VERSION, help="Synthetic OHLC calc version to audit")
    parser.add_argument("--expected-ticker-count", type=int, default=None, help="Optional expected ticker row count")
    parser.add_argument("--expected-group-count", type=int, default=None, help="Optional expected group row count")
    parser.add_argument("--expected-synthetic-ohlc-count", type=int, default=None, help="Optional expected synthetic OHLC row count")
    parser.add_argument("--weekly-window-size", type=int, default=DEFAULT_WEEKLY_WINDOW_SIZE, help="Weekly window size to require")
    parser.add_argument("--strict", action="store_true", help="Upgrade count/window warnings to FAIL")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = load_swing_pipeline_audit(
            analysis_db_path=args.analysis_db,
            signal_date=args.signal_date,
            taxonomy_version=args.taxonomy_version,
            signal_version=args.signal_version,
            ohlc_calc_version=args.ohlc_calc_version,
            expected_ticker_count=args.expected_ticker_count,
            expected_group_count=args.expected_group_count,
            expected_synthetic_ohlc_count=args.expected_synthetic_ohlc_count,
            weekly_window_size=args.weekly_window_size,
            strict=args.strict,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in format_swing_pipeline_audit_summary_lines(result["summary"]):
        print(line)
    return 1 if result["summary"]["validation_status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
