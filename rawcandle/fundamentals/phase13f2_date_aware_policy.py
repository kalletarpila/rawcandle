from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    compare_production_inventory,
    production_inventory,
    stable_hash,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import reject_production_path
from rawcandle.fundamentals.phase13f1_reconciliation import (
    AuditPaths,
    areb_relative_position_audit,
    areb_relative_valuation_audit,
    classification_reconciliation,
    eligibility_audit,
)


PHASE = "PHASE13F2_DATE_AWARE_LISTING_ELIGIBILITY_PREWRITE"
DEFAULT_RUN_ID = "20260912T_PHASE13F2_DATE_AWARE_PREWRITE"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13f2_date_aware")
OUTCOME_B = "OUTCOME B — PRE-WRITE MATERIAL BLOCKER; PRODUCTION UNCHANGED"
OUTCOME_C = "OUTCOME C — PRODUCTION ATTEMPT FAILED AND FULLY ROLLED BACK"
AREB_COMPANY_ID = 192
AUDIT_DATE = "2026-09-12"


@dataclass(frozen=True)
class ListingInterval:
    security_id: int
    ticker: str
    market: str
    listing_start: str | None
    listing_end: str | None
    source: str
    status: str


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _market(value: Any) -> str:
    text = str(value or "usa").strip().lower()
    return "usa" if text in {"", "nasdaq", "nyse", "nysemkt", "amex", "arca", "otc", "otcqx", "otcqb"} else text


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text.lower() if text else None


def eligible_on_date(interval: ListingInterval, calculation_date: str) -> tuple[bool, str]:
    if interval.listing_start is None:
        return False, "LISTING_START_UNRESOLVED"
    if calculation_date < interval.listing_start:
        return False, "PRELISTING"
    if interval.listing_end is not None and calculation_date > interval.listing_end:
        return False, "POST_DELISTING"
    if interval.status == "LISTING_INTERVAL_UNRESOLVED":
        return False, "LISTING_INTERVAL_UNRESOLVED"
    return True, "ELIGIBLE_ON_DATE"


def classify_interval(interval: ListingInterval, calculation_date: str) -> str:
    eligible, reason = eligible_on_date(interval, calculation_date)
    if eligible:
        return "CURRENTLY_LISTED" if interval.listing_end is None else "LISTED_PERIOD"
    return reason


def _storage(label: str) -> dict[str, Any]:
    usage = shutil.disk_usage("/home/kalle/projects/rawcandle")
    return {
        "label": label,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_gib": round(usage.free / (1024**3), 2),
    }


def _provider_index(paths: AuditPaths) -> dict[str, dict[str, Any]]:
    with _readonly(paths.provider) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT table_name,ticker,permaticker,name,exchange,isdelisted,category,firstpricedate,lastpricedate "
            "FROM sharadar_ticker_metadata ORDER BY ticker,table_name"
        )]
    chosen: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row["ticker"]).upper()
        if ticker not in chosen or row["table_name"] == "fundamentals":
            chosen[ticker] = row
    return chosen


def _ohlc_index(paths: AuditPaths) -> dict[tuple[str, str], dict[str, Any]]:
    with _readonly(paths.market) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT UPPER(osake) ticker,market,MIN(pvm) first_ohlc_date,MAX(pvm) last_ohlc_date,COUNT(*) ohlc_rows "
            "FROM osakedata GROUP BY UPPER(osake),market ORDER BY ticker,market"
        )]
    return {(str(row["ticker"]).upper(), _market(row["market"])): row for row in rows}


def _canonical_securities(paths: AuditPaths) -> list[dict[str, Any]]:
    with _readonly(paths.canonical) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active,s.valid_from,s.valid_to "
            "FROM security s JOIN company c USING(company_id) ORDER BY s.security_id"
        )]


