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


PHASE = "PHASE13F1_CLASSIFICATION_CURRENT_UNIVERSE_RECONCILIATION"
DEFAULT_RUN_ID = "20260912T_PHASE13F1_CLASSIFICATION_RECONCILIATION"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13f1_reconciliation")
AREB_COMPANY_ID = 192
OUTCOME_A = "OUTCOME A — CLASSIFICATION AND CURRENT PEER ELIGIBILITY FULLY CONSISTENT"
OUTCOME_B = "OUTCOME B — CORRECTABLE CLASSIFICATION OR ELIGIBILITY DRIFT IDENTIFIED"
OUTCOME_C = "OUTCOME C — IDENTITY OR SOURCE CONTRACT BLOCKS SAFE CORRECTION"


@dataclass(frozen=True)
class AuditPaths:
    canonical: Path = PRODUCTION["canonical"]
    analysis: Path = PRODUCTION["analysis"]
    market: Path = PRODUCTION["market"]
    provider: Path = PRODUCTION["provider"]
    taxonomy: Path = PRODUCTION["taxonomy"]


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _normalize(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text.lower() if text else None


def _market(value: Any) -> str:
    text = str(value or "usa").strip().lower()
    return "usa" if text in {"", "nasdaq", "nyse", "nysemkt", "amex", "arca", "otc", "otcqx", "otcqb"} else text


def _storage(label: str) -> dict[str, Any]:
    usage = shutil.disk_usage("/home/kalle/projects/rawcandle")
    return {
        "label": label,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_gib": round(usage.free / (1024**3), 2),
    }


def _quick_checks(paths: AuditPaths) -> dict[str, dict[str, Any]]:
    output = {}
    for name, path in {
        "provider": paths.provider,
        "canonical": paths.canonical,
        "analysis": paths.analysis,
        "market": paths.market,
        "taxonomy": paths.taxonomy,
    }.items():
        with _readonly(path) as conn:
            output[name] = {
                "path": str(path),
                "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
                "foreign_key_check_rows": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
            }
    return output


def _active_universe(paths: AuditPaths) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with _readonly(paths.canonical) as conn:
        version = dict(conn.execute(
            "SELECT v.* FROM fundamentals_operational_universe_active_version a "
            "JOIN fundamentals_operational_universe_version v USING(universe_version_id)"
        ).fetchone())
        rows = [dict(row) for row in conn.execute(
            "SELECT m.*,c.company_key,c.company_name,s.exchange,s.active AS canonical_security_active,s.valid_from,s.valid_to "
            "FROM fundamentals_operational_universe_member m "
            "JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) "
            "LEFT JOIN company c ON c.company_id=m.company_id "
            "LEFT JOIN security s ON s.security_id=m.security_id "
            "ORDER BY m.membership_status,m.company_id,m.security_id"
        )]
    return version, rows


def _primary_active_securities(paths: AuditPaths, universe_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    with _readonly(paths.canonical) as conn:
        for row in universe_rows:
            status = str(row["membership_status"])
            if status == "ACTIVE_SINGLE_SECURITY":
                output.append(dict(row))
            elif status == "ACTIVE_MULTI_SECURITY":
                securities = [dict(item) for item in conn.execute(
                    "SELECT s.*,c.company_key,c.company_name FROM security s JOIN company c USING(company_id) "
                    "WHERE s.company_id=? AND s.active=1 ORDER BY s.current_ticker,s.security_id",
                    (row["company_id"],),
                )]
                for security in securities:
                    expanded = dict(row)
                    expanded.update({
                        "security_id": security["security_id"],
                        "current_ticker": security["current_ticker"],
                        "exchange": security["exchange"],
                        "canonical_security_active": security["active"],
                        "valid_from": security["valid_from"],
                        "valid_to": security["valid_to"],
                        "company_key": security["company_key"],
                        "company_name": security["company_name"],
                        "identity_resolution_status": "RESOLVED_ACTIVE_MULTI_SECURITY_COMPONENT",
                    })
                    output.append(expanded)
    return output


def _ticker_meta(paths: AuditPaths) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    with _readonly(paths.market) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT rowid AS ticker_meta_rowid,ticker,market,sector,industry FROM ticker_meta ORDER BY ticker,market,rowid"
        )]
    by_key = {(str(row["ticker"]).upper(), _market(row["market"])): row for row in rows}
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_ticker.setdefault(str(row["ticker"]).upper(), []).append(row)
    return by_key, by_ticker, rows


