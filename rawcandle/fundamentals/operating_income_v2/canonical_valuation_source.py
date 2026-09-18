"""Read canonical TTM valuation inputs without a legacy valuation engine."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .valuation import PriceBar


@dataclass(frozen=True)
class CanonicalValuationObservation:
    company_id: int
    security_id: int | None
    ticker: str | None
    fiscal_year: int
    fiscal_quarter: str
    quarter_id: int
    period_end: str
    fundamental_available_date: str | None
    ttm_readiness_status: str
    ttm_blocker_codes: tuple[str, ...]
    ttm_ebit: float | None
    ttm_free_cashflow: float | None
    ttm_net_income_common: float | None
    net_income_common_4q_ready: bool
    shares_outstanding: float | None
    cash: float | None
    total_debt: float | None
    sector: str | None
    industry: str | None


@dataclass(frozen=True)
class ValuationSource:
    rows: tuple[dict[str, Any], ...]
    source_fingerprint: str


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def fiscal_sequence(year: int, quarter: str) -> int:
    return year * 4 + int(quarter.removeprefix("Q"))


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _attached_table_columns(conn: sqlite3.Connection, schema: str, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA {schema}.table_info({table})")}


def _market_identity_sql(expr: str) -> str:
    return (
        f"CASE LOWER(COALESCE({expr},'usa')) "
        "WHEN 'nasdaq' THEN 'usa' WHEN 'nyse' THEN 'usa' WHEN 'nysemkt' THEN 'usa' "
        "WHEN 'amex' THEN 'usa' WHEN 'arca' THEN 'usa' WHEN 'otc' THEN 'usa' "
        "WHEN 'otcqx' THEN 'usa' WHEN 'otcqb' THEN 'usa' ELSE LOWER(COALESCE("
        f"{expr},'usa')) END"
    )


def load_canonical_source(canonical_db: Path, market_db: Path) -> ValuationSource:
    with _readonly(canonical_db) as conn:
        conn.execute(f"ATTACH DATABASE 'file:{market_db}?mode=ro' AS market")
        security_columns = _table_columns(conn, "security")
        market_columns = _attached_table_columns(conn, "market", "ticker_meta")
        security_market = "s.market" if "market" in security_columns else "s.exchange" if "exchange" in security_columns else "'usa'"
        ticker_meta_market = "tm.market" if "market" in market_columns else "'usa'"
        rows = conn.execute(
            f"""
            SELECT t.*, s.current_ticker AS ticker, s.active AS security_active,
                   tm.sector, tm.industry,
                   px.pvm AS price_date, px.open AS price_open, px.high AS price_high,
                   px.low AS price_low, px.close AS price_close
            FROM v4_ttm_values t
            LEFT JOIN security s ON s.security_id=t.security_id AND s.company_id=t.company_id
            LEFT JOIN market.ticker_meta tm ON UPPER(tm.ticker)=UPPER(s.current_ticker)
                 AND {_market_identity_sql(ticker_meta_market)}={_market_identity_sql(security_market)}
            LEFT JOIN market.osakedata px ON px.id=(
                SELECT p.id FROM market.osakedata p
                WHERE p.osake=s.current_ticker AND p.pvm<=t.ttm_source_available_date
                  AND p.open>0 AND p.high>0 AND p.low>0 AND p.close>0
                  AND p.high>=MAX(p.open,p.close,p.low)
                  AND p.low<=MIN(p.open,p.close,p.high)
                ORDER BY p.pvm DESC LIMIT 1
            )
            WHERE t.model_version='V4_TTM_EBIT_FIRST_V1'
            ORDER BY t.company_id,t.endpoint_fiscal_year,
                CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,
                t.ttm_id
            """
        ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        blockers = tuple(json.loads(row["blocker_codes_json"] or "[]"))
        observation = CanonicalValuationObservation(
            company_id=int(row["company_id"]),
            security_id=int(row["security_id"]) if row["security_id"] is not None else None,
            ticker=row["ticker"],
            fiscal_year=int(row["endpoint_fiscal_year"]),
            fiscal_quarter=str(row["endpoint_fiscal_quarter"]),
            quarter_id=int(row["endpoint_quarter_id"]),
            period_end=str(row["period_end"]),
            fundamental_available_date=row["ttm_source_available_date"],
            ttm_readiness_status=str(row["readiness_status"]),
            ttm_blocker_codes=blockers,
            ttm_ebit=_finite(row["ttm_ebit"]),
            ttm_free_cashflow=_finite(row["ttm_free_cashflow"]),
            ttm_net_income_common=_finite(row["ttm_net_income_common"]),
            net_income_common_4q_ready=bool(row["net_income_common_4q_ready"]),
            shares_outstanding=_finite(row["shares_outstanding"]),
            cash=_finite(row["cash"]),
            total_debt=_finite(row["total_debt"]),
            sector=row["sector"],
            industry=row["industry"],
        )
        bars = () if row["price_date"] is None else (PriceBar(
            price_date=str(row["price_date"]), open=row["price_open"], high=row["price_high"],
            low=row["price_low"], close=row["price_close"],
        ),)
        source_payload = {
            "observation": asdict(observation),
            "price_bars": [asdict(bar) for bar in bars],
            "security_active": row["security_active"],
            "ttm_output_fingerprint": row["output_fingerprint"],
        }
        output.append({
            "observation": observation,
            "price_bars": bars,
            "security_active": row["security_active"],
            "source_fingerprint": _hash(source_payload),
        })
    return ValuationSource(tuple(output), _hash([row["source_fingerprint"] for row in output]))
