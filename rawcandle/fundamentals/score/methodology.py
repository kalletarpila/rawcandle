from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence


MODEL_VERSION = "SIMPLE_FUNDAMENTAL_SCORE_V1"
TTM_MODEL_VERSION = "V4_TTM_EBIT_FIRST_V1"
DEVELOPMENT_CUTOFFS = ("2023-12-31", "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31")
VALIDATION_CUTOFFS = ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
RESEARCH_CUTOFFS = (
    "2021-12-31",
    "2022-03-31",
    "2022-06-30",
    "2022-09-30",
    "2022-12-31",
    "2023-06-30",
    "2023-09-30",
    *DEVELOPMENT_CUTOFFS,
    *VALIDATION_CUTOFFS,
)
PERCENTILES = (0.10, 0.25, 0.50, 0.75, 0.85, 0.90)
CONSISTENCY_TOLERANCES = {
    "revenue_growth_yoy_ttm": 0.20,
    "ebit_margin_ttm": 0.05,
    "fcf_margin_ttm": 0.10,
}
ANCHORS = {
    "revenue_growth_yoy_ttm": ((-0.10, 0.0), (0.0, 7.0), (0.10, 12.0), (0.20, 16.0), (0.30, 20.0)),
    "ebit_margin_ttm": ((0.0, 0.0), (0.10, 7.5), (0.25, 15.0)),
    "ebit_margin_direction": ((-0.05, 0.0), (0.0, 7.5), (0.05, 15.0)),
    "fcf_margin_ttm": ((-0.05, 0.0), (0.0, 3.0), (0.05, 7.0), (0.10, 11.0), (0.20, 15.0)),
    "share_change_yoy": ((-0.02, 10.0), (0.0, 8.0), (0.02, 5.0), (0.05, 2.0), (0.10, 0.0)),
}
METRICS = (
    "revenue_growth_yoy_ttm",
    "ebit_margin_ttm",
    "ebit_margin_direction",
    "fcf_margin_ttm",
    "net_debt_to_ebit",
    "share_change_yoy",
    "consistency_points",
)


@dataclass(frozen=True)
class ResearchPaths:
    repo_root: Path
    artifact_root: Path
    canonical_db: Path
    provider_db: Path
    market_db: Path


def research_paths(repo_root: Path, timestamp: str | None = None) -> ResearchPaths:
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ResearchPaths(
        repo_root=repo_root,
        artifact_root=repo_root / "temp" / "fundamentals_v4_3b_score_methodology" / stamp,
        canonical_db=repo_root / "data" / "fundamentals_v4.db",
        provider_db=repo_root / "data" / "fundamentals_provider.db",
        market_db=repo_root / "data" / "osakedata.db",
    )


def connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) <= 1e-12:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def safe_growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 1e-12:
        return None
    value = current / previous - 1.0
    return value if math.isfinite(value) else None


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def piecewise_score(value: float | None, anchors: Sequence[tuple[float, float]]) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (left_x, left_y), (right_x, right_y) in zip(anchors, anchors[1:]):
        if left_x <= value <= right_x:
            fraction = (value - left_x) / (right_x - left_x)
            return left_y + fraction * (right_y - left_y)
    raise AssertionError("piecewise interval not found")


def fiscal_ordinal(year: Any, quarter: Any) -> int:
    return int(year) * 4 + int(str(quarter).removeprefix("Q")) - 1


