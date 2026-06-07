from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

from rawcandle.cli.plan_ec_source_layer_refresh import plan_ec_source_layer_refresh
from rawcandle.ec_dc_coverage_audit import audit_dc_facts_against_ec_sidecar
from rawcandle.ec_dc_fact_parity_audit import audit_dc_ec_fact_parity
from rawcandle.ec_group_index_daily_loader import load_ec_group_index_daily_from_dc
from rawcandle.ec_group_signal_daily_loader import load_ec_group_signal_daily_from_dc
from rawcandle.ec_group_synthetic_ohlc_daily_loader import load_ec_group_synthetic_ohlc_daily_from_dc
from rawcandle.ec_pipeline_watermark_loader import load_ec_pipeline_watermark_from_dc
from rawcandle.ec_ticker_signal_daily_loader import load_ec_ticker_signal_daily_from_dc


SUCCESS_PARITY_STATUSES = {"OK", "OK_WITH_WARNINGS"}
SUCCESS_COVERAGE_STATUSES = {"OK", "OK_WITH_WARNINGS"}
READY_REFRESH_STATUSES = {"READY_REFRESH_NEW_DATE", "READY_REFRESH_REPLACE_DATE"}
BLOCKED_PREFIX = "BLOCKED_"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a guarded recurring ec_ source-layer refresh into an existing SQLite ec_ state")
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
    parser.add_argument("--allow-replace-date", action="store_true", help="Allow recurring refresh to replace an already loaded selected date")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def _backup_filename(
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    selected_signal_date: str,
) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_base = Path(db_path).stem
    safe_signal_date = selected_signal_date.replace("-", "")
    return (
        f"{db_base}__ec_source_layer_refresh__{ecosystem_code}__"
        f"{taxonomy_version_code}__{safe_signal_date}__{timestamp}.sqlite"
    )


def _ensure_backup_dir(backup_dir: str) -> Path:
    path = Path(backup_dir).resolve()
    if not path.exists():
        raise ValueError(f"backup_dir does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"backup_dir is not a directory: {path}")
    if not os.access(path, os.W_OK):
        raise ValueError(f"backup_dir is not writable: {path}")
    return path


def _create_backup(
    db_path: str,
    backup_dir: Path,
    ecosystem_code: str,
    taxonomy_version_code: str,
    selected_signal_date: str,
) -> Path:
    backup_path = backup_dir / _backup_filename(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        selected_signal_date=selected_signal_date,
    )
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


def _selected_date_row_counts(db_path: str, selected_signal_date: str) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "ticker_rows": int(
                conn.execute(
                    "SELECT COUNT(*) FROM ec_ticker_signal_daily WHERE signal_date = ?",
                    (selected_signal_date,),
                ).fetchone()[0]
            ),
            "group_signal_rows": int(
                conn.execute(
                    "SELECT COUNT(*) FROM ec_group_signal_daily WHERE signal_date = ?",
                    (selected_signal_date,),
                ).fetchone()[0]
            ),
            "synthetic_ohlc_rows": int(
                conn.execute(
                    "SELECT COUNT(*) FROM ec_group_synthetic_ohlc_daily WHERE signal_date = ?",
                    (selected_signal_date,),
                ).fetchone()[0]
            ),
            "group_index_rows": int(
                conn.execute(
                    "SELECT COUNT(*) FROM ec_group_index_daily WHERE signal_date = ?",
                    (selected_signal_date,),
                ).fetchone()[0]
            ),
            "watermark_rows": int(
                conn.execute(
                    "SELECT COUNT(*) FROM ec_pipeline_watermark",
                ).fetchone()[0]
            ),
        }
    finally:
        conn.close()


def _run_step(
    *,
    step_name: str,
    completed_steps: list[str],
    fn,
    kwargs: dict[str, object],
) -> dict[str, object]:
    summary = fn(**kwargs)
    completed_steps.append(step_name)
    return summary


def _refresh_refused_summary(
    *,
    status: str,
    errors: list[str],
    planner_summary: dict[str, object] | None,
    skipped_reason: str | None = None,
) -> dict[str, object]:
    return {
        "attempted": False,
        "status": status,
        "signal_date": None,
        "refresh_mode": None,
        "skipped_reason": skipped_reason,
        "backup_path": None,
        "coverage_status": None,
        "parity_status": None,
        "total_mismatch_count": None,
        "ticker_rows": None,
        "group_signal_rows": None,
        "synthetic_ohlc_rows": None,
        "group_index_rows": None,
        "watermark_rows": None,
        "error": "; ".join(errors) if errors else None,
        "errors": errors,
        "planner_summary": planner_summary,
        "completed_steps": [],
        "failed_step": None,
    }


