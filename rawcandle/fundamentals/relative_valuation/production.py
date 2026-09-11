from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.operating_income_v2.activation import assert_v2_active, known_packages
from rawcandle.fundamentals.operating_income_v2.phase10c import LOCKED_PACKAGE

from .engine import MODEL_FINGERPRINT, MODEL_VERSION, calculate_relative_valuation
from .persistence import (
    LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION,
    RelativeValuationRepository,
    SCHEMA_OBJECTS,
    apply_snapshot,
    deactivate_snapshot,
    ensure_schema,
    quick_check,
    set_active_snapshot,
    snapshot_identity,
    validate_snapshot,
)
from .source import ReadOnlySourcePaths, load_relative_valuation_source


ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS = {
    "canonical": ROOT / "data/fundamentals_v4.db",
    "provider": ROOT / "data/fundamentals_provider.db",
    "analysis": ROOT / "data/fundamentals_analysis.db",
    "market": ROOT / "data/osakedata.db",
    "taxonomy": ROOT / "data/analysis.db",
}
DATABASE_TYPES = {
    "canonical": "v4_ttm_values",
    "provider": "provider_observation",
    "analysis": "score_result",
    "market": "osakedata",
    "taxonomy": "ec_entity",
}
BACKUP_DIR = ROOT / "backups"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_relative_valuation_phase11d"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"


