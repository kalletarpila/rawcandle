from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.relative_position.rehearsal import (
    run_full_universe_rehearsal,
)
from rawcandle.fundamentals.relative_position.source import (
    DEFAULT_FRESHNESS_DAYS,
    ReadOnlySourcePaths,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the read-only Fundamentals V4 Relative Position V1 current-snapshot rehearsal"
        )
    )
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--taxonomy-db", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--freshness-days", type=int, default=DEFAULT_FRESHNESS_DAYS)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    return run_full_universe_rehearsal(
        ReadOnlySourcePaths(
            analysis_db=args.analysis_db,
            canonical_db=args.canonical_db,
            market_db=args.market_db,
            taxonomy_db=args.taxonomy_db,
        ),
        as_of_date=args.as_of_date,
        freshness_days=args.freshness_days,
        output_dir=args.output_dir,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        report = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
