from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.progress import progress_line
from rawcandle.fundamentals.admin.taxonomy import SUPPORTED_TAXONOMY_DOMAINS, TEMP_ROOT, TaxonomyPaths, run_apply, run_preview


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 13G.4 copy-only dual-domain taxonomy administration CLI.")
    parser.add_argument("--taxonomy", required=True, choices=SUPPORTED_TAXONOMY_DOMAINS, help="Taxonomy domain to inspect or copy-apply.")
    parser.add_argument("--candidate", type=Path, help="Curated Datacenter taxonomy CSV candidate.")
    parser.add_argument("--candidate-version", help="Expected taxonomy_version in the candidate CSV.")
    parser.add_argument("--apply", action="store_true", help="Run copy-only apply from a saved preview payload.")
    parser.add_argument("--confirm-apply", action="store_true")
    parser.add_argument("--preview-payload", type=Path, help="taxonomy_preview_payload.json produced by preview.")
    parser.add_argument("--preview-fingerprint")
    parser.add_argument("--provider-db", type=Path)
    parser.add_argument("--canonical-db", type=Path)
    parser.add_argument("--analysis-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--taxonomy-db", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--temp-root", type=Path)
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
    progress_callback = None if args.quiet_progress else lambda event: print(progress_line(event), file=sys.stderr, flush=True)
    try:
        if args.apply:
            if not args.preview_payload or not args.preview_fingerprint:
                raise ValueError("--apply requires --preview-payload and --preview-fingerprint")
            result = run_apply(
                taxonomy_domain=args.taxonomy,
                preview_payload_path=args.preview_payload,
                preview_fingerprint=args.preview_fingerprint,
                source_paths=_paths(args),
                run_root=args.run_root or ADMIN_RUN_ROOT,
                temp_root=args.temp_root or TEMP_ROOT,
                confirm_apply=args.confirm_apply,
                progress_callback=progress_callback,
            )
        else:
            result = run_preview(
                taxonomy_domain=args.taxonomy,
                candidate_path=args.candidate,
                candidate_version=args.candidate_version,
                source_paths=_paths(args),
                run_root=args.run_root or ADMIN_RUN_ROOT,
                progress_callback=progress_callback,
            )
        print(json.dumps({"ok": True, "run_id": result["run_id"], "outcome": result.get("outcome"), "artifact_dir": result["artifact_dir"]}, sort_keys=True))
        return 0 if result.get("outcome") in {"COMPLETED", "NO_CHANGE", "ROLLED_BACK"} else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