def _latest_valuation_classification(paths: AuditPaths) -> dict[int, dict[str, Any]]:
    with _readonly(paths.analysis) as conn:
        rows = [dict(row) for row in conn.execute(
            "WITH ranked AS ("
            "SELECT company_id,security_id,ticker,sector,industry,valuation_status,reason_code,fiscal_sequence,"
            "ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY fiscal_sequence DESC,valuation_revised_result_id DESC) rn "
            "FROM valuation_revised_result WHERE history_mode='REVISED_HISTORY'"
            ") SELECT * FROM ranked WHERE rn=1 ORDER BY company_id"
        )]
    return {int(row["company_id"]): row for row in rows}


def _active_rp_groups(paths: AuditPaths) -> dict[int, dict[str, Any]]:
    groups: dict[int, dict[str, Any]] = {}
    with _readonly(paths.analysis) as conn:
        for row in conn.execute(
            "SELECT r.company_id,r.measure,r.peer_scope,r.peer_group_id,r.result_status,r.peer_count,s.model_version,s.model_fingerprint "
            "FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) "
            "JOIN relative_position_snapshot s USING(snapshot_id) "
            "WHERE r.peer_scope IN ('SECTOR','INDUSTRY') ORDER BY r.company_id,r.measure,r.peer_scope,s.model_version"
        ):
            item = groups.setdefault(int(row["company_id"]), {"sector_groups": set(), "industry_groups": set(), "rows": 0})
            item["rows"] += 1
            if row["peer_scope"] == "SECTOR":
                item["sector_groups"].add(str(row["peer_group_id"]))
            elif row["peer_scope"] == "INDUSTRY":
                item["industry_groups"].add(str(row["peer_group_id"]))
    for item in groups.values():
        item["sector_groups"] = sorted(item["sector_groups"])
        item["industry_groups"] = sorted(item["industry_groups"])
    return groups


def _active_rv_groups(paths: AuditPaths) -> dict[int, dict[str, Any]]:
    groups: dict[int, dict[str, Any]] = {}
    with _readonly(paths.analysis) as conn:
        for row in conn.execute(
            "SELECT p.company_id,p.scope,p.group_id,p.status,p.peer_count "
            "FROM relative_valuation_peer_position p JOIN relative_valuation_active_snapshot a USING(snapshot_id) "
            "WHERE p.scope IN ('SECTOR','INDUSTRY') ORDER BY p.company_id,p.scope"
        ):
            item = groups.setdefault(int(row["company_id"]), {"sector_groups": set(), "industry_groups": set(), "rows": 0})
            item["rows"] += 1
            if row["scope"] == "SECTOR":
                item["sector_groups"].add(str(row["group_id"]))
            elif row["scope"] == "INDUSTRY":
                item["industry_groups"].add(str(row["group_id"]))
    for item in groups.values():
        item["sector_groups"] = sorted(item["sector_groups"])
        item["industry_groups"] = sorted(item["industry_groups"])
    return groups


