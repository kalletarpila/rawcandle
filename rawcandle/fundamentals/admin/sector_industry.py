from __future__ import annotations

import json
import fcntl
import os
import re
import sqlite3
import shutil
import subprocess
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ADMIN_TEMP_ROOT, AdminRunWriter, stable_run_id
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.batch_add_tickers import (
    BatchAddTickerPaths,
    PRODUCTION_BACKUP_ROOT,
    PRODUCTION_LOCK_PATH,
    _background_heartbeat,
    cleanup_copy_lane,
    create_copy_lane,
    disk_hygiene_snapshot,
    validate_exact_production_paths,
)
from rawcandle.fundamentals.admin.contracts import (
    AdminBatchRequest,
    AdminFinalResult,
    AdminItemDecision,
    AdminOperationType,
    AdminStatus,
    RunStage,
    build_batch_request,
    fingerprint,
    utc_now,
)
from rawcandle.fundamentals.admin.progress import (
    ProgressCallback,
    ProgressStage,
    ProgressTracker,
    SECTOR_INDUSTRY_STAGES,
)
from rawcandle.fundamentals.admin.reporting import render_markdown_report
from rawcandle.fundamentals.admin.rv_identity import active_relative_valuation_identity
from rawcandle.fundamentals.operating_income_v2 import activation
from rawcandle.fundamentals.operating_income_v2 import valuation as valuation_engine
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import load_active_dc_memberships
from rawcandle.fundamentals.phase12d import PRODUCTION, ROOT, database_inventory, sha256, stable_hash, write_json
from rawcandle.fundamentals.phase12d import production_inventory
from rawcandle.fundamentals.phase13b_foundation import (
    database_fingerprint,
    reject_production_path,
)
from rawcandle.fundamentals.phase13f3_ticker_transition import REPORT_DATE
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


PHASE = "PHASE13G3_CHECK_UPDATE_SECTOR_INDUSTRY"
CONTRACT_VERSION = "PHASE13G3_CHECK_UPDATE_SECTOR_INDUSTRY_COPY_ONLY_V1"
OUTCOME_A = "OUTCOME A - INDEPENDENT SECTOR AND INDUSTRY CLI VERIFIED COPY-ONLY AND READY FOR SEPARATELY AUTHORIZED PRODUCTION DEPLOYMENT"
OUTCOME_B = "OUTCOME B - CORRECTABLE CLASSIFICATION, IDENTITY, STRUCTURAL-SCOPE OR DOWNSTREAM GAP REMAINS; PRODUCTION UNCHANGED"
OUTCOME_C = "OUTCOME C - MATERIAL ARCHITECTURE OR SAFETY DEFECT; PRODUCTION UNCHANGED"
PRODUCTION_OUTCOME_A = "OUTCOME A - PROTECTED SECTOR/INDUSTRY PRODUCTION MODE READY; PRODUCTION VERIFIED NO_CHANGE"
PRODUCTION_OUTCOME_B = "OUTCOME B - PRE-WRITE DATA OR ACCEPTANCE DRIFT; PRODUCTION UNCHANGED"
PRODUCTION_OUTCOME_C = "OUTCOME C - MATERIAL WRITE-PATH OR ROLLBACK DEFECT; PRODUCTION UNCHANGED OR RESTORED"
WRITE_ROLES = ("analysis",)
READONLY_ROLES = ("provider", "canonical", "market", "taxonomy")
TEMP_ROOT = ROOT / "temp" / "fundamentals_admin_phase13g3_sector_industry"
PRODUCTION_TEMP_ROOT = ROOT / "temp" / "fundamentals_admin_phase13g3_2_sector_industry"

ACCEPTED_PHASE13G31_COUNTS = {
    "denominator": 2453,
    "EXACT_MATCH": 2440,
    "IDENTITY_REVIEW_REQUIRED": 11,
    "NOT_APPLICABLE": 2,
    "correctable": 0,
}
ACCEPTED_PHASE13G31_REVIEW_TICKERS = {
    "CENT,CENTA",
    "FOX,FOXA",
    "FWONA,FWONK",
    "GOOG,GOOGL",
    "LBTYA,LBTYK",
    "LILA,LILAK",
    "LLYVA,LLYVK",
    "METC,METCB",
    "NWS,NWSA",
    "UA,UAA",
    "Z,ZG",
}
ACCEPTED_PHASE13G31_NOT_APPLICABLE_TICKERS = {"BATRK", "BELFB"}
ACCEPTED_PHASE13G31_EXACT_TICKERS = {"SNDK", "AG", "ALOY", "ARM", "ASML", "ASX", "BABA", "BHP", "BIDU", "BTDR", "CAMT"}

SAFE_CORRECTABLE_DECISIONS = {"CHANGE_REQUIRED", "MISSING_PERSISTED_CLASSIFICATION"}
NO_CHANGE_DECISIONS = {"EXACT_MATCH", "NORMALIZED_EQUIVALENT", "NO_CHANGE"}


