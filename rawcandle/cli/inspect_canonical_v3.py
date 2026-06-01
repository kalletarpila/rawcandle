from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable


EXPECTED_V3_TABLES = (
    "eco_ecosystem",
    "eco_taxonomy_version",
    "eco_entity",
    "eco_taxonomy_entity_relation",
    "eco_watchlist",
    "eco_watchlist_member",
    "eco_report_window",
    "eco_report_run",
    "eco_entity_window_snapshot",
    "eco_entity_metric_value",
    "eco_entity_coverage",
    "eco_quality_summary",
    "eco_signal_observation",
    "eco_signal_relevance",
    "eco_entity_event",
)


def open_readonly_sqlite(db_path: str) -> sqlite3.Connection:
    resolved_path = Path(db_path).resolve()
    conn = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def count_rows(conn: sqlite3.Connection, table_name: str) -> int:
    if not table_exists(conn, table_name):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count_value FROM {table_name}").fetchone()
    return int(row["count_value"])


def _render_lines(title: str, headers: Iterable[str], rows: list[tuple[object, ...]]) -> list[str]:
    output = [title]
    header_list = list(headers)
    if not rows:
        output.append("(none)")
        return output
    output.append(" | ".join(header_list))
    for row in rows:
        output.append(" | ".join("" if value is None else str(value) for value in row))
    return output


def render_tables_section(conn: sqlite3.Connection) -> list[str]:
    rows = []
    for table_name in EXPECTED_V3_TABLES:
        exists = table_exists(conn, table_name)
        rows.append((table_name, "YES" if exists else "NO", count_rows(conn, table_name) if exists else ""))
    return _render_lines("TABLES", ("table_name", "exists", "row_count"), rows)


def render_windows_section(conn: sqlite3.Connection) -> list[str]:
    if not table_exists(conn, "eco_report_window"):
        return ["REPORT WINDOWS", "eco_report_window missing"]
    rows = conn.execute(
        """
        SELECT window_code, window_label, window_days, is_active, sort_order
        FROM eco_report_window
        ORDER BY sort_order, window_code
        """
    ).fetchall()
    return _render_lines(
        "REPORT WINDOWS",
        ("window_code", "window_label", "window_days", "is_active", "sort_order"),
        [tuple(row) for row in rows],
    )


def render_ecosystems_section(conn: sqlite3.Connection) -> list[str]:
    if not table_exists(conn, "eco_ecosystem"):
        return ["ECOSYSTEMS", "eco_ecosystem missing"]
    rows = conn.execute(
        """
        SELECT ecosystem_code, ecosystem_name, status
        FROM eco_ecosystem
        ORDER BY ecosystem_code
        """
    ).fetchall()
    return _render_lines(
        "ECOSYSTEMS",
        ("ecosystem_code", "ecosystem_name", "status"),
        [tuple(row) for row in rows],
    )


def render_taxonomies_section(conn: sqlite3.Connection) -> list[str]:
    if not table_exists(conn, "eco_ecosystem") or not table_exists(conn, "eco_taxonomy_version"):
        return ["TAXONOMIES", "eco_ecosystem or eco_taxonomy_version missing"]
    rows = conn.execute(
        """
        SELECT e.ecosystem_code, t.version_code, t.version_label, t.status, t.is_active, t.source_type, t.source_reference
        FROM eco_taxonomy_version t
        JOIN eco_ecosystem e ON e.ecosystem_id = t.ecosystem_id
        ORDER BY e.ecosystem_code, t.version_code
        """
    ).fetchall()
    return _render_lines(
        "TAXONOMIES",
        ("ecosystem_code", "version_code", "version_label", "status", "is_active", "source_type", "source_reference"),
        [tuple(row) for row in rows],
    )


