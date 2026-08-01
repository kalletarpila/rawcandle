from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

from rawcandle.cli.ec_source_layer_watchlist_policy import extract_watchlist_membership_fields
from rawcandle.cli.plan_ec_source_layer_backfill import plan_ec_source_layer_backfill
from rawcandle.ec_dc_coverage_audit import audit_dc_facts_against_ec_sidecar
from rawcandle.ec_dc_fact_parity_audit import audit_dc_ec_fact_parity
from rawcandle.ec_group_index_daily_loader import load_ec_group_index_daily_from_dc
from rawcandle.ec_group_signal_daily_loader import load_ec_group_signal_daily_from_dc
from rawcandle.ec_group_synthetic_ohlc_daily_loader import load_ec_group_synthetic_ohlc_daily_from_dc
from rawcandle.ec_pipeline_watermark_loader import advance_ec_pipeline_watermarks_after_historical_backfill
from rawcandle.ec_ticker_signal_daily_loader import load_ec_ticker_signal_daily_from_dc


SUCCESS_PARITY_STATUSES = {"OK", "OK_WITH_WARNINGS"}
SUCCESS_COVERAGE_STATUSES = {"OK", "OK_WITH_WARNINGS"}
REPLACE_ACTIONS = {"REPLACE_PARTIAL", "REPLACE_EXISTING"}
WATERMARK_POLICY = "ADVANCE_CANONICAL_FACT_HEADS_AFTER_VALIDATED_BACKFILL"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a guarded ec_ historical source-layer backfill into an existing SQLite ec_ state")
    parser.add_argument("--db", required=True, help="Path to the target SQLite database")
    parser.add_argument("--ecosystem", required=True, help="Target ecosystem code")
    parser.add_argument("--taxonomy-version", required=True, help="Target taxonomy version code")
    parser.add_argument("--date-from", required=True, help="Inclusive start date in YYYY-MM-DD format")
    parser.add_argument("--date-to", required=True, help="Inclusive end date in YYYY-MM-DD format")
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
    parser.add_argument("--allow-replace-existing", action="store_true", help="Allow planner-approved replacement of partial or fully loaded dates")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def _backup_filename(
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    date_from: str,
    date_to: str,
) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_base = Path(db_path).stem
    safe_date_from = date_from.replace("-", "")
    safe_date_to = date_to.replace("-", "")
    return (
        f"{db_base}__ec_source_layer_backfill__{ecosystem_code}__"
        f"{taxonomy_version_code}__{safe_date_from}_{safe_date_to}__{timestamp}.sqlite"
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
    date_from: str,
    date_to: str,
) -> Path:
    backup_path = backup_dir / _backup_filename(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        date_from=date_from,
        date_to=date_to,
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
        }
    finally:
        conn.close()


def _backfill_refused_summary(
    *,
    status: str,
    errors: list[str],
    planner_summary: dict[str, object] | None,
    date_from: str,
    date_to: str,
) -> dict[str, object]:
    return {
        "status": status,
        "ecosystem_code": None,
        "taxonomy_version_code": None,
        "date_from": date_from,
        "date_to": date_to,
        "selected_dates": [],
        "completed_dates": [],
        "skipped_dates": [],
        "failed_date": None,
        "failed_step": None,
        "backup_path": None,
        "per_date_results": [],
        "total_mismatch_count": 0,
        "error": "; ".join(errors) if errors else None,
        "errors": errors,
        "planner_summary": planner_summary,
        **_watermark_not_run_summary(),
    }


def _watermark_not_run_summary() -> dict[str, object]:
    return {
        "watermark_policy": WATERMARK_POLICY,
        "watermark_refresh_performed": False,
        "watermark_advanced": False,
        "watermark_candidate_latest_signal_date": None,
        "watermark_rows_inserted": 0,
        "watermark_rows_updated": 0,
        "watermark_rows_unchanged": 0,
        "watermark_rows_total": 0,
        "watermark_advance_status": "NOT_RUN",
    }