@dataclass(frozen=True)
class ProductionPlan:
    source_fingerprint: str
    result_fingerprint: str
    physical_content_fingerprint: str
    snapshot_id: str
    company_count: int
    current_fresh_count: int
    current_peer_eligible_count: int
    own_history_ready_fresh_count: int
    own_history_limited_fresh_count: int


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _has_symlink_component(path: Path) -> bool:
    current = path.absolute()
    while current != current.parent:
        if current.exists() and current.is_symlink():
            return True
        current = current.parent
    return current.is_symlink()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _schema_hash(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
    )
    return hashlib.sha256(
        json.dumps(
            [tuple(row) for row in rows], separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()


def database_evidence(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    with sqlite3.connect(f"file:{resolved}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        objects = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        relative_counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in sorted(objects)
            if table.startswith("relative_valuation_")
        }
        active = assert_v2_active(connection)
        evidence = {
            "path": str(path),
            "resolved_path": str(resolved),
            "is_symlink": path.is_symlink(),
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "sha256": _sha256(path),
            "schema_hash": _schema_hash(connection),
            "page_count": int(connection.execute("PRAGMA page_count").fetchone()[0]),
            "freelist_count": int(connection.execute("PRAGMA freelist_count").fetchone()[0]),
            "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
            "quick_check": str(connection.execute("PRAGMA quick_check").fetchone()[0]),
            "foreign_key_violations": len(list(connection.execute("PRAGMA foreign_key_check"))),
            "relative_valuation_counts": relative_counts,
            "active_package": active.persistence_fingerprint,
        }
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        evidence[suffix[1:]] = {
            "exists": sidecar.exists(),
            "size": sidecar.stat().st_size if sidecar.exists() else 0,
            "sha256": _sha256(sidecar) if sidecar.exists() else None,
        }
    return evidence


def validate_production_request(args: Any) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for name, expected in PRODUCTION_PATHS.items():
        supplied = getattr(args, f"{name}_db")
        if (
            not supplied.is_absolute()
            or _has_symlink_component(supplied)
            or supplied.resolve() != expected.resolve()
            or not supplied.is_file()
        ):
            raise PermissionError(f"PHASE11D_EXACT_PRODUCTION_{name.upper()}_PATH_REQUIRED")
        with sqlite3.connect(f"file:{supplied.resolve()}?mode=ro", uri=True) as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
                (DATABASE_TYPES[name],),
            ).fetchone():
                raise ValueError(f"PHASE11D_WRONG_{name.upper()}_DATABASE_TYPE")
        resolved[name] = str(supplied.resolve())
    if len(set(resolved.values())) != len(resolved):
        raise PermissionError("PHASE11D_DATABASE_ROLES_MUST_BE_DISTINCT")
    if args.model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("PHASE11D_MODEL_FINGERPRINT_MISMATCH")
    if args.persistence_version != PERSISTENCE_VERSION:
        raise ValueError("PHASE11D_PERSISTENCE_VERSION_MISMATCH")
    if args.layout_fingerprint != LAYOUT_FINGERPRINT:
        raise ValueError("PHASE11D_LAYOUT_FINGERPRINT_MISMATCH")
    if args.expected_active_package not in known_packages():
        raise ValueError("PHASE11D_ACTIVE_PACKAGE_MISMATCH")
    if not args.full_universe:
        raise ValueError("PHASE11D_FULL_UNIVERSE_REQUIRED")
    if args.confirm_production and not args.apply:
        raise ValueError("PHASE11D_CONFIRM_PRODUCTION_REQUIRES_APPLY")
    if args.apply and not args.confirm_production:
        raise PermissionError("PHASE11D_PRODUCTION_CONFIRMATION_REQUIRED")
    output = args.output.resolve()
    if _has_symlink_component(args.output) or ARTIFACT_ROOT.resolve() not in output.parents:
        raise PermissionError("PHASE11D_OUTPUT_PATH_REJECTED")
    if args.backup_dir.resolve() != BACKUP_DIR.resolve() or _has_symlink_component(args.backup_dir):
        raise PermissionError("PHASE11D_BACKUP_PATH_REJECTED")
    if args.apply:
        status = subprocess.run(
            ("git", "status", "--porcelain"), cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        if status:
            raise RuntimeError("PHASE11D_CLEAN_GIT_WORKTREE_REQUIRED")
    return resolved


def calculate_plan(args: Any) -> tuple[Any, tuple[Any, ...], ProductionPlan]:
    source = load_relative_valuation_source(
        ReadOnlySourcePaths(
            args.analysis_db, args.canonical_db, args.market_db, args.taxonomy_db
        ),
        as_of_date=args.as_of_date,
    )
    snapshot = calculate_relative_valuation(
        source.inputs,
        as_of_date=args.as_of_date,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    content, physical = validate_snapshot(snapshot, source.inputs)
    plan = ProductionPlan(
        source_fingerprint=snapshot.source_fingerprint,
        result_fingerprint=snapshot.result_fingerprint,
        physical_content_fingerprint=physical,
        snapshot_id=snapshot_identity(snapshot, physical),
        company_count=len(content["companies"]),
        current_fresh_count=sum(row["current_fresh"] for row in content["companies"]),
        current_peer_eligible_count=sum(
            row["scope"] == "UNIVERSE" and row["status"] in {
                "RELATIVE_POSITION_READY", "PEER_GROUP_TOO_SMALL"
            }
            for row in content["peers"]
        ),
        own_history_ready_fresh_count=sum(
            company["current_fresh"] and own["status"] == "READY"
            for company, own in zip(content["companies"], content["own_history"])
        ),
        own_history_limited_fresh_count=sum(
            company["current_fresh"] and own["status"] == "LIMITED_HISTORY"
            for company, own in zip(content["companies"], content["own_history"])
        ),
    )
    return snapshot, source.inputs, plan


def require_expected_plan(args: Any, plan: ProductionPlan) -> None:
    expected = {
        "source_fingerprint": args.expected_source_fingerprint,
        "result_fingerprint": args.expected_result_fingerprint,
        "physical_content_fingerprint": args.expected_physical_fingerprint,
        "snapshot_id": args.expected_snapshot_id,
    }
    actual = {name: getattr(plan, name) for name in expected}
    if actual != expected:
        raise RuntimeError(f"PHASE11D_CALCULATION_IDENTITY_MISMATCH:{actual}")


def disk_gate(backup_dir: Path, output: Path) -> dict[str, Any]:
    analysis_size = PRODUCTION_PATHS["analysis"].stat().st_size
    backup = analysis_size
    permanent = 12 * 1024 * 1024
    transient = 128 * 1024 * 1024
    artifacts = 64 * 1024 * 1024
    required = int((backup + permanent + transient + artifacts) * 1.25)
    checks = []
    for location in {PRODUCTION_PATHS["analysis"].parent, backup_dir, output.parent}:
        free = shutil.disk_usage(location).free
        checks.append({"path": str(location.resolve()), "free_bytes": free, "required_bytes": required, "ok": free >= required})
    if not all(row["ok"] for row in checks):
        raise RuntimeError("PHASE11D_INSUFFICIENT_FREE_SPACE")
    return {"analysis_size": analysis_size, "required_bytes": required, "checks": checks}


def online_backup(
    source: Path, backup_dir: Path, stamp: str, *, expected_active_package: str = LOCKED_PACKAGE
) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"fundamentals_analysis.phase11d.{stamp}.db"
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)
    evidence = database_evidence(target)
    if evidence["quick_check"] != "ok" or evidence["foreign_key_violations"]:
        raise RuntimeError("PHASE11D_BACKUP_INTEGRITY_FAILED")
    if evidence["active_package"] != expected_active_package:
        raise RuntimeError("PHASE11D_BACKUP_ACTIVE_PACKAGE_MISMATCH")
    if evidence["relative_valuation_counts"]:
        raise RuntimeError("PHASE11D_BACKUP_NOT_PRE_MIGRATION")
    return evidence


def process_inventory() -> dict[str, Any]:
    rows = subprocess.run(
        ("ps", "-eo", "pid=,args="), check=True, capture_output=True, text=True
    ).stdout.splitlines()
    relevant = [
        row.strip() for row in rows
        if any(term in row.lower() for term in (
            "rawcandle", "fundamental", "sharadar", "stock_update_scheduler"
        ))
        and str(os.getpid()) not in row
    ]
    conflicts = [
        row for row in relevant
        if any(term in row for term in (
            "run_fundamentals_v4", "run_sharadar", "stock_update_scheduler"
        ))
    ]
    if conflicts:
        raise RuntimeError("PHASE11D_CONFLICTING_PROCESS:" + " | ".join(conflicts))
    return {"relevant_processes": relevant, "conflicting_writers": conflicts}


def run_production(args: Any) -> dict[str, Any]:
    resolved = validate_production_request(args)
    args.output.mkdir(parents=True, exist_ok=False)
    before = database_evidence(args.analysis_db)
    with sqlite3.connect(f"file:{args.analysis_db.resolve()}?mode=ro", uri=True) as conn:
        if assert_v2_active(conn).persistence_fingerprint != args.expected_active_package:
            raise RuntimeError("PHASE11D_ACTIVE_PACKAGE_CHANGED")
    process = process_inventory()
    disk = disk_gate(args.backup_dir, args.output)
    snapshot, inputs, plan = calculate_plan(args)
    require_expected_plan(args, plan)
    preflight = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "git_head": subprocess.run(("git", "rev-parse", "HEAD"), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "resolved_paths": resolved,
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "as_of_date": args.as_of_date,
        "plan": asdict(plan),
        "process": process,
        "disk": disk,
        "database_before": before,
    }
    (args.output / "preflight.json").write_text(
        json.dumps(preflight, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if not args.apply:
        return {"outcome": "DRY_RUN", "output": str(args.output), **preflight}

    lock_handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_handle.close()
        raise RuntimeError("PHASE11D_MAINTENANCE_LOCK_HELD") from exc
    try:
        validate_production_request(args)
        with sqlite3.connect(f"file:{args.analysis_db.resolve()}?mode=ro", uri=True) as conn:
            present = {
                str(row[0]) for row in conn.execute(
                    "SELECT name FROM sqlite_schema WHERE name LIKE 'relative_valuation_%' "
                    "OR name LIKE 'idx_relative_valuation_%'"
                )
            }
            expected_objects = set(SCHEMA_OBJECTS)
            if present and present != expected_objects:
                raise RuntimeError("PHASE11D_PARTIAL_RELATIVE_VALUATION_SCHEMA")
            schema_present = present == expected_objects
            active_package = assert_v2_active(conn).persistence_fingerprint
            previous_snapshot_id = None
            if schema_present:
                previous_snapshot_id = RelativeValuationRepository(
                    conn
                ).active_snapshot_id(model_fingerprint=MODEL_FINGERPRINT)
                if previous_snapshot_id is None:
                    raise RuntimeError("PHASE11D_SCHEMA_WITHOUT_ACTIVE_SNAPSHOT")
        if active_package != args.expected_active_package:
            raise RuntimeError("PHASE11D_ACTIVE_PACKAGE_CHANGED")
        backup = None
        if not schema_present:
            backup = online_backup(
                args.analysis_db,
                args.backup_dir,
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                expected_active_package=args.expected_active_package,
            )
        snapshot_again, inputs_again, plan_again = calculate_plan(args)
        require_expected_plan(args, plan_again)
        if plan_again != plan:
            raise RuntimeError("PHASE11D_SOURCE_CHANGED_AFTER_PREFLIGHT")
        applied_at = utc_now()
        apply_completed = False
        try:
            with sqlite3.connect(args.analysis_db) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                if not schema_present:
                    connection.execute("BEGIN IMMEDIATE")
                    ensure_schema(connection, applied_at_utc=applied_at)
                    connection.commit()
                report = apply_snapshot(
                    connection, snapshot_again, inputs_again,
                    applied_at_utc=applied_at,
                )
                apply_completed = report.outcome == "ACTIVATED"
                check = quick_check(connection)
                if not check["ok"]:
                    raise RuntimeError(
                        f"PHASE11D_DEEP_CHECK_FAILED:{check['errors']}"
                    )
                repository = RelativeValuationRepository(connection)
                metadata = repository.active_metadata(
                    model_fingerprint=MODEL_FINGERPRINT
                )
        except Exception:
            if apply_completed:
                with sqlite3.connect(args.analysis_db) as rollback:
                    rollback.execute("BEGIN IMMEDIATE")
                    if previous_snapshot_id is None:
                        deactivate_snapshot(
                            rollback, model_fingerprint=MODEL_FINGERPRINT
                        )
                    else:
                        set_active_snapshot(
                            rollback,
                            model_fingerprint=MODEL_FINGERPRINT,
                            snapshot_id=previous_snapshot_id,
                            activated_at_utc=utc_now(),
                        )
                    rollback.commit()
            raise
        after = database_evidence(args.analysis_db)
        result = {
            "outcome": report.outcome,
            "output": str(args.output),
            "backup": backup,
            "apply": asdict(report),
            "plan": asdict(plan_again),
            "active_metadata": metadata,
            "deep_check": check,
            "database_before": before,
            "database_after": after,
        }
        (args.output / "deployment_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return result
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()
