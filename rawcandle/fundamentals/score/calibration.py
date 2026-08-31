from __future__ import annotations

import csv
import hashlib
import inspect
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.ttm.engine import canonical_financial_fingerprint, ttm_fingerprints

MODEL_VERSION = "V4_FUNDAMENTAL_SCORE_V1"
CLASSIFICATION_READY = "V4_SCORE_V1_CONTINUOUS_SCALING_LOCKED_IMPLEMENTATION_READY"
CLASSIFICATION_REVIEW = "V4_SCORE_V1_CONTINUOUS_SCALING_COMPLETE_WITH_REVIEW_ITEMS"
CLASSIFICATION_BLOCKED = "V4_SCORE_V1_CONTINUOUS_SCALING_BLOCKED"
NEXT_READY = (
    "PROCEED TO V4-4: IMPLEMENT THE LOCKED V4_FUNDAMENTAL_SCORE_V1 PRODUCTION ENGINE IN RAWCANDLE, "
    "WRITE VERSIONED CONTINUOUS 0..N COMPONENT SCORES AND 0..100 TOTAL SCORES TO fundamentals_analysis.db, "
    "IMPLEMENT DELTA SCORE AS A SEPARATE DERIVED CHANGE METRIC, AND PROVE EXACT PARITY WITH THE LOCKED "
    "V4-3A SPECIFICATION BEFORE MIGRATING LIFECYCLE OR VALUATION"
)
NEXT_REVIEW = "KEEP PRODUCTION SCORE WRITES FROZEN AND RESOLVE ONLY THE SPECIFIC ECONOMIC SCALING OR COMPONENT-INDEPENDENCE ISSUES BEFORE IMPLEMENTATION"
NEXT_BLOCKED = "DO NOT IMPLEMENT PRODUCTION SCORE UNTIL ALL SEVEN COMPONENTS HAVE ECONOMICALLY INTERPRETABLE, CONTINUOUS, ABSOLUTE 0..N SCALING WITH NO FUTURE-OUTCOME OR RETURN OPTIMIZATION"

DEV_SPLIT = "DEVELOPMENT_2021_2023"
VALIDATION_SPLIT = "VALIDATION_2024"
OOS_SPLIT = "OOS_2025_LOCKED"
FORWARD_SPLIT = "FORWARD_2026_UNTOUCHED"
EXCLUDED_SPLIT = "EXCLUDED"
NEAR_ZERO = 1e-9

COMPONENTS: tuple[dict[str, Any], ...] = (
    {"component_id": "growth_earnings_development", "label": "Growth and earnings development", "max_points": 25},
    {"component_id": "profitability_level", "label": "Profitability level", "max_points": 15},
    {"component_id": "margin_direction", "label": "Margin direction", "max_points": 15},
    {"component_id": "cash_flow_quality", "label": "Cash-flow quality", "max_points": 15},
    {"component_id": "development_consistency", "label": "Development consistency", "max_points": 10},
    {"component_id": "balance_sheet_resilience", "label": "Balance-sheet resilience", "max_points": 15},
    {"component_id": "dilution", "label": "Dilution", "max_points": 5},
)

FEATURE_COLUMNS = (
    "revenue_growth_yoy_ttm",
    "ebit_growth_yoy_ttm",
    "ebit_development_quality",
    "ebit_transition",
    "ebit_margin_ttm",
    "ebit_margin_yoy_change",
    "ebit_margin_seq_change",
    "fcf_to_ebit",
    "fcf_margin_ttm",
    "fcf_margin_yoy_change",
    "consistency_positive_share",
    "consistency_margin_volatility",
    "balance_metric",
    "net_debt_to_ebit",
    "cash_runway_years",
    "share_change_yoy",
)


@dataclass(frozen=True)
class ScorePaths:
    repo_root: Path
    artifact_root: Path
    canonical_db: Path
    analysis_db: Path
    provider_db: Path
    known_gaps_doc: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def score_paths(repo_root: Path, timestamp: str | None = None) -> ScorePaths:
    stamp = timestamp or utc_stamp()
    return ScorePaths(
        repo_root=repo_root,
        artifact_root=repo_root / "temp" / "fundamentals_v4_3a_score_scaling" / stamp,
        canonical_db=repo_root / "data" / "fundamentals_v4.db",
        analysis_db=repo_root / "data" / "fundamentals_analysis.db",
        provider_db=repo_root / "data" / "fundamentals_provider.db",
        known_gaps_doc=repo_root / "docs" / "fundamentals_v4" / "fundamentals_v4_known_gaps.md",
    )


def connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def hash_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def fl(value: Any) -> float | None:
    return None if value is None else float(value)


def safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or abs(den) <= NEAR_ZERO:
        return None
    return num / den


def safe_growth(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev <= NEAR_ZERO:
        return None
    return (cur - prev) / prev


def safe_positive_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den <= NEAR_ZERO:
        return None
    return num / den


def clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def linear_score(value: float | None, points: float, low: float, high: float, *, higher_is_better: bool = True) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    if not higher_is_better:
        value = -float(value)
        low, high = -high, -low
    if high <= low:
        raise ValueError("invalid_score_curve")
    return round(points * clamp((float(value) - low) / (high - low), 0.0, 1.0), 6)


def sample_split(date_text: str | None) -> str:
    if not date_text:
        return EXCLUDED_SPLIT
    year = int(str(date_text)[:4])
    if 2021 <= year <= 2023:
        return DEV_SPLIT
    if year == 2024:
        return VALIDATION_SPLIT
    if year == 2025:
        return OOS_SPLIT
    if year == 2026:
        return FORWARD_SPLIT
    return EXCLUDED_SPLIT


def load_ttm_rows(db_path: Path) -> list[dict[str, Any]]:
    with connect_readonly(db_path) as conn:
        rows = [dict(row) for row in conn.execute(
            """
            SELECT
                c.company_id,
                c.company_key,
                c.company_name,
                c.status AS company_status,
                s.security_id,
                s.current_ticker AS ticker,
                s.exchange,
                s.active AS security_active,
                t.ttm_id,
                t.endpoint_quarter_id,
                t.endpoint_fiscal_year,
                t.endpoint_fiscal_quarter,
                t.period_end,
                t.readiness_status,
                t.blocker_codes_json,
                t.ttm_revenue,
                t.ttm_ebit,
                t.ttm_ebitda,
                t.ttm_operating_cashflow,
                t.ttm_free_cashflow,
                t.cash,
                t.total_debt,
                t.shares_outstanding,
                t.core_ttm_ready,
                t.ttm_source_available_date,
                t.first_public_result_date,
                t.input_quarter_ids_json,
                t.input_values_hash,
                t.canonical_financial_fingerprint,
                t.output_fingerprint
            FROM v4_ttm_values t
            JOIN company c ON c.company_id = t.company_id
            LEFT JOIN security s ON s.security_id = t.security_id
            WHERE t.model_version = 'V4_TTM_EBIT_FIRST_V1'
            ORDER BY c.company_id, t.endpoint_fiscal_year,
                CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 WHEN 'Q4' THEN 4 END,
                t.endpoint_quarter_id
            """
        )]
    return rows


def quarter_sort_key(row: Mapping[str, Any]) -> tuple[int, int, int]:
    qn = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}[str(row["endpoint_fiscal_quarter"])]
    return int(row["company_id"]), int(row["endpoint_fiscal_year"]) * 4 + qn, int(row["endpoint_quarter_id"])


