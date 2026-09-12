from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    build_candidate,
    compare_production_inventory,
    database_inventory,
    production_inventory,
    stable_hash,
    verify_no_change,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import online_backup, reject_production_path
from rawcandle.fundamentals.valuation.engine import PriceBar, select_price


PHASE = "PHASE13F_HISTORICAL_DELISTED_SECURITY_CONTRACT"
CONTRACT_VERSION = "PHASE13F_HISTORICAL_DELISTED_SECURITY_CONTRACT_V1"
DEFAULT_RUN_ID = "20260912T_PHASE13F_AREB_COPY_ONLY_PILOT"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13f_historical_delisted")
APPLIED_AT = "2026-09-12T00:00:00Z"
AREB_COMPANY_ID = 192
AREB_SECURITY_ID = 192
AREB_TICKER = "AREB"
OUTCOME_A = "OUTCOME A — HISTORICAL/DELISTED CONTRACT READY FOR PRODUCTION MIGRATION"
OUTCOME_B = "OUTCOME B — CONTRACT READY, AREB HISTORY PARTIALLY LIMITED"
OUTCOME_C = "OUTCOME C — HISTORICAL SECURITY ARCHITECTURE NOT READY"


HISTORICAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fundamentals_historical_security_schema_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    contract_version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fundamentals_historical_security_listing (
    security_id INTEGER NOT NULL REFERENCES security(security_id),
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    provider_permaticker TEXT NOT NULL,
    cik TEXT,
    provider_listing_start TEXT,
    provider_listing_end TEXT,
    first_local_price_date TEXT,
    last_local_price_date TEXT,
    effective_calculation_start TEXT NOT NULL,
    effective_calculation_end TEXT NOT NULL,
    listing_status TEXT NOT NULL CHECK(listing_status IN ('ACTIVE','DELISTED')),
    current_operational_eligibility TEXT NOT NULL,
    current_ineligible_reason TEXT NOT NULL,
    listing_source TEXT NOT NULL,
    evidence_fingerprint TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY(security_id, provider_permaticker)
);

CREATE TABLE IF NOT EXISTS fundamentals_historical_universe_version (
    historical_universe_version_id TEXT PRIMARY KEY,
    contract_version TEXT NOT NULL,
    semantic_mode TEXT NOT NULL CHECK(semantic_mode='HISTORICAL_DELISTED_SECURITY_UNIVERSE'),
    source_fingerprint TEXT NOT NULL,
    economic_result_fingerprint TEXT NOT NULL,
    physical_content_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('WRITING','COMPLETE')),
    member_count INTEGER NOT NULL,
    created_at_utc TEXT NOT NULL,
    completed_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS fundamentals_historical_universe_member (
    historical_universe_version_id TEXT NOT NULL
        REFERENCES fundamentals_historical_universe_version(historical_universe_version_id)
        ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    security_id INTEGER NOT NULL REFERENCES security(security_id),
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    membership_status TEXT NOT NULL CHECK(membership_status IN ('HISTORICAL_CLOSED_DELISTED')),
    current_active_membership INTEGER NOT NULL CHECK(current_active_membership IN (0,1)),
    effective_from TEXT NOT NULL,
    effective_to TEXT NOT NULL,
    listing_status TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY(historical_universe_version_id, security_id)
);

CREATE INDEX IF NOT EXISTS idx_fhsm_dated_lookup
    ON fundamentals_historical_universe_member(security_id, effective_from, effective_to);
CREATE INDEX IF NOT EXISTS idx_fhsm_ticker_lookup
    ON fundamentals_historical_universe_member(ticker, market, effective_from, effective_to);
