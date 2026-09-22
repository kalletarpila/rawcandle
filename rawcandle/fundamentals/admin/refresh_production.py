"""Guarded three-database Production publication for Refresh Fundamentals."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sqlite3
import threading
from contextlib import ExitStack, contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths, _assert_clean_worktree
from rawcandle.fundamentals.admin.contracts import AdminOperationType, RunStage, utc_now
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.production_transaction import BACKUP_ROOT, ADMIN_LOCK, production_lock
from rawcandle.fundamentals.admin.publication_journal import (
    ACTIVE_JOURNAL_PATH,
    PUBLICATION_ROLES,
    PublicationRecoveryError,
    PublicationRecoveredRetryRequired,
    fsync_directory,
    fsync_file,
    prepare_journal,
    guard_production_writes,
    restore_old_generation,
    sha256_file,
    sqlite_verification,
    update_journal,
    INCOMPLETE_STATES,
)
from rawcandle.fundamentals.admin.refresh_copy_runtime import (
    REPLACEMENT_CLASSES,
    _analysis_state,
    _identity_mapping,
    fresh_rebuild_canonical,
    prepare_compact_read_only_sources,
    replace_provider_histories,
    revalidate_bound_source,
    validate_provider_candidate,
)
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    CONTRACT_VERSION,
    _production_file_state,
    _request,
    _summary_counts,
    ensure_refresh_state_schema,
)
from rawcandle.fundamentals.admin.source_bundle import (
    ReadOnlySourceMode,
    SOURCE_CONTRACT_VERSION,
    TaxonomySourceMode,
)
from rawcandle.fundamentals.operating_income_v2.full_rebuild import validate_rebuild
from rawcandle.fundamentals.phase12d import PRODUCTION
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.fundamentals.providers.sharadar import SharadarClient


PRODUCTION_CONTRACT_VERSION = "PHASE13G3_28_REFRESH_PRODUCTION_COMPACT_SOURCE_V2"
PRODUCTION_STAGES = (
    "PRODUCTION_PREFLIGHT", "SOURCE_REVALIDATION", "PROVIDER_CANDIDATE",
    "CANONICAL_CANDIDATE", "ANALYSIS_CANDIDATE", "CANDIDATE_VALIDATION",
    "FINAL_SOURCE_RECHECK", "BACKUP", "JOURNAL_PREPARE", "PUBLISH_PROVIDER",
    "PUBLISH_CANONICAL", "PUBLISH_ANALYSIS", "POSTFLIGHT", "JOURNAL_COMMIT",
    "CLEANUP", "COMPLETED",
)


class StaleRefreshTest(RuntimeError):
    pass


class SimulatedPublicationCrash(BaseException):
    """Fault-injection exception that intentionally bypasses ordinary rollback."""


class RefreshPostflightValidationError(RuntimeError):
    """A required Refresh analysis lineage contract is absent or inconsistent."""


@contextmanager
def _durable_heartbeat(writer: AdminRunWriter, stage: str, message: str):
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(30.0):
            writer.append_jsonl("progress_events.jsonl", {
                "current_stage_id": stage, "stage_state": "RUNNING", "message": message,
            })

    thread = threading.Thread(target=beat, name="refresh-production-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=30.0)


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"REFRESH_EVIDENCE_PATH_INVALID:{path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"REFRESH_EVIDENCE_INVALID:{path.name}")
    return value


def load_production_authorization(
    *, preview_payload_path: Path, preview_fingerprint: str, test_run_id: str,
    run_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = run_root.resolve()
    preview_path = preview_payload_path.resolve(strict=True)
    if preview_payload_path.is_symlink() or preview_path.name != "refresh_preview.json" or root not in preview_path.parents:
        raise ValueError("REFRESH_PRODUCTION_PREVIEW_PATH_INVALID")
    preview = _load_json(preview_path)
    if (
        preview.get("contract_version") != CONTRACT_VERSION
        or preview.get("refresh_set_fingerprint") != preview_fingerprint
        or not preview.get("future_test_authorized")
        or preview.get("discovery", {}).get("status") != "COMPLETE"
    ):
        raise ValueError("REFRESH_PRODUCTION_PREVIEW_BINDING_MISMATCH")
    changes = preview.get("ticker_changes") or []
    if not any(item.get("classification") in REPLACEMENT_CLASSES for item in changes):
        raise ValueError("REFRESH_PRODUCTION_NO_EFFECTIVE_CHANGE")
    if any(item.get("classification") == "REVIEW_REQUIRED" for item in changes):
        raise ValueError("REFRESH_PRODUCTION_REVIEW_REQUIRED")
    if not test_run_id or Path(test_run_id).name != test_run_id or ".." in test_run_id:
        raise ValueError("REFRESH_PRODUCTION_TEST_RUN_ID_REQUIRED")
    test_dir = (root / test_run_id).resolve()
    if root not in test_dir.parents or test_dir.name != test_run_id:
        raise ValueError("REFRESH_PRODUCTION_TEST_PATH_INVALID")
    test = _load_json(test_dir / "result.json")
    downstream = test.get("downstream") or {}
    analysis = downstream.get("analysis") or {}
    canonical = downstream.get("canonical") or {}
    bootstrap = canonical.get("publication_date_bootstrap") or {}
    expected_preview_run = preview_path.parent.name
    valid = (
        test.get("operation_type") == AdminOperationType.REFRESH_FUNDAMENTALS.value
        and test.get("mode") == "COPY_ONLY_APPLY"
        and test.get("outcome") == "COMPLETED"
        and test.get("preview_fingerprint") == preview_fingerprint
        and test.get("bound_preview_run_id") == expected_preview_run
        and test.get("production_file_state_unchanged") is True
        and analysis.get("status") == "READY"
        and (analysis.get("invocation_counts") or {}).get("full_v2_rebuild") == 1
        and canonical.get("identity_contract", {}).get("company_security_identity_mapping_unchanged") is True
        and bootstrap.get("repair_required") == 0
    )
    if not valid:
        raise ValueError("REFRESH_PRODUCTION_MATCHING_SUCCESSFUL_TEST_REQUIRED")
    source_revalidation = _load_json(test_dir / "source_revalidation.json")
    if source_revalidation.get("refresh_set_fingerprint") != preview_fingerprint:
        raise ValueError("REFRESH_PRODUCTION_TEST_REFRESH_SET_MISMATCH")
    if source_revalidation.get("schema", {}).get("schema_fingerprint") != preview.get("schema", {}).get("schema_fingerprint"):
        raise ValueError("REFRESH_PRODUCTION_TEST_SCHEMA_MISMATCH")
    source_binding_path = test_dir / "read_only_source_binding.json"
    source_binding = _load_json(source_binding_path)
    if source_binding != downstream.get("read_only_source_binding"):
        raise ValueError("REFRESH_PRODUCTION_TEST_SOURCE_BINDING_EVIDENCE_MISMATCH")
    test_semantic_binding = _semantic_source_binding(source_binding)
    if (
        test_semantic_binding["market"]["mode"] != ReadOnlySourceMode.STABLE_SOURCE_BUNDLE.value
        or test_semantic_binding["market"]["source_contract_version"] != SOURCE_CONTRACT_VERSION
        or test_semantic_binding["taxonomy"]["mode"] != TaxonomySourceMode.FULL_SQLITE_BACKUP.value
    ):
        raise ValueError("REFRESH_PRODUCTION_TEST_SOURCE_BINDING_POLICY_UNSUPPORTED")
    test["_authorized_source_binding"] = source_binding
    test["_authorized_source_binding_path"] = str(source_binding_path)
    return preview, test


def _semantic_source_binding(evidence: Mapping[str, Any]) -> dict[str, Any]:
    market_evidence = evidence.get("market")
    taxonomy_evidence = evidence.get("taxonomy")
    if not isinstance(market_evidence, Mapping) or not isinstance(taxonomy_evidence, Mapping):
        raise ValueError("REFRESH_SOURCE_BINDING_MALFORMED")
    manifest = market_evidence.get("bundle_manifest")
    taxonomy = taxonomy_evidence.get("binding")
    if not isinstance(manifest, Mapping) or not isinstance(taxonomy, Mapping):
        raise ValueError("REFRESH_SOURCE_BINDING_MALFORMED")
    market = manifest.get("market")
    canonical = manifest.get("canonical_binding")
    coverage = market.get("valuation_coverage") if isinstance(market, Mapping) else None
    if not all(isinstance(value, Mapping) for value in (market, canonical, coverage)):
        raise ValueError("REFRESH_SOURCE_BINDING_MALFORMED")
    required = (
        manifest.get("source_contract_version"), manifest.get("as_of_date"),
        market.get("semantic_fingerprint"), canonical.get("semantic_fingerprint"),
        taxonomy.get("version"), taxonomy.get("semantic_fingerprint"),
    )
    if any(not str(value or "") for value in required):
        raise ValueError("REFRESH_SOURCE_BINDING_MALFORMED")
    return {
        "market": {
            "mode": market_evidence.get("mode"),
            "source_contract_version": manifest.get("source_contract_version"),
            "as_of_date": manifest.get("as_of_date"),
            "semantic_fingerprint": market.get("semantic_fingerprint"),
            "schema_fingerprint": market.get("schema_fingerprint"),
            "row_counts": market.get("row_counts"),
            "canonical_binding": {
                key: canonical.get(key)
                for key in (
                    "semantic_fingerprint", "valuation_requirement_count",
                    "recent_ticker_count", "validation_sample_ticker",
                )
            },
            "valuation_coverage": {
                "requirements": coverage.get("requirements"),
                "status_counts": coverage.get("status_counts"),
                "status_identity_fingerprints": coverage.get("status_identity_fingerprints"),
            },
        },
        "taxonomy": {
            "mode": taxonomy_evidence.get("mode"),
            "domain": taxonomy.get("domain"),
            "version": taxonomy.get("version"),
            "semantic_fingerprint": taxonomy.get("semantic_fingerprint"),
            "membership_rows": taxonomy.get("membership_rows"),
        },
    }


def compare_test_and_production_source_bindings(
    test_evidence: Mapping[str, Any], production_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    tested = _semantic_source_binding(test_evidence)
    production = _semantic_source_binding(production_evidence)
    differences = [
        section for section in ("market", "taxonomy")
        if tested[section] != production[section]
    ]
    return {
        "status": "MATCH" if not differences else "STALE",
        "differing_contract_sections": differences,
        "test": tested,
        "production": production,
    }


def run_refresh_production_full_v2_downstream(
    *, provider_candidate: Path, canonical_candidate: Path,
    read_only_sources: Mapping[str, Path], lane_dir: Path, as_of_date: str,
) -> dict[str, Any]:
    candidate_paths = BatchAddTickerPaths(
        provider_candidate,
        canonical_candidate,
        lane_dir / "unused.db",
        read_only_sources["market"],
        read_only_sources["taxonomy"],
    )
    return run_full_v2_downstream(
        candidate_paths.as_dict(),
        output=lane_dir / "analysis_rebuild",
        as_of_date=as_of_date,
    )


def _provider_semantic_fingerprint(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        for row in connection.execute(
            "SELECT po.provider,po.native_table,po.provider_record_key,po.company_id,po.security_id,po.content_hash,po.provenance_json,"
            "s.ticker,s.dimension,s.date,s.reportperiod,s.lastupdated "
            "FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id) "
            "WHERE po.provider='SHARADAR' AND po.native_table='fundamentals' "
            "ORDER BY po.provider_record_key,po.content_hash,po.observation_id"
        ):
            digest.update(json.dumps(tuple(row), separators=(",", ":"), default=str).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def _publish_refresh_state(
    provider_candidate: Path, *, source_watermark: str, schema_fingerprint: str,
    run_id: str, completed_at: str,
) -> dict[str, Any]:
    provider_fingerprint = _provider_semantic_fingerprint(provider_candidate)
    with sqlite3.connect(provider_candidate) as connection:
        ensure_refresh_state_schema(connection)
        connection.execute("DELETE FROM sharadar_refresh_state")
        connection.execute(
            "INSERT INTO sharadar_refresh_state(singleton_id,source_dataset,source_table,published_source_watermark,"
            "provider_semantic_fingerprint,source_schema_fingerprint,successful_run_id,completed_at_utc) "
            "VALUES(1,'SHARADAR','fundamentals',?,?,?,?,?)",
            (source_watermark, provider_fingerprint, schema_fingerprint, run_id, completed_at),
        )
        connection.commit()
    return {
        "mode": "ESTABLISHED_PUBLISHED_STATE",
        "published_source_watermark": source_watermark,
        "provider_semantic_fingerprint": provider_fingerprint,
        "source_schema_fingerprint": schema_fingerprint,
        "successful_run_id": run_id,
        "completed_at_utc": completed_at,
        "next_query_overlap_days": 3,
    }


def _storage_preflight(paths: BatchAddTickerPaths, *, temp_root: Path, backup_root: Path) -> dict[str, Any]:
    temp_root.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    sizes = {role: path.stat().st_size for role, path in paths.as_dict().items()}
    publication_total = sum(sizes[role] for role in PUBLICATION_ROLES)
    read_only_total = sizes["taxonomy"]
    # Publication candidates/backups and rebuild scratch, plus the taxonomy
    # snapshot. Compact market size is measured after construction.
    requirements: dict[int, dict[str, Any]] = {}
    location_requirements = (
        (temp_root, int(publication_total * 1.75) + read_only_total),
        (backup_root, int(publication_total * 1.25)),
    )
    for location, location_required in location_requirements:
        device = location.stat().st_dev
        item = requirements.setdefault(device, {"paths": [], "required_bytes": 0})
        item["paths"].append(str(location.resolve()))
        item["required_bytes"] += max(location_required, 64 * 1024 * 1024)
    for item in requirements.values():
        item["available_bytes"] = shutil.disk_usage(item["paths"][0]).free
        if item["available_bytes"] < item["required_bytes"]:
            raise RuntimeError("REFRESH_PRODUCTION_INSUFFICIENT_STORAGE")
    return {
        "source_sizes": sizes,
        "required_read_only_copy_roles": ["taxonomy"],
        "compact_market_bundle_built_during_candidate_preparation": True,
        "filesystems": {str(device): item for device, item in requirements.items()},
    }


def _cleanup_candidate_lane(lane_dir: Path, journal: Mapping[str, Any] | None) -> dict[str, Any]:
    state = str((journal or {}).get("state") or "NOT_PREPARED")
    if journal is not None and state in INCOMPLETE_STATES:
        return {
            "status": "RETAINED_FOR_RECOVERY", "journal_state": state,
            "path": str(lane_dir.resolve()), "removed": False,
        }
    files = []
    removed_file_count = 0
    removed_bytes = 0
    if lane_dir.exists():
        for path in lane_dir.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            size = path.stat().st_size
            removed_file_count += 1
            removed_bytes += size
            if size >= 1024 * 1024 or path.suffix in {".db", ".db-wal", ".db-shm"}:
                files.append({"path": str(path.resolve()), "size": size})
        shutil.rmtree(lane_dir)
    return {
        "status": "COMPLETED", "journal_state": state,
        "path": str(lane_dir.resolve()), "removed": True,
        "removed_file_count": removed_file_count,
        "removed_bytes": removed_bytes,
        "remaining_phase_owned_files": 0 if not lane_dir.exists() else len(list(lane_dir.rglob("*"))),
        "files": files,
    }


def _verified_backups(paths: BatchAddTickerPaths, backup_dir: Path) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    fsync_directory(backup_dir.parent)
    result: dict[str, Any] = {}
    for role in PUBLICATION_ROLES:
        source = paths.as_dict()[role]
        backup = backup_dir / f"{role}.db"
        online_backup(source, backup)
        fsync_file(backup)
        fsync_directory(backup_dir)
        verified = sqlite_verification(backup)
        source_sha = sha256_file(source)
        result[role] = {
            "role": role, "source": str(source.resolve()), "backup": str(backup.resolve()),
            "verification": verified, "source_sha256": source_sha,
            "snapshot_method": "SQLITE_ONLINE_BACKUP",
        }
    return result


def _candidate_manifest(paths: Mapping[str, Path], backups: Mapping[str, Any]) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    for role in PUBLICATION_ROLES:
        candidate = paths[role]
        verification = sqlite_verification(candidate)
        target = Path(backups[role]["source"])
        if candidate.stat().st_dev != target.stat().st_dev:
            raise RuntimeError(f"REFRESH_CANDIDATE_CROSS_FILESYSTEM:{role}")
        roles[role] = {
            "production_path": str(target),
            "old_production_fingerprint": backups[role]["source_sha256"],
            "backup_path": backups[role]["backup"],
            "verified_backup_fingerprint": backups[role]["verification"]["sha256"],
            "candidate_path": str(candidate.resolve()),
            "candidate_fingerprint": verification["sha256"],
            "replacement_state": "NOT_STARTED",
        }
    return roles


def _replace_role(
    role: str, journal: Mapping[str, Any], *, journal_path: Path,
) -> dict[str, Any]:
    roles = dict(journal["roles"])
    record = dict(roles[role])
    intended = update_journal(
        journal_path, journal, state="PUBLISHING",
        current_publication_step=f"REPLACING_{role.upper()}",
    )
    candidate = Path(record["candidate_path"])
    target = Path(record["production_path"])
    fsync_file(candidate)
    os.replace(candidate, target)
    fsync_file(target)
    fsync_directory(target.parent)
    actual = sqlite_verification(target)
    if actual["sha256"] != record["candidate_fingerprint"]:
        raise RuntimeError(f"REFRESH_PUBLISHED_FINGERPRINT_MISMATCH:{role}")
    record["replacement_state"] = "REPLACED_AND_VERIFIED"
    record["candidate_replacement_verified"] = True
    roles = dict(intended["roles"])
    roles[role] = record
    return update_journal(
        journal_path, intended, roles=roles,
        current_publication_step=f"PUBLISHED_{role.upper()}",
    )


def _required_taxonomy_dependency(analysis_result: Mapping[str, Any]) -> dict[str, str]:
    dependency = analysis_result.get("active_taxonomy")
    required = ("domain", "version", "semantic_fingerprint")
    if not isinstance(dependency, Mapping) or any(not str(dependency.get(key) or "") for key in required):
        raise RefreshPostflightValidationError(
            "REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MISSING_OR_MALFORMED"
        )
    normalized = {key: str(dependency[key]) for key in required}
    if normalized["domain"] != "dc_ecosystem":
        raise RefreshPostflightValidationError(
            "REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_WRONG_DOMAIN"
        )
    return normalized


def _validate_analysis_generation(
    analysis_path: Path, *, analysis_result: Mapping[str, Any], as_of_date: str,
    sources: Mapping[str, Path],
) -> dict[str, Any]:
    dependency = _required_taxonomy_dependency(analysis_result)
    try:
        validation = validate_rebuild(
            analysis_path, as_of_date=as_of_date,
            taxonomy_dependency=dependency, sources=sources,
        )
    except KeyError as exc:
        raise RefreshPostflightValidationError(
            "REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MALFORMED"
        ) from exc
    except RuntimeError as exc:
        if "TAXONOMY" in str(exc):
            raise RefreshPostflightValidationError(
                f"REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MISMATCH:{exc}"
            ) from exc
        raise
    return {"taxonomy_dependency": dependency, "validation": validation}


def _publication_activity(journal: Mapping[str, Any] | None) -> dict[str, list[str]]:
    roles = (journal or {}).get("roles") or {}
    replaced = [
        role for role in PUBLICATION_ROLES
        if isinstance(roles.get(role), Mapping)
        and roles[role].get("candidate_replacement_verified") is True
    ]
    restored = [
        role for role in PUBLICATION_ROLES
        if isinstance(roles.get(role), Mapping)
        and roles[role].get("rollback_restoration_verified") is True
    ]
    return {"live_replacements": replaced, "rollback_restorations": restored}


def _postflight(
    *, paths: BatchAddTickerPaths, histories: Mapping[str, Any],
    merge_plans: Mapping[str, Any],
    canonical_result: Mapping[str, Any], analysis_result: Mapping[str, Any],
    expected_roles: Mapping[str, Mapping[str, Any]], refresh_state: Mapping[str, Any],
    as_of_date: str, read_only_sources: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    provider = validate_provider_candidate(paths.provider_db, histories, merge_plans=merge_plans)
    with sqlite3.connect(f"file:{paths.provider_db.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        state = connection.execute("SELECT * FROM sharadar_refresh_state WHERE singleton_id=1").fetchone()
    if state is None or any(str(state[key]) != str(refresh_state[key]) for key in (
        "published_source_watermark", "provider_semantic_fingerprint", "source_schema_fingerprint",
        "successful_run_id", "completed_at_utc",
    )):
        raise RuntimeError("REFRESH_PUBLISHED_STATE_MISMATCH")
    identity = _identity_mapping(paths.canonical_db)
    if identity != canonical_result["identity_contract"]["after"]:
        raise RuntimeError("REFRESH_PUBLISHED_IDENTITY_MISMATCH")
    bootstrap = canonical_result.get("publication_date_bootstrap") or {}
    preserved = int(bootstrap.get("preservation_map_applied", -1))
    applicable = int(bootstrap.get("preservation_map_applicable_existing_quarters", -1))
    if bootstrap.get("repair_required") != 0 or preserved != applicable:
        raise RuntimeError("REFRESH_PUBLISHED_FIRST_PUBLIC_PRESERVATION_MISMATCH")
    canonical = sqlite_verification(paths.canonical_db)
    with sqlite3.connect(f"file:{paths.canonical_db.resolve()}?mode=ro", uri=True) as connection:
        duplicates = int(connection.execute(
            "SELECT COUNT(*) FROM (SELECT company_id,fiscal_year,fiscal_quarter,COUNT(*) n FROM v4_quarter GROUP BY 1,2,3 HAVING n>1)"
        ).fetchone()[0])
        missing_first = int(connection.execute("SELECT COUNT(*) FROM v4_quarter WHERE first_public_result_date IS NULL").fetchone()[0])
    if duplicates or missing_first:
        raise RuntimeError("REFRESH_PUBLISHED_CANONICAL_CONTRACT_FAILED")
    sources = {
        "provider": paths.provider_db, "canonical": paths.canonical_db,
        "market": (read_only_sources or {}).get("market", paths.market_db),
        "taxonomy": (read_only_sources or {}).get("taxonomy", paths.taxonomy_db),
    }
    analysis_lineage = _validate_analysis_generation(
        paths.analysis_db, analysis_result=analysis_result,
        as_of_date=as_of_date, sources=sources,
    )
    taxonomy = analysis_lineage["taxonomy_dependency"]
    analysis = analysis_lineage["validation"]
    fingerprints = {}
    for role in PUBLICATION_ROLES:
        actual = sha256_file(paths.as_dict()[role])
        expected = str(expected_roles[role]["candidate_fingerprint"])
        if actual != expected:
            raise RuntimeError(f"REFRESH_POSTFLIGHT_ROLE_FINGERPRINT_MISMATCH:{role}")
        fingerprints[role] = actual
    return {
        "provider": provider,
        "canonical": {
            **canonical,
            "duplicate_quarters": duplicates,
            "missing_first_public_dates": missing_first,
            "first_public_preservation_map_applied": preserved,
            "first_public_preservation_map_applicable": applicable,
            "first_public_repair_required": 0,
        },
        "analysis": analysis,
        "role_fingerprints": fingerprints,
        "cross_role_lineage": {
            "provider_semantic_fingerprint_matches_refresh_state": _provider_semantic_fingerprint(paths.provider_db) == refresh_state["provider_semantic_fingerprint"],
            "canonical_identity_matches_candidate": True,
            "analysis_matches_validated_candidate": True,
            "taxonomy_dependency": taxonomy,
        },
    }


def _duration(started: str, completed: str) -> float:
    return max(0.0, (datetime.fromisoformat(completed.replace("Z", "+00:00")) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds())


def render_report(result: Mapping[str, Any]) -> str:
    canonical = result.get("canonical_candidate") or {}
    impact = canonical.get("impact") or {}
    bootstrap = canonical.get("publication_date_bootstrap") or {}
    provider = result.get("provider_candidate") or {}
    refresh_state = result.get("refresh_state") or {}
    old_state = result.get("old_refresh_state") or {}
    published = result.get("outcome") == "COMPLETED"
    boundary_crossed = bool(result.get("write_boundary_crossed"))
    old_watermark = old_state.get("published_watermark")
    proposed_watermark = refresh_state.get("published_source_watermark")
    published_after = proposed_watermark if published else old_watermark
    provider_candidate_count = provider.get("ticker_count", 0)
    provider_published_count = provider_candidate_count if published else 0
    canonical_heading = "Canonical Publication" if published else "Canonical Candidate Impact"
    activity = result.get("publication_activity") or _publication_activity(result.get("journal"))
    live_replacements = list(activity.get("live_replacements") or [])
    rollback_restorations = list(activity.get("rollback_restorations") or [])
    source_binding = result.get("production_source_binding") or {}
    market_evidence = source_binding.get("market") or {}
    market_manifest = market_evidence.get("bundle_manifest") or {}
    market_binding = market_manifest.get("market") or {}
    taxonomy_evidence = source_binding.get("taxonomy") or {}
    taxonomy_binding = taxonomy_evidence.get("binding") or {}
    binding_comparison = result.get("test_source_binding_comparison") or {}
    lines = [
        "# Refresh Fundamentals Production Update", "", "## Executive Summary", "",
        "- Operation: Refresh Fundamentals", "- Stage: Production update",
        f"- Production result: {result.get('outcome', 'FAILED')}",
        f"- Duration: {result.get('duration_seconds', 0):.1f} seconds",
        f"- Publication boundary entered: {'YES' if boundary_crossed else 'NO'}",
        f"- Live database replacements before completion/failure: {len(live_replacements)} ({', '.join(live_replacements) or 'none'})",
        f"- Rollback restorations: {len(rollback_restorations)} ({', '.join(rollback_restorations) or 'none'})",
        f"- Net published generation changed: {'YES' if published else 'NO'}",
        f"- Rollback required: {'YES' if (result.get('rollback') or {}).get('status') not in (None, 'NOT_REQUIRED') else 'NO'}",
        f"- Changed known tickers: {result.get('summary_counts', {}).get('effective_changed_known', 0)}",
        f"- Provider candidate replacements: {provider_candidate_count}",
        f"- Provider published replacements: {provider_published_count}",
        f"- Canonical {'published' if published else 'candidate'} source-driven added/changed/removed: {impact.get('added_quarters', 0)} / {impact.get('changed_quarters', 0)} / {impact.get('removed_quarters', 0)}",
        f"- First-public bootstrap-only changes: {impact.get('bootstrap_only_date_changes', 0)}",
        f"- Full V2/RP/RV: {(result.get('analysis_candidate') or {}).get('status', 'NOT_RUN')}",
        f"- Published Refresh state before: {old_state.get('mode') or 'BOOTSTRAP_BASELINE'}",
        f"- Published Refresh state after: {refresh_state.get('mode') if published else old_state.get('mode') or 'BOOTSTRAP_BASELINE'}",
        f"- Published watermark before: {old_watermark or 'NONE'}",
        f"- Published watermark after: {published_after or 'NONE'}",
        f"- Candidate/proposed next watermark: {proposed_watermark or 'NOT_PREPARED'}",
        f"- Postflight: {'PASSED' if result.get('postflight') else 'NOT_COMPLETED'}",
        f"- Rollback: {(result.get('rollback') or {}).get('status', 'NOT_REQUIRED')}",
        "", "## Source Refresh", "",
        f"- Refresh-set fingerprint: `{result.get('preview_fingerprint')}`",
        f"- Source schema fingerprint: `{refresh_state.get('source_schema_fingerprint', 'not published')}`",
        f"- Source classifications: `{json.dumps(result.get('summary_counts') or {}, sort_keys=True)}`",
        "", "## Read-Only Source Binding", "",
        f"- Authorizing Test run: `{result.get('test_run_id', 'NOT_RECORDED')}`",
        f"- Test evidence: `{(result.get('test_source_binding_reference') or {}).get('evidence_path', 'NOT_RECORDED')}`",
        f"- Market mode: `{market_evidence.get('mode', 'NOT_PREPARED')}`",
        f"- Source contract: `{market_manifest.get('source_contract_version', 'NOT_PREPARED')}`",
        f"- Market semantic fingerprint: `{market_binding.get('semantic_fingerprint', 'NOT_PREPARED')}`",
        f"- Canonical binding: `{(market_manifest.get('canonical_binding') or {}).get('semantic_fingerprint', 'NOT_PREPARED')}`",
        f"- Coverage: `{json.dumps((market_binding.get('valuation_coverage') or {}).get('status_counts', {}), sort_keys=True)}`",
        f"- Taxonomy mode: `{taxonomy_evidence.get('mode', 'NOT_PREPARED')}`",
        f"- Taxonomy version/fingerprint: `{taxonomy_binding.get('version', 'NOT_PREPARED')}` / `{taxonomy_binding.get('semantic_fingerprint', 'NOT_PREPARED')}`",
        f"- Test vs Production: `{binding_comparison.get('status', 'NOT_COMPARED')}`",
        f"- Differing contract sections: `{json.dumps(binding_comparison.get('differing_contract_sections', []))}`",
        f"- Full market-copy bytes avoided: {market_evidence.get('old_full_copy_bytes_avoided', 0)}",
        f"- Compact market bytes/build seconds: {market_evidence.get('compact_bundle_bytes', 0)} / {market_evidence.get('bundle_build_seconds', 0)}",
        "", f"## Provider {'Publication' if published else 'Candidate'}", "",
        f"- Candidate ARQ/MRQ replacement tickers: {provider_candidate_count}",
        f"- Published ARQ/MRQ replacement tickers: {provider_published_count}",
        "", f"## {canonical_heading}", "",
        f"- Quarters added: {impact.get('added_quarters', 0)}",
        f"- Quarters financially/source changed: {impact.get('changed_quarters', 0)}",
        f"- Quarters removed: {impact.get('removed_quarters', 0)}",
        f"- Source availability date changes: {impact.get('source_availability_date_changes', 0)}",
        f"- First-public bootstrap eligible: {bootstrap.get('bootstrap_eligible', 0)}",
        f"- Established dates preserved: {impact.get('first_public_result_date_preserved', 0)}",
        f"- New first-public dates: {impact.get('new_first_public_result_date_established', 0)}",
        f"- Removed-quarter date evidence: {len(canonical.get('removed_quarter_publication_evidence') or [])}",
        f"- `first_public_result_date preservation map applied: {bootstrap.get('preservation_map_applied', 0)}/{bootstrap.get('preservation_map_applicable_existing_quarters', 0)} surviving existing quarters`",
        f"- `first_public_result_date repair_required: {bootstrap.get('repair_required', 'not checked')}`",
        "- `company/security identity mapping before candidate rebuild == after candidate rebuild`: "
        + str(bool(canonical.get("identity_contract", {}).get("company_security_identity_mapping_unchanged"))).lower(),
        "", "## Analysis Outcome", "",
        f"- B1/full package status: {(result.get('analysis_candidate') or {}).get('status', 'NOT_RUN')}",
        "- Canonical/downstream financial values remain ARQ-based.",
        "- MRQ overlay intentionally deferred for a later impact study.",
        "", "## Publication Safety", "",
        f"- Backups verified: {len(result.get('backups') or {})}/3",
        f"- Journal state: {(result.get('journal') or {}).get('state', 'NOT_PREPARED')}",
        f"- Candidate/source-copy cleanup: {(result.get('cleanup') or {}).get('status', 'NOT_RECORDED')}",
        "- Publication order: provider -> canonical -> analysis.",
        "- The three-file set is journaled and recoverable, not reader-atomically replaced as one filesystem operation.",
        "- A reader can observe an intermediate generation during the bounded replacement window; generation-directory activation is deferred.",
        "", "## Final Result", "",
        str(result.get("user_message") or "See technical evidence for the final state."),
    ]
    ticker_changes = result.get("ticker_changes") or []
    if ticker_changes:
        lines.extend([
            "", "## Ticker Results", "",
            "| Ticker | Source change | Latest Q before/after | ARQ rows | MRQ rows | Canonical +/~/- | Score before/after | Lifecycle before/after | Valuation before/after | RP before/after | RV before/after | Publication date | Final action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        company_impact = canonical.get("company_impact") or {}
        analysis_before = result.get("analysis_before") or {}
        analysis_after = result.get("analysis_after") or {}
        for item in ticker_changes:
            ticker = str(item.get("ticker") or "")
            company_id = item.get("identity", {}).get("company_id")
            ticker_impact = company_impact.get(company_id) or company_impact.get(str(company_id)) or {}
            before = analysis_before.get(ticker) or {}
            after = analysis_after.get(ticker) or {}

            def transition(key: str) -> str:
                return f"{before.get(key)} -> {after.get(key)}"

            if published:
                final_action = "Published"
            elif canonical:
                final_action = "Candidate prepared; not published"
            elif provider:
                final_action = "Provider candidate prepared; not published"
            else:
                final_action = "Candidate not prepared; not published"

            lines.append(
                f"| {ticker} | {item.get('classification')} | "
                f"{item.get('old_latest_fiscal_quarter') or '-'} -> {item.get('new_latest_fiscal_quarter') or '-'} | "
                f"{item.get('current_counts', {}).get('ARQ', 0)} -> {item.get('source_counts', {}).get('ARQ', 0)} | "
                f"{item.get('current_counts', {}).get('MRQ', 0)} -> {item.get('source_counts', {}).get('MRQ', 0)} | "
                f"{ticker_impact.get('quarters_added', 0)}/{ticker_impact.get('quarters_changed', 0)}/{ticker_impact.get('quarters_removed', 0)} | "
                f"{transition('score')} | {transition('lifecycle')} | {transition('valuation')} | "
                f"{transition('relative_position_count')} | {transition('relative_valuation')} | "
                f"preserved={ticker_impact.get('first_public_dates_preserved', 0)}, new={ticker_impact.get('new_first_public_dates', 0)}, removed evidence={item.get('removed_count', 0)} | {final_action} |"
            )
    if result.get("error"):
        lines.extend(["", "## Technical Appendix", "", f"- Error: `{result['error']}`", f"- Failed stage: `{result.get('failed_stage')}`"])
    return "\n".join(lines) + "\n"


def run_production_apply(
    *, preview_payload_path: Path, preview_fingerprint: str, test_run_id: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(), run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT, backup_root: Path = BACKUP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH, client: SharadarClient | None = None,
    confirm_production: bool = False, production_intent: bool = False,
    rehearsal: bool = False, scheduler_log_dir: str | None = None,
    lock_path: Path = ADMIN_LOCK, progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    as_of_date: str | None = None, inject_failure_at: str | None = None,
    inject_crash_at: str | None = None,
) -> dict[str, Any]:
    if not confirm_production:
        raise PermissionError("REFRESH_PRODUCTION_CONFIRMATION_REQUIRED")
    production_paths = {role: path.resolve() for role, path in PRODUCTION.items()}
    actual_production = source_paths.analysis_db.resolve() == production_paths["analysis"]
    if actual_production != (production_intent and not rehearsal):
        raise PermissionError("REFRESH_EXPLICIT_PRODUCTION_INTENT_REQUIRED")
    if actual_production:
        if any(source_paths.as_dict()[role].resolve() != production_paths[role] for role in source_paths.as_dict()):
            raise PermissionError("REFRESH_EXACT_PRODUCTION_PATHS_REQUIRED")
        if run_root.resolve() != ADMIN_RUN_ROOT.resolve() or journal_path.resolve() != ACTIVE_JOURNAL_PATH.resolve() or lock_path.resolve() != ADMIN_LOCK.resolve():
            raise PermissionError("REFRESH_PRODUCTION_GUARD_PATH_OVERRIDE_REJECTED")
    elif any(path.resolve() in set(production_paths.values()) for path in source_paths.as_dict().values()):
        raise PermissionError("REFRESH_REHEARSAL_MUST_USE_ONLY_COPIES")

    run_id = stable_run_id(AdminOperationType.REFRESH_FUNDAMENTALS, preview_fingerprint, suffix="production" if actual_production else "transaction_rehearsal") + "_" + secrets.token_hex(4)
    writer = AdminRunWriter(run_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=run_root)
    started = utc_now()
    lane_dir = temp_root / run_id
    backup_dir = backup_root / run_id
    api = client or SharadarClient()
    stage = PRODUCTION_STAGES[0]
    journal: dict[str, Any] | None = None
    write_boundary_crossed = False
    result: dict[str, Any] = {
        "run_id": run_id, "artifact_dir": str(writer.run_dir),
        "operation_type": AdminOperationType.REFRESH_FUNDAMENTALS.value,
        "mode": "PRODUCTION_APPLY" if actual_production else "TRANSACTION_REHEARSAL",
        "trigger_source": "MANUAL", "contract_version": PRODUCTION_CONTRACT_VERSION,
        "preview_fingerprint": preview_fingerprint, "test_run_id": test_run_id,
        "started_at_utc": started, "outcome": "FAILED", "write_boundary_crossed": False,
        "write_set": list(PUBLICATION_ROLES), "warnings": [],
    }

    def progress(stage_name: str, state: str, message: str) -> None:
        payload = {
            "run_id": run_id, "operation_type": AdminOperationType.REFRESH_FUNDAMENTALS.value,
            "current_stage_id": stage_name, "current_stage_number": PRODUCTION_STAGES.index(stage_name) + 1,
            "total_declared_stages": len(PRODUCTION_STAGES), "stage_state": state,
            "message": message, "timestamp_utc": utc_now(),
        }
        writer.write_json("progress_status.json", payload)
        writer.append_jsonl("progress_events.jsonl", payload)
        if progress_callback is None:
            return
        try:
            progress_callback(payload)
        except Exception:
            pass

    def crash(point: str) -> None:
        if inject_crash_at == point:
            raise SimulatedPublicationCrash(f"SIMULATED_REFRESH_PUBLICATION_CRASH:{point}")

    writer.write_json("request.json", _request().as_dict() | {"options": {"contract_version": PRODUCTION_CONTRACT_VERSION, "mode": result["mode"]}})
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Refresh Production request recorded.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Refresh Production preflight started.", preview_fingerprint=preview_fingerprint)
    locks = ExitStack()
    try:
        progress(stage, "RUNNING", "Validating Preview, Test, paths, locks, and recovery state.")
        preview, test = load_production_authorization(
            preview_payload_path=preview_payload_path, preview_fingerprint=preview_fingerprint,
            test_run_id=test_run_id, run_root=run_root,
        )
        result["preview"] = {"run_id": preview_payload_path.resolve().parent.name, "payload": str(preview_payload_path.resolve())}
        result["test_on_copies"] = {"run_id": test_run_id, "outcome": test["outcome"]}
        test_source_binding = test["_authorized_source_binding"]
        result["test_source_binding_reference"] = {
            "test_run_id": test_run_id,
            "evidence_path": test["_authorized_source_binding_path"],
            "semantic_contract": _semantic_source_binding(test_source_binding),
        }
        calculation_as_of_date = as_of_date or date.today().isoformat()
        owner = locks.enter_context(production_lock(lock_path=lock_path, scheduler_log_dir=scheduler_log_dir))
        result["lock_owner"] = owner
        result["recovery_preflight"] = guard_production_writes(journal_path)
        if actual_production:
            result["git_state"] = _assert_clean_worktree()
            if result["git_state"].get("dirty"):
                result["warnings"].append({"code": "DIRTY_GIT_WORKTREE", "message": "Git worktree contains uncommitted changes."})
        before_files = _production_file_state(source_paths)
        result["production_file_state_before"] = before_files
        result["storage_preflight_before_build"] = _storage_preflight(source_paths, temp_root=temp_root, backup_root=backup_root)
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Authorization passed; candidate-first build begins.", preview_fingerprint=preview_fingerprint)
        progress(stage, "COMPLETED", "Production authorization and recovery preflight passed.")

        stage = "SOURCE_REVALIDATION"
        progress(stage, "RUNNING", "Revalidating complete Sharadar histories against the successful Test.")
        try:
            revalidated = revalidate_bound_source(preview, source_paths, api)
        except Exception as exc:
            raise StaleRefreshTest("STALE_REFRESH_TEST") from exc
        if revalidated["refresh_set_fingerprint"] != preview_fingerprint:
            raise StaleRefreshTest("STALE_REFRESH_TEST")
        writer.write_json(
            "source_revalidation.json",
            {key: value for key, value in revalidated.items() if key not in {"histories", "merge_plans"}},
        )
        progress(stage, "COMPLETED", "Sharadar source still matches the tested refresh set.")

        changed = [item for item in revalidated["ticker_changes"] if item["classification"] in REPLACEMENT_CLASSES]
        changed_tickers = [item["ticker"] for item in changed]
        identities = {item["ticker"]: item["identity"] for item in changed}
        histories = {ticker: revalidated["histories"][ticker] for ticker in changed_tickers}
        merge_plans = {ticker: revalidated["merge_plans"][ticker] for ticker in changed_tickers}
        result["summary_counts"] = _summary_counts(revalidated["ticker_changes"])
        result["ticker_changes"] = changed
        result["old_refresh_state"] = revalidated["state"]
        lane_dir.mkdir(parents=True, exist_ok=False)
        provider_candidate = lane_dir / "provider_candidate.db"
        canonical_candidate = lane_dir / "canonical_candidate.db"

        stage = "PROVIDER_CANDIDATE"
        progress(stage, "RUNNING", "Preparing the isolated provider candidate.")
        with _durable_heartbeat(writer, stage, "Provider candidate construction is still running."):
            online_backup(source_paths.provider_db, provider_candidate)
            provider_result = replace_provider_histories(
                provider_candidate, histories, identities,
                applied_at=utc_now(), merge_plans=merge_plans,
            )
        source_watermark = str(revalidated["discovery"].get("observed_source_max_lastupdated") or "")
        if not source_watermark:
            raise RuntimeError("REFRESH_SOURCE_WATERMARK_MISSING")
        refresh_state = _publish_refresh_state(
            provider_candidate, source_watermark=source_watermark,
            schema_fingerprint=revalidated["schema"]["schema_fingerprint"],
            run_id=run_id, completed_at=utc_now(),
        )
        result["provider_candidate"] = provider_result
        result["refresh_state"] = refresh_state
        progress(stage, "COMPLETED", "Provider candidate and candidate-only Refresh state are ready.")

        stage = "CANONICAL_CANDIDATE"
        progress(stage, "RUNNING", "Fresh-building canonical, TTM, structural state, and publication dates.")
        with _durable_heartbeat(writer, stage, "Fresh canonical rebuild is still running."):
            online_backup(source_paths.canonical_db, canonical_candidate)
            canonical_result = fresh_rebuild_canonical(
                provider_candidate, canonical_candidate, applied_at=utc_now(),
                affected_company_ids=[int(identity["company_id"]) for identity in identities.values()],
            )
        if canonical_result["publication_date_bootstrap"]["repair_required"]:
            raise RuntimeError("REFRESH_PUBLISH_DATE_REPAIR_REQUIRED")
        result["canonical_candidate"] = canonical_result
        writer.write_json("publish_date_bootstrap_summary.json", canonical_result["publication_date_bootstrap"])
        writer.write_json("removed_quarter_publication_evidence.json", canonical_result["removed_quarter_publication_evidence"])
        progress(stage, "COMPLETED", "Canonical candidate passed identity and publication-date invariants.")

        stage = "ANALYSIS_CANDIDATE"
        progress(stage, "RUNNING", "Binding compact read-only sources and building the full V2, RP V2, and RV candidate once.")
        before_analysis = _analysis_state(source_paths.analysis_db, source_paths.canonical_db, changed_tickers)
        with _durable_heartbeat(writer, stage, "Compact market bundle and taxonomy copy preparation is still running."):
            read_only_copies, production_source_binding = prepare_compact_read_only_sources(
                source_paths,
                lane_dir=lane_dir,
                canonical_candidate=canonical_candidate,
                as_of_date=calculation_as_of_date,
            )
        binding_comparison = compare_test_and_production_source_bindings(
            test_source_binding,
            production_source_binding,
        )
        result["production_source_binding"] = production_source_binding
        result["test_source_binding_comparison"] = binding_comparison
        writer.write_json("read_only_source_binding.json", production_source_binding)
        writer.write_json("test_source_binding_comparison.json", binding_comparison)
        if binding_comparison["status"] != "MATCH":
            raise StaleRefreshTest(
                "REFRESH_TEST_SOURCE_BINDING_STALE:"
                + ",".join(binding_comparison["differing_contract_sections"])
            )
        with _durable_heartbeat(writer, stage, "Full V2, RP V2, and RV rebuild is still running."):
            analysis_result = run_refresh_production_full_v2_downstream(
                provider_candidate=provider_candidate,
                canonical_candidate=canonical_candidate,
                read_only_sources=read_only_copies,
                lane_dir=lane_dir,
                as_of_date=calculation_as_of_date,
            )
        analysis_candidate = Path(analysis_result["candidate_analysis_db"])
        if analysis_result.get("status") != "READY" or analysis_result.get("invocation_counts", {}).get("full_v2_rebuild") != 1:
            raise RuntimeError("REFRESH_FULL_V2_REBUILD_NOT_READY")
        result["analysis_candidate"] = analysis_result
        result["analysis_before"] = before_analysis
        result["analysis_after"] = _analysis_state(analysis_candidate, canonical_candidate, changed_tickers)
        progress(stage, "COMPLETED", "Full V2, RP V2, and RV candidate is READY.")

        stage = "CANDIDATE_VALIDATION"
        progress(stage, "RUNNING", "Validating all three complete candidates.")
        candidate_paths_by_role = {
            "provider": provider_candidate, "canonical": canonical_candidate, "analysis": analysis_candidate,
        }
        candidate_checks = {role: sqlite_verification(path) for role, path in candidate_paths_by_role.items()}
        validate_provider_candidate(provider_candidate, histories, merge_plans=merge_plans)
        if _identity_mapping(canonical_candidate) != canonical_result["identity_contract"]["after"]:
            raise RuntimeError("REFRESH_CANONICAL_IDENTITY_VALIDATION_FAILED")
        candidate_sources = {
            "provider": provider_candidate, "canonical": canonical_candidate,
            "market": read_only_copies["market"], "taxonomy": read_only_copies["taxonomy"],
        }
        candidate_analysis_lineage = _validate_analysis_generation(
            analysis_candidate, analysis_result=analysis_result,
            as_of_date=calculation_as_of_date, sources=candidate_sources,
        )
        result["candidate_validation"] = candidate_checks
        result["candidate_analysis_lineage"] = candidate_analysis_lineage
        progress(stage, "COMPLETED", "Provider, canonical, and analysis candidates all passed validation.")

        stage = "FINAL_SOURCE_RECHECK"
        progress(stage, "RUNNING", "Rechecking complete source state immediately before publication.")
        try:
            final_source = revalidate_bound_source(preview, source_paths, api)
        except Exception as exc:
            raise StaleRefreshTest("STALE_REFRESH_SOURCE_BEFORE_PUBLICATION") from exc
        if final_source["refresh_set_fingerprint"] != revalidated["refresh_set_fingerprint"]:
            raise StaleRefreshTest("STALE_REFRESH_SOURCE_BEFORE_PUBLICATION")
        result["final_source_recheck"] = {
            key: value for key, value in final_source.items()
            if key not in {"histories", "merge_plans"}
        }
        result["storage_preflight_before_publication"] = _storage_preflight(source_paths, temp_root=temp_root, backup_root=backup_root)
        if before_files != _production_file_state(source_paths):
            raise RuntimeError("REFRESH_PRODUCTION_DATABASE_CHANGED_DURING_CANDIDATE_BUILD")
        progress(stage, "COMPLETED", "Final source recheck matches the candidate generation.")

        stage = "BACKUP"
        progress(stage, "RUNNING", "Creating and verifying the old complete generation backup set.")
        with _durable_heartbeat(writer, stage, "Verified backup creation is still running."):
            backups = _verified_backups(source_paths, backup_dir)
        result["backups"] = backups
        progress(stage, "COMPLETED", "All three old-generation backups are verified and durable.")
        crash("AFTER_BACKUPS_BEFORE_PREPARED")

        stage = "JOURNAL_PREPARE"
        roles = _candidate_manifest(candidate_paths_by_role, backups)
        journal = prepare_journal(
            path=journal_path, operation_type=AdminOperationType.REFRESH_FUNDAMENTALS.value,
            run_id=run_id, preview_run_id=preview_payload_path.resolve().parent.name,
            test_run_id=test_run_id, refresh_set_fingerprint=preview_fingerprint,
            old_source_watermark=revalidated["state"].get("published_watermark"),
            new_source_watermark=source_watermark,
            source_schema_fingerprint=revalidated["schema"]["schema_fingerprint"], roles=roles,
        )
        result["journal"] = journal
        progress(stage, "COMPLETED", "Durable publication journal is PREPARED.")
        crash("AFTER_PREPARED")

        for role in PUBLICATION_ROLES:
            stage = f"PUBLISH_{role.upper()}"
            progress(stage, "RUNNING", f"Publishing and verifying {role}.")
            if not write_boundary_crossed:
                writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Journaled three-database publication started.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
                write_boundary_crossed = True
                result["write_boundary_crossed"] = True
            journal = _replace_role(role, journal, journal_path=journal_path)
            result["journal"] = journal
            progress(stage, "COMPLETED", f"Published and verified {role}.")
            crash(f"AFTER_{role.upper()}_REPLACEMENT")
            if inject_failure_at == f"AFTER_{role.upper()}_REPLACEMENT":
                raise RuntimeError(f"INJECTED_REFRESH_PUBLICATION_FAILURE:{role}")

        stage = "POSTFLIGHT"
        journal = update_journal(journal_path, journal, state="POSTFLIGHT", current_publication_step="POSTFLIGHT", postflight_state="RUNNING")
        result["journal"] = journal
        crash("AFTER_ALL_REPLACEMENTS_BEFORE_POSTFLIGHT")
        if inject_failure_at == "POSTFLIGHT":
            raise RuntimeError("INJECTED_REFRESH_POSTFLIGHT_FAILURE")
        postflight = _postflight(
            paths=source_paths, histories=histories, merge_plans=merge_plans,
            canonical_result=canonical_result,
            analysis_result=analysis_result, expected_roles=roles, refresh_state=refresh_state,
            as_of_date=calculation_as_of_date,
            read_only_sources=read_only_copies,
        )
        result["postflight"] = postflight
        journal = update_journal(journal_path, journal, postflight_state="PASSED", current_publication_step="POSTFLIGHT_PASSED")
        result["journal"] = journal
        progress(stage, "COMPLETED", "Production-path and cross-role postflight passed.")
        crash("AFTER_POSTFLIGHT_BEFORE_COMPLETED")

        stage = "JOURNAL_COMMIT"
        journal = update_journal(
            journal_path, journal, state="COMPLETED", current_publication_step="COMPLETED",
            postflight_state="PASSED", rollback_recovery_state="NOT_REQUIRED",
        )
        result["journal"] = journal
        result["outcome"] = "COMPLETED"
        result["rollback"] = {"status": "NOT_REQUIRED"}
        result["user_message"] = "Refresh Fundamentals Production update completed. The provider, canonical, and analysis generation passed postflight."
        progress(stage, "COMPLETED", "Publication journal committed after successful postflight.")
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["errors"] = [{"type": type(exc).__name__, "message": str(exc)}]
        result["failed_stage"] = stage
        stale = isinstance(exc, StaleRefreshTest)
        recovery_retry = isinstance(exc, PublicationRecoveredRetryRequired)
        recovery_failed = isinstance(exc, PublicationRecoveryError) and not recovery_retry
        if recovery_retry:
            result["outcome"] = "RETRY_REQUIRED"
            result["publication_recovery"] = exc.recovery
        elif recovery_failed:
            result["outcome"] = "RECOVERY_FAILED"
        if journal is not None and write_boundary_crossed:
            try:
                journal = update_journal(journal_path, journal, state="ROLLING_BACK", rollback_recovery_state="ROLLING_BACK_COMPLETE_SET")
                recovered = restore_old_generation(journal, journal_path=journal_path)
                journal = update_journal(
                    journal_path, recovered["journal"], state="ROLLED_BACK",
                    rollback_recovery_state="OLD_GENERATION_RESTORED_AND_VERIFIED",
                )
                result["journal"] = journal
                result["rollback"] = {"status": "ROLLED_BACK", "roles": recovered["roles"]}
                result["outcome"] = "FAILED_ROLLED_BACK"
                result["user_message"] = "Production publication failed after the publication boundary. The previous provider, canonical, and analysis generation was restored and verified."
            except Exception as rollback_exc:
                result["rollback"] = {"status": "CRITICAL_ROLLBACK_FAILED", "error": f"{type(rollback_exc).__name__}: {rollback_exc}"}
                result["outcome"] = "CRITICAL_ROLLBACK_FAILED"
                result["user_message"] = "RawCandle could not restore a complete verified Fundamentals generation. Production-writing Fundamentals operations are blocked until recovery is resolved."
        else:
            result["database_safety"] = "NO_PRODUCTION_DATABASES_MODIFIED"
            result["production_file_state_unchanged"] = result.get("production_file_state_before") == _production_file_state(source_paths) if result.get("production_file_state_before") else True
            result["retry_authorization"] = (
                {
                    "direct_production_retry_available": False,
                    "preview_test_preserved": False,
                    "preview_test_rerun_required": True,
                    "reason": "RECOVERY_COMPLETED_FRESH_INVOCATION_REQUIRED",
                }
                if recovery_retry else {
                    "direct_production_retry_available": not stale,
                    "preview_test_preserved": not stale,
                    "preview_test_rerun_required": stale,
                }
            )
            result["user_message"] = (
                "An incomplete previous publication was detected. RawCandle restored the previous verified Fundamentals generation before allowing new writes. This operation stopped before mutation; run Preview and Test on copies again."
                if recovery_retry else
                "RawCandle could not restore a complete verified Fundamentals generation. Production-writing Fundamentals operations are blocked until recovery is resolved."
                if recovery_failed else
                "The successful Test source binding is stale or source fundamentals changed. No production databases were modified. Run Preview and Test on copies again."
                if stale else
                "Production candidates did not pass validation. No production databases were modified."
            )
    finally:
        locks.close()
        result["cleanup"] = _cleanup_candidate_lane(lane_dir, journal)
        if result.get("production_file_state_before"):
            result["production_file_state_after"] = _production_file_state(source_paths)
            result["production_file_state_unchanged"] = (
                result["production_file_state_before"] == result["production_file_state_after"]
            )
        result["publication_activity"] = _publication_activity(journal)
        result["production_writes"] = len(result["publication_activity"]["live_replacements"])
        result["production_generation_changed"] = result.get("outcome") == "COMPLETED"
        completed = utc_now()
        result["completed_at_utc"] = completed
        result["duration_seconds"] = _duration(started, completed)
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", render_report(result))
        terminal = RunStage.COMPLETED if result.get("outcome") == "COMPLETED" else RunStage.FAILED_AFTER_WRITE if write_boundary_crossed else RunStage.FAILED_BEFORE_WRITE
        try:
            writer.checkpoint(terminal, message=f"Refresh Production {result.get('outcome')}.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        except ValueError:
            pass
        writer.write_exit_code(0 if result.get("outcome") == "COMPLETED" else 3)
        writer.write_manifest()
    return result