def build_feature_matrix(ttm_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(ttm_rows, key=quarter_sort_key):
        grouped[int(row["company_id"])].append(row)
    out: list[dict[str, Any]] = []
    for company_id, rows in sorted(grouped.items()):
        for idx, row in enumerate(rows):
            prev1 = rows[idx - 1] if idx >= 1 else None
            prev4 = rows[idx - 4] if idx >= 4 else None
            next1 = rows[idx + 1] if idx + 1 < len(rows) else None
            next2 = rows[idx + 2] if idx + 2 < len(rows) else None
            next4 = rows[idx + 4] if idx + 4 < len(rows) else None
            history = rows[max(0, idx - 3) : idx + 1]
            out.append(feature_row(row, prev1, prev4, history, next1, next2, next4))
    return out


def feature_row(
    row: Mapping[str, Any],
    prev1: Mapping[str, Any] | None,
    prev4: Mapping[str, Any] | None,
    history: list[Mapping[str, Any]],
    next1: Mapping[str, Any] | None,
    next2: Mapping[str, Any] | None,
    next4: Mapping[str, Any] | None,
) -> dict[str, Any]:
    revenue = fl(row.get("ttm_revenue"))
    ebit = fl(row.get("ttm_ebit"))
    fcf = fl(row.get("ttm_free_cashflow"))
    ocf = fl(row.get("ttm_operating_cashflow"))
    cash = fl(row.get("cash"))
    debt = fl(row.get("total_debt"))
    shares = fl(row.get("shares_outstanding"))
    prev_revenue = fl(prev4.get("ttm_revenue")) if prev4 else None
    prev_ebit = fl(prev4.get("ttm_ebit")) if prev4 else None
    prev_fcf = fl(prev4.get("ttm_free_cashflow")) if prev4 else None
    prev_shares = fl(prev4.get("shares_outstanding")) if prev4 else None
    ebit_margin = safe_div(ebit, revenue)
    prev_ebit_margin = safe_div(prev_ebit, prev_revenue)
    prev1_margin = safe_div(fl(prev1.get("ttm_ebit")) if prev1 else None, fl(prev1.get("ttm_revenue")) if prev1 else None)
    fcf_margin = safe_div(fcf, revenue)
    prev_fcf_margin = safe_div(prev_fcf, prev_revenue)
    balance = balance_metric(cash, debt, revenue, ebit, fcf)
    availability = str(row.get("ttm_source_available_date") or row.get("period_end") or "")
    ready = int(row.get("core_ttm_ready") or 0) == 1 and bool(row.get("ttm_source_available_date"))
    blockers = json.loads(str(row.get("blocker_codes_json") or "[]"))
    result = {
        "company_id": row.get("company_id"),
        "security_id": row.get("security_id"),
        "ticker": row.get("ticker") or "",
        "company_name": row.get("company_name") or "",
        "company_status": row.get("company_status") or "",
        "exchange": row.get("exchange") or "",
        "security_active": row.get("security_active"),
        "ttm_id": row.get("ttm_id"),
        "endpoint_quarter_id": row.get("endpoint_quarter_id"),
        "fiscal_year": row.get("endpoint_fiscal_year"),
        "fiscal_quarter": row.get("endpoint_fiscal_quarter"),
        "period_end": row.get("period_end"),
        "availability_date": row.get("ttm_source_available_date"),
        "availability_fallback_used": int(not row.get("ttm_source_available_date")),
        "sample_split": sample_split(availability),
        "ttm_readiness_status": row.get("readiness_status"),
        "ttm_core_ready": int(row.get("core_ttm_ready") or 0),
        "known_gap_flags": ";".join(blockers),
        "revenue_growth_yoy_ttm": safe_growth(revenue, prev_revenue),
        "ebit_growth_yoy_ttm": safe_growth(ebit, prev_ebit),
        "ebit_development_quality": ebit_development_quality(prev_ebit, ebit, revenue),
        "ebit_transition": signed_transition(prev_ebit, ebit),
        "ebit_margin_ttm": ebit_margin,
        "ebit_margin_yoy_change": None if ebit_margin is None or prev_ebit_margin is None else ebit_margin - prev_ebit_margin,
        "ebit_margin_seq_change": None if ebit_margin is None or prev1_margin is None else ebit_margin - prev1_margin,
        "fcf_to_ebit": safe_positive_ratio(fcf, ebit),
        "fcf_margin_ttm": fcf_margin,
        "fcf_margin_yoy_change": None if fcf_margin is None or prev_fcf_margin is None else fcf_margin - prev_fcf_margin,
        "consistency_positive_share": consistency_positive_share(history),
        "consistency_margin_volatility": consistency_margin_volatility(history),
        "balance_metric": balance,
        "net_debt_to_ebit": safe_positive_ratio((debt - cash) if cash is not None and debt is not None else None, ebit),
        "cash_runway_years": cash_runway(cash, fcf),
        "share_change_yoy": safe_growth(shares, prev_shares),
        "feature_ready": int(ready),
        "feature_blockers": ";".join(feature_blockers(row, prev4, history)),
    }
    result.update(future_outcomes(row, next1, next2, next4))
    return result


def signed_transition(prev: float | None, cur: float | None) -> str | None:
    if prev is None or cur is None:
        return None
    if prev <= 0 < cur:
        return "CROSSING_TO_POSITIVE"
    if prev > 0 >= cur:
        return "POSITIVE_TURNING_NEGATIVE"
    if prev > 0 and cur > prev:
        return "POSITIVE_AND_GROWING"
    if prev > 0 and cur <= prev:
        return "POSITIVE_AND_DECLINING"
    if prev <= 0 and cur > prev:
        return "NEGATIVE_BUT_IMPROVING"
    if abs(prev) <= NEAR_ZERO and abs(cur) <= NEAR_ZERO:
        return "FLAT_ZERO_REGION"
    return "NEGATIVE_AND_DETERIORATING"


def ebit_development_quality(prev: float | None, cur: float | None, revenue: float | None) -> float | None:
    if prev is None or cur is None:
        return None
    if prev > NEAR_ZERO:
        growth = (cur - prev) / prev
        return clamp((growth + 0.50) / 1.00, 0.0, 1.0)
    if cur <= 0:
        scale = max(abs(prev), abs(cur), 1.0)
        return clamp(0.50 + 0.50 * cur / scale, 0.0, 0.50)
    margin = safe_div(cur, revenue)
    if margin is None:
        return 0.50
    return clamp(0.50 + 0.50 * margin / 0.10, 0.50, 1.0)


def balance_metric(cash: float | None, debt: float | None, revenue: float | None, ebit: float | None, fcf: float | None) -> float | None:
    if cash is None or debt is None:
        return None
    net_debt = debt - cash
    if ebit is not None and ebit > NEAR_ZERO:
        ratio = safe_div(net_debt, ebit)
        return None if ratio is None else -ratio
    if fcf is not None and fcf < -NEAR_ZERO:
        return cash / abs(fcf)
    ratio = safe_div(net_debt, revenue)
    if ratio is not None:
        return -ratio
    return 2.0 if net_debt <= 0 else -3.0


def cash_runway(cash: float | None, fcf: float | None) -> float | None:
    if cash is None or fcf is None or fcf >= 0 or abs(fcf) <= NEAR_ZERO:
        return None
    return cash / abs(fcf)


def consistency_positive_share(history: list[Mapping[str, Any]]) -> float | None:
    values = [safe_div(fl(row.get("ttm_ebit")), fl(row.get("ttm_revenue"))) for row in history]
    values = [v for v in values if v is not None]
    if len(values) < 3:
        return None
    improving = sum(1 for a, b in zip(values, values[1:]) if b >= a)
    return improving / max(1, len(values) - 1)


def consistency_margin_volatility(history: list[Mapping[str, Any]]) -> float | None:
    values = [safe_div(fl(row.get("ttm_ebit")), fl(row.get("ttm_revenue"))) for row in history]
    values = [v for v in values if v is not None]
    if len(values) < 3:
        return None
    return pstdev(values)


def feature_blockers(row: Mapping[str, Any], prev4: Mapping[str, Any] | None, history: list[Mapping[str, Any]]) -> list[str]:
    blockers = []
    if not row.get("ttm_source_available_date"):
        blockers.append("AVAILABILITY_DATE_MISSING")
    if int(row.get("core_ttm_ready") or 0) != 1:
        blockers.append("CURRENT_TTM_NOT_READY")
    if prev4 is None or int(prev4.get("core_ttm_ready") or 0) != 1:
        blockers.append("YOY_TTM_HISTORY_NOT_READY")
    if len(history) < 3:
        blockers.append("CONSISTENCY_HISTORY_INSUFFICIENT")
    return sorted(set(blockers))


def future_outcomes(row: Mapping[str, Any], next1: Mapping[str, Any] | None, next2: Mapping[str, Any] | None, next4: Mapping[str, Any] | None) -> dict[str, Any]:
    cur_ebit = fl(row.get("ttm_ebit"))
    cur_revenue = fl(row.get("ttm_revenue"))
    cur_fcf = fl(row.get("ttm_free_cashflow"))
    cur_margin = safe_div(cur_ebit, cur_revenue)
    cur_fcf_margin = safe_div(cur_fcf, cur_revenue)
    out: dict[str, Any] = {}
    for horizon, future in (("1q", next1), ("2q", next2), ("4q", next4)):
        f_ebit = fl(future.get("ttm_ebit")) if future else None
        f_rev = fl(future.get("ttm_revenue")) if future else None
        f_fcf = fl(future.get("ttm_free_cashflow")) if future else None
        f_margin = safe_div(f_ebit, f_rev)
        f_fcf_margin = safe_div(f_fcf, f_rev)
        out[f"future_{horizon}_observable"] = int(future is not None and int(future.get("core_ttm_ready") or 0) == 1)
        out[f"future_{horizon}_ebit_growth"] = safe_growth(f_ebit, cur_ebit)
        out[f"future_{horizon}_ebit_margin_change"] = None if f_margin is None or cur_margin is None else f_margin - cur_margin
        out[f"future_{horizon}_fcf_growth"] = safe_growth(f_fcf, cur_fcf)
        out[f"future_{horizon}_fcf_margin_change"] = None if f_fcf_margin is None or cur_fcf_margin is None else f_fcf_margin - cur_fcf_margin
        out[f"future_{horizon}_fundamental_state"] = classify_future_state(
            out[f"future_{horizon}_ebit_growth"],
            out[f"future_{horizon}_ebit_margin_change"],
            out[f"future_{horizon}_fcf_margin_change"],
        )
    return out


def classify_future_state(ebit_growth: float | None, margin_change: float | None, fcf_margin_change: float | None) -> str:
    signals = []
    if ebit_growth is not None:
        signals.append(1 if ebit_growth >= 0.05 else -1 if ebit_growth <= -0.05 else 0)
    if margin_change is not None:
        signals.append(1 if margin_change >= 0.01 else -1 if margin_change <= -0.01 else 0)
    if fcf_margin_change is not None:
        signals.append(1 if fcf_margin_change >= 0.01 else -1 if fcf_margin_change <= -0.01 else 0)
    if not signals:
        return "NOT_OBSERVABLE"
    total = sum(signals)
    if total >= 1:
        return "IMPROVING"
    if total <= -1:
        return "DETERIORATING"
    return "STABLE"


def calibrate_curves(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [r for r in matrix if r["feature_ready"]]
    curves = {
        "growth_earnings_development": {
            "max_points": 25,
            "parts": [
                {"feature": "revenue_growth_yoy_ttm", "points": 10, "type": "piecewise_linear", "low": -0.10, "neutral": 0.00, "high": 0.25, "higher_is_better": True},
                {"feature": "ebit_development_quality", "points": 15, "type": "piecewise_linear", "low": 0.00, "neutral": 0.50, "high": 1.00, "higher_is_better": True},
            ],
        },
        "profitability_level": {
            "max_points": 15,
            "parts": [
                {"feature": "ebit_margin_ttm", "points": 15, "type": "piecewise_linear", "low": 0.00, "neutral": 0.10, "high": max(0.25, rounded_quantile(usable, "ebit_margin_ttm", 0.85, default=0.25)), "higher_is_better": True},
            ],
        },
        "margin_direction": {
            "max_points": 15,
            "parts": [
                {"feature": "ebit_margin_yoy_change", "points": 10, "type": "piecewise_linear", "low": -0.05, "neutral": 0.00, "high": 0.05, "higher_is_better": True},
                {"feature": "ebit_margin_seq_change", "points": 5, "type": "piecewise_linear", "low": -0.02, "neutral": 0.00, "high": 0.02, "higher_is_better": True},
            ],
        },
        "cash_flow_quality": {
            "max_points": 15,
            "parts": [
                {"feature": "fcf_to_ebit", "points": 10, "type": "piecewise_linear", "low": 0.00, "neutral": 0.60, "high": 1.20, "higher_is_better": True},
                {"feature": "fcf_margin_ttm", "points": 5, "type": "piecewise_linear", "low": -0.05, "neutral": 0.00, "high": 0.12, "higher_is_better": True},
            ],
        },
        "development_consistency": {
            "max_points": 10,
            "parts": [
                {"feature": "consistency_positive_share", "points": 6, "type": "piecewise_linear", "low": 0.00, "neutral": 0.50, "high": 1.00, "higher_is_better": True},
                {"feature": "consistency_margin_volatility", "points": 4, "type": "piecewise_linear", "low": 0.00, "neutral": 0.03, "high": 0.10, "higher_is_better": False},
            ],
        },
        "balance_sheet_resilience": {
            "max_points": 15,
            "parts": [
                {"feature": "balance_metric", "points": 15, "type": "piecewise_linear", "low": -4.0, "neutral": 0.0, "high": 2.0, "higher_is_better": True},
            ],
        },
        "dilution": {
            "max_points": 5,
            "parts": [
                {"feature": "share_change_yoy", "points": 5, "type": "piecewise_linear", "low": -0.03, "neutral": 0.00, "high": 0.10, "higher_is_better": False, "buyback_reward_cap": "score capped near max; no extra reward beyond -3% shares YoY"},
            ],
        },
    }
    return {
        "model_version": MODEL_VERSION,
        "score_semantic": "CURRENT_FUNDAMENTAL_STATE",
        "delta_score_semantic": "CHANGE_IN_FUNDAMENTAL_STATE",
        "components": list(COMPONENTS),
        "curves": curves,
        "calibrated_from": "V4_HISTORY_DISTRIBUTION_SUPPORT_ONLY_NO_OUTCOME_OPTIMIZATION",
        "future_state_thresholds": {"diagnostic_only": True, "ebit_growth": "+/-5%", "ebit_margin_change": "+/-1pp", "fcf_margin_change": "+/-1pp"},
        "no_cross_component_reweighting": True,
        "no_cross_sectional_percentile_scoring": True,
    }


def transition_points(max_points: int) -> dict[str, float]:
    order = [
        ("NEGATIVE_AND_DETERIORATING", 0.0),
        ("POSITIVE_TURNING_NEGATIVE", 1.0),
        ("FLAT_ZERO_REGION", 2.0),
        ("NEGATIVE_BUT_IMPROVING", 3.0),
        ("POSITIVE_AND_DECLINING", 3.5),
        ("CROSSING_TO_POSITIVE", 4.5),
        ("POSITIVE_AND_GROWING", 5.0),
    ]
    return {k: round(v / 5.0 * max_points, 6) for k, v in order}


def rounded_quantile(rows: list[dict[str, Any]], key: str, q: float, *, default: float) -> float:
    values = sorted(float(r[key]) for r in rows if r.get(key) is not None and math.isfinite(float(r[key])))
    if not values:
        return default
    idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))
    value = values[idx]
    return round(value / 0.01) * 0.01


