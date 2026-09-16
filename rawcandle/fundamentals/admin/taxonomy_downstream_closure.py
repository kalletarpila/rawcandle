from __future__ import annotations

import json
import subprocess
import shutil
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths, PRODUCTION_LOCK_PATH, _background_heartbeat
from rawcandle.fundamentals.admin.contracts import AdminBatchRequest, AdminFinalResult, AdminOperationType, AdminStatus, RunStage, fingerprint, utc_now
from rawcandle.fundamentals.admin.progress import ProgressStage, ProgressTracker, TAXONOMY_DOWNSTREAM_CLOSURE_STAGES
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.admin.rv_identity import active_relative_valuation_identity
from rawcandle.fundamentals.admin import taxonomy as tax
from rawcandle.fundamentals.admin import taxonomy_acceptance as base
from rawcandle.fundamentals.operating_income_v2 import activation
from rawcandle.fundamentals.phase12d import PRODUCTION, stable_hash
from rawcandle.fundamentals.phase13b_foundation import candidate_relative_valuation_dependency_state, taxonomy_identity
from rawcandle.io_atomic import write_text_atomic


CONTRACT_VERSION = "PHASE13G42_DC_ECOSYSTEM_DOWNSTREAM_CLOSURE_V1"
OUTCOME_A = "OUTCOME A - DC_ECOSYSTEM FULL DOWNSTREAM FIXED POINT AND BOUNDED PRODUCTION POSTFLIGHT VERIFIED"
OUTCOME_B = "OUTCOME B - CORRECTABLE DOWNSTREAM OR POSTFLIGHT LIMITATION REMAINS; PRODUCTION UNCHANGED"
OUTCOME_C = "OUTCOME C - MATERIAL DEPENDENCY, ROLLBACK OR PRODUCTION-SAFETY DEFECT; PRODUCTION UNCHANGED"
TEMP_ROOT = ADMIN_TEMP_ROOT.parent / "fundamentals_admin_phase13g4_2_taxonomy_downstream_closure"


class BoundedPostflightTimeout(RuntimeError):
    pass


def _write_json(path: Path, value: Mapping[str, Any] | Sequence[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n")
    return path


def _readonly(path: Path, *, timeout_seconds: float) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout_seconds)
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
            raise BoundedPostflightTimeout(f"PHASE13G42_POSTFLIGHT_TIMEOUT:{stage}") from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)
    if time.monotonic() > deadline:
        raise BoundedPostflightTimeout(f"PHASE13G42_POSTFLIGHT_TIMEOUT:{stage}")
    return rows


