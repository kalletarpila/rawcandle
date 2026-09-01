from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from rawcandle.fundamentals.valuation.engine import (
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    PriceBar,
    ValuationObservation,
    ValuationResult,
    calculate_valuation,
)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_production_source_inputs(
    canonical_db: Path,
    provider_db: Path,
    market_db: Path,
) -> list[tuple[ValuationObservation, list[PriceBar]]]:
    """Build rehearsal inputs without changing production's pre-Phase-3B schema."""
    conn = _connect_readonly(canonical_db)
    try:
        conn.execute(f"ATTACH DATABASE 'file:{provider_db}?mode=ro' AS provider")
        conn.execute(f"ATTACH DATABASE 'file:{market_db}?mode=ro' AS market")
        rows = conn.execute(
            """
            WITH common_income AS (
                SELECT iq.ttm_id,
                       COUNT(*) AS input_count,
                       SUM(CASE WHEN NULLIF(json_extract(po.payload_json, '$.netinccmn'), '') IS NOT NULL THEN 1 ELSE 0 END) AS common_count,
                       SUM(CAST(NULLIF(json_extract(po.payload_json, '$.netinccmn'), '') AS REAL)) AS ttm_net_income_common
                FROM v4_ttm_input_quarter iq
                LEFT JOIN v4_field_provenance fp
                  ON fp.quarter_id=iq.input_quarter_id AND fp.canonical_field='net_income'
                LEFT JOIN provider.provider_observation po
                  ON po.observation_id=fp.provider_observation_id
                GROUP BY iq.ttm_id
            ), endpoint_ticker AS (
                SELECT t.ttm_id, COALESCE(po.provider_ticker, s.current_ticker) AS ticker
                FROM v4_ttm_values t
                LEFT JOIN security s ON s.security_id=t.security_id
                LEFT JOIN v4_field_provenance fp
                  ON fp.quarter_id=t.endpoint_quarter_id AND fp.canonical_field='shares_outstanding'
                LEFT JOIN provider.provider_observation po
                  ON po.observation_id=fp.provider_observation_id
            )
            SELECT t.*, et.ticker, ci.input_count, ci.common_count, ci.ttm_net_income_common,
                   tm.sector, tm.industry,
                   px.pvm AS price_date, px.open AS price_open, px.high AS price_high,
                   px.low AS price_low, px.close AS price_close
            FROM v4_ttm_values t
            LEFT JOIN endpoint_ticker et ON et.ttm_id=t.ttm_id
            LEFT JOIN common_income ci ON ci.ttm_id=t.ttm_id
            LEFT JOIN market.ticker_meta tm ON tm.ticker=et.ticker
            LEFT JOIN market.osakedata px ON px.id=(
                SELECT p2.id FROM market.osakedata p2
                WHERE p2.osake=et.ticker AND p2.pvm<=t.ttm_source_available_date
                  AND p2.open IS NOT NULL AND p2.high IS NOT NULL
                  AND p2.low IS NOT NULL AND p2.close IS NOT NULL
                  AND p2.open>0 AND p2.high>0 AND p2.low>0 AND p2.close>0
                  AND p2.high>=MAX(p2.open,p2.close,p2.low)
                  AND p2.low<=MIN(p2.open,p2.close,p2.high)
                ORDER BY p2.pvm DESC LIMIT 1
            )
            WHERE t.model_version='V4_TTM_EBIT_FIRST_V1'
            ORDER BY t.company_id, t.endpoint_fiscal_year,
                     CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,
                     t.ttm_id
            """
        ).fetchall()
    finally:
        conn.close()

    output: list[tuple[ValuationObservation, list[PriceBar]]] = []
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
            ttm_ebit=row["ttm_ebit"],
            ttm_free_cashflow=row["ttm_free_cashflow"],
            ttm_net_income_common=row["ttm_net_income_common"],
            net_income_common_4q_ready=bool(row["input_count"] == 4 and row["common_count"] == 4),
            shares_outstanding=row["shares_outstanding"],
            cash=row["cash"],
            total_debt=row["total_debt"],
            sector=row["sector"],
            industry=row["industry"],
        )
        bars = []
        if row["price_date"] is not None:
            bars.append(
                PriceBar(
                    price_date=str(row["price_date"]),
                    open=row["price_open"],
                    high=row["price_high"],
                    low=row["price_low"],
                    close=row["price_close"],
                )
            )
        output.append((observation, bars))
    return output


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(values: Iterable[float | None]) -> dict[str, Any]:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return {
        "valid_n": len(valid),
        **{f"p{int(p * 100):02d}": _quantile(valid, p) for p in (0.01, 0.10, 0.25, 0.50, 0.75, 0.90, 0.99)},
    }


