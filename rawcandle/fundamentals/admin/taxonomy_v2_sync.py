"""Refresh Fundamentals from the already-active Datacenter taxonomy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths, _background_heartbeat, cleanup_copy_lane, create_copy_lane
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest, AdminFinalResult, AdminOperationType, AdminStatus, RunStage,
    fingerprint, utc_now,
)
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.progress import ProgressStage, ProgressTracker
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import load_active_dc_memberships
from rawcandle.fundamentals.phase13b_foundation import database_fingerprint


def _state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    _, taxonomy = load_active_dc_memberships(paths.taxonomy_db, paths.canonical_db)
    return {
        "sources": {role: database_fingerprint(paths.as_dict()[role]) for role in ("provider", "canonical", "market", "taxonomy")},
        "analysis": database_fingerprint(paths.analysis_db),
        "active_taxonomy": taxonomy,
    }


def run_preview(
    *, taxonomy_domain: str = "dc_ecosystem", candidate_path: Path | None = None,
    candidate_version: str | None = None, source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT, progress_callback=None,
) -> dict[str, Any]:
    if taxonomy_domain != "dc_ecosystem":
        raise ValueError("FUNDAMENTALS_TAXONOMY_DOMAIN_MUST_BE_DC_ECOSYSTEM")
    if candidate_path is not None or candidate_version is not None:
        raise ValueError("FUNDAMENTALS_ADMIN_TAXONOMY_CSV_NOT_ACCEPTED")
    started = utc_now()
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"taxonomy_domain": taxonomy_domain, "as_of_date": started[:10]}), suffix="active_preview")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(
        run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        run_dir=writer.run_dir,
        stages=(ProgressStage.LOAD_ACTIVE_TAXONOMY, ProgressStage.BUILD_PREVIEW, ProgressStage.COMPLETED),
        callback=progress_callback,
    )
    request = AdminBatchRequest(operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, requested_inputs=(), normalized_inputs=(), options={"taxonomy_domain": taxonomy_domain})
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Active taxonomy rebuild preview requested.")
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Reading active dc_ecosystem taxonomy.")
    failed_stage = ProgressStage.LOAD_ACTIVE_TAXONOMY
    try:
        progress.running(ProgressStage.LOAD_ACTIVE_TAXONOMY, "Reading active taxonomy and source state.")
        with _background_heartbeat(progress, "Reading authoritative databases is still running."):
            state = _state(source_paths)
        progress.completed(ProgressStage.LOAD_ACTIVE_TAXONOMY, "Active taxonomy and source state loaded.")
        failed_stage = ProgressStage.BUILD_PREVIEW
        progress.running(ProgressStage.BUILD_PREVIEW, "Binding active taxonomy to the rebuild preview.")
        preview = {
            "taxonomy_domain": taxonomy_domain,
            "source_state": state,
            "as_of_date": started[:10],
            "action": "FULL_V2_REBUILD",
        }
        preview["preview_fingerprint"] = fingerprint(preview)
        payload_path = writer.write_json("taxonomy_preview_payload.json", preview)
        writer.write_json("preview.json", preview)
        result = AdminFinalResult(
            run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.COMPLETED, mode="ACTIVE_TAXONOMY_PREVIEW",
            started_at_utc=started, completed_at_utc=utc_now(),
            preview_fingerprint=preview["preview_fingerprint"], request=request.as_dict(),
            downstream={"action": "FULL_V2_REBUILD", "active_taxonomy": state["active_taxonomy"], "invocation_counts": {"full_v2_rebuild": 0}},
            artifacts={"preview": str(payload_path)},
        )
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result.as_dict()))
        progress.completed(ProgressStage.BUILD_PREVIEW, "Active taxonomy rebuild preview ready.")
        writer.checkpoint(RunStage.PREVIEW_READY, message="Active taxonomy preview ready.", preview_fingerprint=preview["preview_fingerprint"])
        writer.checkpoint(RunStage.COMPLETED, message="Active taxonomy preview ready.", preview_fingerprint=preview["preview_fingerprint"])
        writer.write_exit_code(0)
        progress.running(ProgressStage.COMPLETED, "Taxonomy preview completed.")
        progress.completed(ProgressStage.COMPLETED, "Taxonomy preview completed.")
        writer.write_manifest()
        return result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "preview_payload_path": str(payload_path), "active_taxonomy": state["active_taxonomy"]}
    except Exception as exc:
        progress.failed(failed_stage, "Taxonomy preview failed.", errors=(f"{type(exc).__name__}: {exc}",))
        writer.write_error(exc)
        result = AdminFinalResult(
            run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.FAILED, mode="ACTIVE_TAXONOMY_PREVIEW",
            started_at_utc=started, completed_at_utc=utc_now(), request=request.as_dict(),
            errors=({"type": type(exc).__name__, "message": str(exc)},),
        )
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result.as_dict()))
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message="Taxonomy preview failed before any write.")
        writer.write_exit_code(2)
        writer.write_manifest()
        raise


def run_apply(
    *, taxonomy_domain: str, preview_payload_path: Path, preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(), run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT, confirm_apply: bool = False,
    keep_copies: bool = False, inject_failure_at: str | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    if not confirm_apply:
        raise PermissionError("FUNDAMENTALS_TAXONOMY_COPY_CONFIRMATION_REQUIRED")
    if taxonomy_domain != "dc_ecosystem":
        raise ValueError("FUNDAMENTALS_TAXONOMY_DOMAIN_MUST_BE_DC_ECOSYSTEM")
    preview = json.loads(Path(preview_payload_path).read_text(encoding="utf-8"))
    if preview.get("preview_fingerprint") != preview_fingerprint or preview.get("action") != "FULL_V2_REBUILD":
        raise ValueError("FUNDAMENTALS_TAXONOMY_PREVIEW_MISMATCH")
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, preview_fingerprint, suffix="active_copy")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(
        run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        run_dir=writer.run_dir,
        stages=(ProgressStage.PREFLIGHT, ProgressStage.CREATE_COPIES, ProgressStage.PACKAGE_CALCULATION, ProgressStage.FINAL_VALIDATION, ProgressStage.CLEANUP, ProgressStage.COMPLETED),
        callback=progress_callback,
    )
    request = AdminBatchRequest(operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, requested_inputs=(), normalized_inputs=(), options={"taxonomy_domain": taxonomy_domain})
    started = utc_now()
    progress.running(ProgressStage.PREFLIGHT, "Checking active taxonomy preview binding.")
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Active taxonomy copy rebuild requested.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Creating copy lane for active taxonomy rebuild.", preview_fingerprint=preview_fingerprint)
    lane = None
    write_boundary_crossed = False
    failed_stage = ProgressStage.PREFLIGHT
    try:
        with _background_heartbeat(progress, "Checking active source state is still running."):
            if _state(source_paths) != preview["source_state"]:
                raise RuntimeError("FUNDAMENTALS_TAXONOMY_STALE_PREVIEW")
        progress.completed(ProgressStage.PREFLIGHT, "Preview binding confirmed.")
        failed_stage = ProgressStage.CREATE_COPIES
        progress.running(ProgressStage.CREATE_COPIES, "Copying authoritative source databases.")
        lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "apply_lane", writer=writer)
        progress.completed(ProgressStage.CREATE_COPIES, "Source copies are ready.")
        if _state(lane.paths) != preview["source_state"]:
            raise RuntimeError("FUNDAMENTALS_TAXONOMY_COPY_SOURCE_MISMATCH")
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Building disposable V2 analysis.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
        write_boundary_crossed = True
        failed_stage = ProgressStage.PACKAGE_CALCULATION
        progress.running(ProgressStage.PACKAGE_CALCULATION, "Building fresh V2 analysis and Relative Valuation.")
        with _background_heartbeat(progress, "Full V2 analysis rebuild is still running."):
            downstream = run_full_v2_downstream(
                lane.paths.as_dict(), output=lane.lane_dir / "full_v2_downstream",
                as_of_date=preview["as_of_date"], inject_failure_at=inject_failure_at,
            )
        progress.completed(ProgressStage.PACKAGE_CALCULATION, "Full V2 rebuild validated.")
        failed_stage = ProgressStage.FINAL_VALIDATION
        progress.running(ProgressStage.FINAL_VALIDATION, "Verifying active taxonomy identity.")
        expected = preview["source_state"]["active_taxonomy"]
        actual = downstream["active_taxonomy"]
        if any(expected[key] != actual[key] for key in ("domain", "version", "semantic_fingerprint")):
            raise RuntimeError("FUNDAMENTALS_TAXONOMY_REBUILD_IDENTITY_MISMATCH")
        progress.completed(ProgressStage.FINAL_VALIDATION, "Active taxonomy identity matches the rebuild.")
        failed_stage = ProgressStage.CLEANUP
        downstream["candidate_retained"] = keep_copies
        result = AdminFinalResult(
            run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.COMPLETED, mode="COPY_ONLY_APPLY",
            started_at_utc=started, completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint, request=request.as_dict(),
            downstream=downstream, rollback={"status": "NOT_REQUIRED"},
            artifacts={"rebuild_result": str(lane.lane_dir / "full_v2_downstream" / "full_v2_rebuild" / "result.json")},
            recommended_next_action="Production replacement remains gated pending atomic V2 publication.",
        )
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result.as_dict()))
        writer.checkpoint(RunStage.COMPLETED, message="Active taxonomy copy rebuild validated.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
        writer.write_exit_code(0)
        progress.running(ProgressStage.CLEANUP, "Discarding disposable database copies." if not keep_copies else "Retaining copy lane.")
        progress.completed(ProgressStage.CLEANUP, "Copy lane cleanup scheduled.")
        progress.running(ProgressStage.COMPLETED, "Taxonomy copy rebuild completed.")
        progress.completed(ProgressStage.COMPLETED, "Taxonomy copy rebuild completed.")
        writer.write_manifest()
        return result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "active_taxonomy": actual}
    except Exception as exc:
        progress.failed(failed_stage, "Taxonomy copy rebuild failed.", errors=(f"{type(exc).__name__}: {exc}",))
        writer.write_error(exc)
        result = AdminFinalResult(
            run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.FAILED, mode="COPY_ONLY_APPLY",
            started_at_utc=started, completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint, request=request.as_dict(),
            rollback={"status": "DISPOSABLE_COPY_REMOVED" if not keep_copies else "COPY_RETAINED_FOR_INSPECTION"},
            errors=({"type": type(exc).__name__, "message": str(exc)},),
            downstream={"write_boundary_crossed": write_boundary_crossed, "production_writes": 0},
        )
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result.as_dict()))
        writer.checkpoint(RunStage.FAILED_AFTER_WRITE if write_boundary_crossed else RunStage.FAILED_BEFORE_WRITE, message=str(exc), preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(3 if write_boundary_crossed else 2)
        writer.write_manifest()
        raise
    finally:
        if lane is not None and not keep_copies:
            cleanup_copy_lane(lane)


def run_production_apply(
    *, preview_payload_path: Path, preview_fingerprint: str, test_run_id: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(), run_root: Path = ADMIN_RUN_ROOT,
    backup_root: Path | None = None, confirm_production: bool = False,
    progress_callback=None,
) -> dict[str, Any]:
    if not confirm_production:
        raise PermissionError("ADMIN_TAXONOMY_PRODUCTION_CONFIRMATION_REQUIRED")
    from rawcandle.fundamentals.admin.production_operations import TAXONOMY
    from rawcandle.fundamentals.admin.production_transaction import run_transaction

    return run_transaction(
        TAXONOMY, preview_payload_path=preview_payload_path,
        preview_fingerprint=preview_fingerprint, test_run_id=test_run_id,
        source_paths=source_paths, run_root=run_root, backup_root=backup_root,
        production_intent=True,
    )