def _pragma_bounded_subprocess(path: Path, pragma: str, *, timeout_seconds: float) -> list[list[Any]]:
    script = (
        "import json, sqlite3, sys\n"
        "path, pragma = sys.argv[1], sys.argv[2]\n"
        "conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=1)\n"
        "conn.execute('PRAGMA query_only=ON')\n"
        "try:\n"
        "    rows = conn.execute(f'PRAGMA {pragma}').fetchall()\n"
        "    print(json.dumps([list(row) for row in rows], default=str))\n"
        "finally:\n"
        "    conn.close()\n"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, str(path.resolve()), pragma],
            check=True,
            capture_output=True,
            text=True,
            timeout=max(0.001, timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        raise BoundedPostflightTimeout(f"PHASE13G42_POSTFLIGHT_TIMEOUT:pragma:{pragma}:{path}") from exc
    return json.loads(completed.stdout or "[]")


def _table_exists_bounded(conn: sqlite3.Connection, table: str, *, timeout_seconds: float) -> bool:
    rows = _execute_bounded(
        conn,
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
        (table,),
        timeout_seconds=timeout_seconds,
        stage=f"table_exists:{table}",
    )
    return bool(rows)


def _schema_identity(conn: sqlite3.Connection, tables: Sequence[str], *, timeout_seconds: float) -> dict[str, Any]:
    rows = _execute_bounded(
        conn,
        "SELECT name,type,sql FROM sqlite_schema WHERE type IN ('table','index','trigger','view') ORDER BY type,name",
        timeout_seconds=timeout_seconds,
        stage="schema_identity",
    )
    selected = [
        {"name": row["name"], "type": row["type"], "sql": row["sql"]}
        for row in rows
        if not tables or str(row["name"]).split("_idx")[0] in tables or str(row["name"]) in tables
    ]
    return {"object_count": len(selected), "fingerprint": stable_hash(selected)}


def _dependency_rows(conn: sqlite3.Connection, *, timeout_seconds: float) -> dict[str, Any]:
    tables = ("fundamentals_result_dependency", "relative_valuation_snapshot_dependency")
    output: dict[str, Any] = {}
    for table in tables:
        if not _table_exists_bounded(conn, table, timeout_seconds=timeout_seconds):
            output[table] = {"status": "MISSING", "row_count": 0, "fingerprint": None}
            continue
        rows = [
            dict(row)
            for row in _execute_bounded(
                conn,
                f"SELECT * FROM {table} ORDER BY 1,2,3,4 LIMIT 100000",
                timeout_seconds=timeout_seconds,
                stage=f"dependency_rows:{table}",
            )
        ]
        output[table] = {"status": "OK", "row_count": len(rows), "fingerprint": stable_hash(rows)}
    return output


def bounded_logical_postflight(
    paths: tax.TaxonomyPaths,
    *,
    timeout_seconds: float = 20.0,
    heartbeat: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise BoundedPostflightTimeout("PHASE13G42_POSTFLIGHT_TIMEOUT:timeout_budget")
    started = time.monotonic()
    roles: dict[str, Any] = {}
    protected_tables = {
        "analysis": (
            "operating_income_v2_package_manifest",
            "relative_position_active_snapshot",
            "relative_position_snapshot",
            "relative_valuation_active_snapshot",
            "relative_valuation_snapshot",
            "fundamentals_result_dependency",
            "relative_valuation_snapshot_dependency",
        ),
        "taxonomy": (
            "ec_taxonomy_version",
            "ec_membership",
            "ec_entity",
            "ec_ecosystem",
            "dc_ecosystem_membership",
        ),
    }
    for role, path in paths.as_dict().items():
        stage_started = time.monotonic()
        if heartbeat:
            heartbeat("database_start", {"role": role, "path": str(path)})
        quick_started = time.monotonic()
        if heartbeat:
            heartbeat("stage_start", {"role": role, "stage": "quick_check"})
        try:
            quick = _pragma_bounded_subprocess(path, "quick_check", timeout_seconds=timeout_seconds)
        except Exception as exc:
            if heartbeat:
                heartbeat("stage_failed", {"role": role, "stage": "quick_check", "elapsed_seconds": round(time.monotonic() - quick_started, 6), "error": type(exc).__name__})
            raise
        if heartbeat:
            heartbeat("stage_done", {"role": role, "stage": "quick_check", "elapsed_seconds": round(time.monotonic() - quick_started, 6)})

        foreign_started = time.monotonic()
        if heartbeat:
            heartbeat("stage_start", {"role": role, "stage": "foreign_key_check"})
        try:
            foreign = _pragma_bounded_subprocess(path, "foreign_key_check", timeout_seconds=timeout_seconds)
        except Exception as exc:
            if heartbeat:
                heartbeat("stage_failed", {"role": role, "stage": "foreign_key_check", "elapsed_seconds": round(time.monotonic() - foreign_started, 6), "error": type(exc).__name__})
            raise
        if heartbeat:
            heartbeat("stage_done", {"role": role, "stage": "foreign_key_check", "elapsed_seconds": round(time.monotonic() - foreign_started, 6)})

        with _readonly(path, timeout_seconds=timeout_seconds) as conn:
            schema_started = time.monotonic()
            if heartbeat:
                heartbeat("stage_start", {"role": role, "stage": "schema_identity"})
            schema = _schema_identity(conn, protected_tables.get(role, ()), timeout_seconds=timeout_seconds)
            if heartbeat:
                heartbeat("stage_done", {"role": role, "stage": "schema_identity", "elapsed_seconds": round(time.monotonic() - schema_started, 6)})
            roles[role] = {
                "path": str(path),
                "quick_check": quick[0][0] if quick else None,
                "foreign_key_errors": len(foreign),
                "schema_identity": schema,
                "elapsed_seconds": round(time.monotonic() - stage_started, 6),
            }
            if role == "analysis":
                dependency_started = time.monotonic()
                if heartbeat:
                    heartbeat("stage_start", {"role": role, "stage": "dependency_rows"})
                roles[role]["dependency_rows"] = _dependency_rows(conn, timeout_seconds=timeout_seconds)
                if heartbeat:
                    heartbeat("stage_done", {"role": role, "stage": "dependency_rows", "elapsed_seconds": round(time.monotonic() - dependency_started, 6)})
        if heartbeat:
            heartbeat("database_done", {"role": role, "elapsed_seconds": roles[role]["elapsed_seconds"]})
    active = _active_identities(paths)
    dc = tax._active_state(paths, "dc_ecosystem")
    ec = tax._active_state(paths, "ec_taxonomy")
    identity = taxonomy_identity(paths.taxonomy_db)
    dependency = _taxonomy_dependency_state(paths)
    blockers = []
    for role, item in roles.items():
        if item["quick_check"] != "ok":
            blockers.append(f"{role}:QUICK_CHECK:{item['quick_check']}")
        if item["foreign_key_errors"]:
            blockers.append(f"{role}:FOREIGN_KEY_ERRORS:{item['foreign_key_errors']}")
    if ec["active_version"].get("update_contract_status") != "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY":
        blockers.append("EC_TAXONOMY_CONTRACT_CHANGED")
    logical_roles = {
        role: {key: value for key, value in item.items() if key != "elapsed_seconds"}
        for role, item in roles.items()
    }
    logical = {
        "roles": logical_roles,
        "active_identities": active,
        "dc_taxonomy": {
            "active_version": dc["active_version"],
            "semantic_fingerprint": dc["semantic_fingerprint"],
            "counts": dc["counts"],
        },
        "ec_taxonomy": {
            "status": ec["active_version"].get("update_contract_status"),
            "semantic_fingerprint": ec["semantic_fingerprint"],
            "active_version": ec["active_version"],
        },
        "taxonomy_identity": {
            "taxonomy_source_version": identity.get("taxonomy_source_version"),
            "taxonomy_economic_fingerprint": identity.get("taxonomy_economic_fingerprint"),
            "taxonomy_presentation_fingerprint": identity.get("taxonomy_presentation_fingerprint"),
        },
        "taxonomy_dependencies": dependency,
    }
    logical["fingerprint"] = stable_hash(logical)
    return {
        "status": "OK" if not blockers else "BLOCKED",
        "blockers": blockers,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "logical_state": logical,
    }


def compare_bounded_postflight(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_state = before.get("logical_state") if isinstance(before.get("logical_state"), Mapping) else {}
    after_state = after.get("logical_state") if isinstance(after.get("logical_state"), Mapping) else {}
    comparisons = {
        "logical_fingerprint_unchanged": before_state.get("fingerprint") == after_state.get("fingerprint"),
        "active_identities_unchanged": before_state.get("active_identities") == after_state.get("active_identities"),
        "dc_taxonomy_unchanged": before_state.get("dc_taxonomy") == after_state.get("dc_taxonomy"),
        "ec_taxonomy_unchanged": before_state.get("ec_taxonomy") == after_state.get("ec_taxonomy"),
        "dependencies_unchanged": before_state.get("taxonomy_dependencies") == after_state.get("taxonomy_dependencies"),
    }
    return {"status": "MATCH" if all(comparisons.values()) and after.get("status") == "OK" else "MISMATCH", "comparisons": comparisons}


def taxonomy_change_counters(preview_counts: Mapping[str, Any], apply_result: Mapping[str, Any]) -> dict[str, int]:
    additions = int(preview_counts.get("ADDED") or 0)
    removals = int(preview_counts.get("REMOVED") or 0)
    role_changes = int(preview_counts.get("ROLE_TIER_CHANGED") or 0)
    primary_changes = int(preview_counts.get("PRIMARY_CHANGED") or 0)
    semantic_changes = additions + removals + role_changes + primary_changes
    taxonomy_apply = apply_result.get("taxonomy_apply") if isinstance(apply_result.get("taxonomy_apply"), Mapping) else apply_result
    load_summary = taxonomy_apply.get("load_summary") if isinstance(taxonomy_apply.get("load_summary"), Mapping) else {}
    persisted = int(load_summary.get("taxonomy_rows") or taxonomy_apply.get("rows_changed") or 0)
    version_rows = 1 if taxonomy_apply.get("outcome") == "APPLIED" else 0
    return {
        "semantic_changes": semantic_changes,
        "membership_additions": additions,
        "membership_removals": removals,
        "role_or_tier_changes": role_changes,
        "primary_changes": primary_changes,
        "persisted_membership_rows": persisted,
        "version_rows_written": version_rows,
        "dependency_rows_written": 0,
    }


def _active_identities(paths: tax.TaxonomyPaths) -> dict[str, Any]:
    analysis = paths.analysis_db
    with sqlite3.connect(f"{analysis.resolve().as_uri()}?mode=ro", uri=True, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        package: dict[str, Any]
        try:
            package = activation.assert_v2_active(conn).__dict__
        except Exception:
            package = {"status": "NOT_ACTIVE"}
        rp = []
        if _plain_table_exists(conn, "relative_position_active_snapshot"):
            rp = [dict(row) for row in conn.execute("SELECT * FROM relative_position_active_snapshot ORDER BY model_fingerprint")]
    try:
        rv = active_relative_valuation_identity(analysis)
        rv = {key: value for key, value in rv.items() if key != "database_path"}
    except Exception as exc:
        rv = {"status": "NOT_ACTIVE", "error": type(exc).__name__}
    return {"operating_income_package": package, "active_relative_position": rp, "active_relative_valuation": rv}


def _plain_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _taxonomy_dependency_state(paths: tax.TaxonomyPaths) -> dict[str, Any]:
    taxonomy = taxonomy_identity(paths.taxonomy_db)
    universe = _active_universe_identity(paths.canonical_db)
    try:
        compatibility = candidate_relative_valuation_dependency_state(
            paths.analysis_db,
            report_date="2026-09-12",
            expected_universe_fingerprint=universe.get("economic_result_fingerprint"),
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
    except Exception as exc:
        compatibility = {"status": "NOT_AVAILABLE", "error": type(exc).__name__, "reason": str(exc)}
    return {
        "taxonomy_economic_fingerprint": taxonomy.get("taxonomy_economic_fingerprint"),
        "taxonomy_presentation_fingerprint": taxonomy.get("taxonomy_presentation_fingerprint"),
        "compatibility": compatibility,
    }


def _active_universe_identity(canonical_db: Path) -> dict[str, Any]:
    with sqlite3.connect(f"{canonical_db.resolve().as_uri()}?mode=ro", uri=True, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        if not _plain_table_exists(conn, "fundamentals_operational_universe_active_version"):
            return {"status": "MISSING"}
        row = conn.execute(
            "SELECT v.* FROM fundamentals_operational_universe_active_version a "
            "JOIN fundamentals_operational_universe_version v USING(universe_version_id) WHERE a.singleton=1"
        ).fetchone()
    return dict(row) if row else {"status": "MISSING"}


def _downstream_fingerprint(paths: tax.TaxonomyPaths, snapshots: Mapping[str, Any] | None = None) -> dict[str, Any]:
    active = _active_identities(paths)
    dependency = _taxonomy_dependency_state(paths)
    dependency_rows = _analysis_dependency_fingerprint(paths.analysis_db)
    snapshot_fp = {
        ticker: {"status": item.get("status"), "fingerprint": item.get("fingerprint")}
        for ticker, item in sorted((snapshots or {}).items())
        if isinstance(item, Mapping)
    }
    payload = {"active_identities": active, "taxonomy_dependencies": dependency, "dependency_rows": dependency_rows, "snapshots": snapshot_fp}
    return {"payload": payload, "fingerprint": stable_hash(payload)}


def _analysis_dependency_fingerprint(analysis_db: Path) -> dict[str, Any]:
    run_local_columns = {
        "dependency_id",
        "created_at_utc",
        "dependency_as_of_date",
        "provenance_json",
        "taxonomy_source_fingerprint",
    }
    with sqlite3.connect(f"{analysis_db.resolve().as_uri()}?mode=ro", uri=True, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        output: dict[str, Any] = {}
        for table in ("fundamentals_result_dependency", "relative_valuation_snapshot_dependency"):
            if not _plain_table_exists(conn, table):
                output[table] = {"status": "MISSING", "row_count": 0, "fingerprint": None}
                continue
            rows = [
                {key: value for key, value in dict(row).items() if key not in run_local_columns}
                for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1,2,3,4")
            ]
            output[table] = {"status": "OK", "row_count": len(rows), "fingerprint": stable_hash(rows)}
    return output


def _run_downstream_once(paths: tax.TaxonomyPaths, output: Path, *, changed_ticker: str, progress: ProgressTracker | None) -> dict[str, Any]:
    from rawcandle.fundamentals.admin.sector_industry import _run_downstream

    with _background_heartbeat(progress, "Phase 13G.4.2 downstream closure chain is still running."):
        result = _run_downstream(
            BatchAddTickerPaths(paths.provider_db, paths.canonical_db, paths.analysis_db, paths.market_db, paths.taxonomy_db),
            output,
            changed_tickers=(changed_ticker,),
            applied_at=utc_now(),
            progress=None,
        )
    counts = dict(result.get("invocation_counts") or {})
    counts["dependency_attachment"] = 1 if result.get("dependencies") else 0
    counts["compatibility_verification"] = 1 if result.get("post_refresh_compatibility") else 0
    counts["snapshot"] = len(result.get("snapshots") or {})
    result["invocation_counts"] = counts
    result["fingerprints"] = _downstream_fingerprint(paths, result.get("snapshots"))
    return result


def _apply_and_downstream(
    paths: tax.TaxonomyPaths,
    *,
    candidate_csv: Path,
    candidate_version: str,
    affected_ticker: str,
    output: Path,
    progress: ProgressTracker | None,
) -> dict[str, Any]:
    before_downstream = _downstream_fingerprint(paths)
    apply = base._apply_candidate_to_lane(paths, candidate_csv, candidate_version)
    counters = taxonomy_change_counters({}, apply)
    downstream: dict[str, Any]
    if apply["taxonomy_apply"]["outcome"] == "NO_CHANGE":
        downstream = {
            "status": "SKIPPED_AFTER_TAXONOMY_NO_CHANGE",
            "invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0, "dependency_attachment": 0, "snapshot": 0},
            "fingerprints": before_downstream,
        }
    else:
        downstream = _run_downstream_once(paths, output, changed_ticker=affected_ticker, progress=progress)
    return {
        "apply": apply,
        "counters": counters,
        "downstream": downstream,
        "before_downstream": before_downstream,
        "after_downstream": _downstream_fingerprint(paths, downstream.get("snapshots")),
    }


def _copy_set_fingerprint(paths: tax.TaxonomyPaths) -> dict[str, Any]:
    state = {
        "taxonomy": base._fingerprints(paths),
        "downstream": _downstream_fingerprint(paths),
    }
    state["fingerprint"] = stable_hash(state)
    return state


def _write_report(result: Mapping[str, Any]) -> str:
    lines = [render_markdown_report(result).rstrip(), "", "## Phase 13G.4.2 Downstream Closure", ""]
    lines.append("Candidate status: `TEST_ONLY_NOT_FOR_PRODUCTION`")
    lines.append("Production writes: `0`")
    lines.append("")
    for key in (
        "baseline",
        "change_counters",
        "dependency_graph",
        "primary",
        "fixed_point_repeat",
        "replay",
        "rollback_after_downstream",
        "production_immutability",
        "scheduler",
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


def _dependency_graph() -> dict[str, Any]:
    return {
        "dc_ecosystem": {
            "direct_input": True,
            "consumed_identity": "taxonomy_identity.taxonomy_economic_fingerprint and active dc semantic fingerprint",
            "stale_detection": "candidate_relative_valuation_dependency_state and dependency rows compare active universe/taxonomy fingerprints",
        },
        "operating_income_package": {
            "direct_taxonomy_input": False,
            "invoked_for_full_chain": True,
            "reason": "The established admin downstream chain refreshes the package before RP/RV so copy lanes share the same authoritative ordering.",
        },
        "relative_position": {
            "direct_taxonomy_input": True,
            "field": "taxonomy_db through refresh_relative_position",
            "full_refresh_required": True,
        },
        "relative_valuation": {
            "direct_taxonomy_input": True,
            "field": "taxonomy_economic_fingerprint dependency compatibility",
            "full_refresh_required": True,
        },
        "dependency_attachment": {
            "direct_taxonomy_input": True,
            "field": "fundamentals_result_dependency and relative_valuation_snapshot_dependency",
        },
        "snapshot": {
            "direct_taxonomy_input": True,
            "field": "SnapshotPaths.taxonomy_db",
        },
    }


def run_dc_ecosystem_downstream_closure(
    *,
    source_paths: tax.TaxonomyPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = TEMP_ROOT,
    postflight_timeout_seconds: float = 20.0,
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
        options={"phase": "13G.4.2", "taxonomy_domain": "dc_ecosystem"},
    )
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"contract": CONTRACT_VERSION, "request": request}), suffix="dc_ecosystem_downstream_closure")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, run_dir=writer.run_dir, stages=TAXONOMY_DOWNSTREAM_CLOSURE_STAGES, callback=progress_callback)
    root = (temp_root / run_id).resolve()
    baseline_root = root / "baseline"
    primary_root = root / "primary_lane"
    replay_root = root / "replay_lane"
    rollback_root = root / "rollback_lane"
    lock_handle = None
    write_boundary_crossed = False
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Phase 13G.4.2 downstream closure request recorded.")
    writer.checkpoint(RunStage.APPLY_STARTED, message="Phase 13G.4.2 copy-only downstream closure orchestration started.")
    try:
        progress.running(ProgressStage.PREFLIGHT, "Verifying required commits, retained evidence and maintenance lock.")
        for short_hash in ("fe076a4", "6129d72"):
            if not base._commit_is_present(short_hash):
                raise RuntimeError(f"PHASE13G42_REQUIRED_COMMIT_MISSING:{short_hash}")
        lock_handle = PRODUCTION_LOCK_PATH.open("w")
        try:
            import fcntl

            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("PHASE13G42_MAINTENANCE_LOCK_BUSY") from exc
        retained = sorted(str(path) for path in (ADMIN_RUN_ROOT).glob("*dc_ecosystem_acceptance") if (path / "result.json").exists())
        preflight = {"required_commits_present": True, "retained_phase13g41_evidence": retained[-5:], "scheduler_evidence": dict(scheduler_evidence or {})}
        writer.write_json("preflight.json", preflight)
        progress.completed(ProgressStage.PREFLIGHT, "Preflight completed.")

        progress.running(ProgressStage.PAUSE_SCHEDULER, "Recording externally managed scheduler pause evidence.")
        scheduler = dict(scheduler_evidence or {"status": "EXTERNAL_SCHEDULER_EVIDENCE_NOT_SUPPLIED"})
        writer.write_json("scheduler_evidence.json", scheduler)
        progress.completed(ProgressStage.PAUSE_SCHEDULER, "Scheduler pause evidence recorded.")

        postflight_events: list[dict[str, Any]] = []

        def heartbeat(event: str, details: Mapping[str, Any]) -> None:
            postflight_events.append({"event": event, "details": dict(details), "timestamp_utc": utc_now()})
            writer.write_json("postflight_heartbeat.json", {"events": postflight_events[-100:]})

        progress.running(ProgressStage.PRODUCTION_LOGICAL_BASELINE, "Running bounded logical production baseline.")
        production_before = bounded_logical_postflight(source_paths, timeout_seconds=postflight_timeout_seconds, heartbeat=heartbeat)
        writer.write_json("production_logical_baseline.json", production_before)
        if production_before["status"] != "OK":
            raise RuntimeError("PHASE13G42_PRODUCTION_BASELINE_BLOCKED")
        progress.completed(ProgressStage.PRODUCTION_LOGICAL_BASELINE, "Production logical baseline captured.")

        progress.running(ProgressStage.CAPTURE_COPIES, "Capturing production-shaped baseline copies.")
        baseline_paths = base._copy_paths(source_paths, baseline_root)
        baseline_checks = base._db_checks(baseline_paths)
        writer.write_json("baseline_copy_inventory.json", baseline_checks)
        progress.completed(ProgressStage.CAPTURE_COPIES, "Baseline copies captured.")

        progress.running(ProgressStage.VALIDATE_COPIES, "Validating copy baseline and building test-only candidate.")
        baseline_fp = base._fingerprints(baseline_paths)
        baseline_set = _copy_set_fingerprint(baseline_paths)
        active_rows = tax._active_state(baseline_paths, "dc_ecosystem")["rows"]
        candidate = base._build_test_candidate(active_rows, str(baseline_fp["dc_active_version"]["taxonomy_version_code"]), writer.run_dir)
        validation = tax._validate_rows(candidate["rows"], identity_index=tax._active_state(baseline_paths, "dc_ecosystem")["identity_index"])
        if validation["status"] != "OK":
            raise RuntimeError(f"PHASE13G42_CANDIDATE_INVALID:{validation['errors']}")
        writer.write_json("test_only_candidate.json", {key: value for key, value in candidate.items() if key != "rows"})
        writer.write_json("candidate_validation.json", validation)
        progress.completed(ProgressStage.VALIDATE_COPIES, "Copy baseline and candidate validated.", processed_items=int(baseline_fp["dc_counts"]["rows"]))

        primary_paths = base._lane_from_baseline(baseline_paths, primary_root)
        preview = tax.run_preview(
            taxonomy_domain="dc_ecosystem",
            candidate_path=Path(candidate["candidate_csv"]),
            candidate_version=str(candidate["candidate_version"]),
            source_paths=primary_paths,
            run_root=writer.run_dir / "preview",
        )
        preview_json = json.loads((Path(preview["artifact_dir"]) / "preview.json").read_text(encoding="utf-8"))
        if preview_json.get("blockers"):
            raise RuntimeError(f"PHASE13G42_PREVIEW_BLOCKED:{preview_json['blockers']}")
        writer.write_json("preview_summary.json", preview_json)

        progress.running(ProgressStage.APPLY_TAXONOMY, "Applying test-only taxonomy candidate on primary lane.")
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Copy-only taxonomy write boundary crossed on isolated primary lane.", preview_fingerprint=str(preview.get("preview_fingerprint")), write_boundary_crossed=True)
        write_boundary_crossed = True
        primary_apply = base._apply_candidate_to_lane(primary_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        change_counters = taxonomy_change_counters(preview_json.get("change_counts") or {}, primary_apply)
        if change_counters["semantic_changes"] != 1 or change_counters["role_or_tier_changes"] != 1:
            raise RuntimeError("PHASE13G42_UNEXPECTED_SEMANTIC_COUNTERS")
        writer.write_json("primary_taxonomy_apply.json", primary_apply)
        writer.write_json("change_counters.json", change_counters)
        progress.completed(ProgressStage.APPLY_TAXONOMY, "Taxonomy candidate applied to primary lane.")

        progress.running(ProgressStage.ATTACH_DEPENDENCIES, "Recording dependency graph and running full downstream chain.")
        dependency_graph = _dependency_graph()
        writer.write_json("dependency_graph.json", dependency_graph)
        primary_downstream = _run_downstream_once(primary_paths, writer.run_dir / "primary_downstream", changed_ticker=str(candidate["affected_ticker"]), progress=progress)
        change_counters["dependency_rows_written"] = int(bool(primary_downstream.get("dependencies")))
        writer.write_json("primary_downstream.json", primary_downstream)
        progress.completed(ProgressStage.ATTACH_DEPENDENCIES, "Full downstream chain completed.")
        for stage in (ProgressStage.PACKAGE_REFRESH, ProgressStage.RELATIVE_POSITION_REFRESH, ProgressStage.RELATIVE_VALUATION_REFRESH, ProgressStage.SNAPSHOT_SMOKE):
            progress.running(stage, f"{stage.value} evidence persisted.")
            progress.completed(stage, f"{stage.value} evidence persisted.")

        progress.running(ProgressStage.FIXED_POINT_REPEAT, "Repeating identical candidate after downstream refresh.")
        repeat = base._repeat_no_change(primary_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        repeat["downstream_invocation_counts"] = {"package": 0, "relative_position": 0, "relative_valuation": 0}
        repeat["after_downstream"] = _downstream_fingerprint(primary_paths, primary_downstream.get("snapshots"))
        writer.write_json("fixed_point_repeat.json", repeat)
        if repeat["outcome"] != "NO_CHANGE":
            raise RuntimeError("PHASE13G42_FIXED_POINT_NO_CHANGE_FAILED")
        progress.completed(ProgressStage.FIXED_POINT_REPEAT, "Fixed-point repeat NO_CHANGE verified.")

        progress.running(ProgressStage.INDEPENDENT_REPLAY, "Running independent replay lane with full downstream chain.")
        replay_paths = base._lane_from_baseline(baseline_paths, replay_root)
        replay_apply = base._apply_candidate_to_lane(replay_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        replay_downstream = _run_downstream_once(replay_paths, writer.run_dir / "replay_downstream", changed_ticker=str(candidate["affected_ticker"]), progress=progress)
        replay_repeat = base._repeat_no_change(replay_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        replay_match = {
            "taxonomy_semantic_fingerprint": primary_apply["after"]["dc_semantic_fingerprint"] == replay_apply["after"]["dc_semantic_fingerprint"],
            "membership_fingerprint": primary_apply["after"]["taxonomy_identity"]["taxonomy_economic_fingerprint"] == replay_apply["after"]["taxonomy_identity"]["taxonomy_economic_fingerprint"],
            "hierarchy_fingerprint": primary_apply["after"]["taxonomy_identity"]["taxonomy_presentation_fingerprint"] == replay_apply["after"]["taxonomy_identity"]["taxonomy_presentation_fingerprint"],
            "downstream_fingerprint": primary_downstream["fingerprints"]["fingerprint"] == replay_downstream["fingerprints"]["fingerprint"],
            "repeat_no_change": replay_repeat["outcome"] == "NO_CHANGE",
        }
        replay = {"apply": replay_apply, "downstream": replay_downstream, "repeat": replay_repeat, "lane_match": replay_match, "status": "MATCH" if all(replay_match.values()) else "MISMATCH"}
        writer.write_json("independent_replay.json", replay)
        if replay["status"] != "MATCH":
            raise RuntimeError("PHASE13G42_REPLAY_MISMATCH")
        progress.completed(ProgressStage.INDEPENDENT_REPLAY, "Independent replay matched primary lane.")

        progress.running(ProgressStage.ROLLBACK_AFTER_DOWNSTREAM, "Proving complete restore after taxonomy and downstream writes.")
        rollback_paths = base._lane_from_baseline(baseline_paths, rollback_root)
        rollback_apply = base._apply_candidate_to_lane(rollback_paths, Path(candidate["candidate_csv"]), str(candidate["candidate_version"]))
        rollback_downstream = _run_downstream_once(rollback_paths, writer.run_dir / "rollback_downstream", changed_ticker=str(candidate["affected_ticker"]), progress=progress)
        partial = _copy_set_fingerprint(rollback_paths)
        restored_paths = base._restore_lane_from_baseline(baseline_paths, rollback_root)
        restored = _copy_set_fingerprint(restored_paths)
        rollback = {
            "partial_taxonomy_state_existed": rollback_apply["changed"],
            "partial_downstream_state_existed": partial["fingerprint"] != baseline_set["fingerprint"],
            "restored_matches_baseline": restored["fingerprint"] == baseline_set["fingerprint"],
            "downstream_invocation_counts_before_restore": rollback_downstream.get("invocation_counts"),
            "baseline": baseline_set,
            "partial": partial,
            "restored": restored,
        }
        writer.write_json("rollback_after_downstream.json", rollback)
        if not rollback["partial_taxonomy_state_existed"] or not rollback["partial_downstream_state_existed"] or not rollback["restored_matches_baseline"]:
            raise RuntimeError("PHASE13G42_ROLLBACK_AFTER_DOWNSTREAM_FAILED")
        progress.completed(ProgressStage.ROLLBACK_AFTER_DOWNSTREAM, "Rollback after downstream write boundary verified.")

        progress.running(ProgressStage.PRODUCTION_LOGICAL_POSTFLIGHT, "Running bounded logical production postflight.")
        production_after = bounded_logical_postflight(source_paths, timeout_seconds=postflight_timeout_seconds, heartbeat=heartbeat)
        production_compare = compare_bounded_postflight(production_before, production_after)
        production_immutability = {"before": production_before, "after": production_after, "comparison": production_compare}
        writer.write_json("production_logical_postflight.json", production_after)
        writer.write_json("production_immutability.json", production_immutability)
        if production_compare["status"] != "MATCH":
            raise RuntimeError("PHASE13G42_PRODUCTION_LOGICAL_STATE_CHANGED")
        progress.completed(ProgressStage.PRODUCTION_LOGICAL_POSTFLIGHT, "Bounded production postflight matched baseline.")

        progress.running(ProgressStage.RESTORE_SCHEDULER, "Recording scheduler restore evidence.")
        progress.completed(ProgressStage.RESTORE_SCHEDULER, "Scheduler restore evidence recorded.")

        progress.running(ProgressStage.CLEANUP, "Removing Phase 13G.4.2 copy lanes.")
        cleanup = base._cleanup(root)
        writer.write_json("cleanup.json", cleanup)
        progress.completed(ProgressStage.CLEANUP, "Cleanup completed.")

        result = {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "contract_version": CONTRACT_VERSION,
            "outcome_text": OUTCOME_A,
            "baseline": {"production": production_before, "copy": baseline_fp, "copy_set": baseline_set},
            "candidate": {key: value for key, value in candidate.items() if key != "rows"},
            "preview": {"preview_fingerprint": preview.get("preview_fingerprint"), "artifact_dir": preview.get("artifact_dir"), "change_counts": preview_json.get("change_counts")},
            "change_counters": change_counters,
            "dependency_graph": dependency_graph,
            "primary": {"apply": primary_apply, "downstream": primary_downstream},
            "fixed_point_repeat": repeat,
            "replay": replay,
            "rollback_after_downstream": rollback,
            "production_immutability": production_immutability,
            "scheduler": scheduler,
            "cleanup": cleanup,
            "tests": {"full_suite": "NOT_RUN_BY_CLOSURE_ORCHESTRATOR"},
        }
        final = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.COMPLETED,
            mode="DC_ECOSYSTEM_DOWNSTREAM_COPY_ONLY_CLOSURE",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=str(preview.get("preview_fingerprint")),
            request=request.as_dict(),
            summary_counts=change_counters,
            downstream={"invocation_counts": primary_downstream.get("invocation_counts", {})},
            rollback=rollback,
            artifacts={"report": str(writer.run_dir / "report.md")},
            recommended_next_action=OUTCOME_A,
        )
        result["final_result"] = final.as_dict()
        writer.write_json("result.json", result)
        writer.write_text("report.md", _write_report(result))
        writer.checkpoint(RunStage.COMPLETED, message=OUTCOME_A, preview_fingerprint=str(preview.get("preview_fingerprint")), counters=change_counters, write_boundary_crossed=True)
        writer.write_exit_code(0)
        writer.write_manifest()
        progress.running(ProgressStage.COMPLETED, "Downstream closure completed.")
        progress.completed(ProgressStage.COMPLETED, "Downstream closure completed.")
        return result
    except Exception as exc:
        if root.exists() and not keep_copies_on_failure:
            shutil.rmtree(root, ignore_errors=True)
        writer.write_error(exc)
        final = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.FAILED,
            mode="DC_ECOSYSTEM_DOWNSTREAM_COPY_ONLY_CLOSURE",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=None,
            request=request.as_dict(),
            recommended_next_action=OUTCOME_C,
            errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
        )
        result = final.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "error": type(exc).__name__, "outcome_text": OUTCOME_C}
        writer.write_json("result.json", result)
        writer.write_text("report.md", _write_report(result))
        writer.checkpoint(RunStage.FAILED_AFTER_WRITE if write_boundary_crossed else RunStage.FAILED_BEFORE_WRITE, message=OUTCOME_C, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(2)
        writer.write_manifest()
        return result
    finally:
        if lock_handle is not None:
            try:
                import fcntl

                fcntl.flock(lock_handle, fcntl.LOCK_UN)
            finally:
                lock_handle.close()
