from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.operating_income_v2 import activation, diagnostic_flags_eight, phase10b
from rawcandle.fundamentals.operating_income_v2.persistence import physical_fingerprint, row_counts
from rawcandle.fundamentals.operating_income_v2.pipeline import refresh_active_package
from rawcandle.fundamentals.operating_income_v2.readers import ActiveModelRepository, ParallelModelRepository
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RELATIVE_VALUATION_MODEL
from rawcandle.fundamentals.relative_valuation.engine import calculate_relative_valuation
from rawcandle.fundamentals.relative_valuation.persistence import (
    RelativeValuationRepository,
    apply_snapshot,
    snapshot_identity,
    validate_snapshot,
)
from rawcandle.fundamentals.relative_valuation.source import ReadOnlySourcePaths, load_relative_valuation_source
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.ui_service import FundamentalsSnapshotUIService, resolve_report_download

from .phase12d import (
    PRODUCTION,
    REPORT_ROOT,
    ROOT,
    _file_state,
    _overlap_readiness,
    _provider_winners,
    _provenance_reconciliation,
    _ttm_chain_reconciliation,
    _validate_artifacts,
    build_candidate,
    canonical_logical_fingerprint,
    compare_production_inventory,
    copy_database,
    database_inventory,
    process_inventory,
    production_inventory,
    rebuild_ttm,
    reconcile_canonical,
    sha256,
    stable_hash,
    write_json,
)


EXPECTED = {
    "rebuild": "06521fcd073813e4bfa3605a15bcd9e2e4002a05dbb1e55ebe3444defe4eb741",
    "provider": "e98f1334d3fd7d7ce22e48a3858f487b17e414e705ab64f1baef922572d4f6f4",
    "canonical": "74cd17f19b253caa75e403dfe95a081f1af3b7d0c225715db88c9f169a3737bf",
    "ttm": "7b74ab52354f51b31a425eae36dbe84d9a1be9ca68ae469a6c1cf832421b9862",
    "package": activation.TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT,
    "package_economic": "3fdd93b6fedcdf7384728016c55fd955a2c44dfbc03c4618a758fd1601c84b27",
    "package_physical": "63fb7191889c22835ebef895dd1afbca455998345b7d4495a1382a9b747324fa",
    "endpoints": 87_319,
    "diagnostic_evaluations": 698_552,
    "new_history": 36_734,
    "revised_overlap": 395,
    "unchanged_overlap": 50_190,
    "readiness_changes": 6_383,
}
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase12e"
BACKUP_ROOT = ROOT / "backups"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"
PHASE12D_ROOT = ROOT / "temp/fundamentals_v4_phase12d/20260910T_PHASE12D_REHEARSAL_V7"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _report_inventory() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(REPORT_ROOT.rglob("*")) if path.is_file()
    }


