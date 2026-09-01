from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.relative_position.phase4c import run_phase4c
from rawcandle.fundamentals.relative_position.source import ReadOnlySourcePaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run protected Relative Position V1 Phase 4C rehearsal operations"
    )
    parser.add_argument("--analysis-source", type=Path, required=True)
    parser.add_argument("--canonical-source", type=Path, required=True)
    parser.add_argument("--market-source", type=Path, required=True)
    parser.add_argument("--taxonomy-source", type=Path, required=True)
    parser.add_argument("--analysis-destination", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--model-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--create-online-backup", action="store_true")
    parser.add_argument("--verify-idempotency", action="store_true")
    parser.add_argument("--exercise-changed-source", action="store_true")
    parser.add_argument("--exercise-failures", action="store_true")
    parser.add_argument("--output-json", type=Path)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    return run_phase4c(
        ReadOnlySourcePaths(
            analysis_db=args.analysis_source,
            canonical_db=args.canonical_source,
            market_db=args.market_source,
            taxonomy_db=args.taxonomy_source,
        ),
        destination=args.analysis_destination,
        as_of_date=args.as_of_date,
        model_fingerprint=args.model_fingerprint,
        full_universe=args.full_universe,
        apply=args.apply,
        create_online_backup=args.create_online_backup,
        verify_idempotency=args.verify_idempotency,
        exercise_changed_source=args.exercise_changed_source,
        exercise_failures=args.exercise_failures,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc), "ok": False}, sort_keys=True), file=sys.stderr)
        return 2
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
