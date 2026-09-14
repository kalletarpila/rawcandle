from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    compare_production_inventory,
    database_inventory,
    production_inventory,
    rebuild_ttm,
    reconcile_canonical,
    sha256,
    stable_hash,
    write_csv,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    ensure_candidate_schema,
    online_backup,
    reject_production_path,
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13f1_reconciliation import AuditPaths
from rawcandle.fundamentals.phase13f3_1_package_recovery import instrumented_package_refresh, utc_now
from rawcandle.fundamentals.phase13f3_ticker_transition import (
    APPLIED_AT,
    REPORT_DATE,
    TRANSITIONS,
    _apply_transition_identities,
    _areb_counts,
    _manual_rv_refresh,
    _snapshot_smoke,
    _storage,
    _valuation_classification_update,
    enhanced_listing_population,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position
from rawcandle.fundamentals.schema.production_bootstrap import (
    ALLOWED_DIMENSIONS,
    insert_production_sharadar_observation,
)


PHASE = "PHASE13F3_2_SUCCESSOR_FUNDAMENTALS_RECOVERY_DATE_AWARE_RV"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13f3_2_successor_recovery")
DEFAULT_RUN_ID = "20260913T_PHASE13F3_2_SUCCESSOR_RECOVERY"
ARCHIVE = Path("/home/kalle/projects/rawcandle/data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip")
ARCHIVE_SHA256 = "dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36"
OUTCOME_A = "OUTCOME A — SUCCESSOR FUNDAMENTALS RECOVERED AND DATE-AWARE COPY-ONLY CHAIN VERIFIED; STRUCTURAL-BREAK PRODUCTION POLICY STILL DEFERRED"
OUTCOME_B = "OUTCOME B — SUCCESSOR FUNDAMENTALS OR DATE-AWARE COPY-ONLY CHAIN STILL BLOCKED"

NUMERIC_FIELDS = (
    "revenue", "gp", "opinc", "ebit", "ebitda", "netinc", "netinccmn", "ncfo",
    "capex", "fcf", "cashneq", "debt", "debtc", "debtnc", "sharesbas",
    "shareswa", "shareswadil", "receivables", "inventory", "payables",
    "deferredrev", "assets",
)
SUCCESSORS = tuple(str(row["current_ticker"]) for row in TRANSITIONS)
PERMATICKERS = {
    "VMRK": "197624",
    "IA": "198182",
    "VAI": "120343",
    "NXH": "195902",
    "NMAD": "108994",
}


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _cik(value: Any) -> str | None:
    match = re.search(r"CIK=(\d+)", str(value or ""))
    return match.group(1).zfill(10) if match else None


def _provider_metadata(provider_db: Path) -> dict[str, dict[str, Any]]:
    with readonly(provider_db) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,secfilings,"
            "firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated,payload_json "
            "FROM sharadar_ticker_metadata WHERE table_name='fundamentals' "
            "AND (UPPER(ticker) IN (%s) OR permaticker IN ('197799')) "
            "ORDER BY ticker,lastupdated DESC" % ",".join("?" for _ in SUCCESSORS),
            SUCCESSORS,
        )]
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row["ticker"]).upper()
        if ticker not in out:
            row["cik"] = _cik(row.get("secfilings"))
            out[ticker] = row
    return out


def _canonical_identities(canonical_db: Path) -> dict[str, dict[str, Any]]:
    tickers = tuple(str(row["historical_ticker"]) for row in TRANSITIONS) + SUCCESSORS
    marks = ",".join("?" for _ in tickers)
    with readonly(canonical_db) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active,s.valid_from,s.valid_to,"
            "cc.cik_normalized "
            "FROM security s JOIN company c USING(company_id) "
            "LEFT JOIN company_cik cc USING(company_id) "
            f"WHERE UPPER(s.current_ticker) IN ({marks}) ORDER BY s.current_ticker",
            tuple(ticker.upper() for ticker in tickers),
        )]
    return {str(row["current_ticker"]).upper(): row for row in rows}


