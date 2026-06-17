from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


CURRENT_DASHBOARD_TABLES = (
    "dc_dashboard_action_summary_daily",
    "dc_dashboard_decision_trace_daily",
    "dc_dashboard_enrichment_run_daily",
    "dc_dashboard_group_enrichment_daily",
    "dc_dashboard_ticker_enrichment_daily",
)

LEGACY_SNAPSHOT_TABLES = (
    "dc_dashboard_decision_trace",
    "dc_dashboard_market_map",
    "dc_dashboard_runs",
    "dc_dashboard_source_reports",
    "dc_dashboard_ticker_status",
    "dc_dashboard_watchlist_status",
)

WARNING_TEXT = (
    "This command is read-only. It does not drop tables. Current _daily "
    "dashboard enrichment tables must not be dropped by legacy snapshot cleanup. "
    "DB cleanup requires separate backup-confirmed approval. VACUUM is a "
    "separate high-risk operation requiring disk-space checks."
)

FOREIGN_KEY_VIOLATION_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only preflight inventory for old dc_dashboard snapshot-style "
            "SQLite tables."
        )
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect read-only")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-if-legacy-snapshot-tables",
        action="store_true",
        help=(
            "Exit with code 2 if any known legacy dc_dashboard snapshot tables "
            "exist after printing the report."
        ),
    )
    return parser


def _validate_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"Missing db: {db_path}")
    if not path.is_file():
        raise ValueError(f"db is not a file: {db_path}")
    return path.resolve()


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _placeholders(values: tuple[str, ...] | list[str]) -> str:
    return ", ".join("?" for _ in values)


def _table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS row_count FROM {_quote_identifier(table_name)}").fetchone()
    return int(row["row_count"])


def _existing_tables(conn: sqlite3.Connection, table_names: tuple[str, ...]) -> list[str]:
    rows = conn.execute(
        f"""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name IN ({_placeholders(table_names)})
        ORDER BY name
        """,
        table_names,
    ).fetchall()
    return [str(row["name"]) for row in rows]


def _table_presence_with_counts(
    conn: sqlite3.Connection,
    table_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    existing = set(_existing_tables(conn, table_names))
    entries: list[dict[str, Any]] = []
    for table_name in sorted(table_names):
        present = table_name in existing
        entries.append(
            {
                "table": table_name,
                "present": present,
                "row_count": _table_row_count(conn, table_name) if present else None,
            }
        )
    return entries


def _sql_contains_table_name(sql: str | None, table_name: str) -> bool:
    if not sql:
        return False
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(table_name)}(?![A-Za-z0-9_])"
    return re.search(pattern, sql) is not None


def _sql_contains_any_table(sql: str | None, table_names: tuple[str, ...]) -> bool:
    return any(_sql_contains_table_name(sql, table_name) for table_name in table_names)


def _related_schema_objects(
    conn: sqlite3.Connection,
    present_legacy_tables: list[str],
) -> dict[str, Any]:
    indexes = []
    triggers = []
    views = []

    if present_legacy_tables:
        indexes = [
            {"name": str(row["name"]), "table": str(row["tbl_name"])}
            for row in conn.execute(
                f"""
                SELECT name, tbl_name
                FROM sqlite_master
                WHERE type='index' AND tbl_name IN ({_placeholders(present_legacy_tables)})
                ORDER BY tbl_name, name
                """,
                present_legacy_tables,
            ).fetchall()
        ]

    trigger_rows = conn.execute(
        """
        SELECT name, tbl_name, sql
        FROM sqlite_master
        WHERE type='trigger'
        ORDER BY name
        """
    ).fetchall()
    for row in trigger_rows:
        table_name = str(row["tbl_name"])
        sql = row["sql"]
        if table_name in present_legacy_tables or _sql_contains_any_table(sql, LEGACY_SNAPSHOT_TABLES):
            triggers.append({"name": str(row["name"]), "table": table_name})

    view_rows = conn.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type='view'
        ORDER BY name
        """
    ).fetchall()
    for row in view_rows:
        if _sql_contains_any_table(row["sql"], LEGACY_SNAPSHOT_TABLES):
            views.append(str(row["name"]))

    return {
        "indexes": indexes,
        "triggers": triggers,
        "views": views,
    }


def _other_dc_dashboard_like_tables(conn: sqlite3.Connection) -> list[dict[str, str]]:
    known_tables = set(CURRENT_DASHBOARD_TABLES) | set(LEGACY_SNAPSHOT_TABLES)
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name LIKE 'dc_dashboard%'
        ORDER BY name
        """
    ).fetchall()
    return [
        {"table": str(row["name"]), "classification": "UNKNOWN_REVIEW_REQUIRED"}
        for row in rows
        if str(row["name"]) not in known_tables
    ]


def _foreign_key_violations_from_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for row in rows[:FOREIGN_KEY_VIOLATION_LIMIT]:
        violations.append(
            {
                "table": str(row[0]),
                "rowid": row[1],
                "parent": str(row[2]),
                "fkid": row[3],
            }
        )
    return violations