def _correlation(results: Sequence[ValuationResult], left: str, right: str) -> float | None:
    pairs = [
        (float(getattr(result, left)), float(getattr(result, right)))
        for result in results
        if getattr(result, left) is not None and getattr(result, right) is not None
    ]
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    return numerator / math.sqrt(x_var * y_var) if x_var > 0 and y_var > 0 else None


def summarize(results: Sequence[ValuationResult]) -> dict[str, Any]:
    statuses = Counter(result.valuation_status for result in results)
    reasons = Counter(result.reason_code for result in results)
    full = [result for result in results if result.valuation_status == "VALUATION_FULL"]
    scores = [float(result.total_valuation_score) for result in full if result.total_valuation_score is not None]
    bands = Counter()
    for score in scores:
        if score < 20:
            bands["0_20"] += 1
        elif score < 40:
            bands["20_40"] += 1
        elif score < 60:
            bands["40_60"] += 1
        elif score < 80:
            bands["60_80"] += 1
        else:
            bands["80_100"] += 1
    replay_payload = [result.result_fingerprint for result in results]
    replay_fingerprint = hashlib.sha256(
        json.dumps(replay_payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    latest: dict[int, ValuationResult] = {}
    for result in results:
        previous = latest.get(result.company_id)
        key = (result.fiscal_year, int(result.fiscal_quarter[-1]), result.quarter_id)
        if previous is None or key > (previous.fiscal_year, int(previous.fiscal_quarter[-1]), previous.quarter_id):
            latest[result.company_id] = result
    requested_samples = {
        "NVDA", "AAPL", "MSFT", "TSLA", "DAVE", "AMC", "BE", "T", "VZ",
        "O", "JPM", "AIG", "CME",
    }
    samples = {
        result.ticker: result.to_dict()
        for result in latest.values()
        if result.ticker in requested_samples
    }
    return {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "candidate_observations": len(results),
        "status_counts": dict(sorted(statuses.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "not_applicable": {
            "reit": reasons["UNSUPPORTED_REIT_MODEL"],
            "bank": reasons["UNSUPPORTED_BANK_MODEL"],
            "insurance": reasons["UNSUPPORTED_INSURANCE_MODEL"],
            "other_financial": reasons["UNSUPPORTED_FINANCIAL_MODEL"],
        },
        "score_distribution": _distribution(scores),
        "score_bands": dict(sorted(bands.items())),
        "exact_zero_count": sum(score == 0.0 for score in scores),
        "exact_zero_share": sum(score == 0.0 for score in scores) / len(scores) if scores else None,
        "exact_100_count": sum(score == 100.0 for score in scores),
        "exact_100_share": sum(score == 100.0 for score in scores) / len(scores) if scores else None,
        "component_distributions": {
            field: _distribution(getattr(result, field) for result in full)
            for field in (
                "ebit_yield",
                "ebit_points",
                "fcf_yield",
                "fcf_points",
                "earnings_yield",
                "earnings_points",
            )
        },
        "component_point_correlations": {
            "ebit_fcf": _correlation(full, "ebit_points", "fcf_points"),
            "ebit_earnings": _correlation(full, "ebit_points", "earnings_points"),
            "fcf_earnings": _correlation(full, "fcf_points", "earnings_points"),
        },
        "latest_company_count": len(latest),
        "samples": samples,
        "phase3a_full_formula_ready_reference": 41576,
        "replay_fingerprint": replay_fingerprint,
    }


def run_rehearsal(repo_root: Path, output_path: Path) -> dict[str, Any]:
    inputs = load_production_source_inputs(
        repo_root / "data" / "fundamentals_v4.db",
        repo_root / "data" / "fundamentals_provider.db",
        repo_root / "data" / "osakedata.db",
    )
    results = [calculate_valuation(observation, bars) for observation, bars in inputs]
    summary = summarize(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return summary
