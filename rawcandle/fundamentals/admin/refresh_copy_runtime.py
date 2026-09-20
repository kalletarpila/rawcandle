"""Copy-only Refresh Fundamentals replacement and full downstream rebuild."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths, _background_heartbeat
from rawcandle.fundamentals.admin.contracts import AdminFinalResult, AdminOperationType, AdminStatus, RunStage, fingerprint, utc_now
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.progress import ProgressCallback, ProgressStage, ProgressTracker, REFRESH_FUNDAMENTALS_TEST_STAGES
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    CONTRACT_VERSION,
    FINANCIAL_FIELDS,
    REFRESH_REPLACEMENT_CLASSES,
    REFRESH_DIMENSIONS,
    REFRESH_REQUEST_FIELDS,
    RETAINED_OUTSIDE_SOURCE_WINDOW,
    HistoryTrust,
    RefreshPreviewError,
    _production_file_state,
    _raw_row,
    _request,
    _summary_counts,
    audit_publish_date_bootstrap,
    build_source_history_merge,
    compare_ticker_histories,
    discover_changed_tickers,
    fetch_complete_history,
    history_fingerprints,
    load_current_history,
    normalize_source_row,
    provider_key_diagnostics,
    refresh_binding_change,
    resolve_identity,
    resolve_refresh_state,
    source_key,
    source_schema,
)
from rawcandle.fundamentals.admin.structural_context import _events
from rawcandle.fundamentals.phase12d import rebuild_ttm, reconcile_canonical, stable_hash
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.fundamentals.providers.sharadar import SharadarClient
from rawcandle.fundamentals.ttm.engine import ensure_ttm_schema


TEST_CONTRACT_VERSION = "PHASE13G3_10_SHARADAR_REFRESH_RETENTION_COPY_TEST_V1"
REPLACEMENT_CLASSES = REFRESH_REPLACEMENT_CLASSES
FULL_V2_READ_ONLY_SOURCE_ROLES = ("market", "taxonomy")


class StaleRefreshPreview(RefreshPreviewError):
    pass


def prepare_full_v2_read_only_copies(
    source_paths: BatchAddTickerPaths, *, lane_dir: Path,
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    """Snapshot the read-only authorities required by the full V2 rebuild."""
    copies: dict[str, Path] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for role in FULL_V2_READ_ONLY_SOURCE_ROLES:
        source = source_paths.as_dict()[role]
        destination = lane_dir / f"{role}.db"
        source_stat = source.stat()
        copy_result = online_backup(source, destination)
        copies[role] = destination
        evidence[role] = {
            **copy_result,
            "role": role,
            "purpose": "FULL_V2_READ_ONLY_SOURCE",
            "source_size": source_stat.st_size,
            "source_mtime_ns": source_stat.st_mtime_ns,
            "immutable_after_creation": True,
            "cleanup_required": True,
        }
    return copies, evidence


def _load_bound_preview(path: Path, expected_fingerprint: str, run_root: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    root = run_root.resolve()
    if path.is_symlink() or resolved.name != "refresh_preview.json" or root not in resolved.parents:
        raise PermissionError("REFRESH_PREVIEW_ARTIFACT_REQUIRED")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("REFRESH_PREVIEW_CONTRACT_MISMATCH")
    if payload.get("refresh_set_fingerprint") != expected_fingerprint:
        raise ValueError("REFRESH_PREVIEW_FINGERPRINT_MISMATCH")
    changes = payload.get("ticker_changes") or []
    changed = [item for item in changes if item.get("classification") in REPLACEMENT_CLASSES]
    if not payload.get("future_test_authorized") or payload.get("discovery", {}).get("status") != "COMPLETE":
        raise ValueError("REFRESH_PREVIEW_NOT_AUTHORIZED")
    if any(item.get("classification") == "REVIEW_REQUIRED" for item in changes):
        raise ValueError("REFRESH_PREVIEW_HAS_REVIEW_REQUIRED")
    if not changed:
        raise ValueError("REFRESH_PREVIEW_NO_CHANGE_NOT_TESTABLE")
    if not payload.get("schema", {}).get("schema_fingerprint"):
        raise ValueError("REFRESH_PREVIEW_SOURCE_SCHEMA_EVIDENCE_MISSING")
    return payload


def _binding(
    *, state: Any, schema: Mapping[str, Any], discovery: Mapping[str, Any], changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "dataset": "SHARADAR",
        "table": "fundamentals",
        "schema_fingerprint": schema["schema_fingerprint"],
        "state_mode": state.mode,
        "published_watermark": state.published_watermark,
        "derived_watermark": state.derived_watermark,
        "query_start_date": state.query_start_date,
        "observed_source_max_lastupdated": discovery["observed_source_max_lastupdated"],
        "ticker_changes": [refresh_binding_change(item) for item in changes],
    }


def revalidate_bound_source(
    preview: Mapping[str, Any], paths: BatchAddTickerPaths, client: SharadarClient,
) -> dict[str, Any]:
    state = resolve_refresh_state(paths.provider_db)
    expected_state = preview["state"]
    for field in ("mode", "published_watermark", "derived_watermark", "query_start_date"):
        if getattr(state, field) != expected_state.get(field):
            raise StaleRefreshPreview("STALE_REFRESH_PREVIEW")
    schema = source_schema(client)
    if schema["schema_fingerprint"] != preview["schema"]["schema_fingerprint"]:
        raise StaleRefreshPreview("STALE_REFRESH_PREVIEW")
    discovery = discover_changed_tickers(client, query_start_date=state.query_start_date)
    identities = {ticker: resolve_identity(paths, ticker) for ticker in discovery["changed_tickers"]}
    histories: dict[str, dict[str, HistoryTrust]] = {}
    merge_plans: dict[str, dict[str, Any]] = {}
    changes: list[dict[str, Any]] = []
    for ticker in discovery["changed_tickers"]:
        identity = identities[ticker]
        if identity["status"] != "KNOWN":
            changes.append({
                "ticker": ticker, "classification": identity["status"],
                "review_reason": identity.get("reason"), "identity": identity,
            })
            continue
        histories[ticker] = {dimension: fetch_complete_history(client, ticker, dimension) for dimension in REFRESH_DIMENSIONS}
        current = {dimension: load_current_history(paths.provider_db, ticker, dimension) for dimension in REFRESH_DIMENSIONS}
        item = compare_ticker_histories(ticker, current, histories[ticker])
        if all("rows" in current.get(dimension, {}) for dimension in REFRESH_DIMENSIONS):
            merge_plans[ticker] = build_source_history_merge(ticker, current, histories[ticker])
        item["identity"] = identity
        changes.append(item)
    changes.sort(key=lambda item: str(item["ticker"]))
    if any(item["classification"] == "REVIEW_REQUIRED" for item in changes):
        raise StaleRefreshPreview("STALE_REFRESH_PREVIEW")
    actual = fingerprint(_binding(state=state, schema=schema, discovery=discovery, changes=changes))
    if actual != preview["refresh_set_fingerprint"]:
        raise StaleRefreshPreview("STALE_REFRESH_PREVIEW")
    changed = [item for item in changes if item["classification"] in REPLACEMENT_CLASSES]
    if not changed:
        raise StaleRefreshPreview("STALE_REFRESH_PREVIEW")
    return {
        "state": state.as_dict(), "schema": schema, "discovery": discovery,
        "ticker_changes": changes, "histories": histories, "merge_plans": merge_plans,
        "changed_tickers": [item["ticker"] for item in changed],
        "refresh_set_fingerprint": actual,
    }


def _provider_unrelated_fingerprint(path: Path, excluded_tickers: Sequence[str]) -> str:
    excluded = {ticker.upper() for ticker in excluded_tickers}
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = [
            tuple(row) for row in connection.execute(
                "SELECT po.observation_id,po.provider_record_key,po.content_hash,s.ticker,s.dimension,s.date,s.reportperiod,s.lastupdated "
                "FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id) "
                "WHERE po.provider='SHARADAR' AND po.native_table='fundamentals' ORDER BY po.observation_id"
            ) if str(row[3]).upper() not in excluded or str(row[4]).upper() not in REFRESH_DIMENSIONS
        ]
        native_counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("sharadar_ticker_metadata", "sharadar_action_metadata")
        }
    return stable_hash({"unrelated_rows": rows, "native_counts": native_counts})


def _observation_id(record_key: str, content_hash: str) -> str:
    return hashlib.sha256(f"SHARADAR|fundamentals|{record_key}|{content_hash}".encode()).hexdigest()


def replace_provider_histories(
    provider_db: Path, histories: Mapping[str, Mapping[str, HistoryTrust]],
    identities: Mapping[str, Mapping[str, Any]], *, applied_at: str,
    merge_plans: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    tickers = sorted(histories)
    unrelated_before = _provider_unrelated_fingerprint(provider_db, tickers)
    run_id = "REFRESH_COPY_" + hashlib.sha256((applied_at + "|".join(tickers)).encode()).hexdigest()[:20]
    replaced: list[dict[str, Any]] = []
    with sqlite3.connect(provider_db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,request_scope,source_version,metadata_json) "
            "VALUES(?,'SHARADAR',?,?,'COMPLETED','REFRESH_ARQ_MRQ_COMPLETE_HISTORY',?,?)",
            (run_id, applied_at, applied_at, TEST_CONTRACT_VERSION, json.dumps({"tickers": tickers}, sort_keys=True)),
        )
        for ticker in tickers:
            identity = identities[ticker]
            before_counts = {}
            removed_ids: list[str] = []
            for dimension in REFRESH_DIMENSIONS:
                ids = [str(row[0]) for row in connection.execute(
                    "SELECT po.observation_id FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id) "
                    "WHERE po.provider='SHARADAR' AND po.native_table='fundamentals' AND UPPER(s.ticker)=? AND s.dimension=?",
                    (ticker, dimension),
                )]
                before_counts[dimension] = len(ids)
                removed_ids.extend(ids)
            connection.executemany("DELETE FROM provider_observation WHERE observation_id=?", ((item,) for item in removed_ids))
            inserted = Counter()
            for dimension in REFRESH_DIMENSIONS:
                trust = histories[ticker][dimension]
                if trust.status != "COMPLETE":
                    raise ValueError(f"COMPLETE_HISTORY_NOT_TRUSTED:{ticker}:{dimension}")
                rows = (
                    merge_plans[ticker]["dimensions"][dimension]["merged_rows"]
                    if merge_plans is not None else trust.rows
                )
                for row in rows:
                    item = normalize_source_row(row, expected_ticker=ticker, expected_dimension=dimension)
                    key = source_key(item)
                    record_key = "|".join(key)
                    content_hash = fingerprint(_raw_row(item))
                    observation_id = _observation_id(record_key, content_hash)
                    payload = dict(item)
                    retention_status = row.get("_history_retention_status")
                    provenance = {}
                    if retention_status == RETAINED_OUTSIDE_SOURCE_WINDOW:
                        provenance = {
                            "history_retention_status": RETAINED_OUTSIDE_SOURCE_WINDOW,
                            "history_retention_evidence": row.get("_history_retention_evidence"),
                        }
                    connection.execute(
                        "INSERT INTO provider_observation(observation_id,run_id,provider,provider_record_key,company_id,security_id,"
                        "provider_ticker,provider_security_id,native_table,dimension,calendardate,reportperiod,fiscalperiod,"
                        "source_availability_date,observed_at_utc,fetched_at_utc,content_hash,provider_status,payload_json,provenance_json) "
                        "VALUES(?,?,'SHARADAR',?,?,?,?,?,'fundamentals',?,?,?,?,?,?,?,?,'SUCCESS',?,?)",
                        (observation_id, run_id, record_key, identity["company_id"], identity["security_id"], ticker,
                         identity["provider_security_id"], dimension, item["calendardate"], item["reportperiod"],
                         item["fiscalperiod"], item["date"], item["lastupdated"], applied_at, content_hash,
                         json.dumps(payload, sort_keys=True), json.dumps(provenance, sort_keys=True)),
                    )
                    columns = ("observation_id", "ticker", "permaticker", *REFRESH_REQUEST_FIELDS[1:])
                    values = (observation_id, ticker, identity["provider_security_id"], *[item[field] for field in REFRESH_REQUEST_FIELDS[1:]])
                    connection.execute(
                        f"INSERT INTO sharadar_fundamental_observation({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                        values,
                    )
                    inserted[dimension] += 1
            replaced.append({
                "ticker": ticker, "before_counts": before_counts,
                "after_counts": dict(inserted), "removed_physical_rows": len(removed_ids),
                "source_history_action": (merge_plans or {}).get(ticker, {}).get("action", {}),
            })
        connection.commit()
    verification = validate_provider_candidate(provider_db, histories, merge_plans=merge_plans)
    unrelated_after = _provider_unrelated_fingerprint(provider_db, tickers)
    if unrelated_before != unrelated_after:
        raise RuntimeError("REFRESH_PROVIDER_UNRELATED_STATE_CHANGED")
    return {"run_id": run_id, "ticker_count": len(tickers), "tickers": replaced, "verification": verification, "unrelated_state_unchanged": True}


def validate_provider_candidate(
    path: Path,
    histories: Mapping[str, Mapping[str, HistoryTrust]],
    *,
    merge_plans: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence = []
    retained_rows: list[dict[str, Any]] = []
    true_removal_rows: list[dict[str, Any]] = []
    retained_payload_mismatch_count = 0
    retained_provenance_valid = 0
    retained_duplicate_count = 0
    current_source_marked_retained_count = 0
    true_removal_absent = 0
    for ticker in sorted(histories):
        for dimension in REFRESH_DIMENSIONS:
            actual = load_current_history(path, ticker, dimension)
            expected = histories[ticker][dimension]
            expected_rows = (
                merge_plans[ticker]["dimensions"][dimension]["merged_rows"]
                if merge_plans is not None else expected.rows
            )
            expected_keys = {source_key(row) for row in expected_rows}
            if actual["invalid_rows"] or actual["legacy_source_version_ambiguities"]:
                raise RuntimeError(f"REFRESH_PROVIDER_CANDIDATE_AMBIGUOUS:{ticker}:{dimension}")
            if actual["current_row_count"] != len(expected_rows):
                raise RuntimeError(f"REFRESH_PROVIDER_CANDIDATE_COUNT_MISMATCH:{ticker}:{dimension}")
            if {source_key(row) for row in actual["rows"]} != expected_keys:
                raise RuntimeError(f"REFRESH_PROVIDER_CANDIDATE_KEY_MISMATCH:{ticker}:{dimension}")
            expected_hashes = history_fingerprints(expected_rows)
            if (
                actual["effective_content_fingerprint"], actual["raw_source_fingerprint"]
            ) != (
                expected_hashes["effective_content_fingerprint"],
                expected_hashes["raw_source_fingerprint"],
            ):
                raise RuntimeError(f"REFRESH_PROVIDER_CANDIDATE_FINGERPRINT_MISMATCH:{ticker}:{dimension}")
            actual_map = {source_key(row): row for row in actual["rows"]}
            source_keys = {source_key(row) for row in expected.rows}
            retained_keys = {
                source_key(row) for row in expected_rows
                if row.get("_history_retention_status") == RETAINED_OUTSIDE_SOURCE_WINDOW
            }
            actual_retained = {
                key for key, row in actual_map.items()
                if row.get("_history_retention_status") == RETAINED_OUTSIDE_SOURCE_WINDOW
            }
            if actual_retained != retained_keys:
                raise RuntimeError(f"REFRESH_PROVIDER_RETENTION_STATE_MISMATCH:{ticker}:{dimension}")
            marked_source_keys = {
                key for key in source_keys
                if actual_map[key].get("_history_retention_status")
            }
            current_source_marked_retained_count += len(marked_source_keys)
            if marked_source_keys:
                raise RuntimeError(f"REFRESH_CURRENT_SOURCE_MARKED_RETAINED:{ticker}:{dimension}")
            true_removed = {
                tuple(item[field] for field in ("ticker", "dimension", "date", "reportperiod"))
                for item in ((merge_plans or {}).get(ticker, {}).get("dimensions", {}).get(dimension, {}).get("true_removed_keys", []))
            }
            if true_removed & set(actual_map):
                raise RuntimeError(f"REFRESH_TRUE_REMOVAL_RETAINED:{ticker}:{dimension}")
            true_removal_absent += len(true_removed - set(actual_map))
            true_removal_rows.extend({
                "ticker": key[0], "dimension": key[1], "date": key[2],
                "reportperiod": key[3], "absent_from_candidate": key not in actual_map,
            } for key in sorted(true_removed))
            expected_map = {source_key(row): row for row in expected_rows}
            duplicate_count = max(0, actual["physical_row_count"] - actual["current_row_count"])
            retained_duplicate_count += duplicate_count
            if duplicate_count:
                raise RuntimeError(f"REFRESH_PROVIDER_CANDIDATE_DUPLICATE_KEYS:{ticker}:{dimension}")
            for key in sorted(retained_keys):
                actual_row = actual_map[key]
                expected_row = expected_map[key]
                payload_matches = fingerprint(_raw_row(actual_row)) == fingerprint(_raw_row(expected_row))
                provenance_valid = (
                    actual_row.get("_history_retention_status") == RETAINED_OUTSIDE_SOURCE_WINDOW
                    and actual_row.get("_history_retention_evidence")
                    == expected_row.get("_history_retention_evidence")
                )
                retained_payload_mismatch_count += int(not payload_matches)
                retained_provenance_valid += int(provenance_valid)
                if not payload_matches:
                    raise RuntimeError(f"REFRESH_RETAINED_PAYLOAD_MISMATCH:{ticker}:{dimension}")
                if not provenance_valid:
                    raise RuntimeError(f"REFRESH_RETAINED_PROVENANCE_INVALID:{ticker}:{dimension}")
                fiscal_year, fiscal_quarter = str(actual_row["fiscalperiod"]).split("-")
                retained_rows.append({
                    "ticker": ticker, "dimension": dimension,
                    "date": key[2], "reportperiod": key[3],
                    "fiscal_year": int(fiscal_year), "fiscal_quarter": fiscal_quarter,
                    "history_retention_status": actual_row.get("_history_retention_status"),
                    "provenance_valid": provenance_valid,
                    "payload_matches_previously_accepted": payload_matches,
                    "source_identity_unchanged": source_key(actual_row) == key,
                })
            evidence.append({
                "ticker": ticker, "dimension": dimension, "row_count": len(expected_rows),
                "effective_fingerprint": expected_hashes["effective_content_fingerprint"],
                "raw_fingerprint": expected_hashes["raw_source_fingerprint"],
                "current_source_key_count": len(source_keys),
                "retained_only_key_count": len(retained_keys),
                "true_removed_key_count": len(true_removed),
                "duplicate_true_keys": 0,
            })
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        orphans = connection.execute(
            "SELECT COUNT(*) FROM sharadar_fundamental_observation s LEFT JOIN provider_observation po USING(observation_id) WHERE po.observation_id IS NULL"
        ).fetchone()[0]
    if quick != "ok" or foreign or orphans:
        raise RuntimeError("REFRESH_PROVIDER_CANDIDATE_INTEGRITY_FAILED")
    expected_retained_total = len(retained_rows)
    true_removal_expected = len(true_removal_rows)
    retention_validation = {
        "expected_retained_total": expected_retained_total,
        "actual_retained_total": sum(item["retained_only_key_count"] for item in evidence),
        "retained_arq": sum(row["dimension"] == "ARQ" for row in retained_rows),
        "retained_mrq": sum(row["dimension"] == "MRQ" for row in retained_rows),
        "retained_provenance_valid": retained_provenance_valid,
        "true_removal_expected": true_removal_expected,
        "true_removal_absent": true_removal_absent,
        "retained_payload_mismatch_count": retained_payload_mismatch_count,
        "retained_duplicate_count": retained_duplicate_count,
        "current_source_marked_retained_count": current_source_marked_retained_count,
        "retained_rows": retained_rows,
        "true_removal_rows": true_removal_rows,
    }
    return {
        "histories": evidence, "retention_validation": retention_validation,
        "quick_check": quick, "foreign_key_errors": len(foreign), "orphan_children": int(orphans),
    }


def _quarter_rows(path: Path) -> dict[tuple[int, int, str], dict[str, Any]]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return {
            (int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])): dict(row)
            for row in connection.execute("SELECT q.*,f.* FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id)")
        }


def _identity_mapping(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        payload = {
            table: [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}")]
            for table, order in (
                ("company", "company_id"),
                ("security", "security_id"),
                ("ticker_alias", "alias_id"),
                ("provider_security_identity", "provider,provider_security_id"),
                ("provider_company_identity", "provider,provider_identifier_type,provider_identifier_value"),
            )
        }
    return {"fingerprint": stable_hash(payload), "company_count": len(payload["company"]), "security_count": len(payload["security"])}


def build_publication_date_preservation_map(
    rows: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> tuple[dict[tuple[int, int, str], str], dict[str, Any]]:
    preserved: dict[tuple[int, int, str], str] = {}
    counts: Counter[str] = Counter()
    repair: list[dict[str, Any]] = []
    for key, row in rows.items():
        established = row.get("first_public_result_date")
        availability = row.get("source_availability_date")
        candidate = established or availability
        try:
            if not candidate:
                raise ValueError("missing")
            date.fromisoformat(str(candidate))
        except ValueError:
            repair.append({"company_id": key[0], "fiscal_year": key[1], "fiscal_quarter": key[2], "reason": "MISSING_OR_INVALID_PUBLICATION_DATE_BASELINE"})
            continue
        preserved[key] = str(candidate)
        counts["already_established" if established else "bootstrap_eligible"] += 1
    return preserved, {**dict(counts), "repair_required": len(repair), "repair_cases": repair}


def fresh_rebuild_canonical(
    provider_db: Path, canonical_db: Path, *, applied_at: str,
    affected_company_ids: Sequence[int] = (),
) -> dict[str, Any]:
    identity_before = _identity_mapping(canonical_db)
    before = _quarter_rows(canonical_db)
    preserved_dates, bootstrap_summary = build_publication_date_preservation_map(before)
    if bootstrap_summary["repair_required"]:
        raise RuntimeError("REFRESH_PUBLISH_DATE_REPAIR_REQUIRED")
    bootstrap = Counter({key: value for key, value in bootstrap_summary.items() if isinstance(value, int)})
    with sqlite3.connect(canonical_db) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        for table in (
            "v4_ttm_input_quarter", "v4_ttm_contract", "v4_ttm_values",
            "v4_common_earnings_provenance", "v4_operating_working_capital_provenance", "v4_field_provenance",
            "v4_quarter_financials", "v4_quarter",
        ):
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                connection.execute(f"DELETE FROM {table}")
        for table in ("fundamentals_quarter_economic_regime", "fundamentals_ttm_economic_regime"):
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                connection.execute(f"DELETE FROM {table}")
        connection.commit()
    canonical = reconcile_canonical(provider_db, canonical_db, applied_at=applied_at)
    with sqlite3.connect(canonical_db) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        ensure_ttm_schema(connection)
        rows = connection.execute("SELECT quarter_id,company_id,fiscal_year,fiscal_quarter,source_availability_date FROM v4_quarter").fetchall()
        for quarter_id, company_id, fiscal_year, fiscal_quarter, availability in rows:
            key = (int(company_id), int(fiscal_year), str(fiscal_quarter))
            first_public = preserved_dates.get(key) or availability
            if not first_public:
                raise RuntimeError(f"REFRESH_NEW_QUARTER_PUBLICATION_DATE_MISSING:{key}")
            connection.execute("UPDATE v4_quarter SET first_public_result_date=? WHERE quarter_id=?", (first_public, quarter_id))
            bootstrap["preserved"] += int(key in preserved_dates)
            bootstrap["new_dates_established"] += int(key not in preserved_dates)
        connection.commit()
    ttm = rebuild_ttm(canonical_db, applied_at=applied_at)
    structural = structural_break.apply_contract(canonical_db, events=_events(), applied_at_utc=applied_at)
    after = _quarter_rows(canonical_db)
    identity_after = _identity_mapping(canonical_db)
    if identity_before != identity_after:
        raise RuntimeError("REFRESH_CANONICAL_IDENTITY_MAPPING_CHANGED")
    financial_fields = tuple(FINANCIAL_FIELDS) + (
        "gross_profit", "operating_income", "net_income", "net_income_common", "operating_cashflow",
        "free_cashflow", "cash", "total_debt", "shares_outstanding", "accounts_receivable",
        "accounts_payable", "deferred_revenue", "total_assets",
    )
    shared = before.keys() & after.keys()
    financial_changed = [key for key in shared if any(before[key].get(field) != after[key].get(field) for field in financial_fields) or before[key].get("period_end") != after[key].get("period_end")]
    availability_changed = [key for key in shared if before[key].get("source_availability_date") != after[key].get("source_availability_date")]
    changed = sorted(set(financial_changed) | set(availability_changed))
    bootstrap_only = [key for key in shared if not before[key].get("first_public_result_date") and key not in changed]
    affected = {int(value) for value in affected_company_ids}
    unexplained = [key for key in changed if key[0] not in affected] if affected else []
    unexplained.extend(key for key in (before.keys() ^ after.keys()) if affected and key[0] not in affected)
    if unexplained:
        raise RuntimeError("REFRESH_UNAFFECTED_CANONICAL_STATE_CHANGED")
    first_moved = [key for key in shared if (before[key].get("first_public_result_date") or before[key].get("source_availability_date")) != after[key].get("first_public_result_date")]
    if first_moved:
        raise RuntimeError("REFRESH_FIRST_PUBLIC_RESULT_DATE_MOVED")
    with sqlite3.connect(f"file:{canonical_db.resolve()}?mode=ro", uri=True) as connection:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        duplicates = connection.execute("SELECT COUNT(*) FROM (SELECT company_id,fiscal_year,fiscal_quarter,COUNT(*) n FROM v4_quarter GROUP BY 1,2,3 HAVING n>1)").fetchone()[0]
    if quick != "ok" or foreign or duplicates:
        raise RuntimeError("REFRESH_CANONICAL_CANDIDATE_INTEGRITY_FAILED")
    removed = sorted(before.keys() - after.keys())
    surviving_existing = len(before.keys() & after.keys())
    company_impact: dict[int, dict[str, Any]] = {}
    for company_id in sorted(affected):
        before_keys = {key for key in before if key[0] == company_id}
        after_keys = {key for key in after if key[0] == company_id}
        shared_keys = before_keys & after_keys
        latest_before = max(before_keys, key=lambda key: (key[1], int(key[2][1]))) if before_keys else None
        latest_after = max(after_keys, key=lambda key: (key[1], int(key[2][1]))) if after_keys else None
        company_impact[company_id] = {
            "latest_before": f"{latest_before[1]} {latest_before[2]}" if latest_before else None,
            "latest_after": f"{latest_after[1]} {latest_after[2]}" if latest_after else None,
            "quarters_added": len(after_keys - before_keys),
            "quarters_changed": sum(key in changed for key in shared_keys),
            "quarters_removed": len(before_keys - after_keys),
            "source_availability_date_changes": sum(key in availability_changed for key in shared_keys),
            "first_public_dates_preserved": len(shared_keys),
            "new_first_public_dates": len(after_keys - before_keys),
        }
    removed_evidence = [{
        "company_id": key[0], "fiscal_year": key[1], "fiscal_quarter": key[2],
        "prior_first_public_result_date": before[key].get("first_public_result_date") or before[key].get("source_availability_date"),
    } for key in removed]
    return {
        "canonical": canonical, "ttm": ttm, "structural": structural,
        "publication_date_bootstrap": {
            "canonical_quarters_inspected": len(before), **dict(bootstrap), "repair_required": 0,
            "bootstrapped_in_candidate": bootstrap["bootstrap_eligible"],
            "preservation_map_applied": surviving_existing,
            "preservation_map_applicable_existing_quarters": surviving_existing,
        },
        "impact": {
            "unchanged_quarters": len(shared) - len(changed), "added_quarters": len(after.keys() - before.keys()),
            "changed_quarters": len(changed), "removed_quarters": len(removed),
            "source_availability_date_changes": len(availability_changed),
            "bootstrap_only_date_changes": len(bootstrap_only),
            "first_public_result_date_preserved": bootstrap["preserved"],
            "new_first_public_result_date_established": bootstrap["new_dates_established"],
            "unexplained_unaffected_changes": len(unexplained),
        },
        "removed_quarter_publication_evidence": removed_evidence,
        "company_impact": company_impact,
        "identity_contract": {
            "before": identity_before,
            "after": identity_after,
            "company_security_identity_mapping_unchanged": True,
        },
        "quick_check": quick, "foreign_key_errors": len(foreign), "duplicate_quarters": int(duplicates),
    }


def _analysis_state(analysis_db: Path, canonical_db: Path, tickers: Sequence[str]) -> dict[str, Any]:
    with sqlite3.connect(f"file:{canonical_db.resolve()}?mode=ro", uri=True) as canonical:
        canonical.row_factory = sqlite3.Row
        identities = {str(row["current_ticker"]): int(row["company_id"]) for row in canonical.execute(
            f"SELECT current_ticker,company_id FROM security WHERE UPPER(current_ticker) IN ({','.join('?' for _ in tickers)})",
            tuple(tickers),
        )} if tickers else {}
    output = {}
    with sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for ticker in tickers:
            company_id = identities.get(ticker)
            if company_id is None:
                continue
            score = connection.execute("SELECT readiness_status,total_score FROM score_result WHERE company_id=? ORDER BY quarter_id DESC LIMIT 1", (company_id,)).fetchone()
            lifecycle = connection.execute("SELECT lifecycle_status,final_state FROM lifecycle_revised_result WHERE company_id=? ORDER BY fiscal_sequence DESC LIMIT 1", (company_id,)).fetchone()
            valuation = connection.execute("SELECT valuation_status,total_valuation_score FROM valuation_revised_result WHERE company_id=? ORDER BY fiscal_sequence DESC LIMIT 1", (company_id,)).fetchone()
            rp = connection.execute("SELECT COUNT(*) FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) WHERE r.company_id=?", (company_id,)).fetchone()[0]
            rv = connection.execute("SELECT valuation_status,current_valuation_score FROM relative_valuation_company_result r JOIN relative_valuation_active_snapshot a USING(snapshot_id) WHERE r.company_id=?", (company_id,)).fetchone()
            output[ticker] = {
                "score": dict(score) if score else None, "lifecycle": dict(lifecycle) if lifecycle else None,
                "valuation": dict(valuation) if valuation else None, "relative_position_count": int(rp),
                "relative_valuation": dict(rv) if rv else None,
            }
    return output


def _quarter_evidence(path: Path, company_id: int) -> list[dict[str, Any]]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,source_reportperiod,"
            "source_availability_date,first_public_result_date FROM v4_quarter "
            "WHERE company_id=? ORDER BY fiscal_year,fiscal_quarter",
            (company_id,),
        )]


def _source_fiscal_evidence(path: Path, ticker: str) -> list[dict[str, Any]]:
    output = []
    for dimension in REFRESH_DIMENSIONS:
        for row in load_current_history(path, ticker, dimension)["rows"]:
            output.append({
                "ticker": ticker, "dimension": dimension, "date": row["date"],
                "reportperiod": row["reportperiod"], "fiscalperiod": row["fiscalperiod"],
                "history_retention_status": row.get("_history_retention_status"),
            })
    return output


def build_test_evidence(
    *, preview: Mapping[str, Any], changed: Sequence[Mapping[str, Any]],
    provider_result: Mapping[str, Any], canonical_result: Mapping[str, Any],
    production_provider: Path, provider_candidate: Path,
    production_canonical: Path, canonical_candidate: Path,
) -> dict[str, Any]:
    validation = dict(provider_result["verification"]["retention_validation"])
    bootstrap = canonical_result["publication_date_bootstrap"]
    impact = canonical_result["impact"]
    validation.update({
        "ambiguous_removal_count": sum(
            int(item.get("source_history_action", {}).get("ambiguous_removals", 0))
            for item in changed
        ),
        "canonical_removed_quarter_count": int(impact["removed_quarters"]),
        "first_public_preservation_applicable": int(bootstrap["preservation_map_applicable_existing_quarters"]),
        "first_public_preservation_applied": int(bootstrap["preservation_map_applied"]),
        "first_public_repair_required": int(bootstrap["repair_required"]),
        "new_first_public_expected": int(
            preview.get("publication_date_state", {}).get("expected_new_quarter_initializations", 0)
        ),
        "new_first_public_actual": int(impact["new_first_public_result_date_established"]),
    })
    representatives = {}
    for item in changed:
        events = item.get("source_history_events", [])
        if not events:
            continue
        ticker = str(item["ticker"])
        company_id = int(item["identity"]["company_id"])
        canonical_before = _quarter_evidence(production_canonical, company_id)
        canonical_after = _quarter_evidence(canonical_candidate, company_id)
        before_keys = {(row["fiscal_year"], row["fiscal_quarter"]) for row in canonical_before}
        after_keys = {(row["fiscal_year"], row["fiscal_quarter"]) for row in canonical_after}
        relevant_fiscal = {
            (event["fiscal_identity"]["fiscal_year"], event["fiscal_identity"]["fiscal_quarter"])
            for event in events
        } | (before_keys ^ after_keys)

        def source_is_relevant(row: Mapping[str, Any]) -> bool:
            year, quarter = str(row["fiscalperiod"]).split("-")
            return (int(year), quarter) in relevant_fiscal

        def quarter_is_relevant(row: Mapping[str, Any]) -> bool:
            return (int(row["fiscal_year"]), str(row["fiscal_quarter"])) in relevant_fiscal

        representatives[ticker] = {
            "source_history_action": item.get("source_history_action", {}),
            "source_history_events": events,
            "retained_rows": [row for row in validation["retained_rows"] if row["ticker"] == ticker],
            "true_removal_rows": [row for row in validation["true_removal_rows"] if row["ticker"] == ticker],
            "provider_before": [
                row for row in _source_fiscal_evidence(production_provider, ticker)
                if source_is_relevant(row)
            ],
            "provider_candidate": [
                row for row in _source_fiscal_evidence(provider_candidate, ticker)
                if source_is_relevant(row)
            ],
            "canonical_before": [row for row in canonical_before if quarter_is_relevant(row)],
            "canonical_candidate": [row for row in canonical_after if quarter_is_relevant(row)],
            "canonical_impact": (
                canonical_result["company_impact"].get(company_id)
                or canonical_result["company_impact"].get(str(company_id))
                or {}
            ),
        }
    return {
        "contract_version": TEST_CONTRACT_VERSION,
        "summary": {key: value for key, value in validation.items() if key not in {"retained_rows", "true_removal_rows"}},
        "retained_rows": validation["retained_rows"],
        "true_removal_rows": validation["true_removal_rows"],
        "representatives": representatives,
    }


def _render_report(result: Mapping[str, Any]) -> str:
    downstream = result.get("downstream") or {}
    bootstrap = downstream.get("canonical", {}).get("publication_date_bootstrap", {})
    retention = downstream.get("test_evidence", {}).get("summary", {})
    representative_evidence = downstream.get("test_evidence", {}).get("representatives", {})
    lines = [
        "# Refresh Fundamentals Test on Copies", "", "## Executive Summary", "",
        f"- Preview run: `{result.get('bound_preview_run_id')}`",
        f"- Test run: `{result.get('run_id')}`",
        f"- Refresh-set fingerprint: `{result.get('preview_fingerprint')}`",
        f"- Changed known tickers: {result.get('summary_counts', {}).get('effective_changed_known', 0)}",
        f"- Source replacement tickers: {downstream.get('provider', {}).get('ticker_count', 0)}",
        f"- ARQ rows before/after: {sum(item.get('before_counts', {}).get('ARQ', 0) for item in downstream.get('provider', {}).get('tickers', []))} / {sum(item.get('after_counts', {}).get('ARQ', 0) for item in downstream.get('provider', {}).get('tickers', []))}",
        f"- MRQ rows before/after: {sum(item.get('before_counts', {}).get('MRQ', 0) for item in downstream.get('provider', {}).get('tickers', []))} / {sum(item.get('after_counts', {}).get('MRQ', 0) for item in downstream.get('provider', {}).get('tickers', []))}",
        f"- First-public dates bootstrapped: {bootstrap.get('bootstrapped_in_candidate', 0)}",
        f"- B1/full rebuild: {downstream.get('analysis', {}).get('status', 'NOT_RUN')}",
        "- Production writes: 0", "",
        "## Publication Date Bootstrap", "",
        f"- Canonical quarters inspected: {bootstrap.get('canonical_quarters_inspected', 0)}",
        f"- Bootstrap eligible: {bootstrap.get('bootstrap_eligible', 0)}",
        f"- Already established: {bootstrap.get('already_established', 0)}",
        f"- Repair required: {bootstrap.get('repair_required', 0)}", "",
        "## Explicit Invariants", "",
        "- `company/security identity mapping before candidate rebuild == after candidate rebuild`: "
        + ("true" if downstream.get("canonical", {}).get("identity_contract", {}).get("company_security_identity_mapping_unchanged") else "false"),
        f"- `first_public_result_date preservation map applied: {bootstrap.get('preservation_map_applied', 0)}/{bootstrap.get('preservation_map_applicable_existing_quarters', 0)} existing quarters`",
        "",
        "## Source-Window Retention Validation", "",
        f"- Expected newly aged-out rows: {retention.get('expected_retained_total', 0)}",
        f"- Retained in provider candidate: {retention.get('actual_retained_total', 0)}",
        f"- Retained ARQ: {retention.get('retained_arq', 0)}",
        f"- Retained MRQ: {retention.get('retained_mrq', 0)}",
        f"- Correct retained provenance: {retention.get('retained_provenance_valid', 0)}/{retention.get('expected_retained_total', 0)}",
        f"- True source removals expected: {retention.get('true_removal_expected', 0)}",
        f"- True source removals absent from candidate: {retention.get('true_removal_absent', 0)}/{retention.get('true_removal_expected', 0)}",
        f"- Ambiguous removals: {retention.get('ambiguous_removal_count', 0)}", "",
        "| Ticker | Action | Provider candidate | Canonical result |",
        "| --- | --- | --- | --- |",
    ]
    retained_examples = [
        (ticker, evidence) for ticker, evidence in sorted(representative_evidence.items())
        if evidence.get("retained_rows")
    ][:3]
    removal_examples = [
        (ticker, evidence) for ticker, evidence in sorted(representative_evidence.items())
        if evidence.get("true_removal_rows")
    ]
    for ticker, evidence in retained_examples + removal_examples:
        retained = evidence.get("retained_rows", [])
        removals = evidence.get("true_removal_rows", [])
        impact = evidence.get("canonical_impact", {})
        if retained:
            dimensions = "/".join(sorted({str(row["dimension"]) for row in retained}))
            action = "Retain outside source window"
            provider = f"retained {dimensions}"
        else:
            action = "True source-key removal"
            provider = f"{sum(bool(row.get('absent_from_candidate')) for row in removals)} keys absent"
        canonical = (
            f"+{impact.get('quarters_added', 0)} / {impact.get('quarters_changed', 0)} / "
            f"-{impact.get('quarters_removed', 0)} quarters"
        )
        lines.append(f"| {ticker} | {action} | {provider} | {canonical} |")
    lines.extend([
        "",
        "## Ticker Summary", "",
        "| Ticker | Source change | Latest quarter | ARQ rows | Canonical impact | Score before/after | Final |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ])
    before = downstream.get("analysis_before", {})
    after = downstream.get("analysis_after", {})
    for item in downstream.get("ticker_changes", []):
        ticker = item["ticker"]
        company_id = item.get("identity", {}).get("company_id")
        impact = (
            downstream.get("canonical", {}).get("company_impact", {}).get(company_id)
            or downstream.get("canonical", {}).get("company_impact", {}).get(str(company_id))
            or {}
        )
        score_before = (before.get(ticker, {}).get("score") or {}).get("total_score")
        score_after = (after.get(ticker, {}).get("score") or {}).get("total_score")
        lines.append(
            f"| {ticker} | {item['classification']} | {item.get('old_latest_fiscal_quarter')} -> {item.get('new_latest_fiscal_quarter')} | "
            f"{item.get('current_counts', {}).get('ARQ', 0)} -> {item.get('source_counts', {}).get('ARQ', 0)} | "
            f"+{impact.get('quarters_added', 0)} / {impact.get('quarters_changed', 0)} / -{impact.get('quarters_removed', 0)} | "
            f"{score_before} -> {score_after} | Tested successfully |"
        )
    lines.extend(["", "## Detailed Ticker Results", ""])
    company_impact = downstream.get("canonical", {}).get("company_impact", {})
    before = downstream.get("analysis_before", {})
    after = downstream.get("analysis_after", {})
    for item in downstream.get("ticker_changes", []):
        ticker = item["ticker"]
        company_id = item.get("identity", {}).get("company_id")
        impact = company_impact.get(company_id) or company_impact.get(str(company_id)) or {}
        prior = before.get(ticker, {})
        current = after.get(ticker, {})
        lines.extend([
            f"### {ticker}", "", "#### Source refresh", "",
            f"- Classification: {item.get('classification')}",
            f"- ARQ rows: {item.get('current_counts', {}).get('ARQ', 0)} -> {item.get('source_counts', {}).get('ARQ', 0)}",
            f"- MRQ rows: {item.get('current_counts', {}).get('MRQ', 0)} -> {item.get('source_counts', {}).get('MRQ', 0)}",
            f"- Source rows added/changed/removed: {item.get('added_count', 0)} / {item.get('changed_count', 0)} / {item.get('removed_count', 0)}",
            "", "#### Canonical impact", "",
            f"- Latest quarter: {impact.get('latest_before')} -> {impact.get('latest_after')}",
            f"- Quarters added/changed/removed: {impact.get('quarters_added', 0)} / {impact.get('quarters_changed', 0)} / {impact.get('quarters_removed', 0)}",
            "", "#### Publication date", "",
            f"- Existing first-public dates preserved: {impact.get('first_public_dates_preserved', 0)}",
            f"- New first-public dates established: {impact.get('new_first_public_dates', 0)}",
            f"- Source availability date changes: {impact.get('source_availability_date_changes', 0)}",
            "", "#### V2 analysis", "",
            f"- Score: {prior.get('score')} -> {current.get('score')}",
            f"- Lifecycle: {prior.get('lifecycle')} -> {current.get('lifecycle')}",
            f"- Valuation: {prior.get('valuation')} -> {current.get('valuation')}",
            f"- RP result count: {prior.get('relative_position_count')} -> {current.get('relative_position_count')}",
            f"- RV: {prior.get('relative_valuation')} -> {current.get('relative_valuation')}",
            "", "#### Final result", "", "- Tested successfully", "",
        ])
    lines.extend(["## Safety", "", "Production databases were read and copied only. Temporary candidate databases were removed after evidence capture.", ""])
    return "\n".join(lines)


def run_apply(
    *, preview_payload_path: Path, preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(), run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT, client: SharadarClient | None = None,
    confirm_apply: bool = False, progress_callback: ProgressCallback | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    if not confirm_apply:
        raise PermissionError("REFRESH_TEST_CONFIRMATION_REQUIRED")
    request = _request()
    run_id = stable_run_id(AdminOperationType.REFRESH_FUNDAMENTALS, preview_fingerprint, suffix="test")
    writer = AdminRunWriter(run_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=run_root)
    progress = ProgressTracker(
        run_id=run_id, operation_type=AdminOperationType.REFRESH_FUNDAMENTALS,
        run_dir=writer.run_dir, stages=REFRESH_FUNDAMENTALS_TEST_STAGES,
        callback=progress_callback,
    )
    writer.write_json("request.json", request.as_dict() | {"options": {"contract_version": TEST_CONTRACT_VERSION, "mode": "COPY_ONLY_APPLY"}})
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Refresh copy Test request recorded.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Refresh copy Test started.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Production write boundary will not be crossed.", preview_fingerprint=preview_fingerprint)
    before_files = _production_file_state(source_paths)
    started = utc_now()
    lane_dir = temp_root / run_id
    failed_stage = ProgressStage.PREVIEW_BINDING
    api = client or SharadarClient()
    try:
        progress.running(failed_stage, "Validating bound Refresh Preview.")
        preview = _load_bound_preview(preview_payload_path, preview_fingerprint, run_root)
        progress.completed(failed_stage, "Bound Preview is authorized for Test on copies.")

        failed_stage = ProgressStage.SOURCE_REVALIDATION
        progress.running(failed_stage, "Revalidating complete Sharadar source state.")
        revalidated = revalidate_bound_source(preview, source_paths, api)
        writer.write_json(
            "source_revalidation.json",
            {key: value for key, value in revalidated.items() if key not in {"histories", "merge_plans"}},
        )
        progress.completed(failed_stage, "Sharadar source still matches Preview.")

        changed = [item for item in revalidated["ticker_changes"] if item["classification"] in REPLACEMENT_CLASSES]
        changed_tickers = [item["ticker"] for item in changed]
        identities = {item["ticker"]: item["identity"] for item in changed}
        selected_histories = {ticker: revalidated["histories"][ticker] for ticker in changed_tickers}
        selected_merge_plans = {ticker: revalidated["merge_plans"][ticker] for ticker in changed_tickers}

        failed_stage = ProgressStage.COPY_PROVIDER
        progress.running(failed_stage, "Copying provider and stable read-only authorities.")
        lane_dir.mkdir(parents=True, exist_ok=False)
        provider_candidate = lane_dir / "provider_candidate.db"
        canonical_candidate = lane_dir / "canonical_candidate.db"
        with _background_heartbeat(progress, "Database copying is still running."):
            copies = {
                "provider": online_backup(source_paths.provider_db, provider_candidate),
                "canonical": online_backup(source_paths.canonical_db, canonical_candidate),
            }
            read_only_copies, read_only_evidence = prepare_full_v2_read_only_copies(
                source_paths, lane_dir=lane_dir,
            )
            copies.update(read_only_evidence)
        writer.write_json("copy_manifest.json", copies)
        progress.completed(failed_stage, "Disposable database copies created.")

        applied_at = utc_now()
        failed_stage = ProgressStage.PROVIDER_REPLACEMENT
        progress.running(failed_stage, "Replacing complete ARQ/MRQ histories in provider candidate.", total_items=len(changed_tickers))
        with _background_heartbeat(progress, "Provider complete-history replacement is still running."):
            provider_result = replace_provider_histories(
                provider_candidate, selected_histories, identities,
                applied_at=applied_at, merge_plans=selected_merge_plans,
            )
        writer.write_json("provider_replacement_summary.json", provider_result)
        progress.completed(failed_stage, "Provider candidate replacement completed.", processed_items=len(changed_tickers), total_items=len(changed_tickers))

        failed_stage = ProgressStage.PROVIDER_VALIDATION
        progress.running(failed_stage, "Validating provider candidate integrity and exact source equivalence.")
        progress.completed(failed_stage, "Provider candidate is exact and relationally valid.")

        failed_stage = ProgressStage.PUBLISH_DATE_BOOTSTRAP
        progress.running(failed_stage, "Bootstrapping immutable first-public dates on canonical candidate.")
        # Bootstrap eligibility belongs to the pre-refresh production pair. A
        # candidate winner may legitimately move source_availability_date.
        audit = audit_publish_date_bootstrap(source_paths)
        if audit["exception_count"]:
            raise RuntimeError("REFRESH_PUBLISH_DATE_REPAIR_REQUIRED")

        failed_stage = ProgressStage.CANONICAL_REBUILD
        progress.running(failed_stage, "Fresh-building deletion-safe canonical, TTM and structural state.")
        with _background_heartbeat(progress, "Fresh canonical rebuild is still running."):
            canonical_result = fresh_rebuild_canonical(
                provider_candidate, canonical_candidate, applied_at=applied_at,
                affected_company_ids=[int(identity["company_id"]) for identity in identities.values()],
            )
        writer.write_json("publish_date_bootstrap_summary.json", canonical_result["publication_date_bootstrap"])
        writer.write_json("canonical_rebuild_summary.json", canonical_result)
        progress.completed(failed_stage, "Fresh canonical candidate rebuilt.", processed_rows=canonical_result["canonical"]["canonical_rows"])

        failed_stage = ProgressStage.CANONICAL_VALIDATION
        progress.running(failed_stage, "Validating canonical identity, dates, deletion safety and TTM.")
        progress.completed(failed_stage, "Canonical candidate validation completed.")

        failed_stage = ProgressStage.ANALYSIS_REBUILD
        progress.running(failed_stage, "Building complete V2, RP V2 and RV analysis candidate.")
        analysis_before = _analysis_state(source_paths.analysis_db, source_paths.canonical_db, changed_tickers)
        candidate_paths = BatchAddTickerPaths(
            provider_candidate, canonical_candidate, lane_dir / "unused_analysis.db",
            read_only_copies["market"], read_only_copies["taxonomy"],
        )
        with _background_heartbeat(progress, "Full V2, RP V2 and RV rebuild is still running."):
            analysis_result = run_full_v2_downstream(
                candidate_paths.as_dict(), output=lane_dir / "analysis_rebuild", as_of_date=as_of_date or date.today().isoformat(),
            )
        analysis_candidate = Path(analysis_result["candidate_analysis_db"])
        progress.completed(failed_stage, "Full V2, RP V2 and RV candidate built.")

        failed_stage = ProgressStage.ANALYSIS_VALIDATION
        progress.running(failed_stage, "Validating B1/full analysis result.")
        if analysis_result["status"] != "READY" or analysis_result["invocation_counts"]["full_v2_rebuild"] != 1:
            raise RuntimeError("REFRESH_FULL_V2_REBUILD_NOT_READY")
        analysis_after = _analysis_state(analysis_candidate, canonical_candidate, changed_tickers)
        progress.completed(failed_stage, "B1/full analysis candidate is READY.")

        failed_stage = ProgressStage.IMPACT_COMPARISON
        progress.running(failed_stage, "Comparing source, canonical and analytical outcomes.")
        test_evidence = build_test_evidence(
            preview=preview, changed=changed, provider_result=provider_result,
            canonical_result=canonical_result,
            production_provider=source_paths.provider_db, provider_candidate=provider_candidate,
            production_canonical=source_paths.canonical_db, canonical_candidate=canonical_candidate,
        )
        downstream = {
            "provider": provider_result, "canonical": canonical_result, "analysis": analysis_result,
            "analysis_before": analysis_before, "analysis_after": analysis_after, "ticker_changes": changed,
            "test_evidence": test_evidence,
            "legacy_provider_compaction": provider_key_diagnostics(source_paths.provider_db),
        }
        deletion_evidence = []
        removed_quarters = canonical_result["removed_quarter_publication_evidence"]
        for item in changed:
            if not item.get("removed_count"):
                continue
            ticker = item["ticker"]
            company_id = int(item["identity"]["company_id"])
            candidate_keys = {
                source_key(row)
                for dimension in REFRESH_DIMENSIONS
                for row in load_current_history(provider_candidate, ticker, dimension)["rows"]
            }
            prior_keys = [tuple(key[field] for field in ("ticker", "dimension", "date", "reportperiod")) for key in item["removed_keys"]]
            deletion_evidence.append({
                "ticker": ticker,
                "complete_source_histories": {dimension: selected_histories[ticker][dimension].evidence() for dimension in REFRESH_DIMENSIONS},
                "prior_source_keys": item["removed_keys"],
                "production_provider_contained_prior_rows": True,
                "candidate_removed_keys_absent": all(key not in candidate_keys for key in prior_keys),
                "canonical_removed_quarter_evidence": [row for row in removed_quarters if int(row["company_id"]) == company_id],
                "unrelated_provider_state_unchanged": provider_result["unrelated_state_unchanged"],
            })
        downstream["source_deletion_evidence"] = deletion_evidence
        writer.write_json("refresh_test_evidence.json", test_evidence)
        writer.write_json("source_deletion_evidence.json", deletion_evidence)
        writer.write_json("analysis_outcome_summary.json", {"before": analysis_before, "after": analysis_after, "rebuild": analysis_result})
        writer.write_json("ticker_impact_summary.json", changed)
        progress.completed(failed_stage, "Impact comparison completed.")

        failed_stage = ProgressStage.REPORT
        progress.running(failed_stage, "Writing durable copy-Test evidence.")
        preview_run_id = preview_payload_path.resolve().parent.name
        counts = _summary_counts(revalidated["ticker_changes"])
        result_obj = AdminFinalResult(
            run_id=run_id, operation_type=AdminOperationType.REFRESH_FUNDAMENTALS,
            outcome=AdminStatus.COMPLETED, mode="COPY_ONLY_APPLY", started_at_utc=started,
            completed_at_utc=utc_now(), preview_fingerprint=preview_fingerprint,
            request=request.as_dict(), summary_counts=counts,
            rollback={"status": "NOT_REQUIRED", "write_boundary_crossed": False}, downstream=downstream,
            artifacts={
                "source_revalidation": str(writer.run_dir / "source_revalidation.json"),
                "refresh_test_evidence": str(writer.run_dir / "refresh_test_evidence.json"),
                "operation_report": str(writer.run_dir / "operation_report.md"),
            },
            recommended_next_action="Production update is not yet enabled for Refresh Fundamentals.",
        )
        result = result_obj.as_dict() | {
            "artifact_dir": str(writer.run_dir), "bound_preview_run_id": preview_run_id,
            "trigger_source": "MANUAL",
            "production_writes": 0, "database_safety": "COPY_ONLY",
        }
        after_files = _production_file_state(source_paths)
        result["production_file_state_unchanged"] = before_files == after_files
        if not result["production_file_state_unchanged"]:
            raise RuntimeError("PRODUCTION_FILE_STATE_CHANGED_DURING_REFRESH_TEST")
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_report(result))
        progress.completed(failed_stage, "Durable Test evidence written.")
        failed_stage = ProgressStage.CLEANUP
        progress.running(failed_stage, "Removing phase-owned candidate databases.")
        shutil.rmtree(lane_dir)
        progress.completed(failed_stage, "Candidate databases removed.")
        writer.checkpoint(RunStage.COMPLETED, message="Refresh Test on copies completed.", preview_fingerprint=preview_fingerprint, counters=counts)
        progress.running(ProgressStage.COMPLETED, "Refresh Test on copies completed.")
        progress.completed(ProgressStage.COMPLETED, "Refresh Test on copies completed.")
        writer.write_exit_code(0)
        writer.write_manifest()
        return result
    except Exception as exc:
        writer.write_error(exc)
        if lane_dir.exists():
            shutil.rmtree(lane_dir, ignore_errors=True)
        progress.failed(failed_stage, "Refresh Test stopped; production remained unchanged.", errors=(f"{type(exc).__name__}: {exc}",))
        message = "Sharadar fundamentals changed after Preview. Run Preview again before Test on copies." if isinstance(exc, StaleRefreshPreview) else "Review the Test diagnostics and run Preview again before retrying."
        result = AdminFinalResult(
            run_id=run_id, operation_type=AdminOperationType.REFRESH_FUNDAMENTALS, outcome=AdminStatus.FAILED,
            mode="COPY_ONLY_APPLY", started_at_utc=started, completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint, request=request.as_dict(), summary_counts={"failed": 1},
            rollback={"status": "NOT_REQUIRED", "write_boundary_crossed": False},
            artifacts={"error": str(writer.run_dir / "error.json")}, recommended_next_action=message,
            errors=({"type": type(exc).__name__, "message": str(exc)},),
        ).as_dict() | {
            "artifact_dir": str(writer.run_dir), "failed_stage": failed_stage.value,
            "trigger_source": "MANUAL",
            "production_writes": 0, "database_safety": "COPY_ONLY",
            "production_file_state_unchanged": before_files == _production_file_state(source_paths),
        }
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_report(result))
        writer.write_exit_code(2)
        writer.write_manifest()
        return result
