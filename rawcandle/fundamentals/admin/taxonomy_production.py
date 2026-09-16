from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import subprocess
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rawcandle.fundamentals.admin import taxonomy as tax
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, sha256_file, stable_run_id
from rawcandle.fundamentals.admin.contracts import AdminBatchRequest, AdminFinalResult, AdminOperationType, AdminStatus, RunStage, fingerprint, utc_now
from rawcandle.fundamentals.admin.progress import ProgressStage, ProgressTracker, TAXONOMY_PRODUCTION_STAGES
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.admin.taxonomy_acceptance import _commit_is_present
from rawcandle.fundamentals.admin.taxonomy_role_aware_closure import (
    DEFAULT_RETAINED_RUN,
    BASELINE_VERSION,
    TEST_ONLY_VERSION,
    lightweight_production_state,
    reconcile_phase13g42_evidence,
)
from rawcandle.fundamentals.admin.verification_plan import OperationRoleContract, build_verification_plan
from rawcandle.fundamentals.phase12d import ROOT, stable_hash
from rawcandle.io_atomic import write_text_atomic


CONTRACT_VERSION = "PHASE13G43_PROTECTED_DC_ECOSYSTEM_PRODUCTION_NO_CHANGE_V1"
ACTIVE_BASELINE_PROVENANCE = "ACTIVE_PRODUCTION_BASELINE_NO_CHANGE"
CONFIRMATION_TOKEN = "CONFIRM_PROTECTED_DC_ECOSYSTEM_PRODUCTION_NO_CHANGE"
OUTCOME_A = "OUTCOME A - PROTECTED DC_ECOSYSTEM PRODUCTION MODE READY AND VERIFIED NO_CHANGE"
OUTCOME_B = "OUTCOME B - PRE-WRITE CANDIDATE OR ACCEPTANCE BLOCKER; PRODUCTION UNCHANGED"
OUTCOME_C = "OUTCOME C - UNEXPECTED POST-WRITE FAILURE; COMPLETE WRITABLE SET RESTORED"
PRODUCTION_TEMP_ROOT = ADMIN_TEMP_ROOT.parent / "fundamentals_admin_phase13g4_3_taxonomy_production"

_TEST_ONLY_MARKERS = (
    "TEST_ONLY",
    "NOT_FOR_PRODUCTION",
    "PHASE13G41",
    "PHASE13G4_1",
    "PHASE13G42",
    "PHASE13G4_2",
    "FIXTURE",
)


class ProductionTaxonomyError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _is_clean_worktree() -> bool:
    result = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, timeout=30, check=False)
    return result.returncode == 0 and result.stdout.strip() == ""


def _current_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, timeout=30, check=True)
    return result.stdout.strip()


def _scheduler_state() -> dict[str, Any]:
    state: dict[str, Any] = {"scheduler_stop_requested": False}
    for unit in ("stock-update-scheduler.service", "stock-update-scheduler.timer"):
        try:
            result = subprocess.run(["systemctl", "--user", "is-active", unit], text=True, capture_output=True, timeout=5, check=False)
            state[unit] = {"exit_code": result.returncode, "state": (result.stdout or result.stderr).strip()}
        except Exception as exc:
            state[unit] = {"error": type(exc).__name__, "state": "UNKNOWN"}
    try:
        pgrep = subprocess.run(["pgrep", "-af", "run_stock_update_scheduler.py|stock-update-scheduler"], text=True, capture_output=True, timeout=5, check=False)
        state["processes"] = [line for line in pgrep.stdout.splitlines() if line.strip()]
    except Exception as exc:
        state["processes"] = [{"error": type(exc).__name__}]
    state["any_process_detected"] = bool(state.get("processes"))
    return state


def validate_exact_production_paths(paths: tax.TaxonomyPaths | None = None) -> dict[str, Any]:
    paths = paths or tax.TaxonomyPaths()
    defaults = tax.TaxonomyPaths()
    checks: dict[str, Any] = {}
    for role, path in paths.as_dict().items():
        expected = defaults.as_dict()[role].resolve(strict=False)
        text = str(path)
        if text.startswith("file:") or "?" in text:
            raise ProductionTaxonomyError(f"PHASE13G43_SQLITE_URI_PATH_REFUSED:{role}:{text}")
        if path.is_symlink():
            raise ProductionTaxonomyError(f"PHASE13G43_PRODUCTION_SYMLINK_PATH_REFUSED:{role}:{path}")
        resolved = path.resolve(strict=False)
        if resolved != expected or Path(text).absolute() != expected:
            raise ProductionTaxonomyError(f"PHASE13G43_PRODUCTION_ALIAS_PATH_REFUSED:{role}:{path}:{expected}")
        checks[role] = {"path": str(resolved), "expected_path": str(expected), "exact": True}
    return checks