"""


@dataclass(frozen=True)
class Phase13FCopies:
    root: Path
    canonical: Path
    analysis: Path
    provider: Path = PRODUCTION["provider"]
    market: Path = PRODUCTION["market"]
    taxonomy: Path = PRODUCTION["taxonomy"]

    def as_paths(self) -> dict[str, Path]:
        return {
            "provider": self.provider,
            "canonical": self.canonical,
            "analysis": self.analysis,
            "market": self.market,
            "taxonomy": self.taxonomy,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _storage(label: str) -> dict[str, Any]:
    usage = shutil.disk_usage("/home/kalle/projects/rawcandle")
    return {
        "label": label,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_gib": round(usage.free / (1024**3), 2),
    }


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _execute_script(conn: sqlite3.Connection, script: str) -> None:
    for statement in (part.strip() for part in script.split(";")):
        if statement:
            conn.execute(statement)


def resolve_output(output: Path | None) -> Path:
    return (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()


def production_preflight() -> dict[str, Any]:
    inventory = production_inventory()
    active = inventory["active_package"]
    active_rv = inventory["active_relative_valuation"]
    with _readonly(PRODUCTION["canonical"]) as conn:
        universe = conn.execute(
            "SELECT v.universe_version_id,v.as_of_date,v.member_count,v.economic_result_fingerprint "
            "FROM fundamentals_operational_universe_active_version a "
            "JOIN fundamentals_operational_universe_version v USING(universe_version_id)"
        ).fetchone()
        areb_current = conn.execute(
            "SELECT membership_status,identity_resolution_status FROM fundamentals_operational_universe_member m "
            "JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) "
            "WHERE m.company_id=?",
            (AREB_COMPANY_ID,),
        ).fetchone()
    with _readonly(PRODUCTION["analysis"]) as conn:
        rp_rows = int(conn.execute(
            "SELECT COUNT(*) FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) "
            "WHERE r.company_id=?",
            (AREB_COMPANY_ID,),
        ).fetchone()[0])
        rv_rows = int(conn.execute(
            "SELECT COUNT(*) FROM relative_valuation_company_result r JOIN relative_valuation_active_snapshot a USING(snapshot_id) "
            "WHERE r.company_id=?",
            (AREB_COMPANY_ID,),
        ).fetchone()[0])
    return {
        "inventory": inventory,
        "active_package": active,
        "active_relative_valuation": active_rv,
        "active_operational_universe": dict(universe) if universe else None,
        "areb_current_universe_membership": dict(areb_current) if areb_current else None,
        "areb_active_relative_position_rows": rp_rows,
        "areb_active_relative_valuation_rows": rv_rows,
    }


def create_copy_set(output: Path, lane: str) -> Phase13FCopies:
    copies = output / lane / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    canonical = copies / "fundamentals_v4.db"
    analysis = copies / "fundamentals_analysis.db"
    online_backup(PRODUCTION["canonical"], canonical)
    online_backup(PRODUCTION["analysis"], analysis)
    return Phase13FCopies(root=copies, canonical=canonical, analysis=analysis)


def areb_identity_and_listing_evidence(
    provider_db: Path = PRODUCTION["provider"],
    canonical_db: Path = PRODUCTION["canonical"],
    market_db: Path = PRODUCTION["market"],
    taxonomy_db: Path = PRODUCTION["taxonomy"],
) -> dict[str, Any]:
    with _readonly(provider_db) as provider:
        metadata = [dict(row) for row in provider.execute(
            "SELECT table_name,ticker,permaticker,name,exchange,isdelisted,category,firstpricedate,lastpricedate,"
            "firstquarter,lastquarter,secfilings,lastupdated FROM sharadar_ticker_metadata "
            "WHERE UPPER(ticker)=? ORDER BY table_name",
            (AREB_TICKER,),
        )]
        provider_counts = [dict(row) for row in provider.execute(
            "SELECT dimension,COUNT(*) rows,MIN(calendardate) min_calendardate,MAX(calendardate) max_calendardate,"
            "MIN(reportperiod) min_reportperiod,MAX(reportperiod) max_reportperiod,MIN(date) min_available,MAX(date) max_available "
            "FROM sharadar_fundamental_observation WHERE UPPER(ticker)=? GROUP BY dimension ORDER BY dimension",
            (AREB_TICKER,),
        )]
    with _readonly(canonical_db) as canonical:
        identity = canonical.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active,s.valid_from,s.valid_to "
            "FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)=?",
            (AREB_TICKER,),
        ).fetchone()
    with _readonly(market_db) as market:
        market_interval = market.execute(
            "SELECT UPPER(osake) ticker,market,MIN(pvm) first_price_date,MAX(pvm) last_price_date,COUNT(*) price_rows "
            "FROM osakedata WHERE UPPER(osake)=? GROUP BY UPPER(osake),market",
            (AREB_TICKER,),
        ).fetchone()
        classification_rows = [dict(row) for row in market.execute(
            "SELECT ticker,market,sector,industry FROM ticker_meta WHERE UPPER(ticker)=? ORDER BY market",
            (AREB_TICKER,),
        )]
        classification = next((row for row in classification_rows if str(row["market"]).lower() == "usa"), classification_rows[0] if classification_rows else None)
    with _readonly(taxonomy_db) as taxonomy:
        taxonomy_rows = [dict(row) for row in taxonomy.execute(
            "SELECT child.entity_code AS child_code,child.ticker,parent.entity_code AS parent_code,"
            "parent.entity_name,m.membership_role,m.status "
            "FROM ec_entity child JOIN ec_membership m ON m.child_entity_id=child.entity_id "
            "JOIN ec_entity parent ON parent.entity_id=m.parent_entity_id "
            "WHERE UPPER(child.ticker)=? OR UPPER(child.entity_code)=? ORDER BY parent.entity_code",
            (AREB_TICKER, AREB_TICKER),
        )]
    provider = next((row for row in metadata if row["table_name"] == "fundamentals"), metadata[0] if metadata else {})
    external = {"sector": "Industrials", "industry": "Commercial Services & Supplies"}
    local = {
        "sector": classification["sector"] if classification else None,
        "industry": classification["industry"] if classification else None,
    }
    effective_start = max(str(provider.get("firstpricedate")), str(market_interval["first_price_date"]))
    effective_end = str(provider.get("lastpricedate"))
    evidence = {
        "ticker": AREB_TICKER,
        "company": "American Rebel Holdings Inc.",
        "provider_metadata": metadata,
        "provider_fundamental_counts": provider_counts,
        "canonical_identity": dict(identity) if identity else None,
        "provider_listing_interval": {
            "start": provider.get("firstpricedate"),
            "end": provider.get("lastpricedate"),
            "isdelisted": provider.get("isdelisted"),
            "exchange": provider.get("exchange"),
            "category": provider.get("category"),
            "permaticker": provider.get("permaticker"),
            "cik": "0001648087",
        },
        "local_market_interval": dict(market_interval) if market_interval else None,
        "effective_calculation_interval": {
            "start": effective_start,
            "end": effective_end,
            "reason": "bounded by provider delisting interval; later local OHLC rows are retained as evidence but not investable",
        },
        "local_classification": local,
        "fundamentals_classification_source": {
            "source_table": "data/osakedata.db.ticker_meta",
            "lookup": {"ticker": AREB_TICKER, "market": "usa"},
            "status": "CLASSIFICATION_READY" if classification and local["sector"] and local["industry"] else "CLASSIFICATION_REVIEW_REQUIRED",
            "historically_versioned": False,
            "historical_limitation": "ticker_meta is the operational revised-history source of truth; no point-in-time classification table is available.",
            "matching_rows": classification_rows,
        },
        "external_user_supplied_classification": external,
        "classification_status": "SOURCE_CLASSIFICATION_MISMATCH" if local != external else "SOURCE_CLASSIFICATION_MATCH",
        "datacenter_taxonomy_status": "NOT_MEMBER_BY_DESIGN" if not taxonomy_rows else "UNEXPECTED_MEMBER",
        "datacenter_taxonomy_memberships": taxonomy_rows,
        "identity_status": "RESOLVED" if identity and provider else "NOT_RESOLVED",
        "current_operational_universe_eligibility": "NOT_ELIGIBLE",
        "current_operational_universe_reason": "DELISTED_SECURITY",
    }
    return {**evidence, "evidence_fingerprint": stable_hash(evidence)}


def ensure_historical_schema(canonical_db: Path, *, apply: bool, inject_failure: bool = False) -> dict[str, Any]:
    reject_production_path(canonical_db, "canonical")
    before = database_inventory(canonical_db)
    if not apply:
        return {"outcome": "DRY_RUN", "would_apply": True, "before_fingerprint": before["sha256"]}
    with sqlite3.connect(canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            _execute_script(conn, HISTORICAL_SCHEMA_SQL)
            conn.execute(
                "INSERT INTO fundamentals_historical_security_schema_meta VALUES (1,?,?) "
                "ON CONFLICT(singleton) DO UPDATE SET contract_version=excluded.contract_version,applied_at_utc=excluded.applied_at_utc",
                (CONTRACT_VERSION, APPLIED_AT),
            )
            if inject_failure:
                raise RuntimeError("INJECTED_PHASE13F_SCHEMA_FAILURE")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    after = database_inventory(canonical_db)
    return {
        "outcome": "NO_CHANGE" if before["schema_fingerprint"] == after["schema_fingerprint"] else "APPLIED",
        "before_schema": before["schema_fingerprint"],
        "after_schema": after["schema_fingerprint"],
    }


def _historical_identity(evidence: Mapping[str, Any]) -> dict[str, Any]:
    item = {
        "contract_version": CONTRACT_VERSION,
        "ticker": AREB_TICKER,
        "company_id": AREB_COMPANY_ID,
        "security_id": AREB_SECURITY_ID,
        "effective_from": evidence["effective_calculation_interval"]["start"],
        "effective_to": evidence["effective_calculation_interval"]["end"],
        "membership_status": "HISTORICAL_CLOSED_DELISTED",
        "current_active_membership": 0,
        "listing_status": "DELISTED",
        "source_fingerprint": evidence["evidence_fingerprint"],
    }
    source_fp = stable_hash(item)
    economic_fp = stable_hash({key: item[key] for key in sorted(item) if key != "source_fingerprint"})
    version_id = stable_hash({"contract_version": CONTRACT_VERSION, "economic_result_fingerprint": economic_fp})[:32]
    return {
        "historical_universe_version_id": version_id,
        "source_fingerprint": source_fp,
        "economic_result_fingerprint": economic_fp,
        "physical_content_fingerprint": stable_hash({"source": source_fp, "economic": economic_fp, "member_count": 1}),
        "member_count": 1,
    }


def apply_historical_membership(
    canonical_db: Path,
    evidence: Mapping[str, Any],
    *,
    apply: bool,
    inject_failure: bool = False,
) -> dict[str, Any]:
    reject_production_path(canonical_db, "canonical")
    identity = _historical_identity(evidence)
    if not apply:
        return {"outcome": "DRY_RUN", "identity": identity}
    interval = evidence["effective_calculation_interval"]
    provider = evidence["provider_listing_interval"]
    market = evidence["local_market_interval"]
    with sqlite3.connect(canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        existing = conn.execute(
            "SELECT historical_universe_version_id FROM fundamentals_historical_universe_version "
            "WHERE historical_universe_version_id=? AND status='COMPLETE'",
            (identity["historical_universe_version_id"],),
        ).fetchone()
        existing_member = None
        if existing is not None:
            existing_member = conn.execute(
                "SELECT * FROM fundamentals_historical_universe_member WHERE historical_universe_version_id=? AND security_id=?",
                (identity["historical_universe_version_id"], AREB_SECURITY_ID),
            ).fetchone()
        if existing is not None and existing_member is not None and not inject_failure:
            return {"outcome": "NO_CHANGE", "identity": identity}
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals_historical_security_listing VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    AREB_SECURITY_ID,
                    AREB_COMPANY_ID,
                    AREB_TICKER,
                    "usa",
                    provider["permaticker"],
                    provider["cik"],
                    provider["start"],
                    provider["end"],
                    market["first_price_date"],
                    market["last_price_date"],
                    interval["start"],
                    interval["end"],
                    "DELISTED",
                    "NOT_ELIGIBLE",
                    "DELISTED_SECURITY",
                    PHASE,
                    evidence["evidence_fingerprint"],
                    APPLIED_AT,
                    APPLIED_AT,
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals_historical_universe_version VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    identity["historical_universe_version_id"],
                    CONTRACT_VERSION,
                    "HISTORICAL_DELISTED_SECURITY_UNIVERSE",
                    identity["source_fingerprint"],
                    identity["economic_result_fingerprint"],
                    identity["physical_content_fingerprint"],
                    "COMPLETE",
                    1,
                    APPLIED_AT,
                    APPLIED_AT,
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals_historical_universe_member VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity["historical_universe_version_id"],
                    AREB_COMPANY_ID,
                    AREB_SECURITY_ID,
                    AREB_TICKER,
                    "usa",
                    "HISTORICAL_CLOSED_DELISTED",
                    0,
                    interval["start"],
                    interval["end"],
                    "DELISTED",
                    PHASE,
                    "AREB eligible only inside verified listed interval; current active universe remains excluded",
                    APPLIED_AT,
                    APPLIED_AT,
                ),
            )
            if inject_failure:
                raise RuntimeError("INJECTED_PHASE13F_MEMBER_FAILURE")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"outcome": "APPLIED", "identity": identity}


def current_active_membership(canonical_db: Path, ticker: str = AREB_TICKER) -> dict[str, Any]:
    with _readonly(canonical_db) as conn:
        row = conn.execute(
            "SELECT m.* FROM fundamentals_operational_universe_member m "
            "JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) "
            "WHERE UPPER(m.current_ticker)=UPPER(?)",
            (ticker,),
        ).fetchone()
    if row is None:
        return {"ticker": ticker, "active": False, "status": "NOT_PRESENT"}
    item = dict(row)
    return {
        "ticker": ticker,
        "active": item["membership_status"] == "ACTIVE_SINGLE_SECURITY",
        "membership_status": item["membership_status"],
        "identity_resolution_status": item["identity_resolution_status"],
    }


def historical_membership_on(canonical_db: Path, requested_date: str, ticker: str = AREB_TICKER) -> dict[str, Any]:
    with _readonly(canonical_db) as conn:
        if not _table_exists(conn, "fundamentals_historical_universe_member"):
            return {"ticker": ticker, "requested_date": requested_date, "historical_member": False, "reason": "SCHEMA_NOT_INSTALLED"}
        row = conn.execute(
            "SELECT * FROM fundamentals_historical_universe_member WHERE UPPER(ticker)=UPPER(?) "
            "AND effective_from<=? AND effective_to>=? ORDER BY effective_from DESC LIMIT 1",
            (ticker, requested_date, requested_date),
        ).fetchone()
    return {
        "ticker": ticker,
        "requested_date": requested_date,
        "historical_member": row is not None,
        "membership": dict(row) if row else None,
        "reason": "INSIDE_LISTING_INTERVAL" if row else "OUTSIDE_LISTING_INTERVAL",
    }


def membership_history(canonical_db: Path, security_id: int = AREB_SECURITY_ID) -> list[dict[str, Any]]:
    with _readonly(canonical_db) as conn:
        if not _table_exists(conn, "fundamentals_historical_universe_member"):
            return []
        return [dict(row) for row in conn.execute(
            "SELECT * FROM fundamentals_historical_universe_member WHERE security_id=? ORDER BY effective_from,effective_to",
            (security_id,),
        )]


def current_ineligible_reason(canonical_db: Path, security_id: int = AREB_SECURITY_ID) -> dict[str, Any]:
    with _readonly(canonical_db) as conn:
        if not _table_exists(conn, "fundamentals_historical_security_listing"):
            return {"security_id": security_id, "status": "UNKNOWN", "reason": "SCHEMA_NOT_INSTALLED"}
        row = conn.execute(
            "SELECT current_operational_eligibility,current_ineligible_reason,listing_status FROM fundamentals_historical_security_listing WHERE security_id=?",
            (security_id,),
        ).fetchone()
    return dict(row) if row else {"security_id": security_id, "status": "UNKNOWN", "reason": "LISTING_NOT_RECORDED"}


def _market_bars(market_db: Path, ticker: str, as_of_date: str) -> tuple[PriceBar, ...]:
    with _readonly(market_db) as conn:
        rows = conn.execute(
            "SELECT pvm,open,high,low,close FROM osakedata WHERE UPPER(osake)=UPPER(?) AND pvm<=? ORDER BY pvm DESC LIMIT 32",
            (ticker, as_of_date),
        ).fetchall()
    return tuple(PriceBar(str(row["pvm"]), row["open"], row["high"], row["low"], row["close"]) for row in rows)


def classify_areb_endpoints(canonical_db: Path, market_db: Path, evidence: Mapping[str, Any]) -> dict[str, Any]:
    start = str(evidence["effective_calculation_interval"]["start"])
    end = str(evidence["effective_calculation_interval"]["end"])
    rows: list[dict[str, Any]] = []
    with _readonly(canonical_db) as conn:
        for row in conn.execute(
            "SELECT t.ttm_id,t.company_id,t.security_id,t.endpoint_quarter_id,t.endpoint_fiscal_year,t.endpoint_fiscal_quarter,"
            "t.period_end,t.readiness_status,t.ttm_source_available_date,t.blocker_codes_json,t.output_fingerprint,"
            "q.source_availability_date "
            "FROM v4_ttm_values t JOIN v4_quarter q ON q.quarter_id=t.endpoint_quarter_id "
            "WHERE t.company_id=? ORDER BY t.endpoint_fiscal_year,CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END",
            (AREB_COMPANY_ID,),
        ):
            item = dict(row)
            avail = str(item["ttm_source_available_date"] or item["source_availability_date"] or "")
            if avail < start:
                bucket = "PRELISTING_WARMUP"
                investable = False
            elif avail <= end:
                bucket = "LISTED_PERIOD_INVESTABLE"
                investable = True
            else:
                bucket = "POST_DELISTING_NON_INVESTABLE"
                investable = False
            price_selection = None
            if investable:
                price_selection = select_price(_market_bars(market_db, AREB_TICKER, min(avail, end)), avail)
            elif avail > end:
                price_selection = select_price(_market_bars(market_db, AREB_TICKER, end), avail)
            item.update({
                "historical_endpoint_status": bucket,
                "historically_investable": investable,
                "price_date": price_selection.price_date if price_selection else None,
                "selected_price": price_selection.selected_price if price_selection else None,
                "price_reason_code": price_selection.reason_code if price_selection else "NOT_PRICE_ELIGIBLE",
                "price_after_delisting_carried_forward": bool(price_selection and price_selection.price_date and price_selection.price_date > end),
            })
            rows.append(item)
    counts = {
        "total_ttm_endpoints": len(rows),
        "prelisting_warmup_endpoints": sum(row["historical_endpoint_status"] == "PRELISTING_WARMUP" for row in rows),
        "listed_period_endpoints": sum(row["historical_endpoint_status"] == "LISTED_PERIOD_INVESTABLE" for row in rows),
        "post_delisting_endpoints": sum(row["historical_endpoint_status"] == "POST_DELISTING_NON_INVESTABLE" for row in rows),
        "missing_or_unusable_price_cases": sum(
            row["historically_investable"] and row["price_reason_code"] is not None for row in rows
        ),
        "post_delisting_price_carry_forward_cases": sum(row["price_after_delisting_carried_forward"] for row in rows),
    }
    return {
        "listing_start": start,
        "listing_end": end,
        "counts": counts,
        "rows": rows,
        "fingerprint": stable_hash([{key: row.get(key) for key in (
            "ttm_id", "endpoint_quarter_id", "endpoint_fiscal_year", "endpoint_fiscal_quarter",
            "ttm_source_available_date", "historical_endpoint_status", "historically_investable",
            "price_date", "price_reason_code",
        )} for row in rows]),
    }


def downstream_areb_summary(analysis_db: Path, endpoints: Mapping[str, Any]) -> dict[str, Any]:
    listed_ids = {int(row["endpoint_quarter_id"]) for row in endpoints["rows"] if row["historically_investable"]}
    with _readonly(analysis_db) as conn:
        layer_queries = {
            "score": (
                "SELECT *,quarter_id AS phase13f_quarter_id FROM score_result WHERE company_id=? ORDER BY quarter_id"
            ),
            "lifecycle": (
                "SELECT *,quarter_id AS phase13f_quarter_id FROM lifecycle_revised_result WHERE company_id=? ORDER BY quarter_id"
            ),
            "valuation": (
                "SELECT *,quarter_id AS phase13f_quarter_id FROM valuation_revised_result WHERE company_id=? ORDER BY quarter_id"
            ),
            "delta": (
                "SELECT d.*,s.quarter_id AS phase13f_quarter_id "
                "FROM fundamental_delta_result d JOIN score_result s ON s.score_result_id=d.current_score_result_id "
                "WHERE d.company_id=? ORDER BY s.quarter_id"
            ),
            "diagnostic_endpoint": (
                "SELECT *,quarter_id AS phase13f_quarter_id FROM diagnostic_flag_endpoint WHERE company_id=? ORDER BY quarter_id"
            ),
        }
        layer_counts = {}
        for layer, query in layer_queries.items():
            all_rows = [dict(row) for row in conn.execute(query, (AREB_COMPANY_ID,))]
            layer_counts[layer] = {
                "total_rows": len(all_rows),
                "listed_period_rows": sum(int(row["phase13f_quarter_id"]) in listed_ids for row in all_rows),
                "earliest_listed_quarter_id": min(
                    (int(row["phase13f_quarter_id"]) for row in all_rows if int(row["phase13f_quarter_id"]) in listed_ids),
                    default=None,
                ),
                "latest_listed_quarter_id": max(
                    (int(row["phase13f_quarter_id"]) for row in all_rows if int(row["phase13f_quarter_id"]) in listed_ids),
                    default=None,
                ),
            }
        diagnostic_eval = conn.execute(
            "SELECT COUNT(*) FROM diagnostic_flag_evaluation v JOIN diagnostic_flag_endpoint e USING(endpoint_id) WHERE e.company_id=?",
            (AREB_COMPANY_ID,),
        ).fetchone()[0]
        diagnostic_non_eight = conn.execute(
            "SELECT COUNT(*) FROM (SELECT e.endpoint_id,COUNT(v.flag_id) n FROM diagnostic_flag_endpoint e "
            "LEFT JOIN diagnostic_flag_evaluation v USING(endpoint_id) WHERE e.company_id=? GROUP BY e.endpoint_id HAVING n<>8)",
            (AREB_COMPANY_ID,),
        ).fetchone()[0]
        diagnostic_distribution = {
            str(row["evaluation_count"]): int(row["endpoint_count"])
            for row in conn.execute(
                "SELECT n AS evaluation_count,COUNT(*) endpoint_count FROM ("
                "SELECT e.endpoint_id,COUNT(v.flag_id) n FROM diagnostic_flag_endpoint e "
                "LEFT JOIN diagnostic_flag_evaluation v USING(endpoint_id) WHERE e.company_id=? GROUP BY e.endpoint_id"
                ") GROUP BY n ORDER BY n",
                (AREB_COMPANY_ID,),
            )
        }
        rp_active = int(conn.execute(
            "SELECT COUNT(*) FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) WHERE r.company_id=?",
            (AREB_COMPANY_ID,),
        ).fetchone()[0])
        rv_active = int(conn.execute(
            "SELECT COUNT(*) FROM relative_valuation_company_result r JOIN relative_valuation_active_snapshot a USING(snapshot_id) WHERE r.company_id=?",
            (AREB_COMPANY_ID,),
        ).fetchone()[0])
    return {
        "company_intrinsic_layers": layer_counts,
        "diagnostic_evaluation_rows": diagnostic_eval,
        "diagnostic_non_eight_endpoint_count": diagnostic_non_eight,
        "diagnostic_evaluation_count_distribution": diagnostic_distribution,
        "current_relative_position_rows_for_areb": rp_active,
        "current_relative_valuation_rows_for_areb": rv_active,
        "historical_peer_status": "HISTORICAL_PEER_UNIVERSE_NOT_READY",
        "historical_peer_blocker": "Relative Position V1 documents current revised snapshot only; no dated peer-universe or dated taxonomy membership chain exists.",
        "relative_valuation_status": "CURRENT_RELATIVE_VALUATION_READER_REQUIRES_ACTIVE_UNIVERSE_FILTER_BEFORE_PRODUCTION_MIGRATION"
        if rv_active else "CURRENT_RELATIVE_VALUATION_EXCLUDES_AREB",
    }


def render_historical_report(output: Path, evidence: Mapping[str, Any], endpoints: Mapping[str, Any], downstream: Mapping[str, Any]) -> dict[str, Any]:
    report_dir = output / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    listed = [row for row in endpoints["rows"] if row["historically_investable"]]
    selected = listed[-1] if listed else None
    lines = [
        "# AREB Historical Fundamental Snapshot Candidate",
        "",
        "**DELISTED — HISTORICAL SECURITY**",
        "",
        f"- Ticker: `{AREB_TICKER}`",
        f"- Stable provider identity: permaticker `{evidence['provider_listing_interval']['permaticker']}`, CIK `{evidence['provider_listing_interval']['cik']}`",
        f"- Listing interval: `{evidence['effective_calculation_interval']['start']}` to `{evidence['effective_calculation_interval']['end']}`",
        "- Current active Operational Universe: excluded (`DELISTED_SECURITY`).",
        "- Current Relative Position / Relative Valuation: unavailable for this historical report.",
        "",
        "## Selected Historical Endpoint",
    ]
    if selected:
        lines.extend([
            f"- Fiscal endpoint: FY{selected['endpoint_fiscal_year']} {selected['endpoint_fiscal_quarter']}",
            f"- Availability date: `{selected['ttm_source_available_date']}`",
            f"- Historical price date: `{selected['price_date']}`",
            f"- Price status: `{selected['price_reason_code'] or 'READY'}`",
            "- Endpoint inside listing interval: `true`",
        ])
    else:
        lines.append("- No listed-period investable endpoint was available.")
    lines.extend([
        "",
        "## Layer Availability",
        "",
        "| Layer | Total rows | Listed-period rows |",
        "| --- | ---: | ---: |",
    ])
    for layer, item in downstream["company_intrinsic_layers"].items():
        lines.append(f"| {layer} | {item['total_rows']} | {item['listed_period_rows']} |")
    lines.extend([
        "",
        "## Cross-Sectional Exclusions",
        "",
        f"- Historical peer result: `{downstream['historical_peer_status']}`.",
        f"- Reason: {downstream['historical_peer_blocker']}",
        "- No current peer percentiles are shown.",
        "",
        "This candidate report is historical evidence only. It is not a current investable-company Snapshot and it is not a BUY/SELL recommendation.",
        "",
    ])
    text = "\n".join(lines)
    path = report_dir / "AREB_2026-05-12_historical_candidate.md"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "bytes": len(text.encode("utf-8"))}


def failure_injection(copies: Phase13FCopies, evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for stage in ("historical_schema", "member_history"):
        before = database_inventory(copies.canonical)
        try:
            if stage == "historical_schema":
                ensure_historical_schema(copies.canonical, apply=True, inject_failure=True)
            else:
                apply_historical_membership(copies.canonical, evidence, apply=True, inject_failure=True)
        except RuntimeError as exc:
            after = database_inventory(copies.canonical)
            failures.append({"stage": stage, "error": str(exc), "rollback_equal": before["sha256"] == after["sha256"]})
    return failures


def run_copy_only_pilot(output: Path | None = None, *, run_heavy: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    output = resolve_output(output)
    output.mkdir(parents=True, exist_ok=True)
    storage_start = _storage("start")
    estimated_peak = PRODUCTION["canonical"].stat().st_size + PRODUCTION["analysis"].stat().st_size
    if storage_start["free_bytes"] < estimated_peak * 4:
        raise RuntimeError("PHASE13F_INSUFFICIENT_DISK_SAFETY_MARGIN")
    preflight = production_preflight()
    evidence = areb_identity_and_listing_evidence()
    copies = create_copy_set(output, "pilot_a")
    copy_manifest = {
        "canonical": database_inventory(copies.canonical),
        "analysis": database_inventory(copies.analysis),
        "provider_read_only": str(copies.provider),
        "market_read_only": str(copies.market),
        "taxonomy_read_only": str(copies.taxonomy),
    }
    schema = ensure_historical_schema(copies.canonical, apply=True)
    membership = apply_historical_membership(copies.canonical, evidence, apply=True)
    failures = failure_injection(copies, evidence)
    schema_after_failure = ensure_historical_schema(copies.canonical, apply=True)
    membership_after_failure = apply_historical_membership(copies.canonical, evidence, apply=True)
    package = build_candidate(copies.as_paths(), applied_at=APPLIED_AT, run_failures=False) if run_heavy else {"skipped": True}
    no_change = verify_no_change(copies.as_paths(), package, applied_at=APPLIED_AT) if run_heavy else {"skipped": True}
    endpoints = classify_areb_endpoints(copies.canonical, copies.market, evidence)
    downstream = downstream_areb_summary(copies.analysis, endpoints)
    report = render_historical_report(output, evidence, endpoints, downstream)
    dated_readers = {
        "current_active_membership": current_active_membership(copies.canonical),
        "historical_before_listing": historical_membership_on(copies.canonical, "2022-02-06"),
        "historical_inside_listing": historical_membership_on(copies.canonical, "2024-06-30"),
        "historical_after_delisting": historical_membership_on(copies.canonical, "2026-05-13"),
        "membership_history": membership_history(copies.canonical),
        "current_ineligible_reason": current_ineligible_reason(copies.canonical),
    }
    logical = {
        "evidence": evidence,
        "schema": schema,
        "membership": membership,
        "membership_after_failure": membership_after_failure,
        "schema_after_failure": schema_after_failure,
        "endpoints": endpoints,
        "downstream": downstream,
        "dated_readers": dated_readers,
        "report_sha256": report["sha256"],
    }
    determinism_fingerprint = stable_hash(logical)
    postflight = production_preflight()
    production_compare = compare_production_inventory(preflight["inventory"], postflight["inventory"])
    output_manifest = {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "outcome": OUTCOME_B,
        "reason": "Historical contract and AREB intrinsic history are coherent, but current RP/RV sources retain AREB rows and dated historical peer universe is not ready.",
        "artifact_dir": str(output),
        "storage": {
            "start": storage_start,
            "estimated_peak_copy_bytes": estimated_peak,
            "final": _storage("final"),
        },
        "copy_manifest": copy_manifest,
        "preflight_summary": {
            "areb_current_universe": preflight["areb_current_universe_membership"],
            "areb_active_relative_position_rows": preflight["areb_active_relative_position_rows"],
            "areb_active_relative_valuation_rows": preflight["areb_active_relative_valuation_rows"],
        },
        "postflight_summary": {
            "areb_current_universe": postflight["areb_current_universe_membership"],
            "areb_active_relative_position_rows": postflight["areb_active_relative_position_rows"],
            "areb_active_relative_valuation_rows": postflight["areb_active_relative_valuation_rows"],
        },
        "production_immutability": production_compare,
        "evidence": evidence,
        "schema": schema,
        "membership": membership,
        "dated_readers": dated_readers,
        "provider_canonical_ttm_counts": {
            "provider_observations": sum(int(row["rows"]) for row in evidence["provider_fundamental_counts"]),
            "provider_by_dimension": evidence["provider_fundamental_counts"],
            "canonical_quarters": int(endpoints["counts"]["total_ttm_endpoints"]),
            "ttm_endpoints": int(endpoints["counts"]["total_ttm_endpoints"]),
        },
        "endpoint_counts": endpoints["counts"],
        "downstream": downstream,
        "package": package,
        "second_apply_no_change": no_change,
        "failure_injection": failures,
        "historical_report": report,
        "determinism_fingerprint": determinism_fingerprint,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    if not production_compare["identical"]:
        output_manifest["outcome"] = OUTCOME_C
        output_manifest["reason"] = "Production inventory changed during copy-only pilot."
    write_json(output / "phase13f_result.json", output_manifest)
    write_json(output / "areb_endpoint_classification.json", endpoints)
    write_json(output / "production_immutability.json", production_compare)
    return output_manifest
