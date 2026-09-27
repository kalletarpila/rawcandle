from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.datacenter_weighting_v2_migration import (
    run_v2_production_parity_rehearsal,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a temp-copy DC/EC production-parity rehearsal for weighted V2."
    )
    parser.add_argument("--source-analysis-db", type=Path, required=True)
    parser.add_argument("--price-db", type=Path, required=True)
    parser.add_argument("--taxonomy-csv", type=Path, required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--ecosystem", default="DATACENTER")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args(argv)
    summary = run_v2_production_parity_rehearsal(
        source_analysis_db=args.source_analysis_db,
        price_db=args.price_db,
        taxonomy_csv=args.taxonomy_csv,
        taxonomy_version=args.taxonomy_version,
        market=args.market,
        ecosystem_code=args.ecosystem,
        output_dir=args.output_dir,
        requested_end_date=args.end_date,
    )
    for key in sorted(summary):
        if key not in {"first_build_stages", "second_build_stages"}:
            print(f"SUMMARY {key}={summary[key]}")
    return 0 if summary["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