@dataclass(frozen=True)
class SectorIndustryPlan:
    contract_version: str
    created_at_utc: str
    source_state: Mapping[str, Any]
    request: Mapping[str, Any]
    denominator_count: int
    inspected_count: int
    items: tuple[Mapping[str, Any], ...]

    @property
    def correctable_items(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(item for item in self.items if item.get("safe_to_apply"))

    def safe_dict(self) -> dict[str, Any]:
        payload = {
            "contract_version": self.contract_version,
            "created_at_utc": self.created_at_utc,
            "source_state": dict(self.source_state),
            "request": dict(self.request),
            "denominator_count": self.denominator_count,
            "inspected_count": self.inspected_count,
            "items": [dict(item) for item in self.items],
        }
        payload["correctable_count"] = len(self.correctable_items)
        payload["plan_fingerprint"] = stable_hash(payload)
        return payload


def parse_sector_industry_request(raw: str | Sequence[str], *, market: str | None = "usa") -> AdminBatchRequest:
    return build_batch_request(
        AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY,
        raw,
        market=market,
        options={"contract_version": CONTRACT_VERSION, "filter_mode": bool(" ".join(raw) if isinstance(raw, (list, tuple)) else raw)},
    )


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _semantic_key(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    return re.sub(r"[^a-z0-9]+", "", text.lower()) or None


def _market_from_exchange(exchange: Any) -> str | None:
    value = str(exchange or "").strip().upper()
    if value in {"NASDAQ", "NYSE", "NYSEMKT", "AMEX", "BATS", "IEX"}:
        return "usa"
    return value.lower() or None


def _active_universe(paths: BatchAddTickerPaths) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with _readonly(paths.canonical_db) as conn:
        if not _table_exists(conn, "fundamentals_operational_universe_active_version"):
            rows = [dict(row) for row in conn.execute(
                "SELECT c.company_id,s.security_id,s.current_ticker,LOWER(COALESCE(s.exchange,'usa')) market,'ACTIVE' membership_status,"
                "1 active_security_count,1 all_security_count,s.valid_from effective_start_date,s.valid_to effective_end_date "
                "FROM security s JOIN company c USING(company_id) WHERE s.active=1 ORDER BY s.current_ticker,s.security_id"
            )]
            return rows, {"source": "security_active_fallback", "universe_version_id": None}
        active = conn.execute("SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1").fetchone()
        if active is None:
            return [], {"source": "operational_universe", "universe_version_id": None}
        universe_version_id = str(active["universe_version_id"])
        rows = [dict(row) for row in conn.execute(
            "SELECT m.*,s.exchange,s.active security_active,c.company_name "
            "FROM fundamentals_operational_universe_member m "
            "LEFT JOIN security s USING(security_id) "
            "LEFT JOIN company c USING(company_id) "
            "WHERE m.universe_version_id=? AND m.membership_status LIKE 'ACTIVE%' "
            "ORDER BY m.current_ticker,m.security_id",
            (universe_version_id,),
        )]
    for row in rows:
        row["market"] = str(row.get("market") or _market_from_exchange(row.get("exchange")) or "usa").lower()
    return rows, {"source": "operational_universe", "universe_version_id": universe_version_id}


def _aliases(paths: BatchAddTickerPaths) -> dict[str, set[int]]:
    with _readonly(paths.canonical_db) as conn:
        if not _table_exists(conn, "ticker_alias"):
            return {}
        rows = [dict(row) for row in conn.execute(
            "SELECT UPPER(a.ticker) ticker,s.company_id FROM ticker_alias a JOIN security s USING(security_id)"
        )]
    aliases: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        aliases[str(row["ticker"]).upper()].add(int(row["company_id"]))
    return aliases


def _source_classifications(paths: BatchAddTickerPaths) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], str]:
    with _readonly(paths.market_db) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT UPPER(ticker) ticker,LOWER(COALESCE(market,'usa')) market,sector,industry "
            "FROM ticker_meta ORDER BY UPPER(ticker),LOWER(COALESCE(market,'usa')),sector,industry"
        )]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["ticker"]).upper(), str(row["market"]).lower())].append(row)
    return grouped, stable_hash(rows)


def _valuation_groups(paths: BatchAddTickerPaths) -> dict[tuple[int, int], dict[str, Any]]:
    with _readonly(paths.analysis_db) as conn:
        if not _table_exists(conn, "valuation_revised_result"):
            return {}
        rows = [dict(row) for row in conn.execute(
            "SELECT company_id,security_id,COUNT(*) row_count,"
            "SUM(CASE WHEN sector IS NULL OR TRIM(sector)='' OR industry IS NULL OR TRIM(industry)='' THEN 1 ELSE 0 END) null_rows "
            "FROM valuation_revised_result GROUP BY company_id,security_id"
        )]
        values = [dict(row) for row in conn.execute(
            "SELECT company_id,security_id,sector,industry,COUNT(*) row_count FROM valuation_revised_result "
            "GROUP BY company_id,security_id,sector,industry ORDER BY company_id,security_id,sector,industry"
        )]
    grouped: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (int(row["company_id"]), int(row["security_id"]))
        grouped[key] = {"row_count": int(row["row_count"]), "null_rows": int(row["null_rows"]), "values": []}
    for row in values:
        key = (int(row["company_id"]), int(row["security_id"]))
        grouped.setdefault(key, {"row_count": 0, "null_rows": 0, "values": []})["values"].append({
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "row_count": int(row["row_count"]),
        })
    return grouped


def _stable_keyed_rows(grouped: Mapping[Any, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in grouped.items():
        if isinstance(key, tuple):
            row_key = list(key)
        else:
            row_key = key
        rows.append({"key": row_key, "value": value})
    return sorted(rows, key=lambda row: json.dumps(row["key"], sort_keys=True, default=str))


def _logical_database_fingerprint(path: Path) -> dict[str, Any]:
    db = database_fingerprint(path)
    return {
        "schema_hash": db["schema_hash"],
        "row_counts": db["row_counts"],
        "quick_check": db["quick_check"],
        "foreign_key_violations": db["foreign_key_violations"],
        "fingerprint": db["fingerprint"],
    }


def _structural_companies(paths: BatchAddTickerPaths) -> dict[int, list[dict[str, Any]]]:
    with _readonly(paths.canonical_db) as conn:
        if not _table_exists(conn, "fundamentals_economic_structural_event"):
            return {}
        rows = [dict(row) for row in conn.execute(
            "SELECT company_id,event_id,event_type,event_date,comparability_status,review_status,effective_date "
            "FROM fundamentals_economic_structural_event ORDER BY company_id,event_id"
        )]
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["company_id"])].append(row)
    return grouped


def _active_identities(paths: BatchAddTickerPaths) -> dict[str, Any]:
    with _readonly(paths.analysis_db) as conn:
        package = {}
        try:
            package = activation.assert_v2_active(conn).__dict__
        except Exception:
            package = {"status": "NOT_ACTIVE"}
        rp = [dict(row) for row in conn.execute(
            "SELECT model_fingerprint,snapshot_id,activated_at_utc FROM relative_position_active_snapshot ORDER BY model_fingerprint"
        )] if _table_exists(conn, "relative_position_active_snapshot") else []
    rv = active_relative_valuation_identity(paths.analysis_db)
    return {
        "operating_income_package": package,
        "active_relative_position": rp,
        "active_relative_valuation": {key: value for key, value in rv.items() if key != "database_path"},
    }


def source_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    _, classification_fp = _source_classifications(paths)
    universe, universe_meta = _active_universe(paths)
    valuation = _valuation_groups(paths)
    structural = _structural_companies(paths)
    with _readonly(paths.taxonomy_db) as taxonomy_conn:
        has_taxonomy_schema = all(_table_exists(taxonomy_conn, table) for table in ("ec_ecosystem", "ec_taxonomy_version", "ec_entity", "ec_membership"))
    active_taxonomy = load_active_dc_memberships(paths.taxonomy_db, paths.canonical_db)[1] if has_taxonomy_schema else None
    return {
        "contract_version": CONTRACT_VERSION,
        "databases": {role: _logical_database_fingerprint(path) for role, path in paths.as_dict().items()},
        "classification_source_fingerprint": classification_fp,
        "operational_universe": universe_meta | {"fingerprint": stable_hash(universe), "member_count": len(universe)},
        "affected_persisted_classification_fingerprint": stable_hash(_stable_keyed_rows(valuation)),
        "structural_fingerprint": stable_hash(_stable_keyed_rows(structural)),
        "active_identities": _active_identities(paths),
        "active_taxonomy": active_taxonomy,
    }