def build_preflight_report(db_path: str) -> dict[str, Any]:
    resolved = _validate_db_path(db_path)
    with _connect_read_only(resolved) as conn:
        present_legacy_tables = _existing_tables(conn, LEGACY_SNAPSHOT_TABLES)
        legacy_table_counts = [
            {"table": table_name, "row_count": _table_row_count(conn, table_name)}
            for table_name in present_legacy_tables
        ]
        missing_legacy_tables = [
            table_name
            for table_name in sorted(LEGACY_SNAPSHOT_TABLES)
            if table_name not in present_legacy_tables
        ]
        current_dashboard_table_presence = _table_presence_with_counts(
            conn,
            CURRENT_DASHBOARD_TABLES,
        )
        other_dashboard_like_tables = _other_dc_dashboard_like_tables(conn)
        related_schema_objects = _related_schema_objects(conn, present_legacy_tables)
        integrity_rows = [str(row[0]) for row in conn.execute("PRAGMA integrity_check").fetchall()]
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        database_list = [
            {"seq": int(row[0]), "name": str(row[1]), "file": str(row[2])}
            for row in conn.execute("PRAGMA database_list").fetchall()
        ]

    total_legacy_rows = sum(int(entry["row_count"]) for entry in legacy_table_counts)
    status = (
        "LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND"
        if present_legacy_tables
        else "NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND"
    )
    return {
        "db_path": str(resolved),
        "db_exists": True,
        "db_size_bytes": resolved.stat().st_size,
        "status": status,
        "legacy_snapshot_table_count": len(present_legacy_tables),
        "total_legacy_snapshot_rows": total_legacy_rows,
        "legacy_snapshot_tables": legacy_table_counts,
        "missing_known_legacy_snapshot_tables": missing_legacy_tables,
        "current_dashboard_table_presence": current_dashboard_table_presence,
        "other_dc_dashboard_like_tables": other_dashboard_like_tables,
        "related_schema_objects": related_schema_objects,
        "integrity_check": integrity_rows,
        "foreign_key_check": {
            "violation_count": len(fk_rows),
            "violations": _foreign_key_violations_from_rows(fk_rows),
        },
        "page_count": page_count,
        "freelist_count": freelist_count,
        "database_list": database_list,
        "warning": WARNING_TEXT,
    }


def _print_text_report(report: dict[str, Any]) -> None:
    print("DC DASHBOARD LEGACY DB CLEANUP PREFLIGHT")
    print(f"db_path={report['db_path']}")
    print(f"db_exists={report['db_exists']}")
    print(f"db_size_bytes={report['db_size_bytes']}")
    print(f"status={report['status']}")
    print(f"legacy_snapshot_table_count={report['legacy_snapshot_table_count']}")
    print(f"total_legacy_snapshot_rows={report['total_legacy_snapshot_rows']}")

    print("legacy_snapshot_tables:")
    for table in report["legacy_snapshot_tables"]:
        print(f"  {table['table']}: {table['row_count']}")
    if not report["legacy_snapshot_tables"]:
        print("  NONE")

    print("missing_known_legacy_snapshot_tables:")
    for table_name in report["missing_known_legacy_snapshot_tables"]:
        print(f"  {table_name}")
    if not report["missing_known_legacy_snapshot_tables"]:
        print("  NONE")

    print("current_dashboard_table_presence:")
    for entry in report["current_dashboard_table_presence"]:
        state = "present" if entry["present"] else "missing"
        row_count = "NA" if entry["row_count"] is None else entry["row_count"]
        print(f"  {entry['table']}: {state} row_count={row_count}")

    print("other_dc_dashboard_like_tables:")
    for entry in report["other_dc_dashboard_like_tables"]:
        print(f"  {entry['table']}: {entry['classification']}")
    if not report["other_dc_dashboard_like_tables"]:
        print("  NONE")

    related = report["related_schema_objects"]
    print("related_indexes:")
    for index in related["indexes"]:
        print(f"  {index['table']}.{index['name']}")
    if not related["indexes"]:
        print("  NONE")

    print("related_triggers:")
    for trigger in related["triggers"]:
        print(f"  {trigger['table']}.{trigger['name']}")
    if not related["triggers"]:
        print("  NONE")

    print("related_views:")
    for view_name in related["views"]:
        print(f"  {view_name}")
    if not related["views"]:
        print("  NONE")

    print("integrity_check:")
    for value in report["integrity_check"]:
        print(f"  {value}")

    fk_summary = report["foreign_key_check"]
    print(f"foreign_key_violation_count={fk_summary['violation_count']}")
    for violation in fk_summary["violations"]:
        print(
            "  "
            f"table={violation['table']} rowid={violation['rowid']} "
            f"parent={violation['parent']} fkid={violation['fkid']}"
        )
    print(f"page_count={report['page_count']}")
    print(f"freelist_count={report['freelist_count']}")
    print(f"warning={report['warning']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_preflight_report(args.db)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    else:
        _print_text_report(report)

    if (
        args.fail_if_legacy_snapshot_tables
        and report["legacy_snapshot_table_count"] > 0
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
