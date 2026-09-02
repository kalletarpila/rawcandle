from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.delta.rehearsal import RehearsalPaths, run_full_history_rehearsal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the read-only Fundamentals V4 Delta V1 rehearsal")
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--provider-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--taxonomy-db", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--freshness-days", type=int, default=180)
    parser.add_argument("--score-model-fingerprint", required=True)
    parser.add_argument("--lifecycle-model-fingerprint", required=True)
    parser.add_argument("--valuation-model-fingerprint", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    return run_full_history_rehearsal(
        RehearsalPaths(args.analysis_db, args.canonical_db, args.provider_db, args.market_db, args.taxonomy_db),
        as_of_date=args.as_of_date, freshness_days=args.freshness_days,
        score_model_fingerprint=args.score_model_fingerprint,
        lifecycle_model_fingerprint=args.lifecycle_model_fingerprint,
        valuation_model_fingerprint=args.valuation_model_fingerprint,
        output_dir=args.output_dir,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
