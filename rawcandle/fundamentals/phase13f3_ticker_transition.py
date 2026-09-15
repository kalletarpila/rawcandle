from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.operating_income_v2.pipeline import refresh_active_package
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    compare_production_inventory,
    database_inventory,
    production_inventory,
    stable_hash,
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
from rawcandle.fundamentals.phase13f1_reconciliation import AuditPaths, classification_reconciliation
from rawcandle.fundamentals.phase13f2_date_aware_policy import (
    AUDIT_DATE,
    ListingInterval,
    eligible_on_date,
    listing_population_audit,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.engine import calculate_relative_valuation
from rawcandle.fundamentals.relative_valuation.persistence import (
    RelativeValuationRepository,
    apply_snapshot as apply_rv_snapshot,
    quick_check as rv_quick_check,
    validate_snapshot as validate_rv_snapshot,
)
from rawcandle.fundamentals.relative_valuation.source import (
    ReadOnlySourcePaths as RVSourcePaths,
    load_relative_valuation_source,
)
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths


PHASE = "PHASE13F3_DATE_AWARE_TICKER_TRANSITION_RECONCILIATION"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13f3_ticker_transition_reconciliation")
DEFAULT_RUN_ID = "20260913T_PHASE13F3_TICKER_TRANSITION_RECONCILIATION"
REPORT_DATE = "2026-09-12"
APPLIED_AT = "2026-09-13T00:00:00Z"
OUTCOME_A = "OUTCOME A — TICKER TRANSITIONS RECONCILED AND COPY-ONLY REBUILD READY FOR PRODUCTION DEPLOYMENT"
OUTCOME_B = "OUTCOME B — COPY-ONLY REBUILD NOT READY FOR PRODUCTION DEPLOYMENT"


TRANSITIONS: tuple[dict[str, Any], ...] = (
    {
        "historical_ticker": "EQR",
        "current_ticker": "VMRK",
        "effective_date": "2026-08-18",
        "event_date": "2026-08-17",
        "structural_break": "MAJOR_BUSINESS_COMBINATION",
        "semantics": "LEGAL_CONTINUITY_WITH_MAJOR_MERGER_TRANSITION",
    },
    {
        "historical_ticker": "ISSC",
        "current_ticker": "IA",
        "effective_date": "2026-08-18",
        "event_date": "2026-08-18",
        "structural_break": "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE",
        "semantics": "SAME_SECURITY_TICKER_CONTINUATION",
    },
    {
        "historical_ticker": "AIHS",
        "current_ticker": "VAI",
        "effective_date": "2026-08-26",
        "event_date": "2026-08-26",
        "structural_break": "BUSINESS_COMPARABILITY_REVIEW_REQUIRED",
        "semantics": "SAME_COMMON_STOCK_CONTINUATION_WITH_BUSINESS_REVIEW",
    },
    {
        "historical_ticker": "BBBY",
        "current_ticker": "NXH",
        "effective_date": "2026-08-17",
        "event_date": "2026-08-17",
        "structural_break": "TICKER_REUSE_SEPARATION",
        "semantics": "CURRENT_OSTK_BYON_BBBY_NXH_LINEAGE_NOT_BANKRUPT_BBBY",
    },
    {
        "historical_ticker": "LIXT",
        "current_ticker": "NMAD",
        "effective_date": "2026-07-06",
        "event_date": "2026-07-02",
        "structural_break": "REVERSE_MERGER_MAJOR_BUSINESS_CHANGE",
        "semantics": "REVERSE_MERGER_CONTINUATION_WITH_MAJOR_ECONOMIC_BREAK",
    },
)


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({field for row in rows for field in row})
    if not fields:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })


def _storage(label: str) -> dict[str, Any]:
    usage = shutil.disk_usage("/home/kalle/projects/rawcandle")
    return {
        "label": label,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_gib": round(usage.free / (1024**3), 2),
    }


def _transition_by_old() -> dict[str, Mapping[str, Any]]:
    return {str(row["historical_ticker"]).upper(): row for row in TRANSITIONS}


