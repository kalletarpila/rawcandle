from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from rawcandle.fundamentals.diagnostic_flags.rehearsal import run_full_history_rehearsal
from rawcandle.fundamentals.diagnostic_flags.source import ReadOnlyDiagnosticPaths


REHEARSAL_ROOT = Path(__file__).resolve().parents[2] / "temp" / "fundamentals_v4_diagnostic_flags_phase6b"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the read-only Fundamentals V4 Diagnostic Flags V1 rehearsal")
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--freshness-days", type=int, default=180)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.freshness_days < 0:
        raise ValueError("FRESHNESS_DAYS_MUST_BE_NONNEGATIVE")
    output = args.output_dir.resolve()
    try:
        output.relative_to(REHEARSAL_ROOT.resolve())
    except ValueError as exc:
        raise PermissionError("PHASE6B_OUTPUT_MUST_BE_UNDER_REHEARSAL_ROOT") from exc
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("PHASE6B_OUTPUT_DIRECTORY_NOT_EMPTY")
    return run_full_history_rehearsal(
        ReadOnlyDiagnosticPaths(args.canonical_db, args.analysis_db),
        output,
        as_of=args.as_of,
        freshness_days=args.freshness_days,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
