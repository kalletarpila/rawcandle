#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.swing_group_persistence import (
    DEFAULT_SIGNAL_VERSION,
    format_group_swing_overheat_summary_lines,
    format_group_swing_summary_lines,
    format_group_swing_timing_summary_lines,
    persist_datacenter_group_overheat_risk,
    persist_datacenter_group_timing_states,
    persist_datacenter_group_swing_signals,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist deterministic datacenter group swing metrics into dc_group_swing_signal_daily."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-csv", type=Path, required=False, help="Path to datacenter taxonomy CSV")
    parser.add_argument("--signal-date", type=str, required=False, help="Exact signal date (YYYY-MM-DD)")
    parser.add_argument("--start-date", type=str, required=False, help="Range start date (YYYY-MM-DD) for timing-only updates")
    parser.add_argument("--end-date", type=str, required=False, help="Range end date (YYYY-MM-DD) for timing-only updates")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to persist")
    parser.add_argument("--run-id", type=str, default=None, help="Optional explicit run identifier")
    parser.add_argument("--created-at-utc", type=str, default=None, help="Optional explicit created_at_utc timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    parser.add_argument("--write-mode", type=str, required=True, help="Write mode: insert-missing, upsert, replace-date, update-existing, replace-timing-range, replace-overheat-range")
    parser.add_argument("--timing-only", action="store_true", help="Update only timing_state and timing_reason on existing group swing rows")
    parser.add_argument("--overheat-only", action="store_true", help="Update only overheat_risk_level on existing group swing rows")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if sum(1 for flag in (args.timing_only, args.overheat_only) if flag) > 1:
            raise ValueError("timing-only and overheat-only cannot be used together")
        if args.overheat_only:
            selected_start_date = args.start_date or args.signal_date
            selected_end_date = args.end_date or args.signal_date or args.start_date
            if selected_start_date is None:
                raise ValueError("signal-date or start-date is required for overheat-only updates")
            summary = persist_datacenter_group_overheat_risk(
                analysis_db_path=args.analysis_db,
                start_date=selected_start_date,
                end_date=selected_end_date,
                signal_version=args.signal_version,
                run_id=args.run_id,
                created_at_utc=args.created_at_utc,
                write_mode=args.write_mode,
            )
            lines = format_group_swing_overheat_summary_lines(summary)
        elif args.timing_only:
            selected_start_date = args.start_date or args.signal_date
            selected_end_date = args.end_date or args.signal_date or args.start_date
            if selected_start_date is None:
                raise ValueError("signal-date or start-date is required for timing-only updates")
            summary = persist_datacenter_group_timing_states(
                analysis_db_path=args.analysis_db,
                start_date=selected_start_date,
                end_date=selected_end_date,
                signal_version=args.signal_version,
                run_id=args.run_id,
                created_at_utc=args.created_at_utc,
                write_mode=args.write_mode,
            )
            lines = format_group_swing_timing_summary_lines(summary)
        else:
            if args.taxonomy_csv is None or args.signal_date is None:
                raise ValueError("taxonomy-csv and signal-date are required for base group swing persistence")
            summary = persist_datacenter_group_swing_signals(
                analysis_db_path=args.analysis_db,
                taxonomy_csv_path=args.taxonomy_csv,
                signal_date=args.signal_date,
                signal_version=args.signal_version,
                run_id=args.run_id,
                created_at_utc=args.created_at_utc,
                write_mode=args.write_mode,
            )
            lines = format_group_swing_summary_lines(summary)
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
