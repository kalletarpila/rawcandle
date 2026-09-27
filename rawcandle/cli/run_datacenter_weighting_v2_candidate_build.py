from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from analysis.datacenter_indices.swing_group_synthetic_ohlc import WEIGHTED_CALC_VERSION
from rawcandle.datacenter_weighting_v2_migration import build_v2_candidate_generation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a chain-complete weighted V2 candidate generation."
    )
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--price-db", type=Path, required=True)
    parser.add_argument("--taxonomy-csv", type=Path, required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--chain-start-date", default="2025-08-01")
    parser.add_argument("--confirm-analysis-db", type=Path, required=True)
    parser.add_argument("--confirm-calc-version", required=True)
    args = parser.parse_args(argv)
    if args.analysis_db.resolve() != args.confirm_analysis_db.resolve():
        parser.error("--confirm-analysis-db must exactly match --analysis-db")
    if args.confirm_calc_version != WEIGHTED_CALC_VERSION:
        parser.error(f"--confirm-calc-version must be {WEIGHTED_CALC_VERSION}")
    summary = build_v2_candidate_generation(
        analysis_db=args.analysis_db,
        price_db=args.price_db,
        taxonomy_csv=args.taxonomy_csv,
        taxonomy_version=args.taxonomy_version,
        market=args.market,
        requested_end_date=args.end_date,
        validated_chain_start_date=args.chain_start_date,
        created_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    for key in sorted(summary):
        if key != "stages":
            print(f"SUMMARY {key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
