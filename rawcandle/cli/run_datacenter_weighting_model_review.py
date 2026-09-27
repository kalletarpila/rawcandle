from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.datacenter_weighting_model_review import run_model_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review V1 DC weighting concentration and shadow guardrails."
    )
    parser.add_argument("--phase3-dir", type=Path, required=True)
    parser.add_argument("--taxonomy-csv", type=Path, required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--price-db", type=Path, required=True)
    parser.add_argument("--market", default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = run_model_review(
            phase3_dir=args.phase3_dir,
            taxonomy_csv=args.taxonomy_csv,
            taxonomy_version=args.taxonomy_version,
            price_db=args.price_db,
            market=args.market,
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
