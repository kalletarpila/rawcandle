from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dev_tools.run_datacenter_dashboard_html import _REPORT_DATE_RE

DEFAULT_FORMAT = "text"
SUPPORTED_FORMATS = {DEFAULT_FORMAT}
SOURCE_NAMES = ("analysis_db", "price_db", "dashboard_db")
RELEVANT_TABLE_TOKENS = (
    "datacenter",
    "dashboard",
    "ecosystem",
    "dow",
    "structure",
    "divergence",
    "candle",
    "signal",
    "layer",
    "subindustry",
    "ticker",
    "report",
    "rc_",
)
MAX_TABLE_ROWS = 50
SECTION_NAMES = (
    "source_reports",
    "action_summary",
    "market_map",
    "watchlist",
    "tickers",
    "decision_trace",
)
SECTION_REQUIREMENTS: dict[str, set[str]] = {
    "source_reports": {
        "source_report_path",
        "source_report_type",
        "source_report_date",
        "loaded_row_count",
        "status",
    },
    "action_summary": {
        "action_bucket",
        "action_label",
        "ticker_count",
        "weight_sum",
        "notes",
    },
    "market_map": {
        "layer_order",
        "subindustry_order",
        "layer_name",
        "subindustry_name",
        "ticker_count",
        "watchlist_count",
        "avg_return_5d",
        "avg_return_20d",
        "avg_return_60d",
        "avg_trend_score",
        "avg_action_score",
        "dominant_action_bucket",
    },
    "watchlist": {
        "ticker",
        "company_name",
        "layer_name",
        "subindustry_name",
        "action_bucket",
        "action_label",
        "watchlist_reason",
        "last_close",
        "return_5d",
        "return_20d",
        "return_60d",
        "trend_state",
        "latest_structure_label",
        "latest_bos_event_type",
        "latest_reset_reason",
        "bullish_candle_signal",
        "bullish_divergence_signal",
        "hidden_bullish_divergence_signal",
        "data_status",
    },
    "tickers": {
        "ticker",
        "company_name",
        "layer_name",
        "subindustry_name",
        "last_close",
        "return_5d",
        "return_20d",
        "return_60d",
        "trend_state",
        "latest_structure_label",
        "latest_bos_event_type",
        "latest_bos_freshness",
        "latest_reset_reason",
        "latest_reset_freshness",
        "bullish_candle_signal",
        "bullish_divergence_signal",
        "hidden_bullish_divergence_signal",
        "action_bucket",
        "action_label",
        "data_status",
    },
    "decision_trace": {
        "ticker",
        "trace_order",
        "rule_group",
        "rule_name",
        "input_value",
        "decision",
        "reason",
    },
}
DASHBOARD_FINAL_SNAPSHOT_TABLES = {
    "source_reports": "ecosystem_dashboard_source_reports",
    "action_summary": "ecosystem_dashboard_action_summary",
    "market_map": "ecosystem_dashboard_market_map",
    "watchlist": "ecosystem_dashboard_watchlist_status",
    "tickers": "ecosystem_dashboard_ticker_status",
    "decision_trace": "ecosystem_dashboard_decision_trace",
}
ANALYSIS_SECTION_TABLE_HINTS = {
    "source_reports": ("report",),
    "action_summary": ("action", "summary", "signal"),
    "market_map": ("group", "layer", "subindustry", "ecosystem"),
    "watchlist": ("watchlist", "signal"),
    "tickers": ("ticker", "signal"),
    "decision_trace": ("trace", "rule", "decision"),
}


@dataclass(frozen=True)
class SourceDatabaseAudit:
    source_name: str
    path: str
    status: str
    reason: str
    table_count: int | None
    tables: dict[str, list[str]]
    table_row_counts: dict[str, int | None]
    table_rows_capped: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit for structured ecosystem dashboard source availability."
    )
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--analysis-db")
    parser.add_argument("--price-db")
    parser.add_argument("--dashboard-db")
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    return parser


def _normalize(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _validate_report_date(report_date: str) -> str:
    normalized = report_date.strip()
    if not _REPORT_DATE_RE.match(normalized):
        raise ValueError(f"invalid report_date format: {normalized}")
    return normalized


def _validate_format(output_format: str) -> str:
    normalized = output_format.strip().lower()
    if normalized not in SUPPORTED_FORMATS:
        raise ValueError(
            f"unsupported format={output_format}; currently supported: {DEFAULT_FORMAT}"
        )
    return normalized


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name ASC
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in rows]


def _table_row_count(conn: sqlite3.Connection, table_name: str) -> int | None:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    except sqlite3.DatabaseError:
        return None
    if row is None:
        return None
    return int(row[0])


def _is_relevant_table_name(table_name: str) -> bool:
    lowered = table_name.lower()
    return any(token in lowered for token in RELEVANT_TABLE_TOKENS)


