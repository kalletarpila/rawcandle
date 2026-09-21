"""Provider-to-canonical company CIK synchronization administration workflow."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import (
    ADMIN_RUN_ROOT,
    ADMIN_TEMP_ROOT,
    AdminRunWriter,
    stable_run_id,
)
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import (
    AdminOperationType,
    RunStage,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.production_transaction import (
    BACKUP_ROOT as ADMIN_BACKUP_ROOT,
    production_lock,
)
from rawcandle.fundamentals.admin.provider_cik import extract_sharadar_cik, normalize_cik
from rawcandle.fundamentals.admin.publication_journal import (
    ACTIVE_JOURNAL_PATH,
    fsync_directory,
    fsync_file,
    guard_production_writes,
    sha256_file,
    sqlite_verification,
)
from rawcandle.fundamentals.phase13b_foundation import online_backup


OPERATION = AdminOperationType.SYNCHRONIZE_PROVIDER_CIK
CONTRACT_VERSION = "PHASE13G3_17_PROVIDER_CANONICAL_CIK_SYNC_V1"
CONFIRMATION_TOKEN = "CONFIRM_PRODUCTION_PROVIDER_CIK_SYNC"
TEMP_ROOT = ADMIN_TEMP_ROOT / "provider_cik_sync"
BACKUP_ROOT = ADMIN_BACKUP_ROOT / "provider_cik_sync"
HISTORICAL_REFERENCE = {
    "DMRC", "FC", "FUBO", "GBX", "HUBG", "LITS", "MAGN", "MCFT",
    "NEUP", "NTNX", "PFGC", "SNDK", "SR", "UNF", "XOM", "XPRO",
}

ProgressCallback = Callable[[Mapping[str, Any]], None]


class CikSyncError(RuntimeError):
    pass


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _hash_rows(rows: Sequence[Sequence[Any]] | Any) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(tuple(row), separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _table_fingerprint(connection: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]
    if not columns:
        return _hash_rows(())
    selected = ",".join(f'"{column}"' for column in columns)
    ordered = ",".join(f'"{column}"' for column in columns)
    return _hash_rows(connection.execute(f'SELECT {selected} FROM "{table}" ORDER BY {ordered}'))


def _canonical_fingerprints(path: Path) -> dict[str, str]:
    with _readonly(path) as connection:
        tables = [str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        by_table = {table: _table_fingerprint(connection, table) for table in tables}
    non_target = hashlib.sha256()
    identity_format_tables = {"company", "company_cik", "provider_company_identity"}
    for table in sorted(name for name in by_table if name not in identity_format_tables):
        non_target.update(table.encode("utf-8"))
        non_target.update(by_table[table].encode("ascii"))
    with _readonly(path) as connection:
        company_semantic = _hash_rows(
            (
                row[0],
                (
                    f"SEC_CIK:{normalize_cik(str(row[1]).removeprefix('SEC_CIK:'))}"
                    if str(row[1]).startswith("SEC_CIK:")
                    and normalize_cik(str(row[1]).removeprefix("SEC_CIK:"))
                    else row[1]
                ),
                *row[2:],
            )
            for row in connection.execute(
                "SELECT company_id,company_key,company_name,status,created_at_utc,updated_at_utc "
                "FROM company ORDER BY company_id"
            )
        )
        provider_company_semantic_rows = [
            (
                row[0], row[1],
                normalize_cik(row[2]) if row[1] == "CIK" else row[2],
                row[3], row[4], row[5], row[6],
                normalize_cik(row[7]) if row[1] == "CIK" else row[7],
                row[8],
            )
            for row in connection.execute(
                "SELECT provider,provider_identifier_type,provider_identifier_value,company_id,"
                "provider_ticker,source,source_type,source_value,created_at_utc "
                "FROM provider_company_identity ORDER BY provider,provider_identifier_type,provider_identifier_value"
            )
        ]
        provider_company_semantic = _hash_rows(sorted(
            provider_company_semantic_rows,
            key=lambda row: json.dumps(row, separators=(",", ":"), default=str),
        ))
    return {
        "company_cik": by_table.get("company_cik", _hash_rows(())),
        "non_target_canonical": non_target.hexdigest(),
        "company": by_table.get("company", _hash_rows(())),
        "company_semantic": company_semantic,
        "provider_company_identity": by_table.get("provider_company_identity", _hash_rows(())),
        "provider_company_identity_semantic": provider_company_semantic,
        "security": by_table.get("security", _hash_rows(())),
        "ticker_alias": by_table.get("ticker_alias", _hash_rows(())),
        "provider_security_identity": by_table.get("provider_security_identity", _hash_rows(())),
        "v4_quarter": by_table.get("v4_quarter", _hash_rows(())),
        "v4_quarter_financials": by_table.get("v4_quarter_financials", _hash_rows(())),
    }


def _database_state(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256_file(path),
    }


def _provider_metadata(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    by_permaticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts = {"all_stocks": 0, "all_stocks_with_cik": 0, "active_stocks": 0, "active_stocks_with_cik": 0, "fundamentals": 0, "fundamentals_with_cik": 0}
    with _readonly(path) as connection:
        rows = connection.execute(
            "SELECT table_name,ticker,permaticker,name,exchange,isdelisted,category,secfilings,lastupdated "
            "FROM sharadar_ticker_metadata ORDER BY table_name,ticker,permaticker"
        )
        for raw in rows:
            row = dict(raw)
            extracted = extract_sharadar_cik(row.get("secfilings"))
            row["cik_extraction"] = extracted.as_dict()
            table = str(row.get("table_name") or "").lower()
            if table == "stocks":
                counts["all_stocks"] += 1
                counts["all_stocks_with_cik"] += int(extracted.status == "AVAILABLE")
                if str(row.get("isdelisted") or "").upper() == "N":
                    counts["active_stocks"] += 1
                    counts["active_stocks_with_cik"] += int(extracted.status == "AVAILABLE")
            elif table == "fundamentals":
                counts["fundamentals"] += 1
                counts["fundamentals_with_cik"] += int(extracted.status == "AVAILABLE")
                by_permaticker[str(row.get("permaticker") or "")].append(row)
    return by_permaticker, counts


def audit(paths: BatchAddTickerPaths) -> dict[str, Any]:
    metadata, provider_counts = _provider_metadata(paths.provider_db)
    with _readonly(paths.canonical_db) as connection:
        company_total = int(connection.execute("SELECT COUNT(*) FROM company").fetchone()[0])
        company_with_cik = int(connection.execute("SELECT COUNT(DISTINCT company_id) FROM company_cik").fetchone()[0])
        active_rows = [dict(row) for row in connection.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,"
            "psi.provider_security_id permaticker,psi.provider_ticker "
            "FROM security s JOIN company c USING(company_id) "
            "LEFT JOIN provider_security_identity psi ON psi.security_id=s.security_id AND psi.provider='SHARADAR' "
            "WHERE s.active=1 ORDER BY c.company_id,s.security_id"
        )]
        canonical_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
        noncanonical_count = 0
        for row in connection.execute(
            "SELECT company_id,cik_normalized,cik_display,status,source,source_type,source_value "
            "FROM company_cik ORDER BY company_id,cik_normalized"
        ):
            item = dict(row)
            item["normalized_comparable"] = normalize_cik(item["cik_normalized"])
            noncanonical_count += int(item["normalized_comparable"] != item["cik_normalized"])
            canonical_rows[int(item["company_id"])].append(item)
        provider_company_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in connection.execute(
            "SELECT provider,provider_identifier_type,provider_identifier_value,company_id,source_value "
            "FROM provider_company_identity WHERE provider_identifier_type='CIK' "
            "ORDER BY company_id,provider,provider_identifier_value"
        ):
            item = dict(row)
            item["normalized_comparable"] = normalize_cik(item["provider_identifier_value"])
            provider_company_rows[int(item["company_id"])].append(item)

    active_by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
    linked = linked_with_cik = 0
    for row in active_rows:
        active_by_company[int(row["company_id"])].append(row)
        if row.get("permaticker"):
            linked += 1
            source_rows = metadata.get(str(row["permaticker"]), [])
            available = {
                item["cik_extraction"]["cik_normalized"] for item in source_rows
                if item["cik_extraction"]["status"] == "AVAILABLE"
            }
            linked_with_cik += int(bool(available))

    preliminary: list[dict[str, Any]] = []
    cik_to_companies: dict[str, set[int]] = defaultdict(set)
    for company_id, securities in active_by_company.items():
        provider_rows: list[dict[str, Any]] = []
        for security in securities:
            for row in metadata.get(str(security.get("permaticker") or ""), []):
                provider_rows.append({
                    "security_id": security["security_id"],
                    "current_ticker": security["current_ticker"],
                    "permaticker": security.get("permaticker"),
                    "provider_ticker": row.get("ticker"),
                    "source_metadata_type": row.get("table_name"),
                    "secfilings": row.get("secfilings"),
                    "cik_extraction": row["cik_extraction"],
                })
        provider_ciks = sorted({
            row["cik_extraction"]["cik_normalized"] for row in provider_rows
            if row["cik_extraction"]["status"] == "AVAILABLE"
        })
        canonical_items = canonical_rows.get(company_id, [])
        canonical_ciks = sorted({
            row["normalized_comparable"] for row in canonical_items
            if row["normalized_comparable"] is not None
        })
        invalid_canonical = any(row["normalized_comparable"] is None for row in canonical_items)
        for cik in provider_ciks:
            cik_to_companies[cik].add(company_id)
        preliminary.append({
            "company_id": company_id,
            "company_name": securities[0]["company_name"],
            "company_key": securities[0]["company_key"],
            "security_ids": [int(row["security_id"]) for row in securities],
            "tickers": [str(row["current_ticker"]) for row in securities],
            "provider_rows": provider_rows,
            "provider_ciks": provider_ciks,
            "canonical_ciks": canonical_ciks,
            "canonical_rows": canonical_items,
            "provider_company_identity_rows": provider_company_rows.get(company_id, []),
            "invalid_canonical_cik": invalid_canonical,
        })

    items: list[dict[str, Any]] = []
    for item in preliminary:
        provider_ciks = item["provider_ciks"]
        canonical_ciks = item["canonical_ciks"]
        canonical_item = item["canonical_rows"][0] if len(item["canonical_rows"]) == 1 else None
        provider_identity_rows = item["provider_company_identity_rows"]
        provider_identity_ciks = {
            row["normalized_comparable"] for row in provider_identity_rows
            if row["normalized_comparable"] is not None
        }
        company_key = str(item["company_key"] or "")
        company_key_cik = normalize_cik(company_key.removeprefix("SEC_CIK:")) if company_key.startswith("SEC_CIK:") else None
        identity_reference = canonical_ciks[0] if len(canonical_ciks) == 1 else (
            provider_ciks[0] if len(provider_ciks) == 1 else None
        )
        identity_representation_conflict = bool(
            identity_reference
            and (
                any(row["normalized_comparable"] is None for row in provider_identity_rows)
                or len(provider_identity_ciks) > 1
                or (provider_identity_ciks and provider_identity_ciks != {identity_reference})
                or (company_key.startswith("SEC_CIK:") and company_key_cik != identity_reference)
            )
        )
        noncanonical_identity_representation = bool(
            identity_reference
            and (
                (
                    canonical_item
                    and (
                        str(canonical_item["cik_normalized"]) != identity_reference
                        or str(canonical_item["cik_display"]) != identity_reference
                        or (
                            normalize_cik(canonical_item.get("source_value")) == identity_reference
                            and canonical_item.get("source_value") != identity_reference
                        )
                    )
                )
                or any(
                    row["provider_identifier_value"] != identity_reference
                    or (
                        normalize_cik(row.get("source_value")) == identity_reference
                        and row.get("source_value") != identity_reference
                    )
                    for row in provider_identity_rows
                )
                or (
                    company_key.startswith("SEC_CIK:")
                    and company_key != f"SEC_CIK:{identity_reference}"
                )
            )
        )
        formatting_only = bool(
            canonical_item
            and canonical_ciks
            and provider_ciks == canonical_ciks
            and noncanonical_identity_representation
            and not identity_representation_conflict
        )
        if item["invalid_canonical_cik"] or len(canonical_ciks) > 1 or identity_representation_conflict:
            classification = "CANONICAL_IDENTITY_CONFLICT"
        elif len(provider_ciks) > 1:
            classification = "REVIEW_REQUIRED_CIK_CONFLICT"
        elif provider_ciks and len(cik_to_companies[provider_ciks[0]]) > 1:
            classification = "REVIEW_REQUIRED_CIK_MULTI_COMPANY"
        elif not canonical_ciks and not provider_ciks:
            classification = "PROVIDER_CIK_UNAVAILABLE"
        elif not canonical_ciks:
            classification = "SYNC_ELIGIBLE"
        elif not provider_ciks:
            classification = "PROVIDER_CIK_UNAVAILABLE_CANONICAL_PRESENT"
        elif formatting_only:
            classification = "FORMAT_NORMALIZATION_ELIGIBLE"
        elif canonical_ciks[0] == provider_ciks[0]:
            classification = "ALREADY_IN_SYNC"
        else:
            classification = "REVIEW_REQUIRED_CIK_CONFLICT"
        item["classification"] = classification
        item["proposed_cik"] = provider_ciks[0] if classification in {
            "SYNC_ELIGIBLE", "FORMAT_NORMALIZATION_ELIGIBLE",
        } else None
        items.append(item)

    active_missing = [item for item in items if not item["canonical_ciks"] and not item["invalid_canonical_cik"]]
    eligible = [item for item in items if item["classification"] == "SYNC_ELIGIBLE"]
    format_eligible = [item for item in items if item["classification"] == "FORMAT_NORMALIZATION_ELIGIBLE"]
    unavailable = [item for item in active_missing if item["classification"] == "PROVIDER_CIK_UNAVAILABLE"]
    review = [item for item in items if item["classification"].startswith("REVIEW_REQUIRED") or item["classification"] == "CANONICAL_IDENTITY_CONFLICT"]
    current_missing_tickers = {ticker for item in active_missing for ticker in item["tickers"]}
    counts = {
        "canonical_companies": company_total,
        "canonical_companies_with_cik": company_with_cik,
        "canonical_companies_missing_cik": company_total - company_with_cik,
        "active_securities": len(active_rows),
        "active_securities_with_company_cik": sum(bool(canonical_rows.get(int(row["company_id"]))) for row in active_rows),
        "active_securities_missing_company_cik": sum(not bool(canonical_rows.get(int(row["company_id"]))) for row in active_rows),
        "provider_identities_linked_to_active_securities": linked,
        "linked_provider_identities_with_cik": linked_with_cik,
        "linked_provider_identities_without_cik": linked - linked_with_cik,
        "sync_eligible": len(eligible),
        "format_normalization_eligible": len(format_eligible),
        "already_in_sync": sum(item["classification"] == "ALREADY_IN_SYNC" for item in items),
        "provider_cik_unavailable": len(unavailable),
        "review_required": len(review),
        "noncanonical_existing_cik_rows": noncanonical_count,
    }
    proposed = [{
        "action": (
            "BACKFILL_MISSING_CIK" if item["classification"] == "SYNC_ELIGIBLE"
            else "NORMALIZE_CIK_FORMAT"
        ),
        "company_id": item["company_id"],
        "company_name": item["company_name"],
        "security_ids": item["security_ids"],
        "tickers": item["tickers"],
        "provider_cik": item["proposed_cik"],
        "provider_rows": item["provider_rows"],
        "canonical_rows": item["canonical_rows"],
        "provider_company_identity_rows": item["provider_company_identity_rows"],
        "company_key": item["company_key"],
    } for item in eligible + format_eligible]
    binding = fingerprint({
        "counts": counts,
        "items": [{
            "company_id": item["company_id"],
            "security_ids": item["security_ids"],
            "tickers": item["tickers"],
            "provider_ciks": item["provider_ciks"],
            "canonical_ciks": item["canonical_ciks"],
            "classification": item["classification"],
        } for item in items],
        "proposed_changes": proposed,
    })
    return {
        "counts": counts,
        "provider_metadata_counts": provider_counts,
        "items": items,
        "proposed_changes": proposed,
        "binding_fingerprint": binding,
        "historical_reference": {
            "expected_tickers": sorted(HISTORICAL_REFERENCE),
            "accounted_for": sorted(HISTORICAL_REFERENCE & current_missing_tickers),
            "missing_from_current_gap": sorted(HISTORICAL_REFERENCE - current_missing_tickers),
            "all_accounted_for": HISTORICAL_REFERENCE <= current_missing_tickers,
        },
    }


def _summary_counts(audit_result: Mapping[str, Any]) -> dict[str, int]:
    return {key: int(value) for key, value in (audit_result.get("counts") or {}).items()}


def _preview_fingerprint(audit_result: Mapping[str, Any]) -> str:
    return fingerprint({
        "contract_version": CONTRACT_VERSION,
        "binding_fingerprint": audit_result["binding_fingerprint"],
        "proposed_changes": audit_result["proposed_changes"],
    })


def _emit(callback: ProgressCallback | None, run_id: str, number: int, stage: str, state: str, message: str) -> None:
    if callback:
        callback({
            "run_id": run_id,
            "operation_type": OPERATION.value,
            "current_stage_number": number,
            "total_declared_stages": 3,
            "current_stage_id": stage,
            "stage_state": state,
            "message": message,
        })


def _render_report(result: Mapping[str, Any]) -> str:
    current = result.get("after_audit") or result.get("audit") or {}
    before = result.get("before_audit") or result.get("audit") or {}
    counts = current.get("counts") or before.get("counts") or result.get("summary_counts") or {}
    lines = [
        "# Provider-to-Canonical CIK Synchronization",
        "", "## Executive Summary", "",
        f"- Mode: {result.get('mode')}",
        f"- Outcome: {result.get('outcome')}",
        f"- Production changed: {'Yes' if result.get('production_changed') else 'No'}",
        f"- Canonical companies missing CIK: {counts.get('canonical_companies_missing_cik', 0)}",
        f"- Active securities missing company CIK: {counts.get('active_securities_missing_company_cik', 0)}",
        f"- Synchronization eligible: {counts.get('sync_eligible', 0)}",
        f"- Formatting-only normalization eligible: {counts.get('format_normalization_eligible', 0)}",
        f"- Already in sync: {counts.get('already_in_sync', 0)}",
        f"- Provider CIK unavailable: {counts.get('provider_cik_unavailable', 0)}",
        f"- Review/conflict: {counts.get('review_required', 0)}",
        f"- Existing noncanonical CIK representations (reported, not changed): {counts.get('noncanonical_existing_cik_rows', 0)}",
        "", "## Affected Companies", "",
    ]
    items = before.get("items") or current.get("items") or []
    affected = [item for item in items if item.get("classification") in {
        "SYNC_ELIGIBLE", "FORMAT_NORMALIZATION_ELIGIBLE", "PROVIDER_CIK_UNAVAILABLE", "REVIEW_REQUIRED_CIK_CONFLICT",
        "REVIEW_REQUIRED_CIK_MULTI_COMPANY", "CANONICAL_IDENTITY_CONFLICT",
    }]
    if not affected:
        lines.append("- None")
    for item in affected:
        lines.extend([
            f"- {', '.join(item.get('tickers') or [])} / company_id={item.get('company_id')}: {item.get('classification')}",
            f"  provider CIK: {', '.join(item.get('provider_ciks') or []) or 'unavailable'}; canonical CIK: {', '.join(item.get('canonical_ciks') or []) or 'missing'}",
        ])
    validation = result.get("validation") or {}
    lines.extend([
        "", "## Safety And Validation", "",
        f"- Zero-write Preview: {'Yes' if result.get('mode') == 'PREVIEW' else 'Not applicable'}",
        f"- Updated canonical companies: {result.get('updated_count', 0)}",
        f"- Non-target canonical state unchanged: {validation.get('non_target_canonical_unchanged', 'Not run')}",
        f"- Provider unchanged: {validation.get('provider_unchanged', 'Not run')}",
        f"- Analysis unchanged: {validation.get('analysis_unchanged', 'Not run')}",
        f"- SQLite quick_check: {validation.get('quick_check', (current.get('sqlite') or {}).get('quick_check', 'Not run'))}",
        f"- Foreign-key errors: {validation.get('foreign_key_errors', (current.get('sqlite') or {}).get('foreign_key_errors', 'Not run'))}",
        f"- Candidate/temp cleanup: {result.get('cleanup_status', 'Not applicable')}",
        "", "## Next Step", "",
    ])
    if result.get("mode") == "PREVIEW" and result.get("outcome") == "COMPLETED":
        lines.append("Run Test on copies after reviewing every eligible and review-required company above.")
    elif result.get("mode") == "COPY_ONLY_APPLY":
        lines.append("Production update is available only for this exact tested Preview.")
    elif result.get("mode") == "PRODUCTION_APPLY":
        lines.append("Production synchronization completed; retain the verified rollback backup pending operator acceptance.")
    else:
        lines.append("No update is required.")
    lines.append("")
    return "\n".join(lines)


def _finalize(writer: AdminRunWriter, result: dict[str, Any], *, exit_code: int = 0) -> dict[str, Any]:
    result["artifact_dir"] = str(writer.run_dir)
    result["report_filename"] = "operation_report.md"
    if result.get("mode") == "PREVIEW":
        result["preview_payload_path"] = str(writer.run_dir / "result.json")
    writer.write_json("result.json", result)
    writer.write_text("operation_report.md", _render_report(result))
    writer.write_exit_code(exit_code)
    writer.write_manifest()
    return result


def run_preview(
    *, paths: BatchAddTickerPaths | None = None, run_root: Path = ADMIN_RUN_ROOT,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    paths = paths or BatchAddTickerPaths()
    started = utc_now()
    request_fingerprint = fingerprint({"operation": OPERATION.value, "provider": str(paths.provider_db), "canonical": str(paths.canonical_db)})
    run_id = stable_run_id(OPERATION, request_fingerprint)
    writer = AdminRunWriter(run_id, OPERATION, root=run_root)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="CIK synchronization Preview request recorded.")
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Auditing provider-to-canonical CIK state.")
    _emit(progress_callback, run_id, 1, "AUDIT", "RUNNING", "Reading provider and canonical identity state.")
    production_before = {role: _database_state(path) for role, path in {
        "provider": paths.provider_db, "canonical": paths.canonical_db, "analysis": paths.analysis_db,
    }.items()}
    audit_result = audit(paths)
    production_after = {role: _database_state(path) for role, path in {
        "provider": paths.provider_db, "canonical": paths.canonical_db, "analysis": paths.analysis_db,
    }.items()}
    preview_fingerprint = _preview_fingerprint(audit_result)
    outcome = "COMPLETED" if (
        audit_result["counts"]["sync_eligible"]
        or audit_result["counts"]["format_normalization_eligible"]
        or audit_result["counts"]["review_required"]
    ) else "NO_CHANGE"
    result = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "operation_type": OPERATION.value,
        "mode": "PREVIEW",
        "outcome": outcome,
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "preview_fingerprint": preview_fingerprint,
        "audit": audit_result,
        "summary_counts": _summary_counts(audit_result),
        "proposed_changes": audit_result["proposed_changes"],
        "production_state_before": production_before,
        "production_state_after": production_after,
        "production_state_unchanged": production_before == production_after,
        "production_changed": False,
        "write_boundary_crossed": False,
        "recommended_next_action": "Run Test on copies after reviewing the CIK synchronization Preview.",
    }
    writer.checkpoint(RunStage.PREVIEW_READY, message="CIK synchronization Preview is ready.", preview_fingerprint=preview_fingerprint, counters=result["summary_counts"])
    writer.checkpoint(RunStage.COMPLETED, message="Read-only CIK Preview completed.", preview_fingerprint=preview_fingerprint)
    _emit(progress_callback, run_id, 1, "AUDIT", "COMPLETED", "Read-only CIK Preview completed.")
    return _finalize(writer, result)


def _load_result(path: Path, mode: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CikSyncError("CIK_SYNC_EVIDENCE_PATH_INVALID")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract_version") != CONTRACT_VERSION or payload.get("mode") != mode:
        raise CikSyncError("CIK_SYNC_EVIDENCE_CONTRACT_MISMATCH")
    return payload


def _assert_preview_current(preview: Mapping[str, Any], paths: BatchAddTickerPaths) -> dict[str, Any]:
    current = audit(paths)
    if current["binding_fingerprint"] != (preview.get("audit") or {}).get("binding_fingerprint"):
        raise CikSyncError("CIK_SYNC_STALE_PREVIEW")
    if _preview_fingerprint(current) != preview.get("preview_fingerprint"):
        raise CikSyncError("CIK_SYNC_PREVIEW_FINGERPRINT_MISMATCH")
    return current


def _apply_changes(path: Path, changes: Sequence[Mapping[str, Any]], *, applied_at: str) -> int:
    updated_companies = 0
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            for change in changes:
                company_id = int(change["company_id"])
                cik = normalize_cik(change.get("provider_cik"))
                if cik is None:
                    raise CikSyncError("CIK_SYNC_PROPOSED_CIK_INVALID")
                action = str(change.get("action") or "BACKFILL_MISSING_CIK")
                existing_rows = list(connection.execute(
                    "SELECT cik_normalized,source_value FROM company_cik WHERE company_id=?",
                    (company_id,),
                ))
                if action == "BACKFILL_MISSING_CIK":
                    if existing_rows:
                        raise CikSyncError("CIK_SYNC_CANONICAL_CONFLICT_DURING_APPLY")
                    provider_rows = change.get("provider_rows") or []
                    source = provider_rows[0] if provider_rows else {}
                    connection.execute(
                        "INSERT INTO company_cik(company_id,cik_normalized,cik_display,source,source_table,source_row_id,status,created_at_utc,source_type,source_name,source_field,source_value,derivation,confidence) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            company_id, cik, cik, "PHASE13G3_17_PROVIDER_CIK_SYNC",
                            "sharadar_ticker_metadata", str(source.get("provider_ticker") or ""),
                            "ACTIVE", applied_at, "PROVIDER_METADATA", "Sharadar ticker metadata",
                            "secfilings", str(source.get("secfilings") or ""),
                            "parsed and normalized SEC CIK query parameter", "HIGH",
                        ),
                    )
                elif action == "NORMALIZE_CIK_FORMAT":
                    if len(existing_rows) != 1 or normalize_cik(existing_rows[0][0]) != cik:
                        raise CikSyncError("CIK_SYNC_FORMAT_NORMALIZATION_STATE_CHANGED")
                    old_cik, old_source_value = existing_rows[0]
                    source_value = cik if normalize_cik(old_source_value) == cik else old_source_value
                    connection.execute(
                        "UPDATE company_cik SET cik_normalized=?,cik_display=?,source_value=? "
                        "WHERE company_id=? AND cik_normalized=?",
                        (cik, cik, source_value, company_id, old_cik),
                    )
                    identities = list(connection.execute(
                        "SELECT provider,provider_identifier_value,source_value FROM provider_company_identity "
                        "WHERE company_id=? AND provider_identifier_type='CIK'",
                        (company_id,),
                    ))
                    if any(normalize_cik(row[1]) != cik for row in identities):
                        raise CikSyncError("CIK_SYNC_PROVIDER_COMPANY_IDENTITY_CONFLICT")
                    for provider, old_value, identity_source_value in identities:
                        normalized_source = cik if normalize_cik(identity_source_value) == cik else identity_source_value
                        connection.execute(
                            "UPDATE provider_company_identity SET provider_identifier_value=?,source_value=? "
                            "WHERE provider=? AND provider_identifier_type='CIK' AND provider_identifier_value=?",
                            (cik, normalized_source, provider, old_value),
                        )
                    company_key = connection.execute(
                        "SELECT company_key FROM company WHERE company_id=?", (company_id,)
                    ).fetchone()[0]
                    if str(company_key).startswith("SEC_CIK:"):
                        if normalize_cik(str(company_key).removeprefix("SEC_CIK:")) != cik:
                            raise CikSyncError("CIK_SYNC_COMPANY_KEY_CONFLICT")
                        connection.execute(
                            "UPDATE company SET company_key=? WHERE company_id=?",
                            (f"SEC_CIK:{cik}", company_id),
                        )
                else:
                    raise CikSyncError("CIK_SYNC_UNKNOWN_CHANGE_ACTION")
                updated_companies += 1
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return updated_companies


def _validate_candidate(
    *, before_audit: Mapping[str, Any], before_fingerprints: Mapping[str, str],
    after_audit: Mapping[str, Any], after_fingerprints: Mapping[str, str],
    expected_updates: int, updated: int, candidate: Path,
) -> dict[str, Any]:
    sqlite_state = sqlite_verification(candidate)
    expected_active_security_reduction = sum(
        len(change.get("security_ids") or ())
        for change in before_audit.get("proposed_changes") or ()
        if change.get("action") == "BACKFILL_MISSING_CIK"
    )
    validation = {
        "updated_count_matches": updated == expected_updates,
        "eligible_resolved": int((after_audit.get("counts") or {}).get("sync_eligible") or 0) == 0,
        "format_normalization_resolved": int((after_audit.get("counts") or {}).get("format_normalization_eligible") or 0) == 0,
        "active_missing_reduced": (
            int((before_audit.get("counts") or {}).get("active_securities_missing_company_cik") or 0)
            - int((after_audit.get("counts") or {}).get("active_securities_missing_company_cik") or 0)
            == expected_active_security_reduction
        ),
        "non_target_canonical_unchanged": before_fingerprints["non_target_canonical"] == after_fingerprints["non_target_canonical"],
        "company_mapping_semantically_unchanged": before_fingerprints["company_semantic"] == after_fingerprints["company_semantic"],
        "provider_company_identity_semantically_unchanged": before_fingerprints["provider_company_identity_semantic"] == after_fingerprints["provider_company_identity_semantic"],
        "security_mapping_unchanged": before_fingerprints["security"] == after_fingerprints["security"],
        "ticker_aliases_unchanged": before_fingerprints["ticker_alias"] == after_fingerprints["ticker_alias"],
        "provider_security_mapping_unchanged": before_fingerprints["provider_security_identity"] == after_fingerprints["provider_security_identity"],
        "quarter_state_unchanged": before_fingerprints["v4_quarter"] == after_fingerprints["v4_quarter"],
        "quarter_financials_unchanged": before_fingerprints["v4_quarter_financials"] == after_fingerprints["v4_quarter_financials"],
        "quick_check": sqlite_state["quick_check"],
        "foreign_key_errors": sqlite_state["foreign_key_errors"],
    }
    if not all(value is True or value == "ok" or value == 0 for value in validation.values()):
        raise CikSyncError("CIK_SYNC_CANDIDATE_VALIDATION_FAILED")
    return validation


def _validation_passed(validation: Mapping[str, Any]) -> bool:
    return all(value is True or value == "ok" or value == 0 for value in validation.values())


def run_apply(
    *, preview_payload_path: Path, preview_fingerprint: str, confirm_apply: bool,
    paths: BatchAddTickerPaths | None = None, run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = TEMP_ROOT, progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not confirm_apply:
        raise CikSyncError("CIK_SYNC_TEST_CONFIRMATION_REQUIRED")
    paths = paths or BatchAddTickerPaths()
    preview = _load_result(preview_payload_path, "PREVIEW")
    if preview.get("preview_fingerprint") != preview_fingerprint or preview.get("outcome") != "COMPLETED":
        raise CikSyncError("CIK_SYNC_PREVIEW_NOT_AUTHORIZED")
    current = _assert_preview_current(preview, paths)
    run_id = stable_run_id(OPERATION, preview_fingerprint, suffix="apply")
    writer = AdminRunWriter(run_id, OPERATION, root=run_root)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="CIK Test request recorded.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Starting CIK Test on copies.", preview_fingerprint=preview_fingerprint)
    _emit(progress_callback, run_id, 2, "TEST_ON_COPIES", "RUNNING", "Creating isolated canonical Test copy.")
    copy_dir = temp_root / run_id
    candidate = copy_dir / "canonical_test.db"
    production_before = {"provider": _database_state(paths.provider_db), "canonical": _database_state(paths.canonical_db), "analysis": _database_state(paths.analysis_db)}
    before_fingerprints = _canonical_fingerprints(paths.canonical_db)
    cleanup_status = "FAILED"
    try:
        copy_dir.mkdir(parents=True, exist_ok=False)
        online_backup(paths.canonical_db, candidate)
        updated = _apply_changes(candidate, preview["proposed_changes"], applied_at=utc_now())
        candidate_paths = BatchAddTickerPaths(paths.provider_db, candidate, paths.analysis_db, paths.market_db, paths.taxonomy_db)
        after_audit = audit(candidate_paths)
        after_fingerprints = _canonical_fingerprints(candidate)
        validation = _validate_candidate(
            before_audit=current, before_fingerprints=before_fingerprints,
            after_audit=after_audit, after_fingerprints=after_fingerprints,
            expected_updates=len(preview["proposed_changes"]), updated=updated, candidate=candidate,
        )
        production_after = {"provider": _database_state(paths.provider_db), "canonical": _database_state(paths.canonical_db), "analysis": _database_state(paths.analysis_db)}
        validation["provider_unchanged"] = production_before["provider"] == production_after["provider"]
        validation["analysis_unchanged"] = production_before["analysis"] == production_after["analysis"]
        validation["production_canonical_unchanged"] = production_before["canonical"] == production_after["canonical"]
        if not all((validation["provider_unchanged"], validation["analysis_unchanged"], validation["production_canonical_unchanged"])):
            raise CikSyncError("CIK_SYNC_TEST_PRODUCTION_ISOLATION_FAILED")
        result = {
            "contract_version": CONTRACT_VERSION,
            "run_id": run_id,
            "operation_type": OPERATION.value,
            "mode": "COPY_ONLY_APPLY",
            "outcome": "COMPLETED",
            "started_at_utc": utc_now(),
            "completed_at_utc": utc_now(),
            "preview_run_id": preview["run_id"],
            "preview_fingerprint": preview_fingerprint,
            "preview_payload_path": str(preview_payload_path),
            "preview_binding_fingerprint": current["binding_fingerprint"],
            "before_audit": current,
            "after_audit": after_audit,
            "summary_counts": _summary_counts(current),
            "updated_count": updated,
            "validation": validation,
            "production_state_before": production_before,
            "production_state_after": production_after,
            "production_changed": False,
            "write_boundary_crossed": False,
            "candidate_bytes": candidate.stat().st_size,
            "recommended_next_action": "Review Test evidence, then authorize Production update separately.",
        }
    finally:
        shutil.rmtree(copy_dir, ignore_errors=True)
        cleanup_status = "COMPLETED" if not copy_dir.exists() else "FAILED"
    result["cleanup_status"] = cleanup_status
    result["remaining_phase_owned_large_files"] = 0 if cleanup_status == "COMPLETED" else 1
    writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Production databases remained unchanged.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.COMPLETED, message="CIK Test on copies completed.", preview_fingerprint=preview_fingerprint, counters=result["summary_counts"])
    _emit(progress_callback, run_id, 2, "TEST_ON_COPIES", "COMPLETED", "CIK Test on copies completed and Test DB was removed.")
    return _finalize(writer, result)


def _restore_backup(backup: Path, target: Path) -> None:
    restore = target.parent / f".{target.name}.cik-sync-restore-{os.getpid()}.db"
    try:
        shutil.copy2(backup, restore)
        sqlite_verification(restore)
        fsync_file(restore)
        os.replace(restore, target)
        fsync_file(target)
        fsync_directory(target.parent)
    finally:
        restore.unlink(missing_ok=True)


def run_production_apply(
    *, preview_payload_path: Path, preview_fingerprint: str, test_run_id: str,
    confirm_production: bool, paths: BatchAddTickerPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT, temp_root: Path = TEMP_ROOT,
    backup_root: Path = BACKUP_ROOT, journal_path: Path = ACTIVE_JOURNAL_PATH,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not confirm_production:
        raise CikSyncError("CIK_SYNC_PRODUCTION_EXPLICIT_CONFIRMATION_REQUIRED")
    paths = paths or BatchAddTickerPaths()
    preview = _load_result(preview_payload_path, "PREVIEW")
    test = _load_result(run_root / test_run_id / "result.json", "COPY_ONLY_APPLY")
    if (
        preview.get("preview_fingerprint") != preview_fingerprint
        or test.get("outcome") != "COMPLETED"
        or test.get("preview_fingerprint") != preview_fingerprint
        or test.get("preview_run_id") != preview.get("run_id")
        or not _validation_passed(test.get("validation") or {})
    ):
        raise CikSyncError("CIK_SYNC_MATCHING_SUCCESSFUL_TEST_REQUIRED")
    run_id = stable_run_id(OPERATION, preview_fingerprint, suffix="production")
    writer = AdminRunWriter(run_id, OPERATION, root=run_root)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="CIK Production request recorded.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Validating CIK Production evidence.", preview_fingerprint=preview_fingerprint)
    candidate_dir = temp_root / run_id
    candidate = candidate_dir / "canonical_candidate.db"
    backup_dir = backup_root / run_id
    backup = backup_dir / "canonical.db"
    publication_started = False
    cleanup_status = "FAILED"
    backup_retained = False
    with production_lock():
        guard_production_writes(journal_path)
        current = _assert_preview_current(preview, paths)
        before_state = {"provider": _database_state(paths.provider_db), "canonical": _database_state(paths.canonical_db), "analysis": _database_state(paths.analysis_db)}
        before_fingerprints = _canonical_fingerprints(paths.canonical_db)
        if shutil.disk_usage(backup_root.parent).free < paths.canonical_db.stat().st_size * 3:
            raise CikSyncError("CIK_SYNC_INSUFFICIENT_STORAGE")
        try:
            candidate_dir.mkdir(parents=True, exist_ok=False)
            backup_dir.mkdir(parents=True, exist_ok=False)
            online_backup(paths.canonical_db, candidate)
            updated = _apply_changes(candidate, preview["proposed_changes"], applied_at=utc_now())
            candidate_paths = BatchAddTickerPaths(paths.provider_db, candidate, paths.analysis_db, paths.market_db, paths.taxonomy_db)
            candidate_audit = audit(candidate_paths)
            validation = _validate_candidate(
                before_audit=current, before_fingerprints=before_fingerprints,
                after_audit=candidate_audit, after_fingerprints=_canonical_fingerprints(candidate),
                expected_updates=len(preview["proposed_changes"]), updated=updated, candidate=candidate,
            )
            online_backup(paths.canonical_db, backup)
            backup_retained = True
            backup_verification = sqlite_verification(backup)
            writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Candidate and rollback backup verified.", preview_fingerprint=preview_fingerprint)
            writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Publishing canonical CIK candidate atomically.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            _emit(progress_callback, run_id, 3, "PRODUCTION_UPDATE", "RUNNING", "Publishing verified canonical candidate.")
            fsync_file(candidate)
            os.replace(candidate, paths.canonical_db)
            publication_started = True
            fsync_file(paths.canonical_db)
            fsync_directory(paths.canonical_db.parent)
            postflight = audit(paths)
            post_fingerprints = _canonical_fingerprints(paths.canonical_db)
            validation.update({
                "published_binding_matches_candidate": postflight["binding_fingerprint"] == candidate_audit["binding_fingerprint"],
                "non_target_canonical_unchanged": before_fingerprints["non_target_canonical"] == post_fingerprints["non_target_canonical"],
                "provider_unchanged": before_state["provider"] == _database_state(paths.provider_db),
                "analysis_unchanged": before_state["analysis"] == _database_state(paths.analysis_db),
            })
            if not all(value is True or value == "ok" or value == 0 for value in validation.values()):
                raise CikSyncError("CIK_SYNC_PRODUCTION_POSTFLIGHT_FAILED")
            result = {
                "contract_version": CONTRACT_VERSION,
                "run_id": run_id,
                "operation_type": OPERATION.value,
                "mode": "PRODUCTION_APPLY",
                "outcome": "COMPLETED",
                "started_at_utc": utc_now(),
                "completed_at_utc": utc_now(),
                "preview_run_id": preview["run_id"],
                "test_run_id": test_run_id,
                "preview_fingerprint": preview_fingerprint,
                "preview_payload_path": str(preview_payload_path),
                "before_audit": current,
                "after_audit": postflight,
                "summary_counts": _summary_counts(current),
                "updated_count": updated,
                "validation": validation,
                "backup": {"path": str(backup), "verification": backup_verification},
                "production_state_before": before_state,
                "production_state_after": {"provider": _database_state(paths.provider_db), "canonical": _database_state(paths.canonical_db), "analysis": _database_state(paths.analysis_db)},
                "production_changed": updated > 0,
                "write_boundary_crossed": True,
                "rollback": {"status": "NOT_REQUIRED"},
                "recommended_next_action": "Review postflight evidence and authorize rollback-backup cleanup separately.",
            }
        except BaseException as exc:
            writer.write_error(exc)
            if publication_started:
                writer.checkpoint(
                    RunStage.ROLLBACK_STARTED,
                    message="CIK Production postflight failed; restoring verified canonical backup.",
                    preview_fingerprint=preview_fingerprint,
                    write_boundary_crossed=True,
                )
                try:
                    _restore_backup(backup, paths.canonical_db)
                    restored = _database_state(paths.canonical_db)
                    if (
                        restored["sha256"] != sha256_file(backup)
                        or _canonical_fingerprints(paths.canonical_db) != before_fingerprints
                    ):
                        raise CikSyncError("CIK_SYNC_ROLLBACK_FINGERPRINT_MISMATCH")
                    writer.checkpoint(
                        RunStage.ROLLBACK_COMPLETE,
                        message="Canonical rollback completed and old-generation fingerprint verified.",
                        preview_fingerprint=preview_fingerprint,
                        write_boundary_crossed=True,
                    )
                    writer.checkpoint(
                        RunStage.FAILED_AFTER_WRITE,
                        message="CIK Production update failed after publication and was rolled back.",
                        preview_fingerprint=preview_fingerprint,
                        write_boundary_crossed=True,
                    )
                    outcome = "ROLLED_BACK"
                    rollback = {"status": "ROLLED_BACK", "restored_sha256": restored["sha256"]}
                except BaseException as rollback_exc:
                    writer.write_error(rollback_exc)
                    writer.checkpoint(
                        RunStage.FAILED_AFTER_WRITE,
                        message="CIK Production rollback failed.",
                        preview_fingerprint=preview_fingerprint,
                        write_boundary_crossed=True,
                    )
                    outcome = "CRITICAL_ROLLBACK_FAILED"
                    rollback = {"status": "FAILED", "error": type(rollback_exc).__name__}
            else:
                writer.checkpoint(
                    RunStage.FAILED_BEFORE_WRITE,
                    message="CIK Production update failed before the write boundary.",
                    preview_fingerprint=preview_fingerprint,
                )
                shutil.rmtree(backup_dir, ignore_errors=True)
                backup_retained = False
                outcome = "FAILED"
                rollback = {"status": "NOT_REQUIRED"}
            result = {
                "contract_version": CONTRACT_VERSION,
                "run_id": run_id,
                "operation_type": OPERATION.value,
                "mode": "PRODUCTION_APPLY",
                "outcome": outcome,
                "started_at_utc": utc_now(),
                "completed_at_utc": utc_now(),
                "preview_run_id": preview["run_id"],
                "test_run_id": test_run_id,
                "preview_fingerprint": preview_fingerprint,
                "preview_payload_path": str(preview_payload_path),
                "before_audit": current,
                "summary_counts": _summary_counts(current),
                "updated_count": 0,
                "validation": {},
                "production_state_before": before_state,
                "production_state_after": {
                    "provider": _database_state(paths.provider_db),
                    "canonical": _database_state(paths.canonical_db),
                    "analysis": _database_state(paths.analysis_db),
                },
                "production_changed": outcome == "CRITICAL_ROLLBACK_FAILED",
                "write_boundary_crossed": publication_started,
                "rollback": rollback,
                "errors": [{"type": type(exc).__name__, "message": str(exc)}],
                "recommended_next_action": "Review failure and rollback evidence before rerunning Preview and Test.",
            }
        finally:
            shutil.rmtree(candidate_dir, ignore_errors=True)
            cleanup_status = "COMPLETED" if not candidate_dir.exists() else "FAILED"
    result["cleanup_status"] = cleanup_status
    result["remaining_phase_owned_large_files"] = int(backup_retained and backup.exists()) + int(cleanup_status != "COMPLETED")
    if result["outcome"] == "COMPLETED":
        writer.checkpoint(RunStage.COMPLETED, message="CIK Production update completed.", preview_fingerprint=preview_fingerprint, counters=result["summary_counts"], write_boundary_crossed=True)
        _emit(progress_callback, run_id, 3, "PRODUCTION_UPDATE", "COMPLETED", "CIK Production update completed.")
        return _finalize(writer, result)
    _emit(progress_callback, run_id, 3, "PRODUCTION_UPDATE", "FAILED", "CIK Production update failed; review terminal evidence.")
    return _finalize(writer, result, exit_code=1)
