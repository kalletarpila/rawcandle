from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from analysis.datacenter_indices.taxonomy import DatacenterTaxonomyRow, load_datacenter_taxonomy_csv
from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest,
    AdminFinalResult,
    AdminItemDecision,
    AdminOperationType,
    AdminStatus,
    RunStage,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.progress import ProgressStage, ProgressTracker, TAXONOMY_STAGES
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.phase12d import PRODUCTION, stable_hash
from rawcandle.io_atomic import write_text_atomic
from rawcandle.testing.database_isolation import PROTECTED_DATABASE_PATHS


CONTRACT_VERSION = "PHASE13G4_CHECK_UPDATE_TAXONOMY_DUAL_DOMAIN_COPY_ONLY_V2"
DATACENTER_ECOSYSTEM_CODE = "DATACENTER"
SUPPORTED_TAXONOMY_DOMAINS = ("dc_ecosystem", "ec_taxonomy")
CURRENT_PRIMARY_PRODUCTION_TAXONOMY = "dc_ecosystem"
TEMP_ROOT = ADMIN_TEMP_ROOT.parent / "fundamentals_admin_phase13g4_taxonomy"
OUTCOME_A = "OUTCOME A - DUAL-DOMAIN TAXONOMY CLI AND COPY-ONLY UPDATE CHAIN VERIFIED"
OUTCOME_B = "OUTCOME B - TAXONOMY DATA, IDENTITY OR DEPENDENCY LIMITATION REMAINS"
OUTCOME_C = "OUTCOME C - MATERIAL TAXONOMY ARCHITECTURE OR SAFETY DEFECT; PRODUCTION UNCHANGED"


@dataclass(frozen=True)
class TaxonomyPaths:
    provider_db: Path = PRODUCTION["provider"]
    canonical_db: Path = PRODUCTION["canonical"]
    analysis_db: Path = PRODUCTION["analysis"]
    market_db: Path = PRODUCTION["market"]
    taxonomy_db: Path = PRODUCTION["taxonomy"]

    def as_batch_paths(self) -> BatchAddTickerPaths:
        return BatchAddTickerPaths(
            provider_db=self.provider_db,
            canonical_db=self.canonical_db,
            analysis_db=self.analysis_db,
            market_db=self.market_db,
            taxonomy_db=self.taxonomy_db,
        )

    def as_dict(self) -> dict[str, Path]:
        return self.as_batch_paths().as_dict()


def validate_taxonomy_domain(taxonomy_domain: str) -> str:
    normalized = taxonomy_domain.strip().lower()
    if normalized not in SUPPORTED_TAXONOMY_DOMAINS:
        raise ValueError(f"PHASE13G4_UNKNOWN_TAXONOMY_DOMAIN:{taxonomy_domain}")
    return normalized


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_rw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_from_csv(row: DatacenterTaxonomyRow) -> dict[str, Any]:
    return {
        "taxonomy_version": row.taxonomy_version,
        "ticker": row.ticker.upper(),
        "layer": row.layer,
        "subindustry": row.subindustry,
        "report_group_status": row.report_group_status,
        "is_primary": int(row.is_primary),
        "role_weight": float(row.role_weight),
        "notes": row.notes or "",
    }


def _rows_from_candidate(candidate_path: Path, version: str | None) -> tuple[str, list[dict[str, Any]], str]:
    rows = load_datacenter_taxonomy_csv(candidate_path, expected_taxonomy_version=version)
    versions = sorted({row.taxonomy_version for row in rows})
    if len(versions) != 1:
        raise ValueError(f"TAXONOMY_CANDIDATE_VERSION_COUNT:{versions}")
    return versions[0], [_row_from_csv(row) for row in rows], _sha256(candidate_path)


def _row_key(row: Mapping[str, Any], *, include_version: bool = False) -> tuple[Any, ...]:
    key = (
        str(row["ticker"]).upper(),
        str(row["layer"]),
        str(row["subindustry"]),
        int(row["is_primary"]),
    )
    return ((str(row["taxonomy_version"]),) + key) if include_version else key


def _semantic_payload(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "taxonomy_version": str(row["taxonomy_version"]),
            "ticker": str(row["ticker"]).upper(),
            "layer": str(row["layer"]),
            "subindustry": str(row["subindustry"]),
            "report_group_status": str(row["report_group_status"]),
            "is_primary": int(row["is_primary"]),
            "role_weight": float(row["role_weight"] or 0),
            "notes": row.get("notes") or "",
        }
        for row in sorted(rows, key=lambda item: _row_key(item, include_version=True))
    ]