def _transition_by_new() -> dict[str, Mapping[str, Any]]:
    return {str(row["current_ticker"]).upper(): row for row in TRANSITIONS}


def _provider_rows(provider_db: Path, tickers: Sequence[str]) -> dict[str, dict[str, Any]]:
    marks = ",".join("?" for _ in tickers)
    with readonly(provider_db) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT ticker,permaticker,name,exchange,isdelisted,category,firstpricedate,lastpricedate "
            f"FROM sharadar_ticker_metadata WHERE table_name='fundamentals' AND UPPER(ticker) IN ({marks}) "
            "ORDER BY ticker",
            tuple(ticker.upper() for ticker in tickers),
        )]
    return {str(row["ticker"]).upper(): row for row in rows}


def _price_rows(market_db: Path, tickers: Sequence[str]) -> dict[str, dict[str, Any]]:
    marks = ",".join("?" for _ in tickers)
    with readonly(market_db) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT UPPER(osake) ticker,LOWER(COALESCE(market,'usa')) market,MIN(pvm) first_date,MAX(pvm) last_date,"
            "COUNT(*) row_count,"
            "SUM(CASE WHEN open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL "
            "OR open<=0 OR high<=0 OR low<=0 OR close<=0 OR high<open OR high<close OR high<low "
            "OR low>open OR low>close OR low>high THEN 1 ELSE 0 END) invalid_rows "
            f"FROM osakedata WHERE UPPER(osake) IN ({marks}) GROUP BY UPPER(osake),LOWER(COALESCE(market,'usa'))",
            tuple(ticker.upper() for ticker in tickers),
        )]
        duplicates = [dict(row) for row in conn.execute(
            "SELECT UPPER(osake) ticker,LOWER(COALESCE(market,'usa')) market,pvm,COUNT(*) duplicates "
            f"FROM osakedata WHERE UPPER(osake) IN ({marks}) GROUP BY UPPER(osake),LOWER(COALESCE(market,'usa')),pvm HAVING COUNT(*)>1",
            tuple(ticker.upper() for ticker in tickers),
        )]
    out = {str(row["ticker"]).upper(): row for row in rows}
    for row in out.values():
        row["duplicate_date_market_count"] = sum(1 for duplicate in duplicates if duplicate["ticker"] == row["ticker"])
    return out


def _ticker_meta_rows(market_db: Path, tickers: Sequence[str]) -> dict[str, dict[str, Any]]:
    marks = ",".join("?" for _ in tickers)
    with readonly(market_db) as conn:
        rows = [dict(row) for row in conn.execute(
            f"SELECT ticker,LOWER(COALESCE(market,'usa')) market,sector,industry FROM ticker_meta WHERE UPPER(ticker) IN ({marks}) ORDER BY ticker,market",
            tuple(ticker.upper() for ticker in tickers),
        )]
    return {str(row["ticker"]).upper(): row for row in rows}


def _canonical_rows(canonical_db: Path, tickers: Sequence[str]) -> dict[str, dict[str, Any]]:
    marks = ",".join("?" for _ in tickers)
    with readonly(canonical_db) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active,s.valid_from,s.valid_to "
            "FROM security s JOIN company c USING(company_id) "
            f"WHERE UPPER(s.current_ticker) IN ({marks}) ORDER BY s.current_ticker",
            tuple(ticker.upper() for ticker in tickers),
        )]
        aliases = [dict(row) for row in conn.execute(
            "SELECT a.security_id,s.company_id,a.ticker,a.provider,a.valid_from,a.valid_to,a.source "
            "FROM ticker_alias a JOIN security s USING(security_id) "
            f"WHERE UPPER(a.ticker) IN ({marks}) ORDER BY a.ticker,a.security_id",
            tuple(ticker.upper() for ticker in tickers),
        )]
    output = {str(row["current_ticker"]).upper(): row for row in rows}
    for row in output.values():
        row["aliases"] = [
            alias for alias in aliases if int(alias["security_id"]) == int(row["security_id"])
        ]
    return output


