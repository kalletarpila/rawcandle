from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    REPORT_ROOT,
    ROOT,
    SCHEDULER_CONFIG,
    compare_production_inventory,
    database_inventory,
    rebuild_ttm,
    reconcile_canonical,
    sha256,
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
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13f3_1_package_recovery import instrumented_package_refresh
from rawcandle.fundamentals.phase13f3_2_successor_recovery import (
    _apply_provider_identity_links,
    archive_reconciliation,
    stage_provider_rows,
    successor_canonical_ttm_report,
)
from rawcandle.fundamentals.phase13f3_3_structural_break_contract import (
    _events,
    _structural_evidence,
    _structural_package_fingerprint,
)
from rawcandle.fundamentals.phase13f3_ticker_transition import (
    APPLIED_AT,
    REPORT_DATE,
    _apply_transition_identities,
    _areb_counts,
    _manual_rv_refresh,
    _snapshot_smoke,
    _valuation_classification_update,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position


PHASE = "PHASE13F4_2_STRUCTURAL_PRODUCTION_FULL_BACKUP_ROLLBACK"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13f4_2_structural_production"
BACKUP_ROOT = ROOT / "backups/fundamentals_v4_phase13f4_2_structural_production"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"
DEFAULT_RUN_ID = "20260913T_PHASE13F4_2_STRUCTURAL_PRODUCTION"
WRITE_ROLES = ("provider", "canonical", "analysis")
READ_ONLY_ROLES = ("market", "taxonomy")

ACCEPTED = {
    "structural_contract": "ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1",
    "structural_package_fingerprint": "748cd15828bef0bd57f75f977aadea571053940e94b38c2a221b43335e0d6c9a",
    "event_fingerprint": "085690bdb3479a88f53cac4248e0ab970a0a743934eca29d1d867a8eba57096d",
    "structural_source_fingerprint": "c9fd41fdedc7b926d801bf7d56884746e552bc6593fba92c22db1e522c1a63d6",
    "structural_regime_fingerprint": "57e2827981be62c9c300ac0e0a71a26afefd04dd9b9f85670593c57ebcdff8e5",
    "package_economic_result_fingerprint": "1700f71e13935fccf7509cf8b9e99fb9f6705cfe9ddf5f49157b53d59a85e4d5",
    "package_physical_content_fingerprint": "f6144cc126d1a5c3af8735841800903e5e233a1953712ca4b5dd1ba0b67f654a",
    "rv_snapshot": "1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b",
    "rv_result_fingerprint": "9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3",
    "rv_source_fingerprint": "af0e480b64d57bfc8f65fe2ddf9777cfdf5d7b8afbb801bcf95aaea44ebc61ee",
}

OUTCOME_A = "OUTCOME A — STRUCTURAL-REGIME PACKAGE ACTIVE IN PRODUCTION AND VERIFIED STABLE UNDER FULL-BACKUP ROLLBACK POLICY"
OUTCOME_B = "OUTCOME B — PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED"
OUTCOME_C = "OUTCOME C — DEPLOYMENT FAILED AND COMPLETE BACKUP SET RESTORED SUCCESSFULLY"
OUTCOME_D = "OUTCOME D — PRODUCTION STATE UNRESOLVED; MANUAL RECOVERY REQUIRED"


class PhaseStageJournal:
    def __init__(self, output: Path, backup_dir: Path, phase: str, *, heartbeat_seconds: float = 10.0) -> None:
        self.output = output
        self.backup_dir = backup_dir
        self.phase = phase
        self.heartbeat_seconds = heartbeat_seconds
        self.journal_path = output / "stage_journal.jsonl"
        self.current_path = output / "stage_current.json"
        self.heartbeat_path = output / "heartbeat.jsonl"
        self.exit_code_path = output / "exit_code"
        self._previous_stage: str | None = None
        self._sequence = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _atomic_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _append_jsonl(self, path: Path, payload: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def checkpoint(
        self,
        stage: str,
        *,
        writes_may_have_occurred: bool,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._sequence += 1
        payload = {
            "phase": self.phase,
            "run_id": self.output.name,
            "timestamp_utc": utc_now(),
            "pid": os.getpid(),
            "sequence": self._sequence,
            "stage": stage,
            "writes_may_have_occurred": writes_may_have_occurred,
            "artifact_dir": str(self.output),
            "backup_dir": str(self.backup_dir),
            "preceding_completed_stage": self._previous_stage,
            "details": dict(details or {}),
        }
        self._append_jsonl(self.journal_path, payload)
        self._atomic_json(self.current_path, payload)
        self._previous_stage = stage
        print(f"[{payload['timestamp_utc']}] {self.phase} {stage}", flush=True)
        return payload

    def start_heartbeat(self) -> None:
        if self._thread is not None:
            return

        def beat() -> None:
            while not self._stop.wait(self.heartbeat_seconds):
                self._append_jsonl(self.heartbeat_path, {
                    "phase": self.phase,
                    "run_id": self.output.name,
                    "timestamp_utc": utc_now(),
                    "pid": os.getpid(),
                    "stage": self._previous_stage,
                    "artifact_dir": str(self.output),
                    "backup_dir": str(self.backup_dir),
                })

        self._thread = threading.Thread(target=beat, name=f"{self.phase}_heartbeat", daemon=True)
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def write_exit_code(self, code: int) -> None:
        tmp = self.exit_code_path.with_name(f".{self.exit_code_path.name}.{os.getpid()}.tmp")
        tmp.write_text(f"{code}\n", encoding="utf-8")
        tmp.replace(self.exit_code_path)


@dataclass(frozen=True)
class AcceptanceField:
    check_id: str
    path: tuple[str, ...]
    meaning: str
    expected: Any
    expected_type: str
    nullable: bool
    identity_kind: str
    failure_reason: str


ACCEPTANCE_CONTRACT: tuple[AcceptanceField, ...] = (
    AcceptanceField("PROVIDER_STAGING_REPLAY_NO_CHANGE", ("provider_staging_replay_logical_changes",), "Second provider staging pass must be logical no-change.", 0, "int", False, "calculated result", "PROVIDER_STAGING_REPLAY_NOT_NO_CHANGE"),
    AcceptanceField("STRUCTURAL_CONTRACT_VERSION", ("structural_contract_version",), "Versioned structural-break economic contract identity.", ACCEPTED["structural_contract"], "str", False, "source input", "STRUCTURAL_CONTRACT_VERSION"),
    AcceptanceField("STRUCTURAL_EVENT_COUNT", ("structural_event_count",), "Accepted structural-event population size.", 5, "int", False, "source input", "STRUCTURAL_EVENT_COUNT"),
    AcceptanceField("STRUCTURAL_QUARTER_REGIME_COUNT", ("structural_quarter_regime_count",), "Canonical quarters assigned to structural regimes.", 197, "int", False, "calculated result", "STRUCTURAL_QUARTER_REGIME_COUNT"),
    AcceptanceField("STRUCTURAL_TTM_REGIME_COUNT", ("structural_ttm_regime_count",), "TTM endpoints assigned to structural regimes.", 197, "int", False, "calculated result", "STRUCTURAL_TTM_REGIME_COUNT"),
    AcceptanceField("STRUCTURAL_SOURCE_FINGERPRINT", ("structural_source_fingerprint",), "Current structural source/dependency fingerprint exposed by Relative Valuation source metadata.", ACCEPTED["structural_source_fingerprint"], "str", False, "dependency state", "STRUCTURAL_SOURCE_FINGERPRINT"),
    AcceptanceField("STRUCTURAL_EVENT_FINGERPRINT", ("structural_event_fingerprint",), "Structural event economic fingerprint.", ACCEPTED["event_fingerprint"], "str", False, "source input", "STRUCTURAL_EVENT_FINGERPRINT"),
    AcceptanceField("STRUCTURAL_REGIME_FINGERPRINT", ("structural_regime_fingerprint",), "Full structural regime assignment fingerprint.", ACCEPTED["structural_regime_fingerprint"], "str", False, "calculated result", "STRUCTURAL_REGIME_FINGERPRINT"),
    AcceptanceField("STRUCTURAL_PACKAGE_FINGERPRINT", ("structural_package_fingerprint",), "Structural package dependency fingerprint derived from the regime fingerprint.", ACCEPTED["structural_package_fingerprint"], "str", False, "dependency state", "STRUCTURAL_PACKAGE_FINGERPRINT"),
    AcceptanceField("PACKAGE_FIRST_OUTCOME", ("package_first_outcome",), "First package apply must activate the accepted package.", "APPLIED", "str", False, "persisted content", "PACKAGE_FIRST_OUTCOME"),
    AcceptanceField("PACKAGE_SECOND_OUTCOME", ("package_second_outcome",), "Inner package replay must be no-change.", "NO_CHANGE", "str", False, "persisted content", "PACKAGE_SECOND_OUTCOME"),
    AcceptanceField("PACKAGE_SECOND_LOGICAL_CHANGES", ("package_second_logical_changes",), "Inner package replay must write zero logical rows.", 0, "int", False, "persisted content", "PACKAGE_SECOND_LOGICAL_CHANGES"),
    AcceptanceField("PACKAGE_PHYSICAL_NO_CHANGE", ("package_second_physical_no_change",), "Inner package replay must preserve physical content fingerprint.", True, "bool", False, "persisted content", "PACKAGE_PHYSICAL_NO_CHANGE"),
    AcceptanceField("PACKAGE_ECONOMIC_FINGERPRINT", ("package_economic_fingerprint",), "Accepted Operating-Income V2 package economic result fingerprint.", ACCEPTED["package_economic_result_fingerprint"], "str", False, "persisted content", "PACKAGE_ECONOMIC_FINGERPRINT"),
    AcceptanceField("PACKAGE_PHYSICAL_FINGERPRINT", ("package_physical_fingerprint",), "Accepted Operating-Income V2 package physical content fingerprint.", ACCEPTED["package_physical_content_fingerprint"], "str", False, "persisted content", "PACKAGE_PHYSICAL_FINGERPRINT"),
    AcceptanceField("DIAGNOSTIC_EVALUATION_MULTIPLIER", ("diagnostic_evaluation_multiplier_ok",), "All eight diagnostic evaluations must exist for every diagnostic endpoint.", True, "bool", False, "persisted content", "DIAGNOSTIC_EVALUATION_MULTIPLIER"),
    AcceptanceField("DEPENDENCY_ATTACHMENT_STATUS", ("dependency_status",), "Operational-universe, taxonomy and structural dependencies must be compatible.", "COMPATIBLE", "str", False, "dependency state", "DEPENDENCY_ATTACHMENT_STATUS"),
    AcceptanceField("POST_REFRESH_COMPATIBILITY", ("post_refresh_compatibility_state",), "Relative Valuation dependencies must be compatible after manual refresh and dependency attachment.", "COMPATIBLE", "str", False, "dependency state", "POST_REFRESH_COMPATIBILITY"),
    AcceptanceField("RV_FIRST_OUTCOME", ("rv_first_outcome",), "Manual full-universe Relative Valuation refresh must activate the accepted snapshot.", "ACTIVATED", "str", False, "active pointer", "RV_FIRST_OUTCOME"),
    AcceptanceField("RV_SECOND_OUTCOME", ("rv_second_outcome",), "Manual Relative Valuation replay must be no-change.", "NO_CHANGE", "str", False, "persisted content", "RV_SECOND_OUTCOME"),
    AcceptanceField("RV_SECOND_LOGICAL_ZERO_WRITES", ("rv_second_logical_zero_writes",), "Manual Relative Valuation replay must perform zero logical writes.", True, "bool", False, "persisted content", "RV_SECOND_LOGICAL_ZERO_WRITES"),
    AcceptanceField("RV_SECOND_PHYSICAL_NO_CHANGE", ("rv_second_physical_no_change",), "Manual Relative Valuation replay must preserve physical content fingerprint.", True, "bool", False, "persisted content", "RV_SECOND_PHYSICAL_NO_CHANGE"),
    AcceptanceField("RV_SNAPSHOT_ID", ("rv_snapshot_id",), "Accepted Relative Valuation active snapshot identity from the apply report.", ACCEPTED["rv_snapshot"], "str", False, "active pointer", "RV_SNAPSHOT_ID"),
    AcceptanceField("RV_RESULT_FINGERPRINT", ("rv_result_fingerprint",), "Accepted Relative Valuation result fingerprint from persisted snapshot metadata.", ACCEPTED["rv_result_fingerprint"], "str", False, "persisted content", "RV_RESULT_FINGERPRINT"),
    AcceptanceField("RV_SOURCE_FINGERPRINT", ("rv_source_fingerprint",), "Accepted Relative Valuation source fingerprint from calculated snapshot metadata.", ACCEPTED["rv_source_fingerprint"], "str", False, "source input", "RV_SOURCE_FINGERPRINT"),
    AcceptanceField("AREB_POST_DELISTING_RV_ROWS", ("areb_post_delisting_relative_valuation_rows",), "AREB must have no post-delisting current Relative Valuation participation.", 0, "int", False, "calculated result", "AREB_POST_DELISTING_RV_ROWS"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_git(args: tuple[str, ...], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=ROOT, check=check, capture_output=True, text=True)


def _git_text(args: tuple[str, ...]) -> str:
    return _run_git(args).stdout.strip()


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _sidecar_state(path: Path, suffix: str) -> dict[str, Any]:
    sidecar = Path(str(path) + suffix)
    return {
        "exists": sidecar.exists(),
        "size": sidecar.stat().st_size if sidecar.exists() else None,
        "mtime_ns": sidecar.stat().st_mtime_ns if sidecar.exists() else None,
        "sha256": sha256(sidecar) if sidecar.exists() else None,
    }


def _light_database_inventory(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with _readonly(path) as conn:
        schema = [tuple(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        )]
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256(path),
        "schema_fingerprint": stable_hash(schema),
        "row_counts": {},
        "page_count": page_count,
        "freelist_count": freelist,
        "journal_mode": journal_mode,
        "quick_check": "SKIPPED_READ_ONLY_SOURCE",
        "foreign_key_errors": "SKIPPED_READ_ONLY_SOURCE",
        "wal": _sidecar_state(path, "-wal"),
        "shm": _sidecar_state(path, "-shm"),
        "journal": _sidecar_state(path, "-journal"),
    }


def _targeted_production_inventory() -> dict[str, Any]:
    databases = {
        role: (database_inventory(path) if role in WRITE_ROLES else _light_database_inventory(path))
        for role, path in PRODUCTION.items()
    }
    reports = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(REPORT_ROOT.glob("**/*")) if path.is_file()
    }
    scheduler = {
        "exists": SCHEDULER_CONFIG.exists(),
        "sha256": sha256(SCHEDULER_CONFIG) if SCHEDULER_CONFIG.exists() else None,
        "size": SCHEDULER_CONFIG.stat().st_size if SCHEDULER_CONFIG.exists() else None,
        "mtime_ns": SCHEDULER_CONFIG.stat().st_mtime_ns if SCHEDULER_CONFIG.exists() else None,
    }
    with _readonly(PRODUCTION["analysis"]) as conn:
        from rawcandle.fundamentals.operating_income_v2.activation import assert_v2_active

        active = asdict(assert_v2_active(conn))
        relative = [dict(row) for row in conn.execute(
            "SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint"
        )]
    return {
        "databases": databases,
        "reports": reports,
        "reports_fingerprint": stable_hash(reports),
        "scheduler": scheduler,
        "active_package": active,
        "active_relative_valuation": relative,
    }


def _assert_paths() -> dict[str, str]:
    resolved: dict[str, str] = {}
    for role, path in PRODUCTION.items():
        if not path.is_absolute() or path.is_symlink() or path.resolve() != path or not path.is_file():
            raise RuntimeError(f"PHASE13F4_2_PRODUCTION_PATH_REFUSED:{role}:{path}")
        resolved[role] = str(path)
        if role in WRITE_ROLES:
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = Path(str(path) + suffix)
                if sidecar.exists() and sidecar.stat().st_size:
                    raise RuntimeError(f"PHASE13F4_2_SQLITE_SIDECAR_PRESENT:{role}:{sidecar}:{sidecar.stat().st_size}")
    if len(set(resolved.values())) != len(resolved):
        raise RuntimeError("PHASE13F4_2_DATABASE_ROLE_ALIAS")
    return resolved


def _process_inventory() -> dict[str, Any]:
    rows = subprocess.run(("ps", "-eo", "pid=,args="), check=True, capture_output=True, text=True).stdout.splitlines()
    relevant = [
        row.strip()
        for row in rows
        if any(term in row.lower() for term in ("rawcandle", "fundamental", "sharadar", "stock_update_scheduler"))
        and str(os.getpid()) not in row
    ]
    conflicts = [
        row for row in relevant
        if any(term in row for term in ("run_fundamentals_v4", "run_phase13", "run_phase12", "run_sharadar", "stock_update_scheduler"))
    ]
    return {"relevant_processes": relevant, "conflicting_writers": conflicts}


def _storage_gate(output: Path, backup_dir: Path) -> dict[str, Any]:
    write_bytes = sum(PRODUCTION[role].stat().st_size for role in WRITE_ROLES)
    required = int(write_bytes * 3.0 + 2 * 1024 * 1024 * 1024)
    locations = {ROOT, output.parent, backup_dir.parent, Path("/tmp")}
    checks = []
    for location in locations:
        existing = location
        while not existing.exists():
            existing = existing.parent
        usage = shutil.disk_usage(existing)
        checks.append({
            "path": str(existing.resolve()),
            "free_bytes": usage.free,
            "required_bytes": required,
            "ok": usage.free >= required,
        })
    if not all(row["ok"] for row in checks):
        raise RuntimeError("PHASE13F4_2_INSUFFICIENT_FREE_SPACE")
    return {"write_set_bytes": write_bytes, "required_bytes": required, "checks": checks}


def _schema_parity() -> dict[str, Any]:
    return {
        "structural_annotation": "phase10b.calculate -> rehearsal.calculate -> _annotate_structural_rows",
        "score": "phase10b.calculate uses operating_income_v2.score",
        "lifecycle": "phase10b.calculate uses operating_income_v2.rehearsal._lifecycle with structural regime checks",
        "valuation": "phase10b.calculate uses structural-aware canonical valuation source",
        "delta": "phase10b.calculate uses _same_structural_regime for compatible history",
        "diagnostics": "phase10b.apply_candidate_package persists diagnostic_flags_eight",
        "relative_position": "refresh_relative_position production entrypoint",
        "relative_valuation": "phase13f3_ticker_transition._manual_rv_refresh",
        "dependencies": "phase13b_foundation.attach_dependencies",
        "activation": "phase10b.apply_candidate_package and relative_valuation.persistence.apply_snapshot",
        "ok": True,
    }


def _preflight(output: Path, backup_dir: Path, *, require_clean: bool) -> dict[str, Any]:
    paths = _assert_paths()
    git_status = _git_text(("status", "--porcelain"))
    if require_clean and git_status:
        raise RuntimeError("PHASE13F4_2_CLEAN_GIT_WORKTREE_REQUIRED")
    required = {}
    for commit in ("0804609", "34be0c6", "a01fc83", "a825dd9", "7c18d90", "58d5b16", "68ab231", "1c35b1c"):
        required[commit] = _run_git(("cat-file", "-e", f"{commit}^{{commit}}"), check=False).returncode == 0
    if not all(required.values()):
        raise RuntimeError("PHASE13F4_2_REQUIRED_COMMIT_MISSING:" + json.dumps(required, sort_keys=True))
    process = _process_inventory()
    if process["conflicting_writers"]:
        raise RuntimeError("PHASE13F4_2_CONFLICTING_WRITER:" + " | ".join(process["conflicting_writers"]))
    inventory = _targeted_production_inventory()
    bad = {
        role: {"quick_check": row["quick_check"], "foreign_key_errors": row["foreign_key_errors"]}
        for role, row in inventory["databases"].items()
        if role in WRITE_ROLES and (row["quick_check"] != "ok" or row["foreign_key_errors"])
    }
    if bad:
        raise RuntimeError("PHASE13F4_2_INTEGRITY_PRECHECK_FAILED:" + json.dumps(bad, sort_keys=True))
    source = archive_reconciliation()
    accepted_by_dimension = {
        "ARQ": sum(int(row["ARQ_row_count"]) for row in source["reconciliation"]),
        "MRQ": sum(int(row["MRQ_row_count"]) for row in source["reconciliation"]),
    }
    if accepted_by_dimension != {"ARQ": 199, "MRQ": 202}:
        raise RuntimeError(f"PHASE13F4_2_SOURCE_RECONCILIATION_FAILED:{accepted_by_dimension}")
    return {
        "git": {
            "head": _git_text(("rev-parse", "HEAD")),
            "short_head": _git_text(("rev-parse", "--short", "HEAD")),
            "branch": _git_text(("branch", "--show-current")),
            "status_clean": not bool(git_status),
            "required_commits": required,
        },
        "paths": paths,
        "process": process,
        "storage": _storage_gate(output, backup_dir),
        "parity": _schema_parity(),
        "production_inventory": inventory,
        "source_reconciliation": {
            **{key: value for key, value in source.items() if key != "rows_by_ticker"},
            "accepted_by_dimension": accepted_by_dimension,
        },
    }


def _backup_write_set(backup_dir: Path) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for role in WRITE_ROLES:
        source = PRODUCTION[role]
        target = backup_dir / source.name
        copied = online_backup(source, target)
        copied["sha256"] = sha256(target)
        copied["inventory"] = database_inventory(target)
        if copied["inventory"]["quick_check"] != "ok" or copied["inventory"]["foreign_key_errors"]:
            raise RuntimeError(f"PHASE13F4_2_BACKUP_INTEGRITY_FAILED:{role}")
        manifest[role] = copied
    write_json(backup_dir / "backup_manifest.json", manifest)
    return manifest


def _restore_to_path(source: Path, destination: Path) -> None:
    if destination.exists():
        destination.unlink()
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def _restore_rehearsal_inventory(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with _readonly(path) as conn:
        tables = [
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")
        ]
        user_tables = [table for table in tables if not table.startswith("sqlite_")]
        row_counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM \"{table.replace(chr(34), chr(34) * 2)}\"").fetchone()[0])
            for table in user_tables
        }
        schema = [tuple(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        )]
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        foreign = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256(path),
        "schema_fingerprint": stable_hash(schema),
        "row_counts": row_counts,
        "quick_check": quick,
        "foreign_key_errors": foreign,
    }


def _restore_rehearsal(backup_manifest: Mapping[str, Mapping[str, Any]], output: Path) -> dict[str, Any]:
    restore_dir = output / "restore_rehearsal"
    restore_dir.mkdir(parents=True, exist_ok=True)
    rows = {}
    for role in WRITE_ROLES:
        source = Path(str(backup_manifest[role]["destination"]))
        target = restore_dir / f"{role}.restored.db"
        _restore_to_path(source, target)
        inventory = _restore_rehearsal_inventory(target)
        backup_inventory = backup_manifest[role]["inventory"]
        ok = (
            inventory["schema_fingerprint"] == backup_inventory["schema_fingerprint"]
            and inventory["row_counts"] == backup_inventory["row_counts"]
            and inventory["quick_check"] == "ok"
            and inventory["foreign_key_errors"] == 0
        )
        rows[role] = {"path": str(target), "ok": ok, "inventory": inventory}
        if not ok:
            raise RuntimeError(f"PHASE13F4_2_RESTORE_REHEARSAL_FAILED:{role}")
    return {"restore_dir": str(restore_dir), "roles": rows, "ok": True}


def _restore_backups(backup_manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    restored = {}
    for role in WRITE_ROLES:
        source = Path(str(backup_manifest[role]["destination"]))
        _restore_to_path(source, PRODUCTION[role])
        restored[role] = database_inventory(PRODUCTION[role])
        if restored[role]["quick_check"] != "ok" or restored[role]["foreign_key_errors"]:
            raise RuntimeError(f"PHASE13F4_2_RESTORE_INTEGRITY_FAILED:{role}")
    return restored


def _structural_dependency_metadata(structural_contract: Mapping[str, Any], structural_package_fingerprint: str) -> dict[str, Any]:
    return {
        "structural_contract_version": structural_break.CONTRACT_VERSION,
        "structural_package_fingerprint": structural_package_fingerprint,
        "structural_event_fingerprint": structural_contract["economic_event_fingerprint"],
        "structural_regime_fingerprint": structural_contract["regime_fingerprint"],
        "structural_event_count": structural_contract["event_count"],
        "structural_quarter_regime_count": structural_contract["quarter_regime_count"],
        "structural_ttm_regime_count": structural_contract["ttm_regime_count"],
    }


def _apply_pipeline_for_paths(
    paths: CandidatePaths,
    output: Path,
    *,
    source: Mapping[str, Any],
    applied_at: str,
    allow_production: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {"applied_at_utc": applied_at}
    result["transition_identities"] = _apply_transition_identities(paths.canonical_db, allow_production=allow_production)
    result["provider_staging"] = stage_provider_rows(
        paths.provider_db,
        paths.canonical_db,
        source["rows_by_ticker"],
        allow_production=allow_production,
    )
    result["provider_identity_links"] = _apply_provider_identity_links(
        paths.canonical_db,
        provider_db=paths.provider_db,
        allow_production=allow_production,
    )
    result["provider_identity_links_replay"] = _apply_provider_identity_links(
        paths.canonical_db,
        provider_db=paths.provider_db,
        allow_production=allow_production,
    )
    result["transition_identities_replay"] = _apply_transition_identities(paths.canonical_db, allow_production=allow_production)
    result["provider_staging_replay"] = stage_provider_rows(
        paths.provider_db,
        paths.canonical_db,
        source["rows_by_ticker"],
        allow_production=allow_production,
    )
    result["canonical"] = reconcile_canonical(paths.provider_db, paths.canonical_db, applied_at=applied_at)
    result["ttm"] = rebuild_ttm(paths.canonical_db, applied_at=applied_at)
    result["successor_canonical_ttm"] = successor_canonical_ttm_report(paths.canonical_db)
    result["structural_contract"] = structural_break.apply_contract(
        paths.canonical_db,
        events=_events(),
        applied_at_utc=applied_at,
    )
    result["structural_evidence"] = _structural_evidence(paths.canonical_db)
    structural_package_fingerprint = _structural_package_fingerprint(result["structural_contract"])
    result["structural_package_fingerprint"] = structural_package_fingerprint
    result["valuation_classification"] = _valuation_classification_update(
        paths.analysis_db,
        paths.market_db,
        paths.canonical_db,
        allow_production=allow_production,
    )
    result["schema"] = ensure_candidate_schema(paths, applied_at_utc=applied_at, apply=True, allow_production=allow_production)
    universe = backfill_universe(paths, applied_at_utc=applied_at, apply=True, allow_production=allow_production)
    result["universe"] = universe
    result["package"] = instrumented_package_refresh(
        {
            "provider": paths.provider_db,
            "canonical": paths.canonical_db,
            "analysis": paths.analysis_db,
            "market": paths.market_db,
            "taxonomy": paths.taxonomy_db,
        },
        output,
        allow_production=allow_production,
    )
    result["relative_position"] = asdict(refresh_relative_position(
        canonical_db=paths.canonical_db,
        analysis_db=paths.analysis_db,
        market_db=paths.market_db,
        taxonomy_db=paths.taxonomy_db,
        snapshot_date=REPORT_DATE,
        model_fingerprint=RP_MODEL_FINGERPRINT,
        applied_at_utc=applied_at,
    ))
    taxonomy = taxonomy_identity(paths.taxonomy_db)
    result["pre_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    result["relative_valuation"] = _manual_rv_refresh(paths, output=output)
    structural_metadata = _structural_dependency_metadata(result["structural_contract"], structural_package_fingerprint)
    result["dependencies"] = attach_dependencies(
        paths,
        universe=universe["identity"],
        applied_at_utc=applied_at,
        apply=True,
        allow_production=allow_production,
        structural_metadata=structural_metadata,
    )
    result["post_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
        paths.analysis_db,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    result["snapshots"] = _snapshot_smoke(paths, output)
    result["areb"] = _areb_counts(paths.analysis_db)
    return result


def _apply_pipeline(output: Path, *, source: Mapping[str, Any], applied_at: str) -> dict[str, Any]:
    paths = CandidatePaths(
        PRODUCTION["canonical"],
        PRODUCTION["analysis"],
        PRODUCTION["taxonomy"],
        provider_db=PRODUCTION["provider"],
        market_db=PRODUCTION["market"],
    )
    return _apply_pipeline_for_paths(paths, output, source=source, applied_at=applied_at, allow_production=True)


def _copy_acceptance_candidate(output: Path, *, source: Mapping[str, Any], applied_at: str) -> dict[str, Any]:
    candidate_dir = output / "prewrite_candidate"
    copies = candidate_dir / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    paths = CandidatePaths(
        copies / PRODUCTION["canonical"].name,
        copies / PRODUCTION["analysis"].name,
        PRODUCTION["taxonomy"],
        provider_db=copies / PRODUCTION["provider"].name,
        market_db=PRODUCTION["market"],
    )
    result: dict[str, Any] = {
        "started_at_utc": utc_now(),
        "paths": {
            "provider": str(paths.provider_db),
            "canonical": str(paths.canonical_db),
            "analysis": str(paths.analysis_db),
            "market": str(paths.market_db),
            "taxonomy": str(paths.taxonomy_db),
        },
    }
    try:
        result["backups"] = {
            "provider": online_backup(PRODUCTION["provider"], paths.provider_db),
            "canonical": online_backup(PRODUCTION["canonical"], paths.canonical_db),
            "analysis": online_backup(PRODUCTION["analysis"], paths.analysis_db),
        }
        result["before"] = {
            "provider": database_inventory(paths.provider_db),
            "canonical": database_inventory(paths.canonical_db),
            "analysis": database_inventory(paths.analysis_db),
        }
        candidate = _apply_pipeline_for_paths(paths, candidate_dir / "candidate_apply", source=source, applied_at=applied_at, allow_production=False)
        result["candidate"] = candidate
        result["acceptance_view"] = _acceptance_view(candidate)
        result["acceptance_blockers"] = _acceptance_blockers(candidate)
        result["final_inventory"] = {
            "provider": database_inventory(paths.provider_db),
            "canonical": database_inventory(paths.canonical_db),
            "analysis": database_inventory(paths.analysis_db),
        }
        write_json(candidate_dir / "prewrite_candidate_result.json", result)
        return result
    finally:
        if copies.exists():
            shutil.rmtree(copies)
        write_json(candidate_dir / "cleanup.json", {
            "transient_copies_removed": not copies.exists(),
            "remaining_database_artifacts": [
                str(path) for path in candidate_dir.rglob("*")
                if path.suffix in {".db", ".sqlite"} or path.name.endswith(("-wal", "-shm", "-journal"))
            ],
        })


def _required(result: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = result
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(".".join(path))
        current = current[part]
    return current


def _acceptance_view(result: Mapping[str, Any]) -> dict[str, Any]:
    package_first = _required(result, ("package", "first_apply"))
    package_second = _required(result, ("package", "second_apply"))
    package_rows = _required(package_first, ("rows",))
    rv = _required(result, ("relative_valuation",))
    structural_source = _required(rv, ("source_metadata", "structural_break", "fingerprint"))
    diagnostic_endpoint = int(_required(package_rows, ("diagnostic_endpoint",)))
    diagnostic_evaluation = int(_required(package_rows, ("diagnostic_evaluation",)))
    return {
        "provider_staging_replay_logical_changes": int(_required(result, ("provider_staging_replay", "logical_changes"))),
        "structural_contract_version": str(_required(result, ("structural_contract", "contract_version"))),
        "structural_event_count": int(_required(result, ("structural_contract", "event_count"))),
        "structural_quarter_regime_count": int(_required(result, ("structural_contract", "quarter_regime_count"))),
        "structural_ttm_regime_count": int(_required(result, ("structural_contract", "ttm_regime_count"))),
        "structural_source_fingerprint": str(structural_source),
        "structural_event_fingerprint": str(_required(result, ("structural_contract", "economic_event_fingerprint"))),
        "structural_regime_fingerprint": str(_required(result, ("structural_contract", "regime_fingerprint"))),
        "structural_package_fingerprint": str(_required(result, ("structural_package_fingerprint",))),
        "package_first_outcome": str(_required(package_first, ("outcome",))),
        "package_second_outcome": str(_required(package_second, ("outcome",))),
        "package_second_logical_changes": int(_required(package_second, ("logical_changes",))),
        "package_second_physical_no_change": bool(_required(result, ("package", "second_physical_no_change"))),
        "package_economic_fingerprint": str(_required(package_first, ("economic_result_fingerprint",))),
        "package_physical_fingerprint": str(_required(package_first, ("physical_content_fingerprint",))),
        "diagnostic_evaluation_multiplier_ok": diagnostic_endpoint > 0 and diagnostic_evaluation == diagnostic_endpoint * 8,
        "dependency_status": str(_required(result, ("dependencies", "status"))),
        "post_refresh_compatibility_state": str(_required(result, ("post_refresh_compatibility", "state"))),
        "rv_first_outcome": str(_required(rv, ("first_apply", "outcome"))),
        "rv_second_outcome": str(_required(rv, ("second_apply", "outcome"))),
        "rv_second_logical_zero_writes": bool(_required(rv, ("second_logical_zero_writes",))),
        "rv_second_physical_no_change": bool(_required(rv, ("second_physical_no_change",))),
        "rv_snapshot_id": str(_required(rv, ("first_apply", "snapshot_id"))),
        "rv_result_fingerprint": str(_required(rv, ("snapshot", "result_fingerprint"))),
        "rv_source_fingerprint": str(_required(rv, ("snapshot", "source_fingerprint"))),
        "areb_post_delisting_relative_valuation_rows": int(_required(result, ("areb", "post_delisting_relative_valuation_rows"))),
    }


def acceptance_contract_artifact() -> list[dict[str, Any]]:
    return [
        {
            "stable_check_identifier": field.check_id,
            "semantic_field": ".".join(field.path),
            "economic_meaning": field.meaning,
            "expected_value_or_rule": field.expected,
            "authoritative_runtime_object": "canonical acceptance view built from production/copy pipeline result",
            "actual_accessor_or_normalized_field_name": field.path[-1],
            "expected_type": field.expected_type,
            "nullable": field.nullable,
            "identity_kind": field.identity_kind,
            "failure_reason": field.failure_reason,
        }
        for field in ACCEPTANCE_CONTRACT
    ]


def _acceptance_blockers(result: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    try:
        view = _acceptance_view(result)
    except (KeyError, TypeError, ValueError) as exc:
        path = str(exc).strip("'")
        missing_reasons = {
            "relative_valuation.first_apply.snapshot_id": "RV_SNAPSHOT_ID_MISSING",
            "first_apply.snapshot_id": "RV_SNAPSHOT_ID_MISSING",
            "relative_valuation.snapshot.result_fingerprint": "RV_RESULT_FINGERPRINT_MISSING",
            "snapshot.result_fingerprint": "RV_RESULT_FINGERPRINT_MISSING",
            "relative_valuation.snapshot.source_fingerprint": "RV_SOURCE_FINGERPRINT_MISSING",
            "snapshot.source_fingerprint": "RV_SOURCE_FINGERPRINT_MISSING",
            "relative_valuation.source_metadata.structural_break.fingerprint": "STRUCTURAL_SOURCE_FINGERPRINT_MISSING",
            "source_metadata.structural_break.fingerprint": "STRUCTURAL_SOURCE_FINGERPRINT_MISSING",
            "structural_contract.regime_fingerprint": "STRUCTURAL_REGIME_FINGERPRINT_MISSING",
            "structural_contract.economic_event_fingerprint": "STRUCTURAL_EVENT_FINGERPRINT_MISSING",
            "structural_package_fingerprint": "STRUCTURAL_PACKAGE_FINGERPRINT_MISSING",
            "package.first_apply.economic_result_fingerprint": "PACKAGE_ECONOMIC_FINGERPRINT_MISSING",
            "economic_result_fingerprint": "PACKAGE_ECONOMIC_FINGERPRINT_MISSING",
            "package.first_apply.physical_content_fingerprint": "PACKAGE_PHYSICAL_FINGERPRINT_MISSING",
            "physical_content_fingerprint": "PACKAGE_PHYSICAL_FINGERPRINT_MISSING",
            "dependencies.status": "DEPENDENCY_ATTACHMENT_STATUS_MISSING",
            "post_refresh_compatibility.state": "POST_REFRESH_COMPATIBILITY_MISSING",
        }
        return [missing_reasons.get(path, f"ACCEPTANCE_VIEW_INCOMPLETE:{path}")]
    for field in ACCEPTANCE_CONTRACT:
        actual = view.get(field.path[-1])
        if actual != field.expected:
            blockers.append(field.failure_reason)
    return blockers


def _second_no_change(first: Mapping[str, Any], second: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    compare = compare_production_inventory(before, after)
    return {
        "provider_replay_changes": second["provider_staging_replay"]["logical_changes"],
        "package_outcome": second["package"]["first_apply"]["outcome"],
        "package_second_apply_outcome": second["package"]["second_apply"]["outcome"],
        "relative_position_outcome": second["relative_position"]["apply"]["outcome"],
        "relative_valuation_outcome": second["relative_valuation"]["first_apply"]["outcome"],
        "relative_valuation_second_outcome": second["relative_valuation"]["second_apply"]["outcome"],
        "inventory_exact_no_change": before == after,
        "inventory_normalized_no_change": compare["identical"],
        "inventory_compare": compare,
    }


def run_phase13f4_2(
    output: Path | None = None,
    *,
    apply: bool = False,
    phase: str = PHASE,
    artifact_root: Path = ARTIFACT_ROOT,
    backup_root: Path = BACKUP_ROOT,
    default_run_id: str = DEFAULT_RUN_ID,
    result_filename: str = "phase13f4_2_result.json",
    outcome_a: str = OUTCOME_A,
    outcome_b: str = OUTCOME_B,
    outcome_c: str = OUTCOME_C,
    outcome_d: str = OUTCOME_D,
) -> dict[str, Any]:
    started = time.monotonic()
    output = (output or artifact_root / default_run_id).resolve()
    backup_dir = backup_root / output.name
    output.mkdir(parents=True, exist_ok=True)
    journal = PhaseStageJournal(output, backup_dir, phase)
    journal.start_heartbeat()
    final_exit_code = 1
    try:
        journal.checkpoint("PREFLIGHT_STARTED", writes_may_have_occurred=False)
        preflight = _preflight(output, backup_dir, require_clean=apply)
        journal.checkpoint("PREFLIGHT_ACCEPTED", writes_may_have_occurred=False, details={
            "active_package": preflight.get("production_inventory", {}).get("active_package", {}).get("persistence_fingerprint"),
            "active_relative_valuation_count": len(preflight.get("production_inventory", {}).get("active_relative_valuation", [])),
        })
    except BaseException as exc:
        journal.checkpoint("FAILED_PREWRITE", writes_may_have_occurred=False, details={"error_type": type(exc).__name__})
        final_exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 2
        result = {"phase": phase, "outcome": outcome_b, "artifact_dir": str(output), "error": type(exc).__name__, "reason": str(exc), "traceback": traceback.format_exc()}
        write_json(output / result_filename, result)
        journal.write_exit_code(final_exit_code)
        journal.stop_heartbeat()
        return result
    try:
        source = archive_reconciliation()
    except BaseException as exc:
        journal.checkpoint("FAILED_PREWRITE", writes_may_have_occurred=False, details={"error_type": type(exc).__name__})
        final_exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 2
        result = {"phase": phase, "outcome": outcome_b, "artifact_dir": str(output), "error": type(exc).__name__, "reason": str(exc), "traceback": traceback.format_exc()}
        write_json(output / result_filename, result)
        journal.write_exit_code(final_exit_code)
        journal.stop_heartbeat()
        return result
    write_json(output / "production_preflight.json", preflight)
    write_json(output / "acceptance_contract.json", acceptance_contract_artifact())
    if not apply:
        journal.checkpoint("SUCCESS", writes_may_have_occurred=False, details={"mode": "DRY_RUN"})
        result = {
            "phase": phase,
            "outcome": outcome_b,
            "mode": "DRY_RUN",
            "artifact_dir": str(output),
            "preflight": preflight,
            "write_set": list(WRITE_ROLES),
            "read_only_roles": list(READ_ONLY_ROLES),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / result_filename, result)
        journal.write_exit_code(0)
        journal.stop_heartbeat()
        return result

    backup_manifest: dict[str, Any] | None = None
    lock_handle = None
    write_boundary_armed = False
    try:
        prewrite_candidate = _copy_acceptance_candidate(output, source=source, applied_at=APPLIED_AT)
        if prewrite_candidate["acceptance_blockers"]:
            journal.checkpoint("FAILED_PREWRITE", writes_may_have_occurred=False, details={
                "acceptance_blockers": prewrite_candidate["acceptance_blockers"],
            })
            final_exit_code = 2
            result = {
                "phase": phase,
                "outcome": outcome_b,
                "artifact_dir": str(output),
                "preflight": preflight,
                "prewrite_candidate": prewrite_candidate,
                "acceptance_contract": acceptance_contract_artifact(),
                "reason": "PREWRITE_ACCEPTANCE_BLOCKERS:" + ",".join(prewrite_candidate["acceptance_blockers"]),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
            write_json(output / result_filename, result)
            journal.write_exit_code(final_exit_code)
            return result
        lock_handle = LOCK_PATH.open("w")
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal.checkpoint("BACKUP_STARTED", writes_may_have_occurred=False)
        backup_manifest = _backup_write_set(backup_dir)
        journal.checkpoint("BACKUP_COMPLETE", writes_may_have_occurred=False, details={
            role: backup_manifest[role].get("sha256") for role in WRITE_ROLES
        })
        journal.checkpoint("RESTORE_REHEARSAL_STARTED", writes_may_have_occurred=False)
        restore_rehearsal = _restore_rehearsal(backup_manifest, output)
        journal.checkpoint("RESTORE_REHEARSAL_COMPLETE", writes_may_have_occurred=False, details={
            role: restore_rehearsal["roles"][role]["ok"] for role in WRITE_ROLES
        })
        journal.checkpoint("WRITE_BOUNDARY_ARMED", writes_may_have_occurred=False)
        before_apply = _targeted_production_inventory()
        applied_at = utc_now()
        write_boundary_armed = True
        journal.checkpoint("FIRST_APPLY_STARTED", writes_may_have_occurred=True, details={"applied_at_utc": applied_at})
        first = _apply_pipeline(output / "first_apply", source=source, applied_at=applied_at)
        journal.checkpoint("FIRST_APPLY_COMPLETE", writes_may_have_occurred=True, details={
            "package_outcome": first.get("package", {}).get("first_apply", {}).get("outcome"),
            "rv_outcome": first.get("relative_valuation", {}).get("first_apply", {}).get("outcome"),
        })
        blockers = _acceptance_blockers(first)
        if blockers:
            raise RuntimeError("PHASE13F4_2_ACCEPTANCE_BLOCKERS:" + ",".join(blockers))
        second_before = _targeted_production_inventory()
        journal.checkpoint("SECOND_APPLY_STARTED", writes_may_have_occurred=True)
        second = _apply_pipeline(output / "second_apply", source=source, applied_at=applied_at)
        journal.checkpoint("SECOND_APPLY_COMPLETE", writes_may_have_occurred=True, details={
            "package_outcome": second.get("package", {}).get("first_apply", {}).get("outcome"),
            "rv_outcome": second.get("relative_valuation", {}).get("first_apply", {}).get("outcome"),
        })
        journal.checkpoint("POSTFLIGHT_STARTED", writes_may_have_occurred=True)
        second_after = _targeted_production_inventory()
        no_change = _second_no_change(first, second, second_before, second_after)
        if not (
            no_change["provider_replay_changes"] == 0
            and no_change["package_outcome"] == "NO_CHANGE"
            and no_change["relative_valuation_outcome"] == "NO_CHANGE"
            and no_change["inventory_normalized_no_change"]
        ):
            raise RuntimeError("PHASE13F4_2_SECOND_RUN_NOT_NO_CHANGE:" + json.dumps(no_change, sort_keys=True, default=str))
        postflight = _targeted_production_inventory()
        final_integrity = {
            role: (database_inventory(path) if role in WRITE_ROLES else _light_database_inventory(path))
            for role, path in PRODUCTION.items()
        }
        journal.checkpoint("POSTFLIGHT_COMPLETE", writes_may_have_occurred=True, details={
            "active_package": postflight.get("active_package", {}).get("persistence_fingerprint"),
            "active_relative_valuation_count": len(postflight.get("active_relative_valuation", [])),
        })
        result = {
            "phase": phase,
            "outcome": outcome_a,
            "artifact_dir": str(output),
            "backup_dir": str(backup_dir),
            "activation_timestamp": applied_at,
            "preflight": preflight,
            "prewrite_candidate": prewrite_candidate,
            "acceptance_contract": acceptance_contract_artifact(),
            "backup_manifest": backup_manifest,
            "restore_rehearsal": restore_rehearsal,
            "first_apply": first,
            "acceptance_blockers": blockers,
            "second_apply": second,
            "second_no_change": no_change,
            "production_compare": compare_production_inventory(before_apply, postflight),
            "production_postflight": postflight,
            "final_integrity": final_integrity,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / result_filename, result)
        journal.checkpoint("SUCCESS", writes_may_have_occurred=True, details={
            "active_package": postflight.get("active_package", {}).get("persistence_fingerprint"),
            "result_file": result_filename,
        })
        final_exit_code = 0
        journal.write_exit_code(final_exit_code)
        return result
    except BaseException as exc:
        restored = None
        restore_error = None
        if backup_manifest is not None and write_boundary_armed:
            try:
                journal.checkpoint("ROLLBACK_STARTED", writes_may_have_occurred=True, details={"error_type": type(exc).__name__})
                restored = _restore_backups(backup_manifest)
                journal.checkpoint("ROLLBACK_COMPLETE", writes_may_have_occurred=True, details={
                    role: restored[role].get("sha256") for role in WRITE_ROLES
                })
            except BaseException as restore_exc:  # pragma: no cover - production recovery path
                restore_error = {"type": type(restore_exc).__name__, "message": str(restore_exc), "traceback": traceback.format_exc()}
        failure_stage = "FAILED_POSTWRITE" if write_boundary_armed else "FAILED_PREWRITE"
        journal.checkpoint(failure_stage, writes_may_have_occurred=write_boundary_armed, details={
            "error_type": type(exc).__name__,
            "restored": restored is not None,
            "restore_error": restore_error is not None,
        })
        outcome = (
            outcome_c if restored is not None and restore_error is None
            else (outcome_b if not write_boundary_armed else outcome_d)
        )
        final_exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 2
        result = {
            "phase": phase,
            "outcome": outcome,
            "artifact_dir": str(output),
            "backup_dir": str(backup_dir) if backup_manifest else None,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
            "backup_manifest": backup_manifest,
            "restored": restored,
            "restore_error": restore_error,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        write_json(output / result_filename, result)
        journal.write_exit_code(final_exit_code)
        return result
    finally:
        if lock_handle is not None:
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_UN)
            finally:
                lock_handle.close()
        journal.stop_heartbeat()
        if not journal.exit_code_path.exists():
            journal.write_exit_code(final_exit_code)
