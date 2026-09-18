from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.progress import progress_line
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.taxonomy_v2_sync import run_apply, run_preview, run_production_apply


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild Fundamentals from the active dc_ecosystem taxonomy.")
    parser.add_argument("--taxonomy", default="dc_ecosystem", choices=("dc_ecosystem",))
    parser.add_argument("--apply", action="store_true", help="Run copy-only apply from a saved preview payload.")
    parser.add_argument("--production", action="store_true", help="Reserved until atomic V2 production publication is available.")
    parser.add_argument("--confirm-apply", action="store_true")
    parser.add_argument("--confirm-production")
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


def _paths(args: argparse.Namespace) -> BatchAddTickerPaths:
    defaults = BatchAddTickerPaths()
    return BatchAddTickerPaths(
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
        if args.production and args.apply:
            result = run_production_apply()
        elif args.production:
            result = run_preview(taxonomy_domain=args.taxonomy, source_paths=_paths(args), run_root=args.run_root or ADMIN_RUN_ROOT)
        elif args.apply:
            if not args.preview_payload or not args.preview_fingerprint:
                raise ValueError("--apply requires --preview-payload and --preview-fingerprint")
            result = run_apply(
                taxonomy_domain=args.taxonomy,
                preview_payload_path=args.preview_payload,
                preview_fingerprint=args.preview_fingerprint,
                source_paths=_paths(args),
                run_root=args.run_root or ADMIN_RUN_ROOT,
                temp_root=args.temp_root or Path("temp/fundamentals_admin_taxonomy"),
                confirm_apply=args.confirm_apply,
                progress_callback=progress_callback,
            )
        else:
            result = run_preview(
                taxonomy_domain=args.taxonomy,
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