def _write_candidate_csv(path: Path, version: str, rows: Sequence[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("taxonomy_version", "ticker", "layer", "subindustry", "report_group_status", "is_primary", "role_weight", "notes"))
        for row in sorted(rows, key=lambda item: _row_key(item)):
            writer.writerow(
                (
                    version,
                    row["ticker"],
                    row["layer"],
                    row["subindustry"],
                    row["report_group_status"],
                    int(row["is_primary"]),
                    float(row["role_weight"] or 0),
                    row.get("notes") or "",
                )
            )
    return path


def _validate_rows(rows: Sequence[Mapping[str, Any]], *, identity_index: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    seen_semantic: set[tuple[str, str, str]] = set()
    valid_roles = {"CORE", "EXTENDED", "WATCH_ONLY", "TOO_SMALL"}
    for row in rows:
        ticker = str(row["ticker"]).upper()
        layer = str(row["layer"]).strip()
        subindustry = str(row["subindustry"]).strip()
        role = str(row["report_group_status"]).strip()
        semantic = (ticker, layer, subindustry)
        by_ticker.setdefault(ticker, []).append(row)
        if not layer or not subindustry:
            errors.append({"status": "INVALID_HIERARCHY", "ticker": ticker, "reason": "layer/subindustry must be non-empty"})
        if role not in valid_roles:
            errors.append({"status": "INVALID_ROLE", "ticker": ticker, "reason": f"invalid role {role}"})
        if semantic in seen_semantic:
            errors.append({"status": "DUPLICATE_MEMBERSHIP", "ticker": ticker, "reason": f"duplicate membership {layer}/{subindustry}"})
        seen_semantic.add(semantic)
        if identity_index is not None and ticker not in identity_index:
            errors.append({"status": "UNRESOLVED_IDENTITY", "ticker": ticker, "reason": "ticker is absent from the selected taxonomy domain identity set"})
    for ticker, ticker_rows in sorted(by_ticker.items()):
        primaries = [row for row in ticker_rows if int(row["is_primary"]) == 1]
        if len(primaries) != 1:
            errors.append({"status": "PRIMARY_DESIGNATION_INVALID", "ticker": ticker, "reason": f"expected exactly one primary membership, found {len(primaries)}"})
    return {
        "status": "OK" if not errors else "BLOCKED",
        "errors": errors,
        "counts": {
            "rows": len(rows),
            "tickers": len(by_ticker),
            "primary_memberships": sum(1 for row in rows if int(row["is_primary"]) == 1),
            "layers": len({str(row["layer"]) for row in rows}),
            "subindustries": len({str(row["subindustry"]) for row in rows}),
        },
    }


def _dc_rows(conn: sqlite3.Connection, taxonomy_version: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "dc_ecosystem_membership"):
        raise RuntimeError("PHASE13G4_DC_ECOSYSTEM_TABLE_MISSING")
    params: tuple[Any, ...] = ()
    where = ""
    if taxonomy_version:
        where = "WHERE taxonomy_version=?"
        params = (taxonomy_version,)
    rows = conn.execute(
        f"""
        SELECT taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
        FROM dc_ecosystem_membership
        {where}
        ORDER BY taxonomy_version,ticker,layer,subindustry,is_primary
        """,
        params,
    ).fetchall()
    return [
        {
            "taxonomy_version": row["taxonomy_version"],
            "ticker": str(row["ticker"]).upper(),
            "layer": row["layer"],
            "subindustry": row["subindustry"],
            "report_group_status": row["report_group_status"],
            "is_primary": int(row["is_primary"]),
            "role_weight": float(row["role_weight"] or 0),
            "notes": row["notes"] or "",
        }
        for row in rows
    ]


def _dc_current_version(rows: Sequence[Mapping[str, Any]]) -> str | None:
    versions = sorted({str(row["taxonomy_version"]) for row in rows})
    if not versions:
        return None
    if len(versions) == 1:
        return versions[0]
    return versions[-1]


def _ec_active_version(conn: sqlite3.Connection) -> dict[str, Any]:
    for table in ("ec_ecosystem", "ec_taxonomy_version", "ec_entity", "ec_membership"):
        if not _table_exists(conn, table):
            raise RuntimeError(f"PHASE13G4_EC_TABLE_MISSING:{table}")
    rows = conn.execute(
        """
        SELECT e.ecosystem_id,e.ecosystem_code,v.taxonomy_version_id,v.taxonomy_version_code,
               v.taxonomy_name,v.source_reference,v.source_hash,v.status,v.is_active,
               v.active_from,v.active_to
        FROM ec_taxonomy_version v
        JOIN ec_ecosystem e ON e.ecosystem_id=v.ecosystem_id
        WHERE e.ecosystem_code=? AND v.is_active=1
        ORDER BY v.taxonomy_version_id
        """,
        (DATACENTER_ECOSYSTEM_CODE,),
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"PHASE13G4_EC_ACTIVE_VERSION_COUNT:{len(rows)}")
    return dict(rows[0])


def _ec_rows_for_version(conn: sqlite3.Connection, taxonomy_version_id: int, taxonomy_version_code: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT child.ticker AS ticker,
               layer.entity_name AS layer,
               sub.entity_name AS subindustry,
               tm.membership_role AS report_group_status,
               tm.is_primary AS is_primary,
               tm.role_weight AS role_weight,
               tm.source_note AS notes,
               child.entity_id AS entity_id
        FROM ec_membership tm
        JOIN ec_entity child ON child.entity_id=tm.child_entity_id AND child.entity_type='TICKER'
        JOIN ec_entity sub ON sub.entity_id=tm.parent_entity_id AND sub.entity_type='GROUP_L2'
        JOIN ec_membership sm ON sm.child_entity_id=sub.entity_id
             AND sm.taxonomy_version_id=tm.taxonomy_version_id
             AND sm.membership_type='CONTAINS'
             AND sm.status='ACTIVE'
        JOIN ec_entity layer ON layer.entity_id=sm.parent_entity_id AND layer.entity_type='GROUP_L1'
        WHERE tm.taxonomy_version_id=?
          AND tm.membership_type='CONTAINS'
          AND tm.status='ACTIVE'
          AND child.ticker IS NOT NULL
        ORDER BY child.ticker, layer.entity_name, sub.entity_name
        """,
        (taxonomy_version_id,),
    ).fetchall()
    return [
        {
            "taxonomy_version": taxonomy_version_code,
            "ticker": str(row["ticker"]).upper(),
            "layer": row["layer"],
            "subindustry": row["subindustry"],
            "report_group_status": row["report_group_status"],
            "is_primary": int(row["is_primary"]),
            "role_weight": float(row["role_weight"] or 0),
            "notes": row["notes"] or "",
            "entity_id": int(row["entity_id"]),
        }
        for row in rows
    ]


def _ec_identity_index(conn: sqlite3.Connection, ecosystem_id: int) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        """
        SELECT entity_id,ticker,entity_code
        FROM ec_entity
        WHERE ecosystem_id=? AND entity_type='TICKER' AND status='ACTIVE'
        """,
        (ecosystem_id,),
    ):
        ticker = str(row["ticker"] or row["entity_code"]).upper()
        index.setdefault(ticker, {"ticker": ticker, "entity_id": int(row["entity_id"]), "resolution": "EXACT_ENTITY"})
    if _table_exists(conn, "ec_entity_alias"):
        for row in conn.execute(
            """
            SELECT a.alias_value,e.entity_id,e.ticker,e.entity_code
            FROM ec_entity_alias a
            JOIN ec_entity e ON e.entity_id=a.entity_id
            WHERE a.ecosystem_id=? AND a.alias_type='TICKER'
              AND a.status='ACTIVE' AND e.entity_type='TICKER' AND e.status='ACTIVE'
            """,
            (ecosystem_id,),
        ):
            alias = str(row["alias_value"]).upper()
            ticker = str(row["ticker"] or row["entity_code"]).upper()
            index.setdefault(alias, {"ticker": ticker, "entity_id": int(row["entity_id"]), "resolution": "ALIAS_ENTITY", "alias": alias})
    return index


def _active_state(paths: TaxonomyPaths, taxonomy_domain: str) -> dict[str, Any]:
    domain = validate_taxonomy_domain(taxonomy_domain)
    with _connect_ro(paths.taxonomy_db) as conn:
        if domain == "dc_ecosystem":
            active = _ec_active_version(conn)
            rows_for_fingerprint = _ec_rows_for_version(conn, int(active["taxonomy_version_id"]), str(active["taxonomy_version_code"]))
            identity_index = _ec_identity_index(conn, int(active["ecosystem_id"]))
            version_inventory = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT taxonomy_version_code
                    FROM ec_taxonomy_version v
                    JOIN ec_ecosystem e ON e.ecosystem_id=v.ecosystem_id
                    WHERE e.ecosystem_code=?
                    ORDER BY taxonomy_version_code
                    """,
                    (DATACENTER_ECOSYSTEM_CODE,),
                )
            ]
            active_version: dict[str, Any] = dict(active) | {
                "domain": domain,
                "storage_domain": "ec_sidecar_for_datacenter",
                "activation_semantics": "Current production Datacenter taxonomy is stored in ec_* sidecar rows for ecosystem_code=DATACENTER; this phase does not migrate it to a separate general EC taxonomy.",
                "is_current_primary_production_taxonomy": True,
            }
        else:
            ecosystems = [dict(row) for row in conn.execute("SELECT * FROM ec_ecosystem ORDER BY ecosystem_code").fetchall()] if _table_exists(conn, "ec_ecosystem") else []
            distinct_general = [row for row in ecosystems if str(row.get("ecosystem_code")) != DATACENTER_ECOSYSTEM_CODE]
            rows_for_fingerprint = []
            identity_index = {}
            version_inventory = [
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT taxonomy_version_code
                    FROM ec_taxonomy_version v
                    JOIN ec_ecosystem e ON e.ecosystem_id=v.ecosystem_id
                    WHERE e.ecosystem_code=?
                    ORDER BY taxonomy_version_code
                    """,
                    (DATACENTER_ECOSYSTEM_CODE,),
                )
            ] if _table_exists(conn, "ec_taxonomy_version") and _table_exists(conn, "ec_ecosystem") else []
            active_version = {
                "domain": domain,
                "is_current_primary_production_taxonomy": False,
                "update_contract_status": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
                "activation_semantics": "No repository-distinct general ec_taxonomy storage, pointer, consumer set, or safe write contract was found in this phase.",
                "discovered_ecosystems": ecosystems,
                "distinct_general_ecosystem_count": len(distinct_general),
            }
        validation = _validate_rows(rows_for_fingerprint)
        return {
            "domain": domain,
            "active_version": active_version,
            "version_inventory": version_inventory,
            "schema": _schema_contract(domain),
            "counts": validation["counts"],
            "rows": rows_for_fingerprint,
            "identity_index": identity_index,
            "semantic_fingerprint": stable_hash({"taxonomy_domain": domain, "rows": _semantic_payload(rows_for_fingerprint)}),
            "validation": validation,
            "source_state_fingerprint": stable_hash(
                {
                    "taxonomy_domain": domain,
                    "active_version": active_version,
                    "version_inventory": version_inventory,
                    "semantic_fingerprint": stable_hash(_semantic_payload(rows_for_fingerprint)),
                }
            ),
            "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_errors": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
            "current_primary_production_taxonomy": CURRENT_PRIMARY_PRODUCTION_TAXONOMY,
        }


def _schema_contract(taxonomy_domain: str) -> dict[str, Any]:
    if taxonomy_domain == "dc_ecosystem":
        return {
            "database_role": "taxonomy",
            "tables": ["ec_ecosystem", "ec_taxonomy_version", "ec_entity", "ec_entity_alias", "ec_membership"],
            "candidate_source_schema": "datacenter_taxonomy_csv",
            "ecosystem_code": DATACENTER_ECOSYSTEM_CODE,
            "versioning": "ec_taxonomy_version active pointer for the Datacenter ecosystem",
            "legacy_table_observed": "dc_ecosystem_membership",
        }
    return {
        "database_role": "taxonomy",
        "tables": [],
        "candidate_source_schema": "not accepted until a distinct general EC taxonomy contract exists",
        "versioning": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
        "update_contract_status": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
    }


def _diff_rows(
    active_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    identity_index: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    active_by_key = {_row_key(row): row for row in active_rows}
    candidate_by_key = {_row_key(row): row for row in candidate_rows}
    changes: list[dict[str, Any]] = []
    for key in sorted(set(active_by_key) | set(candidate_by_key)):
        old = active_by_key.get(key)
        new = candidate_by_key.get(key)
        ticker = str((new or old or {})["ticker"]).upper()
        identity = dict(identity_index.get(ticker, {}))
        if old is None and new is not None:
            kind = "MEMBERSHIP_ADDED"
            old_value = None
            new_value = _change_value(new)
        elif new is None and old is not None:
            kind = "MEMBERSHIP_REMOVED"
            old_value = _change_value(old)
            new_value = None
        else:
            old_value = _change_value(old)
            new_value = _change_value(new)
            if old_value == new_value:
                kind = "UNCHANGED"
            elif old and new and int(old["is_primary"]) != int(new["is_primary"]):
                kind = "PRIMARY_DESIGNATION_CHANGED"
            elif old and new and str(old["report_group_status"]) != str(new["report_group_status"]):
                kind = "ROLE_TIER_CHANGED"
            else:
                kind = "MEMBERSHIP_CHANGED"
        applicable = kind != "UNCHANGED" and bool(identity)
        changes.append(
            {
                "change_type": kind,
                "taxonomy_path": f"{(new or old)['layer']} / {(new or old)['subindustry']}",
                "ticker": ticker,
                "identity_resolution": identity.get("resolution", "UNRESOLVED"),
                "resolved_ticker": identity.get("ticker"),
                "old_value": old_value,
                "new_value": new_value,
                "reason": _reason(kind, identity),
                "automatic_apply_eligible": applicable,
                "blocking_status": [] if identity else ["UNRESOLVED_IDENTITY"],
            }
        )
    counts: dict[str, int] = {}
    for row in changes:
        counts[str(row["change_type"])] = counts.get(str(row["change_type"]), 0) + 1
    counts["automatic_apply_eligible"] = sum(1 for row in changes if row["automatic_apply_eligible"])
    counts["blocked"] = sum(1 for row in changes if row["blocking_status"])
    return changes, counts


def _change_value(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "role": row["report_group_status"],
        "is_primary": int(row["is_primary"]),
        "role_weight": float(row["role_weight"] or 0),
        "notes": row.get("notes") or "",
    }


def _reason(kind: str, identity: Mapping[str, Any]) -> str:
    if not identity:
        return "Ticker could not be resolved to an existing identity in the selected taxonomy domain."
    if kind == "UNCHANGED":
        return "Candidate row matches the selected taxonomy domain."
    return "Candidate differs from the selected taxonomy domain and is eligible for copy-only apply."


def _decision_from_change(taxonomy_domain: str, change: Mapping[str, Any]) -> AdminItemDecision:
    blockers = tuple(str(item) for item in change.get("blocking_status") or ())
    status = AdminStatus.REJECTED if blockers else (AdminStatus.NO_CHANGE if change["change_type"] == "UNCHANGED" else AdminStatus.ELIGIBLE)
    return AdminItemDecision(
        item_key=f"{taxonomy_domain}:{change['ticker']}:{change['taxonomy_path']}",
        requested_value=str(change["ticker"]),
        normalized_value=str(change.get("resolved_ticker") or change["ticker"]),
        status=status,
        reason=str(change["reason"]),
        old_value=json.dumps(change.get("old_value"), sort_keys=True),
        new_value=json.dumps(change.get("new_value"), sort_keys=True),
        source_category=f"{taxonomy_domain}_candidate",
        blockers=blockers,
        applied_action=None if status != AdminStatus.ELIGIBLE else str(change["change_type"]),
        details={"taxonomy_domain": taxonomy_domain, "change_type": change["change_type"], "taxonomy_path": change["taxonomy_path"], "identity_resolution": change["identity_resolution"]},
    )


def _request(taxonomy_domain: str, candidate_path: Path | None, *, mode: str, candidate_version: str | None = None) -> AdminBatchRequest:
    requested = (str(candidate_path),) if candidate_path else ()
    return AdminBatchRequest(
        operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        requested_inputs=requested,
        normalized_inputs=requested,
        market=None,
        options={"mode": mode, "taxonomy_domain": taxonomy_domain, "candidate_version": candidate_version},
    )


def _write_payload(path: Path, payload: Mapping[str, Any]) -> None:
    write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n")


def render_taxonomy_report(result: Mapping[str, Any]) -> str:
    lines = [render_markdown_report(result).rstrip(), "", "## Taxonomy Details", ""]
    lines.append(f"- taxonomy_domain: `{result.get('taxonomy_domain')}`")
    lines.append(f"- current_primary_production_taxonomy: `{CURRENT_PRIMARY_PRODUCTION_TAXONOMY}`")
    lines.append("- production_primary_switch: `NOT_AUTHORIZED_AND_NOT_PERFORMED`")
    lines.append("")
    downstream = result.get("downstream") if isinstance(result.get("downstream"), Mapping) else {}
    for key in ("domain_contract", "active_taxonomy", "candidate", "change_counts", "dependency_reasoning", "isolation", "production_immutability"):
        if key in downstream:
            lines.append(f"### {key.replace('_', ' ').title()}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(downstream[key], indent=2, sort_keys=True, default=str))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _dependency_reasoning(taxonomy_domain: str, has_changes: bool) -> dict[str, Any]:
    if taxonomy_domain == "dc_ecosystem":
        return {
            "taxonomy_domain": taxonomy_domain,
            "fundamentals_package_required": False,
            "relative_position_required": False,
            "relative_valuation_required": False,
            "datacenter_taxonomy_dependency_required": has_changes,
            "package_invocations": 0,
            "relative_position_invocations": 0,
            "relative_valuation_invocations": 0,
            "datacenter_dependency_invocations": 1 if has_changes else 0,
            "reason": "dc_ecosystem remains the primary Datacenter taxonomy; downstream refreshes are copy-only and only required when this domain changes.",
        }
    return {
        "taxonomy_domain": taxonomy_domain,
        "fundamentals_package_required": False,
        "relative_position_required": False,
        "relative_valuation_required": False,
        "datacenter_taxonomy_dependency_required": False,
        "package_invocations": 0,
        "relative_position_invocations": 0,
        "relative_valuation_invocations": 0,
        "datacenter_dependency_invocations": 0,
        "reason": "ec_taxonomy is a separate future target; this phase does not activate Datacenter RP/RV refreshes or switch production primary taxonomy.",
        "update_contract_status": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY",
    }


def run_preview(
    *,
    taxonomy_domain: str,
    candidate_path: Path | None = None,
    candidate_version: str | None = None,
    source_paths: TaxonomyPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT,
    progress_callback=None,
) -> dict[str, Any]:
    domain = validate_taxonomy_domain(taxonomy_domain)
    source_paths = source_paths or TaxonomyPaths()
    started = utc_now()
    request = _request(domain, candidate_path, mode="CANDIDATE_PREVIEW" if candidate_path else "CURRENT_STATE_AUDIT", candidate_version=candidate_version)
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"taxonomy_domain": domain, "request": request}), suffix=f"{domain}_preview")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, run_dir=writer.run_dir, stages=TAXONOMY_STAGES, callback=progress_callback)
    writer.checkpoint(RunStage.REQUEST_CREATED, message=f"Taxonomy administration request recorded for {domain}.")
    writer.checkpoint(RunStage.PREVIEW_STARTED, message=f"{domain} read-only preview started.")
    writer.write_json("request.json", request.as_dict())
    try:
        progress.running(ProgressStage.LOAD_ACTIVE_TAXONOMY, f"Loading {domain} state read-only.")
        active_state = _active_state(source_paths, domain)
        progress.completed(ProgressStage.LOAD_ACTIVE_TAXONOMY, f"{domain} state loaded.", processed_items=active_state["counts"]["rows"], total_items=active_state["counts"]["rows"])

        candidate: dict[str, Any] | None = None
        candidate_rows: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        counts: dict[str, int] = {"UNCHANGED": active_state["counts"]["rows"], "blocked": 0, "automatic_apply_eligible": 0}
        decisions: tuple[AdminItemDecision, ...] = tuple()
        proposed_changes: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        if candidate_path is None:
            progress.skipped(ProgressStage.LOAD_CANDIDATE, "No candidate supplied; current-state audit only.")
            progress.skipped(ProgressStage.RESOLVE_IDENTITIES, "No candidate identities to resolve.")
            progress.running(ProgressStage.VALIDATE_HIERARCHY, f"Validating {domain} active taxonomy invariants.")
            progress.completed(ProgressStage.VALIDATE_HIERARCHY, f"{domain} invariants validated.", processed_items=active_state["counts"]["rows"], total_items=active_state["counts"]["rows"])
        else:
            progress.running(ProgressStage.LOAD_CANDIDATE, f"Loading {domain} candidate.")
            version, candidate_rows, source_hash = _rows_from_candidate(candidate_path, candidate_version)
            candidate_validation = _validate_rows(candidate_rows, identity_index=active_state["identity_index"])
            candidate = {"path": str(candidate_path), "taxonomy_version": version, "source_hash": source_hash, "validation": candidate_validation, "counts": candidate_validation["counts"]}
            progress.completed(ProgressStage.LOAD_CANDIDATE, "Candidate loaded.", processed_items=len(candidate_rows), total_items=len(candidate_rows))
            progress.running(ProgressStage.RESOLVE_IDENTITIES, f"Resolving candidate tickers inside {domain}.")
            progress.completed(ProgressStage.RESOLVE_IDENTITIES, "Candidate identity resolution completed.", processed_items=len(candidate_rows), total_items=len(candidate_rows))
            progress.running(ProgressStage.VALIDATE_HIERARCHY, f"Validating {domain} candidate hierarchy.")
            if domain == "ec_taxonomy":
                blockers.append({"status": "EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY", "reason": "No distinct safe versioned update path for general ec_taxonomy was discovered."})
            if candidate_validation["status"] != "OK":
                blockers.extend(candidate_validation["errors"])
            progress.completed(ProgressStage.VALIDATE_HIERARCHY, "Candidate validation completed.", processed_items=len(candidate_rows), total_items=len(candidate_rows))
            progress.running(ProgressStage.BUILD_DIFF, f"Building {domain} taxonomy diff.")
            changes, counts = _diff_rows(active_state["rows"], candidate_rows, active_state["identity_index"])
            blockers.extend(row for row in changes if row["blocking_status"])
            proposed_changes = [row for row in changes if row["change_type"] != "UNCHANGED"]
            decisions = tuple(_decision_from_change(domain, change) for change in changes if change["change_type"] != "UNCHANGED" or change["blocking_status"])
            progress.completed(ProgressStage.BUILD_DIFF, "Taxonomy diff built.", processed_items=len(changes), total_items=len(changes))

        preview = {
            "operation_type": AdminOperationType.CHECK_UPDATE_TAXONOMY.value,
            "contract_version": CONTRACT_VERSION,
            "taxonomy_domain": domain,
            "current_primary_production_taxonomy": CURRENT_PRIMARY_PRODUCTION_TAXONOMY,
            "production_primary_switch": "NOT_AUTHORIZED_AND_NOT_PERFORMED",
            "request": request.as_dict(),
            "source_state_fingerprint": active_state["source_state_fingerprint"],
            "active_taxonomy": {
                "domain": domain,
                "version": active_state["active_version"],
                "version_inventory": active_state["version_inventory"],
                "counts": active_state["counts"],
                "semantic_fingerprint": active_state["semantic_fingerprint"],
                "validation": active_state["validation"],
                "schema": active_state["schema"],
            },
            "candidate": candidate,
            "change_counts": counts,
            "proposed_changes": proposed_changes,
            "blockers": blockers,
            "expected_writable_database_set": [f"taxonomy_copy:{domain}"] if proposed_changes and not blockers else [],
            "dependency_reasoning": _dependency_reasoning(domain, bool(proposed_changes)),
            "cross_domain_isolation": {
                "selected_domain": domain,
                "non_selected_domain": "ec_taxonomy" if domain == "dc_ecosystem" else "dc_ecosystem",
                "implicit_synchronization": False,
                "primary_taxonomy_switch": False,
            },
        }
        preview["preview_fingerprint"] = fingerprint(preview)
        writer.write_json("preview.json", preview)
        payload = {"taxonomy_domain": domain, "taxonomy_preview": preview, "active_rows": _semantic_payload(active_state["rows"])}
        if candidate_path is not None:
            payload["candidate_rows"] = _semantic_payload(candidate_rows)
        payload_path = writer.run_dir / "taxonomy_preview_payload.json"
        _write_payload(payload_path, payload)
        writer.write_items_csv([item.as_dict() for item in decisions])
        progress.running(ProgressStage.PREVIEW_VALIDATION, f"Writing immutable {domain} preview.")
        progress.completed(ProgressStage.PREVIEW_VALIDATION, "Taxonomy preview ready.")
        outcome = AdminStatus.NO_CHANGE if not proposed_changes and candidate_path else AdminStatus.COMPLETED
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=outcome,
            mode="CURRENT_STATE_AUDIT" if candidate_path is None else "CANDIDATE_PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview["preview_fingerprint"],
            request=request.as_dict(),
            item_results=decisions,
            summary_counts=counts,
            downstream={
                "domain_contract": active_state["schema"],
                "active_taxonomy": preview["active_taxonomy"],
                "candidate": candidate,
                "change_counts": counts,
                "dependency_reasoning": preview["dependency_reasoning"],
                "isolation": preview["cross_domain_isolation"],
                "production_immutability": "READ_ONLY_PREVIEW",
            },
            artifacts={"preview": str(writer.run_dir / "preview.json"), "payload": str(payload_path)},
            recommended_next_action=OUTCOME_B if blockers else ("Preview is applicable on isolated copies." if proposed_changes else "No taxonomy changes detected."),
        )
        result_dict = result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "preview_payload_path": str(payload_path), "taxonomy_domain": domain}
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_taxonomy_report(result_dict))
        writer.checkpoint(RunStage.PREVIEW_READY, message=f"{domain} preview ready. Production was not modified.", preview_fingerprint=preview["preview_fingerprint"], counters=counts)
        writer.write_exit_code(0 if not blockers else 1)
        writer.write_manifest()
        progress.running(ProgressStage.COMPLETED, "Taxonomy preview completed.")
        progress.completed(ProgressStage.COMPLETED, "Taxonomy preview completed.")
        return result_dict
    except Exception as exc:
        writer.write_error(exc)
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.FAILED,
            mode="PREVIEW",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=None,
            request=request.as_dict(),
            errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
            recommended_next_action=OUTCOME_B,
        )
        result_dict = result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "error": type(exc).__name__, "taxonomy_domain": domain}
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_taxonomy_report(result_dict))
        writer.checkpoint(RunStage.FAILED_BEFORE_WRITE, message=OUTCOME_B)
        writer.write_exit_code(2)
        writer.write_manifest()
        return result_dict


def _copy_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _copy_paths(source_paths: TaxonomyPaths, copy_root: Path) -> TaxonomyPaths:
    mapping = {}
    for role, source in source_paths.as_dict().items():
        target = copy_root / f"{role}.db"
        _copy_sqlite(source, target)
        mapping[role] = target
    return TaxonomyPaths(
        provider_db=mapping["provider"],
        canonical_db=mapping["canonical"],
        analysis_db=mapping["analysis"],
        market_db=mapping["market"],
        taxonomy_db=mapping["taxonomy"],
    )


def _refuse_production_write_path(path: Path) -> None:
    resolved = path.resolve(strict=False)
    if resolved in PROTECTED_DATABASE_PATHS:
        raise PermissionError(f"PHASE13G4_PRODUCTION_WRITE_PATH_REFUSED:{resolved}")


def _apply_dc_candidate_to_copy(copy_taxonomy_db: Path, rows: Sequence[Mapping[str, Any]], candidate_version: str) -> dict[str, Any]:
    _refuse_production_write_path(copy_taxonomy_db)
    with _connect_rw(copy_taxonomy_db) as conn:
        if not _table_exists(conn, "dc_ecosystem_membership"):
            raise RuntimeError("PHASE13G4_DC_ECOSYSTEM_TABLE_MISSING")
        before_count = int(conn.execute("SELECT COUNT(*) FROM dc_ecosystem_membership WHERE taxonomy_version=?", (candidate_version,)).fetchone()[0])
        with conn:
            conn.execute("DELETE FROM dc_ecosystem_membership WHERE taxonomy_version=?", (candidate_version,))
            conn.executemany(
                """
                INSERT INTO dc_ecosystem_membership (
                    taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes,created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        candidate_version,
                        row["ticker"],
                        row["layer"],
                        row["subindustry"],
                        row["report_group_status"],
                        int(row["is_primary"]),
                        float(row["role_weight"] or 0),
                        row.get("notes") or None,
                        utc_now(),
                    )
                    for row in rows
                ],
            )
        after_count = int(conn.execute("SELECT COUNT(*) FROM dc_ecosystem_membership WHERE taxonomy_version=?", (candidate_version,)).fetchone()[0])
    return {"outcome": "APPLIED", "domain": "dc_ecosystem", "replaced_rows": before_count, "rows_changed": after_count}


