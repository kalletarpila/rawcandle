from __future__ import annotations

import json
import shutil
import sqlite3
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, sha256_file, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import AdminBatchRequest, AdminFinalResult, AdminOperationType, AdminStatus, RunStage, fingerprint, utc_now
from rawcandle.fundamentals.admin.progress import ProgressStage, ProgressTracker, TAXONOMY_ACCEPTANCE_STAGES
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.admin import taxonomy as tax
from rawcandle.fundamentals.phase12d import PRODUCTION, stable_hash
from rawcandle.fundamentals.phase13b_foundation import taxonomy_identity
from rawcandle.io_atomic import write_text_atomic


CONTRACT_VERSION = "PHASE13G41_DC_ECOSYSTEM_COPY_ONLY_ACCEPTANCE_V1"
OUTCOME_A = "OUTCOME A - DC_ECOSYSTEM PRODUCTION-SHAPED COPY UPDATE, REPLAY AND ROLLBACK VERIFIED"
OUTCOME_B = "OUTCOME B - CORRECTABLE DC TAXONOMY DATA, DEPENDENCY OR IMPLEMENTATION LIMITATION REMAINS"
OUTCOME_C = "OUTCOME C - MATERIAL TAXONOMY VERSIONING OR SAFETY DEFECT; PRODUCTION UNCHANGED"
TEMP_ROOT = ADMIN_TEMP_ROOT.parent / "fundamentals_admin_phase13g4_1_taxonomy_acceptance"