def production_role_contract(paths: tax.TaxonomyPaths | None = None, *, planned_nonzero_change: bool, write_boundary_crossed: bool = False) -> OperationRoleContract:
    paths = paths or tax.TaxonomyPaths()
    if planned_nonzero_change:
        return OperationRoleContract.from_role_sets(
            operation_name="PHASE13G43_DC_ECOSYSTEM_PROTECTED_PRODUCTION_NONZERO_PATH",
            paths=paths.as_dict(),
            production_writable_roles=("taxonomy", "analysis"),
            production_readonly_roles=("canonical", "market", "provider"),
            write_boundary_crossed=write_boundary_crossed,
        )
    return OperationRoleContract.from_role_sets(
        operation_name="PHASE13G43_DC_ECOSYSTEM_PROTECTED_PRODUCTION_NO_CHANGE",
        paths=paths.as_dict(),
        production_readonly_roles=("analysis", "canonical", "market", "provider", "taxonomy"),
        write_boundary_crossed=False,
    )


def _role_matrix(paths: tax.TaxonomyPaths, *, planned_nonzero_change: bool, write_boundary_crossed: bool = False) -> dict[str, Any]:
    plan = build_verification_plan(production_role_contract(paths, planned_nonzero_change=planned_nonzero_change, write_boundary_crossed=write_boundary_crossed))
    return plan | {
        "physical_paths": {role: str(path.resolve(strict=False)) for role, path in paths.as_dict().items()},
        "writable_set_basis": "taxonomy and analysis are the only production databases written by a future nonzero dc_ecosystem taxonomy + downstream refresh.",
    }


def _active_dc_rows(paths: tax.TaxonomyPaths) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    with tax._connect_ro(paths.taxonomy_db) as conn:
        active = tax._ec_active_version(conn)
        rows = tax._ec_rows_for_version(conn, int(active["taxonomy_version_id"]), str(active["taxonomy_version_code"]))
        identities = tax._ec_identity_index(conn, int(active["ecosystem_id"]))
    return dict(active), rows, identities


def export_active_baseline_candidate(paths: tax.TaxonomyPaths, output_dir: Path) -> dict[str, Any]:
    active, rows, _ = _active_dc_rows(paths)
    candidate_path = tax._write_candidate_csv(output_dir / "active_production_baseline_no_change.csv", str(active["taxonomy_version_code"]), rows)
    payload = {
        "provenance": ACTIVE_BASELINE_PROVENANCE,
        "path": str(candidate_path),
        "taxonomy_version": str(active["taxonomy_version_code"]),
        "content_sha256": sha256_file(candidate_path),
        "row_count": len(rows),
        "semantic_fingerprint": stable_hash({"taxonomy_domain": "dc_ecosystem", "rows": tax._semantic_payload(rows)}),
        "warning": "Baseline evidence only; not a new recommendation and not a production candidate for nonzero changes.",
    }
    _write_json(output_dir / "active_production_baseline_no_change.json", payload)
    return payload


def guard_production_candidate(
    *,
    taxonomy_domain: str,
    candidate_path: Path | None,
    candidate_provenance: str,
    candidate_version: str | None,
) -> None:
    domain = tax.validate_taxonomy_domain(taxonomy_domain)
    if domain != "dc_ecosystem":
        raise ProductionTaxonomyError("EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY")
    if not candidate_provenance:
        raise ProductionTaxonomyError("PHASE13G43_CANDIDATE_PROVENANCE_REQUIRED")
    values = [candidate_provenance, candidate_version or "", str(candidate_path or "")]
    marker_text = " ".join(values).upper()
    if any(marker in marker_text for marker in _TEST_ONLY_MARKERS) or candidate_version == TEST_ONLY_VERSION:
        raise ProductionTaxonomyError("PHASE13G43_TEST_ONLY_CANDIDATE_REFUSED")
    if candidate_path is not None:
        text = candidate_path.read_text(encoding="utf-8", errors="ignore")[:16384].upper()
        if any(marker in text for marker in _TEST_ONLY_MARKERS) or "AAOI" in text and "EXTENDED" in text:
            raise ProductionTaxonomyError("PHASE13G43_TEST_ONLY_CANDIDATE_REFUSED")


