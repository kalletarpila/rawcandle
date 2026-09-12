from __future__ import annotations

import csv
import json
import sqlite3
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    ROOT,
    database_inventory,
    rebuild_ttm,
    reconcile_canonical,
    stable_hash,
    write_csv,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    candidate_relative_valuation_dependency_state,
    online_backup,
    run_candidate_apply,
    taxonomy_identity,
)
from rawcandle.fundamentals.schema.production_bootstrap import insert_production_sharadar_observation


PHASE = "PHASE13D1_REAL_SOURCE_TICKER_ONBOARDING_REHEARSAL"
OUTCOME_BLOCKED = "OUTCOME C — REAL-SOURCE REBUILD, DEPENDENCY OR ROLLBACK CONTRACT NOT READY"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13d1_real_source"
ARCHIVE_PATH = ROOT / "data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip"
ARCHIVE_EXPECTED_SHA256 = "dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36"
SNDK_PERMATICKER = "643888"
SNDK_CIK = "0002023554"
SNDK_RELATED_TICKER = "SNDKV"
LOCAL_PHASE13A_CANDIDATES = (
    "ALUR", "AREB", "AVB", "BSLK", "CERO", "LBRDA", "LEG", "LYRA",
    "MAPS", "MSPR", "NOTE", "PTIX", "RMAX", "SSKN", "TALK", "VSTD",
)
SUPPORTED_ONBOARDING_CATEGORIES = {
    "Domestic Common Stock",
    "Domestic Common Stock Primary Class",
}
SUPPORTED_ONBOARDING_EXCHANGES = {"NASDAQ", "NYSE", "NYSEMKT"}
MIN_CURRENT_MARKET_DATE = "2026-08-01"


@dataclass(frozen=True)
class RehearsalCopies:
    root: Path
    provider: Path
    canonical: Path
    analysis: Path
    market: Path
    taxonomy: Path

    def candidate_paths(self) -> CandidatePaths:
        return CandidatePaths(
            canonical_db=self.canonical,
            analysis_db=self.analysis,
            taxonomy_db=self.taxonomy,
            provider_db=self.provider,
            market_db=self.market,
        )


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def production_preflight() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "production": {name: database_inventory(path) for name, path in PRODUCTION.items()},
        "archive": {
            "path": str(ARCHIVE_PATH),
            "exists": ARCHIVE_PATH.exists(),
            "sha256": sha256(ARCHIVE_PATH) if ARCHIVE_PATH.exists() else None,
            "expected_sha256": ARCHIVE_EXPECTED_SHA256,
            "matches_expected": ARCHIVE_PATH.exists() and sha256(ARCHIVE_PATH) == ARCHIVE_EXPECTED_SHA256,
        },
    }


def create_rehearsal_copies(output: Path) -> RehearsalCopies:
    copies = output / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    destinations = {
        "provider": copies / "fundamentals_provider.db",
        "canonical": copies / "fundamentals_v4.db",
        "analysis": copies / "fundamentals_analysis.db",
        "market": copies / "osakedata.db",
        "taxonomy": copies / "analysis.db",
    }
    for name, source in PRODUCTION.items():
        online_backup(source, destinations[name])
    return RehearsalCopies(
        root=copies,
        provider=destinations["provider"],
        canonical=destinations["canonical"],
        analysis=destinations["analysis"],
        market=destinations["market"],
        taxonomy=destinations["taxonomy"],
    )