def classification_reconciliation(paths: AuditPaths) -> dict[str, Any]:
    version, universe_rows = _active_universe(paths)
    meta_by_key, meta_by_ticker, meta_rows = _ticker_meta(paths)
    valuation = _latest_valuation_classification(paths)
    rp_groups = _active_rp_groups(paths)
    rv_groups = _active_rv_groups(paths)
    primary = _primary_active_securities(paths, universe_rows)
    output_rows = []
    for row in primary:
        ticker = str(row["current_ticker"] or "").upper()
        market = _market(row["market"])
        meta = meta_by_key.get((ticker, market))
        same_ticker = meta_by_ticker.get(ticker, [])
        ambiguity = len([item for item in same_ticker if _market(item["market"]) == market]) > 1
        valuation_row = valuation.get(int(row["company_id"]), {})
        rp = rp_groups.get(int(row["company_id"]), {})
        rv = rv_groups.get(int(row["company_id"]), {})
        raw_sector = meta.get("sector") if meta else None
        raw_industry = meta.get("industry") if meta else None
        required = []
        affected = []
        if meta is None:
            status = "MISSING_TICKER_META_ROW" if same_ticker else "NO_TICKER_META_FOR_TICKER"
            required.append("resolve ticker_meta identity before classification-dependent rebuild")
            affected.extend(["valuation_applicability", "relative_position_groups", "relative_valuation_groups", "snapshot_presentation"])
        elif ambiguity:
            status = "AMBIGUOUS_TICKER_MARKET_MATCH"
            required.append("deduplicate ticker_meta ticker+market rows")
        elif raw_sector in (None, "") or raw_industry in (None, ""):
            status = "INCOMPLETE_TICKER_META_CLASSIFICATION"
            required.append("populate ticker_meta sector/industry from authorized source")
        else:
            status = "CLASSIFICATION_READY"
        valuation_exact = (
            valuation_row.get("sector") == raw_sector and valuation_row.get("industry") == raw_industry
            if meta else False
        )
        rp_sector_groups = rp.get("sector_groups", [])
        rp_industry_groups = rp.get("industry_groups", [])
        rv_sector_groups = rv.get("sector_groups", [])
        rv_industry_groups = rv.get("industry_groups", [])
        rp_exact = (
            (not rp_sector_groups or raw_sector in rp_sector_groups)
            and (not rp_industry_groups or raw_industry in rp_industry_groups)
            if meta else False
        )
        rv_exact = (
            (not rv_sector_groups or raw_sector in rv_sector_groups)
            and (not rv_industry_groups or raw_industry in rv_industry_groups)
            if meta else False
        )
        exact = bool(meta and status == "CLASSIFICATION_READY" and valuation_exact and rp_exact and rv_exact)
        normalized = bool(meta and _normalize(valuation_row.get("sector")) == _normalize(raw_sector) and _normalize(valuation_row.get("industry")) == _normalize(raw_industry))
        if meta and status == "CLASSIFICATION_READY" and not valuation_exact:
            required.append("rebuild valuation-derived classification fields")
            affected.extend(["valuation_revised_result", "relative_position_source", "relative_valuation_source", "snapshot"])
        if meta and status == "CLASSIFICATION_READY" and not rp_exact:
            required.append("rebuild Relative Position groups")
            affected.append("relative_position")
        if meta and status == "CLASSIFICATION_READY" and not rv_exact:
            required.append("refresh Relative Valuation groups")
            affected.append("relative_valuation")
        output_rows.append({
            "company_id": row["company_id"],
            "company_key": row["company_key"],
            "company_name": row["company_name"],
            "security_id": row["security_id"],
            "current_ticker": row["current_ticker"],
            "market": market,
            "exchange": row["exchange"],
            "active_universe_status": row["membership_status"],
            "identity_resolution_status": row["identity_resolution_status"],
            "canonical_security_active": row["canonical_security_active"],
            "ticker_meta_rowid": meta.get("ticker_meta_rowid") if meta else None,
            "ticker_meta_sector_raw": raw_sector,
            "ticker_meta_industry_raw": raw_industry,
            "ticker_meta_sector_normalized": _normalize(raw_sector),
            "ticker_meta_industry_normalized": _normalize(raw_industry),
            "valuation_sector": valuation_row.get("sector"),
            "valuation_industry": valuation_row.get("industry"),
            "rp_sector_groups": rp.get("sector_groups", []),
            "rp_industry_groups": rp.get("industry_groups", []),
            "rv_sector_groups": rv.get("sector_groups", []),
            "rv_industry_groups": rv.get("industry_groups", []),
            "exact_match_status": "EXACT_MATCH" if exact else "NOT_EXACT_MATCH",
            "normalized_match_status": "NORMALIZED_MATCH" if normalized else "NOT_NORMALIZED_MATCH",
            "missing_ambiguous_status": status,
            "classification_source": "data/osakedata.db.ticker_meta",
            "required_correction": "; ".join(dict.fromkeys(required)) or "NONE",
            "affected_downstream_layers": sorted(set(affected)),
        })
    canonical_keys = {(str(row["current_ticker"]).upper(), _market(row["market"])) for row in universe_rows if row["current_ticker"]}
    orphan_meta = [
        row for row in meta_rows
        if (str(row["ticker"]).upper(), _market(row["market"])) not in canonical_keys
    ]
    summary = {
        "active_universe_version": version,
        "total_universe_members": len(universe_rows),
        "primary_active_security_rows": len(primary),
        "ticker_meta_rows": len(meta_rows),
        "ticker_meta_rows_without_current_ou_match": len(orphan_meta),
        "exact_matches": sum(row["exact_match_status"] == "EXACT_MATCH" for row in output_rows),
        "normalized_only_matches": sum(row["exact_match_status"] != "EXACT_MATCH" and row["normalized_match_status"] == "NORMALIZED_MATCH" for row in output_rows),
        "sector_mismatches": sum(row["ticker_meta_sector_raw"] is not None and row["valuation_sector"] != row["ticker_meta_sector_raw"] for row in output_rows),
        "industry_mismatches": sum(row["ticker_meta_industry_raw"] is not None and row["valuation_industry"] != row["ticker_meta_industry_raw"] for row in output_rows),
        "both_mismatching": sum(
            row["ticker_meta_sector_raw"] is not None and row["ticker_meta_industry_raw"] is not None
            and row["valuation_sector"] != row["ticker_meta_sector_raw"]
            and row["valuation_industry"] != row["ticker_meta_industry_raw"]
            for row in output_rows
        ),
        "missing_sector": sum(row["ticker_meta_sector_raw"] in (None, "") for row in output_rows),
        "missing_industry": sum(row["ticker_meta_industry_raw"] in (None, "") for row in output_rows),
        "missing_ticker_meta_row": sum(row["missing_ambiguous_status"] in {"MISSING_TICKER_META_ROW", "NO_TICKER_META_FOR_TICKER"} for row in output_rows),
        "ambiguous_ticker_market_match": sum(row["missing_ambiguous_status"] == "AMBIGUOUS_TICKER_MARKET_MATCH" for row in output_rows),
        "unresolved_stable_identity": sum("UNRESOLVED" in str(row["identity_resolution_status"]) for row in output_rows),
    }
    return {
        "summary": summary,
        "rows": output_rows,
        "orphan_ticker_meta_sample": orphan_meta[:100],
        "fingerprint": stable_hash({"summary": summary, "rows": output_rows}),
    }


