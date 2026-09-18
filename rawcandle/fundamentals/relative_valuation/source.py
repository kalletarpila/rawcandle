from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.operating_income_v2 import valuation
from rawcandle.fundamentals.operating_income_v2 import relative_position as active_relative_position
from rawcandle.fundamentals.operating_income_v2.activation import assert_v2_active
from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.operating_income_v2 import peer_source_context as peer_source
from rawcandle.fundamentals.operating_income_v2.peer_ranking_core import CURRENT_FRESHNESS_DAYS
from rawcandle.fundamentals.ttm.engine import MODEL_VERSION as TTM_MODEL_VERSION

from .engine import HistoricalEndpoint, RelativeValuationInput, canonical_json


@dataclass(frozen=True)
class ReadOnlySourcePaths:
    analysis_db: Path
    canonical_db: Path
    market_db: Path
    taxonomy_db: Path
    provider_db: Path | None = None


@dataclass(frozen=True)
class RelativeValuationSource:
    inputs: tuple[RelativeValuationInput, ...]
    classification_fingerprint: str
    taxonomy_fingerprint: str
    source_fingerprint: str
    metadata: dict[str, Any]


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _validate_paths(paths: ReadOnlySourcePaths) -> None:
    configured = tuple(
        path for path in (
            paths.analysis_db,
            paths.canonical_db,
            paths.market_db,
            paths.taxonomy_db,
            paths.provider_db,
        )
        if path is not None
    )
    for path in configured:
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(path)
    resolved = tuple(path.resolve() for path in configured)
    if len(set(resolved)) != len(resolved):
        raise ValueError("RELATIVE_VALUATION_SOURCE_PATHS_MUST_BE_DISTINCT")


def _active_universe_members(canonical_db: Path, as_of_date: str) -> tuple[set[int] | None, dict[str, Any]]:
    with _readonly(canonical_db) as conn:
        has_schema = conn.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='fundamentals_operational_universe_active_version'"
        ).fetchone()
        if has_schema is None:
            return None, {"status": "UNIVERSE_SCHEMA_ABSENT_LEGACY_ALLOWED"}
        active = conn.execute(
            "SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1"
        ).fetchone()
        if active is None:
            return None, {"status": "ACTIVE_UNIVERSE_ABSENT_LEGACY_ALLOWED"}
        rows = [dict(row) for row in conn.execute(
            "SELECT company_id,security_id,current_ticker,membership_status,effective_start_date,effective_end_date "
            "FROM fundamentals_operational_universe_member WHERE universe_version_id=? ORDER BY company_id",
            (active["universe_version_id"],),
        )]
    eligible = {
        int(row["company_id"])
        for row in rows
        if str(row["membership_status"]) in {"ACTIVE_SINGLE_SECURITY", "ACTIVE_MULTI_SECURITY"}
    }
    return eligible, {
        "status": "ACTIVE_UNIVERSE_FILTER_APPLIED",
        "universe_version_id": str(active["universe_version_id"]),
        "member_rows": len(rows),
        "eligible_companies": len(eligible),
    }


