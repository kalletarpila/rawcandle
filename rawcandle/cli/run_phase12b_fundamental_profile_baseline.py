from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.research.fundamental_profile_baseline.runner import run
from rawcandle.research.fundamental_profile_baseline.source import ResearchPaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read-only Phase 12B revised-history baseline research"
    )
    parser.add_argument("--canonical-db", required=True, type=Path)
    parser.add_argument("--analysis-db", required=True, type=Path)
    parser.add_argument("--provider-db", required=True, type=Path)
    parser.add_argument("--market-db", required=True, type=Path)
    parser.add_argument("--taxonomy-db", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--contract-fingerprint", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = run(
            ResearchPaths(
                canonical_db=args.canonical_db,
                analysis_db=args.analysis_db,
                provider_db=args.provider_db,
                market_db=args.market_db,
                taxonomy_db=args.taxonomy_db,
            ),
            args.output_dir,
            contract_fingerprint=args.contract_fingerprint,
        )
        print(json.dumps(result.__dict__, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({
            "outcome": "OUTCOME_D",
            "error": type(exc).__name__,
            "reason": str(exc),
        }, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