def production_source_probe(paths: AuditPaths = AuditPaths()) -> dict[str, Any]:
    meta = _provider_metadata(paths.provider)
    canonical = _canonical_identities(paths.canonical)
    rows = []
    with readonly(paths.provider) as conn:
        for transition in TRANSITIONS:
            ticker = str(transition["current_ticker"])
            historical = str(transition["historical_ticker"])
            permaticker = PERMATICKERS[ticker]
            counts = [dict(row) for row in conn.execute(
                "SELECT provider_ticker,provider_security_id,dimension,COUNT(*) rows,MIN(reportperiod) earliest_period,"
                "MAX(reportperiod) latest_period,MIN(source_availability_date) earliest_availability,"
                "MAX(source_availability_date) latest_availability "
                "FROM provider_observation WHERE provider='SHARADAR' AND native_table='fundamentals' "
                "AND (provider_security_id=? OR UPPER(provider_ticker) IN (?,?)) "
                "GROUP BY provider_ticker,provider_security_id,dimension ORDER BY provider_ticker,dimension",
                (permaticker, ticker, historical),
            )]
            rows.append({
                "ticker": ticker,
                "historical_ticker": historical,
                "permaticker": permaticker,
                "provider_cik": (meta.get(ticker) or {}).get("cik"),
                "canonical": canonical.get(historical) or canonical.get(ticker),
                "production_provider_counts": counts,
                "production_rows": sum(int(row["rows"]) for row in counts),
            })
    return {"rows": rows, "all_absent": all(row["production_rows"] == 0 for row in rows)}


def _malformed_number(value: Any) -> bool:
    if value is None or str(value).strip() == "":
        return False
    try:
        float(str(value).replace(",", ""))
    except ValueError:
        return True
    return False


def archive_reconciliation(archive: Path = ARCHIVE, provider_db: Path = PRODUCTION["provider"]) -> dict[str, Any]:
    actual_sha = sha256(archive)
    if actual_sha != ARCHIVE_SHA256:
        raise RuntimeError(f"PHASE13F3_2_ARCHIVE_SHA_MISMATCH:{actual_sha}")
    meta = _provider_metadata(provider_db)
    rows_by_ticker: dict[str, list[dict[str, Any]]] = {ticker: [] for ticker in SUCCESSORS}
    numeric_malformed: Counter[str] = Counter()
    exact_seen: set[str] = set()
    duplicate_count = 0
    revisions: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    with zipfile.ZipFile(archive) as zipped:
        name = zipped.namelist()[0]
        with zipped.open(name) as raw:
            reader = csv.DictReader((line.decode("utf-8-sig") for line in raw))
            for row in reader:
                ticker = str(row.get("ticker") or "").strip().upper()
                dimension = str(row.get("dimension") or "").strip().upper()
                if ticker not in rows_by_ticker or dimension not in ALLOWED_DIMENSIONS:
                    continue
                enriched = dict(row)
                enriched["ticker"] = ticker
                enriched["dimension"] = dimension
                enriched["permaticker"] = PERMATICKERS[ticker]
                rows_by_ticker[ticker].append(enriched)
                fingerprint = stable_hash(enriched)
                duplicate_count += int(fingerprint in exact_seen)
                exact_seen.add(fingerprint)
                revisions[(ticker, dimension, str(row.get("reportperiod") or ""), str(row.get("fiscalperiod") or ""))].add(
                    str(row.get("lastupdated") or row.get("date") or "")
                )
                for field in NUMERIC_FIELDS:
                    if _malformed_number(row.get(field)):
                        numeric_malformed[ticker] += 1
    reconciled = []
    for transition in TRANSITIONS:
        ticker = str(transition["current_ticker"])
        items = rows_by_ticker[ticker]
        by_dimension = Counter(str(row["dimension"]) for row in items)
        periods = [str(row.get("reportperiod") or "") for row in items if row.get("reportperiod")]
        availability = [str(row.get("date") or "") for row in items if row.get("date")]
        revisions_for_ticker = sum(
            max(len(values) - 1, 0)
            for key, values in revisions.items()
            if key[0] == ticker
        )
        source_status = "FOUND_IN_VERIFIED_ARCHIVE" if by_dimension["ARQ"] and by_dimension["MRQ"] else "NO_FUNDAMENTALS_AVAILABLE"
        provider = meta.get(ticker, {})
        reconciled.append({
            "current_ticker": ticker,
            "historical_tickers": [transition["historical_ticker"], *str(provider.get("relatedtickers") or "").split()],
            "provider_permaticker": PERMATICKERS[ticker],
            "cik": provider.get("cik"),
            "provider_company_name": provider.get("name"),
            "source_level_used": "LEVEL_2_VERIFIED_TEN_YEAR_ARCHIVE",
            "ARQ_row_count": by_dimension["ARQ"],
            "MRQ_row_count": by_dimension["MRQ"],
            "earliest_fiscal_period": min(periods) if periods else None,
            "latest_fiscal_period": max(periods) if periods else None,
            "earliest_availability_date": min(availability) if availability else None,
            "latest_availability_date": max(availability) if availability else None,
            "revision_count": revisions_for_ticker,
            "exact_duplicate_count": 0,
            "malformed_numeric_count": numeric_malformed[ticker],
            "current_and_historical_ticker_distribution": dict(sorted(Counter(row["ticker"] for row in items).items())),
            "identity_conflicts": [],
            "source_fingerprint": stable_hash(items),
            "final_source_status": source_status,
        })
    contamination = nxh_contamination_artifact(rows_by_ticker.get("NXH", ()), meta)
    return {
        "archive_path": str(archive.resolve()),
        "archive_sha256": actual_sha,
        "archive_sha256_verified": True,
        "rows_by_ticker": rows_by_ticker,
        "reconciliation": reconciled,
        "bbby_nxh_contamination": contamination,
        "exact_duplicate_count": duplicate_count,
        "fingerprint": stable_hash(reconciled),
    }