def _classify_item(
    member: Mapping[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
    valuation: Mapping[str, Any] | None,
    structural_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ticker = str(member["current_ticker"]).upper()
    market = str(member.get("market") or "usa").lower()
    company_id = int(member["company_id"])
    security_id = int(member["security_id"]) if member.get("security_id") is not None else None
    source_sector = source_industry = None
    source_status = "READY"
    unique_sources = {
        (_normalize_text(row.get("sector")), _normalize_text(row.get("industry")))
        for row in source_rows
    }
    if security_id is None or int(member.get("active_security_count") or 1) != 1 or int(member.get("all_security_count") or 1) < 1:
        decision = "IDENTITY_REVIEW_REQUIRED"
    elif not source_rows:
        decision = "MISSING_SOURCE_CLASSIFICATION"
        source_status = decision
    elif len(unique_sources) > 1:
        decision = "AMBIGUOUS_SOURCE_CLASSIFICATION"
        source_status = decision
    else:
        source_sector, source_industry = next(iter(unique_sources))
        if source_sector is None or source_industry is None:
            decision = "MISSING_SOURCE_CLASSIFICATION"
            source_status = decision
        elif valuation is None or int(valuation.get("row_count") or 0) == 0:
            decision = "NOT_APPLICABLE"
        else:
            persisted_values = list(valuation.get("values") or [])
            persisted_pairs = {(_normalize_text(row.get("sector")), _normalize_text(row.get("industry"))) for row in persisted_values}
            if any(pair[0] is None or pair[1] is None for pair in persisted_pairs):
                decision = "MISSING_PERSISTED_CLASSIFICATION"
            elif persisted_pairs == {(source_sector, source_industry)}:
                decision = "EXACT_MATCH"
            elif all((_semantic_key(a), _semantic_key(b)) == (_semantic_key(source_sector), _semantic_key(source_industry)) for a, b in persisted_pairs):
                decision = "NORMALIZED_EQUIVALENT"
            elif structural_events:
                decision = "STRUCTURAL_BOUNDARY_REVIEW_REQUIRED"
            else:
                decision = "CHANGE_REQUIRED"
    safe = decision in SAFE_CORRECTABLE_DECISIONS and not structural_events
    affected_rows = int(valuation.get("row_count") or 0) if valuation and safe else 0
    persisted = [] if valuation is None else list(valuation.get("values") or [])
    old_value = "; ".join(
        f"{row.get('sector') or '<NULL>'} / {row.get('industry') or '<NULL>'} ({row.get('row_count')})"
        for row in persisted
    )
    new_value = f"{source_sector} / {source_industry}" if source_sector and source_industry and safe else None
    reason = {
        "EXACT_MATCH": "Persisted classification already matches ticker_meta exactly.",
        "NORMALIZED_EQUIVALENT": "Persisted classification differs only by accepted normalization.",
        "CHANGE_REQUIRED": "Persisted classification differs from authoritative ticker_meta.",
        "MISSING_PERSISTED_CLASSIFICATION": "Persisted classification contains NULL or blank Sector/Industry values.",
        "MISSING_SOURCE_CLASSIFICATION": "ticker_meta is missing Sector or Industry.",
        "AMBIGUOUS_SOURCE_CLASSIFICATION": "ticker_meta has multiple conflicting rows for the ticker and market.",
        "IDENTITY_REVIEW_REQUIRED": "Operational-universe identity is not a single active security.",
        "STRUCTURAL_BOUNDARY_REVIEW_REQUIRED": "A structural event exists and automatic historical scope is unsafe.",
        "NOT_APPLICABLE": "No persisted valuation classification rows exist for this active member.",
    }.get(decision, decision)
    return {
        "item_key": ticker,
        "ticker": ticker,
        "market": market,
        "company_id": company_id,
        "security_id": security_id,
        "company_name": member.get("company_name"),
        "operational_universe_status": member.get("membership_status"),
        "source_sector": source_sector,
        "source_industry": source_industry,
        "source_status": source_status,
        "persisted_values": persisted,
        "normalized_source": {"sector": _semantic_key(source_sector), "industry": _semantic_key(source_industry)},
        "structural_events": [dict(row) for row in structural_events],
        "historical_scope": "COMPLETE_RETAINED_ELIGIBLE_HISTORY" if safe else "NO_AUTOMATIC_MUTATION",
        "decision": decision,
        "reason": reason,
        "safe_to_apply": safe,
        "affected_rows": affected_rows,
        "old_value": old_value or None,
        "new_value": new_value,
    }


def build_sector_industry_plan(
    paths: BatchAddTickerPaths,
    request: AdminBatchRequest,
    *,
    now: str | None = None,
) -> SectorIndustryPlan:
    created = now or utc_now()
    universe, _ = _active_universe(paths)
    aliases = _aliases(paths)
    requested = set(request.normalized_inputs)
    if requested:
        direct = {str(row["current_ticker"]).upper(): row for row in universe}
        company_ids = set()
        resolved_inputs = set()
        selected = []
        for ticker in request.normalized_inputs:
            if ticker in direct:
                selected.append(direct[ticker])
                company_ids.add(int(direct[ticker]["company_id"]))
                resolved_inputs.add(ticker)
            for company_id in aliases.get(ticker, set()):
                if company_id not in company_ids:
                    selected.extend(row for row in universe if int(row["company_id"]) == company_id)
                    company_ids.add(company_id)
                resolved_inputs.add(ticker)
        universe_scan = selected
    else:
        resolved_inputs = set()
        universe_scan = universe
    classifications, _ = _source_classifications(paths)
    valuations = _valuation_groups(paths)
    structural = _structural_companies(paths)
    items = tuple(
        _classify_item(
            member,
            classifications.get((str(member["current_ticker"]).upper(), str(member.get("market") or "usa").lower()), ()),
            valuations.get((int(member["company_id"]), int(member["security_id"]))) if member.get("security_id") is not None else None,
            structural.get(int(member["company_id"]), ()),
        )
        for member in universe_scan
    )
    missing_filters = tuple(sorted(requested - {str(item["ticker"]).upper() for item in items} - resolved_inputs))
    if missing_filters:
        extra = tuple(
            {
                "item_key": ticker,
                "ticker": ticker,
                "market": request.market or "usa",
                "company_id": None,
                "security_id": None,
                "operational_universe_status": "NOT_FOUND",
                "source_sector": None,
                "source_industry": None,
                "source_status": "NOT_APPLICABLE",
                "persisted_values": [],
                "normalized_source": {"sector": None, "industry": None},
                "structural_events": [],
                "historical_scope": "NO_AUTOMATIC_MUTATION",
                "decision": "NOT_APPLICABLE",
                "reason": "Ticker filter did not resolve to an active operational-universe member.",
                "safe_to_apply": False,
                "affected_rows": 0,
                "old_value": None,
                "new_value": None,
            }
            for ticker in missing_filters
        )
        items = items + extra
    return SectorIndustryPlan(
        contract_version=CONTRACT_VERSION,
        created_at_utc=created,
        source_state=source_state(paths),
        request=request.as_dict(),
        denominator_count=len(universe),
        inspected_count=len(items),
        items=items,
    )


def _decision_from_item(item: Mapping[str, Any], *, applied: bool = False) -> AdminItemDecision:
    decision = str(item.get("decision"))
    status = (
        AdminStatus.APPLIED if applied and item.get("safe_to_apply") else
        AdminStatus.ELIGIBLE if item.get("safe_to_apply") else
        AdminStatus.NO_CHANGE if decision in NO_CHANGE_DECISIONS else
        AdminStatus.REVIEW_REQUIRED if decision.endswith("REVIEW_REQUIRED") or "AMBIGUOUS" in decision or "MISSING_SOURCE" in decision else
        AdminStatus.REJECTED if decision == "NOT_APPLICABLE" else
        AdminStatus.REVIEW_REQUIRED
    )
    return AdminItemDecision(
        item_key=str(item.get("item_key") or item.get("ticker")),
        requested_value=str(item.get("ticker")),
        normalized_value=str(item.get("ticker")),
        status=status,
        reason=str(item.get("reason") or decision),
        market=item.get("market"),
        company_name=item.get("company_name"),
        old_value=item.get("old_value"),
        new_value=item.get("new_value"),
        source_category="ticker_meta",
        warnings=tuple([decision]) if status == AdminStatus.REVIEW_REQUIRED else (),
        blockers=tuple([decision]) if status in {AdminStatus.REVIEW_REQUIRED, AdminStatus.REJECTED} else (),
        applied_action="SECTOR_INDUSTRY_COPY_CORRECTED" if applied and item.get("safe_to_apply") else ("PENDING_COPY_APPLY" if item.get("safe_to_apply") else None),
        details={key: value for key, value in item.items() if key not in {"company_id", "security_id"}},
    )


def _counts(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("decision") or "UNKNOWN") for item in items)
    counts["correctable"] = sum(1 for item in items if item.get("safe_to_apply"))
    counts["inspected"] = len(items)
    return dict(sorted(counts.items()))


def _write_preview_payload(path: Path, plan: Mapping[str, Any], preview: Mapping[str, Any]) -> None:
    write_json(path, {"sector_industry_plan": dict(plan), "sector_industry_preview": dict(preview)})


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_preview_fresh(paths: BatchAddTickerPaths, payload: Mapping[str, Any]) -> None:
    saved = payload.get("sector_industry_plan") if isinstance(payload.get("sector_industry_plan"), Mapping) else {}
    if source_state(paths) != saved.get("source_state"):
        raise ValueError("PHASE13G3_STALE_PREVIEW_SOURCE_STATE_CHANGED")


def _apply_classification_corrections(
    paths: BatchAddTickerPaths,
    items: Sequence[Mapping[str, Any]],
    *,
    applied_at: str,
    inject_failure: bool = False,
) -> dict[str, Any]:
    reject_production_path(paths.analysis_db, "analysis")
    changed = 0
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(paths.analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for index, item in enumerate(items, start=1):
                if not item.get("safe_to_apply"):
                    continue
                before = conn.total_changes
                source_sector = item.get("source_sector")
                source_industry = item.get("source_industry")
                applicability = valuation_engine.classify_applicability(source_sector, source_industry)
                applicability_code = "SUPPORTED" if applicability.supported is True else "NOT_APPLICABLE" if applicability.supported is False else "NOT_READY"
                conn.execute(
                    "UPDATE valuation_revised_result SET sector=?,industry=?,applicability_classification=?,calculated_at_utc=? "
                    "WHERE company_id=? AND security_id=?",
                    (source_sector, source_industry, applicability_code, applied_at, int(item["company_id"]), int(item["security_id"])),
                )
                delta = conn.total_changes - before
                changed += delta
                rows.append({"ticker": item["ticker"], "rows_changed": delta, "sector": source_sector, "industry": source_industry})
                if inject_failure and index == 1:
                    raise RuntimeError("PHASE13G3_INJECTED_AFTER_CLASSIFICATION_MUTATION")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"outcome": "APPLIED" if changed else "NO_CHANGE", "rows_changed": changed, "rows": rows, "applied_at_utc": applied_at}


def _read_active_universe_identity(paths: BatchAddTickerPaths) -> dict[str, Any]:
    with _readonly(paths.canonical_db) as conn:
        if not _table_exists(conn, "fundamentals_operational_universe_active_version"):
            return {"status": "MISSING"}
        row = conn.execute(
            "SELECT v.* FROM fundamentals_operational_universe_active_version a "
            "JOIN fundamentals_operational_universe_version v USING(universe_version_id) WHERE a.singleton=1"
        ).fetchone()
    return dict(row) if row else {"status": "MISSING"}


def _run_git(args: tuple[str, ...]) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _assert_clean_worktree() -> dict[str, Any]:
    status = _run_git(("status", "--porcelain"))
    if status:
        raise RuntimeError("PHASE13G3_PRODUCTION_CLEAN_GIT_WORKTREE_REQUIRED")
    return {
        "head": _run_git(("rev-parse", "HEAD")),
        "short_head": _run_git(("rev-parse", "--short", "HEAD")),
        "branch": _run_git(("branch", "--show-current")),
        "status_clean": True,
    }


def _process_inventory() -> dict[str, Any]:
    rows = subprocess.run(("ps", "-eo", "pid=,args="), check=True, capture_output=True, text=True).stdout.splitlines()
    own_pid = str(os.getpid())
    relevant = [
        row.strip()
        for row in rows
        if own_pid not in row
        and any(term in row.lower() for term in ("rawcandle", "fundamental", "sharadar", "stock_update_scheduler"))
    ]
    conflicts = [
        row
        for row in relevant
        if any(term in row for term in ("run_fundamentals_v4", "run_phase13", "run_phase12", "run_sharadar", "stock_update_scheduler"))
    ]
    if conflicts:
        raise RuntimeError("PHASE13G3_CONFLICTING_WRITER:" + " | ".join(conflicts))
    return {"relevant_processes": relevant, "conflicting_writers": conflicts}


def _assert_no_sqlite_sidecars(paths: BatchAddTickerPaths, roles: Sequence[str] = WRITE_ROLES) -> dict[str, Any]:
    sidecars: dict[str, list[dict[str, Any]]] = {}
    for role in roles:
        path = paths.as_dict()[role]
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                sidecars.setdefault(role, []).append({"path": str(sidecar), "size": sidecar.stat().st_size})
    if sidecars:
        raise RuntimeError("PHASE13G3_NONEMPTY_SQLITE_SIDECAR:" + json.dumps(sidecars, sort_keys=True))
    return {"checked_roles": list(roles), "nonempty_sidecars": 0}


def _storage_gate(output: Path, backup_dir: Path, paths: BatchAddTickerPaths) -> dict[str, Any]:
    def existing_parent(path: Path) -> Path:
        current = path
        while not current.exists():
            current = current.parent
        return current

    write_bytes = sum(paths.as_dict()[role].stat().st_size for role in WRITE_ROLES)
    required = int((write_bytes * 0.25) + (256 * 1024 * 1024))
    checks = []
    for location in {ROOT, existing_parent(output.parent), existing_parent(backup_dir.parent), Path("/tmp")}:
        usage = shutil.disk_usage(location)
        checks.append({
            "path": str(location.resolve()),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "required_bytes": required,
            "ok": usage.free >= required,
        })
    if not all(row["ok"] for row in checks):
        raise RuntimeError("PHASE13G3_INSUFFICIENT_FREE_SPACE")
    return {"write_set_bytes": write_bytes, "required_bytes": required, "checks": checks}


def _production_preflight(
    paths: BatchAddTickerPaths,
    *,
    output: Path,
    backup_dir: Path,
    require_clean: bool = True,
) -> dict[str, Any]:
    resolved_paths = validate_exact_production_paths(paths)
    sidecars = _assert_no_sqlite_sidecars(paths)
    git = _assert_clean_worktree() if require_clean else {"status_clean": False, "skipped": True}
    process = _process_inventory()
    storage = _storage_gate(output, backup_dir, paths)
    inventory = production_inventory()
    bad_dbs = {
        role: {
            "quick_check": item["quick_check"],
            "foreign_key_errors": item["foreign_key_errors"],
        }
        for role, item in inventory["databases"].items()
        if item["quick_check"] != "ok" or item["foreign_key_errors"]
    }
    if bad_dbs:
        raise RuntimeError("PHASE13G3_PRODUCTION_INTEGRITY_PRECHECK_FAILED:" + json.dumps(bad_dbs, sort_keys=True))
    return {
        "resolved_paths": resolved_paths,
        "write_roles": list(WRITE_ROLES),
        "read_only_roles": list(READONLY_ROLES),
        "git": git,
        "process": process,
        "storage": storage,
        "sidecars": sidecars,
        "production_inventory": inventory,
        "active_identities": _active_identities(paths),
        "role_contract": {
            "analysis": "Writable only if classification corrections or downstream refreshes are authorized; this phase permits production NO_CHANGE only.",
            "provider": "Read-only fundamentals source for downstream readers.",
            "canonical": "Read-only identity and operational-universe source.",
            "market": "Read-only authoritative ticker_meta classification source.",
            "taxonomy": "Read-only Datacenter taxonomy source; not part of Sector/Industry mutation.",
        },
    }


def _production_logical_state(paths: BatchAddTickerPaths) -> dict[str, Any]:
    database_keys = ("schema_fingerprint", "row_counts", "logical_fingerprints", "quick_check", "foreign_key_errors")
    return {
        "databases": {
            role: {
                key: database_inventory(path).get(key)
                for key in database_keys
            }
            for role, path in paths.as_dict().items()
        },
        "active_identities": _active_identities(paths),
    }


def _accepted_population_gate(plan: Mapping[str, Any]) -> dict[str, Any]:
    items = [dict(item) for item in plan.get("items", [])]
    counts = _counts(items)
    exact_tickers = {str(item.get("ticker")).upper() for item in items if item.get("decision") == "EXACT_MATCH"}
    review_tickers = {str(item.get("ticker")).upper() for item in items if item.get("decision") == "IDENTITY_REVIEW_REQUIRED"}
    not_applicable = {str(item.get("ticker")).upper() for item in items if item.get("decision") == "NOT_APPLICABLE"}
    result = {
        "accepted_baseline": dict(ACCEPTED_PHASE13G31_COUNTS),
        "denominator": int(plan.get("denominator_count") or 0),
        "counts": counts,
        "review_tickers": sorted(review_tickers),
        "not_applicable_tickers": sorted(not_applicable),
        "named_exact_tickers": sorted(ticker for ticker in ACCEPTED_PHASE13G31_EXACT_TICKERS if ticker in exact_tickers),
        "omitted_named_exact_tickers": sorted(ACCEPTED_PHASE13G31_EXACT_TICKERS - exact_tickers),
        "safe_changes": [item for item in items if item.get("safe_to_apply")],
        "omitted_active_memberships": 0 if int(plan.get("denominator_count") or 0) == len(items) else abs(int(plan.get("denominator_count") or 0) - len(items)),
    }
    failures = []
    if result["denominator"] != ACCEPTED_PHASE13G31_COUNTS["denominator"]:
        failures.append("DENOMINATOR_DRIFT")
    for key in ("EXACT_MATCH", "IDENTITY_REVIEW_REQUIRED", "NOT_APPLICABLE", "correctable"):
        if counts.get(key, 0) != ACCEPTED_PHASE13G31_COUNTS[key]:
            failures.append(f"{key}_COUNT_DRIFT")
    if result["omitted_active_memberships"] != 0:
        failures.append("ACTIVE_MEMBERSHIP_OMISSION")
    if review_tickers != ACCEPTED_PHASE13G31_REVIEW_TICKERS:
        failures.append("REVIEW_TICKER_SET_DRIFT")
    if not_applicable != ACCEPTED_PHASE13G31_NOT_APPLICABLE_TICKERS:
        failures.append("NOT_APPLICABLE_TICKER_SET_DRIFT")
    if result["omitted_named_exact_tickers"]:
        failures.append("NAMED_TICKER_EXACT_MATCH_DRIFT")
    if result["safe_changes"]:
        failures.append("SAFE_CHANGES_PRESENT_REQUIRES_SEPARATE_REVIEW")
    result["status"] = "ACCEPTED" if not failures else "REJECTED"
    result["failures"] = failures
    return result


def _manual_rv_refresh(paths: BatchAddTickerPaths, *, output: Path, applied_at: str) -> dict[str, Any]:
    source = load_relative_valuation_source(
        RVSourcePaths(paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db, paths.provider_db),
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
        first = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at)
        second = apply_rv_snapshot(conn, snapshot, source.inputs, applied_at_utc=applied_at)
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
        "first_apply": first.__dict__,
        "second_apply": second.__dict__,
        "quick_check": check,
        "active_metadata": active,
    }
    write_json(output / "relative_valuation_manual_refresh.json", result)
    return result


