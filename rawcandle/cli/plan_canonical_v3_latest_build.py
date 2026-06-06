from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceReadinessSpec:
    table_name: str
    date_column: str
    required: bool
    note: str


@dataclass(frozen=True)
class AllowedBuildStep:
    step_number: int
    function_name: str
    target_tables: tuple[str, ...]
    source_tables: tuple[str, ...]
    required_parameters: tuple[str, ...]


@dataclass(frozen=True)
class BypassedBuilder:
    function_name: str
    forbidden_sources: tuple[str, ...]
    replacement_builders: tuple[str, ...]


ALLOWED_SOURCE_SPECS = (
    SourceReadinessSpec(
        table_name="dc_ticker_swing_signal_daily",
        date_column="signal_date",
        required=True,
        note="required lower-level ticker source",
    ),
    SourceReadinessSpec(
        table_name="dc_group_swing_signal_daily",
        date_column="signal_date",
        required=True,
        note="required lower-level group source",
    ),
    SourceReadinessSpec(
        table_name="dc_group_synthetic_ohlc_daily",
        date_column="ohlc_date",
        required=True,
        note="required lower-level group synthetic source",
    ),
    SourceReadinessSpec(
        table_name="technical_signal_relevance",
        date_column="signal_date",
        required=True,
        note="required for signal relevance builder",
    ),
    SourceReadinessSpec(
        table_name="stock_dow_structure_events",
        date_column="event_date",
        required=True,
        note="rows with event_date <= signal_date are sufficient",
    ),
    SourceReadinessSpec(
        table_name="dc_group_index_daily",
        date_column="index_date",
        required=False,
        note="not used by current allowed build sequence",
    ),
)

FIXED_FORBIDDEN_TABLES = (
    "dc_report_context_daily_v2",
    "dc_report_context_window_v2",
    "dc_report_context_group_v2",
    "dc_report_classification_v2",
)

