#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_pipeline_orchestrator import (
    DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    format_pipeline_final_summary_lines,
    run_datacenter_swing_pipeline,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full datacenter swing V1 pipeline in the safe operational order."
    )
    parser.add_argument("--price-db", type=Path, required=True, help="Path to OHLCV SQLite database")
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-csv", type=Path, required=True, help="Path to datacenter taxonomy CSV")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to run")
    parser.add_argument("--market", type=str, required=True, help="Market value for ticker and synthetic stages")
    parser.add_argument("--signal-date", type=str, required=True, help="Selected daily report date and weekly end date (YYYY-MM-DD)")
    parser.add_argument("--start-date", type=str, required=True, help="Backfill start date for swing stages (YYYY-MM-DD)")
    parser.add_argument("--index-base-date", type=str, required=True, help="Safe index history anchor and index stage start (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated report files")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to run")
    parser.add_argument("--ohlc-calc-version", type=str, default=DEFAULT_OHLC_CALC_VERSION, help="Synthetic OHLC calc version to run")
    parser.add_argument("--expected-ticker-count", type=int, default=None, help="Optional expected ticker row count for audit")
    parser.add_argument("--expected-group-count", type=int, default=None, help="Optional expected group row count for audit")
    parser.add_argument("--expected-synthetic-ohlc-count", type=int, default=None, help="Optional expected synthetic OHLC row count for audit")
    parser.add_argument("--weekly-window-size", type=int, default=20, help="Rolling valid-trading-day window size for audit and weekly report")
    parser.add_argument("--watchlist-file", type=Path, default=None, help="Optional plain-text watchlist file for daily and rolling reports")
    parser.add_argument("--no-taxonomy-listing", action="store_true", help="Omit the taxonomy listing section from daily and rolling reports")
    parser.add_argument("--technical-relevance-run-id", type=str, default=None, help="Optional explicit technical relevance run_id for daily and weekly report threading")
    parser.add_argument("--no-technical-relevance", action="store_true", help="Disable automatic or explicit technical relevance usage in daily and weekly reports")
    parser.add_argument("--profile-technical-relevance", action="store_true", help="Print optional profiling SUMMARY lines for automatic technical relevance when it executes")
    parser.add_argument("--profile-ticker-swing-snapshots", action="store_true", help="Print optional profiling SUMMARY lines for Stage 2 ticker swing base snapshots")
    parser.add_argument("--stage2-incremental", action="store_true", help="Opt in to Stage 2 incremental execution planning")
    parser.add_argument(
        "--stage2-overlap-trading-days",
        type=int,
        default=DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
        help="Stage 2 incremental output overlap in valid trading days",
    )
    parser.add_argument("--skip-index", action="store_true", help="Skip the datacenter base index stage")
    parser.add_argument("--skip-audit", action="store_true", help="Skip the read-only pipeline audit stage")
    parser.add_argument("--skip-reports", action="store_true", help="Skip daily and weekly report generation")
    parser.add_argument("--audit-strict", action="store_true", help="Upgrade audit count/window warnings to FAIL")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned stages without writing any rows or reports")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.weekly_window_size <= 0:
        print("ERROR weekly-window-size must be greater than 0", file=sys.stderr)
        return 1
    if args.stage2_overlap_trading_days < 0:
        print("ERROR stage2-overlap-trading-days must be zero or greater", file=sys.stderr)
        return 1
    if args.technical_relevance_run_id is not None and not args.technical_relevance_run_id.strip():
        print("ERROR technical-relevance-run-id must be non-empty when provided", file=sys.stderr)
        return 1
    if args.no_technical_relevance and args.technical_relevance_run_id is not None:
        print(
            "ERROR --no-technical-relevance and --technical-relevance-run-id cannot be used together",
            file=sys.stderr,
        )
        return 1
    try:
        result = run_datacenter_swing_pipeline(
            price_db=args.price_db,
            analysis_db=args.analysis_db,
            taxonomy_csv=args.taxonomy_csv,
            taxonomy_version=args.taxonomy_version,
            market=args.market,
            signal_date=args.signal_date,
            start_date=args.start_date,
            index_base_date=args.index_base_date,
            output_dir=args.output_dir,
            signal_version=args.signal_version,
            ohlc_calc_version=args.ohlc_calc_version,
            expected_ticker_count=args.expected_ticker_count,
            expected_group_count=args.expected_group_count,
            expected_synthetic_ohlc_count=args.expected_synthetic_ohlc_count,
            weekly_window_size=args.weekly_window_size,
            watchlist_file=args.watchlist_file,
            no_taxonomy_listing=args.no_taxonomy_listing,
            technical_relevance_run_id=args.technical_relevance_run_id,
            no_technical_relevance=args.no_technical_relevance,
            profile_technical_relevance=args.profile_technical_relevance,
            profile_ticker_swing_snapshots=args.profile_ticker_swing_snapshots,
            stage2_incremental=args.stage2_incremental,
            stage2_overlap_trading_days=args.stage2_overlap_trading_days,
            skip_index=args.skip_index,
            skip_audit=args.skip_audit,
            skip_reports=args.skip_reports,
            audit_strict=args.audit_strict,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in format_pipeline_final_summary_lines(result["summary"]):
        print(line)
    return 1 if result["summary"]["pipeline_status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
