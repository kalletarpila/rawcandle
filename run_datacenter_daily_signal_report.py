#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_daily_report import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    DEFAULT_WATCHLIST_FILE,
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
    parser.add_argument(
        "--watchlist-file",
        type=Path,
        default=Path(DEFAULT_WATCHLIST_FILE),
        help="Plain-text watchlist file with one ticker per line",
    )
    parser.add_argument("--output-md", type=Path, default=None, help="Optional output Markdown path")
    parser.add_argument("--output-csv", type=Path, default=None, help="Optional output CSV path")
    parser.add_argument("--top-n", type=int, default=20, help="Maximum row count for scanner and ranking sections")
    parser.add_argument("--no-taxonomy-listing", action="store_true", help="Omit the full datacenter taxonomy listing section")
    parser.add_argument("--technical-relevance-run-id", type=str, default=None, help="Optional explicit technical relevance run_id for read-only report context")
    parser.add_argument("--generated-at-utc", type=str, default=None, help="Optional explicit generated_at_utc timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    return parser.parse_args(argv)


def _resolve_output_timestamp_hhmm(generated_at_utc: str | None) -> str:
    if generated_at_utc:
        return datetime.strptime(generated_at_utc, "%Y-%m-%dT%H:%M:%SZ").strftime("%H%M")
    return datetime.now().strftime("%H%M")


def _timestamp_output_path(path: Path | None, *, date_value: str, hhmm: str) -> Path | None:
    if path is None:
        return None
    stem = path.stem
    for token in (date_value, date_value.replace("-", "_")):
        if token in stem:
            return path.with_name(f"{stem.replace(token, f'{token}_{hhmm}', 1)}{path.suffix}")
    return path.with_name(f"{stem}_{hhmm}{path.suffix}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_hhmm = _resolve_output_timestamp_hhmm(args.generated_at_utc)
    output_md = _timestamp_output_path(
        args.output_md,
        date_value=args.signal_date,
        hhmm=output_hhmm,
    )
    output_csv = _timestamp_output_path(
        args.output_csv,
        date_value=args.signal_date,
        hhmm=output_hhmm,
    )
    try:
        result = write_daily_swing_signal_report(
            analysis_db_path=args.analysis_db,
            signal_date=args.signal_date,
            signal_version=args.signal_version,
            ohlc_calc_version=args.ohlc_calc_version,
            taxonomy_version=args.taxonomy_version,
            watchlist_file=args.watchlist_file,
            output_md=output_md,
            output_csv=output_csv,
            top_n=args.top_n,
            generated_at_utc=args.generated_at_utc,
            include_taxonomy_listing=not args.no_taxonomy_listing,
            technical_relevance_run_id=args.technical_relevance_run_id,
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