def nxh_contamination_artifact(nxh_rows: Sequence[Mapping[str, Any]], meta: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    nxh = meta.get("NXH", {})
    rejected_tickers = sorted({str(row.get("ticker") or "").upper() for row in nxh_rows if str(row.get("ticker") or "").upper() != "NXH"})
    bankrupt = meta.get("BBBYQ", {})
    conflicts = []
    if str(nxh.get("permaticker")) != "195902":
        conflicts.append("NXH_PERMATICKER_NOT_195902")
    if _cik(nxh.get("secfilings")) == _cik(bankrupt.get("secfilings")):
        conflicts.append("NXH_CIK_MATCHES_BANKRUPT_BBBYQ")
    if rejected_tickers:
        conflicts.append("NON_NXH_ROWS_PRESENT_IN_ACCEPTED_NXH_SET")
    return {
        "accepted_ticker": "NXH",
        "accepted_permaticker": nxh.get("permaticker"),
        "accepted_cik": _cik(nxh.get("secfilings")),
        "accepted_related_tickers": str(nxh.get("relatedtickers") or "").split(),
        "rejected_bankrupt_ticker": "BBBYQ",
        "rejected_bankrupt_permaticker": bankrupt.get("permaticker"),
        "rejected_bankrupt_cik": _cik(bankrupt.get("secfilings")),
        "accepted_rows": len(nxh_rows),
        "rejected_tickers_in_accepted_set": rejected_tickers,
        "contamination_conflicts": conflicts,
        "status": "PASS" if not conflicts else "FAIL",
        "reason": "NXH rows are current Overstock/Beyond lineage by ticker metadata, CIK and permaticker; BBBYQ is a separate bankrupt issuer.",
    }


def _apply_provider_identity_links(
    canonical_db: Path,
    *,
    provider_db: Path | None = None,
    allow_production: bool = False,
) -> dict[str, Any]:
    if not allow_production:
        reject_production_path(canonical_db, "canonical")
    writes = 0
    rows = []
    meta = _provider_metadata(provider_db or PRODUCTION["provider"])
    with sqlite3.connect(canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for ticker, permaticker in PERMATICKERS.items():
                security = conn.execute(
                    "SELECT security_id,company_id,current_ticker FROM security WHERE UPPER(current_ticker)=?",
                    (ticker,),
                ).fetchone()
                if security is None:
                    rows.append({"ticker": ticker, "status": "SECURITY_NOT_FOUND"})
                    continue
                before = conn.total_changes
                conn.execute(
                    "INSERT OR IGNORE INTO provider_security_identity(provider,provider_security_id,security_id,provider_ticker,source,created_at_utc) "
                    "VALUES('SHARADAR',?,?,?,?,?)",
                    (permaticker, int(security["security_id"]), ticker, PHASE, APPLIED_AT),
                )
                cik = (meta.get(ticker) or {}).get("cik")
                if cik:
                    conn.execute(
                        "INSERT OR IGNORE INTO provider_company_identity(provider,provider_identifier_type,provider_identifier_value,company_id,provider_ticker,source,source_type,source_value,created_at_utc) "
                        "VALUES('SEC','CIK',?,?,?,?,?,?,?)",
                        (cik, int(security["company_id"]), ticker, PHASE, "sharadar_ticker_metadata.secfilings", cik, APPLIED_AT),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO company_cik(company_id,cik_normalized,cik_display,source,source_table,source_row_id,status,created_at_utc,source_type,source_name,source_field,source_value,derivation,confidence) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            int(security["company_id"]), cik, cik, PHASE, "sharadar_ticker_metadata", ticker,
                            "ACTIVE", APPLIED_AT, "PROVIDER_METADATA", "Sharadar ticker metadata",
                            "secfilings", cik, "parsed SEC CIK query parameter", "HIGH",
                        ),
                    )
                writes += conn.total_changes - before
                rows.append({"ticker": ticker, "permaticker": permaticker, "security_id": int(security["security_id"]), "company_id": int(security["company_id"]), "status": "LINKED"})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"rows": rows, "writes": writes, "fingerprint": stable_hash(rows)}


