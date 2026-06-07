from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

from rawcandle.cli.plan_ec_source_layer_build import plan_ec_source_layer_build
from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_datacenter_watchlist_loader import load_datacenter_watchlist_to_ec_sidecar
from rawcandle.ec_dc_coverage_audit import audit_dc_facts_against_ec_sidecar
from rawcandle.ec_dc_fact_parity_audit import audit_dc_ec_fact_parity
from rawcandle.ec_group_index_daily_loader import load_ec_group_index_daily_from_dc
from rawcandle.ec_group_signal_daily_loader import load_ec_group_signal_daily_from_dc
from rawcandle.ec_group_synthetic_ohlc_daily_loader import load_ec_group_synthetic_ohlc_daily_from_dc
from rawcandle.ec_pipeline_watermark_loader import load_ec_pipeline_watermark_from_dc
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration
from rawcandle.ec_ticker_signal_daily_loader import load_ec_ticker_signal_daily_from_dc


SUCCESS_PARITY_STATUSES = {"OK", "OK_WITH_WARNINGS"}
SUCCESS_COVERAGE_STATUSES = {"OK", "OK_WITH_WARNINGS"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a guarded ec_ source-layer build into a SQLite database")
    parser.add_argument("--db", required=True, help="Path to the target SQLite database")
    parser.add_argument("--ecosystem", required=True, help="Target ecosystem code")
    parser.add_argument("--taxonomy-version", required=True, help="Target taxonomy version code")
    parser.add_argument("--taxonomy-csv", required=True, help="Path to taxonomy CSV")
    parser.add_argument("--watchlist", required=True, help="Path to watchlist TXT")
    parser.add_argument("--backup-dir", required=True, help="Existing writable directory for pre-write backups")
    parser.add_argument("--confirm-db", required=True, help="Must exactly match --db before any write")
    parser.add_argument("--confirm-ecosystem", required=True, help="Must exactly match --ecosystem before any write")
    parser.add_argument(
        "--confirm-taxonomy-version",
        required=True,
        help="Must exactly match --taxonomy-version before any write",
    )
    parser.add_argument("--signal-date", help="Optional explicit signal date in YYYY-MM-DD format")
    parser.add_argument("--replace-existing", action="store_true", help="Accepted by parser; replacement is still gated by planner and loader capabilities")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def _backup_filename(db_path: str, ecosystem_code: str, taxonomy_version_code: str) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_base = Path(db_path).stem
    return f"{db_base}__ec_source_layer__{ecosystem_code}__{taxonomy_version_code}__{timestamp}.sqlite"


def _ensure_backup_dir(backup_dir: str) -> Path:
    path = Path(backup_dir).resolve()
    if not path.exists():
        raise ValueError(f"backup_dir does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"backup_dir is not a directory: {path}")
    if not os.access(path, os.W_OK):
        raise ValueError(f"backup_dir is not writable: {path}")
    return path


def _create_backup(db_path: str, backup_dir: Path, ecosystem_code: str, taxonomy_version_code: str) -> Path:
    backup_path = backup_dir / _backup_filename(db_path, ecosystem_code, taxonomy_version_code)
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


def _collect_ec_row_counts(db_path: str) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name GLOB 'ec_*'
            ORDER BY name
            """
        ).fetchall()
        counts: dict[str, int] = {}
        for (table_name,) in rows:
            counts[str(table_name)] = int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
        return counts
    finally:
        conn.close()


def _build_refused_summary(
    *,
    errors: list[str],
    planner_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "status": "BUILD_REFUSED",
        "errors": errors,
        "planner_summary": planner_summary,
        "backup_path": None,
        "completed_steps": [],
        "failed_step": None,
    }


def _run_loader_step(
    *,
    step_name: str,
    completed_steps: list[str],
    fn,
    kwargs: dict[str, object],
) -> dict[str, object]:
    summary = fn(**kwargs)
    completed_steps.append(step_name)
    return summary


def run_ec_source_layer_build(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    backup_dir: str,
    confirm_db: str,
    confirm_ecosystem: str,
    confirm_taxonomy_version: str,
    signal_date: str | None = None,
    replace_existing: bool = False,
) -> dict[str, object]:
    gate_errors: list[str] = []
    if confirm_db != db_path:
        gate_errors.append("--confirm-db must exactly match --db")
    if confirm_ecosystem != ecosystem_code:
        gate_errors.append("--confirm-ecosystem must exactly match --ecosystem")
    if confirm_taxonomy_version != taxonomy_version_code:
        gate_errors.append("--confirm-taxonomy-version must exactly match --taxonomy-version")

    try:
        resolved_backup_dir = _ensure_backup_dir(backup_dir)
    except Exception as exc:
        gate_errors.append(str(exc))
        resolved_backup_dir = None

    planner_summary = plan_ec_source_layer_build(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        taxonomy_csv_path=taxonomy_csv_path,
        watchlist_path=watchlist_path,
        signal_date=signal_date,
    )

    if planner_summary.get("status") != "READY_NO_WRITE_PLAN":
        gate_errors.append(
            "planner gate did not pass: "
            f"{planner_summary.get('status')}"
        )

    if gate_errors:
        return _build_refused_summary(errors=gate_errors, planner_summary=planner_summary)

    assert resolved_backup_dir is not None
    try:
        backup_path = _create_backup(
            db_path=db_path,
            backup_dir=resolved_backup_dir,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
        )
    except Exception as exc:
        return {
            "status": "BUILD_FAILED_BEFORE_WRITE",
            "errors": [str(exc)],
            "planner_summary": planner_summary,
            "backup_path": None,
            "completed_steps": [],
            "failed_step": "backup",
        }

    selected_date_info = planner_summary.get("selected_date_info", {})
    assert isinstance(selected_date_info, dict)
    selected_signal_date = signal_date or selected_date_info.get("selected_signal_date")
    completed_steps: list[str] = []

    try:
        apply_ec_sidecar_migration(db_path)
        completed_steps.append("apply_ec_sidecar_migration")

        taxonomy_summary = _run_loader_step(
            step_name="load_datacenter_taxonomy_to_ec_sidecar",
            completed_steps=completed_steps,
            fn=load_datacenter_taxonomy_to_ec_sidecar,
            kwargs={
                "db_path": db_path,
                "taxonomy_csv_path": taxonomy_csv_path,
                "taxonomy_version_code": taxonomy_version_code,
                "ecosystem_code": ecosystem_code,
                "replace_existing": False,
            },
        )

        watchlist_summary = _run_loader_step(
            step_name="load_datacenter_watchlist_to_ec_sidecar",
            completed_steps=completed_steps,
            fn=load_datacenter_watchlist_to_ec_sidecar,
            kwargs={
                "db_path": db_path,
                "watchlist_path": watchlist_path,
                "ecosystem_code": ecosystem_code,
                "replace_existing": False,
            },
        )

        ticker_summary = _run_loader_step(
            step_name="load_ec_ticker_signal_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_ticker_signal_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": replace_existing,
            },
        )
        if ticker_summary.get("status") == "FAILED":
            raise RuntimeError("Ticker fact loader returned FAILED")

        group_signal_summary = _run_loader_step(
            step_name="load_ec_group_signal_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_group_signal_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": replace_existing,
            },
        )
        if group_signal_summary.get("status") == "FAILED":
            raise RuntimeError("Group signal fact loader returned FAILED")

        synthetic_summary = _run_loader_step(
            step_name="load_ec_group_synthetic_ohlc_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_group_synthetic_ohlc_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": replace_existing,
            },
        )
        if synthetic_summary.get("status") == "FAILED":
            raise RuntimeError("Synthetic OHLC fact loader returned FAILED")

        group_index_summary = _run_loader_step(
            step_name="load_ec_group_index_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_group_index_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": replace_existing,
            },
        )
        if group_index_summary.get("status") == "FAILED":
            raise RuntimeError("Group index fact loader returned FAILED")

        pipeline_watermark_summary = _run_loader_step(
            step_name="load_ec_pipeline_watermark_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_pipeline_watermark_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "replace_existing": replace_existing,
            },
        )
        if pipeline_watermark_summary.get("status") == "FAILED":
            raise RuntimeError("Pipeline watermark loader returned FAILED")

        coverage_audit_summary = _run_loader_step(
            step_name="audit_dc_facts_against_ec_sidecar",
            completed_steps=completed_steps,
            fn=audit_dc_facts_against_ec_sidecar,
            kwargs={
                "analysis_db_path": db_path,
                "ec_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
            },
        )
        if coverage_audit_summary.get("status") not in SUCCESS_COVERAGE_STATUSES:
            raise RuntimeError(
                "Coverage audit returned non-success status: "
                f"{coverage_audit_summary.get('status')}"
            )

        parity_audit_summary = _run_loader_step(
            step_name="audit_dc_ec_fact_parity",
            completed_steps=completed_steps,
            fn=audit_dc_ec_fact_parity,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
            },
        )
        parity_status = parity_audit_summary.get("status")
        total_mismatch_count = int(parity_audit_summary.get("total_mismatch_count", 0))
        if parity_status not in SUCCESS_PARITY_STATUSES or total_mismatch_count != 0:
            raise RuntimeError(
                "Fact parity audit did not meet acceptance criteria: "
                f"status={parity_status}, total_mismatch_count={total_mismatch_count}"
            )

        return {
            "status": "BUILD_COMPLETED",
            "planner_summary": planner_summary,
            "backup_path": str(backup_path),
            "selected_signal_date": selected_signal_date,
            "completed_steps": completed_steps,
            "failed_step": None,
            "taxonomy_summary": taxonomy_summary,
            "watchlist_summary": watchlist_summary,
            "ticker_summary": ticker_summary,
            "group_signal_summary": group_signal_summary,
            "synthetic_summary": synthetic_summary,
            "group_index_summary": group_index_summary,
            "pipeline_watermark_summary": pipeline_watermark_summary,
            "coverage_audit_summary": coverage_audit_summary,
            "parity_audit_summary": parity_audit_summary,
            "final_row_counts": _collect_ec_row_counts(db_path),
        }
    except Exception as exc:
        return {
            "status": "BUILD_FAILED",
            "errors": [str(exc)],
            "planner_summary": planner_summary,
            "backup_path": str(backup_path),
            "selected_signal_date": selected_signal_date,
            "completed_steps": completed_steps,
            "failed_step": completed_steps[-1] if completed_steps else "apply_ec_sidecar_migration",
            "warning": "Partial ec_ writes may exist; no automatic rollback was attempted",
        }


def render_build_text(summary: dict[str, object]) -> str:
    lines = [
        "EC Source Layer Build",
        f"Build Status: {summary.get('status')}",
        "",
        "Safety Gates",
    ]
    if summary.get("status") == "BUILD_REFUSED":
        for error in summary.get("errors", []):
            lines.append(f"- {error}")
    else:
        lines.append("- confirm-db matched --db")
        lines.append("- confirm-ecosystem matched --ecosystem")
        lines.append("- confirm-taxonomy-version matched --taxonomy-version")

    planner_summary = summary.get("planner_summary")
    lines.extend(["", "Planner Result"])
    if isinstance(planner_summary, dict):
        lines.append(f"- planner_status={planner_summary.get('status')}")
        selected_date_info = planner_summary.get("selected_date_info")
        if isinstance(selected_date_info, dict):
            lines.append(f"- selected_signal_date={selected_date_info.get('selected_signal_date')}")

    lines.extend(["", "Backup"])
    lines.append(f"- backup_path={summary.get('backup_path')}")

    lines.extend(["", "Build Steps"])
    completed_steps = summary.get("completed_steps", [])
    for step in completed_steps:
        lines.append(f"- completed: {step}")
    failed_step = summary.get("failed_step")
    if failed_step:
        lines.append(f"- failed_step={failed_step}")

    lines.extend(["", "Loader Summaries"])
    for key in (
        "taxonomy_summary",
        "watchlist_summary",
        "ticker_summary",
        "group_signal_summary",
        "synthetic_summary",
        "group_index_summary",
        "pipeline_watermark_summary",
    ):
        section = summary.get(key)
        if isinstance(section, dict):
            lines.append(f"- {key} status={section.get('status')}")

    lines.extend(["", "Coverage Audit"])
    coverage_audit_summary = summary.get("coverage_audit_summary")
    if isinstance(coverage_audit_summary, dict):
        lines.append(f"- status={coverage_audit_summary.get('status')}")

    lines.extend(["", "Fact Parity Audit"])
    parity_audit_summary = summary.get("parity_audit_summary")
    if isinstance(parity_audit_summary, dict):
        lines.append(f"- status={parity_audit_summary.get('status')}")
        lines.append(f"- total_mismatch_count={parity_audit_summary.get('total_mismatch_count')}")

    lines.extend(["", "Final Row Counts"])
    final_row_counts = summary.get("final_row_counts")
    if isinstance(final_row_counts, dict):
        for table_name, row_count in sorted(final_row_counts.items()):
            lines.append(f"- {table_name}={row_count}")

    if summary.get("errors"):
        lines.extend(["", "Errors"])
        for error in summary["errors"]:
            lines.append(f"- {error}")
    if summary.get("warning"):
        lines.extend(["", "Warnings", f"- {summary['warning']}"])

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_ec_source_layer_build(
        db_path=args.db,
        ecosystem_code=args.ecosystem,
        taxonomy_version_code=args.taxonomy_version,
        taxonomy_csv_path=args.taxonomy_csv,
        watchlist_path=args.watchlist,
        backup_dir=args.backup_dir,
        confirm_db=args.confirm_db,
        confirm_ecosystem=args.confirm_ecosystem,
        confirm_taxonomy_version=args.confirm_taxonomy_version,
        signal_date=args.signal_date,
        replace_existing=args.replace_existing,
    )
    sys.stdout.write(render_build_text(summary) + "\n")
    return 0 if summary.get("status") == "BUILD_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