def eligibility_audit(paths: AuditPaths) -> dict[str, Any]:
    _version, universe_rows = _active_universe(paths)
    primary = _primary_active_securities(paths, universe_rows)
    with _readonly(paths.provider) as conn:
        provider_rows = {
            str(row["ticker"]).upper(): dict(row)
            for row in conn.execute(
                "SELECT ticker,permaticker,name,exchange,isdelisted,category,firstpricedate,lastpricedate "
                "FROM sharadar_ticker_metadata WHERE table_name='fundamentals' ORDER BY ticker"
            )
        }
    with _readonly(paths.market) as conn:
        prices = {
            str(row["ticker"]).upper(): dict(row)
            for row in conn.execute(
                "SELECT UPPER(osake) ticker,market,MIN(pvm) first_ohlc_date,MAX(pvm) latest_ohlc_date,COUNT(*) ohlc_rows "
                "FROM osakedata GROUP BY UPPER(osake),market ORDER BY ticker,market"
            )
        }
    anomalies = []
    for row in primary:
        ticker = str(row["current_ticker"]).upper()
        provider = provider_rows.get(ticker)
        price = prices.get(ticker)
        reasons = []
        if provider and provider.get("isdelisted") == "Y":
            reasons.append("PROVIDER_DELISTED")
        if int(row["canonical_security_active"] or 0) != 1:
            reasons.append("CANONICAL_SECURITY_INACTIVE")
        category = str(provider.get("category") if provider else "")
        if provider and "Common Stock" not in category:
            reasons.append("UNSUPPORTED_OR_REVIEW_SECURITY_TYPE")
        if price is None:
            reasons.append("NO_LOCAL_OHLC")
        elif str(price["latest_ohlc_date"]) < "2026-08-29":
            reasons.append("LOCAL_PRICE_HISTORY_STALE_ENDED")
        if reasons:
            anomalies.append({
                "company_id": row["company_id"],
                "security_id": row["security_id"],
                "ticker": row["current_ticker"],
                "market": _market(row["market"]),
                "membership_status": row["membership_status"],
                "canonical_security_active": row["canonical_security_active"],
                "provider": provider,
                "local_price": price,
                "reasons": reasons,
            })
    return {
        "primary_active_security_rows": len(primary),
        "anomaly_count": len(anomalies),
        "reason_counts": {
            reason: sum(reason in row["reasons"] for row in anomalies)
            for reason in sorted({reason for row in anomalies for reason in row["reasons"]})
        },
        "rows": anomalies,
        "fingerprint": stable_hash(anomalies),
    }


