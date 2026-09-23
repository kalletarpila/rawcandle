"""Remove Tickers Preview and candidate-only Test for Fundamentals Administration."""

from __future__ import annotations

import fcntl
import hashlib
import json
import secrets
import shutil
import sqlite3
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from rawcandle.datacenter_taxonomy_operation_log import (
    current_taxonomy_operation_lock,
    taxonomy_lock_held_in_process,
    taxonomy_operation_lock_context,
)
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import (
    BatchAddTickerPaths,
    CopyLane,
    _assert_clean_worktree,
    cleanup_copy_lane,
    create_copy_lane,
)
from rawcandle.fundamentals.admin.contracts import (
    AdminOperationType,
    RunStage,
    build_batch_request,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.identity_resolution import DEFAULT_REGISTRY_PATH
from rawcandle.fundamentals.admin.production_transaction import (
    ADMIN_LOCK,
    BACKUP_ROOT,
    _storage_preflight,
    production_lock,
)
from rawcandle.fundamentals.admin.publication_journal import (
    ACTIVE_JOURNAL_PATH,
    PUBLICATION_ROLES,
    PublicationRecoveryError,
    PublicationRecoveredRetryRequired,
    fsync_directory,
    guard_production_writes,
    prepare_journal,
    restore_old_generation,
    safety_status,
    sqlite_verification,
    update_journal,
)
from rawcandle.fundamentals.admin.refresh_production import (
    _candidate_manifest,
    _cleanup_candidate_lane,
    _production_file_state,
    _publication_activity,
    _replace_role,
    _verified_backups,
)
from rawcandle.fundamentals.admin.structural_context import _events
from rawcandle.fundamentals.admin.source_bundle import (
    SOURCE_CONTRACT_VERSION,
    TaxonomySourceMode,
    bind_taxonomy_source,
    prepare_protected_read_only_sources,
    semantic_source_binding,
)
from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import load_active_dc_memberships
from rawcandle.fundamentals.phase12d import PRODUCTION, rebuild_ttm
from rawcandle.fundamentals.phase13b_foundation import universe_identity


CONTRACT_VERSION = "PHASE13G3_34_REMOVE_TICKERS_PREVIEW_V1"
TEST_CONTRACT_VERSION = "PHASE13G3_35_REMOVE_TICKERS_TEST_V1"
PRODUCTION_CONTRACT_VERSION = "PHASE13G3_36_REMOVE_TICKERS_PRODUCTION_V1"
MAX_TICKERS = 25
REMOVE_TEST_LOCK = ADMIN_TEMP_ROOT.parent / ".remove_tickers_test.lock"
ANALYSIS_TABLES = (
    "score_result",
    "lifecycle_revised_result",
    "valuation_revised_result",
    "fundamental_delta_result",
    "diagnostic_flag_endpoint",
    "relative_position_result",
    "relative_position_coverage",
    "relative_valuation_company_result",
)


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _rows(connection: sqlite3.Connection, query: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, tuple(parameters))]


def _active_universe(connection: sqlite3.Connection) -> tuple[str, list[dict[str, Any]]]:
    required = {
        "company", "security", "ticker_alias",
        "fundamentals_operational_universe_active_version",
        "fundamentals_operational_universe_member",
    }
    missing = sorted(table for table in required if not _table_exists(connection, table))
    if missing:
        raise ValueError(f"REMOVE_TICKERS_REQUIRED_CANONICAL_TABLE_MISSING:{','.join(missing)}")
    active = connection.execute(
        "SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1"
    ).fetchall()
    if len(active) != 1:
        raise ValueError("REMOVE_TICKERS_ACTIVE_UNIVERSE_NOT_UNIQUE")
    version = str(active[0][0])
    members = _rows(
        connection,
        "SELECT * FROM fundamentals_operational_universe_member WHERE universe_version_id=? "
        "ORDER BY company_id,security_id,current_ticker",
        (version,),
    )
    return version, members


def _provider_evidence(path: Path, ticker: str, company_id: int | None, security_id: int | None) -> dict[str, Any]:
    with _readonly(path) as connection:
        evidence: dict[str, Any] = {}
        specifications = {
            "sharadar_fundamental_observation": ("ticker", None),
            "sharadar_ticker_metadata": ("ticker", None),
            "provider_observation": (None, "company_id"),
            "provider_company_identity": ("provider_ticker", "company_id"),
            "provider_security_identity": ("provider_ticker", "security_id"),
        }
        material_rows: dict[str, list[dict[str, Any]]] = {}
        for table, (ticker_column, identity_column) in specifications.items():
            if not _table_exists(connection, table):
                evidence[table] = 0
                continue
            columns = _columns(connection, table)
            clauses: list[str] = []
            parameters: list[Any] = []
            if ticker_column in columns:
                clauses.append(f"UPPER({ticker_column})=UPPER(?)")
                parameters.append(ticker)
            identity = company_id if identity_column == "company_id" else security_id
            if identity_column in columns and identity is not None:
                clauses.append(f"{identity_column}=?")
                parameters.append(identity)
            if not clauses:
                evidence[table] = 0
                continue
            selected = _rows(connection, f"SELECT * FROM {table} WHERE {' OR '.join(clauses)}", parameters)
            evidence[table] = len(selected)
            material_rows[table] = selected
    evidence["present"] = any(value for value in evidence.values() if isinstance(value, int))
    evidence["semantic_fingerprint"] = fingerprint(material_rows)
    evidence["planned_action"] = "PRESERVE_HISTORICAL_PROVIDER_EVIDENCE"
    return evidence


def _analysis_evidence(path: Path, ticker: str, company_id: int | None, security_id: int | None) -> dict[str, Any]:
    counts: dict[str, int] = {}
    material: dict[str, list[dict[str, Any]]] = {}
    with _readonly(path) as connection:
        for table in ANALYSIS_TABLES:
            if not _table_exists(connection, table):
                counts[table] = 0
                continue
            columns = _columns(connection, table)
            clauses: list[str] = []
            parameters: list[Any] = []
            if "ticker" in columns:
                clauses.append("UPPER(ticker)=UPPER(?)")
                parameters.append(ticker)
            if "company_id" in columns and company_id is not None:
                clauses.append("company_id=?")
                parameters.append(company_id)
            if "security_id" in columns and security_id is not None:
                clauses.append("security_id=?")
                parameters.append(security_id)
            selected = _rows(connection, f"SELECT * FROM {table} WHERE {' OR '.join(clauses)}", parameters) if clauses else []
            counts[table] = len(selected)
            material[table] = selected
    return {
        "table_rows": counts,
        "total_rows": sum(counts.values()),
        "present": any(counts.values()),
        "semantic_fingerprint": fingerprint(material),
        "expected_rebuild": "FULL_V2_RP_V2_RV",
    }


def _canonical_plan(path: Path, ticker: str) -> dict[str, Any]:
    with _readonly(path) as connection:
        version, members = _active_universe(connection)
        universe_fingerprint = fingerprint({"universe_version_id": version, "members": members})
        current = _rows(
            connection,
            "SELECT c.company_id,c.company_key,c.company_name,c.status AS company_status,"
            "s.security_id,s.current_ticker,s.active,s.valid_from,s.valid_to "
            "FROM security s JOIN company c USING(company_id) "
            "WHERE UPPER(s.current_ticker)=UPPER(?) ORDER BY s.security_id",
            (ticker,),
        )
        alias_columns = _columns(connection, "ticker_alias")
        alias_name = "ticker" if "ticker" in alias_columns else "alias_ticker"
        aliases = _rows(
            connection,
            f"SELECT a.*,s.company_id,s.current_ticker,s.active FROM ticker_alias a "
            f"JOIN security s USING(security_id) WHERE UPPER(a.{alias_name})=UPPER(?) ORDER BY a.security_id",
            (ticker,),
        )
        if len(current) > 1:
            return {
                "classification": "REMOVAL_BLOCKED", "eligible": False,
                "reasons": ["CURRENT_TICKER_IDENTITY_CONFLICT"], "company_id": None,
                "security_id": None, "current_matches": current, "alias_matches": aliases,
                "active_universe_version_id": version, "current_universe_fingerprint": universe_fingerprint,
                "expected_current_universe_rows_affected": 0, "expected_mutation_set": [],
                "related_securities_preserved": [],
            }
        if not current:
            classification = "AMBIGUOUS_IDENTITY_REVIEW_REQUIRED" if aliases else "ALREADY_ABSENT"
            reasons = ["HISTORICAL_ALIAS_MUST_NOT_REMOVE_CURRENT_SUCCESSOR"] if aliases else ["NO_CURRENT_CANONICAL_SECURITY"]
            return {
                "classification": classification, "eligible": False, "reasons": reasons,
                "company_id": None, "security_id": None, "current_matches": [], "alias_matches": aliases,
                "active_universe_version_id": version, "current_universe_fingerprint": universe_fingerprint,
                "expected_current_universe_rows_affected": 0, "expected_mutation_set": [],
                "related_securities_preserved": [],
            }
        identity = current[0]
        company_id = int(identity["company_id"])
        security_id = int(identity["security_id"])
        related = _rows(
            connection,
            "SELECT security_id,current_ticker,active,valid_from,valid_to FROM security "
            "WHERE company_id=? AND security_id<>? ORDER BY security_id",
            (company_id, security_id),
        )
        company_members = [row for row in members if int(row["company_id"]) == company_id]
        active_related = [row for row in related if int(row.get("active") or 0) == 1]
        member_targets_target = any(
            row.get("security_id") is None or int(row["security_id"]) == security_id
            for row in company_members
        )
        if not int(identity["active"]):
            if company_members and member_targets_target:
                classification, reasons = "REMOVAL_BLOCKED", ["INACTIVE_SECURITY_REMAINS_IN_ACTIVE_UNIVERSE"]
            else:
                classification, reasons = "ALREADY_ABSENT", ["SECURITY_NOT_ACTIVE_IN_FUNDAMENTALS_UNIVERSE"]
        elif not company_members or not member_targets_target:
            classification, reasons = "REMOVAL_BLOCKED", ["SECURITY_ACTIVE_BUT_NOT_IN_ACTIVE_OPERATIONAL_UNIVERSE"]
        elif len(company_members) != 1:
            classification, reasons = "REMOVAL_BLOCKED", ["ACTIVE_UNIVERSE_MEMBERSHIP_CONFLICT"]
        elif active_related:
            classification, reasons = "SHARED_COMPANY_PRESERVE_COMPANY", ["OTHER_ACTIVE_SECURITIES_PRESERVE_COMPANY"]
        else:
            classification, reasons = "REMOVABLE_ACTIVE_SECURITY", ["UNIQUE_ACTIVE_SECURITY_CAN_BE_EXCLUDED"]
        eligible = classification in {"REMOVABLE_ACTIVE_SECURITY", "SHARED_COMPANY_PRESERVE_COMPANY"}
        mutation = []
        if eligible:
            mutation.append({"role": "canonical", "action": "DEACTIVATE_SECURITY", "security_id": security_id})
            mutation.append({
                "role": "canonical", "action": "REBUILD_ACTIVE_OPERATIONAL_UNIVERSE",
                "company_id": company_id,
                "company_preserved": bool(active_related),
            })
            mutation.append({"role": "analysis", "action": "FULL_V2_RP_V2_RV_REBUILD"})
        return {
            "classification": classification, "eligible": eligible, "reasons": reasons,
            "company_id": company_id, "security_id": security_id,
            "company_name": identity.get("company_name"), "company_status": identity.get("company_status"),
            "security_active": bool(identity["active"]), "current_matches": current, "alias_matches": aliases,
            "active_universe_version_id": version, "current_universe_fingerprint": universe_fingerprint,
            "active_universe_membership": company_members,
            "expected_current_universe_rows_affected": 1 if eligible else 0,
            "expected_mutation_set": mutation,
            "related_securities_preserved": related,
            "permanent_identity_action": "PRESERVE_COMPANY_SECURITY_AND_TICKER_ALIAS_HISTORY",
        }