def render_watchlists_section(conn: sqlite3.Connection) -> list[str]:
    if not table_exists(conn, "eco_ecosystem") or not table_exists(conn, "eco_watchlist"):
        return ["WATCHLISTS", "eco_ecosystem or eco_watchlist missing"]
    member_count_sql = (
        """
        SELECT w.watchlist_id, COUNT(wm.watchlist_member_id) AS member_count
        FROM eco_watchlist w
        LEFT JOIN eco_watchlist_member wm ON wm.watchlist_id = w.watchlist_id
        GROUP BY w.watchlist_id
        """
        if table_exists(conn, "eco_watchlist_member")
        else None
    )
    member_counts: dict[int, int] = {}
    if member_count_sql is not None:
        for row in conn.execute(member_count_sql).fetchall():
            member_counts[int(row["watchlist_id"])] = int(row["member_count"])
    rows = conn.execute(
        """
        SELECT w.watchlist_id, e.ecosystem_code, w.watchlist_code, w.watchlist_name, w.status, w.source_type, w.source_reference
        FROM eco_watchlist w
        JOIN eco_ecosystem e ON e.ecosystem_id = w.ecosystem_id
        ORDER BY e.ecosystem_code, w.watchlist_code
        """
    ).fetchall()
    rendered_rows = [
        (
            row["ecosystem_code"],
            row["watchlist_code"],
            row["watchlist_name"],
            row["status"],
            row["source_type"],
            row["source_reference"],
            member_counts.get(int(row["watchlist_id"]), 0) if member_count_sql is not None else "",
        )
        for row in rows
    ]
    return _render_lines(
        "WATCHLISTS",
        ("ecosystem_code", "watchlist_code", "watchlist_name", "status", "source_type", "source_reference", "member_count"),
        rendered_rows,
    )


def render_counts_section(conn: sqlite3.Connection) -> list[str]:
    rows = [(table_name, count_rows(conn, table_name)) for table_name in EXPECTED_V3_TABLES]
    return _render_lines("ROW COUNTS", ("table_name", "row_count"), rows)


def render_text_report(
    conn: sqlite3.Connection,
    *,
    show_tables: bool,
    show_windows: bool,
    show_ecosystems: bool,
    show_taxonomies: bool,
    show_watchlists: bool,
    show_counts: bool,
) -> str:
    sections = ["CANONICAL V3 INSPECT"]
    if show_tables:
        sections.extend(["", *render_tables_section(conn)])
    if show_windows:
        sections.extend(["", *render_windows_section(conn)])
    if show_ecosystems:
        sections.extend(["", *render_ecosystems_section(conn)])
    if show_taxonomies:
        sections.extend(["", *render_taxonomies_section(conn)])
    if show_watchlists:
        sections.extend(["", *render_watchlists_section(conn)])
    if show_counts:
        sections.extend(["", *render_counts_section(conn)])
    return "\n".join(sections) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Canonical V3 schema/data in a SQLite database")
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect")
    parser.add_argument("--format", choices=("text",), default="text")
    parser.add_argument("--show-tables", action="store_true")
    parser.add_argument("--show-windows", action="store_true")
    parser.add_argument("--show-ecosystems", action="store_true")
    parser.add_argument("--show-taxonomies", action="store_true")
    parser.add_argument("--show-watchlists", action="store_true")
    parser.add_argument("--show-counts", action="store_true")
    parser.add_argument("--show-all", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.show_all:
        show_tables = True
        show_windows = True
        show_ecosystems = True
        show_taxonomies = True
        show_watchlists = True
        show_counts = True
    else:
        any_show_flag = any(
            (
                args.show_tables,
                args.show_windows,
                args.show_ecosystems,
                args.show_taxonomies,
                args.show_watchlists,
                args.show_counts,
            )
        )
        if any_show_flag:
            show_tables = args.show_tables
            show_windows = args.show_windows
            show_ecosystems = args.show_ecosystems
            show_taxonomies = args.show_taxonomies
            show_watchlists = args.show_watchlists
            show_counts = args.show_counts
        else:
            show_tables = True
            show_windows = True
            show_ecosystems = True
            show_taxonomies = True
            show_watchlists = True
            show_counts = True

    with open_readonly_sqlite(args.db) as conn:
        if args.format == "text":
            print(
                render_text_report(
                    conn,
                    show_tables=show_tables,
                    show_windows=show_windows,
                    show_ecosystems=show_ecosystems,
                    show_taxonomies=show_taxonomies,
                    show_watchlists=show_watchlists,
                    show_counts=show_counts,
                ),
                end="",
            )
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