def _rank_after_removal(rows: Sequence[Mapping[str, Any]], removed_company_id: int) -> dict[int, dict[str, Any]]:
    kept = [row for row in rows if int(row["company_id"]) != removed_company_id]
    ordered = sorted(kept, key=lambda row: (float(row["source_score"]), int(row["company_id"])))
    output: dict[int, dict[str, Any]] = {}
    n = len(ordered)
    for index, row in enumerate(ordered, 1):
        score = float(row["source_score"])
        lows = [i for i, candidate in enumerate(ordered, 1) if float(candidate["source_score"]) == score]
        rank_low = min(lows)
        rank_high = max(lows)
        average = (rank_low + rank_high) / 2
        percentile = None if n <= 1 else 100 * (average - 1) / (n - 1)
        output[int(row["company_id"])] = {"peer_count": n, "rank_low": rank_low, "rank_high": rank_high, "average_rank": average, "percentile": percentile}
    return output


def areb_relative_position_audit(paths: AuditPaths) -> dict[str, Any]:
    with _readonly(paths.analysis) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT s.model_version,s.model_fingerprint,s.snapshot_date,r.* "
            "FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) "
            "JOIN relative_position_snapshot s USING(snapshot_id) WHERE r.company_id=? "
            "ORDER BY s.model_version,r.measure,r.peer_scope,r.peer_group_id",
            (AREB_COMPANY_ID,),
        )]
        changed_groups = []
        for row in rows:
            if row["result_status"] != "RELATIVE_POSITION_READY":
                continue
            peers = [dict(peer) for peer in conn.execute(
                "SELECT company_id,source_score,percentile,rank_low,rank_high,average_rank,peer_count "
                "FROM relative_position_result WHERE snapshot_id=? AND measure=? AND peer_scope=? AND peer_group_id=? "
                "AND result_status='RELATIVE_POSITION_READY' ORDER BY source_score,company_id",
                (row["snapshot_id"], row["measure"], row["peer_scope"], row["peer_group_id"]),
            )]
            recalculated = _rank_after_removal(peers, AREB_COMPANY_ID)
            changed = sum(
                peer["company_id"] in recalculated and (
                    int(peer["peer_count"]) != recalculated[int(peer["company_id"])]["peer_count"]
                    or float(peer["average_rank"]) != recalculated[int(peer["company_id"])]["average_rank"]
                    or peer["percentile"] != recalculated[int(peer["company_id"])]["percentile"]
                )
                for peer in peers
                if int(peer["company_id"]) != AREB_COMPANY_ID
            )
            changed_groups.append({
                "snapshot_id": row["snapshot_id"],
                "model_version": row["model_version"],
                "measure": row["measure"],
                "peer_scope": row["peer_scope"],
                "peer_group_id": row["peer_group_id"],
                "original_peer_count": row["peer_count"],
                "peer_rows_if_areb_removed": max(0, int(row["peer_count"]) - 1),
                "other_company_rows_changed": changed,
            })
    ready_rows = [row for row in rows if row["result_status"] == "RELATIVE_POSITION_READY"]
    return {
        "active_rows": rows,
        "active_row_count": len(rows),
        "ready_row_count": len(ready_rows),
        "conclusion": "PRODUCTION_DEFECT_AREB_PARTICIPATES_IN_CURRENT_RELATIVE_POSITION" if ready_rows else "HARMLESS_STORED_NON_READY_EVIDENCE",
        "changed_groups": changed_groups,
        "affected_other_company_rows": sum(row["other_company_rows_changed"] for row in changed_groups),
        "fingerprint": stable_hash({"rows": rows, "changed_groups": changed_groups}),
    }


