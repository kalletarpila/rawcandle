from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from rawcandle.fundamentals.diagnostic_flags.engine import (
    DiagnosticEndpoint,
    DiagnosticInput,
    canonical_json,
    fingerprint,
)


@dataclass(frozen=True)
class ReadOnlyDiagnosticPaths:
    canonical_db: Path
    analysis_db: Path


@dataclass(frozen=True)
class DiagnosticSourceRow:
    diagnostic_input: DiagnosticInput
    ticker: str
    sector: str | None
    industry: str | None
    lifecycle: str | None
    lifecycle_status: str | None
    market_cap: float | None

    def to_source_dict(self) -> dict[str, Any]:
        current = self.diagnostic_input.current
        prior = self.diagnostic_input.prior
        return {
            "ticker": self.ticker,
            "sector": self.sector,
            "industry": self.industry,
            "lifecycle": self.lifecycle,
            "lifecycle_status": self.lifecycle_status,
            "market_cap": self.market_cap,
            "fiscal_chain_consecutive": self.diagnostic_input.fiscal_chain_consecutive,
            "current": current.__dict__,
            "prior": prior.__dict__ if prior else None,
        }


@dataclass(frozen=True)
class DiagnosticSource:
    rows: tuple[DiagnosticSourceRow, ...]
    source_fingerprint: str
    source_model_fingerprints: tuple[tuple[str, str], ...]


def connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _fiscal_sequence(year: Any, quarter: Any) -> int:
    position = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(str(quarter))
    if position is None:
        raise ValueError(f"INVALID_FISCAL_QUARTER:{quarter}")
    return int(year) * 4 + position


def _models(conn: sqlite3.Connection) -> tuple[tuple[str, str], ...]:
    tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    result: list[tuple[str, str]] = []
    for name, table in (
        ("score", "score_result"),
        ("lifecycle", "lifecycle_revised_result"),
        ("valuation", "valuation_revised_result"),
        ("delta", "fundamental_delta_result"),
    ):
        if table not in tables:
            continue
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        if "model_fingerprint" in columns:
            values = tuple(str(row[0]) for row in conn.execute(f"SELECT DISTINCT model_fingerprint FROM {table} ORDER BY model_fingerprint"))
            result.append((name, "|".join(values)))
    return tuple(result)