def run_ec_source_layer_refresh(
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
    allow_replace_date: bool = False,
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

    planner_summary = plan_ec_source_layer_refresh(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        taxonomy_csv_path=taxonomy_csv_path,
        watchlist_path=watchlist_path,
        signal_date=signal_date,
        allow_replace_date=allow_replace_date,
    )
    planner_status = str(planner_summary.get("status"))

    if gate_errors:
        return _refresh_refused_summary(
            status="REFRESH_REFUSED",
            errors=gate_errors,
            planner_summary=planner_summary,
        )

    if planner_status == "SKIP_UP_TO_DATE":
        selected_date_info = planner_summary.get("selected_date_info", {})
        selected_signal_date = None
        if isinstance(selected_date_info, dict):
            selected_signal_date = selected_date_info.get("selected_signal_date")
        return {
            "attempted": False,
            "status": "REFRESH_SKIPPED",
            "signal_date": selected_signal_date,
            "refresh_mode": "skip_up_to_date",
            "skipped_reason": "planner reported SKIP_UP_TO_DATE",
            "backup_path": None,
            "coverage_status": None,
            "parity_status": None,
            "total_mismatch_count": None,
            "ticker_rows": None,
            "group_signal_rows": None,
            "synthetic_ohlc_rows": None,
            "group_index_rows": None,
            "watermark_rows": None,
            "error": None,
            "errors": [],
            "planner_summary": planner_summary,
            "completed_steps": [],
            "failed_step": None,
        }

    if planner_status not in READY_REFRESH_STATUSES:
        reason = f"planner gate did not pass: {planner_status}"
        return _refresh_refused_summary(
            status="REFRESH_REFUSED",
            errors=[reason],
            planner_summary=planner_summary,
            skipped_reason=reason if planner_status.startswith(BLOCKED_PREFIX) else None,
        )

    assert resolved_backup_dir is not None
    selected_date_info = planner_summary.get("selected_date_info", {})
    assert isinstance(selected_date_info, dict)
    selected_signal_date = signal_date or selected_date_info.get("selected_signal_date")
    if not isinstance(selected_signal_date, str) or not selected_signal_date:
        return _refresh_refused_summary(
            status="REFRESH_REFUSED",
            errors=["planner did not provide a selected signal date"],
            planner_summary=planner_summary,
        )

    try:
        backup_path = _create_backup(
            db_path=db_path,
            backup_dir=resolved_backup_dir,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            selected_signal_date=selected_signal_date,
        )
    except Exception as exc:
        return {
            "attempted": False,
            "status": "REFRESH_FAILED_BEFORE_WRITE",
            "signal_date": selected_signal_date,
            "refresh_mode": "replace_selected_date" if planner_status == "READY_REFRESH_REPLACE_DATE" else "new_selected_date",
            "skipped_reason": None,
            "backup_path": None,
            "coverage_status": None,
            "parity_status": None,
            "total_mismatch_count": None,
            "ticker_rows": None,
            "group_signal_rows": None,
            "synthetic_ohlc_rows": None,
            "group_index_rows": None,
            "watermark_rows": None,
            "error": str(exc),
            "errors": [str(exc)],
            "planner_summary": planner_summary,
            "completed_steps": [],
            "failed_step": "backup",
        }

    completed_steps: list[str] = []
    refresh_mode = "replace_selected_date" if planner_status == "READY_REFRESH_REPLACE_DATE" else "new_selected_date"

    try:
        ticker_summary = _run_step(
            step_name="load_ec_ticker_signal_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_ticker_signal_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": True,
            },
        )
        if ticker_summary.get("status") == "FAILED":
            raise RuntimeError("Ticker fact loader returned FAILED")

        group_signal_summary = _run_step(
            step_name="load_ec_group_signal_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_group_signal_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": True,
            },
        )
        if group_signal_summary.get("status") == "FAILED":
            raise RuntimeError("Group signal fact loader returned FAILED")

        synthetic_summary = _run_step(
            step_name="load_ec_group_synthetic_ohlc_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_group_synthetic_ohlc_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": True,
            },
        )
        if synthetic_summary.get("status") == "FAILED":
            raise RuntimeError("Synthetic OHLC fact loader returned FAILED")

        group_index_summary = _run_step(
            step_name="load_ec_group_index_daily_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_group_index_daily_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "replace_existing": True,
            },
        )
        if group_index_summary.get("status") == "FAILED":
            raise RuntimeError("Group index fact loader returned FAILED")

        pipeline_watermark_summary = _run_step(
            step_name="load_ec_pipeline_watermark_from_dc",
            completed_steps=completed_steps,
            fn=load_ec_pipeline_watermark_from_dc,
            kwargs={
                "source_db_path": db_path,
                "target_db_path": db_path,
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "replace_existing": True,
            },
        )
        if pipeline_watermark_summary.get("status") == "FAILED":
            raise RuntimeError("Pipeline watermark loader returned FAILED")

        coverage_audit_summary = _run_step(
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
        coverage_status = coverage_audit_summary.get("status")
        if coverage_status not in SUCCESS_COVERAGE_STATUSES:
            raise RuntimeError(
                "Coverage audit returned non-success status: "
                f"{coverage_status}"
            )

        parity_audit_summary = _run_step(
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

        selected_row_counts = _selected_date_row_counts(db_path, selected_signal_date)
        return {
            "attempted": True,
            "status": "REFRESH_COMPLETED",
            "signal_date": selected_signal_date,
            "refresh_mode": refresh_mode,
            "skipped_reason": None,
            "backup_path": str(backup_path),
            "coverage_status": coverage_status,
            "parity_status": parity_status,
            "total_mismatch_count": total_mismatch_count,
            "ticker_rows": selected_row_counts["ticker_rows"],
            "group_signal_rows": selected_row_counts["group_signal_rows"],
            "synthetic_ohlc_rows": selected_row_counts["synthetic_ohlc_rows"],
            "group_index_rows": selected_row_counts["group_index_rows"],
            "watermark_rows": selected_row_counts["watermark_rows"],
            "error": None,
            "errors": [],
            "planner_summary": planner_summary,
            "completed_steps": completed_steps,
            "failed_step": None,
            "ticker_summary": ticker_summary,
            "group_signal_summary": group_signal_summary,
            "synthetic_summary": synthetic_summary,
            "group_index_summary": group_index_summary,
            "pipeline_watermark_summary": pipeline_watermark_summary,
            "coverage_audit_summary": coverage_audit_summary,
            "parity_audit_summary": parity_audit_summary,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "status": "REFRESH_FAILED",
            "signal_date": selected_signal_date,
            "refresh_mode": refresh_mode,
            "skipped_reason": None,
            "backup_path": str(backup_path),
            "coverage_status": None,
            "parity_status": None,
            "total_mismatch_count": None,
            "ticker_rows": None,
            "group_signal_rows": None,
            "synthetic_ohlc_rows": None,
            "group_index_rows": None,
            "watermark_rows": None,
            "error": str(exc),
            "errors": [str(exc)],
            "planner_summary": planner_summary,
            "completed_steps": completed_steps,
            "failed_step": completed_steps[-1] if completed_steps else "backup",
            "warning": "Partial selected-date ec_ writes may exist; no automatic rollback was attempted",
        }


def render_refresh_text(summary: dict[str, object]) -> str:
    lines = [
        "EC Source Layer Refresh",
        f"Refresh Status: {summary.get('status')}",
        "",
        "Safety Gates",
    ]
    if summary.get("status") == "REFRESH_REFUSED":
        for error in summary.get("errors", []):
            lines.append(f"- {error}")
    elif summary.get("status") == "REFRESH_SKIPPED":
        lines.append("- planner returned SKIP_UP_TO_DATE")
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

    lines.extend(["", "Refresh Steps"])
    for step in summary.get("completed_steps", []):
        lines.append(f"- completed: {step}")
    failed_step = summary.get("failed_step")
    if failed_step:
        lines.append(f"- failed_step={failed_step}")

    lines.extend(["", "Loader Summaries"])
    for key in (
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
    coverage_status = summary.get("coverage_status")
    coverage_audit_summary = summary.get("coverage_audit_summary")
    if coverage_status is not None:
        lines.append(f"- status={coverage_status}")
    elif isinstance(coverage_audit_summary, dict):
        lines.append(f"- status={coverage_audit_summary.get('status')}")

    lines.extend(["", "Fact Parity Audit"])
    parity_status = summary.get("parity_status")
    parity_audit_summary = summary.get("parity_audit_summary")
    if parity_status is not None:
        lines.append(f"- status={parity_status}")
        lines.append(f"- total_mismatch_count={summary.get('total_mismatch_count')}")
    elif isinstance(parity_audit_summary, dict):
        lines.append(f"- status={parity_audit_summary.get('status')}")
        lines.append(f"- total_mismatch_count={parity_audit_summary.get('total_mismatch_count')}")

    lines.extend(["", "Selected Date Row Counts"])
    for key in ("ticker_rows", "group_signal_rows", "synthetic_ohlc_rows", "group_index_rows", "watermark_rows"):
        lines.append(f"- {key}={summary.get(key)}")

    lines.extend(["", "Refresh Status"])
    lines.append(f"- attempted={summary.get('attempted')}")
    lines.append(f"- signal_date={summary.get('signal_date')}")
    lines.append(f"- refresh_mode={summary.get('refresh_mode')}")
    lines.append(f"- skipped_reason={summary.get('skipped_reason')}")

    if summary.get("errors"):
        lines.extend(["", "Errors"])
        for error in summary["errors"]:
            lines.append(f"- {error}")
    if summary.get("warning"):
        lines.extend(["", "Warnings", f"- {summary['warning']}"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_ec_source_layer_refresh(
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
        allow_replace_date=args.allow_replace_date,
    )
    sys.stdout.write(render_refresh_text(summary) + "\n")
    return 0 if summary.get("status") == "REFRESH_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