def areb_relative_valuation_audit(paths: AuditPaths) -> dict[str, Any]:
    with _readonly(paths.analysis) as conn:
        company = [dict(row) for row in conn.execute(
            "SELECT s.as_of_date,s.model_version,s.model_fingerprint,c.* FROM relative_valuation_company_result c "
            "JOIN relative_valuation_active_snapshot a USING(snapshot_id) JOIN relative_valuation_snapshot s USING(snapshot_id) "
            "WHERE c.company_id=? ORDER BY c.snapshot_id",
            (AREB_COMPANY_ID,),
        )]
        peers = [dict(row) for row in conn.execute(
            "SELECT p.* FROM relative_valuation_peer_position p JOIN relative_valuation_active_snapshot a USING(snapshot_id) "
            "WHERE p.company_id=? ORDER BY p.scope,p.group_id",
            (AREB_COMPANY_ID,),
        )]
        changed_groups = []
        for row in peers:
            if row["status"] != "RELATIVE_POSITION_READY":
                continue
            group = [dict(peer) for peer in conn.execute(
                "SELECT company_id,source_score,percentile,rank_low,rank_high,average_rank,peer_count "
                "FROM relative_valuation_peer_position WHERE snapshot_id=? AND scope=? AND group_id=? "
                "AND status='RELATIVE_POSITION_READY' ORDER BY source_score,company_id",
                (row["snapshot_id"], row["scope"], row["group_id"]),
            )]
            recalculated = _rank_after_removal(group, AREB_COMPANY_ID)
            changed = sum(
                peer["company_id"] in recalculated and (
                    int(peer["peer_count"]) != recalculated[int(peer["company_id"])]["peer_count"]
                    or float(peer["average_rank"]) != recalculated[int(peer["company_id"])]["average_rank"]
                    or peer["percentile"] != recalculated[int(peer["company_id"])]["percentile"]
                )
                for peer in group
                if int(peer["company_id"]) != AREB_COMPANY_ID
            )
            changed_groups.append({
                "snapshot_id": row["snapshot_id"],
                "scope": row["scope"],
                "group_id": row["group_id"],
                "original_peer_count": row["peer_count"],
                "peer_rows_if_areb_removed": max(0, int(row["peer_count"]) - 1),
                "other_company_rows_changed": changed,
            })
    peer_ready = [row for row in peers if row["status"] == "RELATIVE_POSITION_READY"]
    return {
        "company_rows": company,
        "peer_rows": peers,
        "company_row_count": len(company),
        "peer_ready_count": len(peer_ready),
        "conclusion": "PRODUCTION_DEFECT_AREB_PARTICIPATES_IN_CURRENT_RELATIVE_VALUATION" if peer_ready else "HARMLESS_STORED_NON_READY_EVIDENCE",
        "changed_groups": changed_groups,
        "affected_other_company_rows": sum(row["other_company_rows_changed"] for row in changed_groups),
        "fingerprint": stable_hash({"company": company, "peers": peers, "changed_groups": changed_groups}),
    }


