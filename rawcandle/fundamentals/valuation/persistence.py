from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.valuation.engine import (
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    PriceBar,
    ValuationObservation,
    calculate_valuation,
    classify_applicability,
)


HISTORY_MODE = "REVISED_HISTORY"
TABLE_NAME = "valuation_revised_result"
PERSISTENCE_SCHEMA_VERSION = "V4_VALUATION_REVISED_HISTORY_V1"
CURRENT_FRESHNESS_DAYS = 180

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    valuation_revised_result_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    ticker TEXT,
    security_active INTEGER CHECK (security_active IN (0,1)),
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    fiscal_sequence INTEGER NOT NULL,
    quarter_id INTEGER NOT NULL,
    period_end TEXT NOT NULL,
    fundamental_available_date TEXT,
    price_date TEXT,
    price_age_calendar_days INTEGER,
    selected_price REAL,
    shares_outstanding REAL,
    market_cap REAL,
    cash REAL,
    total_debt REAL,
    net_debt REAL,
    enterprise_value REAL,
    ttm_ebit REAL,
    ttm_free_cashflow REAL,
    ttm_net_income_common REAL,
    ebit_yield REAL,
    ebit_points REAL,
    fcf_yield REAL,
    fcf_points REAL,
    earnings_yield REAL,
    earnings_points REAL,
    total_valuation_score REAL,
    valuation_status TEXT NOT NULL CHECK (valuation_status IN ('VALUATION_FULL','VALUATION_NOT_READY','VALUATION_NOT_APPLICABLE')),
    reason_code TEXT NOT NULL,
    applicability_classification TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    engine_result_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    history_mode TEXT NOT NULL CHECK (history_mode='REVISED_HISTORY'),
    calculated_at_utc TEXT NOT NULL,
    UNIQUE(company_id,fiscal_year,fiscal_quarter,model_fingerprint,history_mode)
);
CREATE INDEX IF NOT EXISTS idx_valuation_revised_current
    ON {TABLE_NAME}(model_fingerprint,history_mode,company_id,fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_valuation_revised_status
    ON {TABLE_NAME}(model_fingerprint,history_mode,valuation_status,reason_code);
"""

LOGICAL_FIELDS = (
    "company_id", "security_id", "ticker", "security_active", "fiscal_year", "fiscal_quarter",
    "fiscal_sequence", "quarter_id", "period_end", "fundamental_available_date", "price_date",
    "price_age_calendar_days", "selected_price", "shares_outstanding", "market_cap", "cash",
    "total_debt", "net_debt", "enterprise_value", "ttm_ebit", "ttm_free_cashflow",
    "ttm_net_income_common", "ebit_yield", "ebit_points", "fcf_yield", "fcf_points",
    "earnings_yield", "earnings_points", "total_valuation_score", "valuation_status",
    "reason_code", "applicability_classification", "sector", "industry", "model_version",
    "model_fingerprint", "source_fingerprint", "engine_result_fingerprint", "result_fingerprint",
    "history_mode",
)


@dataclass(frozen=True)
class ValuationSource:
    rows: tuple[dict[str, Any], ...]
    source_fingerprint: str


@dataclass(frozen=True)
class ReplaceReport:
    rows_before: int
    rows_after: int
    rows_deleted: int
    rows_inserted: int
    rows_unchanged: int
    result_fingerprint: str


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


def load_canonical_source(canonical_db: Path, market_db: Path) -> ValuationSource:
    with _readonly(canonical_db) as conn:
        conn.execute(f"ATTACH DATABASE 'file:{market_db}?mode=ro' AS market")
        rows = conn.execute(
            """
            SELECT t.*, s.current_ticker AS ticker, s.active AS security_active,
                   tm.sector, tm.industry,
                   px.pvm AS price_date, px.open AS price_open, px.high AS price_high,
                   px.low AS price_low, px.close AS price_close
            FROM v4_ttm_values t
            LEFT JOIN security s ON s.security_id=t.security_id AND s.company_id=t.company_id
            LEFT JOIN market.ticker_meta tm ON tm.ticker=s.current_ticker
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
        observation = ValuationObservation(
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


def build_persisted_results(source: ValuationSource, *, calculated_at: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source_row in source.rows:
        observation = source_row["observation"]
        result = calculate_valuation(observation, source_row["price_bars"])
        applicability = classify_applicability(observation.sector, observation.industry)
        classification = "SUPPORTED" if applicability.supported is True else "NOT_APPLICABLE" if applicability.supported is False else "NOT_READY"
        row = {
            **result.to_dict(),
            "security_active": source_row["security_active"],
            "fiscal_sequence": fiscal_sequence(result.fiscal_year, result.fiscal_quarter),
            "applicability_classification": classification,
            "sector": observation.sector,
            "industry": observation.industry,
            "source_fingerprint": source_row["source_fingerprint"],
            "engine_result_fingerprint": result.result_fingerprint,
            "history_mode": HISTORY_MODE,
            "calculated_at_utc": calculated_at,
        }
        row.pop("result_fingerprint")
        row["result_fingerprint"] = _hash({field: row.get(field) for field in LOGICAL_FIELDS if field != "result_fingerprint"})
        output.append(row)
    validate_rows(output)
    return output


def validate_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        identity = (row.get("company_id"), row.get("fiscal_year"), row.get("fiscal_quarter"), row.get("model_fingerprint"))
        if identity in seen:
            raise ValueError(f"DUPLICATE_VALUATION_RESULT:{identity}")
        seen.add(identity)
        if row.get("model_version") != MODEL_VERSION or row.get("model_fingerprint") != MODEL_FINGERPRINT:
            raise ValueError("VALUATION_MODEL_IDENTITY_MISMATCH")
        if row.get("history_mode") != HISTORY_MODE:
            raise ValueError("INVALID_VALUATION_HISTORY_MODE")
        status = row.get("valuation_status")
        score = _finite(row.get("total_valuation_score"))
        if status == "VALUATION_FULL":
            if row.get("reason_code") != "VALUATION_FULL" or row.get("applicability_classification") != "SUPPORTED":
                raise ValueError("VALUATION_FULL_STATUS_REASON_MISMATCH")
            if score is None or not 0 <= score <= 100:
                raise ValueError("VALUATION_FULL_SCORE_INVALID")
            required = ("selected_price", "shares_outstanding", "market_cap", "cash", "total_debt", "enterprise_value", "ttm_ebit", "ttm_free_cashflow", "ttm_net_income_common")
            if any(_finite(row.get(field)) is None for field in required):
                raise ValueError("VALUATION_FULL_REQUIRED_INPUT_MISSING")
        elif status in ("VALUATION_NOT_READY", "VALUATION_NOT_APPLICABLE"):
            if score is not None:
                raise ValueError("NON_FULL_VALUATION_HAS_SCORE")
            expected = "NOT_READY" if status == "VALUATION_NOT_READY" else "NOT_APPLICABLE"
            if row.get("applicability_classification") != expected and status == "VALUATION_NOT_APPLICABLE":
                raise ValueError("VALUATION_APPLICABILITY_STATUS_MISMATCH")
        else:
            raise ValueError("VALUATION_STATUS_INVALID")
        if not row.get("source_fingerprint") or not row.get("engine_result_fingerprint"):
            raise ValueError("VALUATION_FINGERPRINT_MISSING")
        expected_result = _hash({field: row.get(field) for field in LOGICAL_FIELDS if field != "result_fingerprint"})
        if row.get("result_fingerprint") != expected_result:
            raise ValueError("VALUATION_RESULT_FINGERPRINT_MISMATCH")


def logical_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    values = [[row.get(field) for field in LOGICAL_FIELDS] for row in rows]
    values.sort(key=lambda item: (item[0], item[6], item[35]))
    return _hash(values)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version(db_name TEXT PRIMARY KEY,version TEXT NOT NULL,applied_at_utc TEXT NOT NULL)")


def persisted_rows(conn: sqlite3.Connection, *, model_fingerprint: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        f"SELECT * FROM {TABLE_NAME} WHERE model_fingerprint=? AND history_mode=? ORDER BY company_id,fiscal_sequence",
        (model_fingerprint, HISTORY_MODE),
    )]


def replace_results(conn: sqlite3.Connection, rows: Sequence[Mapping[str, Any]]) -> ReplaceReport:
    validate_rows(rows)
    target = logical_fingerprint(rows)
    ensure_schema(conn)
    existing = persisted_rows(conn, model_fingerprint=MODEL_FINGERPRINT)
    if logical_fingerprint(existing) == target:
        return ReplaceReport(len(existing), len(existing), 0, 0, len(existing), target)
    columns = (*LOGICAL_FIELDS, "calculated_at_utc")
    conn.execute("SAVEPOINT valuation_revised_replace")
    try:
        conn.execute(f"DELETE FROM {TABLE_NAME} WHERE model_fingerprint=? AND history_mode=?", (MODEL_FINGERPRINT, HISTORY_MODE))
        conn.executemany(
            f"INSERT INTO {TABLE_NAME} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [[row.get(column) for column in columns] for row in rows],
        )
        stored = persisted_rows(conn, model_fingerprint=MODEL_FINGERPRINT)
        if logical_fingerprint(stored) != target:
            raise RuntimeError("PERSISTED_VALUATION_FINGERPRINT_MISMATCH")
        conn.execute("RELEASE valuation_revised_replace")
    except Exception:
        conn.execute("ROLLBACK TO valuation_revised_replace")
        conn.execute("RELEASE valuation_revised_replace")
        raise
    return ReplaceReport(len(existing), len(rows), len(existing), len(rows), 0, target)


class ValuationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def latest_company(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT * FROM {TABLE_NAME} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence DESC LIMIT 1",
            (company_id, model_fingerprint, HISTORY_MODE),
        ).fetchone()
        return dict(row) if row else None

    def current_universe(self, *, model_fingerprint: str, as_of_date: str, freshness_days: int = CURRENT_FRESHNESS_DAYS) -> list[dict[str, Any]]:
        cutoff = date.fromisoformat(as_of_date)
        rows = self.conn.execute(
            f"""SELECT r.* FROM {TABLE_NAME} r
                WHERE r.model_fingerprint=? AND r.history_mode=?
                  AND r.fundamental_available_date<=?
                  AND r.fiscal_sequence=(SELECT MAX(x.fiscal_sequence) FROM {TABLE_NAME} x
                    WHERE x.company_id=r.company_id AND x.model_fingerprint=r.model_fingerprint
                      AND x.history_mode=r.history_mode AND x.fundamental_available_date<=?)
                ORDER BY r.company_id""",
            (model_fingerprint, HISTORY_MODE, as_of_date, as_of_date),
        ).fetchall()
        return [dict(row) for row in rows if (cutoff - date.fromisoformat(row["fundamental_available_date"])).days <= freshness_days]

    def history(self, company_id: int, *, model_fingerprint: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(
            f"SELECT * FROM {TABLE_NAME} WHERE company_id=? AND model_fingerprint=? AND history_mode=? ORDER BY fiscal_sequence",
            (company_id, model_fingerprint, HISTORY_MODE),
        )]

    def fiscal_quarter(self, company_id: int, fiscal_year: int, fiscal_quarter: str, *, model_fingerprint: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT * FROM {TABLE_NAME} WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=? AND model_fingerprint=? AND history_mode=?",
            (company_id, fiscal_year, fiscal_quarter, model_fingerprint, HISTORY_MODE),
        ).fetchone()
        return dict(row) if row else None

    def by_status(self, status: str, *, model_fingerprint: str, reason_code: str | None = None) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM {TABLE_NAME} WHERE valuation_status=? AND model_fingerprint=? AND history_mode=?"
        params: list[Any] = [status, model_fingerprint, HISTORY_MODE]
        if reason_code is not None:
            sql += " AND reason_code=?"
            params.append(reason_code)
        return [dict(row) for row in self.conn.execute(sql + " ORDER BY company_id,fiscal_sequence", params)]


def quick_check(conn: sqlite3.Connection, *, expected_rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    details: list[str] = []
    try:
        rows = persisted_rows(conn, model_fingerprint=MODEL_FINGERPRINT)
        validate_rows(rows)
        duplicates = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT company_id,fiscal_year,fiscal_quarter,model_fingerprint,COUNT(*) n FROM {TABLE_NAME} GROUP BY 1,2,3,4 HAVING n>1)"
        ).fetchone()[0]
        if duplicates:
            details.append("DUPLICATE_LOGICAL_ROWS")
        for row in rows:
            if row["valuation_status"] != "VALUATION_FULL":
                continue
            if row["price_date"] > row["fundamental_available_date"] or not 0 <= int(row["price_age_calendar_days"]) <= 3:
                details.append("PRICE_DATE_CONTRACT_VIOLATION")
            if row["market_cap"] <= 0 or row["enterprise_value"] <= 0:
                details.append("DENOMINATOR_CONTRACT_VIOLATION")
            points = (row["ebit_points"], row["fcf_points"], row["earnings_points"])
            if not (0 <= points[0] <= 40 and 0 <= points[1] <= 40 and 0 <= points[2] <= 20):
                details.append("COMPONENT_RANGE_VIOLATION")
            if not math.isclose(sum(points), row["total_valuation_score"], abs_tol=1e-9):
                details.append("COMPONENT_SUM_VIOLATION")
            if row["total_valuation_score"] == 0 and not all(row[field] <= 0 for field in ("ttm_ebit", "ttm_free_cashflow", "ttm_net_income_common")):
                details.append("EXACT_ZERO_INVARIANT_VIOLATION")
        sqlite_result = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        foreign_keys = list(conn.execute("PRAGMA foreign_key_check"))
        if sqlite_result.lower() != "ok":
            details.append(f"SQLITE_QUICK_CHECK:{sqlite_result}")
        if foreign_keys:
            details.append("FOREIGN_KEY_CHECK_FAILED")
        result_fp = logical_fingerprint(rows)
        if expected_rows is not None and result_fp != logical_fingerprint(expected_rows):
            details.append("DIRECT_REPLAY_MISMATCH")
    except Exception as exc:
        details.append(f"VALIDATION_ERROR:{exc}")
        rows, result_fp, sqlite_result, foreign_keys = [], "", "not_run", []
    return {
        "ok": not details, "details": details, "rows": len(rows), "result_fingerprint": result_fp,
        "sqlite_quick_check": sqlite_result, "foreign_key_violations": len(foreign_keys),
        "status_counts": dict(sorted(Counter(row["valuation_status"] for row in rows).items())),
    }
