from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.admin.batch_add_tickers import (
    BatchAddTickerPaths,
    run_apply,
    run_preview,
)
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 13G.2 copy-only Batch Add Tickers CLI.")
    parser.add_argument("tickers", nargs="*", help="Tickers separated by spaces. Commas/newlines are accepted inside values.")
    parser.add_argument("--input-file", type=Path, help="Optional file containing tickers.")
    parser.add_argument("--market", default="usa")
    parser.add_argument("--allow-network", action="store_true", help="Permit bounded Sharadar lookup for tickers missing local/archive fundamentals.")
    parser.add_argument("--apply", action="store_true", help="Run copy-only apply from a saved preview payload.")
    parser.add_argument("--confirm-apply", action="store_true")
    parser.add_argument("--preview-payload", type=Path, help="phase13d_preview_payload.json produced by preview.")
    parser.add_argument("--preview-fingerprint")
    parser.add_argument("--provider-db", type=Path)
    parser.add_argument("--canonical-db", type=Path)
    parser.add_argument("--analysis-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--taxonomy-db", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--temp-root", type=Path)
    parser.add_argument("--keep-copies", action="store_true")
    return parser


def _input_text(args: argparse.Namespace) -> str:
    parts = list(args.tickers or [])
    if args.input_file:
        parts.append(args.input_file.read_text(encoding="utf-8"))
    return " ".join(parts)


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
    try:
        if args.apply:
            if not args.preview_payload or not args.preview_fingerprint:
                raise ValueError("--apply requires --preview-payload and --preview-fingerprint")
            result = run_apply(
                preview_payload_path=args.preview_payload,
                preview_fingerprint=args.preview_fingerprint,
                source_paths=_paths(args),
                run_root=args.run_root or ADMIN_RUN_ROOT,
                temp_root=args.temp_root or ADMIN_TEMP_ROOT,
                confirm_apply=args.confirm_apply,
                keep_copies=args.keep_copies,
            )
        else:
            result = run_preview(
                _input_text(args),
                source_paths=_paths(args),
                run_root=args.run_root or ADMIN_RUN_ROOT,
                temp_root=args.temp_root or ADMIN_TEMP_ROOT,
                network_allowed=args.allow_network,
                market=args.market,
            )
        print(json.dumps({"ok": True, "run_id": result["run_id"], "outcome": result.get("outcome"), "artifact_dir": result["artifact_dir"]}, sort_keys=True))
        return 0 if result.get("outcome") == "COMPLETED" else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
