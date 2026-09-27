from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.datacenter_weighting_structure_validation import (
    run_structure_validation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run non-production DC weighting structure validation.")
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--price-db", type=Path, required=True)
    parser.add_argument("--taxonomy-csv", type=Path, required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--chain-start-date", required=True)
    parser.add_argument("--comparison-start-date", required=True)
    parser.add_argument("--comparison-end-date", required=True)
    parser.add_argument("--market", default=None)
    parser.add_argument("--calc-version", default="DC_SWING_OHLC_V1")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = run_structure_validation(
            analysis_db=args.analysis_db,
            price_db=args.price_db,
            taxonomy_csv=args.taxonomy_csv,
            taxonomy_version=args.taxonomy_version,
            chain_start_date=args.chain_start_date,
            comparison_start_date=args.comparison_start_date,
            comparison_end_date=args.comparison_end_date,
            market=args.market,
            calc_version=args.calc_version,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"ERROR {exc}")
        return 1
    for key in sorted(summary):
        print(f"SUMMARY {key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