def _taxonomy_presence(paths: BatchAddTickerPaths, company_id: int | None) -> dict[str, Any]:
    memberships, dependency = load_active_dc_memberships(paths.taxonomy_db, paths.canonical_db)
    rows = memberships.get(company_id, ()) if company_id is not None else ()
    return {
        "present": bool(rows),
        "membership_count": len(rows),
        "memberships": [vars(row) for row in rows],
        "dependency": dependency,
        "planned_action": "READ_ONLY_REEVALUATION_DURING_FUTURE_REBUILD",
    }


def _plan_item(paths: BatchAddTickerPaths, ticker: str) -> dict[str, Any]:
    canonical = _canonical_plan(paths.canonical_db, ticker)
    company_id = canonical.get("company_id")
    security_id = canonical.get("security_id")
    provider = _provider_evidence(paths.provider_db, ticker, company_id, security_id)
    analysis = _analysis_evidence(paths.analysis_db, ticker, company_id, security_id)
    taxonomy = _taxonomy_presence(paths, company_id)
    if canonical["classification"] == "ALREADY_ABSENT" and (provider["present"] or analysis["present"]):
        canonical = {
            **canonical,
            "classification": "AMBIGUOUS_IDENTITY_REVIEW_REQUIRED",
            "reasons": [
                *canonical["reasons"],
                "CURRENT_STATE_EVIDENCE_WITHOUT_ACTIVE_UNIVERSE_IDENTITY",
            ],
        }
    return {
        "requested_ticker": ticker,
        "resolved_ticker": canonical["current_matches"][0]["current_ticker"] if len(canonical["current_matches"]) == 1 else None,
        "company_id": company_id,
        "security_id": security_id,
        "classification": canonical["classification"],
        "removal_eligible": bool(canonical["eligible"]),
        "blocking_or_review_reasons": canonical["reasons"],
        "canonical": canonical,
        "provider": provider,
        "analysis": analysis,
        "taxonomy_rp_rv": taxonomy,
        "expected_derived_rebuild_impact": "FULL_V2_RP_V2_RV" if canonical["eligible"] else "NONE",
    }


def _apply_batch_interactions(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    planned = [{**item, "canonical": dict(item["canonical"])} for item in items]
    requested_security_ids = {
        int(item["security_id"])
        for item in planned
        if item.get("security_id") is not None and item["canonical"].get("eligible")
    }
    for item in planned:
        canonical = item["canonical"]
        if not canonical.get("eligible") or item.get("company_id") is None:
            continue
        securities = [
            *canonical.get("current_matches", ()),
            *canonical.get("related_securities_preserved", ()),
        ]
        remaining = [
            row for row in securities
            if int(row.get("active") or 0) == 1
            and int(row["security_id"]) not in requested_security_ids
        ]
        company_preserved = bool(remaining)
        classification = (
            "SHARED_COMPANY_PRESERVE_COMPANY"
            if company_preserved
            else "REMOVABLE_ACTIVE_SECURITY"
        )
        reasons = [
            "OTHER_ACTIVE_SECURITIES_PRESERVE_COMPANY"
            if company_preserved
            else "NO_ACTIVE_SECURITY_REMAINS_AFTER_REQUESTED_BATCH"
        ]
        mutation = [
            {"role": "canonical", "action": "DEACTIVATE_SECURITY", "security_id": item["security_id"]},
            {
                "role": "canonical", "action": "REBUILD_ACTIVE_OPERATIONAL_UNIVERSE",
                "company_id": item["company_id"], "company_preserved": company_preserved,
            },
            {"role": "canonical", "action": "REBUILD_TTM_FROM_ACTIVE_SECURITY_IDENTITIES"},
            {"role": "analysis", "action": "FULL_V2_RP_V2_RV_REBUILD"},
        ]
        canonical.update(
            classification=classification,
            reasons=reasons,
            expected_mutation_set=mutation,
            remaining_active_securities=remaining,
        )
        item.update(
            classification=classification,
            blocking_or_review_reasons=reasons,
            expected_derived_rebuild_impact="FULL_V2_RP_V2_RV",
        )
    return planned


def _plan_items(paths: BatchAddTickerPaths, tickers: Sequence[str]) -> list[dict[str, Any]]:
    return _apply_batch_interactions([_plan_item(paths, ticker) for ticker in tickers])


def _build_plan_binding(
    items: Sequence[Mapping[str, Any]],
    requested_tickers: Sequence[str],
    source_binding: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "requested_tickers": list(requested_tickers),
        "identity_bindings": [
            {
                "ticker": item["requested_ticker"], "company_id": item["company_id"],
                "security_id": item["security_id"], "classification": item["classification"],
                "expected_mutation_set": item["canonical"]["expected_mutation_set"],
                "canonical_identity_fingerprint": fingerprint({
                    "current_matches": item["canonical"]["current_matches"],
                    "alias_matches": item["canonical"]["alias_matches"],
                    "related_securities_preserved": item["canonical"]["related_securities_preserved"],
                    "active_universe_membership": item["canonical"].get("active_universe_membership", []),
                    "remaining_active_securities": item["canonical"].get("remaining_active_securities", []),
                }),
            }
            for item in items
        ],
        "current_universe_fingerprint": items[0]["canonical"]["current_universe_fingerprint"],
        "provider_state_fingerprints": {
            item["requested_ticker"]: item["provider"]["semantic_fingerprint"] for item in items
        },
        "analysis_state_fingerprints": {
            item["requested_ticker"]: item["analysis"]["semantic_fingerprint"] for item in items
        },
        "read_only_source_binding": dict(source_binding),
    }


@contextmanager
def _shared_sources(
    paths: BatchAddTickerPaths,
    *,
    bundle_dir: Path,
    as_of_date: str,
    tickers: Sequence[str],
    operation_id: str,
) -> Iterator[dict[str, Any]]:
    def prepare(operation_lock: Any) -> dict[str, Any]:
        taxonomy = bind_taxonomy_source(
            paths.taxonomy_db,
            paths.canonical_db,
            mode=TaxonomySourceMode.DIRECT_LOCKED_READ,
            operation_lock=operation_lock,
        )
        _, evidence = prepare_protected_read_only_sources(
            market_db=paths.market_db,
            taxonomy_db=paths.taxonomy_db,
            canonical_db=paths.canonical_db,
            bundle_dir=bundle_dir,
            as_of_date=as_of_date,
            taxonomy_binding=taxonomy,
            additional_full_history_tickers=tickers,
        )
        return evidence

    if taxonomy_lock_held_in_process():
        yield prepare(current_taxonomy_operation_lock())
        return
    with taxonomy_operation_lock_context(
        deployment_id="FUNDAMENTALS",
        operation_type="REMOVE_TICKERS_PREVIEW_DIRECT_LOCKED_READ",
        operation_id=operation_id,
    ) as operation_lock:
        yield prepare(operation_lock)


def _render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Remove Tickers Preview", "", "Production changed: No", "",
        "Remove Tickers removes a security from the active Fundamentals universe; it does not blindly delete permanent company/security identity or historical ticker evidence.",
        "", "## Results", "",
    ]
    for item in result["removal_plan"]:
        lines.extend([
            f"### {item['requested_ticker']}", "",
            f"- Classification: `{item['classification']}`",
            f"- Removal eligible: `{item['removal_eligible']}`",
            f"- Company/security: `{item['company_id']}` / `{item['security_id']}`",
            f"- Canonical/provider/analysis present: `{bool(item['canonical']['current_matches'])}` / `{item['provider']['present']}` / `{item['analysis']['present']}`",
            f"- Related securities preserved: `{len(item['canonical']['related_securities_preserved'])}`",
            f"- Current-universe rows affected: `{item['canonical']['expected_current_universe_rows_affected']}`",
            f"- Expected rebuild: `{item['expected_derived_rebuild_impact']}`",
            f"- Reasons: `{', '.join(item['blocking_or_review_reasons'])}`", "",
        ])
    lines.extend([
        "## Source Policy", "",
        "- Market: `STABLE_SOURCE_BUNDLE`", "- Taxonomy: `DIRECT_LOCKED_READ`",
        "- Full market/taxonomy copies: `0`", "", "## Next Step", "",
        "Eligible plans may proceed to Test on copies. Production mutation is not available in this phase.", "",
    ])
    return "\n".join(lines)


