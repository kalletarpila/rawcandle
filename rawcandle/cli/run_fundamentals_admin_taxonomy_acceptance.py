from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.progress import progress_line
from rawcandle.fundamentals.admin.taxonomy import TaxonomyPaths
from rawcandle.fundamentals.admin.taxonomy_acceptance import TEMP_ROOT, run_dc_ecosystem_copy_acceptance


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 13G.4.1 dc_ecosystem production-shaped copy-only acceptance.")
    parser.add_argument("--provider-db", type=Path)
    parser.add_argument("--canonical-db", type=Path)
    parser.add_argument("--analysis-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--taxonomy-db", type=Path)
    parser.add_argument("--run-root", type=Path, default=ADMIN_RUN_ROOT)
    parser.add_argument("--temp-root", type=Path, default=TEMP_ROOT)
    parser.add_argument("--run-full-downstream", action="store_true")
    parser.add_argument("--skip-production-postflight", action="store_true")
    parser.add_argument("--scheduler-evidence", type=Path)
    parser.add_argument("--keep-copies-on-failure", action="store_true")
    parser.add_argument("--quiet-progress", action="store_true")
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
    evidence = {}
    if args.scheduler_evidence:
        evidence = json.loads(args.scheduler_evidence.read_text(encoding="utf-8"))
    progress_callback = None if args.quiet_progress else lambda event: print(progress_line(event), file=sys.stderr, flush=True)
    result = run_dc_ecosystem_copy_acceptance(
        source_paths=_paths(args),
        run_root=args.run_root,
        temp_root=args.temp_root,
        run_full_downstream=args.run_full_downstream,
        skip_production_postflight=args.skip_production_postflight,
        scheduler_evidence=evidence,
        keep_copies_on_failure=args.keep_copies_on_failure,
        progress_callback=progress_callback,
    )
    print(json.dumps({"ok": result.get("error") is None, "run_id": result["run_id"], "artifact_dir": result["artifact_dir"], "outcome": result.get("outcome_text") or result.get("outcome")}, sort_keys=True))
    return 0 if result.get("error") is None and args.run_full_downstream else (1 if result.get("error") is None else 2)


if __name__ == "__main__":
    raise SystemExit(main())
