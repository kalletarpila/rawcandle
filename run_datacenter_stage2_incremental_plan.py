#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.pipeline_plan import (
    DEFAULT_SIGNAL_VERSION,
    DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
    build_stage2_incremental_plan,
)
from analysis.datacenter_indices.swing_ticker_persistence import (
    DEFAULT_MAX_VALID_PRICE_ROWS,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only Stage 2 incremental execution plan."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--price-db", type=Path, required=True, help="Path to OHLCV SQLite database")
    parser.add_argument("--taxonomy-csv", type=Path, required=True, help="Path to Datacenter taxonomy CSV")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to plan")
    parser.add_argument("--market", type=str, required=True, help="Market value for Stage 2")
    parser.add_argument("--requested-start", type=str, required=True, help="Requested Stage 2 start date")
    parser.add_argument("--requested-end", type=str, required=True, help="Requested Stage 2 target/end date")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to plan")
    parser.add_argument(
        "--stage2-overlap-trading-days",
        type=int,
        default=DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
        help="Pilot output-overlap policy in valid trading/signal dates",
    )
    parser.add_argument(
        "--max-valid-price-rows",
        type=int,
        default=DEFAULT_MAX_VALID_PRICE_ROWS,
        help="Stage 2 input-history baseline used by the existing bounded preload",
    )
    parser.add_argument("--force-full", action="store_true", help="Force full requested-range materialization")
    parser.add_argument("--force-range-start", type=str, default=None, help="Forced output range start date")
    parser.add_argument("--force-range-end", type=str, default=None, help="Forced output range end date")
    parser.add_argument("--dirty-from-date", type=str, default=None, help="Explicit dirty date for this component")
    parser.add_argument(
        "--dependency-dirty-from-date",
        type=str,
        default=None,
        help="Dirty date propagated from an upstream dependency",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    return parser.parse_args(argv)


def _format_plan_text(plan: dict[str, object]) -> list[str]:
    lines = [
        f"SUMMARY component={plan['component']}",
        f"SUMMARY mode={plan['mode']}",
        f"SUMMARY requested_start={plan['requested_start']}",
        f"SUMMARY requested_end={plan['requested_end']}",
        f"SUMMARY effective_requested_end={plan['effective_requested_end']}",
        f"SUMMARY watermark_start={plan['watermark_start'] or 'NONE'}",
        f"SUMMARY watermark_end={plan['watermark_end'] or 'NONE'}",
        f"SUMMARY materialization_start={plan['materialization_start'] or 'NONE'}",
        f"SUMMARY materialization_end={plan['materialization_end'] or 'NONE'}",
        f"SUMMARY calculation_input_start={plan['calculation_input_start'] or 'NONE'}",
        f"SUMMARY calculation_input_end={plan['calculation_input_end'] or 'NONE'}",
        f"SUMMARY overlap_trading_days={plan['overlap_trading_days']}",
        f"SUMMARY max_valid_price_rows={plan['max_valid_price_rows']}",
        f"SUMMARY write_mode={plan['write_mode']}",
        f"SUMMARY reason_code={plan['reason_code']}",
        f"SUMMARY valid_signal_dates={len(plan['valid_signal_dates'])}",
        f"SUMMARY output_dates={len(plan['output_dates'])}",
        "downstream_stage | component | materialization_start | materialization_end | reason_code",
    ]
    for downstream in plan["downstream_stage_plans"]:
        if not isinstance(downstream, dict):
            continue
        lines.append(
            " | ".join(
                [
                    str(downstream["stage_number"]),
                    str(downstream["component"]),
                    str(downstream["materialization_start"]),
                    str(downstream["materialization_end"]),
                    str(downstream["reason_code"]),
                ]
            )
        )
    lines.append("excluded_stage | component | reason_code")
    for excluded in plan["excluded_stage_plans"]:
        if not isinstance(excluded, dict):
            continue
        lines.append(
            " | ".join(
                [
                    str(excluded["stage_number"]),
                    str(excluded["component"]),
                    str(excluded["reason_code"]),
                ]
            )
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan = build_stage2_incremental_plan(
            analysis_db_path=args.analysis_db,
            price_db_path=args.price_db,
            taxonomy_csv_path=args.taxonomy_csv,
            taxonomy_version=args.taxonomy_version,
            market=args.market,
            requested_start=args.requested_start,
            requested_end=args.requested_end,
            signal_version=args.signal_version,
            overlap_trading_days=args.stage2_overlap_trading_days,
            max_valid_price_rows=args.max_valid_price_rows,
            force_full=args.force_full,
            force_range_start=args.force_range_start,
            force_range_end=args.force_range_end,
            dirty_from_date=args.dirty_from_date,
            dependency_dirty_from_date=args.dependency_dirty_from_date,
        ).to_dict()
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        for line in _format_plan_text(plan):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