def _pointer_state(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        active_package = None
        active_relative = []
        if "fundamentals_active_model_family" in tables:
            row = connection.execute("SELECT * FROM fundamentals_active_model_family WHERE singleton=1").fetchone()
            active_package = dict(row) if row else None
        if "relative_valuation_active_snapshot" in tables:
            active_relative = [dict(row) for row in connection.execute("SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint")]
    return {"active_package": active_package, "active_relative_valuation": active_relative}


def derive_relative_valuation_as_of(market_db: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{market_db.resolve()}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT pvm,COUNT(DISTINCT UPPER(osake)) AS companies "
            "FROM osakedata WHERE market='usa' AND open>0 AND high>0 AND low>0 AND close>0 "
            "GROUP BY pvm ORDER BY pvm DESC LIMIT 30"
        ).fetchall()
    if not rows:
        raise RuntimeError("PHASE12E_NO_VALID_US_MARKET_DATES")
    maximum = max(int(row[1]) for row in rows)
    threshold = max(1, int(maximum * 0.90))
    eligible = [str(row[0]) for row in rows if int(row[1]) >= threshold]
    if not eligible:
        raise RuntimeError("PHASE12E_NO_COMPLETE_US_MARKET_DATE")
    selected = max(eligible)
    return {
        "as_of_date": selected,
        "maximum_recent_company_count": maximum,
        "minimum_complete_company_count": threshold,
        "selected_company_count": next(int(row[1]) for row in rows if str(row[0]) == selected),
        "latest_observed_date": max(str(row[0]) for row in rows),
        "rule": "latest valid USA OHLC date with at least 90 percent of the maximum distinct-company count among the latest 30 observed dates",
    }


def _backup_pair(output: Path, stamp: str) -> dict[str, Any]:
    backup_dir = BACKUP_ROOT / f"fundamentals_v4_phase12e_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    result = {}
    for name in ("canonical", "analysis"):
        destination = backup_dir / f"{PRODUCTION[name].stem}.before_phase12e.db"
        manifest = copy_database(PRODUCTION[name], destination)
        manifest["inventory"] = database_inventory(destination)
        manifest["pointers"] = _pointer_state(destination)
        result[name] = manifest
    write_json(output / "backup_manifest.json", result)
    return result


def _restore_rehearsal(output: Path, backups: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    result = {}
    for name in ("canonical", "analysis"):
        source = Path(str(backups[name]["destination"]))
        restored = output / "rollback_rehearsal" / f"{name}.restored.db"
        copy_database(source, restored)
        source_inventory = database_inventory(source)
        restored_inventory = database_inventory(restored)
        keys = ("schema_fingerprint", "row_counts", "quick_check", "foreign_key_errors")
        equal = all(source_inventory[key] == restored_inventory[key] for key in keys)
        pointers_equal = _pointer_state(source) == _pointer_state(restored)
        if not equal or not pointers_equal:
            raise RuntimeError(f"PHASE12E_RESTORE_REHEARSAL_FAILED:{name}")
        result[name] = {"source": source_inventory, "restored": restored_inventory, "logical_equal": True, "pointers_equal": True}
    failure_paths = {
        "provider": PRODUCTION["provider"],
        "canonical": output / "rollback_rehearsal/canonical.failure_candidate.db",
        "analysis": output / "rollback_rehearsal/analysis.failure_candidate.db",
        "market": PRODUCTION["market"],
        "taxonomy": PRODUCTION["taxonomy"],
    }
    copy_database(Path(str(backups["canonical"]["destination"])), failure_paths["canonical"])
    copy_database(Path(str(backups["analysis"]["destination"])), failure_paths["analysis"])
    failure_result = build_candidate(
        failure_paths,
        applied_at="PHASE12E_ROLLBACK_REHEARSAL",
        run_failures=True,
    )
    if len(failure_result["failures"]) != 5 or not all(item["rollback_equal"] for item in failure_result["failures"]):
        raise RuntimeError("PHASE12E_FAILURE_INJECTION_REHEARSAL_FAILED")
    if failure_result["package"]["persistence_fingerprint"] != EXPECTED["package"]:
        raise RuntimeError("PHASE12E_FAILURE_REHEARSAL_PACKAGE_MISMATCH")
    with sqlite3.connect(failure_paths["analysis"]) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        activation.activate_package(connection, EXPECTED["package"], activated_at="ROLLBACK_REHEARSAL")
        connection.commit()
        stale_rejected = False
        try:
            activation.activate_package(
                connection,
                "0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30",
                activated_at="FORBIDDEN",
            )
        except RuntimeError as exc:
            stale_rejected = str(exc) == "OPERATING_INCOME_V2_ARCHIVED_MANIFEST_NOT_ACTIVATABLE"
        if not stale_rejected:
            raise RuntimeError("PHASE12E_STALE_ACTIVATION_NOT_REJECTED")
    result["stale_pointer_activation_rejected"] = True
    result["failure_injections"] = failure_result["failures"]
    write_json(output / "rollback_rehearsal.json", result)
    return result


def _restore_pair(backups: Mapping[str, Mapping[str, Any]], output: Path) -> dict[str, Any]:
    prepared = {}
    for name in ("canonical", "analysis"):
        source = Path(str(backups[name]["destination"]))
        restored = output / f"restore_{name}.verified.db"
        restored.parent.mkdir(parents=True, exist_ok=True)
        if restored.exists() or restored.is_symlink():
            raise FileExistsError(restored)
        shutil.copy2(source, restored)
        source_inventory = database_inventory(source)
        restored_inventory = database_inventory(restored)
        if (
            source_inventory["sha256"] != restored_inventory["sha256"]
            or source_inventory["schema_fingerprint"] != restored_inventory["schema_fingerprint"]
            or source_inventory["row_counts"] != restored_inventory["row_counts"]
            or _pointer_state(source) != _pointer_state(restored)
        ):
            raise RuntimeError(f"PHASE12E_PREPARED_RESTORE_VERIFICATION_FAILED:{name}")
        prepared[name] = restored
    for name in ("canonical", "analysis"):
        with sqlite3.connect(PRODUCTION[name]) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(PRODUCTION[name]) + suffix)
            sidecar.unlink(missing_ok=True)
    for name in ("canonical", "analysis"):
        os.replace(prepared[name], PRODUCTION[name])
    verified = {name: database_inventory(PRODUCTION[name]) for name in ("canonical", "analysis")}
    for name in ("canonical", "analysis"):
        expected = database_inventory(Path(str(backups[name]["destination"])))
        if (
            verified[name]["sha256"] != expected["sha256"]
            or verified[name]["schema_fingerprint"] != expected["schema_fingerprint"]
            or verified[name]["row_counts"] != expected["row_counts"]
            or verified[name]["quick_check"] != "ok"
            or verified[name]["foreign_key_errors"]
            or _pointer_state(PRODUCTION[name]) != _pointer_state(Path(str(backups[name]["destination"])))
        ):
            raise RuntimeError(f"PHASE12E_RESTORE_VERIFICATION_FAILED:{name}")
    return verified


class SidecarMonitor:
    def __init__(self) -> None:
        self.maximum = {f"{name}{suffix}": 0 for name in ("canonical", "analysis") for suffix in ("-wal", "-journal")}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            for name in ("canonical", "analysis"):
                for suffix in ("-wal", "-journal"):
                    path = Path(str(PRODUCTION[name]) + suffix)
                    if path.exists():
                        self.maximum[f"{name}{suffix}"] = max(self.maximum[f"{name}{suffix}"], path.stat().st_size)
            self._stop.wait(0.01)

    def __enter__(self) -> "SidecarMonitor":
        self._thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._stop.set()
        self._thread.join()


def _package_reconciliation(calculated: Mapping[str, Any], package_fingerprint: str) -> dict[str, Any]:
    with sqlite3.connect(f"file:{PRODUCTION['analysis'].resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        ParallelModelRepository(connection).assert_v2_bundle(
            phase10b.MODEL_MAP,
            persistence_fingerprint=package_fingerprint,
        )
        counts = row_counts(connection, diagnostic_model=diagnostic_flags_eight)
        duplicate_evaluations = int(connection.execute(
            "SELECT COUNT(*) FROM (SELECT e.endpoint_id,v.flag_id,COUNT(*) n FROM diagnostic_flag_endpoint e "
            "JOIN diagnostic_flag_evaluation v USING(endpoint_id) JOIN diagnostic_flag_package p USING(package_id) "
            "WHERE p.model_fingerprint=? GROUP BY e.endpoint_id,v.flag_id HAVING n<>1)",
            (diagnostic_flags_eight.MODEL_FINGERPRINT,),
        ).fetchone()[0])
        orphan_evaluations = int(connection.execute(
            "SELECT COUNT(*) FROM diagnostic_flag_evaluation v LEFT JOIN diagnostic_flag_endpoint e USING(endpoint_id) "
            "WHERE e.endpoint_id IS NULL"
        ).fetchone()[0])
        package = ParallelModelRepository(connection).package_manifest(package_fingerprint)
    expected_counts = {
        "score": EXPECTED["endpoints"], "score_component": EXPECTED["endpoints"] * 7,
        "lifecycle": EXPECTED["endpoints"], "valuation": EXPECTED["endpoints"],
        "delta": EXPECTED["endpoints"], "delta_component": EXPECTED["endpoints"] * 7,
        "diagnostic_endpoint": EXPECTED["endpoints"],
        "diagnostic_evaluation": EXPECTED["diagnostic_evaluations"],
    }
    mismatches = {key: {"actual": counts[key], "expected": value} for key, value in expected_counts.items() if counts[key] != value}
    if mismatches or duplicate_evaluations or orphan_evaluations:
        raise RuntimeError(f"PHASE12E_PACKAGE_RECONCILIATION_FAILED:{mismatches}")
    if package["economic_result_fingerprint"] != EXPECTED["package_economic"] or package["physical_content_fingerprint"] != EXPECTED["package_physical"]:
        raise RuntimeError("PHASE12E_PACKAGE_FINGERPRINT_MISMATCH")
    with sqlite3.connect(f"file:{PRODUCTION['analysis'].resolve()}?mode=ro", uri=True) as connection:
        if physical_fingerprint(connection, diagnostic_model=diagnostic_flags_eight) != EXPECTED["package_physical"]:
            raise RuntimeError("PHASE12E_CURRENT_PHYSICAL_FINGERPRINT_MISMATCH")
    ticker_counts = Counter(str(row.get("ticker")) for row in calculated["rows"])
    if ticker_counts["BTAI"] != 21 or ticker_counts["HLX"] != 21:
        raise RuntimeError("PHASE12E_REFERENCE_HISTORY_NOT_PRESERVED")
    return {"counts": counts, "expected": expected_counts, "duplicates": duplicate_evaluations, "orphans": orphan_evaluations, "package": package, "BTAI": ticker_counts["BTAI"], "HLX": ticker_counts["HLX"]}


def _relative_refresh(as_of_date: str, applied_at: str) -> dict[str, Any]:
    source = load_relative_valuation_source(
        ReadOnlySourcePaths(PRODUCTION["analysis"], PRODUCTION["canonical"], PRODUCTION["market"], PRODUCTION["taxonomy"]),
        as_of_date=as_of_date,
    )
    snapshot = calculate_relative_valuation(
        source.inputs,
        as_of_date=as_of_date,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    content, physical = validate_snapshot(snapshot, source.inputs)
    identity = snapshot_identity(snapshot, physical)
    with sqlite3.connect(PRODUCTION["analysis"]) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        report = apply_snapshot(connection, snapshot, source.inputs, applied_at_utc=applied_at)
        metadata = RelativeValuationRepository(connection).active_metadata(model_fingerprint=RELATIVE_VALUATION_MODEL)
    statuses = {
        "peer": dict(Counter(str(row["status"]) for row in content["peers"])),
        "own_history": dict(Counter(str(row["status"]) for row in content["own_history"])),
    }
    cohorts = {
        "current_fresh": sum(bool(row["current_fresh"]) for row in content["companies"]),
        "current_peer_eligible": sum(
            row["scope"] == "UNIVERSE"
            and row["status"] in {"RELATIVE_POSITION_READY", "PEER_GROUP_TOO_SMALL"}
            for row in content["peers"]
        ),
        "own_history_ready_current_fresh": sum(
            bool(company["current_fresh"]) and own["status"] == "READY"
            for company, own in zip(content["companies"], content["own_history"])
        ),
        "own_history_limited_current_fresh": sum(
            bool(company["current_fresh"]) and own["status"] == "LIMITED_HISTORY"
            for company, own in zip(content["companies"], content["own_history"])
        ),
    }
    metadata_counts = {
        "current_fresh": int(metadata["current_fresh_count"]),
        "current_peer_eligible": int(metadata["current_peer_eligible_count"]),
        "own_history_ready_current_fresh": int(metadata["own_history_ready_count"]),
        "own_history_limited_current_fresh": int(metadata["own_history_limited_count"]),
    }
    if cohorts != metadata_counts:
        raise RuntimeError("PHASE12E_RELATIVE_VALUATION_METADATA_RECONCILIATION_FAILED")
    return {
        "apply": asdict(report), "as_of_date": as_of_date,
        "source_fingerprint": snapshot.source_fingerprint,
        "result_fingerprint": snapshot.result_fingerprint,
        "physical_content_fingerprint": physical, "snapshot_id": identity,
        "active_metadata": metadata, "company_rows": len(content["companies"]),
        "peer_rows": len(content["peers"]), "own_history_rows": len(content["own_history"]),
        "component_history_rows": len(content["components"]), "status_distributions": statuses,
        "cohorts": cohorts,
        "four_peer_rows_per_company": len(content["peers"]) == 4 * len(content["companies"]),
        "three_component_rows_per_company": len(content["components"]) == 3 * len(content["companies"]),
    }


def _snapshot_smoke(output: Path, report_date: str) -> dict[str, Any]:
    paths = SnapshotPaths(PRODUCTION["canonical"], PRODUCTION["analysis"], PRODUCTION["market"], PRODUCTION["taxonomy"], PRODUCTION["provider"])
    report_dir = output / "snapshot_smoke"
    results = []
    for ticker in ("NVDA", "AMZN", "CRMD", "APD", "BTAI", "HLX"):
        first = generate_active_company_snapshot(paths, ticker=ticker, report_date=report_date, output_dir=report_dir)
        second = generate_active_company_snapshot(paths, ticker=ticker, report_date=report_date, output_dir=report_dir)
        markdown = Path(first["output_path"]).read_text(encoding="utf-8")
        diagnostic_rows = len((first["snapshot"].get("diagnostic") or {}).get("evaluations", []))
        if second["status"] != "NO_CHANGE" or diagnostic_rows != 8 or "company_id" in markdown or "snapshot_id" in markdown:
            raise RuntimeError(f"PHASE12E_SNAPSHOT_SMOKE_FAILED:{ticker}")
        results.append({"ticker": ticker, "first": first["status"], "second": second["status"], "sha256": sha256(Path(first["output_path"])), "diagnostic_rows": diagnostic_rows})
    service_dir = output / "ui_smoke"
    service = FundamentalsSnapshotUIService(paths=paths, output_dir=service_dir)
    batch = service.generate_batch(ticker_input="NVDA, ZZZZZPHASE12E", report_date_input=report_date)
    generated = next(item for item in batch.results if item.ticker == "NVDA")
    download = resolve_report_download(generated.filename, service_dir)
    rejected = False
    try:
        resolve_report_download("../fundamentals_analysis.db", service_dir)
    except (ValueError, FileNotFoundError):
        rejected = True
    if batch.summary.created != 1 or batch.summary.not_generated != 1 or not rejected:
        raise RuntimeError("PHASE12E_UI_SMOKE_FAILED")
    return {"reports": results, "batch_status": batch.status, "download_sha256": sha256(download), "traversal_rejected": rejected}


def run(output: Path, *, apply: bool, confirm_production: bool) -> dict[str, Any]:
    output = output.resolve()
    if ARTIFACT_ROOT.resolve() not in output.parents or output.exists():
        raise PermissionError("PHASE12E_NEW_ARTIFACT_PATH_REQUIRED")
    if apply and not confirm_production:
        raise PermissionError("PHASE12E_PRODUCTION_CONFIRMATION_REQUIRED")
    if _git("status", "--porcelain"):
        raise RuntimeError("PHASE12E_CLEAN_WORKTREE_REQUIRED")
    if (ROOT / ".git/rebase-merge").exists() or (ROOT / ".git/rebase-apply").exists() or (ROOT / ".git/MERGE_HEAD").exists():
        raise RuntimeError("PHASE12E_INTERRUPTED_GIT_OPERATION")
    output.mkdir(parents=True)
    started = time.perf_counter()
    processes = process_inventory()
    write_json(output / "process_inventory.json", processes)
    if processes["conflicting_writers"]:
        raise RuntimeError("PHASE12E_CONFLICTING_WRITER")
    phase12d_fingerprints = json.loads((PHASE12D_ROOT / "fingerprints.json").read_text(encoding="utf-8"))
    for key in ("rebuild", "canonical", "ttm"):
        artifact_key = "rebuild_contract" if key == "rebuild" else key
        if phase12d_fingerprints[artifact_key] != EXPECTED[key]:
            raise RuntimeError(f"PHASE12E_PHASE12D_IDENTITY_MISMATCH:{key}")
    provider_rows, provider = _provider_winners(PRODUCTION["provider"])
    del provider_rows
    if provider["source_fingerprint"] != EXPECTED["provider"] or provider["winner_rows"] != EXPECTED["endpoints"]:
        raise RuntimeError("PHASE12E_PROVIDER_SOURCE_DRIFT")
    free = shutil.disk_usage(ROOT).free
    backup_bytes = PRODUCTION["canonical"].stat().st_size + PRODUCTION["analysis"].stat().st_size
    estimated_growth = sum((PHASE12D_ROOT / f"candidate_a/{name}").stat().st_size - PRODUCTION[key].stat().st_size for name, key in (("fundamentals_v4.db", "canonical"), ("fundamentals_analysis.db", "analysis")))
    required = int((backup_bytes * 2 + max(estimated_growth, 0) + 2 * 1024**3) * 1.25)
    if free < required:
        raise RuntimeError(f"PHASE12E_DISK_GATE_FAILED:{free}:{required}")
    as_of = derive_relative_valuation_as_of(PRODUCTION["market"])
    preflight = production_inventory()
    reports_before = _report_inventory()
    write_json(output / "preflight.json", {"git_head": _git("rev-parse", "HEAD"), "branch": _git("branch", "--show-current"), "production": preflight, "provider": provider, "disk": {"free_bytes": free, "required_bytes": required, "backup_bytes": backup_bytes, "estimated_growth_bytes": estimated_growth}, "relative_valuation_as_of": as_of})
    if not apply:
        return {"outcome": "DRY_RUN", "output": str(output), "as_of_date": as_of["as_of_date"]}

    lock_handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_handle.close()
        raise RuntimeError("PHASE12E_MAINTENANCE_LOCK_HELD") from exc
    backups: dict[str, Any] | None = None
    try:
        locked_processes = process_inventory()
        write_json(output / "locked_process_inventory.json", locked_processes)
        if locked_processes["conflicting_writers"]:
            raise RuntimeError("PHASE12E_CONFLICTING_WRITER_AFTER_LOCK")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backups = _backup_pair(output, stamp)
        rollback = _restore_rehearsal(output, backups)
        write_json(output / "rollback_policy.json", {"activation_only_rollback": False, "pair_restore_required": True, "verified": bool(rollback)})
        applied_at = utc_now()
        with SidecarMonitor() as monitor:
            canonical = reconcile_canonical(PRODUCTION["provider"], PRODUCTION["canonical"], applied_at=applied_at)
            ttm = rebuild_ttm(PRODUCTION["canonical"], applied_at=applied_at)
            calculated = phase10b.calculate(PRODUCTION, verify_v1_overlap=False)
            package_fingerprint = stable_hash({
                "rebuild_fingerprint": EXPECTED["rebuild"],
                "parent_persistence_fingerprint": phase10b.PACKAGE_FINGERPRINT,
                "provider_source_fingerprint": canonical["source_fingerprint"],
                "canonical_fingerprint": canonical["canonical_fingerprint"],
                "ttm_fingerprint": ttm["fingerprint"],
                "model_map": phase10b.MODEL_MAP,
            })
            if package_fingerprint != EXPECTED["package"]:
                raise RuntimeError("PHASE12E_PACKAGE_IDENTITY_MISMATCH")
            with sqlite3.connect(PRODUCTION["analysis"]) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                previous_package = activation.assert_v2_active(connection).persistence_fingerprint
                package_apply = phase10b.apply_candidate_package(connection, calculated, applied_at=applied_at, persistence_fingerprint=package_fingerprint)
            package_reconciliation = _package_reconciliation(calculated, package_fingerprint)
            readiness = _overlap_readiness(Path(str(backups["canonical"]["destination"])), PRODUCTION["canonical"])
            provenance = _provenance_reconciliation(PRODUCTION["canonical"])
            ttm_chains = _ttm_chain_reconciliation(PRODUCTION["canonical"])
            if canonical.get("NEW_HISTORY", 0) != EXPECTED["new_history"] or canonical.get("REVISED_OVERLAP", 0) != EXPECTED["revised_overlap"] or canonical.get("UNCHANGED_OVERLAP", 0) != EXPECTED["unchanged_overlap"] or canonical["canonical_fingerprint"] != EXPECTED["canonical"] or ttm["fingerprint"] != EXPECTED["ttm"] or readiness["readiness_changed"] != EXPECTED["readiness_changes"] or not provenance["passed"] or not ttm_chains["passed"]:
                raise RuntimeError("PHASE12E_REHEARSAL_RECONCILIATION_MISMATCH")
            with sqlite3.connect(PRODUCTION["analysis"]) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                active = activation.activate_package(connection, package_fingerprint, activated_at=applied_at)
                connection.commit()
            relative_first = _relative_refresh(as_of["as_of_date"], applied_at)
            before_no_change = {name: _file_state(PRODUCTION[name]) for name in ("canonical", "analysis")}
            canonical_no_change = reconcile_canonical(PRODUCTION["provider"], PRODUCTION["canonical"], applied_at=applied_at)
            ttm_no_change = rebuild_ttm(PRODUCTION["canonical"], applied_at=applied_at)
            calculated_again = phase10b.calculate(PRODUCTION, verify_v1_overlap=False)
            with sqlite3.connect(PRODUCTION["analysis"]) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                package_no_change = phase10b.apply_candidate_package(connection, calculated_again, applied_at=applied_at, persistence_fingerprint=package_fingerprint)
            relative_no_change = _relative_refresh(as_of["as_of_date"], applied_at)
            after_no_change = {name: _file_state(PRODUCTION[name]) for name in ("canonical", "analysis")}
            no_change_ok = canonical_no_change.get("NEW_HISTORY", 0) == 0 and canonical_no_change.get("REVISED_OVERLAP", 0) == 0 and ttm_no_change["outcome"] == "NO_CHANGE" and package_no_change.outcome == "NO_CHANGE" and relative_no_change["apply"]["outcome"] == "NO_CHANGE" and before_no_change == after_no_change
            if not no_change_ok:
                raise RuntimeError("PHASE12E_SECOND_APPLY_NOT_PHYSICAL_NO_CHANGE")
            pipeline = refresh_active_package(PRODUCTION)
            if pipeline["outcome"] != "NO_CHANGE" or pipeline["logical_changes"]:
                raise RuntimeError("PHASE12E_PIPELINE_NOT_NO_CHANGE")
        journal = {"sampling_interval_seconds": 0.01, "measured_peak_bytes": monitor.maximum, "maximum_any_bytes": max(monitor.maximum.values())}
        snapshots = _snapshot_smoke(output, as_of["as_of_date"])
        postflight = production_inventory()
        if _report_inventory() != reports_before:
            raise RuntimeError("PHASE12E_PRODUCTION_REPORTS_CHANGED")
        for name in ("provider", "market", "taxonomy"):
            before = preflight["databases"][name]
            after = postflight["databases"][name]
            if before["sha256"] != after["sha256"] or before["row_counts"] != after["row_counts"]:
                raise RuntimeError(f"PHASE12E_PROTECTED_DATABASE_CHANGED:{name}")
        for name in ("canonical", "analysis"):
            if postflight["databases"][name]["quick_check"] != "ok" or postflight["databases"][name]["foreign_key_errors"]:
                raise RuntimeError(f"PHASE12E_POSTFLIGHT_INTEGRITY_FAILED:{name}")
            if any(postflight["databases"][name][sidecar]["exists"] for sidecar in ("wal", "shm", "journal")):
                raise RuntimeError(f"PHASE12E_POSTFLIGHT_SIDECAR_REMAINS:{name}")
        result = {
            "outcome": "PHASE 12E COMPLETE - TEN-YEAR OPERATIONAL HISTORY ACTIVE AND STABLE",
            "previous_package": previous_package, "active_package": asdict(active),
            "canonical": canonical, "ttm": ttm, "package_apply": asdict(package_apply),
            "package_reconciliation": package_reconciliation, "readiness": readiness,
            "provenance": provenance, "ttm_chains": ttm_chains,
            "relative_valuation_first": relative_first, "relative_valuation_second": relative_no_change,
            "second_apply": {"passed": True, "canonical": canonical_no_change, "ttm": ttm_no_change, "package": asdict(package_no_change), "physical_state_equal": True},
            "pipeline_smoke": pipeline, "snapshot_ui_smoke": snapshots, "journal": journal,
            "backups": backups, "production_preflight_fingerprint": stable_hash(preflight),
            "production_postflight": postflight, "reports_unchanged": True,
            "duration_seconds": time.perf_counter() - started,
        }
        write_json(output / "deployment_result.json", result)
        write_json(output / "production_postflight.json", postflight)
        write_json(output / "journal_peak.json", journal)
        write_json(output / "second_no_change.json", result["second_apply"])
        write_json(output / "relative_valuation_refresh.json", relative_first)
        write_json(output / "snapshot_ui_smoke.json", snapshots)
        (output / "commands_run.txt").write_text("python3 -m rawcandle.cli.run_phase12e_ten_year_production --output <phase12e-temp-dir> --apply --confirm-production\n", encoding="utf-8")
        _validate_artifacts(output)
        return result
    except Exception:
        if backups is not None:
            restored = _restore_pair(backups, output)
            write_json(output / "failure_full_pair_restore.json", restored)
        raise
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()
