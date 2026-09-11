from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13d_backend import Phase13DPaths, build_taxonomy_preview, write_json


def _paths(args: argparse.Namespace) -> Phase13DPaths:
    return Phase13DPaths(args.provider_db, args.canonical_db, args.analysis_db, args.market_db, args.taxonomy_db)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 13D read-only Fundamentals taxonomy change preview")
    parser.add_argument("--provider-db", required=True, type=Path)
    parser.add_argument("--canonical-db", required=True, type=Path)
    parser.add_argument("--analysis-db", required=True, type=Path)
    parser.add_argument("--market-db", required=True, type=Path)
    parser.add_argument("--taxonomy-db", required=True, type=Path)
    parser.add_argument("--changes-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        changes = json.loads(args.changes_json.read_text(encoding="utf-8"))
        result = build_taxonomy_preview(_paths(args), changes)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, result)
        print(json.dumps({"ok": True, "preview_fingerprint": result["preview_fingerprint"], "output": str(args.output)}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