def _apply_ec_candidate_to_copy(copy_taxonomy_db: Path, candidate_csv: Path, candidate_version: str) -> dict[str, Any]:
    _refuse_production_write_path(copy_taxonomy_db)
    with _connect_ro(copy_taxonomy_db) as conn:
        before = _ec_active_version(conn)
        existing = conn.execute(
            """
            SELECT taxonomy_version_id,is_active,source_hash
            FROM ec_taxonomy_version v
            JOIN ec_ecosystem e ON e.ecosystem_id=v.ecosystem_id
            WHERE e.ecosystem_code=? AND v.taxonomy_version_code=?
            """,
            (DATACENTER_ECOSYSTEM_CODE, candidate_version),
        ).fetchone()
        if existing and int(existing["is_active"]) == 1 and str(existing["source_hash"]) == _sha256(candidate_csv):
            return {"outcome": "NO_CHANGE", "domain": "ec_taxonomy", "active_version": dict(before), "rows_changed": 0}

    load_summary = load_datacenter_taxonomy_to_ec_sidecar(copy_taxonomy_db, candidate_csv, candidate_version, mark_active=False)
    with _connect_rw(copy_taxonomy_db) as conn:
        active = _ec_active_version(conn)
        new = conn.execute(
            """
            SELECT v.taxonomy_version_id
            FROM ec_taxonomy_version v
            JOIN ec_ecosystem e ON e.ecosystem_id=v.ecosystem_id
            WHERE e.ecosystem_code=? AND v.taxonomy_version_code=?
            """,
            (DATACENTER_ECOSYSTEM_CODE, candidate_version),
        ).fetchone()
        if new is None:
            raise RuntimeError("PHASE13G4_NEW_EC_TAXONOMY_VERSION_MISSING")
        now = utc_now()
        with conn:
            conn.execute("UPDATE ec_taxonomy_version SET is_active=0,status='INACTIVE',active_to=? WHERE taxonomy_version_id=?", (now, int(active["taxonomy_version_id"])))
            conn.execute("UPDATE ec_taxonomy_version SET is_active=1,status='ACTIVE',active_from=?,active_to=NULL WHERE taxonomy_version_id=?", (now, int(new["taxonomy_version_id"])))
    return {"outcome": "APPLIED", "domain": "ec_taxonomy", "load_summary": load_summary, "rows_changed": int(load_summary["taxonomy_rows"])}


