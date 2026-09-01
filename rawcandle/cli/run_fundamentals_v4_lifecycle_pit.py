from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

from rawcandle.fundamentals.lifecycle.persistence import (
    LifecycleResultRepository,
    ensure_lifecycle_pit_schema,
    load_canonical_quarter_versions,
    replay_pit_versions,
    summarize_results,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _production_analysis_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "fundamentals_analysis.db"


def run(
    *,
    source_db: Path,
    destination_db: Path | None,
    apply: bool,
    company_ids: Sequence[int] = (),
    tickers: Sequence[str] = (),
    knowledge_date_from: str | None = None,
    knowledge_date_to: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    generated_at = generated_at_utc or utc_now()
    for value in (knowledge_date_from, knowledge_date_to):
        if value is not None:
            date.fromisoformat(value)
    if knowledge_date_from and knowledge_date_to and knowledge_date_from > knowledge_date_to:
        raise ValueError("LIFECYCLE_KNOWLEDGE_DATE_RANGE_INVALID")
    if apply and destination_db is None:
        raise ValueError("LIFECYCLE_DESTINATION_REQUIRED_FOR_APPLY")
    if destination_db is not None and destination_db.resolve() == _production_analysis_path().resolve():
        raise ValueError("LIFECYCLE_PRODUCTION_DESTINATION_FORBIDDEN_IN_PHASE_2B")
    if destination_db is not None and destination_db.resolve() == source_db.resolve():
        raise ValueError("LIFECYCLE_SOURCE_AND_DESTINATION_MUST_DIFFER")

    versions = load_canonical_quarter_versions(
        source_db,
        company_ids=company_ids,
        tickers=tickers,
        knowledge_date_to=knowledge_date_to,
    )
    computed_results = replay_pit_versions(versions, generated_at_utc=generated_at)
    results = tuple(
        result
        for result in computed_results
        if knowledge_date_from is None or result.knowledge_date >= knowledge_date_from
    )
    summary: dict[str, object] = {
        **summarize_results(results),
        "source_db": str(source_db),
        "destination_db": str(destination_db) if destination_db else None,
        "dry_run": not apply,
        "source_quarter_versions": len(versions),
        "write": {"attempted": 0, "inserted": 0, "duplicate_skipped": 0, "revised_version": 0},
        "errors": 0,
    }
    if apply:
        assert destination_db is not None
        destination_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(destination_db) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            ensure_lifecycle_pit_schema(conn, applied_at_utc=generated_at)
            summary["write"] = LifecycleResultRepository(conn).append(results)
            conn.commit()
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or write Lifecycle V1 PIT rows to an explicit non-production DB")
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--destination-db", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write to the explicit non-production destination")
    parser.add_argument("--company-id", type=int, action="append", default=[])
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--knowledge-date-from")
    parser.add_argument("--knowledge-date-to")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(
        source_db=args.source_db,
        destination_db=args.destination_db,
        apply=args.apply,
        company_ids=args.company_id,
        tickers=args.ticker,
        knowledge_date_from=args.knowledge_date_from,
        knowledge_date_to=args.knowledge_date_to,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