def _listing_eligibility(
    paths: ReadOnlySourcePaths, as_of_date: str
) -> tuple[dict[int, tuple[bool, str]], dict[str, Any]]:
    with _readonly(paths.canonical_db) as conn:
        securities = [dict(row) for row in conn.execute(
            "SELECT security_id,company_id,current_ticker,exchange,active,valid_from,valid_to FROM security ORDER BY security_id"
        )]
    provider: dict[str, dict[str, Any]] = {}
    if paths.provider_db is not None:
        with _readonly(paths.provider_db) as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT ticker,permaticker,isdelisted,firstpricedate,lastpricedate,lastupdated "
                "FROM sharadar_ticker_metadata WHERE table_name='fundamentals' ORDER BY ticker,lastupdated DESC"
            )]
        for row in rows:
            provider.setdefault(str(row["ticker"]).upper(), row)
    eligibility: dict[int, tuple[bool, str]] = {}
    reason_counts: Counter[str] = Counter()
    for security in securities:
        ticker = str(security["current_ticker"]).upper()
        meta = provider.get(ticker)
        start = (meta or {}).get("firstpricedate") or security.get("valid_from")
        end = (meta or {}).get("lastpricedate") if (meta or {}).get("isdelisted") == "Y" else security.get("valid_to")
        reason = "ELIGIBLE_ON_DATE"
        eligible = True
        if start is not None and as_of_date < str(start):
            eligible, reason = False, "PRELISTING"
        elif end is not None and as_of_date > str(end):
            eligible, reason = False, "POST_DELISTING"
        elif start is None and int(security.get("active") or 0) == 0:
            eligible, reason = False, "LISTING_START_UNRESOLVED_FOR_INACTIVE_SECURITY"
        elif int(security.get("active") or 0) == 0 and end is None and meta is None:
            eligible, reason = False, "LISTING_INTERVAL_UNRESOLVED_FOR_INACTIVE_SECURITY"
        eligibility[int(security["security_id"])] = (eligible, reason)
        reason_counts[reason] += 1
    return eligibility, {
        "status": "PROVIDER_METADATA_APPLIED" if paths.provider_db is not None else "CANONICAL_SECURITY_DATES_ONLY",
        "as_of_date": as_of_date,
        "security_count": len(securities),
        "provider_metadata_tickers": len(provider),
        "eligible_securities": sum(1 for eligible, _ in eligibility.values() if eligible),
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def _bars(connection: sqlite3.Connection, ticker: str, as_of_date: str) -> tuple[valuation.PriceBar, ...]:
    rows = list(
        connection.execute(
            "SELECT pvm,open,high,low,close FROM osakedata WHERE osake=? AND pvm<=? ORDER BY pvm DESC LIMIT 32",
            (ticker, as_of_date),
        )
    )
    if not rows:
        rows = list(
            connection.execute(
                "SELECT pvm,open,high,low,close FROM osakedata WHERE UPPER(osake)=? AND pvm<=? ORDER BY pvm DESC LIMIT 32",
                (ticker.upper(), as_of_date),
            )
        )
    return tuple(valuation.PriceBar(str(row["pvm"]), row["open"], row["high"], row["low"], row["close"]) for row in rows)


def _strip_upstream_snapshot_identity(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(row)
    cleaned.pop("snapshot_id", None)
    cleaned.pop("relative_position_result_id", None)
    return cleaned


def _strip_filing_valuation_run_metadata(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(row)
    cleaned.pop("calculated_at_utc", None)
    cleaned.pop("valuation_revised_result_id", None)
    return cleaned


def load_relative_valuation_source(
    paths: ReadOnlySourcePaths,
    *,
    as_of_date: str,
    freshness_days: int = CURRENT_FRESHNESS_DAYS,
) -> RelativeValuationSource:
    _validate_paths(paths)
    snapshot_date = date.fromisoformat(as_of_date)
    if freshness_days != CURRENT_FRESHNESS_DAYS:
        raise ValueError("RELATIVE_VALUATION_FRESHNESS_MUST_BE_180_DAYS")
    identity = peer_source.build_identity_index(paths.canonical_db)
    classifications, classification_fp = peer_source._classification_source(paths.market_db)
    memberships, taxonomy_audit, taxonomy_fp, taxonomy_metadata = peer_source._taxonomy_source(paths.taxonomy_db, identity)
    universe_members, universe_metadata = _active_universe_members(paths.canonical_db, as_of_date)
    security_eligibility, listing_metadata = _listing_eligibility(paths, as_of_date)
    with _readonly(paths.analysis_db) as analysis:
        assert_v2_active(analysis)
        valuation_rows = [_strip_filing_valuation_run_metadata(dict(row)) for row in analysis.execute(
            "SELECT * FROM valuation_revised_result WHERE model_fingerprint=? AND history_mode='REVISED_HISTORY' "
            "AND (fundamental_available_date IS NULL OR fundamental_available_date<=?) "
            "ORDER BY company_id,fiscal_sequence,valuation_revised_result_id",
            (valuation.MODEL_FINGERPRINT, as_of_date),
        )]
        active_peer = analysis.execute(
            "SELECT a.snapshot_id,s.snapshot_date FROM relative_position_active_snapshot a "
            "JOIN relative_position_snapshot s USING(snapshot_id) WHERE a.model_fingerprint=?",
            (active_relative_position.MODEL_FINGERPRINT,),
        ).fetchone()
        peer_rows = [] if active_peer is None else [_strip_upstream_snapshot_identity(dict(row)) for row in analysis.execute(
            "SELECT * FROM relative_position_result WHERE snapshot_id=? AND measure='ABSOLUTE_VALUATION_SCORE' ORDER BY company_id,peer_scope,peer_group_id",
            (active_peer["snapshot_id"],),
        )]
    with _readonly(paths.canonical_db) as canonical:
        ttm_rows = [dict(row) for row in canonical.execute(
            "SELECT * FROM v4_ttm_values WHERE model_version=? AND ttm_source_available_date<=? "
            "ORDER BY company_id,endpoint_fiscal_year,CASE endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END",
            (TTM_MODEL_VERSION, as_of_date),
        )]
        structural_eligibility, structural_metadata = structural_break.latest_ttm_eligibility(
            canonical, as_of_date=as_of_date
        )
        structural_history_quarters = {
            int(row["company_id"]): structural_break.allowed_history_quarter_ids(
                canonical,
                company_id=int(row["company_id"]),
                current_quarter_id=int(row["endpoint_quarter_id"]),
            )
            for row in ttm_rows
            if int(row["company_id"]) in structural_eligibility
        }
    latest_ttm: dict[int, dict[str, Any]] = {}
    for row in ttm_rows:
        latest_ttm[int(row["company_id"])] = row
    history_by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in valuation_rows:
        history_by_company[int(row["company_id"])].append(row)
    peers_by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in peer_rows:
        peers_by_company[int(row["company_id"])].append(row)

    inputs = []
    classification_counts: Counter[str] = Counter()
    exclusion_counts: Counter[str] = Counter()
    with _readonly(paths.market_db) as market:
        for company_id, anchor in sorted(latest_ttm.items()):
            source_security_id = int(anchor["security_id"]) if anchor.get("security_id") is not None else None
            _, security_id, ticker = peer_source.resolve_observation_security(identity, company_id, source_security_id)
            if universe_members is not None and company_id not in universe_members:
                exclusion_counts["NOT_ACTIVE_OPERATIONAL_UNIVERSE_MEMBER"] += 1
                continue
            if security_id is None:
                exclusion_counts["SECURITY_ID_UNRESOLVED"] += 1
                continue
            security_eligible, security_reason = security_eligibility.get(
                int(security_id),
                (False, "SECURITY_LISTING_INTERVAL_MISSING"),
            )
            if not security_eligible:
                exclusion_counts[security_reason] += 1
                continue
            structural = structural_eligibility.get(company_id)
            if structural is not None and not structural.eligible:
                exclusion_counts[structural.reason_code] += 1
                continue
            classification = peer_source.resolve_classification(classifications, identity, company_id, security_id, ticker)
            classification_counts[classification.status] += 1
            histories = history_by_company.get(company_id, [])
            allowed_quarters = structural_history_quarters.get(company_id)
            if allowed_quarters is not None:
                histories = [row for row in histories if int(row["quarter_id"]) in allowed_quarters]
            filing = histories[-1] if histories else None
            available = str(anchor["ttm_source_available_date"])
            age = (snapshot_date - date.fromisoformat(available)).days
            observation = valuation.ValuationObservation(
                company_id=company_id,
                security_id=security_id,
                ticker=ticker,
                fiscal_year=int(anchor["endpoint_fiscal_year"]),
                fiscal_quarter=str(anchor["endpoint_fiscal_quarter"]),
                quarter_id=int(anchor["endpoint_quarter_id"]),
                period_end=str(anchor["period_end"]),
                fundamental_available_date=available,
                ttm_readiness_status=str(anchor["readiness_status"]),
                ttm_blocker_codes=tuple(json.loads(anchor.get("blocker_codes_json") or "[]")),
                ttm_operating_income=anchor.get("ttm_operating_income"),
                ttm_free_cashflow=anchor.get("ttm_free_cashflow"),
                ttm_net_income_common=anchor.get("ttm_net_income_common"),
                net_income_common_4q_ready=bool(anchor.get("net_income_common_4q_ready")),
                shares_outstanding=anchor.get("shares_outstanding"),
                cash=anchor.get("cash"),
                total_debt=anchor.get("total_debt"),
                sector=classification.sector,
                industry=classification.industry,
            )
            history = tuple(
                HistoricalEndpoint(
                    fiscal_sequence=int(row["fiscal_sequence"]),
                    fiscal_year=int(row["fiscal_year"]),
                    fiscal_quarter=str(row["fiscal_quarter"]),
                    available_date=str(row["fundamental_available_date"]),
                    valuation_status=str(row["valuation_status"]),
                    market_cap=row.get("market_cap"),
                    enterprise_value=row.get("enterprise_value"),
                    ttm_operating_income=row.get("ttm_operating_income"),
                    ttm_free_cashflow=row.get("ttm_free_cashflow"),
                    ttm_reported_common_earnings=row.get("ttm_net_income_common"),
                )
                for row in histories
                if row.get("fundamental_available_date")
            )
            inputs.append(
                RelativeValuationInput(
                    company_id=company_id,
                    security_id=security_id,
                    ticker=ticker,
                    sector=classification.sector,
                    industry=classification.industry,
                    ecosystem_memberships=memberships.get(company_id, ()),
                    endpoint_available_date=available,
                    current_fresh=0 <= age <= freshness_days,
                    valuation_observation=observation,
                    price_bars=_bars(market, ticker, as_of_date) if ticker else (),
                    filing_valuation=filing,
                    filing_peer_results=tuple(peers_by_company.get(company_id, ())),
                    history=history,
                )
            )
    payload = {
        "as_of_date": as_of_date,
        "classification_fingerprint": classification_fp,
        "taxonomy_fingerprint": taxonomy_fp,
        "structural_break_fingerprint": structural_metadata.get("fingerprint"),
        "inputs": [asdict(row) for row in inputs],
    }
    metadata = {
        "as_of_date": as_of_date,
        "complete_current": len(inputs),
        "current_fresh": sum(row.current_fresh for row in inputs),
        "history_rows": len(valuation_rows),
        "dated_history_rows": sum(
            row.get("fundamental_available_date") is not None for row in valuation_rows
        ),
        "filing_peer_rows": len(peer_rows),
        "active_filing_peer_snapshot_date": (
            str(active_peer["snapshot_date"]) if active_peer is not None else None
        ),
        "taxonomy": taxonomy_metadata,
        "taxonomy_audit_rows": len(taxonomy_audit),
        "classification_resolution_counts": dict(sorted(classification_counts.items())),
        "operational_universe": universe_metadata,
        "listing_eligibility": listing_metadata,
        "structural_break": structural_metadata,
        "excluded_input_counts": dict(sorted(exclusion_counts.items())),
    }
    return RelativeValuationSource(
        inputs=tuple(inputs),
        classification_fingerprint=classification_fp,
        taxonomy_fingerprint=taxonomy_fp,
        source_fingerprint=hashlib.sha256(canonical_json(payload).encode("ascii")).hexdigest(),
        metadata=metadata,
    )
