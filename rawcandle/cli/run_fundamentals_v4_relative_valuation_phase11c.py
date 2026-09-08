from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.relative_valuation.engine import (
    MODEL_FINGERPRINT, calculate_relative_valuation,
)
from rawcandle.fundamentals.relative_valuation.persistence import (
    LAYOUT_FINGERPRINT, PRODUCTION_ANALYSIS_DB, apply_snapshot,
    ensure_schema, quick_check,
)
from rawcandle.fundamentals.relative_valuation.source import (
    ReadOnlySourcePaths, load_relative_valuation_source,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or apply Phase 11C Relative Valuation to a rehearsal analysis copy")
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--analysis-source-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--taxonomy-db", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--model-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def _validate(args: argparse.Namespace) -> tuple[ReadOnlySourcePaths, Path]:
    if args.model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("RELATIVE_VALUATION_MODEL_FINGERPRINT_MISMATCH")
    sources = ReadOnlySourcePaths(args.analysis_source_db, args.canonical_db, args.market_db, args.taxonomy_db)
    resolved_sources = {path.resolve() for path in (args.canonical_db, args.analysis_source_db, args.market_db, args.taxonomy_db)}
    destination = args.destination
    resolved = destination.resolve()
    if destination.is_symlink() or resolved == PRODUCTION_ANALYSIS_DB.resolve() or resolved in resolved_sources:
        raise PermissionError("RELATIVE_VALUATION_REHEARSAL_DESTINATION_REJECTED")
    temp_root = (Path.cwd() / "temp").resolve()
    if temp_root not in resolved.parents:
        raise PermissionError("RELATIVE_VALUATION_REHEARSAL_DESTINATION_MUST_BE_UNDER_TEMP")
    if args.apply and not args.full_universe:
        raise ValueError("RELATIVE_VALUATION_APPLY_REQUIRES_FULL_UNIVERSE")
    if args.apply and (not destination.exists() or not destination.is_file()):
        raise FileNotFoundError("RELATIVE_VALUATION_DESTINATION_COPY_REQUIRED")
    return sources, resolved


def run(args: argparse.Namespace) -> dict[str, Any]:
    paths, destination = _validate(args)
    source = load_relative_valuation_source(paths, as_of_date=args.as_of_date)
    snapshot = calculate_relative_valuation(
        source.inputs, as_of_date=args.as_of_date,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    output: dict[str, Any] = {
        "mode": "APPLY" if args.apply else "DRY_RUN", "destination": str(destination),
        "as_of_date": args.as_of_date, "model_fingerprint": MODEL_FINGERPRINT,
        "layout_fingerprint": LAYOUT_FINGERPRINT, "source_fingerprint": snapshot.source_fingerprint,
        "result_fingerprint": snapshot.result_fingerprint, "company_count": len(snapshot.companies),
    }
    if not args.apply:
        output["outcome"] = "PLANNED_NO_WRITE"
        return output
    connection = sqlite3.connect(destination)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ensure_schema(connection, applied_at_utc=applied_at)
        connection.commit()
        report = apply_snapshot(connection, snapshot, source.inputs, applied_at_utc=applied_at)
        output.update(report.__dict__)
        output["deep_check"] = quick_check(connection)
    finally:
        connection.close()
    return output


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(build_parser().parse_args(argv))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({"outcome": "FAILED", "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