def _merge_watermark_summary(summary: dict[str, object], watermark_summary: dict[str, object]) -> dict[str, object]:
    merged = dict(summary)
    merged.update(
        {
            "watermark_policy": watermark_summary.get("watermark_policy", WATERMARK_POLICY),
            "watermark_refresh_performed": bool(watermark_summary.get("watermark_refresh_performed", False)),
            "watermark_advanced": bool(watermark_summary.get("watermark_advanced", False)),
            "watermark_candidate_latest_signal_date": watermark_summary.get("watermark_candidate_latest_signal_date"),
            "watermark_rows_inserted": int(watermark_summary.get("watermark_rows_inserted") or 0),
            "watermark_rows_updated": int(watermark_summary.get("watermark_rows_updated") or 0),
            "watermark_rows_unchanged": int(watermark_summary.get("watermark_rows_unchanged") or 0),
            "watermark_rows_total": int(watermark_summary.get("watermark_rows_total") or 0),
            "watermark_advance_status": str(watermark_summary.get("watermark_advance_status") or watermark_summary.get("status") or "UNKNOWN"),
            "watermark_summary": watermark_summary,
        }
    )
    return merged


def _extract_selected_dates(planner_summary: dict[str, object]) -> list[dict[str, str]]:
    loaded_state = planner_summary.get("loaded_state", {})
    if not isinstance(loaded_state, dict):
        return []
    candidate_dates = loaded_state.get("candidate_dates", [])
    if not isinstance(candidate_dates, list):
        return []
    return [
        {"date": str(entry["date"]), "action": str(entry["action"])}
        for entry in candidate_dates
        if isinstance(entry, dict) and "date" in entry and "action" in entry
    ]


def _extract_skipped_dates(planner_summary: dict[str, object]) -> list[dict[str, str]]:
    skipped_dates: list[dict[str, str]] = []
    source_state = planner_summary.get("source_date_availability", {})
    if isinstance(source_state, dict):
        for fact_date in source_state.get("missing_source_dates", []):
            skipped_dates.append({"date": str(fact_date), "reason": "NOT_ALIGNED_SOURCE"})
    loaded_state = planner_summary.get("loaded_state", {})
    if isinstance(loaded_state, dict):
        for fact_date in loaded_state.get("already_loaded_dates", []):
            skipped_dates.append({"date": str(fact_date), "reason": "FULLY_LOADED_IN_EC"})
        for fact_date in loaded_state.get("partial_dates", []):
            skipped_dates.append({"date": str(fact_date), "reason": "PARTIALLY_LOADED_IN_EC"})
    return skipped_dates


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


def _build_date_result(
    *,
    date_value: str,
    action: str,
    completed_steps: list[str],
    replace_existing: bool,
    ticker_summary: dict[str, object],
    group_signal_summary: dict[str, object],
    synthetic_summary: dict[str, object],
    group_index_summary: dict[str, object],
    coverage_audit_summary: dict[str, object],
    parity_audit_summary: dict[str, object],
    row_counts: dict[str, int],
) -> dict[str, object]:
    return {
        "date": date_value,
        "action": action,
        "replace_existing": replace_existing,
        "completed_steps": list(completed_steps),
        "ticker_summary": ticker_summary,
        "group_signal_summary": group_signal_summary,
        "synthetic_summary": synthetic_summary,
        "group_index_summary": group_index_summary,
        "coverage_audit_summary": coverage_audit_summary,
        "parity_audit_summary": parity_audit_summary,
        "row_counts": row_counts,
        "coverage_status": coverage_audit_summary.get("status"),
        "parity_status": parity_audit_summary.get("status"),
        "total_mismatch_count": int(parity_audit_summary.get("total_mismatch_count", 0)),
    }


