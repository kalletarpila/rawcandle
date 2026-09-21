from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.identity_resolution import DEFAULT_REGISTRY_PATH, run_preview


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Fundamentals ticker identity resolution Preview.")
    parser.add_argument("tickers", nargs="+", help="One to 25 ticker symbols.")
    parser.add_argument("--provider-db", type=Path)
    parser.add_argument("--canonical-db", type=Path)
    parser.add_argument("--analysis-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--taxonomy-db", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--run-root", type=Path, default=ADMIN_RUN_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    defaults = BatchAddTickerPaths()
    paths = BatchAddTickerPaths(
        args.provider_db or defaults.provider_db,
        args.canonical_db or defaults.canonical_db,
        args.analysis_db or defaults.analysis_db,
        args.market_db or defaults.market_db,
        args.taxonomy_db or defaults.taxonomy_db,
    )
    try:
        result = run_preview(" ".join(args.tickers), source_paths=paths, run_root=args.run_root, registry_path=args.registry)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "run_id": result["run_id"], "artifact_dir": result["artifact_dir"], "preview_fingerprint": result["preview_fingerprint"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