def load_diagnostic_source(paths: ReadOnlyDiagnosticPaths) -> DiagnosticSource:
    """Resolve revised endpoint inputs without writing or reading raw provider JSON."""
    with connect_readonly(paths.analysis_db) as analysis:
        trajectory = {
            int(row["quarter_id"]): _number(row["component_score"])
            for row in analysis.execute(
                """SELECT sr.quarter_id,sc.component_score
                   FROM score_component sc JOIN score_result sr USING(score_result_id)
                   WHERE sc.component_name='FUNDAMENTAL_TRAJECTORY'"""
            )
        }
        valuations = {
            int(row["quarter_id"]): dict(row)
            for row in analysis.execute("SELECT * FROM valuation_revised_result ORDER BY quarter_id")
        }
        lifecycles = {
            int(row["quarter_id"]): dict(row)
            for row in analysis.execute(
                "SELECT quarter_id,final_state,lifecycle_status FROM lifecycle_revised_result ORDER BY quarter_id"
            )
        }
        source_models = _models(analysis)

    with connect_readonly(paths.canonical_db) as canonical:
        raw_rows = [
            dict(row)
            for row in canonical.execute(
                """SELECT t.company_id,t.endpoint_quarter_id AS quarter_id,t.endpoint_fiscal_year AS fiscal_year,
                          t.endpoint_fiscal_quarter AS fiscal_quarter,t.period_end,t.readiness_status AS ttm_status,
                          t.ttm_source_available_date,t.ttm_revenue,t.ttm_ebit,t.ttm_net_income_common,
                          t.ttm_operating_cashflow,t.ttm_capex,t.cash,t.total_debt,
                          q.source_availability_date,f.accounts_receivable,f.inventory,f.accounts_payable,
                          f.deferred_revenue,f.total_assets,s.current_ticker AS ticker
                   FROM v4_ttm_values t
                   JOIN v4_quarter q ON q.quarter_id=t.endpoint_quarter_id
                   JOIN v4_quarter_financials f ON f.quarter_id=t.endpoint_quarter_id
                   JOIN security s ON s.security_id=t.security_id
                   WHERE t.model_version=(SELECT model_version FROM v4_ttm_values ORDER BY ttm_id DESC LIMIT 1)
                   ORDER BY t.company_id,t.endpoint_fiscal_year,
                            CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,
                            t.endpoint_quarter_id"""
            )
        ]

    endpoints: dict[tuple[int, int], DiagnosticEndpoint] = {}
    metadata: dict[tuple[int, int], tuple[str, str | None, str | None, str | None, str | None, float | None]] = {}
    for row in raw_rows:
        quarter_id = int(row["quarter_id"])
        valuation = valuations.get(quarter_id, {})
        lifecycle = lifecycles.get(quarter_id, {})
        sequence = _fiscal_sequence(row["fiscal_year"], row["fiscal_quarter"])
        endpoint = DiagnosticEndpoint(
            company_id=int(row["company_id"]),
            quarter_id=quarter_id,
            fiscal_year=int(row["fiscal_year"]),
            fiscal_quarter=str(row["fiscal_quarter"]),
            fiscal_sequence=sequence,
            period_end=str(row["period_end"]),
            source_available_date=row["source_availability_date"],
            ttm_available_date=row["ttm_source_available_date"],
            valuation_available_date=valuation.get("fundamental_available_date"),
            ttm_status=row["ttm_status"],
            revenue=_number(row["ttm_revenue"]),
            ebit=_number(row["ttm_ebit"]),
            common_earnings=_number(row["ttm_net_income_common"]),
            operating_cashflow=_number(row["ttm_operating_cashflow"]),
            capex=_number(row["ttm_capex"]),
            cash=_number(row["cash"]),
            total_debt=_number(row["total_debt"]),
            accounts_receivable=_number(row["accounts_receivable"]),
            inventory=_number(row["inventory"]),
            accounts_payable=_number(row["accounts_payable"]),
            deferred_revenue=_number(row["deferred_revenue"]),
            total_assets=_number(row["total_assets"]),
            trajectory=trajectory.get(quarter_id),
            valuation_status=valuation.get("valuation_status"),
            valuation_reason=valuation.get("reason_code"),
            applicability_classification=valuation.get("applicability_classification"),
            applicability_reason=valuation.get("reason_code") if valuation.get("applicability_classification") != "SUPPORTED" else "SUPPORTED_OPERATING_CLASS",
            ebit_yield=_number(valuation.get("ebit_yield")),
            fcf_yield=_number(valuation.get("fcf_yield")),
            earnings_yield=_number(valuation.get("earnings_yield")),
        )
        key = (endpoint.company_id, sequence)
        if key in endpoints:
            raise ValueError(f"DUPLICATE_FISCAL_IDENTITY:{key[0]}:{key[1]}")
        endpoints[key] = endpoint
        metadata[key] = (
            str(row["ticker"]),
            valuation.get("sector"),
            valuation.get("industry"),
            lifecycle.get("final_state"),
            lifecycle.get("lifecycle_status"),
            _number(valuation.get("market_cap")),
        )

    output: list[DiagnosticSourceRow] = []
    for key in sorted(endpoints):
        current = endpoints[key]
        prior = endpoints.get((current.company_id, current.fiscal_sequence - 1))
        chronology_valid = bool(
            prior
            and prior.period_end < current.period_end
            and prior.source_available_date
            and current.source_available_date
            and prior.source_available_date <= current.source_available_date
        )
        ticker, sector, industry, lifecycle, lifecycle_status, market_cap = metadata[key]
        output.append(
            DiagnosticSourceRow(
                diagnostic_input=DiagnosticInput(current, prior, chronology_valid),
                ticker=ticker,
                sector=sector,
                industry=industry,
                lifecycle=lifecycle,
                lifecycle_status=lifecycle_status,
                market_cap=market_cap,
            )
        )
    payload = {
        "rows": [row.to_source_dict() for row in output],
        "source_model_fingerprints": source_models,
    }
    return DiagnosticSource(tuple(output), fingerprint(payload), source_models)


def latest_fresh_source_rows(
    rows: Iterable[DiagnosticSourceRow],
    *,
    as_of: date,
    freshness_days: int = 180,
) -> tuple[DiagnosticSourceRow, ...]:
    latest: dict[int, DiagnosticSourceRow] = {}
    for row in rows:
        endpoint = row.diagnostic_input.current
        available = endpoint.ttm_available_date or endpoint.source_available_date
        if not available or available > as_of.isoformat():
            continue
        existing = latest.get(endpoint.company_id)
        key = (available, endpoint.fiscal_sequence, endpoint.quarter_id)
        if existing is None:
            latest[endpoint.company_id] = row
            continue
        other = existing.diagnostic_input.current
        other_available = other.ttm_available_date or other.source_available_date or ""
        if key > (other_available, other.fiscal_sequence, other.quarter_id):
            latest[endpoint.company_id] = row
    return tuple(
        sorted(
            (
                row for row in latest.values()
                if (as_of - date.fromisoformat(row.diagnostic_input.current.ttm_available_date or row.diagnostic_input.current.source_available_date or "")).days <= freshness_days
            ),
            key=lambda row: (row.ticker, row.diagnostic_input.current.company_id),
        )
    )


def normalized_source_bytes(source: DiagnosticSource) -> bytes:
    return (canonical_json({"source_fingerprint": source.source_fingerprint, "rows": [row.to_source_dict() for row in source.rows]}) + "\n").encode("ascii")
