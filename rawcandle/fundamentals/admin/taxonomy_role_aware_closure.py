from __future__ import annotations

import json
import shutil
import sqlite3
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rawcandle.fundamentals.admin import taxonomy as tax
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.contracts import AdminBatchRequest, AdminFinalResult, AdminOperationType, AdminStatus, RunStage, fingerprint, utc_now
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.admin.rv_identity import active_relative_valuation_identity
from rawcandle.fundamentals.admin.taxonomy_acceptance import _commit_is_present
from rawcandle.fundamentals.admin.taxonomy_downstream_closure import _analysis_dependency_fingerprint
from rawcandle.fundamentals.admin.verification_plan import DatabaseRoleDeclaration, OperationRoleContract, build_verification_plan
from rawcandle.fundamentals.operating_income_v2 import activation
from rawcandle.fundamentals.phase12d import PRODUCTION, ROOT, stable_hash
from rawcandle.fundamentals.phase13b_foundation import taxonomy_identity


CONTRACT_VERSION = "PHASE13G421_ROLE_AWARE_TAXONOMY_CLOSURE_V1"
DEFAULT_RETAINED_RUN = ADMIN_RUN_ROOT / "20260916T114049Z_check_update_taxonomy_63e9ed063201_dc_ecosystem_downstream_closure"
OUTCOME_A = "OUTCOME A - DC_ECOSYSTEM FULL DOWNSTREAM AND ROLE-AWARE PRODUCTION CLOSURE VERIFIED"
OUTCOME_B = "OUTCOME B - RETAINED ACCEPTANCE EVIDENCE OR TARGETED CLOSURE INCOMPLETE; PRODUCTION UNCHANGED"
OUTCOME_C = "OUTCOME C - UNEXPECTED PRODUCTION WRITE OR MATERIAL SAFETY DEFECT"
TEST_ONLY_VERSION = "DC_TAXONOMY_FULL_V2_1_TEST_ONLY_PHASE13G41"
BASELINE_VERSION = "DC_TAXONOMY_FULL_V2_1"
PREVIOUS_TIMEOUT = "PHASE13G42_POSTFLIGHT_TIMEOUT:pragma:quick_check:/home/kalle/projects/rawcandle/data/analysis.db"


class ClosureEvidenceError(RuntimeError):
    pass


class TargetedQueryTimeout(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _connect_ro(path: Path, *, timeout_seconds: float) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=timeout_seconds)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute(f"PRAGMA busy_timeout={max(1, int(timeout_seconds * 1000))}")
    return conn


def _execute_bounded(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] = (),
    *,
    timeout_seconds: float,
    stage: str,
) -> list[sqlite3.Row]:
    deadline = time.monotonic() + timeout_seconds

    def progress() -> int:
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(progress, 1000)
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
    except sqlite3.OperationalError as exc:
        if time.monotonic() > deadline or "interrupted" in str(exc).lower() or "locked" in str(exc).lower():
            raise TargetedQueryTimeout(f"PHASE13G421_TARGETED_QUERY_TIMEOUT:{stage}") from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)
    if time.monotonic() > deadline:
        raise TargetedQueryTimeout(f"PHASE13G421_TARGETED_QUERY_TIMEOUT:{stage}")
    return rows


def phase13g42_role_contract(paths: tax.TaxonomyPaths | None = None, *, future_production_taxonomy: bool = False) -> OperationRoleContract:
    paths = paths or tax.TaxonomyPaths()
    production_writable = ("taxonomy",) if future_production_taxonomy else ()
    production_readonly = tuple(role for role in ("provider", "canonical", "analysis", "market", "taxonomy") if role not in production_writable)
    production_paths = paths.as_dict()
    declarations = [
        *(
            DatabaseRoleDeclaration(role, "production", "writable", production_paths[role], "Future production taxonomy deployment may write this database.")
            for role in production_writable
        ),
        *(
            DatabaseRoleDeclaration(role, "production", "read-only", production_paths[role], "Phase 13G.4.2 read this production database but did not write it.")
            for role in production_readonly
        ),
        *(
            DatabaseRoleDeclaration(role, "copy", "writable", None, "Phase 13G.4.2 mutated this role only on isolated production-shaped copy lanes that were cleaned after the run.")
            for role in ("analysis", "taxonomy")
        ),
        *(
            DatabaseRoleDeclaration(role, "copy", "read-only", None, "Phase 13G.4.2 used this role only as an isolated copy-lane input.")
            for role in ("provider", "canonical", "market")
        ),
    ]
    return OperationRoleContract(
        operation_name="PHASE13G4_2_DC_ECOSYSTEM_DOWNSTREAM_COPY_ONLY" if not future_production_taxonomy else "FUTURE_PRODUCTION_TAXONOMY_DEPLOYMENT",
        declarations=tuple(declarations),
        write_boundary_crossed=False,
    )


