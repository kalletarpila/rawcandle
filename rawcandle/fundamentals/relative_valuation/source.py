from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.operating_income_v2 import valuation
from rawcandle.fundamentals.operating_income_v2 import relative_position as active_relative_position
from rawcandle.fundamentals.operating_income_v2.activation import assert_v2_active
from rawcandle.fundamentals.relative_position import source as peer_source
from rawcandle.fundamentals.relative_position.engine import CURRENT_FRESHNESS_DAYS
from rawcandle.fundamentals.score.engine import TTM_MODEL_VERSION

from .engine import HistoricalEndpoint, RelativeValuationInput, canonical_json


@dataclass(frozen=True)
class ReadOnlySourcePaths:
    analysis_db: Path
    canonical_db: Path
    market_db: Path
    taxonomy_db: Path


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
    configured = (paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db)
    for path in configured:
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(path)
    resolved = tuple(path.resolve() for path in configured)
    if len(set(resolved)) != len(resolved):
        raise ValueError("RELATIVE_VALUATION_SOURCE_PATHS_MUST_BE_DISTINCT")


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
    with _readonly(paths.analysis_db) as analysis:
        assert_v2_active(analysis)
        valuation_rows = [dict(row) for row in analysis.execute(
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
        peer_rows = [] if active_peer is None else [dict(row) for row in analysis.execute(
            "SELECT * FROM relative_position_result WHERE snapshot_id=? AND measure='ABSOLUTE_VALUATION_SCORE' ORDER BY company_id,peer_scope,peer_group_id",
            (active_peer["snapshot_id"],),
        )]
    with _readonly(paths.canonical_db) as canonical:
        ttm_rows = [dict(row) for row in canonical.execute(
            "SELECT * FROM v4_ttm_values WHERE model_version=? AND ttm_source_available_date<=? "
            "ORDER BY company_id,endpoint_fiscal_year,CASE endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END",
            (TTM_MODEL_VERSION, as_of_date),
        )]
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
    with _readonly(paths.market_db) as market:
        for company_id, anchor in sorted(latest_ttm.items()):
            source_security_id = int(anchor["security_id"]) if anchor.get("security_id") is not None else None
            _, security_id, ticker = peer_source.resolve_observation_security(identity, company_id, source_security_id)
            classification = classifications.get(ticker or "", {})
            histories = history_by_company.get(company_id, [])
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
                sector=classification.get("sector"),
                industry=classification.get("industry"),
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
                    sector=classification.get("sector"),
                    industry=classification.get("industry"),
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
    }
    return RelativeValuationSource(
        inputs=tuple(inputs),
        classification_fingerprint=classification_fp,
        taxonomy_fingerprint=taxonomy_fp,
        source_fingerprint=hashlib.sha256(canonical_json(payload).encode("ascii")).hexdigest(),
        metadata=metadata,
    )