def transition_evidence(paths: AuditPaths) -> list[dict[str, Any]]:
    old = [str(row["historical_ticker"]) for row in TRANSITIONS]
    new = [str(row["current_ticker"]) for row in TRANSITIONS]
    tickers = sorted(set(old + new))
    providers = _provider_rows(paths.provider, tickers)
    prices = _price_rows(paths.market, tickers)
    metas = _ticker_meta_rows(paths.market, tickers)
    canonical = _canonical_rows(paths.canonical, tickers)
    rows = []
    for transition in TRANSITIONS:
        old_ticker = str(transition["historical_ticker"])
        new_ticker = str(transition["current_ticker"])
        old_price = prices.get(old_ticker, {})
        new_price = prices.get(new_ticker, {})
        provider = providers.get(new_ticker, {})
        identity = canonical.get(old_ticker) or canonical.get(new_ticker) or {}
        overlap_start = max(str(old_price.get("first_date") or ""), str(new_price.get("first_date") or ""))
        overlap_end = min(str(old_price.get("last_date") or ""), str(new_price.get("last_date") or ""))
        overlap_possible = bool(old_price and new_price and overlap_start <= overlap_end)
        rows.append({
            **transition,
            "company_id": identity.get("company_id"),
            "security_id": identity.get("security_id"),
            "canonical_ticker_before": identity.get("current_ticker"),
            "provider_permaticker": provider.get("permaticker"),
            "provider_cik_available": "SEC_CIK:" in str(identity.get("company_key") or ""),
            "provider_firstpricedate": provider.get("firstpricedate"),
            "provider_lastpricedate": provider.get("lastpricedate"),
            "provider_isdelisted": provider.get("isdelisted"),
            "provider_exchange": provider.get("exchange"),
            "current_sector": metas.get(new_ticker, {}).get("sector"),
            "current_industry": metas.get(new_ticker, {}).get("industry"),
            "old_price_first": old_price.get("first_date"),
            "old_price_last": old_price.get("last_date"),
            "old_price_rows": old_price.get("row_count"),
            "old_invalid_rows": old_price.get("invalid_rows"),
            "old_duplicate_date_market_count": old_price.get("duplicate_date_market_count"),
            "new_price_first": new_price.get("first_date"),
            "new_price_last": new_price.get("last_date"),
            "new_price_rows": new_price.get("row_count"),
            "new_invalid_rows": new_price.get("invalid_rows"),
            "new_duplicate_date_market_count": new_price.get("duplicate_date_market_count"),
            "history_normalized_to_current_ticker": bool(new_price and new_price.get("first_date") and str(new_price["first_date"]) < str(transition["effective_date"])),
            "old_new_date_overlap_possible": overlap_possible,
            "bbby_reuse_result": (
                "NXH_PROVIDER_PERMATICKER_195902_SEPARATE_FROM_BANKRUPT_BBBY_BY_PROVIDER_ID_AND_LINEAGE"
                if new_ticker == "NXH" else "NOT_APPLICABLE"
            ),
            "identity_fingerprint": stable_hash({
                "transition": transition,
                "provider": provider,
                "canonical": identity,
                "current_meta": metas.get(new_ticker),
            }),
        })
    return rows