def _select_tables_for_output(table_names: list[str]) -> tuple[list[str], bool]:
    if len(table_names) <= MAX_TABLE_ROWS:
        return table_names, False
    relevant = [name for name in table_names if _is_relevant_table_name(name)]
    if relevant:
        return relevant[:MAX_TABLE_ROWS], True
    return table_names[:MAX_TABLE_ROWS], True


def _audit_database(source_name: str, path: str | None) -> SourceDatabaseAudit:
    if path is None or not path.strip():
        return SourceDatabaseAudit(
            source_name=source_name,
            path="",
            status="NOT_PROVIDED",
            reason="not_provided",
            table_count=None,
            tables={},
            table_row_counts={},
        )
    normalized_path = path.strip()
    db_path = Path(normalized_path)
    if not db_path.exists():
        return SourceDatabaseAudit(
            source_name=source_name,
            path=normalized_path,
            status="MISSING",
            reason="file_not_found",
            table_count=None,
            tables={},
            table_row_counts={},
        )
    try:
        conn = _connect_read_only(normalized_path)
    except sqlite3.DatabaseError as exc:
        return SourceDatabaseAudit(
            source_name=source_name,
            path=normalized_path,
            status="ERROR",
            reason=f"open_failed:{exc}",
            table_count=None,
            tables={},
            table_row_counts={},
        )
    try:
        table_names = _table_names(conn)
        selected_table_names, capped = _select_tables_for_output(table_names)
        table_columns = {
            table_name: _table_columns(conn, table_name) for table_name in selected_table_names
        }
        row_counts = {
            table_name: _table_row_count(conn, table_name) for table_name in selected_table_names
        }
        return SourceDatabaseAudit(
            source_name=source_name,
            path=normalized_path,
            status="OK",
            reason="read_only_open_ok",
            table_count=len(table_names),
            tables=table_columns,
            table_row_counts=row_counts,
            table_rows_capped=capped,
        )
    except sqlite3.DatabaseError as exc:
        return SourceDatabaseAudit(
            source_name=source_name,
            path=normalized_path,
            status="ERROR",
            reason=f"inspect_failed:{exc}",
            table_count=None,
            tables={},
            table_row_counts={},
        )
    finally:
        conn.close()


def _direct_threshold(section_name: str) -> int:
    required_count = len(SECTION_REQUIREMENTS[section_name])
    return max(required_count - 1, 3)


def _match_section_from_analysis_like_sources(
    section_name: str,
    audits: dict[str, SourceDatabaseAudit],
) -> tuple[str, str, str]:
    best_candidate_source = ""
    best_reason = "no matching analysis/price tables discovered"
    best_score = 0
    best_status = "MISSING"
    required_columns = SECTION_REQUIREMENTS[section_name]
    hints = ANALYSIS_SECTION_TABLE_HINTS[section_name]

    for source_name in ("analysis_db", "price_db"):
        audit = audits[source_name]
        if audit.status != "OK":
            continue
        for table_name, columns in audit.tables.items():
            lowered_name = table_name.lower()
            if not any(token in lowered_name for token in hints):
                continue
            column_set = set(columns)
            matched_columns = sorted(required_columns & column_set)
            if not matched_columns:
                continue
            status = (
                "DIRECT_AVAILABLE"
                if len(matched_columns) >= _direct_threshold(section_name)
                else "PARTIAL_AVAILABLE"
            )
            candidate_source = f"{source_name}:{table_name}"
            reason = f"matched_columns={','.join(matched_columns)}"
            score = len(matched_columns)
            if (
                score > best_score
                or (score == best_score and candidate_source < best_candidate_source)
            ):
                best_candidate_source = candidate_source
                best_reason = reason
                best_score = score
                best_status = status
    return best_status, best_candidate_source, best_reason