def resolve_listing_interval(security: Mapping[str, Any], provider: Mapping[str, Any] | None, ohlc: Mapping[str, Any] | None) -> ListingInterval:
    ticker = str(security["current_ticker"]).upper()
    market = _market(security.get("exchange"))
    if provider:
        start = provider.get("firstpricedate") or (ohlc or {}).get("first_ohlc_date")
        end = provider.get("lastpricedate") if provider.get("isdelisted") == "Y" else None
        status = "DELISTED" if provider.get("isdelisted") == "Y" else "CURRENTLY_LISTED"
        return ListingInterval(int(security["security_id"]), ticker, market, start, end, "provider_metadata", status)
    if int(security.get("active") or 0) == 1 and ohlc:
        return ListingInterval(
            int(security["security_id"]), ticker, market,
            ohlc.get("first_ohlc_date"), None, "canonical_active_plus_local_ohlc",
            "LISTING_INTERVAL_UNRESOLVED",
        )
    if ohlc:
        return ListingInterval(
            int(security["security_id"]), ticker, market,
            ohlc.get("first_ohlc_date"), ohlc.get("last_ohlc_date"), "local_ohlc_only",
            "LISTING_INTERVAL_UNRESOLVED",
        )
    return ListingInterval(int(security["security_id"]), ticker, market, None, None, "missing_local_listing_evidence", "LISTING_INTERVAL_UNRESOLVED")


def listing_population_audit(paths: AuditPaths) -> dict[str, Any]:
    providers = _provider_index(paths)
    ohlc = _ohlc_index(paths)
    rows = []
    for security in _canonical_securities(paths):
        ticker = str(security["current_ticker"]).upper()
        market = _market(security.get("exchange"))
        interval = resolve_listing_interval(security, providers.get(ticker), ohlc.get((ticker, market)))
        current_eligible, reason = eligible_on_date(interval, AUDIT_DATE)
        rows.append({
            **security,
            "market": market,
            "provider_permaticker": providers.get(ticker, {}).get("permaticker") if providers.get(ticker) else None,
            "provider_isdelisted": providers.get(ticker, {}).get("isdelisted") if providers.get(ticker) else None,
            "provider_firstpricedate": providers.get(ticker, {}).get("firstpricedate") if providers.get(ticker) else None,
            "provider_lastpricedate": providers.get(ticker, {}).get("lastpricedate") if providers.get(ticker) else None,
            "local_first_ohlc": ohlc.get((ticker, market), {}).get("first_ohlc_date") if ohlc.get((ticker, market)) else None,
            "local_last_ohlc": ohlc.get((ticker, market), {}).get("last_ohlc_date") if ohlc.get((ticker, market)) else None,
            "listing_start": interval.listing_start,
            "listing_end": interval.listing_end,
            "listing_status": interval.status,
            "listing_source": interval.source,
            "eligible_on_audit_date": current_eligible,
            "eligibility_reason": reason,
            "classification": classify_interval(interval, AUDIT_DATE),
        })
    unresolved_current = [
        row for row in rows
        if int(row["active"] or 0) == 1 and row["listing_status"] == "LISTING_INTERVAL_UNRESOLVED"
    ]
    return {
        "total_securities": len(rows),
        "currently_listed": sum(row["eligible_on_audit_date"] for row in rows),
        "delisted": sum(row["listing_status"] == "DELISTED" for row in rows),
        "unresolved_listing_intervals": sum(row["listing_status"] == "LISTING_INTERVAL_UNRESOLVED" for row in rows),
        "unresolved_current_active_count": len(unresolved_current),
        "rows": rows,
        "unresolved_current_active_sample": unresolved_current[:100],
        "fingerprint": stable_hash(rows),
    }