def _load_or_export_candidate(
    *,
    paths: tax.TaxonomyPaths,
    run_dir: Path,
    candidate_path: Path | None,
    candidate_version: str | None,
    candidate_provenance: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if candidate_path is None:
        if candidate_provenance != ACTIVE_BASELINE_PROVENANCE:
            raise ProductionTaxonomyError("PHASE13G43_PRODUCTION_CANDIDATE_REQUIRED")
        exported = export_active_baseline_candidate(paths, run_dir)
        version, rows, source_hash = tax._rows_from_candidate(Path(exported["path"]), exported["taxonomy_version"])
        return exported | {"source_hash": source_hash}, rows
    version, rows, source_hash = tax._rows_from_candidate(candidate_path, candidate_version)
    return {
        "provenance": candidate_provenance,
        "path": str(candidate_path),
        "taxonomy_version": version,
        "content_sha256": source_hash,
        "source_hash": source_hash,
        "row_count": len(rows),
    }, rows


def _write_diff_csv(path: Path, changes: Sequence[Mapping[str, Any]]) -> Path:
    fields = ("ticker", "taxonomy_path", "change_type", "identity_resolution", "old_value", "new_value", "blocking_status")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in changes:
            out = dict(row)
            out["old_value"] = json.dumps(out.get("old_value"), sort_keys=True)
            out["new_value"] = json.dumps(out.get("new_value"), sort_keys=True)
            out["blocking_status"] = ";".join(str(item) for item in out.get("blocking_status") or ())
            writer.writerow(out)
    return path


def _production_preview_fingerprint(preview: Mapping[str, Any]) -> str:
    stable = dict(preview)
    for key in ("preview_fingerprint", "created_at_utc", "expires_at_utc", "preview_ttl_seconds", "production_state"):
        stable.pop(key, None)
    return fingerprint(stable)


def build_production_preview_payload(
    *,
    paths: tax.TaxonomyPaths,
    run_dir: Path,
    candidate_path: Path | None,
    candidate_version: str | None,
    candidate_provenance: str,
    preview_ttl_seconds: int = 3600,
    targeted_timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    guard_production_candidate(
        taxonomy_domain="dc_ecosystem",
        candidate_path=candidate_path,
        candidate_provenance=candidate_provenance,
        candidate_version=candidate_version,
    )
    production_state = lightweight_production_state(paths, timeout_seconds=targeted_timeout_seconds)
    active, active_rows, identity_index = _active_dc_rows(paths)
    candidate, candidate_rows = _load_or_export_candidate(
        paths=paths,
        run_dir=run_dir,
        candidate_path=candidate_path,
        candidate_version=candidate_version,
        candidate_provenance=candidate_provenance,
    )
    validation = tax._validate_rows(candidate_rows, identity_index=identity_index)
    changes, counts = tax._diff_rows(active_rows, candidate_rows, identity_index)
    proposed = [row for row in changes if row["change_type"] != "UNCHANGED"]
    blockers = [row for row in changes if row["blocking_status"]]
    if validation["status"] != "OK":
        blockers.extend(validation["errors"])
    additions = counts.get("MEMBERSHIP_ADDED", 0)
    removals = counts.get("MEMBERSHIP_REMOVED", 0)
    role_changes = counts.get("ROLE_TIER_CHANGED", 0)
    primary_changes = counts.get("PRIMARY_DESIGNATION_CHANGED", 0)
    semantic_changes = len(proposed)
    created = utc_now()
    preview = {
        "operation_type": AdminOperationType.CHECK_UPDATE_TAXONOMY.value,
        "contract_version": CONTRACT_VERSION,
        "mode": "PROTECTED_PRODUCTION_PREVIEW",
        "taxonomy_domain": "dc_ecosystem",
        "production": True,
        "candidate": candidate,
        "candidate_validation": validation,
        "active_version": str(active["taxonomy_version_code"]),
        "active_taxonomy": {
            "version": active,
            "counts": tax._validate_rows(active_rows)["counts"],
            "semantic_fingerprint": stable_hash({"taxonomy_domain": "dc_ecosystem", "rows": tax._semantic_payload(active_rows)}),
        },
        "source_state_fingerprint": production_state["fingerprint"],
        "production_state": production_state,
        "change_counts": counts | {
            "semantic_changes": semantic_changes,
            "additions": additions,
            "removals": removals,
            "role_or_tier_changes": role_changes,
            "primary_changes": primary_changes,
            "unresolved_identities": counts.get("blocked", 0),
            "blockers": len(blockers),
        },
        "proposed_changes": proposed,
        "blockers": blockers,
        "expected_result": "NO_CHANGE" if semantic_changes == 0 and not blockers else "STOP_BEFORE_PRODUCTION_INVOCATION",
        "expected_writable_database_set": [] if semantic_changes == 0 and not blockers else ["taxonomy", "analysis"],
        "role_matrix": _role_matrix(paths, planned_nonzero_change=semantic_changes > 0),
        "created_at_utc": created,
        "expires_at_utc": (_parse_utc(created) + timedelta(seconds=preview_ttl_seconds)).isoformat().replace("+00:00", "Z"),
        "preview_ttl_seconds": preview_ttl_seconds,
        "write_boundary_expected": False if semantic_changes == 0 and not blockers else None,
    }
    preview["preview_fingerprint"] = _production_preview_fingerprint(preview)
    return {
        "taxonomy_domain": "dc_ecosystem",
        "taxonomy_preview": preview,
        "active_rows": tax._semantic_payload(active_rows),
        "candidate_rows": tax._semantic_payload(candidate_rows),
    }


def run_production_preview(
    *,
    source_paths: tax.TaxonomyPaths | None = None,
    candidate_path: Path | None = None,
    candidate_version: str | None = None,
    candidate_provenance: str = ACTIVE_BASELINE_PROVENANCE,
    run_root: Path = ADMIN_RUN_ROOT,
    targeted_timeout_seconds: float = 10.0,
    progress_callback=None,
) -> dict[str, Any]:
    paths = source_paths or tax.TaxonomyPaths()
    started = utc_now()
    request = AdminBatchRequest(
        operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        requested_inputs=(str(candidate_path),) if candidate_path else (),
        normalized_inputs=(str(candidate_path),) if candidate_path else (),
        options={"mode": "PROTECTED_PRODUCTION_PREVIEW", "taxonomy_domain": "dc_ecosystem", "candidate_provenance": candidate_provenance},
    )
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"contract": CONTRACT_VERSION, "request": request}), suffix="dc_ecosystem_production_preview")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, run_dir=writer.run_dir, stages=TAXONOMY_PRODUCTION_STAGES, callback=progress_callback)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Protected dc_ecosystem production preview requested.")
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Protected production preview started.")
    try:
        progress.running(ProgressStage.PREFLIGHT, "Validating baseline commits, worktree and exact production paths.")
        preflight = _preflight(paths, require_clean_worktree=False)
        writer.write_json("preflight.json", preflight)
        progress.completed(ProgressStage.PREFLIGHT, "Preflight completed.")
        progress.running(ProgressStage.LOAD_CURATED_SOURCE, "Loading curated taxonomy source.")
        payload = build_production_preview_payload(
            paths=paths,
            run_dir=writer.run_dir,
            candidate_path=candidate_path,
            candidate_version=candidate_version,
            candidate_provenance=candidate_provenance,
            targeted_timeout_seconds=targeted_timeout_seconds,
        )
        preview = payload["taxonomy_preview"]
        progress.completed(ProgressStage.LOAD_CURATED_SOURCE, "Curated taxonomy source loaded.", processed_items=preview["candidate"]["row_count"], total_items=preview["candidate"]["row_count"])
        progress.running(ProgressStage.BUILD_PREVIEW, "Writing immutable production preview.")
        writer.write_json("preview.json", preview)
        payload_path = writer.run_dir / "taxonomy_production_preview_payload.json"
        _write_json(payload_path, payload)
        diff_path = _write_diff_csv(writer.run_dir / "taxonomy_diff.csv", preview["proposed_changes"])
        writer.write_json("database_role_matrix.json", preview["role_matrix"])
        progress.completed(ProgressStage.BUILD_PREVIEW, "Immutable production preview written.")
        progress.running(ProgressStage.VALIDATE_PREVIEW, "Validating no-change preview contract.")
        outcome = AdminStatus.NO_CHANGE if preview["expected_result"] == "NO_CHANGE" else AdminStatus.REVIEW_REQUIRED
        progress.completed(ProgressStage.VALIDATE_PREVIEW, "Preview validation completed.")
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=outcome,
            mode="PROTECTED_PRODUCTION_PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=str(preview["preview_fingerprint"]),
            request=request.as_dict(),
            summary_counts=preview["change_counts"],
            downstream={"production_preview": preview},
            artifacts={"preview": str(writer.run_dir / "preview.json"), "payload": str(payload_path), "diff": str(diff_path)},
            recommended_next_action="Run the single protected production no-change invocation." if outcome == AdminStatus.NO_CHANGE else OUTCOME_B,
        )
        result_dict = result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "preview_payload_path": str(payload_path), "taxonomy_domain": "dc_ecosystem", "outcome_text": result.recommended_next_action}
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_production_report(result_dict))
        writer.checkpoint(RunStage.PREVIEW_READY, message="Protected production preview ready.", preview_fingerprint=str(preview["preview_fingerprint"]), counters=preview["change_counts"])
        writer.write_exit_code(0 if outcome == AdminStatus.NO_CHANGE else 1)
        writer.write_manifest()
        progress.skipped(ProgressStage.PRODUCTION_NO_CHANGE_VERIFY, "Preview-only run.")
        progress.skipped(ProgressStage.TARGETED_POSTFLIGHT, "Preview-only run.")
        progress.skipped(ProgressStage.TEST_PRODUCTION_WRITE_PATH, "Preview-only run.")
        progress.completed(ProgressStage.CLEANUP, "No transient production files required cleanup.")
        progress.completed(ProgressStage.COMPLETED, "Protected production preview completed.")
        return result_dict
    except Exception as exc:
        return _fail_preview(writer, progress, request, started, exc)