ALLOWED_BUILD_STEPS = (
    AllowedBuildStep(
        1,
        "build_canonical_v3_base_run",
        ("eco_report_run", "eco_entity_coverage", "eco_quality_summary"),
        ("eco_ecosystem", "eco_taxonomy_version", "eco_entity", "eco_taxonomy_entity_relation", "eco_watchlist", "eco_watchlist_member", "eco_report_window", "dc_ticker_swing_signal_daily"),
        ("db_path", "ecosystem_code", "signal_date", "taxonomy_version_code", "run_id"),
    ),
    AllowedBuildStep(2, "build_canonical_v3_ticker_daily_direct_metrics", ("eco_entity_metric_value",), ("dc_ticker_swing_signal_daily",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(3, "build_canonical_v3_group_status_from_group_swing", ("eco_entity_metric_value",), ("dc_group_swing_signal_daily",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(4, "build_canonical_v3_group_window_status_from_group_swing", ("eco_entity_metric_value",), ("dc_group_swing_signal_daily",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(5, "build_canonical_v3_ticker_window_metrics", ("eco_entity_metric_value",), ("dc_ticker_swing_signal_daily", "dc_group_swing_signal_daily"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(6, "build_canonical_v3_group_window_metrics", ("eco_entity_metric_value",), ("dc_group_swing_signal_daily", "dc_group_synthetic_ohlc_daily"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(7, "build_canonical_v3_group_historical_metrics", ("eco_entity_metric_value",), ("dc_group_swing_signal_daily", "dc_group_synthetic_ohlc_daily"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(8, "build_canonical_v3_ticker_freshness_from_signal_daily", ("eco_entity_metric_value", "eco_signal_observation"), ("dc_ticker_swing_signal_daily",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(9, "build_canonical_v3_daily_trigger_classifications", ("eco_classification_decision",), ("dc_ticker_swing_signal_daily", "dc_group_swing_signal_daily"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(10, "build_canonical_v3_rolling2_sell_pressure_classifications", ("eco_classification_decision",), ("dc_ticker_swing_signal_daily", "dc_group_swing_signal_daily"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(11, "build_canonical_v3_rolling5_pullback_classifications", ("eco_classification_decision",), ("dc_ticker_swing_signal_daily", "dc_group_swing_signal_daily"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(12, "build_canonical_v3_rolling30_watchlist_classifications", ("eco_classification_decision",), ("dc_ticker_swing_signal_daily", "dc_group_swing_signal_daily"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(13, "build_canonical_v3_window_snapshots", ("eco_entity_window_snapshot",), ("dc_ticker_swing_signal_daily", "dc_group_synthetic_ohlc_daily", "eco_entity_coverage", "eco_quality_summary", "eco_classification_decision", "eco_entity_metric_value"), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(14, "build_canonical_v3_ma_status", ("eco_signal_observation",), ("dc_ticker_swing_signal_daily",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(15, "build_canonical_v3_ma_break_status", ("eco_signal_observation",), ("dc_ticker_swing_signal_daily",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(16, "build_canonical_v3_signal_relevance", ("eco_signal_observation", "eco_signal_relevance"), ("technical_signal_relevance",), ("db_path", "run_id", "technical_relevance_run_id", "window_code='daily'", "replace_existing=True")),
    AllowedBuildStep(17, "build_canonical_v3_ticker_structure_events", ("eco_entity_event",), ("stock_dow_structure_events",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(18, "build_canonical_v3_group_structure_events", ("eco_entity_event",), ("dc_group_synthetic_ohlc_daily",), ("db_path", "run_id", "replace_existing=True")),
    AllowedBuildStep(19, "build_canonical_v3_group_freshness_metrics", ("eco_entity_metric_value",), ("eco_entity_event", "eco_entity_metric_value", "eco_entity", "eco_report_run"), ("db_path", "run_id", "replace_existing=True")),
)

BYPASSED_BUILDERS = (
    BypassedBuilder(
        "build_canonical_v3_classification_decisions",
        ("dc_report_classification_v2",),
        (
            "build_canonical_v3_daily_trigger_classifications",
            "build_canonical_v3_rolling2_sell_pressure_classifications",
            "build_canonical_v3_rolling5_pullback_classifications",
            "build_canonical_v3_rolling30_watchlist_classifications",
        ),
    ),
    BypassedBuilder(
        "build_canonical_v3_snapshot_metrics",
        (
            "dc_report_context_daily_v2",
            "dc_report_context_window_v2",
            "dc_report_context_group_v2",
            "dc_report_classification_v2",
        ),
        (
            "build_canonical_v3_ticker_daily_direct_metrics",
            "build_canonical_v3_ticker_window_metrics",
            "build_canonical_v3_group_window_metrics",
            "build_canonical_v3_window_snapshots",
        ),
    ),
    BypassedBuilder(
        "build_canonical_v3_freshness",
        ("dc_report_context_daily_v2", "dc_report_context_window_v2"),
        ("build_canonical_v3_ticker_freshness_from_signal_daily",),
    ),
    BypassedBuilder(
        "build_canonical_v3_group_status_metrics",
        ("dc_report_context_group_v2", "dc_report_context_window_v2"),
        (
            "build_canonical_v3_group_status_from_group_swing",
            "build_canonical_v3_group_window_status_from_group_swing",
            "build_canonical_v3_group_window_metrics",
        ),
    ),
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


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _generate_run_id(ecosystem_code: str, signal_date: str, taxonomy_version_code: str) -> str:
    return f"V3_BASE_{ecosystem_code}_{signal_date.replace('-', '_')}_{taxonomy_version_code}"


def _resolve_ecosystem(conn: sqlite3.Connection, ecosystem_code: str) -> bool:
    row = conn.execute(
        """
        SELECT ecosystem_id
        FROM eco_ecosystem
        WHERE ecosystem_code = ?
        """,
        (ecosystem_code,),
    ).fetchone()
    return row is not None


def _resolve_taxonomy_version(conn: sqlite3.Connection, ecosystem_code: str, taxonomy_version: str) -> bool:
    row = conn.execute(
        """
        SELECT tv.taxonomy_version_id
        FROM eco_taxonomy_version tv
        JOIN eco_ecosystem ee ON ee.ecosystem_id = tv.ecosystem_id
        WHERE ee.ecosystem_code = ? AND tv.version_code = ?
        """,
        (ecosystem_code, taxonomy_version),
    ).fetchone()
    return row is not None


def _query_scalar(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> object:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return row[0]


def _group_concat_run_ids(
    conn: sqlite3.Connection,
    table_name: str,
    date_column: str,
    signal_date: str,
) -> str:
    columns = _column_names(conn, table_name)
    if "run_id" not in columns:
        return ""
    value = _query_scalar(
        conn,
        f"SELECT GROUP_CONCAT(DISTINCT run_id) FROM {table_name} WHERE {date_column} = ?",
        (signal_date,),
    )
    return "" if value is None else str(value)


def _run_ids_for_date(
    conn: sqlite3.Connection,
    table_name: str,
    date_column: str,
    signal_date: str,
) -> list[str]:
    columns = _column_names(conn, table_name)
    if "run_id" not in columns:
        return []
    rows = conn.execute(
        f"""
        SELECT DISTINCT run_id
        FROM {table_name}
        WHERE {date_column} = ?
        ORDER BY run_id
        """,
        (signal_date,),
    ).fetchall()
    return [str(row["run_id"]) for row in rows]


def _latest_date(conn: sqlite3.Connection, table_name: str, date_column: str) -> str:
    value = _query_scalar(conn, f"SELECT MAX({date_column}) FROM {table_name}", ())
    return "" if value is None else str(value)


def _requested_date_count(conn: sqlite3.Connection, spec: SourceReadinessSpec, signal_date: str) -> int:
    if spec.table_name == "stock_dow_structure_events":
        value = _query_scalar(
            conn,
            f"SELECT COUNT(*) FROM {spec.table_name} WHERE {spec.date_column} <= ?",
            (signal_date,),
        )
    else:
        value = _query_scalar(
            conn,
            f"SELECT COUNT(*) FROM {spec.table_name} WHERE {spec.date_column} = ?",
            (signal_date,),
        )
    return int(value or 0)


def _source_status(conn: sqlite3.Connection, spec: SourceReadinessSpec, signal_date: str) -> tuple[str, int, str, str, str]:
    if not table_exists(conn, spec.table_name):
        status = "MISSING" if spec.required else "NOT_REQUIRED_FOR_CURRENT_BUILD"
        return status, 0, "", "", "table missing"

    columns = _column_names(conn, spec.table_name)
    if spec.date_column not in columns:
        status = "BLOCKED_UNCLEAR_SOURCE" if spec.required else "UNCLEAR"
        return status, 0, "", "", f"missing date column {spec.date_column}"

    row_count = _requested_date_count(conn, spec, signal_date)
    latest_date = _latest_date(conn, spec.table_name, spec.date_column)
    run_ids = _group_concat_run_ids(conn, spec.table_name, spec.date_column, signal_date)

    if not spec.required:
        return "NOT_REQUIRED_FOR_CURRENT_BUILD", row_count, latest_date, run_ids, spec.note
    if row_count > 0:
        return "READY", row_count, latest_date, run_ids, spec.note
    return "MISSING", row_count, latest_date, run_ids, spec.note


def _detect_dashboard_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name LIKE 'dc_dashboard_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def _forbidden_rows_for_date(conn: sqlite3.Connection, table_name: str, signal_date: str) -> tuple[str, int]:
    if not table_exists(conn, table_name):
        return "", 0
    columns = _column_names(conn, table_name)
    for date_column in ("signal_date", "index_date", "ohlc_date", "event_date"):
        if date_column in columns:
            count = int(
                _query_scalar(
                    conn,
                    f"SELECT COUNT(*) FROM {table_name} WHERE {date_column} = ?",
                    (signal_date,),
                )
                or 0
            )
            return date_column, count
    return "", 0


def _forbidden_replacement_builder(table_name: str) -> str:
    replacements = {
        "dc_report_context_daily_v2": "build_canonical_v3_ticker_freshness_from_signal_daily",
        "dc_report_context_window_v2": "build_canonical_v3_window_snapshots / build_canonical_v3_group_window_metrics",
        "dc_report_context_group_v2": "build_canonical_v3_group_status_from_group_swing / build_canonical_v3_group_window_status_from_group_swing",
        "dc_report_classification_v2": "replacement classification builders",
    }
    return replacements.get(table_name, "")


def _render_plan_header(db_path: str, ecosystem: str, taxonomy_version: str, signal_date: str, run_id: str) -> list[str]:
    return [
        "V3 Latest-Date Build Plan",
        f"db_path: {Path(db_path).resolve()}",
        f"ecosystem: {ecosystem}",
        f"taxonomy_version: {taxonomy_version}",
        f"signal_date: {signal_date}",
        f"planned_run_id: {run_id}",
    ]


def _render_source_readiness(
    conn: sqlite3.Connection,
    signal_date: str,
) -> tuple[list[str], str]:
    lines = [
        "Source Readiness",
        "table_name | status | row_count | latest_date | source_run_ids | note",
    ]
    statuses: list[str] = []
    for spec in ALLOWED_SOURCE_SPECS:
        status, row_count, latest_date, run_ids, note = _source_status(conn, spec, signal_date)
        statuses.append(status)
        lines.append(
            f"{spec.table_name} | {status} | {row_count} | {latest_date} | {run_ids} | date_column={spec.date_column}; {note}"
        )

    if any(status == "MISSING" for status in statuses):
        plan_status = "BLOCKED_MISSING_SOURCE"
    elif any(status in {"UNCLEAR", "BLOCKED_UNCLEAR_SOURCE"} for status in statuses):
        plan_status = "BLOCKED_UNCLEAR_SOURCE"
    else:
        plan_status = "READY_NO_WRITE_PLAN"
    return lines, plan_status


def _render_forbidden_sources(conn: sqlite3.Connection, signal_date: str) -> list[str]:
    lines = [
        "Forbidden Source Check",
        "table_name | exists | rows_for_requested_date | status | replacement_builder",
    ]
    table_names = list(FIXED_FORBIDDEN_TABLES) + _detect_dashboard_tables(conn)
    for table_name in sorted(dict.fromkeys(table_names)):
        exists = table_exists(conn, table_name)
        date_column, row_count = _forbidden_rows_for_date(conn, table_name, signal_date)
        note = _forbidden_replacement_builder(table_name)
        if not date_column and exists:
            rows_text = "n/a"
        else:
            rows_text = str(row_count)
        suffix = f"; date_column={date_column}" if date_column else ""
        lines.append(
            f"{table_name} | {'yes' if exists else 'no'} | {rows_text} | FORBIDDEN_BYPASS | {note}{suffix}"
        )
    return lines


def _resolve_technical_relevance_run_id(
    conn: sqlite3.Connection,
    *,
    ecosystem: str,
    taxonomy_version: str,
    signal_date: str,
) -> str:
    table_name = "technical_signal_relevance"
    if not table_exists(conn, table_name):
        return "technical_relevance_run_id=<SELECT_FROM_READY_TECHNICAL_SIGNAL_RELEVANCE_RUN_IDS>"
    run_ids = _run_ids_for_date(conn, table_name, "signal_date", signal_date)
    preferred = f"{ecosystem}_TECH_REL_{taxonomy_version}_{signal_date.replace('-', '_')}"
    preferred_matches = [run_id for run_id in run_ids if run_id == preferred]
    if len(preferred_matches) == 1:
        return f"technical_relevance_run_id={preferred_matches[0]}"
    return "technical_relevance_run_id=<SELECT_FROM_READY_TECHNICAL_SIGNAL_RELEVANCE_RUN_IDS>"


def _format_required_parameters(
    step: AllowedBuildStep,
    *,
    run_id: str,
    technical_relevance_parameter: str,
) -> str:
    rendered: list[str] = []
    for parameter in step.required_parameters:
        if parameter == "run_id":
            rendered.append(f"run_id={run_id}")
        elif parameter == "technical_relevance_run_id":
            rendered.append(technical_relevance_parameter)
        else:
            rendered.append(parameter)
    return ", ".join(rendered)


def _render_allowed_build_sequence(
    conn: sqlite3.Connection,
    *,
    ecosystem: str,
    taxonomy_version: str,
    signal_date: str,
    run_id: str,
) -> list[str]:
    lines = [
        "Allowed Build Sequence",
        "step | function_name | target_tables | source_tables | status | required_parameters | note",
    ]
    technical_relevance_parameter = _resolve_technical_relevance_run_id(
        conn,
        ecosystem=ecosystem,
        taxonomy_version=taxonomy_version,
        signal_date=signal_date,
    )
    for step in ALLOWED_BUILD_STEPS:
        lines.append(
            f"{step.step_number} | {step.function_name} | {', '.join(step.target_tables)} | "
            f"{', '.join(step.source_tables)} | PLANNED_ALLOWED_SOURCE | "
            f"{_format_required_parameters(step, run_id=run_id, technical_relevance_parameter=technical_relevance_parameter)} | not executed"
        )
    return lines


def _render_bypassed_builders() -> list[str]:
    lines = [
        "Bypassed Builders",
        "function_name | forbidden_source_tables | replacement_builders | status",
    ]
    for builder in BYPASSED_BUILDERS:
        lines.append(
            f"{builder.function_name} | {', '.join(builder.forbidden_sources)} | "
            f"{', '.join(builder.replacement_builders)} | BYPASS_FOR_LATEST_DATE"
        )
    return lines


def _render_plan_status(plan_status: str, ecosystem_exists: bool, taxonomy_exists: bool) -> list[str]:
    final_status = plan_status
    if not ecosystem_exists or not taxonomy_exists:
        final_status = "BLOCKED_UNCLEAR_SOURCE"
    lines = [
        "Plan Status",
        f"status: {final_status}",
        f"ecosystem_resolved: {'yes' if ecosystem_exists else 'no'}",
        f"taxonomy_version_resolved: {'yes' if taxonomy_exists else 'no'}",
        "No builders executed.",
        "No DB writes performed.",
    ]
    return lines


def render_text_plan(
    conn: sqlite3.Connection,
    *,
    db_path: str,
    ecosystem: str,
    taxonomy_version: str,
    signal_date: str,
    run_id: str,
) -> str:
    ecosystem_exists = _resolve_ecosystem(conn, ecosystem)
    taxonomy_exists = _resolve_taxonomy_version(conn, ecosystem, taxonomy_version)
    source_lines, plan_status = _render_source_readiness(conn, signal_date)
    sections = [
        *_render_plan_header(db_path, ecosystem, taxonomy_version, signal_date, run_id),
        "",
        *source_lines,
        "",
        *_render_forbidden_sources(conn, signal_date),
        "",
        *_render_allowed_build_sequence(
            conn,
            ecosystem=ecosystem,
            taxonomy_version=taxonomy_version,
            signal_date=signal_date,
            run_id=run_id,
        ),
        "",
        *_render_bypassed_builders(),
        "",
        *_render_plan_status(plan_status, ecosystem_exists, taxonomy_exists),
    ]
    return "\n".join(sections) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a no-write Canonical V3 latest-date Eco build")
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect")
    parser.add_argument("--ecosystem", required=True, help="Eco ecosystem_code")
    parser.add_argument("--taxonomy-version", required=True, help="Eco taxonomy version_code")
    parser.add_argument("--signal-date", required=True, help="Target signal_date in YYYY-MM-DD format")
    parser.add_argument("--run-id", help="Optional explicit planned run_id")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_id = args.run_id or _generate_run_id(args.ecosystem, args.signal_date, args.taxonomy_version)

    try:
        with open_readonly_sqlite(args.db) as conn:
            if args.format == "text":
                print(
                    render_text_plan(
                        conn,
                        db_path=args.db,
                        ecosystem=args.ecosystem,
                        taxonomy_version=args.taxonomy_version,
                        signal_date=args.signal_date,
                        run_id=run_id,
                    )
                )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
