#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices.pipeline_watermark import list_pipeline_watermarks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect read-only datacenter pipeline watermarks from analysis.db."
    )
    parser.add_argument("--analysis-db", type=Path, required=True, help="Path to analysis.db")
    parser.add_argument("--taxonomy-version", type=str, required=True, help="Taxonomy version to inspect")
    parser.add_argument("--component-name", type=str, default=None, help="Optional component name filter")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = list_pipeline_watermarks(
            analysis_db_path=args.analysis_db,
            taxonomy_version=args.taxonomy_version,
            component_name=args.component_name,
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    print(f"SUMMARY taxonomy_version={args.taxonomy_version}")
    print(f"SUMMARY component_count={len(rows)}")
    print("SUMMARY validation_status=OK")
    print(
        "component_name | market | signal_version | calc_version | start_date | end_date | status | row_count | last_successful_at_utc"
    )
    for row in rows:
        print(
            " | ".join(
                [
                    str(row["component_name"]),
                    str(row["market"]),
                    str(row["signal_version"]),
                    str(row["calc_version"]),
                    str(row["start_date"]),
                    str(row["end_date"]),
                    str(row["status"]),
                    "" if row["row_count"] is None else str(row["row_count"]),
                    str(row["last_successful_at_utc"]),
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
