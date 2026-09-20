from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.universe_removal import run_preview, run_production, run_test


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Controlled Fundamentals-universe ticker removal")
    result.add_argument("ticker", nargs="?")
    result.add_argument("--mode", choices=("preview", "test", "production"))
    result.add_argument("--preview-payload", type=Path)
    result.add_argument("--preview-fingerprint")
    result.add_argument("--test-run-id")
    result.add_argument("--confirm-production", action="store_true")
    result.add_argument("--backup-root", type=Path)
    result.add_argument("--provider-db", type=Path)
    result.add_argument("--canonical-db", type=Path)
    result.add_argument("--analysis-db", type=Path)
    result.add_argument("--market-db", type=Path)
    result.add_argument("--taxonomy-db", type=Path)
    result.add_argument("--run-root", type=Path, default=ADMIN_RUN_ROOT)
    result.add_argument("--temp-root", type=Path, default=ADMIN_TEMP_ROOT)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.mode or not args.ticker:
        parser().print_help()
        return 2
    defaults = BatchAddTickerPaths()
    paths = BatchAddTickerPaths(
        args.provider_db or defaults.provider_db, args.canonical_db or defaults.canonical_db,
        args.analysis_db or defaults.analysis_db, args.market_db or defaults.market_db,
        args.taxonomy_db or defaults.taxonomy_db,
    )
    try:
        if args.mode == "preview":
            result = run_preview(args.ticker, source_paths=paths, run_root=args.run_root)
        elif args.mode == "test":
            if not args.preview_payload or not args.preview_fingerprint:
                raise ValueError("test requires --preview-payload and --preview-fingerprint")
            result = run_test(
                preview_payload_path=args.preview_payload, preview_fingerprint=args.preview_fingerprint,
                source_paths=paths, run_root=args.run_root, temp_root=args.temp_root,
            )
        else:
            if not args.preview_payload or not args.preview_fingerprint or not args.test_run_id:
                raise ValueError("production requires --preview-payload, --preview-fingerprint and --test-run-id")
            kwargs = {}
            if args.backup_root is not None:
                kwargs["backup_root"] = args.backup_root
            result = run_production(
                preview_payload_path=args.preview_payload, preview_fingerprint=args.preview_fingerprint,
                test_run_id=args.test_run_id, confirm_production=args.confirm_production,
                source_paths=paths, run_root=args.run_root, temp_root=args.temp_root, **kwargs,
            )
        print(json.dumps({"ok": result["outcome"] == "COMPLETED", "run_id": result["run_id"], "outcome": result["outcome"], "artifact_dir": result["artifact_dir"]}, sort_keys=True))
        return 0 if result["outcome"] == "COMPLETED" else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
