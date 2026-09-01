from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from rawcandle.fundamentals.lifecycle.revised_history import (
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    RevisedLifecycleRepository,
    build_revised_results,
    ensure_revised_schema,
    load_revised_source,
    logical_fingerprint,
    persisted_rows,
    quick_check,
    replace_revised_results,
    summarize,
)
from rawcandle.fundamentals.score.engine import score_fingerprint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Fundamentals V4 Lifecycle V1 revised history")
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--destination-db", type=Path)
    parser.add_argument("--company-id", action="append", type=int, default=[])
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write to the explicit non-production destination")
    parser.add_argument(
        "--rehearsal-source-analysis-db",
        type=Path,
        help="SQLite-backup this read-only analysis source into destination, then apply twice",
    )
    parser.add_argument("--output-json", type=Path)
    return parser


def _production_analysis_path() -> Path:
    return (Path(__file__).resolve().parents[2] / "data" / "fundamentals_analysis.db").resolve()


def _validate(args: argparse.Namespace) -> None:
    if args.full_universe and (args.company_id or args.ticker):
        raise ValueError("FULL_UNIVERSE_CANNOT_HAVE_COMPANY_FILTERS")
    if not args.full_universe and not args.company_id and not args.ticker:
        raise ValueError("EXPLICIT_SCOPE_REQUIRED")
    if args.apply and args.destination_db is None:
        raise ValueError("APPLY_REQUIRES_EXPLICIT_DESTINATION")
    if args.rehearsal_source_analysis_db and not args.apply:
        raise ValueError("REHEARSAL_REQUIRES_APPLY")
    if args.apply and args.destination_db.resolve() == _production_analysis_path():
        raise ValueError("PHASE_2C_PRODUCTION_DESTINATION_BLOCKED")
    if args.destination_db and args.destination_db.resolve() == args.canonical_db.resolve():
        raise ValueError("SOURCE_AND_DESTINATION_MUST_DIFFER")
    if args.rehearsal_source_analysis_db and args.destination_db.resolve() == args.rehearsal_source_analysis_db.resolve():
        raise ValueError("REHEARSAL_SOURCE_AND_DESTINATION_MUST_DIFFER")


