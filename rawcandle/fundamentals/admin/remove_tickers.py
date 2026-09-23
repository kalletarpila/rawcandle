"""Read-only Remove Tickers planning for Fundamentals Administration."""

from __future__ import annotations

import shutil
import sqlite3
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import AdminOperationType, build_batch_request, fingerprint, utc_now
from rawcandle.fundamentals.admin.publication_journal import ACTIVE_JOURNAL_PATH, safety_status
from rawcandle.fundamentals.admin.source_bundle import (
    SOURCE_CONTRACT_VERSION,
    TaxonomySourceMode,
    bind_taxonomy_source,
    prepare_protected_read_only_sources,
    semantic_source_binding,
)
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import load_active_dc_memberships


CONTRACT_VERSION = "PHASE13G3_34_REMOVE_TICKERS_PREVIEW_V1"
MAX_TICKERS = 25
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


@contextmanager
def _shared_sources(
    paths: BatchAddTickerPaths,
    *,
    bundle_dir: Path,
    as_of_date: str,
    tickers: Sequence[str],
    operation_id: str,
) -> Iterator[dict[str, Any]]:
    with taxonomy_operation_lock_context(
        deployment_id="FUNDAMENTALS",
        operation_type="REMOVE_TICKERS_PREVIEW_DIRECT_LOCKED_READ",
        operation_id=operation_id,
    ) as operation_lock:
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
        yield evidence


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
        "No Test or Production mutation is available in this phase.", "",
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
            items = [_plan_item(source_paths, ticker) for ticker in request.normalized_inputs]
    finally:
        shutil.rmtree(bundle_dir.parent, ignore_errors=True)
    plan_binding = {
        "contract_version": CONTRACT_VERSION,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "requested_tickers": list(request.normalized_inputs),
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
        "read_only_source_binding": source_binding,
    }
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
        "recommended_next_action": "Review the removal plan. Test and Production are not available in this phase.",
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
