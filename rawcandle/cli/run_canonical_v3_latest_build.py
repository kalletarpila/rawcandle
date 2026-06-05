from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable

from rawcandle.cli import plan_canonical_v3_latest_build as planner
from rawcandle.report_canonical_v3_base_builder import build_canonical_v3_base_run
from rawcandle.report_canonical_v3_daily_classification_replacement_builder import (
    build_canonical_v3_daily_trigger_classifications,
)
from rawcandle.report_canonical_v3_entity_event_builder import (
    build_canonical_v3_ticker_structure_events,
)
from rawcandle.report_canonical_v3_group_event_builder import (
    build_canonical_v3_group_structure_events,
)
from rawcandle.report_canonical_v3_group_historical_metric_builder import (
    build_canonical_v3_group_historical_metrics,
)
from rawcandle.report_canonical_v3_group_status_replacement_builder import (
    build_canonical_v3_group_status_from_group_swing,
)
from rawcandle.report_canonical_v3_group_window_metric_replacement_builder import (
    build_canonical_v3_group_window_metrics,
)
from rawcandle.report_canonical_v3_group_window_status_replacement_builder import (
    build_canonical_v3_group_window_status_from_group_swing,
)
from rawcandle.report_canonical_v3_ma_break_status_builder import (
    build_canonical_v3_ma_break_status,
)
from rawcandle.report_canonical_v3_ma_status_builder import build_canonical_v3_ma_status
from rawcandle.report_canonical_v3_rolling2_classification_replacement_builder import (
    build_canonical_v3_rolling2_sell_pressure_classifications,
)
from rawcandle.report_canonical_v3_rolling30_classification_replacement_builder import (
    build_canonical_v3_rolling30_watchlist_classifications,
)
from rawcandle.report_canonical_v3_rolling5_classification_replacement_builder import (
    build_canonical_v3_rolling5_pullback_classifications,
)
from rawcandle.report_canonical_v3_signal_relevance_builder import (
    build_canonical_v3_signal_relevance,
)
from rawcandle.report_canonical_v3_ticker_daily_metric_replacement_builder import (
    build_canonical_v3_ticker_daily_direct_metrics,
)
from rawcandle.report_canonical_v3_ticker_freshness_replacement_builder import (
    build_canonical_v3_ticker_freshness_from_signal_daily,
)
from rawcandle.report_canonical_v3_ticker_window_metric_replacement_builder import (
    build_canonical_v3_ticker_window_metrics,
)
from rawcandle.report_canonical_v3_window_snapshot_replacement_builder import (
    build_canonical_v3_window_snapshots,
)


FORBIDDEN_BUILDERS = (
    "build_canonical_v3_classification_decisions",
    "build_canonical_v3_snapshot_metrics",
    "build_canonical_v3_freshness",
    "build_canonical_v3_group_status_metrics",
)