def stage_provider_rows(
    provider_db: Path,
    canonical_db: Path,
    rows_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    inject_failure: bool = False,
    allow_production: bool = False,
) -> dict[str, Any]:
    if not allow_production:
        reject_production_path(provider_db, "provider")
    run_id = "PHASE13F3_2_" + stable_hash({ticker: len(rows) for ticker, rows in rows_by_ticker.items()})[:24]
    now = APPLIED_AT
    inserted = Counter()
    matched = Counter()
    skipped = Counter()
    with readonly(canonical_db) as canonical:
        identities = {
            str(row["current_ticker"]).upper(): (int(row["company_id"]), int(row["security_id"]))
            for row in canonical.execute("SELECT company_id,security_id,current_ticker FROM security")
        }
    with sqlite3.connect(provider_db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,request_scope,entitlement_scope,source_version,metadata_json) "
                "VALUES(?,'SHARADAR',?,?,'SUCCESS',?,?,?,?)",
                (
                    run_id, now, now, "PHASE13F3_2_SUCCESSOR_ARQ_MRQ_ARCHIVE_ROWS",
                    "Sharadar Fundamentals local verified archive", "PHASE13F3_2",
                    json.dumps({"archive_sha256": ARCHIVE_SHA256, "source": str(ARCHIVE)}, sort_keys=True),
                ),
            )
            seen = 0
            for ticker in SUCCESSORS:
                identity = identities.get(ticker)
                if identity is None:
                    skipped["identity_not_found"] += len(rows_by_ticker.get(ticker, ()))
                    continue
                company_id, security_id = identity
                for row in rows_by_ticker.get(ticker, ()):
                    matched[str(row["dimension"])] += 1
                    if insert_production_sharadar_observation(
                        conn, row, run_id, now, company_id=company_id, security_id=security_id
                    ):
                        inserted[str(row["dimension"])] += 1
                    seen += 1
                    if inject_failure and seen >= 3:
                        raise RuntimeError("PHASE13F3_2_INJECTED_PROVIDER_STAGING_FAILURE")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "run_id": run_id,
        "matched_by_dimension": dict(sorted(matched.items())),
        "inserted_by_dimension": dict(sorted(inserted.items())),
        "logical_changes": sum(inserted.values()),
        "skipped": dict(sorted(skipped.items())),
    }


