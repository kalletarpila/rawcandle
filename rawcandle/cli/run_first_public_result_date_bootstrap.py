from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.first_public_result_date_bootstrap import (
    BOOTSTRAP_BACKUP_ROOT,
    RUN_ROOT,
    TEMP_ROOT,
    run_preview,
    run_production,
    run_test,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-time first_public_result_date bootstrap maintenance utility")
    parser.add_argument("mode", choices=("preview", "test", "production"))
    parser.add_argument("--preview-result", type=Path)
    parser.add_argument("--test-result", type=Path)
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--canonical-db", type=Path)
    parser.add_argument("--provider-db", type=Path)
    parser.add_argument("--analysis-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--taxonomy-db", type=Path)
    parser.add_argument("--run-root", type=Path, default=RUN_ROOT)
    parser.add_argument("--temp-root", type=Path, default=TEMP_ROOT)
    parser.add_argument("--backup-root", type=Path, default=BOOTSTRAP_BACKUP_ROOT)
    return parser


def _paths(args: argparse.Namespace) -> BatchAddTickerPaths:
    default = BatchAddTickerPaths()
    return BatchAddTickerPaths(
        provider_db=args.provider_db or default.provider_db,
        canonical_db=args.canonical_db or default.canonical_db,
        analysis_db=args.analysis_db or default.analysis_db,
        market_db=args.market_db or default.market_db,
        taxonomy_db=args.taxonomy_db or default.taxonomy_db,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "preview":
            result = run_preview(paths=_paths(args), run_root=args.run_root)
        elif args.mode == "test":
            if args.preview_result is None:
                raise ValueError("test requires --preview-result")
            result = run_test(
                preview_result_path=args.preview_result, paths=_paths(args),
                run_root=args.run_root, temp_root=args.temp_root,
            )
        else:
            if args.preview_result is None or args.test_result is None:
                raise ValueError("production requires --preview-result and --test-result")
            result = run_production(
                preview_result_path=args.preview_result, test_result_path=args.test_result,
                confirm_production=args.confirm_production, paths=_paths(args),
                run_root=args.run_root, backup_root=args.backup_root,
            )
        print(json.dumps({
            "ok": result.get("outcome") in {"READY", "ALREADY_BOOTSTRAPPED", "COMPLETED"},
            "run_id": result["run_id"], "outcome": result["outcome"],
            "artifact_dir": result["artifact_dir"],
        }, sort_keys=True))
        return 0 if result.get("outcome") in {"READY", "ALREADY_BOOTSTRAPPED", "COMPLETED"} else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
