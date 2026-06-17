from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


KNOWN_V2_TABLES = (
    "dc_report_classification_v2",
    "dc_report_context_daily_v2",
    "dc_report_context_group_v2",
    "dc_report_context_window_v2",
    "dc_report_data_quality_summary_v2",
    "dc_report_ecosystem_window_change_v2",
    "dc_report_group_overheat_progression_v2",
    "dc_report_group_relative_change_v2",
    "dc_report_group_timing_persistence_v2",
    "dc_report_ma_break_status_v2",
    "dc_report_run_v2",
    "dc_report_signal_freshness_v2",
    "dc_report_synthetic_event_history_v2",
    "dc_report_taxonomy_ticker_coverage_v2",
    "dc_report_technical_relevance_context_v2",
    "dc_report_valid_signal_date_v2",
    "dc_report_watchlist_ticker_v2",
)

CURRENT_DC_SOURCE_FACT_TABLES = (
    "dc_group_index_daily",
    "dc_group_swing_signal_daily",
    "dc_group_synthetic_ohlc_daily",
    "dc_pipeline_watermark",
    "dc_ticker_swing_signal_daily",
)

CURRENT_EC_KEY_TABLES = (
    "ec_group_index_daily",
    "ec_group_signal_daily",
    "ec_group_synthetic_ohlc_daily",
    "ec_pipeline_watermark",
    "ec_ticker_signal_daily",
)

WARNING_TEXT = (
    "This command is read-only. It does not drop tables. DB cleanup requires "
    "separate backup-confirmed approval. Dropping tables may not shrink SQLite "
    "file size without VACUUM. VACUUM is a separate high-risk operation "
    "requiring disk-space checks."
)

FOREIGN_KEY_VIOLATION_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only preflight inventory for retired dc_report_*_v2 SQLite tables."
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect read-only")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-if-v2-tables",
        action="store_true",
        help="Exit with code 2 if any known dc_report_*_v2 tables exist after printing the report.",
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


def _table_presence(conn: sqlite3.Connection, table_names: tuple[str, ...]) -> list[dict[str, Any]]:
    existing = set(_existing_tables(conn, table_names))
    return [
        {"table": table_name, "present": table_name in existing}
        for table_name in sorted(table_names)
    ]


def _sql_contains_known_table(sql: str | None, table_names: tuple[str, ...]) -> bool:
    if not sql:
        return False
    return any(table_name in sql for table_name in table_names)


def _related_schema_objects(
    conn: sqlite3.Connection,
    present_v2_tables: list[str],
) -> dict[str, Any]:
    indexes = []
    triggers = []
    views = []

    if present_v2_tables:
        indexes = [
            {"name": str(row["name"]), "table": str(row["tbl_name"])}
            for row in conn.execute(
                f"""
                SELECT name, tbl_name
                FROM sqlite_master
                WHERE type='index' AND tbl_name IN ({_placeholders(present_v2_tables)})
                ORDER BY tbl_name, name
                """,
                present_v2_tables,
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
        if table_name in present_v2_tables or _sql_contains_known_table(sql, KNOWN_V2_TABLES):
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
        if _sql_contains_known_table(row["sql"], KNOWN_V2_TABLES):
            views.append(str(row["name"]))

    return {
        "indexes": indexes,
        "triggers": triggers,
        "views": views,
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


def build_preflight_report(db_path: str) -> dict[str, Any]:
    resolved = _validate_db_path(db_path)
    with _connect_read_only(resolved) as conn:
        present_v2_tables = _existing_tables(conn, KNOWN_V2_TABLES)
        table_counts = [
            {"table": table_name, "row_count": _table_row_count(conn, table_name)}
            for table_name in present_v2_tables
        ]
        missing_known_v2_tables = [
            table_name for table_name in sorted(KNOWN_V2_TABLES) if table_name not in present_v2_tables
        ]
        related_schema_objects = _related_schema_objects(conn, present_v2_tables)
        integrity_rows = [str(row[0]) for row in conn.execute("PRAGMA integrity_check").fetchall()]
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        database_list = [
            {"seq": int(row[0]), "name": str(row[1]), "file": str(row[2])}
            for row in conn.execute("PRAGMA database_list").fetchall()
        ]
        preserved_current_tables = {
            "dc_source_facts": _table_presence(conn, CURRENT_DC_SOURCE_FACT_TABLES),
            "ec_key_tables": _table_presence(conn, CURRENT_EC_KEY_TABLES),
        }

    total_rows = sum(int(entry["row_count"]) for entry in table_counts)
    status = "DC_REPORT_V2_TABLES_FOUND" if present_v2_tables else "NO_DC_REPORT_V2_TABLES_FOUND"
    return {
        "db_path": str(resolved),
        "db_exists": True,
        "db_size_bytes": resolved.stat().st_size,
        "status": status,
        "v2_table_count": len(present_v2_tables),
        "total_v2_rows": total_rows,
        "v2_tables": table_counts,
        "missing_known_v2_tables": missing_known_v2_tables,
        "related_schema_objects": related_schema_objects,
        "preserved_current_tables": preserved_current_tables,
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


def _print_table_presence(title: str, entries: list[dict[str, Any]]) -> None:
    print(f"{title}:")
    for entry in entries:
        print(f"  {entry['table']}: {'present' if entry['present'] else 'missing'}")


def _print_text_report(report: dict[str, Any]) -> None:
    print("DC REPORT V2 DB CLEANUP PREFLIGHT")
    print(f"db_path={report['db_path']}")
    print(f"db_exists={report['db_exists']}")
    print(f"db_size_bytes={report['db_size_bytes']}")
    print(f"status={report['status']}")
    print(f"v2_table_count={report['v2_table_count']}")
    print(f"total_v2_rows={report['total_v2_rows']}")
    print("v2_tables:")
    for table in report["v2_tables"]:
        print(f"  {table['table']}: {table['row_count']}")
    if not report["v2_tables"]:
        print("  NONE")

    print("missing_known_v2_tables:")
    for table_name in report["missing_known_v2_tables"]:
        print(f"  {table_name}")
    if not report["missing_known_v2_tables"]:
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

    preserved = report["preserved_current_tables"]
    _print_table_presence("preserved_dc_source_fact_tables", preserved["dc_source_facts"])
    _print_table_presence("preserved_ec_key_tables", preserved["ec_key_tables"])

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

    if args.fail_if_v2_tables and report["v2_table_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