def percentile(values: Iterable[float | None], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not ordered:
        return None
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def load_ttm_rows(path: Path) -> list[dict[str, Any]]:
    with connect_readonly(path) as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT t.*, s.current_ticker AS ticker, s.active AS security_active,
                       s.exchange, c.company_name
                FROM v4_ttm_values t
                JOIN security s ON s.security_id = t.security_id
                JOIN company c ON c.company_id = t.company_id
                WHERE t.model_version = ?
                  AND t.ttm_source_available_date <= '2025-12-31'
                ORDER BY t.company_id, t.endpoint_fiscal_year,
                    CASE t.endpoint_fiscal_quarter
                        WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END
                """,
                (TTM_MODEL_VERSION,),
            )
        ]


def _metric_levels(row: Mapping[str, Any], previous_year: Mapping[str, Any] | None) -> dict[str, float | None]:
    revenue = _float(row.get("ttm_revenue"))
    ebit = _float(row.get("ttm_ebit"))
    fcf = _float(row.get("ttm_free_cashflow"))
    previous_revenue = _float(previous_year.get("ttm_revenue")) if previous_year else None
    previous_ebit = _float(previous_year.get("ttm_ebit")) if previous_year else None
    return {
        "revenue_growth_yoy_ttm": safe_growth(revenue, previous_revenue),
        "ebit_margin_ttm": safe_div(ebit, revenue),
        "ebit_margin_direction": _difference(safe_div(ebit, revenue), safe_div(previous_ebit, previous_revenue)),
        "fcf_margin_ttm": safe_div(fcf, revenue),
    }


def build_features(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["company_id"])].append(row)
    output: list[dict[str, Any]] = []
    for company_rows in grouped.values():
        ordered = sorted(company_rows, key=lambda row: fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"]))
        by_ordinal = {fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"]): row for row in ordered}
        levels: dict[int, dict[str, float | None]] = {}
        for row in ordered:
            ordinal = fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"])
            previous_year = by_ordinal.get(ordinal - 4)
            levels[ordinal] = _metric_levels(row, previous_year)
        for row in ordered:
            ordinal = fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"])
            current = levels[ordinal]
            consistency = consistency_points(ordinal, by_ordinal, levels)
            cash = _float(row.get("cash"))
            debt = _float(row.get("total_debt"))
            ebit = _float(row.get("ttm_ebit"))
            previous_year = by_ordinal.get(ordinal - 4)
            shares = _float(row.get("shares_outstanding"))
            previous_shares = _float(previous_year.get("shares_outstanding")) if previous_year else None
            item = {
                **dict(row),
                **current,
                "fiscal_ordinal": ordinal,
                "net_debt": None if cash is None or debt is None else debt - cash,
                "net_debt_to_ebit": safe_div(debt - cash, ebit) if cash is not None and debt is not None and ebit is not None and ebit > 0 else None,
                "share_change_yoy": safe_growth(shares, previous_shares),
                "consistency_points": consistency,
                "dilution_outlier": int(safe_growth(shares, previous_shares) is not None and abs(safe_growth(shares, previous_shares) or 0.0) > 0.50),
                "recent_ebit_margin_trend": _recent_margin_trend(ordinal, by_ordinal),
            }
            item.update(component_scores(item))
            output.append(item)
    return output


def consistency_points(
    endpoint_ordinal: int,
    rows_by_ordinal: Mapping[int, Mapping[str, Any]],
    levels_by_ordinal: Mapping[int, Mapping[str, float | None]],
) -> float | None:
    available = []
    for count in (4, 3):
        ordinals = list(range(endpoint_ordinal - count + 1, endpoint_ordinal + 1))
        if all(
            ordinal in rows_by_ordinal
            and int(rows_by_ordinal[ordinal].get("core_ttm_ready") or 0) == 1
            and all(levels_by_ordinal[ordinal].get(metric) is not None for metric in CONSISTENCY_TOLERANCES)
            for ordinal in ordinals
        ):
            available = ordinals
            break
    if not available:
        return None
    instabilities = []
    for metric, tolerance in CONSISTENCY_TOLERANCES.items():
        changes = [
            clamp(abs(float(levels_by_ordinal[current][metric]) - float(levels_by_ordinal[previous][metric])) / tolerance, 0.0, 1.0)
            for previous, current in zip(available, available[1:])
        ]
        instabilities.append(mean(changes))
    return clamp(10.0 * (1.0 - mean(instabilities)), 0.0, 10.0)


def balance_points(row: Mapping[str, Any], floor: float = 4.0) -> float | None:
    cash = _float(row.get("cash"))
    debt = _float(row.get("total_debt"))
    ebit = _float(row.get("ttm_ebit"))
    fcf = _float(row.get("ttm_free_cashflow"))
    if cash is None or debt is None or ebit is None or fcf is None:
        return None
    net_debt = debt - cash
    if ebit > 0:
        return piecewise_score(net_debt / ebit, ((0.0, 15.0), (1.0, 12.0), (2.0, 8.0), (3.0, 4.0), (floor, 0.0)))
    if net_debt <= 0 and fcf >= 0:
        return 10.0
    if net_debt <= 0 and fcf < 0:
        return 5.0
    return 0.0


def component_scores(row: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "revenue_growth_points": piecewise_score(_float(row.get("revenue_growth_yoy_ttm")), ANCHORS["revenue_growth_yoy_ttm"]),
        "ebit_profitability_points": piecewise_score(_float(row.get("ebit_margin_ttm")), ANCHORS["ebit_margin_ttm"]),
        "ebit_margin_direction_points": piecewise_score(_float(row.get("ebit_margin_direction")), ANCHORS["ebit_margin_direction"]),
        "fcf_margin_points": piecewise_score(_float(row.get("fcf_margin_ttm")), ANCHORS["fcf_margin_ttm"]),
        "balance_sheet_points": balance_points(row),
        "dilution_points": piecewise_score(_float(row.get("share_change_yoy")), ANCHORS["share_change_yoy"]),
    }


def asof_snapshot(features: Sequence[Mapping[str, Any]], cutoff: str) -> list[dict[str, Any]]:
    latest: dict[int, Mapping[str, Any]] = {}
    for row in features:
        available = row.get("ttm_source_available_date")
        if not available or str(available) > cutoff:
            continue
        security_id = int(row["security_id"])
        current = latest.get(security_id)
        key = (str(available), int(row["fiscal_ordinal"]), int(row["ttm_id"]))
        current_key = (
            str(current.get("ttm_source_available_date")),
            int(current["fiscal_ordinal"]),
            int(current["ttm_id"]),
        ) if current else ("", -1, -1)
        if key > current_key:
            latest[security_id] = row
    output = []
    cutoff_date = date.fromisoformat(cutoff)
    for row in latest.values():
        item = dict(row)
        item["snapshot_age_days"] = (cutoff_date - date.fromisoformat(str(row["ttm_source_available_date"]))).days
        output.append(item)
    return sorted(output, key=lambda row: int(row["security_id"]))


def cross_section_summary(features: Sequence[Mapping[str, Any]], cutoff: str) -> dict[str, Any]:
    rows = asof_snapshot(features, cutoff)
    ttm_ready = [row for row in rows if int(row.get("core_ttm_ready") or 0) == 1]
    ready = [row for row in ttm_ready if int(row["snapshot_age_days"]) <= 180]
    metric_summary = {}
    for metric in METRICS:
        values = [_float(row.get(metric)) for row in ready]
        non_null = [value for value in values if value is not None]
        low, high = _anchor_bounds(metric)
        metric_summary[metric] = {
            "non_null_count": len(non_null),
            **{f"p{int(q * 100)}": percentile(non_null, q) for q in PERCENTILES},
            "floor_saturation": _fraction(non_null, lambda value: value <= low) if low is not None else None,
            "ceiling_saturation": _fraction(non_null, lambda value: value >= high) if high is not None else None,
        }
    ages = [float(row["snapshot_age_days"]) for row in rows]
    return {
        "cutoff": cutoff,
        "eligible_security_count": len(rows),
        "ttm_ready_security_count": len(ttm_ready),
        "ready_security_count": len(ready),
        "fresh_180d_count": len(ready),
        "snapshot_age_days": {f"p{int(q * 100)}": percentile(ages, q) for q in (0.10, 0.25, 0.50, 0.75, 0.90)},
        "snapshot_age_max": max(ages) if ages else None,
        "metrics": metric_summary,
        "consistency_zero_saturation": _fraction([_float(row.get("consistency_points")) for row in ready], lambda value: value <= 0.0),
        "consistency_full_saturation": _fraction([_float(row.get("consistency_points")) for row in ready], lambda value: value >= 10.0),
    }


def aggregate_percentiles(summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for metric in METRICS:
        for name in ("p10", "p25", "p50", "p75", "p85", "p90", "floor_saturation", "ceiling_saturation"):
            values = [_float(summary["metrics"][metric].get(name)) for summary in summaries]
            values = [value for value in values if value is not None]
            rows.append({
                "metric": metric,
                "statistic": name,
                "cutoff_median": median(values) if values else None,
                "cutoff_min": min(values) if values else None,
                "cutoff_max": max(values) if values else None,
            })
    return rows


def legacy_consistency(row: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> float | None:
    endpoint = int(row["fiscal_ordinal"])
    by_ordinal = {int(item["fiscal_ordinal"]): item for item in history}
    ordinals = list(range(endpoint - 3, endpoint + 1))
    if not all(ordinal in by_ordinal for ordinal in ordinals):
        ordinals = list(range(endpoint - 2, endpoint + 1))
    series = []
    for metric in ("revenue_growth_yoy_ttm", "ebitda_margin_ttm", "fcf_margin_ttm"):
        values = [_float(by_ordinal[ordinal].get(metric)) for ordinal in ordinals if ordinal in by_ordinal]
        if len(values) < 3 or any(value is None for value in values):
            return None
        average = mean(float(value) for value in values)
        if abs(average) <= 1e-12:
            coefficient = math.inf
        else:
            variance = mean((float(value) - average) ** 2 for value in values)
            coefficient = math.sqrt(variance) / abs(average)
        series.append(coefficient)
    average_cv = mean(series)
    for limit, points in ((0.05, 10.0), (0.10, 8.0), (0.15, 6.0), (0.20, 4.0), (0.30, 2.0)):
        if average_cv <= limit:
            return points
    return 0.0


def add_legacy_inputs(features: list[dict[str, Any]]) -> None:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        grouped[int(row["company_id"])].append(row)
        row["ebitda_margin_ttm"] = safe_div(_float(row.get("ttm_ebitda")), _float(row.get("ttm_revenue")))
    for rows in grouped.values():
        for row in rows:
            row["legacy_consistency_points"] = legacy_consistency(row, rows)


def consistency_examples(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates = [row for row in rows if row.get("consistency_points") is not None]
    selectors = {
        "stable_strong": lambda row: _float(row.get("ebit_margin_ttm")) is not None and _float(row.get("ebit_margin_ttm")) >= 0.20 and _float(row.get("fcf_margin_ttm")) is not None and _float(row.get("fcf_margin_ttm")) >= 0.10,
        "stable_weak": lambda row: _float(row.get("ebit_margin_ttm")) is not None and _float(row.get("ebit_margin_ttm")) <= 0 and _float(row.get("fcf_margin_ttm")) is not None and _float(row.get("fcf_margin_ttm")) <= 0,
        "steadily_improving": lambda row: row.get("recent_ebit_margin_trend") == "IMPROVING",
        "steadily_weakening": lambda row: row.get("recent_ebit_margin_trend") == "WEAKENING",
        "volatile": lambda row: True,
    }
    examples = []
    for label, predicate in selectors.items():
        subset = [row for row in candidates if predicate(row)]
        reverse = label != "volatile"
        if subset:
            chosen = sorted(subset, key=lambda row: float(row["consistency_points"]), reverse=reverse)[0]
            examples.append({
                "example_type": label,
                "ticker": chosen.get("ticker"),
                "period_end": chosen.get("period_end"),
                "availability_date": chosen.get("ttm_source_available_date"),
                "revenue_growth_yoy_ttm": chosen.get("revenue_growth_yoy_ttm"),
                "ebit_margin_ttm": chosen.get("ebit_margin_ttm"),
                "ebit_margin_direction": chosen.get("ebit_margin_direction"),
                "fcf_margin_ttm": chosen.get("fcf_margin_ttm"),
                "consistency_points": chosen.get("consistency_points"),
                "legacy_consistency_points": chosen.get("legacy_consistency_points"),
            })
    return examples


def dilution_audit(provider_db: Path, market_db: Path, canonical_features: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    security_by_ticker: dict[str, dict[str, Any]] = {}
    with connect_readonly(provider_db.parent / "fundamentals_v4.db") as conn:
        for row in conn.execute(
            """
            SELECT psi.provider_ticker, s.security_id, s.active
            FROM provider_security_identity psi
            JOIN security s ON s.security_id = psi.security_id
            WHERE psi.provider = 'SHARADAR'
            """
        ):
            security_by_ticker[str(row["provider_ticker"])] = dict(row)
    revenue_by_key = {
        (int(row["company_id"]), int(row["fiscal_ordinal"])): abs(float(row["ttm_revenue"]))
        for row in canonical_features
        if row.get("ttm_revenue") is not None
    }
    company_by_security = {int(row["security_id"]): int(row["company_id"]) for row in canonical_features}
    action_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    split_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    provider_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with connect_readonly(market_db) as conn:
        for row in conn.execute("SELECT osake AS ticker, split_date AS date, split_ratio FROM splits_data WHERE split_date <= '2025-12-31'"):
            split_by_ticker[str(row["ticker"])].append(dict(row))
    with connect_readonly(provider_db) as conn:
        for row in conn.execute("SELECT date, action, ticker, value FROM sharadar_action_metadata WHERE date <= '2025-12-31'"):
            action_by_ticker[str(row["ticker"])].append(dict(row))
        for row in conn.execute(
            """
            SELECT ticker, reportperiod, fiscalperiod, sharesbas, shareswa, shareswadil
            FROM sharadar_fundamental_observation
            WHERE dimension = 'ARQ'
              AND date <= '2025-12-31'
            ORDER BY ticker, reportperiod
            """
        ):
            provider_rows[str(row["ticker"])].append(dict(row))
    outliers = []
    total_yoy = 0
    for ticker, rows in provider_rows.items():
        indexed = {_provider_ordinal(row["fiscalperiod"]): row for row in rows if _provider_ordinal(row["fiscalperiod"]) is not None}
        security = security_by_ticker.get(ticker, {})
        security_id = security.get("security_id")
        company_id = company_by_security.get(int(security_id)) if security_id is not None else None
        for ordinal, row in indexed.items():
            previous = indexed.get(ordinal - 4)
            change = safe_growth(_float(row.get("sharesbas")), _float(previous.get("sharesbas")) if previous else None)
            if change is None:
                continue
            total_yoy += 1
            if abs(change) <= 0.50:
                continue
            next_row = indexed.get(ordinal + 1)
            wa_change = safe_growth(_float(row.get("shareswa")), _float(previous.get("shareswa")) if previous else None)
            wadil_change = safe_growth(_float(row.get("shareswadil")), _float(previous.get("shareswadil")) if previous else None)
            actions = action_by_ticker.get(str(row["ticker"]), [])
            previous_period_end = date.fromisoformat(str(previous["reportperiod"]))
            current_period_end = date.fromisoformat(str(row["reportperiod"]))
            action_match = [action for action in actions if previous_period_end < date.fromisoformat(action["date"]) <= current_period_end]
            split_match = [split for split in split_by_ticker.get(ticker, []) if previous_period_end < date.fromisoformat(split["date"]) <= current_period_end]
            revenue = revenue_by_key.get((company_id, ordinal)) if company_id is not None else None
            outliers.append({
                "ticker": row["ticker"],
                "security_active": security.get("active"),
                "fiscalperiod": row["fiscalperiod"],
                "reportperiod": row["reportperiod"],
                "direction": "POSITIVE" if change > 0 else "NEGATIVE",
                "sharesbas_change_yoy": change,
                "shareswa_change_yoy": wa_change,
                "shareswadil_change_yoy": wadil_change,
                "weighted_average_corroboration": _corroboration(change, wa_change, wadil_change),
                "next_quarter_sequential_change": safe_growth(_float(next_row.get("sharesbas")) if next_row else None, _float(row.get("sharesbas"))),
                "company_size_bucket": _size_bucket(revenue),
                "local_action_evidence": ";".join(sorted({str(action["action"]) for action in action_match})),
                "local_split_evidence": ";".join(str(split["split_ratio"]) for split in split_match),
                "evidence_classification": _dilution_evidence_classification(change, wa_change, wadil_change, action_match, split_match),
            })
    strata = _stratify_outliers(outliers)
    sample = _representative_sample(outliers, 60)
    return {
        "provider_yoy_observations": total_yoy,
        "outlier_count": len(outliers),
        "outlier_rate": len(outliers) / total_yoy if total_yoy else None,
        "outliers": outliers,
        "strata": strata,
        "sample": sample,
        "classification_counts": dict(Counter(row["evidence_classification"] for row in outliers)),
        "local_action_coverage": sum(1 for row in outliers if row["local_action_evidence"]),
        "local_split_coverage": sum(1 for row in outliers if row["local_split_evidence"]),
    }


def balance_sensitivity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    positive = [row for row in rows if _float(row.get("ttm_ebit")) is not None and _float(row.get("ttm_ebit")) > 0 and row.get("net_debt_to_ebit") is not None]
    output = []
    for floor in (4.0, 5.0, 6.0):
        values = [float(row["net_debt_to_ebit"]) for row in positive]
        output.append({
            "floor_multiple": floor,
            "observations": len(values),
            "floor_count": sum(value >= floor for value in values),
            "floor_saturation": _fraction(values, lambda value: value >= floor),
            "median_component_points": median(float(balance_points(row, floor) or 0.0) for row in positive) if positive else None,
        })
    return output


def balance_driver_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    positive = [row for row in rows if row.get("net_debt_to_ebit") is not None]
    floor = [row for row in positive if float(row["net_debt_to_ebit"]) >= 4.0]
    comparison = [row for row in positive if float(row["net_debt_to_ebit"]) < 4.0]

    def describe(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        margins = [safe_div(_float(row.get("ttm_ebit")), _float(row.get("ttm_revenue"))) for row in items]
        debt_to_revenue = [safe_div(_float(row.get("net_debt")), _float(row.get("ttm_revenue"))) for row in items]
        return {
            "observations": len(items),
            "ebit_margin_median": percentile(margins, 0.50),
            "ebit_margin_at_or_below_5pct": _fraction(margins, lambda value: value <= 0.05),
            "net_debt_to_revenue_median": percentile(debt_to_revenue, 0.50),
            "net_debt_to_revenue_at_or_above_50pct": _fraction(debt_to_revenue, lambda value: value >= 0.50),
            "net_debt_to_ebit_at_or_above_20x": _fraction([_float(row.get("net_debt_to_ebit")) for row in items], lambda value: value >= 20.0),
        }

    return {
        "positive_ebit_all": describe(positive),
        "net_debt_to_ebit_at_or_above_4x": describe(floor),
        "net_debt_to_ebit_below_4x": describe(comparison),
        "missing_cash_or_total_debt": sum(row.get("cash") is None or row.get("total_debt") is None for row in rows),
    }


def run(paths: ResearchPaths) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=False)
    features = build_features(load_ttm_rows(paths.canonical_db))
    add_legacy_inputs(features)
    summaries = [cross_section_summary(features, cutoff) for cutoff in RESEARCH_CUTOFFS]
    development = [summary for summary in summaries if summary["cutoff"] in DEVELOPMENT_CUTOFFS]
    development_rows = [
        row
        for cutoff in DEVELOPMENT_CUTOFFS
        for row in asof_snapshot(features, cutoff)
        if int(row.get("core_ttm_ready") or 0) == 1 and int(row["snapshot_age_days"]) <= 180
    ]
    consistency_values = [_float(row.get("consistency_points")) for row in development_rows]
    legacy_pairs = [
        (float(row["consistency_points"]), float(row["legacy_consistency_points"]))
        for row in development_rows
        if row.get("consistency_points") is not None and row.get("legacy_consistency_points") is not None
    ]
    dilution = dilution_audit(paths.provider_db, paths.market_db, features)
    dilution_cutoff_medians = [
        percentile([
            _float(row.get("dilution_points"))
            for row in asof_snapshot(features, cutoff)
            if int(row.get("core_ttm_ready") or 0) == 1 and int(row["snapshot_age_days"]) <= 180
        ], 0.50)
        for cutoff in DEVELOPMENT_CUTOFFS
    ]
    consistency_cutoff_medians = [summary["metrics"]["consistency_points"]["p50"] for summary in development]
    summary = {
        "model_version": MODEL_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "database_access": "READ_ONLY",
        "production_database_writes": 0,
        "universe_exclusions_applied": [],
        "universe_exclusion_limitation": "No reliable point-in-time sector, industry, financial-company, or REIT classification exists in the V4 contract.",
        "freshness_rule_applied_days": 180,
        "freshness_rationale": "Two quarterly reporting cycles; development P90 snapshot age is below 70 days and fewer than 1% of TTM-ready rows are excluded at each development cutoff.",
        "methodology_decisions": {
            "consistency": "LOCKED_WITH_CANDIDATE_TOLERANCES_UNCHANGED",
            "balance_floor": "LOCKED_AT_4X",
            "dilution": "BLOCKED_PENDING_SPLIT_NORMALIZED_PERIOD_END_SHARE_HISTORY",
        },
        "research_cutoffs": summaries,
        "development_cutoffs": list(DEVELOPMENT_CUTOFFS),
        "validation_cutoffs": list(VALIDATION_CUTOFFS),
        "forward_2026_inspected": False,
        "development_percentile_ranges": aggregate_percentiles(development),
        "consistency": {
            "tolerances": CONSISTENCY_TOLERANCES,
            "observations": sum(value is not None for value in consistency_values),
            "missing": sum(value is None for value in consistency_values),
            **{f"p{int(q * 100)}": percentile(consistency_values, q) for q in (0.10, 0.25, 0.50, 0.75, 0.90)},
            "zero_saturation": _fraction(consistency_values, lambda value: value <= 0.0),
            "full_saturation": _fraction(consistency_values, lambda value: value >= 10.0),
            "legacy_pair_count": len(legacy_pairs),
            "legacy_pearson_correlation": _pearson(legacy_pairs),
        },
        "balance_sensitivity": balance_sensitivity(development_rows),
        "balance_drivers": balance_driver_summary(development_rows),
        "dilution": {key: value for key, value in dilution.items() if key not in {"outliers", "strata", "sample"}},
        "dilution_semantics": {
            "sharesbas": "period-end basic common shares outstanding",
            "shareswa": "period weighted-average basic shares used for basic EPS",
            "shareswadil": "period weighted-average diluted shares used for diluted EPS",
            "historical_split_adjustment": "NOT_RELIABLY_RECONCILED",
        },
        "imputation_candidates": {
            "consistency_points": median(float(value) for value in consistency_cutoff_medians if value is not None),
            "dilution_points_provisional_blocked": median(float(value) for value in dilution_cutoff_medians if value is not None),
        },
    }
    _write_json(paths.artifact_root / "methodology_summary.json", summary)
    _write_csv(paths.artifact_root / "asof_cross_sections.csv", _flatten_cross_sections(summaries))
    _write_csv(paths.artifact_root / "development_percentile_ranges.csv", summary["development_percentile_ranges"])
    _write_csv(paths.artifact_root / "consistency_examples.csv", consistency_examples(development_rows))
    _write_csv(paths.artifact_root / "balance_sensitivity.csv", summary["balance_sensitivity"])
    _write_csv(paths.artifact_root / "dilution_outlier_strata.csv", dilution["strata"])
    _write_csv(paths.artifact_root / "dilution_outlier_sample.csv", dilution["sample"])
    fingerprints = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths.artifact_root.iterdir())
        if path.is_file()
    }
    _write_json(paths.artifact_root / "artifact_fingerprints.json", fingerprints)
    return summary


def _anchor_bounds(metric: str) -> tuple[float | None, float | None]:
    if metric == "net_debt_to_ebit":
        return None, 4.0
    anchors = ANCHORS.get(metric)
    return (anchors[0][0], anchors[-1][0]) if anchors else (None, None)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _difference(current: float | None, previous: float | None) -> float | None:
    return None if current is None or previous is None else current - previous


def _recent_margin_trend(endpoint_ordinal: int, rows_by_ordinal: Mapping[int, Mapping[str, Any]]) -> str | None:
    ordinals = list(range(endpoint_ordinal - 3, endpoint_ordinal + 1))
    if not all(ordinal in rows_by_ordinal for ordinal in ordinals):
        return None
    margins = [
        safe_div(_float(rows_by_ordinal[ordinal].get("ttm_ebit")), _float(rows_by_ordinal[ordinal].get("ttm_revenue")))
        for ordinal in ordinals
    ]
    if any(value is None for value in margins):
        return None
    changes = [float(current) - float(previous) for previous, current in zip(margins, margins[1:])]
    if all(change > 0 for change in changes):
        return "IMPROVING"
    if all(change < 0 for change in changes):
        return "WEAKENING"
    return "MIXED"


def _fraction(values: Iterable[float | None], predicate: Any) -> float | None:
    observed = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(predicate(value) for value in observed) / len(observed) if observed else None


def _provider_ordinal(value: Any) -> int | None:
    text = str(value or "")
    if "-Q" not in text:
        return None
    year, quarter = text.split("-Q", 1)
    return int(year) * 4 + int(quarter) - 1


def _corroboration(change: float, wa_change: float | None, wadil_change: float | None) -> str:
    supporting = [value for value in (wa_change, wadil_change) if value is not None]
    matched = sum((value > 0) == (change > 0) and abs(value) > 0.50 for value in supporting)
    return f"{matched}_OF_{len(supporting)}"


def _size_bucket(revenue: float | None) -> str:
    if revenue is None:
        return "UNKNOWN"
    if revenue < 100_000_000:
        return "LT_100M"
    if revenue < 1_000_000_000:
        return "100M_TO_1B"
    if revenue < 10_000_000_000:
        return "1B_TO_10B"
    return "GE_10B"


def _dilution_evidence_classification(
    change: float,
    wa_change: float | None,
    wadil_change: float | None,
    actions: Sequence[Mapping[str, Any]],
    splits: Sequence[Mapping[str, Any]],
) -> str:
    action_types = {str(action["action"]).lower() for action in actions}
    if "split" in action_types or splits:
        return "LOCAL_SPLIT_EVIDENCE"
    supporting = [value for value in (wa_change, wadil_change) if value is not None]
    matched = sum((value > 0) == (change > 0) and abs(value) > 0.50 for value in supporting)
    if matched == 2:
        return "ALL_SHARE_FIELDS_CORROBORATE"
    if matched == 1:
        return "ONE_WEIGHTED_FIELD_CORROBORATES"
    return "UNRESOLVED"


def _stratify_outliers(outliers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dimensions = {
        "direction": lambda row: row["direction"],
        "calendar_quarter": lambda row: f"{str(row['reportperiod'])[:4]}Q{(int(str(row['reportperiod'])[5:7]) - 1) // 3 + 1}",
        "security_status": lambda row: "ACTIVE" if row.get("security_active") == 1 else "INACTIVE" if row.get("security_active") == 0 else "UNMATCHED",
        "company_size": lambda row: row["company_size_bucket"],
        "weighted_average_corroboration": lambda row: row["weighted_average_corroboration"],
        "evidence_classification": lambda row: row["evidence_classification"],
    }
    output = []
    for dimension, getter in dimensions.items():
        counts = Counter(getter(row) for row in outliers)
        for value, count in sorted(counts.items()):
            output.append({"dimension": dimension, "value": value, "count": count, "share": count / len(outliers) if outliers else None})
    return output


def _representative_sample(outliers: Sequence[Mapping[str, Any]], limit: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in outliers:
        groups[(str(row["direction"]), str(row["evidence_classification"]))].append(row)
    selected = []
    per_group = max(1, limit // max(1, len(groups)))
    for key in sorted(groups):
        selected.extend(sorted(groups[key], key=lambda row: abs(float(row["sharesbas_change_yoy"])), reverse=True)[:per_group])
    return [dict(row) for row in selected[:limit]]


def _pearson(pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    x_mean, y_mean = mean(xs), mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = math.sqrt(sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def _flatten_cross_sections(summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for summary in summaries:
        for metric, values in summary["metrics"].items():
            rows.append({
                "cutoff": summary["cutoff"],
                "eligible_security_count": summary["eligible_security_count"],
                "ttm_ready_security_count": summary["ttm_ready_security_count"],
                "ready_security_count": summary["ready_security_count"],
                "fresh_180d_count": summary["fresh_180d_count"],
                **{f"age_{key}": value for key, value in summary["snapshot_age_days"].items()},
                "metric": metric,
                **values,
            })
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only Score V1 Phase 1B methodology research")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--timestamp")
    args = parser.parse_args()
    paths = research_paths(args.repo_root.resolve(), args.timestamp)
    run(paths)
    print(paths.artifact_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