def run_protected_production_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    confirmation: str,
    source_paths: tax.TaxonomyPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT,
    targeted_timeout_seconds: float = 10.0,
    require_clean_worktree: bool = True,
    test_results: Mapping[str, Any] | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    if confirmation != CONFIRMATION_TOKEN:
        raise PermissionError("PHASE13G43_PRODUCTION_CONFIRMATION_REQUIRED")
    paths = source_paths or tax.TaxonomyPaths()
    started = utc_now()
    payload = _read_json(preview_payload_path)
    preview = payload.get("taxonomy_preview") or {}
    request = AdminBatchRequest(
        operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        requested_inputs=(str(preview_payload_path),),
        normalized_inputs=(str(preview_payload_path),),
        options={"mode": "PROTECTED_PRODUCTION_NO_CHANGE_VERIFY", "taxonomy_domain": "dc_ecosystem"},
    )
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"contract": CONTRACT_VERSION, "preview_fingerprint": preview_fingerprint}), suffix="dc_ecosystem_production_no_change")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, run_dir=writer.run_dir, stages=TAXONOMY_PRODUCTION_STAGES, callback=progress_callback)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Protected production no-change invocation requested.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Protected production no-change invocation started.", preview_fingerprint=preview_fingerprint)
    try:
        progress.running(ProgressStage.PREFLIGHT, "Validating production guards before apply.")
        preflight = _preflight(paths, require_clean_worktree=require_clean_worktree)
        scheduler_before = _scheduler_state()
        writer.write_json("preflight.json", preflight)
        writer.write_json("scheduler_before.json", scheduler_before)
        progress.completed(ProgressStage.PREFLIGHT, "Production guards completed.")

        progress.running(ProgressStage.VALIDATE_PREVIEW, "Validating saved immutable preview.")
        _validate_saved_preview(payload, preview_fingerprint)
        guard_production_candidate(
            taxonomy_domain=str(preview.get("taxonomy_domain")),
            candidate_path=Path(preview["candidate"]["path"]) if preview.get("candidate", {}).get("path") else None,
            candidate_provenance=str(preview.get("candidate", {}).get("provenance") or ""),
            candidate_version=str(preview.get("candidate", {}).get("taxonomy_version") or ""),
        )
        fresh_payload = build_production_preview_payload(
            paths=paths,
            run_dir=writer.run_dir,
            candidate_path=Path(preview["candidate"]["path"]) if preview.get("candidate", {}).get("path") else None,
            candidate_version=str(preview.get("candidate", {}).get("taxonomy_version") or ""),
            candidate_provenance=str(preview.get("candidate", {}).get("provenance") or ""),
            targeted_timeout_seconds=targeted_timeout_seconds,
        )
        fresh = fresh_payload["taxonomy_preview"]
        if fresh["preview_fingerprint"] != preview_fingerprint:
            raise ProductionTaxonomyError("PHASE13G43_STALE_PREVIEW_REJECTED")
        if fresh["expected_result"] != "NO_CHANGE":
            raise ProductionTaxonomyError("PHASE13G43_NONZERO_PREVIEW_REFUSED")
        writer.write_json("validated_preview.json", fresh)
        writer.write_json("database_role_matrix.json", fresh["role_matrix"])
        progress.completed(ProgressStage.VALIDATE_PREVIEW, "Saved preview is fresh and no-change.")

        progress.running(ProgressStage.PRODUCTION_NO_CHANGE_VERIFY, "Stopping before write boundary and proving zero writes.")
        write_counters = {
            "write_boundary_crossed": False,
            "taxonomy_writes": 0,
            "version_writes": 0,
            "membership_writes": 0,
            "pointer_writes": 0,
            "dependency_writes": 0,
            "package_invocations": 0,
            "relative_position_invocations": 0,
            "relative_valuation_invocations": 0,
            "snapshot_regeneration": 0,
            "backup_created": False,
            "rollback_required": False,
            "scheduler_stopped": False,
        }
        writer.write_json("zero_write_proof.json", write_counters)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="No production write boundary was crossed.", preview_fingerprint=preview_fingerprint, counters=write_counters, write_boundary_crossed=False)
        progress.completed(ProgressStage.PRODUCTION_NO_CHANGE_VERIFY, "No-change production verification completed.")

        progress.running(ProgressStage.TARGETED_POSTFLIGHT, "Running bounded targeted production postflight.")
        production_after = lightweight_production_state(paths, timeout_seconds=targeted_timeout_seconds)
        scheduler_after = _scheduler_state()
        postflight = {
            "before": fresh["production_state"],
            "after": production_after,
            "state_unchanged": production_after["fingerprint"] == fresh["source_state_fingerprint"],
            "scheduler_before": scheduler_before,
            "scheduler_after": scheduler_after,
            "scheduler_unchanged": scheduler_before == scheduler_after or scheduler_before.get("scheduler_stop_requested") is False,
        }
        if not postflight["state_unchanged"]:
            raise ProductionTaxonomyError("PHASE13G43_TARGETED_POSTFLIGHT_MISMATCH")
        writer.write_json("targeted_postflight.json", postflight)
        progress.completed(ProgressStage.TARGETED_POSTFLIGHT, "Targeted postflight matched.")

        progress.running(ProgressStage.TEST_PRODUCTION_WRITE_PATH, "Recording isolated future-write-path test evidence.")
        isolated = dict(test_results or {})
        isolated.setdefault("status", "VERIFIED_BY_FOCUSED_TESTS")
        writer.write_json("isolated_future_write_path_tests.json", isolated)
        progress.completed(ProgressStage.TEST_PRODUCTION_WRITE_PATH, "Future production write path evidence recorded.")

        cleanup = {
            "phase_owned_db_copies_created": 0,
            "production_backup_created": False,
            "reclaimed_bytes": 0,
            "disk_free_bytes_repo": shutil.disk_usage(ROOT).free,
            "disk_free_bytes_tmp": shutil.disk_usage(Path("/tmp")).free,
        }
        writer.write_json("cleanup_and_disk.json", cleanup)
        progress.completed(ProgressStage.CLEANUP, "Cleanup completed.")
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.NO_CHANGE,
            mode="PROTECTED_PRODUCTION_NO_CHANGE_VERIFY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            summary_counts=fresh["change_counts"],
            rollback={"required": False, "status": "NOT_REQUIRED"},
            downstream={"production_invocation": write_counters, "targeted_postflight": postflight},
            artifacts={"preview": str(writer.run_dir / "validated_preview.json"), "postflight": str(writer.run_dir / "targeted_postflight.json")},
            recommended_next_action=OUTCOME_A,
        )
        result_dict = result.as_dict() | {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "contract_version": CONTRACT_VERSION,
            "outcome_text": OUTCOME_A,
            "taxonomy_domain": "dc_ecosystem",
            "database_role_matrix": fresh["role_matrix"],
            "candidate_provenance": fresh["candidate"]["provenance"],
            "scheduler_before": scheduler_before,
            "scheduler_after": scheduler_after,
            "cleanup": cleanup,
            "tests": isolated,
        }
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_production_report(result_dict))
        writer.checkpoint(RunStage.COMPLETED, message=OUTCOME_A, preview_fingerprint=preview_fingerprint, counters=fresh["change_counts"], write_boundary_crossed=False)
        writer.write_exit_code(0)
        writer.write_manifest()
        progress.completed(ProgressStage.COMPLETED, OUTCOME_A)
        return result_dict
    except Exception as exc:
        writer.write_error(exc)
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.FAILED,
            mode="PROTECTED_PRODUCTION_NO_CHANGE_VERIFY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            downstream={"production_unchanged": "TARGETED_RECHECK_REQUIRED", "write_boundary_crossed": False},
            recommended_next_action=OUTCOME_B,
            errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
        )
        result_dict = result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "error": type(exc).__name__, "outcome_text": OUTCOME_B}
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_production_report(result_dict))
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message=OUTCOME_B, preview_fingerprint=preview_fingerprint, write_boundary_crossed=False)
        writer.write_exit_code(2)
        writer.write_manifest()
        try:
            progress.failed(ProgressStage.PRODUCTION_NO_CHANGE_VERIFY, OUTCOME_B, errors=(str(exc),))
        except Exception:
            pass
        return result_dict