def _backup(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        destination_path.unlink()
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()


def run(args: argparse.Namespace) -> dict[str, object]:
    _validate(args)
    started = time.monotonic()
    source = load_revised_source(
        args.canonical_db,
        company_ids=args.company_id,
        tickers=args.ticker,
    )
    rows = build_revised_results(source)
    company_scope = None if args.full_universe else sorted(
        {int(item.company_id) for item in source.observations} | set(args.company_id)
    )
    report: dict[str, object] = {
        "mode": "APPLY" if args.apply else "PLAN",
        "canonical_db": str(args.canonical_db.resolve()),
        "destination_db": str(args.destination_db.resolve()) if args.destination_db else None,
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "summary": summarize(rows, source.source_input_fingerprint),
        "planned": {"rows": len(rows)},
    }
    plan_database = args.rehearsal_source_analysis_db or args.destination_db
    if plan_database and plan_database.exists():
        with sqlite3.connect(f"file:{plan_database}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            table_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lifecycle_revised_result'"
            ).fetchone()
            if table_exists:
                scope_clause = ""
                scope_params: tuple[object, ...] = ()
                if company_scope:
                    scope_clause = f" AND company_id IN ({','.join('?' for _ in company_scope)})"
                    scope_params = tuple(company_scope)
                existing = int(conn.execute(
                    "SELECT COUNT(*) FROM lifecycle_revised_result "
                    "WHERE model_fingerprint=? AND history_mode='REVISED_HISTORY'" + scope_clause,
                    (MODEL_FINGERPRINT, *scope_params),
                ).fetchone()[0])
                existing_rows = persisted_rows(conn)
                if company_scope is not None:
                    selected = set(company_scope)
                    existing_rows = [row for row in existing_rows if int(row["company_id"]) in selected]
            else:
                existing = 0
                existing_rows = []
        unchanged = logical_fingerprint(existing_rows) == logical_fingerprint(rows)
        report["planned"] = {
            "rows_before": existing,
            "rows_inserted": 0 if unchanged else len(rows),
            "rows_deleted": 0 if unchanged else existing,
            "rows_unchanged": existing if unchanged else 0,
        }
    if args.apply:
        destination = args.destination_db
        assert destination is not None
        production_before = None
        score_before = None
        if args.rehearsal_source_analysis_db:
            production_before = {
                "size": args.rehearsal_source_analysis_db.stat().st_size,
                "mtime_ns": args.rehearsal_source_analysis_db.stat().st_mtime_ns,
            }
            _backup(args.rehearsal_source_analysis_db, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        size_before = destination.stat().st_size if destination.exists() else 0
        with sqlite3.connect(destination) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            ensure_revised_schema(conn)
            has_score = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='score_result'").fetchone()
            score_before = score_fingerprint(conn) if has_score else None
            first = replace_revised_results(conn, rows, company_scope=company_scope)
            conn.commit()
            first_check = quick_check(conn, expected_rows=rows)
            first_fp = first.result_fingerprint
            second = replace_revised_results(conn, rows, company_scope=company_scope)
            conn.commit()
            second_check = quick_check(conn, expected_rows=rows)
            repository = RevisedLifecycleRepository(conn)
            current = repository.current_universe(model_fingerprint=MODEL_FINGERPRINT)
            sample_company_id = int(current[0]["company_id"]) if current else None
            sample_current = repository.current_company(sample_company_id, model_fingerprint=MODEL_FINGERPRINT) if sample_company_id else None
            sample_history = repository.history(sample_company_id, model_fingerprint=MODEL_FINGERPRINT) if sample_company_id else []
            sample_quarter = (
                repository.fiscal_quarter(
                    sample_company_id,
                    int(sample_history[0]["fiscal_year"]),
                    str(sample_history[0]["fiscal_quarter"]),
                    model_fingerprint=MODEL_FINGERPRINT,
                )
                if sample_history else None
            )
            score_after = score_fingerprint(conn) if has_score else None
        if not first_check["ok"] or not second_check["ok"]:
            raise RuntimeError(f"LIFECYCLE_QUICK_CHECK_FAILED:{first_check}:{second_check}")
        if first_fp != second.result_fingerprint or second.rows_inserted != 0:
            raise RuntimeError("LIFECYCLE_SECOND_REBUILD_NOT_IDEMPOTENT")
        if score_before != score_after:
            raise RuntimeError("SCORE_V1_CHANGED_DURING_LIFECYCLE_REHEARSAL")
        report.update({
            "first_apply": first.__dict__,
            "second_apply": second.__dict__,
            "first_quick_check": first_check,
            "second_quick_check": second_check,
            "current_universe_companies": len(current),
            "reader_smoke": {
                "sample_company_id": sample_company_id,
                "current_quarter_id": sample_current["quarter_id"] if sample_current else None,
                "history_rows": len(sample_history),
                "quarter_lookup_id": sample_quarter["quarter_id"] if sample_quarter else None,
            },
            "score_before": score_before,
            "score_after": score_after,
            "destination_growth_bytes": destination.stat().st_size - size_before,
        })
        if args.rehearsal_source_analysis_db:
            production_after = {
                "size": args.rehearsal_source_analysis_db.stat().st_size,
                "mtime_ns": args.rehearsal_source_analysis_db.stat().st_mtime_ns,
            }
            report["production_source_before"] = production_before
            report["production_source_after"] = production_after
            report["production_source_unchanged"] = production_before == production_after
            if production_before != production_after:
                raise RuntimeError("PRODUCTION_ANALYSIS_SOURCE_CHANGED")
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    output = json.dumps(report, indent=2, sort_keys=True)
    print(output)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
