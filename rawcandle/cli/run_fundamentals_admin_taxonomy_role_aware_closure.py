from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.taxonomy import TaxonomyPaths
from rawcandle.fundamentals.admin.taxonomy_role_aware_closure import DEFAULT_RETAINED_RUN, run_role_aware_taxonomy_closure


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 13G.4.2.1 role-aware dc_ecosystem taxonomy closure.")
    parser.add_argument("--provider-db", type=Path)
    parser.add_argument("--canonical-db", type=Path)
    parser.add_argument("--analysis-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--taxonomy-db", type=Path)
    parser.add_argument("--retained-run-dir", type=Path, default=DEFAULT_RETAINED_RUN)
    parser.add_argument("--run-root", type=Path, default=ADMIN_RUN_ROOT)
    parser.add_argument("--targeted-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--test-results-json", type=Path)
    return parser


def _paths(args: argparse.Namespace) -> TaxonomyPaths:
    defaults = TaxonomyPaths()
    return TaxonomyPaths(
        provider_db=args.provider_db or defaults.provider_db,
        canonical_db=args.canonical_db or defaults.canonical_db,
        analysis_db=args.analysis_db or defaults.analysis_db,
        market_db=args.market_db or defaults.market_db,
        taxonomy_db=args.taxonomy_db or defaults.taxonomy_db,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    test_results = {}
    if args.test_results_json:
        test_results = json.loads(args.test_results_json.read_text(encoding="utf-8"))
    result = run_role_aware_taxonomy_closure(
        source_paths=_paths(args),
        retained_run_dir=args.retained_run_dir,
        run_root=args.run_root,
        targeted_timeout_seconds=args.targeted_timeout_seconds,
        test_results=test_results,
    )
    print(json.dumps({"ok": result.get("error") is None, "run_id": result["run_id"], "artifact_dir": result["artifact_dir"], "outcome": result.get("outcome_text")}, sort_keys=True))
    return 0 if result.get("error") is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