def run_ec_source_layer_backfill(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    date_from: str,
    date_to: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    backup_dir: str,
    confirm_db: str,
    confirm_ecosystem: str,
    confirm_taxonomy_version: str,
    allow_replace_existing: bool = False,
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

    planner_summary = plan_ec_source_layer_backfill(
        db_path=db_path,
        ecosystem_code=ecosystem_code,
        taxonomy_version_code=taxonomy_version_code,
        date_from=date_from,
        date_to=date_to,
        taxonomy_csv_path=taxonomy_csv_path,
        watchlist_path=watchlist_path,
        allow_replace_existing=allow_replace_existing,
    )
    planner_status = str(planner_summary.get("status"))
    watchlist_membership_fields = extract_watchlist_membership_fields(planner_summary)

    if gate_errors:
        summary = _backfill_refused_summary(
            status="BACKFILL_REFUSED",
            errors=gate_errors,
            planner_summary=planner_summary,
            date_from=date_from,
            date_to=date_to,
        )
        summary["ecosystem_code"] = ecosystem_code
        summary["taxonomy_version_code"] = taxonomy_version_code
        summary.update(watchlist_membership_fields)
        return summary

    if planner_status == "SKIP_ALL_DATES_ALREADY_LOADED":
        return {
            "status": "BACKFILL_SKIPPED",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_from": date_from,
            "date_to": date_to,
            "selected_dates": [],
            "completed_dates": [],
            "skipped_dates": _extract_skipped_dates(planner_summary),
            "failed_date": None,
            "failed_step": None,
            "backup_path": None,
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": None,
            "errors": [],
            "planner_summary": planner_summary,
            "skipped_reason": "planner reported SKIP_ALL_DATES_ALREADY_LOADED",
            **_watermark_not_run_summary(),
            **watchlist_membership_fields,
        }

    if planner_status != "READY_BACKFILL_PLAN":
        reason = f"planner gate did not pass: {planner_status}"
        summary = _backfill_refused_summary(
            status="BACKFILL_REFUSED",
            errors=[reason],
            planner_summary=planner_summary,
            date_from=date_from,
            date_to=date_to,
        )
        summary["ecosystem_code"] = ecosystem_code
        summary["taxonomy_version_code"] = taxonomy_version_code
        summary.update(watchlist_membership_fields)
        return summary

    selected_dates = _extract_selected_dates(planner_summary)
    skipped_dates = _extract_skipped_dates(planner_summary)
    if not selected_dates:
        return {
            "status": "BACKFILL_SKIPPED",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_from": date_from,
            "date_to": date_to,
            "selected_dates": [],
            "completed_dates": [],
            "skipped_dates": skipped_dates,
            "failed_date": None,
            "failed_step": None,
            "backup_path": None,
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": None,
            "errors": [],
            "planner_summary": planner_summary,
            "skipped_reason": "planner returned READY_BACKFILL_PLAN with zero eligible selected dates",
            **_watermark_not_run_summary(),
            **watchlist_membership_fields,
        }

    assert resolved_backup_dir is not None
    try:
        backup_path = _create_backup(
            db_path=db_path,
            backup_dir=resolved_backup_dir,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:
        return {
            "status": "BACKFILL_FAILED_BEFORE_WRITE",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_from": date_from,
            "date_to": date_to,
            "selected_dates": selected_dates,
            "completed_dates": [],
            "skipped_dates": skipped_dates,
            "failed_date": None,
            "failed_step": "backup",
            "backup_path": None,
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": str(exc),
            "errors": [str(exc)],
            "planner_summary": planner_summary,
            **_watermark_not_run_summary(),
        }

    per_date_results: list[dict[str, object]] = []
    completed_dates: list[str] = []
    total_mismatch_count = 0

    try:
        for selected in selected_dates:
            current_date = selected["date"]
            action = selected["action"]
            replace_existing = action in REPLACE_ACTIONS
            completed_steps: list[str] = []

            ticker_summary = _run_step(
                step_name="load_ec_ticker_signal_daily_from_dc",
                completed_steps=completed_steps,
                fn=load_ec_ticker_signal_daily_from_dc,
                kwargs={
                    "source_db_path": db_path,
                    "target_db_path": db_path,
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": current_date,
                    "replace_existing": replace_existing,
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
                    "signal_date": current_date,
                    "replace_existing": replace_existing,
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
                    "signal_date": current_date,
                    "replace_existing": replace_existing,
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
                    "signal_date": current_date,
                    "replace_existing": replace_existing,
                },
            )
            if group_index_summary.get("status") == "FAILED":
                raise RuntimeError("Group index fact loader returned FAILED")

            coverage_audit_summary = _run_step(
                step_name="audit_dc_facts_against_ec_sidecar",
                completed_steps=completed_steps,
                fn=audit_dc_facts_against_ec_sidecar,
                kwargs={
                    "analysis_db_path": db_path,
                    "ec_db_path": db_path,
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": current_date,
                },
            )
            coverage_status = str(coverage_audit_summary.get("status"))
            if coverage_status not in SUCCESS_COVERAGE_STATUSES:
                raise RuntimeError(f"Coverage audit returned non-success status: {coverage_status}")

            parity_audit_summary = _run_step(
                step_name="audit_dc_ec_fact_parity",
                completed_steps=completed_steps,
                fn=audit_dc_ec_fact_parity,
                kwargs={
                    "source_db_path": db_path,
                    "target_db_path": db_path,
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": current_date,
                    "include_pipeline_watermark": False,
                },
            )
            parity_status = str(parity_audit_summary.get("status"))
            mismatch_count = int(parity_audit_summary.get("total_mismatch_count", 0))
            if parity_status not in SUCCESS_PARITY_STATUSES or mismatch_count != 0:
                raise RuntimeError(
                    "Fact parity audit did not meet acceptance criteria: "
                    f"status={parity_status}, total_mismatch_count={mismatch_count}"
                )

            row_counts = _selected_date_row_counts(db_path, current_date)
            date_result = _build_date_result(
                date_value=current_date,
                action=action,
                completed_steps=completed_steps,
                replace_existing=replace_existing,
                ticker_summary=ticker_summary,
                group_signal_summary=group_signal_summary,
                synthetic_summary=synthetic_summary,
                group_index_summary=group_index_summary,
                coverage_audit_summary=coverage_audit_summary,
                parity_audit_summary=parity_audit_summary,
                row_counts=row_counts,
            )
            per_date_results.append(date_result)
            completed_dates.append(current_date)
            total_mismatch_count += mismatch_count
    except Exception as exc:
        failed_date = selected_dates[len(completed_dates)]["date"] if len(completed_dates) < len(selected_dates) else None
        failed_step = completed_steps[-1] if completed_steps else "backup"
        return {
            "status": "BACKFILL_FAILED",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_from": date_from,
            "date_to": date_to,
            "selected_dates": selected_dates,
            "completed_dates": completed_dates,
            "skipped_dates": skipped_dates,
            "failed_date": failed_date,
            "failed_step": failed_step,
            "backup_path": str(backup_path),
            "per_date_results": per_date_results,
            "total_mismatch_count": total_mismatch_count,
            "error": str(exc),
            "errors": [str(exc)],
            "planner_summary": planner_summary,
            "failed_date_completed_steps": list(completed_steps),
            "warning": "Partial selected-date ec_ writes may exist; no automatic rollback was attempted",
            **_watermark_not_run_summary(),
            **watchlist_membership_fields,
        }

    try:
        watermark_candidate_latest_signal_date = max(completed_dates)
        watermark_summary = advance_ec_pipeline_watermarks_after_historical_backfill(
            target_db_path=db_path,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            latest_signal_date=watermark_candidate_latest_signal_date,
        )
        watermark_advance_status = str(
            watermark_summary.get("watermark_advance_status")
            or watermark_summary.get("status")
            or "UNKNOWN"
        )
        if watermark_advance_status != "OK":
            raise RuntimeError(f"Historical backfill watermark advancement returned {watermark_advance_status}")
    except Exception as exc:
        failed_summary = {
            "status": "BACKFILL_FAILED",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_from": date_from,
            "date_to": date_to,
            "selected_dates": selected_dates,
            "completed_dates": completed_dates,
            "skipped_dates": skipped_dates,
            "failed_date": None,
            "failed_step": "advance_ec_pipeline_watermarks_after_historical_backfill",
            "backup_path": str(backup_path),
            "per_date_results": per_date_results,
            "total_mismatch_count": total_mismatch_count,
            "error": str(exc),
            "errors": [str(exc)],
            "planner_summary": planner_summary,
            "warning": "Selected-date ec_ fact writes completed, but final watermark advancement failed; retry is required",
            **_watermark_not_run_summary(),
            **watchlist_membership_fields,
        }
        failed_summary["watermark_candidate_latest_signal_date"] = max(completed_dates) if completed_dates else None
        failed_summary["watermark_advance_status"] = "FAILED"
        return failed_summary

    completed_summary = {
        "status": "BACKFILL_COMPLETED",
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": taxonomy_version_code,
        "date_from": date_from,
        "date_to": date_to,
        "selected_dates": selected_dates,
        "completed_dates": completed_dates,
        "skipped_dates": skipped_dates,
        "failed_date": None,
        "failed_step": None,
        "backup_path": str(backup_path),
        "per_date_results": per_date_results,
        "total_mismatch_count": total_mismatch_count,
        "error": None,
        "errors": [],
        "planner_summary": planner_summary,
        "watermark_policy_note": "Historical backfill advanced canonical EC fact watermark heads once after successful coverage and fact parity validation.",
        **watchlist_membership_fields,
    }
    return _merge_watermark_summary(completed_summary, watermark_summary)


def render_backfill_text(summary: dict[str, object]) -> str:
    lines = [
        "EC Source Layer Backfill",
        f"Backfill Status: {summary.get('status')}",
        "",
        "Safety Gates",
    ]
    if summary.get("status") == "BACKFILL_REFUSED":
        for error in summary.get("errors", []):
            lines.append(f"- {error}")
    elif summary.get("status") == "BACKFILL_SKIPPED":
        lines.append(f"- {summary.get('skipped_reason')}")
    else:
        lines.append("- confirm-db matched --db")
        lines.append("- confirm-ecosystem matched --ecosystem")
        lines.append("- confirm-taxonomy-version matched --taxonomy-version")

    planner_summary = summary.get("planner_summary")
    lines.extend(["", "Planner Result"])
    if isinstance(planner_summary, dict):
        lines.append(f"- planner_status={planner_summary.get('status')}")
    lines.append(f"- watchlist_membership_status={summary.get('watchlist_membership_status')}")
    lines.append(f"- watchlist_sync_required={str(bool(summary.get('watchlist_sync_required'))).lower()}")
    lines.append(f"- watchlist_missing_in_loaded_count={summary.get('watchlist_missing_in_loaded_count')}")
    lines.append(f"- watchlist_loaded_only_count={summary.get('watchlist_loaded_only_count')}")

    lines.extend(["", "Backup"])
    lines.append(f"- backup_path={summary.get('backup_path')}")

    lines.extend(["", "Selected Dates"])
    lines.append(f"- date_from={summary.get('date_from')}")
    lines.append(f"- date_to={summary.get('date_to')}")
    lines.append(f"- selected_dates={summary.get('selected_dates')}")
    lines.append(f"- completed_dates={summary.get('completed_dates')}")
    lines.append(f"- skipped_dates={summary.get('skipped_dates')}")

    lines.extend(["", "Backfill Steps"])
    for date_result in summary.get("per_date_results", []):
        if not isinstance(date_result, dict):
            continue
        lines.append(f"- {date_result.get('date')}: completed_steps={date_result.get('completed_steps')}")
    if summary.get("failed_date"):
        lines.append(f"- failed_date={summary.get('failed_date')}")
        lines.append(f"- failed_step={summary.get('failed_step')}")
        if summary.get("failed_date_completed_steps") is not None:
            lines.append(f"- failed_date_completed_steps={summary.get('failed_date_completed_steps')}")

    lines.extend(["", "Per-Date Loader Summaries"])
    for date_result in summary.get("per_date_results", []):
        if not isinstance(date_result, dict):
            continue
        lines.append(
            f"- {date_result.get('date')}: "
            f"ticker={date_result.get('ticker_summary', {}).get('status')}, "
            f"group_signal={date_result.get('group_signal_summary', {}).get('status')}, "
            f"synthetic={date_result.get('synthetic_summary', {}).get('status')}, "
            f"group_index={date_result.get('group_index_summary', {}).get('status')}"
        )

    lines.extend(["", "Per-Date Coverage Audit"])
    for date_result in summary.get("per_date_results", []):
        if not isinstance(date_result, dict):
            continue
        lines.append(f"- {date_result.get('date')}: status={date_result.get('coverage_status')}")

    lines.extend(["", "Per-Date Fact Parity Audit"])
    for date_result in summary.get("per_date_results", []):
        if not isinstance(date_result, dict):
            continue
        lines.append(
            f"- {date_result.get('date')}: "
            f"status={date_result.get('parity_status')}, "
            f"total_mismatch_count={date_result.get('total_mismatch_count')}"
        )

    lines.extend(["", "Final Row Counts"])
    for date_result in summary.get("per_date_results", []):
        if not isinstance(date_result, dict):
            continue
        lines.append(f"- {date_result.get('date')}: row_counts={date_result.get('row_counts')}")

    lines.extend(["", "Backfill Status"])
    lines.append(f"- total_mismatch_count={summary.get('total_mismatch_count')}")
    lines.append(f"- error={summary.get('error')}")

    if summary.get("watermark_policy"):
        lines.extend(["", "Watermark Policy"])
        lines.append(f"- watermark_policy={summary.get('watermark_policy')}")
        lines.append(f"- watermark_refresh_performed={str(bool(summary.get('watermark_refresh_performed'))).lower()}")
        lines.append(f"- watermark_advanced={str(bool(summary.get('watermark_advanced'))).lower()}")
        lines.append(f"- watermark_candidate_latest_signal_date={summary.get('watermark_candidate_latest_signal_date')}")
        lines.append(f"- watermark_rows_inserted={summary.get('watermark_rows_inserted')}")
        lines.append(f"- watermark_rows_updated={summary.get('watermark_rows_updated')}")
        lines.append(f"- watermark_rows_unchanged={summary.get('watermark_rows_unchanged')}")
        lines.append(f"- watermark_rows_total={summary.get('watermark_rows_total')}")
        lines.append(f"- watermark_advance_status={summary.get('watermark_advance_status')}")
        if summary.get("watermark_policy_note"):
            lines.append(f"- {summary.get('watermark_policy_note')}")

    if summary.get("errors"):
        lines.extend(["", "Errors"])
        for error in summary.get("errors", []):
            lines.append(f"- {error}")
    if summary.get("warning"):
        lines.extend(["", "Warnings", f"- {summary.get('warning')}"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_ec_source_layer_backfill(
        db_path=args.db,
        ecosystem_code=args.ecosystem,
        taxonomy_version_code=args.taxonomy_version,
        date_from=args.date_from,
        date_to=args.date_to,
        taxonomy_csv_path=args.taxonomy_csv,
        watchlist_path=args.watchlist,
        backup_dir=args.backup_dir,
        confirm_db=args.confirm_db,
        confirm_ecosystem=args.confirm_ecosystem,
        confirm_taxonomy_version=args.confirm_taxonomy_version,
        allow_replace_existing=args.allow_replace_existing,
    )
    sys.stdout.write(render_backfill_text(summary) + "\n")
    return 0 if summary.get("status") == "BACKFILL_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
