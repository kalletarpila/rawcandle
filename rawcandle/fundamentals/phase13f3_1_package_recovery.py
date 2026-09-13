from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from rawcandle.fundamentals.operating_income_v2 import activation, phase10b
from rawcandle.fundamentals.operating_income_v2.persistence import row_counts
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    compare_production_inventory,
    database_inventory,
    production_inventory,
    stable_hash,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    ensure_candidate_schema,
    online_backup,
    reject_production_path,
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13f3_ticker_transition import (
    APPLIED_AT,
    REPORT_DATE,
    _apply_transition_identities,
    _areb_counts,
    _manual_rv_refresh,
    _snapshot_smoke,
    _storage,
    _valuation_classification_update,
    classification_summary,
    enhanced_listing_population,
    transition_evidence,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position


PHASE = "PHASE13F3_1_PACKAGE_REFRESH_RECOVERY"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13f3_1_package_refresh_recovery")
DEFAULT_RUN_ID = "20260913T_PHASE13F3_1_PACKAGE_REFRESH_RECOVERY"
OUTCOME_A = "OUTCOME A — PACKAGE REFRESH RECOVERED AND COMPLETE COPY-ONLY TECHNICAL CHAIN VERIFIED; OWN-HISTORY PRODUCTION ACTIVATION STILL DEFERRED"
OUTCOME_B = "OUTCOME B — PACKAGE REFRESH OR DOWNSTREAM TECHNICAL CHAIN STILL BLOCKED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sidecars(path: Path) -> dict[str, Any]:
    out = {}
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        out[suffix.removeprefix("-")] = {
            "exists": sidecar.exists(),
            "size": sidecar.stat().st_size if sidecar.exists() else 0,
        }
    return out


def _db_runtime_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        return {
            "exists": True,
            "path": str(path.resolve()),
            "size": path.stat().st_size,
            "page_count": conn.execute("PRAGMA page_count").fetchone()[0],
            "freelist_count": conn.execute("PRAGMA freelist_count").fetchone()[0],
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
            "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_errors": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
            "sidecars": _sidecars(path),
        }


class StageTelemetry:
    def __init__(self, output: Path, *, analysis_db: Path) -> None:
        self.output = output
        self.analysis_db = analysis_db
        self.events: list[dict[str, Any]] = []
        self._started = time.monotonic()
        self.output.mkdir(parents=True, exist_ok=True)

    def emit(self, stage: str, status: str, *, include_db_state: bool = True, **payload: Any) -> None:
        event = {
            "sequence": len(self.events) + 1,
            "stage": stage,
            "status": status,
            "timestamp_utc": utc_now(),
            "elapsed_seconds": round(time.monotonic() - self._started, 3),
            "pid": None,
            "analysis_db": _db_runtime_state(self.analysis_db) if include_db_state else {
                "path": str(self.analysis_db.resolve()),
                "size": self.analysis_db.stat().st_size if self.analysis_db.exists() else None,
                "sidecars": _sidecars(self.analysis_db),
                "sqlite_state_skipped": "write_transaction_active",
            },
            "storage": _storage(stage),
            **payload,
        }
        self.events.append(event)
        write_json(self.output / "package_refresh_telemetry.json", {"events": self.events})

    @contextmanager
    def heartbeat(self, stage: str, *, interval_seconds: float = 15.0) -> Iterator[None]:
        stop = threading.Event()

        def run() -> None:
            tick = 0
            while not stop.wait(interval_seconds):
                tick += 1
                self.emit(stage, "RUNNING", heartbeat=tick)

        thread = threading.Thread(target=run, name=f"{stage}-heartbeat", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=interval_seconds)


def instrumented_package_refresh(paths: Mapping[str, Path], output: Path) -> dict[str, Any]:
    analysis = paths["analysis"]
    reject_production_path(analysis, "analysis")
    telemetry = StageTelemetry(output, analysis_db=analysis)
    telemetry.emit("package_refresh", "STARTED", paths={key: str(value.resolve()) for key, value in paths.items()})
    with sqlite3.connect(f"file:{analysis.resolve()}?mode=ro", uri=True) as reader:
        active = activation.assert_v2_active(reader)
    candidate_active = active.persistence_fingerprint in {
        phase10b.PACKAGE_FINGERPRINT,
        activation.TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT,
    }
    if not candidate_active:
        raise RuntimeError(f"PHASE13F3_1_UNSUPPORTED_ACTIVE_PACKAGE:{active.persistence_fingerprint}")

    telemetry.emit(
        "calculate",
        "STARTED",
        active_package=asdict(active),
        verify_v1_overlap=active.persistence_fingerprint != activation.TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT,
    )
    calculate_started = time.monotonic()
    with telemetry.heartbeat("calculate"):
        calculated = phase10b.calculate(
            paths,
            verify_v1_overlap=active.persistence_fingerprint != activation.TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT,
        )
    telemetry.emit(
        "calculate",
        "COMPLETED",
        elapsed_stage_seconds=round(time.monotonic() - calculate_started, 3),
        rows={
            "ttm_rows": len(calculated["rows"]),
            "score_rows": len(calculated["score_v2"]),
            "diagnostic_rows": len(calculated["diagnostics_full"]),
            "fresh_rows": len(calculated["fresh"]),
        },
        fingerprints=calculated.get("fingerprints", {}),
    )

    stage_marks: list[dict[str, Any]] = []

    def apply_stage(stage: str, conn: sqlite3.Connection) -> None:
        counts = row_counts(conn, diagnostic_model=phase10b.diagnostic_flags_eight)
        mark = {
            "stage": stage,
            "timestamp_utc": utc_now(),
            "counts": counts,
            "in_transaction": conn.in_transaction,
        }
        stage_marks.append(mark)
        telemetry.emit(
            f"apply_{stage}",
            "COMPLETED",
            include_db_state=False,
            counts=counts,
            in_transaction=conn.in_transaction,
        )

    telemetry.emit("apply", "STARTED")
    apply_started = time.monotonic()
    with sqlite3.connect(analysis) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=60000")
        first = phase10b.apply_candidate_package(
            conn,
            calculated,
            applied_at=APPLIED_AT,
            persistence_fingerprint=active.persistence_fingerprint,
            stage_callback=apply_stage,
        )
        validation = phase10b.validate_candidate_package(conn)
        before_second = database_inventory(analysis)
        second_started = time.monotonic()
        second = phase10b.apply_candidate_package(
            conn,
            calculated,
            applied_at=APPLIED_AT,
            persistence_fingerprint=active.persistence_fingerprint,
        )
        after_second = database_inventory(analysis)
        active_after = activation.assert_v2_active(conn)
    telemetry.emit(
        "apply",
        "COMPLETED",
        elapsed_stage_seconds=round(time.monotonic() - apply_started, 3),
        first_apply=asdict(first),
        validation=validation,
        second_apply=asdict(second),
        second_elapsed_seconds=round(time.monotonic() - second_started, 3),
        second_physical_no_change=before_second == after_second,
        active_after=asdict(active_after),
    )
    result = {
        "outcome": first.outcome,
        "root_cause_classification": "LONG_RUNNING_AUTHORITATIVE_CALCULATION_WITHOUT_INNER_PROGRESS_OUTPUT",
        "active_before": asdict(active),
        "active_after": asdict(active_after),
        "calculation_fingerprints": calculated.get("fingerprints", {}),
        "first_apply": asdict(first),
        "second_apply": asdict(second),
        "second_physical_no_change": before_second == after_second,
        "validation": validation,
        "stage_marks": stage_marks,
        "telemetry_path": str(output / "package_refresh_telemetry.json"),
    }
    write_json(output / "package_refresh_result.json", result)
    return result


def _copy_rehearsal(output: Path, lane: str) -> dict[str, Any]:
    lane_dir = output / lane
    copies = lane_dir / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    canonical = copies / "fundamentals_v4.db"
    analysis = copies / "fundamentals_analysis.db"
    result: dict[str, Any] = {"lane": lane, "started_at_utc": utc_now()}
    try:
        result["backups"] = {
            "canonical": online_backup(PRODUCTION["canonical"], canonical),
            "analysis": online_backup(PRODUCTION["analysis"], analysis),
        }
        paths = CandidatePaths(canonical, analysis, PRODUCTION["taxonomy"], provider_db=PRODUCTION["provider"], market_db=PRODUCTION["market"])
        result["identity"] = _apply_transition_identities(canonical)
        result["valuation_classification"] = _valuation_classification_update(analysis, PRODUCTION["market"], canonical)
        ensure_candidate_schema(paths, applied_at_utc=APPLIED_AT, apply=True)
        universe = backfill_universe(paths, applied_at_utc=APPLIED_AT, apply=True)
        result["universe"] = universe
        package = instrumented_package_refresh(
            {
                "provider": PRODUCTION["provider"],
                "canonical": canonical,
                "analysis": analysis,
                "market": PRODUCTION["market"],
                "taxonomy": PRODUCTION["taxonomy"],
            },
            lane_dir,
        )
        result["package"] = package
        rp = refresh_relative_position(
            canonical_db=canonical,
            analysis_db=analysis,
            market_db=PRODUCTION["market"],
            taxonomy_db=PRODUCTION["taxonomy"],
            snapshot_date=REPORT_DATE,
            model_fingerprint=RP_MODEL_FINGERPRINT,
            applied_at_utc=APPLIED_AT,
        )
        result["relative_position"] = asdict(rp)
        taxonomy = taxonomy_identity(PRODUCTION["taxonomy"])
        pre_refresh = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["pre_refresh_compatibility"] = pre_refresh
        rv = _manual_rv_refresh(paths, output=lane_dir)
        result["relative_valuation"] = rv
        dependencies = attach_dependencies(paths, universe=universe["identity"], applied_at_utc=APPLIED_AT, apply=True)
        result["dependencies"] = dependencies
        post_refresh = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["post_refresh_compatibility"] = post_refresh
        result["snapshots"] = _snapshot_smoke(paths, lane_dir)
        result["areb_after"] = _areb_counts(analysis)
        result["final_inventory"] = {"canonical": database_inventory(canonical), "analysis": database_inventory(analysis)}
        write_json(lane_dir / "rehearsal_result.json", result)
        return result
    except BaseException as exc:
        result["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        write_json(lane_dir / "rehearsal_failure.json", result)
        raise
    finally:
        if copies.exists():
            shutil.rmtree(copies)
        write_json(lane_dir / "cleanup.json", {
            "transient_copies_removed": not copies.exists(),
            "storage": _storage("cleanup"),
            "remaining_database_artifacts": [
                str(path) for path in lane_dir.rglob("*")
                if path.suffix in {".db", ".sqlite"} or path.name.endswith(("-wal", "-shm", "-journal"))
            ],
        })


def _economic_fingerprint(result: Mapping[str, Any]) -> str:
    return stable_hash({
        "identity": result["identity"]["fingerprint"],
        "universe": result["universe"]["identity"]["economic_result_fingerprint"],
        "package": result["package"]["first_apply"]["economic_result_fingerprint"],
        "relative_position": result["relative_position"]["result_fingerprint"],
        "relative_valuation": result["relative_valuation"]["snapshot"]["result_fingerprint"],
        "snapshots": {
            ticker: {
                key: value for key, value in row.items()
                if key in {"status", "fingerprint", "error", "reason"}
            }
            for ticker, row in result["snapshots"].items()
        },
    })


def run_phase13f3_1(output: Path | None = None) -> dict[str, Any]:
    started = time.monotonic()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    reject_production_path(output, "output")
    output.mkdir(parents=True, exist_ok=True)
    pre_inventory = production_inventory()
    transitions = transition_evidence(CandidateAuditPaths)
    listing = enhanced_listing_population(CandidateAuditPaths)
    classification = classification_summary(CandidateAuditPaths)
    blockers: list[str] = ["OWN_HISTORY_STRUCTURAL_BREAK_POLICY_REQUIRES_SEPARATE_VERSIONED_CONTRACT"]
    run_1: dict[str, Any] | None = None
    replay: dict[str, Any] | None = None
    try:
        run_1 = _copy_rehearsal(output, "run_1")
        first_ok = (
            run_1["package"]["outcome"] in {"APPLIED", "NO_CHANGE"}
            and run_1["post_refresh_compatibility"]["state"] == "COMPATIBLE"
            and all(row.get("status") != "FAILED" for row in run_1["snapshots"].values())
            and int(run_1["areb_after"]["post_delisting_relative_valuation_rows"]) == 0
        )
        if first_ok:
            replay = _copy_rehearsal(output, "run_2")
            deterministic = {
                "run_1": _economic_fingerprint(run_1),
                "run_2": _economic_fingerprint(replay),
            }
            deterministic["match"] = deterministic["run_1"] == deterministic["run_2"]
            if not deterministic["match"]:
                blockers.append("DETERMINISTIC_REPLAY_MISMATCH")
        else:
            deterministic = {"match": False, "reason": "FIRST_RUN_DID_NOT_PASS_RECONCILIATION"}
            if run_1["post_refresh_compatibility"]["state"] != "COMPATIBLE":
                blockers.append(f"POST_REFRESH_RV_COMPATIBILITY:{run_1['post_refresh_compatibility']['state']}")
            failed_snapshots = {
                ticker: row.get("reason") or row.get("error")
                for ticker, row in run_1["snapshots"].items()
                if row.get("status") == "FAILED"
            }
            if failed_snapshots:
                blockers.append("SNAPSHOT_SMOKE_FAILURES:" + json.dumps(failed_snapshots, sort_keys=True))
            if int(run_1["areb_after"]["post_delisting_relative_valuation_rows"]):
                blockers.append(
                    f"AREB_POST_DELISTING_CURRENT_RV_ROWS:{run_1['areb_after']['post_delisting_relative_valuation_rows']}"
                )
            if len(blockers) == 1:
                blockers.append("FIRST_COPY_REHEARSAL_RECONCILIATION_FAILED")
    except BaseException as exc:
        deterministic = {"match": False, "reason": type(exc).__name__, "message": str(exc)}
        blockers.append("PACKAGE_REFRESH_OR_DOWNSTREAM_CHAIN_EXCEPTION")
    post_inventory = production_inventory()
    result = {
        "phase": PHASE,
        "outcome": OUTCOME_A if blockers == ["OWN_HISTORY_STRUCTURAL_BREAK_POLICY_REQUIRES_SEPARATE_VERSIONED_CONTRACT"] else OUTCOME_B,
        "blockers": blockers,
        "transitions": transitions,
        "listing_unresolved_current_active_count": listing["unresolved_current_active_count"],
        "classification_counts": classification["counts"],
        "run_1": run_1,
        "run_2": replay,
        "determinism": deterministic,
        "production_immutability": compare_production_inventory(pre_inventory, post_inventory),
        "storage": {"final": _storage("final")},
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    write_json(output / "phase13f3_1_result.json", result)
    report = render_report(output, result)
    result["report"] = report
    write_json(output / "phase13f3_1_result.json", result)
    return result


def render_report(output: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    package = (result.get("run_1") or {}).get("package") or {}
    lines = [
        "# Phase 13F.3.1 Package Refresh Recovery",
        "",
        f"Outcome: **{result['outcome']}**",
        "",
        f"Package root-cause classification: `{package.get('root_cause_classification', 'NOT_COMPLETED')}`",
        f"Package first apply: `{(package.get('first_apply') or {}).get('outcome')}`",
        f"Package second apply: `{(package.get('second_apply') or {}).get('outcome')}`",
        f"Post-refresh RV compatibility: `{((result.get('run_1') or {}).get('post_refresh_compatibility') or {}).get('state')}`",
        f"Deterministic replay: `{(result.get('determinism') or {}).get('match')}`",
        f"Production immutable: `{result['production_immutability']['identical']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{blocker}`" for blocker in result["blockers"])
    text = "\n".join(lines) + "\n"
    path = output / "phase13f3_1_report.md"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "bytes": len(text.encode("utf-8"))}


from rawcandle.fundamentals.phase13f1_reconciliation import AuditPaths

CandidateAuditPaths = AuditPaths()
