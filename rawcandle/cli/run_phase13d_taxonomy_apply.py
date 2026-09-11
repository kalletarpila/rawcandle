from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13d_backend import Phase13DPaths, apply_taxonomy_preview


def _paths(args: argparse.Namespace) -> Phase13DPaths:
    return Phase13DPaths(args.provider_db, args.canonical_db, args.analysis_db, args.market_db, args.taxonomy_db)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 13D protected taxonomy apply on database copies")
    parser.add_argument("--provider-db", required=True, type=Path)
    parser.add_argument("--canonical-db", required=True, type=Path)
    parser.add_argument("--analysis-db", required=True, type=Path)
    parser.add_argument("--market-db", required=True, type=Path)
    parser.add_argument("--taxonomy-db", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--preview-fingerprint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = apply_taxonomy_preview(
            _paths(args),
            preview_path=args.preview,
            preview_fingerprint=args.preview_fingerprint,
            apply=args.apply,
            confirm_apply=args.confirm_apply,
            output=args.output,
        )
        print(json.dumps({"ok": True, "outcome": result["outcome"], "relative_valuation_state": result.get("relative_valuation_state"), "output": str(args.output)}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
