from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


EXPECTED_TABLES = [
    "dc_dashboard_ticker_enrichment_daily",
    "dc_dashboard_group_enrichment_daily",
    "dc_dashboard_action_summary_daily",
    "dc_dashboard_decision_trace_daily",
    "dc_dashboard_enrichment_run_daily",
]

OLD_SNAPSHOT_TABLES = [
    "dc_dashboard_runs",
    "dc_dashboard_source_reports",
    "dc_dashboard_market_map",
    "dc_dashboard_watchlist_status",
    "dc_dashboard_ticker_status",
    "dc_dashboard_decision_trace",
]

SECTION_NAME_BY_TABLE = {
    "dc_dashboard_ticker_enrichment_daily": "ticker_enrichment",
    "dc_dashboard_group_enrichment_daily": "group_enrichment",
    "dc_dashboard_action_summary_daily": "action_summary",
    "dc_dashboard_decision_trace_daily": "decision_trace",
    "dc_dashboard_enrichment_run_daily": "enrichment_run",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit for Datacenter dashboard enrichment tables in analysis.db."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--format", default="text")
    return parser


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(f"file:{normalized}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _emit_row(values: list[object]) -> None:
    print(";".join("" if value is None else str(value) for value in values))


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _row_count_total(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])


def _row_count_for_selection(
    conn: sqlite3.Connection,
    table_name: str,
    signal_date: str,
    taxonomy_version: str,
) -> int:
    columns = _table_columns(conn, table_name)
    if "signal_date" not in columns or "taxonomy_version" not in columns:
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version),
    ).fetchone()
    return int(row[0])


def _table_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchone()
    return int(row[0])


def _table_status(exists: bool) -> str:
    return "OK" if exists else "MISSING"


def _section_status(exists: bool, row_count_for_date: int | None) -> tuple[str, str]:
    if not exists:
        return "MISSING_TABLE", "expected_table_missing"
    if (row_count_for_date or 0) > 0:
        return "READY", "rows_available"
    return "EMPTY", "no_rows_for_signal_date_taxonomy_version"


def _overall_status(section_statuses: list[str]) -> tuple[str, str]:
    if any(status == "MISSING_TABLE" for status in section_statuses):
        return "MISSING_TABLES", "missing_expected_tables"
    if all(status == "READY" for status in section_statuses):
        return "READY", "all_sections_ready"
    if any(status == "READY" for status in section_statuses) and any(
        status == "EMPTY" for status in section_statuses
    ):
        return "PARTIAL", "some_sections_empty"
    if all(status == "EMPTY" for status in section_statuses):
        return "EMPTY", "all_sections_empty"
    return "FAILED", "unexpected_section_state"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.format != "text":
        print(
            f"ERROR: unsupported format={args.format}; currently supported: text",
            file=sys.stderr,
        )
        return 1

    try:
        with _connect_read_only(args.analysis_db) as conn:
            table_count = _table_count(conn)

            _emit_row(["section", "database"])
            _emit_row(["database", "path", "status", "table_count", "reason"])
            _emit_row(["database", args.analysis_db, "OK", table_count, ""])

            table_rows: list[tuple[str, bool, int | None, int | None, str]] = []
            missing_tables: list[str] = []
            for table_name in EXPECTED_TABLES:
                exists = _table_exists(conn, table_name)
                total_count = _row_count_total(conn, table_name) if exists else None
                selected_count = (
                    _row_count_for_selection(
                        conn,
                        table_name,
                        args.signal_date,
                        args.taxonomy_version,
                    )
                    if exists
                    else None
                )
                if not exists:
                    missing_tables.append(table_name)
                table_rows.append(
                    (table_name, exists, total_count, selected_count, _table_status(exists))
                )

            _emit_row(["section", "tables"])
            _emit_row(
                ["tables", "table_name", "exists", "row_count_total", "row_count_for_date", "status"]
            )
            for table_name, exists, total_count, selected_count, status in table_rows:
                _emit_row(
                    [
                        "tables",
                        table_name,
                        1 if exists else 0,
                        total_count if exists else "",
                        selected_count if exists else "",
                        status,
                    ]
                )

            _emit_row(["section", "section_readiness"])
            _emit_row(["section_readiness", "section_name", "status", "row_count", "reason"])
            section_rows: list[tuple[str, str, int | str, str]] = []
            section_statuses: list[str] = []
            total_selected_rows = 0
            per_table_selected = {row[0]: row[3] if row[3] is not None else 0 for row in table_rows}
            for table_name, exists, _, selected_count, _ in table_rows:
                section_name = SECTION_NAME_BY_TABLE[table_name]
                status, reason = _section_status(exists, selected_count)
                row_count_value: int | str = "" if not exists else int(selected_count or 0)
                section_rows.append((section_name, status, row_count_value, reason))
                section_statuses.append(status)
                if exists:
                    total_selected_rows += int(selected_count or 0)
            overall_status, overall_reason = _overall_status(section_statuses)
            section_rows.append(("overall", overall_status, total_selected_rows, overall_reason))
            for section_name, status, row_count, reason in section_rows:
                _emit_row(["section_readiness", section_name, status, row_count, reason])

            old_snapshot_present = [
                table_name for table_name in OLD_SNAPSHOT_TABLES if _table_exists(conn, table_name)
            ]

            _emit_row(["section", "warnings"])
            _emit_row(["warnings", "warning_code", "details"])
            if missing_tables:
                _emit_row(
                    [
                        "warnings",
                        "MISSING_EXPECTED_TABLES",
                        ",".join(missing_tables),
                    ]
                )
            if old_snapshot_present:
                _emit_row(
                    [
                        "warnings",
                        "OLD_DASHBOARD_SNAPSHOT_TABLES_PRESENT",
                        ",".join(old_snapshot_present),
                    ]
                )
            if not missing_tables and all(
                int(per_table_selected[table_name]) == 0 for table_name in EXPECTED_TABLES
            ):
                _emit_row(
                    [
                        "warnings",
                        "NO_ENRICHMENT_ROWS_FOR_SELECTION",
                        f"{args.signal_date}|{args.taxonomy_version}",
                    ]
                )

            _emit_row(["section", "summary"])
            print(
                f"SUMMARY datacenter_dashboard_enrichment_audit.analysis_db={args.analysis_db}"
            )
            print(f"SUMMARY datacenter_dashboard_enrichment_audit.signal_date={args.signal_date}")
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.taxonomy_version="
                f"{args.taxonomy_version}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.expected_tables="
                f"{len(EXPECTED_TABLES)}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.missing_tables="
                f"{len(missing_tables)}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.old_snapshot_tables_present="
                f"{len(old_snapshot_present)}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.ticker_rows="
                f"{per_table_selected['dc_dashboard_ticker_enrichment_daily']}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.group_rows="
                f"{per_table_selected['dc_dashboard_group_enrichment_daily']}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.action_summary_rows="
                f"{per_table_selected['dc_dashboard_action_summary_daily']}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.decision_trace_rows="
                f"{per_table_selected['dc_dashboard_decision_trace_daily']}"
            )
            print(
                "SUMMARY datacenter_dashboard_enrichment_audit.enrichment_run_rows="
                f"{per_table_selected['dc_dashboard_enrichment_run_daily']}"
            )
            print(
                f"SUMMARY datacenter_dashboard_enrichment_audit.readiness={overall_status}"
            )
            print("SUMMARY datacenter_dashboard_enrichment_audit.status=OK")
            return 0
    except (FileNotFoundError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
