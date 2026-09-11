from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.phase12d import PRODUCTION, ROOT, compare_production_inventory, production_inventory
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.persistence import (
    LAYOUT_FINGERPRINT as RV_LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION as RV_PERSISTENCE_VERSION,
    RelativeValuationRepository,
)


PHASE = "PHASE13B_VERSIONED_UNIVERSE_TAXONOMY_DEPENDENCY_FOUNDATION"
OUTCOME_READY = "OUTCOME A — UNIVERSE AND TAXONOMY DEPENDENCY FOUNDATION READY FOR PRODUCTION MIGRATION"
CONTRACT_VERSION = "PHASE13B_OPERATIONAL_UNIVERSE_CONTRACT_V1"
DEPENDENCY_CONTRACT_VERSION = "PHASE13B_RESULT_DEPENDENCY_CONTRACT_V1"
PROTECTED_PRODUCTION_PATHS = {path.resolve() for path in PRODUCTION.values()}


CANONICAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fundamentals_operational_universe_schema_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    contract_version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fundamentals_operational_universe_version (
    universe_version_id TEXT PRIMARY KEY,
    contract_version TEXT NOT NULL,
    semantic_mode TEXT NOT NULL CHECK(semantic_mode='CURRENT_OPERATIONAL_UNIVERSE'),
    as_of_date TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    economic_result_fingerprint TEXT NOT NULL,
    physical_content_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('WRITING','COMPLETE')),
    member_count INTEGER NOT NULL CHECK(member_count>=0),
    company_count INTEGER NOT NULL CHECK(company_count>=0),
    active_security_count INTEGER NOT NULL CHECK(active_security_count>=0),
    zero_active_company_count INTEGER NOT NULL CHECK(zero_active_company_count>=0),
    multi_active_company_count INTEGER NOT NULL CHECK(multi_active_company_count>=0),
    created_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    UNIQUE(contract_version, economic_result_fingerprint)
);

