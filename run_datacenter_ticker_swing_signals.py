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
    finalize_ticker_swing_profile_summary,
    format_ticker_scanner_summary_lines,
    format_ticker_swing_profile_summary_lines,
    format_ticker_swing_summary_lines,
    load_existing_ticker_signal_dates,
    load_valid_price_dates_for_market,
    merge_ticker_swing_profile_summary,
    _empty_ticker_swing_profile_aggregate,
    persist_datacenter_ticker_scanner_signals,
    persist_datacenter_ticker_swing_snapshots,
    persist_datacenter_ticker_swing_snapshots_for_dates,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist deterministic datacenter ticker swing base snapshots into dc_ticker_swing_signal_daily."
    )
    parser.add_argument("--price-db", type=Path, required=False, help="Path to OHLCV SQLite database")
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-csv", type=Path, required=False, help="Path to datacenter taxonomy CSV")
    parser.add_argument("--as-of-date", type=str, required=False, help="Exact signal date (YYYY-MM-DD)")
    parser.add_argument("--start-date", type=str, required=False, help="Range start date (YYYY-MM-DD) for scanner-only updates")
    parser.add_argument("--end-date", type=str, required=False, help="Range end date (YYYY-MM-DD)")
    parser.add_argument("--market", type=str, default=None, help="Optional market value to filter from osakedata")
    parser.add_argument("--taxonomy-version", type=str, default=None, help="Optional taxonomy version scope for scanner-only updates")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to persist")
    parser.add_argument("--run-id", type=str, default=None, help="Optional explicit run identifier")
    parser.add_argument("--created-at-utc", type=str, default=None, help="Optional explicit created_at_utc timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    parser.add_argument("--write-mode", type=str, required=True, help="Write mode: insert-missing, upsert, replace-date, update-existing, replace-scanner-range")
    parser.add_argument("--max-valid-price-rows", type=int, default=DEFAULT_MAX_VALID_PRICE_ROWS, help="Maximum valid OHLCV rows to load per ticker")
    parser.add_argument("--scanner-only", action="store_true", help="Update only scanner signal fields on existing ticker swing rows")
    parser.add_argument("--profile", action="store_true", help="Print coarse timing SUMMARY lines for base ticker swing persistence")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.scanner_only:
            selected_start_date = args.start_date or args.as_of_date
            selected_end_date = args.end_date or args.as_of_date or args.start_date
            if selected_start_date is None:
                raise ValueError("as-of-date or start-date is required for scanner-only updates")
            selected_dates = load_existing_ticker_signal_dates(
                analysis_db_path=args.analysis_db,
                start_date=selected_start_date,
                end_date=selected_end_date,
                signal_version=args.signal_version,
                taxonomy_version=args.taxonomy_version,
            )
            summary = persist_datacenter_ticker_scanner_signals(
                analysis_db_path=args.analysis_db,
                start_date=selected_dates[0] if selected_dates else selected_start_date,
                end_date=selected_dates[-1] if selected_dates else selected_end_date,
                signal_version=args.signal_version,
                taxonomy_version=args.taxonomy_version,
                run_id=args.run_id,
                created_at_utc=args.created_at_utc,
                write_mode=args.write_mode,
            )
            summary["taxonomy_version"] = args.taxonomy_version if args.taxonomy_version is not None else "ALL"
            if args.start_date is not None or args.end_date is not None:
                requested_start_date = selected_start_date
                requested_end_date = selected_end_date
                from datetime import date as _date
                calendar_day_count = (
                    (_date.fromisoformat(requested_end_date) - _date.fromisoformat(requested_start_date)).days + 1
                )
                summary["requested_start_date"] = requested_start_date
                summary["requested_end_date"] = requested_end_date
                summary["valid_trading_dates"] = len(selected_dates)
                summary["skipped_non_trading_dates"] = max(calendar_day_count - len(selected_dates), 0)
            lines = format_ticker_scanner_summary_lines(summary)
        else:
            if args.price_db is None or args.taxonomy_csv is None:
                raise ValueError("price-db and taxonomy-csv are required for base ticker swing persistence")
            if args.as_of_date is not None and (args.start_date is not None or args.end_date is not None):
                raise ValueError("Use either as-of-date or start-date/end-date for base ticker swing persistence")
            if args.as_of_date is not None:
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
                    profile=args.profile,
                )
                lines = format_ticker_swing_summary_lines(summary)
            else:
                if args.start_date is None or args.end_date is None:
                    raise ValueError("as-of-date or start-date/end-date are required for base ticker swing persistence")
                valid_dates = load_valid_price_dates_for_market(
                    price_db_path=args.price_db,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    market=args.market,
                    taxonomy_csv_path=args.taxonomy_csv,
                )
                range_lines: list[str] = []
                profile_aggregate = _empty_ticker_swing_profile_aggregate()
                summaries, aggregated_profile_summary = persist_datacenter_ticker_swing_snapshots_for_dates(
                    analysis_db_path=args.analysis_db,
                    price_db_path=args.price_db,
                    taxonomy_csv_path=args.taxonomy_csv,
                    as_of_dates=valid_dates,
                    market=args.market,
                    signal_version=args.signal_version,
                    run_id=args.run_id,
                    created_at_utc=args.created_at_utc,
                    write_mode=args.write_mode,
                    max_valid_price_rows=args.max_valid_price_rows,
                    profile=args.profile,
                )
                for summary in summaries:
                    range_lines.extend(
                        format_ticker_swing_summary_lines(summary, include_profile=not args.profile)
                    )
                    if args.profile:
                        merge_ticker_swing_profile_summary(profile_aggregate, summary)
                from datetime import date as _date
                requested_start_date = args.start_date
                requested_end_date = args.end_date
                calendar_day_count = (
                    (_date.fromisoformat(requested_end_date) - _date.fromisoformat(requested_start_date)).days + 1
                )
                range_lines.extend(
                    [
                        f"SUMMARY requested_start_date={requested_start_date}",
                        f"SUMMARY requested_end_date={requested_end_date}",
                        f"SUMMARY valid_trading_dates={len(valid_dates)}",
                        f"SUMMARY skipped_non_trading_dates={max(calendar_day_count - len(valid_dates), 0)}",
                    ]
                )
                if args.profile:
                    range_lines.extend(
                        format_ticker_swing_profile_summary_lines(
                            aggregated_profile_summary
                            if aggregated_profile_summary is not None
                            else finalize_ticker_swing_profile_summary(profile_aggregate)
                        )
                    )
                lines = range_lines
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
