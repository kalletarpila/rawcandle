from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.relative_position.engine import (
    CURRENT_FRESHNESS_DAYS,
    EcosystemMembership,
    RelativeMeasure,
    RelativeObservation,
    canonical_json,
    normalize_classification,
)
from rawcandle.fundamentals.score.engine import (
    MODEL_FINGERPRINT as FUNDAMENTAL_MODEL_FINGERPRINT,
    MODEL_VERSION as FUNDAMENTAL_MODEL_VERSION,
    TTM_MODEL_VERSION,
)
from rawcandle.fundamentals.valuation.engine import (
    MODEL_FINGERPRINT as VALUATION_MODEL_FINGERPRINT,
    MODEL_VERSION as VALUATION_MODEL_VERSION,
)
from rawcandle.fundamentals.valuation.persistence import HISTORY_MODE


DEFAULT_FRESHNESS_DAYS = CURRENT_FRESHNESS_DAYS


@dataclass(frozen=True)
class ReadOnlySourcePaths:
    analysis_db: Path
    canonical_db: Path
    market_db: Path
    taxonomy_db: Path


@dataclass(frozen=True)
class IdentityIndex:
    security_by_id: Mapping[int, Mapping[str, Any]]
    active_by_company: Mapping[int, tuple[Mapping[str, Any], ...]]
    current_ticker_to_companies: Mapping[str, frozenset[int]]
    alias_to_companies: Mapping[str, frozenset[int]]


@dataclass(frozen=True)
class CurrentRelativeSource:
    observations: tuple[RelativeObservation, ...]
    classification_fingerprint: str
    taxonomy_fingerprint: str
    taxonomy_audit: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _validate_paths(paths: ReadOnlySourcePaths) -> None:
    resolved = [path.resolve() for path in (
        paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db
    )]
    if len(set(resolved)) != len(resolved):
        raise ValueError("RELATIVE_POSITION_SOURCE_PATHS_MUST_BE_DISTINCT")
    for path in resolved:
        if not path.is_file():
            raise FileNotFoundError(path)


def build_identity_index(canonical_db: Path) -> IdentityIndex:
    with _readonly(canonical_db) as conn:
        securities = [dict(row) for row in conn.execute(
            "SELECT security_id,company_id,current_ticker,active FROM security ORDER BY security_id"
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
) -> tuple[dict[str, dict[str, str | None]], str]:
    with _readonly(market_db) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT ticker,sector,industry FROM ticker_meta ORDER BY ticker"
        )]
    by_ticker: dict[str, dict[str, str | None]] = {}
    for row in rows:
        ticker = str(row["ticker"])
        if ticker in by_ticker:
            raise ValueError(f"DUPLICATE_TICKER_META:{ticker}")
        by_ticker[ticker] = {
            "sector": normalize_classification(row.get("sector")),
            "industry": normalize_classification(row.get("industry")),
        }
    return by_ticker, _hash(rows)


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


