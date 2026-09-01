from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.score.engine import ScorePaths, run_score, score_paths
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_MODEL_FINGERPRINT
from rawcandle.fundamentals.valuation.production import PRODUCTION_PATHS, validate_production_request
from rawcandle.fundamentals.relative_position.production import (
    PRODUCTION_PATHS as RELATIVE_POSITION_PRODUCTION_PATHS,
    validate_production_request as validate_relative_position_production_request,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Fundamentals V4 Simple Fundamental Score V1")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd().resolve())
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--valuation-model-fingerprint", required=True)
    parser.add_argument("--relative-position-model-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = score_paths(args.repo_root)
    if args.artifact_root:
        paths = ScorePaths(
            repo_root=paths.repo_root,
            artifact_root=args.artifact_root,
            canonical_db=paths.canonical_db,
            analysis_db=paths.analysis_db,
            market_db=paths.market_db,
        )
    resolved = validate_production_request(
        canonical_db=paths.canonical_db,
        provider_db=PRODUCTION_PATHS["provider"],
        analysis_db=paths.analysis_db,
        market_db=paths.market_db,
        model_fingerprint=args.valuation_model_fingerprint,
        full_universe=args.full_universe,
        apply=args.apply,
        confirm_production=args.confirm_production,
    )
    relative_resolved = validate_relative_position_production_request(
        canonical_db=paths.canonical_db,
        provider_db=RELATIVE_POSITION_PRODUCTION_PATHS["provider"],
        analysis_db=paths.analysis_db,
        market_db=paths.market_db,
        taxonomy_db=RELATIVE_POSITION_PRODUCTION_PATHS["taxonomy"],
        model_fingerprint=args.relative_position_model_fingerprint,
        full_universe=args.full_universe,
        apply=args.apply,
        confirm_production=args.confirm_production,
    )
    preflight = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "resolved_paths": resolved,
        "valuation_model_fingerprint": args.valuation_model_fingerprint,
        "relative_position_model_fingerprint": args.relative_position_model_fingerprint,
        "relative_position_resolved_paths": relative_resolved,
        "scope": "FULL_UNIVERSE",
    }
    print(json.dumps({"production_preflight": preflight}, sort_keys=True), flush=True)
    summary = run_score(
        paths,
        write_production=args.apply,
        production_preflight=preflight,
        relative_position_model_fingerprint=args.relative_position_model_fingerprint,
    )
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"model_version={summary['model_version']}")
    print(f"model_fingerprint={summary['model_fingerprint']}")
    print(f"score_rows={summary['production']['rows_after']}")
    print(f"status_counts={summary['status_counts']}")
    return 0 if summary["classification"] != "V4_SCORE_V1_IMPLEMENTATION_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