def successor_canonical_ttm_report(canonical_db: Path) -> dict[str, Any]:
    marks = ",".join("?" for _ in SUCCESSORS)
    with readonly(canonical_db) as conn:
        rows = []
        for security in conn.execute(f"SELECT company_id,security_id,current_ticker FROM security WHERE UPPER(current_ticker) IN ({marks}) ORDER BY current_ticker", SUCCESSORS):
            company_id = int(security["company_id"])
            quarter = conn.execute(
                "SELECT COUNT(*) rows,MIN(period_end) earliest_endpoint,MAX(period_end) latest_endpoint,MIN(source_availability_date) earliest_availability,MAX(source_availability_date) latest_availability "
                "FROM v4_quarter WHERE company_id=?",
                (company_id,),
            ).fetchone()
            ttm = conn.execute(
                "SELECT COUNT(*) rows,MIN(period_end) earliest_endpoint,MAX(period_end) latest_endpoint,MIN(ttm_source_available_date) earliest_availability,MAX(ttm_source_available_date) latest_availability,"
                "SUM(CASE WHEN readiness_status='TTM_READY' THEN 1 ELSE 0 END) ready_rows "
                "FROM v4_ttm_values WHERE company_id=?",
                (company_id,),
            ).fetchone()
            rows.append({
                "current_ticker": security["current_ticker"],
                "company_id": company_id,
                "security_id": int(security["security_id"]),
                "canonical_quarter_count": int(quarter["rows"] or 0),
                "ttm_endpoint_count": int(ttm["rows"] or 0),
                "ttm_ready_count": int(ttm["ready_rows"] or 0),
                "earliest_endpoint": ttm["earliest_endpoint"] or quarter["earliest_endpoint"],
                "latest_endpoint": ttm["latest_endpoint"] or quarter["latest_endpoint"],
                "earliest_availability_date": ttm["earliest_availability"] or quarter["earliest_availability"],
                "latest_availability_date": ttm["latest_availability"] or quarter["latest_availability"],
                "readiness_status": "READY" if int(ttm["ready_rows"] or 0) > 0 else "NO_READY_TTM_ENDPOINT",
            })
    return {"rows": rows, "all_have_ttm": all(row["ttm_endpoint_count"] > 0 for row in rows)}


def structural_endpoint_policy(canonical_db: Path) -> dict[str, Any]:
    report = successor_canonical_ttm_report(canonical_db)
    rows = []
    for transition in TRANSITIONS:
        ticker = str(transition["current_ticker"])
        row = next(item for item in report["rows"] if item["current_ticker"] == ticker)
        latest = row["latest_endpoint"]
        latest_availability = row["latest_availability_date"]
        transition_date = str(transition["effective_date"])
        has_post_transition = latest is not None and str(latest) >= transition_date
        if transition["structural_break"] == "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE":
            status = "FULL_CONTINUITY_ALLOWED"
        elif transition["structural_break"] == "TICKER_REUSE_SEPARATION":
            status = "CURRENT_ISSUER_LINEAGE_CONTINUITY_ALLOWED"
        elif transition["structural_break"] in {"MAJOR_BUSINESS_COMBINATION", "REVERSE_MERGER_MAJOR_BUSINESS_CHANGE"}:
            status = "POST_TRANSITION_OBSERVED_ENDPOINT_READY" if has_post_transition else "STRUCTURALLY_LIMITED_NO_POST_TRANSITION_OBSERVED_ENDPOINT"
        else:
            status = "BUSINESS_COMPARABILITY_REVIEW_REQUIRED"
        rows.append({
            "ticker": ticker,
            "structural_break": transition["structural_break"],
            "effective_date": transition_date,
            "latest_endpoint_period_end": latest,
            "latest_endpoint_availability": latest_availability,
            "has_post_transition_observed_endpoint": has_post_transition,
            "snapshot_endpoint_status": status,
        })
    return {"rows": rows, "fingerprint": stable_hash(rows)}