def _section_availability(
    audits: dict[str, SourceDatabaseAudit],
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    dashboard_audit = audits["dashboard_db"]
    has_any_analysis_like_ok = any(
        audits[source_name].status == "OK" for source_name in ("analysis_db", "price_db")
    )

    for section_name in SECTION_NAMES:
        if dashboard_audit.status == "OK" and DASHBOARD_FINAL_SNAPSHOT_TABLES[section_name] in dashboard_audit.tables:
            if has_any_analysis_like_ok:
                status, candidate_source, reason = _match_section_from_analysis_like_sources(
                    section_name,
                    audits,
                )
                if status == "MISSING":
                    rows.append(
                        (
                            section_name,
                            "PARTIAL_AVAILABLE",
                            f"dashboard_db:{DASHBOARD_FINAL_SNAPSHOT_TABLES[section_name]}",
                            "final_snapshot_store_not_direct_structured_source",
                        )
                    )
                    continue
                rows.append((section_name, status, candidate_source, reason))
                continue
            rows.append(
                (
                    section_name,
                    "PARTIAL_AVAILABLE",
                    f"dashboard_db:{DASHBOARD_FINAL_SNAPSHOT_TABLES[section_name]}",
                    "final_snapshot_store_not_direct_structured_source",
                )
            )
            continue

        status, candidate_source, reason = _match_section_from_analysis_like_sources(
            section_name,
            audits,
        )
        rows.append((section_name, status, candidate_source, reason))
    return rows


def _recommended_next_steps(
    availability_rows: list[tuple[str, str, str, str]],
) -> list[tuple[str, str, str]]:
    direct_count = sum(1 for _name, status, _source, _reason in availability_rows if status == "DIRECT_AVAILABLE")
    partial_count = sum(1 for _name, status, _source, _reason in availability_rows if status == "PARTIAL_AVAILABLE")
    if direct_count >= 4:
        return [
            (
                "IMPLEMENT_DIRECT_READER_FROM_EXISTING_TABLES",
                "RECOMMENDED",
                "most required sections appear directly available from structured sources",
            ),
            (
                "KEEP_REPORTS_MODE_AS_FALLBACK",
                "RECOMMENDED",
                "existing reports mode remains the verified compatibility path",
            ),
        ]
    if partial_count > 0:
        return [
            (
                "ADD_STRUCTURED_EXPORT_FROM_DATACENTER_PIPELINE",
                "RECOMMENDED",
                "most required sections are partial or ambiguous; avoid guessing analysis.db semantics",
            ),
            (
                "KEEP_REPORTS_MODE_AS_FALLBACK",
                "RECOMMENDED",
                "reports mode already supplies all sections through parser/decision path",
            ),
        ]
    return [
        (
            "ADD_STRUCTURED_EXPORT_FROM_DATACENTER_PIPELINE",
            "RECOMMENDED",
            "required structured dashboard sections are missing from discovered databases",
        ),
        (
            "KEEP_REPORTS_MODE_AS_FALLBACK",
            "RECOMMENDED",
            "reports mode already supplies all sections through parser/decision path",
        ),
    ]


def _print_row(*values: object) -> None:
    print(";".join(_normalize(value) for value in values))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        normalized_report_date = _validate_report_date(args.report_date)
        _validate_format(args.format)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    audits = {
        "analysis_db": _audit_database("analysis_db", args.analysis_db),
        "price_db": _audit_database("price_db", args.price_db),
        "dashboard_db": _audit_database("dashboard_db", args.dashboard_db),
    }
    availability_rows = _section_availability(audits)
    recommended_rows = _recommended_next_steps(availability_rows)
    direct_count = sum(1 for _name, status, _source, _reason in availability_rows if status == "DIRECT_AVAILABLE")
    partial_count = sum(1 for _name, status, _source, _reason in availability_rows if status == "PARTIAL_AVAILABLE")
    missing_count = sum(1 for _name, status, _source, _reason in availability_rows if status == "MISSING")

    _print_row("section", "source_databases")
    _print_row("source_databases", "source_name", "path", "status", "table_count", "reason")
    for source_name in SOURCE_NAMES:
        audit = audits[source_name]
        _print_row(
            "source_databases",
            source_name,
            audit.path,
            audit.status,
            audit.table_count,
            audit.reason,
        )

    _print_row("section", "source_tables")
    _print_row("source_tables", "source_name", "table_name", "row_count", "columns")
    for source_name in SOURCE_NAMES:
        audit = audits[source_name]
        if audit.status != "OK":
            continue
        for table_name in sorted(audit.tables):
            _print_row(
                "source_tables",
                source_name,
                table_name,
                audit.table_row_counts.get(table_name),
                ",".join(audit.tables[table_name]),
            )

    _print_row("section", "section_availability")
    _print_row("section_availability", "section_name", "status", "candidate_source", "reason")
    for section_name, status, candidate_source, reason in availability_rows:
        _print_row("section_availability", section_name, status, candidate_source, reason)

    _print_row("section", "recommended_next_step")
    _print_row("recommended_next_step", "step", "status", "reason")
    for step, status, reason in recommended_rows:
        _print_row("recommended_next_step", step, status, reason)

    _print_row("section", "summary")
    _print_row(
        f"SUMMARY structured_source_audit.ecosystem_code={args.ecosystem_code.strip()}"
    )
    _print_row(f"SUMMARY structured_source_audit.report_date={normalized_report_date}")
    _print_row(
        f"SUMMARY structured_source_audit.analysis_db_status={audits['analysis_db'].status}"
    )
    _print_row(f"SUMMARY structured_source_audit.price_db_status={audits['price_db'].status}")
    _print_row(
        f"SUMMARY structured_source_audit.dashboard_db_status={audits['dashboard_db'].status}"
    )
    _print_row(
        f"SUMMARY structured_source_audit.direct_available_sections={direct_count}"
    )
    _print_row(
        f"SUMMARY structured_source_audit.partial_available_sections={partial_count}"
    )
    _print_row(f"SUMMARY structured_source_audit.missing_sections={missing_count}")
    if any(audit.table_rows_capped for audit in audits.values()):
        _print_row("SUMMARY structured_source_audit.table_rows_capped=1")
    _print_row("SUMMARY structured_source_audit.status=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