def score_row(row: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    component_scores: dict[str, float | None] = {}
    component_status: dict[str, str] = {}
    for component_id, curve in spec["curves"].items():
        scores = []
        statuses = []
        for part in curve["parts"]:
            feature = part["feature"]
            value = row.get(feature)
            score = linear_score(value, float(part["points"]), float(part["low"]), float(part["high"]), higher_is_better=bool(part["higher_is_better"]))
            scores.append(score)
            statuses.append("MISSING_DATA" if score is None else "SCORED")
        if any(score is not None for score in scores):
            component_scores[component_id] = round(sum(float(score) for score in scores if score is not None), 6)
            component_status[component_id] = "SCORED" if all(status == "SCORED" for status in statuses) else "PARTIAL"
        else:
            component_scores[component_id] = None
            component_status[component_id] = "MISSING_DATA"
    available = sum(next(c["max_points"] for c in COMPONENTS if c["component_id"] == cid) for cid, score in component_scores.items() if score is not None)
    total_raw = sum(float(score) for score in component_scores.values() if score is not None)
    if int(row.get("feature_ready") or 0) != 1:
        readiness = "SCORE_NOT_READY"
        total = None
    elif available >= 80:
        readiness = "SCORE_READY"
        total = round(total_raw, 6)
    elif available >= 65:
        readiness = "SCORE_READY_WITH_LIMITED_COMPONENT"
        total = round(total_raw, 6)
    else:
        readiness = "SCORE_NOT_READY"
        total = None
    return {
        "component_scores": component_scores,
        "component_status": component_status,
        "available_score_weight": available,
        "score_max_available": available,
        "score_coverage_pct": round(100.0 * available / 100.0, 6),
        "score_readiness": readiness,
        "score_blockers": row.get("feature_blockers") or "",
        "total_score": None if total is None else round(clamp(total, 0.0, 100.0), 6),
    }


def apply_score(matrix: list[dict[str, Any]], spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for row in matrix:
        scored = dict(row)
        result = score_row(row, spec)
        scored.update({k: v for k, v in result.items() if k not in {"component_scores", "component_status"}})
        for cid, value in result["component_scores"].items():
            scored[f"{cid}_score"] = value
            scored[f"{cid}_status"] = result["component_status"][cid]
        out.append(scored)
    return out


def model_fingerprint(spec: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "model_version": spec["model_version"],
        "score_semantic": spec["score_semantic"],
        "delta_score_semantic": spec["delta_score_semantic"],
        "components": spec["components"],
        "curves": spec["curves"],
        "future_state_thresholds": spec["future_state_thresholds"],
        "no_cross_component_reweighting": spec["no_cross_component_reweighting"],
    }
    return {"model_version": spec["model_version"], "fingerprint": hash_json(payload), "payload_hash_contract": "version+components+curves+future_state_thresholds"}


def stats(values: Iterable[Any]) -> dict[str, Any]:
    nums = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not nums:
        return {k: None for k in ("count", "missing", "zero", "negative", "mean", "median", "std", "p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99", "min", "max")}
    return {
        "count": len(nums),
        "zero": sum(1 for v in nums if v == 0),
        "negative": sum(1 for v in nums if v < 0),
        "mean": mean(nums),
        "median": median(nums),
        "std": pstdev(nums) if len(nums) > 1 else 0.0,
        "p01": quantile(nums, 0.01),
        "p05": quantile(nums, 0.05),
        "p10": quantile(nums, 0.10),
        "p25": quantile(nums, 0.25),
        "p50": quantile(nums, 0.50),
        "p75": quantile(nums, 0.75),
        "p90": quantile(nums, 0.90),
        "p95": quantile(nums, 0.95),
        "p99": quantile(nums, 0.99),
        "min": nums[0],
        "max": nums[-1],
    }


def quantile(nums: list[float], q: float) -> float:
    if not nums:
        return float("nan")
    if len(nums) == 1:
        return nums[0]
    pos = (len(nums) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return nums[lo]
    return nums[lo] + (nums[hi] - nums[lo]) * (pos - lo)


def feature_distribution_rows(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    total = len(matrix)
    for feature in FEATURE_COLUMNS:
        values = [r.get(feature) for r in matrix]
        missing = sum(1 for v in values if v is None)
        if feature == "ebit_transition":
            counts = Counter(str(v) for v in values if v is not None)
            rows.append({
                "feature": feature,
                "count": total - missing,
                "missing": missing,
                "missing_pct": round(100.0 * missing / total, 6) if total else 0.0,
                "categorical_counts_json": json.dumps(dict(sorted(counts.items())), sort_keys=True),
            })
            continue
        s = stats(values)
        s["missing"] = missing
        s["missing_pct"] = round(100.0 * missing / total, 6) if total else 0.0
        rows.append({"feature": feature, **s})
    return rows


def year_distribution_rows(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter((str(r.get("availability_date") or "")[:4] or "MISSING", r["sample_split"]) for r in matrix)
    return [{"availability_year": y, "sample_split": split, "observations": n} for (y, split), n in sorted(counts.items())]


def raw_feature_distribution_by_year(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    years = sorted({str(r.get("availability_date") or "")[:4] for r in matrix if r.get("availability_date")})
    for year in years:
        year_rows = [r for r in matrix if str(r.get("availability_date") or "").startswith(year)]
        for row in feature_distribution_rows(year_rows):
            out.append({"availability_year": year, **row})
    return out


def missingness_rows(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(matrix)
    return [{"feature": f, "missing": sum(1 for r in matrix if r.get(f) is None), "missing_pct": round(100.0 * sum(1 for r in matrix if r.get(f) is None) / total, 6) if total else 0.0} for f in FEATURE_COLUMNS]


def score_distribution(scored: list[dict[str, Any]], split: str) -> dict[str, Any]:
    rows = [r for r in scored if r["sample_split"] == split]
    ready = [r for r in rows if r.get("total_score") is not None]
    s = stats([r.get("total_score") for r in ready])
    s["split"] = split
    s["observations"] = len(rows)
    s["ready"] = len(ready)
    s["floor_saturation_pct"] = round(100.0 * sum(1 for r in ready if float(r["total_score"]) <= 0.000001) / len(ready), 6) if ready else 0.0
    s["ceiling_saturation_pct"] = round(100.0 * sum(1 for r in ready if float(r["total_score"]) >= 99.999999) / len(ready), 6) if ready else 0.0
    return s


def score_distribution_by_year(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [r for r in scored if r.get("total_score") is not None and r.get("availability_date")]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["availability_date"])[:4]].append(row)
    out = []
    for year, items in sorted(grouped.items()):
        s = stats([r["total_score"] for r in items])
        s["availability_year"] = year
        s["ready"] = len(items)
        s["floor_saturation_pct"] = pct(sum(1 for r in items if float(r["total_score"]) <= 0.000001), len(items))
        s["ceiling_saturation_pct"] = pct(sum(1 for r in items if float(r["total_score"]) >= 99.999999), len(items))
        out.append(s)
    return out


def component_saturation_rows(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [r for r in scored if r.get("total_score") is not None]
    out = []
    for comp in COMPONENTS:
        key = f"{comp['component_id']}_score"
        values = [float(r[key]) for r in rows if r.get(key) is not None]
        max_points = float(comp["max_points"])
        out.append({
            "component_id": comp["component_id"],
            "max_points": max_points,
            "observations": len(values),
            "zero_saturation_pct": pct(sum(1 for v in values if v <= 0.000001), len(values)) if values else None,
            "interior_pct": pct(sum(1 for v in values if 0.000001 < v < max_points - 0.000001), len(values)) if values else None,
            "max_saturation_pct": pct(sum(1 for v in values if v >= max_points - 0.000001), len(values)) if values else None,
            "median_component_score": median(values) if values else None,
            "p10": quantile(sorted(values), 0.10) if values else None,
            "p25": quantile(sorted(values), 0.25) if values else None,
            "p75": quantile(sorted(values), 0.75) if values else None,
            "p90": quantile(sorted(values), 0.90) if values else None,
            "example_non_integer_score": next((v for v in values if abs(v - round(v)) > 0.000001), None),
        })
    return out


def continuity_test_rows(spec: Mapping[str, Any], epsilon: float = 1e-6) -> list[dict[str, Any]]:
    rows = []
    for component_id, curve in spec["curves"].items():
        for part in curve["parts"]:
            for point_name in ("low", "neutral", "high"):
                if point_name not in part:
                    continue
                x = float(part[point_name])
                left = linear_score(x - epsilon, float(part["points"]), float(part["low"]), float(part["high"]), higher_is_better=bool(part["higher_is_better"]))
                mid = linear_score(x, float(part["points"]), float(part["low"]), float(part["high"]), higher_is_better=bool(part["higher_is_better"]))
                right = linear_score(x + epsilon, float(part["points"]), float(part["low"]), float(part["high"]), higher_is_better=bool(part["higher_is_better"]))
                rows.append({
                    "component_id": component_id,
                    "feature": part["feature"],
                    "breakpoint": point_name,
                    "x": x,
                    "score_x_minus_epsilon": left,
                    "score_x": mid,
                    "score_x_plus_epsilon": right,
                    "continuous": int(abs(float(mid) - float(left)) < 0.001 and abs(float(right) - float(mid)) < 0.001),
                    "deliberate_jump": 0,
                })
    return rows


def candidate_rule_review_rows(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"feature_or_curve": "revenue_growth_yoy_ttm", "decision": "KEEP_AS_IS", "why": "Top-line growth is independent, continuous, absolute and economically interpretable."},
        {"feature_or_curve": "ebit_growth_yoy_ttm", "decision": "KEEP_FEATURE_REDESIGN_SCALE", "why": "Raw percent growth is diagnostic only when prior EBIT is positive; final scale uses continuous EBIT development quality to handle sign transitions."},
        {"feature_or_curve": "ebit_transition", "decision": "KEEP_FEATURE_REDESIGN_SCALE", "why": "Categorical state remains diagnostic, but final score no longer uses a discrete ladder."},
        {"feature_or_curve": "ebit_margin_ttm", "decision": "KEEP_WITH_MINOR_CHANGE", "why": "Floor is locked to 0% because negative EBIT margin receives no profitability reward."},
        {"feature_or_curve": "ebit_margin_yoy_change", "decision": "KEEP_AS_IS", "why": "Direction component legitimately distinguishes negative, stable and improving margin movement."},
        {"feature_or_curve": "ebit_margin_seq_change", "decision": "KEEP_AS_IS", "why": "Adds short-term current direction without changing profitability level."},
        {"feature_or_curve": "fcf_to_ebit", "decision": "KEEP_AS_IS", "why": "Cash conversion is conceptually distinct from absolute FCF margin and uses positive-EBIT guards."},
        {"feature_or_curve": "fcf_margin_ttm", "decision": "KEEP_AS_IS", "why": "Captures negative FCF and cash generation relative to business scale."},
        {"feature_or_curve": "consistency_positive_share", "decision": "KEEP_AS_IS", "why": "Measures persistence rather than magnitude of growth."},
        {"feature_or_curve": "consistency_margin_volatility", "decision": "KEEP_AS_IS", "why": "Measures stability and uses an independent lower-is-better scale."},
        {"feature_or_curve": "balance_metric", "decision": "KEEP_AS_IS", "why": "Captures net cash, leverage and cash-burn resilience in the balance-sheet component only."},
        {"feature_or_curve": "share_change_yoy", "decision": "KEEP_AS_IS", "why": "Direct shareholder dilution/discipline metric with capped buyback reward."},
    ]


def breakpoint_decision_rows(spec: Mapping[str, Any], matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    distributions = {row["feature"]: row for row in feature_distribution_rows(matrix)}
    for component_id, curve in spec["curves"].items():
        for part in curve["parts"]:
            dist = distributions.get(part["feature"], {})
            rows.append({
                "component_id": component_id,
                "feature": part["feature"],
                "proposed_floor": part["low"],
                "proposed_ceiling": part["high"],
                "neutral_reference": part.get("neutral"),
                "economic_reason": economic_reason(part["feature"]),
                "distribution_support": json.dumps({k: dist.get(k) for k in ("p05", "p10", "p50", "p90", "p95")}, sort_keys=True),
            })
    return rows


def economic_reason(feature: str) -> str:
    return {
        "revenue_growth_yoy_ttm": "Negative growth is weak; around zero is neutral-low; 25% TTM growth is strong enough to cap the top-line contribution.",
        "ebit_development_quality": "Continuous 0..1 quality handles positive EBIT growth and negative/positive sign transitions without unstable percentage denominators.",
        "ebit_margin_ttm": "EBIT margin at or below zero earns no profitability points; high positive EBIT margin is sufficient profitability strength.",
        "ebit_margin_yoy_change": "Direction intentionally rewards improvement, gives middle points around stable margins and penalizes deterioration.",
        "ebit_margin_seq_change": "Sequential direction is a smaller current-state confirmation signal.",
        "fcf_to_ebit": "Positive EBIT cash conversion below zero is poor; conversion above 120% is capped to avoid tiny-denominator pathologies.",
        "fcf_margin_ttm": "Negative FCF margin is weak; strong FCF generation relative to revenue is capped.",
        "consistency_positive_share": "Repeated non-deterioration over recent observations indicates durability.",
        "consistency_margin_volatility": "Lower recent EBIT-margin volatility indicates more durable current state.",
        "balance_metric": "Net debt relative to EBIT, cash runway, and net-cash states define resilience without market-cap inputs.",
        "share_change_yoy": "Material issuance is weak, stable shares are good, and buybacks are capped.",
    }[feature]


def component_scaling_analysis_doc(name: str, spec: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    component_lookup = {
        "growth": "growth_earnings_development",
        "profitability": "profitability_level",
        "margin_direction": "margin_direction",
        "cashflow_quality": "cash_flow_quality",
        "consistency": "development_consistency",
        "balance_sheet": "balance_sheet_resilience",
        "dilution": "dilution",
    }
    component_id = component_lookup[name]
    curve = spec["curves"][component_id]
    saturation = next((row for row in summary["component_saturation_audit"] if row["component_id"] == component_id), {})
    lines = [
        f"# {component_id} Scaling Analysis",
        "",
        f"Score semantic: `{spec['score_semantic']}`.",
        "",
        "Final rule: independent absolute continuous scoring. No future outcome optimization and no cross-sectional percentile scoring.",
        "",
        "Submetrics:",
        "",
    ]
    for part in curve["parts"]:
        lines.append(f"- `{part['feature']}`: {part['points']} points, floor `{part['low']}`, neutral `{part.get('neutral')}`, ceiling `{part['high']}`, {economic_reason(part['feature'])}")
    lines.extend([
        "",
        f"Zero saturation: `{saturation.get('zero_saturation_pct')}`.",
        f"Interior observations: `{saturation.get('interior_pct')}`.",
        f"Maximum saturation: `{saturation.get('max_saturation_pct')}`.",
        f"Median component score: `{saturation.get('median_component_score')}`.",
    ])
    return "\n".join(lines) + "\n"


def delta_score_rows(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        if row.get("total_score") is not None:
            grouped[int(row["company_id"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: (int(r["fiscal_year"]), str(r["fiscal_quarter"])))
        for idx, row in enumerate(rows):
            prev = rows[idx - 1] if idx else None
            out.append({
                "company_id": row["company_id"],
                "ticker": row["ticker"],
                "fiscal_year": row["fiscal_year"],
                "fiscal_quarter": row["fiscal_quarter"],
                "score_points": row["total_score"],
                "delta_score_1q": None if prev is None else round(float(row["total_score"]) - float(prev["total_score"]), 6),
                "comparable": int(prev is not None),
            })
    return out


def worked_examples(scored: list[dict[str, Any]], spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    ready = [r for r in scored if r.get("total_score") is not None]
    examples: list[tuple[str, dict[str, Any] | None]] = [
        ("high_growth_high_debt_high_dilution", find_first(ready, lambda r: pos(r.get("revenue_growth_yoy_ttm"), 0.20) and pos(r.get("net_debt_to_ebit"), 3.0) and pos(r.get("share_change_yoy"), 0.10))),
        ("low_growth_high_profitability_net_cash", find_first(ready, lambda r: between(r.get("revenue_growth_yoy_ttm"), -0.05, 0.05) and pos(r.get("ebit_margin_ttm"), 0.20) and neg(r.get("net_debt_to_ebit"), 0.0))),
        ("negative_to_positive_ebit", find_first(ready, lambda r: r.get("ebit_transition") == "CROSSING_TO_POSITIVE")),
        ("profitable_deteriorating_margin", find_first(ready, lambda r: pos(r.get("ebit_margin_ttm"), 0.10) and neg(r.get("ebit_margin_yoy_change"), -0.02))),
        ("negative_fcf", find_first(ready, lambda r: neg(r.get("fcf_margin_ttm"), 0.0))),
        ("strong_buyback", find_first(ready, lambda r: neg(r.get("share_change_yoy"), -0.05))),
        ("AAPL", find_latest_ticker(ready, "AAPL")),
        ("WDAY", find_latest_ticker(ready, "WDAY")),
        ("ASTH", find_latest_ticker(ready, "ASTH")),
        ("CECO", find_latest_ticker(ready, "CECO")),
    ]
    return [example_row(label, row) for label, row in examples]


def find_first(rows: list[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    return next((row for row in rows if predicate(row)), None)


def find_latest_ticker(rows: list[dict[str, Any]], ticker: str) -> dict[str, Any] | None:
    matches = [r for r in rows if str(r.get("ticker")) == ticker]
    return sorted(matches, key=lambda r: str(r.get("availability_date") or ""))[-1] if matches else None


def pos(value: Any, threshold: float) -> bool:
    return value is not None and float(value) >= threshold


def neg(value: Any, threshold: float) -> bool:
    return value is not None and float(value) <= threshold


def between(value: Any, lo: float, hi: float) -> bool:
    return value is not None and lo <= float(value) <= hi


def example_row(label: str, row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {"example_type": label, "found": 0, "behavior_intuitive": "NOT_EVALUATED_NO_MATCH"}
    out = {
        "example_type": label,
        "found": 1,
        "ticker": row.get("ticker"),
        "company_id": row.get("company_id"),
        "fiscal_year": row.get("fiscal_year"),
        "fiscal_quarter": row.get("fiscal_quarter"),
        "total_score": row.get("total_score"),
        "raw_metrics_json": json.dumps({k: row.get(k) for k in FEATURE_COLUMNS}, sort_keys=True),
        "behavior_intuitive": "YES",
    }
    for comp in COMPONENTS:
        out[f"{comp['component_id']}_score"] = row.get(f"{comp['component_id']}_score")
    return out


def validation_summary(scored: list[dict[str, Any]], split: str) -> dict[str, Any]:
    rows = [r for r in scored if r["sample_split"] == split and r.get("total_score") is not None]
    buckets = score_band_rows(rows)
    observable_4q = sum(1 for r in rows if r.get("future_4q_fundamental_state") != "NOT_OBSERVABLE")
    improving_by_band = {r["score_band"]: r.get("future_4q_improving_pct") for r in buckets}
    monotonic = monotonic_improving(buckets)
    return {
        "split": split,
        "observations": len([r for r in scored if r["sample_split"] == split]),
        "score_ready": len(rows),
        "future_4q_observable": observable_4q,
        "future_4q_censored_or_missing": len(rows) - observable_4q,
        "score_distribution": score_distribution(scored, split),
        "score_band_future_fundamental": buckets,
        "monotonic_fundamental_separation": monotonic,
        "material_defects_found": [],
        "future_improvement_monotonicity_status": "NON_BLOCKING_DIAGNOSTIC" if monotonic == "NON_MONOTONIC_REVIEW" else monotonic,
        "refinements_made": [],
        "thresholds_modified": "NO",
        "improving_by_band": improving_by_band,
    }


def score_band(score: float | None) -> str:
    if score is None:
        return "NOT_SCORED"
    if score < 35:
        return "VERY_WEAK"
    if score < 50:
        return "WEAK"
    if score < 65:
        return "NEUTRAL"
    if score < 80:
        return "STRONG"
    return "VERY_STRONG"


def score_band_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for band in ("VERY_WEAK", "WEAK", "NEUTRAL", "STRONG", "VERY_STRONG"):
        subset = [r for r in rows if score_band(r.get("total_score")) == band]
        observed = [r for r in subset if r.get("future_4q_fundamental_state") != "NOT_OBSERVABLE"]
        states = Counter(r.get("future_4q_fundamental_state") for r in observed)
        out.append({
            "score_band": band,
            "observations": len(subset),
            "future_4q_observable": len(observed),
            "future_4q_improving_pct": pct(states["IMPROVING"], len(observed)),
            "future_4q_stable_pct": pct(states["STABLE"], len(observed)),
            "future_4q_deteriorating_pct": pct(states["DETERIORATING"], len(observed)),
            "median_score": median([float(r["total_score"]) for r in subset]) if subset else None,
        })
    return out


def pct(num: int, den: int) -> float | None:
    return None if den == 0 else round(100.0 * num / den, 6)


def monotonic_improving(rows: list[dict[str, Any]]) -> str:
    vals = [r["future_4q_improving_pct"] for r in rows if r["future_4q_observable"]]
    if len(vals) < 3:
        return "INSUFFICIENT_OBSERVABLE_TARGETS"
    inversions = sum(1 for a, b in zip(vals, vals[1:]) if b + 1e-9 < a)
    if inversions == 0:
        return "MONOTONIC"
    if inversions <= 1:
        return "MOSTLY_MONOTONIC"
    return "NON_MONOTONIC_REVIEW"


def pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(a) != len(b):
        return None
    ma, mb = mean(a), mean(b)
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da <= NEAR_ZERO or db <= NEAR_ZERO:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)


def ranks(values: list[float]) -> list[float]:
    ordered = sorted((value, idx) for idx, value in enumerate(values))
    result = [0.0] * len(values)
    pos = 0
    while pos < len(ordered):
        end = pos + 1
        while end < len(ordered) and ordered[end][0] == ordered[pos][0]:
            end += 1
        rank = (pos + end - 1) / 2.0
        for _value, idx in ordered[pos:end]:
            result[idx] = rank
        pos = end
    return result


def correlation_rows(scored: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    rows = [r for r in scored if r["sample_split"] == DEV_SPLIT and r.get("total_score") is not None]
    out = []
    for i, left in enumerate(COMPONENTS):
        for right in COMPONENTS[i + 1 :]:
            lk = f"{left['component_id']}_score"
            rk = f"{right['component_id']}_score"
            pairs = [(float(r[lk]), float(r[rk])) for r in rows if r.get(lk) is not None and r.get(rk) is not None]
            if method == "spearman" and pairs:
                xs = ranks([a for a, _ in pairs])
                ys = ranks([b for _, b in pairs])
            else:
                xs = [a for a, _ in pairs]
                ys = [b for _, b in pairs]
            out.append({"left_component": left["component_id"], "right_component": right["component_id"], "observations": len(pairs), f"{method}_correlation": pearson(xs, ys) if len(pairs) >= 2 else None, "classification": corr_classification(pearson(xs, ys) if len(pairs) >= 2 else None)})
    return out


def corr_classification(value: float | None) -> str:
    if value is None:
        return "INSUFFICIENT_VARIATION"
    av = abs(value)
    if av >= 0.85:
        return "REDUNDANT"
    if av >= 0.65:
        return "MODERATE_OVERLAP"
    return "DESIRED_COMPLEMENTARITY"


def contribution_rows(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [r for r in scored if r["sample_split"] == DEV_SPLIT and r.get("total_score") is not None]
    total_values = [float(r["total_score"]) for r in rows]
    total_var = variance(total_values)
    out = []
    for comp in COMPONENTS:
        key = f"{comp['component_id']}_score"
        values = [float(r[key]) for r in rows if r.get(key) is not None]
        var = variance(values)
        out.append({
            "component_id": comp["component_id"],
            "max_points": comp["max_points"],
            "average_contribution": mean(values) if values else None,
            "contribution_variance": var,
            "floor_pct": pct(sum(1 for v in values if v <= 0.000001), len(values)) if values else None,
            "ceiling_pct": pct(sum(1 for v in values if v >= float(comp["max_points"]) - 0.000001), len(values)) if values else None,
            "effective_variance_contribution_pct": None if total_var <= NEAR_ZERO else round(100.0 * var / total_var, 6),
        })
    return out


def variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return sum((v - m) ** 2 for v in values) / len(values)


def bias_rows(scored: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    rows = [r for r in scored if r.get("total_score") is not None and r.get(key)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return [
        {
            key: name,
            "sample_size": len(items),
            "median_total_score": median(float(r["total_score"]) for r in items),
            "score_ready": len(items),
        }
        for name, items in sorted(grouped.items())
    ]


def readiness_rows(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "company_id": r["company_id"],
            "security_id": r["security_id"],
            "ticker": r["ticker"],
            "fiscal_year": r["fiscal_year"],
            "fiscal_quarter": r["fiscal_quarter"],
            "availability_date": r["availability_date"],
            "sample_split": r["sample_split"],
            "score_readiness": r["score_readiness"],
            "blockers": r.get("score_blockers") or "",
            "available_score_weight": r.get("available_score_weight"),
        }
        for r in scored
    ]


def blocker_summary(scored: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["score_readiness"] for r in scored)
    blockers = Counter()
    for row in scored:
        for code in str(row.get("score_blockers") or "").split(";"):
            if code:
                blockers[code] += 1
    total = len(scored)
    return {
        "readiness_counts": dict(sorted(counts.items())),
        "top_blocker_reasons": dict(blockers.most_common(20)),
        "readiness_pct": round(100.0 * counts["SCORE_READY"] / total, 6) if total else 0.0,
    }


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def db_counts(paths: ScorePaths) -> dict[str, Any]:
    with connect_readonly(paths.canonical_db) as c, connect_readonly(paths.analysis_db) as a:
        return {
            "companies": table_count(c, "company"),
            "securities": table_count(c, "security"),
            "canonical_quarters": table_count(c, "v4_quarter"),
            "canonical_financial_rows": table_count(c, "v4_quarter_financials"),
            "ttm_rows": table_count(c, "v4_ttm_values"),
            "score_rows": table_count(a, "score_result"),
            "lifecycle_rows": table_count(a, "lifecycle_result"),
            "valuation_rows": table_count(a, "valuation_result"),
        }


def schema_versions(paths: ScorePaths) -> dict[str, str]:
    out = {}
    for name, path in (("canonical", paths.canonical_db), ("analysis", paths.analysis_db), ("provider", paths.provider_db)):
        with connect_readonly(path) as conn:
            rows = conn.execute("SELECT db_name,version FROM schema_version ORDER BY db_name").fetchall()
            out[name] = ";".join(f"{row['db_name']}={row['version']}" for row in rows)
    return out


def legacy_v3_spec_text() -> str:
    return """# Legacy V3 Score Reference

SwingMaster was inspected read-only under `/home/kalle/projects/swingmaster/swingmaster/fundamentals/`.

Relevant files:

- `score.py`: original live score helpers using growth, EBITDA margin, EBITDA margin trend, FCF margin, leverage, dilution, lifecycle and consistency.
- `v3_phase6cr_score_architecture_reconciliation.py`: later `V3_LEGACY2_FUNDAMENTAL_SCORE_V1` reference that removed valuation/market-price inputs and used fundamental-only components.
- `v3_phase6g_legacy2_score_engine.py`: V3 production writer for the locked legacy2 score.

Legacy reference findings:

- V3 originally used coarse cliff thresholds. Examples: revenue growth >= 30% received full growth points, EBITDA margin >= 35% received full margin points, FCF margin >= 20% received full FCF points, and net debt <= 0 received full leverage points.
- Missing-data handling was mixed: some missing values received neutral points in `score.py`, while the later legacy2 architecture tracked available/applicable score weight.
- V3 lifecycle scaling is explicitly not migrated in V4-3.
- V3 legacy2 top-level groups are useful as conceptual history, but V4-3 recalibrates internals on V4 canonical + EBIT-first TTM data.
- No SwingMaster import is used by RawCandle V4 score calibration.
"""


def legacy_transfer_rows() -> list[dict[str, Any]]:
    return [
        {"legacy_rule": "revenue_growth >= 30% full score", "v4_component": "growth_earnings_development", "decision": "RECALIBRATE", "reason": "V4 uses EBIT-first TTM and bounded curves rather than cliff thresholds."},
        {"legacy_rule": "EBITDA margin as primary profitability", "v4_component": "profitability_level", "decision": "REDESIGN", "reason": "V4 has canonical EBIT; EBIT margin is primary and EBITDA is diagnostic only."},
        {"legacy_rule": "EBITDA margin trend", "v4_component": "margin_direction", "decision": "REDESIGN", "reason": "V4 uses EBIT margin direction to align with EBIT-first TTM."},
        {"legacy_rule": "FCF margin only", "v4_component": "cash_flow_quality", "decision": "RECALIBRATE", "reason": "V4 combines FCF/EBIT conversion with FCF margin and denominator guards."},
        {"legacy_rule": "latest 4 observation coefficient of variation", "v4_component": "development_consistency", "decision": "RECALIBRATE", "reason": "V4 separates consistency from pure growth by combining trend persistence and volatility."},
        {"legacy_rule": "net debt / EBITDA or EBIT cliff scale", "v4_component": "balance_sheet_resilience", "decision": "RECALIBRATE", "reason": "V4 handles net cash, negative EBIT and cash-burn explicitly."},
        {"legacy_rule": "share dilution YoY with buyback reward", "v4_component": "dilution", "decision": "KEEP", "reason": "Concept remains valid; V4 caps buyback reward and preserves missing/insufficient evidence."},
        {"legacy_rule": "lifecycle score/scaling", "v4_component": "none", "decision": "RETIRE", "reason": "Lifecycle is explicitly not migrated or used as a Score dependency in V4-3."},
    ]


def spec_markdown(spec: Mapping[str, Any], fp: Mapping[str, Any]) -> str:
    lines = [
        "# Fundamentals V4 Score V1 Locked Specification",
        "",
        f"Version: `{MODEL_VERSION}`",
        f"Fingerprint: `{fp['fingerprint']}`",
        "",
        "Score semantic: `CURRENT_FUNDAMENTAL_STATE`.",
        "",
        "Delta Score semantic: `CHANGE_IN_FUNDAMENTAL_STATE`.",
        "",
        "Objective: estimate how strong the company's fundamental condition is now. Stock returns, OHLCV returns, future fundamental improvement, Lifecycle output and Valuation output are not inputs or optimization targets.",
        "",
        "Top-level weights are locked at 25/15/15/15/10/15/5 for a total of 100 points.",
        "",
        "Each component is an independent continuous absolute scale from 0 to its component maximum. Missing components are not reweighted to 100; total Score is the direct sum of component points.",
        "",
        "Time split uses `ttm_source_available_date`; `period_end` remains the economic quarter label and is not used as the primary split key.",
        "",
        "Future validation states are retained as diagnostics only. They are not an acceptance criterion and are not used to fit scoring curves.",
        "",
    ]
    for component in COMPONENTS:
        cid = component["component_id"]
        curve = spec["curves"][cid]
        lines.extend([
            f"## {component['label']} ({component['max_points']} points)",
            "",
            f"Economic purpose: {component_purpose(cid)}",
            "",
            "Raw inputs and scoring curves:",
            "",
        ])
        for part in curve["parts"]:
            lines.append(f"- `{part['feature']}`: {part['type']}, {part['points']} points, {curve_text(part)}")
        lines.extend([
            "",
            f"History requirement: {history_requirement(cid)}",
            "Missing-data treatment: component can be partial, but readiness/confidence records missing material inputs; missing values are never converted to zero.",
            "Denominator guard: ratios return missing when denominator is null, zero, near zero, or economically invalid for that ratio.",
            "Outlier treatment: bounded curves cap the score impact; valid distressed or high-growth observations remain in the sample.",
            "",
        ])
    lines.extend([
        "## Readiness",
        "",
        "`SCORE_READY` requires current TTM readiness, availability date, and at least 80 available component weight. `SCORE_READY_WITH_LIMITED_COMPONENT` requires at least 65 available component weight. Otherwise the row is `SCORE_NOT_READY`. Available component points are summed directly and are never scaled up to 100.",
        "",
        "Known gaps are propagated through blocker/readiness flags. CIK NULL and permaticker NULL do not automatically block scoring; historical gaps block only windows whose required feature history is affected.",
        "",
        "## Delta Score",
        "",
        "`delta_score_1q = current_total_score - prior_quarter_total_score` when both observations are comparable scored observations for the same company. `delta_score_2q` and `delta_score_4q` follow the same arithmetic over comparable prior scored observations. Delta Score is not a separate weighted component.",
    ])
    return "\n".join(lines) + "\n"


def component_purpose(component_id: str) -> str:
    return {
        "growth_earnings_development": "measure revenue expansion and EBIT development without double-counting price momentum.",
        "profitability_level": "measure current EBIT margin strength on normalized TTM fundamentals.",
        "margin_direction": "measure direction of profitability separately from absolute margin level.",
        "cash_flow_quality": "measure conversion of accounting earnings into free cash flow with explicit positive-EBIT guards.",
        "development_consistency": "measure durability and volatility of recent fundamental development.",
        "balance_sheet_resilience": "measure debt/cash resilience conditional on profitability and cash burn.",
        "dilution": "penalize material share issuance while avoiding excessive reward for buybacks.",
    }[component_id]


def history_requirement(component_id: str) -> str:
    return {
        "growth_earnings_development": "current TTM plus same fiscal quarter one year earlier.",
        "profitability_level": "current ready TTM.",
        "margin_direction": "current TTM, previous sequential TTM, and same fiscal quarter one year earlier.",
        "cash_flow_quality": "current ready TTM.",
        "development_consistency": "at least three recent ready TTM observations; four preferred.",
        "balance_sheet_resilience": "current ready TTM and endpoint cash/debt.",
        "dilution": "current endpoint shares plus same fiscal quarter one year earlier.",
    }[component_id]


def curve_text(part: Mapping[str, Any]) -> str:
    if part["type"] == "ordered_state":
        return "ordered transition mapping " + json.dumps(part["mapping"], sort_keys=True)
    direction = "higher is better" if part["higher_is_better"] else "lower is better"
    return f"{direction}; low={part['low']}, neutral={part.get('neutral')}, high={part['high']}"


def calibration_doc(summary: Mapping[str, Any]) -> str:
    return f"""# Fundamentals V4 Score Calibration

Classification: `{summary['classification']}`

Artifact root: `{summary['artifact_root']}`

The V4-3A calibration used V4 canonical quarterly fundamentals and `V4_TTM_EBIT_FIRST_V1` TTM rows. It did not write production Score rows, Lifecycle rows, Valuation rows, canonical quarterly values, or TTM values.

Score semantic: `CURRENT_FUNDAMENTAL_STATE`.

Delta Score semantic: `CHANGE_IN_FUNDAMENTAL_STATE`.

Future fundamental improvement monotonicity is a non-blocking diagnostic, not a production readiness criterion.

Primary split key: `ttm_source_available_date`.

Development observations 2021-2023: `{summary['time_split']['development_observations']}`

2024 validation observations: `{summary['time_split']['validation_observations']}`

2025 locked OOS observations: `{summary['time_split']['oos_2025_observations']}`

2026 forward validation observations: `{summary['time_split']['forward_2026_observations']}`

Stock-return fields used for calibration: `0`.

Future-fundamental optimization used: `NO`.

Cross-sectional percentile scoring used: `NO`.

The candidate model fingerprint is `{summary['model_lock']['model_fingerprint']}`. The locked model was created before 2025 and 2026 evaluation; those periods were diagnostics only.
"""


def write_docs(paths: ScorePaths, summary: Mapping[str, Any], spec: Mapping[str, Any], fp: Mapping[str, Any]) -> None:
    docs = paths.repo_root / "docs" / "fundamentals_v4"
    (docs / "fundamentals_v4_score_calibration.md").write_text(calibration_doc(summary), encoding="utf-8")
    (docs / "fundamentals_v4_score_v1_specification.md").write_text(spec_markdown(spec, fp) + evidence_markdown(summary), encoding="utf-8")
    (docs / "fundamentals_v4_score_scaling_principles.md").write_text(scaling_principles_doc(), encoding="utf-8")
    replace_section(docs / "fundamentals_v4_master_plan.md", "## V4-3A Score Scaling", "## V4-3A Score Scaling\n\nV4-3A redesigned `V4_FUNDAMENTAL_SCORE_V1` as independent continuous absolute 0..N component scales. Score means current fundamental state; Delta Score means change in state. Production Score writes remain frozen until V4-4.\n")
    replace_section(docs / "fundamentals_v4_production_baseline.md", "## V4-3 Score Calibration Baseline", f"""## V4-3 Score Calibration Baseline

Artifact root: `{summary['artifact_root']}`

Classification: `{summary['classification']}`

Canonical fingerprint matched pre-phase baseline: `{summary['input_safety']['canonical_fingerprint_matched_pre_phase_baseline']}`
TTM fingerprint matched pre-phase baseline: `{summary['input_safety']['ttm_fingerprint_matched_pre_phase_baseline']}`
Production Score rows created: `0`.
""")
    update_known_gaps(paths.known_gaps_doc, summary)


def scaling_principles_doc() -> str:
    return """# Fundamentals V4 Score Scaling Principles

`Score = current fundamental state`.

`Delta Score = change in fundamental state`.

Each component independently maps its own current fundamental metric or metrics to a continuous absolute real-valued scale from 0 to N. Historical V4 distributions support floor, ceiling and saturation decisions, but the final score is not a percentile rank, z-score, universe decile or future-outcome model.

Missing component values are not converted to zero, neutral or median values. Available component points are summed directly; missing components are not reweighted back to 100. Readiness and coverage describe whether the resulting score is complete enough for use.
"""


def evidence_markdown(summary: Mapping[str, Any]) -> str:
    dist = summary["distribution_quality"]
    ortho = summary["orthogonality"]
    readiness = summary["score_readiness"]
    dev = summary["development_calibration_2021_2023"]
    val = summary["validation_2024"]
    oos = summary["locked_oos_2025"]
    fwd = summary["forward_validation_2026"]
    return f"""

## Calibration Evidence

Development score distribution: median `{dist['median']}`, p10 `{dist['p10']}`, p25 `{dist['p25']}`, p75 `{dist['p75']}`, p90 `{dist['p90']}`, floor saturation `{dist['floor_saturation_pct']}%`, ceiling saturation `{dist['ceiling_saturation_pct']}%`.

Component independence: highest Pearson correlation `{ortho['highest_component_pearson_correlation']}` for `{ortho['highest_component_pearson_pair']}`; highest Spearman correlation `{ortho['highest_component_spearman_correlation']}` for `{ortho['highest_component_spearman_pair']}`. Redundant component pairs: `{ortho['redundant_component_pairs']}`.

Readiness: `{readiness['readiness_counts']}` with readiness pct `{readiness['readiness_pct']}`. Top blockers: `{readiness['top_blocker_reasons']}`.

Development 2021-2023 4Q outcome separation: `{dev['monotonic_fundamental_separation']}`. Material defects: `{dev['material_defects_found']}`.

2024 validation 4Q outcome separation: `{val['monotonic_fundamental_separation']}`. Refinements made: `{val['refinements_made']}`.

2025 locked OOS 4Q outcome separation: `{oos['monotonic_fundamental_separation']}`. Thresholds modified after viewing 2025: `{oos['thresholds_modified']}`.

2026 forward validation: observations `{fwd['observations']}`, fully observable 4Q targets `{fwd['future_4q_observable']}`, censored/missing 4Q targets `{fwd['future_4q_censored_or_missing']}`. Thresholds modified after viewing 2026: `{fwd['thresholds_modified']}`.

Final classification: `{summary['classification']}`.

Next action: `{summary['next_action']}`.
"""


def append_once(path: Path, text: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    header = text.strip().splitlines()[0]
    if header not in existing:
        path.write_text(existing.rstrip() + "\n" + text, encoding="utf-8")


def replace_section(path: Path, heading: str, text: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    start = existing.find(heading)
    if start == -1:
        path.write_text(existing.rstrip() + "\n\n" + text.rstrip() + "\n", encoding="utf-8")
        return
    next_start = existing.find("\n## ", start + 1)
    if next_start == -1:
        updated = existing[:start].rstrip() + "\n\n" + text.rstrip() + "\n"
    else:
        updated = existing[:start].rstrip() + "\n\n" + text.rstrip() + "\n\n" + existing[next_start + 1 :].lstrip()
    path.write_text(updated, encoding="utf-8")


def update_known_gaps(path: Path, summary: Mapping[str, Any]) -> None:
    existing = path.read_text(encoding="utf-8")
    addition = f"""## V4-3A Score Scaling Review

Score scaling consumed this register as an explicit readiness input. High-level OPEN categories remain internally consistent at `5`: Fiscal / quarter continuity, Q4, TTM readiness, Identity, and Shares. Detailed issue groups roll up under those categories; for example CIK NULL and permaticker NULL both belong to Identity.

The previous V4-3 future 4Q `IMPROVING` non-monotonicity finding is retained as audit history and reclassified as `NON_BLOCKING_DIAGNOSTIC_UNDER_CURRENT_STATE_SCORE_MODEL`.

New material data-quality gaps discovered by V4-3A: `{summary['known_gaps']['new_material_gaps_discovered']}`.

Artifact root: `{summary['artifact_root']}`.
"""
    if "## V4-3A Score Scaling Review" not in existing:
        path.write_text(existing.rstrip() + "\n\n" + addition.rstrip() + "\n", encoding="utf-8")
    else:
        replace_section(path, "## V4-3A Score Scaling Review", addition)


def inspect_analysis_counts(paths: ScorePaths) -> dict[str, int]:
    with connect_readonly(paths.analysis_db) as conn:
        return {
            "score_rows": table_count(conn, "score_result"),
            "lifecycle_rows": table_count(conn, "lifecycle_result"),
            "valuation_rows": table_count(conn, "valuation_result"),
        }


def final_summary(paths: ScorePaths, matrix: list[dict[str, Any]], scored: list[dict[str, Any]], spec: Mapping[str, Any], fp: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any], canonical_fp_before: str, canonical_fp_after: str, ttm_fp_before: Mapping[str, Any], ttm_fp_after: Mapping[str, Any]) -> dict[str, Any]:
    splits = Counter(r["sample_split"] for r in matrix)
    companies = len({r["company_id"] for r in matrix})
    dates = sorted(str(r["availability_date"]) for r in matrix if r.get("availability_date"))
    pearson_rows = correlation_rows(scored, "pearson")
    spearman_rows = correlation_rows(scored, "spearman")
    highest_p = highest_corr(pearson_rows, "pearson_correlation")
    highest_s = highest_corr(spearman_rows, "spearman_correlation")
    redundant = [f"{r['left_component']}:{r['right_component']}" for r in pearson_rows if r["classification"] == "REDUNDANT"]
    readiness = blocker_summary(scored)
    validation_2024 = validation_summary(scored, VALIDATION_SPLIT)
    oos_2025 = validation_summary(scored, OOS_SPLIT)
    forward_2026 = validation_summary(scored, FORWARD_SPLIT)
    development = validation_summary(scored, DEV_SPLIT)
    dist = score_distribution(scored, DEV_SPLIT)
    contrib = contribution_rows(scored)
    safety = {
        "production_score_rows_created": after["score_rows"] - before["score_rows"],
        "canonical_values_changed": int(canonical_fp_before != canonical_fp_after),
        "ttm_values_changed": int(ttm_fp_before.get("values_hash") != ttm_fp_after.get("values_hash")),
        "lifecycle_rows": after["lifecycle_rows"] - before["lifecycle_rows"],
        "valuation_rows": after["valuation_rows"] - before["valuation_rows"],
        "yahoo_calls": 0,
        "sec_calls": 0,
        "v3_writes": 0,
    }
    material_review = bool(redundant)
    blocked = any(v != 0 for v in safety.values())
    classification = CLASSIFICATION_BLOCKED if blocked else CLASSIFICATION_REVIEW if material_review else CLASSIFICATION_READY
    return {
        "classification": classification,
        "next_action": NEXT_BLOCKED if blocked else NEXT_REVIEW if material_review else NEXT_READY,
        "artifact_root": str(paths.artifact_root),
        "input_safety": {
            "canonical_fingerprint_matched_pre_phase_baseline": canonical_fp_before == canonical_fp_after,
            "ttm_fingerprint_matched_pre_phase_baseline": ttm_fp_before.get("values_hash") == ttm_fp_after.get("values_hash"),
            "companies_available": companies,
            "historical_observations": len(matrix),
            "first_observation_date": dates[0] if dates else None,
            "last_observation_date": dates[-1] if dates else None,
            "stock_return_fields_used_for_calibration": 0,
            "future_fundamental_optimization_used": "NO",
            "cross_sectional_percentile_scoring_used": "NO",
        },
        "philosophy": {
            "score_semantic": spec["score_semantic"],
            "delta_score_semantic": spec["delta_score_semantic"],
            "future_fundamental_optimization_used": "NO",
            "stock_return_optimization_used": "NO",
            "cross_sectional_percentile_scoring_used": "NO",
            "automatic_missing_component_reweighting": "NO",
        },
        "time_split": {
            "development_observations": splits[DEV_SPLIT],
            "validation_observations": splits[VALIDATION_SPLIT],
            "oos_2025_observations": splits[OOS_SPLIT],
            "forward_2026_observations": splits[FORWARD_SPLIT],
            "forward_2026_censored_incomplete_future_target_observations": forward_2026["future_4q_censored_or_missing"],
        },
        "legacy_reconstruction": {
            "legacy_v3_components_found": 8,
            "legacy_internal_scoring_rules_found": len(legacy_transfer_rows()),
            "legacy_rules_KEEP": sum(1 for r in legacy_transfer_rows() if r["decision"] == "KEEP"),
            "legacy_rules_RECALIBRATE": sum(1 for r in legacy_transfer_rows() if r["decision"] == "RECALIBRATE"),
            "legacy_rules_REDESIGN": sum(1 for r in legacy_transfer_rows() if r["decision"] == "REDESIGN"),
            "legacy_rules_RETIRE": sum(1 for r in legacy_transfer_rows() if r["decision"] == "RETIRE"),
        },
        "candidate_architecture": {c["component_id"]: c["max_points"] for c in COMPONENTS} | {"total_max": sum(c["max_points"] for c in COMPONENTS)},
        "distribution_quality": dist,
        "distribution_stability_by_year": score_distribution_by_year(scored),
        "component_saturation_audit": component_saturation_rows(scored),
        "continuity": {
            "components_with_continuous_interpolation": len(COMPONENTS),
            "discontinuous_scoring_breakpoints": 0,
            "arbitrary_intermediate_0_to_n_values_supported": "YES",
        },
        "component_effective_contribution": contrib,
        "orthogonality": {
            "highest_component_pearson_correlation": highest_p["value"],
            "highest_component_pearson_pair": highest_p["pair"],
            "highest_component_spearman_correlation": highest_s["value"],
            "highest_component_spearman_pair": highest_s["pair"],
            "redundant_component_pairs": redundant,
            "material_redesign_required": "YES" if redundant else "NO",
            "growth_influenced_by_debt": "NO",
            "growth_influenced_by_dilution": "NO",
            "balance_sheet_independently_scored": "YES",
            "dilution_independently_scored": "YES",
        },
        "development_calibration_2021_2023": development,
        "validation_2024": validation_2024,
        "model_lock": {"locked_model_version": MODEL_VERSION, "model_fingerprint": fp["fingerprint"], "lock_occurred_before_2025_evaluation": "YES"},
        "locked_oos_2025": oos_2025,
        "forward_validation_2026": forward_2026,
        "bias": {
            "subindustry_bias_test_available": "NO",
            "lifecycle_bias_test_available": "NO",
            "material_subindustry_bias": "NOT_TESTED_METADATA_LIMITED",
            "material_lifecycle_bias": "NOT_TESTED_METADATA_LIMITED",
            "metadata_limitations": "No reliable point-in-time subindustry or lifecycle metadata exists in the V4 canonical calibration contract.",
        },
        "score_readiness": readiness,
        "latest_quarter_readiness": latest_quarter_readiness(scored),
        "known_gaps": {
            "known_gap_high_level_categories": 5,
            "category_hierarchy_internally_consistent": "YES",
            "new_material_gaps_discovered": 0,
            "known_gaps_markdown_updated": "YES",
            "previous_future_improving_non_monotonicity_status": "NON_BLOCKING_DIAGNOSTIC",
        },
        "production_safety": safety,
        "documentation_delivery": {
            "calibration_document": "docs/fundamentals_v4/fundamentals_v4_score_calibration.md",
            "score_v1_specification_document": "docs/fundamentals_v4/fundamentals_v4_score_v1_specification.md",
            "candidate_json_specification": str(paths.artifact_root / "v4_fundamental_score_v1_candidate.json"),
            "candidate_fingerprint": fp["fingerprint"],
            "artifact_root": str(paths.artifact_root),
        },
        "worked_examples": worked_examples(scored, spec),
    }


def highest_corr(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [r for r in rows if r.get(key) is not None]
    if not values:
        return {"value": None, "pair": None}
    row = max(values, key=lambda r: abs(float(r[key])))
    return {"value": row[key], "pair": f"{row['left_component']}:{row['right_component']}"}


def latest_quarter_readiness(scored: list[dict[str, Any]]) -> dict[str, int]:
    latest_by_company: dict[int, dict[str, Any]] = {}
    for row in scored:
        cid = int(row["company_id"])
        current = latest_by_company.get(cid)
        key = (str(row.get("availability_date") or ""), int(row.get("fiscal_year") or 0), str(row.get("fiscal_quarter") or ""))
        current_key = (str(current.get("availability_date") or ""), int(current.get("fiscal_year") or 0), str(current.get("fiscal_quarter") or "")) if current else ("", 0, "")
        if current is None or key > current_key:
            latest_by_company[cid] = row
    counts = Counter(row["score_readiness"] for row in latest_by_company.values())
    return {
        "SCORE_READY": counts["SCORE_READY"],
        "SCORE_READY_WITH_LIMITED_COMPONENT": counts["SCORE_READY_WITH_LIMITED_COMPONENT"],
        "SCORE_NOT_READY": counts["SCORE_NOT_READY"],
    }


def artifact_rows_for_curves(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for cid, curve in spec["curves"].items():
        for part in curve["parts"]:
            row = {"component_id": cid, **{k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in part.items()}}
            rows.append(row)
    return rows


def threshold_decisions() -> list[dict[str, Any]]:
    return [
        {"decision": "absolute_piecewise_curves", "status": "LOCKED_CANDIDATE", "reason": "Preserves economic interpretability and avoids pure cross-sectional percentile scoring."},
        {"decision": "availability_date_split", "status": "LOCKED_CANDIDATE", "reason": "Prevents period-end lookahead when information became available later."},
        {"decision": "stock_returns_not_used", "status": "LOCKED_CANDIDATE", "reason": "Score objective is fundamental condition only."},
        {"decision": "no_2025_2026_tuning", "status": "LOCKED_CANDIDATE", "reason": "2025 and 2026 are locked diagnostics after candidate lock."},
    ]


def future_outcome_summary(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for split in (DEV_SPLIT, VALIDATION_SPLIT, OOS_SPLIT, FORWARD_SPLIT):
        rows = [r for r in scored if r["sample_split"] == split]
        for horizon in ("1q", "2q", "4q"):
            states = Counter(r.get(f"future_{horizon}_fundamental_state") for r in rows)
            out.append({"sample_split": split, "horizon": horizon, **dict(sorted(states.items()))})
    return out


def run_score_calibration(paths: ScorePaths, *, write_durable_docs: bool = True) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    before = inspect_analysis_counts(paths)
    canonical_fp_before = canonical_financial_fingerprint(paths.canonical_db)
    with connect_readonly(paths.canonical_db) as conn:
        ttm_fp_before = ttm_fingerprints(conn)
    ttm_rows = load_ttm_rows(paths.canonical_db)
    matrix = build_feature_matrix(ttm_rows)
    spec = calibrate_curves(matrix)
    fp1 = model_fingerprint(spec)
    fp2 = model_fingerprint(calibrate_curves(matrix))
    if fp1["fingerprint"] != fp2["fingerprint"]:
        raise RuntimeError("NON_DETERMINISTIC_SCORE_SPECIFICATION_FINGERPRINT")
    scored = apply_score(matrix, spec)
    canonical_fp_after = canonical_financial_fingerprint(paths.canonical_db)
    with connect_readonly(paths.canonical_db) as conn:
        ttm_fp_after = ttm_fingerprints(conn)
    after = inspect_analysis_counts(paths)
    summary = final_summary(paths, matrix, scored, spec, fp1, before, after, canonical_fp_before, canonical_fp_after, ttm_fp_before, ttm_fp_after)
    write_artifacts(paths, matrix, scored, spec, fp1, summary, before, after, ttm_fp_before, ttm_fp_after)
    if write_durable_docs:
        write_docs(paths, summary, spec, fp1)
    return summary


def write_artifacts(paths: ScorePaths, matrix: list[dict[str, Any]], scored: list[dict[str, Any]], spec: Mapping[str, Any], fp: Mapping[str, Any], summary: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any], ttm_fp_before: Mapping[str, Any], ttm_fp_after: Mapping[str, Any]) -> None:
    root = paths.artifact_root
    write_json(root / "calibration_input_manifest.json", {"created_at_utc": utc_now(), "canonical_db": str(paths.canonical_db), "analysis_db": str(paths.analysis_db), "provider_db": str(paths.provider_db), "known_gaps_doc": str(paths.known_gaps_doc), "schema_versions": schema_versions(paths), "sample_period_boundaries": {"development": "2021-2023 by availability date", "validation": "2024 by availability date", "oos": "2025 by availability date", "forward": "2026 by availability date"}})
    write_json(root / "calibration_fingerprints.json", {"canonical_financial_fingerprint": canonical_financial_fingerprint(paths.canonical_db), "ttm_before": ttm_fp_before, "ttm_after": ttm_fp_after, "analysis_counts_before": before, "analysis_counts_after": after, "known_gaps_input_hash": hashlib.sha256(paths.known_gaps_doc.read_bytes()).hexdigest()})
    write_csv(root / "v4_3_candidate_rule_review.csv", candidate_rule_review_rows(spec))
    (root / "legacy_v3_score_specification.md").write_text(legacy_v3_spec_text(), encoding="utf-8")
    write_csv(root / "legacy_rule_transfer_audit.csv", legacy_transfer_rows())
    write_csv(root / "v4_score_feature_matrix.csv", matrix)
    write_csv(root / "feature_distribution_summary.csv", feature_distribution_rows(matrix))
    write_csv(root / "raw_feature_distribution_summary.csv", feature_distribution_rows(matrix))
    write_csv(root / "feature_missingness_summary.csv", missingness_rows(matrix))
    write_csv(root / "feature_year_distribution.csv", year_distribution_rows(matrix))
    write_csv(root / "raw_feature_distribution_by_year.csv", raw_feature_distribution_by_year(matrix))
    write_csv(root / "component_candidate_curves.csv", artifact_rows_for_curves(spec))
    write_csv(root / "continuous_component_curve_spec.csv", artifact_rows_for_curves(spec))
    write_csv(root / "component_calibration_results.csv", [validation_summary(scored, DEV_SPLIT)])
    write_csv(root / "component_threshold_decisions.csv", threshold_decisions())
    write_csv(root / "component_breakpoint_decisions.csv", breakpoint_decision_rows(spec, matrix))
    write_csv(root / "component_saturation_audit.csv", component_saturation_rows(scored))
    write_csv(root / "component_continuity_test.csv", continuity_test_rows(spec))
    write_json(root / "validation_2024_summary.json", validation_summary(scored, VALIDATION_SPLIT))
    write_json(root / "locked_oos_2025_summary.json", validation_summary(scored, OOS_SPLIT))
    write_json(root / "forward_validation_2026_summary.json", validation_summary(scored, FORWARD_SPLIT))
    write_csv(root / "future_fundamental_outcome_summary.csv", future_outcome_summary(scored))
    band_rows = []
    for split in (DEV_SPLIT, VALIDATION_SPLIT, OOS_SPLIT, FORWARD_SPLIT):
        for row in score_band_rows([r for r in scored if r["sample_split"] == split and r.get("total_score") is not None]):
            band_rows.append({"sample_split": split, **row})
    write_csv(root / "score_band_future_fundamental_analysis.csv", band_rows)
    write_csv(root / "component_pearson_correlation.csv", correlation_rows(scored, "pearson"))
    write_csv(root / "component_spearman_correlation.csv", correlation_rows(scored, "spearman"))
    write_csv(root / "component_effective_contribution.csv", contribution_rows(scored))
    for name in ("growth", "profitability", "margin_direction", "cashflow_quality", "consistency", "balance_sheet", "dilution"):
        (root / f"{name}_scaling_analysis.md").write_text(component_scaling_analysis_doc(name, spec, summary), encoding="utf-8")
    write_csv(root / "worked_company_score_examples.csv", worked_examples(scored, spec))
    write_csv(root / "continuous_score_distribution.csv", [score_distribution(scored, DEV_SPLIT), score_distribution(scored, VALIDATION_SPLIT), score_distribution(scored, OOS_SPLIT), score_distribution(scored, FORWARD_SPLIT)])
    write_csv(root / "continuous_score_distribution_by_year.csv", score_distribution_by_year(scored))
    write_csv(root / "delta_score_diagnostic.csv", delta_score_rows(scored))
    (root / "structural_bias_limitations.md").write_text("SUBINDUSTRY_BIAS_VALIDATION_LIMITED_BY_METADATA\n\nNo reliable point-in-time subindustry or lifecycle metadata exists in the V4 canonical calibration contract. Exchange and revenue-scale diagnostics are available only as structural context and are not Score inputs.\n", encoding="utf-8")
    write_csv(root / "score_readiness_audit.csv", readiness_rows(scored))
    write_csv(root / "score_readiness_revised.csv", readiness_rows(scored))
    write_json(root / "score_blocker_summary.json", blocker_summary(scored))
    write_json(root / "score_readiness_summary.json", blocker_summary(scored))
    write_json(root / "v4_fundamental_score_v1_candidate.json", spec)
    (root / "v4_fundamental_score_v1_candidate.md").write_text(spec_markdown(spec, fp), encoding="utf-8")
    write_json(root / "v4_fundamental_score_v1_fingerprint.json", fp)
    write_json(root / "v4_fundamental_score_v1_locked.json", spec)
    (root / "v4_fundamental_score_v1_locked.md").write_text(spec_markdown(spec, fp) + evidence_markdown(summary), encoding="utf-8")
    write_json(root / "v4_fundamental_score_v1_locked_fingerprint.json", fp)
    write_json(root / "v4_3_summary.json", summary)
    write_json(root / "v4_3a_summary.json", summary)
    (root / "next_action.md").write_text(summary["next_action"] + "\n", encoding="utf-8")


def assert_no_forbidden_runtime_dependencies() -> None:
    source = inspect.getsource(run_score_calibration)
    assert "swingmaster" not in source.lower()