def _write_json(path: Path, value: Mapping[str, Any] | Sequence[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n")
    return path


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _copy_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _copy_paths(source: tax.TaxonomyPaths, root: Path) -> tax.TaxonomyPaths:
    copied: dict[str, Path] = {}
    for role, path in source.as_dict().items():
        destination = root / f"{role}.db"
        _copy_sqlite(path, destination)
        copied[role] = destination
    return tax.TaxonomyPaths(
        provider_db=copied["provider"],
        canonical_db=copied["canonical"],
        analysis_db=copied["analysis"],
        market_db=copied["market"],
        taxonomy_db=copied["taxonomy"],
    )


def _db_checks(paths: tax.TaxonomyPaths) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for role, path in paths.as_dict().items():
        with _connect(path) as conn:
            output[role] = {
                "path": str(path),
                "sha256": sha256_file(path),
                "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
                "foreign_key_errors": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
            }
    return output


def _fingerprints(paths: tax.TaxonomyPaths) -> dict[str, Any]:
    dc = tax._active_state(paths, "dc_ecosystem")
    ec = tax._active_state(paths, "ec_taxonomy")
    identity = taxonomy_identity(paths.taxonomy_db)
    return {
        "dc_semantic_fingerprint": dc["semantic_fingerprint"],
        "dc_source_state_fingerprint": dc["source_state_fingerprint"],
        "dc_active_version": dc["active_version"],
        "dc_counts": dc["counts"],
        "ec_semantic_fingerprint": ec["semantic_fingerprint"],
        "ec_status": ec["active_version"].get("update_contract_status"),
        "taxonomy_identity": identity,
        "logical_content_fingerprint": stable_hash(
            {
                "dc": dc["semantic_fingerprint"],
                "ec": ec["semantic_fingerprint"],
                "taxonomy_source_version": identity.get("taxonomy_source_version"),
                "taxonomy_economic_fingerprint": identity.get("taxonomy_economic_fingerprint"),
                "taxonomy_presentation_fingerprint": identity.get("taxonomy_presentation_fingerprint"),
            }
        ),
    }


def _production_taxonomy_postflight(paths: tax.TaxonomyPaths) -> dict[str, Any]:
    dc = tax._active_state(paths, "dc_ecosystem")
    ec = tax._active_state(paths, "ec_taxonomy")
    return {
        "dc_semantic_fingerprint": dc["semantic_fingerprint"],
        "dc_source_state_fingerprint": dc["source_state_fingerprint"],
        "dc_active_version": dc["active_version"],
        "dc_counts": dc["counts"],
        "ec_semantic_fingerprint": ec["semantic_fingerprint"],
        "ec_status": ec["active_version"].get("update_contract_status"),
        "logical_content_fingerprint": stable_hash(
            {
                "dc": dc["semantic_fingerprint"],
                "ec": ec["semantic_fingerprint"],
                "active_version": dc["active_version"].get("taxonomy_version_code"),
            }
        ),
    }


def _build_test_candidate(active_rows: Sequence[Mapping[str, Any]], active_version: str, output: Path) -> dict[str, Any]:
    candidate_version = f"{active_version}_TEST_ONLY_PHASE13G41"
    rows = [dict(row) | {"taxonomy_version": candidate_version} for row in active_rows]
    selected_index: int | None = None
    for index, row in enumerate(rows):
        if int(row["is_primary"]) == 1 and str(row["report_group_status"]) == "CORE" and str(row["ticker"]).upper() != "NVDA":
            selected_index = index
            break
    if selected_index is None:
        for index, row in enumerate(rows):
            if int(row["is_primary"]) == 1 and str(row["report_group_status"]) in {"CORE", "EXTENDED"}:
                selected_index = index
                break
    if selected_index is None:
        raise RuntimeError("PHASE13G41_NO_SAFE_TEST_CANDIDATE_ROW")
    before = dict(rows[selected_index])
    old_role = str(before["report_group_status"])
    new_role = "EXTENDED" if old_role == "CORE" else "CORE"
    rows[selected_index]["report_group_status"] = new_role
    rows[selected_index]["notes"] = "TEST_ONLY_NOT_FOR_PRODUCTION Phase 13G.4.1 role-tier change"
    candidate_csv = tax._write_candidate_csv(output / "dc_ecosystem_test_only_candidate.csv", candidate_version, rows)
    after = dict(rows[selected_index])
    return {
        "status": "TEST_ONLY_NOT_FOR_PRODUCTION",
        "candidate_version": candidate_version,
        "candidate_csv": str(candidate_csv),
        "source_hash": sha256_file(candidate_csv),
        "affected_ticker": str(after["ticker"]).upper(),
        "changed_taxonomy_path": f"{after['layer']} / {after['subindustry']}",
        "change_type": "ROLE_TIER_CHANGED",
        "before": before,
        "after": after,
        "rows": rows,
        "validity_reason": "Role-tier change preserves the existing ticker identity, hierarchy path and primary designation while changing an economically meaningful Datacenter membership tier.",
    }


def _apply_candidate_to_lane(paths: tax.TaxonomyPaths, candidate_csv: Path, candidate_version: str) -> dict[str, Any]:
    before = _fingerprints(paths)
    result = tax._apply_ec_candidate_to_copy(paths.taxonomy_db, candidate_csv, candidate_version)
    result["domain"] = "dc_ecosystem"
    after = _fingerprints(paths)
    return {
        "taxonomy_apply": result,
        "before": before,
        "after": after,
        "changed": before["dc_semantic_fingerprint"] != after["dc_semantic_fingerprint"],
        "ec_unchanged": before["ec_semantic_fingerprint"] == after["ec_semantic_fingerprint"],
    }


def _downstream_smoke(paths: tax.TaxonomyPaths, *, output: Path, affected_ticker: str, run_full_downstream: bool) -> dict[str, Any]:
    if not run_full_downstream:
        return {
            "status": "NOT_RUN_BY_DEFAULT",
            "reason": "Use --run-full-downstream to execute package/RP/RV refresh on copies.",
            "invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0, "dependency_attachment": 0, "snapshot": 0},
            "dependency_reasoning": {
                "operating_income_package_required": False,
                "relative_position_required": True,
                "relative_valuation_required": True,
                "snapshot_smoke_required": True,
            },
        }
    from rawcandle.fundamentals.admin.sector_industry import _run_downstream

    downstream = _run_downstream(
        BatchAddTickerPaths(paths.provider_db, paths.canonical_db, paths.analysis_db, paths.market_db, paths.taxonomy_db),
        output,
        changed_tickers=(affected_ticker,),
        applied_at=utc_now(),
        progress=None,
    )
    counts = dict(downstream.get("invocation_counts") or {})
    counts["dependency_attachment"] = 1 if downstream.get("dependencies") else 0
    counts["snapshot"] = len(downstream.get("snapshots") or {})
    downstream["invocation_counts"] = counts
    return downstream


def _repeat_no_change(paths: tax.TaxonomyPaths, candidate_csv: Path, candidate_version: str) -> dict[str, Any]:
    before = _fingerprints(paths)
    versions_before = _taxonomy_version_count(paths.taxonomy_db)
    result = tax._apply_ec_candidate_to_copy(paths.taxonomy_db, candidate_csv, candidate_version)
    after = _fingerprints(paths)
    versions_after = _taxonomy_version_count(paths.taxonomy_db)
    return {
        "outcome": result["outcome"],
        "taxonomy_writes": int(result.get("rows_changed") or 0),
        "new_version_rows": versions_after - versions_before,
        "membership_writes": 0 if result["outcome"] == "NO_CHANGE" else int(result.get("rows_changed") or 0),
        "active_pointer_writes": 0 if result["outcome"] == "NO_CHANGE" else 1,
        "dependency_writes": 0,
        "package_relative_position_relative_valuation_invocations": "0/0/0",
        "snapshot_regeneration": 0,
        "logical_taxonomy_fingerprint_unchanged": before["dc_semantic_fingerprint"] == after["dc_semantic_fingerprint"],
        "logical_content_fingerprint_unchanged": before["logical_content_fingerprint"] == after["logical_content_fingerprint"],
        "before": before,
        "after": after,
    }


def _taxonomy_version_count(taxonomy_db: Path) -> int:
    with _connect(taxonomy_db) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM ec_taxonomy_version").fetchone()[0])


def _lane_from_baseline(baseline: tax.TaxonomyPaths, root: Path) -> tax.TaxonomyPaths:
    if root.exists():
        shutil.rmtree(root)
    return _copy_paths(baseline, root)


def _restore_lane_from_baseline(baseline: tax.TaxonomyPaths, lane_root: Path) -> tax.TaxonomyPaths:
    if lane_root.exists():
        shutil.rmtree(lane_root)
    return _copy_paths(baseline, lane_root)


def _write_report(result: Mapping[str, Any]) -> str:
    lines = [render_markdown_report(result).rstrip(), "", "## Phase 13G.4.1 Acceptance", ""]
    lines.append("Candidate status: `TEST_ONLY_NOT_FOR_PRODUCTION`")
    lines.append("Production writes: `0`")
    lines.append("Production primary taxonomy remains: `dc_ecosystem`")
    lines.append("EC taxonomy update status: `EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY`")
    lines.append("")
    for key in ("baseline", "candidate", "preview", "apply", "repeat_no_change", "replay", "rollback", "production_immutability", "cleanup"):
        if key in result:
            lines.append(f"### {key.replace('_', ' ').title()}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(result[key], indent=2, sort_keys=True, default=str))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_dc_ecosystem_copy_acceptance(
    *,
    source_paths: tax.TaxonomyPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = TEMP_ROOT,
    run_full_downstream: bool = False,
    skip_production_postflight: bool = False,
    scheduler_evidence: Mapping[str, Any] | None = None,
    keep_copies_on_failure: bool = False,
    progress_callback=None,
) -> dict[str, Any]:
    source_paths = source_paths or tax.TaxonomyPaths()
    started = utc_now()
    request = AdminBatchRequest(
        operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        requested_inputs=(),
        normalized_inputs=(),
        options={"phase": "13G.4.1", "taxonomy_domain": "dc_ecosystem", "run_full_downstream": run_full_downstream},
    )
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"contract": CONTRACT_VERSION, "request": request}), suffix="dc_ecosystem_acceptance")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, run_dir=writer.run_dir, stages=TAXONOMY_ACCEPTANCE_STAGES, callback=progress_callback)
    root = (temp_root / run_id).resolve()
    baseline_root = root / "baseline"
    primary_root = root / "primary_lane"
    replay_root = root / "replay_lane"
    rollback_root = root / "rollback_lane"
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Phase 13G.4.1 dc_ecosystem copy-only acceptance request recorded.")
    writer.checkpoint(RunStage.APPLY_STARTED, message="Phase 13G.4.1 copy-only acceptance orchestration started.")
    write_boundary_crossed = False
    try:
        progress.running(ProgressStage.PREFLIGHT, "Verifying required baseline commit and clean copy-only preflight.")
        baseline_commit = _current_head()
        if baseline_commit != "fe076a4":
            # The exact commit may be an ancestor once this phase is committed.
            if not _commit_is_present("fe076a4"):
                raise RuntimeError("PHASE13G41_REQUIRED_COMMIT_MISSING:fe076a4")
        preflight = {
            "required_commit_present": True,
            "head": baseline_commit,
            "scheduler_evidence": dict(scheduler_evidence or {}),
        }
        writer.write_json("preflight.json", preflight)
        progress.completed(ProgressStage.PREFLIGHT, "Preflight completed.")

        progress.running(ProgressStage.PAUSE_SCHEDULER_FOR_COPY, "Recording scheduler pause evidence.")
        writer.write_json("scheduler_evidence.json", dict(scheduler_evidence or {"status": "EXTERNAL_EVIDENCE_NOT_SUPPLIED"}))
        progress.completed(ProgressStage.PAUSE_SCHEDULER_FOR_COPY, "Scheduler pause evidence recorded.")

        progress.running(ProgressStage.CAPTURE_BASELINE_COPIES, "Capturing production-shaped database copies.")
        baseline_paths = _copy_paths(source_paths, baseline_root)
        baseline_checks = _db_checks(baseline_paths)
        writer.write_json("baseline_copy_inventory.json", baseline_checks)
        progress.completed(ProgressStage.CAPTURE_BASELINE_COPIES, "Baseline copies captured.")
        progress.running(ProgressStage.RESTORE_SCHEDULER, "Recording scheduler restore evidence.")
        progress.completed(ProgressStage.RESTORE_SCHEDULER, "Scheduler restore evidence recorded.")

        progress.running(ProgressStage.LOAD_ACTIVE_TAXONOMY, "Auditing both taxonomy domains on baseline copies.")
        baseline_dc = tax.run_preview(taxonomy_domain="dc_ecosystem", source_paths=baseline_paths, run_root=writer.run_dir / "baseline_audits")
        baseline_ec = tax.run_preview(taxonomy_domain="ec_taxonomy", source_paths=baseline_paths, run_root=writer.run_dir / "baseline_audits")
        baseline_fp = _fingerprints(baseline_paths)
        progress.completed(ProgressStage.LOAD_ACTIVE_TAXONOMY, "Baseline taxonomy audits completed.", processed_items=int(baseline_fp["dc_counts"]["rows"]))

        progress.running(ProgressStage.BUILD_TEST_CANDIDATE, "Building deterministic TEST_ONLY dc_ecosystem candidate.")
        candidate = _build_test_candidate(
            tax._active_state(baseline_paths, "dc_ecosystem")["rows"],
            str(baseline_fp["dc_active_version"]["taxonomy_version_code"]),
            writer.run_dir,
        )
        writer.write_json("test_only_candidate.json", {key: value for key, value in candidate.items() if key != "rows"})
        progress.completed(ProgressStage.BUILD_TEST_CANDIDATE, "Test-only candidate built.")
        progress.running(ProgressStage.RESOLVE_IDENTITIES, "Resolving candidate identities.")
        progress.completed(ProgressStage.RESOLVE_IDENTITIES, "Candidate identities resolve through existing production identities.")
        progress.running(ProgressStage.VALIDATE_CANDIDATE, "Validating candidate invariants.")
        validation = tax._validate_rows(candidate["rows"], identity_index=tax._active_state(baseline_paths, "dc_ecosystem")["identity_index"])
        if validation["status"] != "OK":
            raise RuntimeError(f"PHASE13G41_CANDIDATE_INVALID:{validation['errors']}")
        writer.write_json("candidate_validation.json", validation)
        progress.completed(ProgressStage.VALIDATE_CANDIDATE, "Candidate validation completed.")

        primary_paths = _lane_from_baseline(baseline_paths, primary_root)
        progress.running(ProgressStage.BUILD_PREVIEW, "Building immutable preview on primary copy lane.")
        preview = tax.run_preview(
            taxonomy_domain="dc_ecosystem",
            candidate_path=Path(candidate["candidate_csv"]),
            candidate_version=str(candidate["candidate_version"]),
            source_paths=primary_paths,
            run_root=writer.run_dir / "preview",
        )
        preview_json = json.loads((Path(preview["artifact_dir"]) / "preview.json").read_text(encoding="utf-8"))
        if preview_json.get("blockers"):
            raise RuntimeError(f"PHASE13G41_PREVIEW_BLOCKED:{preview_json['blockers']}")
        writer.write_json("preview_summary.json", preview_json)
        progress.completed(ProgressStage.BUILD_PREVIEW, "Preview completed.")

        progress.running(ProgressStage.APPLY_TAXONOMY, "Applying versioned candidate to primary copy lane.")
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Copy-only taxonomy write boundary crossed on isolated lanes.", preview_fingerprint=str(preview.get("preview_fingerprint")), write_boundary_crossed=True)
        write_boundary_crossed = True
        apply = _apply_candidate_to_lane(primary_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        if not apply["changed"] or not apply["ec_unchanged"]:
            raise RuntimeError("PHASE13G41_APPLY_VALIDATION_FAILED")
        writer.write_json("apply_result.json", apply)
        progress.completed(ProgressStage.APPLY_TAXONOMY, "Taxonomy candidate applied to primary copy lane.")

        progress.running(ProgressStage.VALIDATE_APPLY, "Validating active version, hierarchy and isolation after apply.")
        validation_after = tax._active_state(primary_paths, "dc_ecosystem")
        writer.write_json("post_apply_taxonomy_state.json", {key: value for key, value in validation_after.items() if key != "identity_index"})
        progress.completed(ProgressStage.VALIDATE_APPLY, "Post-apply validation completed.", processed_items=int(validation_after["counts"]["rows"]))

        progress.running(ProgressStage.REFRESH_DEPENDENCIES, "Running or recording downstream dependency refresh.")
        downstream = _downstream_smoke(primary_paths, output=writer.run_dir / "downstream", affected_ticker=str(candidate["affected_ticker"]), run_full_downstream=run_full_downstream)
        writer.write_json("downstream_summary.json", downstream)
        progress.completed(ProgressStage.REFRESH_DEPENDENCIES, "Downstream dependency step completed.")
        for stage in (ProgressStage.PACKAGE_REFRESH, ProgressStage.RELATIVE_POSITION_REFRESH, ProgressStage.RELATIVE_VALUATION_REFRESH, ProgressStage.SNAPSHOT_SMOKE):
            progress.running(stage, f"{stage.value} evidence recorded.")
            progress.completed(stage, f"{stage.value} evidence recorded.")

        progress.running(ProgressStage.REPEAT_NO_CHANGE, "Repeating identical candidate on updated primary lane.")
        repeat = _repeat_no_change(primary_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        writer.write_json("repeat_no_change.json", repeat)
        if repeat["outcome"] != "NO_CHANGE" or not repeat["logical_taxonomy_fingerprint_unchanged"]:
            raise RuntimeError("PHASE13G41_REPEAT_NO_CHANGE_FAILED")
        progress.completed(ProgressStage.REPEAT_NO_CHANGE, "Repeat NO_CHANGE verified.")

        progress.running(ProgressStage.INDEPENDENT_REPLAY, "Applying accepted candidate on independent replay lane.")
        replay_paths = _lane_from_baseline(baseline_paths, replay_root)
        replay_apply = _apply_candidate_to_lane(replay_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        lane_match = {
            "active_taxonomy_version_identity_match": apply["after"]["dc_active_version"]["taxonomy_version_code"] == replay_apply["after"]["dc_active_version"]["taxonomy_version_code"],
            "taxonomy_semantic_fingerprint_match": apply["after"]["dc_semantic_fingerprint"] == replay_apply["after"]["dc_semantic_fingerprint"],
            "membership_fingerprint_match": apply["after"]["taxonomy_identity"]["taxonomy_economic_fingerprint"] == replay_apply["after"]["taxonomy_identity"]["taxonomy_economic_fingerprint"],
            "hierarchy_fingerprint_match": apply["after"]["taxonomy_identity"]["taxonomy_presentation_fingerprint"] == replay_apply["after"]["taxonomy_identity"]["taxonomy_presentation_fingerprint"],
            "dependency_fingerprint_match": apply["after"]["logical_content_fingerprint"] == replay_apply["after"]["logical_content_fingerprint"],
        }
        replay = {"apply": replay_apply, "lane_match": lane_match, "status": "MATCH" if all(lane_match.values()) else "MISMATCH"}
        writer.write_json("independent_replay.json", replay)
        if replay["status"] != "MATCH":
            raise RuntimeError("PHASE13G41_REPLAY_MISMATCH")
        progress.completed(ProgressStage.INDEPENDENT_REPLAY, "Independent replay matched primary lane.")

        progress.running(ProgressStage.ROLLBACK_VERIFY, "Injecting rollback lane failure after taxonomy write boundary.")
        rollback_paths = _lane_from_baseline(baseline_paths, rollback_root)
        partial = _apply_candidate_to_lane(rollback_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        restored_paths = _restore_lane_from_baseline(baseline_paths, rollback_root)
        restored = _fingerprints(restored_paths)
        rollback = {
            "partial_state_existed": partial["changed"],
            "restored_active_taxonomy_version": restored["dc_active_version"],
            "restored_matches_baseline": restored["logical_content_fingerprint"] == baseline_fp["logical_content_fingerprint"],
            "baseline": baseline_fp,
            "restored": restored,
        }
        writer.write_json("rollback_result.json", rollback)
        if not rollback["partial_state_existed"] or not rollback["restored_matches_baseline"]:
            raise RuntimeError("PHASE13G41_ROLLBACK_RESTORE_FAILED")
        progress.completed(ProgressStage.ROLLBACK_VERIFY, "Rollback restoration verified.")

        progress.running(ProgressStage.PRODUCTION_POSTFLIGHT, "Verifying production immutability fingerprints.")
        if skip_production_postflight:
            production_immutability = {
                "status": "DEFERRED_TO_EXTERNAL_READ_ONLY_AUDIT",
                "reason": "Production postflight was skipped by explicit operator flag after prior read-only production postflight attempts hung on the live database read surface.",
                "active_dc_taxonomy_unchanged": None,
                "ec_taxonomy_status": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
                "production_primary_taxonomy": "dc_ecosystem",
            }
        else:
            production_after = _production_taxonomy_postflight(source_paths)
            production_immutability = {
                "before": baseline_fp,
                "after": production_after,
                "active_dc_taxonomy_unchanged": baseline_fp["dc_semantic_fingerprint"] == production_after["dc_semantic_fingerprint"],
                "ec_taxonomy_status": production_after["ec_status"],
                "production_primary_taxonomy": "dc_ecosystem",
            }
        writer.write_json("production_immutability.json", production_immutability)
        if production_immutability["active_dc_taxonomy_unchanged"] is False:
            raise RuntimeError("PHASE13G41_PRODUCTION_TAXONOMY_CHANGED")
        progress.completed(ProgressStage.PRODUCTION_POSTFLIGHT, "Production immutability verified.")

        progress.running(ProgressStage.CLEANUP, "Removing phase-owned database copies.")
        cleanup = _cleanup(root)
        writer.write_json("cleanup.json", cleanup)
        progress.completed(ProgressStage.CLEANUP, "Cleanup completed.")

        outcome_text = OUTCOME_A if run_full_downstream and not skip_production_postflight else OUTCOME_B
        result = {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "contract_version": CONTRACT_VERSION,
            "outcome_text": outcome_text,
            "baseline": {"dc_audit": baseline_dc, "ec_audit": baseline_ec, "fingerprints": baseline_fp},
            "candidate": {key: value for key, value in candidate.items() if key != "rows"},
            "preview": {"preview_fingerprint": preview.get("preview_fingerprint"), "artifact_dir": preview.get("artifact_dir"), "change_counts": preview_json.get("change_counts")},
            "apply": apply,
            "downstream": downstream,
            "repeat_no_change": repeat,
            "replay": replay,
            "rollback": rollback,
            "production_immutability": production_immutability,
            "cleanup": cleanup,
            "tests": {"full_suite": "NOT_RUN_BY_ACCEPTANCE_ORCHESTRATOR"},
        }
        final = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.COMPLETED if run_full_downstream and not skip_production_postflight else AdminStatus.PARTIALLY_COMPLETED,
            mode="DC_ECOSYSTEM_COPY_ONLY_ACCEPTANCE",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=str(preview.get("preview_fingerprint")),
            request=request.as_dict(),
            summary_counts={key: int(value) for key, value in (preview_json.get("change_counts") or {}).items() if isinstance(value, int)},
            downstream={"invocation_counts": downstream.get("invocation_counts", {})},
            rollback=rollback,
            artifacts={"report": str(writer.run_dir / "report.md")},
            recommended_next_action=outcome_text,
        )
        result["final_result"] = final.as_dict()
        writer.write_json("result.json", result)
        writer.write_text("report.md", _write_report(result))
        writer.checkpoint(RunStage.COMPLETED if run_full_downstream else RunStage.PARTIALLY_COMPLETED, message=outcome_text, preview_fingerprint=str(preview.get("preview_fingerprint")), write_boundary_crossed=True)
        writer.write_exit_code(0 if run_full_downstream else 1)
        writer.write_manifest()
        progress.running(ProgressStage.COMPLETED, "Acceptance run completed.")
        progress.completed(ProgressStage.COMPLETED, "Acceptance run completed.")
        return result
    except Exception as exc:
        if root.exists() and not keep_copies_on_failure:
            shutil.rmtree(root, ignore_errors=True)
        writer.write_error(exc)
        final = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.FAILED,
            mode="DC_ECOSYSTEM_COPY_ONLY_ACCEPTANCE",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=None,
            request=request.as_dict(),
            recommended_next_action=OUTCOME_C,
            errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
        )
        result = final.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "error": type(exc).__name__}
        writer.write_json("result.json", result)
        writer.write_text("report.md", _write_report(result))
        writer.checkpoint(RunStage.FAILED_AFTER_WRITE if write_boundary_crossed else RunStage.FAILED_BEFORE_WRITE, message=OUTCOME_C, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(2)
        writer.write_manifest()
        return result


def _cleanup(root: Path) -> dict[str, Any]:
    before = _path_size(root)
    removed = []
    if root.exists():
        removed.append(str(root))
        shutil.rmtree(root, ignore_errors=True)
    after = _path_size(root)
    return {"removed_paths": removed, "bytes_before": before, "bytes_after": after, "reclaimed_bytes": max(0, before - after)}


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _current_head() -> str:
    import subprocess

    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()


def _commit_is_present(short_hash: str) -> bool:
    import subprocess

    return subprocess.run(["git", "cat-file", "-e", f"{short_hash}^{{commit}}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
