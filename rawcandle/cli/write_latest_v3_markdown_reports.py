from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from rawcandle.cli.write_v3_markdown_prototypes import write_reports


@dataclass(frozen=True)
class SelectedRun:
    ecosystem_code: str
    taxonomy_version_code: str
    signal_date: str
    run_id: str
    status: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve the latest matching Eco run and write V3 Markdown reports."
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database")
    parser.add_argument("--ecosystem", required=True, help="Eco ecosystem_code")
    parser.add_argument("--taxonomy-version", required=True, help="Eco taxonomy version_code")
    parser.add_argument("--out-dir", required=True, help="Output directory for Markdown files")
    parser.add_argument("--format", required=True, choices=("text",))
    parser.add_argument("--signal-date", help="Optional exact signal_date filter in YYYY-MM-DD format")
    parser.add_argument(
        "--status",
        default="OK,OK_WITH_WARNINGS",
        help="Comma-separated allowed run statuses. Default: OK,OK_WITH_WARNINGS",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing Markdown files",
    )
    parser.add_argument(
        "--only",
        help="Comma-separated subset of horizons: rolling30,rolling5,rolling2,daily",
    )
    return parser


def open_readonly_sqlite(db_path: str) -> sqlite3.Connection:
    resolved_path = Path(db_path).resolve()
    conn = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_status_filter(value: str) -> tuple[str, ...]:
    statuses = tuple(part.strip() for part in value.split(",") if part.strip())
    if not statuses:
        raise ValueError("--status must specify at least one value")
    return statuses


def resolve_latest_run(
    *,
    db_path: str,
    ecosystem: str,
    taxonomy_version: str,
    signal_date: str | None,
    allowed_statuses: tuple[str, ...],
) -> SelectedRun | None:
    placeholders = ", ".join("?" for _ in allowed_statuses)
    query = f"""
        SELECT
            ee.ecosystem_code AS ecosystem_code,
            tv.version_code AS taxonomy_version_code,
            rr.signal_date AS signal_date,
            rr.run_id AS run_id,
            rr.status AS status
        FROM eco_report_run rr
        JOIN eco_ecosystem ee ON ee.ecosystem_id = rr.ecosystem_id
        JOIN eco_taxonomy_version tv ON tv.taxonomy_version_id = rr.taxonomy_version_id
        WHERE ee.ecosystem_code = ?
          AND tv.version_code = ?
          AND rr.status IN ({placeholders})
    """
    params: list[object] = [ecosystem, taxonomy_version, *allowed_statuses]
    if signal_date is not None:
        query += " AND rr.signal_date = ?"
        params.append(signal_date)
    query += """
        ORDER BY
            rr.signal_date DESC,
            COALESCE(rr.created_at_utc, '') DESC,
            rr.run_id DESC
        LIMIT 1
    """

    with open_readonly_sqlite(db_path) as conn:
        row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return SelectedRun(
        ecosystem_code=str(row["ecosystem_code"]),
        taxonomy_version_code=str(row["taxonomy_version_code"]),
        signal_date=str(row["signal_date"]),
        run_id=str(row["run_id"]),
        status=str(row["status"]),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        allowed_statuses = _parse_status_filter(args.status)
        selected = resolve_latest_run(
            db_path=args.db,
            ecosystem=args.ecosystem,
            taxonomy_version=args.taxonomy_version,
            signal_date=args.signal_date,
            allowed_statuses=allowed_statuses,
        )
        if selected is None:
            print("V3 Latest Markdown Reports")
            print(f"ecosystem: {args.ecosystem}")
            print(f"taxonomy_version: {args.taxonomy_version}")
            print(f"signal_date_filter: {args.signal_date or 'LATEST'}")
            print(f"allowed_statuses: {', '.join(allowed_statuses)}")
            print("final_status: NO_MATCHING_ECO_RUN")
            return 1

        out_dir_resolved, written = write_reports(
            db_path=args.db,
            run_id=selected.run_id,
            out_dir=args.out_dir,
            overwrite=args.overwrite,
            only=args.only,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("final_status: REPORT_GENERATION_FAILED")
        return 1

    print("V3 Latest Markdown Reports")
    print(f"db: {Path(args.db).resolve()}")
    print(f"ecosystem: {selected.ecosystem_code}")
    print(f"taxonomy_version: {selected.taxonomy_version_code}")
    print(f"signal_date: {selected.signal_date}")
    print(f"run_id: {selected.run_id}")
    print(f"run_status: {selected.status}")
    print(f"out_dir: {out_dir_resolved}")
    print(f"overwrite: {args.overwrite}")
    print(f"only: {args.only or 'ALL'}")
    for horizon, output_path, byte_count, line_count in written:
        print(f"{horizon}: path={output_path} bytes={byte_count} lines={line_count}")
    print("final_status: REPORTS_GENERATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