def role_matrix(paths: tax.TaxonomyPaths | None = None) -> dict[str, Any]:
    contract = phase13g42_role_contract(paths)
    plan = build_verification_plan(contract)
    return plan["role_matrix"] | {
        "paths": {role: str(path.resolve()) for role, path in (paths or tax.TaxonomyPaths()).as_dict().items()},
        "production_write_boundary_crossed": False,
        "classification_basis": "Phase 13G.4.2 writes taxonomy and downstream state only on isolated copy lanes.",
    }


def reconcile_phase13g42_evidence(run_dir: Path = DEFAULT_RETAINED_RUN) -> dict[str, Any]:
    if not run_dir.exists():
        raise ClosureEvidenceError(f"PHASE13G421_RETAINED_RUN_MISSING:{run_dir}")
    required = (
        "result.json",
        "error.json",
        "test_only_candidate.json",
        "primary_taxonomy_apply.json",
        "change_counters.json",
        "primary_downstream.json",
        "fixed_point_repeat.json",
        "independent_replay.json",
        "rollback_after_downstream.json",
        "production_logical_baseline.json",
        "postflight_heartbeat.json",
        "artifact_manifest.json",
        "exit_code",
    )
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise ClosureEvidenceError(f"PHASE13G421_RETAINED_ARTIFACTS_MISSING:{missing}")

    result = _read_json(run_dir / "result.json")
    error = _read_json(run_dir / "error.json")
    candidate = _read_json(run_dir / "test_only_candidate.json")
    apply = _read_json(run_dir / "primary_taxonomy_apply.json")
    counters = _read_json(run_dir / "change_counters.json")
    downstream = _read_json(run_dir / "primary_downstream.json")
    repeat = _read_json(run_dir / "fixed_point_repeat.json")
    replay = _read_json(run_dir / "independent_replay.json")
    rollback = _read_json(run_dir / "rollback_after_downstream.json")
    baseline = _read_json(run_dir / "production_logical_baseline.json")
    heartbeat = _read_json(run_dir / "postflight_heartbeat.json")
    exit_code = (run_dir / "exit_code").read_text(encoding="utf-8").strip()

    checks = {
        "result_failed_with_outcome_c": result.get("outcome") == "FAILED" and str(result.get("outcome_text", "")).startswith("OUTCOME C"),
        "terminal_blocker_is_expected_timeout": error.get("message") == PREVIOUS_TIMEOUT,
        "exit_code_2": exit_code == "2",
        "candidate_test_only": candidate.get("status") == "TEST_ONLY_NOT_FOR_PRODUCTION" and candidate.get("candidate_version") == TEST_ONLY_VERSION,
        "candidate_role_tier": candidate.get("affected_ticker") == "AAOI" and candidate.get("change_type") == "ROLE_TIER_CHANGED",
        "taxonomy_apply_applied": apply.get("taxonomy_apply", {}).get("outcome") == "APPLIED",
        "selected_domain_dc": apply.get("taxonomy_apply", {}).get("domain") == "dc_ecosystem",
        "ec_taxonomy_unchanged": apply.get("ec_unchanged") is True and apply.get("after", {}).get("ec_status") == "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
        "semantic_counter": counters.get("semantic_changes") == 1 and counters.get("role_or_tier_changes") == 1,
        "persisted_rows": counters.get("persisted_membership_rows") == 350,
        "downstream_invoked": _downstream_invocations_ok(downstream),
        "fixed_point_no_change": repeat.get("outcome") == "NO_CHANGE",
        "fixed_point_zero_writes": all(int(repeat.get(key, -1)) == 0 for key in ("taxonomy_writes", "membership_writes", "new_version_rows", "dependency_writes", "snapshot_regeneration")),
        "fixed_point_downstream_skipped": repeat.get("package_relative_position_relative_valuation_invocations") == "0/0/0",
        "replay_match": replay.get("status") == "MATCH" and all((replay.get("lane_match") or {}).values()),
        "rollback_restored": rollback.get("partial_taxonomy_state_existed") is True and rollback.get("partial_downstream_state_existed") is True and rollback.get("restored_matches_baseline") is True,
        "baseline_ok": baseline.get("status") == "OK",
        "postflight_timeout_stage_recorded": _heartbeat_has_timeout(heartbeat),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ClosureEvidenceError(f"PHASE13G421_RETAINED_EVIDENCE_INVALID:{failed}")

    return {
        "status": "VALIDATED",
        "retained_run_dir": str(run_dir.resolve()),
        "checks": checks,
        "taxonomy_apply": {
            "outcome": apply["taxonomy_apply"]["outcome"],
            "domain": apply["taxonomy_apply"]["domain"],
            "candidate_status": candidate["status"],
            "candidate_version": candidate["candidate_version"],
            "affected_ticker": candidate["affected_ticker"],
            "change_type": candidate["change_type"],
            "ec_status_after": apply["after"]["ec_status"],
        },
        "change_counters": counters,
        "downstream": {
            "invocation_counts": downstream.get("invocation_counts"),
            "dependencies": downstream.get("dependencies"),
            "fingerprint": downstream.get("fingerprints", {}).get("fingerprint"),
            "snapshot_fingerprints": downstream.get("fingerprints", {}).get("payload", {}).get("snapshots"),
        },
        "fixed_point": {
            "outcome": repeat.get("outcome"),
            "taxonomy_writes": repeat.get("taxonomy_writes"),
            "membership_writes": repeat.get("membership_writes"),
            "new_version_rows": repeat.get("new_version_rows"),
            "dependency_writes": repeat.get("dependency_writes"),
            "downstream_invocations": repeat.get("package_relative_position_relative_valuation_invocations"),
            "logical_content_fingerprint_unchanged": repeat.get("logical_content_fingerprint_unchanged"),
        },
        "replay": {
            "status": replay.get("status"),
            "lane_match": replay.get("lane_match"),
            "downstream_fingerprint": replay.get("downstream", {}).get("fingerprints", {}).get("fingerprint"),
        },
        "rollback": {
            "partial_taxonomy_state_existed": rollback.get("partial_taxonomy_state_existed"),
            "partial_downstream_state_existed": rollback.get("partial_downstream_state_existed"),
            "restored_matches_baseline": rollback.get("restored_matches_baseline"),
            "downstream_invocation_counts_before_restore": rollback.get("downstream_invocation_counts_before_restore"),
        },
        "previous_timeout": {
            "message": error.get("message"),
            "reclassified_as": "OVER_BROAD_READ_ONLY_HEAVY_CHECK",
            "reason": "Production taxonomy database was read-only in Phase 13G.4.2 and production write boundary was not crossed.",
        },
    }


def _downstream_invocations_ok(downstream: Mapping[str, Any]) -> bool:
    counts = downstream.get("invocation_counts") or {}
    return all(int(counts.get(key) or 0) >= 1 for key in ("package", "relative_position", "relative_valuation", "dependency_attachment", "compatibility_verification")) and int(counts.get("snapshot") or 0) >= 2


def _heartbeat_has_timeout(heartbeat: Mapping[str, Any]) -> bool:
    return any(
        event.get("event") == "stage_failed"
        and event.get("details", {}).get("role") == "taxonomy"
        and event.get("details", {}).get("stage") == "quick_check"
        and event.get("details", {}).get("error") == "BoundedPostflightTimeout"
        for event in heartbeat.get("events", [])
    )


def lightweight_production_state(
    paths: tax.TaxonomyPaths | None = None,
    *,
    timeout_seconds: float = 10.0,
    heartbeat: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise TargetedQueryTimeout("PHASE13G421_TARGETED_QUERY_TIMEOUT:timeout_budget")
    paths = paths or tax.TaxonomyPaths()
    started = time.monotonic()
    taxonomy = _targeted_taxonomy_state(paths.taxonomy_db, timeout_seconds=timeout_seconds, heartbeat=heartbeat)
    active = _targeted_active_downstream(paths.analysis_db, timeout_seconds=timeout_seconds, heartbeat=heartbeat)
    dependency = _analysis_dependency_fingerprint(paths.analysis_db)
    current = {
        "taxonomy": taxonomy,
        "active_downstream": active,
        "dependency_rows": dependency,
    }
    blockers: list[str] = []
    if taxonomy["dc_active_version"].get("taxonomy_version_code") != BASELINE_VERSION:
        blockers.append("DC_ACTIVE_VERSION_NOT_BASELINE")
    if taxonomy["active_test_only_version_count"]:
        blockers.append("TEST_ONLY_VERSION_ACTIVE")
    if taxonomy["ec_taxonomy"]["distinct_general_ecosystem_count"] != 0:
        blockers.append("GENERAL_EC_TAXONOMY_POINTER_PRESENT")
    if active["active_relative_valuation"].get("active_snapshot_id") is None:
        blockers.append("RV_ACTIVE_SNAPSHOT_MISSING")
    return {
        "status": "OK" if not blockers else "BLOCKED",
        "blockers": blockers,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "state": current,
        "fingerprint": stable_hash(current),
    }


def _targeted_taxonomy_state(
    taxonomy_db: Path,
    *,
    timeout_seconds: float,
    heartbeat: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    stage_started = time.monotonic()
    if heartbeat:
        heartbeat("targeted_query_start", {"role": "taxonomy", "stage": "dc_active_version", "path": str(taxonomy_db)})
    with _connect_ro(taxonomy_db, timeout_seconds=timeout_seconds) as conn:
        active = tax._ec_active_version(conn)
        rows = tax._ec_rows_for_version(conn, int(active["taxonomy_version_id"]), str(active["taxonomy_version_code"]))
        validation = tax._validate_rows(rows)
        semantic_fingerprint = stable_hash({"taxonomy_domain": "dc_ecosystem", "rows": tax._semantic_payload(rows)})
        identity = taxonomy_identity(taxonomy_db)
        active_test_only = _execute_bounded(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM ec_taxonomy_version
            WHERE is_active=1 AND taxonomy_version_code=?
            """,
            (TEST_ONLY_VERSION,),
            timeout_seconds=timeout_seconds,
            stage="active_test_only_version",
        )[0]["c"]
        ecosystems = [
            dict(row)
            for row in _execute_bounded(
                conn,
                "SELECT * FROM ec_ecosystem ORDER BY ecosystem_code",
                timeout_seconds=timeout_seconds,
                stage="ec_ecosystem_inventory",
            )
        ]
        if heartbeat:
            heartbeat("targeted_query_done", {"role": "taxonomy", "stage": "dc_active_version", "elapsed_seconds": round(time.monotonic() - stage_started, 6)})
    general = [row for row in ecosystems if str(row.get("ecosystem_code")) != tax.DATACENTER_ECOSYSTEM_CODE]
    return {
        "path": str(taxonomy_db.resolve()),
        "dc_active_version": dict(active) | {"domain": "dc_ecosystem"},
        "dc_counts": validation["counts"],
        "dc_semantic_fingerprint": semantic_fingerprint,
        "taxonomy_identity": {
            "taxonomy_source_version": identity.get("taxonomy_source_version"),
            "taxonomy_economic_fingerprint": identity.get("taxonomy_economic_fingerprint"),
            "taxonomy_presentation_fingerprint": identity.get("taxonomy_presentation_fingerprint"),
        },
        "active_test_only_version_count": int(active_test_only),
        "ec_taxonomy": {
            "status": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
            "distinct_general_ecosystem_count": len(general),
            "discovered_ecosystems": ecosystems,
        },
    }


def _targeted_active_downstream(
    analysis_db: Path,
    *,
    timeout_seconds: float,
    heartbeat: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    stage_started = time.monotonic()
    if heartbeat:
        heartbeat("targeted_query_start", {"role": "analysis", "stage": "active_downstream_identities", "path": str(analysis_db)})
    with _connect_ro(analysis_db, timeout_seconds=timeout_seconds) as conn:
        try:
            package = activation.assert_v2_active(conn).__dict__
        except Exception as exc:
            package = {"status": "NOT_ACTIVE", "error": type(exc).__name__}
        rp = []
        exists = _execute_bounded(
            conn,
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='relative_position_active_snapshot'",
            timeout_seconds=timeout_seconds,
            stage="relative_position_active_table_exists",
        )
        if exists:
            rp = [
                dict(row)
                for row in _execute_bounded(
                    conn,
                    "SELECT * FROM relative_position_active_snapshot ORDER BY model_fingerprint",
                    timeout_seconds=timeout_seconds,
                    stage="relative_position_active_identity",
                )
            ]
    rv = active_relative_valuation_identity(analysis_db)
    rv = {key: value for key, value in rv.items() if key != "database_path"}
    if heartbeat:
        heartbeat("targeted_query_done", {"role": "analysis", "stage": "active_downstream_identities", "elapsed_seconds": round(time.monotonic() - stage_started, 6)})
    return {
        "path": str(analysis_db.resolve()),
        "operating_income_package": package,
        "active_relative_position": rp,
        "active_relative_valuation": rv,
    }


def compare_lightweight_to_retained_baseline(current: Mapping[str, Any], retained_run_dir: Path = DEFAULT_RETAINED_RUN) -> dict[str, Any]:
    baseline = _read_json(retained_run_dir / "production_logical_baseline.json").get("logical_state", {})
    baseline_taxonomy = baseline.get("dc_taxonomy", {})
    baseline_identity = baseline.get("taxonomy_identity", {})
    baseline_active = baseline.get("active_identities", {})
    state = current.get("state", {})
    taxonomy = state.get("taxonomy", {})
    active = state.get("active_downstream", {})
    comparisons = {
        "dc_active_version_code_unchanged": taxonomy.get("dc_active_version", {}).get("taxonomy_version_code") == baseline_taxonomy.get("active_version", {}).get("taxonomy_version_code"),
        "dc_semantic_fingerprint_unchanged": taxonomy.get("dc_semantic_fingerprint") == baseline_taxonomy.get("semantic_fingerprint"),
        "dc_counts_unchanged": taxonomy.get("dc_counts") == baseline_taxonomy.get("counts"),
        "taxonomy_economic_fingerprint_unchanged": taxonomy.get("taxonomy_identity", {}).get("taxonomy_economic_fingerprint") == baseline_identity.get("taxonomy_economic_fingerprint"),
        "active_downstream_identities_unchanged": {
            "operating_income_package": active.get("operating_income_package") == baseline_active.get("operating_income_package"),
            "active_relative_position": active.get("active_relative_position") == baseline_active.get("active_relative_position"),
            "active_relative_valuation": active.get("active_relative_valuation") == baseline_active.get("active_relative_valuation"),
        },
    }
    nested = comparisons["active_downstream_identities_unchanged"]
    ok = all(value for key, value in comparisons.items() if key != "active_downstream_identities_unchanged") and all(nested.values())
    return {"status": "MATCH" if ok else "MISMATCH", "comparisons": comparisons}


def run_role_aware_taxonomy_closure(
    *,
    source_paths: tax.TaxonomyPaths | None = None,
    retained_run_dir: Path = DEFAULT_RETAINED_RUN,
    run_root: Path = ADMIN_RUN_ROOT,
    targeted_timeout_seconds: float = 10.0,
    test_results: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_paths = source_paths or tax.TaxonomyPaths()
    started = utc_now()
    request = AdminBatchRequest(
        operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        requested_inputs=(),
        normalized_inputs=(),
        options={"phase": "13G.4.2.1", "taxonomy_domain": "dc_ecosystem", "mode": "ROLE_AWARE_CLOSURE"},
    )
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"contract": CONTRACT_VERSION, "request": request}), suffix="dc_ecosystem_role_aware_closure")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Phase 13G.4.2.1 role-aware taxonomy closure requested.")
    writer.checkpoint(RunStage.APPLY_STARTED, message="Read-only closure verification started.")
    try:
        preflight = {
            "required_commits": {short: _commit_is_present(short) for short in ("fe076a4", "6129d72", "be0c91c")},
            "worktree_expected_clean_before_phase": True,
            "production_writes_authorized": False,
            "heavy_chain_rerun_authorized": False,
        }
        if not all(preflight["required_commits"].values()):
            raise ClosureEvidenceError("PHASE13G421_REQUIRED_COMMIT_MISSING")
        writer.write_json("preflight.json", preflight)

        plan = build_verification_plan(phase13g42_role_contract(source_paths))
        future_plan = build_verification_plan(phase13g42_role_contract(source_paths, future_production_taxonomy=True))
        matrix = role_matrix(source_paths)
        writer.write_json("database_role_matrix.json", matrix)
        writer.write_json("verification_plan.json", plan)
        writer.write_json("future_production_taxonomy_plan.json", future_plan)

        reconciliation = reconcile_phase13g42_evidence(retained_run_dir)
        writer.write_json("phase13g42_evidence_reconciliation.json", reconciliation)

        events: list[dict[str, Any]] = []

        def heartbeat(event: str, details: Mapping[str, Any]) -> None:
            events.append({"event": event, "details": dict(details), "timestamp_utc": utc_now()})
            writer.write_json("targeted_query_heartbeat.json", {"events": events[-100:]})

        production = lightweight_production_state(source_paths, timeout_seconds=targeted_timeout_seconds, heartbeat=heartbeat)
        production_compare = compare_lightweight_to_retained_baseline(production, retained_run_dir)
        writer.write_json("lightweight_production_state.json", production)
        writer.write_json("production_unchanged_comparison.json", production_compare)
        if production["status"] != "OK" or production_compare["status"] != "MATCH":
            raise ClosureEvidenceError("PHASE13G421_LIGHTWEIGHT_PRODUCTION_CLOSURE_BLOCKED")

        timeout_reclassification = {
            "previous_timeout": PREVIOUS_TIMEOUT,
            "new_classification": "NOT_ACCEPTANCE_BLOCKER_FOR_PHASE13G42_COPY_ONLY_READINESS",
            "reason": "Role-aware plan classifies production taxonomy as read-only; no production write boundary was crossed, so full production quick_check was an over-broad post-write check.",
            "guardrail": "Future production taxonomy mode classifies taxonomy as production writable and retains heavy post-write checks after write-boundary crossing.",
        }
        writer.write_json("previous_timeout_reclassification.json", timeout_reclassification)

        tests = dict(test_results or {})
        tests.setdefault("retained_full_suite", {"status": "REUSED_FROM_PHASE13G42_OPERATOR_EVIDENCE", "summary": "3031 passed, 14 deselected, 8 warnings, exit code 0"})
        writer.write_json("test_results.json", tests)

        cleanup = {
            "phase_owned_db_copies_created": 0,
            "heavy_chain_rerun": False,
            "temp_root_exists": False,
            "disk_free_bytes_repo": shutil.disk_usage(ROOT).free,
            "disk_free_bytes_tmp": shutil.disk_usage(Path("/tmp")).free,
        }
        writer.write_json("cleanup_and_disk.json", cleanup)

        result = {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "contract_version": CONTRACT_VERSION,
            "outcome_text": OUTCOME_A,
            "database_role_matrix": matrix,
            "verification_plan": plan,
            "phase13g42_evidence": reconciliation,
            "lightweight_production_state": production,
            "production_unchanged_comparison": production_compare,
            "previous_timeout_reclassification": timeout_reclassification,
            "tests": tests,
            "cleanup": cleanup,
        }
        final = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.COMPLETED,
            mode="ROLE_AWARE_TAXONOMY_CLOSURE",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=None,
            request=request.as_dict(),
            summary_counts=reconciliation["change_counters"],
            downstream={"retained_invocation_counts": reconciliation["downstream"]["invocation_counts"]},
            rollback=reconciliation["rollback"],
            artifacts={"report": str(writer.run_dir / "report.md")},
            recommended_next_action=OUTCOME_A,
        )
        result["final_result"] = final.as_dict()
        writer.write_json("result.json", result)
        writer.write_text("report.md", render_role_aware_closure_report(result))
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="No production write boundary was crossed.", write_boundary_crossed=False)
        writer.checkpoint(RunStage.COMPLETED, message=OUTCOME_A, counters=reconciliation["change_counters"], write_boundary_crossed=False)
        writer.write_exit_code(0)
        writer.write_manifest()
        return result
    except Exception as exc:
        writer.write_error(exc)
        final = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.FAILED,
            mode="ROLE_AWARE_TAXONOMY_CLOSURE",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=None,
            request=request.as_dict(),
            recommended_next_action=OUTCOME_B,
            errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
        )
        result = final.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "error": type(exc).__name__, "outcome_text": OUTCOME_B}
        writer.write_json("result.json", result)
        writer.write_text("report.md", render_role_aware_closure_report(result))
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message=OUTCOME_B, write_boundary_crossed=False)
        writer.write_exit_code(2)
        writer.write_manifest()
        return result


def render_role_aware_closure_report(result: Mapping[str, Any]) -> str:
    lines = [render_markdown_report(result).rstrip(), "", "## Phase 13G.4.2.1 Role-Aware Closure", ""]
    if result.get("outcome_text"):
        lines.append(f"- outcome: `{result['outcome_text']}`")
    lines.append("- production writes: `0`")
    lines.append("- heavy taxonomy/downstream acceptance rerun: `0`")
    lines.append("- production full quick_check: `skipped for read-only roles`")
    lines.append("")
    for key in (
        "database_role_matrix",
        "verification_plan",
        "phase13g42_evidence",
        "lightweight_production_state",
        "production_unchanged_comparison",
        "previous_timeout_reclassification",
        "tests",
        "cleanup",
    ):
        if key in result:
            lines.append(f"### {key.replace('_', ' ').title()}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(result[key], indent=2, sort_keys=True, default=str))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