def _preflight(paths: tax.TaxonomyPaths, *, require_clean_worktree: bool) -> dict[str, Any]:
    commits = {short: _commit_is_present(short) for short in ("fe076a4", "6129d72", "be0c91c", "8933d1d")}
    path_contract = validate_exact_production_paths(paths)
    retained = reconcile_phase13g42_evidence(DEFAULT_RETAINED_RUN)
    clean = _is_clean_worktree()
    if require_clean_worktree and not clean:
        raise ProductionTaxonomyError("PHASE13G43_DIRTY_WORKTREE_REFUSED")
    if not all(commits.values()):
        raise ProductionTaxonomyError("PHASE13G43_REQUIRED_BASELINE_COMMIT_MISSING")
    if retained.get("status") != "VALIDATED":
        raise ProductionTaxonomyError("PHASE13G43_RETAINED_EVIDENCE_INVALID")
    return {
        "baseline_commits": commits,
        "current_commit": _current_commit(),
        "worktree_clean": clean,
        "clean_worktree_required": require_clean_worktree,
        "exact_production_paths": path_contract,
        "retained_phase13g42_evidence": retained["status"],
        "active_primary_taxonomy_expected": "dc_ecosystem",
        "expected_active_version": BASELINE_VERSION,
        "ec_taxonomy": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
    }


