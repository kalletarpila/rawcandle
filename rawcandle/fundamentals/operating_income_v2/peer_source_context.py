from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .peer_ranking_core import EcosystemMembership, canonical_json, normalize_classification

@dataclass(frozen=True)
class IdentityIndex:
    security_by_id: Mapping[int, Mapping[str, Any]]
    active_by_company: Mapping[int, tuple[Mapping[str, Any], ...]]
    current_ticker_to_companies: Mapping[str, frozenset[int]]
    alias_to_companies: Mapping[str, frozenset[int]]


@dataclass(frozen=True)
class ClassificationLookupResult:
    status: str
    sector: str | None
    industry: str | None
    market: str | None


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _market_from_security(security: Mapping[str, Any] | None) -> str | None:
    if security is None:
        return None
    value = security.get("market") or security.get("exchange")
    if value is None:
        return "usa"
    normalized = str(value).strip().lower()
    if not normalized:
        return "usa"
    if normalized in {"nasdaq", "nyse", "nysemkt", "amex", "arca", "otc", "otcqx", "otcqb"}:
        return "usa"
    return normalized


def build_identity_index(canonical_db: Path) -> IdentityIndex:
    with _readonly(canonical_db) as conn:
        security_columns = _table_columns(conn, "security")
        market_expr = "market" if "market" in security_columns else "exchange AS market" if "exchange" in security_columns else "'usa' AS market"
        securities = [dict(row) for row in conn.execute(
            f"SELECT security_id,company_id,current_ticker,active,{market_expr} FROM security ORDER BY security_id"
        )]
        aliases = [dict(row) for row in conn.execute(
            "SELECT security_id,ticker FROM ticker_alias ORDER BY alias_id"
        )]
    security_by_id = {int(row["security_id"]): row for row in securities}
    active: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    current: dict[str, set[int]] = defaultdict(set)
    alias: dict[str, set[int]] = defaultdict(set)
    for security in securities:
        company_id = int(security["company_id"])
        ticker = str(security["current_ticker"])
        if int(security["active"]) == 1:
            active[company_id].append(security)
            current[ticker].add(company_id)
    for row in aliases:
        security = security_by_id.get(int(row["security_id"]))
        if security is not None:
            alias[str(row["ticker"])].add(int(security["company_id"]))
    return IdentityIndex(
        security_by_id=security_by_id,
        active_by_company={key: tuple(value) for key, value in active.items()},
        current_ticker_to_companies={key: frozenset(value) for key, value in current.items()},
        alias_to_companies={key: frozenset(value) for key, value in alias.items()},
    )


def resolve_observation_security(
    index: IdentityIndex, company_id: int, security_id: int | None
) -> tuple[str, int | None, str | None]:
    if security_id is not None:
        security = index.security_by_id.get(security_id)
        if security is None or int(security["company_id"]) != company_id:
            return "SECURITY_ID_UNRESOLVED", None, None
        return "OBSERVATION_SECURITY_ID", security_id, str(security["current_ticker"])
    active = index.active_by_company.get(company_id, ())
    if len(active) == 1:
        security = active[0]
        return (
            "UNIQUE_ACTIVE_SECURITY_FALLBACK",
            int(security["security_id"]),
            str(security["current_ticker"]),
        )
    return "SECURITY_ID_UNRESOLVED", None, None


def resolve_taxonomy_ticker(
    ticker: str, index: IdentityIndex
) -> tuple[str, int | None]:
    direct = index.current_ticker_to_companies.get(ticker, frozenset())
    aliases = index.alias_to_companies.get(ticker, frozenset())
    if len(direct) == 1:
        company_id = next(iter(direct))
        if aliases and aliases != direct:
            return "CONFLICT_CURRENT_VS_ALIAS", None
        return "DIRECT_CURRENT_TICKER", company_id
    if len(direct) > 1:
        return "AMBIGUOUS_CURRENT_TICKER", None
    if len(aliases) == 1:
        return "ALIAS_ONLY", next(iter(aliases))
    if len(aliases) > 1:
        return "AMBIGUOUS_ALIAS", None
    return "UNMAPPED", None


def _classification_source(
    market_db: Path,
) -> tuple[dict[tuple[str, str], dict[str, str | None]], str]:
    with _readonly(market_db) as conn:
        columns = _table_columns(conn, "ticker_meta")
        market_expr = "market" if "market" in columns else "'usa' AS market"
        rows = [dict(row) for row in conn.execute(
            f"SELECT ticker,{market_expr},sector,industry FROM ticker_meta ORDER BY ticker,market"
        )]
    by_ticker: dict[tuple[str, str], dict[str, str | None]] = {}
    for row in rows:
        ticker = str(row["ticker"]).upper()
        market = str(row["market"]).lower()
        key = (ticker, market)
        if key in by_ticker:
            raise ValueError(f"DUPLICATE_TICKER_META:{ticker}:{market}")
        by_ticker[key] = {
            "sector": normalize_classification(row.get("sector")),
            "industry": normalize_classification(row.get("industry")),
            "market": market,
        }
    return by_ticker, _hash(rows)