def normalized_mapping_review(classification_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized_only = [
        row for row in classification_rows
        if row["exact_match_status"] != "EXACT_MATCH"
        and row["normalized_match_status"] == "NORMALIZED_MATCH"
    ]
    reviewed = []
    for row in normalized_only:
        reviewed.append({
            "company_id": row["company_id"],
            "security_id": row["security_id"],
            "ticker": row["current_ticker"],
            "raw_sector": row["ticker_meta_sector_raw"],
            "raw_industry": row["ticker_meta_industry_raw"],
            "valuation_sector": row["valuation_sector"],
            "valuation_industry": row["valuation_industry"],
            "normalized_sector_key": row["ticker_meta_sector_normalized"],
            "normalized_industry_key": row["ticker_meta_industry_normalized"],
            "mapping_decision": "UNRESOLVED_REQUIRES_REVIEW",
        })
    return {
        "normalized_only_count": len(normalized_only),
        "unresolved_count": len(reviewed),
        "rows": reviewed,
        "fingerprint": stable_hash(reviewed),
    }


def seven_classification_omissions(classification_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [
        row for row in classification_rows
        if row["valuation_sector"] is None
        and row["valuation_industry"] is None
        and row["ticker_meta_sector_raw"] is not None
        and row["ticker_meta_industry_raw"] is not None
    ]
    return {"count": len(rows), "rows": rows, "fingerprint": stable_hash(rows)}


def areb_date_aware_reconciliation(paths: AuditPaths) -> dict[str, Any]:
    providers = _provider_index(paths)
    ohlc = _ohlc_index(paths)
    security = next(row for row in _canonical_securities(paths) if int(row["company_id"]) == AREB_COMPANY_ID)
    interval = resolve_listing_interval(security, providers.get("AREB"), ohlc.get(("AREB", "usa")))
    rp = areb_relative_position_audit(paths)
    rv = areb_relative_valuation_audit(paths)
    rp_rows = []
    for row in rp["active_rows"]:
        eligible, reason = eligible_on_date(interval, str(row["source_observation_date"]))
        rp_rows.append({
            "snapshot_id": row["snapshot_id"],
            "model_version": row["model_version"],
            "measure": row["measure"],
            "peer_scope": row["peer_scope"],
            "peer_group_id": row["peer_group_id"],
            "comparison_date": row["source_observation_date"],
            "result_status": row["result_status"],
            "eligible_on_comparison_date": eligible,
            "eligibility_reason": reason,
            "row_classification": "VALID_LISTED_PERIOD" if eligible else reason,
            "peer_count": row["peer_count"],
            "percentile": row["percentile"],
        })
    rv_rows = []
    for row in rv["company_rows"]:
        eligible, reason = eligible_on_date(interval, str(row["as_of_date"]))
        rv_rows.append({
            "snapshot_id": row["snapshot_id"],
            "as_of_date": row["as_of_date"],
            "price_date": row["current_price_date"],
            "current_fresh": row["current_fresh"],
            "valuation_status": row["valuation_status"],
            "eligible_on_snapshot_date": eligible,
            "eligibility_reason": reason,
            "row_classification": "CURRENT_PEER_ELIGIBLE_DEFECT" if not eligible and int(row["current_fresh"]) == 1 else ("VALID_LISTED_PERIOD" if eligible else reason),
        })
    return {
        "interval": interval.__dict__,
        "rp_rows": rp_rows,
        "rv_company_rows": rv_rows,
        "rp_valid_listed_period_rows": sum(row["row_classification"] == "VALID_LISTED_PERIOD" for row in rp_rows),
        "rp_post_delisting_rows": sum(row["row_classification"] == "POST_DELISTING" for row in rp_rows),
        "rv_current_peer_eligible_defects": sum(row["row_classification"] == "CURRENT_PEER_ELIGIBLE_DEFECT" for row in rv_rows),
        "fingerprint": stable_hash({"interval": interval.__dict__, "rp": rp_rows, "rv": rv_rows}),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def render_report(output: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    lines = [
        "# Phase 13F.2 Date-Aware Listing Eligibility Pre-Write Record",
        "",
        f"Outcome: **{result['outcome']}**",
        "",
        "Production writes were not started.",
        "",
        "## Blockers",
        "",
    ]
    for blocker in result["prewrite_blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend([
        "",
        "## Universal Policy",
        "",
        "`eligible_on_date = listing_start <= calculation_date and (listing_end is NULL or calculation_date <= listing_end)`.",
        "",
        "Eligibility is security-specific, not ticker-specific or company-only. AREB is handled by the same rule.",
        "",
        "## Key Evidence",
        "",
        f"- Classification primary active securities: `{result['classification']['summary']['primary_active_security_rows']}`",
        f"- Missing/ambiguous ticker_meta matches: `{result['classification']['summary']['missing_ticker_meta_row'] + result['classification']['summary']['ambiguous_ticker_market_match']}`",
        f"- Normalized-only mappings requiring review: `{result['normalized_mapping_review']['unresolved_count']}`",
        f"- Seven-company valuation omissions found: `{result['seven_classification_omissions']['count']}`",
        f"- Listing intervals unresolved for active securities: `{result['listing_population']['unresolved_current_active_count']}`",
        f"- AREB RP valid listed-period rows: `{result['areb_date_aware']['rp_valid_listed_period_rows']}`",
        f"- AREB RV current peer-eligible defects: `{result['areb_date_aware']['rv_current_peer_eligible_defects']}`",
        "",
        "## Phase 13F.2 Continuation Plan",
        "",
        "1. Review and approve or reject the 196 normalized-only classification mappings.",
        "2. Resolve active security listing intervals that lack provider metadata before production writes.",
        "3. Add versioned classification/listing dependency identities to rebuilt RP/RV outputs.",
        "4. Rehearse schema/dependency migration and full-universe RP plus separate manual RV refresh on protected copies.",
        "5. Only after those gates pass, take durable backups and run the production correction with a mandatory second NO_CHANGE.",
        "",
    ])
    text = "\n".join(lines)
    path = output / "phase13f2_prewrite_report.md"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "bytes": len(text.encode("utf-8"))}


def run_prewrite_audit(output: Path | None = None, *, paths: AuditPaths | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    paths = paths or AuditPaths()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    reject_production_path(output, "output")
    output.mkdir(parents=True, exist_ok=True)
    pre_inventory = production_inventory()
    storage_start = _storage("start")
    classification = classification_reconciliation(paths)
    eligibility = eligibility_audit(paths)
    listing = listing_population_audit(paths)
    normalized = normalized_mapping_review(classification["rows"])
    omissions = seven_classification_omissions(classification["rows"])
    areb = areb_date_aware_reconciliation(paths)
    blockers = []
    if normalized["unresolved_count"]:
        blockers.append(f"NORMALIZED_CLASSIFICATION_MAPPING_REVIEW_REQUIRED:{normalized['unresolved_count']}")
    if listing["unresolved_current_active_count"]:
        blockers.append(f"CURRENT_ACTIVE_LISTING_INTERVAL_UNRESOLVED:{listing['unresolved_current_active_count']}")
    if areb["rv_current_peer_eligible_defects"]:
        blockers.append(f"AREB_CURRENT_RV_PEER_ELIGIBLE_DEFECT:{areb['rv_current_peer_eligible_defects']}")
    if omissions["count"]:
        blockers.append(f"VALUATION_CLASSIFICATION_OMISSIONS_REQUIRE_PIPELINE_REBUILD:{omissions['count']}")
    logical = {
        "phase": PHASE,
        "classification": classification,
        "eligibility": eligibility,
        "listing_population": listing,
        "normalized_mapping_review": normalized,
        "seven_classification_omissions": omissions,
        "areb_date_aware": areb,
        "prewrite_blockers": blockers,
        "outcome": OUTCOME_B,
    }
    fingerprint = stable_hash(logical)
    _write_csv(output / "listing_population.csv", listing["rows"])
    _write_csv(output / "normalized_mapping_review.csv", normalized["rows"])
    _write_csv(output / "seven_classification_omissions.csv", omissions["rows"])
    _write_csv(output / "areb_rp_date_aware_rows.csv", areb["rp_rows"])
    write_json(output / "listing_population.json", listing)
    write_json(output / "normalized_mapping_review.json", normalized)
    write_json(output / "phase13f2_prewrite_result.json", {
        **logical,
        "determinism_fingerprint": fingerprint,
        "production_immutability": compare_production_inventory(pre_inventory, production_inventory()),
        "storage": {"start": storage_start, "final": _storage("final")},
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    })
    result = json.loads((output / "phase13f2_prewrite_result.json").read_text())
    result["report"] = render_report(output, result)
    write_json(output / "phase13f2_prewrite_result.json", result)
    return result