def run_preview(
    raw_inputs: str | Sequence[str],
    *,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH,
    source_context: Callable[..., Any] = _shared_sources,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    request = build_batch_request(
        AdminOperationType.REMOVE_TICKERS,
        raw_inputs,
        options={"contract_version": CONTRACT_VERSION},
    )
    if request.rejected_inputs:
        raise ValueError("REMOVE_TICKERS_MALFORMED_TICKER")
    if not request.normalized_inputs:
        raise ValueError("REMOVE_TICKERS_REQUIRES_TICKER")
    if len(request.normalized_inputs) > MAX_TICKERS:
        raise ValueError("REMOVE_TICKERS_MAXIMUM_25_TICKERS")
    publication = safety_status(journal_path)
    if publication.get("production_writes_blocked"):
        raise RuntimeError(f"REMOVE_TICKERS_PUBLICATION_RECOVERY_REQUIRED:{publication.get('status')}")
    started = utc_now()
    request_fingerprint = fingerprint(request)
    run_id = stable_run_id(AdminOperationType.REMOVE_TICKERS, request_fingerprint, suffix="preview")
    writer = AdminRunWriter(run_id, AdminOperationType.REMOVE_TICKERS, root=run_root)
    writer.write_json("request.json", request.as_dict())
    bundle_dir = temp_root / run_id / "market_source_bundle"
    if progress_callback:
        progress_callback({
            "current_stage_number": 1,
            "total_declared_stages": 1,
            "current_stage_id": "PREVIEW_VALIDATION",
            "stage_state": "RUNNING",
            "message": "Building the protected read-only source binding and removal plan.",
            "run_id": run_id,
        })
    try:
        with source_context(
            source_paths,
            bundle_dir=bundle_dir,
            as_of_date=started[:10],
            tickers=request.normalized_inputs,
            operation_id=f"{run_id}:taxonomy",
        ) as source_evidence:
            source_binding = semantic_source_binding(source_evidence)
            items = _plan_items(source_paths, request.normalized_inputs)
    finally:
        shutil.rmtree(bundle_dir.parent, ignore_errors=True)
    plan_binding = _build_plan_binding(items, request.normalized_inputs, source_binding)
    preview_fingerprint = fingerprint(plan_binding)
    counts = Counter(item["classification"] for item in items)
    outcome = "COMPLETED" if all(item["classification"] in {"REMOVABLE_ACTIVE_SECURITY", "SHARED_COMPANY_PRESERVE_COMPANY", "ALREADY_ABSENT"} for item in items) else "REVIEW_REQUIRED"
    result = {
        "contract_version": CONTRACT_VERSION,
        "operation_type": AdminOperationType.REMOVE_TICKERS.value,
        "mode": "PREVIEW", "outcome": outcome, "run_id": run_id,
        "started_at_utc": started, "completed_at_utc": utc_now(),
        "request": request.as_dict(), "removal_plan": items,
        "plan_binding": plan_binding, "preview_fingerprint": preview_fingerprint,
        "summary_counts": {"requested": len(items), **dict(sorted(counts.items()))},
        "read_only_source_binding": source_binding,
        "full_source_copies_created": 0, "production_changed": False,
        "artifact_dir": str(writer.run_dir),
        "recommended_next_action": "Review the removal plan, then run Test on copies for eligible items. Production is not available.",
    }
    plan_path = writer.write_json("remove_tickers_preview.json", result)
    result["preview_payload_path"] = str(plan_path)
    writer.write_json("result.json", result)
    writer.write_text("operation_report.md", _render_report(result))
    writer.write_manifest()
    if progress_callback:
        progress_callback({
            "current_stage_number": 1,
            "total_declared_stages": 1,
            "current_stage_id": "PREVIEW_VALIDATION",
            "stage_state": "COMPLETED",
            "message": "Remove Tickers preview completed.",
            "run_id": run_id,
        })
    return result


@contextmanager
def _remove_test_lock(lock_path: Path = REMOVE_TEST_LOCK) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("REMOVE_TICKERS_TEST_ALREADY_RUNNING") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _file_state(paths: BatchAddTickerPaths) -> dict[str, dict[str, int]]:
    return {
        role: {"size": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns}
        for role, path in paths.as_dict().items()
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_state(path: Path, *, target_security_ids: set[int] = frozenset()) -> dict[str, Any]:
    with _readonly(path) as connection:
        permanent: dict[str, list[dict[str, Any]]] = {}
        for table, order in (
            ("company", "company_id"),
            ("security", "security_id"),
            ("ticker_alias", "alias_id"),
            ("provider_company_identity", "rowid"),
            ("provider_security_identity", "rowid"),
        ):
            if _table_exists(connection, table):
                permanent[table] = _rows(connection, f"SELECT * FROM {table} ORDER BY {order}")
        unrelated_securities = [
            row for row in permanent.get("security", ())
            if int(row["security_id"]) not in target_security_ids
        ]
        aliases = permanent.get("ticker_alias", [])
        companies = permanent.get("company", [])
        target_rows = [
            row for row in permanent.get("security", ())
            if int(row["security_id"]) in target_security_ids
        ]
    permanent_projection = {
        "company": companies,
        "security_identity": [
            {key: row.get(key) for key in ("security_id", "company_id", "current_ticker", "exchange", "valid_from")}
            for row in permanent.get("security", ())
        ],
        "ticker_alias": aliases,
        "provider_company_identity": permanent.get("provider_company_identity", []),
        "provider_security_identity": permanent.get("provider_security_identity", []),
    }
    return {
        "permanent_identity_fingerprint": fingerprint(permanent_projection),
        "alias_fingerprint": fingerprint(aliases),
        "company_fingerprint": fingerprint(companies),
        "unrelated_security_fingerprint": fingerprint(unrelated_securities),
        "target_security_rows": target_rows,
    }


def _registry_fingerprint(path: Path = DEFAULT_REGISTRY_PATH) -> str | None:
    return _sha256(path) if path.is_file() else None


def _mutate_candidate_universe(
    canonical_db: Path,
    items: Sequence[Mapping[str, Any]],
    *,
    applied_at: str,
) -> dict[str, Any]:
    targets = {
        int(item["security_id"]): int(item["company_id"])
        for item in items
        if item.get("removal_eligible")
    }
    target_companies = set(targets.values())
    with sqlite3.connect(canonical_db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        active = connection.execute(
            "SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1"
        ).fetchone()
        if active is None:
            raise RuntimeError("REMOVE_TICKERS_ACTIVE_UNIVERSE_MISSING")
        old_version = str(active[0])
        members = _rows(
            connection,
            "SELECT * FROM fundamentals_operational_universe_member WHERE universe_version_id=? ORDER BY company_id",
            (old_version,),
        )
        aliases = _rows(
            connection,
            "SELECT * FROM fundamentals_operational_universe_member_alias WHERE universe_version_id=? "
            "ORDER BY company_id,security_id,alias_ticker",
            (old_version,),
        ) if _table_exists(connection, "fundamentals_operational_universe_member_alias") else []
        security_columns = _columns(connection, "security")
        connection.execute("BEGIN IMMEDIATE")
        for security_id in sorted(targets):
            assignments = ["active=0"]
            parameters: list[Any] = []
            if "valid_to" in security_columns:
                assignments.append("valid_to=COALESCE(valid_to,?)")
                parameters.append(applied_at[:10])
            if "updated_at_utc" in security_columns:
                assignments.append("updated_at_utc=?")
                parameters.append(applied_at)
            parameters.append(security_id)
            changed = connection.execute(
                f"UPDATE security SET {','.join(assignments)} WHERE security_id=? AND active=1",
                parameters,
            ).rowcount
            if changed != 1:
                raise RuntimeError(f"REMOVE_TICKERS_SECURITY_DEACTIVATION_FAILED:{security_id}")
        replacement_members: list[dict[str, Any]] = []
        preserved_company_ids: set[int] = set()
        for member in members:
            company_id = int(member["company_id"])
            if company_id not in target_companies:
                replacement_members.append(member)
                continue
            remaining = _rows(
                connection,
                "SELECT security_id,current_ticker FROM security WHERE company_id=? AND active=1 ORDER BY security_id",
                (company_id,),
            )
            if not remaining:
                continue
            preserved_company_ids.add(company_id)
            updated = dict(member)
            updated.update({
                "security_id": int(remaining[0]["security_id"]) if len(remaining) == 1 else None,
                "current_ticker": (
                    str(remaining[0]["current_ticker"])
                    if len(remaining) == 1
                    else ",".join(str(row["current_ticker"]) for row in remaining)
                ),
                "membership_status": "ACTIVE_SINGLE_SECURITY" if len(remaining) == 1 else "ACTIVE_MULTI_SECURITY",
                "identity_resolution_status": "EXACT_ONE_ACTIVE_SECURITY" if len(remaining) == 1 else "MULTIPLE_ACTIVE_SECURITIES_REQUIRES_SECURITY_SELECTION",
                "active_security_count": len(remaining),
                "updated_at_utc": applied_at,
                "reason": "Remove Tickers candidate reconciliation preserves remaining active securities",
            })
            replacement_members.append(updated)
        member_company_ids = {int(row["company_id"]) for row in replacement_members}
        replacement_aliases = [
            row for row in aliases
            if int(row["company_id"]) in member_company_ids
            and int(row["security_id"]) not in targets
        ]
        identity = universe_identity(replacement_members, replacement_aliases, as_of_date=applied_at[:10])
        connection.execute("DELETE FROM fundamentals_operational_universe_active_version")
        connection.execute(
            "INSERT OR IGNORE INTO fundamentals_operational_universe_version VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity["universe_version_id"], "PHASE13B_OPERATIONAL_UNIVERSE_CONTRACT_V1",
                "CURRENT_OPERATIONAL_UNIVERSE", applied_at[:10], identity["source_fingerprint"],
                identity["economic_result_fingerprint"], identity["physical_content_fingerprint"],
                "COMPLETE", identity["member_count"], identity["company_count"],
                identity["active_security_count"], identity["zero_active_company_count"],
                identity["multi_active_company_count"], applied_at, applied_at,
            ),
        )
        for row in replacement_members:
            connection.execute(
                "INSERT OR REPLACE INTO fundamentals_operational_universe_member VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity["universe_version_id"], row["company_id"], row["security_id"], row["current_ticker"],
                    row["market"], row["membership_status"], row["identity_resolution_status"],
                    row["active_security_count"], row["all_security_count"], row["effective_start_date"],
                    row["effective_end_date"], row["source"], row["reason"], row["created_at_utc"], row["updated_at_utc"],
                ),
            )
        for row in replacement_aliases:
            connection.execute(
                "INSERT OR IGNORE INTO fundamentals_operational_universe_member_alias VALUES (?,?,?,?,?,?,?,?)",
                (
                    identity["universe_version_id"], row["company_id"], row["security_id"], row["alias_ticker"],
                    row["provider"], row["valid_from"], row["valid_to"], row["source"],
                ),
            )
        connection.execute(
            "INSERT INTO fundamentals_operational_universe_active_version VALUES (1,?,?)",
            (identity["universe_version_id"], applied_at),
        )
        connection.commit()
    return {
        "old_universe_version_id": old_version,
        "new_universe": identity,
        "deactivated_security_ids": sorted(targets),
        "target_company_ids": sorted(target_companies),
        "shared_companies_preserved": sorted(preserved_company_ids),
    }


def _derived_participation(
    analysis_db: Path,
    *,
    ticker: str,
    company_id: int,
    security_id: int,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    with _readonly(analysis_db) as connection:
        for table in ANALYSIS_TABLES:
            if not _table_exists(connection, table):
                counts[table] = 0
                continue
            columns = _columns(connection, table)
            clauses: list[str] = []
            parameters: list[Any] = []
            if "ticker" in columns:
                clauses.append("UPPER(ticker)=UPPER(?)")
                parameters.append(ticker)
            if "security_id" in columns:
                clauses.append("security_id=?")
                parameters.append(security_id)
            counts[table] = int(connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {' OR '.join(clauses)}", parameters,
            ).fetchone()[0]) if clauses else 0
        company_rows = {}
        for table in ANALYSIS_TABLES:
            if _table_exists(connection, table) and "company_id" in _columns(connection, table):
                company_rows[table] = int(connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE company_id=?", (company_id,),
                ).fetchone()[0])
    return {
        "target_rows_by_table": counts,
        "target_rows_total": sum(counts.values()),
        "company_rows_by_table": company_rows,
        "removed_current_participation": sum(counts.values()) == 0,
    }