def dependency_matrix() -> list[dict[str, Any]]:
    return [
        {"consumer": "Onboarding preview/eligibility", "current_source": "identity + market evidence + ticker_meta audit", "required_source": "ticker_meta by security ticker+market", "compliance": "COMPLIANT_AFTER_PHASE13F", "fallback_behavior": "review required", "missing_ambiguous_behavior": "not ready", "economic_change": "eligibility only", "rebuild_scope": "OU/dependency fingerprints if corrected"},
        {"consumer": "Fundamental Score", "current_source": "financial statements only", "required_source": "not classification-dependent", "compliance": "NOT_APPLICABLE", "fallback_behavior": "none", "missing_ambiguous_behavior": "no effect", "economic_change": False, "rebuild_scope": "none"},
        {"consumer": "Diagnostic applicability", "current_source": "diagnostic source endpoints and applicability ids", "required_source": "ticker_meta where classification-dependent", "compliance": "REVIEW_REQUIRED", "fallback_behavior": "explicit applicability status", "missing_ambiguous_behavior": "not applicable/not ready", "economic_change": "possible status changes", "rebuild_scope": "diagnostic endpoints/evaluations"},
        {"consumer": "Lifecycle", "current_source": "fundamental trends", "required_source": "not ordinary sector/industry", "compliance": "NOT_APPLICABLE_BY_CODE_INSPECTION", "fallback_behavior": "none", "missing_ambiguous_behavior": "no effect", "economic_change": False, "rebuild_scope": "none"},
        {"consumer": "Absolute Valuation", "current_source": "ticker_meta via valuation source loader", "required_source": "ticker_meta by ticker+market", "compliance": "COMPLIANT_AFTER_PHASE13F", "fallback_behavior": "VALUATION_NOT_READY", "missing_ambiguous_behavior": "CLASSIFICATION_NOT_READY", "economic_change": "only applicability/status", "rebuild_scope": "valuation if classification drift exists"},
        {"consumer": "Relative Position", "current_source": "ticker_meta resolver + active package rows", "required_source": "ticker_meta by ticker+market and current eligibility", "compliance": "ELIGIBILITY_DEFECT_FOUND_FOR_AREB", "fallback_behavior": "classification missing coverage row", "missing_ambiguous_behavior": "PEER_CLASSIFICATION_MISSING", "economic_change": "peer denominators/ranks", "rebuild_scope": "full-universe RP"},
        {"consumer": "Relative Valuation", "current_source": "ticker_meta resolver + RV active snapshot", "required_source": "ticker_meta by ticker+market and current eligibility", "compliance": "ELIGIBILITY_DEFECT_FOUND_FOR_AREB", "fallback_behavior": "peer status rows", "missing_ambiguous_behavior": "no peer group", "economic_change": "peer denominators/ranks", "rebuild_scope": "manual full RV refresh"},
        {"consumer": "Snapshot V2/UI", "current_source": "active RP/RV readers", "required_source": "active eligible company only for current reports", "compliance": "READER_REVIEW_REQUIRED_FOR_DELISTED_TICKER_SELECTION", "fallback_behavior": "unavailable if row missing", "missing_ambiguous_behavior": "no classification claim", "economic_change": "presentation and peer blocks", "rebuild_scope": "Snapshot verification after RP/RV refresh"},
    ]


