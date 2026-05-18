#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.pipeline_plan import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    build_datacenter_pipeline_plan,
    format_pipeline_plan_summary_lines,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only datacenter swing pipeline execution recommendation from pipeline watermarks."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to plan")
    parser.add_argument("--market", type=str, required=True, help="Market value for market-scoped components")
    parser.add_argument("--signal-date", type=str, required=True, help="Selected signal date (YYYY-MM-DD)")
    parser.add_argument("--start-date", type=str, required=True, help="Requested swing stage start date (YYYY-MM-DD)")
    parser.add_argument("--index-base-date", type=str, required=True, help="Requested safe index base start date (YYYY-MM-DD)")
    parser.add_argument("--signal-version", type=str, default=DEFAULT_SIGNAL_VERSION, help="Signal version to plan")
    parser.add_argument("--ohlc-calc-version", type=str, default=DEFAULT_OHLC_CALC_VERSION, help="Synthetic OHLC calc version to plan")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_datacenter_pipeline_plan(
            analysis_db_path=args.analysis_db,
            taxonomy_version=args.taxonomy_version,
            market=args.market,
            signal_date=args.signal_date,
            start_date=args.start_date,
            index_base_date=args.index_base_date,
            signal_version=args.signal_version,
            ohlc_calc_version=args.ohlc_calc_version,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for line in format_pipeline_plan_summary_lines(result["summary"]):
        print(line)
    if result["summary"]["validation_status"] == "FAIL":
        return 1
    print(
        "component_name | plan_action | existing_start_date | existing_end_date | requested_start_date | requested_end_date | status | reason"
    )
    for row in result["rows"]:
        print(
            " | ".join(
                [
                    str(row["component_name"]),
                    str(row["plan_action"]),
                    str(row["existing_start_date"]),
                    str(row["existing_end_date"]),
                    str(row["requested_start_date"]),
                    str(row["requested_end_date"]),
                    str(row["status"]),
                    str(row["reason"]),
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