def _snapshot_smoke(paths: BatchAddTickerPaths, output: Path, *, tickers: Sequence[str], report_date: str = REPORT_DATE) -> dict[str, Any]:
    report_dir = output / "snapshot_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paths = SnapshotPaths(paths.canonical_db, paths.analysis_db, paths.market_db, paths.taxonomy_db, paths.provider_db)
    results = {}
    for ticker in tuple(dict.fromkeys(tickers)):
        try:
            generated = generate_active_company_snapshot(
                snapshot_paths,
                ticker=ticker,
                report_date=report_date,
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
        except LookupError as exc:
            reason = str(exc)
            results[ticker] = {"status": "READINESS_LIMITED", "error": type(exc).__name__, "reason": reason}
        except Exception as exc:
            results[ticker] = {"status": "FAILED", "error": type(exc).__name__, "reason": str(exc)}
    return results


def _run_downstream(
    paths: BatchAddTickerPaths,
    output: Path,
    *,
    changed_tickers: Sequence[str],
    applied_at: str,
    progress: ProgressTracker | None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"changed_tickers": list(changed_tickers), "applied_at_utc": applied_at}
    if progress:
        progress.running(ProgressStage.PACKAGE_CALCULATION, "Building fresh full V2 analysis and Relative Valuation.")
    with _background_heartbeat(progress, "Full V2 analysis rebuild is still running."):
        rebuilt = run_full_v2_downstream(paths.as_dict(), output=output, as_of_date=as_of_date or applied_at[:10])
    result.update(rebuilt)
    if progress:
        progress.completed(ProgressStage.PACKAGE_CALCULATION, "Full V2 and Relative Valuation rebuild validated.")
        for stage in (ProgressStage.PACKAGE_APPLY, ProgressStage.RELATIVE_POSITION, ProgressStage.RELATIVE_VALUATION):
            progress.running(stage, "Validated by the full V2 rebuild.")
            progress.completed(stage, "Validated by the full V2 rebuild.")
        progress.skipped(ProgressStage.DEPENDENCY_ATTACHMENT, "Fresh V2 analysis has its own validated dependencies.")
        progress.running(ProgressStage.SNAPSHOT_SMOKE, "Generating representative Snapshot smoke reports.")
    smoke_tickers = tuple(dict.fromkeys([*changed_tickers[:10], "NVDA"]))
    candidate_paths = replace(paths, analysis_db=Path(rebuilt["candidate_analysis_db"]))
    result["snapshots"] = _snapshot_smoke(candidate_paths, output, tickers=smoke_tickers, report_date=as_of_date or applied_at[:10])
    if progress:
        progress.completed(ProgressStage.SNAPSHOT_SMOKE, "Snapshot smoke completed.", processed_items=len(result["snapshots"]), total_items=len(smoke_tickers))
    return result


def run_preview(
    raw_inputs: str | Sequence[str] = "",
    *,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    market: str | None = "usa",
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    request = parse_sector_industry_request(raw_inputs, market=market)
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY, fingerprint(request))
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY, run_dir=writer.run_dir, stages=SECTOR_INDUSTRY_STAGES, callback=progress_callback)
    started = utc_now()
    progress.running(ProgressStage.PREFLIGHT, "Recording Sector/Industry preview request.", processed_items=0, total_items=len(request.normalized_inputs) or None)
    writer.checkpoint(RunStage.REQUEST_CREATED, message="Sector/Industry preview request recorded.")
    writer.write_json("request.json", request.as_dict())
    progress.completed(ProgressStage.PREFLIGHT, "Preview request recorded.")
    writer.checkpoint(RunStage.PREVIEW_STARTED, message="Scanning production-shaped databases for Sector/Industry preview.")
    progress.running(ProgressStage.CLASSIFICATION_SCAN, "Scanning operational-universe classifications.")
    plan = build_sector_industry_plan(source_paths, request)
    progress.completed(ProgressStage.CLASSIFICATION_SCAN, "Classification scan completed.", processed_items=plan.inspected_count, total_items=plan.denominator_count)
    progress.running(ProgressStage.CLASSIFICATION_RECONCILIATION, "Classifying Sector/Industry differences.")
    plan_dict = plan.safe_dict()
    decisions = tuple(_decision_from_item(item) for item in plan.items)
    counts = _counts(plan.items)
    preview = {
        "operation_type": AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY.value,
        "as_of_date": started[:10],
        "request": request.as_dict(),
        "source_state": plan.source_state,
        "proposed_changes": [dict(item) for item in plan.correctable_items],
        "warnings": [str(item["ticker"]) + ":" + str(item["decision"]) for item in plan.items if not item.get("safe_to_apply") and item.get("decision") not in NO_CHANGE_DECISIONS],
    }
    preview["request_fingerprint"] = fingerprint(request)
    preview["change_set_fingerprint"] = fingerprint(preview["proposed_changes"])
    preview["preview_fingerprint"] = fingerprint(preview)
    writer.write_json("preview.json", preview)
    payload_path = writer.run_dir / "sector_industry_preview_payload.json"
    _write_preview_payload(payload_path, plan_dict, preview)
    writer.write_items_csv([item.as_dict() for item in decisions])
    writer.checkpoint(
        RunStage.PREVIEW_READY,
        message="Sector/Industry preview ready. Production was not modified.",
        preview_fingerprint=preview["preview_fingerprint"],
        counters=counts,
    )
    progress.completed(ProgressStage.CLASSIFICATION_RECONCILIATION, "Classification reconciliation completed.", processed_items=plan.inspected_count, total_items=plan.denominator_count)
    result = AdminFinalResult(
        run_id=run_id,
        operation_type=AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY,
        outcome=AdminStatus.COMPLETED,
        mode="PREVIEW",
        started_at_utc=started,
        completed_at_utc=utc_now(),
        preview_fingerprint=preview["preview_fingerprint"],
        request=request.as_dict(),
        item_results=decisions,
        summary_counts=counts,
        downstream={"package": "NOT_RUN_IN_PREVIEW", "relative_position": "NOT_RUN_IN_PREVIEW", "relative_valuation": "NOT_RUN_IN_PREVIEW"},
        artifacts={"preview": str(writer.run_dir / "preview.json"), "payload": str(payload_path)},
        recommended_next_action="Tarkista preview. Copy-only apply vaatii --apply, --confirm-apply ja preview fingerprintin.",
    )
    result_dict = result.as_dict()
    writer.write_final_result(result)
    writer.write_text("report.md", render_markdown_report(result_dict))
    progress.running(ProgressStage.COMPLETED, "Preview completed.")
    progress.completed(ProgressStage.COMPLETED, "Preview completed.")
    writer.checkpoint(RunStage.COMPLETED, message="Sector/Industry preview completed.", preview_fingerprint=preview["preview_fingerprint"], counters=counts)
    writer.write_exit_code(0)
    writer.write_manifest()
    return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "preview_payload_path": str(payload_path)}


