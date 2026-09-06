from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from rawcandle.fundamentals.snapshot.assembler import (
    SnapshotPaths,
    generate_company_snapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "fundamental_reports"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a read-only Fundamentals V4 Company Snapshot V1 Markdown report"
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--report-date", type=date.fromisoformat, required=True)
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--taxonomy-db", type=Path, required=True)
    parser.add_argument("--provider-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _validate(args: argparse.Namespace) -> SnapshotPaths:
    output = args.output_dir.resolve()
    sources = SnapshotPaths(
        canonical_db=args.canonical_db.resolve(),
        analysis_db=args.analysis_db.resolve(),
        market_db=args.market_db.resolve(),
        taxonomy_db=args.taxonomy_db.resolve(),
        provider_db=args.provider_db.resolve(),
    )
    if output in {path.resolve() for path in sources.__dict__.values()}:
        raise ValueError("REPORT_OUTPUT_MUST_NOT_BE_DATABASE_PATH")
    if output.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("REPORT_OUTPUT_MUST_BE_DIRECTORY")
    return sources


def run(args: argparse.Namespace) -> dict[str, object]:
    paths = _validate(args)
    result = generate_company_snapshot(
        paths,
        ticker=args.ticker,
        report_date=args.report_date.isoformat(),
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    )
    snapshot = result.pop("snapshot")
    return {
        "ok": True,
        **result,
        "ticker": snapshot["identity"]["ticker"],
        "report_date": snapshot["report_date"],
        "anchor": snapshot["anchor"],
        "source_state_fingerprint": snapshot["source_state_fingerprint"],
        "source_packages": snapshot["source_state"],
        "model_fingerprints": snapshot["model_fingerprints"],
    }


def main(argv: list[str] | None = None) -> int:
    try:
        summary = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "FAILED", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