def _database_health(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign_key_errors = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
    return {
        "quick_check": quick_check,
        "foreign_key_error_count": len(foreign_key_errors),
        "passed": quick_check == "ok" and not foreign_key_errors,
    }


def _candidate_universe_state(
    canonical_db: Path,
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    with _readonly(canonical_db) as connection:
        version, members = _active_universe(connection)
        target_results = []
        for item in items:
            if item.get("security_id") is None:
                continue
            company_id = int(item["company_id"])
            security_id = int(item["security_id"])
            security = connection.execute(
                "SELECT active FROM security WHERE security_id=? AND company_id=?",
                (security_id, company_id),
            ).fetchone()
            active_siblings = _rows(
                connection,
                "SELECT security_id,current_ticker FROM security "
                "WHERE company_id=? AND active=1 ORDER BY security_id",
                (company_id,),
            )
            company_members = [row for row in members if int(row["company_id"]) == company_id]
            shared = bool(active_siblings)
            company_participation_matches = bool(company_members) if shared else not company_members
            target_results.append({
                "ticker": item["requested_ticker"],
                "company_id": company_id,
                "security_id": security_id,
                "security_identity_present": security is not None,
                "security_inactive": security is not None and int(security[0]) == 0,
                "target_absent_from_active_universe": all(
                    row.get("security_id") is None or int(row["security_id"]) != security_id
                    for row in company_members
                ),
                "active_sibling_security_ids": [int(row["security_id"]) for row in active_siblings],
                "company_participation_preserved": shared and bool(company_members),
                "company_participation_matches": company_participation_matches,
            })
    passed = all(
        row["security_identity_present"]
        and row["security_inactive"]
        and row["target_absent_from_active_universe"]
        and row["company_participation_matches"]
        for row in target_results
    )
    return {
        "active_universe_version_id": version,
        "target_results": target_results,
        "passed": passed,
    }


def _candidate_ttm_state(
    canonical_db: Path,
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    results = []
    with _readonly(canonical_db) as connection:
        for item in items:
            if item.get("company_id") is None or item.get("security_id") is None:
                continue
            company_id = int(item["company_id"])
            removed_security_id = int(item["security_id"])
            active_ids = [
                int(row[0]) for row in connection.execute(
                    "SELECT security_id FROM security WHERE company_id=? AND active=1 ORDER BY security_id",
                    (company_id,),
                )
            ]
            ttm_ids = [
                int(row[0]) for row in connection.execute(
                    "SELECT DISTINCT security_id FROM v4_ttm_values WHERE company_id=? ORDER BY security_id",
                    (company_id,),
                ) if row[0] is not None
            ]
            expected = active_ids[:1]
            results.append({
                "ticker": item["requested_ticker"],
                "company_id": company_id,
                "removed_security_id": removed_security_id,
                "active_security_ids": active_ids,
                "ttm_security_ids": ttm_ids,
                "expected_ttm_security_ids": expected,
                "removed_security_absent": removed_security_id not in ttm_ids,
                "active_security_reconciliation_matches": ttm_ids == expected,
            })
    return {
        "results": results,
        "passed": all(
            row["removed_security_absent"] and row["active_security_reconciliation_matches"]
            for row in results
        ),
    }


def _render_test_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Remove Tickers Test on Copies", "",
        f"- Outcome: `{result.get('outcome')}`",
        f"- Preview: `{result.get('preview_run_id')}`",
        "- Production changed: `No`", "",
        "## Result", "",
    ]
    for item in result.get("ticker_results", ()):
        ticker = item.get("ticker") or item.get("requested_ticker")
        lines.append(
            f"- `{ticker}`: `{item['classification']}`; "
            f"current participation absent `{item.get('removed_current_participation')}`."
        )
    lines.extend([
        "", "## Sources", "",
        "- Market: `STABLE_SOURCE_BUNDLE`",
        "- Taxonomy: `DIRECT_LOCKED_READ`",
        "- Full market/taxonomy copies: `0`", "",
        "## Safety", "",
        "Candidate copies were removed. Production publication remains unavailable.", "",
    ])
    return "\n".join(lines)


def run_test(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH,
    lock_path: Path = REMOVE_TEST_LOCK,
    source_context: Callable[..., Any] = _shared_sources,
    downstream_runner: Callable[..., dict[str, Any]] = run_full_v2_downstream,
    as_of_date: str | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    preview = json.loads(preview_payload_path.read_text(encoding="utf-8"))
    if (
        preview.get("operation_type") != AdminOperationType.REMOVE_TICKERS.value
        or preview.get("mode") != "PREVIEW"
        or preview.get("preview_fingerprint") != preview_fingerprint
    ):
        raise ValueError("REMOVE_TICKERS_TEST_PREVIEW_AUTHORIZATION_INVALID")
    requested = tuple(preview.get("request", {}).get("normalized_inputs") or ())
    if not requested or preview.get("plan_binding", {}).get("requested_tickers") != list(requested):
        raise ValueError("REMOVE_TICKERS_TEST_REQUEST_BINDING_INVALID")
    publication = safety_status(journal_path)
    if publication.get("production_writes_blocked"):
        raise RuntimeError(f"REMOVE_TICKERS_PUBLICATION_RECOVERY_REQUIRED:{publication.get('status')}")
    run_id = stable_run_id(AdminOperationType.REMOVE_TICKERS, preview_fingerprint, suffix="test")
    writer = AdminRunWriter(run_id, AdminOperationType.REMOVE_TICKERS, root=run_root)
    started = utc_now()
    run_temp = temp_root / run_id
    before_live = _file_state(source_paths)
    result: dict[str, Any] = {
        "contract_version": TEST_CONTRACT_VERSION,
        "operation_type": AdminOperationType.REMOVE_TICKERS.value,
        "mode": "COPY_ONLY_APPLY", "outcome": "FAILED", "run_id": run_id,
        "started_at_utc": started, "preview_run_id": preview.get("run_id"),
        "preview_fingerprint": preview_fingerprint, "requested_tickers": list(requested),
        "artifact_dir": str(writer.run_dir), "production_changed": False,
        "full_market_copy_created": False, "full_taxonomy_copy_created": False,
        "production_available": False,
    }
    lane: CopyLane | None = None
    writer.write_json("request.json", {
        "operation_type": AdminOperationType.REMOVE_TICKERS.value,
        "preview_payload_path": str(preview_payload_path),
        "preview_fingerprint": preview_fingerprint,
        "requested_tickers": list(requested),
    })
    try:
        with _remove_test_lock(lock_path):
            if progress_callback:
                progress_callback({
                    "current_stage_number": 1, "total_declared_stages": 3,
                    "current_stage_id": "PREVIEW_VALIDATION", "stage_state": "RUNNING",
                    "message": "Revalidating the Remove Tickers Preview binding.", "run_id": run_id,
                })
            preflight_dir = run_temp / "preflight_sources"
            with source_context(
                source_paths, bundle_dir=preflight_dir / "market_source_bundle",
                as_of_date=as_of_date or str(preview.get("started_at_utc") or started)[:10],
                tickers=requested, operation_id=f"{run_id}:preflight",
            ) as preflight_evidence:
                current_source_binding = semantic_source_binding(preflight_evidence)
                current_items = _plan_items(source_paths, requested)
                current_binding = _build_plan_binding(current_items, requested, current_source_binding)
            result["preview_revalidation"] = {
                "status": "MATCH" if current_binding == preview.get("plan_binding") else "STALE",
                "preview_binding_fingerprint": fingerprint(preview.get("plan_binding")),
                "current_binding_fingerprint": fingerprint(current_binding),
            }
            if current_binding != preview.get("plan_binding") or fingerprint(current_binding) != preview_fingerprint:
                result.update(
                    outcome="STALE_PREVIEW",
                    recommended_next_action="Run Remove Tickers Preview again.",
                    ticker_results=[],
                )
                return result
            classifications = {str(item["classification"]) for item in current_items}
            if "REMOVAL_BLOCKED" in classifications:
                result.update(outcome="BLOCKED", ticker_results=current_items)
                return result
            if "AMBIGUOUS_IDENTITY_REVIEW_REQUIRED" in classifications:
                result.update(outcome="REVIEW_REQUIRED", ticker_results=current_items)
                return result
            eligible = [item for item in current_items if item["removal_eligible"]]
            if not eligible:
                result.update(
                    outcome="NO_CHANGE", ticker_results=current_items,
                    identity_invariants={"status": "NOT_APPLICABLE_ALREADY_ABSENT"},
                    downstream={"status": "NOT_RUN_ALREADY_ABSENT", "invocation_counts": {"full_v2_rebuild": 0}},
                )
                return result
            if progress_callback:
                progress_callback({
                    "current_stage_number": 2, "total_declared_stages": 3,
                    "current_stage_id": "CREATE_COPIES", "stage_state": "RUNNING",
                    "message": "Creating provider, canonical and analysis candidates.", "run_id": run_id,
                })
            lane = create_copy_lane(
                source_paths, lane_dir=run_temp / "candidate_lane", writer=writer,
                roles=("provider", "canonical", "analysis"),
            )
            target_security_ids = {int(item["security_id"]) for item in eligible}
            identity_before = _identity_state(lane.paths.canonical_db, target_security_ids=target_security_ids)
            registry_before = _registry_fingerprint()
            provider_before = _sha256(lane.paths.provider_db)
            mutation = _mutate_candidate_universe(lane.paths.canonical_db, eligible, applied_at=started)
            ttm = rebuild_ttm(lane.paths.canonical_db, applied_at=started)
            structural = structural_break.apply_contract(
                lane.paths.canonical_db, events=_events(), applied_at_utc=started,
            )
            identity_after = _identity_state(lane.paths.canonical_db, target_security_ids=target_security_ids)
            registry_after = _registry_fingerprint()
            provider_after = _sha256(lane.paths.provider_db)
            identity_invariants = {
                "permanent_company_security_identity_preserved": identity_before["permanent_identity_fingerprint"] == identity_after["permanent_identity_fingerprint"],
                "ticker_alias_history_preserved": identity_before["alias_fingerprint"] == identity_after["alias_fingerprint"],
                "company_rows_preserved": identity_before["company_fingerprint"] == identity_after["company_fingerprint"],
                "unrelated_securities_unchanged": identity_before["unrelated_security_fingerprint"] == identity_after["unrelated_security_fingerprint"],
                "reviewed_identity_registry_preserved": registry_before == registry_after,
                "provider_history_preserved": provider_before == provider_after,
                "target_security_ids_preserved": {
                    int(row["security_id"]) for row in identity_after["target_security_rows"]
                } == target_security_ids,
                "target_securities_inactive": all(
                    int(row.get("active") or 0) == 0 for row in identity_after["target_security_rows"]
                ),
            }
            if not all(identity_invariants.values()):
                raise RuntimeError("REMOVE_TICKERS_IDENTITY_INVARIANT_FAILED")
            universe_invariants = _candidate_universe_state(lane.paths.canonical_db, eligible)
            ttm_invariants = _candidate_ttm_state(lane.paths.canonical_db, eligible)
            candidate_health = {
                role: _database_health(path)
                for role, path in {
                    "provider": lane.paths.provider_db,
                    "canonical": lane.paths.canonical_db,
                    "analysis_input_copy": lane.paths.analysis_db,
                }.items()
            }
            if not universe_invariants["passed"]:
                raise RuntimeError("REMOVE_TICKERS_ACTIVE_UNIVERSE_INVARIANT_FAILED")
            if not ttm_invariants["passed"]:
                raise RuntimeError("REMOVE_TICKERS_TTM_RECONCILIATION_FAILED")
            if not all(item["passed"] for item in candidate_health.values()):
                raise RuntimeError("REMOVE_TICKERS_CANDIDATE_DATABASE_HEALTH_FAILED")
            candidate_source_paths = replace(
                lane.paths, market_db=source_paths.market_db, taxonomy_db=source_paths.taxonomy_db,
            )
            candidate_source_dir = lane.lane_dir / "read_only_sources"
            with source_context(
                candidate_source_paths,
                bundle_dir=candidate_source_dir / "market_source_bundle",
                as_of_date=as_of_date or started[:10], tickers=requested,
                operation_id=f"{run_id}:candidate",
            ) as candidate_source_evidence:
                candidate_sources = {
                    "provider": lane.paths.provider_db,
                    "canonical": lane.paths.canonical_db,
                    "market": Path(candidate_source_evidence["market"]["bundle_path"]),
                    "taxonomy": source_paths.taxonomy_db,
                }
                downstream = downstream_runner(
                    candidate_sources,
                    output=lane.lane_dir / "full_v2_downstream",
                    as_of_date=as_of_date or started[:10],
                )
                candidate_binding = semantic_source_binding(candidate_source_evidence)
            candidate_analysis = Path(downstream["candidate_analysis_db"])
            candidate_health["analysis_rebuilt"] = _database_health(candidate_analysis)
            if not candidate_health["analysis_rebuilt"]["passed"]:
                raise RuntimeError("REMOVE_TICKERS_REBUILT_ANALYSIS_HEALTH_FAILED")
            ticker_results = []
            for item in current_items:
                evidence = (
                    _derived_participation(
                        candidate_analysis, ticker=str(item["requested_ticker"]),
                        company_id=int(item["company_id"]), security_id=int(item["security_id"]),
                    )
                    if item.get("company_id") is not None and item.get("security_id") is not None
                    else {"removed_current_participation": True, "target_rows_total": 0}
                )
                ticker_results.append({
                    "ticker": item["requested_ticker"], "classification": item["classification"],
                    "company_id": item["company_id"], "security_id": item["security_id"], **evidence,
                })
            if not all(item["removed_current_participation"] for item in ticker_results if item["classification"] != "ALREADY_ABSENT"):
                raise RuntimeError("REMOVE_TICKERS_DERIVED_CURRENT_PARTICIPATION_REMAINS")
            if downstream.get("invocation_counts", {}).get("full_v2_rebuild") != 1:
                raise RuntimeError("REMOVE_TICKERS_FULL_V2_REBUILD_COUNT_INVALID")
            result.update(
                outcome="COMPLETED", ticker_results=ticker_results,
                exact_candidate_mutation_set=[
                    mutation_item
                    for item in eligible for mutation_item in item["canonical"]["expected_mutation_set"]
                ],
                candidate_mutation=mutation,
                post_mutation_operational_universe_fingerprint=mutation["new_universe"]["economic_result_fingerprint"],
                identity_invariants=identity_invariants,
                active_universe_invariants=universe_invariants,
                ttm_active_security_invariants=ttm_invariants,
                candidate_database_health=candidate_health,
                ttm_reconciliation=ttm,
                structural_reconciliation=structural,
                market_taxonomy_binding=candidate_binding,
                downstream=downstream,
                removed_current_state_participation_verified=True,
            )
            if progress_callback:
                progress_callback({
                    "current_stage_number": 3, "total_declared_stages": 3,
                    "current_stage_id": "FINAL_VALIDATION", "stage_state": "COMPLETED",
                    "message": "Remove Tickers candidate validation completed.", "run_id": run_id,
                })
            return result
    except Exception as exc:
        result.update(
            outcome="FAILED", failed_stage="TEST_ON_COPIES",
            errors=[{"type": type(exc).__name__, "message": str(exc)}],
        )
        return result
    finally:
        cleanup = {"removed_count": 0, "removed_files": []}
        if lane is not None:
            cleanup = cleanup_copy_lane(lane)
        shutil.rmtree(run_temp, ignore_errors=True)
        result["cleanup"] = {
            **cleanup, "run_temp_exists": run_temp.exists(), "status": "COMPLETED",
        }
        result["completed_at_utc"] = utc_now()
        after_live = _file_state(source_paths)
        result["production_changed"] = before_live != after_live
        if result["production_changed"]:
            result["outcome"] = "FAILED"
            result.setdefault("errors", []).append({
                "type": "RuntimeError", "message": "REMOVE_TICKERS_TEST_CHANGED_PRODUCTION",
            })
        writer.write_json("remove_tickers_test_evidence.json", result)
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_test_report(result))
        writer.write_manifest()


class StaleRemoveTickersAuthorization(RuntimeError):
    pass


class SimulatedRemoveTickersPublicationCrash(BaseException):
    """Fault injection that models process death without ordinary rollback."""


def _load_production_authorization(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    test_run_id: str,
    run_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = run_root.resolve()
    preview_path = preview_payload_path.resolve(strict=True)
    if (
        preview_payload_path.is_symlink()
        or preview_path.name != "remove_tickers_preview.json"
        or root not in preview_path.parents
    ):
        raise ValueError("REMOVE_TICKERS_PRODUCTION_PREVIEW_PATH_INVALID")
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    eligible = [item for item in preview.get("removal_plan") or () if item.get("removal_eligible")]
    if (
        preview.get("contract_version") != CONTRACT_VERSION
        or preview.get("operation_type") != AdminOperationType.REMOVE_TICKERS.value
        or preview.get("mode") != "PREVIEW"
        or preview.get("outcome") != "COMPLETED"
        or preview.get("preview_fingerprint") != preview_fingerprint
        or fingerprint(preview.get("plan_binding")) != preview_fingerprint
        or not eligible
    ):
        raise ValueError("REMOVE_TICKERS_PRODUCTION_ELIGIBLE_PREVIEW_REQUIRED")
    if not test_run_id or Path(test_run_id).name != test_run_id or ".." in test_run_id:
        raise ValueError("REMOVE_TICKERS_PRODUCTION_TEST_RUN_ID_REQUIRED")
    test_dir = (root / test_run_id).resolve()
    if root not in test_dir.parents or test_dir.name != test_run_id:
        raise ValueError("REMOVE_TICKERS_PRODUCTION_TEST_PATH_INVALID")
    test_path = test_dir / "result.json"
    evidence_path = test_dir / "remove_tickers_test_evidence.json"
    if test_path.is_symlink() or evidence_path.is_symlink():
        raise ValueError("REMOVE_TICKERS_PRODUCTION_TEST_EVIDENCE_INVALID")
    test = json.loads(test_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    expected_mutations = [
        mutation
        for item in eligible
        for mutation in item["canonical"]["expected_mutation_set"]
    ]
    requested = list(preview.get("request", {}).get("normalized_inputs") or ())
    resolved = [
        (item.get("requested_ticker"), item.get("company_id"), item.get("security_id"))
        for item in preview.get("removal_plan") or ()
    ]
    tested_resolved = [
        (item.get("ticker"), item.get("company_id"), item.get("security_id"))
        for item in test.get("ticker_results") or ()
    ]
    valid = (
        test == evidence
        and test.get("contract_version") == TEST_CONTRACT_VERSION
        and test.get("operation_type") == AdminOperationType.REMOVE_TICKERS.value
        and test.get("mode") == "COPY_ONLY_APPLY"
        and test.get("outcome") == "COMPLETED"
        and test.get("preview_run_id") == preview.get("run_id")
        and test.get("preview_fingerprint") == preview_fingerprint
        and test.get("requested_tickers") == requested
        and tested_resolved == resolved
        and test.get("exact_candidate_mutation_set") == expected_mutations
        and test.get("removed_current_state_participation_verified") is True
        and test.get("production_changed") is False
        and test.get("production_available") is False
        and test.get("cleanup", {}).get("run_temp_exists") is False
        and test.get("downstream", {}).get("invocation_counts", {}).get("full_v2_rebuild") == 1
        and test.get("active_universe_invariants", {}).get("passed") is True
        and test.get("ttm_active_security_invariants", {}).get("passed") is True
        and all(test.get("identity_invariants", {}).values())
    )
    binding = test.get("market_taxonomy_binding") or {}
    if (
        not valid
        or binding.get("market", {}).get("mode") != "STABLE_SOURCE_BUNDLE"
        or binding.get("market", {}).get("source_contract_version") != SOURCE_CONTRACT_VERSION
        or binding.get("taxonomy", {}).get("mode") != "DIRECT_LOCKED_READ"
    ):
        raise StaleRemoveTickersAuthorization(
            "REMOVE_TICKERS_PRODUCTION_MATCHING_SUCCESSFUL_TEST_REQUIRED"
        )
    return preview, test


def _build_production_candidate(
    *,
    source_paths: BatchAddTickerPaths,
    items: Sequence[Mapping[str, Any]],
    requested: Sequence[str],
    lane: CopyLane,
    source_context: Callable[..., Any],
    downstream_runner: Callable[..., dict[str, Any]],
    as_of_date: str,
    applied_at: str,
    run_id: str,
) -> dict[str, Any]:
    eligible = [item for item in items if item.get("removal_eligible")]
    target_security_ids = {int(item["security_id"]) for item in eligible}
    identity_before = _identity_state(lane.paths.canonical_db, target_security_ids=target_security_ids)
    provider_before = _sha256(lane.paths.provider_db)
    registry_before = _registry_fingerprint()
    mutation = _mutate_candidate_universe(lane.paths.canonical_db, eligible, applied_at=applied_at)
    ttm = rebuild_ttm(lane.paths.canonical_db, applied_at=applied_at)
    structural = structural_break.apply_contract(
        lane.paths.canonical_db, events=_events(), applied_at_utc=applied_at,
    )
    identity_after = _identity_state(lane.paths.canonical_db, target_security_ids=target_security_ids)
    identity_invariants = {
        "permanent_company_security_identity_preserved": identity_before["permanent_identity_fingerprint"] == identity_after["permanent_identity_fingerprint"],
        "ticker_alias_history_preserved": identity_before["alias_fingerprint"] == identity_after["alias_fingerprint"],
        "company_rows_preserved": identity_before["company_fingerprint"] == identity_after["company_fingerprint"],
        "unrelated_securities_unchanged": identity_before["unrelated_security_fingerprint"] == identity_after["unrelated_security_fingerprint"],
        "reviewed_identity_registry_preserved": registry_before == _registry_fingerprint(),
        "provider_history_preserved": provider_before == _sha256(lane.paths.provider_db),
        "target_security_ids_preserved": {
            int(row["security_id"]) for row in identity_after["target_security_rows"]
        } == target_security_ids,
        "target_securities_inactive": all(
            int(row.get("active") or 0) == 0 for row in identity_after["target_security_rows"]
        ),
    }
    universe = _candidate_universe_state(lane.paths.canonical_db, eligible)
    ttm_state = _candidate_ttm_state(lane.paths.canonical_db, eligible)
    if not all(identity_invariants.values()) or not universe["passed"] or not ttm_state["passed"]:
        raise RuntimeError("REMOVE_TICKERS_PRODUCTION_CANDIDATE_INVARIANT_FAILED")
    candidate_paths = replace(
        lane.paths, market_db=source_paths.market_db, taxonomy_db=source_paths.taxonomy_db,
    )
    with source_context(
        candidate_paths,
        bundle_dir=lane.lane_dir / "read_only_sources" / "market_source_bundle",
        as_of_date=as_of_date,
        tickers=requested,
        operation_id=f"{run_id}:candidate",
    ) as source_evidence:
        sources = {
            "provider": lane.paths.provider_db,
            "canonical": lane.paths.canonical_db,
            "market": Path(source_evidence["market"]["bundle_path"]),
            "taxonomy": source_paths.taxonomy_db,
        }
        downstream = downstream_runner(
            sources, output=lane.lane_dir / "full_v2_downstream", as_of_date=as_of_date,
        )
        source_binding = semantic_source_binding(source_evidence)
    analysis_candidate = Path(downstream["candidate_analysis_db"])
    health = {
        "provider": _database_health(lane.paths.provider_db),
        "canonical": _database_health(lane.paths.canonical_db),
        "analysis": _database_health(analysis_candidate),
    }
    if (
        downstream.get("status") != "READY"
        or downstream.get("invocation_counts", {}).get("full_v2_rebuild") != 1
        or not all(item["passed"] for item in health.values())
    ):
        raise RuntimeError("REMOVE_TICKERS_PRODUCTION_FULL_V2_REBUILD_NOT_READY")
    ticker_results = []
    for item in items:
        participation = (
            _derived_participation(
                analysis_candidate,
                ticker=str(item["requested_ticker"]),
                company_id=int(item["company_id"]),
                security_id=int(item["security_id"]),
            )
            if item.get("company_id") is not None and item.get("security_id") is not None
            else {"removed_current_participation": True, "target_rows_total": 0}
        )
        ticker_results.append({
            "ticker": item["requested_ticker"], "classification": item["classification"],
            "company_id": item["company_id"], "security_id": item["security_id"],
            **participation,
        })
    if not all(
        item["removed_current_participation"]
        for item in ticker_results
        if item["classification"] != "ALREADY_ABSENT"
    ):
        raise RuntimeError("REMOVE_TICKERS_PRODUCTION_DERIVED_PARTICIPATION_REMAINS")
    return {
        "candidate_paths": {
            "provider": lane.paths.provider_db,
            "canonical": lane.paths.canonical_db,
            "analysis": analysis_candidate,
        },
        "mutation": mutation,
        "ttm": ttm,
        "structural": structural,
        "identity_before": identity_before,
        "identity_after": identity_after,
        "reviewed_identity_registry_fingerprint": registry_before,
        "identity_invariants": identity_invariants,
        "active_universe_invariants": universe,
        "ttm_active_security_invariants": ttm_state,
        "source_binding": source_binding,
        "downstream": downstream,
        "ticker_results": ticker_results,
        "candidate_database_health": health,
    }


def _assert_test_candidate_match(
    test: Mapping[str, Any], candidate: Mapping[str, Any], items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_mutations = [
        mutation
        for item in items if item.get("removal_eligible")
        for mutation in item["canonical"]["expected_mutation_set"]
    ]
    comparisons = {
        "requested_identity_set": [
            (item.get("ticker"), item.get("company_id"), item.get("security_id"))
            for item in test.get("ticker_results") or ()
        ] == [
            (item.get("ticker"), item.get("company_id"), item.get("security_id"))
            for item in candidate["ticker_results"]
        ],
        "mutation_set": test.get("exact_candidate_mutation_set") == expected_mutations,
        "operational_universe": test.get("post_mutation_operational_universe_fingerprint")
        == candidate["mutation"]["new_universe"]["economic_result_fingerprint"],
        "source_binding": test.get("market_taxonomy_binding") == candidate["source_binding"],
        "identity_contract": test.get("identity_invariants") == candidate["identity_invariants"],
        "ttm_fingerprint": test.get("ttm_reconciliation", {}).get("fingerprint")
        == candidate["ttm"].get("fingerprint"),
    }
    if not all(comparisons.values()):
        raise StaleRemoveTickersAuthorization(
            "REMOVE_TICKERS_TEST_BINDING_STALE:"
            + ",".join(key for key, matches in comparisons.items() if not matches)
        )
    return {"status": "MATCH", "comparisons": comparisons}


def _production_postflight(
    *,
    source_paths: BatchAddTickerPaths,
    items: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    roles: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    eligible = [item for item in items if item.get("removal_eligible")]
    universe = _candidate_universe_state(source_paths.canonical_db, eligible)
    ttm_state = _candidate_ttm_state(source_paths.canonical_db, eligible)
    identity = _identity_state(
        source_paths.canonical_db,
        target_security_ids={int(item["security_id"]) for item in eligible},
    )
    identity_matches = identity == candidate["identity_after"]
    registry_preserved = (
        _registry_fingerprint() == candidate["reviewed_identity_registry_fingerprint"]
    )
    ticker_results = [
        {
            "ticker": item["requested_ticker"],
            **_derived_participation(
                source_paths.analysis_db,
                ticker=str(item["requested_ticker"]),
                company_id=int(item["company_id"]),
                security_id=int(item["security_id"]),
            ),
        }
        for item in eligible
    ]
    role_fingerprints = {
        role: sqlite_verification(source_paths.as_dict()[role]) for role in PUBLICATION_ROLES
    }
    roles_match = all(
        role_fingerprints[role]["sha256"] == roles[role]["candidate_fingerprint"]
        for role in PUBLICATION_ROLES
    )
    passed = (
        universe["passed"]
        and ttm_state["passed"]
        and identity_matches
        and registry_preserved
        and roles_match
        and all(item["removed_current_participation"] for item in ticker_results)
    )
    if not passed:
        raise RuntimeError("REMOVE_TICKERS_PRODUCTION_POSTFLIGHT_FAILED")
    return {
        "passed": True,
        "active_universe_invariants": universe,
        "ttm_active_security_invariants": ttm_state,
        "identity_history_matches_candidate": identity_matches,
        "reviewed_identity_registry_preserved": registry_preserved,
        "removed_current_state": ticker_results,
        "database_integrity": role_fingerprints,
        "published_role_fingerprints_match": roles_match,
    }


def _render_production_report(result: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Remove Tickers Production", "",
        f"- Outcome: `{result.get('outcome')}`",
        f"- Preview fingerprint: `{result.get('preview_fingerprint')}`",
        f"- Test run: `{result.get('test_run_id')}`",
        f"- Publication roles: `{','.join(result.get('write_set') or ())}`",
        f"- Postflight: `{(result.get('postflight') or {}).get('passed', False)}`",
        f"- Rollback: `{(result.get('rollback') or {}).get('status', 'NOT_REQUIRED')}`",
        "- Market/taxonomy publication roles: `No`", "",
    ])


def run_production_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    test_run_id: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = ADMIN_TEMP_ROOT,
    backup_root: Path = BACKUP_ROOT,
    journal_path: Path = ACTIVE_JOURNAL_PATH,
    lock_path: Path = ADMIN_LOCK,
    scheduler_log_dir: str | None = None,
    confirm_production: bool = False,
    production_intent: bool = False,
    rehearsal: bool = False,
    source_context: Callable[..., Any] = _shared_sources,
    downstream_runner: Callable[..., dict[str, Any]] = run_full_v2_downstream,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    inject_failure_at: str | None = None,
    inject_crash_at: str | None = None,
    taxonomy_evidence_root: Path | None = None,
) -> dict[str, Any]:
    if not confirm_production:
        raise PermissionError("REMOVE_TICKERS_PRODUCTION_CONFIRMATION_REQUIRED")
    production_paths = {role: path.resolve() for role, path in PRODUCTION.items()}
    actual_production = source_paths.analysis_db.resolve() == production_paths["analysis"]
    if actual_production != (production_intent and not rehearsal):
        raise PermissionError("REMOVE_TICKERS_EXPLICIT_PRODUCTION_INTENT_REQUIRED")
    if actual_production:
        if any(source_paths.as_dict()[role].resolve() != production_paths[role] for role in source_paths.as_dict()):
            raise PermissionError("REMOVE_TICKERS_EXACT_PRODUCTION_PATHS_REQUIRED")
        if (
            run_root.resolve() != ADMIN_RUN_ROOT.resolve()
            or journal_path.resolve() != ACTIVE_JOURNAL_PATH.resolve()
            or lock_path.resolve() != ADMIN_LOCK.resolve()
        ):
            raise PermissionError("REMOVE_TICKERS_PRODUCTION_GUARD_PATH_OVERRIDE_REJECTED")
    elif any(path.resolve() in set(production_paths.values()) for path in source_paths.as_dict().values()):
        raise PermissionError("REMOVE_TICKERS_REHEARSAL_MUST_USE_ONLY_COPIES")
    run_id = stable_run_id(
        AdminOperationType.REMOVE_TICKERS,
        preview_fingerprint,
        suffix="production" if actual_production else "transaction_rehearsal",
    ) + "_" + secrets.token_hex(4)
    writer = AdminRunWriter(run_id, AdminOperationType.REMOVE_TICKERS, root=run_root)
    started = utc_now()
    lane_dir = temp_root / run_id
    backup_dir = backup_root / run_id
    stage = "PRODUCTION_PREFLIGHT"
    lane: CopyLane | None = None
    journal: dict[str, Any] | None = None
    write_boundary_crossed = False
    before_files: dict[str, Any] | None = None
    result: dict[str, Any] = {
        "contract_version": PRODUCTION_CONTRACT_VERSION,
        "operation_type": AdminOperationType.REMOVE_TICKERS.value,
        "mode": "PRODUCTION_APPLY" if actual_production else "TRANSACTION_REHEARSAL",
        "run_id": run_id,
        "artifact_dir": str(writer.run_dir),
        "preview_fingerprint": preview_fingerprint,
        "test_run_id": test_run_id,
        "started_at_utc": started,
        "outcome": "FAILED",
        "write_set": list(PUBLICATION_ROLES),
        "full_market_copy_created": False,
        "full_taxonomy_copy_created": False,
        "warnings": [],
    }

    def progress(state: str, message: str) -> None:
        payload = {
            "run_id": run_id, "operation_type": AdminOperationType.REMOVE_TICKERS.value,
            "current_stage_id": stage, "stage_state": state,
            "message": message, "timestamp_utc": utc_now(),
        }
        writer.write_json("progress_status.json", payload)
        writer.append_jsonl("progress_events.jsonl", payload)
        if progress_callback:
            try:
                progress_callback(payload)
            except Exception:
                pass

    def crash(point: str) -> None:
        if inject_crash_at == point:
            raise SimulatedRemoveTickersPublicationCrash(
                f"SIMULATED_REMOVE_TICKERS_PUBLICATION_CRASH:{point}"
            )

    writer.write_json("request.json", {
        "operation_type": AdminOperationType.REMOVE_TICKERS.value,
        "preview_payload_path": str(preview_payload_path),
        "preview_fingerprint": preview_fingerprint,
        "test_run_id": test_run_id,
    })
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Remove Tickers Production requested.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message="Remove Tickers Production preflight started.", preview_fingerprint=preview_fingerprint)
    locks = ExitStack()
    try:
        progress("RUNNING", "Acquiring Production, scheduler and taxonomy locks before recovery preflight.")
        owner = locks.enter_context(production_lock(lock_path=lock_path, scheduler_log_dir=scheduler_log_dir))
        taxonomy_lock = locks.enter_context(taxonomy_operation_lock_context(
            deployment_id="FUNDAMENTALS",
            operation_type="REMOVE_TICKERS_PRODUCTION_DIRECT_LOCKED_READ",
            operation_id=f"{run_id}:taxonomy",
            evidence_root=taxonomy_evidence_root,
        ))
        result["lock_owner"] = owner
        result["taxonomy_lock"] = {"lock_path": taxonomy_lock.lock_path, "operation_id": taxonomy_lock.operation_id}
        result["recovery_preflight"] = guard_production_writes(journal_path)
        if actual_production:
            result["git_state"] = _assert_clean_worktree()
            if result["git_state"].get("dirty"):
                result["warnings"].append({
                    "code": "DIRTY_GIT_WORKTREE",
                    "message": "Git worktree contains uncommitted changes.",
                })
            elif result["git_state"].get("error"):
                result["warnings"].append({
                    "code": "GIT_STATE_UNAVAILABLE",
                    "message": "Git provenance could not be read.",
                })
        preview, test = _load_production_authorization(
            preview_payload_path=preview_payload_path,
            preview_fingerprint=preview_fingerprint,
            test_run_id=test_run_id,
            run_root=run_root,
        )
        result["preview_run_id"] = preview.get("run_id")
        requested = tuple(preview.get("request", {}).get("normalized_inputs") or ())
        as_of_date = str(preview.get("started_at_utc") or started)[:10]
        before_files = _production_file_state(source_paths)
        result["production_file_state_before"] = before_files
        preflight_dir = temp_root / f".{run_id}.preflight"
        try:
            with source_context(
                source_paths,
                bundle_dir=preflight_dir / "market_source_bundle",
                as_of_date=as_of_date,
                tickers=requested,
                operation_id=f"{run_id}:preflight",
            ) as source_evidence:
                current_items = _plan_items(source_paths, requested)
                current_binding = _build_plan_binding(
                    current_items, requested, semantic_source_binding(source_evidence),
                )
        finally:
            shutil.rmtree(preflight_dir, ignore_errors=True)
        if current_binding != preview.get("plan_binding") or fingerprint(current_binding) != preview_fingerprint:
            raise StaleRemoveTickersAuthorization("REMOVE_TICKERS_PREVIEW_STALE")
        if any(item["classification"] in {"REMOVAL_BLOCKED", "AMBIGUOUS_IDENTITY_REVIEW_REQUIRED"} for item in current_items):
            raise StaleRemoveTickersAuthorization("REMOVE_TICKERS_ELIGIBILITY_CHANGED")
        progress("COMPLETED", "Recovery, Preview, Test, identity and source authorization passed.")

        stage = "CANDIDATE_BUILD"
        progress("RUNNING", "Building provider, canonical and analysis candidates.")
        lane = create_copy_lane(
            source_paths, lane_dir=lane_dir, writer=writer,
            roles=("provider", "canonical", "analysis"),
        )
        candidate = _build_production_candidate(
            source_paths=source_paths,
            items=current_items,
            requested=requested,
            lane=lane,
            source_context=source_context,
            downstream_runner=downstream_runner,
            as_of_date=as_of_date,
            applied_at=started,
            run_id=run_id,
        )
        result["candidate"] = {
            key: value for key, value in candidate.items()
            if key not in {"candidate_paths", "identity_before", "identity_after"}
        }
        result["test_to_production_binding"] = _assert_test_candidate_match(
            test, candidate, current_items,
        )
        if before_files != _production_file_state(source_paths):
            raise RuntimeError("REMOVE_TICKERS_PRODUCTION_DATABASE_CHANGED_DURING_CANDIDATE_BUILD")
        result["storage_preflight"] = _storage_preflight(
            source_paths, tuple(PUBLICATION_ROLES), backup_root,
        )
        progress("COMPLETED", "Candidate generation matches the successful Test evidence.")

        stage = "BACKUP"
        result["backups"] = _verified_backups(source_paths, backup_dir)
        if inject_failure_at == "BEFORE_PREPARED":
            raise RuntimeError("INJECTED_REMOVE_TICKERS_PRE_PUBLICATION_FAILURE")

        stage = "JOURNAL_PREPARE"
        roles = _candidate_manifest(candidate["candidate_paths"], result["backups"])
        journal = prepare_journal(
            path=journal_path,
            operation_type=AdminOperationType.REMOVE_TICKERS.value,
            run_id=run_id,
            preview_run_id=str(preview.get("run_id") or preview_payload_path.resolve().parent.name),
            test_run_id=test_run_id,
            refresh_set_fingerprint=preview_fingerprint,
            old_source_watermark=None,
            new_source_watermark=as_of_date,
            source_schema_fingerprint=SOURCE_CONTRACT_VERSION,
            roles=roles,
        )
        result["journal"] = journal
        crash("AFTER_PREPARED")
        if inject_failure_at == "BEFORE_FIRST_REPLACEMENT":
            raise RuntimeError("INJECTED_REMOVE_TICKERS_PRE_PUBLICATION_FAILURE")
        boundary_preview, boundary_test = _load_production_authorization(
            preview_payload_path=preview_payload_path,
            preview_fingerprint=preview_fingerprint,
            test_run_id=test_run_id,
            run_root=run_root,
        )
        if (
            boundary_preview != preview
            or boundary_test != test
            or before_files != _production_file_state(source_paths)
        ):
            raise StaleRemoveTickersAuthorization(
                "REMOVE_TICKERS_PUBLICATION_BOUNDARY_AUTHORIZATION_STALE"
            )
        result["publication_boundary_revalidation"] = "PASSED"

        for role in PUBLICATION_ROLES:
            stage = f"PUBLISH_{role.upper()}"
            if not write_boundary_crossed:
                writer.checkpoint(
                    RunStage.WRITE_BOUNDARY_CROSSED,
                    message="Journaled Remove Tickers publication started.",
                    preview_fingerprint=preview_fingerprint,
                    write_boundary_crossed=True,
                )
                write_boundary_crossed = True
            journal = _replace_role(role, journal, journal_path=journal_path)
            result["journal"] = journal
            crash(f"AFTER_{role.upper()}_REPLACEMENT")
            if inject_failure_at == f"AFTER_{role.upper()}_REPLACEMENT":
                raise RuntimeError(f"INJECTED_REMOVE_TICKERS_PUBLICATION_FAILURE:{role}")

        stage = "POSTFLIGHT"
        journal = update_journal(
            journal_path, journal, state="POSTFLIGHT",
            current_publication_step="POSTFLIGHT", postflight_state="RUNNING",
        )
        result["journal"] = journal
        if inject_failure_at == "POSTFLIGHT":
            raise RuntimeError("INJECTED_REMOVE_TICKERS_POSTFLIGHT_FAILURE")
        result["postflight"] = _production_postflight(
            source_paths=source_paths, items=current_items, candidate=candidate, roles=roles,
        )
        journal = update_journal(
            journal_path, journal, state="COMPLETED",
            current_publication_step="COMPLETED", postflight_state="PASSED",
            rollback_recovery_state="NOT_REQUIRED",
        )
        result["journal"] = journal
        result["outcome"] = "COMPLETED"
        result["rollback"] = {"status": "NOT_REQUIRED"}
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["errors"] = [{"type": type(exc).__name__, "message": str(exc)}]
        result["failed_stage"] = stage
        stale = isinstance(exc, StaleRemoveTickersAuthorization)
        recovery_retry = isinstance(exc, PublicationRecoveredRetryRequired)
        recovery_failed = isinstance(exc, PublicationRecoveryError) and not recovery_retry
        if recovery_retry:
            result["outcome"] = "RETRY_REQUIRED"
            result["publication_recovery"] = exc.recovery
        elif recovery_failed:
            result["outcome"] = "RECOVERY_FAILED"
        elif stale:
            result["outcome"] = "STALE_PREVIEW_OR_TEST"
        if journal is not None and write_boundary_crossed:
            try:
                journal = update_journal(
                    journal_path, journal, state="ROLLING_BACK",
                    rollback_recovery_state="ROLLING_BACK_COMPLETE_SET",
                )
                recovered = restore_old_generation(journal, journal_path=journal_path)
                journal = update_journal(
                    journal_path, recovered["journal"], state="ROLLED_BACK",
                    rollback_recovery_state="OLD_GENERATION_RESTORED_AND_VERIFIED",
                )
                result["journal"] = journal
                result["rollback"] = {"status": "ROLLED_BACK", "roles": recovered["roles"]}
                result["outcome"] = "FAILED_ROLLED_BACK"
            except Exception as rollback_exc:
                result["rollback"] = {
                    "status": "CRITICAL_ROLLBACK_FAILED",
                    "error": f"{type(rollback_exc).__name__}: {rollback_exc}",
                }
                result["outcome"] = "CRITICAL_ROLLBACK_FAILED"
        elif not write_boundary_crossed:
            if journal is not None:
                journal_path.unlink(missing_ok=True)
                fsync_directory(journal_path.parent)
                journal = None
            backup_dir_existed = backup_dir.exists()
            shutil.rmtree(backup_dir, ignore_errors=True)
            if backup_dir_existed:
                fsync_directory(backup_dir.parent)
            result["pre_publication_cleanup"] = {
                "journal_removed": not journal_path.exists(),
                "backup_directory_removed": not backup_dir.exists(),
            }
            result["database_safety"] = "NO_PRODUCTION_DATABASES_MODIFIED"
            result["retry_authorization"] = {
                "direct_production_retry_available": False,
                "preview_test_preserved": False,
                "preview_test_rerun_required": True,
                "reason": (
                    "RECOVERY_COMPLETED_FRESH_INVOCATION_REQUIRED"
                    if recovery_retry else "STALE_OR_FAILED_PREPUBLICATION_VALIDATION"
                ),
            }
    finally:
        try:
            result["cleanup"] = _cleanup_candidate_lane(lane_dir, journal)
        finally:
            locks.close()
        if before_files is not None:
            result["production_file_state_after"] = _production_file_state(source_paths)
            result["production_file_state_unchanged"] = (
                before_files == result["production_file_state_after"]
            )
        result["publication_activity"] = _publication_activity(journal)
        result["completed_at_utc"] = utc_now()
        writer.write_json("result.json", result)
        writer.write_text("operation_report.md", _render_production_report(result))
        terminal = (
            RunStage.COMPLETED
            if result.get("outcome") == "COMPLETED"
            else RunStage.FAILED_AFTER_WRITE
            if write_boundary_crossed
            else RunStage.FAILED_BEFORE_WRITE
        )
        try:
            writer.checkpoint(
                terminal,
                message=f"Remove Tickers Production {result.get('outcome')}.",
                preview_fingerprint=preview_fingerprint,
                write_boundary_crossed=write_boundary_crossed,
            )
        except ValueError:
            pass
        writer.write_exit_code(0 if result.get("outcome") == "COMPLETED" else 3)
        writer.write_manifest()
    return result