def resolve_classification(
    classifications: Mapping[tuple[str, str], Mapping[str, str | None]],
    index: IdentityIndex,
    company_id: int,
    security_id: int | None,
    ticker: str | None,
) -> ClassificationLookupResult:
    if ticker is None:
        return ClassificationLookupResult("CLASSIFICATION_IDENTITY_UNRESOLVED", None, None, None)
    security = index.security_by_id.get(security_id) if security_id is not None else None
    if security is None or int(security["company_id"]) != company_id:
        return ClassificationLookupResult("CLASSIFICATION_SECURITY_UNRESOLVED", None, None, None)
    market = _market_from_security(security)
    if market is None:
        return ClassificationLookupResult("CLASSIFICATION_MARKET_UNRESOLVED", None, None, None)
    direct = classifications.get((ticker.upper(), market))
    if direct is None:
        same_ticker = [value for (candidate_ticker, _), value in classifications.items() if candidate_ticker == ticker.upper()]
        status = "CLASSIFICATION_MARKET_MISMATCH" if same_ticker else "CLASSIFICATION_MISSING"
        return ClassificationLookupResult(status, None, None, market)
    if direct.get("sector") is None or direct.get("industry") is None:
        return ClassificationLookupResult("CLASSIFICATION_INCOMPLETE", None, None, market)
    return ClassificationLookupResult("CLASSIFICATION_READY", direct.get("sector"), direct.get("industry"), market)


def _taxonomy_source(
    taxonomy_db: Path, index: IdentityIndex
) -> tuple[dict[int, tuple[EcosystemMembership, ...]], tuple[dict[str, Any], ...], str, dict[str, Any]]:
    with _readonly(taxonomy_db) as conn:
        versions = [dict(row) for row in conn.execute(
            """SELECT tv.taxonomy_version_id,tv.taxonomy_version_code,tv.source_reference,
                      tv.source_hash,e.ecosystem_code
                 FROM ec_taxonomy_version tv
                 JOIN ec_ecosystem e ON e.ecosystem_id=tv.ecosystem_id
                WHERE tv.status='ACTIVE' AND tv.is_active=1 AND e.status='ACTIVE'
                ORDER BY e.ecosystem_code,tv.taxonomy_version_id"""
        )]
        rows = [dict(row) for row in conn.execute(
            """SELECT tv.taxonomy_version_id,tv.taxonomy_version_code,
                      e.ecosystem_code,t.ticker,m.membership_id,
                      m.membership_role,m.is_primary,m.role_weight
                 FROM ec_membership m
                 JOIN ec_taxonomy_version tv
                   ON tv.taxonomy_version_id=m.taxonomy_version_id
                 JOIN ec_ecosystem e ON e.ecosystem_id=m.ecosystem_id
                 JOIN ec_entity t
                   ON t.entity_id=m.child_entity_id AND t.entity_type='TICKER'
                WHERE tv.status='ACTIVE' AND tv.is_active=1
                  AND e.status='ACTIVE' AND m.status='ACTIVE' AND t.status='ACTIVE'
                ORDER BY e.ecosystem_code,t.ticker,m.membership_id"""
        )]
    memberships: dict[int, list[EcosystemMembership]] = defaultdict(list)
    audit: list[dict[str, Any]] = []
    ticker_mappings: dict[tuple[str, str], tuple[str, int | None]] = {}
    for row in rows:
        ticker = str(row["ticker"])
        key = (str(row["ecosystem_code"]), ticker)
        mapping = ticker_mappings.setdefault(key, resolve_taxonomy_ticker(ticker, index))
        status, company_id = mapping
        audit_row = {
            **row,
            "mapping_status": status,
            "company_id": company_id,
        }
        audit.append(audit_row)
        if company_id is not None:
            memberships[company_id].append(
                EcosystemMembership(
                    ecosystem_id=str(row["ecosystem_code"]),
                    role=str(row["membership_role"] or ""),
                    membership_id=str(row["membership_id"]),
                )
            )
    fingerprint = _hash({"versions": versions, "memberships": rows, "mapping": audit})
    unique_mapping_counts = Counter(status for status, _ in ticker_mappings.values())
    metadata = {
        "active_versions": versions,
        "membership_rows": len(rows),
        "unique_tickers": len(ticker_mappings),
        "mapped_companies": len(memberships),
        "unique_ticker_mapping_counts": dict(sorted(unique_mapping_counts.items())),
    }
    return (
        {company_id: tuple(items) for company_id, items in memberships.items()},
        tuple(audit),
        fingerprint,
        metadata,
    )