def render_report(output: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    lines = [
        "# Phase 13F.1 Classification And Current-Universe Reconciliation",
        "",
        f"Outcome: **{result['outcome']}**",
        "",
        "## Summary",
        "",
        f"- Primary active OU security rows: `{result['classification']['summary']['primary_active_security_rows']}`",
        f"- Total active OU version member rows: `{result['classification']['summary']['total_universe_members']}`",
        f"- Exact classification matches: `{result['classification']['summary']['exact_matches']}`",
        f"- Missing ticker_meta rows: `{result['classification']['summary']['missing_ticker_meta_row']}`",
        f"- Eligibility anomalies: `{result['eligibility']['anomaly_count']}`",
        f"- AREB RP conclusion: `{result['areb_relative_position']['conclusion']}`",
        f"- AREB RV conclusion: `{result['areb_relative_valuation']['conclusion']}`",
        "",
        "## Phase 13F.2 Plan",
        "",
        "1. Take production backups and preflight quick_check/foreign_key_check for provider, canonical, analysis, market and taxonomy.",
        "2. Correct current eligibility by transitioning delisted/inactive active-OU anomalies to historical/ineligible membership in a protected transaction.",
        "3. Preserve ticker_meta as the only sector/industry source; correct only rows listed in the reconciliation artifact.",
        "4. Rebuild classification-dependent diagnostics where applicability changes.",
        "5. Rebuild full-universe Relative Position because peer denominators and ranks are cross-sectional.",
        "6. Run the separate manual full-universe Relative Valuation refresh after RP activation.",
        "7. Verify Snapshot/UI no longer selects delisted current companies and then run mandatory second NO_CHANGE.",
        "8. Validate production immutability boundaries and rollback from backups if any gate fails.",
        "",
        "Historical limitation: `ticker_meta` is authoritative for current production classification but is not PIT-versioned.",
        "",
    ]
    path = output / "phase13f1_reconciliation_report.md"
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "bytes": len(text.encode("utf-8"))}


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value for key, value in row.items()})


def run_audit(output: Path | None = None, *, paths: AuditPaths | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    paths = paths or AuditPaths()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    reject_production_path(output, "output")
    output.mkdir(parents=True, exist_ok=True)
    pre_inventory = production_inventory()
    storage_start = _storage("start")
    pre_checks = _quick_checks(paths)
    classification = classification_reconciliation(paths)
    eligibility = eligibility_audit(paths)
    rp = areb_relative_position_audit(paths)
    rv = areb_relative_valuation_audit(paths)
    dependencies = dependency_matrix()
    defects = (
        classification["summary"]["missing_ticker_meta_row"]
        + classification["summary"]["ambiguous_ticker_market_match"]
        + eligibility["anomaly_count"]
        + (1 if rp["conclusion"].startswith("PRODUCTION_DEFECT") else 0)
        + (1 if rv["conclusion"].startswith("PRODUCTION_DEFECT") else 0)
    )
    outcome = OUTCOME_B if defects else OUTCOME_A
    if classification["summary"]["unresolved_stable_identity"]:
        outcome = OUTCOME_C
    logical = {
        "phase": PHASE,
        "classification": classification,
        "eligibility": eligibility,
        "areb_relative_position": rp,
        "areb_relative_valuation": rv,
        "dependency_matrix": dependencies,
        "outcome": outcome,
    }
    fingerprint = stable_hash(logical)
    _write_csv(output / "classification_reconciliation.csv", classification["rows"])
    _write_csv(output / "eligibility_anomalies.csv", eligibility["rows"])
    write_json(output / "classification_reconciliation.json", classification)
    write_json(output / "eligibility_audit.json", eligibility)
    write_json(output / "areb_relative_position_audit.json", rp)
    write_json(output / "areb_relative_valuation_audit.json", rv)
    post_checks = _quick_checks(paths)
    post_inventory = production_inventory()
    report_stub = {
        **logical,
        "determinism_fingerprint": fingerprint,
        "production_immutability": compare_production_inventory(pre_inventory, post_inventory),
    }
    report = render_report(output, report_stub)
    result = {
        **report_stub,
        "artifact_dir": str(output),
        "preflight_checks": pre_checks,
        "postflight_checks": post_checks,
        "production_immutability": compare_production_inventory(pre_inventory, post_inventory),
        "storage": {"start": storage_start, "final": _storage("final")},
        "report": report,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(output / "phase13f1_result.json", result)
    return result