def _fundamental_rows(
    analysis_db: Path, canonical_db: Path, as_of_date: str
) -> list[dict[str, Any]]:
    with _readonly(analysis_db) as conn:
        conn.execute("ATTACH DATABASE ? AS canonical", (f"file:{canonical_db.resolve()}?mode=ro",))
        duplicate = conn.execute(
            """SELECT sr.company_id,sr.quarter_id,COUNT(*) count
                 FROM score_result sr
                WHERE sr.model_fingerprint=?
                GROUP BY sr.company_id,sr.quarter_id HAVING COUNT(*)>1 LIMIT 1""",
            (FUNDAMENTAL_MODEL_FINGERPRINT,),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(
                f"DUPLICATE_FUNDAMENTAL_SOURCE_RESULT:{duplicate['company_id']}:{duplicate['quarter_id']}"
            )
        return [dict(row) for row in conn.execute(
            """WITH ranked AS (
                   SELECT sr.score_result_id,sr.company_id,sr.quarter_id,
                          sr.total_score,sr.readiness_status,sr.missing_input_reason,
                          sr.model_version,sr.model_fingerprint,sr.generated_at_utc,sr.run_id,
                          q.fiscal_year,q.fiscal_quarter,q.period_end,
                          q.source_availability_date,t.security_id,t.output_fingerprint AS ttm_fingerprint,
                          ROW_NUMBER() OVER (
                              PARTITION BY sr.company_id
                              ORDER BY q.fiscal_year DESC,
                                CASE q.fiscal_quarter WHEN 'Q4' THEN 4 WHEN 'Q3' THEN 3
                                     WHEN 'Q2' THEN 2 ELSE 1 END DESC,
                                sr.score_result_id DESC
                          ) rank_number
                     FROM score_result sr
                     JOIN canonical.v4_quarter q ON q.quarter_id=sr.quarter_id
                     LEFT JOIN canonical.v4_ttm_values t
                       ON t.company_id=sr.company_id AND t.endpoint_quarter_id=sr.quarter_id
                      AND t.model_version=?
                    WHERE sr.model_fingerprint=? AND q.source_availability_date<=?
               ) SELECT * FROM ranked WHERE rank_number=1 ORDER BY company_id""",
            (TTM_MODEL_VERSION, FUNDAMENTAL_MODEL_FINGERPRINT, as_of_date),
        )]


def _valuation_rows(analysis_db: Path, as_of_date: str) -> list[dict[str, Any]]:
    with _readonly(analysis_db) as conn:
        return [dict(row) for row in conn.execute(
            """WITH ranked AS (
                   SELECT r.*,ROW_NUMBER() OVER (
                       PARTITION BY company_id
                       ORDER BY fiscal_sequence DESC,valuation_revised_result_id DESC
                   ) rank_number
                     FROM valuation_revised_result r
                    WHERE model_fingerprint=? AND history_mode=?
                      AND fundamental_available_date<=?
               ) SELECT * FROM ranked WHERE rank_number=1 ORDER BY company_id""",
            (VALUATION_MODEL_FINGERPRINT, HISTORY_MODE, as_of_date),
        )]


def _age_days(snapshot: date, available_date: str | None) -> int | None:
    if not available_date:
        return None
    try:
        return (snapshot - date.fromisoformat(available_date)).days
    except ValueError:
        return None


def load_current_relative_source(
    paths: ReadOnlySourcePaths,
    *,
    as_of_date: str,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> CurrentRelativeSource:
    _validate_paths(paths)
    snapshot = date.fromisoformat(as_of_date)
    if freshness_days < 0:
        raise ValueError("FRESHNESS_DAYS_MUST_BE_NONNEGATIVE")
    identity = build_identity_index(paths.canonical_db)
    classifications, classification_fp = _classification_source(paths.market_db)
    memberships, taxonomy_audit, taxonomy_fp, taxonomy_metadata = _taxonomy_source(
        paths.taxonomy_db, identity
    )
    fundamental = _fundamental_rows(paths.analysis_db, paths.canonical_db, as_of_date)
    valuation = _valuation_rows(paths.analysis_db, as_of_date)

    observations: list[RelativeObservation] = []
    identity_counts: Counter[str] = Counter()
    for row in fundamental:
        company_id = int(row["company_id"])
        source_security_id = int(row["security_id"]) if row.get("security_id") is not None else None
        identity_status, security_id, ticker = resolve_observation_security(
            identity, company_id, source_security_id
        )
        identity_counts[identity_status] += 1
        classification = classifications.get(ticker or "", {})
        age = _age_days(snapshot, row.get("source_availability_date"))
        fresh = age is not None and 0 <= age <= freshness_days
        source_status = str(row["readiness_status"])
        eligible = fresh and source_status == "SCORE_FULL"
        reason = "ELIGIBLE" if eligible else (
            "SOURCE_OBSERVATION_DATE_INVALID" if age is None else
            "SOURCE_OBSERVATION_STALE" if not fresh else source_status
        )
        source_payload = {
            key: row.get(key) for key in (
                "score_result_id", "company_id", "quarter_id", "total_score",
                "readiness_status", "missing_input_reason", "model_version",
                "model_fingerprint", "source_availability_date", "ttm_fingerprint",
            )
        }
        observations.append(RelativeObservation(
            source_observation_id=f"score_result:{row['score_result_id']}",
            company_id=company_id,
            security_id=security_id,
            ticker=ticker,
            measure=RelativeMeasure.FUNDAMENTAL_SCORE,
            score=row.get("total_score"),
            source_status=source_status,
            source_eligible=eligible,
            eligibility_reason=reason,
            source_observation_date=row.get("source_availability_date"),
            source_model_version=FUNDAMENTAL_MODEL_VERSION,
            source_model_fingerprint=FUNDAMENTAL_MODEL_FINGERPRINT,
            source_result_fingerprint=_hash(source_payload),
            sector=classification.get("sector"),
            industry=classification.get("industry"),
            ecosystem_memberships=memberships.get(company_id, ()),
        ))

    for row in valuation:
        company_id = int(row["company_id"])
        source_security_id = int(row["security_id"]) if row.get("security_id") is not None else None
        identity_status, security_id, ticker = resolve_observation_security(
            identity, company_id, source_security_id
        )
        identity_counts[identity_status] += 1
        classification = classifications.get(ticker or "", {})
        age = _age_days(snapshot, row.get("fundamental_available_date"))
        fresh = age is not None and 0 <= age <= freshness_days
        source_status = str(row["valuation_status"])
        eligible = fresh and source_status == "VALUATION_FULL"
        reason = "ELIGIBLE" if eligible else (
            "SOURCE_OBSERVATION_DATE_INVALID" if age is None else
            "SOURCE_OBSERVATION_STALE" if not fresh else source_status
        )
        observations.append(RelativeObservation(
            source_observation_id=f"valuation_revised_result:{row['valuation_revised_result_id']}",
            company_id=company_id,
            security_id=security_id,
            ticker=ticker,
            measure=RelativeMeasure.ABSOLUTE_VALUATION_SCORE,
            score=row.get("total_valuation_score"),
            source_status=source_status,
            source_eligible=eligible,
            eligibility_reason=reason,
            source_observation_date=row.get("fundamental_available_date"),
            source_model_version=VALUATION_MODEL_VERSION,
            source_model_fingerprint=VALUATION_MODEL_FINGERPRINT,
            source_result_fingerprint=str(row["result_fingerprint"]),
            sector=classification.get("sector"),
            industry=classification.get("industry"),
            ecosystem_memberships=memberships.get(company_id, ()),
        ))

    observations.sort(key=lambda item: (
        item.measure.value,
        item.company_id if item.company_id is not None else -1,
        item.source_observation_id,
    ))
    eligible_counts = Counter(
        observation.measure.value
        for observation in observations
        if observation.source_eligible
    )
    ecosystem_eligible_counts = Counter(
        observation.measure.value
        for observation in observations
        if observation.source_eligible and any(
            membership.role.strip().upper() in {"CORE", "EXTENDED"}
            for membership in observation.ecosystem_memberships
        )
    )
    metadata = {
        "as_of_date": as_of_date,
        "freshness_days": freshness_days,
        "fundamental_latest_asof": len(fundamental),
        "valuation_latest_asof": len(valuation),
        "eligible_counts": dict(sorted(eligible_counts.items())),
        "ecosystem_eligible_counts": dict(sorted(ecosystem_eligible_counts.items())),
        "fundamental_status_counts": dict(sorted(Counter(
            str(row["readiness_status"]) for row in fundamental
        ).items())),
        "valuation_status_counts": dict(sorted(Counter(
            str(row["valuation_status"]) for row in valuation
        ).items())),
        "identity_resolution_counts": dict(sorted(identity_counts.items())),
        "classification_rows": len(classifications),
        "taxonomy": taxonomy_metadata,
    }
    return CurrentRelativeSource(
        observations=tuple(observations),
        classification_fingerprint=classification_fp,
        taxonomy_fingerprint=taxonomy_fp,
        taxonomy_audit=taxonomy_audit,
        metadata=metadata,
    )
