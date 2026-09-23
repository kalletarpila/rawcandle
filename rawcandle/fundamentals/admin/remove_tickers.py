"""Remove Tickers Preview and candidate-only Test for Fundamentals Administration."""

from __future__ import annotations

import fcntl
import hashlib
import json
import shutil
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import (
    BatchAddTickerPaths,
    CopyLane,
    cleanup_copy_lane,
    create_copy_lane,
)
from rawcandle.fundamentals.admin.contracts import AdminOperationType, build_batch_request, fingerprint, utc_now
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.identity_resolution import DEFAULT_REGISTRY_PATH
from rawcandle.fundamentals.admin.publication_journal import ACTIVE_JOURNAL_PATH, safety_status
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
from rawcandle.fundamentals.phase12d import rebuild_ttm
from rawcandle.fundamentals.phase13b_foundation import universe_identity


CONTRACT_VERSION = "PHASE13G3_34_REMOVE_TICKERS_PREVIEW_V1"
TEST_CONTRACT_VERSION = "PHASE13G3_35_REMOVE_TICKERS_TEST_V1"
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