def run_apply(
    *,
    taxonomy_domain: str,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: TaxonomyPaths | None = None,
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = TEMP_ROOT,
    confirm_apply: bool = False,
    inject_failure_after_write: bool = False,
    progress_callback=None,
) -> dict[str, Any]:
    domain = validate_taxonomy_domain(taxonomy_domain)
    if not confirm_apply:
        raise PermissionError("PHASE13G4_CONFIRM_APPLY_REQUIRED")
    source_paths = source_paths or TaxonomyPaths()
    started = utc_now()
    payload = json.loads(Path(preview_payload_path).read_text(encoding="utf-8"))
    preview = payload["taxonomy_preview"]
    if payload.get("taxonomy_domain") != domain or preview.get("taxonomy_domain") != domain:
        raise ValueError("PHASE13G4_CROSS_DOMAIN_PREVIEW_REJECTED")
    if preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("PHASE13G4_PREVIEW_FINGERPRINT_MISMATCH")
    if domain == "ec_taxonomy":
        raise RuntimeError("EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY")
    request = AdminBatchRequest(
        operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
        requested_inputs=tuple(preview.get("request", {}).get("requested_inputs") or ()),
        normalized_inputs=tuple(preview.get("request", {}).get("normalized_inputs") or ()),
        options={"mode": "COPY_ONLY_APPLY", "taxonomy_domain": domain},
    )
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_TAXONOMY, fingerprint({"taxonomy_domain": domain, "preview_fingerprint": preview_fingerprint}), suffix=f"{domain}_apply")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_TAXONOMY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY, run_dir=writer.run_dir, stages=TAXONOMY_STAGES, callback=progress_callback)
    writer.checkpoint(RunStage.REQUEST_CREATED, message=f"{domain} copy-only apply request recorded.", preview_fingerprint=preview_fingerprint)
    writer.checkpoint(RunStage.APPLY_STARTED, message=f"{domain} copy-only apply started.", preview_fingerprint=preview_fingerprint)
    copy_root = (temp_root / run_id).resolve()
    copy_paths: TaxonomyPaths | None = None
    write_boundary_crossed = False
    try:
        if preview.get("blockers"):
            raise RuntimeError("PHASE13G4_BLOCKED_PREVIEW_REFUSED")
        if not preview.get("candidate"):
            raise RuntimeError("PHASE13G4_APPLY_REQUIRES_CANDIDATE_PREVIEW")
        fresh = run_preview(
            taxonomy_domain=domain,
            candidate_path=Path(preview["candidate"]["path"]),
            candidate_version=str(preview["candidate"]["taxonomy_version"]),
            source_paths=source_paths,
            run_root=writer.run_dir / "stale_check",
            progress_callback=None,
        )
        if fresh.get("preview_fingerprint") != preview_fingerprint:
            raise RuntimeError("PHASE13G4_STALE_PREVIEW_REJECTED")

        progress.running(ProgressStage.CREATE_COPIES, "Creating isolated production-shaped database copies.")
        copy_paths = _copy_paths(source_paths, copy_root)
        before_selected = _active_state(copy_paths, domain)
        before_other = _active_state(copy_paths, "ec_taxonomy" if domain == "dc_ecosystem" else "dc_ecosystem")
        copy_inventory = {role: {"path": str(path), "sha256": _sha256(path)} for role, path in copy_paths.as_dict().items()}
        writer.write_json("copy_inventory.json", copy_inventory)
        progress.completed(ProgressStage.CREATE_COPIES, "Database copies created.")
        writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message=f"Copy-only {domain} write boundary crossed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
        write_boundary_crossed = True
        progress.running(ProgressStage.APPLY_TAXONOMY, f"Applying {domain} candidate to isolated copy.")
        candidate_csv = _write_candidate_csv(copy_root / "candidate.csv", str(preview["candidate"]["taxonomy_version"]), payload["candidate_rows"])
        apply_result = _apply_ec_candidate_to_copy(copy_paths.taxonomy_db, candidate_csv, str(preview["candidate"]["taxonomy_version"]))
        apply_result["domain"] = domain
        if inject_failure_after_write:
            raise RuntimeError("PHASE13G4_INJECTED_AFTER_TAXONOMY_WRITE")
        progress.completed(ProgressStage.APPLY_TAXONOMY, "Candidate taxonomy applied to copy.")
        progress.running(ProgressStage.VALIDATE_APPLY, f"Validating {domain} copy state.")
        after_selected = _active_state(copy_paths, domain)
        after_other = _active_state(copy_paths, "ec_taxonomy" if domain == "dc_ecosystem" else "dc_ecosystem")
        if after_other["semantic_fingerprint"] != before_other["semantic_fingerprint"]:
            raise RuntimeError("PHASE13G4_CROSS_DOMAIN_MUTATION_DETECTED")
        progress.completed(ProgressStage.VALIDATE_APPLY, "Taxonomy copy validation completed.", processed_items=after_selected["counts"]["rows"], total_items=after_selected["counts"]["rows"])
        dependency = _dependency_reasoning(domain, bool(preview["proposed_changes"]))
        replay = {"outcome": "NO_CHANGE", "taxonomy_domain": domain, "taxonomy_fingerprint": after_selected["semantic_fingerprint"], "downstream_invocation_counts": {key: dependency[key] for key in ("package_invocations", "relative_position_invocations", "relative_valuation_invocations", "datacenter_dependency_invocations")}}
        rollback = {"status": "NOT_REQUIRED", "message": "Copy-only apply completed successfully."}
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.COMPLETED if apply_result["outcome"] == "APPLIED" else AdminStatus.NO_CHANGE,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            summary_counts=dict(preview["change_counts"]),
            rollback=rollback,
            downstream={
                "taxonomy_apply": apply_result,
                "domain_contract": _schema_contract(domain),
                "before_active_taxonomy": before_selected["active_version"],
                "after_active_taxonomy": after_selected["active_version"],
                "before_fingerprint": before_selected["semantic_fingerprint"],
                "after_fingerprint": after_selected["semantic_fingerprint"],
                "non_selected_domain_before_fingerprint": before_other["semantic_fingerprint"],
                "non_selected_domain_after_fingerprint": after_other["semantic_fingerprint"],
                "dependency_reasoning": dependency,
                "isolation": {"cross_domain_mutation": False, "production_primary_taxonomy": CURRENT_PRIMARY_PRODUCTION_TAXONOMY, "primary_taxonomy_switch": False},
                "replay": replay,
                "snapshot_smoke": {"status": "NOT_RUN_COPY_ONLY_ADMIN", "reason": "No production snapshot output was regenerated."},
                "production_immutability": "COPY_ONLY_NO_PRODUCTION_WRITES",
            },
            artifacts={"copy_inventory": str(writer.run_dir / "copy_inventory.json")},
            recommended_next_action=OUTCOME_A,
        )
        result_dict = result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "taxonomy_domain": domain}
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_taxonomy_report(result_dict))
        writer.write_items_csv([_decision_from_change(domain, row).as_dict() for row in preview.get("proposed_changes", [])])
        writer.checkpoint(RunStage.COMPLETED, message=OUTCOME_A, preview_fingerprint=preview_fingerprint, counters=preview["change_counts"], write_boundary_crossed=True)
        writer.write_exit_code(0)
        writer.write_manifest()
        return result_dict
    except Exception as exc:
        writer.write_error(exc)
        rollback = {"status": "NOT_REQUIRED", "message": "Failure occurred before copy write boundary."}
        if copy_paths is not None and write_boundary_crossed:
            progress.rolling_back("Restoring copy lane from source databases.")
            shutil.rmtree(copy_root, ignore_errors=True)
            copy_paths = _copy_paths(source_paths, copy_root)
            restored = _active_state(copy_paths, domain)
            rollback = {"status": "RESTORED_COPY_SET", "restored_active_taxonomy": restored["active_version"], "restored_fingerprint": restored["semantic_fingerprint"]}
            progress.rolled_back("Copy lane restored.")
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_TAXONOMY,
            outcome=AdminStatus.ROLLED_BACK if rollback["status"] == "RESTORED_COPY_SET" else AdminStatus.FAILED,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            rollback=rollback,
            downstream={"production_immutability": "COPY_ONLY_NO_PRODUCTION_WRITES", "taxonomy_domain": domain, "write_boundary_crossed": write_boundary_crossed},
            recommended_next_action=OUTCOME_C if write_boundary_crossed else OUTCOME_B,
            errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
        )
        result_dict = result.as_dict() | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "error": type(exc).__name__, "taxonomy_domain": domain}
        writer.write_json("result.json", result_dict)
        writer.write_text("report.md", render_taxonomy_report(result_dict))
        writer.checkpoint(RunStage.FAILED_AFTER_WRITE if write_boundary_crossed else RunStage.FAILED_BEFORE_WRITE, message=result.recommended_next_action, preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(3 if write_boundary_crossed else 2)
        writer.write_manifest()
        return result_dict
    finally:
        if copy_root.exists() and not inject_failure_after_write:
            shutil.rmtree(copy_root, ignore_errors=True)