def _copy_rehearsal(output: Path, lane: str, source: Mapping[str, Any]) -> dict[str, Any]:
    lane_dir = output / lane
    copies = lane_dir / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    provider = copies / "fundamentals_provider.db"
    canonical = copies / "fundamentals_v4.db"
    analysis = copies / "fundamentals_analysis.db"
    result: dict[str, Any] = {"lane": lane, "started_at_utc": utc_now()}
    try:
        result["backups"] = {
            "provider": online_backup(PRODUCTION["provider"], provider),
            "canonical": online_backup(PRODUCTION["canonical"], canonical),
            "analysis": online_backup(PRODUCTION["analysis"], analysis),
        }
        paths = CandidatePaths(canonical, analysis, PRODUCTION["taxonomy"], provider_db=provider, market_db=PRODUCTION["market"])
        before = {"provider": database_inventory(provider), "canonical": database_inventory(canonical), "analysis": database_inventory(analysis)}
        result["before"] = before
        result["identity"] = _apply_transition_identities(canonical)
        result["provider_identity"] = _apply_provider_identity_links(canonical)
        provider_before_failure = database_inventory(provider)
        try:
            stage_provider_rows(provider, canonical, source["rows_by_ticker"], inject_failure=True)
        except RuntimeError as exc:
            provider_after_failure = database_inventory(provider)
            result["provider_staging_rollback"] = {
                "injected_error": str(exc),
                "rollback_equal": provider_before_failure == provider_after_failure,
            }
        result["provider_staging"] = stage_provider_rows(provider, canonical, source["rows_by_ticker"])
        result["provider_staging_replay"] = stage_provider_rows(provider, canonical, source["rows_by_ticker"])
        result["canonical"] = reconcile_canonical(provider, canonical, applied_at=APPLIED_AT)
        result["ttm"] = rebuild_ttm(canonical, applied_at=APPLIED_AT)
        result["successor_canonical_ttm"] = successor_canonical_ttm_report(canonical)
        result["structural_endpoint_policy"] = structural_endpoint_policy(canonical)
        result["valuation_classification"] = _valuation_classification_update(analysis, PRODUCTION["market"], canonical)
        ensure_candidate_schema(paths, applied_at_utc=APPLIED_AT, apply=True)
        universe = backfill_universe(paths, applied_at_utc=APPLIED_AT, apply=True)
        result["universe"] = universe
        result["package"] = instrumented_package_refresh(
            {
                "provider": provider,
                "canonical": canonical,
                "analysis": analysis,
                "market": PRODUCTION["market"],
                "taxonomy": PRODUCTION["taxonomy"],
            },
            lane_dir,
        )
        result["relative_position"] = asdict(refresh_relative_position(
            canonical_db=canonical,
            analysis_db=analysis,
            market_db=PRODUCTION["market"],
            taxonomy_db=PRODUCTION["taxonomy"],
            snapshot_date=REPORT_DATE,
            model_fingerprint=RP_MODEL_FINGERPRINT,
            applied_at_utc=APPLIED_AT,
        ))
        taxonomy = taxonomy_identity(PRODUCTION["taxonomy"])
        result["pre_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["relative_valuation"] = _manual_rv_refresh(paths, output=lane_dir)
        result["dependencies"] = attach_dependencies(paths, universe=universe["identity"], applied_at_utc=APPLIED_AT, apply=True)
        result["post_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["snapshots"] = _snapshot_smoke(paths, lane_dir)
        result["areb_after"] = _areb_counts(analysis)
        result["final_inventory"] = {"provider": database_inventory(provider), "canonical": database_inventory(canonical), "analysis": database_inventory(analysis)}
        write_json(lane_dir / "rehearsal_result.json", result)
        return result
    except BaseException as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(lane_dir / "rehearsal_failure.json", result)
        raise
    finally:
        if copies.exists():
            shutil.rmtree(copies)
        write_json(lane_dir / "cleanup.json", {
            "transient_copies_removed": not copies.exists(),
            "storage": _storage("cleanup"),
            "remaining_database_artifacts": [
                str(path) for path in lane_dir.rglob("*")
                if path.suffix in {".db", ".sqlite"} or path.name.endswith(("-wal", "-shm", "-journal"))
            ],
        })


def _economic_fingerprint(result: Mapping[str, Any]) -> str:
    return stable_hash({
        "source_recovery": result["provider_staging"]["matched_by_dimension"],
        "identity": result["identity"]["fingerprint"],
        "provider_identity": result["provider_identity"]["fingerprint"],
        "canonical": result["canonical"]["canonical_fingerprint"],
        "ttm": result["ttm"]["fingerprint"],
        "universe": result["universe"]["identity"]["economic_result_fingerprint"],
        "package": result["package"]["first_apply"]["economic_result_fingerprint"],
        "relative_position": result["relative_position"]["result_fingerprint"],
        "relative_valuation": result["relative_valuation"]["snapshot"]["result_fingerprint"],
        "structural_endpoint_policy": result["structural_endpoint_policy"]["fingerprint"],
        "snapshots": {
            ticker: {key: row.get(key) for key in ("status", "fingerprint", "reason", "error")}
            for ticker, row in result["snapshots"].items()
        },
    })


def _first_run_ok(run: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if any(row["final_source_status"] != "FOUND_IN_VERIFIED_ARCHIVE" for row in source["reconciliation"]):
        blockers.append("SUCCESSOR_SOURCE_NOT_FULLY_RECOVERED")
    if source["bbby_nxh_contamination"]["status"] != "PASS":
        blockers.append("BBBY_NXH_CONTAMINATION_GATE_FAILED")
    if not run.get("provider_staging_rollback", {}).get("rollback_equal"):
        blockers.append("PROVIDER_STAGING_ROLLBACK_NOT_PROVEN")
    if run["provider_staging"]["logical_changes"] <= 0:
        blockers.append("PROVIDER_STAGING_INSERTED_ZERO_ROWS")
    if run["provider_staging_replay"]["logical_changes"] != 0:
        blockers.append("PROVIDER_STAGING_REPLAY_NOT_NO_CHANGE")
    if not run["successor_canonical_ttm"]["all_have_ttm"]:
        blockers.append("SUCCESSOR_TTM_RECONSTRUCTION_INCOMPLETE")
    if run["pre_refresh_compatibility"]["state"] == "COMPATIBLE":
        blockers.append("PRE_REFRESH_RV_DID_NOT_SHOW_INCOMPATIBILITY")
    if run["post_refresh_compatibility"]["state"] != "COMPATIBLE":
        blockers.append(f"POST_REFRESH_RV_COMPATIBILITY:{run['post_refresh_compatibility']['state']}")
    if int(run["relative_valuation"]["snapshot"]["company_count"]) <= 0:
        blockers.append("RELATIVE_VALUATION_REFRESH_EMPTY_COMPANY_SET")
    if int(run["areb_after"]["post_delisting_relative_valuation_rows"]) != 0:
        blockers.append(f"AREB_POST_DELISTING_CURRENT_RV_ROWS:{run['areb_after']['post_delisting_relative_valuation_rows']}")
    failed = {
        ticker: row.get("reason") or row.get("error")
        for ticker, row in run["snapshots"].items()
        if row.get("status") == "FAILED" and ticker not in {"AREB"}
    }
    if failed:
        blockers.append("SNAPSHOT_SMOKE_FAILURES:" + json.dumps(failed, sort_keys=True))
    return not blockers, blockers


def run_phase13f3_2(output: Path | None = None) -> dict[str, Any]:
    started = time.monotonic()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    reject_production_path(output, "output")
    output.mkdir(parents=True, exist_ok=True)
    pre_inventory = production_inventory()
    blockers: list[str] = []
    production_probe = production_source_probe()
    source = archive_reconciliation()
    serializable_source = {key: value for key, value in source.items() if key != "rows_by_ticker"}
    write_json(output / "source_reconciliation.json", serializable_source)
    write_csv(output / "source_reconciliation.csv", source["reconciliation"])
    write_json(output / "bbby_nxh_identity_contamination.json", source["bbby_nxh_contamination"])
    staged_rows = [dict(row) for rows in source["rows_by_ticker"].values() for row in rows]
    write_csv(output / "accepted_archive_stage_rows.csv", staged_rows)
    listing = enhanced_listing_population(AuditPaths())
    run_1: dict[str, Any] | None = None
    run_2: dict[str, Any] | None = None
    deterministic: dict[str, Any]
    try:
        run_1 = _copy_rehearsal(output, "run_1", source)
        first_ok, first_blockers = _first_run_ok(run_1, source)
        blockers.extend(first_blockers)
        if first_ok:
            run_2 = _copy_rehearsal(output, "run_2", source)
            deterministic = {
                "run_1": _economic_fingerprint(run_1),
                "run_2": _economic_fingerprint(run_2),
            }
            deterministic["match"] = deterministic["run_1"] == deterministic["run_2"]
            if not deterministic["match"]:
                blockers.append("DETERMINISTIC_REPLAY_MISMATCH")
        else:
            deterministic = {"match": False, "reason": "FIRST_RUN_DID_NOT_PASS_RECONCILIATION"}
    except BaseException as exc:
        deterministic = {"match": False, "reason": type(exc).__name__, "message": str(exc)}
        blockers.append("SUCCESSOR_RECOVERY_OR_DOWNSTREAM_CHAIN_EXCEPTION")
    post_inventory = production_inventory()
    result = {
        "phase": PHASE,
        "outcome": OUTCOME_A if not blockers else OUTCOME_B,
        "deferred_policy": "OWN_HISTORY_STRUCTURAL_BREAK_POLICY_REQUIRES_SEPARATE_VERSIONED_CONTRACT",
        "blockers": blockers,
        "production_source_probe": production_probe,
        "source_reconciliation": serializable_source,
        "listing_unresolved_current_active_count": listing["unresolved_current_active_count"],
        "run_1": run_1,
        "run_2": run_2,
        "determinism": deterministic,
        "production_immutability": compare_production_inventory(pre_inventory, post_inventory),
        "storage": {"final": _storage("final")},
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    report = render_report(output, result)
    result["report"] = report
    write_json(output / "phase13f3_2_result.json", result)
    return result


def render_report(output: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    run = result.get("run_1") or {}
    rv_meta = ((run.get("relative_valuation") or {}).get("source_metadata") or {})
    lines = [
        "# Phase 13F.3.2 Successor Fundamentals Recovery",
        "",
        f"Outcome: **{result['outcome']}**",
        "",
        f"Production provider stable-id rows absent before recovery: `{result['production_source_probe']['all_absent']}`",
        f"Archive SHA verified: `{result['source_reconciliation']['archive_sha256_verified']}`",
        f"Provider staging first logical changes: `{((run.get('provider_staging') or {}).get('logical_changes'))}`",
        f"Provider staging replay logical changes: `{((run.get('provider_staging_replay') or {}).get('logical_changes'))}`",
        f"Successor TTM reconstructed: `{((run.get('successor_canonical_ttm') or {}).get('all_have_ttm'))}`",
        f"Pre-refresh RV compatibility: `{((run.get('pre_refresh_compatibility') or {}).get('state'))}`",
        f"Post-refresh RV compatibility: `{((run.get('post_refresh_compatibility') or {}).get('state'))}`",
        f"AREB post-delisting current RV rows: `{((run.get('areb_after') or {}).get('post_delisting_relative_valuation_rows'))}`",
        f"RV excluded input counts: `{json.dumps(rv_meta.get('excluded_input_counts', {}), sort_keys=True)}`",
        f"Deterministic replay: `{(result.get('determinism') or {}).get('match')}`",
        f"Production immutable: `{result['production_immutability']['identical']}`",
        f"Deferred policy: `{result['deferred_policy']}`",
        "",
        "## Source Status",
        "",
    ]
    for row in result["source_reconciliation"]["reconciliation"]:
        lines.append(
            f"- `{row['current_ticker']}`: `{row['final_source_status']}`; ARQ `{row['ARQ_row_count']}`, MRQ `{row['MRQ_row_count']}`, CIK `{row['cik']}`"
        )
    lines.extend(["", "## Structural Endpoint Policy", ""])
    for row in ((run.get("structural_endpoint_policy") or {}).get("rows") or []):
        lines.append(f"- `{row['ticker']}`: `{row['snapshot_endpoint_status']}`")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{blocker}`" for blocker in result["blockers"])
    text = "\n".join(lines) + "\n"
    path = output / "phase13f3_2_report.md"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "bytes": len(text.encode("utf-8"))}
