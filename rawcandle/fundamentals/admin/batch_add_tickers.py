from __future__ import annotations

import csv
import fcntl
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import traceback
from contextlib import contextmanager
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZipFile

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest,
    AdminFinalResult,
    AdminItemDecision,
    AdminOperationType,
    AdminPreview,
    AdminStatus,
    RunStage,
    build_batch_request,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.progress import (
    BATCH_ADD_TICKERS_STAGES,
    ProgressCallback,
    ProgressStage,
    ProgressTracker,
)
from rawcandle.fundamentals.admin.provider_cik import normalize_cik
from rawcandle.fundamentals.admin.identity_resolution import resolve_ticker_identity
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.admin.structural_context import _events, _structural_evidence, _structural_package_fingerprint
from rawcandle.fundamentals.admin.rv_identity import active_relative_valuation_identity
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import load_active_dc_memberships
from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    ROOT,
    compare_production_inventory,
    database_inventory,
    production_inventory,
    rebuild_ttm,
    reconcile_canonical,
    sha256,
    stable_hash,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import database_fingerprint, online_backup
from rawcandle.fundamentals.phase13b_foundation import (
    reject_production_path,
)
from rawcandle.fundamentals.phase13d_backend import (
    Phase13DPaths,
    build_ticker_preview,
    reject_production_or_alias,
)
from rawcandle.fundamentals.providers.sharadar import FUNDAMENTALS_REQUIRED_FIELDS, SharadarClient, redact_url
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.engine import calculate_relative_valuation
from rawcandle.fundamentals.relative_valuation.persistence import (
    RelativeValuationRepository,
    apply_snapshot as apply_rv_snapshot,
    quick_check as rv_quick_check,
    validate_snapshot as validate_rv_snapshot,
)
from rawcandle.fundamentals.relative_valuation.source import (
    ReadOnlySourcePaths as RVSourcePaths,
    load_relative_valuation_source,
)
from rawcandle.fundamentals.schema.migrations import PROVIDER_SCHEMA_SQL
from rawcandle.fundamentals.schema.production_bootstrap import insert_production_sharadar_observation
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.v2_scaffold import SnapshotPaths

REPORT_DATE = "2026-09-12"


PHASE = "PHASE13G2_BATCH_ADD_TICKERS"
CONTRACT_VERSION = "PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V4_BOUND_IDENTITY_APPROVAL"
OUTCOME_B = "OUTCOME B — BATCH ADD TICKERS COPY-ONLY FOUNDATION READY; AUTHORITATIVE FULL DOWNSTREAM GAP REMAINS"
OUTCOME_A = "OUTCOME A — GENERIC BATCH ADD TICKERS AUTHORITATIVE COPY-ONLY PIPELINE VERIFIED AND READY FOR SEPARATELY AUTHORIZED PRODUCTION DEPLOYMENT"
PRODUCTION_OUTCOME_A = "OUTCOME A — BATCH ADD TICKERS ACTIVE AND STABLE IN PRODUCTION"
PRODUCTION_OUTCOME_B = "OUTCOME B — PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED"
PRODUCTION_OUTCOME_C = "OUTCOME C — PRODUCTION DEPLOYMENT FAILED AND COMPLETE BACKUP SET RESTORED"
AUTHORITATIVE_DOWNSTREAM_LIMITATION = {
    "status": "NOT_AVAILABLE_FOR_GENERIC_BATCH_ADD_TICKERS",
    "reason": (
        "The current authoritative Phase 13F.4 pipeline is transition-specific: "
        "it stages source rows and identity repairs for the fixed Phase 13F ticker-transition set, "
        "not arbitrary new ticker onboarding batches."
    ),
    "required_adapter": (
        "A generic provider-source and identity adapter must stage accepted ticker fundamentals, "
        "provider identities, canonical identities and aliases before invoking the existing "
        "canonical/TTM/package/RP/RV/dependency sequence."
    ),
}
WRITE_ROLES = ("provider", "canonical", "analysis")
READONLY_COPY_ROLES = ("market", "taxonomy")
ROLE_ORDER = ("provider", "canonical", "analysis", "market", "taxonomy")
PRODUCTION_BATCH_TICKERS = ("AG", "ALOY", "ARM", "ASML", "ASX", "BABA", "BHP", "BIDU", "BTDR", "CAMT")
PRODUCTION_BACKUP_ROOT = ROOT / "backups/fundamentals_v4_phase13g2_4_batch_add_tickers"
PRODUCTION_LOCK_PATH = ROOT / "temp/.fundamentals_phase13g2_4_add_tickers.lock"
DEFAULT_ARCHIVE = ROOT / "data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip"
SUPPORTED_GENERIC_CATEGORIES = {
    "Domestic Common Stock",
    "Domestic Common Stock Primary Class",
    "ADR Common Stock",
    "ADR Common Stock Primary Class",
    "Canadian Common Stock",
}
SUPPORTED_EXCHANGES = {"NASDAQ", "NYSE", "NYSEMKT"}
EXPECTED_PREWRITE_ACTIVE_PACKAGE = "f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40"
EXPECTED_PREWRITE_RV_MODEL = "76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e"
EXPECTED_PREWRITE_RV_SNAPSHOT = "1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b"
EXPECTED_PREWRITE_RV_RESULT = "9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3"


@dataclass(frozen=True)
class BatchAddTickerPaths:
    provider_db: Path = PRODUCTION["provider"]
    canonical_db: Path = PRODUCTION["canonical"]
    analysis_db: Path = PRODUCTION["analysis"]
    market_db: Path = PRODUCTION["market"]
    taxonomy_db: Path = PRODUCTION["taxonomy"]

    def as_dict(self) -> dict[str, Path]:
        return {
            "provider": self.provider_db,
            "canonical": self.canonical_db,
            "analysis": self.analysis_db,
            "market": self.market_db,
            "taxonomy": self.taxonomy_db,
        }

    def as_phase13d(self) -> Phase13DPaths:
        return Phase13DPaths(
            provider_db=self.provider_db,
            canonical_db=self.canonical_db,
            analysis_db=self.analysis_db,
            market_db=self.market_db,
            taxonomy_db=self.taxonomy_db,
        )


@dataclass(frozen=True)
class CopyLane:
    lane_dir: Path
    paths: BatchAddTickerPaths
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class GenericBatchItemPlan:
    requested_ticker: str
    ticker: str
    status: str
    reason: str
    source_category: str
    provider_metadata: Mapping[str, Any]
    market: Mapping[str, Any]
    classification: Mapping[str, Any]
    canonical: Mapping[str, Any]
    identity_resolution: Mapping[str, Any]
    provider_row_count: int
    provider_arq_row_count: int
    source_fingerprint: str
    rows: tuple[Mapping[str, Any], ...] = ()

    @property
    def eligible(self) -> bool:
        return self.status == "ELIGIBLE"

    def safe_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        payload = {
            "requested_ticker": self.requested_ticker,
            "ticker": self.ticker,
            "status": self.status,
            "reason": self.reason,
            "source_category": self.source_category,
            "provider_metadata": dict(self.provider_metadata),
            "market": dict(self.market),
            "classification": dict(self.classification),
            "canonical": dict(self.canonical),
            "identity_resolution": dict(self.identity_resolution),
            "provider_row_count": self.provider_row_count,
            "provider_arq_row_count": self.provider_arq_row_count,
            "source_fingerprint": self.source_fingerprint,
        }
        if include_rows:
            payload["rows"] = [dict(row) for row in self.rows]
        return payload


@dataclass(frozen=True)
class GenericBatchPlan:
    contract_version: str
    created_at_utc: str
    network_allowed: bool
    archive_path: str | None
    source_state: Mapping[str, Any]
    items: tuple[GenericBatchItemPlan, ...]
    network: Mapping[str, Any]
    ticker_reporting: tuple[Mapping[str, Any], ...] = ()

    @property
    def accepted_tickers(self) -> tuple[str, ...]:
        return tuple(item.ticker for item in self.items if item.eligible)

    def safe_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        core = {
            "contract_version": self.contract_version,
            "created_at_utc": self.created_at_utc,
            "network_allowed": self.network_allowed,
            "archive_path": self.archive_path,
            "source_state": dict(self.source_state),
            "items": [item.safe_dict(include_rows=include_rows) for item in self.items],
            "network": dict(self.network),
            "ticker_reporting": [dict(item) for item in self.ticker_reporting],
        }
        core["accepted_tickers"] = list(self.accepted_tickers)
        core["plan_fingerprint"] = stable_hash(core)
        return core


def parse_batch_tickers(raw: str | Sequence[str], *, market: str | None = "usa") -> AdminBatchRequest:
    return build_batch_request(AdminOperationType.ADD_TICKERS, raw, market=market, options={"contract_version": CONTRACT_VERSION})


def reject_production_write_targets(paths: BatchAddTickerPaths) -> None:
    reject_production_or_alias(paths.as_phase13d())


def validate_exact_production_paths(paths: BatchAddTickerPaths) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for role, path in paths.as_dict().items():
        raw = str(path)
        if raw.startswith("file:"):
            raise PermissionError(f"PHASE13G2_PRODUCTION_SQLITE_URI_REFUSED:{role}:{raw}")
        expected = PRODUCTION[role]
        if path != expected:
            raise PermissionError(f"PHASE13G2_EXACT_PRODUCTION_PATH_REQUIRED:{role}:{expected}")
        if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.resolve() != expected.resolve():
            raise PermissionError(f"PHASE13G2_PRODUCTION_PATH_ALIAS_REFUSED:{role}:{path}")
        resolved[role] = str(path.resolve())
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("PHASE13G2_PRODUCTION_PATH_ROLES_MUST_BE_DISTINCT")
    return resolved


def _assert_no_sqlite_sidecars(paths: BatchAddTickerPaths, roles: Sequence[str] = WRITE_ROLES) -> dict[str, Any]:
    sidecars: dict[str, list[dict[str, Any]]] = {}
    for role in roles:
        path = paths.as_dict()[role]
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                sidecars.setdefault(role, []).append({"path": str(sidecar), "size": sidecar.stat().st_size})
    if sidecars:
        raise RuntimeError("PHASE13G2_NONEMPTY_SQLITE_SIDECAR:" + json.dumps(sidecars, sort_keys=True))
    return {"checked_roles": list(roles), "nonempty_sidecars": 0}


def _run_git(args: tuple[str, ...]) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _assert_clean_worktree() -> dict[str, Any]:
    """Capture Git provenance without making repository cleanliness a safety gate."""
    try:
        status = _run_git(("status", "--porcelain"))
        changed_paths = tuple(
            line[3:].strip()
            for line in status.splitlines()
            if len(line) > 3 and not line.startswith("??")
        )
        return {
            "head": _run_git(("rev-parse", "HEAD")),
            "short_head": _run_git(("rev-parse", "--short", "HEAD")),
            "branch": _run_git(("branch", "--show-current")),
            "status_clean": not bool(status),
            "dirty": bool(status),
            "changed_tracked_paths": list(changed_paths[:50]),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "head": None,
            "short_head": None,
            "branch": None,
            "status_clean": None,
            "dirty": None,
            "error": type(exc).__name__,
        }