TARGET_TABLES_BY_VALIDATION = (
    "eco_report_run",
    "eco_entity_coverage",
    "eco_quality_summary",
    "eco_entity_window_snapshot",
    "eco_entity_metric_value",
    "eco_classification_decision",
    "eco_signal_observation",
    "eco_signal_relevance",
    "eco_entity_event",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run guarded Canonical V3 latest-date Eco build using allowed-source builders only."
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database")
    parser.add_argument("--ecosystem", required=True, help="Eco ecosystem_code")
    parser.add_argument("--taxonomy-version", required=True, help="Eco taxonomy version_code")
    parser.add_argument("--signal-date", required=True, help="Target signal_date in YYYY-MM-DD format")
    parser.add_argument("--run-id", required=True, help="Explicit Eco run_id")
    parser.add_argument("--confirm-run-id", required=True, help="Must exactly equal --run-id before any write")
    parser.add_argument("--backup-dir", required=True, help="Existing writable directory for pre-write DB backup")
    parser.add_argument("--replace-existing", action="store_true", help="Allow replacing an existing target run")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def _backup_filename(db_path: str, run_id: str) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_base = Path(db_path).stem
    return f"{db_base}__{run_id}__{timestamp}.sqlite"


def _ensure_backup_dir(backup_dir: str) -> Path:
    path = Path(backup_dir).resolve()
    if not path.exists():
        raise ValueError(f"backup_dir does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"backup_dir is not a directory: {path}")
    if not os.access(path, os.W_OK):
        raise ValueError(f"backup_dir is not writable: {path}")
    return path


def _create_backup(db_path: str, backup_dir: Path, run_id: str) -> Path:
    backup_path = backup_dir / _backup_filename(db_path, run_id)
    source = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(backup_path))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return backup_path


def _open_rw_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _existing_run_exists(db_path: str, run_id: str) -> bool:
    conn = _open_rw_sqlite(db_path)
    try:
        if not planner.table_exists(conn, "eco_report_run"):
            return False
        row = conn.execute(
            "SELECT 1 FROM eco_report_run WHERE run_id = ? LIMIT 1",
            (run_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _evaluate_planner_status(
    db_path: str,
    ecosystem: str,
    taxonomy_version: str,
    signal_date: str,
) -> str:
    with planner.open_readonly_sqlite(db_path) as conn:
        ecosystem_exists = planner._resolve_ecosystem(conn, ecosystem)
        taxonomy_exists = planner._resolve_taxonomy_version(conn, ecosystem, taxonomy_version)
        _, source_status = planner._render_source_readiness(conn, signal_date)
        if not ecosystem_exists or not taxonomy_exists:
            return "BLOCKED_UNCLEAR_SOURCE"
        return source_status


def _resolve_deterministic_technical_relevance_run_id(
    db_path: str,
    ecosystem: str,
    taxonomy_version: str,
    signal_date: str,
) -> str:
    with planner.open_readonly_sqlite(db_path) as conn:
        resolved = planner._resolve_technical_relevance_run_id(
            conn,
            ecosystem=ecosystem,
            taxonomy_version=taxonomy_version,
            signal_date=signal_date,
        )
    if "<SELECT_FROM_READY_TECHNICAL_SIGNAL_RELEVANCE_RUN_IDS>" in resolved:
        raise ValueError("deterministic technical_relevance_run_id could not be resolved")
    if not resolved.startswith("technical_relevance_run_id="):
        raise ValueError("unexpected technical_relevance_run_id rendering")
    return resolved.split("=", 1)[1]


def _builder_sequence() -> list[tuple[str, Callable[..., dict[str, object]], dict[str, object]]]:
    return [
        (
            "build_canonical_v3_base_run",
            build_canonical_v3_base_run,
            {},
        ),
        ("build_canonical_v3_ticker_daily_direct_metrics", build_canonical_v3_ticker_daily_direct_metrics, {}),
        ("build_canonical_v3_group_status_from_group_swing", build_canonical_v3_group_status_from_group_swing, {}),
        ("build_canonical_v3_group_window_status_from_group_swing", build_canonical_v3_group_window_status_from_group_swing, {}),
        ("build_canonical_v3_ticker_window_metrics", build_canonical_v3_ticker_window_metrics, {}),
        ("build_canonical_v3_group_window_metrics", build_canonical_v3_group_window_metrics, {}),
        ("build_canonical_v3_group_historical_metrics", build_canonical_v3_group_historical_metrics, {}),
        ("build_canonical_v3_ticker_freshness_from_signal_daily", build_canonical_v3_ticker_freshness_from_signal_daily, {}),
        ("build_canonical_v3_daily_trigger_classifications", build_canonical_v3_daily_trigger_classifications, {}),
        ("build_canonical_v3_rolling2_sell_pressure_classifications", build_canonical_v3_rolling2_sell_pressure_classifications, {}),
        ("build_canonical_v3_rolling5_pullback_classifications", build_canonical_v3_rolling5_pullback_classifications, {}),
        ("build_canonical_v3_rolling30_watchlist_classifications", build_canonical_v3_rolling30_watchlist_classifications, {}),
        ("build_canonical_v3_window_snapshots", build_canonical_v3_window_snapshots, {}),
        ("build_canonical_v3_ma_status", build_canonical_v3_ma_status, {}),
        ("build_canonical_v3_ma_break_status", build_canonical_v3_ma_break_status, {}),
        ("build_canonical_v3_signal_relevance", build_canonical_v3_signal_relevance, {"window_code": "daily"}),
        ("build_canonical_v3_ticker_structure_events", build_canonical_v3_ticker_structure_events, {}),
        ("build_canonical_v3_group_structure_events", build_canonical_v3_group_structure_events, {}),
    ]


def _validate_forbidden_builder_sequence(sequence: list[tuple[str, Callable[..., dict[str, object]], dict[str, object]]]) -> None:
    builder_names = [name for name, _, _ in sequence]
    for forbidden_name in FORBIDDEN_BUILDERS:
        if forbidden_name in builder_names:
            raise ValueError(f"forbidden builder present in execution sequence: {forbidden_name}")


def _count_target_rows_for_run(conn: sqlite3.Connection, table_name: str, run_id: str) -> int:
    if table_name == "eco_signal_relevance":
        if not planner.table_exists(conn, "eco_signal_relevance") or not planner.table_exists(conn, "eco_signal_observation"):
            return 0
        return int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM eco_signal_relevance sr
                JOIN eco_signal_observation so
                  ON so.signal_observation_id = sr.signal_observation_id
                WHERE so.run_id = ?
                """,
                (run_id,),
            ).fetchone()[0]
        )
    if not planner.table_exists(conn, table_name):
        return 0
    columns = planner._column_names(conn, table_name)
    if "run_id" not in columns:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name} WHERE run_id = ?", (run_id,)).fetchone()[0])


def _count_forbidden_lineage_rows(conn: sqlite3.Connection, table_name: str, run_id: str) -> int:
    if not planner.table_exists(conn, table_name):
        return 0
    columns = planner._column_names(conn, table_name)
    if "run_id" not in columns:
        return 0

    predicates: list[str] = []
    params: list[object] = [run_id]
    if "source_table" in columns:
        predicates.append("(source_table LIKE 'dc_report_%_v2' OR source_table LIKE 'dc_dashboard_%' OR source_table LIKE 'dc_%_v2')")
    if "source_run_id" in columns:
        predicates.append("(source_run_id LIKE 'dc_report_%_v2' OR source_run_id LIKE 'dc_dashboard_%' OR source_run_id LIKE 'dc_%_v2')")
    if not predicates:
        return 0
    where_clause = " OR ".join(predicates)
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE run_id = ? AND ({where_clause})",
            tuple(params),
        ).fetchone()[0]
    )


def _validate_post_build(db_path: str, run_id: str, signal_date: str) -> dict[str, object]:
    conn = _open_rw_sqlite(db_path)
    try:
        table_counts = {
            table_name: _count_target_rows_for_run(conn, table_name, run_id)
            for table_name in TARGET_TABLES_BY_VALIDATION
        }
        forbidden_lineage_counts = {
            table_name: _count_forbidden_lineage_rows(conn, table_name, run_id)
            for table_name in (
                "eco_entity_window_snapshot",
                "eco_entity_metric_value",
                "eco_classification_decision",
                "eco_signal_observation",
                "eco_entity_event",
            )
        }
        latest_eco_signal_date = ""
        if planner.table_exists(conn, "eco_report_run"):
            latest = conn.execute("SELECT MAX(signal_date) FROM eco_report_run").fetchone()[0]
            latest_eco_signal_date = "" if latest is None else str(latest)
    finally:
        conn.close()

    return {
        "run_exists": table_counts["eco_report_run"] > 0,
        "table_counts": table_counts,
        "forbidden_lineage_counts": forbidden_lineage_counts,
        "latest_eco_signal_date": latest_eco_signal_date,
        "latest_signal_date_ok": latest_eco_signal_date >= signal_date if latest_eco_signal_date else False,
    }


def _append_section(lines: list[str], title: str, body_lines: list[str]) -> None:
    if lines:
        lines.append("")
    lines.append(title)
    lines.extend(body_lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    lines: list[str] = ["V3 Latest-Date Build"]
    lines.append(f"db_path: {Path(args.db).resolve()}")
    lines.append(f"ecosystem: {args.ecosystem}")
    lines.append(f"taxonomy_version: {args.taxonomy_version}")
    lines.append(f"signal_date: {args.signal_date}")
    lines.append(f"run_id: {args.run_id}")

    completed_steps: list[str] = []
    backup_path: Path | None = None
    execution_started = False
    active_step_name = ""

    try:
        safety_lines: list[str] = []
        if args.confirm_run_id != args.run_id:
            raise ValueError("confirm_run_id must exactly equal run_id")
        safety_lines.append("confirmation_gate: OK")

        backup_dir = _ensure_backup_dir(args.backup_dir)
        safety_lines.append(f"backup_dir_gate: OK ({backup_dir})")

        planner_status = _evaluate_planner_status(
            args.db,
            args.ecosystem,
            args.taxonomy_version,
            args.signal_date,
        )
        safety_lines.append(f"planner_status: {planner_status}")
        if planner_status != "READY_NO_WRITE_PLAN":
            raise ValueError(f"planner readiness blocked: {planner_status}")

        technical_relevance_run_id = _resolve_deterministic_technical_relevance_run_id(
            args.db,
            args.ecosystem,
            args.taxonomy_version,
            args.signal_date,
        )
        safety_lines.append(f"technical_relevance_run_id: {technical_relevance_run_id}")

        sequence = _builder_sequence()
        _validate_forbidden_builder_sequence(sequence)
        safety_lines.append("forbidden_builder_gate: OK")

        existing_run = _existing_run_exists(args.db, args.run_id)
        if existing_run and not args.replace_existing:
            raise ValueError("target run already exists and --replace-existing was not provided")
        safety_lines.append(
            f"existing_run_gate: {'OK_REPLACE' if existing_run and args.replace_existing else 'OK'}"
        )
        _append_section(lines, "Safety Gates", safety_lines)

        backup_path = _create_backup(args.db, backup_dir, args.run_id)
        _append_section(
            lines,
            "Backup",
            [
                "backup_status: OK",
                f"backup_path: {backup_path}",
            ],
        )

        execution_lines: list[str] = []
        for step_number, (builder_name, builder_fn, extra_kwargs) in enumerate(sequence, start=1):
            execution_started = True
            active_step_name = builder_name
            kwargs: dict[str, object]
            if builder_name == "build_canonical_v3_base_run":
                kwargs = {
                    "db_path": args.db,
                    "ecosystem_code": args.ecosystem,
                    "signal_date": args.signal_date,
                    "taxonomy_version_code": args.taxonomy_version,
                    "run_id": args.run_id,
                    "replace_run": args.replace_existing,
                }
            elif builder_name == "build_canonical_v3_signal_relevance":
                kwargs = {
                    "db_path": args.db,
                    "run_id": args.run_id,
                    "technical_relevance_run_id": technical_relevance_run_id,
                    "window_code": "daily",
                    "replace_existing": args.replace_existing,
                }
            else:
                kwargs = {
                    "db_path": args.db,
                    "run_id": args.run_id,
                    "replace_existing": args.replace_existing,
                }
            kwargs.update(extra_kwargs)
            summary = builder_fn(**kwargs)
            completed_steps.append(builder_name)
            execution_lines.append(
                f"{step_number}. {builder_name}: OK"
            )
            if isinstance(summary, dict) and "warning_count" in summary:
                execution_lines.append(f"   warning_count={summary['warning_count']}")
        _append_section(lines, "Builder Execution", execution_lines)

        validation = _validate_post_build(args.db, args.run_id, args.signal_date)
        validation_lines = [
            f"run_exists: {validation['run_exists']}",
            f"latest_eco_signal_date: {validation['latest_eco_signal_date']}",
            f"latest_signal_date_ok: {validation['latest_signal_date_ok']}",
        ]
        for table_name, count_value in validation["table_counts"].items():
            validation_lines.append(f"{table_name}_rows: {count_value}")
        for table_name, count_value in validation["forbidden_lineage_counts"].items():
            validation_lines.append(f"{table_name}_forbidden_lineage_rows: {count_value}")
        _append_section(lines, "Post-Build Validation", validation_lines)

        if not validation["run_exists"]:
            raise RuntimeError("post-build validation failed: target eco_report_run row is missing")
        if not validation["latest_signal_date_ok"]:
            raise RuntimeError("post-build validation failed: latest Eco signal date did not reach the requested signal date")
        forbidden_total = sum(int(value) for value in validation["forbidden_lineage_counts"].values())
        if forbidden_total != 0:
            raise RuntimeError("post-build validation failed: forbidden V2/dashboard lineage was detected")

        _append_section(lines, "Build Status", ["status: BUILD_COMPLETED"])
        print("\n".join(lines))
        return 0
    except Exception as exc:
        if backup_path is not None or execution_started:
            failure_lines = []
            if completed_steps:
                failure_lines.append(f"completed_steps: {', '.join(completed_steps)}")
            if active_step_name and (not completed_steps or completed_steps[-1] != active_step_name):
                failure_lines.append(f"failed_step: {active_step_name}")
            if failure_lines:
                _append_section(lines, "Builder Execution", failure_lines)
            _append_section(
                lines,
                "Build Status",
                [
                    "status: BUILD_FAILED",
                    f"error: {exc}",
                    f"backup_path: {backup_path}" if backup_path is not None else "backup_path: NONE",
                    "partial_writes_may_exist: restore from backup may be required",
                ],
            )
        else:
            _append_section(
                lines,
                "Build Status",
                [
                    "status: BUILD_REFUSED",
                    f"error: {exc}",
                ],
            )
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