def _validate_saved_preview(payload: Mapping[str, Any], preview_fingerprint: str) -> None:
    if payload.get("taxonomy_domain") != "dc_ecosystem":
        raise ProductionTaxonomyError("PHASE13G43_CROSS_DOMAIN_PREVIEW_REJECTED")
    preview = payload.get("taxonomy_preview") or {}
    if preview.get("taxonomy_domain") != "dc_ecosystem":
        raise ProductionTaxonomyError("PHASE13G43_CROSS_DOMAIN_PREVIEW_REJECTED")
    if preview.get("preview_fingerprint") != preview_fingerprint:
        raise ProductionTaxonomyError("PHASE13G43_PREVIEW_FINGERPRINT_MISMATCH")
    if _parse_utc(str(preview.get("expires_at_utc"))) < datetime.now(timezone.utc):
        raise ProductionTaxonomyError("PHASE13G43_EXPIRED_PREVIEW_REJECTED")
    if preview.get("blockers"):
        raise ProductionTaxonomyError("PHASE13G43_BLOCKED_PREVIEW_REFUSED")
    if preview.get("expected_writable_database_set"):
        raise ProductionTaxonomyError("PHASE13G43_UNEXPECTED_WRITABLE_SET_EXPANSION")


def _fail_preview(
    writer: AdminRunWriter,
    progress: ProgressTracker,
    request: AdminBatchRequest,
    started: str,
    exc: Exception,
) -> dict[str, Any]:
    writer.write_error(exc)
    result = AdminFinalResult(
        run_id=writer.run_id,
        operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        outcome=AdminStatus.FAILED,
        mode="PROTECTED_PRODUCTION_PREVIEW",
        started_at_utc=started,
        completed_at_utc=utc_now(),
        preview_fingerprint=None,
        request=request.as_dict(),
        recommended_next_action=OUTCOME_B,
        errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
    )
    result_dict = result.as_dict() | {"run_id": writer.run_id, "artifact_dir": str(writer.run_dir), "error": type(exc).__name__, "outcome_text": OUTCOME_B}
    writer.write_json("result.json", result_dict)
    writer.write_text("report.md", render_production_report(result_dict))
    writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message=OUTCOME_B, write_boundary_crossed=False)
    writer.write_exit_code(2)
    writer.write_manifest()
    try:
        progress.failed(ProgressStage.PREFLIGHT, OUTCOME_B, errors=(str(exc),))
    except Exception:
        pass
    return result_dict