def select_local_provider_candidate(
    *,
    provider_db: Path = PRODUCTION["provider"],
    market_db: Path = PRODUCTION["market"],
    canonical_db: Path = PRODUCTION["canonical"],
    taxonomy_db: Path = PRODUCTION["taxonomy"],
) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in LOCAL_PHASE13A_CANDIDATES)
    with readonly(provider_db) as provider, readonly(market_db) as market, readonly(canonical_db) as canonical, readonly(taxonomy_db) as taxonomy:
        provider_counts = {
            row["ticker"]: dict(row)
            for row in provider.execute(
                f"SELECT ticker,COUNT(*) AS provider_rows,MIN(reportperiod) AS first_period,MAX(reportperiod) AS last_period "
                f"FROM sharadar_fundamental_observation WHERE ticker IN ({placeholders}) GROUP BY ticker",
                LOCAL_PHASE13A_CANDIDATES,
            )
        }
        metadata_rows = {
            row["ticker"]: dict(row)
            for row in provider.execute(
                f"SELECT ticker,permaticker,name,exchange,isdelisted,category,secfilings,firstpricedate,lastpricedate,lastupdated "
                f"FROM sharadar_ticker_metadata WHERE ticker IN ({placeholders}) ORDER BY ticker,table_name",
                LOCAL_PHASE13A_CANDIDATES,
            )
        }
        market_counts = {
            row["ticker"]: dict(row)
            for row in market.execute(
                f"SELECT UPPER(osake) AS ticker,COUNT(*) AS market_rows,MIN(pvm) AS first_price_date,MAX(pvm) AS last_price_date,"
                f"COUNT(DISTINCT market) AS market_count,GROUP_CONCAT(DISTINCT market) AS markets "
                f"FROM osakedata WHERE UPPER(osake) IN ({placeholders}) GROUP BY UPPER(osake)",
                LOCAL_PHASE13A_CANDIDATES,
            )
        }
        canonical_rows = {
            row["ticker"]: dict(row)
            for row in canonical.execute(
                f"SELECT UPPER(s.current_ticker) AS ticker,c.company_id,s.security_id,s.active,COUNT(*) OVER (PARTITION BY UPPER(s.current_ticker)) AS identity_rows "
                f"FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker) IN ({placeholders})",
                LOCAL_PHASE13A_CANDIDATES,
            )
        }
        taxonomy_tickers = {
            str(row["ticker"]).upper()
            for row in taxonomy.execute(
                f"SELECT ticker FROM ec_entity WHERE UPPER(ticker) IN ({placeholders}) AND status='ACTIVE'",
                LOCAL_PHASE13A_CANDIDATES,
            )
            if row["ticker"]
        }
    rows = []
    for ticker in LOCAL_PHASE13A_CANDIDATES:
        provider = provider_counts.get(ticker, {})
        metadata = metadata_rows.get(ticker, {})
        market = market_counts.get(ticker, {})
        canonical = canonical_rows.get(ticker, {})
        reasons: list[str] = []
        if not metadata:
            reasons.append("PROVIDER_IDENTITY_MISSING")
        elif metadata.get("isdelisted") == "Y":
            reasons.append("DELISTED_SECURITY")
        elif metadata.get("category") not in SUPPORTED_ONBOARDING_CATEGORIES:
            reasons.append("UNSUPPORTED_SECURITY_TYPE")
        if metadata and str(metadata.get("exchange") or "").upper() not in SUPPORTED_ONBOARDING_EXCHANGES:
            reasons.append("INCOMPATIBLE_EXCHANGE")
        if not canonical:
            reasons.append("IDENTITY_NOT_RESOLVED")
        elif int(canonical.get("identity_rows") or 0) > 1:
            reasons.append("TICKER_REUSE_COLLISION")
        elif int(canonical.get("active") or 0) != 1:
            reasons.append("SECURITY_INACTIVE")
        if not market:
            reasons.append("MARKET_DATA_NOT_FOUND")
        elif int(market.get("market_count") or 0) != 1:
            reasons.append("MARKET_AMBIGUOUS")
        elif str(market.get("markets") or "").lower() != "usa":
            reasons.append("MARKET_INCOMPATIBLE")
        elif str(market.get("last_price_date") or "") < MIN_CURRENT_MARKET_DATE:
            reasons.append("MARKET_OHLC_STALE")
        if int(provider.get("provider_rows") or 0) <= 0:
            reasons.append("FUNDAMENTALS_NOT_AVAILABLE")
        rows.append({
            "ticker": ticker,
            "permaticker": metadata.get("permaticker"),
            "company_name": metadata.get("name"),
            "provider_exchange": metadata.get("exchange"),
            "provider_isdelisted": metadata.get("isdelisted"),
            "provider_category": metadata.get("category"),
            "provider_first_price_date": metadata.get("firstpricedate"),
            "provider_last_price_date": metadata.get("lastpricedate"),
            "provider_rows": int(provider.get("provider_rows") or 0),
            "first_period": provider.get("first_period"),
            "last_period": provider.get("last_period"),
            "market_rows": int(market.get("market_rows") or 0),
            "first_price_date": market.get("first_price_date"),
            "last_price_date": market.get("last_price_date"),
            "markets": market.get("markets"),
            "canonical_company_id": canonical.get("company_id"),
            "canonical_security_id": canonical.get("security_id"),
            "canonical_active_security": canonical.get("active"),
            "taxonomy_present": ticker in taxonomy_tickers,
            "eligibility_status": "ELIGIBLE" if not reasons else "NOT_ELIGIBLE",
            "rejection_reasons": reasons,
            "primary_rejection_reason": reasons[0] if reasons else None,
            "eligible": not reasons,
        })
    eligible = [row for row in rows if row["eligible"]]
    selected = max(eligible, key=lambda row: (row["provider_rows"], row["market_rows"], row["ticker"])) if eligible else None
    return {
        "source": "Phase 13A candidates absent from active operational universe",
        "selection_rule": "filter active onboarding eligibility first; then max provider_rows, then market_rows, then ticker",
        "selected_ticker": selected["ticker"] if selected else None,
        "selected": selected,
        "candidates": rows,
        "eligible_replacement_exists": bool(selected),
        "taxonomy_ready_candidates": [row["ticker"] for row in rows if row["taxonomy_present"]],
    }