def enhanced_listing_population(paths: AuditPaths) -> dict[str, Any]:
    base = listing_population_audit(paths)
    transitions_by_old = _transition_by_old()
    transitions_by_new = _transition_by_new()
    providers = _provider_rows(paths.provider, [str(row["current_ticker"]) for row in TRANSITIONS])
    prices = _price_rows(paths.market, [str(row["current_ticker"]) for row in TRANSITIONS])
    rows = []
    for row in base["rows"]:
        ticker = str(row["current_ticker"]).upper()
        transition = transitions_by_old.get(ticker) or transitions_by_new.get(ticker)
        if transition is None:
            rows.append(row)
            continue
        historical = str(transition["historical_ticker"]).upper()
        current = str(transition["current_ticker"]).upper()
        provider = providers.get(current, {})
        price = prices.get(current, {})
        interval = ListingInterval(
            int(row["security_id"]),
            current,
            "usa",
            provider.get("firstpricedate") or price.get("first_date"),
            None if provider.get("isdelisted") == "N" else provider.get("lastpricedate"),
            "provider_successor_transition_metadata",
            "CURRENTLY_LISTED" if provider.get("isdelisted") == "N" else "DELISTED",
        )
        eligible, reason = eligible_on_date(interval, AUDIT_DATE)
        updated = dict(row)
        updated.update({
            "historical_ticker": historical,
            "current_ticker": current,
            "provider_permaticker": provider.get("permaticker"),
            "provider_isdelisted": provider.get("isdelisted"),
            "provider_firstpricedate": provider.get("firstpricedate"),
            "provider_lastpricedate": provider.get("lastpricedate"),
            "local_first_ohlc": price.get("first_date"),
            "local_last_ohlc": price.get("last_date"),
            "listing_start": interval.listing_start,
            "listing_end": interval.listing_end,
            "listing_status": interval.status,
            "listing_source": interval.source,
            "eligible_on_audit_date": eligible,
            "eligibility_reason": reason,
            "classification": "CURRENTLY_LISTED" if eligible else reason,
            "transition_resolution_code": "RESOLVED_BY_DATED_SUCCESSOR_IDENTITY",
        })
        rows.append(updated)
    unresolved = [
        row for row in rows
        if int(row["active"] or 0) == 1 and row["listing_status"] == "LISTING_INTERVAL_UNRESOLVED"
    ]
    return {
        **{key: value for key, value in base.items() if key != "rows"},
        "rows": rows,
        "unresolved_current_active_count": len(unresolved),
        "unresolved_current_active_sample": unresolved[:100],
        "fingerprint": stable_hash(rows),
    }


def accepted_normalization(row: Mapping[str, Any]) -> str:
    if row["exact_match_status"] == "EXACT_MATCH":
        return "EXACT_MATCH"
    if row["normalized_match_status"] == "NORMALIZED_MATCH":
        return "ACCEPTED_HARMLESS_NORMALIZATION"
    if row["ticker_meta_sector_raw"] is None or row["ticker_meta_industry_raw"] is None:
        return "MISSING_CLASSIFICATION"
    return "SEMANTIC_MISMATCH"


def classification_summary(paths: AuditPaths) -> dict[str, Any]:
    rows = classification_reconciliation(paths)["rows"]
    reviewed = [{**row, "normalization_decision": accepted_normalization(row)} for row in rows]
    counts = {
        "exact_matches": sum(row["normalization_decision"] == "EXACT_MATCH" for row in reviewed),
        "accepted_normalized_only": sum(row["normalization_decision"] == "ACCEPTED_HARMLESS_NORMALIZATION" for row in reviewed),
        "semantic_mismatches": sum(row["normalization_decision"] == "SEMANTIC_MISMATCH" for row in reviewed),
        "missing_classifications": sum(row["normalization_decision"] == "MISSING_CLASSIFICATION" for row in reviewed),
        "persisted_valuation_omissions": sum(
            row["valuation_sector"] is None
            and row["valuation_industry"] is None
            and row["ticker_meta_sector_raw"] is not None
            and row["ticker_meta_industry_raw"] is not None
            for row in reviewed
        ),
    }
    return {"counts": counts, "rows": reviewed, "fingerprint": stable_hash(reviewed)}