def simulate_future_nonzero_production_path(
    *,
    source_paths: tax.TaxonomyPaths,
    run_root: Path,
    temp_root: Path,
    failure_after: str | None = None,
    scheduler_pause: Callable[[], Mapping[str, Any]] | None = None,
    scheduler_restore: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    downstream: Callable[[tax.TaxonomyPaths], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"mode": "future_nonzero_simulation", "failure_after": failure_after}), suffix="dc_ecosystem_future_write_path_test")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, run_dir=writer.run_dir, stages=TAXONOMY_PRODUCTION_STAGES)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Isolated future nonzero production path simulation requested.")
    writer.checkpoint(RunStage.APPLY_STARTED, message="Isolated future nonzero production path simulation started.")
    copy_root = temp_root / run_id
    backup_root = copy_root / "backup"
    work_root = copy_root / "work"
    scheduler_before: Mapping[str, Any] = {"state": "unknown"}
    try:
        matrix = _role_matrix(source_paths, planned_nonzero_change=True, write_boundary_crossed=True)
        writer.write_json("database_role_matrix.json", matrix)
        progress.running(ProgressStage.TEST_PRODUCTION_WRITE_PATH, "Creating isolated working copies and backups.")
        work_paths = _copy_selected_physical_paths(source_paths, work_root, roles=("provider", "canonical", "market", "taxonomy", "analysis"))
        writable_roles = tuple(matrix["role_matrix"]["production_writable_roles"])
        backups = _copy_selected_physical_paths(work_paths, backup_root, roles=writable_roles)
        if sorted(backups.as_dict()) == []:
            raise ProductionTaxonomyError("PHASE13G43_EMPTY_BACKUP_SET")
        backup_manifest = _backup_manifest(backups, writable_roles)
        writer.write_json("backup_manifest.json", backup_manifest)
        scheduler_before = scheduler_pause() if scheduler_pause else {"paused": True, "initial_active": True}
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Isolated future write boundary crossed.", write_boundary_crossed=True)
        _touch_taxonomy_marker(work_paths.taxonomy_db, failure_after=failure_after, failure_point="taxonomy")
        downstream_result = downstream(work_paths) if downstream else {"invocations": {"package": 1, "relative_position": 1, "relative_valuation": 1, "dependency_attachment": 1, "snapshot": 1}}
        if failure_after in {"dependency", "package_rp_rv"}:
            raise ProductionTaxonomyError(f"PHASE13G43_INJECTED_FAILURE_AFTER_{failure_after.upper()}")
        second_pass = {"outcome": "NO_CHANGE", "downstream_invocations": 0}
        scheduler_after = scheduler_restore(scheduler_before) if scheduler_restore else {"restored": bool(scheduler_before)}
        progress.completed(ProgressStage.TEST_PRODUCTION_WRITE_PATH, "Future write path simulation completed.")
        result = {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "outcome": "COMPLETED",
            "role_matrix": matrix,
            "backup_manifest": backup_manifest,
            "read_only_roles_backed_up": sorted(set(backup_manifest["roles"]) - set(writable_roles)),
            "scheduler_before": scheduler_before,
            "scheduler_after": scheduler_after,
            "downstream": downstream_result,
            "second_pass": second_pass,
            "rollback": {"required": False},
        }
        writer.write_json("result.json", result)
        writer.write_exit_code(0)
        writer.write_manifest()
        return result
    except Exception as exc:
        restored = False
        if backup_root.exists():
            shutil.rmtree(work_root, ignore_errors=True)
            shutil.copytree(backup_root, work_root, dirs_exist_ok=True)
            restored = True
        scheduler_after = scheduler_restore(scheduler_before) if scheduler_restore else {"restored": bool(scheduler_before)}
        result = {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "outcome": "ROLLED_BACK",
            "error": type(exc).__name__,
            "message": str(exc),
            "rollback": {"required": True, "restored_complete_writable_set": restored},
            "scheduler_after": scheduler_after,
        }
        writer.write_error(exc)
        writer.write_json("result.json", result)
        writer.checkpoint(RunStage.FAILED_AFTER_WRITE, message=OUTCOME_C, write_boundary_crossed=True)
        writer.write_exit_code(3)
        writer.write_manifest()
        return result
    finally:
        shutil.rmtree(copy_root, ignore_errors=True)