def _process_inventory() -> dict[str, Any]:
    rows = subprocess.run(("ps", "-eo", "pid=,args="), check=True, capture_output=True, text=True).stdout.splitlines()
    own_pid = str(os.getpid())
    relevant = [
        row.strip()
        for row in rows
        if own_pid not in row
        and any(term in row.lower() for term in ("rawcandle", "fundamental", "sharadar", "stock_update_scheduler"))
    ]
    conflicts = [
        row
        for row in relevant
        if any(term in row for term in ("run_fundamentals_v4", "run_phase13", "run_phase12", "run_sharadar", "stock_update_scheduler"))
    ]
    if conflicts:
        raise RuntimeError("PHASE13G2_CONFLICTING_WRITER:" + " | ".join(conflicts))
    return {"relevant_processes": relevant, "conflicting_writers": conflicts}


def _storage_gate(output: Path, backup_dir: Path, paths: BatchAddTickerPaths) -> dict[str, Any]:
    def existing_parent(path: Path) -> Path:
        current = path
        while not current.exists():
            current = current.parent
        return current

    write_bytes = sum(paths.as_dict()[role].stat().st_size for role in WRITE_ROLES)
    required = int((write_bytes * 2.50) + (1024 * 1024 * 1024))
    checks = []
    for location in {ROOT, existing_parent(output.parent), existing_parent(backup_dir.parent), Path("/tmp")}:
        usage = shutil.disk_usage(location)
        checks.append({
            "path": str(location.resolve()),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "required_bytes": required,
            "ok": usage.free >= required,
        })
    if not all(row["ok"] for row in checks):
        raise RuntimeError("PHASE13G2_INSUFFICIENT_FREE_SPACE")
    return {"write_set_bytes": write_bytes, "required_bytes": required, "checks": checks}


def _assert_authorized_production_batch(request: AdminBatchRequest) -> None:
    if tuple(request.normalized_inputs) != PRODUCTION_BATCH_TICKERS:
        raise PermissionError(
            "PHASE13G2_PRODUCTION_BATCH_MUST_MATCH_AUTHORIZED_TICKERS:"
            + " ".join(PRODUCTION_BATCH_TICKERS)
        )
    if request.rejected_inputs:
        raise ValueError("PHASE13G2_PRODUCTION_BATCH_HAS_REJECTED_INPUTS")


def _production_preflight(
    paths: BatchAddTickerPaths,
    *,
    output: Path,
    backup_dir: Path,
    require_clean: bool = True,
    require_expected_active_identities: bool = True,
) -> dict[str, Any]:
    resolved_paths = validate_exact_production_paths(paths)
    sidecars = _assert_no_sqlite_sidecars(paths)
    git = _assert_clean_worktree() if require_clean else {"status_clean": False, "skipped": True}
    process = _process_inventory()
    storage = _storage_gate(output, backup_dir, paths)
    inventory = production_inventory()
    bad_dbs = {
        role: {
            "quick_check": item["quick_check"],
            "foreign_key_errors": item["foreign_key_errors"],
        }
        for role, item in inventory["databases"].items()
        if item["quick_check"] != "ok" or item["foreign_key_errors"]
    }
    if bad_dbs:
        raise RuntimeError("PHASE13G2_PRODUCTION_INTEGRITY_PRECHECK_FAILED:" + json.dumps(bad_dbs, sort_keys=True))
    rv = active_relative_valuation_identity(paths.analysis_db)
    active = {
        "operating_income_package": inventory["active_package"].get("persistence_fingerprint"),
        "relative_valuation_model": rv.get("active_model_fingerprint"),
        "relative_valuation_snapshot": rv.get("active_snapshot_id"),
        "relative_valuation_result": rv.get("active_result_fingerprint"),
    }
    expected = {
        "operating_income_package": EXPECTED_PREWRITE_ACTIVE_PACKAGE,
        "relative_valuation_model": EXPECTED_PREWRITE_RV_MODEL,
        "relative_valuation_snapshot": EXPECTED_PREWRITE_RV_SNAPSHOT,
        "relative_valuation_result": EXPECTED_PREWRITE_RV_RESULT,
    }
    if require_expected_active_identities and active != expected:
        raise RuntimeError("PHASE13G2_PREWRITE_ACTIVE_IDENTITY_MISMATCH:" + json.dumps({"active": active, "expected": expected}, sort_keys=True))
    return {
        "resolved_paths": resolved_paths,
        "write_roles": list(WRITE_ROLES),
        "read_only_roles": list(READONLY_COPY_ROLES),
        "git": git,
        "process": process,
        "storage": storage,
        "sidecars": sidecars,
        "production_inventory": inventory,
        "active_identities": active,
        "expected_prewrite_active_identities": expected,
    }


def _backup_write_set(
    paths: BatchAddTickerPaths,
    backup_dir: Path,
    *,
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {"created_at_utc": utc_now(), "roles": {}}
    for role in WRITE_ROLES:
        source = paths.as_dict()[role]
        destination = backup_dir / f"{role}.{source.name}"
        with _background_heartbeat(progress, f"Backing up {role} production database."):
            copied = online_backup(source, destination)
        inventory = database_inventory(destination)
        copied = dict(copied)
        copied["sha256"] = sha256(destination)
        copied["inventory"] = inventory
        if inventory["quick_check"] != "ok" or inventory["foreign_key_errors"]:
            raise RuntimeError(f"PHASE13G2_BACKUP_INTEGRITY_FAILED:{role}")
        manifest["roles"][role] = copied
    write_json(backup_dir / "backup_manifest.json", manifest)
    return manifest


def _restore_rehearsal(
    backup_manifest: Mapping[str, Any],
    rehearsal_dir: Path,
    *,
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    rehearsal_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"started_at_utc": utc_now(), "roles": {}, "cleanup": {}}
    try:
        for role in WRITE_ROLES:
            backup = Path(str(backup_manifest["roles"][role]["destination"]))
            destination = rehearsal_dir / f"{role}.restore_rehearsal.db"
            with _background_heartbeat(progress, f"Rehearsing restore for {role} database."):
                shutil.copy2(backup, destination)
            restored_sha = sha256(destination)
            expected_sha = str(backup_manifest["roles"][role]["sha256"])
            inventory = database_inventory(destination)
            if restored_sha != expected_sha:
                raise RuntimeError(f"PHASE13G2_RESTORE_REHEARSAL_SHA_MISMATCH:{role}")
            if inventory["quick_check"] != "ok" or inventory["foreign_key_errors"]:
                raise RuntimeError(f"PHASE13G2_RESTORE_REHEARSAL_INTEGRITY_FAILED:{role}")
            result["roles"][role] = {
                "backup": str(backup),
                "rehearsal_path": str(destination),
                "sha256": restored_sha,
                "inventory": inventory,
            }
        return result
    finally:
        removed: list[str] = []
        for path in sorted(rehearsal_dir.glob("*.db*")):
            if path.is_file():
                removed.append(str(path))
                path.unlink(missing_ok=True)
        result["cleanup"] = {"removed_files": removed, "removed_count": len(removed)}
        write_json(rehearsal_dir / "restore_rehearsal_result.json", result)


def _restore_production_from_backups(
    paths: BatchAddTickerPaths,
    backup_manifest: Mapping[str, Any],
    *,
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    restored: dict[str, Any] = {"status": "ROLLED_BACK", "roles": {}}
    for role in WRITE_ROLES:
        source = Path(str(backup_manifest["roles"][role]["destination"]))
        destination = paths.as_dict()[role]
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(destination) + suffix).unlink(missing_ok=True)
        with _background_heartbeat(progress, f"Restoring {role} production database from backup."):
            shutil.copy2(source, destination)
        restored_sha = sha256(destination)
        expected_sha = str(backup_manifest["roles"][role]["sha256"])
        inventory = database_inventory(destination)
        if restored_sha != expected_sha:
            raise RuntimeError(f"PHASE13G2_PRODUCTION_RESTORE_SHA_MISMATCH:{role}")
        if inventory["quick_check"] != "ok" or inventory["foreign_key_errors"]:
            raise RuntimeError(f"PHASE13G2_PRODUCTION_RESTORE_INTEGRITY_FAILED:{role}")
        restored["roles"][role] = {"sha256": restored_sha, "inventory": inventory}
    restored["active_relative_valuation"] = active_relative_valuation_identity(paths.analysis_db)
    return restored


@contextmanager
def _background_heartbeat(progress: ProgressTracker | None, message: str, *, interval_seconds: float = 30.0):
    if progress is None:
        yield
        return
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(interval_seconds):
            progress.heartbeat(message)

    thread = threading.Thread(target=beat, name="phase13g2-progress-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=interval_seconds)


def source_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    rv_identity = active_relative_valuation_identity(paths.analysis_db)
    rv_identity_for_fingerprint = {key: value for key, value in rv_identity.items() if key != "database_path"}
    with _readonly(paths.taxonomy_db) as taxonomy_conn:
        has_taxonomy_schema = all(_table_exists(taxonomy_conn, table) for table in ("ec_ecosystem", "ec_taxonomy_version", "ec_entity", "ec_membership"))
    active_taxonomy = load_active_dc_memberships(paths.taxonomy_db, paths.canonical_db)[1] if has_taxonomy_schema else None
    return {
        "contract_version": CONTRACT_VERSION,
        "databases": {role: database_fingerprint(path) for role, path in paths.as_dict().items()},
        "active_relative_valuation": rv_identity_for_fingerprint,
        "active_taxonomy": active_taxonomy,
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _canonical_identity(paths: BatchAddTickerPaths, ticker: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    cik = metadata.get("cik")
    permaticker = metadata.get("permaticker")
    with _readonly(paths.canonical_db) as conn:
        direct = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active "
            "FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)=UPPER(?) ORDER BY s.active DESC,s.security_id",
            (ticker,),
        )] if _table_exists(conn, "security") else []
        aliases = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active,a.ticker alias_ticker "
            "FROM ticker_alias a JOIN security s USING(security_id) JOIN company c USING(company_id) "
            "WHERE UPPER(a.ticker)=UPPER(?) ORDER BY s.active DESC,s.security_id",
            (ticker,),
        )] if _table_exists(conn, "ticker_alias") else []
        cik_rows = [
            dict(row) for row in conn.execute(
                "SELECT company_id,cik_normalized FROM company_cik"
            )
            if normalize_cik(row["cik_normalized"]) == cik
        ] if cik and _table_exists(conn, "company_cik") else []
        perm_rows = [dict(row) for row in conn.execute(
            "SELECT security_id,provider_security_id FROM provider_security_identity WHERE provider='SHARADAR' AND provider_security_id=?",
            (str(permaticker),),
        )] if permaticker and _table_exists(conn, "provider_security_identity") else []
    rows = direct + aliases
    company_ids = {int(row["company_id"]) for row in rows}
    return {
        "exists": bool(rows),
        "rows": rows,
        "ambiguous": len(company_ids) > 1 or len({int(row["company_id"]) for row in cik_rows}) > 1 or len({int(row["security_id"]) for row in perm_rows}) > 1,
        "company_id": rows[0]["company_id"] if len(company_ids) == 1 else None,
        "security_id": rows[0]["security_id"] if len(company_ids) == 1 and rows else None,
        "cik_conflicts": cik_rows,
        "permaticker_conflicts": perm_rows,
        "cik_identity_conflict": bool(cik_rows) and not bool(rows),
        "permaticker_identity_conflict": bool(perm_rows) and not bool(rows),
    }