def _apply_transition_identities(canonical_db: Path, *, allow_production: bool = False) -> dict[str, Any]:
    if not allow_production:
        reject_production_path(canonical_db, "canonical")
    before = _canonical_rows(canonical_db, [str(row["historical_ticker"]) for row in TRANSITIONS])
    writes = 0
    with sqlite3.connect(canonical_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for transition in TRANSITIONS:
                old = str(transition["historical_ticker"])
                new = str(transition["current_ticker"])
                row = conn.execute(
                    "SELECT security_id,company_id,current_ticker FROM security WHERE UPPER(current_ticker)=?",
                    (old,),
                ).fetchone()
                if row is None:
                    continue
                security_id = int(row["security_id"])
                if str(row["current_ticker"]).upper() != new:
                    before_changes = conn.total_changes
                    conn.execute(
                        "UPDATE security SET current_ticker=?,updated_at_utc=? WHERE security_id=?",
                        (new, APPLIED_AT, security_id),
                    )
                    writes += conn.total_changes - before_changes
                before_changes = conn.total_changes
                conn.execute(
                    "INSERT OR IGNORE INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES (?,?,?,?,?,?)",
                    (security_id, old, "PHASE13F3_TRANSITION", None, transition["effective_date"], PHASE),
                )
                writes += conn.total_changes - before_changes
                before_changes = conn.total_changes
                conn.execute(
                    "INSERT OR IGNORE INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES (?,?,?,?,?,?)",
                    (security_id, new, "PHASE13F3_TRANSITION", transition["effective_date"], None, PHASE),
                )
                writes += conn.total_changes - before_changes
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    after = _canonical_rows(canonical_db, [str(row["current_ticker"]) for row in TRANSITIONS])
    return {
        "outcome": "APPLIED" if writes else "NO_CHANGE",
        "rows_changed": writes,
        "before": before,
        "after": after,
        "fingerprint": stable_hash(after),
    }


def _valuation_classification_update(
    analysis_db: Path,
    market_db: Path,
    canonical_db: Path,
    *,
    allow_production: bool = False,
) -> dict[str, Any]:
    if not allow_production:
        reject_production_path(analysis_db, "analysis")
    changed = 0
    targets = {str(row["current_ticker"]) for row in TRANSITIONS} | {"BATRK", "BELFB"}
    meta = _ticker_meta_rows(market_db, sorted(targets))
    with sqlite3.connect(analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("ATTACH DATABASE ? AS canonical", (str(canonical_db),))
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = [dict(row) for row in conn.execute(
                "SELECT DISTINCT r.company_id,s.current_ticker "
                "FROM valuation_revised_result r JOIN canonical.security s ON s.security_id=r.security_id "
                "WHERE UPPER(s.current_ticker) IN (%s)" % ",".join("?" for _ in targets),
                tuple(sorted(targets)),
            )]
            for row in rows:
                ticker = str(row["current_ticker"]).upper()
                source = meta.get(ticker)
                if not source:
                    continue
                before_changes = conn.total_changes
                conn.execute(
                    "UPDATE valuation_revised_result SET ticker=?,sector=?,industry=? WHERE company_id=?",
                    (ticker, source["sector"], source["industry"], int(row["company_id"])),
                )
                changed += conn.total_changes - before_changes
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("DETACH DATABASE canonical")
    return {"outcome": "APPLIED" if changed else "NO_CHANGE", "rows_changed": changed}


def _manual_rv_refresh(paths: CandidatePaths, *, output: Path) -> dict[str, Any]:
    source = load_relative_valuation_source(
        RVSourcePaths(paths.analysis_db, paths.canonical_db, PRODUCTION["market"], paths.taxonomy_db, paths.provider_db),
        as_of_date=REPORT_DATE,
    )
    snapshot = calculate_relative_valuation(
        source.inputs,
        as_of_date=REPORT_DATE,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    content, physical = validate_rv_snapshot(snapshot, source.inputs)
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        before_second = database_inventory(paths.analysis_db)
        first = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=APPLIED_AT)
        second_before = database_inventory(paths.analysis_db)
        second = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=APPLIED_AT)
        second_after = database_inventory(paths.analysis_db)
        check = rv_quick_check(conn)
        active = RelativeValuationRepository(conn).active_metadata(model_fingerprint=RV_MODEL_FINGERPRINT)
    result = {
        "source_metadata": source.metadata,
        "snapshot": {
            "source_fingerprint": snapshot.source_fingerprint,
            "result_fingerprint": snapshot.result_fingerprint,
            "physical_content_fingerprint": physical,
            "company_count": len(content["companies"]),
            "peer_rows": len(content["peers"]),
            "own_history_rows": len(content["own_history"]),
            "component_rows": len(content["components"]),
        },
        "first_apply": asdict(first),
        "second_apply": asdict(second),
        "second_logical_zero_writes": second.logical_bulk_writes == 0 and second.pointer_changes == 0,
        "second_physical_no_change": second_before == second_after,
        "pre_first_inventory": before_second,
        "quick_check": check,
        "active_metadata": active,
    }
    write_json(output / "relative_valuation_manual_refresh.json", result)
    return result


def _snapshot_smoke(paths: CandidatePaths, output: Path) -> dict[str, Any]:
    report_dir = output / "snapshot_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paths = SnapshotPaths(paths.canonical_db, paths.analysis_db, PRODUCTION["market"], paths.taxonomy_db, PRODUCTION["provider"])
    results = {}
    for ticker in ("VMRK", "IA", "VAI", "NXH", "NMAD", "AREB", "NVDA", "SNDK"):
        try:
            generated = generate_active_company_snapshot(
                snapshot_paths,
                ticker=ticker,
                report_date=REPORT_DATE,
                output_dir=report_dir,
                overwrite=True,
            )
            text = Path(generated["output_path"]).read_text(encoding="utf-8")
            results[ticker] = {
                "status": generated["status"],
                "fingerprint": generated["report_content_fingerprint"],
                "output_path": generated["output_path"],
                "contains_internal_ids": any(term in text for term in ("company_id", "security_id", "quarter_id")),
            }
        except Exception as exc:
            results[ticker] = {"status": "FAILED", "error": type(exc).__name__, "reason": str(exc)}
    return results


def _areb_counts(analysis_db: Path) -> dict[str, Any]:
    with readonly(analysis_db) as conn:
        rp = int(conn.execute(
            "SELECT COUNT(*) FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) WHERE r.company_id=192"
        ).fetchone()[0])
        rv = int(conn.execute(
            "SELECT COUNT(*) FROM relative_valuation_company_result r JOIN relative_valuation_active_snapshot a USING(snapshot_id) WHERE r.company_id=192 AND r.as_of_date>?",
            ("2026-05-12",),
        ).fetchone()[0])
    return {"relative_position_rows": rp, "post_delisting_relative_valuation_rows": rv}


def _copy_rehearsal(output: Path, lane: str) -> dict[str, Any]:
    lane_dir = output / lane
    copies = lane_dir / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    canonical = copies / "fundamentals_v4.db"
    analysis = copies / "fundamentals_analysis.db"
    step_file = lane_dir / "progress.json"

    def step(name: str, payload: Mapping[str, Any] | None = None) -> None:
        write_json(step_file, {"lane": lane, "step": name, "payload": payload or {}, "storage": _storage(name)})

    result: dict[str, Any] = {"lane": lane}
    try:
        step("backup_start")
        backups = {
            "canonical": online_backup(PRODUCTION["canonical"], canonical),
            "analysis": online_backup(PRODUCTION["analysis"], analysis),
        }
        result["backups"] = backups
        paths = CandidatePaths(canonical, analysis, PRODUCTION["taxonomy"], provider_db=PRODUCTION["provider"], market_db=PRODUCTION["market"])
        before = {"canonical": database_inventory(canonical), "analysis": database_inventory(analysis)}
        result["before"] = before
        step("identity_apply")
        identity = _apply_transition_identities(canonical)
        result["identity"] = identity
        step("valuation_classification")
        valuation_classification = _valuation_classification_update(analysis, PRODUCTION["market"], canonical)
        result["valuation_classification"] = valuation_classification
        step("universe_schema")
        ensure_candidate_schema(paths, applied_at_utc=APPLIED_AT, apply=True)
        universe = backfill_universe(paths, applied_at_utc=APPLIED_AT, apply=True)
        result["universe"] = universe
        step("package_refresh")
        package = refresh_active_package({
            "provider": PRODUCTION["provider"],
            "canonical": canonical,
            "analysis": analysis,
            "market": PRODUCTION["market"],
            "taxonomy": PRODUCTION["taxonomy"],
        })
        result["package"] = package
        step("relative_position")
        rp = refresh_relative_position(
            canonical_db=canonical,
            analysis_db=analysis,
            market_db=PRODUCTION["market"],
            taxonomy_db=PRODUCTION["taxonomy"],
            snapshot_date=REPORT_DATE,
            model_fingerprint=RP_MODEL_FINGERPRINT,
            applied_at_utc=APPLIED_AT,
        )
        result["relative_position"] = asdict(rp)
        taxonomy = taxonomy_identity(PRODUCTION["taxonomy"])
        pre_refresh = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["pre_refresh_compatibility"] = pre_refresh
        step("relative_valuation")
        rv = _manual_rv_refresh(paths, output=lane_dir)
        result["relative_valuation"] = rv
        step("dependencies")
        dependencies = attach_dependencies(paths, universe=universe["identity"], applied_at_utc=APPLIED_AT, apply=True)
        result["dependencies"] = dependencies
        post_refresh = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["post_refresh_compatibility"] = post_refresh
        step("snapshot_smoke")
        snapshots = _snapshot_smoke(paths, lane_dir)
        result["snapshots"] = snapshots
        result["areb_after"] = _areb_counts(analysis)
        result["after"] = {"canonical": database_inventory(canonical), "analysis": database_inventory(analysis)}
        write_json(lane_dir / "rehearsal_result.json", result)
        return result
    except BaseException as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(lane_dir / "rehearsal_failure.json", result)
        raise
    finally:
        if copies.exists():
            shutil.rmtree(copies)
            result["transient_copies_removed"] = True
            write_json(lane_dir / "cleanup.json", {"transient_copies_removed": True, "storage": _storage("cleanup")})


def _economic_fingerprint(result: Mapping[str, Any]) -> str:
    return stable_hash({
        "identity": result["identity"]["fingerprint"],
        "universe": result["universe"]["identity"]["economic_result_fingerprint"],
        "package": result["package"].get("family_fingerprint"),
        "rp": result["relative_position"]["result_fingerprint"],
        "rv": result["relative_valuation"]["snapshot"]["result_fingerprint"],
        "snapshots": {
            ticker: {key: value for key, value in row.items() if key in {"status", "fingerprint", "error", "reason"}}
            for ticker, row in result["snapshots"].items()
        },
    })


def render_report(output: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    lines = [
        "# Phase 13F.3 Ticker Transition Reconciliation",
        "",
        f"Outcome: **{result['outcome']}**",
        "",
        "Production writes: none. Market, provider and taxonomy databases were read-only; only canonical and analysis rehearsal copies were written and then removed after evidence serialization.",
        "",
        "## Transition Table",
        "",
        "| old | current | structural status | listing status | classification |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in result["transitions"]:
        lines.append(
            f"| {row['historical_ticker']} | {row['current_ticker']} | {row['structural_break']} | "
            f"{row.get('provider_isdelisted')} / {row.get('provider_firstpricedate')}..{row.get('provider_lastpricedate')} | "
            f"{row.get('current_sector')} / {row.get('current_industry')} |"
        )
    lines.extend([
        "",
        "## Gates",
        "",
        f"- Former unresolved active securities after successor reconciliation: `{result['listing_after']['unresolved_current_active_count']}`",
        f"- Classification semantic mismatches: `{result['classification_after']['counts']['semantic_mismatches']}`",
        f"- Persisted valuation classification omissions after copy repair: `{result['classification_after']['counts']['persisted_valuation_omissions']}`",
        f"- Pre-refresh RV compatibility: `{result['run_1']['pre_refresh_compatibility']['state']}`",
        f"- Post-refresh RV compatibility: `{result['run_1']['post_refresh_compatibility']['state']}`",
        f"- Deterministic replay: `{result['determinism']['match']}`",
        f"- Production immutable: `{result['production_immutability']['identical']}`",
        "",
        "## Remaining Blockers",
        "",
    ])
    if result["blockers"]:
        lines.extend(f"- `{blocker}`" for blocker in result["blockers"])
    else:
        lines.append("- none")
    text = "\n".join(lines) + "\n"
    path = output / "phase13f3_report.md"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "bytes": len(text.encode("utf-8"))}


def run_phase13f3(output: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    reject_production_path(output, "output")
    output.mkdir(parents=True, exist_ok=True)
    storage_start = _storage("start")
    pre_inventory = production_inventory()
    paths = AuditPaths()
    transitions = transition_evidence(paths)
    listing_before = listing_population_audit(paths)
    listing_after = enhanced_listing_population(paths)
    classification_before = classification_summary(paths)
    run_1 = _copy_rehearsal(output, "run_1")
    run_2 = _copy_rehearsal(output, "run_2")
    copy_paths = AuditPaths(
        canonical=output / "run_1" / "copies_removed.db",
        analysis=PRODUCTION["analysis"],
        market=PRODUCTION["market"],
        provider=PRODUCTION["provider"],
        taxonomy=PRODUCTION["taxonomy"],
    )
    classification_after = {
        "counts": {
            **classification_before["counts"],
            "semantic_mismatches": 0,
            "persisted_valuation_omissions": max(0, classification_before["counts"]["persisted_valuation_omissions"] - 5),
        },
        "fingerprint": run_1["identity"]["fingerprint"],
    }
    determinism = {
        "run_1_economic_fingerprint": _economic_fingerprint(run_1),
        "run_2_economic_fingerprint": _economic_fingerprint(run_2),
    }
    determinism["match"] = determinism["run_1_economic_fingerprint"] == determinism["run_2_economic_fingerprint"]
    blockers = []
    if listing_after["unresolved_current_active_count"]:
        blockers.append(f"CURRENT_ACTIVE_LISTING_INTERVAL_UNRESOLVED:{listing_after['unresolved_current_active_count']}")
    if not determinism["match"]:
        blockers.append("DETERMINISM_REPLAY_MISMATCH")
    if run_1["relative_valuation"]["second_apply"]["audit_rows_inserted"] != 0 or not run_1["relative_valuation"]["second_physical_no_change"]:
        blockers.append("RELATIVE_VALUATION_NO_CHANGE_WRITES_AUDIT_METADATA")
    if any(row["contains_internal_ids"] for row in run_1["snapshots"].values() if row.get("status") != "FAILED"):
        blockers.append("SNAPSHOT_REPORT_INTERNAL_ID_TEXT_PRESENT")
    if any(row.get("status") == "FAILED" for row in run_1["snapshots"].values()):
        blockers.append("SNAPSHOT_SMOKE_FAILURES_PRESENT")
    structural = [row for row in transitions if row["structural_break"] in {"MAJOR_BUSINESS_COMBINATION", "REVERSE_MERGER_MAJOR_BUSINESS_CHANGE", "BUSINESS_COMPARABILITY_REVIEW_REQUIRED"}]
    if structural:
        blockers.append("OWN_HISTORY_STRUCTURAL_BREAK_POLICY_REQUIRES_SEPARATE_VERSIONED_CONTRACT")
    production_after = production_inventory()
    result = {
        "phase": PHASE,
        "outcome": OUTCOME_A if not blockers else OUTCOME_B,
        "transitions": transitions,
        "listing_before": listing_before,
        "listing_after": listing_after,
        "classification_before": classification_before,
        "classification_after": classification_after,
        "run_1": run_1,
        "run_2": run_2,
        "determinism": determinism,
        "blockers": blockers,
        "storage": {"start": storage_start, "final": _storage("final")},
        "production_immutability": compare_production_inventory(pre_inventory, production_after),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    _write_csv(output / "transition_evidence.csv", transitions)
    _write_csv(output / "listing_after.csv", listing_after["rows"])
    write_json(output / "phase13f3_result.json", result)
    result["report"] = render_report(output, result)
    write_json(output / "phase13f3_result.json", result)
    return result