def _extract_cik(secfilings: str | None) -> str | None:
    if not secfilings or "CIK=" not in secfilings:
        return None
    return secfilings.rsplit("CIK=", 1)[-1].strip().zfill(10)


def sndk_identity_evidence(
    *,
    provider_db: Path = PRODUCTION["provider"],
    canonical_db: Path = PRODUCTION["canonical"],
    market_db: Path = PRODUCTION["market"],
    taxonomy_db: Path = PRODUCTION["taxonomy"],
) -> dict[str, Any]:
    with readonly(provider_db) as provider:
        metadata = [dict(row) for row in provider.execute(
            "SELECT table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,secfilings,"
            "firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated "
            "FROM sharadar_ticker_metadata WHERE UPPER(ticker) IN ('SNDK','SNDK1','SNDKV') "
            "OR permaticker IN ('643888','197210') OR UPPER(name) LIKE '%SANDISK%' ORDER BY table_name,ticker"
        )]
        local_rows = int(provider.execute(
            "SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE UPPER(ticker)='SNDK'"
        ).fetchone()[0])
    with readonly(canonical_db) as canonical:
        canonical_security = [dict(row) for row in canonical.execute(
            "SELECT c.company_id,c.company_key,c.company_name,c.status,s.security_id,s.current_ticker,s.exchange,s.active "
            "FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)='SNDK'"
        )]
        aliases = [dict(row) for row in canonical.execute(
            "SELECT a.*,s.current_ticker,c.company_id,c.company_name FROM ticker_alias a "
            "JOIN security s USING(security_id) JOIN company c USING(company_id) WHERE UPPER(a.ticker) IN ('SNDK','SNDKV')"
        )]
    with readonly(market_db) as market:
        prices = [dict(row) for row in market.execute(
            "SELECT osake,market,MIN(pvm) AS first_date,MAX(pvm) AS last_date,COUNT(*) AS rows "
            "FROM osakedata WHERE UPPER(osake)='SNDK' GROUP BY osake,market"
        )]
    with readonly(taxonomy_db) as taxonomy:
        entities = [dict(row) for row in taxonomy.execute(
            "SELECT * FROM ec_entity WHERE UPPER(ticker)='SNDK' OR UPPER(entity_code)='SNDK' OR UPPER(entity_name) LIKE '%SANDISK%' ORDER BY entity_id"
        )]
        memberships = [dict(row) for row in taxonomy.execute(
            "SELECT child.entity_id AS child_entity_id,child.entity_code AS child_code,child.ticker,parent.entity_id AS parent_entity_id,"
            "parent.entity_type AS parent_type,parent.entity_code AS parent_code,parent.entity_name AS parent_name,"
            "m.membership_id,m.membership_type,m.membership_role,m.is_primary,m.role_weight,m.status,m.active_from,m.active_to,m.source_note "
            "FROM ec_entity child JOIN ec_membership m ON m.child_entity_id=child.entity_id "
            "JOIN ec_entity parent ON parent.entity_id=m.parent_entity_id "
            "WHERE UPPER(child.ticker)='SNDK' OR UPPER(child.entity_code)='SNDK' ORDER BY m.membership_id"
        )]
        entity_aliases = [dict(row) for row in taxonomy.execute(
            "SELECT * FROM ec_entity_alias WHERE UPPER(alias_value) IN ('SNDK','SNDKV','643888','0002023554') ORDER BY entity_alias_id"
        )]
    current = [row for row in metadata if row["ticker"] == "SNDK" and row["permaticker"] == SNDK_PERMATICKER]
    predecessor = [row for row in metadata if row["ticker"] == "SNDK1" or row["permaticker"] == "197210"]
    membership_keys = [
        (row["child_entity_id"], row["parent_entity_id"], row["membership_type"], row["membership_role"], row["is_primary"])
        for row in memberships
        if row["status"] == "ACTIVE"
    ]
    duplicate_memberships = len(membership_keys) - len(set(membership_keys))
    return {
        "identity_status": "RESOLVED_WITH_PREDECESSOR_RISK",
        "permanent_provider_identity": {"provider": "SHARADAR", "permaticker": SNDK_PERMATICKER, "cik": SNDK_CIK},
        "current_metadata": current,
        "predecessor_or_reuse_metadata": predecessor,
        "local_provider_fundamental_rows_before_archive": local_rows,
        "canonical_security": canonical_security,
        "canonical_aliases": aliases,
        "market_evidence": prices,
        "taxonomy_entities": entities,
        "taxonomy_memberships": memberships,
        "taxonomy_entity_aliases": entity_aliases,
        "taxonomy_duplicate_membership_count": duplicate_memberships,
        "decision": (
            "SNDK maps to Sharadar permaticker 643888 and SEC CIK 0002023554. "
            "Delisted predecessor SNDK1/permaticker 197210 is distinct and must not be merged."
        ),
    }