def _market_evidence(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.market_db) as conn:
        if not _table_exists(conn, "osakedata"):
            return {"status": "MISSING", "markets": [], "row_count": 0}
        rows = [dict(row) for row in conn.execute(
            "SELECT LOWER(COALESCE(market,'usa')) market,COUNT(*) row_count,MIN(pvm) first_date,MAX(pvm) latest_date "
            "FROM osakedata WHERE UPPER(osake)=UPPER(?) GROUP BY LOWER(COALESCE(market,'usa')) ORDER BY market",
            (ticker,),
        )]
    if not rows:
        return {"status": "MISSING", "markets": [], "row_count": 0}
    return {
        "status": "FOUND" if len(rows) == 1 else "AMBIGUOUS",
        "markets": [row["market"] for row in rows],
        "row_count": sum(int(row["row_count"]) for row in rows),
        "first_date": min(str(row["first_date"]) for row in rows),
        "latest_date": max(str(row["latest_date"]) for row in rows),
    }


def _classification(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    with _readonly(paths.market_db) as conn:
        if not _table_exists(conn, "ticker_meta"):
            return {"status": "MISSING", "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION"}
        rows = [dict(row) for row in conn.execute(
            "SELECT ticker,LOWER(COALESCE(market,'usa')) market,sector,industry FROM ticker_meta WHERE UPPER(ticker)=UPPER(?) ORDER BY market",
            (ticker,),
        )]
    if not rows:
        return {"status": "MISSING", "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION"}
    row = next((item for item in rows if item.get("market") == "usa"), rows[0])
    ready = bool(row.get("sector") and row.get("industry"))
    return {
        "status": "READY" if ready else "MISSING",
        "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION",
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "market": row.get("market"),
    }


def _local_provider_rows(paths: BatchAddTickerPaths, ticker: str) -> tuple[dict[str, Any], ...]:
    with _readonly(paths.provider_db) as conn:
        if not _table_exists(conn, "sharadar_fundamental_observation"):
            return ()
        return tuple(dict(row) for row in conn.execute(
            "SELECT * FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?) ORDER BY ticker,dimension,reportperiod,fiscalperiod,date",
            (ticker,),
        ))


def _archive_rows(archive: Path, tickers: set[str]) -> dict[str, tuple[dict[str, Any], ...]]:
    if not archive.exists():
        return {ticker: () for ticker in tickers}
    rows: dict[str, list[dict[str, Any]]] = {ticker: [] for ticker in tickers}
    with ZipFile(archive) as zf:
        name = next((item for item in zf.namelist() if item.lower().endswith(".csv")), None)
        if name is None:
            return {ticker: () for ticker in tickers}
        with zf.open(name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            for row in csv.DictReader(text):
                ticker = str(row.get("ticker") or "").upper()
                if ticker in rows:
                    rows[ticker].append(dict(row))
    return {ticker: tuple(items) for ticker, items in rows.items()}


def _network_rows(tickers: Sequence[str], *, network_allowed: bool, client: SharadarClient | None = None) -> tuple[dict[str, tuple[dict[str, Any], ...]], dict[str, Any]]:
    if not network_allowed:
        return {ticker: () for ticker in tickers}, {"status": "DISABLED", "request_count": 0}
    client = client or SharadarClient()
    output: dict[str, tuple[dict[str, Any], ...]] = {}
    calls: list[dict[str, Any]] = []
    for ticker in tickers:
        result = client.fundamentals(ticker=ticker, fields=FUNDAMENTALS_REQUIRED_FIELDS, limit=10000)
        calls.append({
            "ticker": ticker,
            "status": result.status,
            "auth_status": result.auth_status,
            "http_status": result.http_status,
            "endpoint": result.endpoint,
            "url": redact_url(result.url),
            "rows": len(result.records),
        })
        output[ticker] = tuple(dict(row) for row in result.records) if result.ok else ()
    return output, {"status": "ALLOWED", "request_count": client.request_count, "calls": calls}


def fiscal_sequence_contradictions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Find ARQ/MRQ disagreement for the same reportperiod without banning valid duplicate winners."""
    by_period: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        dimension = str(row.get("dimension") or "").upper()
        reportperiod = str(row.get("reportperiod") or "")
        fiscalperiod = str(row.get("fiscalperiod") or "").upper()
        if dimension not in {"ARQ", "MRQ"} or not reportperiod or not re.fullmatch(r"[0-9]{4}-Q[1-4]", fiscalperiod):
            continue
        by_period.setdefault(reportperiod, {}).setdefault(dimension, set()).add(fiscalperiod)
    contradictions = []
    for reportperiod, dimensions in sorted(by_period.items()):
        if "ARQ" in dimensions and "MRQ" in dimensions and dimensions["ARQ"] != dimensions["MRQ"]:
            contradictions.append({
                "reportperiod": reportperiod,
                "arq_fiscalperiods": sorted(dimensions["ARQ"]),
                "mrq_fiscalperiods": sorted(dimensions["MRQ"]),
            })
    return contradictions


def build_generic_batch_plan(
    paths: BatchAddTickerPaths,
    request: AdminBatchRequest,
    *,
    now: str | None = None,
    network_allowed: bool = False,
    archive_path: Path | None = None,
    network_client: SharadarClient | None = None,
    include_rows: bool = True,
) -> GenericBatchPlan:
    created = now or utc_now()
    tickers = tuple(request.normalized_inputs)
    effective_archive = DEFAULT_ARCHIVE if archive_path is None else archive_path
    archive_rows = _archive_rows(effective_archive, set(tickers)) if effective_archive else {ticker: () for ticker in tickers}
    network_needed: list[str] = []
    local_rows_by_ticker: dict[str, tuple[dict[str, Any], ...]] = {}
    for ticker in tickers:
        local_rows = _local_provider_rows(paths, ticker)
        local_rows_by_ticker[ticker] = local_rows
        if not local_rows and not archive_rows.get(ticker):
            network_needed.append(ticker)
    fetched_rows, network = _network_rows(network_needed, network_allowed=network_allowed, client=network_client)
    items: list[GenericBatchItemPlan] = []
    for ticker in tickers:
        identity_resolution = resolve_ticker_identity(paths, ticker).as_dict()
        metadata_state = dict(identity_resolution["provider_metadata"])
        reviewed = identity_resolution.get("reviewed_resolution") or {}
        if metadata_state.get("status") == "MISSING" and identity_resolution.get("authority_class") == "APPROVED_REVIEW":
            metadata_state["identity"] = {
                "ticker": ticker,
                "name": reviewed.get("company_name") or ticker,
                "exchange": reviewed.get("exchange"),
                "cik": normalize_cik(reviewed.get("cik")),
                "permaticker": reviewed.get("provider_permaticker"),
                "firstpricedate": reviewed.get("effective_date"),
                "category": reviewed.get("security_category"),
            }
        metadata = dict(metadata_state.get("identity") or {})
        canonical = _canonical_identity(paths, ticker, metadata)
        market = _market_evidence(paths, ticker)
        classification = _classification(paths, ticker)
        if local_rows_by_ticker[ticker]:
            rows = local_rows_by_ticker[ticker]
            source_category = "local_provider"
        elif archive_rows.get(ticker):
            rows = archive_rows[ticker]
            source_category = "verified_archive"
        else:
            rows = fetched_rows.get(ticker, ())
            source_category = "network" if rows else ("network_unavailable" if network_allowed else "network_required")
        blockers: list[str] = []
        if identity_resolution["resolution_class"] == "IDENTITY_REVIEW_REQUIRED":
            blockers.extend(identity_resolution["reason_codes"])
        if str(metadata.get("isdelisted") or "").upper() == "Y":
            blockers.append("DELISTED_SECURITY")
        if metadata.get("category") and metadata.get("category") not in SUPPORTED_GENERIC_CATEGORIES:
            blockers.append("UNSUPPORTED_SECURITY_TYPE")
        if identity_resolution["exchange_status"] == "EXCHANGE_UNKNOWN":
            blockers.append("EXCHANGE_UNKNOWN")
        elif identity_resolution["exchange_status"] == "EXCHANGE_CONFIRMED_UNSUPPORTED":
            blockers.append("INCOMPATIBLE_EXCHANGE")
        if market["status"] != "FOUND" or market.get("markets") != ["usa"]:
            blockers.append("MARKET_NOT_UNAMBIGUOUS_USA")
        if classification["status"] != "READY":
            blockers.append("MISSING_CLASSIFICATION")
        arq_rows = [row for row in rows if str(row.get("dimension") or "").upper() == "ARQ"]
        if not arq_rows:
            blockers.append("NO_USABLE_QUARTERLY_HISTORY")
        fiscal_contradictions = fiscal_sequence_contradictions(rows)
        if fiscal_contradictions:
            blockers.append("CONTRADICTORY_FISCAL_SEQUENCE")
        if identity_resolution["resolution_class"] == "EXISTING_SECURITY":
            status = "ALREADY_PRESENT"
            reason = "Ticker is already present in canonical identities."
        elif not identity_resolution["automatic_mutation_permitted"] and not blockers:
            status = "REVIEW_REQUIRED"
            reason = "IDENTITY_MUTATION_NOT_AUTHORIZED"
        elif blockers:
            status = "REVIEW_REQUIRED" if any("REVIEW" in blocker or "AMBIGUOUS" in blocker or blocker in {"PROVIDER_METADATA_MISSING", "NO_USABLE_QUARTERLY_HISTORY", "CONTRADICTORY_FISCAL_SEQUENCE", "CIK_IDENTITY_CONFLICT", "PROVIDER_IDENTITY_CONFLICT", "CURRENT_TICKER_PROVIDER_CONFLICT", "PERMATICKER_CIK_CONFLICT", "TICKER_REUSE_RISK", "TICKER_REUSE_PROVIDER_CONFLICT", "EXCHANGE_UNKNOWN"} for blocker in blockers) else "REJECTED"
            reason = ",".join(blockers)
        else:
            status = "ELIGIBLE"
            reason = "Eligible from provider identity, price, classification and fundamentals evidence."
        safe_rows = tuple(dict(row) for row in rows) if include_rows else ()
        items.append(GenericBatchItemPlan(
            requested_ticker=ticker,
            ticker=ticker,
            status=status,
            reason=reason,
            source_category=source_category,
            provider_metadata=metadata_state,
            market=market,
            classification=classification,
            canonical=canonical,
            identity_resolution=identity_resolution,
            provider_row_count=len(rows),
            provider_arq_row_count=len(arq_rows),
            source_fingerprint=stable_hash({"ticker": ticker, "source_category": source_category, "rows": rows}),
            rows=safe_rows,
        ))
    plan = GenericBatchPlan(
        contract_version=CONTRACT_VERSION,
        created_at_utc=created,
        network_allowed=network_allowed,
        archive_path=str(effective_archive) if effective_archive else None,
        source_state=source_state(paths),
        items=tuple(items),
        network=network,
    )
    from rawcandle.fundamentals.admin.ticker_reporting import build_preview_reporting

    return replace(
        plan,
        ticker_reporting=tuple(build_preview_reporting(paths, plan.safe_dict(include_rows=True))),
    )


def create_copy_lane(
    paths: BatchAddTickerPaths,
    *,
    lane_dir: Path,
    writer: AdminRunWriter | None = None,
) -> CopyLane:
    lane_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    copied: dict[str, Path] = {}
    for role in ROLE_ORDER:
        source = paths.as_dict()[role]
        destination = lane_dir / f"{role}.db"
        manifest[role] = online_backup(source, destination)
        copied[role] = destination
        if writer is not None:
            writer.append_heartbeat({"stage": "COPY_DATABASE", "role": role, "destination": str(destination)})
    copy_paths = BatchAddTickerPaths(
        provider_db=copied["provider"],
        canonical_db=copied["canonical"],
        analysis_db=copied["analysis"],
        market_db=copied["market"],
        taxonomy_db=copied["taxonomy"],
    )
    reject_production_write_targets(copy_paths)
    return CopyLane(lane_dir=lane_dir, paths=copy_paths, manifest=manifest)


def cleanup_copy_lane(lane: CopyLane) -> dict[str, Any]:
    removed: list[str] = []
    for path in sorted(lane.lane_dir.glob("**/*"), reverse=True):
        if path.is_file() and (
            path.suffix in {".db", ".sqlite", ".sqlite3"}
            or path.name.endswith(("-wal", "-shm", "-journal"))
        ):
            removed.append(str(path))
            path.unlink(missing_ok=True)
    for path in sorted(lane.lane_dir.glob("**/*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        lane.lane_dir.rmdir()
    except OSError:
        pass
    return {"removed_files": removed, "removed_count": len(removed)}


def _status_from_phase13d(row: Mapping[str, Any]) -> AdminStatus:
    status = str(row.get("status") or "")
    ready = bool(row.get("ready_for_apply"))
    if ready:
        return AdminStatus.ELIGIBLE
    if status == "ALREADY_PRESENT":
        return AdminStatus.ALREADY_PRESENT
    if status in {"IDENTITY_AMBIGUOUS", "API_FETCH_REQUIRED", "READY_WITH_LIMITATIONS"}:
        return AdminStatus.REVIEW_REQUIRED
    return AdminStatus.REJECTED


def _reason(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or "UNKNOWN")
    eligibility = row.get("eligibility") if isinstance(row.get("eligibility"), Mapping) else {}
    primary = eligibility.get("primary_rejection_reason")
    if primary:
        return f"{status}: {primary}"
    if status == "READY_WITH_LIMITATIONS":
        return "Eligible for copy apply, but taxonomy connectivity is limited."
    if status == "READY_LOCAL_PROVIDER":
        return "Eligible from local provider and market evidence."
    if status == "ALREADY_PRESENT":
        return "Ticker is already present in canonical identities."
    return status.replace("_", " ").title()


def _decision_from_row(row: Mapping[str, Any]) -> AdminItemDecision:
    provider = row.get("provider") if isinstance(row.get("provider"), Mapping) else {}
    identity = provider.get("identity") if isinstance(provider.get("identity"), Mapping) else {}
    market = row.get("market") if isinstance(row.get("market"), Mapping) else {}
    markets = market.get("markets") if isinstance(market.get("markets"), list) else []
    return AdminItemDecision(
        item_key=str(row.get("ticker")),
        requested_value=str(row.get("ticker")),
        normalized_value=str(row.get("ticker")),
        status=_status_from_phase13d(row),
        reason=_reason(row),
        market=str(markets[0]) if len(markets) == 1 else None,
        company_name=identity.get("name"),
        old_value=None,
        new_value="ADD_TO_OPERATIONAL_UNIVERSE" if row.get("ready_for_apply") else None,
        source_category=str(provider.get("source") or provider.get("status") or "local"),
        warnings=tuple(row.get("eligibility", {}).get("rejection_reasons", []) if isinstance(row.get("eligibility"), Mapping) else ()),
        blockers=tuple(row.get("eligibility", {}).get("rejection_reasons", []) if isinstance(row.get("eligibility"), Mapping) else ()),
        applied_action="PENDING_COPY_APPLY" if row.get("ready_for_apply") else None,
        details={
            "phase13d_status": row.get("status"),
            "provider": provider,
            "market": market,
            "canonical": row.get("canonical"),
            "taxonomy": row.get("taxonomy"),
            "estimated_impact": row.get("estimated_impact"),
        },
    )


def _decision_from_plan_item(item: GenericBatchItemPlan) -> AdminItemDecision:
    status = {
        "ELIGIBLE": AdminStatus.ELIGIBLE,
        "ALREADY_PRESENT": AdminStatus.ALREADY_PRESENT,
        "REVIEW_REQUIRED": AdminStatus.REVIEW_REQUIRED,
        "REJECTED": AdminStatus.REJECTED,
    }.get(item.status, AdminStatus.REVIEW_REQUIRED)
    metadata = item.provider_metadata.get("identity") if isinstance(item.provider_metadata.get("identity"), Mapping) else {}
    return AdminItemDecision(
        item_key=item.ticker,
        requested_value=item.requested_ticker,
        normalized_value=item.ticker,
        status=status,
        reason=item.reason,
        market="usa" if item.market.get("markets") == ["usa"] else None,
        company_name=metadata.get("name"),
        old_value=None,
        new_value="ADD_TO_OPERATIONAL_UNIVERSE" if item.eligible else None,
        source_category=item.source_category,
        warnings=(item.reason,) if status == AdminStatus.REVIEW_REQUIRED else (),
        blockers=(item.reason,) if status in {AdminStatus.REVIEW_REQUIRED, AdminStatus.REJECTED} else (),
        applied_action="PENDING_AUTHORITATIVE_COPY_APPLY" if item.eligible else None,
        details=item.safe_dict(include_rows=False),
    )


def _decision_from_plan_mapping(item: Mapping[str, Any]) -> AdminItemDecision:
    status = {
        "ELIGIBLE": AdminStatus.ELIGIBLE,
        "ALREADY_PRESENT": AdminStatus.ALREADY_PRESENT,
        "REVIEW_REQUIRED": AdminStatus.REVIEW_REQUIRED,
        "REJECTED": AdminStatus.REJECTED,
    }.get(str(item.get("status")), AdminStatus.REVIEW_REQUIRED)
    metadata_state = item.get("provider_metadata") if isinstance(item.get("provider_metadata"), Mapping) else {}
    metadata = metadata_state.get("identity") if isinstance(metadata_state.get("identity"), Mapping) else {}
    return AdminItemDecision(
        item_key=str(item.get("ticker")),
        requested_value=str(item.get("requested_ticker") or item.get("ticker")),
        normalized_value=str(item.get("ticker")),
        status=status,
        reason=str(item.get("reason") or item.get("status") or "UNKNOWN"),
        market="usa" if item.get("market", {}).get("markets") == ["usa"] else None,
        company_name=metadata.get("name"),
        old_value=None,
        new_value="ADD_TO_OPERATIONAL_UNIVERSE" if status == AdminStatus.ELIGIBLE else None,
        source_category=str(item.get("source_category") or "unknown"),
        warnings=(str(item.get("reason")),) if status == AdminStatus.REVIEW_REQUIRED else (),
        blockers=(str(item.get("reason")),) if status in {AdminStatus.REVIEW_REQUIRED, AdminStatus.REJECTED} else (),
        applied_action="PENDING_AUTHORITATIVE_COPY_APPLY" if status == AdminStatus.ELIGIBLE else None,
        details={key: value for key, value in item.items() if key != "rows"},
    )


def build_preview_from_copy(
    paths: BatchAddTickerPaths,
    request: AdminBatchRequest,
    *,
    now: str | None = None,
    network_allowed: bool = False,
    network_client: SharadarClient | None = None,
) -> tuple[AdminPreview, dict[str, Any]]:
    raw_preview = build_ticker_preview(paths.as_phase13d(), request.normalized_inputs, now=now)
    generic_plan = build_generic_batch_plan(
        paths,
        request,
        now=now or raw_preview["created_at_utc"],
        network_allowed=network_allowed,
        network_client=network_client,
    )
    rejected_decisions = tuple(
        AdminItemDecision(
            item_key=str(item["requested_value"]),
            requested_value=str(item["requested_value"]),
            normalized_value=str(item["requested_value"]).upper(),
            status=AdminStatus.REJECTED,
            reason=str(item["reason"]),
            source_category="input_parser",
            blockers=(str(item["reason"]),),
        )
        for item in request.rejected_inputs
    )
    if _provider_schema_ready(paths.provider_db):
        decisions = tuple(_decision_from_plan_item(item) for item in generic_plan.items) + rejected_decisions
        proposed = tuple(
            {
                "ticker": item.ticker,
                "action": "ADD_TICKER",
                "status": item.status,
                "ready_for_apply": item.eligible,
                "source_category": item.source_category,
                "provider_row_count": item.provider_row_count,
                "provider_arq_row_count": item.provider_arq_row_count,
            }
            for item in generic_plan.items
            if item.eligible
        )
    else:
        decisions = tuple(_decision_from_row(row) for row in raw_preview["ticker_results"]) + rejected_decisions
        proposed = tuple(
            {
                "ticker": row["ticker"],
                "action": "ADD_TICKER",
                "status": row["status"],
                "ready_for_apply": row["ready_for_apply"],
            }
            for row in raw_preview["ticker_results"]
            if row.get("ready_for_apply")
        )
    preview = AdminPreview(
        operation_type=AdminOperationType.ADD_TICKERS,
        request=request,
        decisions=decisions,
        source_state=generic_plan.source_state,
        proposed_changes=proposed,
        warnings=tuple(
            item.reason for item in generic_plan.items if item.status == "REVIEW_REQUIRED"
        ) + (("Network access enabled for missing archive/provider rows.",) if network_allowed else ()),
    )
    preview_dict = preview.as_dict()
    raw_preview["phase13g2_preview_fingerprint"] = preview_dict["preview_fingerprint"]
    raw_preview["phase13g2_request_fingerprint"] = preview_dict["request_fingerprint"]
    raw_preview["phase13g2_change_set_fingerprint"] = preview_dict["change_set_fingerprint"]
    raw_preview["generic_batch_plan"] = generic_plan.safe_dict(include_rows=True)
    return preview, raw_preview


def _write_preview_payload(path: Path, raw_preview: Mapping[str, Any], phase13g2_preview: Mapping[str, Any]) -> None:
    payload = dict(raw_preview)
    payload["phase13g2_preview"] = dict(phase13g2_preview)
    write_json(path, payload)


def _load_preview_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_preview_not_stale(paths: BatchAddTickerPaths, payload: Mapping[str, Any]) -> None:
    phase_preview = payload.get("phase13g2_preview") if isinstance(payload.get("phase13g2_preview"), Mapping) else {}
    fresh = source_state(paths)
    if fresh != phase_preview.get("source_state"):
        raise ValueError("PHASE13G2_STALE_PREVIEW_SOURCE_STATE_CHANGED")


def _provider_schema_ready(path: Path) -> bool:
    with _readonly(path) as conn:
        return all(_table_exists(conn, table) for table in ("provider_run", "provider_observation", "sharadar_fundamental_observation"))


def _ensure_identity_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS provider_company_identity("
        "provider TEXT NOT NULL, provider_identifier_type TEXT NOT NULL, provider_identifier_value TEXT NOT NULL, "
        "company_id INTEGER NOT NULL, provider_ticker TEXT, source TEXT NOT NULL, source_type TEXT NOT NULL, "
        "source_value TEXT, created_at_utc TEXT NOT NULL, PRIMARY KEY(provider,provider_identifier_type,provider_identifier_value))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS provider_security_identity("
        "provider TEXT NOT NULL, provider_security_id TEXT NOT NULL, security_id INTEGER NOT NULL, "
        "provider_ticker TEXT, source TEXT NOT NULL, created_at_utc TEXT NOT NULL, PRIMARY KEY(provider,provider_security_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS company_cik("
        "company_id INTEGER NOT NULL, cik_normalized TEXT NOT NULL, cik_display TEXT NOT NULL, source TEXT NOT NULL, "
        "source_table TEXT, source_row_id TEXT, status TEXT NOT NULL, created_at_utc TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'LEGACY_BOOTSTRAP', "
        "source_name TEXT, source_field TEXT, source_value TEXT, derivation TEXT, confidence TEXT NOT NULL DEFAULT 'HIGH', "
        "PRIMARY KEY(company_id,cik_normalized))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS phase13g2_applied_plan("
        "plan_fingerprint TEXT PRIMARY KEY, operation TEXT NOT NULL, applied_at_utc TEXT NOT NULL)"
    )


def _next_id(conn: sqlite3.Connection, table: str, column: str) -> int:
    return int(conn.execute(f"SELECT COALESCE(MAX({column}),0)+1 FROM {table}").fetchone()[0])


def _apply_identities(paths: BatchAddTickerPaths, items: Sequence[Mapping[str, Any]], *, applied_at: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(paths.canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            _ensure_identity_tables(conn)
            for item in items:
                ticker = str(item["ticker"]).upper()
                metadata_state = item.get("provider_metadata") if isinstance(item.get("provider_metadata"), Mapping) else {}
                metadata = metadata_state.get("identity") if isinstance(metadata_state.get("identity"), Mapping) else {}
                resolution = item.get("identity_resolution") if isinstance(item.get("identity_resolution"), Mapping) else {}
                mutation = resolution.get("mutation") if isinstance(resolution.get("mutation"), Mapping) else {}
                if not resolution:
                    raise RuntimeError(f"IDENTITY_RESOLUTION_REQUIRED:{ticker}")
                existing = conn.execute(
                    "SELECT c.company_id,s.security_id FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)=UPPER(?)",
                    (ticker,),
                ).fetchone()
                if existing:
                    rows.append({"ticker": ticker, "company_id": int(existing["company_id"]), "security_id": int(existing["security_id"]), "status": "ALREADY_PRESENT"})
                    continue
                cik = str(metadata.get("cik") or "").strip()
                permaticker = str(metadata.get("permaticker") or "").strip()
                action = str(mutation.get("action") or "")
                if not resolution.get("automatic_mutation_permitted") or action not in {"UPDATE_CURRENT_TICKER", "CREATE_SECURITY", "CREATE_COMPANY_AND_SECURITY"}:
                    raise RuntimeError(f"IDENTITY_MUTATION_NOT_AUTHORIZED:{ticker}")
                if resolution.get("authority_class") == "APPROVED_REVIEW" and (
                    resolution.get("readiness_state") != "APPROVED_VALID"
                    or "APPROVED_REVIEW_VALID" not in resolution.get("reason_codes", [])
                    or not resolution.get("approval_fingerprint")
                ):
                    raise RuntimeError(f"IDENTITY_APPROVAL_BINDING_INVALID:{ticker}")
                if action == "UPDATE_CURRENT_TICKER":
                    company_id = int(mutation["company_id"])
                    security_id = int(mutation["security_id"])
                    security = conn.execute(
                        "SELECT company_id,current_ticker,exchange FROM security WHERE security_id=?",
                        (security_id,),
                    ).fetchone()
                    if security is None or int(security["company_id"]) != company_id:
                        raise RuntimeError(f"IDENTITY_TRANSITION_TARGET_MISMATCH:{ticker}")
                    old_ticker = str(security["current_ticker"]).upper()
                    effective_date = str(mutation.get("effective_date") or metadata.get("firstpricedate") or applied_at[:10])
                    old_alias_exists = conn.execute(
                        "SELECT 1 FROM ticker_alias WHERE security_id=? AND UPPER(ticker)=? LIMIT 1",
                        (security_id, old_ticker),
                    ).fetchone()
                    if old_alias_exists is None:
                        conn.execute(
                            "INSERT INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES(?,?,?,?,?,?)",
                            (security_id, old_ticker, "SHARADAR", None, effective_date, PHASE),
                        )
                    conn.execute(
                        "UPDATE ticker_alias SET valid_to=COALESCE(valid_to,?) WHERE security_id=? AND UPPER(ticker)=? AND UPPER(ticker)<>?",
                        (effective_date, security_id, old_ticker, ticker),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES(?,?,?,?,NULL,?)",
                        (security_id, ticker, "SHARADAR", effective_date, PHASE),
                    )
                    conn.execute(
                        "UPDATE security SET current_ticker=?,exchange=COALESCE(?,exchange),updated_at_utc=? WHERE security_id=?",
                        (ticker, metadata.get("exchange"), applied_at, security_id),
                    )
                    if permaticker:
                        linked = conn.execute(
                            "SELECT security_id FROM provider_security_identity WHERE provider='SHARADAR' AND provider_security_id=?",
                            (permaticker,),
                        ).fetchone()
                        if linked is None or int(linked["security_id"]) != security_id:
                            raise RuntimeError(f"IDENTITY_TRANSITION_PERMATICKER_MISMATCH:{ticker}")
                        conn.execute(
                            "UPDATE provider_security_identity SET provider_ticker=?,source=? WHERE provider='SHARADAR' AND provider_security_id=?",
                            (ticker, PHASE, permaticker),
                        )
                    rows.append({"ticker": ticker, "company_id": company_id, "security_id": security_id, "status": "TICKER_TRANSITION", "predecessor_ticker": old_ticker})
                    continue
                target_company_id = mutation.get("company_id")
                company_id = int(target_company_id) if action == "CREATE_SECURITY" and target_company_id is not None else _next_id(conn, "company", "company_id")
                security_id = _next_id(conn, "security", "security_id")
                company_key = f"SEC_CIK:{cik}" if cik else f"SHARADAR_PERMATICKER:{permaticker}"
                company_name = metadata.get("name") or ticker
                exchange = metadata.get("exchange") or "usa"
                valid_from = metadata.get("firstpricedate") or item.get("market", {}).get("first_date") or applied_at[:10]
                if action == "CREATE_COMPANY_AND_SECURITY":
                    conn.execute(
                        "INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?)",
                        (company_id, company_key, company_name, "ACTIVE", applied_at, applied_at),
                    )
                elif action != "CREATE_SECURITY" or conn.execute("SELECT 1 FROM company WHERE company_id=?", (company_id,)).fetchone() is None:
                    raise RuntimeError(f"IDENTITY_COMPANY_TARGET_MISMATCH:{ticker}")
                conn.execute(
                    "INSERT INTO security(security_id,company_id,current_ticker,exchange,active,valid_from,valid_to,created_at_utc,updated_at_utc) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (security_id, company_id, ticker, exchange, 1, valid_from, None, applied_at, applied_at),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES (?,?,?,?,?,?)",
                    (security_id, ticker, "SHARADAR", valid_from, None, PHASE),
                )
                if permaticker:
                    conn.execute(
                        "INSERT OR IGNORE INTO provider_security_identity(provider,provider_security_id,security_id,provider_ticker,source,created_at_utc) VALUES('SHARADAR',?,?,?,?,?)",
                        (permaticker, security_id, ticker, PHASE, applied_at),
                    )
                if cik:
                    conn.execute(
                        "INSERT OR IGNORE INTO provider_company_identity(provider,provider_identifier_type,provider_identifier_value,company_id,provider_ticker,source,source_type,source_value,created_at_utc) "
                        "VALUES('SEC','CIK',?,?,?,?,?,?,?)",
                        (cik, company_id, ticker, PHASE, "sharadar_ticker_metadata.secfilings", cik, applied_at),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO company_cik(company_id,cik_normalized,cik_display,source,source_table,source_row_id,status,created_at_utc,source_type,source_name,source_field,source_value,derivation,confidence) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (company_id, cik, cik, PHASE, "sharadar_ticker_metadata", ticker, "ACTIVE", applied_at, "PROVIDER_METADATA", "Sharadar ticker metadata", "secfilings", cik, "parsed SEC CIK query parameter", "HIGH"),
                    )
                rows.append({"ticker": ticker, "company_id": company_id, "security_id": security_id, "status": "CREATED_SECURITY" if action == "CREATE_SECURITY" else "CREATED"})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"rows": rows, "created": sum(1 for row in rows if row["status"] in {"CREATED", "CREATED_SECURITY", "TICKER_TRANSITION"}), "fingerprint": stable_hash(rows)}


def _stage_generic_provider_rows(paths: BatchAddTickerPaths, items: Sequence[Mapping[str, Any]], *, applied_at: str, inject_failure: bool = False) -> dict[str, Any]:
    identities: dict[str, tuple[int, int]] = {}
    with _readonly(paths.canonical_db) as canonical:
        for row in canonical.execute("SELECT company_id,security_id,current_ticker FROM security"):
            identities[str(row["current_ticker"]).upper()] = (int(row["company_id"]), int(row["security_id"]))
    run_id = "PHASE13G2_" + stable_hash({item["ticker"]: item.get("source_fingerprint") for item in items})[:24]
    inserted = Counter()
    matched = Counter()
    skipped = Counter()
    with sqlite3.connect(paths.provider_db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if not _table_exists(conn, "provider_run"):
            conn.executescript(PROVIDER_SCHEMA_SQL)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,request_scope,entitlement_scope,source_version,metadata_json) "
                "VALUES(?,'SHARADAR',?,?,'SUCCESS',?,?,?,?)",
                (
                    run_id, applied_at, applied_at, "PHASE13G2_GENERIC_BATCH_ADD_TICKERS",
                    "Sharadar local/archive/network staged batch", CONTRACT_VERSION,
                    json.dumps({"tickers": [item["ticker"] for item in items], "sources": {item["ticker"]: item.get("source_category") for item in items}}, sort_keys=True),
                ),
            )
            seen = 0
            for item in items:
                ticker = str(item["ticker"]).upper()
                identity = identities.get(ticker)
                if identity is None:
                    skipped["identity_not_found"] += len(item.get("rows") or ())
                    continue
                company_id, security_id = identity
                for row in item.get("rows") or ():
                    staged = dict(row)
                    staged["ticker"] = ticker
                    if not staged.get("permaticker"):
                        metadata = item.get("provider_metadata", {}).get("identity", {})
                        staged["permaticker"] = metadata.get("permaticker")
                    dimension = str(staged.get("dimension") or "").upper()
                    if dimension not in {"ARQ", "MRQ", "ART", "MRT", "ARY", "MRY"}:
                        skipped["unsupported_dimension"] += 1
                        continue
                    matched[dimension] += 1
                    if insert_production_sharadar_observation(conn, staged, run_id, applied_at, company_id=company_id, security_id=security_id):
                        inserted[dimension] += 1
                    seen += 1
                    if inject_failure and seen >= 3:
                        raise RuntimeError("PHASE13G2_INJECTED_PROVIDER_STAGING_FAILURE")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "run_id": run_id,
        "matched_by_dimension": dict(sorted(matched.items())),
        "inserted_by_dimension": dict(sorted(inserted.items())),
        "logical_changes": sum(inserted.values()),
        "skipped": dict(sorted(skipped.items())),
    }


def _valuation_classification_update_generic(
    paths: BatchAddTickerPaths,
    *,
    tickers: Sequence[str],
    applied_at: str,
    allow_production: bool = False,
) -> dict[str, Any]:
    if not allow_production:
        reject_production_path(paths.analysis_db, "analysis")
    changed = 0
    classification = {ticker: _classification(paths, ticker) for ticker in tickers}
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("ATTACH DATABASE ? AS canonical", (str(paths.canonical_db),))
        conn.execute("BEGIN IMMEDIATE")
        try:
            marks = ",".join("?" for _ in tickers) or "?"
            params = tuple(tickers) if tickers else ("__none__",)
            if _table_exists(conn, "valuation_revised_result"):
                rows = [dict(row) for row in conn.execute(
                    "SELECT DISTINCT r.company_id,s.current_ticker "
                    "FROM valuation_revised_result r JOIN canonical.security s ON s.security_id=r.security_id "
                    f"WHERE UPPER(s.current_ticker) IN ({marks})",
                    params,
                )]
                for row in rows:
                    source = classification.get(str(row["current_ticker"]).upper())
                    if not source or source.get("status") != "READY":
                        continue
                    before = conn.total_changes
                    conn.execute(
                        "UPDATE valuation_revised_result SET ticker=?,sector=?,industry=? WHERE company_id=?",
                        (row["current_ticker"], source["sector"], source["industry"], int(row["company_id"])),
                    )
                    changed += conn.total_changes - before
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("DETACH DATABASE canonical")
    return {"outcome": "APPLIED" if changed else "NO_CHANGE", "rows_changed": changed, "policy": "CURRENT_REVISED_NON_PIT_CLASSIFICATION", "applied_at_utc": applied_at}


def _manual_rv_refresh_generic(paths: BatchAddTickerPaths, *, output: Path, applied_at: str) -> dict[str, Any]:
    source = load_relative_valuation_source(
        RVSourcePaths(paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db, paths.provider_db),
        as_of_date=REPORT_DATE,
    )
    snapshot = calculate_relative_valuation(
        source.inputs,
        as_of_date=REPORT_DATE,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    content, physical = validate_rv_snapshot(snapshot, source.inputs)
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        first = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at)
        second_before = database_inventory(paths.analysis_db)
        second = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at)
        second_after = database_inventory(paths.analysis_db)
        check = rv_quick_check(conn)
        active = RelativeValuationRepository(conn).active_metadata(model_fingerprint=RV_MODEL_FINGERPRINT)
    result = {
        "source_metadata": source.metadata,
        "snapshot": {
            "source_fingerprint": snapshot.source_fingerprint,
            "result_fingerprint": snapshot.result_fingerprint,
            "physical_content_fingerprint": physical,
            "company_count": len(content["companies"]),
            "peer_rows": len(content["peers"]),
            "own_history_rows": len(content["own_history"]),
            "component_rows": len(content["components"]),
        },
        "first_apply": asdict(first),
        "second_apply": asdict(second),
        "second_logical_zero_writes": second.logical_bulk_writes == 0 and second.pointer_changes == 0,
        "second_physical_no_change": second_before == second_after,
        "quick_check": check,
        "active_metadata": active,
    }
    write_json(output / "relative_valuation_manual_refresh.json", result)
    return result


def _snapshot_smoke_generic(paths: BatchAddTickerPaths, output: Path, *, tickers: Sequence[str], report_date: str = REPORT_DATE) -> dict[str, Any]:
    report_dir = output / "snapshot_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paths = SnapshotPaths(paths.canonical_db, paths.analysis_db, paths.market_db, paths.taxonomy_db, paths.provider_db)
    results = {}
    for ticker in tickers:
        try:
            generated = generate_active_company_snapshot(
                snapshot_paths,
                ticker=ticker,
                report_date=report_date,
                output_dir=report_dir,
                overwrite=True,
            )
            text = Path(generated["output_path"]).read_text(encoding="utf-8")
            results[ticker] = {
                "status": generated["status"],
                "fingerprint": generated["report_content_fingerprint"],
                "output_path": generated["output_path"],
                "contains_internal_ids": any(term in text for term in ("company_id", "security_id", "quarter_id")),
            }
        except Exception as exc:
            reason = str(exc)
            if isinstance(exc, LookupError) and reason.startswith("NO_FUNDAMENTAL_ENDPOINT_ON_OR_BEFORE_REPORT_DATE:"):
                results[ticker] = {
                    "status": "READINESS_LIMITED",
                    "error": type(exc).__name__,
                    "reason": reason,
                    "readiness_limitation": "No eligible fundamental endpoint exists on or before the smoke report date.",
                }
            else:
                results[ticker] = {"status": "FAILED", "error": type(exc).__name__, "reason": reason}
    return results


def _run_authoritative_downstream(
    paths: BatchAddTickerPaths,
    output: Path,
    *,
    accepted_tickers: Sequence[str],
    applied_at: str,
    as_of_date: str | None = None,
    progress: ProgressTracker | None = None,
    allow_production: bool = False,
    snapshot_control_tickers: Sequence[str] = (),
) -> dict[str, Any]:
    if allow_production:
        raise PermissionError("ADMIN_FULL_V2_ATOMIC_PRODUCTION_REPLACEMENT_NOT_READY")
    result: dict[str, Any] = {"applied_at_utc": applied_at, "accepted_tickers": list(accepted_tickers)}
    if progress:
        progress.running(ProgressStage.CANONICAL_REBUILD, "Rebuilding canonical quarters from staged provider rows.")
    with _background_heartbeat(progress, "Canonical rebuild is still running."):
        result["canonical"] = reconcile_canonical(paths.provider_db, paths.canonical_db, applied_at=applied_at)
    if progress:
        progress.completed(
            ProgressStage.CANONICAL_REBUILD,
            "Canonical rebuild completed.",
            processed_rows=int(result["canonical"].get("canonical_rows") or 0),
        )
        progress.running(ProgressStage.TTM_REBUILD, "Rebuilding TTM endpoints.")
    with _background_heartbeat(progress, "TTM rebuild is still running."):
        result["ttm"] = rebuild_ttm(paths.canonical_db, applied_at=applied_at)
    if progress:
        progress.completed(ProgressStage.TTM_REBUILD, "TTM rebuild completed.", processed_rows=int(result["ttm"].get("rows") or 0))
        progress.running(ProgressStage.STRUCTURAL_DEPENDENCIES, "Applying structural dependency contract.")
    result["structural_contract"] = structural_break.apply_contract(paths.canonical_db, events=_events(), applied_at_utc=applied_at)
    result["structural_evidence"] = _structural_evidence(paths.canonical_db)
    structural_package_fingerprint = _structural_package_fingerprint(result["structural_contract"])
    result["structural_package_fingerprint"] = structural_package_fingerprint
    if progress:
        progress.completed(
            ProgressStage.STRUCTURAL_DEPENDENCIES,
            "Structural dependencies applied.",
            processed_rows=int(result["structural_contract"].get("quarter_regime_count") or 0),
        )
    if progress:
        progress.running(ProgressStage.PACKAGE_CALCULATION, "Building fresh full V2 analysis and Relative Valuation.")
    with _background_heartbeat(progress, "Full V2 analysis rebuild is still running."):
        rebuilt = run_full_v2_downstream(paths.as_dict(), output=output, as_of_date=as_of_date or applied_at[:10])
    result.update(rebuilt)
    if progress:
        progress.completed(
            ProgressStage.PACKAGE_CALCULATION,
            "Full V2 and Relative Valuation rebuild validated.",
        )
        for stage in (ProgressStage.PACKAGE_APPLY, ProgressStage.RELATIVE_POSITION, ProgressStage.RELATIVE_VALUATION):
            progress.running(stage, "Validated by the full V2 rebuild.")
            progress.completed(stage, "Validated by the full V2 rebuild.")
        progress.skipped(ProgressStage.DEPENDENCY_ATTACHMENT, "Fresh V2 analysis has its own validated dependencies.")
        progress.running(ProgressStage.SNAPSHOT_SMOKE, "Generating eligible Snapshot smoke reports.")
    snapshot_tickers = tuple(dict.fromkeys([*accepted_tickers, *snapshot_control_tickers]))
    candidate_paths = replace(paths, analysis_db=Path(rebuilt["candidate_analysis_db"]))
    result["snapshots"] = _snapshot_smoke_generic(candidate_paths, output, tickers=snapshot_tickers, report_date=as_of_date or applied_at[:10])
    if progress:
        progress.completed(ProgressStage.SNAPSHOT_SMOKE, "Snapshot smoke completed.", processed_items=len(result["snapshots"]), total_items=len(snapshot_tickers))
    return result


def _skip_authoritative_downstream_progress(progress: ProgressTracker, *, reason: str) -> None:
    for stage in (
        ProgressStage.CANONICAL_REBUILD,
        ProgressStage.TTM_REBUILD,
        ProgressStage.STRUCTURAL_DEPENDENCIES,
        ProgressStage.PACKAGE_CALCULATION,
        ProgressStage.PACKAGE_APPLY,
        ProgressStage.RELATIVE_POSITION,
        ProgressStage.RELATIVE_VALUATION,
        ProgressStage.DEPENDENCY_ATTACHMENT,
        ProgressStage.SNAPSHOT_SMOKE,
    ):
        progress.skipped(stage, reason)


def _apply_generic_plan(
    paths: BatchAddTickerPaths,
    plan: Mapping[str, Any],
    *,
    output: Path,
    failure_boundary: str | None = None,
    progress: ProgressTracker | None = None,
    allow_production: bool = False,
    snapshot_control_tickers: Sequence[str] = (),
    as_of_date: str | None = None,
) -> dict[str, Any]:
    plan_fingerprint = str(plan.get("plan_fingerprint") or stable_hash(plan))
    items = [item for item in plan.get("items", []) if item.get("status") == "ELIGIBLE"]
    accepted = [str(item["ticker"]).upper() for item in items]
    applied_at = utc_now()
    with sqlite3.connect(paths.canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_identity_tables(conn)
        existing = conn.execute("SELECT 1 FROM phase13g2_applied_plan WHERE plan_fingerprint=?", (plan_fingerprint,)).fetchone()
    if existing:
        if progress:
            progress.running(ProgressStage.NO_CHANGE_VERIFICATION, "Verifying previously applied no-change batch.")
            progress.completed(ProgressStage.NO_CHANGE_VERIFICATION, "No copy-lane changes required.", processed_items=0, total_items=len(accepted))
        return {"outcome": "NO_CHANGE", "preview_fingerprint": plan_fingerprint, "applied_tickers": [], "downstream": {"invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0}}}
    if progress:
        progress.running(ProgressStage.IDENTITY_AND_UNIVERSE, "Persisting canonical and provider identities.", processed_items=0, total_items=len(accepted))
    identities = _apply_identities(paths, items, applied_at=applied_at)
    if progress:
        progress.completed(ProgressStage.IDENTITY_AND_UNIVERSE, "Canonical and provider identities persisted.", processed_items=len(accepted), total_items=len(accepted))
    if failure_boundary == "identity":
        raise RuntimeError("PHASE13G2_INJECTED_AFTER_IDENTITY")
    if progress:
        progress.running(ProgressStage.PROVIDER_STAGING, "Staging provider rows for accepted tickers.", processed_items=0, total_items=len(accepted))
    provider = _stage_generic_provider_rows(paths, items, applied_at=applied_at, inject_failure=failure_boundary == "provider_staging")
    if progress:
        progress.completed(
            ProgressStage.PROVIDER_STAGING,
            "Provider staging completed.",
            processed_items=len(accepted),
            total_items=len(accepted),
            processed_rows=int(provider.get("logical_changes") or 0),
        )
    if failure_boundary == "provider":
        raise RuntimeError("PHASE13G2_INJECTED_AFTER_PROVIDER")
    if accepted:
        downstream = _run_authoritative_downstream(
            paths,
            output,
            accepted_tickers=accepted,
            applied_at=applied_at,
            as_of_date=as_of_date,
            progress=progress,
            allow_production=allow_production,
            snapshot_control_tickers=snapshot_control_tickers,
        )
    else:
        if progress:
            _skip_authoritative_downstream_progress(progress, reason="No eligible accepted tickers; downstream rebuilds not required.")
        downstream = {"invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0}}
    with sqlite3.connect(paths.canonical_db) as conn:
        _ensure_identity_tables(conn)
        conn.execute(
            "INSERT OR IGNORE INTO phase13g2_applied_plan(plan_fingerprint,operation,applied_at_utc) VALUES(?,?,?)",
            (plan_fingerprint, "GENERIC_BATCH_ADD_TICKERS", applied_at),
        )
        conn.commit()
    return {
        "outcome": "APPLIED" if identities["created"] or provider["logical_changes"] else "NO_CHANGE",
        "preview_fingerprint": plan_fingerprint,
        "applied_tickers": accepted,
        "identities": identities,
        "provider_staging": provider,
        "downstream": downstream,
    }


def run_preview(
    raw_inputs: str | Sequence[str],
    *,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    network_allowed: bool = False,
    market: str | None = "usa",
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    request = parse_batch_tickers(raw_inputs, market=market)
    run_id = stable_run_id(AdminOperationType.ADD_TICKERS, fingerprint(request))
    writer = AdminRunWriter(run_id, AdminOperationType.ADD_TICKERS, root=run_root)
    progress = ProgressTracker(
        run_id=run_id,
        operation_type=AdminOperationType.ADD_TICKERS,
        run_dir=writer.run_dir,
        stages=BATCH_ADD_TICKERS_STAGES,
        callback=progress_callback,
    )
    started = utc_now()
    progress.running(ProgressStage.PREFLIGHT, "Recording Batch Add Tickers preview request.", processed_items=0, total_items=len(request.normalized_inputs))
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Batch Add Tickers preview request recorded.")
    writer.write_json("request.json", request.as_dict() | {"network_allowed": network_allowed})
    progress.completed(ProgressStage.PREFLIGHT, "Preview request recorded.", processed_items=0, total_items=len(request.normalized_inputs))
    progress.running(ProgressStage.PREVIEW_VALIDATION, "Creating copy lane for read-only preview.")
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Creating copy lane for read-only production-shaped preview.")
    lane: CopyLane | None = None
    failure_stage = ProgressStage.PREVIEW_VALIDATION
    try:
        if len(request.normalized_inputs) > 25:
            raise ValueError("ADD_TICKERS_MAXIMUM_25_TICKERS")
        lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "preview_lane", writer=writer)
        progress.completed(ProgressStage.PREVIEW_VALIDATION, "Preview copy lane ready.")
        failure_stage = ProgressStage.SOURCE_RESOLUTION
        progress.running(ProgressStage.SOURCE_RESOLUTION, "Resolving provider, market, identity and classification evidence.", processed_items=0, total_items=len(request.normalized_inputs))
        preview, raw_preview = build_preview_from_copy(lane.paths, request, network_allowed=network_allowed)
        progress.completed(ProgressStage.SOURCE_RESOLUTION, "Source resolution completed.", processed_items=len(request.normalized_inputs), total_items=len(request.normalized_inputs))
        preview_dict = preview.as_dict()
        preview_path = writer.write_json("preview.json", preview_dict)
        phase13d_preview_path = writer.run_dir / "phase13d_preview_payload.json"
        _write_preview_payload(phase13d_preview_path, raw_preview, preview_dict)
        writer.write_items_csv([item.as_dict() for item in preview.decisions])
        writer.checkpoint(
            RunStage.PREVIEW_READY,
            message="Batch preview ready. Production was not modified.",
            preview_fingerprint=preview_dict["preview_fingerprint"],
            counters=_counts(preview.decisions),
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=AdminStatus.COMPLETED,
            mode="PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_dict["preview_fingerprint"],
            request=request.as_dict(),
            item_results=preview.decisions,
            summary_counts=_counts(preview.decisions),
            downstream={
                "package": "NOT_RUN_IN_PREVIEW",
                "relative_position": "NOT_RUN_IN_PREVIEW",
                "relative_valuation": "NOT_RUN_IN_PREVIEW",
                "network": "ALLOWED" if network_allowed else "DISABLED",
                "generic_plan": "READY",
            },
            artifacts={"preview": str(preview_path), "phase13d_preview_payload": str(phase13d_preview_path)},
            recommended_next_action="Review the preview. Copy-only apply requires --apply, --confirm-apply and the preview fingerprint.",
        )
        result_dict = result.as_dict()
        result_dict["ticker_reporting"] = raw_preview["generic_batch_plan"].get("ticker_reporting", [])
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_markdown_report(result_dict))
        progress.running(ProgressStage.CLEANUP, "Removing preview copy lane.")
        cleanup = cleanup_copy_lane(lane)
        progress.completed(ProgressStage.CLEANUP, "Preview copy lane removed.", processed_items=int(cleanup.get("removed_count") or 0))
        progress.running(ProgressStage.COMPLETED, "Preview run completed.")
        progress.completed(ProgressStage.COMPLETED, "Preview run completed.")
        writer.checkpoint(RunStage.COMPLETED, message="Preview run completed.", preview_fingerprint=preview_dict["preview_fingerprint"])
        writer.write_exit_code(0)
        writer.write_manifest()
        return result_dict | {
            "run_id": run_id,
            "artifact_dir": str(writer.run_dir),
            "phase13d_preview_payload_path": str(phase13d_preview_path),
            "cleanup": cleanup,
        }
    except Exception as exc:
        writer.write_error(exc)
        reason = (
            "Preview accepts at most 25 tickers. Shorten the list and try again."
            if str(exc) == "ADD_TICKERS_MAXIMUM_25_TICKERS"
            else "Preview failed during source resolution."
            if failure_stage == ProgressStage.SOURCE_RESOLUTION
            else "Preview failed during validation."
        )
        progress.failed(failure_stage, reason, errors=(f"{type(exc).__name__}: {exc}",))
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message="Preview failed before any write boundary.")
        error_decisions = tuple(
            AdminItemDecision(
                item_key=value,
                requested_value=value,
                normalized_value=value,
                status=AdminStatus.FAILED,
                reason=f"Preview failed before ticker eligibility could be determined: {type(exc).__name__}",
            )
            for value in request.normalized_inputs
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=AdminStatus.FAILED,
            mode="PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=None,
            request=request.as_dict(),
            item_results=error_decisions,
            summary_counts={"requested": len(request.normalized_inputs), "failed": len(error_decisions)},
            rollback={"status": "NOT_REQUIRED", "write_boundary_crossed": False},
            artifacts={
                "error": str(writer.run_dir / "error.json"),
                "progress": str(writer.run_dir / "progress_events.jsonl"),
            },
            recommended_next_action="Review Technical details and the operation report before retrying Preview.",
            errors=({"type": type(exc).__name__, "message": str(exc)},),
        ).as_dict()
        result.update({
            "artifact_dir": str(writer.run_dir),
            "failed_stage": failure_stage.value,
            "database_safety": "NO_DATABASE_WRITES",
            "user_error": reason,
        })
        writer.write_json("result.json", result)
        writer.write_exit_code(2)
        from rawcandle.fundamentals.admin.operation_report import write_operation_report
        write_operation_report(run_id, root=run_root)
        writer.write_manifest()
        cleanup = cleanup_copy_lane(lane) if lane is not None else {"removed_files": [], "removed_count": 0}
        return result | {"cleanup": cleanup, "error": type(exc).__name__}


def run_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    confirm_apply: bool = False,
    failure_boundary: str | None = None,
    keep_copies: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not confirm_apply:
        raise PermissionError("PHASE13G2_APPLY_REQUIRES_CONFIRMATION")
    payload = _load_preview_payload(preview_payload_path)
    phase_preview = payload.get("phase13g2_preview") if isinstance(payload.get("phase13g2_preview"), Mapping) else {}
    if phase_preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("PHASE13G2_PREVIEW_FINGERPRINT_MISMATCH")
    request_payload = phase_preview.get("request") if isinstance(phase_preview.get("request"), Mapping) else {}
    request = AdminBatchRequest(
        operation_type=AdminOperationType.ADD_TICKERS,
        requested_inputs=tuple(request_payload.get("requested_inputs") or ()),
        normalized_inputs=tuple(request_payload.get("normalized_inputs") or ()),
        rejected_inputs=tuple(request_payload.get("rejected_inputs") or ()),
        market=request_payload.get("market"),
        options=request_payload.get("options") or {},
    )
    run_id = stable_run_id(AdminOperationType.ADD_TICKERS, preview_fingerprint, suffix="apply")
    writer = AdminRunWriter(run_id, AdminOperationType.ADD_TICKERS, root=run_root)
    progress = ProgressTracker(
        run_id=run_id,
        operation_type=AdminOperationType.ADD_TICKERS,
        run_dir=writer.run_dir,
        stages=BATCH_ADD_TICKERS_STAGES,
        callback=progress_callback,
    )
    started = utc_now()
    progress.running(ProgressStage.PREFLIGHT, "Recording Batch Add Tickers apply request.", processed_items=0, total_items=len(request.normalized_inputs))
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Copy-only apply request recorded.", preview_fingerprint=preview_fingerprint)
    writer.write_json("request.json", request.as_dict())
    writer.write_json("preview.json", phase_preview)
    progress.completed(ProgressStage.PREFLIGHT, "Apply request recorded.", processed_items=0, total_items=len(request.normalized_inputs))
    progress.running(ProgressStage.PREVIEW_VALIDATION, "Creating copy lane for copy-only apply.")
    writer.checkpoint(RunStage.APPLY_STARTED, message="Creating copy lane for copy-only apply.", preview_fingerprint=preview_fingerprint)
    lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "apply_lane", writer=writer)
    rollback: dict[str, Any] = {}
    write_boundary_crossed = False
    try:
        progress.completed(ProgressStage.PREVIEW_VALIDATION, "Apply copy lane ready.")
        progress.running(ProgressStage.SOURCE_RESOLUTION, "Validating saved preview freshness and source plan.", processed_items=0, total_items=len(request.normalized_inputs))
        _assert_preview_not_stale(lane.paths, payload)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Preview is fresh on apply copy.", preview_fingerprint=preview_fingerprint)
        saved_plan = payload.get("generic_batch_plan")
        if not isinstance(saved_plan, Mapping):
            raise ValueError("ADMIN_ADD_TICKERS_SAVED_GENERIC_PLAN_REQUIRED")
        copy_preview, raw_preview = build_preview_from_copy(
            lane.paths, request, now=payload.get("created_at_utc"),
            network_allowed=bool(saved_plan.get("network_allowed")),
        )
        if raw_preview["generic_batch_plan"]["plan_fingerprint"] != saved_plan.get("plan_fingerprint"):
            raise ValueError("ADMIN_ADD_TICKERS_STALE_PLAN_CONTENT_CHANGED")
        progress.completed(ProgressStage.SOURCE_RESOLUTION, "Saved preview and source plan validated.", processed_items=len(request.normalized_inputs), total_items=len(request.normalized_inputs))
        copy_preview_path = lane.lane_dir / "accepted_preview.json"
        write_json(copy_preview_path, raw_preview)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Applying accepted tickers to database copies.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
        write_boundary_crossed = True
        before = source_state(lane.paths)["databases"]
        if not _provider_schema_ready(lane.paths.provider_db):
            raise RuntimeError("ADMIN_ADD_TICKERS_PROVIDER_SCHEMA_REQUIRED_FOR_V2_REBUILD")
        applied = _apply_generic_plan(
            lane.paths,
            saved_plan,
            output=lane.lane_dir / "generic_authoritative_apply",
            failure_boundary=failure_boundary,
            progress=progress,
            as_of_date=str(payload["created_at_utc"])[:10],
        )
        applied["mode"] = "GENERIC_AUTHORITATIVE_BATCH"
        after = source_state(lane.paths)["databases"]
        repeated = _apply_generic_plan(
            lane.paths,
            saved_plan,
            output=lane.lane_dir / "generic_authoritative_repeat",
            progress=progress,
        )
        saved_plan_items = saved_plan.get("items") if isinstance(saved_plan.get("items"), list) else []
        base_decisions = tuple(_decision_from_plan_mapping(item) for item in saved_plan_items) or copy_preview.decisions
        decisions = _apply_decisions(base_decisions, applied)
        counts = _counts(decisions)
        downstream = applied.get("downstream") if isinstance(applied.get("downstream"), Mapping) else {}
        invocation_counts = downstream.get("invocation_counts") if isinstance(downstream, Mapping) else None
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=AdminStatus.PARTIALLY_COMPLETED if any(item.status in {AdminStatus.REJECTED, AdminStatus.REVIEW_REQUIRED} for item in decisions) else AdminStatus.COMPLETED,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            item_results=decisions,
            summary_counts=counts,
            rollback={"status": "NOT_REQUIRED"},
            downstream={
                "mode": applied.get("mode"),
                "phase13d_candidate_apply": "NOT_USED_GENERIC_AUTHORITATIVE_BATCH" if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH" else "RUN_ONCE_FOR_BATCH",
                "package": downstream.get("package", "NOT_RUN") if isinstance(downstream, Mapping) else "NOT_RUN",
                "relative_position": downstream.get("relative_position", "NOT_RUN") if isinstance(downstream, Mapping) else "NOT_RUN",
                "relative_valuation": downstream.get("relative_valuation", applied.get("relative_valuation_state")) if isinstance(downstream, Mapping) else applied.get("relative_valuation_state"),
                "active_taxonomy": downstream.get("active_taxonomy") if isinstance(downstream, Mapping) else None,
                "invocation_counts": invocation_counts or {"package": 0, "relative_position": 0, "relative_valuation": 0},
                "repeat_apply_outcome": repeated.get("outcome"),
                "authoritative_downstream": {
                    "status": "COMPLETED_FOR_GENERIC_BATCH" if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH" else AUTHORITATIVE_DOWNSTREAM_LIMITATION["status"],
                    "accepted_tickers": applied.get("applied_tickers") or [],
                },
            },
            artifacts={"apply": str(lane.lane_dir / ("generic_authoritative_apply" if applied.get("mode") == "GENERIC_AUTHORITATIVE_BATCH" else "phase13d_apply"))},
            recommended_next_action="Review copy-only evidence. A production run still requires a separate explicit authorization.",
        )
        result_dict = result.as_dict()
        from rawcandle.fundamentals.admin.ticker_reporting import enrich_after_state

        preview_reports = {
            str(report.get("ticker") or "").upper(): report
            for report in saved_plan.get("ticker_reporting") or ()
        }
        action_labels = {}
        for item in decisions:
            before = (preview_reports.get(item.normalized_value, {}).get("before") or {})
            if item.status == AdminStatus.APPLIED:
                label = "Tested successfully - existing ticker" if before.get("canonical_identity") else "Tested successfully - new ticker"
            elif item.status == AdminStatus.ALREADY_PRESENT:
                label = "Existing ticker - V2 analysis now available" if not before.get("v2_analysis") else "Tested successfully - existing ticker"
            elif item.status == AdminStatus.REVIEW_REQUIRED:
                label = "Review required"
            elif item.status == AdminStatus.REJECTED:
                label = "Rejected"
            else:
                label = item.status.value.replace("_", " ").title()
            action_labels[item.normalized_value] = label
        result_dict["ticker_reporting"] = enrich_after_state(
            saved_plan.get("ticker_reporting") or (),
            replace(
                lane.paths,
                analysis_db=Path(downstream["candidate_analysis_db"]),
            ) if downstream.get("candidate_analysis_db") else lane.paths,
            stage="COPY_ONLY_APPLY", final_actions=action_labels,
        )
        result_dict["copy_apply"] = {
            "phase13d_result": applied,
            "repeat_result": repeated,
            "before_inventory": before,
            "after_inventory": after,
            "copy_lane": str(lane.lane_dir),
        }
        writer.write_json("result.json", result_dict)
        writer.write_json("copy_apply_technical.json", result_dict["copy_apply"])
        writer.write_items_csv([item.as_dict() for item in decisions])
        writer.write_text("report.md", render_markdown_report(result_dict))
        progress.running(ProgressStage.FINAL_VALIDATION, "Writing final apply artifacts.")
        progress.completed(ProgressStage.FINAL_VALIDATION, "Final apply artifacts written.", processed_items=len(decisions), total_items=len(decisions))
        writer.checkpoint(RunStage.PARTIALLY_COMPLETED if result.outcome == AdminStatus.PARTIALLY_COMPLETED else RunStage.COMPLETED, message="Copy-only apply completed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True, counters=counts)
        writer.write_exit_code(1 if result.outcome == AdminStatus.PARTIALLY_COMPLETED else 0)
        writer.write_manifest()
        progress.running(ProgressStage.CLEANUP, "Cleaning copy lane." if not keep_copies else "Retaining copy lane by request.")
        cleanup = {"retained": str(lane.lane_dir)} if keep_copies else cleanup_copy_lane(lane)
        progress.completed(ProgressStage.CLEANUP, "Copy lane cleanup completed.", processed_items=int(cleanup.get("removed_count") or 0) if "removed_count" in cleanup else None)
        progress.running(ProgressStage.COMPLETED, "Copy-only apply completed.")
        progress.completed(ProgressStage.COMPLETED, "Copy-only apply completed.")
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup}
    except Exception as exc:
        writer.write_error(exc)
        if write_boundary_crossed:
            progress.rolling_back("Copy apply failed after write boundary; restoring copied databases.", errors=(f"{type(exc).__name__}: {exc}",))
            writer.checkpoint(RunStage.ROLLBACK_STARTED, message="Copy apply failed; restoring copy lane from fresh source backups.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            rollback = _restore_copy_lane_from_sources(source_paths, lane)
            progress.rolled_back("Copied databases restored after failure.")
            writer.checkpoint(RunStage.ROLLBACK_COMPLETE, message="Copy lane restored after failure.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            terminal_stage = RunStage.FAILED_AFTER_WRITE
            outcome = AdminStatus.ROLLED_BACK
        else:
            progress.failed(ProgressStage.SOURCE_RESOLUTION, "Copy apply failed before write boundary.", errors=(f"{type(exc).__name__}: {exc}",))
            rollback = {"status": "NOT_REQUIRED", "message": "Failure occurred before the copy write boundary."}
            terminal_stage = RunStage.FAILED_BEFORE_WRITE
            outcome = AdminStatus.FAILED
        error_decisions = tuple(
            AdminItemDecision(
                item_key=value,
                requested_value=value,
                normalized_value=value,
                status=AdminStatus.FAILED,
                reason=f"Copy apply failed and was rolled back: {type(exc).__name__}",
            )
            for value in request.normalized_inputs
        )
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.ADD_TICKERS,
            outcome=outcome,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            item_results=error_decisions,
            summary_counts=_counts(error_decisions),
            rollback=rollback,
            recommended_next_action="Inspect error.json and retry only after resolving the failure.",
            errors=({"type": type(exc).__name__, "message": str(exc)},),
        )
        result_dict = result.as_dict()
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result_dict))
        writer.checkpoint(terminal_stage, message="Copy-only apply failed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(3 if write_boundary_crossed else 2)
        writer.write_manifest()
        progress.running(ProgressStage.CLEANUP, "Cleaning failed copy lane." if not keep_copies else "Retaining failed copy lane by request.")
        cleanup = {"retained": str(lane.lane_dir)} if keep_copies else cleanup_copy_lane(lane)
        progress.completed(ProgressStage.CLEANUP, "Failed copy lane cleanup completed.", processed_items=int(cleanup.get("removed_count") or 0) if "removed_count" in cleanup else None)
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup, "error": type(exc).__name__}


def run_production_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    backup_root: Path | None = None,
    temp_root: Path = ADMIN_TEMP_ROOT,
    confirm_production: bool = False,
    failure_boundary: str | None = None,
    progress_callback: ProgressCallback | None = None,
    test_run_id: str | None = None,
) -> dict[str, Any]:
    if not confirm_production:
        raise PermissionError("PHASE13G2_PRODUCTION_APPLY_REQUIRES_CONFIRM_PRODUCTION")
    from rawcandle.fundamentals.admin.production_operations import ADD_TICKERS
    from rawcandle.fundamentals.admin.production_transaction import run_transaction

    return run_transaction(
        ADD_TICKERS, preview_payload_path=preview_payload_path, preview_fingerprint=preview_fingerprint,
        test_run_id=test_run_id or "", source_paths=source_paths, run_root=run_root,
        backup_root=backup_root, production_intent=True,
        progress_callback=progress_callback,
    )


def _restore_copy_lane_from_sources(source_paths: BatchAddTickerPaths, lane: CopyLane) -> dict[str, Any]:
    restored: dict[str, Any] = {"status": "ROLLED_BACK", "roles": {}}
    for role in ROLE_ORDER:
        destination = lane.paths.as_dict()[role]
        source = source_paths.as_dict()[role]
        online_backup(source, destination)
        restored["roles"][role] = database_fingerprint(destination)
    return restored


def _apply_decisions(
    decisions: Sequence[AdminItemDecision],
    applied: Mapping[str, Any],
    *,
    mode_label: str = "copy-lane",
) -> tuple[AdminItemDecision, ...]:
    applied_tickers = {str(ticker).upper() for ticker in applied.get("applied_tickers") or ()}
    outcome = str(applied.get("outcome") or "")
    output: list[AdminItemDecision] = []
    for item in decisions:
        if item.status == AdminStatus.ELIGIBLE and item.normalized_value in applied_tickers and outcome == "APPLIED":
            output.append(
                AdminItemDecision(
                    **{
                        **item.__dict__,
                        "status": AdminStatus.APPLIED,
                        "reason": f"Applied on {mode_label}.",
                        "applied_action": "PRODUCTION_ONBOARD_APPLIED" if mode_label == "production" else "COPY_ONBOARD_APPLIED",
                    }
                )
            )
        elif item.status == AdminStatus.ELIGIBLE and outcome == "NO_CHANGE":
            output.append(
                AdminItemDecision(
                    **{
                        **item.__dict__,
                        "status": AdminStatus.NO_CHANGE,
                        "reason": f"No {mode_label} change was required.",
                        "applied_action": "NO_CHANGE",
                    }
                )
            )
        else:
            output.append(item)
    return tuple(output)


def _counts(decisions: Sequence[AdminItemDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in decisions:
        key = item.status.value.lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def disk_hygiene_snapshot(path: Path = Path(".")) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {"path": str(path.resolve()), "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
