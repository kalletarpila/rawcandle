from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.valuation.phase3c import run_rehearsal, validate_destinations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or apply Valuation V1 to explicit rehearsal database copies")
    parser.add_argument("--canonical-source", type=Path, required=True)
    parser.add_argument("--provider-source", type=Path, required=True)
    parser.add_argument("--analysis-source", type=Path, required=True)
    parser.add_argument("--market-source", type=Path, required=True)
    parser.add_argument("--canonical-destination", type=Path)
    parser.add_argument("--analysis-destination", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[2]
    validate_destinations(
        repo_root,
        canonical_source=args.canonical_source,
        analysis_source=args.analysis_source,
        provider_source=args.provider_source,
        market_source=args.market_source,
        canonical_destination=args.canonical_destination,
        analysis_destination=args.analysis_destination,
        apply=args.apply,
    )
    plan = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "canonical_source": str(args.canonical_source.resolve()),
        "provider_source": str(args.provider_source.resolve()),
        "analysis_source": str(args.analysis_source.resolve()),
        "market_source": str(args.market_source.resolve()),
        "canonical_destination": str(args.canonical_destination.resolve()) if args.canonical_destination else None,
        "analysis_destination": str(args.analysis_destination.resolve()) if args.analysis_destination else None,
        "stages": ["A_CANONICAL_SCHEMA", "B_COMMON_EARNINGS", "C_COMMON_TTM", "D_VALUATION_DRY_RUN", "E_ANALYSIS_SCHEMA", "F_FULL_HISTORY", "G_IDENTICAL_RERUN"],
    }
    if not args.apply:
        return plan
    if args.output_dir is None:
        raise ValueError("APPLY_REQUIRES_EXPLICIT_OUTPUT_DIRECTORY")
    assert args.canonical_destination is not None and args.analysis_destination is not None
    return run_rehearsal(
        repo_root=repo_root,
        canonical_source=args.canonical_source,
        provider_source=args.provider_source,
        analysis_source=args.analysis_source,
        market_source=args.market_source,
        canonical_destination=args.canonical_destination,
        analysis_destination=args.analysis_destination,
        output_dir=args.output_dir,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        report = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
