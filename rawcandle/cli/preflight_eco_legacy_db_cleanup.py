from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


WARNING_TEXT = (
    "This command is read-only. It does not drop tables. DB cleanup requires "
    "separate backup-confirmed approval. Dropping tables may not shrink SQLite "
    "file size without VACUUM. VACUUM is a separate high-risk operation "
    "requiring disk-space checks."
)

FOREIGN_KEY_VIOLATION_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only preflight inventory for legacy eco_* SQLite tables."
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect read-only")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--include-empty",
        action="store_true",
        default=True,
        help="Include empty eco_* tables in the report. This is the default.",
    )
    parser.add_argument(
        "--fail-if-eco-tables",
        action="store_true",
        help="Exit with code 2 if any eco_* tables exist after printing the report.",
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


def _fetch_names(conn: sqlite3.Connection, query: str) -> list[str]:
    rows = conn.execute(query).fetchall()
    return [str(row["name"]) for row in rows]


def _table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS row_count FROM {_quote_identifier(table_name)}").fetchone()
    return int(row["row_count"])


def build_preflight_report(db_path: str) -> dict[str, Any]:
    resolved = _validate_db_path(db_path)
    with _connect_read_only(resolved) as conn:
        eco_tables = _fetch_names(
            conn,
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name GLOB 'eco_*'
            ORDER BY name
            """,
        )
        table_counts = [
            {"table": table_name, "row_count": _table_row_count(conn, table_name)}
            for table_name in eco_tables
        ]
        indexes = [
            {"name": str(row["name"]), "table": str(row["tbl_name"])}
            for row in conn.execute(
                """
                SELECT name, tbl_name
                FROM sqlite_master
                WHERE type='index' AND tbl_name GLOB 'eco_*'
                ORDER BY tbl_name, name
                """
            ).fetchall()
        ]
        triggers = [
            {"name": str(row["name"]), "table": str(row["tbl_name"])}
            for row in conn.execute(
                """
                SELECT name, tbl_name
                FROM sqlite_master
                WHERE type='trigger' AND (tbl_name GLOB 'eco_*' OR instr(sql, 'eco_') > 0)
                ORDER BY name
                """
            ).fetchall()
        ]
        views = _fetch_names(
            conn,
            """
            SELECT name
            FROM sqlite_master
            WHERE type='view' AND instr(sql, 'eco_') > 0
            ORDER BY name
            """,
        )
        integrity_rows = [str(row[0]) for row in conn.execute("PRAGMA integrity_check").fetchall()]
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        database_list = [
            {"seq": int(row[0]), "name": str(row[1]), "file": str(row[2])}
            for row in conn.execute("PRAGMA database_list").fetchall()
        ]

    total_rows = sum(int(entry["row_count"]) for entry in table_counts)
    status = "ECO_TABLES_FOUND" if eco_tables else "NO_ECO_TABLES_FOUND"
    return {
        "db_path": str(resolved),
        "db_exists": True,
        "db_size_bytes": resolved.stat().st_size,
        "status": status,
        "eco_table_count": len(eco_tables),
        "total_eco_rows": total_rows,
        "eco_tables": table_counts,
        "related_schema_objects": {
            "indexes": indexes,
            "triggers": triggers,
            "views": views,
        },
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


def _print_text_report(report: dict[str, Any]) -> None:
    print("ECO LEGACY DB CLEANUP PREFLIGHT")
    print(f"db_path={report['db_path']}")
    print(f"db_exists={report['db_exists']}")
    print(f"db_size_bytes={report['db_size_bytes']}")
    print(f"status={report['status']}")
    print(f"eco_table_count={report['eco_table_count']}")
    print(f"total_eco_rows={report['total_eco_rows']}")
    print("eco_tables:")
    for table in report["eco_tables"]:
        print(f"  {table['table']}: {table['row_count']}")
    if not report["eco_tables"]:
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

    if args.fail_if_eco_tables and report["eco_table_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