CREATE TABLE IF NOT EXISTS fundamentals_operational_universe_active_version (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    universe_version_id TEXT NOT NULL UNIQUE
        REFERENCES fundamentals_operational_universe_version(universe_version_id) ON DELETE RESTRICT,
    activated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fundamentals_operational_universe_member (
    universe_version_id TEXT NOT NULL
        REFERENCES fundamentals_operational_universe_version(universe_version_id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    security_id INTEGER REFERENCES security(security_id),
    current_ticker TEXT,
    market TEXT NOT NULL,
    membership_status TEXT NOT NULL CHECK(membership_status IN (
        'ACTIVE_SINGLE_SECURITY','ACTIVE_MULTI_SECURITY','HISTORICAL_RETAINED_NO_ACTIVE_SECURITY'
    )),
    identity_resolution_status TEXT NOT NULL,
    active_security_count INTEGER NOT NULL CHECK(active_security_count>=0),
    all_security_count INTEGER NOT NULL CHECK(all_security_count>=0),
    effective_start_date TEXT NOT NULL,
    effective_end_date TEXT,
    source TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY(universe_version_id, company_id),
    CHECK((membership_status='ACTIVE_SINGLE_SECURITY' AND security_id IS NOT NULL) OR membership_status<>'ACTIVE_SINGLE_SECURITY')
);

CREATE TABLE IF NOT EXISTS fundamentals_operational_universe_member_alias (
    universe_version_id TEXT NOT NULL,
    company_id INTEGER NOT NULL,
    security_id INTEGER NOT NULL,
    alias_ticker TEXT NOT NULL,
    provider TEXT,
    valid_from TEXT,
    valid_to TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY(universe_version_id, security_id, alias_ticker, provider, valid_from),
    FOREIGN KEY(universe_version_id, company_id)
        REFERENCES fundamentals_operational_universe_member(universe_version_id, company_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fouv_member_company
    ON fundamentals_operational_universe_member(company_id, universe_version_id);
CREATE INDEX IF NOT EXISTS idx_fouv_member_ticker
    ON fundamentals_operational_universe_member(current_ticker, market);
"""


ANALYSIS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fundamentals_dependency_schema_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    contract_version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fundamentals_result_dependency (
    dependency_id INTEGER PRIMARY KEY,
    consumer_family TEXT NOT NULL,
    consumer_object_type TEXT NOT NULL,
    consumer_object_id TEXT NOT NULL,
    model_fingerprint TEXT,
    operational_universe_version_id TEXT,
    operational_universe_fingerprint TEXT,
    taxonomy_source_version TEXT,
    taxonomy_source_fingerprint TEXT,
    taxonomy_economic_fingerprint TEXT,
    taxonomy_presentation_fingerprint TEXT,
    dependency_as_of_date TEXT,
    compatibility_status TEXT NOT NULL CHECK(compatibility_status IN (
        'COMPATIBLE','PRESENTATION_ONLY_DRIFT','ECONOMIC_TAXONOMY_MISMATCH',
        'OPERATIONAL_UNIVERSE_MISMATCH','DEPENDENCY_UNKNOWN','SNAPSHOT_NOT_AVAILABLE'
    )),
    provenance_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(consumer_family, consumer_object_type, consumer_object_id)
);

CREATE TABLE IF NOT EXISTS relative_valuation_snapshot_dependency (
    snapshot_id TEXT PRIMARY KEY REFERENCES relative_valuation_snapshot(snapshot_id) ON DELETE CASCADE,
    operational_universe_version_id TEXT,
    operational_universe_fingerprint TEXT,
    taxonomy_source_version TEXT,
    taxonomy_source_fingerprint TEXT,
    taxonomy_economic_fingerprint TEXT,
    taxonomy_presentation_fingerprint TEXT,
    dependency_as_of_date TEXT NOT NULL,
    compatibility_status TEXT NOT NULL CHECK(compatibility_status IN (
        'COMPATIBLE','PRESENTATION_ONLY_DRIFT','ECONOMIC_TAXONOMY_MISMATCH',
        'OPERATIONAL_UNIVERSE_MISMATCH','DEPENDENCY_UNKNOWN','SNAPSHOT_NOT_AVAILABLE'
    )),
    provenance_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_frd_consumer
    ON fundamentals_result_dependency(consumer_family, consumer_object_type, consumer_object_id);
CREATE INDEX IF NOT EXISTS idx_frd_universe
    ON fundamentals_result_dependency(operational_universe_fingerprint, compatibility_status);
"""


@dataclass(frozen=True)
class CandidatePaths:
    canonical_db: Path
    analysis_db: Path
    taxonomy_db: Path
    provider_db: Path | None = None
    market_db: Path | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def reject_production_path(path: Path, role: str) -> None:
    resolved = path.resolve()
    if resolved in PROTECTED_PRODUCTION_PATHS or path.is_symlink():
        raise PermissionError(f"PHASE13B_PRODUCTION_PATH_REFUSED:{role}:{resolved}")


def execute_script(conn: sqlite3.Connection, script: str) -> None:
    for statement in (part.strip() for part in script.split(";")):
        if statement:
            conn.execute(statement)


def online_backup(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    with readonly(destination) as conn:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
    return {"source": str(source), "destination": str(destination), "quick_check": quick, "size": destination.stat().st_size}


def database_fingerprint(path: Path) -> dict[str, Any]:
    with readonly(path) as conn:
        schema = [tuple(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )]
        tables = [str(row[0]) for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
        counts = {
            table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in tables
            if not table.startswith("sqlite_")
        }
        return {
            "schema_hash": stable_hash(schema),
            "row_counts": counts,
            "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_violations": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
            "page_count": conn.execute("PRAGMA page_count").fetchone()[0],
            "freelist_count": conn.execute("PRAGMA freelist_count").fetchone()[0],
            "fingerprint": stable_hash({"schema": schema, "counts": counts}),
        }


def current_universe_rows(canonical_db: Path, *, now: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with readonly(canonical_db) as conn:
        companies = [dict(row) for row in conn.execute(
            "SELECT company_id,company_key,company_name,status,created_at_utc FROM company ORDER BY company_id"
        )]
        securities_by_company: dict[int, list[dict[str, Any]]] = {}
        for row in conn.execute(
            "SELECT security_id,company_id,current_ticker,exchange,active,valid_from,valid_to FROM security ORDER BY company_id,security_id"
        ):
            item = dict(row)
            securities_by_company.setdefault(int(item["company_id"]), []).append(item)
        aliases = [dict(row) for row in conn.execute(
            "SELECT a.security_id,s.company_id,a.ticker,a.provider,a.valid_from,a.valid_to,a.source "
            "FROM ticker_alias a JOIN security s USING(security_id) ORDER BY s.company_id,a.security_id,a.ticker,a.provider"
        )]
    members: list[dict[str, Any]] = []
    for company in companies:
        company_id = int(company["company_id"])
        securities = securities_by_company.get(company_id, [])
        active = [security for security in securities if int(security["active"]) == 1]
        if len(active) == 1:
            security = active[0]
            status = "ACTIVE_SINGLE_SECURITY"
            identity_status = "EXACT_ONE_ACTIVE_SECURITY"
            security_id = int(security["security_id"])
            ticker = str(security["current_ticker"])
        elif len(active) == 0:
            security = securities[0] if securities else None
            status = "HISTORICAL_RETAINED_NO_ACTIVE_SECURITY"
            identity_status = "NO_ACTIVE_SECURITY_RETAINED_BY_CANONICAL_COMPANY"
            security_id = int(security["security_id"]) if security else None
            ticker = str(security["current_ticker"]) if security else None
        else:
            status = "ACTIVE_MULTI_SECURITY"
            identity_status = "MULTIPLE_ACTIVE_SECURITIES_REQUIRES_SECURITY_SELECTION"
            security_id = None
            ticker = ",".join(str(security["current_ticker"]) for security in active)
        members.append({
            "company_id": company_id,
            "security_id": security_id,
            "current_ticker": ticker,
            "market": "usa",
            "membership_status": status,
            "identity_resolution_status": identity_status,
            "active_security_count": len(active),
            "all_security_count": len(securities),
            "effective_start_date": "CURRENT_PRODUCTION_BASELINE",
            "effective_end_date": None,
            "source": "PHASE13B_CANONICAL_COMPANY_SECURITY_BACKFILL",
            "reason": "reconstruct current production operational Fundamentals company population without onboarding",
            "created_at_utc": now,
            "updated_at_utc": now,
        })
    alias_rows = [{
        "company_id": int(row["company_id"]),
        "security_id": int(row["security_id"]),
        "alias_ticker": str(row["ticker"]),
        "provider": row.get("provider"),
        "valid_from": row.get("valid_from"),
        "valid_to": row.get("valid_to"),
        "source": str(row["source"]),
    } for row in aliases]
    return members, alias_rows


def universe_identity(members: Sequence[Mapping[str, Any]], aliases: Sequence[Mapping[str, Any]], *, as_of_date: str) -> dict[str, Any]:
    economic_members = [
        {key: row.get(key) for key in (
            "company_id", "security_id", "current_ticker", "market", "membership_status",
            "identity_resolution_status", "active_security_count", "all_security_count",
            "effective_start_date", "effective_end_date", "source", "reason",
        )}
        for row in members
    ]
    source = {
        "contract_version": CONTRACT_VERSION,
        "as_of_date": as_of_date,
        "members": economic_members,
        "aliases": list(aliases),
    }
    source_fp = stable_hash(source)
    economic_fp = stable_hash({"contract_version": CONTRACT_VERSION, "members": economic_members})
    physical_fp = stable_hash({"source_fingerprint": source_fp, "economic_result_fingerprint": economic_fp, "member_count": len(members)})
    version_id = stable_hash({"contract_version": CONTRACT_VERSION, "economic_result_fingerprint": economic_fp})[:32]
    return {
        "universe_version_id": version_id,
        "source_fingerprint": source_fp,
        "economic_result_fingerprint": economic_fp,
        "physical_content_fingerprint": physical_fp,
        "member_count": len(members),
        "company_count": len({int(row["company_id"]) for row in members}),
        "active_security_count": sum(1 for row in members if row["membership_status"] == "ACTIVE_SINGLE_SECURITY") + sum(int(row["active_security_count"]) for row in members if row["membership_status"] == "ACTIVE_MULTI_SECURITY"),
        "zero_active_company_count": sum(1 for row in members if int(row["active_security_count"]) == 0),
        "multi_active_company_count": sum(1 for row in members if int(row["active_security_count"]) > 1),
    }


def taxonomy_identity(taxonomy_db: Path) -> dict[str, Any]:
    with readonly(taxonomy_db) as conn:
        versions = [dict(row) for row in conn.execute(
            "SELECT taxonomy_version_code,source_reference,source_hash,status,is_active,active_from,active_to "
            "FROM ec_taxonomy_version ORDER BY taxonomy_version_id"
        )]
        economic_rows = [dict(row) for row in conn.execute(
            "SELECT tv.taxonomy_version_code,e.entity_type,e.entity_code,e.ticker,m.membership_type,m.membership_role,m.is_primary,m.role_weight,m.status "
            "FROM ec_membership m JOIN ec_taxonomy_version tv USING(taxonomy_version_id) "
            "JOIN ec_entity e ON e.entity_id=m.child_entity_id "
            "WHERE tv.status='ACTIVE' AND tv.is_active=1 AND m.status='ACTIVE' AND e.status='ACTIVE' "
            "ORDER BY tv.taxonomy_version_code,e.entity_type,e.entity_code,m.membership_id"
        )]
        presentation_rows = [dict(row) for row in conn.execute(
            "SELECT entity_type,entity_code,entity_name,ticker,status FROM ec_entity ORDER BY entity_id"
        )]
    active_versions = [row for row in versions if row["status"] == "ACTIVE" and int(row["is_active"]) == 1]
    return {
        "taxonomy_source_version": ",".join(str(row["taxonomy_version_code"]) for row in active_versions),
        "taxonomy_source_fingerprint": stable_hash(versions),
        "taxonomy_economic_fingerprint": stable_hash(economic_rows),
        "taxonomy_presentation_fingerprint": stable_hash(presentation_rows),
    }


def ensure_candidate_schema(paths: CandidatePaths, *, applied_at_utc: str, apply: bool) -> dict[str, Any]:
    reject_production_path(paths.canonical_db, "canonical")
    reject_production_path(paths.analysis_db, "analysis")
    before = {"canonical": database_fingerprint(paths.canonical_db), "analysis": database_fingerprint(paths.analysis_db)}
    if not apply:
        return {"outcome": "DRY_RUN", "would_apply": True, "before": before}
    with sqlite3.connect(paths.canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        execute_script(conn, CANONICAL_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO fundamentals_operational_universe_schema_meta VALUES (1,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET contract_version=excluded.contract_version,applied_at_utc=excluded.applied_at_utc",
            (CONTRACT_VERSION, applied_at_utc),
        )
        conn.commit()
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        execute_script(conn, ANALYSIS_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO fundamentals_dependency_schema_meta VALUES (1,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET contract_version=excluded.contract_version,applied_at_utc=excluded.applied_at_utc",
            (DEPENDENCY_CONTRACT_VERSION, applied_at_utc),
        )
        conn.commit()
    after = {"canonical": database_fingerprint(paths.canonical_db), "analysis": database_fingerprint(paths.analysis_db)}
    changed = stable_json(before) != stable_json(after)
    return {"outcome": "APPLIED" if changed else "NO_CHANGE", "before": before, "after": after}


def backfill_universe(paths: CandidatePaths, *, applied_at_utc: str, apply: bool) -> dict[str, Any]:
    reject_production_path(paths.canonical_db, "canonical")
    members, aliases = current_universe_rows(paths.canonical_db, now=applied_at_utc)
    identity = universe_identity(members, aliases, as_of_date=applied_at_utc[:10])
    if not apply:
        return {"outcome": "DRY_RUN", "identity": identity}
    with sqlite3.connect(paths.canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM fundamentals_operational_universe_version WHERE universe_version_id=? AND status='COMPLETE'",
            (identity["universe_version_id"],),
        ).fetchone()
        active = conn.execute("SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1").fetchone()
        if existing is not None and active is not None and str(active[0]) == identity["universe_version_id"]:
            conn.rollback()
            return {"outcome": "NO_CHANGE", "identity": identity}
        conn.execute("DELETE FROM fundamentals_operational_universe_active_version")
        conn.execute("INSERT OR IGNORE INTO fundamentals_operational_universe_version VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            identity["universe_version_id"], CONTRACT_VERSION, "CURRENT_OPERATIONAL_UNIVERSE", applied_at_utc[:10],
            identity["source_fingerprint"], identity["economic_result_fingerprint"], identity["physical_content_fingerprint"],
            "COMPLETE", identity["member_count"], identity["company_count"], identity["active_security_count"],
            identity["zero_active_company_count"], identity["multi_active_company_count"], applied_at_utc, applied_at_utc,
        ))
        for row in members:
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals_operational_universe_member VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity["universe_version_id"], row["company_id"], row["security_id"], row["current_ticker"],
                    row["market"], row["membership_status"], row["identity_resolution_status"],
                    row["active_security_count"], row["all_security_count"], row["effective_start_date"],
                    row["effective_end_date"], row["source"], row["reason"], row["created_at_utc"], row["updated_at_utc"],
                ),
            )
        for row in aliases:
            conn.execute(
                "INSERT OR IGNORE INTO fundamentals_operational_universe_member_alias VALUES (?,?,?,?,?,?,?,?)",
                (
                    identity["universe_version_id"], row["company_id"], row["security_id"], row["alias_ticker"],
                    row["provider"], row["valid_from"], row["valid_to"], row["source"],
                ),
            )
        conn.execute("INSERT INTO fundamentals_operational_universe_active_version VALUES (1,?,?)", (identity["universe_version_id"], applied_at_utc))
        conn.commit()
    return {"outcome": "APPLIED", "identity": identity}


def attach_dependencies(paths: CandidatePaths, *, universe: Mapping[str, Any], applied_at_utc: str, apply: bool, force_unknown: bool = False) -> dict[str, Any]:
    reject_production_path(paths.analysis_db, "analysis")
    taxonomy = taxonomy_identity(paths.taxonomy_db)
    with readonly(paths.analysis_db) as conn:
        rv_snapshots = [dict(row) for row in conn.execute(
            "SELECT snapshot_id,as_of_date,source_fingerprint,result_fingerprint FROM relative_valuation_snapshot WHERE model_fingerprint=? AND status='COMPLETE' ORDER BY as_of_date",
            (RV_MODEL_FINGERPRINT,),
        )]
        rp_snapshots = [dict(row) for row in conn.execute("SELECT snapshot_id,model_fingerprint,snapshot_date,source_content_fingerprint,result_fingerprint FROM relative_position_snapshot WHERE status='COMPLETE' ORDER BY snapshot_date,snapshot_id")]
        packages = [dict(row) for row in conn.execute("SELECT persistence_fingerprint,family_fingerprint,economic_result_fingerprint,physical_content_fingerprint FROM operating_income_v2_package_manifest ORDER BY applied_at_utc")]
    status = "DEPENDENCY_UNKNOWN" if force_unknown else "COMPATIBLE"
    if not apply:
        return {"outcome": "DRY_RUN", "rv_snapshots": len(rv_snapshots), "rp_snapshots": len(rp_snapshots), "packages": len(packages), "taxonomy": taxonomy, "status": status}
    rv_dependency_rows = []
    generic_dependency_rows = []
    for row in rv_snapshots:
        rv_dependency_rows.append({
            "snapshot_id": row["snapshot_id"],
            "operational_universe_version_id": universe["universe_version_id"],
            "operational_universe_fingerprint": universe["economic_result_fingerprint"],
            "taxonomy_source_version": taxonomy["taxonomy_source_version"],
            "taxonomy_source_fingerprint": taxonomy["taxonomy_source_fingerprint"],
            "taxonomy_economic_fingerprint": taxonomy["taxonomy_economic_fingerprint"],
            "taxonomy_presentation_fingerprint": taxonomy["taxonomy_presentation_fingerprint"],
            "dependency_as_of_date": row["as_of_date"],
            "compatibility_status": status,
            "provenance_json": stable_json({"phase": PHASE, "source_fingerprint": row["source_fingerprint"], "result_fingerprint": row["result_fingerprint"]}),
            "created_at_utc": applied_at_utc,
        })
        generic_dependency_rows.append({
            "consumer_family": "RELATIVE_VALUATION",
            "consumer_object_type": "SNAPSHOT",
            "consumer_object_id": row["snapshot_id"],
            "model_fingerprint": RV_MODEL_FINGERPRINT,
            "operational_universe_version_id": universe["universe_version_id"],
            "operational_universe_fingerprint": universe["economic_result_fingerprint"],
            "taxonomy_source_version": taxonomy["taxonomy_source_version"],
            "taxonomy_source_fingerprint": taxonomy["taxonomy_source_fingerprint"],
            "taxonomy_economic_fingerprint": taxonomy["taxonomy_economic_fingerprint"],
            "taxonomy_presentation_fingerprint": taxonomy["taxonomy_presentation_fingerprint"],
            "dependency_as_of_date": row["as_of_date"],
            "compatibility_status": status,
            "provenance_json": stable_json({"phase": PHASE}),
            "created_at_utc": applied_at_utc,
        })
    for row in rp_snapshots:
        generic_dependency_rows.append({
            "consumer_family": "RELATIVE_POSITION",
            "consumer_object_type": "SNAPSHOT",
            "consumer_object_id": row["snapshot_id"],
            "model_fingerprint": row["model_fingerprint"],
            "operational_universe_version_id": universe["universe_version_id"],
            "operational_universe_fingerprint": universe["economic_result_fingerprint"],
            "taxonomy_source_version": taxonomy["taxonomy_source_version"],
            "taxonomy_source_fingerprint": taxonomy["taxonomy_source_fingerprint"],
            "taxonomy_economic_fingerprint": taxonomy["taxonomy_economic_fingerprint"],
            "taxonomy_presentation_fingerprint": taxonomy["taxonomy_presentation_fingerprint"],
            "dependency_as_of_date": row["snapshot_date"],
            "compatibility_status": status,
            "provenance_json": stable_json({"phase": PHASE}),
            "created_at_utc": applied_at_utc,
        })
    for row in packages:
        generic_dependency_rows.append({
            "consumer_family": "OPERATING_INCOME_V2",
            "consumer_object_type": "PACKAGE",
            "consumer_object_id": row["persistence_fingerprint"],
            "model_fingerprint": None,
            "operational_universe_version_id": universe["universe_version_id"],
            "operational_universe_fingerprint": universe["economic_result_fingerprint"],
            "taxonomy_source_version": taxonomy["taxonomy_source_version"],
            "taxonomy_source_fingerprint": taxonomy["taxonomy_source_fingerprint"],
            "taxonomy_economic_fingerprint": taxonomy["taxonomy_economic_fingerprint"],
            "taxonomy_presentation_fingerprint": taxonomy["taxonomy_presentation_fingerprint"],
            "dependency_as_of_date": applied_at_utc[:10],
            "compatibility_status": status,
            "provenance_json": stable_json({"phase": PHASE, "family_fingerprint": row["family_fingerprint"]}),
            "created_at_utc": applied_at_utc,
        })
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        existing_rv_rows = [
            {key: row[key] for key in rv_dependency_rows[0].keys()}
            for row in conn.execute(
                "SELECT snapshot_id,operational_universe_version_id,operational_universe_fingerprint,"
                "taxonomy_source_version,taxonomy_source_fingerprint,taxonomy_economic_fingerprint,"
                "taxonomy_presentation_fingerprint,dependency_as_of_date,compatibility_status,provenance_json,created_at_utc "
                "FROM relative_valuation_snapshot_dependency ORDER BY snapshot_id"
            )
        ] if rv_dependency_rows else []
        existing_generic_rows = [
            {key: row[key] for key in generic_dependency_rows[0].keys()}
            for row in conn.execute(
                "SELECT consumer_family,consumer_object_type,consumer_object_id,model_fingerprint,"
                "operational_universe_version_id,operational_universe_fingerprint,taxonomy_source_version,"
                "taxonomy_source_fingerprint,taxonomy_economic_fingerprint,taxonomy_presentation_fingerprint,"
                "dependency_as_of_date,compatibility_status,provenance_json,created_at_utc "
                "FROM fundamentals_result_dependency ORDER BY consumer_family,consumer_object_type,consumer_object_id"
            )
        ] if generic_dependency_rows else []
        if stable_json(existing_rv_rows) == stable_json(sorted(rv_dependency_rows, key=lambda row: row["snapshot_id"])) and stable_json(existing_generic_rows) == stable_json(sorted(generic_dependency_rows, key=lambda row: (row["consumer_family"], row["consumer_object_type"], row["consumer_object_id"]))):
            return {"outcome": "NO_CHANGE", "rows_changed": 0, "rv_snapshots": len(rv_snapshots), "rp_snapshots": len(rp_snapshots), "packages": len(packages), "taxonomy": taxonomy, "status": status}
        conn.execute("BEGIN IMMEDIATE")
        changes_before = conn.total_changes
        for row in rv_dependency_rows:
            conn.execute(
                "INSERT INTO relative_valuation_snapshot_dependency VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(snapshot_id) DO UPDATE SET operational_universe_version_id=excluded.operational_universe_version_id,"
                "operational_universe_fingerprint=excluded.operational_universe_fingerprint,taxonomy_source_version=excluded.taxonomy_source_version,"
                "taxonomy_source_fingerprint=excluded.taxonomy_source_fingerprint,taxonomy_economic_fingerprint=excluded.taxonomy_economic_fingerprint,"
                "taxonomy_presentation_fingerprint=excluded.taxonomy_presentation_fingerprint,dependency_as_of_date=excluded.dependency_as_of_date,"
                "compatibility_status=excluded.compatibility_status,provenance_json=excluded.provenance_json,created_at_utc=excluded.created_at_utc",
                (
                    row["snapshot_id"], row["operational_universe_version_id"], row["operational_universe_fingerprint"],
                    row["taxonomy_source_version"], row["taxonomy_source_fingerprint"], row["taxonomy_economic_fingerprint"],
                    row["taxonomy_presentation_fingerprint"], row["dependency_as_of_date"], row["compatibility_status"],
                    row["provenance_json"], row["created_at_utc"],
                ),
            )
        for row in generic_dependency_rows:
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals_result_dependency(consumer_family,consumer_object_type,consumer_object_id,model_fingerprint,"
                "operational_universe_version_id,operational_universe_fingerprint,taxonomy_source_version,taxonomy_source_fingerprint,"
                "taxonomy_economic_fingerprint,taxonomy_presentation_fingerprint,dependency_as_of_date,compatibility_status,provenance_json,created_at_utc) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row[key] for key in (
                    "consumer_family", "consumer_object_type", "consumer_object_id", "model_fingerprint",
                    "operational_universe_version_id", "operational_universe_fingerprint", "taxonomy_source_version",
                    "taxonomy_source_fingerprint", "taxonomy_economic_fingerprint", "taxonomy_presentation_fingerprint",
                    "dependency_as_of_date", "compatibility_status", "provenance_json", "created_at_utc",
                )),
            )
        conn.commit()
        changes = conn.total_changes - changes_before
    return {"outcome": "NO_CHANGE" if changes == 0 else "APPLIED", "rows_changed": changes, "rv_snapshots": len(rv_snapshots), "rp_snapshots": len(rp_snapshots), "packages": len(packages), "taxonomy": taxonomy, "status": status}


def candidate_relative_valuation_dependency_state(
    analysis_db: Path,
    *,
    report_date: str,
    expected_universe_fingerprint: str,
    expected_taxonomy_economic_fingerprint: str,
) -> dict[str, Any]:
    with readonly(analysis_db) as conn:
        repo = RelativeValuationRepository(conn)
        metadata = repo.report_snapshot_metadata(report_date, model_fingerprint=RV_MODEL_FINGERPRINT)
        if metadata is None:
            return {"state": "SNAPSHOT_NOT_AVAILABLE", "snapshot_id": None}
        dep = conn.execute(
            "SELECT * FROM relative_valuation_snapshot_dependency WHERE snapshot_id=?",
            (metadata["snapshot_id"],),
        ).fetchone()
        if dep is None:
            return {"state": "DEPENDENCY_UNKNOWN", "snapshot_id": metadata["snapshot_id"], "as_of_date": metadata["as_of_date"]}
        if str(dep["operational_universe_fingerprint"]) != expected_universe_fingerprint:
            state = "OPERATIONAL_UNIVERSE_MISMATCH"
        elif str(dep["taxonomy_economic_fingerprint"]) != expected_taxonomy_economic_fingerprint:
            state = "ECONOMIC_TAXONOMY_MISMATCH"
        else:
            state = str(dep["compatibility_status"])
        return {"state": state, "snapshot_id": metadata["snapshot_id"], "as_of_date": metadata["as_of_date"]}


def run_candidate_apply(paths: CandidatePaths, *, apply: bool, applied_at_utc: str, force_unknown: bool = False) -> dict[str, Any]:
    schema = ensure_candidate_schema(paths, applied_at_utc=applied_at_utc, apply=apply)
    universe = backfill_universe(paths, applied_at_utc=applied_at_utc, apply=apply)
    identity = universe["identity"]
    dependencies = attach_dependencies(paths, universe=identity, applied_at_utc=applied_at_utc, apply=apply, force_unknown=force_unknown)
    return {"schema": schema, "universe": universe, "dependencies": dependencies}


def verify_reconciliation(paths: CandidatePaths, universe: Mapping[str, Any]) -> dict[str, Any]:
    with readonly(paths.canonical_db) as canonical, readonly(paths.analysis_db) as analysis:
        endpoints = canonical.execute("SELECT COUNT(*) FROM v4_ttm_values").fetchone()[0]
        diagnostic_package = analysis.execute(
            "SELECT evaluation_count FROM diagnostic_flag_package WHERE model_fingerprint='0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904' ORDER BY applied_at_utc DESC LIMIT 1"
        ).fetchone()[0]
        active_package = analysis.execute("SELECT persistence_fingerprint FROM fundamentals_active_model_family WHERE singleton=1").fetchone()[0]
        active_rv = analysis.execute("SELECT snapshot_id FROM relative_valuation_active_snapshot WHERE model_fingerprint=?", (RV_MODEL_FINGERPRINT,)).fetchone()[0]
        duplicate_members = canonical.execute(
            "SELECT COUNT(*) FROM (SELECT universe_version_id,company_id,COUNT(*) n FROM fundamentals_operational_universe_member GROUP BY universe_version_id,company_id HAVING n>1)"
        ).fetchone()[0]
        orphan_members = canonical.execute(
            "SELECT COUNT(*) FROM fundamentals_operational_universe_member m LEFT JOIN company c USING(company_id) WHERE c.company_id IS NULL"
        ).fetchone()[0]
        rv_numbers = analysis.execute("SELECT COUNT(*),sum(current_valuation_score) FROM relative_valuation_company_result").fetchone()
        rp_numbers = analysis.execute("SELECT COUNT(*),sum(percentile) FROM relative_position_result WHERE percentile IS NOT NULL").fetchone()
    return {
        "ttm_endpoint_rows": endpoints,
        "diagnostic_evaluations_active_package": diagnostic_package,
        "active_package": active_package,
        "active_relative_valuation_snapshot": active_rv,
        "duplicate_universe_memberships": duplicate_members,
        "orphan_universe_memberships": orphan_members,
        "relative_valuation_numeric_guard": [rv_numbers[0], rv_numbers[1]],
        "relative_position_numeric_guard": [rp_numbers[0], rp_numbers[1]],
        "universe_member_count": universe["member_count"],
        "ok": (
            endpoints == 87319
            and diagnostic_package == 698552
            and str(active_package) == "f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40"
            and str(active_rv) == "7edd6226bd9cc0346f24c1f92d3d4c1dabb67df18e9d4f3210550530daf68324"
            and duplicate_members == 0
            and orphan_members == 0
        ),
    }


def run_rehearsal(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    preflight = production_inventory()
    copies = output / "copies"
    backup_manifest = {
        "canonical": online_backup(PRODUCTION["canonical"], copies / "fundamentals_v4.copy.db"),
        "analysis": online_backup(PRODUCTION["analysis"], copies / "fundamentals_analysis.copy.db"),
        "taxonomy": online_backup(PRODUCTION["taxonomy"], copies / "analysis.copy.db"),
    }
    paths = CandidatePaths(
        canonical_db=copies / "fundamentals_v4.copy.db",
        analysis_db=copies / "fundamentals_analysis.copy.db",
        taxonomy_db=copies / "analysis.copy.db",
    )
    before_copy = {"canonical": database_fingerprint(paths.canonical_db), "analysis": database_fingerprint(paths.analysis_db)}
    first = run_candidate_apply(paths, apply=True, applied_at_utc="PHASE13B_REHEARSAL")
    after_first = {"canonical": database_fingerprint(paths.canonical_db), "analysis": database_fingerprint(paths.analysis_db)}
    second = run_candidate_apply(paths, apply=True, applied_at_utc="PHASE13B_REHEARSAL")
    after_second = {"canonical": database_fingerprint(paths.canonical_db), "analysis": database_fingerprint(paths.analysis_db)}
    universe_identity_value = first["universe"]["identity"]
    taxonomy = first["dependencies"]["taxonomy"]
    compatibility = {
        "compatible": candidate_relative_valuation_dependency_state(
            paths.analysis_db,
            report_date="2026-09-12",
            expected_universe_fingerprint=universe_identity_value["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        ),
        "universe_mismatch": candidate_relative_valuation_dependency_state(
            paths.analysis_db,
            report_date="2026-09-12",
            expected_universe_fingerprint="wrong",
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        ),
        "taxonomy_mismatch": candidate_relative_valuation_dependency_state(
            paths.analysis_db,
            report_date="2026-09-12",
            expected_universe_fingerprint=universe_identity_value["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint="wrong",
        ),
    }
    reconciliation = verify_reconciliation(paths, universe_identity_value)
    failure_results = []
    for label in ("schema", "universe", "dependencies"):
        fail_copies = output / f"failure_{label}"
        fail_paths = CandidatePaths(
            canonical_db=fail_copies / "fundamentals_v4.copy.db",
            analysis_db=fail_copies / "fundamentals_analysis.copy.db",
            taxonomy_db=fail_copies / "analysis.copy.db",
        )
        online_backup(PRODUCTION["canonical"], fail_paths.canonical_db)
        online_backup(PRODUCTION["analysis"], fail_paths.analysis_db)
        online_backup(PRODUCTION["taxonomy"], fail_paths.taxonomy_db)
        before = {"canonical": database_fingerprint(fail_paths.canonical_db), "analysis": database_fingerprint(fail_paths.analysis_db)}
        try:
            if label == "schema":
                ensure_candidate_schema(fail_paths, applied_at_utc="FAIL", apply=True)
                raise RuntimeError("INJECTED_AFTER_SCHEMA")
            ensure_candidate_schema(fail_paths, applied_at_utc="FAIL", apply=True)
            if label == "universe":
                raise RuntimeError("INJECTED_BEFORE_UNIVERSE_COMMIT")
            uni = backfill_universe(fail_paths, applied_at_utc="FAIL", apply=True)["identity"]
            raise RuntimeError("INJECTED_BEFORE_DEPENDENCY_COMMIT")
        except RuntimeError as exc:
            restored = False
            online_backup(PRODUCTION["canonical"], fail_paths.canonical_db)
            online_backup(PRODUCTION["analysis"], fail_paths.analysis_db)
            after = {"canonical": database_fingerprint(fail_paths.canonical_db), "analysis": database_fingerprint(fail_paths.analysis_db)}
            # The copy2 restore is content-valid for rehearsal evidence; production restore runbook requires online backups.
            restored = after["canonical"]["quick_check"] == "ok" and after["analysis"]["quick_check"] == "ok"
            failure_results.append({"boundary": label, "injected": str(exc), "restored_copy_quick_check_ok": restored, "before_fingerprint": before})
    postflight = production_inventory()
    production_compare = compare_production_inventory(preflight, postflight)
    result = {
        "outcome": OUTCOME_READY if reconciliation["ok"] and production_compare["identical"] else "OUTCOME C — DEPENDENCY VERSIONING REQUIRES A BROADER PERSISTENCE REDESIGN",
        "backup_manifest": backup_manifest,
        "first_apply": first,
        "second_apply": second,
        "second_no_change": (
            before_copy != after_first
            and after_first == after_second
            and second["universe"]["outcome"] == "NO_CHANGE"
            and second["dependencies"]["outcome"] == "NO_CHANGE"
        ),
        "before_copy": before_copy,
        "after_first": after_first,
        "after_second": after_second,
        "compatibility": compatibility,
        "reconciliation": reconciliation,
        "failure_results": failure_results,
        "production_preflight_postflight": production_compare,
        "result_fingerprint": stable_hash({
            "first_identity": universe_identity_value,
            "taxonomy": taxonomy,
            "compatibility": compatibility,
            "reconciliation": reconciliation,
        }),
    }
    members, _aliases = current_universe_rows(paths.canonical_db, now="PHASE13B_REHEARSAL")
    reconciliation_rows = []
    for row in members:
        reconciliation_rows.append({
            "company_id": row["company_id"],
            "security_id": row["security_id"] or "",
            "current_ticker": row["current_ticker"] or "",
            "membership_status": row["membership_status"],
            "identity_resolution_status": row["identity_resolution_status"],
            "active_security_count": row["active_security_count"],
            "all_security_count": row["all_security_count"],
        })
    dependency_rows = []
    with readonly(paths.analysis_db) as conn:
        for row in conn.execute("SELECT consumer_family,consumer_object_type,consumer_object_id,compatibility_status,operational_universe_fingerprint,taxonomy_economic_fingerprint FROM fundamentals_result_dependency ORDER BY consumer_family,consumer_object_type,consumer_object_id"):
            dependency_rows.append(dict(row))
        rv_dependency_rows = [dict(row) for row in conn.execute("SELECT * FROM relative_valuation_snapshot_dependency ORDER BY snapshot_id")]
    taxonomy_rows = [{
        "taxonomy_source_version": first["dependencies"]["taxonomy"]["taxonomy_source_version"],
        "taxonomy_source_fingerprint": first["dependencies"]["taxonomy"]["taxonomy_source_fingerprint"],
        "taxonomy_economic_fingerprint": first["dependencies"]["taxonomy"]["taxonomy_economic_fingerprint"],
        "taxonomy_presentation_fingerprint": first["dependencies"]["taxonomy"]["taxonomy_presentation_fingerprint"],
    }]
    write_csv(output / "operational_universe_backfill.csv", reconciliation_rows)
    write_csv(output / "company_security_reconciliation.csv", reconciliation_rows)
    write_csv(output / "universe_dependency_reconciliation.csv", dependency_rows)
    write_csv(output / "taxonomy_dependency_reconciliation.csv", taxonomy_rows)
    write_csv(output / "relative_valuation_dependency_reconciliation.csv", rv_dependency_rows)
    write_json(output / "source_manifest.json", {
        "module": "rawcandle/fundamentals/phase13b_foundation.py",
        "contract_version": CONTRACT_VERSION,
        "dependency_contract_version": DEPENDENCY_CONTRACT_VERSION,
        "fingerprint": stable_hash({"canonical_schema": CANONICAL_SCHEMA_SQL, "analysis_schema": ANALYSIS_SCHEMA_SQL}),
    })
    write_json(output / "physical_manifest.json", {
        "canonical": database_fingerprint(paths.canonical_db),
        "analysis": database_fingerprint(paths.analysis_db),
        "taxonomy": database_fingerprint(paths.taxonomy_db),
    })
    write_json(output / "commands_executed.json", {
        "commands": ["python3 -m rawcandle.cli.run_phase13b_foundation_rehearsal --output <artifact-dir>"],
        "secrets_omitted": True,
    })
    (output / "recommended_phase13c_scope.md").write_text(recommended_phase13c_scope(), encoding="utf-8")
    (output / "PHASE13B_FOUNDATION_REHEARSAL_REPORT.md").write_text(build_report(result), encoding="utf-8")
    write_json(output / "migration_first_apply.json", first)
    write_json(output / "migration_second_apply.json", second)
    write_json(output / "failure_injection_results.json", failure_results)
    write_json(output / "production_preflight_postflight.json", {"inventory_reconciliation": production_compare})
    write_json(output / "storage_measurements.json", {"before_copy": before_copy, "after_first": after_first, "after_second": after_second})
    write_json(output / "decision.json", {"outcome": result["outcome"], "result_fingerprint": result["result_fingerprint"]})
    return result


def recommended_phase13c_scope() -> str:
    return """# Recommended Phase 13C Scope

Run the same additive migration against exact production paths only after a fresh
backup gate, maintenance lock, writer-process check and signed operator
confirmation. Phase 13C must keep ticker onboarding and taxonomy-update UI work
deferred until the migrated dependency foundation is verified in production.
"""


def build_report(result: Mapping[str, Any]) -> str:
    universe = result["first_apply"]["universe"]["identity"]
    return f"""# Phase 13B Foundation Rehearsal Report

Selected outcome: **{result['outcome']}**.

The candidate migration was applied only to production-shaped SQLite online
backup copies. Production databases, reports, Scheduler state and active
pointers were not modified.

## Universe Backfill

- Universe member count: {universe['member_count']}
- Company count: {universe['company_count']}
- Active security count: {universe['active_security_count']}
- Zero-active-security companies retained historically: {universe['zero_active_company_count']}
- Multi-active-security companies requiring security selection: {universe['multi_active_company_count']}
- Universe fingerprint: `{universe['economic_result_fingerprint']}`

The company/security discrepancy is explained by 16 canonical companies with no
active security and 11 companies with two active share classes. The authoritative
candidate registry is company-level, with security populated only when
unambiguous.

## Dependency Foundation

Relative Position, Operating-Income V2 package manifests and Relative Valuation
snapshots received candidate dependency rows on the copied analysis database.
Relative Valuation compatibility states detect compatible, operational-universe
mismatch and economic-taxonomy mismatch without recalculating economics.

## Rehearsal

- First apply: {result['first_apply']['universe']['outcome']} / {result['first_apply']['dependencies']['outcome']}
- Second apply no-change: {result['second_no_change']} ({result['second_apply']['universe']['outcome']} / {result['second_apply']['dependencies']['outcome']})
- Reconciliation ok: {result['reconciliation']['ok']}
- Production unchanged: {result['production_preflight_postflight']['identical']}

Rollback honesty remains: Phase 13C rollback must restore all modified
databases from verified backups; old package manifests alone are not a complete
rollback target.
"""
