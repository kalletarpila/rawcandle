from __future__ import annotations

import argparse
from pathlib import Path

from analysis.datacenter_indices.swing_group_synthetic_ohlc import WEIGHTED_CALC_VERSION
from rawcandle.datacenter_weighting_v2_migration import project_v2_to_ec_range


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project an explicit DC weighted V2 date range into EC and audit parity."
    )
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--target-db", type=Path, required=True)
    parser.add_argument("--ecosystem", default="DATACENTER")
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--confirm-target-db", type=Path, required=True)
    parser.add_argument("--confirm-calc-version", required=True)
    args = parser.parse_args(argv)
    if args.target_db.resolve() != args.confirm_target_db.resolve():
        parser.error("--confirm-target-db must exactly match --target-db")
    if args.confirm_calc_version != WEIGHTED_CALC_VERSION:
        parser.error(f"--confirm-calc-version must be {WEIGHTED_CALC_VERSION}")
    summary = project_v2_to_ec_range(
        source_db=args.source_db,
        target_db=args.target_db,
        ecosystem_code=args.ecosystem,
        taxonomy_version=args.taxonomy_version,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    for key in sorted(summary):
        print(f"SUMMARY {key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