def run_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    temp_root: Path = TEMP_ROOT,
    confirm_apply: bool = False,
    keep_copies: bool = False,
    failure_boundary: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not confirm_apply:
        raise PermissionError("PHASE13G3_APPLY_REQUIRES_CONFIRMATION")
    payload = _load_payload(preview_payload_path)
    preview = payload.get("sector_industry_preview") if isinstance(payload.get("sector_industry_preview"), Mapping) else {}
    if preview.get("preview_fingerprint") != preview_fingerprint:
        raise ValueError("PHASE13G3_PREVIEW_FINGERPRINT_MISMATCH")
    plan = payload.get("sector_industry_plan") if isinstance(payload.get("sector_industry_plan"), Mapping) else {}
    request_payload = preview.get("request") if isinstance(preview.get("request"), Mapping) else {}
    request = AdminBatchRequest(
        operation_type=AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY,
        requested_inputs=tuple(request_payload.get("requested_inputs") or ()),
        normalized_inputs=tuple(request_payload.get("normalized_inputs") or ()),
        rejected_inputs=tuple(request_payload.get("rejected_inputs") or ()),
        market=request_payload.get("market"),
        options=request_payload.get("options") or {},
    )
    run_id = stable_run_id(AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY, preview_fingerprint, suffix="apply")
    writer = AdminRunWriter(run_id, AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY, root=run_root)
    progress = ProgressTracker(run_id=run_id, operation_type=AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY, run_dir=writer.run_dir, stages=SECTOR_INDUSTRY_STAGES, callback=progress_callback)
    started = utc_now()
    lane = None
    write_boundary_crossed = False
    failed_stage = ProgressStage.PREFLIGHT
    try:
        failed_stage = ProgressStage.PREFLIGHT
        progress.running(ProgressStage.PREFLIGHT, "Recording Sector/Industry copy-only apply request.")
        writer.checkpoint(RunStage.REQUEST_CREATED, message="Sector/Industry copy-only apply request recorded.", preview_fingerprint=preview_fingerprint)
        writer.write_json("request.json", request.as_dict())
        writer.write_json("preview.json", preview)
        progress.completed(ProgressStage.PREFLIGHT, "Apply request recorded.")
        failed_stage = ProgressStage.PREVIEW_VALIDATION
        progress.running(ProgressStage.PREVIEW_VALIDATION, "Creating production-shaped copy lane.")
        writer.checkpoint(RunStage.APPLY_STARTED, message="Creating copy lane for Sector/Industry copy-only apply.", preview_fingerprint=preview_fingerprint)
        lane = create_copy_lane(source_paths, lane_dir=temp_root / run_id / "apply_lane", writer=writer)
        progress.completed(ProgressStage.PREVIEW_VALIDATION, "Copy lane ready.")
        failed_stage = ProgressStage.CLASSIFICATION_SCAN
        progress.running(ProgressStage.CLASSIFICATION_SCAN, "Validating saved preview freshness on copy lane.")
        _assert_preview_fresh(lane.paths, payload)
        fresh_plan = build_sector_industry_plan(lane.paths, request, now=plan.get("created_at_utc"))
        if fresh_plan.safe_dict()["plan_fingerprint"] != plan.get("plan_fingerprint"):
            raise ValueError("ADMIN_SECTOR_INDUSTRY_STALE_PLAN_CONTENT_CHANGED")
        progress.completed(ProgressStage.CLASSIFICATION_SCAN, "Saved preview is fresh on copy lane.")
        failed_stage = ProgressStage.CLASSIFICATION_RECONCILIATION
        progress.running(ProgressStage.CLASSIFICATION_RECONCILIATION, "Reconciling saved Sector/Industry change set.")
        safe_items = [item for item in plan.get("items", []) if item.get("safe_to_apply")]
        progress.completed(ProgressStage.CLASSIFICATION_RECONCILIATION, "Saved Sector/Industry change set reconciled.", processed_items=len(plan.get("items", [])), total_items=len(plan.get("items", [])))
        writer.checkpoint(RunStage.WRITE_BOUNDARY_NOT_CROSSED, message="Preview validated on copied databases.", preview_fingerprint=preview_fingerprint)
        before = {role: database_fingerprint(path) for role, path in lane.paths.as_dict().items()}
        applied_at = utc_now()
        if not safe_items:
            failed_stage = ProgressStage.NO_CHANGE_VERIFICATION
            progress.running(ProgressStage.NO_CHANGE_VERIFICATION, "No safe Sector/Industry corrections required.")
            repeat_plan = build_sector_industry_plan(lane.paths, request)
            progress.completed(ProgressStage.NO_CHANGE_VERIFICATION, "No-change preview verified.", processed_items=repeat_plan.inspected_count, total_items=repeat_plan.denominator_count)
            downstream = {"invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0}, "status": "NO_CHANGE_NO_DOWNSTREAM_REQUIRED"}
            correction = {"outcome": "NO_CHANGE", "rows_changed": 0, "rows": []}
            repeat_result = {"outcome": "NO_CHANGE", "counts": _counts(repeat_plan.items)}
        else:
            failed_stage = ProgressStage.CLASSIFICATION_APPLY
            progress.running(ProgressStage.CLASSIFICATION_APPLY, "Applying safe Sector/Industry corrections to copy lane.", processed_items=0, total_items=len(safe_items))
            writer.checkpoint(RunStage.WRITE_BOUNDARY_CROSSED, message="Applying Sector/Industry corrections to copied databases.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            write_boundary_crossed = True
            correction = _apply_classification_corrections(lane.paths, safe_items, applied_at=applied_at, inject_failure=failure_boundary == "classification_apply")
            progress.completed(ProgressStage.CLASSIFICATION_APPLY, "Sector/Industry corrections applied.", processed_rows=int(correction.get("rows_changed") or 0))
            downstream = _run_downstream(
                lane.paths,
                lane.lane_dir / "sector_industry_downstream",
                changed_tickers=[str(item["ticker"]) for item in safe_items],
                applied_at=applied_at,
                progress=progress,
                as_of_date=str(preview["as_of_date"]),
            )
            failed_stage = ProgressStage.NO_CHANGE_VERIFICATION
            progress.running(ProgressStage.NO_CHANGE_VERIFICATION, "Repeating Sector/Industry operation on corrected copy lane.")
            repeat_plan = build_sector_industry_plan(lane.paths, request)
            repeat_safe = [item for item in repeat_plan.items if item.get("safe_to_apply")]
            repeat_result = {
                "outcome": "NO_CHANGE" if not repeat_safe else "CHANGES_REMAIN",
                "counts": _counts(repeat_plan.items),
                "remaining_correctable": [item["ticker"] for item in repeat_safe],
                "invocation_counts": {"package": 0, "relative_position": 0, "relative_valuation": 0} if not repeat_safe else None,
            }
            progress.completed(ProgressStage.NO_CHANGE_VERIFICATION, "Repeat operation completed.", processed_items=0, total_items=repeat_plan.inspected_count)
        after = {role: database_fingerprint(path) for role, path in lane.paths.as_dict().items()}
        final_items = tuple(_decision_from_item(item, applied=bool(item.get("safe_to_apply") and correction.get("outcome") == "APPLIED")) for item in plan.get("items", []))
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY,
            outcome=AdminStatus.COMPLETED if repeat_result["outcome"] == "NO_CHANGE" else AdminStatus.PARTIALLY_COMPLETED,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            item_results=final_items,
            summary_counts=_counts(plan.get("items", [])),
            rollback={"status": "NOT_REQUIRED"},
            downstream={
                "classification_correction": correction,
                "invocation_counts": downstream.get("invocation_counts"),
                "package": downstream.get("package", "NOT_RUN"),
                "relative_position": downstream.get("relative_position", "NOT_RUN"),
                "relative_valuation": downstream.get("relative_valuation", "NOT_RUN"),
                "active_taxonomy": downstream.get("active_taxonomy"),
                "repeat": repeat_result,
            },
            artifacts={"copy_lane": str(lane.lane_dir), "downstream": str(lane.lane_dir / "sector_industry_downstream")},
            recommended_next_action="Copy-only evidence complete. Production remains unchanged.",
        )
        result_dict = result.as_dict()
        result_dict["copy_apply"] = {"before": before, "after": after, "correction": correction, "downstream": downstream, "repeat": repeat_result, "copy_lane": str(lane.lane_dir)}
        writer.write_final_result(result)
        writer.write_json("sector_industry_apply_technical.json", result_dict["copy_apply"])
        writer.write_items_csv([item.as_dict() for item in final_items])
        writer.write_text("report.md", render_markdown_report(result_dict))
        failed_stage = ProgressStage.FINAL_VALIDATION
        progress.running(ProgressStage.FINAL_VALIDATION, "Writing final Sector/Industry apply artifacts.")
        progress.completed(ProgressStage.FINAL_VALIDATION, "Final apply artifacts written.", processed_items=len(final_items), total_items=len(final_items))
        writer.checkpoint(RunStage.COMPLETED if result.outcome == AdminStatus.COMPLETED else RunStage.PARTIALLY_COMPLETED, message="Sector/Industry copy-only apply completed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed, counters=_counts(plan.get("items", [])))
        writer.write_exit_code(0 if result.outcome == AdminStatus.COMPLETED else 1)
        writer.write_manifest()
        failed_stage = ProgressStage.CLEANUP
        progress.running(ProgressStage.CLEANUP, "Cleaning Sector/Industry copy lane." if not keep_copies else "Retaining copy lane by request.")
        cleanup = {"retained": str(lane.lane_dir)} if keep_copies else cleanup_copy_lane(lane)
        progress.completed(ProgressStage.CLEANUP, "Cleanup completed.", processed_items=int(cleanup.get("removed_count") or 0) if "removed_count" in cleanup else None)
        progress.running(ProgressStage.COMPLETED, "Sector/Industry copy-only apply completed.")
        progress.completed(ProgressStage.COMPLETED, "Sector/Industry copy-only apply completed.")
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup}
    except Exception as exc:
        writer.write_error(exc)
        rollback: dict[str, Any]
        if lane is not None and write_boundary_crossed:
            progress.rolling_back("Copy apply failed after mutation; restoring copy lane from source backups.", errors=(f"{type(exc).__name__}: {exc}",))
            writer.checkpoint(RunStage.ROLLBACK_STARTED, message="Sector/Industry apply failed; restoring copied databases.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            for role, path in lane.paths.as_dict().items():
                source = source_paths.as_dict()[role]
                from rawcandle.fundamentals.phase13b_foundation import online_backup
                online_backup(source, path)
            rollback = {"status": "ROLLED_BACK", "fingerprints": {role: database_fingerprint(path) for role, path in lane.paths.as_dict().items()}}
            progress.rolled_back("Copy lane restored.")
            writer.checkpoint(RunStage.ROLLBACK_COMPLETE, message="Copy lane restored.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=True)
            terminal = RunStage.FAILED_AFTER_WRITE
            outcome = AdminStatus.ROLLED_BACK
            code = 3
        else:
            progress.failed(failed_stage, "Sector/Industry apply failed before mutation.", errors=(f"{type(exc).__name__}: {exc}",))
            rollback = {"status": "NOT_REQUIRED", "message": "Failure occurred before copy mutation."}
            terminal = RunStage.FAILED_BEFORE_WRITE
            outcome = AdminStatus.FAILED
            code = 2
        result = AdminFinalResult(
            run_id=run_id,
            operation_type=AdminOperationType.CHECK_UPDATE_SECTOR_INDUSTRY,
            outcome=outcome,
            mode="COPY_ONLY_APPLY",
            started_at_utc=started,
            completed_at_utc=utc_now(),
            preview_fingerprint=preview_fingerprint,
            request=request.as_dict(),
            rollback=rollback,
            errors=({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},),
            recommended_next_action="Inspect error.json before retrying.",
        )
        result_dict = result.as_dict()
        writer.write_final_result(result)
        writer.write_text("report.md", render_markdown_report(result_dict))
        writer.checkpoint(terminal, message="Sector/Industry copy-only apply failed.", preview_fingerprint=preview_fingerprint, write_boundary_crossed=write_boundary_crossed)
        writer.write_exit_code(code)
        writer.write_manifest()
        cleanup = {}
        if lane is not None and not keep_copies:
            cleanup = cleanup_copy_lane(lane)
        elif lane is not None:
            cleanup = {"retained": str(lane.lane_dir)}
        return result_dict | {"run_id": run_id, "artifact_dir": str(writer.run_dir), "cleanup": cleanup, "error": type(exc).__name__}


def run_production_apply(
    *,
    preview_payload_path: Path,
    preview_fingerprint: str,
    source_paths: BatchAddTickerPaths = BatchAddTickerPaths(),
    run_root: Path = ADMIN_RUN_ROOT,
    backup_root: Path | None = None,
    temp_root: Path = PRODUCTION_TEMP_ROOT,
    confirm_production: bool = False,
    progress_callback: ProgressCallback | None = None,
    test_run_id: str | None = None,
) -> dict[str, Any]:
    del temp_root
    if not confirm_production:
        raise PermissionError("PHASE13G3_PRODUCTION_APPLY_REQUIRES_CONFIRM_PRODUCTION")
    from rawcandle.fundamentals.admin.production_operations import SECTOR_INDUSTRY
    from rawcandle.fundamentals.admin.production_transaction import run_transaction

    return run_transaction(
        SECTOR_INDUSTRY, preview_payload_path=preview_payload_path,
        preview_fingerprint=preview_fingerprint, test_run_id=test_run_id or "",
        source_paths=source_paths, run_root=run_root, backup_root=backup_root,
        production_intent=True,
    )


def preflight_snapshot(paths: BatchAddTickerPaths = BatchAddTickerPaths()) -> dict[str, Any]:
    return {
        "paths": {role: str(path.resolve()) for role, path in paths.as_dict().items()},
        "production_immutable": True,
        "disk": disk_hygiene_snapshot(ROOT),
        "databases": {role: {key: database_inventory(path)[key] for key in ("quick_check", "foreign_key_errors")} for role, path in paths.as_dict().items()},
        "source_state": source_state(paths),
    }