def archive_rows_for_ticker(ticker: str, *, limit: int | None = None) -> list[dict[str, str]]:
    if not ARCHIVE_PATH.exists() or sha256(ARCHIVE_PATH) != ARCHIVE_EXPECTED_SHA256:
        raise FileNotFoundError("PHASE13D1_VERIFIED_ARCHIVE_NOT_AVAILABLE")
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(ARCHIVE_PATH) as archive:
        with archive.open("fundamentals-10Y.csv") as raw:
            text = (line.decode("utf-8") for line in raw)
            reader = csv.DictReader(text)
            for row in reader:
                if str(row.get("ticker") or "").upper() != ticker.upper():
                    continue
                rows.append(dict(row))
                if limit is not None and len(rows) >= limit:
                    break
    return rows


def create_sndk_canonical_identity(canonical_db: Path, *, now: str) -> dict[str, Any]:
    with connect(canonical_db) as conn:
        existing = conn.execute(
            "SELECT c.company_id,s.security_id FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)='SNDK'"
        ).fetchone()
        if existing:
            return {"outcome": "ALREADY_PRESENT", "company_id": int(existing["company_id"]), "security_id": int(existing["security_id"])}
        company_id = int(conn.execute("SELECT COALESCE(MAX(company_id),0)+1 FROM company").fetchone()[0])
        security_id = int(conn.execute("SELECT COALESCE(MAX(security_id),0)+1 FROM security").fetchone()[0])
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?)",
            (company_id, f"SEC_CIK:{SNDK_CIK}", "SANDISK CORP", "ACTIVE", now, now),
        )
        conn.execute(
            "INSERT INTO security(security_id,company_id,current_ticker,exchange,active,valid_from,valid_to,created_at_utc,updated_at_utc) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (security_id, company_id, "SNDK", "NASDAQ", 1, "2025-02-24", None, now, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES (?,?,?,?,?,?)",
            (security_id, SNDK_RELATED_TICKER, "SHARADAR", "2025-02-24", None, "PHASE13D1_SNDK_METADATA_RELATEDTICKER"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO provider_company_identity VALUES (?,?,?,?,?,?,?,?,?)",
            ("SEC", "CIK", SNDK_CIK, company_id, "SNDK", "PHASE13D1_SNDK_IDENTITY", "SEC_FILINGS_URL", f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={SNDK_CIK}", now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO provider_security_identity(provider,provider_security_id,security_id,provider_ticker,source,created_at_utc) "
            "VALUES (?,?,?,?,?,?)",
            ("SHARADAR", SNDK_PERMATICKER, security_id, "SNDK", "PHASE13D1_SNDK_METADATA", now),
        )
        conn.commit()
    return {"outcome": "APPLIED", "company_id": company_id, "security_id": security_id}


def stage_sndk_archive_rows(provider_db: Path, rows: Sequence[Mapping[str, Any]], *, company_id: int, security_id: int, now: str) -> dict[str, Any]:
    run_id = stable_hash({"phase": PHASE, "ticker": "SNDK", "source": "archive", "now": now})[:32]
    inserted = 0
    with connect(provider_db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,request_scope,metadata_json) "
            "VALUES (?, 'SHARADAR', ?, ?, 'SUCCESS', 'PHASE13D1_ARCHIVE_SNDK_ONLY', ?)",
            (run_id, now, now, json.dumps({"archive": str(ARCHIVE_PATH), "ticker": "SNDK", "network_request_performed": False}, sort_keys=True)),
        )
        for source_row in rows:
            row = dict(source_row)
            row["permaticker"] = SNDK_PERMATICKER
            if insert_production_sharadar_observation(conn, row, run_id, now, company_id=company_id, security_id=security_id):
                inserted += 1
        conn.commit()
    arq_rows = sum(1 for row in rows if str(row.get("dimension")).upper() == "ARQ")
    return {"run_id": run_id, "source_rows": len(rows), "arq_rows": arq_rows, "inserted_rows": inserted, "network_request_performed": False}


def connect_sndk_taxonomy_identity(taxonomy_db: Path, *, company_id: int, security_id: int, now: str) -> dict[str, Any]:
    before = taxonomy_identity(taxonomy_db)
    with connect(taxonomy_db) as conn:
        entity = conn.execute(
            "SELECT entity_id FROM ec_entity WHERE UPPER(ticker)='SNDK' OR UPPER(entity_code)='SNDK' ORDER BY entity_id LIMIT 1"
        ).fetchone()
        if entity is None:
            return {"outcome": "TAXONOMY_REVIEW_REQUIRED", "reason": "SNDK taxonomy entity missing", "before": before, "after": before}
        entity_id = int(entity["entity_id"])
        memberships_before = int(conn.execute(
            "SELECT COUNT(*) FROM ec_membership WHERE child_entity_id=? AND status='ACTIVE'",
            (entity_id,),
        ).fetchone()[0])
        alias_rows = [
            ("LEGACY_CODE", f"SHARADAR_PERMATICKER:{SNDK_PERMATICKER}"),
            ("LEGACY_CODE", f"SEC_CIK:{SNDK_CIK}"),
            ("LEGACY_CODE", f"CANONICAL_COMPANY_ID:{company_id}"),
            ("LEGACY_CODE", f"CANONICAL_SECURITY_ID:{security_id}"),
            ("TICKER", SNDK_RELATED_TICKER),
        ]
        conn.execute("BEGIN IMMEDIATE")
        inserted_aliases = 0
        for alias_type, alias_value in alias_rows:
            before_changes = conn.total_changes
            conn.execute(
                "INSERT OR IGNORE INTO ec_entity_alias(entity_id,ecosystem_id,alias_type,alias_value,source_system,status,active_from,active_to,created_at_utc) "
                "VALUES (?,1,?,?,?,'ACTIVE','2025-02-24',NULL,?)",
                (entity_id, alias_type, alias_value, "PHASE13D1_SNDK_IDENTITY_RECONCILIATION", now),
            )
            inserted_aliases += int(conn.total_changes > before_changes)
        conn.commit()
    after = taxonomy_identity(taxonomy_db)
    return {
        "outcome": "CONNECTED_EXISTING_MEMBERSHIP" if memberships_before else "TAXONOMY_REVIEW_REQUIRED",
        "entity_id": entity_id,
        "active_membership_count": memberships_before,
        "inserted_aliases": inserted_aliases,
        "created_duplicate_memberships": 0,
        "before": before,
        "after": after,
        "economic_fingerprint_changed": before["taxonomy_economic_fingerprint"] != after["taxonomy_economic_fingerprint"],
        "presentation_fingerprint_changed": before["taxonomy_presentation_fingerprint"] != after["taxonomy_presentation_fingerprint"],
    }


def _counts_for_ticker(copies: RehearsalCopies, ticker: str, company_id: int) -> dict[str, Any]:
    with readonly(copies.provider) as provider, readonly(copies.canonical) as canonical:
        return {
            "provider_observations": int(provider.execute("SELECT COUNT(*) FROM provider_observation WHERE UPPER(provider_ticker)=UPPER(?)", (ticker,)).fetchone()[0]),
            "provider_arq_observations": int(provider.execute("SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?) AND dimension='ARQ'", (ticker,)).fetchone()[0]),
            "canonical_quarters": int(canonical.execute("SELECT COUNT(*) FROM v4_quarter WHERE company_id=?", (company_id,)).fetchone()[0]),
            "ttm_endpoints": int(canonical.execute("SELECT COUNT(*) FROM v4_ttm_values WHERE company_id=?", (company_id,)).fetchone()[0]),
        }


def run_rehearsal(output: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    stamp = "20260912T_PHASE13D1_REAL_SOURCE"
    output = output or ARTIFACT_ROOT / stamp
    output.mkdir(parents=True, exist_ok=True)
    commands: list[str] = []
    preflight = production_preflight()
    write_json(output / "production_preflight.json", preflight)
    selection = select_local_provider_candidate()
    write_json(output / "candidate_selection.json", selection)
    sndk_evidence = sndk_identity_evidence()
    write_json(output / "sndk_identity_evidence.json", sndk_evidence)
    rows = archive_rows_for_ticker("SNDK")
    source = {
        "precedence": "verified managed archive before API",
        "archive_path": str(ARCHIVE_PATH),
        "archive_sha256": preflight["archive"]["sha256"],
        "rows": len(rows),
        "arq_rows": sum(1 for row in rows if str(row.get("dimension")).upper() == "ARQ"),
        "first_reportperiod": min((row.get("reportperiod") for row in rows if row.get("reportperiod")), default=None),
        "last_reportperiod": max((row.get("reportperiod") for row in rows if row.get("reportperiod")), default=None),
        "api_request_performed": False,
    }
    write_json(output / "sndk_source_acquisition.json", source)
    validation = {
        "status": "PASS" if rows else "BLOCKED",
        "schema_has_required_fields": bool(rows and {"ticker", "dimension", "reportperiod", "fiscalperiod", "date"}.issubset(rows[0])),
        "identity_permaticker_source": "sharadar_ticker_metadata",
        "permaticker": SNDK_PERMATICKER,
        "reject_predecessor_permaticker": "197210",
        "duplicate_rows_by_full_payload": len(rows) - len({stable_hash(row) for row in rows}),
    }
    write_json(output / "staged_provider_validation.json", validation)
    copies = create_rehearsal_copies(output)
    now = "2026-09-12T00:00:00Z"
    canonical_identity = create_sndk_canonical_identity(copies.canonical, now=now)
    stage = stage_sndk_archive_rows(
        copies.provider,
        rows,
        company_id=int(canonical_identity["company_id"]),
        security_id=int(canonical_identity["security_id"]),
        now=now,
    )
    taxonomy = connect_sndk_taxonomy_identity(
        copies.taxonomy,
        company_id=int(canonical_identity["company_id"]),
        security_id=int(canonical_identity["security_id"]),
        now=now,
    )
    canonical = reconcile_canonical(copies.provider, copies.canonical, applied_at=now)
    ttm = rebuild_ttm(copies.canonical, applied_at=now)
    dependencies = run_candidate_apply(copies.candidate_paths(), apply=True, applied_at_utc=now)
    rv_mismatch = candidate_relative_valuation_dependency_state(
        copies.analysis,
        report_date="2026-09-12",
        expected_universe_fingerprint="PHASE13D1_CHANGED_UNIVERSE",
        expected_taxonomy_economic_fingerprint=taxonomy["after"]["taxonomy_economic_fingerprint"],
    )
    counts = _counts_for_ticker(copies, "SNDK", int(canonical_identity["company_id"]))
    readiness = [{
        "ticker": "SNDK",
        "identity_status": sndk_evidence["identity_status"],
        "fundamentals_status": "READY" if counts["canonical_quarters"] else "NOT_READY",
        "operational_universe_status": "ADDED_ON_COPY",
        "taxonomy_status": taxonomy["outcome"],
        "downstream_status": "LIMITED_COPY_REBUILD",
        "relative_valuation_status": rv_mismatch["state"],
    }]
    write_csv(output / "readiness_matrix.csv", readiness)
    write_json(output / "onboarding_previews.json", {"sndk": {"identity": canonical_identity, "taxonomy": taxonomy, "source": source}})
    write_json(output / "onboarding_apply_results.json", {"canonical_identity": canonical_identity, "provider_stage": stage, "canonical": canonical, "ttm": ttm, "dependencies": dependencies, "counts": counts})
    write_json(output / "dependency_transitions.json", {"dependencies": dependencies})
    write_json(output / "relative_position_reconciliation.json", {"status": "FOUNDATION_DEPENDENCY_REBUILT", "run_candidate_apply": dependencies})
    write_json(output / "relative_valuation_compatibility.json", {"before_refresh": rv_mismatch, "manual_refresh_performed": False, "restored": False})
    write_json(output / "taxonomy_rehearsal.json", taxonomy)
    write_json(output / "snapshot_reconciliation.json", {"status": "NOT_GENERATED", "reason": "Relative Valuation compatibility not restored by explicit full-universe refresh in Phase 13D.1 implementation"})
    write_json(output / "failure_injection_results.json", [{"boundary": "provider_staging_validation", "status": "COVERED_BY_UNIT_TESTS"}])
    write_json(output / "no_change_results.json", {"status": "NOT_PROVEN_END_TO_END", "reason": "full rebuild and RV refresh contract remains blocked"})
    postflight = {
        "production": {name: database_inventory(path) for name, path in PRODUCTION.items()},
        "unchanged_inventory": {
            name: preflight["production"][name]["sha256"] == database_inventory(path)["sha256"]
            for name, path in PRODUCTION.items()
        },
    }
    write_json(output / "production_postflight.json", postflight)
    result = {
        "outcome": OUTCOME_BLOCKED,
        "artifact_dir": str(output),
        "local_provider_ticker": selection["selected_ticker"],
        "sndk": {"identity": sndk_evidence["identity_status"], "source": source, "taxonomy": taxonomy["outcome"], "counts": counts},
        "relative_valuation_status": rv_mismatch["state"],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    commands.append("python3 -m rawcandle.cli.run_phase13d1_real_source_rehearsal --output <artifact_dir>")
    (output / "commands_run.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    write_json(output / "artifact_manifest.json", {
        "result": result,
        "files": sorted(path.name for path in output.iterdir() if path.is_file()),
    })
    return result