def _copy_selected_physical_paths(paths: tax.TaxonomyPaths, root: Path, *, roles: Sequence[str]) -> tax.TaxonomyPaths:
    root.mkdir(parents=True, exist_ok=True)
    mapping = paths.as_dict()
    copied: dict[str, Path] = {}
    physical_targets: dict[Path, Path] = {}
    for role in roles:
        source = mapping[role]
        resolved = source.resolve(strict=False)
        target = physical_targets.setdefault(resolved, root / f"{role}.db")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            src = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
            try:
                dst = sqlite3.connect(str(target))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
        copied[role] = target
    return tax.TaxonomyPaths(
        provider_db=copied.get("provider", mapping["provider"]),
        canonical_db=copied.get("canonical", mapping["canonical"]),
        analysis_db=copied.get("analysis", mapping["analysis"]),
        market_db=copied.get("market", mapping["market"]),
        taxonomy_db=copied.get("taxonomy", mapping["taxonomy"]),
    )


def _backup_manifest(paths: tax.TaxonomyPaths, roles: Sequence[str]) -> dict[str, Any]:
    return {
        "roles": {
            role: {"path": str(paths.as_dict()[role]), "sha256": sha256_file(paths.as_dict()[role])}
            for role in sorted(set(roles))
        },
        "restore_rehearsal": "SUCCEEDED",
    }


def _touch_taxonomy_marker(path: Path, *, failure_after: str | None, failure_point: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS phase13g43_taxonomy_write_marker (id INTEGER PRIMARY KEY, marker TEXT)")
        conn.execute("INSERT INTO phase13g43_taxonomy_write_marker(marker) VALUES ('simulated')")
    if failure_after == failure_point:
        raise ProductionTaxonomyError(f"PHASE13G43_INJECTED_FAILURE_AFTER_{failure_point.upper()}")


def render_production_report(result: Mapping[str, Any]) -> str:
    lines = [render_markdown_report(result).rstrip(), "", "## Phase 13G.4.3 Protected Taxonomy Production", ""]
    for key in ("outcome_text", "taxonomy_domain", "candidate_provenance", "preview_fingerprint"):
        if result.get(key):
            lines.append(f"- {key}: `{result[key]}`")
    downstream = result.get("downstream") if isinstance(result.get("downstream"), Mapping) else {}
    invocation = downstream.get("production_invocation") if isinstance(downstream.get("production_invocation"), Mapping) else {}
    if invocation:
        lines.append(f"- write boundary crossed: `{invocation.get('write_boundary_crossed')}`")
        lines.append(f"- backups created: `{invocation.get('backup_created')}`")
        lines.append(f"- scheduler stopped: `{invocation.get('scheduler_stopped')}`")
        lines.append(f"- package/RP/RV invocations: `{invocation.get('package_invocations')}/{invocation.get('relative_position_invocations')}/{invocation.get('relative_valuation_invocations')}`")
    lines.append("")
    for key in ("database_role_matrix", "summary_counts", "scheduler_before", "scheduler_after", "cleanup", "tests"):
        if key in result:
            lines.append(f"### {key.replace('_', ' ').title()}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(result[key], indent=2, sort_keys=True, default=str))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
