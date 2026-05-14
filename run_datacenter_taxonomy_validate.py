#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analysis.datacenter_indices import load_datacenter_taxonomy_csv


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate datacenter ecosystem taxonomy CSV and print SUMMARY lines."
    )
    parser.add_argument(
        "--taxonomy-csv",
        type=Path,
        required=True,
        help="Path to datacenter taxonomy CSV",
    )
    parser.add_argument(
        "--taxonomy-version",
        type=str,
        required=True,
        help="Expected taxonomy version for every row",
    )
    return parser.parse_args(argv)


def build_summary(rows) -> list[str]:
    taxonomy_version = rows[0].taxonomy_version if rows else ""
    unique_tickers = len({row.ticker for row in rows})
    layer_count = len({row.layer for row in rows})
    subindustry_count = len({row.subindustry for row in rows})
    status_counts = {
        "CORE": sum(1 for row in rows if row.report_group_status == "CORE"),
        "EXTENDED": sum(1 for row in rows if row.report_group_status == "EXTENDED"),
        "WATCH_ONLY": sum(
            1 for row in rows if row.report_group_status == "WATCH_ONLY"
        ),
        "TOO_SMALL": sum(1 for row in rows if row.report_group_status == "TOO_SMALL"),
    }
    summary = [
        f"SUMMARY taxonomy_version={taxonomy_version}",
        f"SUMMARY taxonomy_rows={len(rows)}",
        f"SUMMARY unique_tickers={unique_tickers}",
        f"SUMMARY layer_count={layer_count}",
        f"SUMMARY subindustry_count={subindustry_count}",
        f"SUMMARY core_rows={status_counts['CORE']}",
        f"SUMMARY extended_rows={status_counts['EXTENDED']}",
        f"SUMMARY watch_only_rows={status_counts['WATCH_ONLY']}",
        f"SUMMARY too_small_rows={status_counts['TOO_SMALL']}",
        "SUMMARY duplicate_rows=0",
        "SUMMARY validation_status=OK",
    ]
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = load_datacenter_taxonomy_csv(
            args.taxonomy_csv,
            expected_taxonomy_version=args.taxonomy_version,
        )
    except ValueError as exc:
        print(f"VALIDATION_ERROR {exc}", file=sys.stderr)
        return 1

    for line in build_summary(rows):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
